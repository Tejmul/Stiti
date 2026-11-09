"""Habits: forgiving strength + fading prompts — NOT spaced repetition, NO streak shaming.

Research (report §Habits): automaticity takes a median ~59–66 days (range 4–335, Lally 2010);
habits need steady cue-linked repetition; reminders boost repetition but slow automaticity, so
prompts fade as strength grows; broken-streak framing lowers continuation (66% → 58%).
Strength is a Loop-Habit-Tracker-style EMA: a missed day dents it, never resets it.
"""
from __future__ import annotations

import re
from datetime import date, timedelta

from ..config import CFG
from ..db import one, q

ALPHA = 2 / (21 + 1)    # ~3-week memory: one miss costs ~9% of strength, not everything

NEW_RX = re.compile(r"\b(new habit|start (a )?habit|habit (banana|shuru|start)|i want to (start|build) (a )?habit)\b", re.I)
DONE_RX = re.compile(r"\b(did|done|ho gaya|kar liya|completed|finished)\b", re.I)


def today() -> date:
    from datetime import datetime
    return datetime.now(CFG.tz).date()


def create(name: str, cue: str | None = None, per_week: int = 7) -> int:
    return one("INSERT INTO habits(name, cue, target_per_week) VALUES (%s,%s,%s) RETURNING id",
               (name.strip(), cue, per_week))["id"]


def find(text: str) -> dict | None:
    return one("""SELECT id, name, strength FROM habits WHERE status='active'
                  AND similarity(lower(name), lower(%s)) >= 0.2 ORDER BY similarity(lower(name), lower(%s)) DESC
                  LIMIT 1""", (text, text))


def log(habit_id: int, done: bool = True, day: date | None = None) -> float:
    d = day or today()
    q("""INSERT INTO habit_events(habit_id, day, done) VALUES (%s,%s,%s)
         ON CONFLICT (habit_id, day) DO UPDATE SET done = EXCLUDED.done""", (habit_id, d, done))
    return rescore(habit_id)


def rescore(habit_id: int) -> float:
    h = one("SELECT created_at::date c FROM habits WHERE id=%s", (habit_id,))
    events = {r["day"]: r["done"] for r in q("SELECT day, done FROM habit_events WHERE habit_id=%s", (habit_id,))}
    s, d = 0.0, h["c"]
    while d <= today():
        if d in events:                         # unknown days (not asked) don't count against him
            s = s + ALPHA * ((1.0 if events[d] else 0.0) - s)
        d += timedelta(days=1)
    level = 2 if s < 0.5 else 1 if s < 0.8 else 0   # fading prompts
    q("UPDATE habits SET strength=%s, prompt_level=%s, last_scored=%s WHERE id=%s", (s, level, today(), habit_id))
    return s


def describe(strength: float) -> str:
    if strength >= 0.8:
        return "almost automatic now — I'll stop reminding you"
    if strength >= 0.5:
        return "getting solid — reminders every other day now"
    if strength >= 0.2:
        return "taking root"
    return "just planted"


def handle(text: str) -> str | None:
    """Fast path: 'new habit: meditate after chai', 'did gym', 'how are my habits'."""
    t = text.strip()
    if NEW_RX.search(t):
        body = re.split(r"[:\-]", t, 1)[1] if re.search(r"[:\-]", t) else NEW_RX.sub("", t)
        m = re.search(r"\b(after|before|ke baad|se pehle)\b(.+)$", body, re.I)
        cue = m.group(0).strip() if m else None
        name = body[:m.start()].strip(" ,.") if m else body.strip(" ,.")
        if not name:
            return "Which habit? Say it like “new habit: 10 pushups after brushing”."
        hid = create(name, cue)
        tip = "" if cue else " Tip: tie it to a cue — “after chai”, “before bed” — it sticks faster."
        return f"Habit started: “{name}”{' ' + cue if cue else ''}. No streaks, no pressure — we track strength.{tip} (#{hid})"
    if re.search(r"\b(my habits|habits kaise|habit status|how are my habits)\b", t, re.I):
        rows = q("SELECT name, strength FROM habits WHERE status='active' ORDER BY strength DESC LIMIT 3")
        if not rows:
            return "No habits yet. Want to start one? Say “new habit: …”."
        return "; ".join(f"{r['name']}: {describe(r['strength'])}" for r in rows) + "."
    if DONE_RX.search(t) and re.search(r"\bhabit\b|\bgym\b|\bworkout\b|\bmeditat|\bwalk|\bread", t, re.I):
        h = find(DONE_RX.sub("", t))
        if h:
            s = log(h["id"], True)
            return f"Logged {h['name']} ✔ — {describe(s)}."
    return None


def due_prompts() -> list[dict]:
    """Habits that deserve a (fading) prompt today and haven't been logged."""
    return q("""SELECT h.id, h.name, h.cue FROM habits h
                WHERE h.status='active' AND h.prompt_level > 0
                  AND NOT EXISTS (SELECT 1 FROM habit_events e WHERE e.habit_id=h.id AND e.day=%(d)s)
                  AND (h.prompt_level = 2 OR extract(doy FROM %(d)s::date)::int %% 2 = 0)""", {"d": today()})
