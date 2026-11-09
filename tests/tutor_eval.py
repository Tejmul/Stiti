"""Whiteboard tutor eval (no LLM, no audio, no browser needed).

STITI_DB=postgresql:///stiti_test STITI_HOME=<tmp> uv run python tests/tutor_eval.py
Checks: demo lesson loads + sanitises, layout has no overlaps, LLM schemas fit Cerebras' 5,000-char limit,
`at` timing, Hinglish control words, local grading, a full scripted silent lesson (pause/question/repeat/
hints/confidence/hook revisit) saved to Postgres, board-server security, printed-contents book parser,
and voice phrases that launch the tutor.
"""
from __future__ import annotations

import asyncio
import json
import queue
import threading
from itertools import combinations

from stiti.tutor import commands, grade, lesson, skills, voice_request
from stiti.tutor import book as bookmod
from stiti.tutor.audio import SilentAudio
from stiti.tutor.lesson import Check
from stiti.tutor.player import Tutor
from stiti.tutor.server import BoardServer

ok = fail = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global ok, fail
    ok += cond
    fail += not cond
    print(f"{'✅' if cond else '❌'} {name}" + (f" — {detail}" if detail and not cond else ""))


# ---------------------------------------------------------------- lesson + layout
L = lesson.load(lesson.demos()["compiler"])
check("demo lesson loads", len(L.segments) == 8 and len(L.cue_list()) == 24, f"{len(L.segments)} segs")
bad = lesson.from_dict({"segments": [{"cues": [{"say": "hi", "ops": [{"type": "nope"}, {"type": "box", "text": "x" * 99},
                                                                   {"type": "arrow"}]}]}]})
ops = bad.segments[0].cues[0].ops
check("sanitizer drops unknown/invalid ops, clips labels", len(ops) == 1 and len(ops[0].text) == lesson.MAX_LABEL)

b = skills.Board()
for s in L.segments:
    for c in s.cues:
        b.apply_all(c.ops)
solid = [e for e in b.els.values() if e.kind not in ("arrow", "deco")]
overlaps = [(a.id, c.id) for a, c in combinations(solid, 2) if a.frame == c.frame
            and a.x < c.right and c.x < a.right and a.y < c.bottom and c.y < a.bottom]
check("demo layout: no overlapping elements", not overlaps, str(overlaps[:3]))
tree = {i: b.ref(i) for i in ("asg", "plus", "mul", "rate", "n60")}
check("syntax tree: children centred under parents",
      abs((tree["rate"].cx + tree["n60"].cx) / 2 - tree["mul"].cx) < 2 and tree["mul"].y > tree["plus"].y)
snap = b.snapshot()
n_log = len(b.log)
b.apply(lesson.Op(type="box", text="extra"))
b.restore(snap)
check("snapshot/restore rewinds board + log", len(b.log) == n_log and "extra" not in [getattr(e, "label", "") for e in b.els.values()])
check("long chain wraps instead of overflowing",
      skills.layered_layout([{"id": str(i), "text": "x"} for i in range(6)],
                            [{"from": str(i), "to": str(i + 1)} for i in range(5)],
                            {str(i): (200, 66) for i in range(6)}, "", 1040, 610)[1].startswith(("LRwrap", "TB")))

for name, sch in (("segment", lesson.SEGMENT_SCHEMA), ("answer", lesson.ANSWER_SCHEMA)):
    n = len(json.dumps(sch))
    check(f"{name} schema ≤ 5,000 chars (Cerebras strict limit)", n <= 5000, f"{n} chars")

check("at: word bookmark → proportional time", lesson.resolve_at("tokens", "the lexer makes tokens", 2000, 0) ==
      int(2000 * len("the lexer makes ") / len("the lexer makes tokens")))
check("at: fraction / start / end", lesson.resolve_at("0.5", "x", 2000) == 875 and lesson.resolve_at("start", "x", 2000) == 0)

# ---------------------------------------------------------------- control words + grading
cases = {"ruko": "pause", "ek minute": "pause", "phir se": "repeat", "dobara bolo": "other", "peeche jao": "back",
         "skip": "next", "dheere": "slower", "jaldi bolo": "faster", "aage badho": "resume", "haan": "resume",
         "bas karo": "end", "samajh nahi aaya": "confused", "what is a token?": "question",
         "kya hota hai parser": "question", "hindi mein bolo": "hindi"}
wrong = {t: commands.classify(t) for t, want in cases.items() if commands.classify(t) != want and want != "other"}
check(f"Hinglish control words ({len(cases)} phrases)", not wrong, str(wrong))
check("while answering, a sentence is an answer", commands.classify("the parser catches it", answering=True) == "answer")

mcq = L.segments[2].check
g = [grade.grade(mcq, a, semantic=False)["verdict"] for a in ("B", "parser", "I think it's the lexer", "the second one",
                                                              "pata nahi")]
check("MCQ grading: letter / word / ordinal / idk", g == ["correct", "correct", "wrong", "correct", "idk"], str(g))
why = L.segments[4].check
r = grade.grade(why, "one intermediate code lets the same front end work with many machines; optimizing is easier")
check("open answer: expectation coverage", r["verdict"] == "correct", str(r))
r = grade.grade(why, "so it can work for many machines")
check("open answer: partial credit", r["verdict"] in ("partial", "correct"), str(r))
check("confidence parser", [grade.parse_confidence(x) for x in ("4", "paanch", "pakka", "thoda")] == [4, 5, 5, 2])

# ---------------------------------------------------------------- full scripted lesson (silent, saved)
ev: queue.Queue = queue.Queue()
answers = iter(["it splits it into words", "lexer", "parser", "pata nahi",
                "the same front end works with many machines, and optimizing simple code is easier",
                "lexer then parser then semantic analysis", "4", "C", "5"])
sent: list[dict] = []


class FakeSrv:
    def send(self, m):
        sent.append(m)
        put = lambda x: threading.Timer(0.03, lambda: ev.put(x)).start()  # noqa: E731
        first = lambda cid: m.get("cue_id") == cid and sum(x.get("cue_id") == cid for x in sent) == 1  # noqa: E731
        if m["type"] == "check" or (m["type"] == "status" and str(m.get("caption", "")).startswith(
                ("Not quite", "No worries", "Good start", "Quick one"))):
            put({"type": "text", "text": next(answers)})
        if m["type"] == "cue" and first("s3c2"):
            put({"type": "voice", "text": "wait what is a token?"})
        if m["type"] == "cue" and first("s4c2"):
            put({"type": "control", "cmd": "pause"})
            threading.Timer(0.3, lambda: ev.put({"type": "voice", "text": "aage badho"})).start()
        if m["type"] == "cue" and first("s5c1"):
            put({"type": "voice", "text": "phir se"})


t = Tutor(L, audio=SilentAudio(0.005), events=ev, server=FakeSrv(), persist=True, log=lambda *_: None,
          idle_resume_s=0.3)
res = t.run()
verdicts = [x["verdict"] for x in res["results"]]
check("scripted lesson finishes", res["finished"], str(res))
check("checks: predict + 4 correct (hint ladder used)", verdicts == ["predict", "correct", "correct", "correct", "correct"]
      and res["results"][1]["hints"] == 1, str(verdicts))
check("confidence recorded on quiz checks", [x["confidence"] for x in res["results"][3:]] == [4, 5])
check("question answered locally + resumed", res["questions"] == 1 and any(
    m["type"] == "status" and "Achha, wapas" in str(m.get("caption")) for m in sent))
check("pause / repeat replay the cue (board reset)", sum(m["type"] == "reset" for m in sent) >= 2)
check("hook revisited at the wrap-up", any("Remember your guess" in str(m.get("caption")) for m in sent))
from stiti.db import one  # noqa: E402
row = one("SELECT finished, cursor, jsonb_array_length(results) n FROM tutor_sessions ORDER BY id DESC LIMIT 1")
cards = one("SELECT count(*) n FROM study_cards")["n"]
ep = one("SELECT text FROM episodes WHERE text LIKE 'Tutor lesson on%%' ORDER BY id DESC LIMIT 1")
check("session, 5 revision cards and a memory episode saved", row and row["finished"] and row["n"] == 5 and cards == 5
      and ep is not None, f"{row} cards={cards}")

# ---------------------------------------------------------------- board server security
srv = BoardServer(on_connect=lambda: [{"type": "reset", "actions": []}]).start()


async def ws_try(origin: str, tok: str) -> str:
    import websockets
    try:
        async with websockets.connect(f"ws://127.0.0.1:{srv.port}/ws?t={tok}", origin=origin) as w:
            return json.loads(await w.recv())["type"]
    except Exception as e:
        return type(e).__name__


good_origin = f"http://127.0.0.1:{srv.port}"
r1 = asyncio.run(ws_try(good_origin, srv.token))
r2 = asyncio.run(ws_try("http://evil.example", srv.token))
r3 = asyncio.run(ws_try(good_origin, "wrong"))
import httpx  # noqa: E402
h1 = httpx.get(f"http://127.0.0.1:{srv.port}/").status_code
h2 = httpx.get(f"http://127.0.0.1:{srv.port}/", headers={"host": "evil.example"}).status_code
csp = httpx.get(f"http://127.0.0.1:{srv.port}/").headers.get("content-security-policy", "")
srv.stop()
check("board WS: right origin+token → reset; wrong origin/token refused", r1 == "reset" and r2 != "reset" and r3 != "reset",
      f"{r1} {r2} {r3}")
check("board page: Host check + CSP", h1 == 200 and h2 == 400 and "frame-ancestors 'none'" in csp, f"{h1} {h2}")

# ---------------------------------------------------------------- book: printed contents parser
pages = ["TABLE OF CONTENTS\n1 Introduction 1\n1.1 Language Processors ........ 1\n1.2 The Structure of a Compiler ..... 4\n"
         "1.2.1 Lexical Analysis ........ 5\n2 A Simple Translator 39\n2.1 Introduction ........ 40\n"
         "2.2 Syntax Definition ........ 42\n2.2.1 Definition of Grammars ....... 42\n3 Lexical Analysis 109\n"] + \
        [f"{i - 9} CHAPTER X\nbody text" if i % 2 else f"SECTION {i - 9}\nbody" for i in range(1, 140)]
labels = [bookmod._printed_label(p, i) for i, p in enumerate(pages)]
secs = bookmod.parse_contents(pages, labels)
names = [s.name for s in secs]
check("book: printed contents → sections with page offsets", len(secs) == 9 and names[0] == "1 Introduction"
      and secs[2].page - secs[0].page == 3, f"{names[:3]} {[s.page for s in secs[:3]]}")

# ---------------------------------------------------------------- voice phrases
vr = {t: voice_request(t) for t in ("teach me how DNS works", "DNS padhao", "continue my lesson", "set an alarm for 6")}
check("voice: launch phrases", vr == {"teach me how DNS works": ("how DNS works", False), "DNS padhao": ("DNS", False),
                                      "continue my lesson": (None, True), "set an alarm for 6": None}, str(vr))

print(f"tutor: {ok}/{ok + fail} checks passed")
raise SystemExit(1 if fail else 0)
