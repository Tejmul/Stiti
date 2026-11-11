"""On-screen cards: what Stiti SHOWS while she speaks ("What's on my to-do list?" → the list appears on the desktop).

After each turn the engine builds one typed card from the brain (never from the LLM's words), and the voice loop
hands it to the desktop overlay. Everything stays on this Mac.

Card = {"kind": todos | reminders | news,
        "title": str, "items": [{"id": int|None, "text": str, "meta": str}], "ts": float,
        "focus": {"op": added | done | removed | set | cancelled | moved, "ids": [int]}  (optional)}

What changed is told by the fast-path handler that changed it (`note()`), never guessed from the reply text. The card
then shows the WHOLE list with the change played on it: a new row slides in, a done row gets its ✓ + strike-through
and leaves the list, a cancelled reminder is crossed out and leaves (overlay/card.py draws it, model.choreography
times it).
"""
from __future__ import annotations

import re
import threading
import time
from datetime import datetime

from .config import CFG
from .db import one, q

UPCOMING_RX = re.compile(r"\b(what'?s|what is|show|list|any|kya|kaun|kab|upcoming|coming up|next)\b.*"
                         r"\b(alarms?|reminders?|timers?)\b|\b(alarms?|reminders?)\b.*\b(kya|hai|hain|set)\s*\??$", re.I)
LIST_TODOS_RX = re.compile(r"\b(what are my|show( me)?|list|kya kya|pending|bacha|baaki|my (todos?|tasks|to-?do list)|"
                           r"(todos?|tasks?|to-?do list)\b.*\b(today|kya|dikhao|batao|hain|hai))\b", re.I)


SHOWN = 6                    # rows a card shows (overlay.model.MAX_ROWS); a focused row is always among them
RECENT_S = 900.0             # "it's done" = the task he touched in the last 15 min
_ev = threading.local()      # the turn's change, set by a handler in the engine's thread
_recent = {"task": None, "t": 0.0}


def note(op: str, kind: str, ids) -> None:
    """A fast-path write says what it changed: op added|done|removed|set|cancelled|moved, kind task|intent."""
    ids = [int(ids)] if isinstance(ids, int) else [int(i) for i in ids]
    _ev.last = {"op": op, "kind": kind, "ids": ids}
    if kind == "task" and op == "added" and len(ids) == 1:
        remember_task(ids[0])


def take() -> dict | None:
    """The change noted during this turn (and clear it)."""
    v = getattr(_ev, "last", None)
    _ev.last = None
    return v


def remember_task(tid: int | None) -> None:
    _recent.update(task=tid, t=time.time())


def recent_task() -> int | None:
    return _recent["task"] if time.time() - _recent["t"] < RECENT_S else None


def _with_focus(rows: list[dict], extra: list[dict], ids: list[int]) -> list[dict]:
    """Make sure every focused row is on the card (inside the first SHOWN rows), keeping list order otherwise."""
    have = {r["id"] for r in rows}
    rows = rows + [r for r in extra if r["id"] not in have]
    shown, rest = rows[:SHOWN], rows[SHOWN:]
    missing = [r for r in rest if r["id"] in ids]
    if missing:
        keep = [r for r in shown if r["id"] in ids]
        others = [r for r in shown if r["id"] not in ids][: max(0, SHOWN - len(keep) - len(missing))]
        shown = [r for r in rows if r in others or r in keep or r in missing]
    return shown + [r for r in rows if r not in shown]


def _when(d: datetime | None) -> str:
    if not d:
        return ""
    d = d.astimezone(CFG.tz)
    today = datetime.now(CFG.tz).date()
    day = "today" if d.date() == today else "tomorrow" if (d.date() - today).days == 1 else f"{d:%a %d %b}"
    return f"{day}, {d:%-I:%M %p}".replace(":00 ", " ")


def todos(limit: int = 8, focus: dict | None = None) -> dict:
    ids = list((focus or {}).get("ids") or [])
    rows = q("""SELECT id, title, due FROM tasks WHERE status='open' AND parent_id IS NULL
                ORDER BY due NULLS LAST, created_at LIMIT %s""", (limit,))
    extra = q("SELECT id, title, due FROM tasks WHERE id = ANY(%s) ORDER BY due NULLS LAST, created_at", (ids,)) if ids else []
    rows = _with_focus(list(rows), list(extra), ids)
    n = one("SELECT count(*) n FROM tasks WHERE status='open' AND parent_id IS NULL")["n"]
    card = {"kind": "todos", "title": "Nothing on your list" if not n else f"{n} thing{'s' if n != 1 else ''} to do",
            "items": [{"id": r["id"], "text": r["title"], "meta": f"due {_when(r['due'])}" if r["due"] else ""} for r in rows],
            "ts": time.time()}
    if focus:
        card["focus"] = {"op": focus["op"], "ids": ids}
    elif n == 1 and rows:
        remember_task(rows[0]["id"])                    # "it's done" now means this one
    return card


def reminders(limit: int = 6, focus: dict | None = None) -> dict:
    ids = list((focus or {}).get("ids") or [])
    cols = "id, kind, fire_at, rrule, COALESCE(payload->>'say', payload->>'text') AS text"
    rows = q(f"""SELECT {cols} FROM intents WHERE state IN ('pending','armed') AND fire_at IS NOT NULL AND fire_at > now()
                 ORDER BY fire_at LIMIT %s""", (limit,))
    extra = q(f"SELECT {cols} FROM intents WHERE id = ANY(%s) ORDER BY fire_at", (ids,)) if ids else []
    rows = _with_focus(list(rows), list(extra), ids)
    live = [r for r in rows if not (focus and focus["op"] == "cancelled" and r["id"] in ids)]
    card = {"kind": "reminders", "title": "Coming up" if live else "Nothing coming up",
            "items": [{"id": r["id"], "text": "Alarm" if r["kind"] == "alarm" else (r["text"] or r["kind"].title()),
                       "meta": _when(r["fire_at"]) + (" · repeats" if r["rrule"] else "")} for r in rows],
            "ts": time.time()}
    if focus:
        card["focus"] = {"op": focus["op"], "ids": ids}
    return card


def for_turn(text: str, domain: str, reply: str | None, action: dict | None, live_res=None, live_from: int = 0,
             event: dict | None = None) -> dict | None:
    """The card to show for this turn, or None (most chat turns show nothing). `event` = what a handler noted."""
    if live_res is not None and getattr(live_res, "items", None):
        items = live_res.items[live_from:live_from + 4]
        title = {"papers": "New research", "ai": "AI updates", "tech": "Tech news", "jobs": "Placements & jobs",
                 "world": "Around the world", "india": "India today"}.get(live_res.req.kind, "What I found")
        return {"kind": "news", "title": title,
                "items": [{"id": None, "text": i.title, "meta": i.source} for i in items], "ts": time.time()}
    if event and event.get("ids"):
        if event.get("kind") == "task":
            return todos(focus=event)
        if event.get("kind") == "intent" and event.get("op") != "ask":
            return reminders(focus=event)
    if event and event.get("op") == "ask":             # "which one is done?" → show the list he's choosing from
        return todos()
    if domain == "todo":
        if action and action.get("type") == "task":    # a write that didn't note() itself: show it as added
            return todos(focus={"op": "added", "ids": [action["id"]]})
        if LIST_TODOS_RX.search(text):
            return todos()
    if domain == "time":
        if action and action.get("type") == "intent":
            return reminders(focus={"op": "set", "ids": [action["id"]]})
        if UPCOMING_RX.search(text):
            return reminders()
    return None
