"""Desktop overlay eval (headless: no window is created, no mic, no models).

The pure parts of the orb + cards (state machine, looks, level smoothing, the tick wave, circular hit-testing, card
layout, colours, dismiss timing, capsule width), the no-op API before init(), the audio callback publishing levels,
the voice-loop hooks (thinking → speaking → card → speech ended → listening) and the to-do tick write (only against
a throwaway test DB).
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
s = M.OrbState()
t = s.apply("listening")
check("hidden → listening shows the orb (wake bloom)", t is not None and t.show and not t.hide and t.look.timer)
check("same state again is a no-op (cheap to call often)", s.apply("listening") is None)
t = s.apply("thinking")
check("thinking: no Python timer (render-server comet + tick wave), clickable", not t.look.timer
      and t.look.comet > 0 and t.look.wave > 0 and not t.look.click_through and not t.show)
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
# ================================================================ 2b. the orb: looks, rings, tick wave, hit-testing
print("orb looks")
VIS = ("idle", "listening", "thinking", "speaking")
check("idle is the dimmest, speaking the brightest (glow, rim, ticks)",
      all(getattr(M.LOOKS[a], k) < getattr(M.LOOKS[b], k) for a, b in zip(VIS, VIS[1:]) for k in ("glow", "rim", "ticks")))
check("both rings turn in every visible state, the mid ring slower (and the other way: drawn by orb.py)",
      all(0 < M.LOOKS[k].spin < M.LOOKS[k].counter for k in VIS))
check("idle turns slowly and breathes ~3 s; thinking is the fastest",
      M.LOOKS["idle"].spin >= 10 and 2.5 <= M.LOOKS["idle"].breathe <= 3.5
      and M.LOOKS["thinking"].spin == min(M.LOOKS[k].spin for k in VIS) and M.LOOKS["thinking"].breathe < 1.0)
check("only thinking has the comet (~0.9 s lap) and the render-server tick wave",
      {k for k in VIS if M.LOOKS[k].comet} == {"thinking"} == {k for k in VIS if M.LOOKS[k].wave}
      and M.LOOKS["thinking"].comet == 0.9)
check("her voice moves the ticks more than his mic (gain)", M.LOOKS["speaking"].gain > M.LOOKS["listening"].gain > 0
      and M.LOOKS["idle"].gain == 0 == M.LOOKS["thinking"].gain)
check("look_for without Reduce Motion is the state's own look", all(M.look_for(k) is M.LOOKS[k] for k in M.STATES))
RM = {k: M.look_for(k, reduce_motion=True) for k in M.STATES}
check("Reduce Motion: nothing rotates, travels or breathes in any state",
      all(v.spin == v.counter == v.comet == v.wave == v.breathe == 0 for v in RM.values()))
check("Reduce Motion: thinking is a calm opacity pulse; level, glow and clicks are unchanged",
      RM["thinking"].pulse > 0 and all(RM[k].pulse == 0 for k in M.STATES if k != "thinking")
      and all((RM[k].timer, RM[k].source, RM[k].click_through, RM[k].glow, RM[k].gain)
              == (M.LOOKS[k].timer, M.LOOKS[k].source, M.LOOKS[k].click_through, M.LOOKS[k].glow, M.LOOKS[k].gain)
              for k in M.STATES))
check("a state cross-fades in 150–250 ms", 0.15 <= M.STATE_S <= 0.25 and M.MORPH_S <= 0.3)
check("rings are concentric and never touch: core < inner < mid < ticks < outer arc < rim",
      M.R_CORE * (1 + M.CORE_SWELL) < M.R_INNER < M.R_MID < M.R_TICK
      and M.R_TICK + M.TICK_MAX + 0.75 < M.R_OUTER - 0.75 and M.R_OUTER + 0.75 < M.ORB / 2 - 1 and M.ORB == 64)
d, g = M.dash_pattern(M.R_MID)
check("mid ring: a whole number of dashes fits the circle (no seam)",
      abs(M.MID_DASHES * (d + g) - 2 * math.pi * M.R_MID) < 1e-9 and 0 < d < g)

print("tick wave")
N, W = M.N_TICKS, M.WAVES
check("36 ticks, 10° apart, clockwise from 12 o'clock", N == 36 and M.tick_angle(0) == 0
      and abs(M.tick_angle(9) - math.pi / 2) < 1e-9)
ph = [M.tick_phase(i) for i in range(N)]
check("per-tick phase: rises evenly, wraps once per crest (3 crests around the ring)",
      ph[0] == 0 and all(abs((b - a) - W / N) < 1e-9 for a, b in zip(ph[:N // W - 1], ph[1:N // W]))
      and all(abs(ph[i] - ph[i + N // W]) < 1e-9 for i in range(N - N // W)) and all(0 <= x < 1 for x in ph))
check("silence: every tick at rest, exactly 1.0 (nothing to commit)",
      M.tick_scales(0.0, 1.23) == [1.0] * N and M.tick_scales(-1, 0.5) == [1.0] * N
      and not M.changed_any(M.tick_scales(0.0, 1.0), M.tick_scales(0.0, 2.0)))
loud = M.tick_scales(1.0, 0.37)
check("loud: ticks between rest and the longest tick (0.01 steps), not all the same (a wave)",
      all(1.0 <= x <= M.TICK_MAX / M.TICK_LEN + 0.005 and abs(x * 100 - round(x * 100)) < 1e-6 for x in loud)
      and max(loud) - min(loud) > 0.3
      and max(loud) > 0.95 * M.TICK_MAX / M.TICK_LEN)
crest = lambda t: max(range(N // W), key=lambda i: M.tick_scales(1.0, t)[i])     # noqa: E731
check("the crest travels clockwise around the circle", crest(0.5 / M.WAVE_HZ) == 3 and crest(0.75 / M.WAVE_HZ) == 6
      and crest(1.0 / M.WAVE_HZ) == 9)
check("the same wave on each third of the ring", all(loud[i] == loud[i + N // W] for i in range(N - N // W)))
check("the level sets how far: half as loud = shorter ticks; her gain pushes further",
      max(M.tick_scales(0.5, 0.37)) < max(loud) and max(M.tick_scales(0.5, 0.37, 1.3)) > max(M.tick_scales(0.5, 0.37)))
check("a moving wave is a visible change, a still one is not",
      M.changed_any(M.tick_scales(0.6, 1.0), M.tick_scales(0.6, 1.05))
      and not M.changed_any(loud, list(loud)) and M.changed_any([1.0], [1.0, 1.0]))
dl = [M.tick_delay(i, 0.9) for i in range(N)]
check("thinking: per-tick start delays inside one period, in step with the phase",
      dl[0] == 0 and all(0 <= x < 0.9 for x in dl) and abs(dl[1] - 0.9 * W / N) < 1e-9 and abs(dl[N // W]) < 1e-9)
check("core: 1.0 at rest → 1.6 at full level, clamped",
      M.core_scale(0.0) == 1.0 and M.core_scale(1.0) == 1.6 and M.core_scale(5.0) == 1.6 and M.core_scale(0.5, 1.3) == 1.39)
sv = M.sine_values(0.86, 1.14)
check("breathing loop: starts and ends at the low point, peaks in the middle, no jump at the seam",
      sv[0] == sv[-1] == 0.86 and abs(max(sv) - 1.14) < 1e-9 and sv.index(max(sv)) == len(sv) // 2)
check("…and a new loop picks up where the old one was (phase of the current value)",
      M.sine_phase(0.86, 0.86, 1.14) == 0 and abs(M.sine_phase(1.14, 0.86, 1.14) - 0.5) < 1e-9
      and abs(M.sine_phase(1.0, 0.86, 1.14) - 0.25) < 1e-9 and M.sine_phase(9, 0.86, 1.14) == 0.5
      and M.sine_phase(1, 1, 1) == 0)
check("commit only when something moved", not M.changed(1.0, 1.005) and M.changed(1.0, 1.02))

print("shapes + displays")
R = M.ORB / 2
k = math.sqrt(0.5)
check("orb hit-test is a circle: centre in, the square's corners out",
      M.in_orb(R, R) and not M.in_orb(4, 4) and not M.in_orb(M.ORB - 4, 4) and not M.in_orb(4, M.ORB - 4)
      and not M.in_orb(M.ORB - 4, M.ORB - 4))
check("…exactly the disc: just inside the rim in, just outside out, in every direction",
      all(M.in_orb(R + (R - 0.5) * math.cos(a), R + (R - 0.5) * math.sin(a))
          and not M.in_orb(R + (R + 0.5) * math.cos(a), R + (R + 0.5) * math.sin(a))
          for a in [i * math.pi / 8 for i in range(16)]))
check("…and nothing beside the disc (the glow is not clickable)", not M.in_orb(-1, R) and not M.in_orb(M.ORB + 1, R)
      and not M.in_orb(100, R) and M.in_orb(R + (R - 1) * k, R + (R - 1) * k))
check("as a capsule: the label part is in, the rounded ends' corners are out",
      M.in_orb(200, 5, 246) and M.in_orb(120, R, 246) and not M.in_orb(243, 3, 246) and not M.in_orb(3, 3, 246)
      and not M.in_orb(250, R, 246))
check("card hit-test: rounded corners out", M.in_round_rect(190, 140, 380, 280, M.CARD_RADIUS)
      and not M.in_round_rect(2, 2, 380, 280, M.CARD_RADIUS) and M.CARD_RADIUS == 20)
FR = [(0, 0, 1440, 900), (1440, 0, 1920, 1080)]
check("pointer's display, else the nearest one", M.screen_index(FR, (100, 100)) == 0
      and M.screen_index(FR, (2000, 500)) == 1 and M.screen_index(FR, (5000, 500)) == 1
      and M.screen_index(FR, (-50, 10)) == 0 and M.FOLLOW_S == 0.4)


def lum(c):                                    # WCAG relative luminance of an sRGB colour
    f = lambda v: v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4     # noqa: E731
    r, g_, b_ = (f(x / 255) for x in c)
    return 0.2126 * r + 0.7152 * g_ + 0.0722 * b_


def over(fg, a, bg):                           # fg at alpha a over bg
    return tuple(a * x + (1 - a) * y for x, y in zip(fg, bg))


def contrast(c1, c2):
    hi, lo = sorted((lum(c1), lum(c2)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


print("colours")
check("card and disc are opaque (alpha ≥ 0.94): what is behind never muddies them",
      M.CARD_A >= 0.94 and M.DISC_A >= 0.94 and M.CARD_A <= 1 and M.DISC_A <= 1)
check("always dark; the default theme is the knot orb's: indigo card, amber accent, rice-white hairline",
      lum(M.CARD) < 0.02 and lum(M.DISC) < 0.02 and lum(M.INDIGO) < 0.02 and M.apply_theme("knot") == "knot"
      and M.CARD == (0x12, 0x10, 0x32) and M.ACCENT == M.AMBER == (0xF4, 0xB4, 0x00) and M.HAIR == M.RICE)
check("the reactor theme keeps the D44 blues", M.apply_theme("reactor") == "reactor" and M.CARD == (0x0B, 0x10, 0x26)
      and M.ACCENT == M.SKY == (0x7F, 0xB2, 0xF0) and M.ACCENT_DEEP == M.BLUE and M.HAIR == M.SKY)
M.apply_theme("knot")
worst = over(M.CARD, M.CARD_A, M.WHITE)        # the card over a pure white window
check("text contrast on the card, even over a white window: rows ≥ 7:1, meta + eyebrow ≥ 4.5:1",
      contrast(over(M.WHITE, M.ROW_A, worst), worst) >= 7 and contrast(over(M.WHITE, M.TEXT_A, worst), worst) >= 7
      and contrast(over(M.WHITE, M.META_A, worst), worst) >= 4.5 and contrast(M.ACCENT, worst) >= 4.5,
      f"{contrast(over(M.WHITE, M.META_A, worst), worst):.2f}")
check("text alphas 96 / 90 / 50 %, hairline 28–35 %", (M.TEXT_A, M.ROW_A, M.META_A) == (0.96, 0.90, 0.50)
      and 0.28 <= M.HAIR_A <= 0.35)
ghost = contrast(over(M.CARD, M.CARD_A, M.WHITE), over(M.CARD, M.CARD_A, (0, 0, 0)))
check("text on a window behind the card cannot be read through it (ghost contrast < 1.05:1)", ghost < 1.05, f"{ghost:.3f}")

# ================================================================ 3. card layout
print("card layout")
TODOS = {"kind": "todos", "title": "5 things to do", "ts": 0, "items": [
    {"id": i, "text": f"Task {i}", "meta": "due today, 4 PM" if i == 1 else ""} for i in range(1, 6)]}
L5 = M.layout(TODOS)
check("todos: 5 rows, all tickable, count in the eyebrow, 'You have these to complete'",
      L5.n == 5 and all(r.tickable for r in L5.rows) and L5.eyebrow == "TO-DO · 5 OPEN" and L5.more == 0
      and L5.title == "You have these to complete")
check("rows stack top-down without overlap", all(b.y == a.y + a.h for a, b in zip(L5.rows, L5.rows[1:])))
check("width 380, height fits title + 5 rows of 34", L5.width == 380 and 230 < L5.height < 280 and M.ROW_H == 34
      and L5.height == L5.rows[-1].y + M.ROW_H + M.PAD_BOTTOM, f"{L5.height}")
check("'due today, 4 PM' is shown as 'today, 4 PM' (the eyebrow says TO-DO)", L5.rows[0].meta == "today, 4 PM"
      and M.row_meta("reminders", "due soon") == "due soon" and M.row_meta("todos", "") == "")
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
n2 = M.layout({"kind": "news", "title": "AI", "items": [{"id": None, "text": "Short one", "meta": "HN"},
                                                        {"id": None, "text": "y" * 70, "meta": "HN"},
                                                        {"id": None, "text": "Another short one", "meta": "HN"}]})
check("news: a long headline gets a second line and a taller row; rows still stack without overlap",
      [r.lines for r in n2.rows] == [1, 2, 1] and n2.rows[1].h == M.NEWS_ROW_H + M.NEWS_LINE_H
      and n2.rows[0].h == M.NEWS_ROW_H and all(b.y == a.y + a.h for a, b in zip(n2.rows, n2.rows[1:])))
n3 = M.layout({"kind": "news", "title": "AI", "items": [{"id": None, "text": "Short one", "meta": "HN"}]},
              measure=lambda text: 7)
check("news: the real text measure (AppKit) wins over the guess, capped at two lines",
      n3.rows[0].lines == 2 and M.layout(TODOS, measure=lambda text: 2).rows[0].lines == 1)
rem = M.layout({"kind": "reminders", "title": "Coming up", "items": [{"id": 3, "text": "Alarm", "meta": "today, 7 AM"}]})
check("reminders: not tickable (cancel is by voice), eyebrow ≠ title",
      rem.n == 1 and not rem.rows[0].tickable and rem.eyebrow == "REMINDERS · 1" and rem.title == "Coming up")
check("todo_added / reminder_set don't open a card (orb confirmation)",
      M.layout({"kind": "todo_added", "items": [{"id": 1, "text": "x"}]}) is None
      and M.layout({"kind": "reminder_set", "items": []}) is None and M.layout({}) is None)
bad = M.layout({"kind": "todos", "title": "2 things to do", "items": [None, {"id": "7", "text": " "}, {"id": 2, "text": "ok"}]})
check("junk items dropped, non-int ids not tickable", bad.n == 1 and bad.rows[0].id == 2)
check("long to-do text clipped to one line", len(M.layout({"kind": "todos", "title": "1 thing to do",
                                                         "items": [{"id": 1, "text": "y" * 300}]}).rows[0].text) <= 60)

# ================================================================ 4. orb confirmation + capsule width
print("orb confirmation")
check("confirm text: item · when (no 'due ')",
      M.confirm_text({"items": [{"text": "Start resume", "meta": "due today, 4 PM"}]}) == "Start resume · today, 4 PM")
check("confirm text without meta / without items",
      M.confirm_text({"items": [{"text": "Call home", "meta": ""}]}) == "Call home"
      and M.confirm_text({"title": "Alarm set", "items": []}) == "Alarm set")
check("confirm text clipped", M.confirm_text({"items": [{"text": "z" * 100}]}).endswith("…"))
check("capsule: no label = the disc alone (64); a label widens it by exactly what it needs, ≤ 340",
      M.capsule_width(0) == M.ORB == 64 and M.capsule_width(-5) == M.ORB
      and M.capsule_width(120) == M.ORB + M.CAP_GAP + M.CAP_SYM + 120 + M.CAP_PAD
      and M.ORB < M.capsule_width(100) < M.capsule_width(150) <= M.ORB_MAX_W == 340)
check("capsule width clamps; without an icon it is narrower",
      M.capsule_width(1000) == M.ORB_MAX_W and M.capsule_width(120, symbol=False) == M.capsule_width(120) - M.CAP_SYM)

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
check("on_ack → the orb says what she's doing", ("set_state", "thinking", "calendar") in calls, str(calls))
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

print("knot orb (preview style)")
kp = M.knot_points()
check("the knot is one closed line inside the unit circle", len(kp) == M.KNOT_N and max(math.hypot(x, y) for x, y in kp) <= 1.0 + 1e-9)
ko = M.knot_overs(kp)
check("it crosses itself three times, evenly spaced, one stretch passes over at each",
      len(ko) == 3 and len({(b - a) for a, b in ko}) == 1 and {(ko[k + 1][0] - ko[k][0]) for k in range(2)} == {M.KNOT_N // 3}, str(ko))
check("the knot and its ring fit inside the disc", M.R_KNOT < M.R_KNOT_RING < M.ORB / 2)
os.environ.pop("STITI_ORB", None)
check("the knot is the default orb", M.orb_style() == "knot")
os.environ["STITI_ORB"] = "reactor"
check("STITI_ORB=reactor brings the D44 reactor back", M.orb_style() == "reactor")
os.environ.pop("STITI_ORB")
check("the wake greeting uses what she calls him", M.greeting("Sam") == "Hey Sam, what's on your mind?"
      and M.greeting(None) == M.greeting("you") == "Hey, what's on your mind?")

print(f"overlay: {passed}/{total} checks passed")
sys.exit(0 if passed == total else 1)
