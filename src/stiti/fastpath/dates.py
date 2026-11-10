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
HI_HOURS = {"ek": 1, "do": 2, "teen": 3, "char": 4, "chaar": 4, "paanch": 5, "panch": 5, "chhe": 6, "che": 6,
            "chheh": 6, "saat": 7, "aath": 8, "nau": 9, "das": 10, "dus": 10, "gyarah": 11, "gyaarah": 11,
            "barah": 12, "baarah": 12}
WAKE = re.compile(r"\b(alarm|wake|uth|utha|uthana|uthao|jaga|jagana|jagao|subah)\b", re.I)


def _hinglish_clock(t: str) -> str:
    """'saade 6' → 6:30 · 'sawa 7' → 7:15 · 'paune 8' → 7:45 · 'dedh' → 1:30 · 'dhai' → 2:30 · 'saat baje' → 7 baje."""
    t = re.sub(r"\b(" + "|".join(HI_HOURS) + r")(?=\s*(baje|bajke|bajkar)\b)", lambda m: str(HI_HOURS[m.group(1)]), t)
    t = re.sub(r"\b(\d{1,2}) bajne (?:mein|me|main) (\d{1,2})\b",           # "7 bajne mein 10" → 6:50
               lambda m: f"{(int(m.group(1)) - 1) or 12}:{60 - int(m.group(2)):02d} baje", t)
    t = re.sub(r"\bdedh\b", "1:30", t)
    t = re.sub(r"\b(dhai|dhaai|adhai)\b", "2:30", t)
    hour = r"(\d{1,2}|" + "|".join(HI_HOURS) + r")"
    num = lambda x: int(x) if x.isdigit() else HI_HOURS[x]  # noqa: E731
    t = re.sub(rf"\b(saade|sadhe|saadhe)\s+{hour}\b", lambda m: f"{num(m.group(2))}:30", t)
    t = re.sub(rf"\b(sawa|savva|sava)\s+{hour}\b", lambda m: f"{num(m.group(2))}:15", t)
    t = re.sub(rf"\b(paune|pone)\s+{hour}\b", lambda m: f"{(num(m.group(2)) - 1) or 12}:45", t)
    return t


def now() -> datetime:
    return datetime.now(CFG.tz)


def parse_when(text: str, ref: datetime | None = None) -> datetime | None:
    ref = ref or now()
    t = _hinglish_clock(text.lower())

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
        # a bare number counts only with a suffix, a part-of-day word nearby, a clock form like 6:30, or "at 4"
        # ("remind me at 4 to…": the next sensible 4 — daytime 1–6 means PM — instead of asking "morning or evening?")
        if not suf and not m.group(2) and not re.search(r"\b(subah|morning|shaam|evening|raat|night|dopahar|afternoon)\b", t) \
                and not re.search(r"\b(at|by|around|till|until|before)\s+$", t[:m.start()]):
            continue
        hour, minute = h, mi
        if suf in ("baje", "bajkar", "o'clock", "") and 1 <= h <= 6 and not re.search(
                r"\b(subah|morning|raat|night|am|a\.m\.)\b", t) and not WAKE.search(t):
            hour = h + 12            # "kal 2 baje" = 2 PM (nobody means 2 AM without saying raat); wake-ups stay AM
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
        if hour < 12 and when + timedelta(hours=12) > ref and not re.search(r"\b(am|subah|morning|raat|night|tonight)\b", t) \
                and not WAKE.search(t):
            when += timedelta(hours=12)
        else:
            when += timedelta(days=1)
    return when


def readback(dt: datetime) -> str:
    today = now().date()
    rel = {0: "today", 1: "tomorrow"}.get((dt.date() - today).days)
    day = f"{rel}, " if rel else ""
    return f"{day}{dt.strftime('%a %d %b')} at {dt.strftime('%I:%M %p').lstrip('0')}"


def say_when(dt: datetime) -> str:
    """Spoken form for confirmations: "today at 4 PM" · "tomorrow at 7:30 AM" · "Fri 14 Nov at 9 AM"."""
    days = (dt.date() - now().date()).days
    day = {0: "today", 1: "tomorrow"}.get(days) or dt.strftime("%a %d %b").replace(" 0", " ")
    clock = dt.strftime("%I:%M %p").lstrip("0").replace(":00", "")
    return f"{day} at {clock}"


def second_person(s: str) -> str:
    """"start my resume" → "start your resume" (she reads his words back to him)."""
    for a, b in ((r"\bmy\b", "your"), (r"\bmyself\b", "yourself"), (r"\bmine\b", "yours"), (r"\bI'?m\b", "you're"),
                 (r"\bmera\b", "tera"), (r"\bmeri\b", "teri")):
        s = re.sub(a, b, s, flags=re.I)
    return s
