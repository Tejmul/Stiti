"""Spaced revision with FSRS (py-fsrs, MIT, pure Python). Cards come from lessons; grades come from local checks.

Rating map (research: docs/research/crash_course.md): wrong → Again · used a hint or confidence ≤2 → Hard ·
right → Good · right with confidence 5 and no hint → Easy. Learning steps 10 min / 60 min, so cards from tonight's
early lessons come back as checkpoint questions later the same night; the morning session takes what is due.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from fsrs import Card, Rating, Scheduler

from ..db import one, q

SCHED = Scheduler(desired_retention=0.9, learning_steps=(timedelta(minutes=10), timedelta(minutes=60)),
                  enable_fuzzing=True)


def rating_for(verdict: str | None, hints: int = 0, confidence: int | None = None) -> Rating:
    if verdict not in ("correct", "partial"):
        return Rating.Again
    if verdict == "partial" or hints or (confidence is not None and confidence <= 2):
        return Rating.Hard
    if confidence == 5:
        return Rating.Easy
    return Rating.Good


def _card(row: dict) -> Card:
    if row.get("fsrs"):
        d = row["fsrs"] if isinstance(row["fsrs"], dict) else json.loads(row["fsrs"])
        return Card.from_dict(d)
    return Card(card_id=row["id"])


def review(card_id: int, rating: Rating, when: datetime | None = None) -> datetime:
    row = one("SELECT id, fsrs FROM study_cards WHERE id=%s", (card_id,))
    if not row:
        raise KeyError(card_id)
    card, _ = SCHED.review_card(_card(row), rating, when or datetime.now(timezone.utc))
    q("""UPDATE study_cards SET fsrs=%s, due=%s, stability=%s, difficulty=%s, state=%s, last_review=%s,
                reps = reps + 1, lapses = lapses + %s WHERE id=%s""",
      (json.dumps(card.to_dict()), card.due, card.stability, card.difficulty, int(card.state), card.last_review,
       int(rating == Rating.Again), card_id))
    return card.due


def start(card_ids: list[int], soon_minutes: int = 10) -> None:
    """New cards from a lesson just taught: first look-back in ~10 min (tonight's checkpoints)."""
    due = datetime.now(timezone.utc) + timedelta(minutes=soon_minutes)
    for cid in card_ids:
        q("UPDATE study_cards SET due=%s, fsrs=COALESCE(fsrs, %s) WHERE id=%s",
          (due, json.dumps(Card(card_id=cid, due=due).to_dict()), cid))


def due(limit: int = 30, course_id: int | None = None, slack_minutes: int = 0) -> list[dict]:
    """Due cards, weakest first (lowest stability, most lapses)."""
    return q(f"""SELECT id, front, back, kind, source_pages, lapses, stability FROM study_cards
                 WHERE due <= now() + make_interval(mins => %s) {"AND course_id = %s" if course_id else ""}
                 ORDER BY lapses DESC, stability NULLS FIRST, due LIMIT %s""",
             (slack_minutes, course_id, limit) if course_id else (slack_minutes, limit))


def at_risk(course_id: int, at: datetime, threshold: float = 0.9, limit: int = 40) -> list[dict]:
    """Exam mode: every card whose predicted recall at `at` is below threshold, whatever its due date."""
    rows = q("SELECT id, front, back, fsrs FROM study_cards WHERE course_id=%s", (course_id,))
    risky = [(SCHED.get_card_retrievability(_card(r), at), r) for r in rows]
    return [r for p, r in sorted(risky, key=lambda x: x[0]) if p < threshold][:limit]
