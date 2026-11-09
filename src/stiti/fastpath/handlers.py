"""Fast-path handlers: todos, alarms, reminders, timers. No LLM — works when every cloud is down.

Each handler returns a reply string, or None if it can't confidently handle the text
(the engine then falls through to the LLM). Spoken lists: max 3 items (cognitive-load rule).
"""
from __future__ import annotations

import json
import re
import subprocess

from ..db import one, q
from .dates import now, parse_when, readback

# ---------------- todos ----------------
LIST_RX = re.compile(r"\b(what are my|show( me)?|list|kya kya|pending|bacha|baaki|kaunse|my (todos?|tasks)|"
                     r"todos?\s*\??$|tasks?\s*\??$|(todos?|tasks?|kaam|list)\b.*\b(kya|dikhao|batao|sunao|hain|hai)\b)", re.I)
DONE_RX = re.compile(r"\b(mark|complete|completed|done|finish(ed)?|ho gaya|ho gya|kar liya|khatam)\b", re.I)
ADD_TRIGGERS = re.compile(
    r"^(please\s+)?(add( a)?( new)?( todo| task| to-?do)?( to my (list|todos?))?|new (todo|task)|naya (task|todo)|"
    r"todo|task|remind me to do)\s*[:\-]?\s*|\s*(to my (todo|task)s?( list)?|to (the|my) list|"
    r"(todo|list|task) (mein|me) (daal|dal|add kar)( do| dena)?|daal do|dal do|add kar do|add karo)\s*$", re.I)


ADD_START = re.compile(r"^(please\s+)?(add|new (todo|task)|naya (task|todo)|todo|task)\b|\b(daal|dal) do\b|\badd kar", re.I)
DAYWORDS = re.compile(r"\b(kal|aaj|parso|tomorrow|today|ke liye|for)\b", re.I)


def todo(text: str) -> str | None:
    t = text.strip()
    if ADD_START.search(t):
        return _todo_add(t)
    if DONE_RX.search(t):
        return _todo_done(t)
    if LIST_RX.search(t) and not re.search(r"\b(add|daal|dal|naya)\b", t, re.I):
        return todo_list()
    return None


def _todo_add(t: str) -> str | None:
    if ":" in t:  # "kal ke liye todo daal do: electricity bill bharna"
        title = t.split(":", 1)[1].strip(" .:-")
    else:
        title = ADD_TRIGGERS.sub("", t).strip(" .:-")
        title = ADD_TRIGGERS.sub("", title).strip(" .:-")
    title = DAYWORDS.sub(" ", title) if parse_when(t) else title
    title = re.sub(r"\s+", " ", title).strip(" .:-")
    if not title or len(title) < 2:
        return None
    due = parse_when(t)
    row = one("INSERT INTO tasks(title, due, source) VALUES (%s,%s,'text') RETURNING id", (title, due))
    extra = f", due {readback(due)}" if due else ""
    return f"Added: “{title}”{extra}. (task #{row['id']})"


def todo_list(limit: int = 3) -> str:
    rows = q("""SELECT id, title, due FROM tasks WHERE status='open'
                ORDER BY due NULLS LAST, created_at LIMIT %s""", (limit + 1,))
    total = one("SELECT count(*) n FROM tasks WHERE status='open'")["n"]
    if not rows:
        return "Your list is clear. Nothing pending."
    items = [f"{r['title']}" + (f" (due {readback(r['due'])})" if r["due"] else "") for r in rows[:limit]]
    more = f" …and {total - limit} more — say “more” to hear them." if total > limit else ""
    return f"{total} open. Top {min(limit, total)}: " + "; ".join(items) + "." + more


def _todo_done(text: str) -> str | None:
    cleaned = re.sub(r"\b(mark|as|done|complete|completed|finish(ed)?|ho gaya|ho gya|kar liya|khatam|the|my|task|todo)\b",
                     " ", text, flags=re.I).strip()
    if not cleaned:
        return None
    row = one("""SELECT id, title, similarity(lower(title), lower(%s)) s FROM tasks
                 WHERE status='open' ORDER BY s DESC LIMIT 1""", (cleaned,))
    if not row or row["s"] < 0.2:
        return f"I couldn't find an open task matching “{cleaned}”."
    q("UPDATE tasks SET status='done' WHERE id=%s", (row["id"],))
    return f"Nice — “{row['title']}” is done."


# ---------------- alarms / reminders / timers ----------------
def timeish(text: str) -> str | None:
    t = text.lower()
    if re.search(r"\b(cancel|delete|hata|band kar).*(alarm|reminder|timer)|(alarm|reminder|timer).*(cancel|hata)", t):
        return _cancel_next()
    if re.search(r"\b(my|kitne|which|what|list).*(alarms?|reminders?)\b", t) and not re.search(r"\bset\b", t):
        return list_intents()
    when = parse_when(text)
    if when is None:
        if re.search(r"\b\d{1,2}\b", t):
            return "Morning or evening? Say it like “6 am” or “shaam 6 baje”."
        return None
    kind = "timer" if "timer" in t else "alarm" if re.search(r"\b(alarm|wake|uth|utha)", t) else "reminder"
    what = _reminder_text(text) if kind == "reminder" else None
    payload = {"say": what or ("Timer done!" if kind == "timer" else "Wake up, it's time!"), "kind": kind}
    dbkind = "alarm" if kind in ("alarm", "timer") else "reminder"
    row = one("""INSERT INTO intents(kind, fire_at, payload, user_set) VALUES (%s,%s,%s,true) RETURNING id""",
              (dbkind, when, json.dumps(payload)))
    label = {"timer": "Timer", "alarm": "Alarm", "reminder": "Reminder"}[kind]
    about = f" — “{what}”" if what else ""
    return f"{label} set for {readback(when)}{about}. (#{row['id']})"


def _reminder_text(text: str) -> str | None:
    m = re.search(r"\b(?:to|that|ki|ke liye|about)\s+(.+)$", text, re.I)
    if not m:
        return None
    s = re.sub(r"\b(yaad dila(na|do|dena)?|remind me|at \d.*|kal|aaj|parso|subah|shaam|raat|\d{1,2}(:\d{2})?\s*(am|pm|baje)?)\b",
               " ", m.group(1), flags=re.I)
    s = re.sub(r"\s+", " ", s).strip(" .")
    return s or None


def list_intents(limit: int = 3) -> str:
    rows = q("""SELECT id, kind, fire_at, payload FROM intents WHERE state IN ('pending','armed')
                AND fire_at > now() ORDER BY fire_at LIMIT %s""", (limit,))
    if not rows:
        return "No alarms or reminders set."
    return "Coming up: " + "; ".join(
        f"{r['kind']} {readback(r['fire_at'])}" + (f" — {r['payload'].get('say')}" if r['kind'] == 'reminder' else "")
        for r in rows) + "."


def _cancel_next() -> str:
    row = one("""UPDATE intents SET state='cancelled' WHERE id = (
                   SELECT id FROM intents WHERE state IN ('pending','armed') AND fire_at > now()
                   ORDER BY fire_at LIMIT 1) RETURNING kind, fire_at""")
    return f"Cancelled the {row['kind']} for {readback(row['fire_at'])}." if row else "Nothing to cancel."


def fire_due(notify=print) -> list[dict]:
    """Called by the scheduler loop every few seconds. Durable: state lives in Postgres."""
    rows = q("""UPDATE intents SET state='fired', last_fired_at=now()
                WHERE state IN ('pending','armed') AND fire_at <= now() RETURNING id, kind, payload""")
    for r in rows:
        msg = r["payload"].get("say", "Reminder")
        notify(f"⏰ {msg}")
        try:  # macOS banner + built-in voice (free, local). EventKit mirror comes in Phase 5.
            subprocess.Popen(["osascript", "-e", f'display notification {json.dumps(msg)} with title "Stiti"'])
            subprocess.Popen(["say", msg])
        except OSError:
            pass
    return rows


def control(text: str) -> str | None:
    return "Okay." if re.search(r"^(stop|ruk|chup|bas|cancel|never mind|pause)\b", text.strip(), re.I) else None
