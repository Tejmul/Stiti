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
os.environ.setdefault("STITI_BOARD_FIXED", "0")     # tests: random ports, no waiting for a board tab
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

print("opening a lesson (D42): board first, plan while her voice loads; 'end' ends it")
from stiti.tutor import audio as AU, commands as CM, server as SV      # noqa: E402

order, t_open = [], time.time()
real = dict(make=AU.make, lesson=tutor.make_lesson, start=SV.BoardServer.start, opened=SV.BoardServer.open_browser,
            stop=SV.BoardServer.stop, run=P.Tutor.run, ans=tutor.answerer)


def _mark(name, wait=0.0):
    order.append((name, round(time.time() - t_open, 2)))
    time.sleep(wait)


class _Aud:
    def close(self):
        _mark("audio closed")


def _slow_audio(mode, events, debug=False, scale=1.0):
    _mark("audio loading", 0.5)
    return _Aud()


def _slow_plan(target, args, say=print):
    _mark("planning", 0.5)
    return LS.load(LS.demos()["compiler"]), None, 0


got = {}
AU.make, tutor.make_lesson = _slow_audio, _slow_plan
SV.BoardServer.start = lambda self: (got.update(srv=self, waiting=self.on_connect()), _mark("board started"), self)[2]
SV.BoardServer.open_browser = lambda self: _mark("browser opened")
SV.BoardServer.stop = lambda self: None
P.Tutor.run = lambda self: (got.update(connect=got["srv"].on_connect()), _mark("lesson running"),
                            {"finished": True, "checks_right": 0, "checks_graded": 0, "questions": 0,
                             "cards_saved": 0})[2]
try:
    t_open = time.time()
    res = tutor._teach(["some topic", "--silent", "--classic"])
finally:
    AU.make, tutor.make_lesson = real["make"], real["lesson"]
    SV.BoardServer.start, SV.BoardServer.open_browser = real["start"], real["opened"]
    SV.BoardServer.stop, P.Tutor.run = real["stop"], real["run"]
names = [n for n, _ in order]
at = dict(order)
check("the board opens before her voice loads or the lesson is planned",
      names.index("browser opened") < min(names.index("audio loading"), names.index("planning")), str(order))
check("the board is on screen within 0.3 s", at["browser opened"] < 0.3, str(order))
check("voice loading and planning run at the same time (not one after the other)",
      at["lesson running"] < 0.9 + 15.5 and abs(at["audio loading"] - at["planning"]) < 0.3, str(order))
check("while it loads the board says what's happening",
      got.get("waiting") and got["waiting"][0]["type"] == "status" and "some topic" in got["waiting"][0]["caption"],
      str(got.get("waiting")))
check("once the lesson exists, a (re)loaded page gets the lesson board, not the waiting line",
      got.get("connect") and got["connect"][0]["type"] == "reset", str(got))
order.clear()
tutor.make_lesson = lambda target, args, say=print: (_ for _ in ()).throw(SystemExit("No key."))
AU.make = _slow_audio
SV.BoardServer.start = lambda self: self
SV.BoardServer.open_browser = lambda self: None
SV.BoardServer.stop = lambda self: _mark("board stopped")
try:
    res2 = tutor._teach(["some topic", "--silent", "--classic"])
finally:
    AU.make, tutor.make_lesson = real["make"], real["lesson"]
    SV.BoardServer.start, SV.BoardServer.open_browser, SV.BoardServer.stop = real["start"], real["opened"], real["stop"]
check("a lesson that can't be planned closes the voice and the board, no crash",
      res2 == {"finished": False} and {"audio closed", "board stopped"} <= {n for n, _ in order}, f"{res2} {order}")
for t in ("end", "End.", "end it", "finish", "end the lesson", "stop the class", "bas karo"):
    check(f"{t!r} ends the lesson", CM.classify(t) == "end", CM.classify(t))
for t, want in (("stop", "pause"), ("the end of the array", "question"), ("finish the loop first?", "question"),
                ("end index is what", "question")):
    check(f"{t!r} is not 'end'", CM.classify(t) == want, CM.classify(t))

# ------------------------------------------------------------------ D52: his whole sentence, and he can change the plan
print("\nshe waits for his whole sentence and changes the plan when he asks (D52)")


class SteerPlanner(FakePlanner):
    def __init__(self, decision):
        super().__init__()
        self.decision, self.steers = decision, []

    def steer(self, text, ctx):
        self.steers.append((text, ctx))
        return dict(self.decision)


pl = FakePlanner()
r = run({"The lexer reads": [voice("What happens to"), voice("the spaces between tokens?")]}, planner=pl, pace=0.3)
check("two pieces of his speech → ONE doubt with his whole sentence",
      [c[0] for c in pl.calls] == ["What happens to the spaces between tokens?"], str([c[0] for c in pl.calls]))
check("…she stopped talking while he spoke (no overlap)", r["audio"].overlaps == 0 and r["audio"].stops, "")

pl = SteerPlanner({"action": "skip_to", "part": 3, "target": None, "say": "Okay, straight to why tokens."})
r = run({"Think of reading": [voice("I already know this part, go to why tokens")]}, planner=pl, pace=0.1)
said = r["said"]
check("'I already know this, go to…' → she jumps to that part (not a doubt, not parked)",
      pl.steers and "Okay, straight to why tokens." in said and not pl.calls
      and not any(s.startswith("The lexer reads") for s in said)
      and any(s.startswith("The parser then reads") for s in said), str(said[:8]))
check("…the planner saw the parts of the lesson", pl.steers and pl.steers[0][1]["parts"][2] == "Why tokens",
      str(pl.steers[0][1] if pl.steers else None))

pl = SteerPlanner({"action": "crash", "part": None, "target": None, "say": "Got it, exam tomorrow. Whole thing, fast."})
r = run({"The lexer reads": [voice("Tomorrow."), voice("I have an exam so cover the whole thing quickly")]}, planner=pl,
        pace=0.3)
sw = r["t"].switch
check("'Tomorrow.' + 'I have an exam…' → one request, kept whole (the short first word isn't lost)",
      sw is not None and sw["request"].startswith("Tomorrow") and "exam" in sw["request"], str(sw))
check("…exam → a crash course is planned and this lesson ends (never 'let's park this')",
      sw is not None and sw["mode"] == "crash" and r["t"].ended
      and "Got it, exam tomorrow. Whole thing, fast." in r["said"]
      and not any("park" in s.lower() for s in r["said"]), str(r["said"][-3:]))

r = run({"The lexer reads": [voice("I have an exam tomorrow, I want the whole syllabus")]}, planner=None, pace=0.1)
check("no cloud brain: 'exam tomorrow' still becomes a crash course", (r["t"].switch or {}).get("mode") == "crash",
      str(r["t"].switch))
for t, want in (("Bro, I don't need to go from all start bro.", "steer"),
                ("bro i have a exam tomorrow i want to study a differnet syllabus", "steer"),
                ("what is a token?", "question"), ("it produces tokens", "answer")):
    check(f"{t[:40]!r} → {want}", CM.classify(t, answering=want == "answer" or t.startswith("Bro")) == want,
          CM.classify(t, answering=True))

# ------------------------------------------------------------------ D53: a doubt finds where he's stuck, then checks it
print("\na doubt: where he's stuck → the fix → one check question → pinned to his notes (D53)")


class BridgePlanner(FakePlanner):
    def answer(self, question, ctx):
        d = super().answer(question, ctx)
        d.update({"stuck_at": "what ends a token", "error_type": "missing_prerequisite",
                  "check": {"prompt": "So what tells the lexer a token ended?", "expected": "a space"}})
        return d


pl = BridgePlanner()
r = run({"The lexer reads": [voice("How does the lexer know where a token ends?")],
         "So what tells the lexer": [{"type": "text", "text": "a space"}]}, planner=pl, pace=0.3)
check("after the answer she asks ONE check question about the gap", "So what tells the lexer a token ended?" in r["said"],
      str(r["said"][:12]))
check("…his right reply gets 'Yes, exactly.' (graded locally, no LLM)", "Yes, exactly." in r["said"], str(r["said"][:14]))
check("…where he was stuck is logged", any("stuck at: what ends a token" in x for _, x in r["logs"]), "")
stick = [e for e in r["t"].board.els.values() if e.kind == "sticky" and e.region == "doubts"]
check("his doubt is pinned to the page's doubts strip (his notes)", len(stick) == 1
      and "How does the lexer" in getattr(stick[0], "label", ""), str([getattr(e, "label", "") for e in stick]))

# ------------------------------------------------------------------ hold-to-talk: room voices don't count
print("\nhold-to-talk: only what he says while holding the key counts")
pl = FakePlanner()
r = run({"Think of reading": [{"type": "ptt_mode", "on": True}, voice("Where did you play yesterday, my child?")],
         "The lexer reads": [{"type": "ptt", "down": True}, voice("What happens to the spaces between tokens?"),
                             {"type": "ptt", "down": False}]}, planner=pl, pace=0.3)
qs = [c[0] for c in pl.calls]
check("with hold-to-talk on, a room voice is ignored (not answered, not graded)",
      not any("play yesterday" in q for q in qs)
      and any("not holding the talk key" in x for _, x in r["logs"]), str(qs))
check("…and what he says while holding the key is answered", any("spaces between tokens" in q for q in qs), str(qs))

# ------------------------------------------------------------------ Feature 5: the hint ladder, owned by code
print("\nthe hint ladder: nudge → hint → worked example → answer; the rung reached is kept → rating")
from stiti.tutor.audio import SilentAudio                                # noqa: E402


def ladder_run(answers, *, example=True, hints=True, kind="recall", options=None, exps=None):
    """One check; after the check prompt and every ladder line, his next answer."""
    les = LS.from_dict({"title": "Lexers", "topic": "lexers", "segments": [
        {"id": "t1", "type": "teach", "title": "Longest match", "cues": [
            {"say": "The scanner keeps reading while the characters still fit a token.", "ops": []}],
         "check": {"kind": kind, "prompt": "Which match does the scanner take when two tokens fit?",
                   "options": options, "expectations": exps or ["the longest match"],
                   "hints": ["Think about how much it reads."] if hints else [],
                   "reveal": "The longest match wins."}}]})
    if example:
        les.segments[0].check.example = ["'iffy' could be 'if' + 'fy'", "but 'iffy' is longer", "so: one name"]
    ev, logs, todo = queue.Queue(), [], list(answers)
    started = [False]

    def log(line):
        logs.append(line)
        if line.startswith("Stiti: Which match does the scanner"):
            started[0] = True
        if started[0] and line.startswith("Stiti: ") and todo and not line.startswith(("Stiti: Here's the answer",
                                                                                       "Stiti: Close. ", "Stiti: Yes")):
            a = todo.pop(0)
            threading.Timer(0.05, lambda: ev.put({"type": "text", "text": a})).start()
    t = Tutor(les, audio=SilentAudio(scale=0.01), events=ev, server=FakeSrv(), planner=None, persist=False, log=log,
              pace=0.02, idle_resume_s=0.2, check_timeout_s=3)
    res = t.run()
    said = [x[len("Stiti: "):] for x in logs if x.startswith("Stiti: ")]
    return res["results"][0] if res.get("results") else {}, said


rec, said = ladder_run(["the first one it sees", "the shortest possible", "no idea", "still no clue"])
check("four misses climb every rung in order: nudge → hint → worked example → answer",
      rec.get("ladder") == ["nudge", "hint", "example", "answer"] and rec.get("rung") == 4, str(rec))
i_n = next((i for i, s in enumerate(said) if s.startswith("Not quite. Think about")), 99)
i_h = next((i for i, s in enumerate(said) if "Hint: Think about how much" in s), 99)
i_e = next((i for i, s in enumerate(said) if s.startswith("Let me show you one step: 'iffy'")), 99)
i_a = next((i for i, s in enumerate(said) if s.startswith("Here's the answer. The longest match")), 99)
check("…said in that order, the worked step is ONE line of the example (no LLM)", i_n < i_h < i_e < i_a < 99,
      str(said))
check("…and the record rates it 'again' (FSRS)", rec.get("rating") == "again" and rec.get("verdict") == "wrong", str(rec))
rec, said = ladder_run(["the first one", "the longest match"])
check("right after the nudge → rung 'nudge', rated hard", rec.get("verdict") == "correct" and rec.get("rung") == 1
      and rec.get("rating") == "hard", str(rec))
rec, said = ladder_run(["the longest match"])
check("right at once → rung none, rated good", rec.get("rung") == 0 and rec.get("rating") == "good", str(rec))
rec, said = ladder_run(["I don't know", "the longest match"])
check("'I don't know' skips the pump: straight to the hint", rec.get("ladder") == ["hint"]
      and any(s.startswith("No worries. Hint:") for s in said), str(said))
rec, said = ladder_run(["no idea", "no idea", "no idea"], example=False, hints=False)
check("no hint and no example → the worked step is the start of the answer", rec.get("ladder") == ["example", "answer"]
      and any(s.startswith("Here's how it starts: The longest") for s in said), str(said))
rec, said = ladder_run(["the longest", "the longest"], exps=["the longest match", "it is read left to right"])
check("a partial answer's nudge points at what's missing without giving it away",
      any(s.startswith("Good start, you've got part of it.") and "What else?" in s and "left to right" not in s
          for s in said), str(said))
rec, said = ladder_run(["A", "A"], kind="mcq", options=[{"text": "the first match", "correct": False},
                                                         {"text": "the longest match", "correct": True},
                                                         {"text": "the shortest match", "correct": False}],
                       example=False, hints=False)
check("MCQ: the worked step rules out a wrong option", any(s.startswith("Here's a step: it's not") for s in said),
      str(said))

# never the same question twice — a plain lesson too
print("\nnever the same question twice in a session")
les = LS.from_dict({"title": "Dup", "topic": "dup", "segments": [
    {"id": f"t{i}", "type": "teach", "title": f"Part {i}", "cues": [{"say": f"Sentence number {i}.", "ops": []}],
     "check": {"kind": "recall", "prompt": "Quick one: What does a lexer produce?" if i else "What does a lexer produce?",
               "expectations": ["tokens"], "hints": [], "reveal": "Tokens."}} for i in range(2)]})
ev2: queue.Queue = queue.Queue()
lg2: list[str] = []


def log2(line):
    lg2.append(line)
    if "lexer produce" in line and line.startswith("Stiti: "):
        threading.Timer(0.05, lambda: ev2.put({"type": "text", "text": "tokens"})).start()


r2 = Tutor(les, audio=SilentAudio(scale=0.01), events=ev2, server=FakeSrv(), planner=None, persist=False, log=log2,
           pace=0.02, idle_resume_s=0.2).run()
check("the same question (after normalising) is asked once, the repeat is skipped",
      sum(1 for x in lg2 if x.startswith("Stiti:") and "lexer produce" in x) == 1
      and any("skipped a repeated question" in x for x in lg2) and r2["finished"], str(lg2[-6:]))

les = LS.from_dict({"title": "Few", "topic": "few", "segments": [
    {"id": f"t{i}", "type": "teach", "title": f"Part {i}", "cues": [{"say": f"This is teaching sentence {i}.", "ops": []}],
     "check": {"kind": "recall", "prompt": f"Question number {i}?", "expectations": ["x"], "hints": [],
               "reveal": "X."}} for i in range(2)]})
ev4: queue.Queue = queue.Queue()
lg4: list[str] = []


def log4(line):
    lg4.append(line)
    if line.startswith("Stiti: This is teaching sentence 0") and not any("just teach" in x for x in lg4):
        threading.Timer(0.05, lambda: ev4.put({"type": "text", "text": "just teach"})).start()


r4 = Tutor(les, audio=SilentAudio(scale=0.01), events=ev4, server=FakeSrv(), planner=None, persist=False, log=log4,
           pace=0.02, idle_resume_s=0.2).run()
said4 = [x[len("Stiti: "):] for x in lg4 if x.startswith("Stiti: ")]
check("a plain lesson too: 'just teach' → 'Okay, fewer questions.' once, and the quick checks are held back",
      said4.count("Okay, fewer questions.") == 1 and not any(s.startswith("Question number") for s in said4)
      and r4["finished"], str(said4))

# speech he starts while she is still asking is his answer; speech from before the question is not
print("\nlisten(): drop only speech that started before her question")
fa = FakeAudio()
ev3: queue.Queue = queue.Queue()
lg3: list[str] = []
t3 = Tutor(make_lesson(), audio=fa, events=ev3, server=FakeSrv(), planner=None, persist=False, log=lg3.append, pace=0.1)
now = time.monotonic()
ev3.put(voice("my exam is on friday I think", at=now - 6.0))          # said before the question
ev3.put({"type": "text", "text": "typed before the question"})
ev3.put(voice("tomorrow I have the exam", at=now + 0.05))              # started as she started asking
got = t3.listen("Is this for an exam, and when?", timeout=4)
check("speech that started while she asked is kept as his answer (not 'dropped, said before the question')",
      got is not None and "tomorrow I have the exam" in got, f"{got!r} {[x for x in lg3 if 'dropped' in x]}")
check("…speech and typing from before the question are still dropped",
      sum("dropped, said before the question" in x for x in lg3) == 2 and "friday" not in (got or ""), str(lg3))
lg3.clear()


def late():
    time.sleep(0.1)
    ev3.put(voice("this is old speech from before", at=time.monotonic() - 8.0))   # in flight when she asked
    time.sleep(0.15)
    ev3.put(voice("it is next week on monday", at=time.monotonic() - 0.1))


threading.Thread(target=late, daemon=True).start()
got = t3.listen("When is it?", timeout=6)
check("old speech still in flight when she asked is not taken as the answer; the real one is",
      got is not None and "next week" in got and "old speech" not in got, f"{got!r} {lg3}")

print(f"tutor teacher: {passed}/{total} checks passed")
sys.exit(0 if passed == total else 1)
