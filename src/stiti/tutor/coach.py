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


CONCEPTS_PROMPT = """List the key concepts of this unit of the learner's study material, in teaching order.
UNIT: {unit}
{sources}
Return JSON: concepts = 2–{n} items, each: name (≤5 words), points (2–3 short key facts, ≤12 words each, the way an
exam asks them), weight (1–3: how likely an exam asks it). Only what the SOURCES cover; no invented content."""
CONCEPTS_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["concepts"], "properties": {
    "concepts": {"type": "array", "items": {"type": "object", "additionalProperties": False,
                                            "required": ["name", "points", "weight"],
                                            "properties": {"name": _S, "points": {"type": "array", "items": _S},
                                                           "weight": {"type": "integer"}}}}}}

TOPIC_PROMPT = """Plan the concepts a learner needs for: {topic}
Return JSON: concepts = 6–12 items in teaching order, each: unit (a short group name), name (≤5 words), points (2–3
key facts, ≤12 words each), weight (1–3: how central it is)."""
TOPIC_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["concepts"], "properties": {
    "concepts": {"type": "array", "items": {"type": "object", "additionalProperties": False,
                                            "required": ["unit", "name", "points", "weight"],
                                            "properties": {"unit": _S, "name": _S,
                                                           "points": {"type": "array", "items": _S},
                                                           "weight": {"type": "integer"}}}}}}

PROBES_PROMPT = """Write {n} quick diagnostic questions to find out what the learner already knows. Spread them across
the units (early, middle, late). Each must be answerable by voice in one short sentence (a definition, a first step,
or "what happens when…"), not a yes/no. CONCEPTS (id: unit · name · key facts):
{concepts}
Return JSON: probes = items of: concept_id (copied from the list), question (≤20 words), expected (1–2 short
answers a correct reply must contain)."""
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
Return JSON: steps = {steps} item(s). Each step: say = 1–2 spoken sentences (≤22 words each, plain English, a
concrete example before the jargon); board = 1–3 notes for the board, each with slot "point" (a key fact, ≤10
words), "figure" (ONE small diagram: kind graph with ≤5 nodes + edges, or table ≤4 rows, or formula, or box) or
"example" (one worked-example step, ≤8 words); check = one question the learner answers out loud right after
(kind recall / apply / explain_why, or mcq with 3 options); expectations (1–2 points a right answer must contain),
2 hints that don't give it away, reveal (the answer in one sentence). Step 1 explains and MUST draw one "figure"
(e.g. a DFA as a graph of states with labelled edges, a phase pipeline, a small table); a second step is a worked
example with 2–4 "example" items, one per step of the working. remember = the one line to write in the "Remember" box (≤12 words). Facts only from SOURCES if given."""
_BOARD_ITEM = {"type": "object", "additionalProperties": False,
               "required": ["slot", "kind", "text", "nodes", "edges", "rows"],
               "properties": {"slot": {"type": "string", "enum": ["point", "figure", "example"]},
                              "kind": _nullable({"type": "string", "enum": ["text", "graph", "table", "formula", "box"]}),
                              "text": _nullable(_S),
                              "nodes": _nullable({"type": "array", "items": {
                                  "type": "object", "additionalProperties": False, "required": ["id", "text"],
                                  "properties": {"id": _S, "text": _S}}}),
                              "edges": _nullable({"type": "array", "items": {
                                  "type": "object", "additionalProperties": False, "required": ["from", "to", "text"],
                                  "properties": {"from": _S, "to": _S, "text": _nullable(_S)}}}),
                              "rows": _nullable({"type": "array", "items": {"type": "array", "items": _S}})}}
STEP_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["steps", "remember"], "properties": {
    "steps": {"type": "array", "items": {"type": "object", "additionalProperties": False,
                                         "required": ["say", "board", "check"],
                                         "properties": {
                                             "say": {"type": "array", "items": _S},
                                             "board": {"type": "array", "items": _BOARD_ITEM},
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


# ------------------------------------------------------------------------------------------------ concept map
def _cache_path(source: str) -> Path:
    from ..config import CFG
    return CFG.home / "tutor" / "concepts" / f"{key_for(source)}.json"


def concept_map(source: str, *, book_path: str | None = None, unit: str | None = None, call=None) -> list[Concept]:
    """Every concept of his file (one LLM call per unit, two at a time) or of a topic (one call). Cached per file."""
    from . import planner as P
    call = call or P._call
    cache = _cache_path(source + (f"#{unit}" if unit else ""))
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
        results: dict[int, list[dict]] = {}

        def one(i, sec):
            try:
                srcs = B.sources_for(b, sec, n=30)
                d = call(P.STYLE.format(name=P._name()),
                         CONCEPTS_PROMPT.format(unit=sec.name, n=MAX_CONCEPTS_PER_UNIT,
                                                sources=P._sources_block(srcs, 5000)),
                         CONCEPTS_SCHEMA, "concepts", 900, route="tutor_plan", reasoning="low", patience_s=30)
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
            for c in (results.get(i) or [])[:MAX_CONCEPTS_PER_UNIT]:
                if c.get("name"):
                    out.append(Concept(id=f"u{i}c{len(out)}", name=str(c["name"])[:48], unit=sec.name[:60],
                                       points=[str(p)[:90] for p in (c.get("points") or [])][:3],
                                       weight=int(c.get("weight") or 2), unit_idx=i))
    else:
        d = call(P.STYLE.format(name=P._name()), TOPIC_PROMPT.format(topic=source[:200]), TOPIC_SCHEMA,
                 "concepts", 1500, route="tutor_plan", reasoning="low", patience_s=30)
        units: list[str] = []
        for c in d.get("concepts") or []:
            u = str(c.get("unit") or "Basics")[:60]
            if u not in units:
                units.append(u)
            out.append(Concept(id=f"c{len(out)}", name=str(c.get("name") or "?")[:48], unit=u,
                               points=[str(p)[:90] for p in (c.get("points") or [])][:3],
                               weight=int(c.get("weight") or 2), unit_idx=units.index(u)))
    if out:
        try:
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps([asdict(c) for c in out], indent=1))
        except Exception:
            pass
    return out


def make_probes(concepts: list[Concept], n: int = PROBES, call=None) -> list[dict]:
    from . import planner as P
    call = call or P._call
    listing = "\n".join(f"{c.id}: {c.unit} · {c.name} · {'; '.join(c.points)}" for c in concepts[:40])
    try:
        d = call(P.STYLE.format(name=P._name()), PROBES_PROMPT.format(n=n, concepts=listing), PROBES_SCHEMA,
                 "probes", 700, route="tutor_answer", reasoning="low", patience_s=10)
    except Exception as e:
        print(f"   [coach] probes: {type(e).__name__}: {str(e)[:100]}")
        return []
    ids = {c.id for c in concepts}
    return [p for p in d.get("probes") or [] if p.get("concept_id") in ids and p.get("question")][:n]


# ------------------------------------------------------------------------------------------------ the queue
def parse_goal(text: str) -> dict:
    """'exam tomorrow' → {mode: exam, days: 1}; 'just want to understand it' → {mode: learn}."""
    t = (text or "").lower()
    exam = bool(re.search(r"\b(exams?|tests?|viva|quiz|paper|mid ?sem|end ?sem|finals?|interview)\b", t))
    days = None
    if re.search(r"\b(today|tonight|in (a few|some) hours)\b", t):
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
    return {"mode": "exam" if exam else "learn", "days": days}


def order(concepts: list[Concept], m: Mastery, mode: str, minutes: float) -> list[Concept]:
    """The teaching queue. Learn: book order, skipping what he knows. Exam (Metcalfe & Kornell): nearly-known first,
    then new ones by exam weight, known ones last as one quick check each — all within the time budget."""
    def lvl(c):
        return m.level(c.id)
    if mode == "exam":
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
    if mode == "exam":                               # teach in book order within what fits (easier to follow)
        out.sort(key=lambda c: (c.unit_idx, concepts.index(c)))
    return out


# ------------------------------------------------------------------------------------------------ concept → steps
def _board_ops(items: list[dict]) -> list[Op]:
    ops = []
    for it in items or []:
        slot, kind, text = it.get("slot"), it.get("kind") or "text", (it.get("text") or "").strip()
        if slot == "point" and text:
            ops.append(Op(type="text", text=text[:80], region="points", at="start"))
        elif slot == "example" and text:
            ops.append(Op(type="text", text=text[:60], region="example", at="start"))
        elif slot == "figure":
            if kind == "graph" and it.get("nodes"):
                nodes = [{"id": str(n["id"])[:16], "text": str(n["text"])[:24], "shape": "rectangle", "style": None}
                         for n in it["nodes"][:5] if n.get("id")]
                ids = {n["id"] for n in nodes}
                edges = [{"from": e["from"], "to": e["to"], "text": (e.get("text") or None)}
                         for e in it.get("edges") or [] if e.get("from") in ids and e.get("to") in ids][:6]
                if nodes:
                    ops.append(Op(type="graph", region="figure", nodes=nodes, edges=edges, direction="LR",
                                  at="start"))
            elif kind == "table" and it.get("rows"):
                ops.append(Op(type="table", region="figure", rows=[[str(c)[:20] for c in r][:4] for r in it["rows"][:4]],
                              at="start"))
            elif kind == "formula" and text:
                ops.append(Op(type="formula", region="figure", text=text[:60], at="start"))
            elif text:
                ops.append(Op(type="box", region="figure", text=text[:30], style="blue", at="start"))
    return ops


def concept_segments(c: Concept, idx: int, level: str, mode: str, sources: list[dict] | None,
                     total: int, call=None) -> list[Segment]:
    """One concept → short steps (≤ 2 sentences + his turn), on its own notes page, then the Remember box."""
    from . import planner as P
    from .lesson import sanitize_check
    call = call or P._call
    page = Op(type="new_page", text=f"{c.name}"[:48])
    if level == "known":                             # one quick check, no re-teaching (Kalyuga)
        chk = Check(kind="recall", prompt=f"Quick one on {c.name}: {('what is ' + c.name) if not c.points else c.points[0].rstrip('.') + '. Why?'}",
                    expectations=c.points[:2] or [c.name], hints=[], reveal=(c.points[0] if c.points else ""))
        return [Segment(id=f"k{idx}s0", type="teach", title=c.name,
                        cues=[Cue(id=f"k{idx}s0c1", say=f"You seem to know {c.name}. Quick check.", ops=[page])],
                        check=chk)]
    steps = 1 if level == "shaky" else 2
    level_line = {"new": "has not learned this yet", "shaky": "knows part of it; fix the tricky part"}[level]
    mode_line = "exam soon: focus on what exams ask" if mode == "exam" else "wants real understanding"
    d = call(P.STYLE.format(name=P._name()),
             STEP_PROMPT.format(name=c.name, unit=c.unit, points="; ".join(c.points), level_line=level_line,
                                mode_line=mode_line, steps=steps,
                                sources=P._sources_block(sources, 3500) if sources else ""),
             STEP_SCHEMA, "concept", 1600, route="tutor_plan", reasoning="low", patience_s=30)
    segs: list[Segment] = []
    for j, st in enumerate((d.get("steps") or [])[:steps]):
        says = [s.strip() for s in st.get("say") or [] if isinstance(s, str) and s.strip()][:2]
        if not says:
            continue
        ops = _board_ops(st.get("board"))
        first = [page] if j == 0 else []
        pts = [o for o in ops if o.region == "points"]
        rest = [o for o in ops if o.region != "points"]
        cues = [Cue(id=f"k{idx}s{j}c1", say=says[0], ops=first + pts + (rest if len(says) == 1 else []))]
        if len(says) > 1:
            cues.append(Cue(id=f"k{idx}s{j}c2", say=says[1], ops=rest))
        chk = sanitize_check(st.get("check"))
        segs.append(Segment(id=f"k{idx}s{j}", type="teach" if j == 0 else "worked_example", title=c.name,
                            cues=cues, check=chk))
    rem = str(d.get("remember") or "").strip()[:90]
    if segs and rem:
        segs.append(Segment(id=f"k{idx}r", type="teach", title=c.name, cues=[
            Cue(id=f"k{idx}rc1", say=f"So, remember: {rem}",
                ops=[Op(type="text", text=rem, region="remember", at="start")])]))
    return segs


# ------------------------------------------------------------------------------------------------ the session
class Coach:
    def __init__(self, source: str, *, audio, events, server=None, book_path: str | None = None,
                 unit: str | None = None, goal: dict | None = None, log=print, call=None, persist: bool = True,
                 planner=None, concepts_future=None, **tutor_kw):
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

    # ---- mastery after every answer; a concept he clearly knows is cut short
    def _on_check(self, seg: Segment, rec: dict) -> None:
        cid = self.seg_concept.get(seg.id)
        if not cid or rec.get("verdict") not in ("correct", "partial", "wrong", "idk"):
            return
        p = self.mastery.update(cid, rec["verdict"])
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

    def _build_map(self):
        try:
            if self._future is not None:
                self.concepts = self._future.result(timeout=180)
            else:
                self.concepts = concept_map(self.source, book_path=self.book_path, unit=self.unit, call=self.call)
        except Exception as e:
            self._map_err = e

    def _concept_sources(self, c: Concept) -> list[dict] | None:
        if not self.book_path:
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
        for i, c in enumerate(self.queue):
            if self.t.ended:
                break
            lvl = self.mastery.level(c.id)
            try:
                segs = concept_segments(c, i, lvl, self.goal["mode"], self._concept_sources(c), len(self.queue),
                                        call=self.call)
            except Exception as e:
                self.log(f"   [coach] {c.name}: {type(e).__name__}: {str(e)[:100]}")
                continue
            for s in segs:
                self.seg_concept[s.id] = c.id
            self.L.segments.extend(segs)
        self.L.complete = True                        # type: ignore[attr-defined]

    def opening(self) -> bool:
        """Goal + deadline, then quick probes. False = he ended it."""
        t = self.t
        mapper = threading.Thread(target=self._build_map, daemon=True)
        mapper.start()
        t.status("playing", "starting")
        if self.goal is None:
            ans = t.listen("Hi! Before I start: what do you need? Is this for an exam, and when is it?")
            if ans is None:
                return False
            self.goal = parse_goal(ans)
        mins = EXAM_MINUTES if self.goal["mode"] == "exam" and (self.goal.get("days") or 9) <= 1 else LEARN_MINUTES
        self.goal["minutes"] = mins
        mapper.join(0.1)
        if mapper.is_alive():
            t.say("Got it. Give me a few seconds, I'm reading your notes." if self.book_path
                  else "Got it. Give me a few seconds to plan this.", interruptible=False)
            mapper.join(120)
        if not self.concepts:
            t.say("Sorry, I couldn't read that properly just now. Try again in a minute.")
            return False
        probes = make_probes(self.concepts, call=self.call)
        if probes:
            ev = t.say(f"{'Exam mode. ' if self.goal['mode'] == 'exam' else ''}{len(probes)} quick questions first, so I "
                       "don't teach you what you already know. Short answers are fine, or say I don't know.")
            if ev is not None:
                t.events.put(ev)
        from .grade import grade
        byid = {c.id: c for c in self.concepts}
        for k, pr in enumerate(probes):
            ans = t.listen(pr["question"], check_box={"kind_label": f"Question {k + 1} of {len(probes)}",
                                                      "prompt": pr["question"], "options": []})
            if ans is None:
                return False
            if re.search(r"\b(skip|just (start|teach)|start (now|teaching)|no questions)\b", ans, re.I):
                break
            v = grade(Check(kind="recall", prompt=pr["question"], expectations=pr.get("expected") or []), ans)["verdict"]
            c = byid[pr["concept_id"]]
            self.mastery.set(c.id, {"correct": 0.85, "partial": 0.55}.get(v, 0.15))
            if v == "correct":                       # what comes before it in the same unit is probably known too
                for o in self.concepts:
                    if o.unit_idx == c.unit_idx and self.concepts.index(o) < self.concepts.index(c):
                        self.mastery.set(o.id, max(self.mastery.get(o.id), 0.6))
            t.say({"correct": "Nice, you know that.", "partial": "Partly there."}.get(v, "Okay, we'll cover that."),
                  interruptible=False)
        self.after_probes = dict(self.mastery.p)     # where he started (reports, tests)
        self.queue = order(self.concepts, self.mastery, self.goal["mode"], mins)
        self._show_plan()
        return True

    def _show_plan(self):
        t, q = self.t, self.queue
        if not q:
            return
        acts = t.board.apply(Op(type="new_page", text="Your plan"))
        for c in q[:10]:
            mark = {"known": "✓ ", "shaky": "~ ", "new": ""}[self.mastery.level(c.id)]
            acts += t.board.apply(Op(type="text", text=f"{mark}{c.name}", region="points"))
        acts += t.board.apply(Op(type="text", text="✓ check only · ~ fix the gaps · others: teach",
                                 region="remember"))
        t.send({"type": "actions", "actions": [{**a, "at_ms": i * 120} for i, a in enumerate(acts)]})
        first = q[0].name
        n = len(q)
        exam = self.goal["mode"] == "exam"
        t.say(f"Here's the plan: {n} topic{'s' if n != 1 else ''}"
              f"{', most important first for your exam' if exam else ''}, starting with {first}. "
              "Stop me any time with a doubt.", interruptible=False)

    def run(self) -> dict:
        if not self.opening():
            self.t.ended = True
            return self.t._finish()
        threading.Thread(target=self._writer, daemon=True, name="coach-writer").start()
        return self.t.run()
