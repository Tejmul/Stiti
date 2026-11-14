"""The tutor teaches like a teacher (D40): one voice, never hears herself, answers doubts on the board, resumes.

His complaint (2026-11-14): "it's going and suddenly breaking … two other voices are breaking the speaking voice …
once I ask how it is done or any doubt, it should be able to explain". The 2026-11-11 log showed her own TTS
transcribed as his input ("Chalo today … let's go step by step", "Good question"), Whisper phantoms, "I can't answer
that one properly without my cloud brain" (the demo lesson had no answerer) and "Shall we continue?" after every line.

Simulated end to end with fake audio + fake transcripts + a fake LLM: no speakers, no mic, no cloud.
STITI_DB=postgresql:///stiti_test STITI_HOME=<tmp> uv run python tests/tutor_teacher_eval.py
"""
from __future__ import annotations

import json
import os
import queue
import sys
import threading
import time

db = os.environ.get("STITI_DB", "")
if not db.rstrip("/").split("/")[-1].startswith("stiti_test"):
    sys.exit(f"refusing to run against {db!r}: use a stiti_test* database")
os.environ.setdefault("STITI_LIVE_WARM", "0")
os.environ.setdefault("STITI_EVENTKIT", "off")

passed = total = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global passed, total
    total += 1
    passed += bool(cond)
    print(f"  {'✓' if cond else '✗'} {name}" + (f" — {detail}" if detail and not cond else ""))


from stiti import router                                                 # noqa: E402
from stiti.tutor import ears, lesson as LS, player as P                  # noqa: E402
from stiti.tutor.ears import EchoGuard                                   # noqa: E402
from stiti.tutor.lesson import Op                                        # noqa: E402
from stiti.tutor.player import Tutor                                     # noqa: E402

# ------------------------------------------------------------------ fakes
SCALE = 0.25          # a 10-word sentence "plays" for ~1 s


class FakeAudio:
    """Plays nothing; knows what is 'playing' and counts any overlap (two utterances at once = the bug)."""

    def __init__(self):
        self.guard = EchoGuard()
        self._until = 0.0
        self.cur = ""
        self.started: list[tuple[float, str]] = []
        self.stops: list[float] = []
        self.overlaps = 0

    def synth(self, text, speed=1.0):
        return text, int((len(text.split()) / 2.6 / speed) * 1000 + 300)

    def play(self, audio, ms):
        if self.playing:
            self.overlaps += 1
        self.cur = audio
        self.started.append((time.time(), audio))
        self._until = time.time() + ms / 1000 * SCALE

    @property
    def playing(self):
        return time.time() < self._until

    def stop(self):
        if self.playing:
            self.stops.append(time.time())
        self._until = 0
        self.guard.stopped()

    def close(self):
        pass


class FakePlanner:
    def __init__(self, delay=0.0, down=False):
        self.delay, self.down, self.calls = delay, down, []

    def answer(self, question, ctx):
        self.calls.append((question, ctx))
        time.sleep(self.delay)
        if self.down:
            raise router.NoProvider("groq: 429; openrouter: timeout")
        n = len(self.calls)
        return {"intent": "clarify", "strategy": "direct_explain",
                "say": ["Good question! The lexer keeps reading while characters still fit the token.",
                        f"Like reading the word {'count' if n == 1 else 'apple'} letter by letter until a space.",
                        "The space tells it the token ended."],
                "ops": [Op(type="box", id=f"d{n}a", text="read chars", at="lexer"),
                        Op(type="box", id=f"d{n}b", text="space = end", place="right_of", ref=f"d{n}a", at="space"),
                        Op(type="arrow", ref=f"d{n}a>d{n}b", at="space")]}


class FakeSrv:
    def __init__(self):
        self.sent: list[dict] = []

    def send(self, m):
        self.sent.append(m)


def make_lesson(check=False):
    d = ({"title": "How a lexer works", "topic": "lexers", "segments": [
        {"id": "w", "type": "warmup", "title": "Warm-up", "cues": [
            {"say": "Chalo! Today: how a lexer turns code into tokens. Let's go step by step.",
             "ops": [{"type": "new_page", "text": "Lexers"}]},
            {"say": "Think of reading a sentence word by word.", "ops": []}]},
        {"id": "t1", "type": "teach", "title": "Reading characters", "cues": [
            {"say": "The lexer reads your code one character at a time.",
             "ops": [{"type": "box", "id": "lx", "text": "Lexer", "at": "lexer"}]},
            {"say": "It groups the characters into small meaningful pieces called tokens.",
             "ops": [{"type": "box", "id": "tk", "text": "Tokens", "place": "right_of", "ref": "lx", "at": "tokens"},
                     {"type": "arrow", "ref": "lx>tk", "at": "groups"}]},
            {"say": "A keyword, a name, a number and a plus sign are all tokens.",
             "ops": [{"type": "bullet", "text": "keyword, name, number, +", "at": "keyword"}]},
            {"say": "Spaces and comments are thrown away on the way.", "ops": []}]},
        {"id": "t2", "type": "teach", "title": "Why tokens", "cues": [
            {"say": "The parser then reads tokens, not characters, which is much easier.",
             "ops": [{"type": "box", "id": "ps", "text": "Parser", "place": "right_of", "ref": "tk", "at": "parser"}]},
            {"say": "So the lexer is the first step of every compiler.", "ops": []}]},
    ]})
    if check:
        d["segments"][2]["check"] = {"kind": "recall", "prompt": "Which step comes first, the lexer or the parser?",
                                     "expectations": ["the lexer comes first"], "hints": ["Think characters."],
                                     "reveal": "The lexer.", "on_correct": "Yes, the lexer."}
    return LS.from_dict(d)


def run(script: dict, planner=None, pace=0.1, timeout=60.0, check=False):
    """Play the lesson; `script` maps a cue/line prefix → events pushed 0.15 s after she starts saying it (first
    time only), i.e. while she is mid-sentence."""
    audio, srv, ev, logs = FakeAudio(), FakeSrv(), queue.Queue(), []
    fired = set()
    stamps: dict[str, float] = {}

    def log(line):
        logs.append((time.time(), line))
        for key, evs in script.items():
            if key not in fired and line.startswith("Stiti: " + key):
                fired.add(key)
                stamps[key] = time.time()

                def push(evs=evs, key=key):
                    for e in evs:
                        stamps.setdefault("push:" + key, time.time())
                        ev.put(dict(e))
                        time.sleep(0.02)
                threading.Timer(0.15, push).start()
    t = Tutor(make_lesson(check), audio=audio, events=ev, server=srv, planner=planner, persist=False, log=log, pace=pace,
              idle_resume_s=1)
    out = {}
    th = threading.Thread(target=lambda: out.setdefault("res", t.run()), daemon=True)
    th.start()
    th.join(timeout)
    if th.is_alive():
        t.ended = True
        th.join(5)
    said = [x[len("Stiti: "):] for _, x in logs if x.startswith("Stiti: ")]
    return {"t": t, "audio": audio, "srv": srv, "logs": logs, "said": said, "res": out.get("res"), "stamps": stamps}


def voice(text, **kw):
    return {"type": "voice", "text": text, **kw}


# ------------------------------------------------------------------ 1. the echo guard (pure)
print("she never treats her own voice as his (EchoGuard)")
clock = [100.0]
g = EchoGuard(clock=lambda: clock[0])
g.spoke("Chalo! Today: Lexical Analysis: Code to Tokens. Let's go step by step.", 4000, start=90.0)
g.spoke("Before I explain anything, take a quick guess.", 2500, start=94.2)
g.spoke("Good question. Let me think.", 1500, start=97.0)
REAL_ECHOES = ["Chalo today, let's go to tokens, let's go step by step. Before I explain anything, take a quick guess.",
               "Chalo today, lexical analysis, code to tokens, let's go step by step. Before I explain anything, "
               "can't answer that one.", "Good question.", "Good question, let me thank you."]
for x in REAL_ECHOES:
    check(f"her own words from the 11 Nov log are dropped: {x[:50]!r}", g.check(x, at=98.0) == (False, "her own voice"),
          str(g.check(x, at=98.0)))
for x in ("Two minutes, time's going to tell.", "Thanks for watching!", "Subtitles by the Amara.org community"):
    check(f"Whisper phantom dropped: {x!r}", g.check(x, at=98.0)[1] == "phantom")
check("an unclear non-command is dropped ('Nim nil to nara', low confidence)",
      g.check("Nim nil to nara.", at=98.0, no_speech=0.7, logprob=-1.3) == (False, "unclear"))
check("…but an unclear 'ruko' still pauses", g.check("ruko", at=98.0, no_speech=0.6, logprob=-1.2)[0])
for x in ("ruko", "wait", "ek doubt hai", "stop", "What is a token?", "how does the lexer know where a token ends?",
          "lesson khatam karo"):
    check(f"a real interruption while she talks still counts: {x!r}", g.check(x, at=98.0)[0], str(g.check(x, at=98.0)))
check("a 1–2 word non-command while she talks is not an interruption ('Yo.')", not g.check("Yo.", at=98.0)[0])
check("a one-word echo of what she just said ('think') is dropped", not g.check("think", at=98.0)[0])
check("'Bye.' inside her echo doesn't end the lesson", not g.check("Bye.", at=98.0)[0])
clock[0] = 140.0
check("long after she stopped, his 2-word line counts ('lexer kya')", g.check("lexer kya", at=139.0)[0])
check("…and the same words she said 40 s ago are NOT echo any more", g.check("Good question.", at=139.0)[0])
check("the same noise line again within 20 s = looping hallucination",
      g.check("Kale malawad chendat", at=139.5)[0] and not g.check("Kale malawad chendat", at=139.6)[0])
g.spoke("Shall we continue?", 1200, start=150.0)
clock[0] = 150.5
g.stopped()
check("stopped playback ends the echo window early (+1.5 s tail)", g.in_echo(151.9) and not g.in_echo(152.2))

print("barge-in: her echo never even stops her (TurnTaker veto)")
from stiti.voice import endpoint                                       # noqa: E402
from types import SimpleNamespace                                       # noqa: E402


def verdict(text, veto):
    tt = endpoint.TurnTaker(endpoint.TurnStats.__new__(endpoint.TurnStats), lambda a: None, lambda a: 0.5)
    tt.cur, tt.barge, tt.start_t = [0], "ducked", 98.0
    tt.res = SimpleNamespace(text=text, confident=True, no_speech_prob=0.05, avg_logprob=-0.3)
    tt.veto = veto
    return tt._barge_in(98.5, True)


g2 = EchoGuard(clock=lambda: 98.5)
g2.spoke("It groups the characters into small meaningful pieces called tokens.", 3000, start=97.0)
veto = lambda text, res, start_t: g2.barge_ok(text, res, at=start_t)  # noqa: E731
check("her own sentence heard back → keep talking (resume, not stop)",
      verdict("it groups the characters into meaningful pieces", veto) == [("resume",)])
check("'ruko' → stops her", verdict("ruko bhai", veto) == [("stop",)])
check("a real doubt → stops her", verdict("wait how does it know where it ends", veto) == [("stop",)])
check("the always-on loop (no veto) is unchanged", verdict("it groups the characters into meaningful pieces", None)
      == [("stop",)])

# ------------------------------------------------------------------ 2. a lesson with echo + phantoms: no breaking
print("a lesson with her echo and phantoms in the mic: she never breaks")
r = run({"It groups the characters": [voice("it groups the characters into small meaningful pieces called tokens"),
                                      voice("Thanks for watching!")],
         "Chalo! Today": [voice("Chalo today, how a lexer turns code into tokens, let's go step by step.")],
         "The parser then": [voice("Two minutes, time's going to tell.")]})
said = r["said"]
check("lesson finishes", r["res"] and r["res"]["finished"], str(r["res"]))
check("no line was cut off (no stop while she taught)", not r["audio"].stops, f"{len(r['audio'].stops)} stops")
check("every cue said exactly once (no replay, no duplicate 'Chalo! Today')",
      all(said.count(c.say) == 1 for s in r["t"].L.segments for c in s.cues),
      str([x for x in said if said.count(x) > 1]))
check("the ignored lines are logged with a reason", sum("(ignored" in x for _, x in r["logs"]) == 4,
      str([x for _, x in r["logs"] if "ignored" in x]))
check("never two utterances at once", r["audio"].overlaps == 0)

# ------------------------------------------------------------------ 3. ruko pauses instantly, continue resumes
print("'ruko' pauses instantly; 'continue' picks up the same sentence")
r = run({"It groups the characters": [voice("ruko")], "Okay, paused": [{"type": "text", "text": "continue"}]})
st = r["stamps"]
stop_after = min((s for s in r["audio"].stops if s >= st.get("push:It groups the characters", 0)), default=None)
lat = (stop_after - st["push:It groups the characters"]) if stop_after else None
check("she stopped within 150 ms of hearing 'ruko'", lat is not None and lat < 0.15, f"{lat}")
check("paused line said", any(x.startswith("Okay, paused") for x in r["said"]))
cue = "It groups the characters into small meaningful pieces called tokens."
check("after 'continue' the interrupted sentence replays from its start", r["said"].count(cue) == 2)
check("lesson finishes", r["res"] and r["res"]["finished"])

# ------------------------------------------------------------------ 4. a doubt mid-sentence, answered like a teacher
print("a doubt mid-sentence: stop → 'Good question' → answer drawn on a doubt board → back to the same cue")
pl = FakePlanner(delay=0.7)          # slower than the "Good question." clip (~0.27 s here) → filler
DOUBT = "how does the lexer know where a token ends?"
r = run({"It groups the characters": [voice(DOUBT)]}, planner=pl)
said, t = r["said"], r["t"]
i_cut = said.index(cue)
check("she stopped speaking at once", any(s >= r["stamps"]["push:It groups the characters"] for s in r["audio"].stops))
check("acknowledges first ('Good question.')", said[i_cut + 1] == "Good question.", str(said[i_cut + 1:i_cut + 3]))
check("a filler while the cloud was slow (>0.8 s × pace)", any(x in P.FILLERS for x in said[i_cut + 1:i_cut + 4]))
ans = [x for x in said if "lexer keeps reading" in x or "letter by letter" in x or "token ended" in x]
check("answers in 2–4 spoken sentences", len(ans) == 3, str(ans))
check("doesn't say 'Good question' twice (stripped from the LLM's first line)",
      ans and ans[0].startswith("The lexer keeps reading"), str(ans[:1]))
doubt_els = [e for e in t.board.els.values() if e.frame[1] >= 1 and e.kind in ("box", "arrow")]
lesson_els = [t.board.ref(x) for x in ("lx", "tk")]
check("the answer is DRAWN (box, box, arrow)", len(doubt_els) == 3, str([e.id for e in doubt_els]))
check("…on its own doubt board, under the lesson page (lesson board not wrecked)",
      doubt_els and all(e.frame[1] >= 1 for e in doubt_els) and all(e and e.frame[1] == 0 for e in lesson_els),
      str([(e.id, e.frame) for e in doubt_els]))
titles = [a for m in r["srv"].sent if m["type"] == "actions" for a in m["actions"]
          if "Q: how does the lexer" in json.dumps(a)]
check("the doubt board is titled with his question", bool(titles))
check("then 'Back to where we were.'", "Back to where we were." in said)
check("resumes at the SAME cue (it replays once, nothing skipped)", said.count(cue) == 2
      and said.index("Back to where we were.") < len(said) - 1 - said[::-1].index(cue))
resets = [m for m in r["srv"].sent if m["type"] == "reset"]
check("the replay keeps the doubt board on the canvas", resets and "read chars" in json.dumps(resets[-1]["actions"]))
check("the planner got the lesson context (what she just said + board)", pl.calls and
      cue in " ".join(pl.calls[0][1]["last_said"]) and "Lexer" in pl.calls[0][1]["board"])
check("lesson finishes, one question recorded", r["res"]["finished"] and r["res"]["questions"] == 1, str(r["res"]))
check("never two utterances at once", r["audio"].overlaps == 0, str(r["audio"].overlaps))
check("no 'Shall we continue?'", not any("Shall we continue" in x for x in said))
ops_at = [a["at_ms"] for m in r["srv"].sent if m["type"] == "cue" and m["cue_id"] == "t1c2" for a in m["actions"]
          if a.get("do") != "camera"]
ms = next(m["audio_ms"] for m in r["srv"].sent if m["type"] == "cue" and m["cue_id"] == "t1c2")
check("cue drawing is synced to the words ('tokens' box drawn late in the sentence, inside the clip)",
      ops_at and max(ops_at) > ms * 0.6 and max(ops_at) < ms, f"{ops_at} / {ms}")

print("follow-up doubt: 'samajh nahi aaya' → simpler, with the earlier answer as context")
pl = FakePlanner(delay=0.0)
r = run({"It groups the characters": [voice(DOUBT)], "The space tells it": [voice("samajh nahi aaya")]}, planner=pl,
        pace=0.3)
check("asked the cloud twice", len(pl.calls) == 2, str(len(pl.calls)))
ctx2 = pl.calls[1][1] if len(pl.calls) > 1 else {}
check("the follow-up carries the earlier doubt + answer, and 'simpler'",
      ctx2.get("simpler") is True and ctx2.get("previous", {}).get("q") == DOUBT and ctx2["previous"]["a"])
check("says it'll try another way", any(x in P.SIMPLER for x in r["said"]))
check("the simpler answer draws on the same doubt board",
      len([e for e in r["t"].board.els.values() if e.frame[1] >= 1 and e.kind in ("box", "arrow")]) == 6)
check("still resumes the same cue once at the end", r["said"].count(cue) == 2 and r["res"]["finished"])

print("LLM down: honest once, then just parked")
pl = FakePlanner(down=True)
r = run({"It groups the characters": [voice(DOUBT)], "The parser then": [voice("why can't the parser read characters?")],
         "So the lexer is": [voice("what comes after the parser?")]}, planner=pl)
said = r["said"]
honest = [x for x in said if "thinking brain" in x]
check("tried the cloud for every doubt", len(pl.calls) == 3)
check("the honest 'can't reach my thinking brain' line is said ONCE", len(honest) == 1, str(honest))
check("no 'cloud brain' wording", not any("cloud brain" in x for x in said))
check("later doubts: a short line, not the whole apology again",
      any(x in ("From this lesson:", P.OFFLINE_AGAIN) for x in said))
parks = [a for m in r["srv"].sent if m["type"] == "actions" for a in m["actions"] if "Parking lot" in json.dumps(a)]
check("doubts are parked on the board", bool(parks))
check("lesson still finishes", r["res"]["finished"])

print("no robotic check-ins")
pl = FakePlanner()
script = {"Chalo! Today": [voice("what is a token?")], "It groups the characters": [voice(DOUBT)],
          "Spaces and comments": [voice("why are comments thrown away?")],
          "So the lexer is": [{"type": "text", "text": "okay"}]}
r = run(script, planner=pl, pace=0.1)
said = r["said"]
checkins = [x for x in said if x in P.CHECKINS]
check("'Shall we continue?' never said", not any("Shall we continue" in x for x in said))
check("check-ins ≤ one per teaching section", len(checkins) <= 2, str(checkins))
after_answer = [said[i + 1] for i, x in enumerate(said[:-1]) if "token ended" in x]
check("never a check-in right after an answer", not any(x in P.CHECKINS for x in after_answer), str(after_answer))
check("never the same bridge twice in a row", all(a != b for a, b in zip(said, said[1:]) if a in P.BRIDGES))
r = run({}, planner=pl, pace=0.001)
check("with a tiny gap a check-in comes at a section end (it exists, just rare)",
      any(x in P.CHECKINS for x in r["said"]))

print("checks: the board focusing the answer box is not a raised hand; a doubt in a check doesn't replay a cue")
r = run({"Which step comes first": [{"type": "hand"}, {"type": "text", "text": "why do we need a parser at all?"},
                                    {"type": "text", "text": "the lexer comes first"}]}, planner=FakePlanner(), check=True)
said = r["said"]
check("no 'Sure, take a moment' when the answer box gets focus (11 Nov log)", not any("take a moment" in x for x in said),
      str([x for x in said if "moment" in x]))
check("the doubt in the check is answered", any("lexer keeps reading" in x for x in said))
check("…then the check is asked again, not 'Back to where we were' + a cue replay",
      not any(x in P.BRIDGES for x in said) and said.count("Which step comes first, the lexer or the parser?") == 2,
      str(said[-8:]))
check("the answer is graded right and the lesson finishes", r["res"]["finished"] and r["res"]["checks_right"] == 1,
      str(r["res"]))

# ------------------------------------------------------------------ 5. the planner's strict-JSON answer + root cause #3
print("planner.answer: strict JSON, 2–4 sentences, ops only draw (fake router)")
from stiti.tutor import planner as PM                                   # noqa: E402
seen = {}


def fake_complete(msgs, **kw):
    seen.update(kw, prompt=msgs[-1]["content"])
    return {"text": json.dumps({"intent": "clarify", "strategy": "direct_explain",
                                "say": ["One.", "Two.", "Three.", "Four.", "Five."],
                                "ops": [{"type": "new_page", "text": "x"}, {"type": "box", "id": "d1", "text": "A",
                                                                            "at": "One"},
                                        {"type": "erase", "ref": "lx"}], "pages": None}),
            "provider": "fake", "model": "fake", "ms": 1}


_orig = router.complete
router.complete = fake_complete
ctx = {"lesson": "L", "segment": "S", "last_said": ["x"], "board": "", "previous": {"q": "how?", "a": ["Like this."]},
       "simpler": True}
d = PM.Planner(None).answer("still confused", ctx)
router.complete = _orig
check("route tutor_answer with the strict schema", seen.get("route") == "tutor_answer" and seen.get("schema")
      is LS.ANSWER_SCHEMA)
check("≤ 4 sentences kept", d["say"] == ["One.", "Two.", "Three.", "Four."])
check("doubt ops never flip/erase the lesson board (new_page, erase dropped)", [o.type for o in d["ops"]] == ["box"])
check("the follow-up prompt carries the earlier answer + 'simpler, everyday example'",
      "EARLIER DOUBT: how?" in seen["prompt"] and "everyday example" in seen["prompt"])

print("every lesson can answer doubts (11 Nov: the demo lesson had no answerer → 'cloud brain' every time)")
from stiti import tutor                                                 # noqa: E402
_st = router.status
router.status = lambda: [{"name": "groq", "key": True}]
a = tutor.answerer(None)
router.status = lambda: [{"name": "groq", "key": False}]
b = tutor.answerer(None)
router.status = _st
check("demo / resumed lesson + a free key → gets a cloud answerer", isinstance(a, PM.Planner))
check("no key at all → honest local answers", b is None)
check("a planned lesson keeps its own planner", tutor.answerer(pl) is pl)
check("thresholds are named constants", all(hasattr(ears, n) for n in ("ECHO_WINDOW_S", "ECHO_TAIL_S", "ECHO_OVERLAP",
                                                                       "MIN_BARGE_WORDS"))
      and all(hasattr(P, n) for n in ("FILLER_AFTER_S", "RESUME_GAP_S", "CHECKIN_MIN_GAP_S")))

print(f"tutor teacher: {passed}/{total} checks passed")
sys.exit(0 if passed == total else 1)
