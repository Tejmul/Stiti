"""Real-time conversation eval (D29), offline: no mic, no models besides the embedder, no real LLM, no real music.

1. ● ◐ ○ turn markers: parsing + stripping (whole replies and streamed deltas split anywhere, missing, garbled).
2. Engine: markers never reach speech / memory / web; ◐ drops the reply; speculative turns hold every DB write —
   a discarded speculation leaves no episode, turn, decision or lesson score, a committed one is a normal turn;
   fast paths are never speculated.
3. Speculator (fake engine timings): buffered until commit, replayed in order, dropped on "he went on", budget.
4. TurnTaker events: speech_start / speculate / unspeculate (opt-in), and a ◐ fragment is joined to his next words.
5. Realtime glue: pre-warm on speech start (de-duplicated), "Mm-hm?" after 5 s, adoption through turn().
6. Latency: the same simulated turn with and without preemptive start.
7. Media pause decisions with a mocked AppleScript runner.
Run against a throwaway DB (tests/run_all.sh does that).
"""
from __future__ import annotations

import os
import sys
import tempfile
import threading
import time
from pathlib import Path

os.environ.setdefault("STITI_HOME", tempfile.mkdtemp())
os.environ.setdefault("STITI_STT_BIAS", "off")
os.environ["STITI_MEDIA_PAUSE"] = "off"          # never touch the owner's music from a test

from stiti import router                                              # noqa: E402
from stiti.brain import turnmark as TM                                # noqa: E402
from stiti.voice import endpoint as E                                 # noqa: E402
from stiti.voice import media as M                                    # noqa: E402
from stiti.voice import realtime as R                                 # noqa: E402
from stiti.voice.stt import STTResult                                 # noqa: E402

passed = total = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global passed, total
    total += 1
    passed += bool(cond)
    print(("  ✓ " if cond else "  ✗ ") + name + (f" — {detail}" if detail and not cond else ""))


def streamed(parts: list[str]) -> tuple[str | None, str]:
    ms = TM.MarkerStream()
    out = "".join(ms.feed(p) for p in parts) + ms.flush()
    return ms.marker, out


# ================================================================ 1. markers
print("1. turn-completion markers ● ◐ ○")
check("split: '● Sure, 4 PM.' → ●, text", TM.split("● Sure, 4 PM.") == ("●", "Sure, 4 PM."))
check("split: '◐' alone → ◐, ''", TM.split("◐") == ("◐", ""))
check("split: '○ ' → ○", TM.split("○ ")[0] == "○")
check("split: no marker → None (counts as ●), text untouched", TM.split("Sure thing.") == (None, "Sure thing."))
check("split: dressed '[●] ok' / '**◐**' / 'Marker: ●'",
      TM.split("[●] ok") == ("●", "ok") and TM.split("**◐**")[0] == "◐" and TM.split("Marker: ● hi") == ("●", "hi"))
check("split: lookalike glyphs ⬤ ◑ ◯", [TM.split(x)[0] for x in ("⬤ a", "◑", "◯")] == ["●", "◐", "○"])
check("stray marker mid-text is removed", "●" not in TM.strip("● Done ● for today.") and "◐" not in TM.strip("ok ◐"))
txt = "● Sure, four PM it is."
check("stream split char-by-char", streamed(list(txt)) == ("●", "Sure, four PM it is."), str(streamed(list(txt))))
check("stream: '', ' ', '●', ' Sure'", streamed(["", " ", "●", " Sure", "."]) == ("●", "Sure."))
check("stream: only ◐ (with newline) → ◐, nothing spoken", streamed(["◐", "\n"]) == ("◐", "")
      and streamed(["  ", "◐"]) == ("◐", ""))
check("stream: no marker → passes through unchanged", streamed(["Main ", "dekh ", "rahi hoon."]) == (None, "Main dekh rahi hoon."))
check("stream: dressing split across chunks '**●' + '** Hi'", streamed(["**●", "** Hi"]) == ("●", "Hi"))
check("stream: garbled opener ('[x] hi') → treated as ●, nothing lost", streamed(["[x", "] hi"]) == (None, "[x] hi"))
ms = TM.MarkerStream()
ms.feed("◐")
ms.feed(" ")
check("stream: ◐ decided as soon as anything follows (LLM can be stopped)", ms.incomplete)

# ================================================================ 2. engine (real DB, fake LLM)
print("2. engine: markers stripped everywhere, speculative turns hold their writes")
from stiti import profile                                             # noqa: E402
from stiti.db import one                                              # noqa: E402
from stiti.engine import Engine, NotSpeculable                        # noqa: E402

profile.set("intro_offer", "off", "owner_edit")
CAP: dict = {}


def fake_stream(parts, delay=0.0, record_usage=False):
    def stream(messages, *, privacy=1, info=None, **kw):
        CAP["brief"] = messages[0]["content"]
        CAP["calls"] = CAP.get("calls", 0) + 1
        info = info if info is not None else {}
        t = time.perf_counter()
        out = []
        if record_usage:
            router._record("fake", "fake-model", 10, 5)
        for p in parts:
            if delay:
                time.sleep(delay)
            if not out:
                info["first_ms"] = (time.perf_counter() - t) * 1000
            out.append(p)
            yield p
        info.update(text="".join(out).strip(), provider="fake", model="fake", ms=(time.perf_counter() - t) * 1000)
    return stream


TABLES = ("episodes", "turns", "decisions", "lessons", "facts", "traits", "nudges", "tasks", "intents", "user_directives")


def counts() -> dict:
    return {t: one(f"SELECT count(*) n FROM {t}")["n"] for t in TABLES}


def scores() -> tuple:
    r = one("SELECT coalesce(sum(helpful_count),0) h, coalesce(sum(harmful_count),0) b FROM lessons")
    return (r["h"], r["b"])


real_stream = router.stream
eng = Engine("voice")
got: list[str] = []
router.stream = fake_stream(["●", " That", " sounds", " like", " a long", " day."])
r = eng.turn("I had a really long day at college today.", on_delta=got.append)
check("voice brief asks for the marker (● ◐ ○ rules)", "[TURN MARKER" in CAP.get("brief", ""), CAP.get("brief", "")[-300:])
check("marker never reaches her voice (on_delta)", got and not any(ch in "".join(got) for ch in "●◐○"), str(got))
check("returned + stored reply has no marker", "●" not in r and r.strip() and
      "●" not in (one("SELECT text FROM episodes WHERE id=%s", (eng.last_reply_ep,)) or {}).get("text", "●"), r)
check("last_reply_text (history) clean, marker remembered as ●", "●" not in (eng.last_reply_text or "●")
      and eng.last_marker == "●")
CAP.clear()
router.stream = fake_stream(["●", " Four."])
eng.turn("What time is it in London?", on_delta=got.append)
check("a question gets no marker rules (it's complete)", "[TURN MARKER" not in CAP.get("brief", "x"))

before = counts()
got = []
router.stream = fake_stream(["◐"])
r = eng.turn("I was talking to my friend about the new", on_delta=got.append)
after = counts()
frag = one("SELECT importance FROM episodes WHERE speaker='user' ORDER BY id DESC LIMIT 1")
check("◐ → nothing said, skip_turn, marker ◐", r == "" and got == [] and eng.skip_turn and eng.last_marker == "◐",
      f"{r!r} {got} {eng.skip_turn} {eng.last_marker}")
check("◐ → no reply episode and no turn row; the fragment is kept out of recall (importance 1)",
      after["episodes"] == before["episodes"] + 1 and after["turns"] == before["turns"] and frag["importance"] == 1,
      f"{before} → {after}, {frag}")
CAP.clear()
router.stream = fake_stream(["◐"])
r = eng.turn("I was talking to my friend about the new phone and", on_delta=got.append)
check("right after a ◐ the joined turn gets no marker rules (a ◐-happy model can't silence her)",
      "[TURN MARKER" not in CAP.get("brief", "x"))
eng.incomplete_at = 0.0
router.stream = fake_stream(["○ "])
r = eng.turn("Hmm, so the thing about my project", on_delta=got.append)
check("○ → also dropped (stay quiet longer)", r == "" and eng.skip_turn and eng.last_marker == "○")
eng.incomplete_at = 0.0

web = Engine("text")
CAP.clear()
router.stream = fake_stream(["● ", "Hello", " there."])
wgot: list[str] = []
r = web.turn("Tell me something nice about rainy evenings.", on_delta=wgot.append)
check("web chat: no marker rules in the brief, stray marker stripped from deltas + reply",
      "[TURN MARKER" not in CAP.get("brief", "x") and "●" not in "".join(wgot) and "●" not in r, f"{wgot} {r!r}")

# ---- speculative turns
CHAT = "I watched a really good movie last night with my cousins."
eng2 = Engine("voice")
eng2.turn("I'm feeling okay today, a bit sleepy.", on_delta=lambda d: None)   # some history + lesson ids
state0 = (eng2.last_reply_text, eng2.last_turn_id, eng2.last_user_ep, eng2.last_lesson_ids)
b0, s0 = counts(), scores()
buf: list[str] = []
router.stream = fake_stream(["●", " Which", " one", " was it?"], record_usage=True)
usage0 = one("SELECT coalesce(sum(requests),0) n FROM llm_usage WHERE provider='fake'")["n"]
rs = eng2.turn(CHAT, on_delta=buf.append, speculative=True)
inside = counts()
eng2.speculation_discard()
b1 = counts()
check("speculative turn ran the LLM (buffered text, no marker)", rs and buf and "●" not in "".join(buf), f"{rs!r} {buf}")
check("its writes are invisible to others while held", inside == b0, f"{b0} vs {inside}")
check("discarded → no episode, turn, decision, lesson score left", b1 == b0 and scores() == s0, f"{b0} → {b1}")
check("discarded → engine state exactly as before",
      (eng2.last_reply_text, eng2.last_turn_id, eng2.last_user_ep, eng2.last_lesson_ids) == state0 and eng2._held is None)
check("LLM quota use is recorded even for a discarded speculation (rate limits stay honest)",
      one("SELECT coalesce(sum(requests),0) n FROM llm_usage WHERE provider='fake'")["n"] == usage0 + 1)
router.stream = fake_stream(["●", " Which", " one", " was it?"])
rs = eng2.turn(CHAT, on_delta=lambda d: None, speculative=True)
eng2.speculation_commit()
b2 = counts()
check("committed → stored exactly like a normal turn (+2 episodes, +1 turn)",
      b2["episodes"] == b0["episodes"] + 2 and b2["turns"] == b0["turns"] + 1 and eng2.last_reply_text == rs,
      f"{b0} → {b2}")

blocked = []
for t in ("Remind me at 5 to call mom.", "Add milk to my todos.", "Bye Stiti.", "Play some music on Spotify.",
          "Ek sec.", "No, that's wrong.", "What's on my calendar today?", "Talk in English please.",
          "Remember that my cousin Riya lives in Pune.", "Set an alarm for 6.", "Any news about AI today?"):
    c0 = counts()
    try:
        eng2.turn(t, on_delta=lambda d: None, speculative=True)
        eng2.speculation_discard()
        blocked.append((t, "SPECULATED"))
    except NotSpeculable:
        pass
    if counts() != c0:
        blocked.append((t, "WROTE"))
check("fast paths / actions / flows / corrections are never speculated, and write nothing", not blocked, str(blocked))
eng2.pending = ("tool", {})
try:
    eng2.turn(CHAT, on_delta=lambda d: None, speculative=True)
    ok = False
except NotSpeculable:
    ok = True
eng2.pending = None
check("a pending 'haan/no' confirmation blocks speculation", ok)


class Stop(BaseException):
    pass


def aborting(d):
    raise Stop()


c0, s0 = counts(), scores()
router.stream = fake_stream(["●", " Nice", " one."])
try:
    eng2.turn(CHAT, on_delta=aborting, speculative=True)
except Stop:
    pass
check("a speculation aborted mid-stream (he went on talking) rolls everything back",
      counts() == c0 and scores() == s0 and eng2._held is None)
router.stream = fake_stream(["◐"])
c0 = counts()
r = eng2.turn("So I was telling my cousin that", on_delta=lambda d: None, speculative=True)
eng2.speculation_discard()
check("speculative ◐ + discard → nothing stored at all", r == "" and counts() == c0)
router.stream = real_stream

# ================================================================ 3. Speculator (fake engine, real threads)
print("3. speculator: buffered until the commit, dropped when he goes on")


class FakeNotSpeculable(Exception):
    pass


FakeNotSpeculable.__name__ = "NotSpeculable"


class SpecEngine:
    def __init__(self, parts=("Sure, ", "four ", "PM."), delay=0.05, first=0.25, not_spec=False, mark=None):
        self.parts, self.delay, self.first, self.not_spec, self.mark = parts, delay, first, not_spec, mark
        self.commits = self.discards = self.normal = 0
        self.aborted = False
        self.last_marker, self.skip_turn, self.last_debug, self.incomplete_at = None, False, {}, 0.0

    def turn(self, text, voice_emotion=None, on_delta=None, on_ack=None, speculative=False):
        if speculative and self.not_spec:
            raise FakeNotSpeculable("action")
        if not speculative:
            self.normal += 1
        time.sleep(self.first)                               # recall + LLM time to first token
        try:
            for p in self.parts:
                on_delta(p)
                time.sleep(self.delay)
        except BaseException:
            self.aborted = True
            raise
        if self.mark:
            self.last_marker, self.skip_turn = self.mark, True
            return ""
        return "".join(self.parts)

    def speculation_commit(self):
        self.commits += 1

    def speculation_discard(self):
        self.discards += 1
        self.last_marker, self.skip_turn = None, False


def wait_until(cond, timeout=3.0):
    t = time.time() + timeout
    while time.time() < t and not cond():
        time.sleep(0.005)
    return cond()


fe = SpecEngine()
sp = R.Speculator(lambda: fe)
s = sp.start("Remind me what we said?", 1.0)
time.sleep(0.35)
played: list[tuple[float, str]] = []
check("nothing is played before the commit (all buffered)", s.buf and not played, str(s.buf))
t_adopt = time.monotonic()
s2 = sp.take("Remind me what we said?", 1.0)
reply = sp.run_adopted(s2, lambda d: played.append((time.monotonic(), d)), lambda: "fallback")
check("commit with the same words → buffer replayed in order + live rest, committed once",
      "".join(p for _, p in played) == "Sure, four PM." and fe.commits == 1 and fe.discards == 0 and reply == "Sure, four PM.")
check("first text available at the commit (buffered), not 250 ms later", played[0][0] - t_adopt < 0.05,
      f"{(played[0][0] - t_adopt) * 1000:.0f} ms")
check("gain recorded (≈ head start, capped by the engine's own time)", s2.gain_ms is not None and 200 <= s2.gain_ms <= 400,
      str(s2.gain_ms))

fe = SpecEngine(parts=("a ", "b ", "c ", "d ", "e."), delay=0.1, first=0.05)
sp = R.Speculator(lambda: fe)
s = sp.start("Tell me about it.", 2.0)
time.sleep(0.12)
sp.drop(2.0, "he went on talking")
ok = wait_until(lambda: s.final.is_set())
check("dropped while streaming → LLM stream aborted, rolled back, never committed",
      ok and fe.aborted and fe.discards == 0 and fe.commits == 0 and s.why == "dropped", f"{s.why} {fe.discards}")

fe = SpecEngine(first=0.0, delay=0.0)
sp = R.Speculator(lambda: fe)
s = sp.start("Okay so what now?", 3.0)
wait_until(lambda: s.done.is_set())
sp.drop(3.0, "bye went elsewhere")
check("dropped after it finished → rolled back (discard) once", wait_until(lambda: s.final.is_set())
      and fe.discards == 1 and fe.commits == 0)
check("take() with different words → no adoption", sp.take("Something else", 3.0) is None)

fe = SpecEngine(first=0.0, delay=0.0)
sp = R.Speculator(lambda: fe)
s = sp.start("How was the movie?", 4.0)
wait_until(lambda: s.done.is_set())
sp.settle()
check("settle() before a normal turn drops + rolls back an unused speculation", fe.discards == 1 and s.final.is_set())

fe = SpecEngine(not_spec=True)
sp = R.Speculator(lambda: fe)
s = sp.start("Remind me at 5.", 5.0)
s2 = sp.take("Remind me at 5.", 5.0)
out = sp.run_adopted(s2, lambda d: None, lambda: fe.turn("Remind me at 5.", on_delta=lambda d: None))
check("NotSpeculable → the normal turn runs (nothing lost)", fe.normal == 1 and out == "Sure, four PM." and fe.commits == 0)

fe = SpecEngine(mark="◐", first=0.0)
sp = R.Speculator(lambda: fe)
s = sp.start("I was going to say that", 6.0)
wait_until(lambda: s.done.is_set())
s2 = sp.take("I was going to say that", 6.0)
out = sp.run_adopted(s2, lambda d: None, lambda: "x")
check("adopted ◐ → rolled back (nothing stored), skip_turn kept for the loop",
      out == "" and fe.discards == 1 and fe.commits == 0 and fe.skip_turn and fe.last_marker == "◐")


class Cancelled(Exception):
    pass


fe = SpecEngine(first=0.05, delay=0.05)
sp = R.Speculator(lambda: fe)
s = sp.start("What should I cook?", 7.0)
time.sleep(0.12)
s2 = sp.take("What should I cook?", 7.0)
calls = []


def cancel_on_second(d):
    calls.append(d)
    if len(calls) >= 2:
        raise Cancelled()


try:
    sp.run_adopted(s2, cancel_on_second, lambda: "x")
    raised = False
except Cancelled:
    raised = True
check("continuation grace after the commit → the voice's cancel propagates, turn rolled back",
      raised and fe.commits == 0 and s2.final.is_set())

fe = SpecEngine(first=0.0, delay=0.0)
sp = R.Speculator(lambda: fe, max_drops_per_min=3)
for i in range(3):
    x = sp.start(f"t{i}", 10.0 + i)
    wait_until(lambda: x.done.is_set())
    sp.drop(10.0 + i, "test")
    wait_until(lambda: x.final.is_set())
check("budget: ≤ N dropped speculations a minute (free-tier RPM)", sp.start("t9", 20.0) is None)

# ================================================================ 4. TurnTaker events
print("4. turn-taker events (opt-in): speech_start, speculate, unspeculate; ◐ fragment joined")


class Clock:
    t = 100.0


class FF:
    def __init__(self, ready_t, res):
        self.ready_t, self.res = ready_t, res

    def done(self):
        return Clock.t >= self.ready_t

    def result(self):
        return self.res


TEXTS = {1: "What do you think about my plan?", 2: "I was telling my friend about the", 3: "new phone I bought.",
         4: "to call mom.", 5: "I bought a new phone.", 6: "It was really expensive."}


class Sim:
    def __init__(self, pa=0.3, rt=True, stt_ms=200):
        self.stats = E.TurnStats(Path(tempfile.mkdtemp()) / "s.json")
        self.tt = E.TurnTaker(self.stats, self._stt, lambda fr: pa, start_t=0.0, concat=list)
        self.tt.rt_events = rt
        self.stt_ms, self.events = stt_ms, []

    def _stt(self, frames):
        ids = list(dict.fromkeys(f for f in frames if f is not None))
        return FF(Clock.t + self.stt_ms / 1000, STTResult(" ".join(TEXTS[i] for i in ids), self.stt_ms, 0.05, -0.3))

    def step(self, uid, ms):
        for _ in range(int(round(ms / 32))):
            Clock.t += 0.032
            for ev in self.tt.feed(uid, 0.95 if uid else 0.02, Clock.t):
                self.events.append((Clock.t, ev))

    def kinds(self):
        return [e[0] for _, e in self.events]

    def at(self, kind):
        return next((t for t, e in self.events if e[0] == kind), None)


off = Sim(rt=False)
off.step(1, 1200)
off.step(None, 2000)
check("events are opt-in: the old event stream is unchanged", off.kinds() == ["commit"], str(off.kinds()))
sm = Sim(pa=0.3)
t_end = Clock.t
sm.step(1, 1200)
t_end = Clock.t
sm.step(None, 2000)
k = sm.kinds()
spec_ev = next(e for _, e in sm.events if e[0] == "speculate")
check("finished + unsure audio: speech_start → speculate → commit", k == ["speech_start", "speculate", "commit"], str(k))
check("speculate carries the transcript + segment id the commit will have",
      spec_ev[1] == TEXTS[1] and spec_ev[3] == sm.events[-1][1][1].start_t if False else
      (spec_ev[1] == TEXTS[1] and spec_ev[3] == next(e for _, e in sm.events if e[0] == "commit")[1].start_t))
head = (sm.at("commit") - sm.at("speculate")) * 1000
check(f"speculate fires {head:.0f} ms before the commit (min_delay 1.0 s case)", head >= 400, f"{head:.0f}")
sm = Sim(pa=0.3)
sm.step(5, 900)
sm.step(None, 500)
sm.step(6, 600)
sm.step(None, 2000)
k = sm.kinds()
check("he resumes after a 'finished'-looking pause → unspeculate, then a new speculate on the whole",
      k == ["speech_start", "speculate", "unspeculate", "speculate", "commit"], str(k))
sm = Sim(pa=0.3)
sm.step(2, 900)
sm.step(None, 3500)                                    # "…about the" → unfinished: never speculated
check("an unfinished fragment is never speculated", "speculate" not in sm.kinds(), str(sm.kinds()))

# ◐ keeps listening and joins (TurnTaker prefix set by Realtime.after_turn)
sm = Sim(pa=0.9)
sm.step(1, 900)
sm.step(None, 1500)
sm.tt.prefix, sm.tt.prefix_t, sm.tt.reprompted = "Remind me at 4", Clock.t, False   # what after_turn() sets
sm.step(4, 700)
sm.step(None, 2000)
commits = [e[1] for _, e in sm.events if e[0] == "commit"]
check("◐ → his next words are joined to the kept fragment", commits[-1].text == "Remind me at 4 to call mom.",
      commits[-1].text)

# ================================================================ 5. Realtime glue
print("5. realtime glue: pre-warm, adoption through turn(), ◐ → 'Mm-hm?' after 5 s")


class FakeTT:
    def __init__(self):
        self.prefix, self.prefix_t, self.reprompted, self.busy, self.pending, self.rt_events = "", 0.0, False, False, None, False


class FakeLoop:
    def __init__(self, engine):
        self.engine, self.tt = engine, FakeTT()
        self.awake, self.silenced, self.ring_control, self._work, self.duplex, self.debug = True, False, None, None, None, False
        self.last_activity, self.said = time.time(), []

    def say(self, t):
        self.said.append(t)


warms = []
real_warm = router.warm
router.warm = lambda *a, **k: warms.append(1) or True
fe = SpecEngine(first=0.05, delay=0.0)
lp = FakeLoop(fe)
rt = R.Realtime(lp, media=M.MediaPauser(run=lambda s: "", is_enabled=lambda: False), start_threads=False)
check("Realtime turns the TurnTaker's events on", lp.tt.rt_events)
rt.on_event(("speech_start", 1.0))
lp.awake = False
rt.on_event(("speech_start", 2.0))
lp.awake = True
check("pre-warm on speech start only while awake", len(warms) == 1, str(warms))
router.warm = real_warm
rt.on_event(("speculate", "How was your day?", None, 50.0))
wait_until(lambda: rt.spec.cur is not None and rt.spec.cur.done.is_set())

C = type("C", (), {})
c = C()
c.start_t = 50.0
rt.tick(c)
got = []
out = rt.turn("How was your day?", None, got.append, None)
check("commit → turn() adopts the speculation (no second engine call)",
      out == "Sure, four PM." and fe.normal == 0 and fe.commits == 1 and "".join(got) == "Sure, four PM.")
rt.tick(None)
rt.on_event(("speculate", "And yours?", None, 60.0))
wait_until(lambda: rt.spec.cur.done.is_set())
c.start_t = 60.0
rt.tick(c)                                             # main loop got the commit … but answered it some other way
rt.tick(None)
check("a speculation whose commit wasn't answered by the engine is dropped at the next tick",
      wait_until(lambda: rt.spec.cur.final.is_set()) and fe.discards == 1)
lp._work = threading.Thread(target=time.sleep, args=(0.3,))
lp._work.start()
check("no speculation while her previous reply is still being worked on", not rt.may_speculate())
lp._work.join()

fe2 = SpecEngine(first=0.0, mark="◐")
lp.engine = fe2
rt.spec.engine = lambda: lp.engine
out = rt.turn("So I wanted to ask about the", None, lambda d: None, None)
check("◐ → silent, fragment kept as the TurnTaker prefix, 'Mm-hm?' scheduled for +5 s",
      out == "" and lp.tt.prefix == "So I wanted to ask about the" and rt.reprompt is not None
      and 4.5 < rt.reprompt[0] - time.monotonic() <= 5.0)
rt.tick(None)
check("… nothing said before 5 s", lp.said == [])
rt.reprompt = (time.monotonic() - 0.01, rt.reprompt[1])
rt.tick(None)
check("… 'Mm-hm?' once at 5 s, the fragment stays for his next words",
      lp.said == ["Mm-hm?"] and lp.tt.reprompted and lp.tt.prefix == "So I wanted to ask about the")
rt.after_turn("x")                                     # (engine.skip_turn still set by fe2)
rt.on_event(("speech_start", 3.0))
check("he starts talking → no 'Mm-hm?'", rt.reprompt is None)

# pre-warm de-dup in the router itself
jobs = []
real_job = router._warm_job
router._warm_job = lambda route: jobs.append(route) or setattr(router, "_warm_busy", False)
router._warm_at, router._warm_busy = -1e9, False
starts = [router.warm() for _ in range(5)]
time.sleep(0.05)
check("router.warm(): 5 calls in a row → 1 warm-up", starts == [True, False, False, False, False] and len(jobs) == 1,
      str(starts))
check("… and another after the gap", router.warm(min_gap_s=0.0) and (time.sleep(0.05) or len(jobs) == 2))
router._warm_job = real_job

# ---- through the real VoiceLoop._handle (the one-line call site in work())
import numpy as np                                                    # noqa: E402
from stiti.voice import loop as L                                     # noqa: E402
from stiti.voice.duplex import Duplex                                 # noqa: E402


class FakeTTS:
    def synth_on_worker(self, text, mood):
        return np.ones(int(0.05 * 24000), np.float32), 24000


vl = L.VoiceLoop.__new__(L.VoiceLoop)
fe = SpecEngine(first=0.15, delay=0.0)
fe.last_mood, fe.streamed, fe.last_route, fe.last_action = "calm", True, "llm", None
vl.engine, vl.debug, vl.tts, vl.acks, vl.fillers, vl.ack_text = fe, False, FakeTTS(), {}, [], {}
vl._interrupted, vl._resume, vl._work, vl.last_activity = threading.Event(), None, None, 0.0
vl.awake, vl.silenced, vl.ring_control = True, False, None
vl.duplex = Duplex.__new__(Duplex)
vl.duplex._init_playback()
vl.stats = E.TurnStats(Path(tempfile.mkdtemp()) / "t.json")
vl.tt = E.TurnTaker(vl.stats, None, None)
vl.rt = R.Realtime(vl, media=M.MediaPauser(run=lambda s: "", is_enabled=lambda: False), start_threads=False)
stop_pump = threading.Event()


def pump():
    while not stop_pump.is_set():
        vl.duplex._pull(480)
        time.sleep(0.01)


threading.Thread(target=pump, daemon=True).start()
TXT = "I watched a really good movie last night."
vl._on_event(("speculate", TXT, None, 80.0))
check("loop._on_event hands 'speculate' to Realtime (not to the duplex)", vl.rt.spec.cur is not None)
time.sleep(0.3)                                        # the pause until the commit lands
c = E.Commit(audio=None, res=STTResult(TXT), state="finished", start_t=80.0, commit_t=time.monotonic(),
             end_t=time.monotonic())
vl.rt.tick(c)
t0 = time.monotonic()
vl._handle(TXT, None, c)
vl._wait_work()
stop_pump.set()
check("VoiceLoop._handle adopts it: one engine call, committed, spoken",
      fe.normal == 0 and fe.commits == 1 and vl.duplex.done_id >= 1, f"normal={fe.normal} commits={fe.commits}")

# ================================================================ 6. latency: same turn with and without preemptive start
print("6. latency (simulated: STT 200 ms, unsure audio → commit at min_delay 1.0 s, engine 380 ms to first token)")


def first_text_after_commit(preempt: bool, pa: float) -> float:
    """ms from the commit to her first reply text (TTS adds the same on both sides)."""
    sm = Sim(pa=pa)
    fe = SpecEngine(first=0.38, delay=0.0)
    sp = R.Speculator(lambda: fe)
    marks: dict = {}
    sm.step(1, 1200)
    while "commit" not in marks:
        Clock.t += 0.032
        for ev in sm.tt.feed(None, 0.02, Clock.t):
            if ev[0] == "speculate" and preempt:
                marks["spec_wall"] = time.monotonic()
                sp.start(ev[1], ev[3])
            if ev[0] == "commit":
                marks["commit"] = ev[1]
        time.sleep(0.032)                              # real time, so the engine thread runs alongside
    t_commit = time.monotonic()
    got = []
    s = sp.take(marks["commit"].text, marks["commit"].start_t) if preempt else None
    if s is not None:
        sp.run_adopted(s, lambda d: got.append(time.monotonic()), lambda: "")
    else:
        fe.turn(marks["commit"].text, on_delta=lambda d: got.append(time.monotonic()))
    return (got[0] - t_commit) * 1000


for pa, label in ((0.3, "unsure audio (waits 1.0 s)"), (0.9, "confident audio (commits at once)")):
    off_ms = first_text_after_commit(False, pa)
    on_ms = first_text_after_commit(True, pa)
    print(f"     {label}: first text {off_ms:.0f} ms → {on_ms:.0f} ms after the commit ({off_ms - on_ms:+.0f} ms)")
    if pa < 0.5:
        check("preemptive start cuts ≥ 250 ms off commit → first text when the turn waits", off_ms - on_ms >= 250,
              f"{off_ms:.0f} → {on_ms:.0f}")
    else:
        check("… and never makes the confident case slower", on_ms <= off_ms + 30, f"{off_ms:.0f} → {on_ms:.0f}")

# ================================================================ 7. media pause
print("7. media pause (mocked AppleScript — no real music is touched)")


class Mac:
    def __init__(self, running=(), states=None):
        self.running, self.states, self.calls = set(running), dict(states or {}), []

    def __call__(self, script: str) -> str:
        self.calls.append(script)
        app = script.split('"')[1]
        if script.endswith("is running"):
            return "true" if app in self.running else "false"
        if "player state" in script:
            return self.states.get(app, "stopped")
        if script.endswith(" to pause"):
            self.states[app] = "paused"
        if script.endswith(" to play"):
            self.states[app] = "playing"
        return ""


def acts(mac):
    return [c for c in mac.calls if c.endswith((" to pause", " to play"))]


mac = Mac()
mp = M.MediaPauser(run=mac, is_enabled=lambda: True)
mp.update(True, 0.0)
mp.update(False, 1.0)
mp.update(False, 2.5)
check("nothing running → only 'is running' checks, nothing launched or played",
      not acts(mac) and all(c.endswith("is running") for c in mac.calls), str(mac.calls))
mac = Mac(running=["Spotify", "Music"], states={"Spotify": "playing", "Music": "paused"})
mp = M.MediaPauser(run=mac, is_enabled=lambda: True)
r1 = mp.update(True, 0.0)
mp.update(True, 0.25)
check("wake → pauses only what is actually playing (Spotify), once per session",
      r1 == "pause" and acts(mac) == ['tell application "Spotify" to pause'], str(acts(mac)))
mp.update(False, 5.0)
r2 = mp.update(False, 5.5)
check("… not resumed in the first second of sleep (chime/goodbye)", r2 is None and len(acts(mac)) == 1)
r3 = mp.update(False, 6.2)
check("sleep → resumes exactly what it paused; Music (already paused by him) stays paused",
      r3 == "resume" and acts(mac)[-1] == 'tell application "Spotify" to play' and mac.states["Music"] == "paused",
      str(acts(mac)))
mac = Mac(running=["Music"], states={"Music": "playing"})
mp = M.MediaPauser(run=mac, is_enabled=lambda: True)
mp.update(True, 0.0)
mac.states["Music"] = "playing"                         # he said "play music" while she was awake
mp.update(False, 10.0)
mp.update(False, 11.5)
check("he started music himself meanwhile → left alone (no double play)", acts(mac) == ['tell application "Music" to pause'])
mac = Mac(running=["Music"], states={"Music": "playing"})
mp = M.MediaPauser(run=mac, is_enabled=lambda: True)
mp.update(True, 0.0)
mac.running.discard("Music")                             # he quit it
mp.update(False, 3.0)
mp.update(False, 4.5)
check("app quit meanwhile → nothing launched", acts(mac) == ['tell application "Music" to pause'])
mac = Mac(running=["Spotify"], states={"Spotify": "playing"})
mp = M.MediaPauser(run=mac, is_enabled=lambda: True)
mp.update(True, 0.0)
mp.update(True, 1.0, idle_s=25.0, busy=False)
check("awake but idle ≥ 20 s → music back", acts(mac)[-1] == 'tell application "Spotify" to play')
mac = Mac(running=["Spotify"], states={"Spotify": "playing"})
mp = M.MediaPauser(run=mac, is_enabled=lambda: False)
mp.update(True, 0.0)
check("switch off → never pauses", not acts(mac))
os.environ.pop("STITI_MEDIA_PAUSE", None)
profile.set("media_pause", "off", "owner_edit")
off_ok = M.enabled() is False
profile.set("media_pause", "on", "owner_edit")
on_ok = M.enabled() is True
os.environ["STITI_MEDIA_PAUSE"] = "off"
check("owner_profile media_pause=off/on is the switch (default on)", off_ok and on_ok and M.enabled() is False)

print(f"realtime: {passed}/{total} checks passed")
sys.exit(0 if passed == total else 1)
