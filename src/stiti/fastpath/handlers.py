"""Fast-path handlers: todos, alarms, reminders, timers. No LLM — works when every cloud is down.

Each handler returns a reply string, or None if it can't confidently handle the text
(the engine then falls through to the LLM). Spoken lists: max 3 items (cognitive-load rule).
"""
from __future__ import annotations

import json
import os
import re
import subprocess

from .. import cards
from ..db import one, q
from .dates import now, parse_when, readback, say_when, second_person

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


REMOVE_RX = re.compile(r"\b(remove|delete|cancel|drop|hata|hatao|nikaal|nikal)\b", re.I)
CLEAR_RX = re.compile(r"\b(clear|empty|wipe|delete all|remove all|saare hata|sab hata)\b.*\b(todos?|tasks?|list)\b|"
                      r"\b(todos?|tasks?|list)\b.*\b(clear|khaali|saaf)\b", re.I)
RESTORE_RX = re.compile(r"\b(restore|bring back|undo clear|wapas laao|wapas la do)\b.*\b(todos?|tasks?|list)\b", re.I)


def todo(text: str) -> str | None:
    t = text.strip()
    if RESTORE_RX.search(t):
        n = q("""UPDATE tasks SET status='open' WHERE status='cancelled' AND notes = 'cleared'
                 AND created_at > now() - interval '30 days' RETURNING id""")
        q("UPDATE tasks SET notes=NULL WHERE notes='cleared' AND status='open'")
        if n:
            cards.note("added", "task", [r["id"] for r in n])
        return f"Restored {len(n)} todo{'s' if len(n) != 1 else ''}." if n else "Nothing to restore."
    if CLEAR_RX.search(t):
        n = q("UPDATE tasks SET status='cancelled', notes='cleared' WHERE status='open' RETURNING id")
        if n:
            cards.note("removed", "task", [r["id"] for r in n])
        return (f"Cleared {len(n)} todo{'s' if len(n) != 1 else ''}. Say “restore my todos” if that was a mistake."
                if n else "Your list is already clear.")
    if REMOVE_RX.search(t) and re.search(r"\b(todos?|tasks?|list|kaam)\b", t, re.I):
        return _todo_remove(t)
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
    title = re.sub(r"^(to|that|ki|ke)\s+", "", title, flags=re.I)       # "add a task to call the bank"
    if parse_when(t):                                                   # drop the time words from the title
        title = re.sub(r"\b(at|by|before|on)?\s*\d{1,2}([:.]\d{2})?\s*(am|pm|baje)\b", " ", title, flags=re.I)
        title = re.sub(r"\b(at|by|before)\s+\d{1,2}([:.]\d{2})?\b", " ", title, flags=re.I)
        title = re.sub(r"\s+", " ", title).strip(" .:-")
    if not title or len(title) < 2:
        return None
    due = parse_when(t)
    row = one("INSERT INTO tasks(title, due, source) VALUES (%s,%s,'text') RETURNING id", (title, due))
    cards.note("added", "task", row["id"])
    extra = f", due {say_when(due)}" if due else ""
    return f"Got it — added “{second_person(title)}”{extra}. (task #{row['id']})"


def todo_list(limit: int = 3) -> str:
    rows = q("""SELECT id, title, due FROM tasks WHERE status='open'
                ORDER BY due NULLS LAST, created_at LIMIT %s""", (limit + 1,))
    total = one("SELECT count(*) n FROM tasks WHERE status='open'")["n"]
    if not rows:
        return "Your list is clear. Nothing pending."
    items = [f"{r['title']}" + (f" (due {readback(r['due'])})" if r["due"] else "") for r in rows[:limit]]
    more = f" …and {total - limit} more — say “more” to hear them." if total > limit else ""
    return f"{total} open. Top {min(limit, total)}: " + "; ".join(items) + "." + more


def _todo_remove(text: str) -> str | None:
    cleaned = re.sub(r"\b(remove|delete|cancel|drop|hata|hatao|do|nikaal|nikal|from|my|the|todo|todos|tasks?|list|"
                     r"kaam|se|mein|me|please)\b", " ", text, flags=re.I).strip(" .")
    if not cleaned:
        return None
    row = one("""SELECT id, title, similarity(lower(title), lower(%s)) s FROM tasks
                 WHERE status='open' ORDER BY s DESC LIMIT 1""", (cleaned,))
    if not row or row["s"] < 0.2:
        return f"I couldn't find “{cleaned}” on your list."
    q("UPDATE tasks SET status='cancelled' WHERE id=%s", (row["id"],))
    cards.note("removed", "task", row["id"])
    return f"Done — removed “{row['title']}”. (task #{row['id']})"


# words that carry no task name: "okay, it has been done" / "haan yeh wala ho gaya" → he means "it"
FILLER_RX = re.compile(r"\b(okay|ok|okk|so|yes|yeah|yep|haan|han|ha|it|it's|its|this|that|one|has|have|had|been|is|was|"
                       r"am|are|i|i've|ive|i'm|im|me|we|very|really|with|of|wala|wali|waala|kaam|yeh|ye|woh|wo|bhi|just|now|already|"
                       r"all|abhi|also|and|bro|yaar|stiti|hey|hi|finally|totally|fully|too|got|gotten|thing|stuff)\b", re.I)


SELF_RX = re.compile(r"\b(i[’']?m|i am|i[’']?ve been|main)\b", re.I)
POINT_RX = re.compile(r"\b(it|it[’']?s|that|that[’']?s|this|yeh|ye|woh|wo|wala|wali|ho gaya|ho gya|kar liya|kar diya)\b", re.I)


def _todo_done(text: str) -> str | None:
    cleaned = re.sub(r"\b(mark|as|done|complete|completed|finish(ed)?|ho gaya|ho gya|kar liya|khatam|the|my|task|todo)\b",
                     " ", text, flags=re.I).strip()
    core = re.sub(r"[’'](s|ve|m|re|ll|d)\b", " ", cleaned, flags=re.I)        # it's / i've / i'm → it / i
    core = re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", FILLER_RX.sub(" ", core))).strip()
    if not core:
        if SELF_RX.search(text):
            return None                      # "I'm done" / "I am so done" is about HIM (tired, venting) → chat
        if POINT_RX.search(text):
            return _done_it()                # "okay, it has been done" / "that's done" / "ho gaya"
        return _done_it() if cards.recent_task() else None   # bare "done" only right after a to-do was in play
    row = one("""SELECT id, title, similarity(lower(title), lower(%s)) s FROM tasks
                 WHERE status='open' ORDER BY s DESC LIMIT 1""", (core,))
    if not row or row["s"] < 0.2:
        return f"I couldn't find “{core}” on your list."
    return _mark_done(row["id"], row["title"])


def _mark_done(tid: int, title: str) -> str:
    q("UPDATE tasks SET status='done' WHERE id=%s", (tid,))
    cards.note("done", "task", tid)
    return f"Nice — “{second_person(title)}” is done."


def _done_it() -> str:
    """"It's done" with no task named: the task he just added / was just shown, else the only open one, else ask."""
    rows = q("""SELECT id, title FROM tasks WHERE status='open' AND parent_id IS NULL
                ORDER BY due NULLS LAST, created_at LIMIT 4""")
    if not rows:
        return "Your list is already clear."
    rid = cards.recent_task()
    pick = one("SELECT id, title FROM tasks WHERE id=%s AND status='open'", (rid,)) if rid else None
    if pick is None and len(rows) == 1:
        pick = rows[0]
    if pick is not None:
        return _mark_done(pick["id"], pick["title"])
    names = [f"“{second_person(r['title'])}”" for r in rows[:3]]
    cards.note("ask", "task", [])
    return "Which one is done — " + ", ".join(names[:-1]) + " or " + names[-1] + "?"


# ---------------- alarms / reminders / timers ----------------
def timeish(text: str) -> str | None:
    """Alarms / reminders / timers → life/alarms.py (create, list, cancel, move, snooze; recurring)."""
    from ..life import alarms
    return alarms.handle(text)


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
                   ORDER BY fire_at LIMIT 1) RETURNING kind, fire_at, ek_identifier""")
    if row and row.get("ek_identifier"):
        from ..connectors import eventkit
        eventkit.remove_reminder(row["ek_identifier"])
    return f"Cancelled the {row['kind']} for {readback(row['fire_at'])}." if row else "Nothing to cancel."


def fire_due(notify=print) -> list[dict]:
    """Terminal mode (`stiti chat`): announce what's due; missed ones (late past their grace) are only reported.
    The menubar app uses life/alarms.py directly (real ringing, snooze, voice dismiss)."""
    from ..life import alarms
    deliver, missed = alarms.due()
    for r in deliver:
        msg = r["payload"].get("say", "Reminder")
        notify(f"⏰ {msg}")
        try:
            subprocess.Popen(["osascript", "-e", f'display notification {json.dumps(msg)} with title "Stiti"'])
            subprocess.Popen(["say", msg])
        except OSError:
            pass
    if missed and (m := alarms.missed_summary()):
        notify(f"⏰ {m}")
    return deliver


def control(text: str) -> str | None:
    return "Okay." if re.search(r"^(stop|ruk|chup|bas|cancel|never mind|pause)\b", text.strip(), re.I) else None
