"""The coach (D53): goal first, quick probes, mastery per concept, ≤ 2 sentences then his turn, notes-page board.
No LLM (a fake `call`), no sound (SilentAudio), throwaway STITI_HOME.

STITI_DB=postgresql:///stiti_test STITI_HOME=<tmp> python tests/tutor_coach_eval.py
"""
from __future__ import annotations

import os
import queue
import sys
import threading
import time

db = os.environ.get("STITI_DB", "")
if not db.rstrip("/").split("/")[-1].startswith("stiti_test"):
    sys.exit(f"refusing to run against {db!r}: use a stiti_test* database")

from stiti.tutor import coach as C  # noqa: E402
from stiti.tutor.audio import SilentAudio  # noqa: E402
from stiti.tutor.mastery import Mastery, bkt  # noqa: E402

passed = total = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global passed, total
    total += 1
    passed += bool(cond)
    print(("  ✓ " if cond else "  ✗ ") + name + ("" if cond else f"  — {detail}"))


CALLS: list[str] = []
TOPIC = [{"unit": "Lexing", "name": n, "points": [f"{n} fact one", f"{n} fact two"], "weight": w}
         for n, w in (("Tokens", 3), ("Regular expressions", 2), ("DFA", 3), ("Longest match", 2))]


def fake_call(system, user, schema, name, max_tokens, **kw):
    CALLS.append(name)
    if name == "concepts":
        return {"concepts": TOPIC}
    if name == "probes":
        return {"probes": [{"concept_id": "c0", "question": "What does a lexer produce?", "expected": ["tokens"]},
                           {"concept_id": "c2", "question": "What is a DFA made of?", "expected": ["states"]},
                           {"concept_id": "c3", "question": "Which match does a scanner take?",
                            "expected": ["longest"]}]}
    if name == "concept":
        n = user.count("item(s)")
        steps = []
        for j in range(2):
            steps.append({"say": ["A lexer reads characters one by one.", "It groups them into tokens."],
                          "board": [{"slot": "point", "kind": "text", "text": "Lexer groups chars into tokens",
                                     "nodes": None, "edges": None, "rows": None},
                                    {"slot": "figure", "kind": "graph", "text": None,
                                     "nodes": [{"id": "a", "text": "chars"}, {"id": "b", "text": "tokens"}],
                                     "edges": [{"from": "a", "to": "b", "text": None}], "rows": None},
                                    {"slot": "example", "kind": "text", "text": "x = 42 → ID EQ NUM",
                                     "nodes": None, "edges": None, "rows": None}],
                          "check": {"kind": "recall", "prompt": "What does the lexer output?", "options": None,
                                    "expectations": ["tokens"], "hints": ["Think of words.", "Not characters."],
                                    "reveal": "Tokens."}})
        return {"steps": steps, "remember": "Lexer: characters in, tokens out"}
    raise AssertionError(name)


# ------------------------------------------------------------------ pure pieces
print("goal, mastery, queue")
check("'I have an exam tomorrow' → exam, 1 day", C.parse_goal("I have an exam tomorrow") == {"mode": "exam", "days": 1})
check("'just want to understand it properly' → learn", C.parse_goal("just want to understand it properly")["mode"]
      == "learn")
check("'exam is today' → exam, 0 days", C.parse_goal("my exam is today evening") == {"mode": "exam", "days": 0})
p = 0.25
seq = [p := bkt(p, v) for v in ("correct", "correct", "wrong")]
check("BKT: right answers raise mastery, a wrong one lowers it", seq[0] > 0.25 and seq[1] > seq[0] and seq[2] < seq[1],
      str(seq))
cs = [C.Concept(id=f"c{i}", name=n["name"], unit="Lexing", points=n["points"], weight=n["weight"], unit_idx=0)
      for i, n in enumerate(TOPIC)]
m = Mastery("test-queue")
m.set("c0", 0.9)
m.set("c1", 0.5)
q = C.order(cs, m, "learn", 60)
check("learn mode: what he knows goes last (one quick check), new ones in book order",
      [c.id for c in q][:3] == ["c1", "c2", "c3"] and q[-1].id == "c0", str([c.id for c in q]))
q = C.order(cs, m, "exam", 7)
check("exam mode with 7 minutes: the nearly-known one makes the cut, the budget holds",
      "c1" in [c.id for c in q] and sum(C.CONCEPT_MIN[m.level(c.id)] for c in q) <= 7, str([c.id for c in q]))

# ------------------------------------------------------------------ concept map + steps
print("\nconcept map and steps")
CALLS.clear()
mp = C.concept_map("compilers for an exam", call=fake_call)
mp2 = C.concept_map("compilers for an exam", call=fake_call)
check("topic → concepts, cached (second time: no LLM call)", len(mp) == 4 and len(mp2) == 4 and CALLS == ["concepts"],
      str(CALLS))
segs = C.concept_segments(mp[0], 0, "new", "exam", None, 4, call=fake_call)
check("new concept → 2 short steps + a Remember line", len(segs) == 3 and segs[-1].id.endswith("r"), str([s.id for s in segs]))
check("every step: ≤ 2 sentences, then his turn (a check)",
      all(len(s.cues) <= 2 and s.check is not None for s in segs[:2]), str([(len(s.cues), bool(s.check)) for s in segs]))
regions = {o.region for s in segs for c in s.cues for o in c.ops if o.region}
check("board notes go to slots (points / figure / example / remember), page title first",
      regions >= {"points", "figure", "example", "remember"} and segs[0].cues[0].ops[0].type == "new_page", str(regions))
n = len(CALLS)
k = C.concept_segments(mp[0], 1, "known", "exam", None, 4, call=fake_call)
check("a concept he knows → one quick check, no re-teaching, no LLM call",
      len(k) == 1 and k[0].check is not None and len(CALLS) == n, str(k))

# ------------------------------------------------------------------ a whole coached session
print("\na whole session (typed answers, no sound)")


class FakeSrv:
    def __init__(self):
        self.sent = []

    def send(self, m):
        self.sent.append(m)


ANSWERS = ["I have my exam tomorrow", "tokens", "I don't know", "the shortest one"] + ["tokens"] * 40
events: queue.Queue = queue.Queue()
srv = FakeSrv()
logs: list[str] = []


def feeder(stop):
    """Answer every 'your turn' (status waiting) with the next scripted line."""
    seen = 0
    while not stop.is_set():
        waits = [m for m in list(srv.sent) if m.get("type") == "status" and m.get("mode") == "waiting"]
        if len(waits) > seen and ANSWERS:
            seen = len(waits)
            time.sleep(0.05)
            events.put({"type": "text", "text": ANSWERS.pop(0)})
        time.sleep(0.02)


coach = C.Coach("compilers for an exam", audio=SilentAudio(scale=0.01), events=events, server=srv,
                log=logs.append, call=fake_call, persist=False, planner=None, pace=0.02, idle_resume_s=0.2,
                check_timeout_s=2)
stop = threading.Event()
threading.Thread(target=feeder, args=(stop,), daemon=True).start()
out = {}
th = threading.Thread(target=lambda: out.setdefault("r", coach.run()), daemon=True)
th.start()
th.join(90)
stop.set()
said = [x[len("Stiti: "):] for x in logs if x.startswith("Stiti: ")]
check("she asks his goal and exam date before teaching anything",
      said and "exam" in said[0].lower() and "what do you need" in said[0].lower(), str(said[:2]))
check("exam tomorrow → exam mode", coach.goal and coach.goal["mode"] == "exam" and coach.goal["days"] == 1, str(coach.goal))
check("3 quick probes asked, answers graded into mastery",
      coach.mastery.level("c0") == "known" or coach.mastery.get("c0") >= 0.8, str(coach.mastery.p))
check("…'I don't know' leaves that concept to teach", coach.after_probes.get("c2", 1) < 0.5, str(coach.after_probes))
check("…and it is in the teaching queue", "c2" in [c.id for c in coach.queue], str([c.id for c in coach.queue]))
check("she says the plan out loud and draws it", any(s.startswith("Here's the plan") for s in said)
      and any(m.get("type") == "actions" and any("Your plan" in str(a) for a in m["actions"]) for m in srv.sent),
      str(said[:8]))
check("the session ran to the end", out.get("r") is not None and not th.is_alive(), str(out))
check("mastery updated after his answers during teaching", any("[mastery]" in x for x in logs), "")
els = coach.t.board.els.values()
over = 0
by_frame: dict = {}
for e in els:
    if e.kind not in ("arrow", "deco"):
        by_frame.setdefault(e.frame, []).append(e)
for fr, es in by_frame.items():
    for i, a in enumerate(es):
        for b in es[i + 1:]:
            if a.x < b.right and b.x < a.right and a.y < b.bottom and b.y < a.bottom:
                over += 1
check("board: nothing on a page overlaps anything else", over == 0, f"{over} overlaps")

# ------------------------------------------------------------------ D42 for the coach: board first, voice ∥ reading
print("\nopens fast: board first, her voice and reading his file at the same time")
import stiti.tutor as T  # noqa: E402
from stiti.tutor import audio as AU  # noqa: E402
from stiti.tutor import server as SV  # noqa: E402

marks: list[tuple[str, float]] = []
t0 = time.time()


def mark(n, wait=0.0):
    marks.append((n, time.time() - t0))
    time.sleep(wait)


class _A:
    def close(self):
        pass


real = (AU.make, C.concept_map, C.Coach.run, SV.BoardServer.start, SV.BoardServer.open_browser, SV.BoardServer.stop)
AU.make = lambda mode, events, debug=False, scale=1.0: (mark("voice loading", 0.5), _A())[1]
C.concept_map = lambda *a, **k: (mark("reading file", 0.5), [])[1]
C.Coach.run = lambda self: (self._future.result(), mark("session running"),
                            {"finished": True, "checks_right": 0, "checks_graded": 0, "questions": 0})[2]
SV.BoardServer.start = lambda self: (self.connected.set(), mark("board started"), self)[2]
SV.BoardServer.open_browser = lambda self: mark("browser opened")
SV.BoardServer.stop = lambda self: None
try:
    t0 = time.time()
    T._teach(["compilers", "--silent"])
finally:
    AU.make, C.concept_map, C.Coach.run, SV.BoardServer.start, SV.BoardServer.open_browser, SV.BoardServer.stop = real
at = dict(marks)
check("the board is on screen before anything slow starts", at.get("browser opened", 9) < 0.3
      and at["browser opened"] <= min(at.get("voice loading", 9), at.get("reading file", 9)), str(marks))
check("voice loading and reading his file overlap (not one after the other)",
      abs(at.get("voice loading", 0) - at.get("reading file", 9)) < 0.3 and at.get("session running", 9) < 0.9,
      str(marks))

print(f"tutor coach: {passed}/{total} checks passed")
sys.exit(0 if passed == total else 1)
