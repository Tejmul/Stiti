"""Tutor memory in Stiti's Postgres brain: lessons, sessions (resume cursor), revision cards, and one
episode per lesson so Stiti can later recall "last week you learned compiler phases"."""
from __future__ import annotations

import dataclasses
import json

from ..db import one, q
from .lesson import Lesson


def _plan(lesson: Lesson) -> str:
    return json.dumps(dataclasses.asdict(lesson))


def save_lesson(lesson: Lesson) -> int:
    row = one("SELECT id FROM tutor_lessons WHERE title=%s AND plan=%s::jsonb ORDER BY id DESC LIMIT 1",
              (lesson.title, _plan(lesson)))
    if row:
        return row["id"]
    return one("INSERT INTO tutor_lessons(title, topic, source, plan) VALUES (%s,%s,%s,%s) RETURNING id",
               (lesson.title, lesson.topic, json.dumps(lesson.source), _plan(lesson)))["id"]


def start_session(lesson_id: int, cursor: int = 0) -> int:
    return one("INSERT INTO tutor_sessions(lesson_id, cursor) VALUES (%s,%s) RETURNING id", (lesson_id, cursor))["id"]


def update_session(sid: int, *, cursor: int | None = None, results=None, questions=None,
                   finished: bool | None = None, ended: bool = False) -> None:
    q("""UPDATE tutor_sessions SET cursor=COALESCE(%s, cursor), results=COALESCE(%s::jsonb, results),
            questions=COALESCE(%s::jsonb, questions), finished=COALESCE(%s, finished),
            ended_at=CASE WHEN %s THEN now() ELSE ended_at END WHERE id=%s""",
      (cursor, json.dumps(results) if results is not None else None,
       json.dumps(questions) if questions is not None else None, finished, ended, sid))


def last_unfinished(title: str | None = None) -> dict | None:
    """Most recent session that didn't finish (for `stiti teach --resume`)."""
    return one("""SELECT s.id, s.lesson_id, s.cursor, l.plan, l.title FROM tutor_sessions s
                  JOIN tutor_lessons l ON l.id = s.lesson_id
                  WHERE NOT s.finished AND s.cursor > 0 AND (%s::text IS NULL OR l.title = %s)
                  ORDER BY s.started_at DESC LIMIT 1""", (title, title))


def save_cards(lesson_id: int, cards: list[dict], pages: str | None = None) -> int:
    n = 0
    for c in cards:
        r = one("""INSERT INTO study_cards(lesson_id, front, back, kind, source_pages) VALUES (%s,%s,%s,%s,%s)
                   ON CONFLICT (lesson_id, front) DO NOTHING RETURNING id""",
                (lesson_id, c["front"], c["back"], c.get("kind") or "fact", pages))
        n += bool(r)
    return n


def remember(lesson: Lesson, results: list[dict], questions: list[str], finished: bool) -> None:
    """One memory episode, so the normal brain (recall, sleep job, graph) knows this lesson happened."""
    from ..brain import memory
    right = sum(r.get("verdict") == "correct" for r in results)
    graded = sum(r.get("verdict") not in ("predict", None) for r in results)
    text = (f"Tutor lesson on '{lesson.title}' ({'finished' if finished else 'stopped midway'}). "
            f"Checks right: {right}/{graded}."
            + (f" Asked: {'; '.join(questions[:5])}." if questions else "")
            + (f" Key ideas: {'; '.join(lesson.summary)}." if lesson.summary else ""))
    memory.add_episode(None, "stiti", text, origin="agent", importance=5)
