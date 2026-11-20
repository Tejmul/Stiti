"""The coach (D53): goal first, quick probes, mastery per concept, ≤ 2 sentences then his turn, notes-page board.
No LLM (a fake `call`), no sound (SilentAudio), throwaway STITI_HOME.

STITI_DB=postgresql:///stiti_test STITI_HOME=<tmp> python tests/tutor_coach_eval.py
"""
from __future__ import annotations

import os
os.environ.setdefault("STITI_BOARD_FIXED", "0")     # tests: random ports, no waiting for a board tab
os.environ["STITI_TUTOR_PICTURES"] = "off"          # offline: tests never search Wikimedia (403 on CI, slows lessons)
import queue
import sys
import tempfile
import threading
import time

# run_all.sh shares one STITI_HOME across every eval (CI too): the coach's caches, mastery and "done today" must start
# empty, so this eval works in its own folder inside it (the local models are linked, not copied)
_home = os.environ.get("STITI_HOME") or ""
_own = tempfile.mkdtemp(prefix="coach_eval_", dir=_home if os.path.isdir(_home) else None)
if os.path.isdir(os.path.join(_home, "models")):
    os.symlink(os.path.join(_home, "models"), os.path.join(_own, "models"))
os.environ["STITI_HOME"] = _own

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
        import re as _re
        cname = (_re.search(r"CONCEPT: (.+?) \(unit", user) or [None, "it"])[1]
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
                          # a different question per concept and step (Feature 5: the same one twice is skipped)
                          "check": {"kind": "recall", "prompt": f"In {cname}, step {j + 1}: what does the lexer output?",
                                    "options": None, "expectations": ["tokens"],
                                    "hints": ["Think of words.", "Not characters."], "reveal": "Tokens."}})
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
check("every step: one idea (≤ 3 sentences), then his turn (a check)",
      all(len(s.cues) <= 3 and s.check is not None for s in segs[:2]), str([(len(s.cues), bool(s.check)) for s in segs]))
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
      coach.after_probes.get("c0", 0) >= 0.8, str(coach.after_probes))
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

# ------------------------------------------------------------------ any subject, and a syllabus (tutor_subjects.md)
print("\nany subject: a syllabus file, clean steps, fair grading")
from stiti.config import CFG  # noqa: E402
from stiti.tutor import book as B  # noqa: E402
from stiti.tutor.grade import grade as _grade  # noqa: E402
from stiti.tutor.lesson import Check  # noqa: E402

sdir = CFG.home / "subjects_test"
sdir.mkdir(parents=True, exist_ok=True)
syl = sdir / "os_syllabus.md"
syl.write_text("""CS3401 Operating Systems — Syllabus

UNIT I: Introduction
- Functions of an operating system, system calls
- User mode vs kernel mode

UNIT II: Process Management
- Process states, PCB
- CPU scheduling: FCFS, SJF, Round Robin
- Threads

UNIT III: Memory Management
- Paging and page tables, TLB
- Page replacement (FIFO, LRU, Optimal)

Text books:
1. Silberschatz — Operating System Concepts
""")
sb = B.load(syl)
check("a syllabus is seen as an outline (it only lists topics)", B.is_outline(sb) and len(sb.chapters()) == 3,
      str([s.name for s in sb.sections]))
tops = [B.outline_topics(B.unit_text(sb, s)) for s in sb.chapters()]
check("each unit's own listed topics are found (and the text books are not a topic)",
      tops[1] == ["Process states, PCB", "CPU scheduling: FCFS, SJF, Round Robin", "Threads"]
      and not any("Silberschatz" in t for ts in tops for t in ts), str(tops))
mod = sdir / "micro.txt"
mod.write_text("Microbiology\n\nModule 1 – History\n1. Koch's postulates\n2. Pasteur\n\nModule 2 – Staining\n"
               "1. Gram staining\n2. Acid-fast staining\n\nModule 3 – Growth\n1. Growth curve\n2. Culture media\n")
mb = B.load(mod)
check("'Module 1 – History' headings + numbered topics are units too",
      [s.title for s in mb.chapters()] == ["Module 1 – History", "Module 2 – Staining", "Module 3 – Growth"]
      and B.outline_topics(B.unit_text(mb, mb.chapters()[1])) == ["Gram staining", "Acid-fast staining"],
      str([s.title for s in mb.sections]))
prose = sdir / "notes.md"
para = "The lexer reads characters and groups them into tokens, which the parser then arranges into a tree. " * 12
prose.write_text(f"# Notes\n\n{para}\n\n## More\n\n{para}\n")
wrapped = sdir / "essay.txt"
wrapped.write_text("An essay\n\n" + "\n".join(para[i:i + 70] for i in range(0, len(para), 70)))
check("real notes / hard-wrapped prose are NOT outlines", not B.is_outline(B.load(prose))
      and not B.is_outline(B.load(wrapped)))

PROMPTS: list[tuple[str, str]] = []


def syl_call(system, user, schema, name, max_tokens, **kw):
    PROMPTS.append((name, user))
    if name == "concepts" and "LISTED TOPICS" in user:
        if "unit," in user or "units" in user.split("Return JSON")[-1][:200]:      # flat list → grouped topic call
            return {"concepts": [{"unit": "Centre", "name": "Mean", "points": ["average of all values"], "weight": 2},
                                 {"unit": "Centre", "name": "Median", "points": ["middle value"], "weight": 2},
                                 {"unit": "Spread", "name": "Variance", "points": ["mean squared deviation"],
                                  "weight": 3},
                                 {"unit": "Spread", "name": "Standard deviation", "points": ["root of variance"],
                                  "weight": 3}]}
        return {"concepts": [{"name": ln[2:].split(",")[0][:40], "points": ["a fact", "another fact"], "weight": 2}
                             for ln in user.splitlines() if ln.startswith("- ")]}
    raise AssertionError(name)


mp_s = C.concept_map(str(syl), book_path=str(syl), call=syl_call)
check("syllabus → one call per unit, each with that unit's LISTED TOPICS and general knowledge (no fake sources)",
      len(PROMPTS) == 3 and all("LISTED TOPICS" in u and "SOURCES" not in u for _, u in PROMPTS)
      and any("CPU scheduling: FCFS, SJF, Round Robin" in u and "Threads" in u and "Paging" not in u
              for _, u in PROMPTS), str([u[:80] for _, u in PROMPTS]))
check("…every listed topic becomes a concept, in unit order, marked as taught from general knowledge",
      [c.name for c in mp_s][:3] == ["Functions of an operating system", "User mode vs kernel mode", "Process states"]
      and len(mp_s) == 7 and all(c.general for c in mp_s) and [c.unit_idx for c in mp_s] == [0, 0, 1, 1, 1, 2, 2],
      str([(c.name, c.unit_idx) for c in mp_s]))
n0 = len(PROMPTS)
C.concept_map(str(syl), book_path=str(syl), call=syl_call)
time.sleep(1.1)
syl.write_text(syl.read_text() + "\nUNIT IV: Files\n- File allocation methods\n- RAID levels\n")
mp_s2 = C.concept_map(str(syl), book_path=str(syl), call=syl_call)
check("cached per file — but an edited syllabus is mapped again", len(PROMPTS) == n0 + 4
      and any(c.name == "RAID levels" for c in mp_s2), f"{len(PROMPTS) - n0} calls")
flat = sdir / "stats.md"
flat.write_text("# Statistics revision list\n\n- Mean\n- Median\n- Variance\n- Standard deviation\n")
PROMPTS.clear()
mp_f = C.concept_map(str(flat), book_path=str(flat), call=syl_call)
check("a flat topic list (no unit headings) → ONE call that groups its listed topics into units",
      len(PROMPTS) == 1 and "- Standard deviation" in PROMPTS[0][1] and [c.unit_idx for c in mp_f] == [0, 0, 1, 1]
      and all(c.general for c in mp_f), str(PROMPTS[:1]))


def solo_units(system, user, schema, name, max_tokens, **kw):
    return {"concepts": [{"unit": f"U{i}", "name": f"Idea {i}", "points": ["p"], "weight": 2} for i in range(9)]}


LAZY: list[int] = []


def lazy(system, user, schema, name, max_tokens, **kw):
    LAZY.append(1)
    k = 1 if len(LAZY) == 1 else 8
    return {"concepts": [{"unit": "U" + str(i // 3), "name": f"Step {i}", "points": ["p"], "weight": 2}
                         for i in range(k)]}


lz = C.concept_map("photosynthesis but the model is lazy", call=lazy)
check("a lazy model returns ONE concept for a topic → asked once more, the full map is kept",
      len(LAZY) == 2 and len(lz) == 8, f"{len(LAZY)} calls, {len(lz)} concepts")
rg = C.concept_map("a topic whose model gives one unit per concept", call=solo_units)
check("a model that gives every concept its own unit → regrouped (≈3 per unit)",
      len({c.unit_idx for c in rg}) == 3 and [c.unit_idx for c in rg][:4] == [0, 0, 0, 1], str([c.unit for c in rg]))

STEP_USER: list[str] = []


def step_call(system, user, schema, name, max_tokens, **kw):
    STEP_USER.append(user)
    return {"steps": [
        {"say": ["Imagine a car speeding up. Its speedometer changes every second. That change is a rate. "
                 "We call it a derivative."],
         "points": ["Derivative of u·v equals u'v + uv'"], "figure": None, "example": [],
         "check": {"kind": "recall", "prompt": "What two things does the product rule need?", "options": None,
                   "expectations": ["Mentions u prime v plus u v prime", "The answer should state that order matters",
                                    "extra third point"], "hints": ["h1", "h2"], "reveal": "u'v + uv'"}},
        {"say": ["Let's do one.", "Take x squared times sine x."], "points": [],
         "figure": {"kind": "formula", "text": "d/dx[uv] = u'v + uv'", "nodes": None, "edges": None, "rows": None},
         "example": ["u = x^2, v = sin x", "u' = 2x, v' = cos x", "= 2x sin x + x^2 cos x"],
         "check": {"kind": "apply", "prompt": "Derivative of x^2 sin x?", "options": None,
                   "expectations": ["2x sin x + x^2 cos x"], "hints": [], "reveal": "2x sin x + x^2 cos x"}}],
        "remember": "The product rule: first' times second plus first times second' — always both terms, in order"}


pc = C.Concept(id="pr", name="Product rule", unit="Calculus", points=["Derivative of u·v = u'v + uv'",
                                                                     "Used for products of functions"],
               general=True)
ss = C.concept_segments(pc, 0, "new", "learn", None, 1, call=step_call)
check("the new step form (points / figure / example fields) still lands in the board slots",
      {o.region for s in ss for cu in s.cues for o in cu.ops if o.region} >= {"points", "figure", "example", "remember"},
      str([[o.region for cu in s.cues for o in cu.ops] for s in ss]))
check("step 1 always gets the figure (borrowed from step 2 when the model left it out)",
      any(o.region == "figure" for cu in ss[0].cues for o in cu.ops)
      and not any(o.region == "figure" for cu in ss[1].cues for o in cu.ops), "")
check("a 4-sentence 'say' is cut to one idea: 3 spoken sentences", len(ss[0].cues) == 3
      and ss[0].cues[0].say == "Imagine a car speeding up." and ss[0].cues[1].say.startswith("Its speedometer")
      and ss[0].cues[2].say == "That change is a rate.", str([cu.say for cu in ss[0].cues]))
check("…the figure / example still appear with sentence 2, sentence 3 draws nothing new",
      not ss[0].cues[2].ops, str([[o.region for o in cu.ops] for cu in ss[0].cues]))
check("the worked-example lines ride on each check (the hint ladder's third rung)",
      ss[0].check.example[:1] == ["u = x^2, v = sin x"] and ss[1].check.example[-1] == "= 2x sin x + x^2 cos x",
      str([s.check.example for s in ss[:2]]))
check("rubric expectations become spoken words, at most 2",
      ss[0].check.expectations == ["u prime v plus u v prime", "order matters"], str(ss[0].check.expectations))
pts = [o.text for cu in ss[0].cues for o in cu.ops if o.region == "points"]
check("fallback key points don't repeat one the model already wrote (u·v = … ≈ u·v equals …)",
      len(pts) == 2 and "Used for products of functions" in pts, str(pts))
check("no 'book says' for a topic: the step prompt asks for standard knowledge, not SOURCES",
      C.FACTS_GENERAL in STEP_USER[-1] and C.FACTS_FROM_SOURCES not in STEP_USER[-1], STEP_USER[-1][-200:])
rem = ss[-1].cues[0].ops[0].text
check("long text is clipped at a word, with '…'", rem.endswith("…") and len(rem) <= 90 and " in or" not in rem
      and rem[:-1] == rem[:-1].rstrip(), rem)


def probe_call(system, user, schema, name, max_tokens, **kw):
    return {"probes": [{"concept_id": "u0c0", "question": "What is an OS?", "expected": ["manages hardware"]},
                       {"concept_id": "u0c0", "question": "Again?", "expected": ["x"]},
                       {"concept_id": "u0c1", "question": "Kernel mode?", "expected": [
                           "Identifies privileged access", "full hardware access", "third"]},
                       {"concept_id": "u2c5", "question": "LRU?", "expected": ["least recently used"]}]}


pr = C.make_probes(mp_s, n=3, call=probe_call)
check("probes: one per concept, spread over units first",
      [p["concept_id"] for p in pr] == ["u0c0", "u2c5", "u0c1"], str(pr))
check("…ways of saying ONE answer listed as separate items become one 'A or B' point (rubric words gone)",
      pr[2]["expected"] == ["privileged access or full hardware access or third"], str(pr[2]))
kc = C.concept_segments(pc, 9, "known", "exam", None, 1, call=step_call)[0].check
check("a known concept's quick check doesn't hand him the answer in the question",
      not any(w in kc.prompt for w in ("u'v", "Used for")), kc.prompt)


def gr(q, exps, a):
    return _grade(Check(kind="recall", prompt=q, expectations=exps), a, semantic=False)["verdict"]


check("grading: 'thirty shirts' = 30 shirts; 'ten shirts' is not",
      gr("What is the surplus?", ["30 shirts"], "thirty shirts are left") == "correct"
      and gr("What is the surplus?", ["30 shirts"], "ten shirts are left") != "correct")
check("grading: 'eight point four' = 8.4, and a number at the end of a sentence counts",
      gr("What is the mean?", ["8.4"], "the mean works out to eight point four") == "correct"
      and gr("When did it begin?", ["1914"], "The war started in 1914.") == "correct")
check("grading: a comma list is one answer, not three alternatives",
      gr("Name the Triple Alliance.", ["Germany, Austria-Hungary, Italy"], "Germany, Austria-Hungary and Italy")
      == "correct" and gr("Name the Triple Alliance.", ["Germany, Austria-Hungary, Italy"],
                          "Germany, France and Britain") != "correct")
check("grading: 'A or B' alternatives — either one is right",
      gr("Name one metric.", ["throughput or waiting time"], "the average waiting time") == "correct")
check("grading: repeating the question's words isn't an answer",
      gr("Where do you put the decorator relative to the function?", ["above the function"],
         "you put it after the function") != "correct"
      and gr("Where do you put the decorator relative to the function?", ["above the function"],
             "right above it") == "correct")
check("grading: spoken maths matches written (x squared = x^2, two x = 2x)",
      gr("Derivative of x^2 sin x?", ["2x sin x + x^2 cos x"], "two x sin x plus x squared cos x") == "correct")

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

# ------------------------------------------------------------------ Feature 5: pacing, hint ladder, Blurt, no repeats
print("\nFeature 5: one check per full idea, sparser when he's fed up, Blurt, never the same question twice")
from stiti.tutor import pacing as PC  # noqa: E402
from stiti.tutor import srs as SRS  # noqa: E402

check("questions match after normalising ('Quick one: What does it OUTPUT?' = 'what does it output')",
      PC.norm_q("Quick one: What does the lexer OUTPUT?") == PC.norm_q("what does the lexer output"))
check("rung → rating: unaided good · nudge/hint hard · worked example / answer again · sure + unaided easy",
      [PC.rung_rating("correct", r) for r in range(5)] == ["good", "hard", "hard", "again", "again"]
      and PC.rung_rating("correct", 0, 5) == "easy" and PC.rung_rating("wrong", 0) == "again")
check("…and FSRS uses it (srs.rating_for(…, rung=…))",
      SRS.rating_for("correct", 1, None, rung=3) == SRS.Rating.Again
      and SRS.rating_for("correct", 0, None, rung=0) == SRS.Rating.Good
      and SRS.rating_for("correct", 1, None, rung=2) == SRS.Rating.Hard)
check("right only after help is partial evidence for mastery (worked example → wrong)",
      [PC.mastery_verdict("correct", r) for r in (0, 1, 3)] == ["correct", "partial", "wrong"])
pc_ = PC.Pacing(3)
tipped = [pc_.note(a, v) for a, v in (("tokens", "correct"), ("ok", "wrong"), ("whatever", "wrong"), ("fine", "wrong"))]
check("curt non-answers ('ok', 'whatever', 'fine') make him 'fed up'; an honest short right answer doesn't",
      tipped == [False, False, False, True], str(tipped))
pc_ = PC.Pacing(3)
check("a stressed voice on curt answers tips it sooner (2 curt + tense voice)",
      [pc_.note("ok", "wrong", "stressed"), pc_.note("hmm", "wrong", "stressed")] == [False, True])
pc_ = PC.Pacing(3)
check("'I don't know' is honest, not curt (the ladder helps instead)",
      not any(pc_.note("I don't know", "idk") for _ in range(5)))
check("'skip the questions' / 'just teach' / 'test me' are commands, not doubts",
      [CMD.classify(x) for x in ("skip the questions", "just teach", "stop asking me", "let me blurt", "test me")]
      == ["fewer", "fewer", "fewer", "blurt", "blurt"])
check("'no exam, I just want to learn it' is learn mode, not exam",
      C.parse_goal("no exam now, I just want to learn it")["mode"] == "learn")


def session2(source, answer_for, *, blurt=False, goal=None, voice_at=None, call=None, timeout=120):
    """A whole coached session; answer_for(prompt_on_screen, n) gives his answer to each 'your turn'.
    voice_at = {line_prefix: text}: said once while she is saying a line starting with that prefix."""
    ev: queue.Queue = queue.Queue()
    sv = FakeSrv()
    lg: list[str] = []
    stop = threading.Event()
    fired: set = set()

    def log(x):
        lg.append(x)
        for pre, text in (voice_at or {}).items():
            if pre not in fired and x.startswith("Stiti: " + pre):
                fired.add(pre)
                ev.put({"type": "text", "text": text})

    def feed():
        seen = n = 0
        while not stop.is_set():
            sent = list(sv.sent)
            waits = [m for m in sent if m.get("type") == "status" and m.get("mode") == "waiting"]
            if len(waits) > seen:
                seen = len(waits)
                shown = [m for m in sent if m.get("type") == "check"]
                time.sleep(0.05)
                a = answer_for(shown[-1]["prompt"] if shown else "", n)
                n += 1
                if a is not None:
                    ev.put({"type": "text", "text": a})
            time.sleep(0.02)
    co = C.Coach(source, audio=SilentAudio(scale=0.01), events=ev, server=sv, log=log, call=call or fake_call,
                 persist=False, planner=None, pace=0.02, idle_resume_s=0.2, check_timeout_s=2, blurt=blurt, goal=goal)
    co.sent = sv.sent
    threading.Thread(target=feed, daemon=True).start()
    res = {}
    th = threading.Thread(target=lambda: res.setdefault("r", co.run()), daemon=True)
    th.start()
    th.join(timeout)
    stop.set()
    return co, [x[len("Stiti: "):] for x in lg if x.startswith("Stiti: ")], res.get("r"), lg


def lesson_checks(co):
    """The lesson's own check questions she asked (not the probes / goal / Blurt), in order."""
    probes = {"What does a lexer produce?", "What is a DFA made of?", "Which match does a scanner take?"}
    return [m["prompt"] for m in co.sent if m.get("type") == "check" and m.get("prompt") not in probes
            and not str(m.get("kind_label", "")).startswith(("Question", "Blurt"))]


ans_ok = lambda prompt, n: "I have an exam tomorrow" if n == 0 else "tokens"   # noqa: E731
cop, saidp, rp, lgp = session2("pacing test", ans_ok)
gaps = cop.t.pacing.gaps
avg = sum(gaps) / max(1, len(gaps))
check("a lesson averages ≥ 3 sentences between checks (one check per full idea, not every 2 sentences)",
      rp is not None and rp.get("finished") and len(gaps) >= 3 and avg >= 3, f"gaps {gaps}")
asked = lesson_checks(cop)
check("…and every concept still gets its check", {cop.seg_concept.get(r["segment"]) for r in cop.t.results
                                                    if r.get("verdict")} >= {c.id for c in cop.queue}, str(asked))
check("…the planned 2-sentence steps don't each get a check (some are held for the full idea)",
      any("[pacing] no check yet" in x for x in lgp) and len(asked) < sum(1 for s in cop.L.segments if s.check),
      f"{len(asked)} asked")
normed = [PC.norm_q(p) for p in asked]
check("no question asked twice in a session", len(normed) == len(set(normed)), str(asked))

# curt answers → sparser checks for the rest of the session, said once
curt = lambda prompt, n: "I have an exam tomorrow" if n == 0 else "tokens" if n <= 3 else "ok"   # noqa: E731
coc, saidc, rc, lgc = session2("curt test", curt)
fewer_at = next((i for i, x in enumerate(lgc) if "[pacing] fewer questions from now on" in x), None)
check("curt 'ok' answers → 'Okay, fewer questions.' said once",
      saidc.count("Okay, fewer questions.") == 1 and coc.t.pacing.sparse, str([s for s in saidc if "fewer" in s]))
after = coc.t.pacing.gaps[coc.t.pacing.sparse_at:] if coc.t.pacing.sparse else []
check("…and after it the checks are sparser (≥ 7 sentences apart)",
      fewer_at is not None and all(g >= PC.SPARSE_GAP for g in after), f"gaps {coc.t.pacing.gaps}, "
      f"sparse from #{coc.t.pacing.sparse_at}")
check("…fewer checks than the same lesson with normal answers", len(lesson_checks(coc)) < len(asked),
      f"{len(lesson_checks(coc))} vs {len(asked)}")
# "skip the questions" in a check: the answer, then fewer — said once
sk = lambda prompt, n: "I have an exam tomorrow" if n == 0 else "tokens" if n <= 3 else "skip the questions"  # noqa: E731
cos_, saids, rs, _ = session2("skip questions test", sk)
check("'skip the questions' → the answer, 'Okay, fewer questions.' once, sparse for the rest",
      saids.count("Okay, fewer questions.") == 1 and cos_.t.pacing.sparse and rs and rs.get("finished")
      and any(s.startswith("The answer: Tokens") for s in saids), str([s for s in saids if "ewer" in s or "answer" in s]))
check("…fewer lesson checks than the same lesson with normal answers",
      len(lesson_checks(cos_)) < len(asked), f"{len(lesson_checks(cos_))} vs {len(asked)}")

# Blurt after each topic (the Lessons page flag): per-point marks, mastery, missed points re-taught once
BL_TOPIC = [{"unit": "Lexing", "name": "Tokens", "weight": 3,
             "points": ["A lexer turns characters into tokens", "Whitespace and comments are thrown away"]},
            {"unit": "Lexing", "name": "Regular expressions", "weight": 2,
             "points": ["Regular expressions describe token patterns", "Each regex becomes a finite automaton"]}]


def bl_call(system, user, schema, name, max_tokens, **kw):
    if name == "concepts":
        return {"concepts": BL_TOPIC}
    if name == "probes":
        return {"probes": []}
    if name == "blurt":
        raise RuntimeError("no LLM in this test")
    return fake_call(system, user, schema, name, max_tokens, **kw)


def bl_ans(prompt, n):
    if n == 0:
        return "I have an exam tomorrow"
    if prompt.startswith("Everything you remember about Tokens"):
        return "the lexer turns the characters into tokens"
    if prompt.startswith("Everything you remember about Regular"):
        return "regular expressions describe the token patterns, and each regex becomes a finite automaton"
    return "tokens"


cob, saidb, rb, lgb = session2("blurt test", bl_ans, blurt=True, call=bl_call)
check("--blurt: after each topic 'tell me everything you remember about …'",
      any(s.startswith("Now, without looking: tell me everything you remember about Tokens") for s in saidb)
      and any("remember about Regular expressions" in s for s in saidb), str([s for s in saidb if "remember" in s]))
b1 = cob.blurts[0]["result"]["points"] if cob.blurts else []
check("Blurt is graded per key point: recalled / missed",
      [p["status"] for p in b1] == ["recalled", "missed"], str(b1))
labels = {getattr(e, "label", ""): e for e in cob.t.board.els.values()}
check("the board's Blurt page marks each point ✓ recalled / ✗ missed, with the score",
      "✓ A lexer turns characters into tokens" in labels and "✗ Whitespace and comments are thrown away" in labels
      and any(lb.startswith("Recalled 1 of 2") for lb in labels), str([lb for lb in labels if lb[:1] in "✓✗~R"]))
check("…the missed point is re-taught briefly", "Whitespace and comments are thrown away." in saidb, str(saidb[-12:]))
check("…mastery updated per concept from its points",
      any("[mastery] c0 blurt partial" in x for x in lgb) and any("[mastery] c1 blurt correct" in x for x in lgb),
      str([x for x in lgb if "blurt" in x]))
check("…and his notes keep the Blurt (✓ / ✗ per point)",
      cob.notes_path is not None and "## Blurt · Tokens — 1 of 2 recalled" in cob.notes_path.read_text()
      and "- ✗ Whitespace" in cob.notes_path.read_text(), (cob.notes_path.read_text() if cob.notes_path else "")[-300:])

cod2, saidd2, rd2, lgd2 = session2("blurt day test", lambda p, n: (
    "the lexer turns characters into tokens and regular expressions describe token patterns"
    if p.startswith("Everything") else "tokens"), blurt=True, call=bl_call,
    goal={"mode": "day", "days": 0, "hours": 2.0, "hours_said": True})
check("day mode: one Blurt at the end of the section (unit), over its topics",
      len(cod2.blurts) == 1 and cod2.blurts[0]["topic"] == "Lexing" and len(cod2.blurts[0]["result"]["points"]) == 4
      and [p["status"] for p in cod2.blurts[0]["result"]["points"]] == ["recalled", "missed", "recalled", "missed"],
      str([(b["topic"], [p["status"] for p in b["result"]["points"]]) for b in cod2.blurts]))

# Blurt grading itself: the free-LLM second opinion only when a point is partial
from stiti.tutor import grade as G  # noqa: E402
BP = ["Plants use sunlight to make glucose", "Oxygen is released as a by-product"]
BA = "plants take sunlight and turn it into glucose, and they give off oxygen"
loc = G.blurt_grade(BP, BA, topic="Photosynthesis")
JUDGED: list[str] = []


def judge(system, user, schema, name, max_tokens, **kw):
    JUDGED.append(name)
    return {"points": [{"n": 1, "status": "recalled"}, {"n": 2, "status": "recalled"}], "reason": "gives off = released"}


llm = G.blurt_grade(BP, BA, topic="Photosynthesis", llm=True, call=judge)
check("Blurt local grading: a paraphrase the keywords half-catch is 'partial'",
      [p["status"] for p in loc["points"]] == ["recalled", "partial"], str(loc["points"]))
check("…the free-LLM second opinion settles partial points (one call)",
      JUDGED == ["blurt"] and llm["source"] == "llm" and llm["recalled"] == 2 and llm["score"] == 1.0, str(llm))
JUDGED.clear()
G.blurt_grade(BP, "plants use sunlight to make glucose and oxygen is released as a by-product", topic="Photosynthesis",
              llm=True, call=judge)
none = G.blurt_grade(BP, "I don't know", topic="Photosynthesis", llm=True, call=judge)
check("…and is never asked when nothing is partial (all recalled, or 'I don't know' → all missed)",
      JUDGED == [] and none["missed"] == 2, str(JUDGED))
down = G.blurt_grade(BP, BA, topic="Photosynthesis", llm=True,
                     call=lambda *a, **k: (_ for _ in ()).throw(RuntimeError("429")))
check("…LLM down → the local grades stand", down["source"] == "local" and down.get("llm_error"), str(down))
check("the topic's own name recalls nothing ('photosynthesis is about plants')",
      G.blurt_grade(["Photosynthesis makes glucose"], "photosynthesis is a thing", topic="Photosynthesis",
                    semantic=False)["points"][0]["status"] == "missed")

# "test me" any time → a Blurt on the concept on the board; a missed point is re-taught only once per session
cot, saidt, rt, lgt = session2("blurt voice test", lambda p, n: "I have an exam tomorrow" if n == 0 else (
    "I don't remember" if p.startswith("Everything") else "tokens"), call=bl_call,
    voice_at={"It groups them into tokens": "test me", "So, remember": "let me blurt"})
check("'test me' while she teaches → 'Go on, tell me everything you remember about Tokens.'",
      any(s.startswith("Go on, tell me everything you remember about") for s in saidt)
      and any(s == "Okay, back to where we were." for s in saidt), str([s for s in saidt if "remember" in s][:3]))
check("…graded (all missed), and each missed point re-taught only once even when he blurts again",
      len(cot.blurts) >= 2 and saidt.count("Whitespace and comments are thrown away.") == 1,
      f"{len(cot.blurts)} blurts; {[s for s in saidt if 'Whitespace' in s]}")

# the goal is remembered per file: no "is this for an exam?" every lesson
cog, saidg, _, _ = session2("goal memory test", ans_ok)
cog2, saidg2, _, _ = session2("goal memory test", lambda p, n: "tokens")
check("same file again within days: no goal question, 'Still the exam tomorrow? Carrying on.'",
      not any("what do you need" in s.lower() for s in saidg2)
      and any(s.startswith("Still the exam tomorrow") for s in saidg2)
      and cog2.goal["mode"] == "exam" and cog2.goal["days"] == 1, str(saidg2[:3]))
cog3, saidg3, _, _ = session2("goal memory test", lambda p, n: "no exam now, I just want to learn it" if n == 0
                              else "tokens")
check("…one line corrects it ('no exam now, I just want to learn it' → learn)", cog3.goal["mode"] == "learn",
      str(cog3.goal))
mg = Mastery("goal memory old test")
mg.set_goal({"mode": "exam", "days": 1})
mg.goal["exam_date"] = "2000-01-01"
mg.save()
cog4, saidg4, _, _ = session2("goal memory old test", ans_ok)
check("an exam date that has passed → she asks again", any("what do you need" in s.lower() for s in saidg4),
      str(saidg4[:2]))
cog5, saidg5, _, _ = session2("goal flags test", lambda p, n: "tokens", goal={"mode": "day", "days": 0, "hours": 2.0})
check("a goal from the Lessons page: never asked, and stored for next time",
      not any("what do you need" in s.lower() or s.startswith("Still") for s in saidg5)
      and Mastery("goal flags test").goal.get("mode") == "day", str(saidg5[:2]))

# questions answered right recently are not asked again in the next session
asked_ok = {q for q, r in Mastery("pacing test").asked.items() if r.get("ok")}
cop2, saidp2, _, _ = session2("pacing test", lambda p, n: "tokens")
again = [p for p in lesson_checks(cop2) if PC.norm_q(p) in asked_ok]
check("next session: no question he answered right in the last days is asked again",
      asked_ok and not again, f"{len(asked_ok)} remembered; re-asked {again}")
pz = PC.Pacing(3, store=Mastery("pacing test"))
mz = Mastery("pacing test")
k_old = next(iter(asked_ok))
mz.asked[k_old]["t"] = time.time() - 5 * 86400
check("…but after a few days (or a wrong answer) it may come back",
      not PC.Pacing(3, store=mz).repeat(k_old) and pz.repeat(k_old))

print(f"tutor coach: {passed}/{total} checks passed")
sys.exit(0 if passed == total else 1)
