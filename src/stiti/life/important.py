"""Important things (D49): she notices what matters, asks once, and books it. No LLM anywhere on this path.

  notice   brain/notice.py finds a dated event / deadline in his words, in mail (sender + subject + first lines) and in
           documents he ingests. One row per thing in `noticed` (never asked twice).
  ask      his own short, calm sentence → one question in the same turn. Everything else (mail, documents, a long or
           upset sentence) → one spoken question through the proactive gate, at most MAX_ASKS_PER_DAY a day; ignored
           → it waits in the noticed list ("what did you notice?").
  book     "yes" → calendar entry + reminders ahead (defaults by kind, or his own: "remind me on the 1st",
           "two days before") → read back exactly what was written. Exams / deadlines / interviews: one follow-up,
           "Want a preparation plan, and when do you want to start?".
           "no" → dropped for good. "just note it" → a fact, no calendar. "put it on my list" → a to-do with the date.
  direct   "my exams are on the 9th, give me a reminder on the 1st" → no question: booked and read back.

The open question is a row (stage + asked_at), not process state: it survives a restart. Mail and document text is
untrusted — pattern-matched only, never sent to an LLM, and nothing is written from it without his yes.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta

from ..brain import notice
from ..brain.notice import Item
from ..config import CFG
from ..db import one, q
from ..fastpath import dates

ANSWER_WINDOW = timedelta(minutes=10)   # a bare "yes" counts this long after she asked (and only if nothing else was said)
UNDO_WINDOW = timedelta(minutes=5)
MAX_ASKS_PER_DAY = 2                    # spoken "is this important?" questions she starts herself
ASK_GAP = timedelta(minutes=30)
SHORT_WORDS = 22                        # a longer sentence is about more than the date: don't answer it with a form
MAIL_EVERY_S = 15 * 60
PREP_KINDS = ("exam", "deadline", "interview")
PREP_MIN_AHEAD = timedelta(days=2)

# reminders ahead, by kind: ("days", n, hour) = n days before at that hour · ("hours", n) = n hours before (needs a
# time; else that morning at 8) · ("morning", hour) = the day itself
DEFAULTS: dict[str, list[tuple]] = {
    "exam": [("days", 7, 9), ("days", 1, 18), ("morning", 7)],
    "deadline": [("days", 2, 9), ("days", 1, 9)],
    "bill": [("days", 2, 9), ("days", 1, 9)],
    "interview": [("days", 1, 19), ("hours", 1)],
    "meeting": [("days", 1, 19), ("hours", 1)],
    "appointment": [("days", 1, 19), ("hours", 1)],
    "event": [("days", 1, 19), ("hours", 1)],
    "travel": [("days", 1, 18), ("hours", 3)],
    "birthday": [("morning", 9)],
    "result": [("morning", 9)],
}
AHEAD = {"exam": "a few days before", "deadline": "a couple of days before", "bill": "a couple of days before",
         "travel": "the day before", "birthday": "that morning", "result": "that morning"}

YES = re.compile(r"^\W*(?:(?:hey|ok|okay|oh|hmm|stiti)\W+)*(?:yes|yeah|yep|yup|ya|haan?|han|ha|ji|sure|ok(?:ay)?|please|"
                 r"kar do|kar de|do it|do that|go ahead|save it|book it|add it|put it|it is|it'?s important|important|"
                 r"zaroori|bilkul|of course|definitely|theek hai|thik hai|sounds good|why not|chalo|absolutely)\b", re.I)
NO = re.compile(r"^\W*(?:(?:hey|ok|okay|oh|hmm|stiti)\W+)*(?:no|nope|nah|nahi|nahin|not (?:important|needed|now|really|"
                r"required)|leave it|rehne do|chhodo|chodo|skip|don'?t|mat|ignore|it'?s fine|no need|zaroorat nahi|"
                r"never ?mind|drop it|forget it)\b|\bnot (?:that |so |very )?important\b|\bzaroori nahi\b", re.I)
NOTE = re.compile(r"\b(?:note|remember|yaad rakh\w*|keep (?:it|that) in mind)\b|somewhere else", re.I)
NO_CAL = re.compile(r"\b(?:no|not (?:on|in)(?: the| my)?|without|bina) calend[ae]r\b|calend[ae]r (?:pe |par |mein |me )?"
                    r"(?:nahi|mat)\b", re.I)
TODO = re.compile(r"\b(?:to-?do|todos?|task|my list|the list|list (?:mein|me|pe))\b", re.I)
NO_REMINDERS = re.compile(r"\b(?:no|without|bina|don'?t need) reminders?\b|\b(?:only|just|sirf|bas) (?:the |on the |on my )?"
                          r"calend[ae]r\b", re.I)
REMIND = re.compile(r"\b(?:give me (?:a |one |the )?reminders?|remind me|set (?:a |my |the )?reminders?|put (?:a )?reminders?|"
                    r"(?:i want|i need|need) (?:a )?reminders?|reminders? (?:de(?:na| do| dena)?|laga\w*(?: do| dena)?|"
                    r"set kar\w*(?: do| dena)?|chahiye)|(?:mujhe )?yaad dila\w*(?: dena| do)?)\b", re.I)
TO_CAL = re.compile(r"\b(?:put|add|save|mark|book|note|daal\w*|dal\w*)\b.{0,25}\bcalend[ae]r\b|"
                    r"\bcalend[ae]r (?:pe|par|mein|me) (?:daal|dal|laga|add)\w*", re.I)
_N = dates._NUM
N_BEFORE = re.compile(rf"\b{_N}\s+(days?|din|weeks?|hafte|hafta|hours?|hrs?|ghante|ghanta)\s+"
                      r"(?:before|pehle|pahle|prior|earlier|in advance|ahead)\b", re.I)
DAY_BEFORE = re.compile(r"\b(?:the\s+)?(?:previous day|day\s+(?:before|pehle|pahle))\b", re.I)
EVE_BEFORE = re.compile(r"\b(?:night|evening|raat|shaam)\s+(?:before|pehle|pahle)\b", re.I)
MORNING_OF = re.compile(r"\b(?:that|same|us|usi)\s+(?:din\s+)?(?:morning|subah)\b|\bmorning of\b|\bon the day\b|\bsame day\b|"
                        r"\busi din\b", re.I)
FIX_DATE = re.compile(r"\b(?:actually|it'?s|its|it is|not|nahi|wrong|galat|i meant|i said)\b", re.I)
UNDO = re.compile(r"^\W*(?:undo|cancel (?:that|it|all that|those|them)|remove (?:that|it|those|them)|nahi nahi|galat|"
                  r"that'?s wrong|wrong|no,? (?:that'?s )?(?:wrong|not right)|hata do|mat karo|delete (?:that|it|those))\b",
                  re.I)
LIST_ASK = re.compile(r"\b(?:anything|something|kuch|koi)\s+(?:important|zaroori)\b|\bwhat (?:did|have) you notice\w*\b|"
                      r"\bwhat'?s important\b|\b(?:did|have) you notice\w* (?:anything|something)\b|"
                      r"\b(?:show|tell|read) (?:me )?(?:the |my )?noticed\b|\bnoticed list\b|\bkya (?:notice|dekha)\b.*\b(?:tumne|tune)\b|"
                      r"\bimportant (?:kuch|kya) hai\b", re.I)
MAIL_ASK = re.compile(r"\b(?:check|scan|look (?:at|through|in)|go through|read|dekh\w*)\b.{0,25}\b(?:mails?|emails?|inbox)\b"
                      r".{0,40}\b(?:important|matters?|dates?|deadlines?|zaroori|events?|exams?|interviews?)\b|"
                      r"\b(?:anything|something|kuch) (?:important|zaroori)\b.{0,20}\b(?:mails?|emails?|inbox)\b", re.I)
OFF = re.compile(r"\b(?:stop|don'?t|do not|mat|band karo)\b.{0,25}\b(?:ask\w*|pooch\w*|puch\w*)\b.{0,40}"
                 r"\b(?:important|calendar|mails?|dates?|notice\w*)\b", re.I)
ON = re.compile(r"\b(?:start|you can|feel free to|phir se)\b.{0,15}\b(?:ask\w*|pooch\w*)\b.{0,40}\b(?:important|calendar)\b",
                re.I)
AGAIN = re.compile(r"^\W*(?:what|sorry|pardon|huh|hmm|kya|haan\?|come again|say that again|repeat(?: that)?|phir se(?: bolo)?|"
                   r"what did you say|didn'?t (?:get|catch) (?:that|it))\W*$", re.I)
OTHER_CMD = re.compile(r"\b(?:alarms?|timers?|to-?dos?|wake me|add .{1,40} to (?:my|the) list)\b", re.I)
REFER = re.compile(r"\b(?:save|book|add|put|note|keep|mark|important|zaroori|calend[ae]r|yes|haan)\b", re.I)
POINTS = re.compile(r"\b(?:that|this|woh|wo|us|one|wala|wali|both|all|dono|sab|first|second|third|1st|2nd|3rd|pehla|"
                    r"doosra|dusra|teesra)\b", re.I)
ORDINAL = {"first": 0, "1st": 0, "pehla": 0, "pehle wala": 0, "second": 1, "2nd": 1, "doosra": 1, "dusra": 1,
           "third": 2, "3rd": 2, "teesra": 2}
MAIL_HINT = ("I can't read your mail yet. Put MAIL_ADDRESS and MAIL_APP_PASSWORD, a Google app password, in the .env "
             "file and restart me.")
UPSET = re.compile(r"\b(?:stress\w*|tens(?:ed|ion)|scared|panic\w*|anxious|worried|overwhelm\w*|can'?t (?:do|handle|take|cope)|"
                   r"crying|depress\w*|freaking|screwed|fed up|exhausted|hopeless|dar lag\w*|ghabra\w*|pareshan|"
                   r"dimag kharab|pagal ho)\b", re.I)
COLS = ("id, what, kind, when_at, has_time, source, source_ref, source_label, heard, meta, confidence, privacy, status, "
        "stage, asked_at, asked_via, answered_at, event_id, reminder_ids, prep_intent_id, task_id, fact_id")


@dataclass
class Out:
    text: str
    chunk: str | None = None            # hand over to the step-by-step chunker with this goal (the engine owns it)


# ------------------------------------------------------------------------------------------------ the outside world
# (tests swap these three: no real calendar is ever touched)
def add_event(title: str, start: datetime, minutes: int = 60, all_day: bool = False, notes: str | None = None) -> str | None:
    if os.getenv("STITI_EVENTKIT", "on") == "off":
        return None
    from ..connectors import eventkit
    return eventkit.add_event(title, start, minutes, notes, all_day=all_day)


def cal_events(start: datetime, end: datetime) -> list[dict]:
    from ..connectors import eventkit
    return eventkit.events_quiet(start, end)


def remove_event(title: str, day: datetime) -> int:
    if os.getenv("STITI_EVENTKIT", "on") == "off":
        return 0
    from ..connectors import eventkit
    return eventkit.cancel_event(title, day)


def _in_call() -> bool:
    from . import proactive
    return proactive.in_call()


# ------------------------------------------------------------------------------------------------ words
def _now(now: datetime | None) -> datetime:
    return now or datetime.now(CFG.tz)


def _when(r: dict) -> datetime:
    return r["when_at"].astimezone(CFG.tz)


def _name() -> str:
    """What she calls him — from the profile, never a hard-coded name ("" before the intro)."""
    try:
        from .. import profile
        return profile.call() if (profile.get("name") or profile.get("call_me")) else ""
    except Exception:
        return ""


def subject(r: dict) -> str:
    """"your exams" · "your mom's birthday" · "Riya's birthday" · "the fee payment"."""
    what = r["what"]
    if r["source"] != "said" and what[:1].isupper() and not what.split()[0].isupper() and "'" not in what.split()[0]:
        what = what[0].lower() + what[1:]
    if (r["meta"] or {}).get("mine"):
        return f"your {what}"
    return what if re.match(r"[A-Z][\w]*'s\b", what) else f"the {what}"


def _verb(r: dict) -> str:
    plural = bool((r["meta"] or {}).get("plural"))
    if (r["meta"] or {}).get("starts"):
        return "start" if plural else "starts"
    if r["kind"] in ("deadline", "bill"):
        return "are due" if plural else "is due"
    if r["kind"] == "result":
        return "come out" if plural else "comes out"
    return "are" if plural else "is"


def _at(r: dict) -> str:
    w = _when(r)
    return f" at {dates.say_clock(w.hour, w.minute)}" if r["has_time"] else ""


def title(r: dict) -> str:
    t = r["what"][:1].upper() + r["what"][1:]
    meta = r["meta"] or {}
    return t + ((" start" if meta.get("plural") else " starts") if meta.get("starts")
                else " due" if r["kind"] in ("deadline", "bill") else "")


def statement(r: dict, now: datetime) -> str:
    s = subject(r)
    return f"{s[:1].upper()}{s[1:]} {_verb(r)} on {dates.say_day(_when(r).date(), now)}{_at(r)}."


def ask_text(r: dict, now: datetime) -> str:
    """The one question. His own words: read back + offer. Mail / document: say where it came from, ask if it matters."""
    day = dates.say_day(_when(r).date(), now) + _at(r)
    n = _name()
    hey = f"{n}, " if n else ""
    if r["source"] == "mail":
        line = f"{hey}there's a mail from {r['source_label'] or 'someone'} about {_about(r)} on {day}."
    elif r["source"] == "document":
        line = f"{hey}your document “{r['source_label'] or 'that file'}” mentions {_about(r)} on {day}."
    elif r["asked_via"] == "turn" or r.get("_turn"):
        return (f"{statement(r, now)} Want me to put that on the calendar and remind you "
                f"{AHEAD.get(r['kind'], 'before it')}?")
    else:
        return f"{hey}you mentioned {subject(r)} on {day}. Want me to put that on the calendar and remind you before?"
    line = line[:1].upper() + line[1:]
    return f"{line} Is that important? I can put it on the calendar and remind you before."


def _about(r: dict) -> str:
    s = subject(r)
    if s.startswith("the "):
        w = s[4:]
        return ("an " if w[:1].lower() in "aeiou" else "a ") + w if not (r["meta"] or {}).get("plural") else w
    return s


# ------------------------------------------------------------------------------------------------ state
def _row(rid: int) -> dict | None:
    return one(f"SELECT {COLS} FROM noticed WHERE id=%s", (rid,))


def disabled() -> bool:
    r = one("SELECT disabled FROM nudge_arms WHERE kind='noticed'")
    return bool(r and r["disabled"])


def _set_disabled(off: bool) -> None:
    q("""INSERT INTO nudge_arms(kind, disabled) VALUES ('noticed', %s)
         ON CONFLICT (kind) DO UPDATE SET disabled = EXCLUDED.disabled, updated_at = now()""", (off,))


def store(it: Item, privacy: int = 1, reuse: tuple[str, ...] = ("new",)) -> dict | None:
    """Remember a noticed thing. None when it is already known and settled (asked / declined / booked): she never
    brings the same thing up twice."""
    row = one(f"""INSERT INTO noticed(what, kind, when_at, has_time, source, source_ref, source_label, heard, meta,
                                      confidence, privacy)
                  VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (source_ref) DO NOTHING RETURNING {COLS}""",
              (it.what, it.kind, it.when, it.has_time, it.source, it.key, it.label, it.heard, json.dumps(it.meta),
               it.confidence, privacy))
    if row:
        return row
    old = one(f"SELECT {COLS} FROM noticed WHERE source_ref=%s", (it.key,))
    return old if old and old["status"] in reuse else None


def _words(s: str) -> set[str]:
    return {w[:-1] if w.endswith("s") and len(w) > 4 else w for w in re.findall(r"[a-z]{4,}", (s or "").lower())} \
        - {"your", "with", "from", "that", "this", "have", "about", "start", "starts", "tomorrow", "today", "reminder"}


def already_booked(what: str, when: datetime, now: datetime) -> bool:
    """Is it on the calendar that day, or already a reminder around then? Then there is nothing to ask."""
    mine = _words(what)
    if not mine:
        return False
    day = when.replace(hour=0, minute=0, second=0, microsecond=0)
    try:
        if any(mine & _words(e.get("title", "")) for e in cal_events(day, day + timedelta(days=1))):
            return True
    except Exception:
        pass
    for r in q("""SELECT payload FROM intents WHERE user_set AND kind='reminder' AND state IN ('pending','armed')
                  AND fire_at > %s AND fire_at BETWEEN %s AND %s""",
               (now, day - timedelta(days=1), day + timedelta(days=1))):
        if mine & _words(" ".join(str(r["payload"].get(k) or "") for k in ("label", "say"))):
            return True
    return False


def _mark_asked(rid: int, now: datetime, via: str) -> None:
    q("UPDATE noticed SET stage=NULL WHERE stage IS NOT NULL AND id<>%s", (rid,))
    q("UPDATE noticed SET status='asked', stage='important', asked_at=%s, asked_via=%s WHERE id=%s", (now, via, rid))


def mark_asked(rid: int, now: datetime | None = None, via: str = "voice") -> None:
    """The proactive question was delivered (voice / banner / Telegram): it is never asked again."""
    _mark_asked(rid, _now(now), via)


def open_question(now: datetime | None = None) -> dict | None:
    """The question she is waiting on right now (asked ≤ 10 min ago and nothing else said since)."""
    now = _now(now)
    return one(f"""SELECT {COLS} FROM noticed WHERE stage IS NOT NULL AND asked_at >= %s AND asked_at <= %s
                   ORDER BY asked_at DESC LIMIT 1""", (now - ANSWER_WINDOW, now + timedelta(minutes=1)))


def settle(now: datetime | None = None) -> None:
    """He talked about something else: the question is no longer "the last thing she said". The item stays in the
    noticed list; a bare "yes" later must not book it."""
    q("UPDATE noticed SET stage=NULL WHERE stage IS NOT NULL")


def expire(now: datetime | None = None) -> None:
    q("UPDATE noticed SET status='expired', stage=NULL WHERE status IN ('new','asked') AND when_at < %s", (_now(now),))


def waiting(now: datetime | None = None) -> list[dict]:
    """Noticed, not answered yet, still ahead — soonest first."""
    return q(f"""SELECT {COLS} FROM noticed WHERE status IN ('new','asked') AND when_at > %s ORDER BY when_at, id""",
             (_now(now),))


# ------------------------------------------------------------------------------------------------ reminders
def default_times(r: dict, now: datetime) -> list[datetime]:
    when, out = _when(r), []
    day = when.replace(hour=0, minute=0, second=0, microsecond=0)
    for spec in DEFAULTS.get(r["kind"], DEFAULTS["event"]):
        if spec[0] == "days":
            t = (day - timedelta(days=spec[1])).replace(hour=spec[2])
        elif spec[0] == "hours":
            t = when - timedelta(hours=spec[1]) if r["has_time"] else day.replace(hour=8)
        else:
            t = day.replace(hour=spec[1])
            if r["has_time"] and when <= t + timedelta(minutes=30):       # an 8 AM exam: "that morning" is 90 min before
                t = when - timedelta(minutes=90)
        out.append(t)
    return _valid(out, r, now)[0]


def _valid(times: list[datetime], r: dict, now: datetime) -> tuple[list[datetime], int]:
    """Only reminders that are still ahead and before the thing itself. Returns (kept, dropped)."""
    when = _when(r)
    last = when if r["has_time"] else when.replace(hour=23, minute=59)
    keep = sorted({t for t in times if now + timedelta(minutes=5) < t < last})
    return keep, len(set(times)) - len(keep)


def his_times(text: str, r: dict, now: datetime) -> tuple[list[datetime], int] | None:
    """Reminders in his own words: "on the 1st" · "two days before" · "a week before and the day before" ·
    "ek din pehle shaam 6 baje" · "that morning". None = he named none. Returns (times still valid, dropped)."""
    when = _when(r)
    day = when.replace(hour=0, minute=0, second=0, microsecond=0)
    fixed: list[datetime] = []          # exact moments ("3 hours before", "the evening before")
    days: list[datetime] = []           # whole days: at 9 AM, or at the clock he names
    spans: list[tuple[int, int]] = []
    for m in N_BEFORE.finditer(text):
        n = int(m[1]) if m[1].isdigit() else dates._SMALL[m[1].lower()]
        unit = m[2].lower()
        spans.append(m.span())
        if unit in ("hour", "hours", "hr", "hrs", "ghante", "ghanta"):
            if r["has_time"]:
                fixed.append(when - timedelta(hours=n))
            else:
                days.append(day)                    # no time known: that morning instead
        else:
            days.append(day - timedelta(days=n * (7 if unit.startswith(("week", "haft")) else 1)))
    for m in DAY_BEFORE.finditer(text):
        if not any(a <= m.start() < b for a, b in spans):
            spans.append(m.span())
            days.append(day - timedelta(days=1))
    for m in EVE_BEFORE.finditer(text):
        spans.append(m.span())
        fixed.append((day - timedelta(days=1)).replace(hour=19))
    for m in MORNING_OF.finditer(text):
        spans.append(m.span())
        fixed.append(day.replace(hour=7) if not r["has_time"] or when.hour > 8 else when - timedelta(minutes=90))
    rest = text
    for a, b in spans:
        rest = rest[:a] + " " * (b - a) + rest[b:]
    for h in dates.find_days(rest, now, loose=True):
        days.append(datetime(h.day.year, h.day.month, h.day.day, tzinfo=CFG.tz))
        rest = rest[:h.start] + " " * (h.end - h.start) + rest[h.end:]
    if not fixed and not days:
        return None
    clock = dates.clock_in(rest) or (9, 0)
    return _valid(fixed + [d.replace(hour=clock[0], minute=clock[1]) for d in days], r, now)


def _label(r: dict, at: datetime) -> str:
    """What the reminder says when it rings: "your exams start tomorrow" · "your interview is today at 3 PM"."""
    days = (_when(r).date() - at.date()).days
    day = {0: "today", 1: "tomorrow"}.get(days) or f"on {dates.short_day(_when(r).date(), at)}"
    return f"{subject(r)} {_verb(r)} {day}{_at(r)}"


def _say_times(times: list[datetime], r: dict, now: datetime) -> str:
    when, parts = _when(r), []
    for t in times:
        d = (when.date() - t.date()).days
        clock = "" if t.hour == 9 and t.minute == 0 and d > 1 else f" at {dates.say_clock(t.hour, t.minute)}"
        near = {0: "today", 1: "tomorrow"}.get((t.date() - now.date()).days)
        if near and not (d == 0 and r["has_time"] and when - t <= timedelta(hours=6)):
            parts.append(f"{near} at {dates.say_clock(t.hour, t.minute)}")
        elif d == 0 and r["has_time"] and when - t <= timedelta(hours=6):
            mins = round((when - t).total_seconds() / 60)
            parts.append("an hour before" if mins == 60 else f"{mins // 60} hours before" if mins % 60 == 0
                         else f"{mins} minutes before")
        elif d == 0:
            parts.append(f"that morning{clock}")
        elif d == 1:
            parts.append(f"the day before{clock}")
        else:
            parts.append(f"on {dates.short_day(t.date(), now)}{clock}")
    return parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]


# ------------------------------------------------------------------------------------------------ follow-through
def book(r: dict, now: datetime, times: list[datetime] | None = None, *, cal: bool = True, rem: bool = True,
         dropped: int = 0, answer: str = "") -> str:
    """Write it — calendar entry, reminders — and say back exactly what was written, nothing more."""
    from . import alarms
    when = _when(r)
    event_id = None
    if cal and not r["event_id"]:
        try:
            event_id = add_event(title(r), when, 60, all_day=not r["has_time"],
                                 notes="Added by Stiti" + (f" — from a mail from {r['source_label']}" if r["source"] == "mail" else ""))
        except Exception as e:
            print(f"[important] calendar: {type(e).__name__}: {e}", flush=True)
    ids: list[int] = []
    if rem:
        for t in (default_times(r, now) if times is None else times):
            try:
                rid = alarms.create_at(t, _label(r, t), heard=r["heard"])
            except Exception as e:
                print(f"[important] reminder: {type(e).__name__}: {e}", flush=True)
                rid = None
            if rid:
                ids.append(rid)
    set_times = [x["fire_at"].astimezone(CFG.tz) for x in q(
        "SELECT fire_at FROM intents WHERE id = ANY(%s) ORDER BY fire_at", (ids,))] if ids else []
    on_cal = bool(event_id or (cal and r["event_id"]))
    subj = subject(r)
    Subj = subj[:1].upper() + subj[1:]
    day = dates.say_day(when.date(), now) + _at(r)
    be = "are" if (r["meta"] or {}).get("plural") else "is"
    if not on_cal and not set_times:                # nothing was written: say so, claim nothing
        if cal and rem:
            why = "I couldn't put it on your calendar, and " + (
                "it's too close for a reminder." if times is None else "that reminder time has already passed.")
        elif cal:
            why = "I couldn't put it on your calendar."
        else:
            why = "That reminder time has already passed."
        q("UPDATE noticed SET stage=NULL, answer=%s WHERE id=%s", (answer[:200], r["id"]))
        return f"{why} Nothing is booked for {subj}."
    told = _say_times(set_times, r, now) if set_times else ""
    if on_cal and set_times:
        text = f"Done. {Subj} {be} on the calendar for {day}, and I'll remind you {told}."
    elif on_cal:
        text = f"Done. {Subj} {be} on the calendar for {day}." + (
            "" if not rem else " No reminder — it's too close for one." if times is None
            else " That reminder time has already passed, so no reminder.")
    elif cal:
        text = f"I couldn't put {subj} on your calendar, but I'll remind you {told}."
    else:
        text = f"Done. I'll remind you {told} about {subj}."
    if dropped and set_times:
        text += " One time you said has already passed, so I skipped it."
    prep = r["kind"] in PREP_KINDS and when - now >= PREP_MIN_AHEAD and not r["prep_intent_id"] and r["status"] != "accepted"
    q("""UPDATE noticed SET status='accepted', stage=%s, asked_at=%s, answered_at=%s, answer=%s,
                event_id=COALESCE(%s, event_id), reminder_ids = reminder_ids || %s::bigint[] WHERE id=%s""",
      ("prep" if prep else None, now, now, answer[:200], event_id, ids, r["id"]))
    if prep:
        text += (" Want a preparation plan, and when do you want to start?" if r["kind"] != "deadline"
                 else " Want a plan for it, and when do you want to start?")
    return text


def note(r: dict, now: datetime, answer: str = "") -> str:
    """"Just note it" / "save it somewhere else": a fact in her memory, nothing on the calendar."""
    from ..brain import factstore
    from ..brain.lifeupdate import _me, _owner
    subj = subject(r)
    who = _owner()
    third = re.sub(r"^your\b", f"{who}'s", subj)
    fact = f"{third[:1].upper()}{third[1:]} {_verb(r)} on {_when(r):%-d %B %Y}{_at(r)}."
    try:
        _, fid = factstore.add(_me(), "noted", fact, obj_literal=fact, confidence=0.9, privacy=r["privacy"],
                               origin="conversation" if r["source"] == "said" else "stiti")
        factstore.refresh(background=True)
    except Exception as e:
        print(f"[important] note: {type(e).__name__}: {e}", flush=True)
        fid = None
    if not fid:
        return "I couldn't save that just now. Tell me once more in a moment."
    q("UPDATE noticed SET status='noted', stage=NULL, answered_at=%s, answer=%s, fact_id=%s WHERE id=%s",
      (now, answer[:200], fid, r["id"]))
    return f"Noted — {subj} {_verb(r)} on {dates.say_day(_when(r).date(), now)}{_at(r)}. Nothing on the calendar."


def to_list(r: dict, now: datetime, answer: str = "") -> str:
    row = one("INSERT INTO tasks(title, due, source, privacy) VALUES (%s,%s,'noticed',%s) RETURNING id",
              (title(r), _when(r), r["privacy"]))
    if not row:
        return "I couldn't add that just now."
    try:
        from .. import cards
        cards.note("added", "task", row["id"])
    except Exception:
        pass
    q("UPDATE noticed SET status='noted', stage=NULL, answered_at=%s, answer=%s, task_id=%s WHERE id=%s",
      (now, answer[:200], row["id"], r["id"]))
    return f"Added to your list: {title(r)}, {dates.short_day(_when(r).date(), now)}. Nothing on the calendar."


def decline(r: dict, now: datetime, answer: str = "") -> str:
    q("UPDATE noticed SET status='declined', stage=NULL, answered_at=%s, answer=%s WHERE id=%s", (now, answer[:200], r["id"]))
    return "Okay, I'll leave it. I won't ask about that one again."


def undo(r: dict, now: datetime) -> str:
    """Right after a booking: "undo" / "that's wrong" takes back everything she wrote for it."""
    ids = list(r["reminder_ids"] or []) + ([r["prep_intent_id"]] if r["prep_intent_id"] else [])
    gone = q("UPDATE intents SET state='cancelled' WHERE id = ANY(%s) AND state IN ('pending','armed') RETURNING id, ek_identifier",
             (ids,)) if ids else []
    if os.getenv("STITI_EVENTKIT", "on") != "off":
        for g in gone:
            if g.get("ek_identifier"):
                try:
                    from ..connectors import eventkit
                    eventkit.remove_reminder(g["ek_identifier"])
                except Exception:
                    pass
    off_cal = 0
    if r["event_id"]:
        try:
            off_cal = remove_event(title(r), _when(r))
        except Exception as e:
            print(f"[important] undo calendar: {type(e).__name__}: {e}", flush=True)
    if r["task_id"]:
        q("UPDATE tasks SET status='cancelled' WHERE id=%s AND status='open'", (r["task_id"],))
    q("""UPDATE noticed SET status='declined', stage=NULL, answer='undone', reminder_ids='{}', prep_intent_id=NULL,
                event_id=%s WHERE id=%s""", (None if off_cal or not r["event_id"] else r["event_id"], r["id"]))
    parts = []
    if gone:
        parts.append(f"cancelled {'the reminder' if len(gone) == 1 else f'all {len(gone)} reminders'}")
    if r["event_id"]:
        parts.append("took it off the calendar" if off_cal else "couldn't take it off the calendar — remove it there")
    return ("Okay — " + " and ".join(parts) + ".") if parts else "Okay, dropped."


def _prep_goal(r: dict) -> str:
    return (f"prepare for {subject(r)}" if r["kind"] != "deadline" else f"finish {subject(r)}")


def _answer_prep(r: dict, text: str, now: datetime) -> Out | None:
    when = _when(r)
    if NO.search(text) and not dates.find_days(text, now, loose=True):
        q("UPDATE noticed SET stage=NULL WHERE id=%s", (r["id"],))
        return Out("Okay, no plan. The rest stays as booked.")
    days = dates.find_days(text, now, loose=True)
    start_now = bool(re.search(r"\b(?:now|right away|abhi|aaj se|from today|today|aaj|immediately|let'?s start)\b", text, re.I))
    if days and not (start_now and days[0].day == now.date()):
        d = days[0].day
        rest = text[:days[0].start] + " " + text[days[0].end:]
        clock = dates.clock_in(rest) or (9, 0)
        at = datetime(d.year, d.month, d.day, *clock, tzinfo=CFG.tz)
        if at >= (when if r["has_time"] else when.replace(hour=0, minute=0)):
            return Out(f"That's not before {dates.short_day(when.date(), now)}. Say an earlier day and I'll set it.")
        if at <= now:
            return Out("That time has already passed. Say another day and I'll set it.")
        from . import alarms
        goal = _prep_goal(r)
        rid = alarms.create_at(at, ("time to start preparing" if r["kind"] != "deadline" else "time to start on it")
                               + f" — {_label(r, at)}", heard=text)
        if not rid:
            return Out("I couldn't set that reminder just now. Say it once more?")
        task = one("INSERT INTO tasks(title, due, wait_until, source, privacy) VALUES (%s,%s,%s,'noticed',%s) RETURNING id",
                   (goal[:1].upper() + goal[1:].replace("your ", "", 1), when, at, r["privacy"]))
        q("UPDATE noticed SET stage=NULL, prep_intent_id=%s, task_id=%s WHERE id=%s", (rid, task["id"] if task else None, r["id"]))
        clock_s = "" if clock == (9, 0) else f" at {dates.say_clock(*clock)}"
        return Out(f"Okay. I'll remind you on {dates.short_day(d, now)}{clock_s or ' at 9 AM'} to start"
                   + (", and it's on your list." if task else ".")
                   + " Say “break it down” then and we'll plan the steps.")
    if start_now or YES.search(text):
        q("UPDATE noticed SET stage=NULL WHERE id=%s", (r["id"],))
        return Out("", chunk=_prep_goal(r))
    return None


def _answer_important(r: dict, text: str, now: datetime) -> Out | None:
    if REMIND.search(text) or N_BEFORE.search(text) or DAY_BEFORE.search(text) or MORNING_OF.search(text) \
            or EVE_BEFORE.search(text) or (dates.find_days(text, now, loose=True) and not NO.search(text)
                                           and not FIX_DATE.search(text)):
        got = his_times(REMIND.sub(" ", text), r, now)
        if got is not None:
            return Out(book(r, now, got[0], cal=not NO_CAL.search(text), dropped=got[1], answer=text))
    if FIX_DATE.search(text) and (days := dates.find_days(text, now, loose=True)) and not REMIND.search(text):
        d = days[0].day                             # "no, it's on the 12th": fix the day, ask again (once)
        new = _when(r).replace(year=d.year, month=d.month, day=d.day)
        if new.date() != _when(r).date() and new > now:
            it = Item(r["what"], r["kind"], new, r["has_time"], r["confidence"], r["source"], r["source_label"],
                      r["heard"] or "", dict(r["meta"] or {}))
            if one("SELECT 1 AS x FROM noticed WHERE source_ref=%s AND id<>%s", (it.key, r["id"])):
                return None
            q("UPDATE noticed SET when_at=%s, source_ref=%s, asked_at=%s, asked_via='turn' WHERE id=%s",
              (new, it.key, now, r["id"]))
            return Out(ask_text(dict(_row(r["id"]), _turn=True), now))
    if TODO.search(text) and not NO.match(text):
        return Out(to_list(r, now, text))
    if NO_CAL.search(text) and (YES.search(text) or REMIND.search(text)):
        return Out(book(r, now, None, cal=False, answer=text))      # "yes, but not on the calendar": reminders only
    if NOTE.search(text) or NO_CAL.search(text):
        return Out(note(r, now, text))
    if NO_REMINDERS.search(text):
        return Out(book(r, now, None, rem=False, answer=text))
    if NO.search(text):
        return Out(decline(r, now, text))
    if YES.search(text):
        return Out(book(r, now, None, answer=text))
    return None


def _pick(text: str, rows: list[dict]) -> list[dict]:
    """Which noticed thing does he mean? "the exam one" · "the first one" · "the mail one" · "both"."""
    t = text.lower()
    if re.search(r"\b(?:both|all (?:of them)?|sab|dono|everything)\b", t) and len(rows) > 1:
        return rows
    for word, i in ORDINAL.items():
        if re.search(rf"\b{word}\b", t) and i < len(rows):
            return [rows[i]]
    said = _words(t)
    hits = [r for r in rows if said & (_words(r["what"]) | {r["kind"]} | _words(r["source_label"] or ""))
            or (r["source"] == "mail" and re.search(r"\b(?:mail|email)\b", t))
            or (r["source"] == "document" and re.search(r"\b(?:document|doc|file|pdf)\b", t))]
    return hits[:1]


def noticed_list(now: datetime, via_list: bool = True) -> str:
    """"What did you notice?" — the things still waiting for his answer, soonest first (at most three read out)."""
    rows = waiting(now)
    if not rows:
        return "Nothing waiting on you right now."
    lines = []
    for r in rows[:3]:
        day = dates.short_day(_when(r).date(), now) + _at(r)
        src = (f"a mail from {r['source_label']}: " if r["source"] == "mail" and r["source_label"] else
               f"in “{r['source_label']}”: " if r["source"] == "document" and r["source_label"] else "")
        lines.append(f"{src}{subject(r)} on {day}")
    q("""UPDATE noticed SET status='asked', asked_at=COALESCE(asked_at, %s), asked_via=COALESCE(asked_via, 'list'),
                stage=NULL WHERE id = ANY(%s)""", (now, [r["id"] for r in rows[:3]]))
    more = f" And {len(rows) - 3} more." if len(rows) > 3 else ""
    if len(lines) == 1:
        one_ = rows[0]
        q("UPDATE noticed SET stage='important', asked_at=%s WHERE id=%s", (now, one_["id"]))
        return f"One thing: {lines[0]}. Should I put it on the calendar and remind you before?"
    head = {2: "Two things", 3: "Three things"}[len(lines)]
    return (f"{head}: " + "; ".join(lines) + f".{more} Say “save the first one”, or “not important”.")


def check_mail(now: datetime, fetch=None) -> str:
    """"Check my mail for anything important" — honest when mail isn't set up."""
    from ..connectors import mail
    if fetch is None and not mail.configured():
        return MAIL_HINT
    try:
        scan_mail(now, fetch)
    except Exception as e:
        print(f"[important] mail: {type(e).__name__}: {e}", flush=True)
        return "I couldn't reach your mail just now. Try again in a bit."
    rows = [r for r in waiting(now) if r["source"] == "mail"]
    if not rows:
        return "Nothing with a date in your unread mail."
    r = rows[0]
    _mark_asked(r["id"], now, "turn")
    lead = "" if len(rows) == 1 else f"{len(rows)} things in your mail. First: "
    text = ask_text(r, now)
    if lead:
        n = _name()
        text = lead + (text[len(n) + 2:] if n and text.startswith(n + ", ") else text[0].lower() + text[1:])
    return text


# ------------------------------------------------------------------------------------------------ the turn
def _instruction(text: str, now: datetime) -> tuple[Item, list[datetime] | None, int, bool] | None:
    """He already said what to do: "my exams are on the 9th, give me a reminder on the 1st" · "interview on Friday at
    3, put it on my calendar" · "remind me two days before my exam on the 9th". → (item, his times or None, dropped,
    wants reminders). None = this is a plain reminder / alarm command: its fast path keeps it."""
    m, c = REMIND.search(text), TO_CAL.search(text)
    if not m and not c:
        return None
    cut = min(x.start() for x in (m, c) if x)
    pre = text[:cut].rstrip(" ,;-–—").rstrip()
    pre = re.sub(r"\b(?:and|so|to|please|toh|aur|then|can you|could you|will you)\s*$", "", pre, flags=re.I).rstrip(" ,;")
    items = [i for i in notice.detect(pre, now) if i.confidence >= 0.6] if len(pre) > 8 else []
    if items:
        it = items[0]
        fake = {"when_at": it.when, "has_time": it.has_time}
        got = his_times(REMIND.sub(" ", TO_CAL.sub(" ", text[cut:])), fake, now) if m else None
        return it, (got[0] if got else None), (got[1] if got else 0), bool(m) or not c
    if not m:
        return None
    post = text[m.end():]
    spans = [x.span() for rx in (N_BEFORE, DAY_BEFORE, EVE_BEFORE, MORNING_OF) for x in rx.finditer(post)]
    if not spans:
        return None                                 # "remind me about my exam on the 9th" → the reminder fast path
    bare = post
    for a, b in spans:
        bare = bare[:a] + " " * (b - a) + bare[b:]
    bare = re.sub(r"^\s*(?:about|for|of|that|ki|ke liye|before|pehle)\b", " ", re.sub(r"\s+", " ", bare)).strip()
    items = [i for i in notice.detect(bare, now) if i.confidence >= 0.6]
    if not items:
        return None
    it = items[0]
    offs = " ".join(post[a:b] for a, b in spans)
    got = his_times(offs, {"when_at": it.when, "has_time": it.has_time}, now)
    return it, (got[0] if got else None), (got[1] if got else 0), True


def hint(text: str, now: datetime | None = None) -> bool:
    """Pure read: would this text be handled here? (a speculative voice turn must not start it — D29)"""
    try:
        if LIST_ASK.search(text) or MAIL_ASK.search(text) or OFF.search(text) or ON.search(text):
            return True
        if open_question(now) is not None:
            return True
        return bool(notice.detect(text, _now(now)))
    except Exception:
        return False


def from_turn(text: str, *, now: datetime | None = None, privacy: int = 1, calm: bool = True) -> str | None:
    """His own words in a normal turn. Returns her reply (the one question, or the read-back of a direct instruction)
    or None (nothing to say: maybe a thing was quietly put on the noticed list for a better moment)."""
    now = _now(now)
    if REMIND.search(text) or TO_CAL.search(text):
        ins = _instruction(text, now)
        if ins is None:
            return None
        it, times, dropped, wants_rem = ins
        row = store(it, privacy, reuse=("new", "asked", "declined", "noted", "expired", "accepted"))
        if row is None:
            return None
        if row["status"] == "accepted" and times is None:
            return f"That's already booked: {statement(row, now)[:-1].replace(' on ', ' — ', 1)}."
        if row["status"] == "accepted":
            return book(row, now, times, cal=False, dropped=dropped, answer=text)
        if times is None and already_booked(it.what, it.when, now):
            q("UPDATE noticed SET status='accepted', answer='already booked' WHERE id=%s", (row["id"],))
            return f"That's already on your calendar or in your reminders: {subject(row)}, {dates.short_day(it.when.date(), now)}."
        return book(row, now, times, rem=wants_rem or times is not None, dropped=dropped, answer=text)
    items = [i for i in notice.detect(text, now) if i.confidence >= notice.ASK_MIN]
    if not items:
        maybe_llm(text, now, privacy)
        return None
    rows = []
    for it in items:
        if already_booked(it.what, it.when, now):
            continue
        row = store(it, privacy)
        if row is not None:
            rows.append(row)
    if not rows or disabled():
        return None
    if OTHER_CMD.search(text):
        return None                                 # "…so set an alarm for 6": that command runs; this waits in the list
    if not calm or UPSET.search(text) or len(text.split()) > SHORT_WORDS:
        return None                                 # not the moment: it waits for the proactive gate / the list
    r = rows[0]
    _mark_asked(r["id"], now, "turn")
    return ask_text(dict(r, asked_via="turn"), now)


def answer(text: str, *, now: datetime | None = None) -> Out | None:
    """Is this his answer to her question, or a request about the noticed things? None = no: the turn goes on."""
    now = _now(now)
    if OFF.search(text):
        _set_disabled(True)
        settle(now)
        return Out("Okay, I'll stop asking. I'll still keep a list — say “what did you notice” when you want it.")
    if ON.search(text):
        _set_disabled(False)
        return Out("Okay, I'll ask again when something looks important.")
    if MAIL_ASK.search(text):
        return Out(check_mail(now))
    if LIST_ASK.search(text):
        expire(now)
        return Out(noticed_list(now))
    r = open_question(now)
    if r is not None:
        out = _answer_prep(r, text, now) if r["stage"] == "prep" else _answer_important(r, text, now)
        if out is not None:
            return out
        if AGAIN.match(text):                       # he didn't catch it: the same question once more, nothing new
            return Out(ask_text(dict(r, _turn=r["asked_via"] == "turn"), now) if r["stage"] == "important"
                       else "Want a plan for it, and when do you want to start?")
    if UNDO.search(text) and len(text.split()) <= 8:
        last = one(f"""SELECT {COLS} FROM noticed WHERE status='accepted' AND answered_at >= %s
                       ORDER BY answered_at DESC LIMIT 1""", (now - UNDO_WINDOW,))
        if last is not None:
            return Out(undo(last, now))
    # "yes, save that exam one" · "the first one" · "the mail one is not important" — about the noticed list, later
    if len(text.split()) <= 14 and POINTS.search(text) and (REFER.search(text) or NO.search(text)) \
            and not notice.QUESTION.search(text) and not notice.detect(text, now):
        picks = _pick(text, waiting(now))
        if picks:
            said = [(_answer_important(p, text, now) or Out(book(p, now, None, answer=text))).text for p in picks]
            if len(said) > 1:                       # several at once: the prep question would become a quiz
                q("UPDATE noticed SET stage=NULL WHERE id = ANY(%s)", ([p["id"] for p in picks],))
                said = [re.sub(r"\s*Want a (?:preparation )?plan[^?]*\?$", "", x) for x in said]
            return Out(" ".join(said))
    return None


# ------------------------------------------------------------------------------------------------ she asks first
def candidate(present: bool, now: datetime | None = None) -> tuple[str, dict] | None:
    """One noticed thing to ask about now, or None. The proactive gate (quiet hours, daily nudge budget, busy) is
    applied by proactive.tick(); here: he's present, not in a call, ≤ MAX_ASKS_PER_DAY a day, ≥ 30 min apart, and no
    other question of hers is still open."""
    now = _now(now)
    expire(now)
    if not present or disabled() or _in_call() or open_question(now) is not None:
        return None
    day0 = now.replace(hour=0, minute=0, second=0, microsecond=0)
    asked = q("""SELECT asked_at FROM noticed WHERE asked_at >= %s AND asked_via IN ('voice','notification','telegram')
                 ORDER BY asked_at DESC""", (day0,))
    if len(asked) >= MAX_ASKS_PER_DAY or (asked and now - asked[0]["asked_at"] < ASK_GAP):
        return None
    for r in q(f"SELECT {COLS} FROM noticed WHERE status='new' AND when_at > %s ORDER BY when_at, id LIMIT 5", (now,)):
        if already_booked(r["what"], _when(r), now):
            q("UPDATE noticed SET status='accepted', answer='already booked' WHERE id=%s", (r["id"],))
            continue
        return ask_text(r, now), {"key": f"noticed:{r['id']}", "noticed_id": r["id"]}
    return None


# ------------------------------------------------------------------------------------------------ mail + documents
def scan_mail(now: datetime | None = None, fetch=None) -> int:
    """Look at unread mail (sender + subject + first lines) for dated things. Returns how many new ones were noticed.
    Nothing is written to the calendar from here — a mail can only ever lead to a question."""
    now = _now(now)
    if fetch is None:
        from ..connectors import mail
        if not mail.configured():
            return 0
        fetch = lambda: mail.unread(limit=10, snippet=True)      # noqa: E731
    r = fetch()
    if not isinstance(r, dict) or "error" in r:
        return 0
    n = 0
    for msg in r.get("latest") or []:
        for it in notice.from_mail(str(msg.get("from") or ""), str(msg.get("subject") or ""),
                                   str(msg.get("snippet") or ""), now):
            if it.confidence >= notice.ASK_MIN and not already_booked(it.what, it.when, now) and store(it, 1, reuse=()):
                n += 1
    return n


def scan_document(title_: str, text: str, privacy: int = 1, now: datetime | None = None, limit: int = 3) -> int:
    """A document he ingested: dated things in it go on the noticed list (soonest first, at most `limit`)."""
    now = _now(now)
    found = [i for i in notice.detect((text or "")[:30000], now, "document", notice.clean(title_, 50))
             if i.confidence >= notice.ASK_MIN]
    n = 0
    for it in sorted(found, key=lambda i: i.when)[:limit]:
        it.what = notice.clean(it.what, 60)
        if it.what and not already_booked(it.what, it.when, now) and store(it, privacy, reuse=()):
            n += 1
    return n


_scan = {"t": 0.0, "busy": False}


def background_scan() -> None:
    """Called by the app scheduler once a minute: every 15 min, unread mail is scanned off-thread (when set up)."""
    from ..connectors import mail
    if _scan["busy"] or time.time() - _scan["t"] < MAIL_EVERY_S or not mail.configured():
        return
    _scan.update(t=time.time(), busy=True)

    def job():
        try:
            n = scan_mail()
            if n:
                print(f"[important] mail: {n} new dated thing(s) noticed", flush=True)
        except Exception as e:
            print(f"[important] mail scan: {type(e).__name__}: {e}"[:200], flush=True)
        finally:
            _scan["busy"] = False
    threading.Thread(target=job, daemon=True).start()


# ------------------------------------------------------------------------------------------------ optional: the cloud
# What the rules can't date ("my exams are in the second week of December") may be read by a free cloud model in the
# background — never on the hot path, never for private (P2) text, never for mail or documents. Its find is only put
# on the noticed list (source 'llm'): she still asks before anything is written.
VAGUE = re.compile(r"\b(?:week|month|end of|mid|middle of|beginning of|early|late|after|around|hafte|mahine|"
                   + dates._MON + r")\b", re.I)
LLM_SYS = ("Extract ONE dated event or deadline from the user's sentence. Today is {today}. Reply with JSON only: "
           '{{"what": "<2-5 words from the sentence>", "kind": "exam|interview|deadline|bill|result|travel|appointment|'
           'birthday|meeting|event", "date": "YYYY-MM-DD"}}. If no future date can be worked out, reply {{"date": null}}.')
_bg: threading.Thread | None = None


def maybe_llm(text: str, now: datetime, privacy: int) -> bool:
    global _bg
    if privacy >= 2 or os.getenv("STITI_NOTICE_LLM", "1") == "0" or len(text.split()) > 40:
        return False
    if not (notice._nouns(text) and notice.MINE.search(text) and VAGUE.search(text)) or notice.QUESTION.search(text) \
            or notice.COMMAND.search(text) or notice.PAST.search(text) or notice.UNSURE.search(text):
        return False

    def job():
        try:
            from .. import router
            info = router.complete([{"role": "system", "content": LLM_SYS.format(today=f"{now:%A %Y-%m-%d}")},
                                    {"role": "user", "content": text}], route="extract", privacy=privacy,
                                   max_tokens=120, temperature=0.0, json_mode=True)
            it = from_llm(info.get("text") or "", text, now)
            if it is not None and not already_booked(it.what, it.when, now):
                store(it, privacy, reuse=())
        except Exception as e:
            print(f"[important] cloud read skipped: {type(e).__name__}: {e}"[:160], flush=True)
    _bg = threading.Thread(target=job, daemon=True)
    _bg.start()
    return True


def from_llm(raw: str, text: str, now: datetime) -> Item | None:
    """Trust nothing the model says: the date must parse and be ahead, the kind must be one of ours, and the words
    must be his own (found in his sentence)."""
    m = re.search(r"\{.*\}", raw or "", re.S)
    try:
        d = json.loads(m[0]) if m else {}
        day = datetime.strptime(str(d.get("date")), "%Y-%m-%d").replace(tzinfo=CFG.tz)
    except Exception:
        return None
    what = notice.clean(str(d.get("what") or ""), 60)
    kind = str(d.get("kind") or "")
    if kind not in DEFAULTS or day.date() <= now.date() or day - now > timedelta(days=400) or len(what) < 3:
        return None
    if not all(w.lower() in text.lower() for w in re.findall(r"[A-Za-z]{3,}", what)):
        return None
    what = re.sub(r"^(?:my|our|the)\s+", "", what, flags=re.I)
    return Item(what, kind, day, False, 0.7, "llm", None, text[:200],
                {"mine": True, "plural": what.lower().endswith("s") and not what.lower().endswith("ss"), "starts": False})


def join(timeout: float = 20.0) -> None:
    """Tests: wait for the background read."""
    if _bg is not None:
        _bg.join(timeout)
