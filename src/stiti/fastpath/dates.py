"""Hinglish/English time parsing for alarms & reminders. Deterministic, no LLM.

Alarms/reminders are always future, so "kal" = tomorrow and "parso" = day after tomorrow here.
Every result is read back as an absolute date (report risk: kal/parso ambiguity).
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta

from ..config import CFG

WEEKDAYS = {d: i for i, d in enumerate(
    ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"])}
WEEKDAYS.update({"somvar": 0, "mangalvar": 1, "budhvar": 2, "guruvar": 3, "shukravar": 4,
                 "shanivar": 5, "ravivar": 6, "itvaar": 6})

REL = re.compile(r"\b(?:in\s+)?(\d+|ek|do|teen|half an?|aadha)\s*(min(?:ute)?s?|minat|hours?|hrs?|ghant[ae]|sec(?:ond)?s?)"
                 r"\s*(?:mein|me|baad|later|from now)?\b", re.I)
CLOCK = re.compile(r"\b(\d{1,2})(?:[:.](\d{2}))?\s*(am|pm|a\.m\.|p\.m\.|baje|bajkar|o'?clock)?\b", re.I)
NUMWORD = {"ek": 1, "do": 2, "teen": 3, "half a": 0.5, "half an": 0.5, "aadha": 0.5}


def now() -> datetime:
    return datetime.now(CFG.tz)


def parse_when(text: str, ref: datetime | None = None) -> datetime | None:
    ref = ref or now()
    t = text.lower()

    m = REL.search(t)
    if m and not re.search(r"\b(baje|am|pm)\b", t):
        n = NUMWORD.get(m.group(1), None)
        n = float(m.group(1)) if n is None else n
        unit = m.group(2)
        if unit.startswith(("h", "ghant")):
            return ref + timedelta(hours=n)
        if unit.startswith("s"):
            return ref + timedelta(seconds=n)
        return ref + timedelta(minutes=n)

    day = ref.date()
    explicit_day = False
    if re.search(r"\b(day after tomorrow|parso|parson)\b", t):
        day, explicit_day = day + timedelta(days=2), True
    elif re.search(r"\b(tomorrow|kal)\b", t):
        # 00:00-03:59 and he hasn't slept: "kal" usually means later today (read back anyway)
        late_night = ref.hour < 4 and re.search(r"\bkal\b", t) and not re.search(r"\btomorrow\b", t)
        day, explicit_day = (day if late_night else day + timedelta(days=1)), True
    elif re.search(r"\b(today|aaj|tonight)\b", t):
        explicit_day = True
    elif "next week" in t or "agle hafte" in t:
        day, explicit_day = day + timedelta(days=7), True
    for name, idx in WEEKDAYS.items():
        if re.search(rf"\b{name}\b", t):
            delta = (idx - ref.weekday()) % 7 or 7
            day, explicit_day = ref.date() + timedelta(days=delta), True
            break

    hour = minute = None
    for m in CLOCK.finditer(t):
        h, mi, suf = int(m.group(1)), int(m.group(2) or 0), (m.group(3) or "").lower()
        if h > 23 or mi > 59:
            continue
        # a bare number counts only with a suffix or a part-of-day word nearby
        if not suf and not re.search(r"\b(subah|morning|shaam|evening|raat|night|dopahar|afternoon)\b", t):
            continue
        hour, minute = h, mi
        if suf.startswith("p") and h < 12:
            hour = h + 12
        elif suf.startswith("a") and h == 12:
            hour = 0
        break

    if hour is not None and hour <= 12:
        if re.search(r"\b(shaam|evening)\b", t) and hour < 12:
            hour += 12
        elif re.search(r"\b(raat|night|tonight)\b", t):
            hour = 0 if hour == 12 else (hour + 12 if hour >= 6 and hour < 12 else hour)
            if hour == 0 and not explicit_day:
                day += timedelta(days=1)
        elif re.search(r"\b(dopahar|afternoon)\b", t) and hour < 12:
            hour = hour + 12 if hour < 6 or hour == 12 else hour

    if hour is None and not explicit_day:
        return None
    if hour is None:
        hour, minute = 9, 0  # day given, no time -> 9 AM default (read back so he can fix it)

    when = datetime(day.year, day.month, day.day, hour, minute or 0, tzinfo=CFG.tz)
    if when <= ref and not explicit_day:
        # ambiguous clock without am/pm/part-of-day: try +12h, else tomorrow
        if hour < 12 and when + timedelta(hours=12) > ref and not re.search(r"\b(am|subah|morning)\b", t):
            when += timedelta(hours=12)
        else:
            when += timedelta(days=1)
    return when


def readback(dt: datetime) -> str:
    today = now().date()
    rel = {0: "today", 1: "tomorrow"}.get((dt.date() - today).days)
    day = f"{rel}, " if rel else ""
    return f"{day}{dt.strftime('%a %d %b')} at {dt.strftime('%I:%M %p').lstrip('0')}"
