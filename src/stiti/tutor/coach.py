"""Coach — a teaching session that starts from HIM, not from page 1 (D53).

Research: docs/research/tutor_agent.md (VanLehn: he acts every step · Kalyuga: don't re-teach what he knows ·
Metcalfe & Kornell: triage under a deadline · AutoTutor hint ladder · DeepTutor goal-first + mastery gate · OATutor BKT).

1. While the concept map of his file is built (cached per file), she asks his goal: exam? when?
2. Three quick probes spread over the units → local grading → mastery per concept (mastery.py).
3. The queue: what he needs most first. Exam mode: nearly-known before brand-new, known ones get one quick check.
4. Each concept = short steps: ≤ 2 spoken sentences, then HIS turn (a check), graded locally; mastery updates after
   every answer, and a concept he clearly knows is cut short. The board is one notes page per concept (slots).
Concepts are written by the free cloud LLM one at a time while he works, so the first one starts in seconds.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .lesson import Check, Cue, Lesson, Op, Segment
from .mastery import KNOWN, SHAKY, Mastery, key_for

# ---- pacing / budget
CONCEPT_MIN = {"new": 6.0, "shaky": 4.0, "known": 1.0}   # minutes each, for the time budget
EXAM_MINUTES = 100        # a "tomorrow" exam session; he can always say "stop" or "continue later"
LEARN_MINUTES = 40
MAX_CONCEPTS_PER_UNIT = 5
PROBES = 3

_CHECK_KINDS = ["mcq", "recall", "apply", "explain_why"]
_S = {"type": "string"}


def _nullable(t):
    return {"anyOf": [t, {"type": "null"}]}


def _cut(s: str, n: int) -> str:
    """Clip at a word boundary with '…' ('Cell wall of Gram-positive and…', not '…Gram-negative bac')."""
    s = " ".join((s or "").split())
    if len(s) <= n:
        return s
    k = s.rfind(" ", 0, n)
    return (s[:k] if k >= n // 2 else s[:n - 1]).rstrip(" ,;:-–—(") + "…"


CONCEPTS_PROMPT = """List the key concepts of this unit of the learner's study material, in teaching order.
UNIT: {unit}
{sources}
Return JSON: concepts = 2–{n} items, each: name (≤5 words), points (2–3 short key facts, ≤12 words each, stated as
facts the way an exam asks them, not instructions like "Explain X"), weight (1–3: how likely an exam asks it).
Only what the SOURCES cover; no invented content."""
OUTLINE_PROMPT = """This unit of the learner's syllabus only LISTS its topics. Plan the concepts to teach it, using
accurate standard textbook knowledge at the level the course implies.
COURSE: {course}
UNIT: {unit}
LISTED TOPICS:
{topics}
Return JSON: concepts = {lo}–{n} items in the listed order that together cover EVERY listed topic (one concept per
topic; split a topic only when it lists several big ideas, merge two tiny ones), each: name (≤5 words: the
syllabus's own term, shortened if long), points (2–3 key facts, ≤12 words each, stated as facts the way an exam asks them, not
instructions like "Explain X"), weight (1–3: how likely an exam asks it). Nothing outside this unit's topics."""
CONCEPTS_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["concepts"], "properties": {
    "concepts": {"type": "array", "items": {"type": "object", "additionalProperties": False,
                                            "required": ["name", "points", "weight"],
                                            "properties": {"name": _S, "points": {"type": "array", "items": _S},
                                                           "weight": {"type": "integer"}}}}}}

TOPIC_PROMPT = """Plan the concepts a learner needs for: {topic}
{listed}Return JSON: concepts = {lo}–{hi} items in teaching order, grouped into 2–5 units: unit = a short group name
shared by 2–4 consecutive concepts (never one unit per concept). Concepts of THIS topic itself: start with what it
is and why it matters (at most one quick refresher of a prerequisite, only if essential), build up to its core
ideas, end with how it is used / typical problems. Each: unit, name (≤5 words), points (2–3 key facts, ≤12 words
each, stated as accurate facts, not instructions like "Explain X"), weight (1–3: how central it is, or how likely
an exam asks it)."""
TOPIC_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["concepts"], "properties": {
    "concepts": {"type": "array", "items": {"type": "object", "additionalProperties": False,
                                            "required": ["unit", "name", "points", "weight"],
                                            "properties": {"unit": _S, "name": _S,
                                                           "points": {"type": "array", "items": _S},
                                                           "weight": {"type": "integer"}}}}}}

PROBES_PROMPT = """Write {n} quick diagnostic questions to find out what the learner already knows. Take each from a
DIFFERENT unit (early, middle, late), on a central concept. Each question: ≤20 words, answerable by voice in one
short sentence (a definition, a first step, a cause, "what happens when…"), with one clear right answer; not yes/no,
not "list all…". CONCEPTS (id: unit · name · key facts):
{concepts}
Return JSON: probes = items of: concept_id (copied from the list), question, expected = usually ONE key point a
right spoken answer must contain (a second only if the question asks for two things), 1–5 words, true and taken
from that concept's key facts, not words from the question; add the common spoken ways to say it, and any other
right answers, in that ONE point joined by " or " (e.g. "light intensity or amount of light", "throughput or
waiting time")."""
PROBES_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["probes"], "properties": {
    "probes": {"type": "array", "items": {"type": "object", "additionalProperties": False,
                                          "required": ["concept_id", "question", "expected"],
                                          "properties": {"concept_id": _S, "question": _S,
                                                         "expected": {"type": "array", "items": _S}}}}}}

STEP_PROMPT = """Teach ONE concept by voice on a whiteboard, as a few short steps. After every step the learner
answers a question — that is how they learn (never a lecture).
CONCEPT: {name} (unit: {unit}) · key facts: {points}
LEARNER: {level_line} · mode: {mode_line}
{sources}
Return JSON: steps = {steps} item(s). Each step has:
- say: 1–2 spoken sentences in total, one per array item (≤22 words each, plain English, a concrete example
  before the jargon: a real everyday case, or for maths / code a small specific instance — no forced analogies).
- points: 1–2 key facts for the board (≤10 words each).
- figure: ONE small diagram that fits the subject, REQUIRED in step 1 (null in later steps): kind "graph" (≤5 nodes
  with short labels + labelled edges: a process, a cause → effect chain, a cycle, a timeline, a structure), "table"
  (rows = ≤4 rows × ≤3 cells: a comparison or values, first row = headers), "formula" (text = the formula; use it
  whenever the concept IS an equation or rule in symbols), or "box" (text = one key term or rule, ≤4 words).
- example: in a second step, 2–4 lines of working (≤8 words each), one per line: for a method, formula, rule or
  code, solve one real problem step by step; for facts, history, biology or language, walk through one real case,
  sequence or timeline (never a made-up "what if"). Empty in step 1.
- check: one question the learner answers out loud right after, about what this step just showed, with one clear
  right answer (never yes/no): kind recall / apply / explain_why, or mcq with 3 options (one correct).
  expectations = usually ONE key point a right SPOKEN answer must contain (a second only if the question asks for
  two things), 1–6 words in a student's own words (e.g. "longest match", "x squared"), not words from the question,
  never rubric phrasing like "mentions …"; add the common spoken ways to say it (and other right answers) in that
  ONE point joined by " or " (e.g. "light intensity or amount of light"); the exact number or value when the
  answer is one. hints = 2 hints that don't give it away; reveal = the answer in one
  sentence.
remember = the one fact for the "Remember" box: a statement, not a question (≤12 words).
{facts_rule}"""
FACTS_FROM_SOURCES = "Facts only from SOURCES."
FACTS_GENERAL = ("Use accurate standard textbook knowledge. Never claim \"the book says\" or \"your notes say\": the "
                 "learner's file only lists topics.")
_GRAPH = {"nodes": _nullable({"type": "array", "items": {
              "type": "object", "additionalProperties": False, "required": ["id", "text"],
              "properties": {"id": _S, "text": _S}}}),
          "edges": _nullable({"type": "array", "items": {
              "type": "object", "additionalProperties": False, "required": ["from", "to", "text"],
              "properties": {"from": _S, "to": _S, "text": _nullable(_S)}}}),
          "rows": _nullable({"type": "array", "items": {"type": "array", "items": _S}})}
# the older one-list form (board = [{slot, kind, text, nodes, edges, rows}]) is still read by _step_board
_BOARD_ITEM = {"type": "object", "additionalProperties": False,
               "required": ["slot", "kind", "text", "nodes", "edges", "rows"],
               "properties": {"slot": {"type": "string", "enum": ["point", "figure", "example"]},
                              "kind": _nullable({"type": "string", "enum": ["text", "graph", "table", "formula", "box"]}),
                              "text": _nullable(_S), **_GRAPH}}
_FIGURE = _nullable({"type": "object", "additionalProperties": False,
                     "required": ["kind", "text", "nodes", "edges", "rows"],
                     "properties": {"kind": {"type": "string", "enum": ["graph", "table", "formula", "box"]},
                                    "text": _nullable(_S), **_GRAPH}})
STEP_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["steps", "remember"], "properties": {
    "steps": {"type": "array", "items": {"type": "object", "additionalProperties": False,
                                         "required": ["say", "points", "figure", "example", "check"],
                                         "properties": {
                                             "say": {"type": "array", "items": _S},
                                             "points": {"type": "array", "items": _S},
                                             "figure": _FIGURE,
                                             "example": {"type": "array", "items": _S},
                                             "check": {"type": "object", "additionalProperties": False,
                                                       "required": ["kind", "prompt", "options", "expectations",
                                                                    "hints", "reveal"],
                                                       "properties": {
                                                           "kind": {"type": "string", "enum": _CHECK_KINDS},
                                                           "prompt": _S,
                                                           "options": _nullable({"type": "array", "items": {
                                                               "type": "object", "additionalProperties": False,
                                                               "required": ["text", "correct"],
                                                               "properties": {"text": _S,
                                                                              "correct": {"type": "boolean"}}}}),
                                                           "expectations": {"type": "array", "items": _S},
                                                           "hints": {"type": "array", "items": _S},
                                                           "reveal": _S}}}}},
    "remember": _S}}


@dataclass
class Concept:
    id: str
    name: str
    unit: str
    points: list[str] = field(default_factory=list)
    weight: int = 2
    unit_idx: int = 0
    general: bool = False         # taught from general knowledge (a topic, or a syllabus that only lists topics)


# ------------------------------------------------------------------------------------------------ concept map
def _cache_path(source: str) -> Path:
    from ..config import CFG
    return CFG.home / "tutor" / "concepts" / f"{key_for(source)}.json"


def _concept(raw: dict, cid: str, unit: str, unit_idx: int, general: bool) -> Concept:
    try:
        w = min(3, max(1, int(raw.get("weight") or 2)))
    except (TypeError, ValueError):
        w = 2
    return Concept(id=cid, name=_cut(str(raw.get("name") or "?"), 48), unit=unit[:60],
                   points=[_cut(str(p), 90) for p in (raw.get("points") or []) if str(p).strip()][:3],
                   weight=w, unit_idx=unit_idx, general=general)


def _regroup(out: list[Concept]) -> list[Concept]:
    """A weak model gives every concept its own 'unit': regroup consecutive ones in threes (units drive the probe
    spread and 'a right answer means the earlier ones of that unit are known')."""
    units = list(dict.fromkeys(c.unit for c in out))
    if len(out) < 6 or len(units) <= max(5, len(out) // 2):
        return out
    for k, c in enumerate(out):
        c.unit_idx = k // 3
        c.unit = out[(k // 3) * 3].unit
    return out


def _topic_concepts(call, P, topic: str, listed: list[str] | None = None) -> list[Concept]:
    if listed:                                     # a syllabus with no unit headings: group its topics into units
        lst = ("LISTED TOPICS (cover every one, in this order; merge two tiny ones if needed):\n"
               + "\n".join(f"- {t}" for t in listed[:30]) + "\n")
        lo, hi = min(len(listed), 6), min(20, max(8, len(listed) + 2))
    else:
        lst, lo, hi = "", 6, 12
    prompt = TOPIC_PROMPT.format(topic=topic[:200], listed=lst, lo=lo, hi=hi)
    out: list[Concept] = []
    for attempt in range(2):                       # a lazy free model sometimes returns ONE concept: ask once more
        d = call(P.STYLE.format(name=P._name()), prompt + ("" if not attempt else
                 f"\n(Your last answer had only {len(out)}. Give {lo}–{hi} concepts.)"),
                 TOPIC_SCHEMA, "concepts", 2200 if listed else 1500, route="tutor_plan", reasoning="low", patience_s=30)
        units: list[str] = []
        got: list[Concept] = []
        for c in d.get("concepts") or []:
            if not c.get("name"):
                continue
            u = str(c.get("unit") or "Basics")[:60]
            if u not in units:
                units.append(u)
            got.append(_concept(c, f"c{len(got)}", u, units.index(u), True))
        if len(got) > len(out):
            out = got
        if len(out) >= min(lo, 4):
            break
    return _regroup(out[:hi])


def concept_map(source: str, *, book_path: str | None = None, unit: str | None = None, call=None) -> list[Concept]:
    """Every concept of his file (one LLM call per unit, two at a time) or of a topic (one call). Cached per file.
    A syllabus / topic list (book.is_outline) has no text to teach from: its listed topics name the concepts and
    general knowledge fills them in (Concept.general)."""
    from . import planner as P
    call = call or P._call
    stamp = ""
    if book_path:
        try:                                       # he edits his syllabus → a fresh map, not last week's cache
            st = Path(book_path).expanduser().stat()
            stamp = f"@{int(st.st_mtime)}:{st.st_size}"
        except OSError:
            pass
    cache = _cache_path(source + (f"#{unit}" if unit else "") + stamp)
    try:
        return [Concept(**c) for c in json.loads(cache.read_text())]
    except Exception:
        pass
    out: list[Concept] = []
    if book_path:
        from . import book as B
        b = B.load(book_path)
        units = b.chapters() or b.sections
        if unit:
            sec = b.find(unit)
            units = [sec] if sec else units
        outline = B.is_outline(b)
        course = b.title
        if b.pages:
            course = next((ln.strip(" #*") for ln in b.pages[0].splitlines() if ln.strip(" #*")), b.title)[:120]
        if outline and len(units) <= 1:              # a flat topic list: the LLM groups it into units
            topics = B.outline_topics(B.unit_text(b, units[0]) if units else "\n".join(b.pages))
            out = _topic_concepts(call, P, course, topics)
            units = []
        results: dict[int, list[dict]] = {}
        caps: dict[int, int] = {}

        def one(i, sec):
            try:
                if outline:                          # the unit only lists topics: those + general knowledge
                    topics = B.outline_topics(B.unit_text(b, sec))[:12]
                    caps[i] = n = min(8, max(3, len(topics) + 1))
                    prompt = OUTLINE_PROMPT.format(course=course, unit=sec.name, lo=min(len(topics), n) or 2, n=n,
                                                   topics="\n".join(f"- {t}" for t in topics) or "(see the unit name)")
                else:
                    srcs = B.sources_for(b, sec, n=30)
                    prompt = CONCEPTS_PROMPT.format(unit=sec.name, n=MAX_CONCEPTS_PER_UNIT,
                                                    sources=P._sources_block(srcs, 5000))
                d = call(P.STYLE.format(name=P._name()), prompt, CONCEPTS_SCHEMA, "concepts",
                         1200 if outline else 900, route="tutor_plan", reasoning="low", patience_s=30)
                results[i] = d.get("concepts") or []
            except Exception as e:
                print(f"   [coach] concepts for {sec.name}: {type(e).__name__}: {str(e)[:100]}")
                results[i] = [{"name": sec.title or sec.name, "points": [], "weight": 2}]
        threads = []
        for i, sec in enumerate(units[:12]):
            th = threading.Thread(target=one, args=(i, sec), daemon=True)
            threads.append(th)
            th.start()
            if len(threads) % 2 == 0:                # two at a time: free per-minute limits
                for t in threads[-2:]:
                    t.join(60)
        for t in threads:
            t.join(60)
        for i, sec in enumerate(units[:12]):
            for c in (results.get(i) or [])[:caps.get(i, MAX_CONCEPTS_PER_UNIT)]:
                if c.get("name"):
                    out.append(_concept(c, f"u{i}c{len(out)}", sec.name, i, outline))
    else:
        out = _topic_concepts(call, P, source)
    if out:
        try:
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps([asdict(c) for c in out], indent=1))
        except Exception:
            pass
    return out


_RUBRIC = re.compile(r"^(?:(?:the )?(?:answer|response|reply|learner|student|they)\s+)?(?:should\s+|must\s+)?"
                     r"(?:mentions?|identif(?:y|ies)|states?|says?|notes?|explains?|includes?|contains?|uses?|"
                     r"names?|recogni[sz]es?|understands?|describes?|gives?|lists?|refers? to)\b[:\s]*(?:that\s+)?",
                     re.I)


_MANY = re.compile(r"\b(two|three|four|five|both|each|all|list|steps|order|sequence|compare|differ\w*|vs|versus)\b|"
                   r"\band (why|how|what|when|where|which|who)\b", re.I)


def clean_expectations(exps, k: int = 2, question: str = "") -> list[str]:
    """Expectations are words a right SPOKEN answer contains, not a rubric: 'Mentions printing before the call' →
    'printing before the call'. At most k (one spoken sentence rarely covers more). Free models list ways of saying
    ONE answer as separate items (['tuberculosis', 'TB'], ['sum divided by count', 'total divided by number']), and
    the grader needs ALL items — so unless the question asks for several things, they become one 'A or B' point."""
    out: list[str] = []
    for e in exps or []:
        e = _RUBRIC.sub("", str(e).strip()).strip(" .'\"")
        if e and e.lower() not in (x.lower() for x in out):
            out.append(e[:120])
    if question and len(out) > 1 and not _MANY.search(question):
        return [" or ".join(out)[:240]]
    return out[:k]


def make_probes(concepts: list[Concept], n: int = PROBES, call=None) -> list[dict]:
    from . import planner as P
    call = call or P._call
    listing = "\n".join(f"{c.id}: {c.unit} · {c.name} · {'; '.join(c.points)}" for c in concepts[:40])
    try:
        d = call(P.STYLE.format(name=P._name()), PROBES_PROMPT.format(n=n + 2, concepts=listing), PROBES_SCHEMA,
                 "probes", 700, route="tutor_answer", reasoning="low", patience_s=10)
    except Exception as e:
        print(f"   [coach] probes: {type(e).__name__}: {str(e)[:100]}")
        return []
    byid = {c.id: c for c in concepts}
    out, seen = [], set()
    for p in d.get("probes") or []:
        cid = p.get("concept_id")
        if cid not in byid or cid in seen or not p.get("question"):
            continue
        seen.add(cid)
        out.append({**p, "expected": clean_expectations(p.get("expected"), question=p["question"]) or byid[cid].points[:1]})
    firsts, rest, used = [], [], set()                # spread over the units: one per unit first
    for p in out:
        u = byid[p["concept_id"]].unit_idx
        (rest if u in used else firsts).append(p)
        used.add(u)
    return (firsts + rest)[:n]


# ------------------------------------------------------------------------------------------------ focus
def _words(t: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", (t or "").lower())


def matches(want: str, c: Concept) -> bool:
    """'SDD' ↔ 'Syntax Directed Definitions', 'AST' / 'abstract syntax tree' ↔ 'Abstract Syntax Trees'."""
    w, n = _words(want), _words(c.name)
    if not w or not n:
        return False
    stem = lambda x: x[:-1] if len(x) > 3 and x.endswith("s") else x  # noqa: E731
    initials = "".join(x[0] for x in n if x not in ("and", "of", "the", "a", "in"))
    if len(w) == 1 and len(w[0]) >= 2 and w[0] in (initials, initials.rstrip("s")):
        return True
    ws, ns = {stem(x) for x in w}, {stem(x) for x in n}
    return len(ws & ns) / len(ws) >= 0.6


def focus_split(text: str | None) -> list[str]:
    """'SDD and abstract syntax tree' → ['SDD', 'abstract syntax tree']."""
    return [p.strip() for p in re.split(r",|\band\b|&|\+", text or "") if p.strip()]


# ------------------------------------------------------------------------------------------------ the queue
DAY_RX = re.compile(r"\b((whole|entire|full|complete|all (of )?the|all my) (syllabus|book|course|portion|portions|notes|"
                    r"thing|subject|units?|chapters?)|everything (today|tonight)|in (a|one) day|today itself|"
                    r"by tonight|whole day|all day)\b")
# speech-to-text writes "4 hours" or "four hours"; "ah" / "a h" must never read as an hour (words need a space)
_NUM_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
              "ten": 10, "eleven": 11, "twelve": 12, "an": 1, "a": 1, "a couple of": 2, "a few": 3, "some": 3}
HOURS_RX = re.compile(r"\b(?:(\d{1,2}(?:\.\d)?)\s*|(" + "|".join(sorted(_NUM_WORDS, key=len, reverse=True))
                      + r")\s+)(and a half\s+)?(?:hours?|hrs?|h)\b( and a half)?")
DAY_DEFAULT_H = 6.0       # "the whole syllabus today" with no hours said
BREAK_EVERY_MIN = 45      # day mode: a 5-minute break about this often (he says "continue" to come back)
BREAK_MIN = 5
DAY_RESUME_H = 14         # day mode: what he did in the last 14 h counts as "done today" when he comes back
EXAM_RX = re.compile(r"\b(exams?|tests?|viva|quiz|paper|mid ?sem|end ?sem|finals?|interview)\b")


def _hours(t: str) -> float | None:
    """'in 4 hours' → 4 · 'four and a half hours' → 4.5 · 'an hour and a half' → 1.5 · none → None (0.5–14)."""
    m = HOURS_RX.search(t)
    if not m:
        return None
    h = float(m.group(1)) if m.group(1) else float(_NUM_WORDS[m.group(2)])
    h += 0.5 if (m.group(3) or m.group(4)) else 0
    return min(14.0, max(0.5, h))


def parse_goal(text: str) -> dict:
    """'exam tomorrow' → {mode: exam, days: 1}; 'just want to understand it' → {mode: learn};
    'teach me the whole syllabus today (in 6 hours)' / 'cover it in 4 hours' → {mode: day, hours: 6 / 4}."""
    t = (text or "").lower()
    hours = _hours(t)
    exam = bool(EXAM_RX.search(t))
    if DAY_RX.search(t) or (hours is not None and not exam):    # his whole syllabus, or a few hours he has today
        return {"mode": "day", "days": 0, "hours": hours or DAY_DEFAULT_H, "hours_said": hours is not None}
    days = None
    if re.search(r"\b(today|tonight)\b", t) or hours is not None:
        days = 0
    elif re.search(r"\btomorrow\b", t):
        days = 1
    else:
        try:
            from ..fastpath import dates
            hits = dates.find_days(text, loose=True)
            if hits:
                days = max(0, (hits[0].day - dates.now().date()).days)
        except Exception:
            pass
    if days is not None and not exam and re.search(r"\b(on|by|before|in \d+ days?)\b", t):
        exam = True
    out = {"mode": "exam" if exam else "learn", "days": days}
    if hours is not None:                            # "exam in 3 hours": the plan must fit in them
        out["hours"] = hours
    return out


def goal_from_flags(args: list[str]) -> dict | None:
    """`--goal-mode learn|exam|day [--days N] [--hours H]` (the web Lessons page) → the same goal dict parse_goal
    gives, so the coach skips the spoken goal question. None when no (valid) --goal-mode is given."""
    def val(flag):
        return args[args.index(flag) + 1] if flag in args and args.index(flag) + 1 < len(args) else None
    mode = val("--goal-mode")
    try:
        if mode == "day":                            # hours_said: the plan line only says "your N hours" if he chose N
            return {"mode": "day", "days": 0, "hours": max(1.0, min(12.0, float(val("--hours") or DAY_DEFAULT_H))),
                    "hours_said": val("--hours") is not None}
        if mode == "exam":
            return {"mode": "exam", "days": max(0, min(365, int(val("--days") or 1)))}
    except ValueError:
        return None
    return {"mode": "learn", "days": None} if mode == "learn" else None


def order(concepts: list[Concept], m: Mastery, mode: str, minutes: float) -> list[Concept]:
    """The teaching queue. Learn: book order, skipping what he knows. Exam (Metcalfe & Kornell): nearly-known first,
    then new ones by exam weight, known ones last as one quick check each — all within the time budget."""
    def lvl(c):
        return m.level(c.id)
    if mode == "day":                                # the whole syllabus: new + shaky by importance, known as checks
        q = sorted([c for c in concepts if lvl(c) != "known"], key=lambda c: (-c.weight, c.unit_idx)) + \
            [c for c in concepts if lvl(c) == "known"]
    elif mode == "exam":
        shaky = [c for c in concepts if lvl(c) == "shaky"]
        new = sorted([c for c in concepts if lvl(c) == "new"], key=lambda c: (-c.weight, c.unit_idx))
        known = [c for c in concepts if lvl(c) == "known"]
        q = shaky + new + known
    else:
        q = [c for c in concepts if lvl(c) != "known"] + [c for c in concepts if lvl(c) == "known"][:2]
    out, spent = [], 0.0
    for c in q:
        cost = CONCEPT_MIN[lvl(c)]
        if spent + cost > minutes and out:
            continue
        out.append(c)
        spent += cost
    if mode in ("exam", "day"):                      # teach in book order within what fits (easier to follow)
        out.sort(key=lambda c: (c.unit_idx, concepts.index(c)))
    return out


# ------------------------------------------------------------------------------------------------ concept → steps
_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(“‘])")


def two_sentences(items) -> list[str]:
    """≤ 2 spoken sentences per step, even when the model packs four into one 'say' item."""
    out: list[str] = []
    for it in items or []:
        if isinstance(it, str):
            out += [x.strip() for x in _SENT_SPLIT.split(it.strip()) if x.strip()]
    return out[:2]


def _same_point(a: str, b: str) -> bool:
    """'Derivative of u·v = u'v + uv'' ≈ 'Derivative of u·v equals u'v + uv'' (most content words shared)."""
    stem = lambda x: x[:-1] if len(x) > 3 and x.endswith("s") else x  # noqa: E731
    wa = {stem(w) for w in _words(a) if len(w) > 2 or w.isdigit()}
    wb = {stem(w) for w in _words(b) if len(w) > 2 or w.isdigit()}
    return bool(wa and wb) and len(wa & wb) / min(len(wa), len(wb)) >= 0.6


def _step_board(st: dict) -> list[dict]:
    """A step's board notes as slot items: the separate points / figure / example fields (a weak model fills a
    named field far more reliably than 'one of the items must have slot figure'), plus any older-form board list."""
    items = [it for it in st.get("board") or [] if isinstance(it, dict)]
    none = {"nodes": None, "edges": None, "rows": None}
    items += [{"slot": "point", "kind": "text", "text": str(p), **none} for p in st.get("points") or [] if p]
    fig = st.get("figure")
    if isinstance(fig, dict) and (fig.get("text") or fig.get("nodes") or fig.get("rows")):
        items.append({**none, **fig, "slot": "figure"})
    items += [{"slot": "example", "kind": "text", "text": str(x), **none} for x in (st.get("example") or [])[:6] if x]
    return items


def _board_ops(items: list[dict]) -> list[Op]:
    ops = []
    for it in items or []:
        slot, kind, text = it.get("slot"), it.get("kind") or "text", (it.get("text") or "").strip()
        if slot == "point" and text:
            ops.append(Op(type="text", text=_cut(text, 80), region="points", at="start"))
        elif slot == "example" and text:
            ops.append(Op(type="text", text=_cut(text, 60), region="example", at="start"))
        elif slot == "figure":
            if kind == "graph" and it.get("nodes"):
                nodes = [{"id": str(n["id"])[:16], "text": _cut(str(n["text"]), 24), "shape": "rectangle", "style": None}
                         for n in it["nodes"][:5] if n.get("id")]
                ids = {n["id"] for n in nodes}
                edges = [{"from": e["from"], "to": e["to"], "text": (e.get("text") or None)}
                         for e in it.get("edges") or [] if e.get("from") in ids and e.get("to") in ids][:6]
                if nodes:
                    ops.append(Op(type="graph", region="figure", nodes=nodes, edges=edges, direction="LR",
                                  at="start"))
            elif kind == "table" and it.get("rows"):
                ops.append(Op(type="table", region="figure", rows=[[_cut(str(c), 20) for c in r][:4] for r in it["rows"][:4]],
                              at="start"))
            elif kind == "formula" and text:
                ops.append(Op(type="formula", region="figure", text=text[:60], at="start"))
            elif text:
                ops.append(Op(type="box", region="figure", text=_cut(text, 30), style="blue", at="start"))
    return ops


def concept_segments(c: Concept, idx, level: str, mode: str, sources: list[dict] | None,
                     total: int, call=None, again: bool = False) -> list[Segment]:
    """One concept → short steps (≤ 2 sentences + his turn), on its own notes page, then the Remember box.
    again=True: he still got it wrong after the first pass — a different angle and a new example (one step)."""
    from . import planner as P
    from .lesson import sanitize_check
    call = call or P._call
    page = Op(type="new_page", text=(f"{c.name} — again" if again else c.name)[:48])
    if level == "known":                             # one quick check, no re-teaching (Kalyuga)
        # ask without giving the answer away in the question (the old "<fact>. Why?" let an echo pass)
        chk = Check(kind="recall", prompt=f"Quick one: in a sentence, what do you know about {c.name}?",
                    expectations=c.points[:1] or [c.name], hints=c.points[1:2],
                    reveal=(c.points[0] if c.points else ""))
        return [Segment(id=f"k{idx}s0", type="teach", title=c.name,
                        cues=[Cue(id=f"k{idx}s0c1", say=f"You seem to know {c.name}. Quick check.", ops=[page])],
                        check=chk)]
    steps = 1 if level == "shaky" or again else 2
    level_line = {"new": "has not learned this yet", "shaky": "knows part of it; fix the tricky part"}[level]
    if again:
        level_line = ("got it wrong even after one explanation: explain it from a DIFFERENT angle with a NEW, very "
                      "concrete example; simpler words")
    mode_line = "exam soon: focus on what exams ask" if mode == "exam" else "wants real understanding"
    d = call(P.STYLE.format(name=P._name()),
             STEP_PROMPT.format(name=c.name, unit=c.unit, points="; ".join(c.points), level_line=level_line,
                                mode_line=mode_line, steps=steps,
                                sources=P._sources_block(sources, 3500) if sources else "",
                                facts_rule=FACTS_FROM_SOURCES if sources else FACTS_GENERAL),
             STEP_SCHEMA, "concept", 1600, route="tutor_plan", reasoning="low", patience_s=30)
    segs: list[Segment] = []
    raw = [st for st in (d.get("steps") or []) if isinstance(st, dict)][:steps]
    boards = [_step_board(st) for st in raw]
    if boards and not any(it.get("slot") == "figure" for it in boards[0]):
        for b in boards[1:]:                         # step 1 always shows a figure: borrow a later step's
            fig = next((it for it in b if it.get("slot") == "figure"), None)
            if fig:
                b.remove(fig)
                boards[0].append(fig)
                break
    n_points = sum(1 for b in boards for it in b if it.get("slot") == "point" and (it.get("text") or "").strip())
    for j, st in enumerate(raw):
        says = two_sentences(st.get("say"))
        if not says:
            continue
        ops = _board_ops(boards[j])
        if j == 0 and n_points < 2:                  # too few key points from the model: the concept map has them
            given = [o.text or "" for o in ops if o.region == "points"]
            extra = []
            for pt in c.points:
                if len(given) + len(extra) < 3 and not any(_same_point(pt, g) for g in given + extra):
                    extra.append(pt)
            ops = ops + [Op(type="text", text=_cut(pt, 80), region="points", at="start") for pt in extra]
        first = [page] if j == 0 else []
        pts = [o for o in ops if o.region == "points"]
        rest = [o for o in ops if o.region != "points"]
        cues = [Cue(id=f"k{idx}s{j}c1", say=says[0], ops=first + pts + (rest if len(says) == 1 else []))]
        if len(says) > 1:
            cues.append(Cue(id=f"k{idx}s{j}c2", say=says[1], ops=rest))
        chk = sanitize_check(st.get("check"))
        if chk:
            chk.expectations = clean_expectations(chk.expectations, question=chk.prompt) or ([chk.reveal] if chk.reveal else [])
        segs.append(Segment(id=f"k{idx}s{j}", type="teach" if j == 0 else "worked_example", title=c.name,
                            cues=cues, check=chk))
    rem = _cut(str(d.get("remember") or ""), 90)
    if segs and rem:
        segs.append(Segment(id=f"k{idx}r", type="teach", title=c.name, cues=[
            Cue(id=f"k{idx}rc1", say=f"So, remember: {rem}",
                ops=[Op(type="text", text=rem, region="remember", at="start")])]))
    return segs


# ------------------------------------------------------------------------------------------------ the session
class Coach:
    def __init__(self, source: str, *, audio, events, server=None, book_path: str | None = None,
                 unit: str | None = None, goal: dict | None = None, log=print, call=None, persist: bool = True,
                 planner=None, concepts_future=None, focus: list[str] | None = None, **tutor_kw):
        from .player import Tutor
        self.source, self.book_path, self.unit = source, book_path, unit
        self.goal, self.log, self.call = goal, log, call
        title = Path(book_path).stem if book_path else source
        self.L = Lesson(title=title[:80], topic=source[:120], segments=[],
                        source={"kind": "book", "path": book_path, "section": unit or "all"} if book_path
                        else {"kind": "topic"})
        self.L.complete = False                      # type: ignore[attr-defined]   (filled while he works)
        self.mastery = Mastery(source + (f"#{unit}" if unit else ""))
        from . import answerer
        self.t = Tutor(self.L, audio=audio, events=events, server=server, planner=planner or answerer(), log=log,
                       persist=persist, **tutor_kw)
        self.t.on_check = self._on_check
        self.concepts: list[Concept] = []
        self.queue: list[Concept] = []
        self.seg_concept: dict[str, str] = {}
        self._map_err: Exception | None = None
        self._sources: dict[str, list[dict]] = {}
        self.after_probes: dict[str, float] = {}
        self._future = concepts_future               # D42: the map started while her voice was still loading
        self.focus = focus or []                     # "teach me SDD and AST": only these concepts
        # the subject in plain words (any subject: "The Compiler Notebook" → "Compiler", "photosynthesis" → itself),
        # for the picture search and the ear — nothing in the engine is about one subject
        self.subject = " ".join(w for w in re.findall(r"[A-Za-z][A-Za-z0-9+#-]*", title)
                                if w.lower() not in {"the", "notebook", "notes", "book", "my", "a", "an", "of", "for",
                                                     "and", "final", "draft", "pdf", "html", "unit", "chapter"})[:60]
        self.pictures = os.getenv("STITI_TUTOR_PICTURES", "on") != "off"
        self.t.before_end = self._before_end
        self.revisited: set[str] = set()
        self.checked: set[str] = set()               # concepts he answered something on this session
        self._recapped = False
        self.returning = False
        self.notes_path: Path | None = None
        self.t0 = time.time()
        self.done_today: set[str] = set()            # day mode: concepts already done earlier today
        self.pool_n = 0                              # how many concepts the queue was chosen from

    # ---- mastery after every answer; a concept he clearly knows is cut short
    def _on_check(self, seg: Segment, rec: dict) -> None:
        cid = self.seg_concept.get(seg.id)
        if not cid or rec.get("verdict") not in ("correct", "partial", "wrong", "idk"):
            return
        p = self.mastery.update(cid, rec["verdict"])
        self.checked.add(cid)
        self.log(f"   [mastery] {cid} {rec['verdict']} → {p:.2f}")
        if rec["verdict"] == "correct" and p >= KNOWN and rec.get("attempts", 1) <= 1:
            nxt = [s.id for s in self.L.segments]
            i = nxt.index(seg.id) if seg.id in nxt else -1
            rest = [s for s in self.L.segments[i + 1:] if self.seg_concept.get(s.id) == cid and not s.id.endswith("r")]
            if rest:                                  # skip his remaining steps of this concept, keep "Remember"
                after = rest[-1].id
                k = next((kk for kk, (si, _) in enumerate(self.t._flat()) if self.L.segments[si].id == after), None)
                if k is not None:
                    self.t.say("You've got this one. Moving on.")
                    self.t.skip_to = k + len(rest[-1].cues)

    # ---- the end of the plan: come back to what's still wrong (spacing), then a recap + his notes saved
    def _before_end(self) -> bool:
        byid = {c.id: c for c in self.concepts}
        weak = [byid[cid] for cid in self.checked
                if cid in byid and cid not in self.revisited and self.mastery.level(cid) == "new"][:2]
        if weak and not self.t.ended:
            names = " and ".join(c.name for c in weak)
            self.t.say(f"Before we finish, let's come back to {names}, from another angle.", interruptible=False)
            added = False
            for c in weak:
                self.revisited.add(c.id)
                try:
                    segs = concept_segments(c, f"{self.queue.index(c) if c in self.queue else 0}v", "shaky",
                                            self.goal["mode"], self._concept_sources(c), len(self.queue),
                                            call=self.call, again=True)
                except Exception as e:
                    self.log(f"   [coach] again {c.name}: {type(e).__name__}: {str(e)[:100]}")
                    continue
                for sg in segs:
                    self.seg_concept[sg.id] = c.id
                self.L.segments.extend(segs)
                added = added or bool(segs)
            if added:
                return True
        if self._recapped:
            return False
        self._recapped = True
        self._recap()
        return True

    def _recap(self) -> None:
        """A 'Today' page (✓ solid · ~ revise) said in one line, and his notes written to a markdown file."""
        byid = {c.id: c for c in self.concepts}
        taught = [byid[c.id] for c in self.queue if c.id in byid]
        solid = [c for c in taught if self.mastery.level(c.id) == "known"]
        weak = [c for c in taught if self.mastery.level(c.id) != "known"]
        day = (self.goal or {}).get("mode") == "day"
        done = len(self._done_today()) if day else 0    # the whole day, this session and the ones before
        ops = [Op(type="new_page", text=f"Today · {done} of {len(self.concepts)} done" if day else "Today")]
        ops += [Op(type="text", text=f"✓ {c.name}", region="points") for c in solid[:6]]
        ops += [Op(type="text", text=f"~ {c.name}", region="points") for c in weak[:6]]
        self.notes_path = self.save_notes()
        if self.notes_path:
            ops.append(Op(type="text", text=f"Notes saved: {self.notes_path.name}", region="remember"))
        line = "That's it for today."
        if day:
            line += f" Today so far: {done} of {len(self.concepts)} topics done."
        if solid:
            line += f" Solid now: {', '.join(c.name for c in solid[:3])}."
        if weak:
            line += f" To revise: {', '.join(c.name for c in weak[:3])}. I'll ask you those first next time."
        self.L.segments.append(Segment(id="recap", type="teach", title="Today", cues=[Cue(id="recapc1", say=line,
                                                                                            ops=ops)]))

    def save_notes(self) -> Path | None:
        """His notes as plain markdown (principle 7: memory he can read): per concept the key points, the example,
        the Remember line; then his doubts. ~/.stiti/tutor/notes/<title>.md"""
        try:
            from ..config import CFG
            lines = [f"# {self.L.title} — notes", f"_{time.strftime('%d %b %Y')} · mode: {self.goal.get('mode')}_", ""]
            cur = None
            for sg in self.L.segments:
                if sg.id == "recap" or sg.type == "break":  # a break page is not part of his notes
                    continue
                if sg.title != cur:
                    cur = sg.title
                    lv = self.mastery.level(self.seg_concept.get(sg.id, ""))
                    lines += ["", f"## {cur}" + {"known": " ✓", "shaky": " ~", "new": ""}.get(lv, "")]
                for cue in sg.cues:
                    for o in cue.ops:
                        if o.region == "points" and o.text:
                            lines.append(f"- {o.text}")
                        elif o.region == "example" and o.text:
                            lines.append(f"  - e.g. {o.text}")
                        elif o.region == "remember" and o.text:
                            lines.append(f"> **Remember:** {o.text}")
                        elif o.type == "graph" and o.edges:
                            nm = {n["id"]: n["text"] for n in o.nodes or []}
                            lines.append("  - " + "; ".join(f"{nm.get(e['from'], e['from'])} →"
                                                             f"{(' ' + e['text'] + ' →') if e.get('text') else ''} "
                                                             f"{nm.get(e['to'], e['to'])}" for e in o.edges))
                        elif o.type == "table" and o.rows:
                            lines.append("  - " + " | ".join(o.rows[0]))
                            lines += ["    " + " | ".join(r) for r in o.rows[1:]]
                        elif o.type == "formula" and o.text:
                            lines.append(f"  - `{o.text}`")
            if self.t.questions:
                lines += ["", "## Your doubts"] + [f"- {q}" for q in dict.fromkeys(self.t.questions)]
            path = CFG.home / "tutor" / "notes" / f"{re.sub(r'[^A-Za-z0-9]+', '-', self.L.title).strip('-')[:60]}.md"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("\n".join(lines).strip() + "\n")
            return path
        except Exception as e:
            self.log(f"   [coach] notes: {type(e).__name__}: {e}")
            return None

    def _build_map(self):
        try:
            if self._future is not None:
                self.concepts = self._future.result(timeout=180)
            else:
                self.concepts = concept_map(self.source, book_path=self.book_path, unit=self.unit, call=self.call)
        except Exception as e:
            self._map_err = e

    def _concept_sources(self, c: Concept) -> list[dict] | None:
        if not self.book_path or c.general:          # a syllabus only lists topics: teach from general knowledge
            return None
        if c.unit not in self._sources:
            try:
                from . import book as B
                b = B.load(self.book_path)
                sec = next((s for s in (b.chapters() or b.sections) if s.name[:60] == c.unit), None)
                self._sources[c.unit] = B.sources_for(b, sec, n=25) if sec else []
            except Exception:
                self._sources[c.unit] = []
        return self._sources[c.unit]

    def _writer(self):
        """Write each concept's steps while he works on the previous one (first one ready in seconds)."""
        since_break = 0.0
        for i, c in enumerate(self.queue):
            if self.t.ended:
                break
            lvl = self.mastery.level(c.id)
            if self.goal["mode"] == "day" and since_break >= BREAK_EVERY_MIN and i:
                since_break = 0.0                    # a real break: she stops and waits for "continue"
                done, total = len(self.done_today) + i, len(self.concepts)      # progress across the day
                self.L.segments.append(Segment(id=f"brk{i}", type="break", title="Break", cues=[Cue(
                    id=f"brk{i}c1", say=f"Break time, {BREAK_MIN} minutes. {done} of {total} topics done today. "
                                        "Stand up, drink some water, look away from the screen.",
                    ops=[Op(type="new_page", text=f"Break · {BREAK_MIN} min"),
                         Op(type="text", text=f"✓ {done} of {total} topics done today", region="points"),
                         Op(type="text", text="Stand up · water · look far away", region="points"),
                         Op(type="text", text=f"Next: {c.name}", region="remember")])]))
            since_break += CONCEPT_MIN[lvl]
            pic = None
            if self.pictures and lvl != "known":         # the best real picture, looked up while the steps are written
                from concurrent.futures import ThreadPoolExecutor
                from .pictures import picture_op
                pic = ThreadPoolExecutor(1).submit(picture_op, c.name, context=self.subject)
            try:
                segs = concept_segments(c, i, lvl, self.goal["mode"], self._concept_sources(c), len(self.queue),
                                        call=self.call)
            except Exception as e:
                self.log(f"   [coach] {c.name}: {type(e).__name__}: {str(e)[:100]}")
                continue
            if pic is not None and segs:
                try:
                    op = pic.result(timeout=8)
                except Exception:
                    op = None
                if op is not None:                       # top of the figure slot; the drawn diagram follows below
                    ops = segs[0].cues[0].ops
                    at = next((k for k, o in enumerate(ops) if o.region == "figure"), len(ops))
                    ops.insert(at, op)
                    self.log(f"   [coach] picture for {c.name}: {op.text}")
            for s in segs:
                self.seg_concept[s.id] = c.id
            self.L.segments.extend(segs)
        self.L.complete = True                        # type: ignore[attr-defined]

    def opening(self) -> bool:
        """Goal + deadline, then quick probes. False = he ended it."""
        t = self.t
        self.t0 = time.time()
        mapper = threading.Thread(target=self._build_map, daemon=True)
        mapper.start()
        # bias the ear to the goal words + HIS subject (his topic, or his book's title words: never compiler words
        # for every subject)
        t.ears_on(["exam", "tomorrow", "syllabus", "unit", "chapter", "test"] + self.focus + self.subject.split()[:6])
        t.status("playing", "starting")
        asked = self.goal is None
        if asked:
            ans = t.listen("Hi! Before I start: what do you need? Is this for an exam, and when is it?")
            if ans is None:
                return False
            self.goal = parse_goal(ans)
        day = self.goal["mode"] == "day"
        if day:
            mins = (self.goal.get("hours") or DAY_DEFAULT_H) * 60 * 0.85    # minus breaks
        else:
            days = self.goal.get("days")                # 0 = today: an exam today is ≤ 1 day too
            mins = EXAM_MINUTES if self.goal["mode"] == "exam" and (9 if days is None else days) <= 1 else LEARN_MINUTES
            if self.goal.get("hours"):                  # "exam in 2 hours": never plan more than he has
                mins = min(mins, self.goal["hours"] * 60 * 0.85)
        self.goal["minutes"] = mins
        mapper.join(0.1)
        if mapper.is_alive():
            t.say(f"{'Got it.' if asked else 'Okay.'} Give me a few seconds, I'm reading your notes." if self.book_path
                  else f"{'Got it.' if asked else 'Okay.'} Give me a few seconds to plan this.", interruptible=False)
            mapper.join(120)
        if not self.concepts:
            t.say("Sorry, I couldn't read that properly just now. Try again in a minute.")
            return False
        if self.focus:
            sel = [c for c in self.concepts if any(matches(f, c) for f in self.focus)]
            if sel:
                self.concepts = sel
                self.log(f"   [coach] focus {self.focus} → {[c.name for c in sel]}")
            else:
                t.say(f"I couldn't find {' and '.join(self.focus)} in your notes, so I'll plan the whole thing.",
                      interruptible=False)
        t.extra_words = [c.name for c in self.concepts][:12]
        t.ears_on(t.extra_words)                     # his file's concept names bias the ear for the probes
        recent = [c for c in self.concepts if time.time() - self.mastery.seen.get(c.id, 0) < 21 * 86400]
        self.returning = len(recent) >= 3
        if day:                                      # stopped and came back today: what he did BEFORE this session
            self.done_today = self._done_today(before=self.t0)    # (not the probes about to be asked now)
        probes = [] if self.returning else make_probes(self.concepts, n=min(PROBES, max(1, len(self.concepts))),
                                                         call=self.call)
        if self.returning and not self.done_today:
            solid = sum(self.mastery.level(c.id) == "known" for c in self.concepts)
            t.say(f"Welcome back. You're solid on {solid} of {len(self.concepts)} topics here, so I'll pick up "
                  "from what's left.", interruptible=False)
        if probes:
            t.say(f"{'Exam mode. ' if self.goal['mode'] == 'exam' else ''}{len(probes)} quick questions first, so I "
                  "don't teach you what you already know. Short answers are fine, or say I don't know.",
                  interruptible=False)
        from .grade import grade
        byid = {c.id: c for c in self.concepts}
        for k, pr in enumerate(probes):
            ans = t.listen(pr["question"], check_box={"kind_label": f"Question {k + 1} of {len(probes)}",
                                                      "prompt": pr["question"], "options": []})
            if ans is None:
                return False
            if re.search(r"\b(skip|just (start|teach)|start (now|teaching)|no questions)\b", ans, re.I):
                break
            v = grade(Check(kind="recall", prompt=pr["question"], expectations=pr.get("expected") or []), ans,
                      llm=True, call=self.call)["verdict"]     # mis-heard right answers get a free-LLM second opinion
            c = byid[pr["concept_id"]]
            self.mastery.set(c.id, {"correct": 0.85, "partial": 0.55}.get(v, 0.15))
            if v == "correct":                       # what comes before it in the same unit is probably known too
                for o in self.concepts:
                    if o.unit_idx == c.unit_idx and self.concepts.index(o) < self.concepts.index(c):
                        self.mastery.set(o.id, max(self.mastery.get(o.id), 0.6))
            t.say({"correct": "Nice, you know that.", "partial": "Partly there."}.get(v, "Okay, we'll cover that."),
                  interruptible=False)
        self.after_probes = dict(self.mastery.p)     # where he started (reports, tests)
        pool = self.concepts
        if self.done_today:                          # day mode, same day: carry on with what's left
            rest = [c for c in pool if c.id not in self.done_today]
            n, total = len(self.done_today), len(pool)
            if rest:
                pool = rest
                t.say(f"{'Welcome back. ' if self.returning else ''}{n} of {total} topic{'s' if total != 1 else ''} "
                      f"done today already. Let's do the other {len(rest)}.", interruptible=False)
            else:
                t.say(f"{'Welcome back. ' if self.returning else ''}You've covered all {total} topics today "
                      "already, so this is a quick revision round.", interruptible=False)
        self.pool_n = len(pool)
        self.queue = order(pool, self.mastery, self.goal["mode"], mins)
        self._show_plan()
        return True

    def _done_today(self, before: float | None = None) -> set[str]:
        """Day mode: the concepts he got at least partly right in the last DAY_RESUME_H hours (before `before`)."""
        now = before or time.time()
        return {c.id for c in self.concepts
                if 0 <= now - self.mastery.seen.get(c.id, 0) < DAY_RESUME_H * 3600
                and self.mastery.level(c.id) != "new"}

    def _show_plan(self):
        t, q = self.t, self.queue
        if not q:
            return
        exam = self.goal["mode"] == "exam"
        day = self.goal["mode"] == "day"
        title = "Your plan"
        if day and self.done_today:                  # progress across the day: what's done before this session
            title += f" · {len(self.done_today)} of {len(self.concepts)} done today"
        acts = t.board.apply(Op(type="new_page", text=title))
        for c in q[:10]:
            mark = {"known": "✓ ", "shaky": "~ ", "new": ""}[self.mastery.level(c.id)]
            acts += t.board.apply(Op(type="text", text=f"{mark}{c.name}", region="points"))
        if len(q) > 10:
            acts += t.board.apply(Op(type="text", text=f"… and {len(q) - 10} more", region="points"))
        acts += t.board.apply(Op(type="text", text="✓ check only · ~ fix the gaps · others: teach",
                                 region="remember"))
        t.send({"type": "actions", "actions": [{**a, "at_ms": i * 120} for i, a in enumerate(acts)]})
        first = q[0].name
        n = len(q)
        topics = f"{n} topic{'s' if n != 1 else ''}"
        if day:
            est, since, n_brk = 0.0, 0.0, 0         # the same break rule as _writer
            for k, c in enumerate(q):
                if since >= BREAK_EVERY_MIN and k:
                    n_brk, since = n_brk + 1, 0.0
                since += CONCEPT_MIN[self.mastery.level(c.id)]
                est += CONCEPT_MIN[self.mastery.level(c.id)]
            est += n_brk * BREAK_MIN
            def hours(h):
                return f"{h:g} hour{'' if h == 1 else 's'}"
            dur = f"{max(5, round(est / 5) * 5):.0f} minutes" if est < 60 else f"{hours(round(est / 30) / 2)}"
            dur += " with short breaks" if n_brk else ""
            hrs = self.goal.get("hours") or DAY_DEFAULT_H
            said = self.goal.get("hours_said", True)
            if n < (self.pool_n or n):               # it doesn't all fit: say so, and what she chose
                who = f"your {hours(hrs)} fit{'s' if hrs == 1 else ''}" if said else "one day fits"
                body = f"{who} the {n} most important of {self.pool_n} topics, about {dur}"
            else:
                body = f"{topics}, about {dur}" + (f", inside your {hours(hrs)}" if said else "")
        else:
            body = topics + (", most important first for your exam" if exam else "")
        t.say(f"Here's the plan: {body}, starting with {first}. Stop me any time with a doubt.", interruptible=False)

    def run(self) -> dict:
        if not self.opening():
            self.t.ended = True
            return self.t._finish()
        threading.Thread(target=self._writer, daemon=True, name="coach-writer").start()
        return self.t.run()
