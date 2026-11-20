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


def rating_for(verdict: str | None, hints: int = 0, confidence: int | None = None, rung: int | None = None) -> Rating:
    """rung (Feature 5 hint ladder: 0 none · 1 nudge · 2 hint · 3 worked example · 4 answer) wins when given."""
    if rung is not None:
        from .pacing import rung_rating
        return {"again": Rating.Again, "hard": Rating.Hard, "good": Rating.Good,
                "easy": Rating.Easy}[rung_rating(verdict, rung, confidence)]
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


# ------------------------------------------------------------------------------------------------ concept cards
# Feature 3: one card per concept the coach taught (front = its check question, back = what a right answer contains),
# keyed by (mastery source key, concept id) — taught again later, the same card is updated, never duplicated.
CONCEPT_COLS = "id, front, back, source_key, source, concept_id, concept, check_spec, lapses, stability, due, reps"


def card_back(check: dict) -> str:
    exps = [str(e) for e in check.get("expectations") or [] if e]
    right = next((str(o.get("text")) for o in check.get("options") or [] if o.get("correct")), "")
    return ("; ".join(exps) or right or str(check.get("reveal") or ""))[:400]


def concept_card(source: str, source_key: str, concept_id: str, concept: str, check: dict) -> int:
    """Create or update the concept's card; a new card starts due now (the first rating schedules it)."""
    spec = {k: check.get(k) for k in ("kind", "prompt", "options", "expectations", "hints", "reveal", "example")}
    row = one("""INSERT INTO study_cards(front, back, kind, source_key, source, concept_id, concept, check_spec, due)
                 VALUES (%s,%s,'concept',%s,%s,%s,%s,%s, now())
                 ON CONFLICT (source_key, concept_id) WHERE source_key IS NOT NULL
                 DO UPDATE SET front=EXCLUDED.front, back=EXCLUDED.back, source=EXCLUDED.source,
                               concept=EXCLUDED.concept, check_spec=EXCLUDED.check_spec
                 RETURNING id, fsrs""",
              (str(check.get("prompt") or concept)[:400], card_back(check) or concept, source_key, source[:400],
               str(concept_id)[:64], concept[:120], json.dumps(spec)))
    if row["fsrs"] is None:
        q("UPDATE study_cards SET fsrs=%s WHERE id=%s", (json.dumps(Card(card_id=row["id"]).to_dict()), row["id"]))
    return row["id"]


def _source_filter(source_key: str | None, source: str | None) -> tuple[str, tuple]:
    if source_key:
        return " AND source_key = %s", (source_key,)
    if source:                                     # his file: the whole file and any of its units ("path#Unit 3")
        return " AND (lower(source) = lower(%s) OR lower(split_part(source, '#', 1)) = lower(%s))", (source, source)
    return "", ()


def due_concepts(source_key: str | None = None, source: str | None = None, limit: int = 12,
                 when: datetime | None = None) -> list[dict]:
    """Concept cards due now (or at `when`), weakest first (most lapses, lowest stability, longest overdue)."""
    extra, args = _source_filter(source_key, source)
    return q(f"""SELECT {CONCEPT_COLS} FROM study_cards WHERE source_key IS NOT NULL AND due <= %s{extra}
                 ORDER BY lapses DESC, stability NULLS FIRST, due LIMIT %s""",
             (when or datetime.now(timezone.utc), *args, limit))


def due_counts(when: datetime | None = None) -> dict:
    """{"total": n, "by_key": {source_key: n}} — what the Lessons page shows as "Review · N due"."""
    rows = q("""SELECT source_key, count(*) AS n FROM study_cards WHERE source_key IS NOT NULL AND due <= %s
                GROUP BY source_key""", (when or datetime.now(timezone.utc),))
    by = {r["source_key"]: int(r["n"]) for r in rows}
    return {"total": sum(by.values()), "by_key": by}


def next_due(source_key: str | None = None) -> datetime | None:
    extra, args = _source_filter(source_key, None)
    r = one(f"SELECT min(due) AS d FROM study_cards WHERE source_key IS NOT NULL{extra}", args)
    return r["d"] if r else None


def concept_cards(source_key: str) -> list[dict]:
    return q(f"SELECT {CONCEPT_COLS}, fsrs FROM study_cards WHERE source_key = %s", (source_key,))


def recall_at(row: dict, at: datetime) -> float:
    """FSRS retrievability of one card at a moment (0 for a card never reviewed)."""
    card = _card(row)
    if card.last_review is None:
        return 0.0
    return float(SCHED.get_card_retrievability(card, at))
