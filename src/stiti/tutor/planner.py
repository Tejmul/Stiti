"""Lesson planner — the ONLY part of the tutor that needs a cloud LLM (free tiers via router.py).

Code owns the lesson's shape (pedagogy §7.1): warm-up + guess-first hook, a 3-box map, one teaching
segment per big idea, a no-peeking quiz, learner-first wrap-up and revision cards. The LLM only fills
slots, in small strict-JSON calls (constrained decoding on Groq/Cerebras, sanitised in code):
  1 outline call  -> thesis, 3 ideas, hook, key terms, quiz MCQ, cards       (~2–3K tokens)
  3 segment calls -> cues (say + board ops) + one check each                 (~3–4K tokens each)
Segments are written in a background thread while earlier ones play, so the learner never waits
long. Questions during the lesson: one small `answer()` call each. ~15–20K tokens per 15-min lesson.
"""
from __future__ import annotations

import json
import threading

from .. import router
from .lesson import (ANSWER_SCHEMA, SEGMENT_SCHEMA, Check, Cue, Lesson, Op, Segment, sanitize_op,
                     sanitize_segment)

OUTLINE_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["title", "thesis", "hook_prompt", "hook_answer", "key_terms", "ideas", "quiz", "cards", "summary"],
    "properties": {
        "title": {"type": "string"}, "thesis": {"type": "string"},
        "hook_prompt": {"type": "string"}, "hook_answer": {"type": "string"},
        "key_terms": {"type": "array", "items": {"type": "string"}},
        "ideas": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["title", "key_points", "diagram", "pages"],
            "properties": {"title": {"type": "string"}, "key_points": {"type": "array", "items": {"type": "string"}},
                           "diagram": {"type": "string"},
                           "pages": {"anyOf": [{"type": "array", "items": {"type": "string"}}, {"type": "null"}]}}}},
        "quiz": {"type": "object", "additionalProperties": False, "required": ["prompt", "options", "reveal"],
                 "properties": {"prompt": {"type": "string"}, "reveal": {"type": "string"},
                                "options": {"type": "array", "items": {
                                    "type": "object", "additionalProperties": False, "required": ["text", "correct"],
                                    "properties": {"text": {"type": "string"}, "correct": {"type": "boolean"}}}}}},
        "cards": {"type": "array", "items": {"type": "object", "additionalProperties": False,
                                             "required": ["front", "back"],
                                             "properties": {"front": {"type": "string"}, "back": {"type": "string"}}}},
        "summary": {"type": "array", "items": {"type": "string"}},
    },
}

STYLE = """You are Stiti, {name}'s friend who is also a great tutor, teaching by voice on a shared whiteboard.
Speak like a warm, casual Indian friend: mostly simple English, a light touch of Hinglish ("chalo", "achha"),
technical terms in English. Short spoken sentences (max 22 words). No markdown, no emoji."""

OUTLINE_PROMPT = """Plan a {minutes}-minute spoken whiteboard lesson.
TOPIC: {topic}
LEARNER: {learner}
{sources}
Return JSON: title (≤6 words); thesis (one sentence); exactly 3 ideas, each with a short title (≤5 words),
2–4 key_points, one diagram idea (flow / tree / compare table / cycle / formula), and pages (only page labels
that appear in SOURCES, else null); hook_prompt: one "guess first" question about the thesis; hook_answer: the
short true answer; key_terms: 2–4 terms; quiz: one multiple-choice question (3 options, exactly one correct,
wrong options = common misconceptions) + reveal; cards: 5 revision flashcards; summary: 3 lines ≤10 words.
Never invent facts about a book: if SOURCES are given, book claims must come from them."""

SEGMENT_PROMPT = """Write ONE teaching segment of the lesson "{title}" as JSON.
THIS SEGMENT'S IDEA: {idea}
WHOLE LESSON: thesis "{thesis}"; ideas: {ideas}. Earlier segments already taught: {done}.
LEARNER: {learner}
{sources}
Rules:
- plan_notes first (≤3 lines of your reasoning). Then 5–8 cues. Each cue = one spoken sentence ("say").
- Start with a concrete example, then the idea, then the name. One idea at a time. Never read the board aloud.
- Board ops (≤4 per cue) draw what the sentence names, WHILE it is said: set "at" to a word copied from "say".
- First cue's first op: {{"type":"new_page","text":"<segment title>"}}. Labels ≤4 words. No pixel coordinates —
  use place (right_of/below/left_of/above/next_line/center) + ref (an earlier id) or region (main/side/notes).
- Op types: box (shape rectangle|ellipse|diamond, style plain|warm|green|blue|red|violet), arrow (ref "a>b",
  text = short label), graph (nodes [{{id,text}}] ≤7 + edges [{{from,to,text}}]; flows, trees, cycles),
  table (rows of ≤4 short cells, first row = header), formula (text), bullet (side notes), sticky (a tip),
  text, highlight (ref + style underline|circle|marker|pointer|tick|cross|color), strike, erase.
  Give every drawn item a short id (b1, n2…) so later ops can refer to it. Unused fields = null.
- origin: "book" only when the sentence states what SOURCES say (then pages = labels from SOURCES), else
  "tutor_example" / "general_knowledge" / "tutor_bridge". Never invent page numbers.
- End with ONE check: kind mcq (3 options, 1 correct, wrong ones = misconceptions) or explain_why or apply;
  1–3 expectations (what a good answer covers), exactly 2 hints that don't give it away, reveal, on_correct.
  Never ask "did you understand?" as a check.
Example cue: {{"say":"Phase one is the lexer. It chops characters into tokens, like words.","origin":"general_knowledge",
"pages":null,"ops":[{{"type":"box","id":"lex","text":"Lexer","ref":null,"place":"next_line","region":null,
"shape":"rectangle","style":"blue","at":"lexer","nodes":null,"edges":null,"rows":null}}]}}"""

ANSWER_PROMPT = """The learner interrupted the lesson with a question. Answer it on the side board.
LESSON: {lesson} · current part: {segment} · you just said: {said}
BOARD (id | type | label):
{board}
{sources}
QUESTION: {question}
Decide intent + strategy first. Then say: 1–3 short spoken sentences, a direct answer (clarify → answer
briefly + one example; tangent → one line, offer to park it; out of scope → say so kindly). ops: ≤3 board ops
for the side board (text / box / arrow / formula / small graph), each with "at" = a word from your sentences.
Unused op fields = null. Facts about a book only from SOURCES; otherwise label them as general knowledge."""


def _learner() -> str:
    try:
        from .. import profile
        nm = profile.call() if profile.known() else "the learner"
    except Exception:
        nm = "the learner"
    return f"{nm}; adult self-learner; light Hinglish; wants clear intuition + exam-ready points"


def _name() -> str:
    try:
        from .. import profile
        return profile.call() if profile.known() else "your"
    except Exception:
        return "your"


def _sources_block(sources: list[dict] | None, limit_chars: int = 9000) -> str:
    if not sources:
        return "SOURCES: none (use general knowledge; mark origin general_knowledge)."
    out, n = [], 0
    for s in sources:
        line = f"[p.{s['page']}] {s['text']}"
        if n + len(line) > limit_chars:
            break
        out.append(line)
        n += len(line)
    return "SOURCES (cite only these page labels):\n" + "\n".join(out)


def _call(system: str, user: str, schema: dict, name: str, max_tokens: int) -> dict:
    r = router.complete([{"role": "system", "content": system}, {"role": "user", "content": user}],
                        route="tutor_plan", max_tokens=max_tokens, temperature=0.4, schema=schema,
                        schema_name=name, reasoning="medium")
    text = r["text"].strip()
    if text.startswith("```"):
        text = text.strip("`").split("\n", 1)[1] if "\n" in text else text
    return json.loads(text[text.find("{"): text.rfind("}") + 1])


class Planner:
    def __init__(self, sources: list[dict] | None = None):
        self.sources = sources
        self.pages = {str(s["page"]) for s in sources or []}

    def _fix_pages(self, seg: Segment) -> Segment:
        for c in seg.cues:
            c.pages = [p for p in (c.pages or []) if p in self.pages] or None
            if c.origin == "book" and not c.pages:
                c.origin = "general_knowledge"
        return seg

    def outline(self, topic: str, minutes: int = 15) -> dict:
        return _call(STYLE.format(name=_name()),
                     OUTLINE_PROMPT.format(minutes=minutes, topic=topic, learner=_learner(),
                                           sources=_sources_block(self.sources)),
                     OUTLINE_SCHEMA, "outline", 2500)

    def segment(self, out: dict, i: int) -> Segment | None:
        idea = out["ideas"][i]
        d = _call(STYLE.format(name=_name()),
                  SEGMENT_PROMPT.format(title=out["title"], idea=json.dumps(idea, ensure_ascii=False),
                                        thesis=out["thesis"], ideas=[x["title"] for x in out["ideas"]],
                                        done=[x["title"] for x in out["ideas"][:i]] or "nothing yet",
                                        learner=_learner(), sources=_sources_block(self.sources)),
                  SEGMENT_SCHEMA, "segment", 4000)
        d["id"], d["type"] = f"t{i + 1}", "teach"
        seg = sanitize_segment(d, i)
        return self._fix_pages(seg) if seg else None

    def answer(self, question: str, ctx: dict) -> dict:
        d = _call(STYLE.format(name=_name()),
                  ANSWER_PROMPT.format(lesson=ctx["lesson"], segment=ctx["segment"],
                                       said=" ".join(ctx["last_said"])[-600:], board=ctx["board"] or "(empty)",
                                       sources=_sources_block(self.sources, 4000), question=question),
                  ANSWER_SCHEMA, "answer", 900)
        d["ops"] = [o for o in (sanitize_op(x) for x in d.get("ops") or [] if isinstance(x, dict)) if o][:3]
        d["say"] = [s for s in d.get("say") or [] if isinstance(s, str) and s.strip()][:3]
        return d


# ---------------------------------------------------------------- code-built parts of the lesson
def opening(out: dict) -> list[Segment]:
    ideas = out["ideas"][:3]
    o = lambda **k: Op(**k)  # noqa: E731
    warm = Segment(id="w", type="warmup", title="Warm-up", cues=[
        Cue("wc1", f"Chalo! Today: {out['title']}. Let's go step by step.",
            [o(type="new_page", text=out["title"]), o(type="text", text="Goal: " + out["thesis"][:60], region="goal")]),
        Cue("wc2", "Before I explain anything, take a quick guess.",
            [o(type="box", id="q", text="?", shape="ellipse", style="violet", place="center", at="guess")]),
    ], check=Check(kind="predict", prompt=out["hook_prompt"], expectations=[out["hook_answer"]],
                   reveal="Hold that thought. We'll come back to your guess at the end."))
    cues = [Cue("mc1", "Here's the whole idea in one line. " + out["thesis"],
                [o(type="erase", ref="q"), o(type="text", id="thesis", text=out["thesis"], place="next_line")])]
    styles = ["blue", "green", "warm"]
    for i, idea in enumerate(ideas):
        ops = [o(type="box", id=f"m{i + 1}", text=idea["title"], style=styles[i % 3],
                 place="next_line" if i == 0 else "right_of", ref=f"m{i}" if i else None, at=idea["title"].split()[0])]
        if i:
            ops.append(o(type="arrow", ref=f"m{i}>m{i + 1}", at="start"))
        cues.append(Cue(f"mc{i + 2}", f"{['First', 'Then', 'And finally'][i]}: {idea['title']}.", ops))
    if out.get("key_terms"):
        terms = out["key_terms"][:4]
        cues.append(Cue("mc9", "A few words we'll use: " + ", ".join(terms) + ".",
                        [o(type="bullet", text=t, at=t.split()[0]) for t in terms]))
    return [warm, Segment(id="map", type="organizer", title="The big picture", cues=cues)]


def closing(out: dict) -> list[Segment]:
    ideas = [x["title"] for x in out["ideas"][:3]]
    q = out.get("quiz") or {}
    segs = [Segment(id="q1", type="quiz", title="Quiz", cues=[
        Cue("qc1", "Quick quiz, no peeking. I'll move to a fresh board.", [Op(type="new_page", text="Quick quiz")])],
        check=Check(kind="recall", prompt="Name the three big ideas from today, in your own words.",
                    expectations=ideas, hints=["The first one was about " + ideas[0].lower() + ".",
                                               "Think of the three boxes on the first board."],
                    reveal="The three ideas: " + "; ".join(ideas) + ".", on_correct="All three. Nice recall.",
                    confidence=True))]
    if q.get("prompt") and q.get("options"):
        segs.append(Segment(id="q2", type="quiz", title="Quiz", cues=[
            Cue("qc2", "Last one.", [Op(type="text", text="Q2", place="center")])],
            check=Check(kind="mcq", prompt=q["prompt"], options=[{"text": x["text"][:80], "correct": bool(x["correct"])}
                                                                 for x in q["options"][:4]],
                        expectations=[q.get("reveal", "")], hints=[], reveal=q.get("reveal", ""), confidence=True)))
    summary = out.get("summary") or ideas
    cues = [Cue("sc1", "Let's wrap up with the big ideas.", [Op(type="new_page", text="What you learned")])]
    for i, line in enumerate(summary[:3]):
        cues.append(Cue(f"sc{i + 2}", line, [Op(type="box", id=f"w{i + 1}", text=line[:32],
                                                     style=["blue", "green", "warm"][i], place="next_line")]))
    cues.append(Cue("sc9", f"I've saved {len(out.get('cards') or [])} revision cards. See you tomorrow for a two minute revise!",
                    [Op(type="highlight", ref=f"w{i + 1}", style="tick") for i in range(min(3, len(summary)))]))
    segs.append(Segment(id="sum", type="summary", title="Wrap-up", cues=cues))
    return segs


def build(topic: str, *, minutes: int = 15, sources: list[dict] | None = None, source: dict | None = None,
          log=print) -> tuple[Lesson, Planner]:
    """Outline now (blocking, one call); teaching segments fill in the background while the opening plays."""
    p = Planner(sources)
    out = p.outline(topic, minutes)
    if len(out.get("ideas") or []) < 1:
        raise ValueError("planner returned no ideas")
    out["ideas"] = out["ideas"][:3]
    lesson = Lesson(title=out["title"][:80], topic=topic, segments=opening(out),
                    source=source or {"kind": "topic"}, minutes=minutes,
                    cards=[{"front": c["front"][:160], "back": c["back"][:200], "kind": "fact"}
                           for c in out.get("cards") or []][:8],
                    summary=[s[:100] for s in out.get("summary") or []][:3])
    lesson.complete = False  # type: ignore[attr-defined]

    def fill():
        try:
            for i in range(len(out["ideas"])):
                try:
                    seg = p.segment(out, i)
                except Exception as e:
                    log(f"   [planner] segment {i + 1} failed: {type(e).__name__}: {str(e)[:120]}")
                    seg = None
                if seg:
                    lesson.segments.append(seg)
            lesson.segments.extend(closing(out))
        finally:
            lesson.complete = True  # type: ignore[attr-defined]
    threading.Thread(target=fill, daemon=True, name="lesson-writer").start()
    return lesson, p
