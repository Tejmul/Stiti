"""Proactive layer: morning brief + Nudge Gate (report §Proactive nudges).

LLM agents over-intervene; Stiti gets a daily budget of unprompted nudges (default 4, range 3–5),
fires only at natural breakpoints (start of a session / first message of the day), and logs
accept/dismiss for later bandit learning. User-set alarms are never counted or suppressed.
"""
from __future__ import annotations

import json
import os
from datetime import datetime

from ..config import CFG
from ..db import one, q
from ..fastpath import handlers
from . import habits

BUDGET = int(os.getenv("STITI_NUDGE_BUDGET", "4"))


def sent_today() -> int:
    return one("SELECT count(*) n FROM nudges WHERE sent_at >= date_trunc('day', now() AT TIME ZONE %s) AT TIME ZONE %s",
               (CFG.tz.key, CFG.tz.key))["n"]


def allowed() -> bool:
    return sent_today() < BUDGET


def record(kind: str, payload: dict | None = None) -> int:
    return one("INSERT INTO nudges(kind, payload) VALUES (%s,%s) RETURNING id", (kind, json.dumps(payload or {})))["id"]


def morning_brief(now: datetime | None = None, low_energy: bool = False) -> str | None:
    """Once per day, on his first message (a natural breakpoint)."""
    now = now or datetime.now(CFG.tz)
    if one("SELECT 1 FROM nudges WHERE kind='morning_brief' AND sent_at >= date_trunc('day', now() AT TIME ZONE %s) AT TIME ZONE %s",
           (CFG.tz.key, CFG.tz.key)) or not allowed():
        return None
    greet = "Good morning" if now.hour < 12 else "Hey" if now.hour < 17 else "Good evening"
    fresh = " New week, fresh start." if now.weekday() == 0 else ""
    parts = [f"{greet}!{fresh}"]
    if low_energy:
        parts.append(handlers.todo_list(limit=1) + " Just that one is enough today.")
    else:
        parts.append(handlers.todo_list(limit=3))
    nxt = handlers.list_intents(limit=1)
    if not nxt.startswith("No "):
        parts.append(nxt)
    hp = habits.due_prompts()
    if hp:
        h = hp[0]
        parts.append(f"And {h['name']}{' ' + h['cue'] if h['cue'] else ''} when you get a chance.")
    record("morning_brief", {"text": " ".join(parts)})
    return " ".join(parts)
