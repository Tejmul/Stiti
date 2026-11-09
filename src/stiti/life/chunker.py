"""Socratic Chunker: lazy, one-level-at-a-time goal breakdown (ADaPT, NAACL 2024) + if-then plans.

Never plans everything up front (BabyAGI-style over-planning is what the research says to avoid).
Phases: 1 define done → 2 first doable step (≤ ~25 min) → 3 if-then for when/where → 4 offer next.
Works with no LLM (questions are templates); the night job can later suggest steps via the cloud.
"""
from __future__ import annotations

import re

from ..db import one

START_RX = re.compile(r"\b(break (it |this )?down|break down|chhote steps|steps mein (todo|baant)|"
                      r"kaise shuru karu|where do i start|overwhelm)", re.I)
MINUTES_RX = re.compile(r"(\d+)\s*(min|minute|minutes|ghanta|hour|hr)", re.I)


class Chunker:
    def __init__(self, goal: str):
        self.goal = goal.strip(" .") or "this"
        self.phase = 1
        self.parent_id: int | None = None
        self.step: str | None = None

    def start(self) -> str:
        return f"Okay, let's make “{self.goal}” small. What does *done* look like — how will you know it's finished?"

    def answer(self, text: str) -> tuple[str, bool]:
        """Returns (reply, finished)."""
        t = text.strip()
        if self.phase == 1:
            self.parent_id = one("INSERT INTO tasks(title, done_when, source) VALUES (%s,%s,'chunker') RETURNING id",
                                 (self.goal, t))["id"]
            self.phase = 2
            return "Nice. What's the very first step you could do in about 25 minutes?", False
        if self.phase == 2:
            m = MINUTES_RX.search(t)
            mins = int(m.group(1)) * (60 if m and m.group(2).lower().startswith(("h", "g")) else 1) if m else 25
            if mins > 60:
                return "That's still big. What's a smaller piece of it — something you could start right away?", False
            self.step = MINUTES_RX.sub("", t).strip(" ,.")
            self.phase = 3
            return "When and where will you do it? Say it as “if/when X, then I'll do it”.", False
        if self.phase == 3:
            one("""INSERT INTO tasks(title, parent_id, if_then, est_minutes, source) VALUES (%s,%s,%s,25,'chunker')
                   RETURNING id""", (self.step, self.parent_id, t))
            self.phase = 4
            return (f"Saved: “{self.step}” — {t}. That's the only step that matters right now. "
                    "Want to plan the next one too, or stop here?"), False
        if re.search(r"\b(yes|haan|next|aage|another)\b", t, re.I):
            self.phase = 2
            return "Okay — what's the next small step after that?", False
        return "Perfect, stopping here. One step at a time. 💪", True


def goal_from(text: str) -> str:
    m = re.search(r"(?:break (?:it |this )?down|break down)\s*:?\s*(.+)$", text, re.I)
    if m:
        return m.group(1)
    return START_RX.sub("", text).strip(" :,.") or "this goal"
