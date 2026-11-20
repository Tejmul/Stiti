"""Review — a short spoken quiz of the concept cards that are due (feature 3, docs/FEATURE_PLAN.md).

Every concept the coach teaches leaves an FSRS card (coach.py `_card`: front = its check question, back = the
points a right answer has). `stiti teach --review [<file>]`, "review" / "what's due" by voice, or Start review on
the Lessons page run this: one question per due card (weakest first, at most REVIEW_MAX ≈ 5 minutes), graded locally
by grade.py; a miss gets one hint, then the answer. Each answer → an FSRS rating (wrong → Again · a hint or partly
right → Hard · right → Good) → the card's next due date, and the concept's mastery (origin "review") — so the map,
the Lessons page and the next lesson's queue all see it. No LLM needed to run a review.
"""
from __future__ import annotations

from .lesson import Check, Cue, Lesson, Op, Segment
from .mastery import Mastery

REVIEW_MAX = 10            # about five minutes of spoken questions


def card_check(c: dict) -> Check:
    """The card's check, asked the way it was taught; one hint at most (hint → reveal)."""
    spec = c.get("check_spec") or {}
    if isinstance(spec, str):
        import json
        try:
            spec = json.loads(spec)
        except ValueError:
            spec = {}
    opts = spec.get("options") or None
    if opts and not any(o.get("correct") for o in opts):
        opts = None
    exps = [str(e) for e in spec.get("expectations") or [] if e] or ([c["back"]] if c.get("back") else [])
    hints = [str(h) for h in spec.get("hints") or [] if h][:1] or [f"It's about {c.get('concept') or 'this topic'}."]
    kind = spec.get("kind") if spec.get("kind") in ("mcq", "recall", "apply", "explain_why") else "recall"
    if kind == "mcq" and not opts:
        kind = "recall"
    return Check(kind=kind, prompt=str(c.get("front") or spec.get("prompt") or ""), options=opts, expectations=exps,
                 hints=hints, reveal=str(spec.get("reveal") or c.get("back") or ""), on_correct="Yes, that's it.",
                 example=[str(x) for x in spec.get("example") or [] if x][:4])   # the ladder's worked-example rung


def build(cards: list[dict]) -> Lesson:
    n = len(cards)
    segs = [Segment(id="rintro", type="organizer", title="Review", cues=[Cue(
        "rintro1", f"Review time. {n} quick question{'s' if n != 1 else ''} on what you're about to forget. "
                   "Short answers are fine, or say I don't know.",
        [Op(type="new_page", text="Review"),
         Op(type="text", text=f"{n} card{'s' if n != 1 else ''} due", region="points"),
         Op(type="text", text="Answer out loud · a miss gets one hint", region="remember")])])]
    for k, c in enumerate(cards):
        name = str(c.get("concept") or "Review")[:48]
        say = "First one." if k == 0 else "Last one." if k == n - 1 else "Next."
        segs.append(Segment(id=f"r{c['id']}", type="quiz", title=name, cues=[Cue(
            f"r{c['id']}c", say, [Op(type="new_page", text=name),
                                  Op(type="text", text=f"Card {k + 1} of {n}", region="remember")])],
                            check=card_check(c)))
    return Lesson(title="Review", topic="Review", segments=segs, source={"kind": "review"}, minutes=5)


class Review:
    """One review session on the board + voice. `cards` = srs.due_concepts(...) rows."""

    def __init__(self, cards: list[dict], *, audio, events, server=None, log=print, persist: bool = True,
                 planner=None, **tutor_kw):
        from . import answerer
        from .player import Tutor
        self.cards = cards
        self.byseg = {f"r{c['id']}": c for c in cards}
        self.L = build(cards)
        self.log = log
        self.t = Tutor(self.L, audio=audio, events=events, server=server, log=log, persist=persist,
                       planner=planner if planner is not None else (answerer() if persist else None), **tutor_kw)
        self.t.on_check = self._on_check
        self.t.before_end = self._before_end
        self.t.short_ladder = True                    # a short quiz: one hint then the answer (the rung still rates)
        self.done: list[dict] = []
        self._mastery: dict[str, Mastery] = {}
        self._recapped = False

    def _on_check(self, seg: Segment, rec: dict) -> None:
        c = self.byseg.get(seg.id)
        if not c or rec.get("verdict") not in ("correct", "partial", "wrong", "idk"):
            return                                    # skipped / ended: the card stays due, mastery unchanged
        from . import srs
        # Feature 5: the hint-ladder rung he needed decides the FSRS rating; the mastery event keeps the verdict + hints
        rating = srs.rating_for(rec["verdict"], rec.get("hints", 0), rec.get("confidence"), rung=rec.get("rung"))
        due = srs.review(c["id"], rating)
        m = self._mastery.get(c["source"]) or self._mastery.setdefault(c["source"], Mastery(c["source"]))
        p = m.update(c["concept_id"], rec["verdict"], origin="review", hints=rec.get("hints", 0))
        self.done.append({"card": c["id"], "concept": c.get("concept"), "verdict": rec["verdict"],
                          "hints": rec.get("hints", 0), "rating": rating.name, "due": due, "p": p})
        self.log(f"   [review] card {c['id']} {rec['verdict']} (hints {rec.get('hints', 0)}) → {rating.name}, "
                 f"due {due:%d %b %H:%M}, mastery {p:.2f}")

    def _before_end(self) -> bool:
        """Once, at the end: how it went, what comes back soon, on a "Review done" page."""
        if self._recapped or not self.done:
            return False
        self._recapped = True
        right = [d for d in self.done if d["verdict"] == "correct"]
        miss = [d for d in self.done if d["verdict"] != "correct"]
        line = f"Done. {len(right)} of {len(self.done)} right."
        if miss:
            names = ", ".join(dict.fromkeys(str(d["concept"]) for d in miss[:3]))
            line += f" {names} will come back soon."
        if right:
            line += " The rest comes back in a few days."
        ops = [Op(type="new_page", text="Review done")]
        ops += [Op(type="text", text=f"✓ {d['concept']}"[:80], region="points") for d in right[:6]]
        ops += [Op(type="text", text=f"~ {d['concept']}"[:80], region="points") for d in miss[:6]]
        ops.append(Op(type="text", text=f"{len(right)} of {len(self.done)} right", region="remember"))
        self.L.segments.append(Segment(id="rdone", type="teach", title="Review done",
                                       cues=[Cue("rdonec1", line, ops)]))
        return True

    def run(self) -> dict:
        res = self.t.run()
        res["reviewed"] = self.done
        return res
