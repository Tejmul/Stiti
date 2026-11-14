"""Proactive layer: morning brief + Nudge Gate (report §Proactive nudges).

LLM agents over-intervene; Stiti gets a daily budget of unprompted nudges (default 4, range 3–5),
fires only at natural breakpoints (start of a session / first message of the day), and logs
accept/dismiss for later bandit learning. User-set alarms are never counted or suppressed.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta

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


def _clock(t: datetime) -> str:
    return f"{t.astimezone(CFG.tz):%I:%M}".lstrip("0").replace(":00", "")


def _and(items: list[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def _default_events(now: datetime) -> list[dict]:
    from ..connectors import eventkit
    return eventkit.today_events_quiet(now)


def _default_weather():
    from ..connectors import weather
    return weather.cached()


def _default_headline() -> str | None:
    from ..connectors import live
    return live.cached_headline()


def _agenda(now: datetime, events: list[dict], low_energy: bool) -> str:
    """One sentence: the next 1–2 timed events + how many to-dos / reminders today."""
    ahead = [e for e in events if not e.get("all_day") and e["start"] >= now - timedelta(minutes=5)][:2]
    top = one("""SELECT title FROM tasks WHERE status='open' ORDER BY due NULLS LAST, created_at LIMIT 1""")
    if low_energy:
        if top:
            return f"Just one thing matters today: {handlers.second_person(top['title'])}."
        return "Nothing you have to do today — take it easy."
    n_todo = one("SELECT count(*) n FROM tasks WHERE status='open'")["n"]
    n_rem = one("""SELECT count(*) n FROM intents WHERE user_set AND state IN ('pending','armed')
                   AND kind IN ('alarm','reminder') AND fire_at > %s
                   AND fire_at < date_trunc('day', %s::timestamptz AT TIME ZONE %s) AT TIME ZONE %s + interval '1 day'""",
                (now, now, CFG.tz.key, CFG.tz.key))["n"]
    counts = []
    if n_todo:
        counts.append("one to-do" if n_todo == 1 else f"{n_todo} to-dos")
    if n_rem:
        counts.append("a reminder" if n_rem == 1 else f"{n_rem} reminders")
    if ahead:
        s = "You've got " + _and([f"{e['title']} at {_clock(e['start'])}" for e in ahead])
        return s + (f", plus {_and(counts)} today." if counts else ".")
    if counts:
        s = f"You have {_and(counts)} today"
        if top and n_todo:
            s += f" — first up, {handlers.second_person(top['title'])}"
        return s + "."
    return "Nothing on the calendar and no to-dos — an open day."


def morning_brief(now: datetime | None = None, low_energy: bool = False, name: str | None = None, *,
                  events=None, weather=None, headline=None) -> str | None:
    """Once per day, on his first wake / hello (a natural breakpoint). At most three short sentences:
    greeting + weather · the next 1–2 calendar events + to-do / reminder count · one cached headline (or a habit).
    Nothing here waits on the network: weather and news come from caches the background already filled.
    events(now) / weather() / headline() are injectable for tests."""
    now = now or datetime.now(CFG.tz)
    if one("SELECT 1 FROM nudges WHERE kind='morning_brief' AND sent_at >= date_trunc('day', now() AT TIME ZONE %s) AT TIME ZONE %s",
           (CFG.tz.key, CFG.tz.key)) or not allowed():
        return None
    greet = "Good morning" if now.hour < 12 else "Hey" if now.hour < 17 else "Good evening"
    hi = f"{greet}{', ' + name if name else ''}"
    try:
        w = (weather or _default_weather)()
    except Exception:
        w = None
    if w is not None:
        from ..connectors import weather as wx
        line = wx.one_liner(w, now)
        parts = [f"{hi} — {line[0].lower()}{line[1:]}"]          # "Good morning, Tejmul — it's 24 and clear in Pune…"
    else:
        parts = [f"{hi} — new week, fresh start." if now.weekday() == 0 else f"{hi}!"]
    try:
        evs = (events or _default_events)(now)
    except Exception:
        evs = []
    parts.append(_agenda(now, evs, low_energy))
    if not low_energy:
        try:
            h = (headline or _default_headline)()
        except Exception:
            h = None
        if h:
            parts.append(f"In the news: {h}.")
        else:
            hp = habits.due_prompts()
            if hp:
                parts.append(f"And {hp[0]['name']}{' ' + hp[0]['cue'] if hp[0]['cue'] else ''} when you get a chance.")
    text = " ".join(parts)
    record("morning_brief", {"text": text})
    return text
