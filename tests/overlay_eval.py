"""Desktop overlay eval (headless: no window is created, no mic, no models).

The pure parts of the pill + cards (state machine, level smoothing, card layout, dismiss timing, pill width), the
no-op API before init(), the audio callback publishing levels, the voice-loop hooks (thinking → speaking → card →
speech ended → listening) and the to-do tick write (only against a throwaway test DB).
"""
from __future__ import annotations

import math
import os
import sys
import tempfile
import threading
import time
from pathlib import Path

import numpy as np

os.environ.setdefault("STITI_HOME", tempfile.mkdtemp())
os.environ.setdefault("STITI_STT_BIAS", "off")

from stiti import overlay                                              # noqa: E402
from stiti.overlay import model as M                                   # noqa: E402

passed = total = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global passed, total
    total += 1
    passed += bool(cond)
    print(("  ✓ " if cond else "  ✗ ") + name + (f" — {detail}" if detail and not cond else ""))


# ================================================================ 1. state machine
print("state machine")
s = M.PillState()
t = s.apply("listening")
check("hidden → listening shows the pill (wake bloom)", t is not None and t.show and not t.hide and t.look.timer)
check("same state again is a no-op (cheap to call often)", s.apply("listening") is None)
t = s.apply("thinking")
check("thinking: no Python timer (render-server ripple), clickable", not t.look.timer and t.look.anim == "wave"
      and not t.look.click_through and not t.show)
t = s.apply("thinking", "calendar")
check("thinking + detail is a change (label 'Checking calendar')", t is not None and t.detail == "calendar")
t = s.apply("speaking")
check("the doing label stays while she speaks in the same turn", t.detail == "calendar" and t.look.source == "out")
t = s.apply("listening")
check("…and clears when the turn ends", t.detail is None and t.look.source == "mic" and t.look.click_through)
t = s.apply("speaking")
check("speaking straight from listening has no stale label", t.detail is None)
t = s.apply("hidden")
check("→ hidden hides (and closes cards)", t.hide and not t.show and not t.look.visible)
try:
    s.apply("dancing")
    check("unknown state refused", False)
except ValueError:
    check("unknown state refused", True)
check("only listening / speaking need the 30 Hz timer",
      {k for k, v in M.LOOKS.items() if v.timer} == {"listening", "speaking"})
check("click-through while idle / listening (never eats a menu-bar click)",
      M.LOOKS["listening"].click_through and M.LOOKS["idle"].click_through and M.LOOKS["hidden"].click_through)
check("doing labels for every on_ack kind", all(M.doing_label(k) for k in ("calendar", "mail", "plan", "tools", "web"))
      and M.doing_label("weird") is None and M.doing_label(None) is None)

# ================================================================ 2. level meter (Wispr Flow's level path)
print("level meter")
lm = M.LevelMeter(**M.METER["mic"])
check("dBFS: 0.1 rms = -20 dB, silence / NaN / negative = -200", abs(lm.db(0.1) + 20) < 1e-6
      and lm.db(0.0) == -200 and lm.db(float("nan")) == -200 and lm.db(-1) == -200)
check("floor starts at -60 dB with a 20 dB range", lm.floor == -60 and lm.target(0.01) == 1.0
      and abs(lm.target(10 ** (-50 / 20)) - 0.5) < 1e-6 and lm.target(10 ** (-65 / 20)) == 0.0)
t = 0.0
for _ in range(30):
    t += 1 / 30
    lm.step(10 ** (-68 / 20), t)                   # quiet room
check("floor follows the quietest level heard", abs(lm.floor + 68) < 1e-3 and lm.value == 0.0, f"{lm.floor:.1f}")
for _ in range(60):
    t += 1 / 30
    lm.step(10 ** (-68 / 20), t)
check("a steady room keeps a steady floor", abs(lm.floor + 68) < 1e-3, f"{lm.floor}")
for _ in range(60):
    t += 1 / 30
    lm.step(0.05, t)                                # 2 s of speech
check("…which creeps up only slowly while he talks (0.5 dB/s)", -67.1 < lm.floor < -66.9, f"{lm.floor:.2f}")
lm2 = M.LevelMeter(floor_min=-75, floor_max=-35)
for _ in range(10):
    lm2.step(1e-9, 0.0)
check("floor is clamped (AEC digital silence can't push it to -200)", lm2.floor == -75)
lm = M.LevelMeter(**M.METER["mic"])
vals, t = [], 0.0
for _ in range(15):
    t += 1 / 30
    vals.append(lm.step(0.05, t))                   # loud speech
steps = [b - a for a, b in zip([0.0] + vals, vals)]
check("slew limit: rises ≤ 1.6/s (≈0.053 per 30 fps frame)", max(steps) <= 1.6 / 30 + 0.011, f"{max(steps):.3f}")
check("rises steadily toward 1 while he talks", vals[-1] > 0.6 and all(b >= a for a, b in zip(vals, vals[1:])), f"{vals}")
for _ in range(90):
    t += 1 / 30
    lm.step(0.0, t)
check("returns to exactly 0 in silence (the timer can idle)", lm.value == 0.0)
la, lb = M.LevelMeter(**M.METER["mic"]), M.LevelMeter(**M.METER["mic"])
ta = tb = 0.0
la.step(0.02, 0.0)
lb.step(0.02, 0.0)
for _ in range(12):
    ta += 1 / 60
    la.step(0.02, ta)
for _ in range(6):
    tb += 1 / 30
    lb.step(0.02, tb)
check("frame-rate independent smoothing (60 vs 30 fps ≈ same)", abs(la.value - lb.value) <= 0.06,
      f"{la.value} vs {lb.value}")
check("output always 0..1 in 0.01 steps", all(0 <= v <= 1 and abs(v * 100 - round(v * 100)) < 1e-6 for v in vals))
check("her voice meter: floor stays within -40..-25 dB", M.METER["out"]["floor_min"] == -40)
sc = M.dot_scales(1.0)
check("dots: centre bulge 1 − d²/48, symmetric, 1.0 at rest",
      sc[3] == max(sc) and sc[0] == sc[6] and sc[1] == sc[5] and M.dot_scales(0.0) == [1.0] * 7
      and M.bulge(3) == 1.0 and abs(M.bulge(0) - (1 - 4.5 ** 2 / 48)) < 1e-9)
keys, delay = M.shimmer(3)
k0, d0 = M.shimmer(0)
check("shimmer: 1 s keyframes ×1→1.2→1.5→1.1→1.3→1, 0.1 s per dot from the centre",
      keys == M.SHIMMER_KEYS and delay == 0.0 and abs(d0 - 0.3) < 1e-9 and max(k0) < 1.5 and k0[0] == k0[-1] == 1.0
      and M.SHIMMER_TIMES == [0.0, 0.2, 0.4, 0.8, 0.9, 1.0])
check("state transitions 100 ms on Flow's curve", M.STATE_S == 0.1 and M.STATE_EASE == (0.05, 0.6, 0.4, 0.95))
check("commit only when the swell moved", not M.changed(1.0, 1.005) and M.changed(1.0, 1.02))

print("shapes + displays")
check("capsule hit-test: centre in, corners out", M.in_round_rect(84, 20, 168, 40, 20)
      and not M.in_round_rect(1, 1, 168, 40, 20) and not M.in_round_rect(167, 39, 168, 40, 20)
      and M.in_round_rect(20, 1, 168, 40, 20) and not M.in_round_rect(-1, 20, 168, 40, 20))
check("card hit-test: rounded corners out", M.in_round_rect(180, 140, 360, 280, 18) and not M.in_round_rect(2, 2, 360, 280, 18))
FR = [(0, 0, 1440, 900), (1440, 0, 1920, 1080)]
check("pointer's display, else the nearest one", M.screen_index(FR, (100, 100)) == 0
      and M.screen_index(FR, (2000, 500)) == 1 and M.screen_index(FR, (5000, 500)) == 1
      and M.screen_index(FR, (-50, 10)) == 0 and M.FOLLOW_S == 0.4)

# ================================================================ 3. card layout
print("card layout")
TODOS = {"kind": "todos", "title": "5 things to do", "ts": 0, "items": [
    {"id": i, "text": f"Task {i}", "meta": "due today, 4 PM" if i == 1 else ""} for i in range(1, 6)]}
L5 = M.layout(TODOS)
check("todos: 5 rows, all tickable, count in the eyebrow, 'You have these to complete'",
      L5.n == 5 and all(r.tickable for r in L5.rows) and L5.eyebrow == "TO-DO · 5 OPEN" and L5.more == 0
      and L5.title == "You have these to complete")
check("rows stack top-down without overlap", all(b.y == a.y + a.h for a, b in zip(L5.rows, L5.rows[1:])))
check("width 360, height fits title + 5 rows", L5.width == 360 and 240 < L5.height < 300, f"{L5.height}")
check("row_at maps a click to its row", M.row_at(L5, L5.rows[2].y + 5) == 2 and M.row_at(L5, 1) is None)
many = {"kind": "todos", "title": "12 things to do", "items": [{"id": i, "text": f"T{i}", "meta": ""} for i in range(8)]}
L8 = M.layout(many)
check("≤ 6 rows, then '+N more' (count from the brain's total)", L8.n == 6 and L8.more == 6, f"n={L8.n} more={L8.more}")
check("'+N more' line adds height", L8.height > M.layout({**many, "title": "8 things to do"}).height - 1)
empty = M.layout({"kind": "todos", "title": "Nothing on your list", "items": []})
check("empty list: the brain's title only, small card",
      empty.n == 0 and empty.height < 100 and empty.eyebrow == "TO-DO" and empty.title == "Nothing on your list")
news = M.layout({"kind": "news", "title": "AI updates", "items": [{"id": None, "text": "x" * 200, "meta": "HN"}]})
check("news: 380 wide, not tickable, long headline clipped",
      news.width == 380 and not news.rows[0].tickable and len(news.rows[0].text) <= 90)
rem = M.layout({"kind": "reminders", "title": "Coming up", "items": [{"id": 3, "text": "Alarm", "meta": "today, 7 AM"}]})
check("reminders: not tickable (cancel is by voice), eyebrow ≠ title",
      rem.n == 1 and not rem.rows[0].tickable and rem.eyebrow == "REMINDERS · 1" and rem.title == "Coming up")
check("todo_added / reminder_set don't open a card (pill confirmation)",
      M.layout({"kind": "todo_added", "items": [{"id": 1, "text": "x"}]}) is None
      and M.layout({"kind": "reminder_set", "items": []}) is None and M.layout({}) is None)
bad = M.layout({"kind": "todos", "title": "2 things to do", "items": [None, {"id": "7", "text": " "}, {"id": 2, "text": "ok"}]})
check("junk items dropped, non-int ids not tickable", bad.n == 1 and bad.rows[0].id == 2)
check("long to-do text clipped to one line", len(M.layout({"kind": "todos", "title": "1 thing to do",
                                                         "items": [{"id": 1, "text": "y" * 300}]}).rows[0].text) <= 60)

# ================================================================ 4. pill confirmation + width
print("pill confirmation")
check("confirm text: item · when (no 'due ')",
      M.confirm_text({"items": [{"text": "Start resume", "meta": "due today, 4 PM"}]}) == "Start resume · today, 4 PM")
check("confirm text without meta / without items",
      M.confirm_text({"items": [{"text": "Call home", "meta": ""}]}) == "Call home"
      and M.confirm_text({"title": "Alarm set", "items": []}) == "Alarm set")
check("confirm text clipped", M.confirm_text({"items": [{"text": "z" * 100}]}).endswith("…"))
check("pill width: compact 168, grows with the label, ≤ 320",
      M.pill_width(0) == 168 and 168 < M.pill_width(100) < M.pill_width(150) <= M.PILL_MAX_W)
check("pill width clamps", M.pill_width(1000) == M.PILL_MAX_W and M.pill_width(120, with_dots=False) < M.pill_width(120))

# ================================================================ 5. dismiss timer
print("dismiss timer")
d = M.DismissTimer("todos", 5, now=100.0)
check("not due while she is still speaking", not d.due(110.0))
d.speech_ended(110.0)
check("due 4 s + 1.2 s × rows after her speech ends", not d.due(119.9) and d.due(120.0), f"{d.remaining(110.0)}")
check("capped at 15 s", M.dismiss_after("todos", 30) == 15.0)
check("news 8 s, confirmation 2.5 s", M.dismiss_after("news", 4) == 8.0 and M.dismiss_after("todo_added", 1) == 2.5)
d = M.DismissTimer("todos", 1, now=0.0, speaking=False)
check("shown without speech → the clock starts at once", d.due(5.2) and not d.due(5.1))
d = M.DismissTimer("todos", 1, now=0.0)
d.speech_ended(1.0)
d.hover(True, 3.0)
check("hovering pauses it", not d.due(100.0))
d.hover(False, 100.0)
check("leaving resumes with what was left (≥ 1.5 s)", not d.due(102.0) and d.due(103.2))
d = M.DismissTimer("todos", 1, now=0.0)
d.hover(True, 0.5)
d.speech_ended(1.0)
d.hover(False, 50.0)
check("speech ended while hovered → full time after leaving", not d.due(55.1) and d.due(55.3))
d = M.DismissTimer("todos", 1, now=0.0)
d.speech_ended(1.0)
d.speech_ended(9.0)
check("a second speech_ended doesn't extend it", d.due(6.3))
check("failsafe: closes after 60 s if speech never ends", M.DismissTimer("todos", 1, 0.0).due(60.0))

# ================================================================ 6. API before init
print("API without a display (not initialised)")
check("not active", not overlay.active())
try:
    overlay.set_state("listening")
    overlay.set_state("bogus")
    overlay.show_card({"kind": "todos", "items": []})
    overlay.show_card(None)
    overlay.hide_card()
    overlay.speech_ended()
    overlay.set_click_handler(lambda: None)
    overlay.set_enabled(False)
    overlay.set_enabled(True)
    overlay.shutdown()
    check("every call is a silent no-op", True)
except Exception as e:
    check("every call is a silent no-op", False, f"{type(e).__name__}: {e}")
r = []
th = threading.Thread(target=lambda: r.append(overlay.init()))
th.start()
th.join()
check("init() off the main thread refuses (AppKit is main-thread only)", r == [False] and not overlay.active())
overlay.level(0.25, 0.5)
check("level() just stores two floats", overlay._lv == [0.25, 0.5])

# ================================================================ 7. audio callback publishes levels
print("audio callback")
from stiti.voice.duplex import Duplex                                   # noqa: E402

dx = Duplex.__new__(Duplex)
dx._init_playback()
dx.on_mic = lambda x: None
tone = (0.2 * np.sin(np.arange(4800) / 48000 * 2 * math.pi * 220)).astype(np.float32)
dx.play(tone, 48000)
frames = 320                                   # != BLOCK: skips the APM (no sound device / livekit needed)
mic_in = np.full((frames, 1), 0.05, np.float32)
outs = []
overlay.level(0.0, 0.0)
for k in range(5):                             # 1,600 samples < 40 ms: nothing published yet
    out_buf = np.zeros((frames, 1), np.float32)
    dx._cb(mic_in, out_buf, frames, None, None)
    outs.append(out_buf[:, 0].copy())
check("levels wait for a full 40 ms block", overlay._lv == [0.0, 0.0] and dx._lv_n == 1600)
out_buf = np.zeros((frames, 1), np.float32)
dx._cb(mic_in, out_buf, frames, None, None)
outs.append(out_buf[:, 0].copy())
allout = np.concatenate(outs)
want_out = float(np.sqrt(np.mean(allout ** 2)))
check("out RMS over the 40 ms block = her voice level", abs(dx.out_rms - want_out) < 1e-5 and dx.out_rms > 0.1,
      f"{dx.out_rms:.4f} vs {want_out:.4f}")
check("mic RMS = his (cleaned) voice level", abs(dx.mic_rms - 0.05) < 1e-4, f"{dx.mic_rms:.4f}")
check("published to the overlay, block restarted", overlay._lv == [dx.mic_rms, dx.out_rms] and dx._lv_n == 0)
dx._cb(np.zeros((0, 1), np.float32), np.zeros((0, 1), np.float32), 0, None, None)
check("an empty block doesn't divide by zero", True)

# ================================================================ 8. voice-loop hooks
print("voice loop hooks")
from stiti.voice import endpoint as E                                   # noqa: E402
from stiti.voice import loop as L                                       # noqa: E402

calls: list[tuple] = []
for name in ("set_state", "show_card", "speech_ended", "hide_card"):
    setattr(overlay, name, (lambda n: lambda *a, **k: calls.append((n,) + a))(name))


class FakeTTS:
    def synth_on_worker(self, text, mood):
        return np.ones(int(0.05 * 24000), np.float32), 24000


class CardEngine:
    def __init__(self, card_ts_offset: float = 0.0, ack: str | None = None):
        self.last_mood, self.streamed, self.last_debug = "calm", False, {}
        self.last_route, self.last_action, self.last_card = "fast_path", None, None
        self.off, self.ack = card_ts_offset, ack

    def turn(self, text, voice_emotion=None, on_delta=None, on_ack=None):
        if self.ack:
            on_ack(self.ack)
        self.last_card = {"kind": "todos", "title": "1 thing to do", "items": [{"id": 1, "text": "x", "meta": ""}],
                          "ts": time.time() + self.off}
        return "You have one thing to do."


vl = L.VoiceLoop.__new__(L.VoiceLoop)
vl.engine, vl.debug, vl.tts, vl.acks, vl.fillers, vl.ack_text = CardEngine(), False, FakeTTS(), {}, [], {}
vl._interrupted, vl._resume, vl._work, vl.last_activity = threading.Event(), None, None, 0.0
vl.awake, vl.silenced = True, False
vl.duplex = Duplex.__new__(Duplex)
vl.duplex._init_playback()
vl.stats = E.TurnStats(Path(tempfile.mkdtemp()) / "t.json")
vl.tt = E.TurnTaker(vl.stats, None, None)
stop_pump = threading.Event()


def pump():
    while not stop_pump.is_set():
        vl.duplex._pull(480)
        time.sleep(0.01)


threading.Thread(target=pump, daemon=True).start()
vl._handle("What's on my to-do list?", None, None)
vl._wait_work()
names = [c[0] if c[0] != "set_state" else f"state:{c[1]}" for c in calls]
check("thinking → speaking → … → speech ended → listening",
      names[0] == "state:thinking" and "state:speaking" in names and names[-2:] == ["speech_ended", "state:listening"],
      str(names))
check("this turn's card is shown, before her speech ends",
      "show_card" in names and names.index("show_card") < names.index("speech_ended"), str(names))
check("the card is the brain's dict (kind/title/items)", any(c[0] == "show_card" and c[1]["kind"] == "todos" for c in calls))
calls.clear()
vl.engine = CardEngine(card_ts_offset=-3600)
vl._handle("hmm", None, None)
vl._wait_work()
check("a stale card from an earlier turn is not re-shown", not any(c[0] == "show_card" for c in calls), str(calls))
calls.clear()
vl.acks, vl.ack_text = {"calendar": (np.ones(1200, np.float32), 24000)}, {"calendar": "Checking your calendar."}
vl.engine = CardEngine(ack="calendar")
vl._handle("what's on my calendar", None, None)
vl._wait_work()
check("on_ack → the pill says what she's doing", ("set_state", "thinking", "calendar") in calls, str(calls))
calls.clear()
vl.say("Hello.")
check("say() while awake: speaking → listening", [c[1] for c in calls if c[0] == "set_state"] == ["speaking", "listening"])
calls.clear()
vl.awake = False
vl.say("A nudge.", nudge=True)
check("asleep: a nudge puts nothing on screen", calls == [], str(calls))
vl.awake = True
vl._chime = lambda up: None
vl.deactivate()
check("stop word → hidden", ("set_state", "hidden") in calls)
stop_pump.set()

# ================================================================ 9. tick a to-do (throwaway DB only)
print("tick a to-do in the brain")
dbu = os.getenv("STITI_DB", "")
if not dbu or dbu.rstrip("/").endswith("/stiti"):
    print("  (skipped: needs STITI_DB pointing at a throwaway test DB)")
else:
    from stiti.db import one, q                                         # noqa: E402
    from stiti.overlay.ui import _db_tick                               # noqa: E402
    tid = one("INSERT INTO tasks(title) VALUES ('overlay test task') RETURNING id")["id"]
    _db_tick(tid, True)
    check("click → status done", one("SELECT status FROM tasks WHERE id=%s", (tid,))["status"] == "done")
    _db_tick(tid, False)
    check("click again → open again", one("SELECT status FROM tasks WHERE id=%s", (tid,))["status"] == "open")
    q("UPDATE tasks SET status='cancelled' WHERE id=%s", (tid,))
    _db_tick(tid, True)
    check("never revives a cancelled task", one("SELECT status FROM tasks WHERE id=%s", (tid,))["status"] == "cancelled")

print(f"overlay: {passed}/{total} checks passed")
sys.exit(0 if passed == total else 1)
