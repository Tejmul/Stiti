"""On-screen cards: what Stiti SHOWS while she speaks ("What's on my to-do list?" → the list appears on the desktop).

After each turn the engine builds one typed card from the brain (never from the LLM's words), and the voice loop
hands it to the desktop overlay. Everything stays on this Mac.

Card = {"kind": todos | todo_added | reminders | reminder_set | news,
        "title": str, "items": [{"id": int|None, "text": str, "meta": str}], "ts": float}
"""
from __future__ import annotations

import re
import time
from datetime import datetime

from .config import CFG
from .db import one, q

UPCOMING_RX = re.compile(r"\b(what'?s|what is|show|list|any|kya|kaun|kab|upcoming|coming up|next)\b.*"
                         r"\b(alarms?|reminders?|timers?)\b|\b(alarms?|reminders?)\b.*\b(kya|hai|hain|set)\s*\??$", re.I)
LIST_TODOS_RX = re.compile(r"\b(what are my|show( me)?|list|kya kya|pending|bacha|baaki|my (todos?|tasks|to-?do list)|"
                           r"(todos?|tasks?|to-?do list)\b.*\b(today|kya|dikhao|batao|hain|hai))\b", re.I)


def _when(d: datetime | None) -> str:
    if not d:
        return ""
    d = d.astimezone(CFG.tz)
    today = datetime.now(CFG.tz).date()
    day = "today" if d.date() == today else "tomorrow" if (d.date() - today).days == 1 else f"{d:%a %d %b}"
    return f"{day}, {d:%-I:%M %p}".replace(":00 ", " ")


def todos(limit: int = 8) -> dict:
    rows = q("""SELECT id, title, due FROM tasks WHERE status='open' AND parent_id IS NULL
                ORDER BY due NULLS LAST, created_at LIMIT %s""", (limit,))
    n = one("SELECT count(*) n FROM tasks WHERE status='open' AND parent_id IS NULL")["n"]
    return {"kind": "todos", "title": "Nothing on your list" if not n else f"{n} thing{'s' if n != 1 else ''} to do",
            "items": [{"id": r["id"], "text": r["title"], "meta": f"due {_when(r['due'])}" if r["due"] else ""} for r in rows],
            "ts": time.time()}


def reminders(limit: int = 6) -> dict:
    rows = q("""SELECT id, kind, fire_at, rrule, COALESCE(payload->>'say', payload->>'text') AS text FROM intents
                WHERE state IN ('pending','armed') AND fire_at IS NOT NULL AND fire_at > now()
                ORDER BY fire_at LIMIT %s""", (limit,))
    return {"kind": "reminders", "title": "Coming up" if rows else "Nothing coming up",
            "items": [{"id": r["id"], "text": "Alarm" if r["kind"] == "alarm" else (r["text"] or r["kind"].title()),
                       "meta": _when(r["fire_at"]) + (" · repeats" if r["rrule"] else "")} for r in rows],
            "ts": time.time()}


def for_turn(text: str, domain: str, reply: str | None, action: dict | None, live_res=None, live_from: int = 0) -> dict | None:
    """The card to show for this turn, or None (most chat turns show nothing)."""
    if live_res is not None and getattr(live_res, "items", None):
        items = live_res.items[live_from:live_from + 4]
        title = {"papers": "New research", "ai": "AI updates", "tech": "Tech news", "jobs": "Placements & jobs",
                 "world": "Around the world", "india": "India today"}.get(live_res.req.kind, "What I found")
        return {"kind": "news", "title": title,
                "items": [{"id": None, "text": i.title, "meta": i.source} for i in items], "ts": time.time()}
    if domain == "todo":
        if action and action.get("type") == "task":
            r = one("SELECT id, title, due FROM tasks WHERE id=%s", (action["id"],))
            if r:
                return {"kind": "todo_added", "title": "Added to your list",
                        "items": [{"id": r["id"], "text": r["title"], "meta": f"due {_when(r['due'])}" if r["due"] else ""}],
                        "ts": time.time()}
        if LIST_TODOS_RX.search(text):
            return todos()
    if domain == "time":
        if action and action.get("type") == "intent":
            r = one("""SELECT id, kind, fire_at, rrule, COALESCE(payload->>'say', payload->>'text') AS text
                       FROM intents WHERE id=%s""", (action["id"],))
            if r and r["fire_at"]:
                return {"kind": "reminder_set", "title": f"{r['kind'].title()} set",
                        "items": [{"id": r["id"], "text": "Alarm" if r["kind"] == "alarm" else (r["text"] or "Reminder"),
                                   "meta": _when(r["fire_at"]) + (" · repeats" if r["rrule"] else "")}],
                        "ts": time.time()}
        if UPCOMING_RX.search(text):
            return reminders()
    return None
