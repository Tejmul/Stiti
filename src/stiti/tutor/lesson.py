"""Lesson format for the whiteboard tutor (D14/D15).

A lesson = segments; a segment = cues (one spoken sentence each) + an optional check.
Each cue carries semantic board ops (no pixels — layout is done in code, see skills.py).

The same flat, all-nullable op shape is used by hand-written demos and by the LLM planner, so the
LLM can be held to a strict json_schema (Groq + Cerebras strict mode: no oneOf/minItems/pattern).
`sanitize_*` is the code-side guard: unknown op types dropped, labels clipped, caps enforced.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

OP_TYPES = ["title", "text", "bullet", "box", "arrow", "graph", "table", "formula", "sticky",
            "highlight", "strike", "erase", "focus", "new_page", "image_hint"]
SHAPES = ["rectangle", "ellipse", "diamond"]
PLACES = ["auto", "right_of", "left_of", "below", "above", "next_line", "center"]
REGIONS = ["main", "side", "notes", "parking", "goal"]
STYLES = ["plain", "warm", "green", "blue", "red", "violet", "muted",                  # colours
          "underline", "circle", "marker", "tick", "cross", "pointer", "color"]        # highlight kinds
SEGMENT_TYPES = ["warmup", "hook", "organizer", "teach", "worked_example", "contrast", "pulse",
                 "explain_back", "apply", "quiz", "summary", "close", "answer"]
CHECK_KINDS = ["predict", "mcq", "recall", "explain_why", "explain_back", "apply", "discriminate"]
ORIGINS = ["book", "tutor_example", "tutor_bridge", "general_knowledge"]

MAX_OPS_PER_CUE = 5
MAX_LABEL = 32
MAX_TEXT = 120
MAX_GRAPH_NODES = 8
MAX_TABLE = (6, 4)


@dataclass
class Op:
    type: str
    id: str | None = None
    text: str | None = None
    ref: str | None = None
    place: str | None = None
    region: str | None = None
    shape: str | None = None
    style: str | None = None
    at: str | None = None
    direction: str | None = None
    nodes: list[dict] | None = None
    edges: list[dict] | None = None
    rows: list[list[str]] | None = None


@dataclass
class Check:
    kind: str
    prompt: str
    options: list[dict] | None = None          # [{text, correct}]
    expectations: list[str] = field(default_factory=list)
    hints: list[str] = field(default_factory=list)
    reveal: str = ""
    on_correct: str = ""
    confidence: bool = False                    # quiz: ask "1–5, kitna sure?"


@dataclass
class Cue:
    id: str
    say: str
    ops: list[Op] = field(default_factory=list)
    origin: str = "tutor_bridge"
    pages: list[str] | None = None


@dataclass
class Segment:
    id: str
    type: str
    title: str
    cues: list[Cue]
    check: Check | None = None
    minutes: float = 0


@dataclass
class Lesson:
    title: str
    topic: str
    segments: list[Segment]
    source: dict = field(default_factory=lambda: {"kind": "topic"})
    minutes: float = 30
    cards: list[dict] = field(default_factory=list)
    summary: list[str] = field(default_factory=list)

    def cue_list(self) -> list[tuple[int, int]]:
        return [(si, ci) for si, s in enumerate(self.segments) for ci in range(len(s.cues))]

    def words(self) -> int:
        return sum(len(c.say.split()) for s in self.segments for c in s.cues)


# ---------------------------------------------------------------- sanitizers
def _clip(s, n: int) -> str | None:
    if s is None:
        return None
    s = re.sub(r"\s+", " ", str(s)).strip()
    return s[:n] if s else None


def _enum(v, allowed: list[str], default=None):
    return v if v in allowed else default


def sanitize_op(d: dict) -> Op | None:
    t = d.get("type")
    if t not in OP_TYPES:
        return None
    long_text = t in ("text", "sticky", "formula", "bullet", "title")
    op = Op(
        type=t,
        id=_clip(d.get("id"), 24),
        text=_clip(d.get("text"), MAX_TEXT if long_text else MAX_LABEL),
        ref=_clip(d.get("ref"), 60),
        place=_enum(d.get("place"), PLACES, "auto"),
        region=_enum(d.get("region"), REGIONS),
        shape=_enum(d.get("shape"), SHAPES, "rectangle"),
        style=_enum(d.get("style"), STYLES),
        at=_clip(d.get("at"), 40) or "start",
        direction=d.get("direction") if d.get("direction") in ("LR", "TB") else None,
    )
    if t == "graph":
        nodes = [{"id": _clip(n.get("id"), 24), "text": _clip(n.get("text"), MAX_LABEL) or "?",
                  "shape": _enum(n.get("shape"), SHAPES, "rectangle"), "style": _enum(n.get("style"), STYLES)}
                 for n in (d.get("nodes") or []) if isinstance(n, dict) and n.get("id")][:MAX_GRAPH_NODES]
        ids = {n["id"] for n in nodes}
        op.nodes = nodes
        op.edges = [{"from": e.get("from"), "to": e.get("to"), "text": _clip(e.get("text"), 20)}
                    for e in (d.get("edges") or [])
                    if isinstance(e, dict) and e.get("from") in ids and e.get("to") in ids][:12]
        if not nodes:
            return None
    if t == "table":
        rows = [[_clip(c, 24) or "" for c in (r or [])][:MAX_TABLE[1]] for r in (d.get("rows") or [])
                if isinstance(r, list)][:MAX_TABLE[0]]
        if not rows:
            return None
        op.rows = rows
    if t in ("box", "title", "text", "bullet", "formula", "sticky") and not op.text:
        return None
    if t in ("arrow", "highlight", "strike", "erase") and not op.ref:
        return None
    return op


def sanitize_check(d: dict | None) -> Check | None:
    if not d or not d.get("prompt"):
        return None
    opts = [{"text": _clip(o.get("text"), 80) or "", "correct": bool(o.get("correct"))}
            for o in (d.get("options") or []) if isinstance(o, dict) and o.get("text")][:4] or None
    if opts and not any(o["correct"] for o in opts):
        opts = None
    return Check(kind=_enum(d.get("kind"), CHECK_KINDS, "recall"), prompt=_clip(d["prompt"], 220),
                 options=opts,
                 expectations=[_clip(e, 120) for e in (d.get("expectations") or []) if e][:3],
                 hints=[_clip(h, 160) for h in (d.get("hints") or []) if h][:2],
                 reveal=_clip(d.get("reveal"), 300) or "", on_correct=_clip(d.get("on_correct"), 160) or "",
                 confidence=bool(d.get("confidence")))


def sanitize_segment(d: dict, idx: int) -> Segment | None:
    sid = _clip(d.get("id"), 12) or f"s{idx + 1}"
    cues = []
    for j, c in enumerate(d.get("cues") or []):
        say = _clip((c or {}).get("say"), 240)
        if not say:
            continue
        ops = [o for o in (sanitize_op(x) for x in (c.get("ops") or []) if isinstance(x, dict)) if o]
        cues.append(Cue(id=f"{sid}c{j + 1}", say=say, ops=ops[:MAX_OPS_PER_CUE],
                        origin=_enum(c.get("origin"), ORIGINS, "tutor_bridge"),
                        pages=[str(p) for p in (c.get("pages") or [])][:4] or None))
    if not cues:
        return None
    return Segment(id=sid, type=_enum(d.get("type"), SEGMENT_TYPES, "teach"),
                   title=_clip(d.get("title"), 48) or f"Part {idx + 1}", cues=cues,
                   check=sanitize_check(d.get("check")), minutes=float(d.get("minutes") or 0))


def from_dict(d: dict) -> Lesson:
    segs = [s for s in (sanitize_segment(x, i) for i, x in enumerate(d.get("segments") or [])) if s]
    if not segs:
        raise ValueError("lesson has no playable segments")
    return Lesson(title=_clip(d.get("title"), 80) or "Lesson", topic=_clip(d.get("topic"), 120) or "",
                  segments=segs, source=d.get("source") or {"kind": "topic"},
                  minutes=float(d.get("minutes") or 30),
                  cards=[{"front": _clip(c.get("front"), 160), "back": _clip(c.get("back"), 200),
                          "kind": c.get("kind") or "fact"}
                         for c in (d.get("cards") or []) if c.get("front") and c.get("back")][:8],
                  summary=[_clip(s, 100) for s in (d.get("summary") or []) if s][:3])


def load(path: str | Path) -> Lesson:
    return from_dict(json.loads(Path(path).read_text()))


DEMOS = Path(__file__).parent / "demos"


def demos() -> dict[str, Path]:
    return {p.stem: p for p in sorted(DEMOS.glob("*.json"))}


# ---------------------------------------------------------------- timing
def resolve_at(at: str | None, say: str, audio_ms: int, lead_ms: int = 150) -> int:
    """`at` = "start" | "end" | fraction "0.4" | a word copied from `say` (bookmark).

    Kokoro int8 has no word timings, so a word resolves by its character offset in the sentence
    (proportional) — the same schema works unchanged once a timed TTS model is used.
    """
    end = max(0, audio_ms - 250)
    if not at or at == "start":
        return 0
    if at == "end":
        return end
    try:
        f = float(at)
        if 0 <= f <= 1:
            return int(end * f)
    except ValueError:
        pass
    i = say.lower().find(at.lower())
    if i < 0:
        return 0
    return max(0, int(audio_ms * i / max(1, len(say))) - lead_ms)


# ---------------------------------------------------------------- strict JSON schema for the LLM
def _nullable(t: dict) -> dict:
    return {"anyOf": [t, {"type": "null"}]}


_S = {"type": "string"}
OP_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["type", "id", "text", "ref", "place", "region", "shape", "style", "at", "nodes", "edges", "rows"],
    "properties": {
        "type": {"type": "string", "enum": OP_TYPES},
        "id": _nullable(_S), "text": _nullable(_S), "ref": _nullable(_S),
        "place": _nullable({"type": "string", "enum": PLACES}),
        "region": _nullable({"type": "string", "enum": REGIONS}),
        "shape": _nullable({"type": "string", "enum": SHAPES}),
        "style": _nullable({"type": "string", "enum": STYLES}),
        "at": _nullable(_S),
        "nodes": _nullable({"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["id", "text"],
            "properties": {"id": _S, "text": _S}}}),
        "edges": _nullable({"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["from", "to", "text"],
            "properties": {"from": _S, "to": _S, "text": _nullable(_S)}}}),
        "rows": _nullable({"type": "array", "items": {"type": "array", "items": _S}}),
    },
}
CHECK_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["kind", "prompt", "options", "expectations", "hints", "reveal", "on_correct"],
    "properties": {
        "kind": {"type": "string", "enum": CHECK_KINDS}, "prompt": _S,
        "options": _nullable({"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["text", "correct"],
            "properties": {"text": _S, "correct": {"type": "boolean"}}}}),
        "expectations": {"type": "array", "items": _S}, "hints": {"type": "array", "items": _S},
        "reveal": _S, "on_correct": _S,
    },
}
SEGMENT_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["plan_notes", "id", "type", "title", "cues", "check"],
    "properties": {
        "plan_notes": _S,                       # think first, then format ("Let Me Speak Freely")
        "id": _S, "type": {"type": "string", "enum": SEGMENT_TYPES}, "title": _S,
        "cues": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["say", "origin", "pages", "ops"],
            "properties": {"say": _S, "origin": {"type": "string", "enum": ORIGINS},
                           "pages": _nullable({"type": "array", "items": _S}),
                           "ops": {"type": "array", "items": OP_SCHEMA}}}},
        "check": _nullable(CHECK_SCHEMA),
    },
}
ANSWER_SCHEMA = {   # live Q&A turn: decide first, then words + board ops (Tutor CoPilot ordering)
    "type": "object", "additionalProperties": False,
    "required": ["intent", "strategy", "say", "ops", "pages"],
    "properties": {
        "intent": {"type": "string", "enum": ["clarify", "ahead", "tangent", "challenge", "out_of_scope",
                                              "affect", "chitchat"]},
        "strategy": {"type": "string", "enum": ["direct_explain", "contrast_example", "redraw", "defer",
                                                "park", "offer_choice"]},
        "say": {"type": "array", "items": _S},
        "ops": {"type": "array", "items": OP_SCHEMA},
        "pages": _nullable({"type": "array", "items": _S}),
    },
}
