"""Features 3 + 4: review cards (FSRS) from every concept the coach teaches, a spoken review session of what's due,
and the mastery map (append-only mastery_events → Strong / Focus / Not started, a concept × day heatmap, at risk on
exam day) on the Lessons page API and as a "Map" page on the board.

Offline: a fake LLM `call`, SilentAudio, typed answers, temp STITI_HOME + temp study folder, a stiti_test* database.

STITI_DB=postgresql:///stiti_test STITI_HOME=<tmp> python tests/review_map_eval.py
"""
from __future__ import annotations

import os
os.environ.setdefault("STITI_BOARD_FIXED", "0")     # tests: random ports, no waiting for a board tab
import json
import queue
import re
import sys
import tempfile
import threading
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

db = os.environ.get("STITI_DB", "")
if not db.rstrip("/").split("/")[-1].startswith("stiti_test"):
    sys.exit(f"refusing to run against {db!r}: use a stiti_test* database")
if not os.environ.get("STITI_HOME"):
    sys.exit("set STITI_HOME to a throwaway folder")
os.environ.setdefault("STITI_LIVE_WARM", "0")
os.environ["STITI_TUTOR_PICTURES"] = "off"          # offline: no picture search

from fsrs import Card, Rating, State  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402

import stiti.tutor as T  # noqa: E402
from stiti import router  # noqa: E402
from stiti.config import CFG  # noqa: E402
from stiti.db import one, q  # noqa: E402
from stiti.tutor import coach as C  # noqa: E402
from stiti.tutor import mastery_map as MM  # noqa: E402
from stiti.tutor import review as RV  # noqa: E402
from stiti.tutor import srs  # noqa: E402
from stiti.tutor.audio import SilentAudio  # noqa: E402
from stiti.tutor.mastery import Mastery, key_for  # noqa: E402
from stiti.web import lessons, server  # noqa: E402

if CFG.home.resolve() == (Path.home() / ".stiti").resolve():
    sys.exit("refusing to write into the real ~/.stiti: use a throwaway STITI_HOME")

passed = total = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global passed, total
    total += 1
    passed += bool(cond)
    print(("  ✓ " if cond else "  ✗ ") + name + ("" if cond else f"  — {detail}"))


TOPIC = [{"unit": "Lexing", "name": n, "points": [f"{n} fact one", f"{n} fact two"], "weight": w}
         for n, w in (("Tokens", 3), ("Regular expressions", 2), ("DFA", 3), ("Longest match", 2))]


def fake_call(system, user, schema, name, max_tokens, **kw):
    if name == "concepts":
        return {"concepts": TOPIC}
    if name == "probes":
        return {"probes": [{"concept_id": "c0", "question": "What does a lexer produce?", "expected": ["tokens"]},
                           {"concept_id": "c2", "question": "What is a DFA made of?", "expected": ["states"]},
                           {"concept_id": "c3", "question": "Which match does a scanner take?",
                            "expected": ["longest"]}]}
    if name == "concept":
        cname = re.search(r"CONCEPT: (.+?) \(unit", user).group(1)
        return {"steps": [{"say": ["A lexer reads characters one by one.", "It groups them into tokens."],
                           "board": [{"slot": "point", "kind": "text", "text": "Lexer groups chars into tokens",
                                      "nodes": None, "edges": None, "rows": None}],
                           "check": {"kind": "recall", "prompt": f"What is the key idea of {cname}?",
                                     "options": None, "expectations": ["tokens"],
                                     "hints": ["Think of words.", "Not characters."], "reveal": "Tokens."}}],
                "remember": "Lexer: characters in, tokens out"}
    raise AssertionError(name)


class FakeSrv:
    def __init__(self):
        self.sent = []

    def send(self, m):
        self.sent.append(m)


def drive(make, answers: list[str], wait: float = 120):
    """Run a coach / review session; every 'your turn' (status waiting) gets the next typed answer."""
    ev: queue.Queue = queue.Queue()
    sv = FakeSrv()
    lg: list[str] = []
    stop = threading.Event()

    def feed():
        seen = 0
        while not stop.is_set():                     # his turn: a question asked, or a hint given (same check)
            waits = [m for m in list(sv.sent) if m.get("type") == "status" and (
                m.get("mode") == "waiting" or (m.get("mode") == "playing" and " Hint: " in (m.get("caption") or "")))]
            if len(waits) > seen and answers:
                seen = len(waits)
                time.sleep(0.05)
                ev.put({"type": "text", "text": answers.pop(0)})
            time.sleep(0.02)
    obj = make(ev, sv, lg)
    threading.Thread(target=feed, daemon=True).start()
    res: dict = {}
    th = threading.Thread(target=lambda: res.setdefault("r", obj.run()), daemon=True)
    th.start()
    th.join(wait)
    stop.set()
    return obj, sv, [x[len("Stiti: "):] for x in lg if x.startswith("Stiti: ")], lg, res.get("r")


KW = dict(pace=0.02, idle_resume_s=0.2, check_timeout_s=2)
now = datetime.now(timezone.utc)

# ------------------------------------------------------------------ 1. a lesson's checks → cards + mastery events
print("a coached lesson leaves one review card per concept, and every mastery change in mastery_events")
RUN = format(time.time_ns() % 10**9, "x")             # a STITI_HOME may be shared by several evals / runs
SRC = f"compilers for review {RUN}"
KEY = key_for(SRC)
co, sv, said, logs, res = drive(lambda ev, sv, lg: C.Coach(
    SRC, audio=SilentAudio(scale=0.01), events=ev, server=sv, log=lg.append, call=fake_call, persist=False,
    cards=True, planner=None, goal={"mode": "exam", "days": 3}, **KW),
    ["tokens", "I don't know", "the shortest one", "no idea", "no idea", "no idea"] + ["tokens"] * 60)
check("the session ran to the end", res is not None and res.get("finished"), str(res)[:200])
cards = q("SELECT * FROM study_cards WHERE source_key=%s ORDER BY id", (KEY,))
check("one card per concept he answered a check on (no duplicates)",
      len(cards) == len(co.checked) >= 3 and {c["concept_id"] for c in cards} == co.checked
      and len({c["concept_id"] for c in cards}) == len(cards), f"{len(cards)} cards, checked {co.checked}")
byc = {c["concept_id"]: c for c in cards}
c2 = byc.get("c2", {})
check("card front = the concept's check question, back = its expected points, linked to source + concept",
      c2.get("front") == "What is the key idea of DFA?" and c2.get("back") == "tokens" and c2.get("concept") == "DFA"
      and c2.get("source") == SRC and c2.get("kind") == "concept", str({k: c2.get(k) for k in ("front", "back", "concept")}))
spec = c2.get("check_spec") or {}
check("…the whole check is kept (hints, reveal) so a review asks it the same way",
      spec.get("hints") == ["Think of words.", "Not characters."] and spec.get("reveal") == "Tokens.", str(spec))
check("every card was rated by its check: FSRS state saved, due in the future",
      all(c["reps"] >= 1 and c["fsrs"] and c["due"] > now for c in cards), str([(c["reps"], c["due"]) for c in cards]))
check("the check he missed even after both hints counted as a lapse (Again)",
      sum(c["lapses"] for c in cards) >= 1, str([(c["concept_id"], c["lapses"]) for c in cards]))
evs = q("SELECT concept_id, verdict, origin, p_before, p_after, hints FROM mastery_events WHERE source_key=%s ORDER BY id",
        (KEY,))
origins = [e["origin"] for e in evs]
check("mastery_events: the 3 probes (origin probe) then every check (origin check), append-only",
      origins[:3] == ["probe"] * 3 and origins.count("check") >= len(co.checked) and set(origins) <= {"probe", "check"},
      str(origins))
check("…each with verdict, p before → after; the JSON summary still holds the latest value",
      all(e["p_after"] is not None for e in evs)
      and abs(evs[-1]["p_after"] - co.mastery.p[evs[-1]["concept_id"]]) < 1e-3
      and json.loads(co.mastery.path.read_text())["p"] == co.mastery.p, str(evs[-1]))
check("…a hint used is recorded on the event", any(e["hints"] >= 1 for e in evs if e["origin"] == "check"),
      str([(e["verdict"], e["hints"]) for e in evs]))
check("exam in 3 days → the exam date is remembered with his mastery (for 'at risk on exam day')",
      json.loads(co.mastery.path.read_text()).get("exam") == (date.today() + timedelta(days=3)).isoformat())

# the board's Map page at the start
acts = [a for m in sv.sent if m.get("type") == "actions" for a in m["actions"]]
blob = [json.dumps(a) for a in acts]
i_map = next((i for i, b in enumerate(blob) if '"Map"' in b), None)
i_plan = next((i for i, b in enumerate(blob) if "Your plan" in b), None)
check("a 'Map' notes page is drawn on the board before 'Your plan'", i_map is not None and i_plan is not None
      and i_map < i_plan, f"map {i_map} plan {i_plan}")
check("…with Strong / Focus / Not started lines and she says the map in one line",
      any("Strong (" in b for b in blob) and any("Not started (" in b for b in blob)
      and any(s.startswith("Your map:") and "to focus on" in s for s in said), str([s for s in said if "map" in s.lower()]))
ops = MM.board_ops(co.concepts, co.mastery, due=2)
check("Map page ops: new_page + 3 points + a counts table (figure) + a remember line (≤ slot sizes)",
      [o.type for o in ops][:1] == ["new_page"] and sum(o.region == "points" for o in ops) == 3
      and any(o.type == "table" and o.region == "figure" for o in ops)
      and any(o.region == "remember" and "2 due for review" in (o.text or "") for o in ops)
      and all(len(o.text or "") <= 80 for o in ops), str([(o.type, o.region, o.text) for o in ops]))

# no cards when the lesson isn't saved (cards default to persist)
co_off = C.Coach("no cards source", audio=SilentAudio(scale=0.01), events=queue.Queue(), server=None, log=lambda *a: None,
                 call=fake_call, persist=False, planner=None)
check("persist=False and no cards flag → no card is written", co_off.cards is False)

# ------------------------------------------------------------------ 2. FSRS rating map + due dates
print("\nFSRS: rating from the verdict + hints; due dates follow FSRS")
check("right → Good · right after a hint → Hard · partly → Hard · wrong / don't know → Again · sure + right → Easy",
      (srs.rating_for("correct"), srs.rating_for("correct", 1), srs.rating_for("partial"), srs.rating_for("wrong"),
       srs.rating_for("idk"), srs.rating_for("correct", 0, 5)) ==
      (Rating.Good, Rating.Hard, Rating.Hard, Rating.Again, Rating.Again, Rating.Easy))
k2 = key_for("fsrs test")
cid_a = srs.concept_card("fsrs test", k2, "a", "Alpha", {"prompt": "What is alpha?", "expectations": ["first"]})
cid_b = srs.concept_card("fsrs test", k2, "b", "Beta", {"prompt": "What is beta?", "expectations": ["second"]})
cid_a2 = srs.concept_card("fsrs test", k2, "a", "Alpha", {"prompt": "Alpha, again?", "expectations": ["first"]})
row_a = one("SELECT front, reps FROM study_cards WHERE id=%s", (cid_a,))
check("taught again → the same card is updated (front), not duplicated", cid_a2 == cid_a and row_a["front"] == "Alpha, again?"
      and one("SELECT count(*) n FROM study_cards WHERE source_key=%s", (k2,))["n"] == 2, str(row_a))
t0 = datetime.now(timezone.utc)
da = srs.review(cid_a, Rating.Again, t0)
db_ = srs.review(cid_b, Rating.Good, t0)
check("new card: Again → back in 10 minutes, Good → in an hour (learning steps)",
      abs((da - t0).total_seconds() - 600) < 5 and abs((db_ - t0).total_seconds() - 3600) < 5, f"{da - t0} {db_ - t0}")
db2 = srs.review(cid_b, Rating.Good, t0 + timedelta(hours=1))
check("…Good again → graduates to days", (db2 - t0) >= timedelta(days=1), str(db2 - t0))
check("…a lapse is counted on Again", one("SELECT lapses FROM study_cards WHERE id=%s", (cid_a,))["lapses"] == 1)

# ------------------------------------------------------------------ 3. due selection
print("\nwhat's due")
q("UPDATE study_cards SET due = now() - interval '2 hours' WHERE source_key=%s", (KEY,))
q("UPDATE study_cards SET due = now() - interval '1 hour' WHERE id=%s", (cid_a,))
q("UPDATE study_cards SET due = now() + interval '3 days' WHERE id=%s", (cid_b,))
book_src = "/tmp/Some Book.pdf#Unit 2"
kb = key_for(book_src)
cid_u = srs.concept_card(book_src, kb, "u0", "Unit two idea", {"prompt": "Unit two?", "expectations": ["two"]})
d_all = srs.due_concepts()
ids = [r["id"] for r in d_all]
check("due cards now: the past-due ones, never the one due in 3 days", cid_b not in ids and cid_a in ids
      and byc["c2"]["id"] in ids and cid_u in ids, str(ids))
check("weakest first (most lapses first)", d_all[0]["lapses"] == max(r["lapses"] for r in d_all), str([r["lapses"] for r in d_all]))
check("per source key", {r["id"] for r in srs.due_concepts(KEY)} == {c["id"] for c in cards},
      str([r["concept_id"] for r in srs.due_concepts(KEY)]))
check("per file: '--review book.pdf' finds the cards of any of its units", [r["id"] for r in srs.due_concepts(source="/tmp/Some Book.pdf")]
      == [cid_u], str(srs.due_concepts(source="/tmp/Some Book.pdf")))
dc = srs.due_counts()
check("due counts per source key + total (what the Lessons page shows)", dc["total"] == len(d_all)
      and dc["by_key"].get(KEY) == len(srs.due_concepts(KEY)) and dc["by_key"].get(k2) == 1, str(dc))
check("a limit keeps the session short", len(srs.due_concepts(limit=2)) == 2)

# ------------------------------------------------------------------ 4. the review session, end to end (typed)
print("\nthe review session: one question each, hint → reveal, graded locally, FSRS + mastery updated")
due_now = [r for r in srs.due_concepts(KEY) if r["back"] == "tokens"]      # the taught ones (not quick checks)
check("review cards for this file are due", len(due_now) >= 3, str(len(due_now)))
due_now = due_now[:3]
before = {r["id"]: one("SELECT reps, lapses, due FROM study_cards WHERE id=%s", (r["id"],)) for r in due_now}
answers = ["tokens", "no idea", "still no idea", "no idea", "tokens"]
rv, sv2, said2, logs2, res2 = drive(lambda ev, sv, lg: RV.Review(
    due_now, audio=SilentAudio(scale=0.01), events=ev, server=sv, log=lg.append, persist=False, **KW), answers)
check("the review ran to the end", res2 is not None and res2.get("finished"), str(res2)[:200])
verd = [d["verdict"] for d in rv.done]
check("one question per due card, graded: right / wrong after a hint / (third card)",
      len(rv.done) == len(due_now) and verd[0] == "correct" and verd[1] == "wrong", str(rv.done))
check("a miss gets one hint, then the answer is revealed", sum(" Hint: " in s for s in said2) == 2
      and any(s.startswith("Here's the answer.") and "Tokens." in s for s in said2), str(said2))
if len(rv.done) >= 3:
    check("right after a hint → Hard; right → Good; wrong → Again",
          [d["rating"] for d in rv.done] == ["Good", "Again", "Hard"] and rv.done[2]["hints"] == 1,
          str([(d["verdict"], d["hints"], d["rating"]) for d in rv.done]))
after = {r["id"]: one("SELECT reps, lapses, due FROM study_cards WHERE id=%s", (r["id"],)) for r in due_now}
check("every reviewed card: one more rep, a new due date in the future (FSRS)",
      all(after[i]["reps"] == before[i]["reps"] + 1 and after[i]["due"] > datetime.now(timezone.utc) for i in after),
      str(after))
check("…the missed one gained a lapse", after[due_now[1]["id"]]["lapses"] == before[due_now[1]["id"]]["lapses"] + 1)
rev_ev = q("SELECT concept_id, verdict, hints, origin FROM mastery_events WHERE source_key=%s AND origin='review' ORDER BY id",
           (KEY,))
check("mastery updated by every answer (mastery_events origin 'review', with hints)",
      [e["concept_id"] for e in rev_ev] == [r["concept_id"] for r in due_now]
      and [e["verdict"] for e in rev_ev] == verd, str(rev_ev))
m_now = Mastery(SRC)
check("…and the readable JSON moved too", all(abs(m_now.get(d_["concept_id"]) - rv.done[i]["p"]) < 1e-3
                                              for i, d_ in enumerate(due_now)), str(m_now.p))
check("the board gets a page per card titled by its concept, then 'Review done'",
      any('"Review done"' in json.dumps(m) for m in sv2.sent)
      and any(json.dumps(due_now[0]["concept"]) in json.dumps(m) for m in sv2.sent))
check("she sums it up: 'Done. N of M right.'", any(s.startswith(f"Done. {verd.count('correct')} of {len(verd)} right.")
                                                for s in said2), str(said2[-2:]))
check("nothing from this file is due right after the review", not srs.due_concepts(KEY)
      or all(r["id"] not in after for r in srs.due_concepts(KEY)), str(srs.due_concepts(KEY)))

# card_check: an old card without a spec still works; MCQ cards keep their options
cc = RV.card_check({"id": 1, "front": "What is X?", "back": "the x", "concept": "X", "check_spec": None})
check("a card without a stored check → recall on its back, one generic hint", cc.kind == "recall"
      and cc.expectations == ["the x"] and len(cc.hints) == 1 and cc.reveal == "the x")
mc = RV.card_check({"id": 2, "front": "Pick", "back": "b", "concept": "Y", "check_spec": {
    "kind": "mcq", "options": [{"text": "a", "correct": False}, {"text": "b", "correct": True}], "expectations": [],
    "hints": ["h1", "h2"], "reveal": "b"}})
check("an MCQ card is asked as MCQ, with at most one hint", mc.kind == "mcq" and len(mc.options) == 2 and mc.hints == ["h1"])

# ------------------------------------------------------------------ 5. the CLI and the voice
print("\n`stiti teach --review` and 'review' / 'what's due' by voice")
from stiti.tutor import audio as AU  # noqa: E402

made: list[str] = []
ran: list[list[int]] = []


class _A:
    def close(self):
        pass


real = (AU.make, RV.Review.run)
AU.make = lambda mode, events, debug=False, scale=1.0: (made.append(mode), _A())[1]
RV.Review.run = lambda self: (ran.append([c["id"] for c in self.cards]),
                              {"finished": True, "checks_right": 0, "checks_graded": 0})[1]
try:
    r_none = T._teach(["--review", "--key", "0" * 16, "--silent", "--no-board"])
    n_made = len(made)
    T._teach(["--review", "--key", kb, "--silent", "--no-board"])
    T._teach(["--review", "/tmp/Some Book.pdf", "--silent", "--no-board"])
    T._teach(["--review", "--limit", "1", "--silent", "--no-board"])
finally:
    AU.make, RV.Review.run = real
check("nothing due → says so, no voice loaded, no board", r_none.get("finished") and n_made == 0, str(r_none))
check("--key → only that source's due cards; a file path → that file's; --limit caps it",
      len(ran) == 3 and ran[0] == [cid_u] and ran[1] == [cid_u] and len(ran[2]) == 1, str(ran))
check("'--key' / '--limit' values are never mistaken for the target", "--key" in T.VALUE_FLAGS and "--limit" in T.VALUE_FLAGS)
vr = T.voice_request
yes = ["review", "let's review", "Stiti, start my review", "review time", "what's due", "what is due for review",
       "time for my review", "do a review now", "can we review?"]
no = ["review my PR", "start the review of my code", "what's due today", "add review notes to my to-do list",
      "remind me to review the slides at 5"]
check("review phrases → a review session", all(vr(s) == (None, False, "review") for s in yes),
      str({s: vr(s) for s in yes if vr(s) != (None, False, "review")}))
check("…but code review, to-dos and 'what's due today' are not", all(vr(s) is None or vr(s)[-1] != "review" for s in no),
      str({s: vr(s) for s in no}))
check("'revise karna hai' is still the crash-course revision", vr("revise karna hai") == (None, False, "revise"))
spawned: list[list[str]] = []
real_spawn, real_active = T._spawn, T.tutor_active
T._spawn = lambda args: spawned.append(list(args))
T.tutor_active = lambda: False
try:
    n_due = srs.due_counts()["total"]
    msg = T.launch(None, False, "review")
    first_spawn = list(spawned)
    q("UPDATE study_cards SET due = now() + interval '9 days'")
    msg0 = T.launch(None, False, "review")
finally:
    T._spawn, T.tutor_active = real_spawn, real_active
check("voice launch: N due → 'Review time: N cards due' and `teach --review` spawns",
      first_spawn == [["--review"]] and f"{n_due} card" in msg, f"{msg} {first_spawn}")
check("…nothing due → she says so and nothing opens", "Nothing's due" in msg0 and len(spawned) == 1, msg0)

# ------------------------------------------------------------------ 6. map: grouping, heatmap, at risk
print("\nthe map: Strong / Focus / Not started, heatmap, at risk on exam day")
MSRC = f"map test topic {RUN}"
MK = key_for(MSRC)
home = CFG.home
names = ["Tokens", "Regular expressions", "DFA", "Longest match", "Lexer → Parser", "Symbol table"]
weights = [2, 2, 3, 2, 1, 3]
(home / "tutor" / "concepts").mkdir(parents=True, exist_ok=True)
(home / "tutor" / "concepts" / f"{MK}.json").write_text(json.dumps(
    [{"id": f"c{i}", "name": n, "unit": "Lexing", "points": [], "weight": w, "unit_idx": 0}
     for i, (n, w) in enumerate(zip(names, weights))]))
mm = Mastery(MSRC)
mm.set("c0", 0.9, verdict="correct", origin="check")
mm.set("c1", 0.6, verdict="partial", origin="check")
mm.set("c2", 0.2, verdict="wrong", origin="probe")
mm.set("c3", 0.85, verdict="correct", origin="check")       # strong once…
mm.set("c3", 0.3, verdict="wrong", origin="review")         # …then dropped
d = MM.load(MK)
g = MM.groups(d["concepts"], d["p"], d["seen"], MM._ever_strong(MK))
gid = {k: [c["id"] for c in v] for k, v in g.items()}
check("Strong ≥ 0.8 · Focus = seen below 0.8 · Not started = never answered",
      gid == {"strong": ["c0"], "focus": ["c1", "c2", "c3"], "not_started": ["c4", "c5"]}, str(gid))
lv = {c["id"]: (c["level"], c["dropped"]) for v in g.values() for c in v}
check("levels for the chip colours (strong / shaky / weak / new); strong-then-dropped is flagged",
      lv == {"c0": ("strong", False), "c1": ("shaky", False), "c2": ("weak", False), "c3": ("weak", True),
             "c4": ("new", False), "c5": ("new", False)}, str(lv))
check("the map matches mastery: every concept in exactly one group",
      sorted(sum(gid.values(), [])) == sorted(f"c{i}" for i in range(6)))

# heatmap: answers per concept per day
q("INSERT INTO mastery_events(source_key, concept_id, verdict, p_before, p_after, origin, at) VALUES "
  "(%s,'c1','wrong',0.25,0.3,'check', now() - interval '3 days'),"
  "(%s,'c1','correct',0.3,0.5,'review', now() - interval '3 days'),"
  "(%s,'c5','correct',0.25,0.6,'check', now() - interval '40 days'),"
  "(%s,'c4','inferred',0.25,0.6,'probe', now())", (MK, MK, MK, MK))
hm = MM.heatmap(MK, d["concepts"])
rows = {r["id"]: r["cells"] for r in hm["rows"]}
today = datetime.now().astimezone().date()
check("30 days, oldest first, ending today (his local days)", len(hm["days"]) == 30
      and hm["days"][-1] == today.isoformat() and hm["days"][0] == (today - timedelta(days=29)).isoformat(), str(hm["days"][-2:]))
check("today's answers counted per concept, cell = [answers, p at the end of the day]",
      rows.get("c3", [None])[-1] == [2, 0.3] and rows.get("c0", [None])[-1] == [1, 0.9], str({k: v[-1] for k, v in rows.items()}))
check("3 days ago: 2 answers on c1 (the day's last p)", rows.get("c1", [None] * 30)[-4] == [2, 0.5], str(rows.get("c1")))
check("older than 30 days and 'inferred' bumps don't count; concepts without answers have no row",
      "c5" not in rows and "c4" not in rows and list(rows) == ["c0", "c1", "c2", "c3"], str(list(rows)))

# at risk on exam day: (1 − recall at the exam) × weight
exam = today + timedelta(days=5)
t_now = datetime.now(timezone.utc)
for cid, stab in (("c0", 400.0), ("c1", 1.0)):
    card_id = srs.concept_card(MSRC, MK, cid, names[int(cid[1])], {"prompt": f"Q {cid}", "expectations": ["x"]})
    cd = Card(card_id=card_id, state=State.Review, stability=stab, difficulty=5.0, last_review=t_now,
              due=t_now + timedelta(days=max(1, int(stab))))
    q("UPDATE study_cards SET fsrs=%s, due=%s WHERE id=%s", (json.dumps(cd.to_dict()), cd.due, card_id))
risk = MM.at_risk(MK, d["concepts"], d["p"], d["seen"], exam)
rid = [r["id"] for r in risk]
check("a card he'll still remember on exam day (recall ≥ 0.9) is not at risk", "c0" not in rid, str(risk))
check("riskiest first: never-started weight 3, then a weak weight-3 one, …, a fading card last",
      rid[:2] == ["c5", "c2"] and rid[-1] == "c1" and all(risk[i]["risk"] >= risk[i + 1]["risk"] for i in range(len(risk) - 1)),
      str([(r["id"], r["recall"], r["weight"], r["risk"]) for r in risk]))
c1r = next((r for r in risk if r["id"] == "c1"), {})
check("…recall comes from FSRS for a concept with a card", c1r.get("card") is True and 0.3 < c1r.get("recall", 0) < 0.9,
      str(c1r))
full = MM.build(MK, exam)
check("build(): groups + counts + heatmap + at risk + days to the exam", full["counts"] == {"strong": 1, "focus": 3,
      "not_started": 2} and full["exam_days"] == 5 and full["at_risk"] and full["heatmap"]["rows"], str(full["counts"]))
check("no exam date known → no at-risk list", MM.build(MK)["at_risk"] == [] and MM.build(MK)["exam"] is None)
check("an exam date in the past → no at-risk list", MM.build(MK, today - timedelta(days=1))["at_risk"] == [])
check("unknown key → None", MM.build("f" * 16) is None)

# ------------------------------------------------------------------ 7. API + validation
print("\nthe Lessons page API: review counts, Start review, the map, focus start")
books = Path(tempfile.mkdtemp(prefix="stiti-books-"))
big = books / "Compiler Notebook.pdf"
big.write_bytes(b"%PDF" + b"x" * 80_000)
T.BOOK_DIRS = (str(books),)
FK = key_for(str(big))
(home / "tutor" / "concepts" / f"{FK}.json").write_text(json.dumps(
    [{"id": f"c{i}", "name": n, "unit": "Lexing", "points": [], "weight": 2, "unit_idx": 0}
     for i, n in enumerate(["Tokens", "Lexer → Parser", "DFA"])]))
fm = Mastery(str(big))
fm.exam = (today + timedelta(days=4)).isoformat()
fm.set("c0", 0.9, verdict="correct", origin="check")
fm.set("c1", 0.5, verdict="partial", origin="check")
fc = srs.concept_card(str(big), FK, "c1", "Lexer → Parser", {"prompt": "Lexer to parser?", "expectations": ["tokens"]})
q("UPDATE study_cards SET due = now() - interval '1 minute' WHERE id=%s", (fc,))

spawned = []
state = {"active": False}
T._spawn = lambda args: spawned.append(list(args))
T.tutor_active = lambda: state["active"]
keys = {"on": True}
router.status = lambda: [{"name": "fake", "key": keys["on"]}]
base = f"http://127.0.0.1:{server.PORT}"
host = {"host": f"127.0.0.1:{server.PORT}"}
auth = {"x-stiti-token": server.web_token(), **host}
write = {**auth, "origin": base}
cl = TestClient(server.app(), base_url=base)

o = cl.get("/api/lessons", headers=auth).json()
prow = {p["key"]: p for p in o.get("progress", [])}
check("overview: review.total = cards due now; each progress row has its own 'due'",
      o.get("review", {}).get("total") == srs.due_counts()["total"] == 1 and prow.get(FK, {}).get("due") == 1
      and prow.get(MK, {}).get("due") == 0, str(o.get("review")) + str({k: v.get("due") for k, v in prow.items()}))

r = cl.get("/api/lessons/map", params={"key": FK}, headers=auth)
mj = r.json() if r.status_code == 200 else {}
check("GET /api/lessons/map?key=… → groups, heatmap, at risk (stored exam date), due, label, start target",
      r.status_code == 200 and mj.get("counts") == {"strong": 1, "focus": 1, "not_started": 1}
      and mj.get("exam") == fm.exam and mj.get("exam_days") == 4 and isinstance(mj.get("at_risk"), list)
      and mj.get("due") == 1 and mj.get("label") == "Compiler Notebook.pdf" and mj.get("kind") == "file"
      and mj.get("target") == str(big) and len(mj.get("heatmap", {}).get("days", [])) == 30, r.text[:300])
check("…the raw source path isn't echoed as 'source'", "source" not in mj)
foc = {c["id"]: c["focus"] for v in mj.get("groups", {}).values() for c in v}
check("each concept carries a safe focus name ('Lexer → Parser' → 'Lexer Parser')", foc.get("c1") == "Lexer Parser"
      and foc.get("c0") == "Tokens", str(foc))
r2 = cl.get("/api/lessons/map", params={"key": FK, "exam": (today + timedelta(days=10)).isoformat()}, headers=auth)
check("?exam=YYYY-MM-DD overrides the stored date", r2.status_code == 200 and r2.json().get("exam_days") == 10, r2.text[:200])
check("needs the token", cl.get("/api/lessons/map", params={"key": FK}, headers=host).status_code == 403)
badmap = {"no key": {}, "short": {"key": "abc"}, "upper": {"key": FK.upper()}, "traversal": {"key": "../../web_token"},
          "17 hex": {"key": FK + "a"}, "bad exam": {"key": FK, "exam": "tomorrow"},
          "bad exam date": {"key": FK, "exam": "2026-13-40"}}
codes = {k: cl.get("/api/lessons/map", params=v, headers=auth).status_code for k, v in badmap.items()}
check("malformed key / exam → 400", all(c == 400 for c in codes.values()), str(codes))
check("unknown key → 404", cl.get("/api/lessons/map", params={"key": "0" * 16}, headers=auth).status_code == 404)
tm = cl.get("/api/lessons/map", params={"key": MK}, headers=auth).json()
check("a topic's map: kind topic, the topic is the start target", tm.get("kind") == "topic" and tm.get("target") == MSRC,
      str({k: tm.get(k) for k in ("kind", "target", "label")}))


def start(body, headers=write):
    spawned.clear()
    return cl.post("/api/lessons/start", content=json.dumps(body), headers={**headers, "content-type": "application/json"})


r = start({"mode": "review"})
check("Start review (all files) → `teach --review`", r.status_code == 200 and r.json().get("ok")
      and spawned == [["--review"]] and r.json().get("due") == 1, f"{r.status_code} {r.text[:120]} {spawned}")
r = start({"mode": "review", "key": FK, "ptt": True})
check("Start review for one file → `--review --key K --ptt`", r.status_code == 200 and spawned == [["--review", "--key", FK, "--ptt"]],
      str(spawned))
keys["on"] = False
r = start({"mode": "review", "key": FK})
check("a review needs no cloud key (graded locally)", r.status_code == 200 and spawned == [["--review", "--key", FK]], r.text)
keys["on"] = True
r = start({"mode": "review", "key": MK})
check("nothing due for that file → 409 'Nothing is due', nothing opens", r.status_code == 409 and not spawned
      and "Nothing is due" in r.json().get("error", ""), r.text)
r = start({"mode": "review"}, headers=auth)
check("needs same-origin as well as the token", r.status_code == 403 and not spawned)
bad = {"key not hex": {"mode": "review", "key": "zzzzzzzzzzzzzzzz"}, "key too short": {"mode": "review", "key": "abc"},
       "key a path": {"mode": "review", "key": "../../etc/passwd"}, "key not a string": {"mode": "review", "key": 7},
       "with a target": {"mode": "review", "target": str(big)}, "with hours": {"mode": "review", "hours": 2},
       "with focus": {"mode": "review", "focus": "DFA"}, "ptt not bool": {"mode": "review", "ptt": "yes"},
       "key flag": {"mode": "review", "key": "--resume"}}
res_bad = {k: start(v) for k, v in bad.items()}
check("bad review requests → 400 with a message, nothing spawned",
      all(x.status_code == 400 and x.json().get("error") for x in res_bad.values()) and not spawned,
      str({k: x.status_code for k, x in res_bad.items()}))
state["active"] = True
r = start({"mode": "review"})
check("a lesson already running → 409, no review on top", r.status_code == 409 and not spawned and r.json().get("active"))
state["active"] = False

# clicking a concept on the map → a lesson with --focus "<concept>"
r = start({"target": mj["target"], "mode": "learn", "focus": foc["c1"]})
check("map → concept click → `teach <file> --goal-mode learn --focus \"Lexer Parser\"`",
      r.status_code == 200 and spawned == [[str(big), "--goal-mode", "learn", "--focus", "Lexer Parser"]], f"{r.text[:100]} {spawned}")
r = start({"target": tm["target"], "mode": "learn", "focus": "Symbol table"})
check("…a topic's concept too", spawned == [[MSRC, "--goal-mode", "learn", "--focus", "Symbol table"]], str(spawned))
check("…and the coach gets exactly that focus", C.focus_split(spawned[0][-1]) == ["Symbol table"]
      and C.matches("Symbol table", C.Concept(id="c5", name="Symbol table", unit="Lexing")))
check("focus_name() output always passes the start validation", all(
    lessons.build_args({"target": MSRC, "focus": lessons.focus_name(n)})[0][-1] == lessons.focus_name(n)
    for n in names + ["C++ / Java: types", "Σ alphabets & ε-moves"] if lessons.focus_name(n)))

import shutil  # noqa: E402

shutil.rmtree(books, ignore_errors=True)
print(f"\nreview + map: {passed}/{total} checks passed")
sys.exit(0 if passed == total else 1)
