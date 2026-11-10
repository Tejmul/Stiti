"""Turn-taking eval (offline, no mic, no models): the text check, the end-of-turn waits, continuation grace,
two-stage barge-in, the phantom-"Bye." gate, his learned pace, duplex duck/pause/resume and the heard-only text.

A simulated segmenter: synthetic 32 ms VAD frames + a fake Smart Turn + a fake Whisper (ready N ms after it was
asked) drive the same endpoint.TurnTaker the voice loop uses. Run with STITI_HOME pointing at a temp dir.
"""
from __future__ import annotations

import os
import sys
import tempfile
import threading
import time
from pathlib import Path

import numpy as np

os.environ.setdefault("STITI_HOME", tempfile.mkdtemp())
os.environ.setdefault("STITI_STT_BIAS", "off")

from stiti.voice import endpoint as E                                  # noqa: E402
from stiti.voice.duplex import RATE, Duplex                            # noqa: E402
from stiti.voice.stt import STTResult, score                           # noqa: E402

passed = total = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global passed, total
    total += 1
    passed += bool(cond)
    print(("  ✓ " if cond else "  ✗ ") + name + (f" — {detail}" if detail and not cond else ""))


# ================================================================ 1. text check
print("text check (finished / unfinished / wait)")
CASES = {
    # his real fragments from ~/.stiti/logs/app.log
    "So...": "unfinished", "So.": "unfinished", "And I'll put the chat.": "finished",
    "Karang li am preparing for placements and making projects.": "finished", "remind me at 4 to": "unfinished",
    # English
    "Remind me at 4.": "finished", "What are my todos?": "finished", "Thank you.": "finished",
    "I'm doing well.": "finished", "I think so.": "finished", "What's the weather like?": "finished",
    "I was talking to my friend about the": "unfinished", "I want to go and": "unfinished", "Okay so": "unfinished",
    "Set an alarm for": "unfinished", "Remind me": "unfinished", "um": "unfinished", "And then I": "unfinished",
    "I'd love to.": "finished", "Come on.": "finished", "So I was thinking,": "unfinished",
    # Hinglish
    "Mujhe lagta hai ki": "unfinished", "Main office jaa raha hoon aur": "unfinished", "Toh": "unfinished",
    "kya chal raha hai": "finished", "Kal subah 6 baje alarm laga do.": "finished", "Chalo phir.": "finished",
    "Aaj bahut kaam tha kyunki": "unfinished", "matlab": "unfinished",
    "Mujhe lagta hain ki?": "unfinished", "And?": "finished", "Matlab?": "finished", "Kab se?": "finished",
    "Where are you from?": "finished",
    # wait phrases
    "Hold on.": "wait", "Ek sec.": "wait", "ruko yaar": "wait", "Let me think.": "wait", "Hmm, let me think.": "wait",
    "one second": "wait", "Wait, what time is my meeting?": "finished", "Ek minute ka timer laga do.": "finished",
}
bad = [(t, E.text_state(t), want) for t, want in CASES.items() if E.text_state(t) != want]
check(f"{len(CASES) - len(bad)}/{len(CASES)} transcripts classified right", not bad, str(bad))
check("join: 'So...' + 'I was thinking…' reads as one sentence",
      E.join_text("So...", "I was thinking about the trip.") == "So I was thinking about the trip.",
      E.join_text("So...", "I was thinking about the trip."))
check("join: 'Remind me at 4.' + 'to call mom'",
      E.join_text("Remind me at 4.", "to call mom") == "Remind me at 4 to call mom")
check("join: 'Haan so.' + 'And I'll put the chat.' keeps the meaning",
      E.join_text("Haan so.", "And I'll put the chat.") == "Haan so and I'll put the chat.")
t0 = time.perf_counter()
for _ in range(1000):
    E.text_state("Main office jaa raha hoon aur phir kal subah")
check("text check < 1 ms", (time.perf_counter() - t0) < 1.0, f"{(time.perf_counter() - t0):.3f} ms each")


# ================================================================ 2. simulated segmenter
class Clock:
    t = 0.0


class FakeFuture:
    def __init__(self, clock, ready_t, res):
        self.clock, self.ready_t, self.res = clock, ready_t, res

    def done(self):
        return self.clock.t >= self.ready_t

    def result(self):
        return self.res


class Sim:
    """Frames are utterance ids (None = silence); the fake STT returns the texts of the ids it 'hears'."""

    def __init__(self, texts: dict, pa: dict | None = None, stt_ms: float = 280, conf: dict | None = None,
                 stats_path: Path | None = None, start_t: float = 100.0):
        self.clock = Clock()
        self.clock.t = start_t
        self.texts, self.pa, self.stt_ms, self.conf = texts, pa or {}, stt_ms, conf or {}
        self.stats = E.TurnStats(stats_path or Path(tempfile.mkdtemp()) / "turn_stats.json")
        self.tt = E.TurnTaker(self.stats, self._stt, self._smart, start_t=start_t - 10, concat=list)
        self.events: list[tuple[float, tuple]] = []
        self.playing, self.play_started = False, None
        self.stt_calls = 0

    def _ids(self, frames):
        out = []
        for f in frames:
            if f is not None and f not in out:
                out.append(f)
        return out

    def _stt(self, frames):
        self.stt_calls += 1
        ids = self._ids(frames)
        text = " ".join(self.texts[i] for i in ids)
        nsp, lp = self.conf.get(ids[-1] if ids else None, (0.05, -0.3))
        return FakeFuture(self.clock, self.clock.t + self.stt_ms / 1000, STTResult(text, self.stt_ms, nsp, lp))

    def _smart(self, frames):
        ids = self._ids(frames)
        return self.pa.get(ids[-1] if ids else None, 0.9)

    def step(self, uid=None, ms: float = 32, p: float | None = None):
        for _ in range(int(round(ms / 32))):
            self.clock.t += 0.032
            prob = p if p is not None else (0.95 if uid is not None else 0.02)
            for ev in self.tt.feed(uid, prob, self.clock.t, self.playing, self.play_started):
                self.events.append((self.clock.t, ev))
                if ev[0] == "stop":
                    self.playing = False

    def speak(self, uid, ms, p=None):
        self.step(uid, ms, p)
        return self.clock.t

    def quiet(self, ms):
        self.step(None, ms)

    def commits(self):
        return [(t, e[1]) for t, e in self.events if e[0] == "commit"]

    def kinds(self):
        return [e[0] for _, e in self.events]

    def play(self, started_ago: float = 5.0):
        self.playing, self.play_started = True, self.clock.t - started_ago


print("end of turn")
# finished + confident audio → commit as soon as the transcript is ready (≈160 + 280 ms)
s = Sim({1: "What are my todos?"}, pa={1: 0.9})
end = s.speak(1, 1200)
s.quiet(4000)
cm = s.commits()
dt = cm[0][0] - end if cm else None
check("finished & Smart Turn ≥ 0.5 → commit ≈ 450 ms after he stops (D18 speed kept)",
      len(cm) == 1 and 0.40 <= dt <= 0.50 and cm[0][1].text == "What are my todos?" and not cm[0][1].timed_out,
      f"{dt}")
check("Smart Turn asked once, Whisper once", s.stt_calls == 1)

# finished words but the audio model unsure → learned min_delay (0.6 s at start)
s = Sim({1: "I went to the market today."}, pa={1: 0.3})
end = s.speak(1, 1500)
s.quiet(4000)
cm = s.commits()
dt = cm[0][0] - end if cm else None
check(f"finished & Smart Turn < 0.5 → wait min_delay ({E.MIN_DELAY_START} s)", len(cm) == 1
      and E.MIN_DELAY_START - 0.02 <= dt <= E.MIN_DELAY_START + 0.08, f"{dt}")

# "So..." → wait 3 s, then commit as a timed-out fragment, keep it, join the next part
s = Sim({1: "So...", 2: "I was thinking about the trip."}, pa={1: 0.95, 2: 0.9})
end = s.speak(1, 500)
s.quiet(2000)
check("'So...' is not answered after 2 s of silence (audio said 'done' 0.95)", not s.commits())
s.quiet(1500)
cm = s.commits()
dt = cm[0][0] - end if cm else None
check("unfinished → commit at 3.0 s, marked timed-out (→ 'Mm-hm?')",
      len(cm) == 1 and 2.95 <= dt <= 3.1 and cm[0][1].timed_out and cm[0][1].state == "unfinished", f"{dt}")
s.speak(2, 1500)
s.quiet(1500)
cm = s.commits()
check("the next part is joined to the kept fragment and answered",
      len(cm) == 2 and cm[1][1].text == "So I was thinking about the trip." and cm[1][1].state == "finished"
      and cm[1][1].reprompted, cm[-1][1].text if cm else "")

# "remind me at 4 to" → 3 s
s = Sim({1: "remind me at 4 to"}, pa={1: 0.8})
end = s.speak(1, 1200)
s.quiet(5000)
cm = s.commits()
check("'remind me at 4 to' waits 3 s", len(cm) == 1 and 2.95 <= cm[0][0] - end <= 3.1)

# a second unfinished timeout in a row is answered (no 'Mm-hm?' loop)
s = Sim({1: "So...", 2: "and"}, pa={1: 0.9, 2: 0.9})
s.speak(1, 400)
s.quiet(3500)
s.speak(2, 300)
s.quiet(3500)
cm = s.commits()
check("second unfinished timeout → answered, not re-prompted again",
      len(cm) == 2 and cm[1][1].reprompted and cm[1][1].timed_out, str([(c.text, c.reprompted) for _, c in cm]))

# wait phrase → 8 s silent hold
s = Sim({1: "Hold on."}, pa={1: 0.9})
end = s.speak(1, 600)
s.quiet(7000)
check("'Hold on.' → nothing for 7 s", not s.commits())
s.quiet(2000)
cm = s.commits()
check("wait phrase → commit at 8 s as 'wait' (loop stays silent)",
      len(cm) == 1 and 7.95 <= cm[0][0] - end <= 8.1 and cm[0][1].state == "wait" and cm[0][1].timed_out)

# he resumes inside the pause → no commit, and the pause is learned
s = Sim({1: "I want to go"}, pa={1: 0.2})
s.speak(1, 800)
s.quiet(450)
s.speak(1, 800)
s.quiet(3500)
check("he resumed after a 0.45 s pause → one turn, pause learned", len(s.commits()) == 1 and s.stats.pauses == 1)

# noise (empty transcript) doesn't eat a kept fragment
s = Sim({1: "So...", 2: "", 3: "the trip"}, pa={1: 0.9, 2: 0.9, 3: 0.9})
s.speak(1, 400)
s.quiet(3500)
s.speak(2, 200)
s.quiet(1500)
s.speak(3, 500)
s.quiet(1500)
texts = [c.text for _, c in s.commits()]
check("a noise blip after 'Mm-hm?' is dropped and the fragment survives",
      texts == ["So...", "", "So the trip"], str(texts))

# max utterance safety
s = Sim({1: "long story"})
s.speak(1, 31000)
check("30 s monologue is committed anyway", len(s.commits()) == 1)


print("continuation grace (he wasn't done)")
s = Sim({1: "Remind me at 4.", 2: "to call mom"}, pa={1: 0.9, 2: 0.9})
end = s.speak(1, 1000)
s.quiet(450)
cm = s.commits()
c1 = cm[0][1]
pend = E.Pending(c1.text, committed_t=c1.commit_t, speech_end_t=c1.end_t)
s.tt.pending = pend
s.quiet(300)
pend.first_audio_t = s.clock.t                       # her first audio
s.play(started_ago=0.0)
s.quiet(200)
before = s.stats.min_delay
s.speak(2, 700)                                      # 0.2 s into her reply he goes on
s.playing = False
s.quiet(1500)
cm = s.commits()
check("he goes on ≤0.9 s after her first audio → reply cancelled", "cancel" in s.kinds() and pend.cancelled)
check("the parts are joined and answered as one",
      len(cm) == 2 and cm[1][1].text == "Remind me at 4 to call mom" and cm[1][1].replaces is pend,
      cm[-1][1].text if cm else "")
check("…and she learns to wait longer (immediate interruption)",
      s.stats.interrupts == 1 and s.stats.min_delay > before, f"{before} → {s.stats.min_delay}")
check("no barge-in duck/stop for a continuation", "stop" not in s.kinds())

s = Sim({1: "Remind me at 4.", 2: "to call mom"})
s.speak(1, 1000)
s.quiet(450)
c1 = s.commits()[0][1]
pend = E.Pending(c1.text, committed_t=c1.commit_t, speech_end_t=c1.end_t)
s.tt.pending = pend
s.quiet(100)
s.speak(2, 500)                                      # before her first audio
check("he goes on before her first audio → cancelled too", pend.cancelled)

s = Sim({1: "What's up?", 2: "tell me a joke instead"})
s.speak(1, 800)
s.quiet(450)
c1 = s.commits()[0][1]
pend = E.Pending(c1.text, committed_t=c1.commit_t, speech_end_t=c1.end_t)
s.tt.pending = pend
s.quiet(300)
pend.first_audio_t = s.clock.t
s.play(started_ago=0.0)
s.quiet(1500)                                        # 1.5 s into her answer
s.speak(2, 1200)
check("1.5 s into her answer it's a barge-in, not a continuation", not pend.cancelled and "duck" in s.kinds())


print("barge-in (duck → pause → his words decide)")
s = Sim({1: "Haan."}, conf={1: (0.1, -0.3)})
s.play()
s.speak(1, 450)
s.quiet(800)
k = s.kinds()
check("'haan' over her: duck at 250 ms, then resume — never stopped, no turn",
      k[:1] == ["duck"] and "resume" in k and "stop" not in k and "pause" not in k and not s.commits(), str(k))
t_duck = next(t for t, e in s.events if e[0] == "duck")
check("duck fires after ~250 ms of his speech", abs((t_duck - (s.clock.t - 1.25)) - 0.256) < 0.05)

s = Sim({1: "Wait, tomorrow not today."}, conf={1: (0.1, -0.4)})
s.play()
s.speak(1, 1300)
s.quiet(1500)
k = s.kinds()
cm = s.commits()
check(f"2+ words: duck → pause at {E.FORCE_PAUSE_MS} ms → stop", k[:3] == ["duck", "pause", "stop"], str(k))
check("…and it becomes his turn (barged)", len(cm) == 1 and cm[0][1].barged and cm[0][1].overlap)

s = Sim({1: "Stop."}, conf={1: (0.05, -0.2)})
s.play()
s.speak(1, 400)
s.quiet(600)
check("one confident stop word → stop", "stop" in s.kinds())

s = Sim({1: "Nice."}, conf={1: (0.05, -0.2)})
s.play()
s.speak(1, 400)
s.quiet(600)
check("one non-stop word → resume", "resume" in s.kinds() and "stop" not in s.kinds())

s = Sim({1: "mumble words here"}, stt_ms=5000)
s.play()
s.speak(1, 1000)
s.quiet(1600)
k = s.kinds()
check("paused and nothing heard for 1.5 s → resume", k[:2] == ["duck", "pause"] and k[2:3] == ["resume"], str(k))

s = Sim({1: "echo"}, start_t=100.0)
s.tt.started_t = s.clock.t - 1.0                     # loop started 1 s ago (AEC warm-up)
s.play()
s.speak(1, 800)
check("no barge-in in the first 3 s after start-up", "duck" not in s.kinds())
s = Sim({1: "echo"})
s.play(started_ago=0.0)
s.speak(1, 240)
check("no barge-in in the first 250 ms of a playback", "duck" not in s.kinds())
s = Sim({1: "echo"})
s.play()
s.speak(1, 800, p=0.65)
check("VAD bar is 0.7 while she speaks (0.65 ignored)", "duck" not in s.kinds() and not s.tt.busy)
s = Sim({1: "hello there"})
s.speak(1, 800, p=0.65)
check("…but 0.65 counts as speech when she's quiet", s.tt.busy)

check("barge verdicts", [E.barge_verdict(x) for x in ("haan", "okay okay", "theek hai", "", "bas", "no",
                                                      "wait a second", "Bye.", "tell me more")]
      == ["resume", "resume", "resume", "resume", "stop", "stop", "stop", "resume", "stop"])
check("an unsure lone stop word doesn't stop her", E.barge_verdict("No.", confident=False) == "resume")


print("'bye' gate (phantom 'Bye.')")
ended = 50.0
mk = lambda **k: E.Commit(audio=[], **k)  # noqa: E731
phantom = STTResult("Bye.", 300, 0.55, -0.9)
sure = STTResult("Bye.", 300, 0.05, -0.3)
check("lone low-confidence 'Bye.' right after her reply → ignored",
      not E.goodbye_counts(mk(speech_ms=250, start_t=ended + 0.4), phantom, ended))
check("confident but in the echo tail (0.5 s after she stopped) → ignored",
      not E.goodbye_counts(mk(speech_ms=500, start_t=ended + 0.5), sure, ended))
check("confident, long enough, said a few seconds later → goodbye",
      E.goodbye_counts(mk(speech_ms=500, start_t=ended + 3.0), sure, ended))
check("too short (<300 ms) → ignored", not E.goodbye_counts(mk(speech_ms=200, start_t=ended + 3), sure, ended))
check("a confirmed barge-in 'okay bye' counts even while she was talking",
      E.goodbye_counts(mk(speech_ms=400, start_t=ended - 1, barged=True), STTResult("Okay bye.", 1, 0.1, -0.5), ended))
r = STTResult("Bye.", 1, 0.3, -0.7)
check("confidence thresholds: no_speech < 0.4 and logprob > -0.8", r.confident
      and not STTResult("Bye.", 1, 0.45, -0.7).confident and not STTResult("Bye.", 1, 0.3, -0.85).confident)
check("unclear transcript → ask again", STTResult("kuch bhi", 1, 0.2, -1.1).unclear
      and not STTResult("what are my todos", 1, 0.1, -0.4).unclear)
nsp, lp = score([{"start": 0, "end": 1, "no_speech_prob": 0.1, "avg_logprob": -0.2},
                 {"start": 1, "end": 4, "no_speech_prob": 0.5, "avg_logprob": -1.0}])
check("whisper scores are duration-weighted", abs(nsp - 0.4) < 1e-6 and abs(lp + 0.8) < 1e-6, f"{nsp} {lp}")


print("his pace (EMA, persisted)")
p = Path(tempfile.mkdtemp()) / "turn_stats.json"
st = E.TurnStats(p)
check(f"starts at {E.MIN_DELAY_START} s", st.min_delay == E.MIN_DELAY_START)
for _ in range(30):
    st.immediate_interrupt(2.0)
check("immediate interruptions push the wait up (EMA α=0.9)", 1.5 < st.min_delay <= 2.1, str(st.min_delay))
low = st.min_delay
st.immediate_interrupt(0.2)
check("…and a short one never pulls it down", st.min_delay == low)
for _ in range(100):
    st.immediate_interrupt(9.0)
check("clamped at 3.0 s", st.min_delay == 3.0)
for _ in range(200):
    st.observe_pause(0.1)
check("clamped at 0.5 s", st.min_delay == 0.5)
st.observe_pause(1.5)
st2 = E.TurnStats(p)
check("persisted to turn_stats.json and reloaded", abs(st2.min_delay - st.min_delay) < 1e-3
      and st2.pauses == st.pauses and st2.interrupts == st.interrupts and p.exists())
check("default path is under STITI_HOME", str(E.TurnStats().path).startswith(os.environ["STITI_HOME"]))
check("confident turns stay fast unless he taught her to wait",
      E.wait_for("finished", 0.9, E.MIN_DELAY_START) == 0.0
      and abs(E.wait_for("finished", 0.9, E.MIN_DELAY_START + 0.4) - 0.4) < 1e-9
      and E.wait_for("finished", 0.2, 1.0) == 1.0 and E.wait_for("unfinished", 0.9, 0.6) == 3.0
      and E.wait_for("wait", 0.9, 0.6) == 8.0)


print("duplex: duck / pause / resume / stop, heard pieces")
d = Duplex.__new__(Duplex)
d._init_playback()
one = np.ones(4800, np.float32)                       # 0.1 s each
ids = [d.play(one, RATE) for _ in range(3)]
d._pull(4800)
d._pull(480)
check("done_id counts fully played pieces", d.done_id == ids[0])
d.duck()
o = d._pull(2400)
check("duck → 30 % with a ramp (no click)", abs(o[-1] - 0.3) < 1e-3 and o[0] > 0.9)
d.pause()
d._pull(2400)
done_before, left_before = d.done_id, len(d._cur) + sum(len(b) for _, b in d._buf)
held = d._pull(4800)
check("pause → fades out and holds (still 'playing', nothing consumed)", held.max() == 0 and d.playing
      and d.done_id == done_before and len(d._cur) + sum(len(b) for _, b in d._buf) == left_before)
d.resume()
o = d._pull(2400)
check("resume → back to full volume where she paused", abs(o[-1] - 1.0) < 1e-3)
d.stop_playback()
check("stop → a ≤30 ms fade tail, rest dropped", len(d._cur) <= int(0.03 * RATE) and not d._buf)
d._pull(4800)
check("…then silent, with an end time for the bye gate", not d.playing and d.ended_at is not None)


print("speaker: heard-only text after a barge-in, English acks")
from stiti.voice import speaker as S                                  # noqa: E402

check("acks/fillers are English with no time promises",
      all(not any(w in t.lower() for w in ("ek sec", "dekhti", "karti", "one sec", "second"))
          for t in list(S.ACKS.values()) + S.FILLERS) and S.FILLER_AFTER_S == 1.5)


class FakeTTS:
    def synth_on_worker(self, text, mood):
        return np.ones(int(0.08 * 24000), np.float32), 24000


class FakeLoop:
    def __init__(self):
        self.duplex = Duplex.__new__(Duplex)
        self.duplex._init_playback()
        self._interrupted = threading.Event()
        self.tts, self.acks, self.fillers, self.ack_text = FakeTTS(), {}, [], {}


fl = FakeLoop()
stop_pump = threading.Event()


def pump():                                           # the 10 ms audio callback
    while not stop_pump.is_set():
        fl.duplex._pull(480)
        time.sleep(0.01)


threading.Thread(target=pump, daemon=True).start()
firsts = []
sp = S.Speaker(fl, filler_after=1e9, on_first_audio=firsts.append)
for piece in ["First sentence.", "Second sentence.", "Third sentence.", "Fourth sentence."]:
    sp.add(piece)
sp.close()


def cut():
    while fl.duplex.done_id < 2:
        time.sleep(0.005)
    fl._interrupted.set()


threading.Thread(target=cut, daemon=True).start()
left = sp.run()
stop_pump.set()
check("heard = the pieces played to the end", sp.heard[:2] == ["First sentence.", "Second sentence."]
      and "Fourth sentence." not in sp.heard, str(sp.heard))
check("left = the rest (re-said on a mere 'haan')", left and left[-1] == "Fourth sentence."
      and set(sp.heard).isdisjoint(left), str(left))
check("first-audio hook fired once (continuation-grace clock)", len(firsts) == 1)


print("loop: a cancelled reply aborts the LLM stream and isn't spoken")
from stiti.voice import loop as L                                     # noqa: E402


class FakeEngine:
    def __init__(self):
        self.last_mood, self.streamed, self.last_debug, self.aborted = "calm", False, {}, False
        self.last_route, self.last_action, self.truncated = "llm", None, None

    def turn(self, text, voice_emotion=None, on_delta=None, on_ack=None):
        self.streamed = True
        try:
            for w in ["Sure, ", "four ", "PM ", "it ", "is. ", "Anything ", "else?"]:
                time.sleep(0.15)
                on_delta(w)
        except BaseException:
            self.aborted = True
            raise
        return "Sure, four PM it is. Anything else?"

    def truncate_last_reply(self, heard):
        self.truncated = heard


vl = L.VoiceLoop.__new__(L.VoiceLoop)
vl.engine, vl.debug, vl.tts, vl.acks, vl.fillers, vl.ack_text = FakeEngine(), False, FakeTTS(), {}, [], {}
vl._interrupted, vl._resume, vl._work, vl.last_activity = threading.Event(), None, None, 0.0
vl.duplex = Duplex.__new__(Duplex)
vl.duplex._init_playback()
vl.stats = E.TurnStats(Path(tempfile.mkdtemp()) / "t.json")
vl.tt = E.TurnTaker(vl.stats, None, None)
stop_pump.clear()
fl.duplex = vl.duplex
threading.Thread(target=pump, daemon=True).start()
c = E.Commit(audio=None, res=STTResult("Remind me at 4."), state="finished", commit_t=time.monotonic(),
             end_t=time.monotonic())


def canceller():
    time.sleep(0.2)
    pend = vl.tt.pending
    pend.cancelled = True
    vl._on_event(("cancel", pend))


threading.Thread(target=canceller, daemon=True).start()
t0 = time.time()
vl._handle("Remind me at 4.", None, c)
took = time.time() - t0
vl._wait_work()
check("cancel → _handle returns at once, the LLM stream is aborted", took < 0.6 and vl.engine.aborted, f"{took:.2f}s")

vl.engine = FakeEngine()
vl._interrupted.clear()


def barger():
    while vl.duplex.done_id < 1:
        time.sleep(0.005)
    vl._on_event(("stop",))


threading.Thread(target=barger, daemon=True).start()
vl._handle("Set it for 4.", None, None)
vl._wait_work()
stop_pump.set()
check("barge-in stop → engine.truncate_last_reply(heard part only)",
      vl.engine.truncated is not None and vl.engine.truncated.startswith("Sure")
      and "else" not in vl.engine.truncated and vl.engine.last_interrupted, repr(vl.engine.truncated))

from stiti.brain import learning                                      # noqa: E402

undone = []
real_undo, learning.undo_last = learning.undo_last, lambda a: undone.append(a) or "ok"
done_th = threading.Thread(target=lambda: None)
done_th.start()
vl.engine.last_action = {"type": "intent", "id": 7}
vl._undo_replaced(E.Pending("Remind me at 4.", 0, 0, action={"type": "intent", "id": 7}, work=done_th))
learning.undo_last = real_undo
check("a joined continuation undoes the fragment's fast-path write (no double reminder)",
      undone == [{"type": "intent", "id": 7}] and vl.engine.last_action is None)

print("engine hooks (persona branch; guarded so this branch works alone)")


class HoldEngine(FakeEngine):
    def turn(self, text, voice_emotion=None, on_delta=None, on_ack=None):
        self.skip_turn = True
        return ""


vl.engine = HoldEngine()
vl.fillers = [(np.ones(2400, np.float32), 24000)]
vl.duplex = Duplex.__new__(Duplex)
vl.duplex._init_playback()
played = []
real_play = vl.duplex.play
vl.duplex.play = lambda a, sr: played.append(len(a)) or real_play(a, sr)
vl._interrupted.clear()
vl._handle("Ek sec.", None, None)
check("engine.skip_turn → she says nothing, no filler", played == [])
vl.fillers = []

off = type("E", (), {"last_reply_text": "Done, 4 PM. Anything else?"})()
check("after 'Anything else?' the loop sees an answer, not a goodbye",
      L._after_offer(off) and not L._after_offer(type("E", (), {"last_reply_text": "Done."})())
      and not any(L._explicit_bye(t) for t in ("that's it", "okay", "bas", "no", "nothing", "not yet")))
check("…but a real bye still ends it", all(L._explicit_bye(t) for t in ("bye", "okay bye", "good night", "chalo bye")))

# ---- measured on ElevenLabs' live demo (docs/research/re_elevenlabs_live.md)
check("'I was wondering' / 'baat ye hai ki' + pause → unfinished (EL waited and joined)",
      all(E.text_state(s) == "unfinished" for s in ("I was wondering", "So I was wondering if", "baat ye hai ki",
                                                     "Can you tell me")) and E.text_state("Can you tell me the time?") == "finished")
check("'Mmh, mmh.' / 'hmmm' / 'uh-huh' over her → resume, not stop (EL dropped its answer)",
      E.barge_verdict("Mmh, mmh.") == "resume" and E.barge_verdict("uh-huh") == "resume" and E.barge_verdict("wait, stop") == "stop")

print(f"turn-taking: {passed}/{total} checks passed")
sys.exit(0 if passed == total else 1)
