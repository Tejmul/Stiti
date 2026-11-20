"""The coach (D53): goal first, quick probes, mastery per concept, ≤ 2 sentences then his turn, notes-page board.
No LLM (a fake `call`), no sound (SilentAudio), throwaway STITI_HOME.

STITI_DB=postgresql:///stiti_test STITI_HOME=<tmp> python tests/tutor_coach_eval.py
"""
from __future__ import annotations

import os
os.environ.setdefault("STITI_BOARD_FIXED", "0")     # tests: random ports, no waiting for a board tab
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
# day mode: "if I give my entire syllabus it should be able to teach me in a day"
for said, hours in (("teach me the whole syllabus today", 6.0), ("I want to finish everything in 4 hours", 4.0),
                    ("cover all the units by tonight", 6.0), ("whole syllabus today, I have four hours", 4.0),
                    ("the entire portion in one day, two and a half hours", 2.5)):
    g = C.parse_goal(said)
    check(f"day mode: {said!r} → day, {hours:g} h", g["mode"] == "day" and g["hours"] == hours and g["days"] == 0, str(g))
check("day mode: hours he never said are marked as a default",
      C.parse_goal("teach me the whole syllabus today")["hours_said"] is False
      and C.parse_goal("everything in 4 hours")["hours_said"] is True)
check("…exam phrases stay exam ('ah' is not an hour): 'ah okay, exam tomorrow' → exam, 1 day",
      C.parse_goal("ah okay, I have an exam tomorrow") == {"mode": "exam", "days": 1})
check("…'my exam is in 3 hours' → exam today, the plan fits in 3 hours",
      C.parse_goal("my exam is in 3 hours") == {"mode": "exam", "days": 0, "hours": 3.0})
check("…'I need a hand' is not an hour", C.parse_goal("I need a hand to understand it")["mode"] == "learn")
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
q = C.order(cs, m, "day", 6 * 60 * 0.85)
check("day mode, 6 hours: every concept he doesn't know is taught, the known one as a quick check, in book order",
      [c.id for c in q] == ["c0", "c1", "c2", "c3"], str([c.id for c in q]))
q = C.order(cs, m, "day", 11)
check("day mode, too little time: the heaviest concepts first (DFA w3 in, Longest match w2 out), budget holds, "
      "known one still checked",
      [c.id for c in q] == ["c0", "c1", "c2"] and sum(C.CONCEPT_MIN[m.level(c.id)] for c in q) <= 11,
      str([c.id for c in q]))

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

# ------------------------------------------------------------------ still wrong → again; recap; notes; welcome back
print("\nhe keeps getting it wrong → she comes back to it; recap; notes saved; next time: welcome back")


def session(source, answers, hold_s=0.4):
    """A whole coached session: every 'your turn' (status waiting) gets the next scripted answer; every pause
    ('paused — say continue', e.g. a day-mode break) is held hold_s, then answered "continue". co.pauses records,
    per pause: the cue it came after, cues sent when it began and after holding (equal = she really waited)."""
    ev: queue.Queue = queue.Queue()
    sv = FakeSrv()
    lg: list[str] = []
    stop = threading.Event()
    pauses: list[dict] = []

    def cues():
        return [m for m in list(sv.sent) if m.get("type") == "cue"]

    def feed():
        seen = held = 0
        while not stop.is_set():
            sent = list(sv.sent)
            waits = [m for m in sent if m.get("type") == "status" and m.get("mode") == "waiting"]
            paused = [m for m in sent if m.get("type") == "status" and m.get("mode") == "paused"
                      and m.get("text") == "paused — say continue"]
            if len(paused) > held:
                held = len(paused)
                before = cues()
                time.sleep(hold_s)
                pauses.append({"after": before[-1]["cue_id"] if before else None, "cues_at": len(before),
                               "cues_held": len(cues())})
                ev.put({"type": "text", "text": "continue"})
            elif len(waits) > seen and answers:
                seen = len(waits)
                time.sleep(0.05)
                ev.put({"type": "text", "text": answers.pop(0)})
            time.sleep(0.02)
    co = C.Coach(source, audio=SilentAudio(scale=0.01), events=ev, server=sv, log=lg.append, call=fake_call,
                 persist=False, planner=None, pace=0.02, idle_resume_s=0.2, check_timeout_s=2)
    co.pauses, co.sent = pauses, sv.sent
    threading.Thread(target=feed, daemon=True).start()
    res = {}
    th = threading.Thread(target=lambda: res.setdefault("r", co.run()), daemon=True)
    th.start()
    th.join(120)
    stop.set()
    return co, [x[len("Stiti: "):] for x in lg if x.startswith("Stiti: ")], res.get("r")


co2, said2, r2 = session("compilers second test", ["exam tomorrow", "no idea", "no idea", "no idea"] + ["no idea"] * 120)
check("concepts still wrong after their steps come back later, from another angle",
      any(s.startswith("Before we finish, let's come back to") for s in said2)
      and any(sg.id.endswith("v") or "v" in sg.id.split("s")[0] for sg in co2.L.segments)
      and any(sg.cues[0].ops and sg.cues[0].ops[0].type == "new_page" and "again" in (sg.cues[0].ops[0].text or "")
              for sg in co2.L.segments), str(said2[-6:]))
check("a 'Today' recap is said at the end (to revise: …, asked first next time)",
      any(s.startswith("That's it for today.") and "To revise" in s for s in said2), str(said2[-3:]))
notes = co2.notes_path.read_text() if co2.notes_path else ""
check("his notes are saved as readable markdown (concepts, points, examples, Remember)",
      co2.notes_path is not None and notes.startswith("# ") and "## Tokens" in notes and "- Lexer groups" in notes
      and "e.g." in notes and "**Remember:**" in notes, notes[:300])
check("the session finished normally", r2 is not None and r2.get("finished"), str(r2))
co3, said3, r3 = session("compilers second test", ["exam tomorrow"] + ["tokens"] * 120)
check("next session on the same file: 'Welcome back', no probe questions again",
      any(s.startswith("Welcome back") for s in said3) and co3.returning
      and not any("quick questions first" in s for s in said3), str(said3[:4]))

# ------------------------------------------------------------------ day mode: the whole syllabus in a day
print("\nday mode: the whole syllabus today — breaks she waits at, progress across the day, same-day resume")
real_break = C.BREAK_EVERY_MIN
C.BREAK_EVERY_MIN = 5                                 # a break after every ~5 estimated minutes (not 45)
try:
    cod, saidd, rd = session("compilers day test", ["teach me the whole syllabus today in 4 hours", "tokens",
                                                    "I don't know", "the shortest one"] + ["tokens"] * 120)
finally:
    C.BREAK_EVERY_MIN = real_break
check("day goal heard: day mode, 4 hours", cod.goal and cod.goal["mode"] == "day" and cod.goal["hours"] == 4.0,
      str(cod.goal))
check("first session of the day: nothing is 'done today already' (his probe answers don't count)",
      not cod.done_today and not any("done today already" in s for s in saidd), str(saidd[:8]))
plan = next((s for s in saidd if s.startswith("Here's the plan")), "")
check("the plan line says the time it takes and his 4 hours", "4 hours" in plan and "breaks" in plan
      and "minutes" in plan, plan)
check("the whole syllabus is in the queue (all 4 concepts)", [c.id for c in cod.queue] == ["c0", "c1", "c2", "c3"],
      str([c.id for c in cod.queue]))
brks = [sg for sg in cod.L.segments if sg.type == "break"]
check("breaks are put between concepts (never first)", len(brks) >= 2 and cod.L.segments[0].type != "break",
      str([sg.id for sg in cod.L.segments]))
check("a break page shows progress across the day ('N of 4 topics done today')",
      all(any("of 4 topics done today" in (o.text or "") for o in sg.cues[0].ops) for sg in brks)
      and any(s.startswith("Break time") for s in saidd), str([o.text for o in brks[0].cues[0].ops] if brks else ""))
check("at a break she really stops and waits (no next step) until he says continue",
      len(cod.pauses) >= len(brks) >= 2
      and all(p["after"] and p["after"].startswith("brk") and p["cues_at"] == p["cues_held"] for p in cod.pauses),
      str(cod.pauses))
n_cues = len([m for m in cod.sent if m.get("type") == "cue"])
check("…and after 'continue' the lesson goes on to the next concept", cod.pauses and n_cues > cod.pauses[-1]["cues_at"]
      and any(m.get("type") == "cue" and m.get("cue_id", "").startswith("k3") for m in cod.sent), str(n_cues))
check("the day session runs to the end with a recap: 'That's it for today. Today so far: N of 4'",
      rd is not None and rd.get("finished")
      and any(s.startswith("That's it for today.") and "Today so far:" in s and "of 4 topics" in s for s in saidd),
      str(saidd[-3:]))
dnotes = cod.notes_path.read_text() if cod.notes_path else ""
check("his notes have the concepts but no break pages", "## Tokens" in dnotes and "Break" not in dnotes
      and "Stand up" not in dnotes, dnotes[:400])

# same day, later: c0–c2 done earlier today (≥ 3 seen → no probes), c3 still to do
md = Mastery("compilers resume test")
for cid, p in (("c0", 0.9), ("c1", 0.6), ("c2", 0.85)):
    md.set(cid, p)
time.sleep(0.05)
cor, saidr, rr = session("compilers resume test", ["whole syllabus today, I have four hours"] + ["tokens"] * 120)
check("same day again: 'Welcome back. 3 of 4 topics done today already', no probes",
      any(s.startswith("Welcome back. 3 of 4 topics done today already") for s in saidr)
      and not any("quick questions first" in s for s in saidr) and not any("You're solid on" in s for s in saidr),
      str(saidr[:4]))
check("…it skips what's done today: only the rest is taught", [c.id for c in cor.queue] == ["c3"],
      str([c.id for c in cor.queue]))
check("…the plan page shows the day's progress ('Your plan · 3 of 4 done today')",
      any(m.get("type") == "actions" and any("3 of 4 done today" in str(a) for a in m["actions"]) for m in cor.sent),
      "")
check("…and the recap counts the whole day", rr is not None and rr.get("finished")
      and any("Today so far: 4 of 4 topics done." in s for s in saidr), str(saidr[-3:]))
cof, saidf, _ = session("compilers resume test", ["whole syllabus today"] + ["tokens"] * 120)
check("all done today → a quick revision round, said so", any("covered all 4 topics today already" in s for s in saidf)
      and len(cof.queue) == 4, str(saidf[:4]))
check("one topic left: no 'short breaks' promised when there won't be one",
      any(s.startswith("Here's the plan: 1 topic, about 5 minutes, inside your 4 hours") for s in saidr),
      str([s for s in saidr if s.startswith("Here's the plan")]))


def plan_line(goal, n_concepts):
    """The plan she says for a fresh syllabus of n new concepts (no session, no sound)."""
    lg: list[str] = []
    cp = C.Coach(f"plan line test {n_concepts} {goal}", audio=SilentAudio(scale=0.01), events=queue.Queue(),
                 server=FakeSrv(), log=lg.append, call=fake_call, persist=False, planner=None, pace=0.02)
    cp.goal = dict(goal)
    cp.concepts = [C.Concept(id=f"p{i}", name=f"Topic {i}", unit="U", weight=1 + i % 3) for i in range(n_concepts)]
    cp.pool_n = n_concepts
    cp.queue = C.order(cp.concepts, cp.mastery, "day", (goal.get("hours") or C.DAY_DEFAULT_H) * 60 * 0.85)
    cp._show_plan()
    return cp, next((x for x in lg if x.startswith("Stiti: Here's the plan")), "")


cp, line = plan_line({"mode": "day", "days": 0, "hours": 1.0, "hours_said": True}, 20)
check("syllabus too big for his time: she says so ('your 1 hour fits the 8 most important of 20 topics')",
      "your 1 hour fits the 8 most important of 20 topics" in line and "1 hours" not in line, line)
check("…and the most important go first (every weight-3 concept is in)",
      all(c in cp.queue for c in cp.concepts if c.weight == 3), str([c.weight for c in cp.queue]))
cp, line = plan_line({"mode": "day", "days": 0, "hours": 6.0, "hours_said": False}, 12)
check("a whole syllabus with no hours said: real time in hours, breaks, no made-up 'your 6 hours'",
      "12 topics, about 1.5 hours with short breaks" in line and "your" not in line, line)
from stiti.tutor import commands as CMD  # noqa: E402
check("'I'm back' / 'back now' mean continue (a break ends)",
      CMD.classify("I'm back") == "resume" and CMD.classify("back now") == "resume" and CMD.classify("back") == "back")

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


real = (AU.make, C.concept_map, C.Coach.run, SV.BoardServer.start, SV.BoardServer.open_if_no_tab, SV.BoardServer.stop,
        T._coach_target)
T._coach_target = lambda target, args: True         # the coach path, with or without a cloud key in this checkout
AU.make = lambda mode, events, debug=False, scale=1.0: (mark("voice loading", 0.5), _A())[1]
C.concept_map = lambda *a, **k: (mark("reading file", 0.5), [])[1]
C.Coach.run = lambda self: (self._future.result(), mark("session running"),
                            {"finished": True, "checks_right": 0, "checks_graded": 0, "questions": 0})[2]
SV.BoardServer.start = lambda self: (self.connected.set(), mark("board started"), self)[2]
SV.BoardServer.open_if_no_tab = lambda self: (mark("browser opened"), True)[1]   # the board tab goes up here
SV.BoardServer.stop = lambda self: None
try:
    t0 = time.time()
    T._teach(["compilers", "--silent"])
finally:
    (AU.make, C.concept_map, C.Coach.run, SV.BoardServer.start, SV.BoardServer.open_if_no_tab, SV.BoardServer.stop,
     T._coach_target) = real
at = dict(marks)
check("the board is on screen before anything slow starts", at.get("browser opened", 9) < 0.3
      and at["browser opened"] <= min(at.get("voice loading", 9), at.get("reading file", 9)), str(marks))
check("voice loading and reading his file overlap (not one after the other)",
      abs(at.get("voice loading", 0) - at.get("reading file", 9)) < 0.3 and at.get("session running", 9) < 0.9,
      str(marks))

print(f"tutor coach: {passed}/{total} checks passed")
sys.exit(0 if passed == total else 1)
