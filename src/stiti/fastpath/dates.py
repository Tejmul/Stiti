"""Hinglish/English time parsing for alarms & reminders. Deterministic, no LLM.

Alarms/reminders are always future, so "kal" = tomorrow and "parso" = day after tomorrow here.
Every result is read back as an absolute date (report risk: kal/parso ambiguity).
"""
from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta

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


# ------------------------------------------------------------------------------------------------ calendar days
# "the 9th" · "9th December" · "December 9" · "18 Nov 2026" · "9 tarikh" · "2026-12-09" · "9/12/2026" — and, for
# text that is already known to be about an event (loose=True): "9/12", "9 ko", "by Friday", "in 3 days",
# "3 din baad", "next week", "this weekend", "kal", "parso". A bare day number means its next occurrence.
MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov",
                                      "dec"], 1)}
_MON = (r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sep(?:t(?:ember)?)?|"
        r"oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)")
_NOT_A_DAY = (r"(?!\s+(?:year|sem|semester|round|chapter|time|floor|class|place|rank|attempt|part|unit|week|day|"
              r"one|step|person|std|standard|grade|edition|half|lesson|module|question|prize|position|try|thing|"
              r"floor|line|page|slide|point|batch|gen|generation)\b)")
_SMALL = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "ten": 10,
          "ek": 1, "do": 2, "teen": 3, "char": 4, "chaar": 4, "paanch": 5, "panch": 5, "das": 10, "dus": 10,
          "couple of": 2, "few": 3}
_NUM = r"(\d{1,2}|" + "|".join(sorted(_SMALL, key=len, reverse=True)) + r")"
_DAY_RX = [
    ("iso", re.compile(r"\b(20\d\d)-(\d{1,2})-(\d{1,2})\b")),
    ("dmy", re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{2}|20\d\d)\b")),
    ("d_mon", re.compile(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?{_MON}\b\.?(?:,?\s+(20\d\d))?")),
    ("mon_d", re.compile(rf"\b{_MON}\.?\s+(\d{{1,2}})(st|nd|rd|th)?\b(?:,?\s+(20\d\d))?")),
    ("tarikh", re.compile(r"\b(\d{1,2})\s*(?:tarikh|tareekh|taarikh|tarik|taareekh)\b")),
    ("ord", re.compile(rf"\b(?:the\s+)?(\d{{1,2}})(?:st|nd|rd|th)\b{_NOT_A_DAY}")),
]
_LOOSE_RX = [
    ("dm", re.compile(r"\b(\d{1,2})/(\d{1,2})\b(?!/)")),
    ("ko", re.compile(r"\b(\d{1,2})\s+(?:ko|se|tak)\b(?!\s*(?:baje|bajkar|\d))")),
    ("rel", re.compile(r"\b(day after tomorrow|parson?|tomorrow|kal|today|aaj|tonight)\b")),
    ("wd", re.compile(r"\b(?:(?:next|this|coming|agle|is)\s+)?(" + "|".join(WEEKDAYS) + r")\b")),
    ("in", re.compile(rf"\b(?:in|after)\s+{_NUM}\s+(days?|weeks?|months?)\b")),
    ("baad", re.compile(rf"\b{_NUM}\s+(din|hafte|hafta|mahine|mahina)\s+(?:baad|mein|me|ke baad)\b")),
    ("next", re.compile(r"\b(next week|agle hafte|next month|agle mahine|this weekend|is weekend)\b")),
]


@dataclass
class DayHit:
    day: date
    start: int          # where the date words sit in the text
    end: int
    exact: bool         # a month / weekday / relative word was said (not just "the 9th")


def _ymd(y: int, m: int, d: int) -> date | None:
    try:
        return date(y, m, d)
    except ValueError:
        return None


def _next_dom(d: int, ref: date) -> date | None:
    """The next day-of-month `d` on or after ref ("the 9th" said on 18 Nov → 9 Dec)."""
    if not 1 <= d <= 31:
        return None
    y, m = ref.year, ref.month
    for _ in range(13):
        if d <= calendar.monthrange(y, m)[1] and date(y, m, d) >= ref:
            return date(y, m, d)
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return None


def _with_month(d: int, mon: str, year: str | None, ref: date) -> date | None:
    m = MONTHS[mon[:3]]
    if year:
        return _ymd(int(year), m, d)
    out = _ymd(ref.year, m, d)
    return out if out and out >= ref else _ymd(ref.year + 1, m, d)


def find_days(text: str, ref: datetime | None = None, loose: bool = False) -> list[DayHit]:
    """Every calendar day named in the text, in reading order. loose=False keeps only unmistakable forms."""
    ref = ref or now()
    today, t = ref.date(), text.lower()
    hits: list[DayHit] = []

    def free(a: int, b: int) -> bool:
        return all(b <= h.start or a >= h.end for h in hits)

    for name, rx in _DAY_RX + (_LOOSE_RX if loose else []):
        for m in rx.finditer(t):
            if not free(m.start(), m.end()):
                continue
            day, exact = None, True
            if name == "iso":
                day = _ymd(int(m[1]), int(m[2]), int(m[3]))
            elif name == "dmy":
                day = _ymd(int(m[3]) + (2000 if len(m[3]) == 2 else 0), int(m[2]), int(m[1]))
            elif name == "d_mon":
                day = _with_month(int(m[1]), m[2], m[3], today)
            elif name == "mon_d":
                if m[1] == "may" and not m[3] and not m[4] and not re.search(r"\b(on|by|from|till|until|before|of)\s+$",
                                                                             t[:m.start()]):
                    continue                        # "I may 5 minute late" is not the 5th of May
                day = _with_month(int(m[2]), m[1], m[4], today)
            elif name in ("tarikh", "ord", "ko"):
                day, exact = _next_dom(int(m[1]), today), name == "tarikh"
            elif name == "dm":
                if int(m[2]) > 12:
                    continue
                day = _ymd(today.year, int(m[2]), int(m[1]))
                if day and day < today:
                    day = _ymd(today.year + 1, int(m[2]), int(m[1]))
            elif name == "rel":
                day = today + timedelta(days={"day after tomorrow": 2, "parso": 2, "parson": 2, "tomorrow": 1,
                                              "kal": 1}.get(m[1], 0))
            elif name == "wd":
                day = today + timedelta(days=(WEEKDAYS[m[1]] - today.weekday()) % 7 or 7)
            elif name in ("in", "baad"):
                n = int(m[1]) if m[1].isdigit() else _SMALL[m[1]]
                unit = m[2][0]
                day = today + timedelta(days=n * (7 if unit in "wh" else 30 if unit == "m" else 1))
            elif name == "next":
                w = m[1]
                day = today + timedelta(days=7 if "week" in w and "weekend" not in w or "hafte" in w
                                        else 30 if "month" in w or "mahine" in w
                                        else (5 - today.weekday()) % 7 or 7)
            if day is not None:
                hits.append(DayHit(day, m.start(), m.end(), exact))
    hits.sort(key=lambda h: h.start)
    for i, h in enumerate(hits[:-1]):               # "from the 9th to the 15th of December": the 9th is December's
        nxt = hits[i + 1]
        if not h.exact and nxt.exact and nxt.start - h.end <= 12 and nxt.day.day != h.day.day:
            moved = _ymd(nxt.day.year, nxt.day.month, h.day.day)
            if moved and moved <= nxt.day:
                h.day, h.exact = moved, True
    return hits


_CLOCKISH = re.compile(r"\d{1,2}(?:[:.]\d{2})?\s*(?:am|pm|a\.m\.|p\.m\.|baje|bajkar|o'?clock)\b|\b\d{1,2}:\d{2}\b|"
                       r"\b(?:at|@)\s+\d{1,2}\b|\b(?:saade|sadhe|sawa|paune|dedh|dhai)\b|"
                       r"\b(?:" + "|".join(HI_HOURS) + r")\s+baje\b", re.I)


def clock_in(text: str) -> tuple[int, int] | None:
    """(hour, minute) when the text names a clock time ("at 3 pm", "shaam 6 baje", "10:30"); None when it doesn't.
    Give it the text WITHOUT its date words (DayHit.start / .end) so "18 November" isn't read as 6 PM."""
    if not _CLOCKISH.search(text):
        return None
    base = datetime(2001, 1, 1, tzinfo=CFG.tz)          # any fixed midnight: only the clock part is used
    when = parse_when(re.sub(r"\b(tomorrow|kal|today|aaj|parson?|next week|agle hafte)\b|\b(" + "|".join(WEEKDAYS)
                             + r")\b", " ", text, flags=re.I), base)
    return (when.hour, when.minute) if when is not None else None


def say_day(d: date, ref: datetime | None = None) -> str:
    """Spoken, always absolute: "Wednesday the 9th of December" (the year only when it isn't this one)."""
    ref = ref or now()
    n = d.day
    suf = "th" if 11 <= n % 100 <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{d:%A} the {n}{suf} of {d:%B}" + (f" {d.year}" if d.year != ref.year else "")


def short_day(d: date, ref: datetime | None = None) -> str:
    """"Wed 2 Dec" — for a list of reminders read back in one breath."""
    ref = ref or now()
    return f"{d:%a} {d.day} {d:%b}" + (f" {d.year}" if d.year != ref.year else "")


def say_clock(hour: int, minute: int = 0) -> str:
    return f"{hour % 12 or 12}" + (f":{minute:02d}" if minute else "") + (" AM" if hour < 12 else " PM")


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
    if not explicit_day and (named := find_days(t, ref)):
        day, explicit_day = named[0].day, True      # "on the 1st" / "18 November" / "9 tarikh ko" (D49)
        t = t[:named[0].start] + " " * (named[0].end - named[0].start) + t[named[0].end:]   # …and it's not a clock

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
