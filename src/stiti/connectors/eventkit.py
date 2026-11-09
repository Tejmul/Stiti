"""Apple Calendar + Reminders via EventKit (pyobjc). Free, local, syncs through iCloud.

- Alarms/reminders are mirrored as Reminders WITH an alarm → they ring on iPhone/Watch even if
  Stiti or the Mac is off (report §Alarms: three layers so nothing depends on Stiti being awake).
- Calendar is read for "what's on my calendar" and as fixed blocks for the CP-SAT planner.
  Google calendars added to macOS Calendar are included automatically.
First use shows a one-time macOS permission prompt (Calendar / Reminders).
"""
from __future__ import annotations

import threading
from datetime import datetime, timedelta

from ..config import CFG

_store = None
_granted: dict[str, bool] = {}


def _ek():
    import EventKit
    return EventKit


def store():
    global _store
    if _store is None:
        _store = _ek().EKEventStore.alloc().init()
    return _store


def _request(kind: str, timeout: float = 60) -> bool:
    """kind: 'reminders' | 'events'. Blocks until the user answers the macOS prompt (or timeout)."""
    if kind in _granted:
        return _granted[kind]
    EK = _ek()
    etype = EK.EKEntityTypeReminder if kind == "reminders" else EK.EKEntityTypeEvent
    status = EK.EKEventStore.authorizationStatusForEntityType_(etype)
    if status in (3, 4):          # fullAccess (3 on 14+, 'authorized' legacy) / writeOnly(4)
        _granted[kind] = True
        return True
    if status in (1, 2):          # restricted / denied
        _granted[kind] = False
        return False
    done, result = threading.Event(), [False]

    def cb(granted, err):
        result[0] = bool(granted)
        done.set()
    s = store()
    if kind == "reminders":
        s.requestFullAccessToRemindersWithCompletion_(cb)
    else:
        s.requestFullAccessToEventsWithCompletion_(cb)
    done.wait(timeout)
    _granted[kind] = result[0]
    return result[0]


def _nsdate(dt: datetime):
    from Foundation import NSDate
    return NSDate.dateWithTimeIntervalSince1970_(dt.timestamp())


def _pydt(nsd) -> datetime:
    return datetime.fromtimestamp(nsd.timeIntervalSince1970(), CFG.tz)


# ---------------- reminders (alarm mirror) ----------------
def add_reminder(title: str, when: datetime, notes: str | None = None) -> str | None:
    if not _request("reminders"):
        return None
    EK = _ek()
    from Foundation import NSCalendar, NSCalendarUnitDay, NSCalendarUnitHour, NSCalendarUnitMinute, \
        NSCalendarUnitMonth, NSCalendarUnitYear
    s = store()
    r = EK.EKReminder.reminderWithEventStore_(s)
    r.setTitle_(title)
    if notes:
        r.setNotes_(notes)
    r.setCalendar_(s.defaultCalendarForNewReminders())
    units = NSCalendarUnitYear | NSCalendarUnitMonth | NSCalendarUnitDay | NSCalendarUnitHour | NSCalendarUnitMinute
    r.setDueDateComponents_(NSCalendar.currentCalendar().components_fromDate_(units, _nsdate(when)))
    r.addAlarm_(EK.EKAlarm.alarmWithAbsoluteDate_(_nsdate(when)))
    ok, err = s.saveReminder_commit_error_(r, True, None)
    return r.calendarItemIdentifier() if ok else None


def remove_reminder(identifier: str) -> bool:
    if not identifier or not _request("reminders"):
        return False
    s = store()
    item = s.calendarItemWithIdentifier_(identifier)
    if item is None:
        return False
    ok, _ = s.removeReminder_commit_error_(item, True, None)
    return bool(ok)


def mirror_intent_async(intent_id: int) -> None:
    """Called after an alarm/reminder is set; never blocks the reply."""
    def work():
        from ..db import one, q
        row = one("SELECT kind, fire_at, payload FROM intents WHERE id=%s", (intent_id,))
        if not row or not row["fire_at"]:
            return
        title = row["payload"].get("say") or ("Alarm" if row["kind"] == "alarm" else "Reminder")
        ident = add_reminder(f"⏰ {title}" if row["kind"] == "alarm" else title, row["fire_at"],
                             notes="Set by Stiti")
        if ident:
            q("UPDATE intents SET ek_identifier=%s WHERE id=%s", (ident, intent_id))
    threading.Thread(target=work, daemon=True).start()


# ---------------- calendar (read) ----------------
def events(start: datetime, end: datetime) -> list[dict]:
    if not _request("events"):
        return []
    s = store()
    pred = s.predicateForEventsWithStartDate_endDate_calendars_(_nsdate(start), _nsdate(end), None)
    out = []
    for e in s.eventsMatchingPredicate_(pred) or []:
        out.append({"title": str(e.title() or "(no title)"), "start": _pydt(e.startDate()), "end": _pydt(e.endDate()),
                    "all_day": bool(e.isAllDay()), "location": str(e.location() or ""),
                    "calendar": str(e.calendar().title())})
    out.sort(key=lambda x: x["start"])
    return out


def today_events(now: datetime | None = None) -> list[dict]:
    now = now or datetime.now(CFG.tz)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return events(start, start + timedelta(days=1))


def speak_events(evts: list[dict], label: str = "today") -> str:
    if not evts:
        return f"Your calendar is free {label}."
    items = [("all day: " if e["all_day"] else f"{e['start']:%I:%M %p} ").lstrip("0") + e["title"] for e in evts[:3]]
    more = f" …and {len(evts) - 3} more." if len(evts) > 3 else ""
    return f"{len(evts)} on your calendar {label}: " + "; ".join(items) + "." + more


# ---------------- calendar (write — only after his "haan") ----------------
def add_event(title: str, start: datetime, minutes: int = 60, notes: str | None = None) -> str | None:
    if not _request("events"):
        return None
    EK = _ek()
    s = store()
    e = EK.EKEvent.eventWithEventStore_(s)
    e.setTitle_(title)
    e.setStartDate_(_nsdate(start))
    e.setEndDate_(_nsdate(start + timedelta(minutes=minutes)))
    if notes:
        e.setNotes_(notes)
    e.setCalendar_(s.defaultCalendarForNewEvents())
    ok, err = s.saveEvent_span_commit_error_(e, EK.EKSpanThisEvent, True, None)
    return e.eventIdentifier() if ok else None


def cancel_event(title: str, day: datetime) -> int:
    """Delete events on that day whose title contains `title` (case-insensitive). Returns count."""
    if not _request("events"):
        return 0
    EK = _ek()
    s = store()
    start = day.replace(hour=0, minute=0, second=0, microsecond=0)
    pred = s.predicateForEventsWithStartDate_endDate_calendars_(_nsdate(start), _nsdate(start + timedelta(days=1)), None)
    n = 0
    for e in s.eventsMatchingPredicate_(pred) or []:
        if title.lower() in str(e.title() or "").lower():
            ok, _ = s.removeEvent_span_commit_error_(e, EK.EKSpanThisEvent, True, None)
            n += bool(ok)
    return n


# ---------------- reminders (two-way: ticked on iPhone → done in Stiti) ----------------
def completed_ids(identifiers: list[str]) -> list[str]:
    if not identifiers or not _request("reminders"):
        return []
    s = store()
    done = []
    for ident in identifiers:
        item = s.calendarItemWithIdentifier_(ident)
        if item is not None and item.isCompleted():
            done.append(ident)
    return done
