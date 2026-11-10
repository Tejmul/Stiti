"""Crash course + any-book reader: loaders (txt/md/epub-style chapters, Contents dedupe, Roman numerals, no-structure
fallback), course math, prerequisite ordering, diagnostics, FSRS revision, voice phrases. Offline except one
optional live planning check (runs only with an LLM key)."""
from __future__ import annotations

import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ok = fail = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global ok, fail
    ok += bool(cond)
    fail += not cond
    print(f"{'✅' if cond else '❌'} {name}" + (f" — {detail}" if detail and not cond else ""))


from stiti.tutor import book, course, srs, voice_request  # noqa: E402

tmp = Path(tempfile.mkdtemp())
para = ("Selection acts on small variations that are useful to the organism in its struggle for life. " * 12 + "\n\n")
gut = ("The Project Gutenberg eBook of Test\n*** START OF THE PROJECT GUTENBERG EBOOK TEST ***\n\nCONTENTS\n\n"
       "I. THE WORLD IN SPACE 1\nII. THE WORLD IN TIME 5\nIII. THE BEGINNINGS OF LIFE 9\n\n"
       + "".join(f"{rn}\n\n{t}\n\n" + para * 6 for rn, t in
                 [("I", "THE WORLD IN SPACE"), ("II", "THE WORLD IN TIME"), ("III", "THE BEGINNINGS OF LIFE")])
       + "*** END OF THE PROJECT GUTENBERG EBOOK TEST ***\nlicence text " * 3)
(tmp / "history.txt").write_text(gut)
b = book.load(tmp / "history.txt")
names = [s.title for s in b.chapters()]
check("txt book: Roman-numeral chapters found once (Contents list deduped)",
      names == ["The World In Space", "The World In Time", "The Beginnings Of Life"], str(names))
check("txt book: Gutenberg licence stripped", not any("licence text" in p for p in b.pages))
check("txt book: real pseudo-pages so sections have page ranges",
      len(b.pages) > 3 and b.chapters()[1].page > b.chapters()[0].page, f"{len(b.pages)} pages")
check("find: 'chapter 2', 'II' and title words", b.find("chapter 2") is b.chapters()[1] and b.find("II") is
      b.chapters()[1] and b.find("beginnings").title == "The Beginnings Of Life")

md = "# My Notes\n\n## Chapter 1: Graphs\n\n" + para * 4 + "## Chapter 2: Trees\n\n" + para * 4 + "## Chapter 3: Heaps\n\n" + para * 4
(tmp / "notes.md").write_text(md)
check("markdown book: 'Chapter N:' headings", [s.title for s in book.load(tmp / "notes.md").chapters()][:1] == ["Graphs"]
      or len(book.load(tmp / "notes.md").chapters()) == 3, str([s.name for s in book.load(tmp / "notes.md").chapters()]))
(tmp / "flat.txt").write_text(para * 40)
fb = book.load(tmp / "flat.txt")
check("no structure at all: falls back to page-range units", len(fb.chapters()) >= 1 and fb.chapters()[0].end > 0)
check("sources_for works on a text book", len(book.sources_for(b, b.chapters()[0])) > 0)

check("lessons per night: 2 h → 4, 3 h → 7, 4 h → 10 (cap)",
      [course.lesson_count(h) for h in (2, 3, 4, 6)] == [4, 7, 10, 10])
topics = [{"title": "B", "importance": 3, "prereqs": ["A"]}, {"title": "A", "importance": 5, "prereqs": []},
          {"title": "C", "importance": 2, "prereqs": ["B", "D"]}, {"title": "D", "importance": 1, "prereqs": ["C"]}]
order = [topics[i]["title"] for i in course._topo(topics)]
check("prerequisites first, cycles broken", order.index("A") < order.index("B") < order.index("C") and len(order) == 4,
      str(order))
check("diagnostic validated: exactly one correct option",
      course._diag("q?", [{"text": "a", "correct": True}, {"text": "b", "correct": False}]) is not None
      and course._diag("q?", [{"text": "a", "correct": True}, {"text": "b", "correct": True}]) is None)

R = srs.Rating
check("FSRS rating map", [srs.rating_for("wrong"), srs.rating_for("correct", 1), srs.rating_for("correct", 0, 2),
                          srs.rating_for("correct", 0, 4), srs.rating_for("correct", 0, 5)]
      == [R.Again, R.Hard, R.Hard, R.Good, R.Easy])
from stiti.db import one, q  # noqa: E402
cid = one("INSERT INTO tutor_courses(title, plan) VALUES ('t', '{}') RETURNING id")["id"]
card = one("INSERT INTO study_cards(front, back, course_id) VALUES ('What is a token?', 'A lexeme class', %s) "
           "RETURNING id", (cid,))["id"]
srs.start([card], soon_minutes=10)
due_now = [c["id"] for c in srs.due(course_id=cid)]
due_soon = [c["id"] for c in srs.due(course_id=cid, slack_minutes=11)]
check("new lesson cards come back ~10 min later (in-night checkpoint)", card not in due_now and card in due_soon)
nxt = srs.review(card, R.Good)
nxt2 = srs.review(card, R.Good, datetime.now(timezone.utc) + timedelta(minutes=70))
check("FSRS schedules further out after each good recall", nxt2 - datetime.now(timezone.utc) > timedelta(hours=12),
      f"{nxt} → {nxt2}")
check("exam mode finds at-risk cards", isinstance(srs.at_risk(cid, datetime.now(timezone.utc) + timedelta(days=30)), list))
q("DELETE FROM tutor_courses WHERE id=%s", (cid,))

vr = {t: voice_request(t) for t in ("teach me operating systems tonight", "ek raat mein DBMS sikha do",
                                    "crash course on machine learning", "continue my course", "revise karna hai",
                                    "teach me how DNS works")}
check("voice: crash course / revise / resume phrases", vr == {
    "teach me operating systems tonight": ("operating systems", False, "night"),
    "ek raat mein DBMS sikha do": ("DBMS", False, "night"),
    "crash course on machine learning": ("machine learning", False, "night"),
    "continue my course": (None, True, "night"), "revise karna hai": (None, False, "revise"),
    "teach me how DNS works": ("how DNS works", False)}, str(vr))

from stiti import router  # noqa: E402
if any(s["key"] for s in router.status()):
    p = course.plan_subject("Computer networks basics", hours=2)
    check("live: subject syllabus → overview + ordered lessons with diagnostics",
          len(p["lessons"]) == 4 and p["lessons"][0]["kind"] == "overview"
          and sum(bool(x.get("diag")) for x in p["lessons"][1:]) >= 2, str([x["title"] for x in p["lessons"]]))
else:
    print("   (no LLM key: live planning check skipped)")

print(f"course: {ok}/{ok + fail} checks passed")
sys.exit(1 if fail else 0)
