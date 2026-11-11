"""Alarms, reminders and timers: one structure (no LLM — works when every cloud is down).

  create   "kal 6 baje uthana" · "remind me at 7 pm to call mummy" · "10 minute ka timer" · "roz 7 baje alarm"
           · "weekdays 6:30 wake me" · "har somvar 9 baje standup yaad dilana"  (recurrence → RFC 5545 RRULE)
  manage   list · cancel (next / #id / "7 am wala" / "about mom" / all) · move ("7 wala 7:30 kar do") · snooze
  fire     due → policy by kind and lateness (a 9 AM alarm is NOT rung at 8 PM after the Mac was off; it's
           reported as missed) → alarm/timer RING (tone + voice, louder each round) until "band karo" /
           "uth gaya" / "5 minute aur" or auto-stop → recurring ones re-arm for their next time.
  missed   told once ("while I was off you missed your 9:00 alarm").
State lives in Postgres `intents`; alarms/reminders are also mirrored to Apple Reminders (ring on iPhone/Watch).
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import threading
import time
from datetime import datetime, timedelta

from dateutil.rrule import rrulestr

from ..config import CFG
from ..db import one, q
from ..fastpath.dates import WAKE, now, parse_when, readback, say_when, second_person

# grace: how late a fire may still be delivered (after that it's "missed", not rung hours later)
# (research: docs/research/alarms.md — Alexa-style "fire if ≤30 min late, else drop")
GRACE = {"alarm": timedelta(minutes=30), "timer": timedelta(minutes=2), "reminder": timedelta(hours=12),
         "checkin": timedelta(hours=1), "nudge": timedelta(minutes=30), "event_trigger": timedelta(hours=1)}
RING_IF_LATE_UNDER = timedelta(minutes=10)   # alarm 10–30 min late: a short spoken note instead of a full ring
QUIET = (23, 7)                              # reminders/check-ins are not SPOKEN 23:00–07:00 (alarms still ring)
SNOOZE_MIN = int(os.getenv("STITI_SNOOZE_MIN", "9"))
MAX_SNOOZES = 3
RING_MAX_S = 10 * 60                   # then stop ringing and report it as missed
RING_ROUND_S = 20                      # tone + voice line, repeated with rising volume

DAYS = {"mo": ("monday", "mondays", "somvar", "som"), "tu": ("tuesday", "tuesdays", "mangalvar", "mangal"),
        "we": ("wednesday", "wednesdays", "budhvar", "budh"), "th": ("thursday", "thursdays", "guruvar", "guru"),
        "fr": ("friday", "fridays", "shukravar", "shukra"), "sa": ("saturday", "saturdays", "shanivar", "shani"),
        "su": ("sunday", "sundays", "ravivar", "itvaar", "ravi")}
EVERY = re.compile(r"\b(every|har|each|roz|rozana|daily|everyday|weekdays?|weekends?|mondays|tuesdays|wednesdays|"
                   r"thursdays|fridays|saturdays|sundays)\b", re.I)
DISMISS_RX = re.compile(r"\b(stop|band|bandh|off|uth gay[ai]|utth gay[ai]|i'?m up|i am up|jaag gay[ai]|okay|ok|"
                        r"theek hai|done|bas|chup|shut up|enough|thank you|thanks|dismiss)\b", re.I)
SNOOZE_RX = re.compile(r"\b(snooze|(\d+|paanch|das|5|10) ?(min(ute)?s?|minat) (aur|more|baad)|thodi der|aur sone do|"
                       r"5 more|later|baad mein)\b", re.I)


# ------------------------------------------------------------------------------------------------ parsing
def recurrence(text: str, when: datetime) -> str | None:
    """'roz' / 'every day' → DAILY · 'weekdays' → MO–FR · 'weekends' · 'every monday and thursday' / 'har somvar'."""
    t = text.lower()
    if not EVERY.search(t):
        return None
    hm = f";BYHOUR={when.hour};BYMINUTE={when.minute};BYSECOND=0"
    if re.search(r"\bweekdays?\b|monday (to|se) friday|mon-fri", t):
        return "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR" + hm
    if re.search(r"\bweekends?\b", t):
        return "FREQ=WEEKLY;BYDAY=SA,SU" + hm
    days = [code.upper() for code, names in DAYS.items() if any(re.search(rf"\b{n}\b", t) for n in names)]
    if days and re.search(r"\b(every|har|each)\b|days\b", t):
        return "FREQ=WEEKLY;BYDAY=" + ",".join(days) + hm
    if re.search(r"\b(every ?day|har din|roz|rozana|daily|everyday|every morning|every night|har subah|har raat)\b", t):
        return "FREQ=DAILY" + hm
    return None


def next_time(rule: str, after: datetime) -> datetime | None:
    start = after.replace(second=0, microsecond=0)
    return rrulestr(rule, dtstart=start - timedelta(days=1)).after(after, inc=False)


def _kind(text: str) -> str:
    t = text.lower()
    if re.search(r"\btimer\b", t):
        return "timer"
    if re.search(r"\b(remind|yaad|reminder)\b", t):
        return "reminder"
    return "alarm" if WAKE.search(t) else "reminder"


def _label(text: str) -> str | None:
    m = re.search(r"\b(?:to|that|ki|ke liye|about|for)\s+(.+)$", text, re.I)
    if not m:
        return None
    s = re.sub(r"\b(yaad dila(na|do|dena)?|remind me|reminder|alarm|set|at \d.*|kal|aaj|parso|subah|shaam|raat|"
               r"every ?day|daily|roz|rozana|weekdays?|weekends?|every|har|\d{1,2}([:.]\d{2})?\s*(am|pm|baje)?|"
               r"tomorrow|today|tonight|morning|evening)\b", " ", m.group(1), flags=re.I)
    s = re.sub(r"\s+", " ", s).strip(" .,")
    return s if len(s) >= 3 else None


def _rule_words(rule: str | None) -> str:
    if not rule:
        return ""
    if "FREQ=DAILY" in rule:
        return "every day"
    days = re.search(r"BYDAY=([A-Z,]+)", rule)
    if days:
        d = days.group(1)
        if d == "MO,TU,WE,TH,FR":
            return "every weekday"
        if d == "SA,SU":
            return "every weekend"
        names = {"MO": "Mon", "TU": "Tue", "WE": "Wed", "TH": "Thu", "FR": "Fri", "SA": "Sat", "SU": "Sun"}
        return "every " + "/".join(names[x] for x in d.split(","))
    return "repeating"


# ------------------------------------------------------------------------------------------------ commands
def handle(text: str) -> str | None:
    """Entry point from the fast path. None = not an alarm/reminder/timer thing."""
    t = text.lower()
    if re.search(r"\b(cancel|delete|remove|hata|hatao|band kar|mat bajana).*(alarms?|reminders?|timers?)|"
                 r"(alarms?|reminders?|timers?).*(cancel|delete|hata|hatao|remove|band kar|mat)", t):
        return cancel(text)
    if re.search(r"\b(move|change|shift|badal|kar do|instead).*(alarm|reminder)|(alarm|reminder).*\b(to|ko|kar do)\b.*\d",
                 t) and re.search(r"\d", t) and re.search(r"\b(move|change|shift|badal|instead|ko)\b", t):
        return move(text)
    if re.search(r"\bsnooze\b", t):
        return snooze_latest()
    if re.search(r"\b(my|kitne|which|what|list|kaunse|show|upcoming|saare|all)\b.*\b(alarms?|reminders?|timers?)\b", t) \
            and not re.search(r"\bset\b", t):
        return list_all()
    if not ASK_RX.search(t):
        return None          # "what should I study this evening?" mentions a time; it is not asking for a reminder
    return create(text)


# He has to ASK for one (2026-11-11: "Namaskar, aaj shaam ko main kya padhun?" and "what about tomorrow morning?"
# each created a 9 AM reminder — any line the classifier tagged "time" with a parseable time became one).
ASK_RX = re.compile(r"\b(remind\w*|alarms?|timers?|wake|jaga\w*|utha\w*|uth\w*|yaad|set|laga\w*|bajao|bajana|"
                    r"notify|ping me|alert me|countdown)\b|\b\d+\s*(min|mins|minute|minutes|sec|second|seconds|hour|"
                    r"hours|ghante|minat)\b.*\b(ka|ke|for|after|baad|mein|me)\b|\b(in|after)\s+\d+\s*(min|minute|hour)", re.I)


def create(text: str, ref: datetime | None = None) -> str | None:
    when = parse_when(text, ref)
    if when is None:
        if re.search(r"\b\d{1,2}\b", text) and re.search(r"\b(alarm|remind|yaad|timer|uth|wake)\b", text, re.I):
            return "Morning or evening? Say it like “6 am” or “shaam 6 baje”."
        return None
    kind = _kind(text)
    rule = recurrence(text, when) if kind != "timer" else None
    if rule:
        when = next_time(rule, (ref or now()) - timedelta(seconds=1)) or when
    label = _label(text) if kind == "reminder" else None
    if kind == "reminder" and not label:
        label = None
    say = label or {"timer": "Timer done!", "alarm": "Wake up, it's time!"}.get(kind, "Here's your reminder.")
    payload = {"say": say, "kind": kind, "label": label, "snoozes": 0, "heard": text[:120]}
    row = one("""INSERT INTO intents(kind, fire_at, rrule, payload, user_set) VALUES (%s,%s,%s,%s,true) RETURNING id""",
              ("alarm" if kind in ("alarm", "timer") else "reminder", when, rule, json.dumps(payload)))
    if kind != "timer" and os.getenv("STITI_EVENTKIT", "on") != "off":
        try:
            from ..connectors import eventkit
            eventkit.mirror_intent_async(row["id"])          # also rings on iPhone/Watch if Stiti is off
        except Exception:
            pass
    if kind == "timer":
        mins = round((when - (ref or now())).total_seconds() / 60)
        return f"Timer set for {mins} minute{'s' if mins != 1 else ''} (rings at {when:%I:%M %p}). (#{row['id']})".replace(" 0", " ")
    # spoken confirmation: repeat the key slot, nothing more ("Got it — reminder today at 4 PM: start your resume.")
    if rule:
        at = when.strftime("%I:%M %p").lstrip("0").replace(":00", "")
        slot = f"{_rule_words(rule)} at {at}"
    else:
        slot = say_when(when) if (ref is None or ref.date() == now().date()) else readback(when)
    if kind == "alarm":
        return f"Done — alarm {slot}. (#{row['id']})"
    about = f": {second_person(label)}" if label else ""
    return f"Got it — reminder {slot}{about}. (#{row['id']})"


def _upcoming(kinds=("alarm", "reminder")) -> list[dict]:
    return q("""SELECT id, kind, fire_at, rrule, payload, ek_identifier FROM intents
                WHERE state IN ('pending','armed') AND user_set AND kind = ANY(%s) AND fire_at > now() - interval '1 minute'
                ORDER BY fire_at""", (list(kinds),))


def _describe(r: dict) -> str:
    p = r["payload"]
    k = p.get("kind") or r["kind"]
    rep = f" ({_rule_words(r['rrule'])})" if r.get("rrule") else ""
    about = f" — {p.get('label') or p.get('say')}" if k == "reminder" else ""
    return f"{k} {readback(r['fire_at'])}{rep}{about} (#{r['id']})"


def list_all(limit: int = 6) -> str:
    rows = _upcoming()
    if not rows:
        return "No alarms or reminders set."
    head = "; ".join(_describe(r) for r in rows[:limit])
    more = f" …and {len(rows) - limit} more." if len(rows) > limit else "."
    return f"You have {len(rows)}: {head}{more}"


def _pick(text: str, rows: list[dict]) -> list[dict]:
    """Which alarm does he mean? #id · a time he mentions · words of the reminder · else the next one."""
    if (m := re.search(r"#?\b(\d{1,6})\b(?!\s*(am|pm|baje|:|\.\d))", text)) and any(r["id"] == int(m.group(1)) for r in rows) \
            and re.search(r"#|\b(number|no\.?|id)\b", text, re.I):
        return [r for r in rows if r["id"] == int(m.group(1))]
    if re.search(r"\b(all|saare|sab|every)\b", text, re.I):
        kind = "alarm" if re.search(r"\balarms?\b", text, re.I) else "reminder" if re.search(r"\breminders?\b", text, re.I) else None
        return [r for r in rows if kind is None or r["kind"] == kind]
    first_time = re.split(r"\b(to|ko|se)\b", text, maxsplit=1)[0]
    when = parse_when(first_time)
    if when is not None:
        hits = [r for r in rows if r["fire_at"].astimezone(CFG.tz).strftime("%H:%M") == when.strftime("%H:%M")]
        if hits:
            return hits[:1]
    words = {w for w in re.findall(r"[a-z]{4,}", text.lower())} - {"cancel", "delete", "remove", "reminder", "alarm",
                                                                   "alarms", "reminders", "about", "hatao", "wala", "wali"}
    hits = [r for r in rows if words & set(re.findall(r"[a-z]{4,}", str(r["payload"].get("label") or "").lower()))]
    if hits:
        return hits[:1]
    kind = "alarm" if re.search(r"\balarm", text, re.I) else "reminder" if re.search(r"\breminder", text, re.I) else None
    rows = [r for r in rows if kind is None or r["kind"] == kind]
    return rows[:1]


def cancel(text: str) -> str:
    targets = _pick(text, _upcoming())
    if not targets:
        return "Nothing to cancel."
    for r in targets:
        q("UPDATE intents SET state='cancelled' WHERE id=%s", (r["id"],))
        if r.get("ek_identifier"):
            try:
                from ..connectors import eventkit
                eventkit.remove_reminder(r["ek_identifier"])
            except Exception:
                pass
    if len(targets) > 1:
        return f"Cancelled all {len(targets)}."
    return f"Cancelled the {_describe(targets[0])}."


def move(text: str) -> str:
    rows = _upcoming()
    parts = re.split(r"\b(to|ko|se|instead)\b", text, maxsplit=1)
    target = _pick(parts[0], rows)
    new = parse_when(text.split(parts[1], 1)[1] if len(parts) > 1 else text) if target else None
    if not target or new is None:
        return "Which one, and to what time? Say: move my 7 am alarm to 7:30."
    r = target[0]
    rule = r["rrule"]
    tail = text.split(parts[1], 1)[1] if len(parts) > 1 else text
    if r["fire_at"] and not re.search(r"\b(am|pm|a\.m\.|p\.m\.|subah|shaam|raat|dopahar|morning|evening|night|"
                                      r"afternoon|noon)\b", tail, re.I):
        old_h = r["fire_at"].astimezone(new.tzinfo).hour       # "move my 6:30 alarm to 7:15" stays in the morning
        if old_h < 12 <= new.hour:
            new -= timedelta(hours=12)
        elif new.hour < 12 <= old_h:
            new += timedelta(hours=12)
        if not rule and new <= now():
            new += timedelta(days=1)
    if rule:
        rule = re.sub(r"BYHOUR=\d+;BYMINUTE=\d+", f"BYHOUR={new.hour};BYMINUTE={new.minute}", rule)
        new = next_time(rule, now()) or new
    q("UPDATE intents SET fire_at=%s, rrule=%s WHERE id=%s", (new, rule, r["id"]))
    r["fire_at"], r["rrule"] = new, rule
    return f"Moved: {_describe(r)}."


def snooze(intent_id: int, minutes: int = SNOOZE_MIN) -> str:
    row = one("SELECT payload FROM intents WHERE id=%s", (intent_id,))
    if not row:
        return "Nothing to snooze."
    p = row["payload"]
    if p.get("snoozes", 0) >= MAX_SNOOZES:
        return "That was the last snooze. Time to get up!"
    p["snoozes"] = p.get("snoozes", 0) + 1
    q("UPDATE intents SET state='pending', fire_at=now() + make_interval(mins => %s), payload=%s WHERE id=%s",
      (minutes, json.dumps(p), intent_id))
    return f"Okay, {minutes} more minutes."


def snooze_latest() -> str:
    row = one("""SELECT id FROM intents WHERE kind='alarm' AND last_fired_at > now() - interval '20 minutes'
                 ORDER BY last_fired_at DESC LIMIT 1""")
    return snooze(row["id"]) if row else "No alarm is ringing."


# ------------------------------------------------------------------------------------------------ firing
def due(ref: datetime | None = None) -> tuple[list[dict], list[dict]]:
    """Claim everything due. Returns (deliver, missed). Recurring ones re-arm for their next time right away."""
    ref = ref or now()
    rows = q("""UPDATE intents SET state='fired', last_fired_at=now()
                WHERE state IN ('pending','armed') AND fire_at <= %s
                RETURNING id, kind, fire_at, rrule, payload, user_set""", (ref,))
    deliver, missed = [], []
    for r in rows:
        k = r["payload"].get("kind") or r["kind"]
        late = ref - r["fire_at"]
        r["late_min"] = int(late.total_seconds() // 60)
        (deliver if late <= GRACE.get(k, GRACE.get(r["kind"], timedelta(hours=1))) else missed).append(r)
        if r["rrule"]:
            nxt = next_time(r["rrule"], ref)
            if nxt:
                p = dict(r["payload"], snoozes=0)
                q("UPDATE intents SET state='pending', fire_at=%s, payload=%s WHERE id=%s", (nxt, json.dumps(p), r["id"]))
    for r in missed:
        q("UPDATE intents SET state = CASE WHEN rrule IS NULL THEN 'expired' ELSE state END, "
          "payload = payload || '{\"missed\": true, \"told\": false}'::jsonb WHERE id=%s", (r["id"],))
    return deliver, missed


def quiet_now(t: datetime | None = None) -> bool:
    h = (t or now()).hour
    return h >= QUIET[0] or h < QUIET[1]


def late_note(r: dict) -> str:
    p = r["payload"]
    when = f"{r['fire_at'].astimezone(CFG.tz):%I:%M %p}".lstrip("0")
    what = p.get("label") or ("alarm" if (p.get("kind") or r["kind"]) == "alarm" else p.get("say"))
    return f"Late, sorry — I was off: your {when} {what}."


def missed_summary(mark: bool = True) -> str | None:
    rows = q("""SELECT id, kind, fire_at, payload FROM intents WHERE user_set AND payload->>'missed' = 'true'
                AND payload->>'told' = 'false' AND fire_at > now() - interval '2 days' ORDER BY fire_at""")
    if not rows:
        return None
    if mark:
        q("UPDATE intents SET payload = payload || '{\"told\": true}'::jsonb WHERE id = ANY(%s)", ([r["id"] for r in rows],))
    items = [f"your {r['fire_at'].astimezone(CFG.tz):%I:%M %p} {r['payload'].get('kind') or r['kind']}".replace(" 0", " ")
             + (f" ({r['payload'].get('label')})" if r["payload"].get("label") else "") for r in rows[:4]]
    return "While I was off, you missed " + ", ".join(items) + "."


def _ring_line(r: dict, round_no: int) -> str:
    p = r["payload"]
    if (p.get("kind") or r["kind"]) == "timer":
        return "Timer done!" if round_no == 0 else "Timer's still ringing — say stop."
    t = now()
    hi = f"{t:%I:%M}".lstrip("0")
    first = ("Good morning! " if t.hour < 12 else "") + f"It's {hi}. Uth jao!" if p.get("say", "").startswith("Wake") \
        else f"It's {hi}. {p.get('say')}"
    return first if round_no == 0 else ["Chalo, uth jao!", "Still ringing — say band karo, or 5 minute aur.",
                                        "Up up up!"][round_no % 3]


def tone(round_no: int, sr: int = 24000):
    """A soft three-note ring that gets louder each round (gentle wake → escalation)."""
    import numpy as np
    vol = min(0.65, 0.18 + 0.12 * round_no)
    t = np.linspace(0, 0.16, int(sr * 0.16), endpoint=False)
    notes = [np.sin(2 * np.pi * f * t) * np.minimum(1, (0.16 - t) * 30) for f in (784, 988, 1175)]
    gap = np.zeros(int(sr * 0.06))
    one_ring = np.concatenate([x for n in notes for x in (n, gap)])
    return (np.concatenate([one_ring, np.zeros(int(sr * 0.25)), one_ring]) * vol).astype("float32"), sr


class Ringer:
    """Rings one alarm/timer through Stiti's voice output (echo-cancelled, so "band karo" is heard over it),
    or through macOS sounds when the voice loop is off. Stops on dismiss / snooze / RING_MAX_S."""

    def __init__(self, row: dict, loop=None, log=print):
        self.row, self.loop, self.log = row, loop, log
        self.done = threading.Event()
        self.outcome = "missed"

    def control(self, text: str) -> str | None:
        """Voice while ringing. Returns what to say back, or None if it wasn't about the alarm."""
        if SNOOZE_RX.search(text):
            m = re.search(r"\b(\d+|paanch|das)\b", text)
            mins = {"paanch": 5, "das": 10}.get(m.group(1), None) if m else None
            mins = mins or (int(m.group(1)) if m and m.group(1).isdigit() else SNOOZE_MIN)
            self.outcome = "snoozed"
            self.done.set()
            return snooze(self.row["id"], min(30, mins))
        if DISMISS_RX.search(text):
            self.outcome = "dismissed"
            self.done.set()
            return "Good. Have a great day!" if now().hour < 12 else "Okay, stopped."
        return None

    def stop(self) -> None:
        self.outcome = "dismissed"
        self.done.set()

    def run(self) -> str:
        t0, k = time.time(), 0
        while not self.done.is_set() and time.time() - t0 < RING_MAX_S:
            line = _ring_line(self.row, k)
            if self.loop is not None and getattr(self.loop, "duplex", None) is not None and not self.loop.paused.is_set():
                self.loop.duplex.play(*tone(k))
                self.loop.say(line)                       # same duplex queue: tone then voice
            else:
                subprocess.run(["afplay", "-v", str(min(1.0, 0.3 + 0.15 * k)), "/System/Library/Sounds/Glass.aiff"],
                               capture_output=True)
                subprocess.run(["say", line], capture_output=True)
            k += 1
            self.done.wait(RING_ROUND_S)
        if self.loop is not None and getattr(self.loop, "duplex", None) is not None:
            self.loop.duplex.stop_playback()
        if not self.done.is_set():
            self.outcome = "missed"
            q("UPDATE intents SET payload = payload || '{\"missed\": true, \"told\": false}'::jsonb WHERE id=%s",
              (self.row["id"],))
        if self.outcome in ("dismissed", "missed") and not self.row.get("rrule"):
            q("UPDATE intents SET state='done' WHERE id=%s AND state='fired'", (self.row["id"],))
        self.log(f"[alarm] #{self.row['id']} {self.outcome}")
        return self.outcome
