"""Her short fixed lines — each with a few wordings, never the same one twice in a row (D50).

Until now every confirmation was one string ("Got it — added …", "Done — alarm …"), so ten to-dos in a row sounded
like a machine. Each line here has 4–6 variants in her voice: warm, brief, the key slot (the item, the time) always
said back, no machine-talk. All of them are original text. Home Assistant's `intents` responses, Leon's to-do / timer
answers and the OVOS alerts dialogs were read to see WHICH situations to word; no sentence was copied.

`line(key, **slots)` picks the next variant in a fixed rotation (deterministic: after `reset()` the sequence is always
the same), and skips a variant that opens with the same word as the line she said just before, so "Got it — … /
Got it — …" does not happen across different kinds of line either. The first variant of every key is the old wording.
A line only WORDS what the caller already did — the caller writes the row first, then asks for the sentence.
"""
from __future__ import annotations

import re
import threading

LINES: dict[str, list[str]] = {
    # ---- to-dos
    "todo_added": ["Got it — added {item}{due}.", "Added {item}{due}.", "Okay, {item} is on your list{due}.",
                   "On your list now: {item}{due}.", "Done — {item} is added{due}."],
    "todo_done": ["Nice — {item} is done.", "Ticked off {item}.", "Good, {item} is off your list.",
                  "Marked {item} as done.", "{item} — done."],
    "todo_removed": ["Done — removed {item}.", "Removed {item}.", "Okay, {item} is off your list.",
                     "Took {item} off your list."],
    "todo_not_found": ["I couldn't find {item} on your list.", "I don't see {item} on your list.",
                       "There's no {item} on your list.", "Nothing like {item} on your list."],
    "todo_which_done": ["Which one is done — {names}?", "Which one — {names}?", "Which one did you finish — {names}?",
                        "Which of these is done: {names}?"],
    "list_empty": ["Your list is clear. Nothing pending.", "Nothing pending. Your list is clear.",
                   "All clear — nothing on your list.", "Nothing on your list right now."],
    "list_already_clear": ["Your list is already clear.", "Nothing left on your list — it's clear.",
                           "Your list is clear already.", "There's nothing open, your list is clear."],
    "list_one": ["Just one: {said}.", "Only one thing: {said}.", "One thing left: {said}.", "Just this: {said}."],
    "list_some": ["You have {n}: {said}.", "{n} things: {said}.", "There are {n}: {said}.", "{n} on your list: {said}."],
    "list_many": ["You have {n}. Top {k}: {said}. Say “more” for the rest.",
                  "{n} on your list. The first {k}: {said}. Say “more” for the rest.",
                  "There are {n}. Top {k}: {said}. Say “more” to hear the rest.",
                  "{n} open. First {k}: {said}. Say “more” for the rest."],
    # ---- alarms / reminders / timers
    "alarm_set": ["Done — alarm {slot}.", "Alarm set, {slot}.", "Okay, alarm {slot}.", "You're set: alarm {slot}.",
                  "Alarm's on for {slot}."],
    "reminder_set": ["Got it — reminder {slot}: {label}.", "Okay, I'll remind you {slot}: {label}.",
                     "Reminder {slot}: {label}.", "Will do — reminder {slot}: {label}.",
                     "Sure, I'll remind you {slot}: {label}."],
    "reminder_ask_label": ["Got it — reminder {slot}. What's it for?", "Okay, reminder {slot}. What's it for?",
                           "Reminder {slot}. What should I remind you about?", "Sure, {slot}. What's it for?"],
    "timer_set": ["Timer set for {mins} (rings at {at}).", "Okay, {mins} on the timer (rings at {at}).",
                  "Timer's running: {mins} (rings at {at}).", "Started — {mins} timer (rings at {at}).",
                  "{mins}, starting now (rings at {at})."],
    "label_set": ["Got it — {said}, {when}.", "Okay — {said}, {when}.", "Right — {said}, {when}.",
                  "Sure: {said}, {when}."],
    "label_skip": ["Okay, I'll just ping you then.", "Fine, I'll just ping you then.", "Alright — a plain ping it is.",
                   "Okay, no note. I'll ping you then."],
    "cancelled_one": ["Cancelled the {what}.", "Okay, the {what} is off.", "The {what} is cancelled.",
                      "Dropped the {what}."],
    "cancelled_all": ["Cancelled all {n}.", "All {n} cancelled.", "Okay, all {n} are off.", "Cleared all {n}."],
    "nothing_to_cancel": ["Nothing to cancel.", "There's nothing set to cancel.", "Nothing's set, so nothing to cancel.",
                          "No alarm or reminder to cancel."],
    "none_set": ["No alarms or reminders set.", "Nothing's set right now.", "You have no alarms or reminders.",
                 "Nothing coming up — no alarms, no reminders."],
    "listed": ["You have {n}: {head}{more}", "{n} coming up: {head}{more}", "There are {n}: {head}{more}",
               "{n} set: {head}{more}"],
    "moved": ["Moved: {what}.", "Changed it — {what}.", "Okay, shifted: {what}.", "Now it's {what}."],
    "fixed": ["Fixed — {kind} {when}.", "Okay, corrected: {kind} {when}.", "Changed it — {kind} {when}.",
              "Right, {kind} {when} it is."],
    # ---- a detail is missing: ask for it
    "ask_when": ["What time should I remind you? Say it like “at 7 pm”.", "For when? Say it like “at 7 pm”.",
                 "When should I remind you? Something like “at 7 pm”.", "What time? You can say “at 7 pm”."],
    "ask_ampm": ["Morning or evening? Say it like “6 am” or “shaam 6 baje”.", "Morning or evening? “6 am” or “6 pm”.",
                 "Is that morning or evening?", "Morning or evening — which one?"],
    "ask_move": ["Which one, and to what time? Say: move my 7 am alarm to 7:30.",
                 "Which one, and to when? Like: move my 7 am alarm to 7:30.",
                 "Which alarm, and what's the new time?", "Tell me which one and the new time."],
    # ---- she did not catch him (voice)
    "clarify": ["Sorry, say that again?", "Sorry, I didn't catch that.", "Hmm, say that once more?",
                "I missed that — once more?", "Sorry, one more time?"],
    # ---- he told her something / nothing else to say
    "got_it": ["Got it.", "Okay.", "Right.", "Mm, okay.", "Alright."],
    "update_ack": ["Got it — updated: {notes}.", "Okay, updated: {notes}.", "Updated — {notes}.",
                   "Right, changed that: {notes}."],
    "remember_ack": ["Noted — I'll remember that.", "Okay, I'll remember that.", "Saved. I'll remember that.",
                     "Got it, I'll remember that."],
    "learned": ["Noted — {facts}.", "Okay — {facts}.", "Got that: {facts}.", "Right, {facts}."],
    "tool_cancelled": ["Okay, cancelled.", "Okay, I'll leave it.", "Alright, dropped.", "Fine, not doing it."],
    "nag_done": ["Nice, done.", "Good, done.", "Done — nice."],
    "nag_stop": ["Okay, I won't remind you again.", "Okay, I'll stop reminding you.", "Alright, no more reminders on that."],
}
# After one of these she closes with "Anything else?" — a finished create / add / remove (engine.turn).
CLOSES = ("todo_added", "todo_removed", "alarm_set", "reminder_set", "timer_set", "label_set")

# ---- voice: said from pre-made audio while a slow action runs / while she thinks (voice/speaker.py)
ACKS: dict[str, list[str]] = {
    "calendar": ["Checking your calendar.", "Let me look at your calendar.", "Pulling up your calendar.",
                 "Okay, your calendar."],
    "mail": ["Let me check your mail.", "Checking your mail.", "Looking at your inbox.", "Okay, your mail."],
    "plan": ["Okay, let me plan your day.", "Let me put your day together.", "Planning your day.",
             "Okay, sorting out your day."],
    "tools": ["Let me look.", "Let me check.", "Looking.", "Okay, checking."],
    "web": ["Let me look that up.", "Looking that up.", "Let me find out.", "Okay, checking online."],
}
FILLERS = ["Hmm.", "Hmm, let me think.", "Let me see.", "Mm.", "Right, so."]

_lock = threading.Lock()
_at: dict[str, int] = {}            # key → index of the variant used last
_opener = ""                        # the first word of the line she said last (any key)
_SLOT = re.compile(r"\{(\w+)\}")


def _open(template: str) -> str:
    m = re.match(r"[A-Za-z']+", template)
    return m.group(0).lower() if m else ""


def reset() -> None:
    """Start the rotation again (tests; a fresh process starts here anyway)."""
    global _opener
    with _lock:
        _at.clear()
        _opener = ""


def turn(key: str, n: int) -> int:
    """The next index 0..n-1 for a rotating choice (pre-made ack / filler audio), never the one used last."""
    with _lock:
        i = (_at.get(key, -1) + 1) % max(1, n)
        _at[key] = i
        return i


def line(key: str, **slots) -> str:
    """The next wording of `key`, slots filled in. Never the wording used last for this key; and when another
    variant exists, not one that opens with the same word as the previous line she said."""
    global _opener
    opts = LINES[key]
    with _lock:
        i = (_at.get(key, -1) + 1) % len(opts)
        for _ in range(len(opts) - 2):                  # (keeps at least the "not the last one" guarantee)
            if not _opener or _open(opts[i]) != _opener:
                break
            i = (i + 1) % len(opts)
        _at[key] = i
        _opener = _open(opts[i])
    out = opts[i].format(**slots)
    return out[:1].upper() + out[1:]


def _rx(template: str) -> re.Pattern:
    parts = _SLOT.split(template)       # literal, slot, literal, slot, …
    pat = "".join(re.escape(p) if i % 2 == 0 else ".*?" for i, p in enumerate(parts))
    return re.compile(pat + r"\s*", re.S | re.I)


_CLOSE_RX = [_rx(t) for k in CLOSES for t in LINES[k]]


def confirms(reply: str) -> bool:
    """Is this one of her finished-action confirmations (added / removed / set)? Only those earn "Anything else?"."""
    r = (reply or "").strip()
    return bool(r) and not r.endswith("?") and any(rx.fullmatch(r) for rx in _CLOSE_RX)


def variants(key: str, **slots) -> list[str]:
    """Every wording of `key` with these slots filled in (tests: "she said one of her lines for this, with the item")."""
    out = [t.format(**slots) for t in LINES[key]]
    return [o[:1].upper() + o[1:] for o in out]
