"""One-night crash course: "teach me this book / subject tonight".  Design + evidence: docs/research/crash_course.md, D19.

  plan   book → chapters scored LOCALLY (foundation, centrality, goal match, size; no LLM reads the book)
         → ONE course-map LLM call orders the night and writes a "guess first" diagnostic MCQ per lesson.
         Bare subject → one LLM call drafts the syllabus (importance + prerequisites), code orders it.
  night  kick-off (map + diagnostic: skip what he knows, shorten what he half-knows) → lessons back to back
         (next lesson written while this one plays) → checkpoint (FSRS cards due) + break every 2 lessons
         → final review quiz → course-map board (green/amber/red) → cheat sheet → 9 am revision reminder → sleep.
"""
from __future__ import annotations

import json
import re
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

from ..config import CFG
from ..db import one, q
from . import srs
from .lesson import Check, Cue, Lesson, Op, Segment

LESSON_MIN, SHORT_IDEAS = 15, 2
BREAK_SHORT_MIN, BREAK_LONG_MIN = 6, 15
SKIP_TITLES = re.compile(r"\b(preface|foreword|acknowledg|contents|index|bibliograph|references|glossary|about the "
                         r"author|gutenberg|copyright|dedication|list of|appendix|exercises? for|answers? to|"
                         r"illustrations|notes on|further reading)\b", re.I)

_S = {"type": "string"}
_OPTS = {"type": "array", "items": {"type": "object", "additionalProperties": False, "required": ["text", "correct"],
                                    "properties": {"text": _S, "correct": {"type": "boolean"}}}}
COURSE_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["title", "lessons"],
    "properties": {"title": _S, "lessons": {"type": "array", "items": {
        "type": "object", "additionalProperties": False, "required": ["unit", "title", "why", "diag_prompt", "diag_options"],
        "properties": {"unit": {"type": "integer"}, "title": _S, "why": _S, "diag_prompt": _S, "diag_options": _OPTS}}}}}
SUBJECT_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["title", "topics"],
    "properties": {"title": _S, "topics": {"type": "array", "items": {
        "type": "object", "additionalProperties": False,
        "required": ["title", "importance", "prereqs", "key_points", "diag_prompt", "diag_options"],
        "properties": {"title": _S, "importance": {"type": "integer"}, "prereqs": {"type": "array", "items": _S},
                       "key_points": {"type": "array", "items": _S}, "diag_prompt": _S, "diag_options": _OPTS}}}}}

COURSE_PROMPT = """Plan a one-night crash course from this book for {learner}.
BOOK: {title}. GOAL: {goal}. Time: {hours} h → exactly {n} lessons of ~15 min (lesson 1, a whole-book overview,
is added by code — do NOT include it).
UNITS (index · title · pages · local importance score 0–1; higher = more central/foundational):
{units}
Choose the {n} units that matter most for the goal (prefer high scores and foundations; skip front/back matter),
ordered so prerequisites come first (usually book order). For each: unit = its index, a short lesson title, why it
matters (≤15 words), and ONE diagnostic multiple-choice question (4 options, exactly one correct) that tells
whether the learner already understands this unit's core idea — test understanding, not trivia."""

SUBJECT_PROMPT = """Draft a one-night crash-course syllabus for "{subject}" for {learner}. GOAL: {goal}.
Return 10–14 topics that together give exam-ready core understanding (most important first is NOT required).
For each: title, importance 1–5 (5 = everything depends on it / most examined), prereqs (titles of other topics
from your list that must come first), 2–4 key_points, and ONE diagnostic multiple-choice question (4 options,
exactly one correct) that tells whether the learner already understands it."""


def lesson_count(hours: float) -> int:
    """⌊(minutes − 30) / 20⌋, 2…10 (30 min of the night go to kick-off, checkpoints and review)."""
    return max(2, min(10, (int(hours * 60) - 30) // 20))


# ------------------------------------------------------------------------------------------------ planning
def _units(book) -> list:
    secs = [s for s in book.chapters() if not SKIP_TITLES.search(s.title)]
    if len(secs) < 4:                                    # few chapters: teach their sections instead
        secs = [s for s in book.sections if s.level <= 2 and not SKIP_TITLES.search(s.title)] or book.sections
    return secs


def _score_units(book, units, goal: str | None) -> list[float]:
    import numpy as np

    from .. import embed
    texts = []
    for u in units:
        body = re.sub(r"\s+", " ", " ".join(book.pages[u.page:u.page + 2]))[:600]
        texts.append(f"{u.title}. {body}")
    vecs = np.concatenate([embed._embed(texts[b:b + 32]) for b in range(0, len(texts), 32)])
    norm = lambda a: (a - a.min()) / (a.max() - a.min() + 1e-9)  # noqa: E731
    central = norm(vecs @ vecs.mean(axis=0))
    pages = np.array([max(1, u.end - u.page) for u in units], dtype=float)
    share = norm(np.log1p(pages))
    found = norm(1 - np.arange(len(units)) / max(1, len(units)))   # earlier units are what later ones build on
    goal_m = norm(vecs @ np.asarray(embed.embed_query(goal).to_numpy(), dtype=np.float32)) if goal else np.zeros(len(units))
    w = (0.30, 0.25, 0.25, 0.20) if goal else (0.40, 0.35, 0.0, 0.25)
    return list(w[0] * found + w[1] * central + w[2] * goal_m + w[3] * share)


def _diag(prompt: str, options: list[dict]) -> dict | None:
    opts = [{"text": str(o.get("text", ""))[:90], "correct": bool(o.get("correct"))} for o in options or []][:4]
    if not prompt or len(opts) < 2 or sum(o["correct"] for o in opts) != 1:
        return None
    return {"prompt": prompt[:200], "options": opts}


def plan_book(path: str, hours: float = 3, goal: str | None = None, log=print) -> dict:
    from . import book as B
    from .planner import _call, _learner
    b = B.load(path)
    units = _units(b)
    if not units:
        raise ValueError("couldn't find any chapters or sections in that book")
    n = lesson_count(hours) - 1
    log(f"   {b.title}: {len(units)} units, planning {n + 1} lessons for {hours:g} h…")
    scores = _score_units(b, units, goal)
    lines = "\n".join(f"{k} · {u.name[:70]} · p.{u.label}–{b.labels[min(u.end, len(b.labels)) - 1]} · {s:.2f}"
                      for k, (u, s) in enumerate(zip(units, scores)))
    chosen: list[dict] = []
    try:
        d = _call("You are an expert curriculum designer. Output only JSON.",
                  COURSE_PROMPT.format(learner=_learner(), title=b.title, goal=goal or "solid core understanding",
                                       hours=hours, n=n, units=lines[:12000]),
                  COURSE_SCHEMA, "course", 3000, patience_s=60)
        seen = set()
        for x in d.get("lessons") or []:
            k = x.get("unit")
            if isinstance(k, int) and 0 <= k < len(units) and k not in seen:
                seen.add(k)
                chosen.append({"unit": k, "title": (x.get("title") or units[k].title)[:70], "why": x.get("why", "")[:120],
                               "diag": _diag(x.get("diag_prompt", ""), x.get("diag_options"))})
        title = d.get("title") or b.title
    except Exception as e:                               # no LLM: deterministic plan from the local scores
        log(f"   (course map from local scores only: {type(e).__name__})")
        title = b.title
    if len(chosen) < min(n, len(units)):                 # top up / fallback from the local ranking
        have = {c["unit"] for c in chosen}
        for k in sorted(range(len(units)), key=lambda k: -scores[k]):
            if len(chosen) >= min(n, len(units)):
                break
            if k not in have:
                chosen.append({"unit": k, "title": units[k].title[:70], "why": "", "diag": None})
    chosen = sorted(chosen[:n], key=lambda c: units[c["unit"]].page)        # prerequisites first ≈ book order
    lessons = [{"title": f"The big picture: {title}"[:80], "kind": "overview", "depth": "full", "status": "todo"}]
    for c in chosen:
        u = units[c["unit"]]
        lessons.append({"title": c["title"], "kind": "unit", "why": c["why"], "diag": c["diag"], "depth": "full",
                        "status": "todo", "unit": {"name": u.name, "page": u.page, "end": u.end, "label": u.label}})
    return {"title": title[:80], "kind": "book", "path": str(Path(path).expanduser()), "goal": goal, "hours": hours,
            "units_total": len(units), "lessons": lessons}


def _topo(topics: list[dict]) -> list[int]:
    """Prerequisites first (Kahn); a cycle is broken by dropping its remaining edges."""
    idx = {t["title"].lower(): i for i, t in enumerate(topics)}
    deps = {i: {idx[p.lower()] for p in t.get("prereqs") or [] if p.lower() in idx and idx[p.lower()] != i}
            for i, t in enumerate(topics)}
    order, done = [], set()
    while len(order) < len(topics):
        ready = [i for i in range(len(topics)) if i not in done and deps[i] <= done]
        if not ready:                                    # cycle: take the most important remaining topic
            ready = [max((i for i in range(len(topics)) if i not in done), key=lambda i: topics[i]["importance"])]
        for i in ready:
            order.append(i)
            done.add(i)
    return order


def plan_subject(subject: str, hours: float = 3, goal: str | None = None, log=print) -> dict:
    from .planner import _call, _learner
    n = lesson_count(hours) - 1
    log(f"   Drafting a syllabus for {subject!r}: {n + 1} lessons for {hours:g} h…")
    d = _call("You are an expert curriculum designer. Output only JSON.",
              SUBJECT_PROMPT.format(subject=subject, learner=_learner(), goal=goal or "solid core understanding"),
              SUBJECT_SCHEMA, "syllabus", 3500, patience_s=60)
    topics = [t for t in d.get("topics") or [] if t.get("title")]
    for t in topics:
        t["importance"] = max(1, min(5, int(t.get("importance") or 3)))
    keep = set(sorted(range(len(topics)), key=lambda i: -topics[i]["importance"])[:n])
    lessons = [{"title": f"The big picture: {subject}"[:80], "kind": "overview", "depth": "full", "status": "todo"}]
    for i in _topo(topics):
        if i in keep:
            t = topics[i]
            lessons.append({"title": t["title"][:70], "kind": "topic", "why": "", "status": "todo", "depth": "full",
                            "key_points": [k[:120] for k in t.get("key_points") or []][:4],
                            "diag": _diag(t.get("diag_prompt", ""), t.get("diag_options"))})
    return {"title": (d.get("title") or subject)[:80], "kind": "subject", "subject": subject, "goal": goal,
            "hours": hours, "lessons": lessons}


def create(target: str, hours: float = 3, goal: str | None = None, log=print) -> int:
    p = Path(target).expanduser()
    from . import BOOK_EXTS
    plan = plan_book(str(p), hours, goal, log) if p.exists() and p.suffix.lower() in BOOK_EXTS \
        else plan_subject(target, hours, goal, log)
    row = one("""INSERT INTO tutor_courses(title, source, goal, hours, plan) VALUES (%s,%s,%s,%s,%s) RETURNING id""",
              (plan["title"], json.dumps({k: plan.get(k) for k in ("kind", "path", "subject")}), goal, hours,
               json.dumps(plan)))
    return row["id"]


def load(course_id: int | None = None) -> dict | None:
    row = one("SELECT * FROM tutor_courses WHERE id=%s", (course_id,)) if course_id else \
        one("SELECT * FROM tutor_courses WHERE status IN ('planned','running','stopped') ORDER BY updated_at DESC LIMIT 1")
    return row


def _save(cid: int, plan: dict, cursor: int, status: str) -> None:
    q("UPDATE tutor_courses SET plan=%s, cursor=%s, status=%s, updated_at=now() WHERE id=%s",
      (json.dumps(plan), cursor, status, cid))


# ------------------------------------------------------------------------------------------------ the night
def _quiz_lesson(title: str, intro: str, items: list[tuple[str, Check]]) -> Lesson:
    segs = [Segment(id="intro", type="organizer", title=title,
                    cues=[Cue("i1", intro, [Op(type="new_page", text=title)])])]
    for k, (sid, chk) in enumerate(items):
        say = "First one." if k == 0 else "Last one." if k == len(items) - 1 else "Next."
        segs.append(Segment(id=sid, type="quiz", title=title, cues=[Cue(f"{sid}c", say, [])], check=chk))
    return Lesson(title=title, topic=title, segments=segs, source={"kind": "course"}, minutes=5)


class Night:
    def __init__(self, course_id: int, *, audio, events, server=None, log=print):
        row = load(course_id)
        self.cid, self.plan, self.cursor = row["id"], row["plan"], row["cursor"]
        self.audio, self.events, self.srv, self.log = audio, events, server, log
        self.t0 = time.time()
        self.deadline = self.t0 + float(self.plan.get("hours", 3)) * 3600
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="next-lesson")
        self.next: dict[int, Future] = {}
        self._book = None
        self.stopped = False

    # -- helpers
    def _tutor(self, lesson: Lesson, planner=None):
        from . import answerer
        from .player import Tutor
        return Tutor(lesson, audio=self.audio, events=self.events, server=self.srv, planner=answerer(planner))

    def _run(self, lesson: Lesson, planner=None) -> dict:
        t = self._tutor(lesson, planner)
        res = t.run()
        if getattr(t, "lesson_id", None):
            q("UPDATE tutor_lessons SET course_id=%s WHERE id=%s", (self.cid, t.lesson_id))
        res["lesson_id"] = getattr(t, "lesson_id", None)
        if getattr(t, "ended", False) and not res.get("finished"):
            self.stopped = True                          # he said stop / bas karo — not just a slow writer
        return res

    def _say_board(self, title: str, lines: list[tuple[str, str]], speech: str) -> dict:
        """A one-cue board page: lines = [(text, style)]."""
        ops = [Op(type="new_page", text=title)]
        for i, (txt, style) in enumerate(lines[:12]):
            ops.append(Op(type="box", id=f"b{i}", text=txt[:42], style=style, place="next_line"))
        return self._run(Lesson(title=title, topic=title, source={"kind": "course"}, minutes=1,
                                segments=[Segment(id="s", type="organizer", title=title, cues=[Cue("c1", speech, ops)])]))

    def book(self):
        if self._book is None:
            from . import book as B
            self._book = B.load(self.plan["path"])
        return self._book

    def _build(self, i: int):
        from . import planner
        L = self.plan["lessons"][i]
        ideas = SHORT_IDEAS if L["depth"] == "short" else 3
        minutes = 10 if L["depth"] == "short" else LESSON_MIN
        if self.plan["kind"] == "book":
            from . import book as B
            b = self.book()
            if L["kind"] == "overview":
                sources = []
                for u in [x["unit"] for x in self.plan["lessons"] if x.get("unit")][:10]:
                    sec = B.Section("", u["name"], 1, u["page"], u["label"])
                    sec.end = u["end"]
                    sources += B.sources_for(b, sec, n=4, max_pages=4)
                topic = (f"A 15-minute big-picture overview of the whole book '{b.title}': what it is about, how its "
                         f"main parts fit together (" + "; ".join(x["title"] for x in self.plan["lessons"][1:]) + ")")
            else:
                u = L["unit"]
                sec = B.Section("", u["name"], 1, u["page"], u["label"])
                sec.end = u["end"]
                sources = B.sources_for(b, sec)
                topic = f"{u['name']} — from the book '{b.title}'"
            return planner.build(topic, minutes=minutes, sources=sources, ideas=ideas, log=self.log,
                                 source={"kind": "book", "path": self.plan["path"], "course": self.cid})
        if L["kind"] == "overview":
            topic = (f"A 15-minute big-picture overview of {self.plan['subject']}: how these parts fit together: "
                     + "; ".join(x["title"] for x in self.plan["lessons"][1:]))
        else:
            topic = f"{L['title']} (part of a one-night crash course on {self.plan['subject']}). " \
                    f"Cover: {'; '.join(L.get('key_points') or [])}"
        return planner.build(topic, minutes=minutes, ideas=ideas, log=self.log,
                             source={"kind": "topic", "course": self.cid})

    def _prefetch(self, i: int) -> None:
        if i < len(self.plan["lessons"]) and i not in self.next and self.plan["lessons"][i]["depth"] != "skip":
            self.next[i] = self.pool.submit(self._build, i)

    def _wait_break(self, minutes: int) -> None:
        from .player import Tutor
        end = time.time() + minutes * 60
        while time.time() < end and not self.stopped:
            try:
                ev = self.events.get(timeout=1)
            except Exception:
                continue
            kind, _ = Tutor._kind(ev)
            if kind in ("end", "stop"):
                self.stopped = True
            elif kind not in ("other", "hand", "click"):
                return                                   # "chalo / continue / I'm back" ends the break early

    # -- phases
    def kickoff(self) -> None:
        L = self.plan["lessons"]
        mins = round((self.deadline - time.time()) / 60)
        self._say_board("Tonight's plan", [(f"{k + 1}. {x['title']}", "blue" if k == 0 else "plain") for k, x in enumerate(L)],
                        f"Chalo! Tonight: {self.plan['title']}. {len(L)} short lessons in about {mins // 60} hours "
                        f"{mins % 60} minutes, with breaks. First, a quick guess-check so I can skip what you already know.")
        if self.stopped:
            return
        items = [(f"d{k}", Check(kind="mcq", prompt=x["diag"]["prompt"], options=x["diag"]["options"], confidence=True,
                                 reveal="Okay, noted.", on_correct="Nice."))
                 for k, x in enumerate(L) if x.get("diag")][:10]
        if not items:
            return
        res = self._run(_quiz_lesson("Quick guess-check", "Just guess, it's fine to be wrong. It actually helps you "
                                     "remember later.", items))
        for r in res.get("results") or []:
            k = int(r["segment"][1:]) if r.get("segment", "").startswith("d") else None
            if k is None:
                continue
            conf = r.get("confidence") or 3
            if r.get("verdict") == "correct" and conf >= 4:
                L[k]["depth"] = "skip"                   # knows it: checkpoint question + cards only
            elif r.get("verdict") == "correct":
                L[k]["depth"] = "short"
        skipped = [x["title"] for x in L if x["depth"] == "skip"]
        if skipped:
            self.audio_say(f"You already know {', '.join(skipped[:3])} — I'll skip those and just check them later.")

    def audio_say(self, text: str) -> None:
        self._run(Lesson(title="note", topic="note", source={"kind": "course"}, minutes=1,
                         segments=[Segment(id="s", type="organizer", title="note", cues=[Cue("c1", text, [])])]))

    def checkpoint(self) -> None:
        cards = srs.due(limit=3, course_id=self.cid, slack_minutes=5)
        if not cards:
            return
        items = [(f"c{c['id']}", Check(kind="recall", prompt=c["front"], expectations=[c["back"]], reveal=c["back"],
                                       hints=[], on_correct="Yes!")) for c in cards]
        res = self._run(_quiz_lesson("Checkpoint", "Quick checkpoint from earlier, no peeking.", items))
        for r in res.get("results") or []:
            if r.get("segment", "").startswith("c"):
                srs.review(int(r["segment"][1:]), srs.rating_for(r.get("verdict"), r.get("hints", 0), r.get("confidence")))

    def lesson(self, i: int) -> None:
        L = self.plan["lessons"][i]
        self._prefetch(i)
        try:
            lesson, planner = self.next.pop(i).result()
        except Exception as e:
            self.log(f"   [course] couldn't write lesson {i + 1} ({type(e).__name__}: {str(e)[:120]}) — skipping")
            L["status"] = "missed"
            return
        self._prefetch(i + 1)                            # write the next lesson while this one plays
        res = self._run(lesson, planner)
        graded = res.get("checks_graded") or 0
        score = (res.get("checks_right") or 0) / graded if graded else 1.0
        L["status"] = "green" if score >= 0.8 else "amber" if score >= 0.4 else "red"
        L["score"] = round(score, 2)
        if res.get("lesson_id"):
            ids = [r["id"] for r in q("UPDATE study_cards SET course_id=%s WHERE lesson_id=%s RETURNING id",
                                      (self.cid, res["lesson_id"]))]
            srs.start(ids, soon_minutes=10)
            L["summary"] = lesson.summary

    def final_review(self) -> None:
        cards = srs.due(limit=8, course_id=self.cid, slack_minutes=24 * 60)
        if cards:
            items = [(f"c{c['id']}", Check(kind="recall", prompt=c["front"], expectations=[c["back"]], reveal=c["back"],
                                           hints=[], on_correct="Yes!")) for c in cards]
            res = self._run(_quiz_lesson("Final review", "Last round: mixed questions from the whole night.", items))
            for r in res.get("results") or []:
                if r.get("segment", "").startswith("c"):
                    srs.review(int(r["segment"][1:]),
                               srs.rating_for(r.get("verdict"), r.get("hints", 0), r.get("confidence")))
        style = {"green": "green", "amber": "warm", "red": "red", "skip": "green"}
        lines = [(x["title"], style.get(x["status"] if x["depth"] != "skip" else "skip", "muted"))
                 for x in self.plan["lessons"]]
        weak = [x["title"] for x in self.plan["lessons"] if x["status"] in ("amber", "red")]
        sheet = self.cheat_sheet()
        remind = self.morning_reminder()
        self._say_board("Your course map", lines,
                        "That's the night! Green you've got, orange needs one more look"
                        + (f" — especially {', '.join(weak[:2])}" if weak else "") + ". I saved a cheat sheet"
                        + (f" and {remind}" if remind else "") + ". Now go sleep, sleep is when it sticks. Good night!")
        self.log(f"   cheat sheet: {sheet}")

    def cheat_sheet(self) -> str:
        d = CFG.home / "courses"
        d.mkdir(parents=True, exist_ok=True)
        slug = re.sub(r"[^a-z0-9]+", "-", self.plan["title"].lower()).strip("-")[:40]
        path = d / f"{datetime.now():%Y-%m-%d}-{slug}.md"
        out = [f"# {self.plan['title']} — one-night cheat sheet", ""]
        for x in self.plan["lessons"]:
            mark = {"green": "✅", "amber": "🟠", "red": "🔴", "missed": "⏭"}.get(x["status"], "·")
            out.append(f"## {mark} {x['title']}" + (f"  (p.{x['unit']['label']}+)" if x.get("unit") else ""))
            out += [f"- {s}" for s in x.get("summary") or []]
            out.append("")
        cards = q("SELECT front, back FROM study_cards WHERE course_id=%s ORDER BY id", (self.cid,))
        if cards:
            out += ["## Revision cards", ""] + [f"- **{c['front']}** — {c['back']}" for c in cards]
        path.write_text("\n".join(out))
        return str(path)

    def morning_reminder(self) -> str | None:
        try:
            from ..fastpath import handlers
            r = handlers.timeish(f"remind me tomorrow at 9 am to revise {self.plan['title'][:50]} with Stiti")
            return "set a revision reminder for 9 tomorrow morning" if r else None
        except Exception:
            return None

    def run(self) -> dict:
        _save(self.cid, self.plan, self.cursor, "running")
        L = self.plan["lessons"]
        if self.cursor == 0:
            self._prefetch(0)                            # overview writes itself during the kick-off
            self.kickoff()
        breaks = 0
        i = self.cursor
        while i < len(L) and not self.stopped:
            if time.time() > self.deadline - 15 * 60:     # keep the last 15 min for the review
                for x in L[i:]:
                    x["status"] = "missed"
                break
            if L[i]["depth"] == "skip":
                L[i]["status"] = "green"
            else:
                self.lesson(i)
            i += 1
            _save(self.cid, self.plan, i, "running")
            if not self.stopped and i < len(L) and i % 2 == 0:   # every 2 lessons: checkpoint + break
                self.checkpoint()
                breaks += 1
                mins = BREAK_LONG_MIN if breaks % 3 == 0 else BREAK_SHORT_MIN
                if not self.stopped:
                    self._say_board(f"Break · {mins} min", [("Stand up · water · look far away", "green"),
                                                             ("Say \"chalo\" when you're back", "muted")],
                                    f"Break time, {mins} minutes. Stand up, drink some water, no phone. "
                                    "Say chalo when you're back.")
                    self._wait_break(mins)
        if not self.stopped:
            self.final_review()
        _save(self.cid, self.plan, i, "stopped" if self.stopped else "done")
        self.pool.shutdown(wait=False, cancel_futures=True)
        done = sum(x["status"] in ("green", "amber", "red") for x in L)
        return {"finished": not self.stopped, "lessons_done": done, "lessons": len(L), "course_id": self.cid}


def revise_lesson(course_id: int | None = None, limit: int = 20) -> tuple[Lesson | None, list[dict]]:
    """Morning / exam revision: due cards (weakest first) as one quick quiz."""
    cards = srs.due(limit=limit, course_id=course_id)
    if not cards:
        return None, []
    items = [(f"c{c['id']}", Check(kind="recall", prompt=c["front"], expectations=[c["back"]], reveal=c["back"],
                                   hints=[], on_correct="Yes!", confidence=True)) for c in cards]
    return _quiz_lesson("Revision", f"Good morning! {len(cards)} quick questions, weakest first.", items), cards


_lock = threading.Lock()
