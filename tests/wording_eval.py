"""Less repetitive wording (D50): her fixed lines have 4–6 variants each, the same wording never comes twice in a
row, the choice is deterministic, every variant passes her own rules — and she still only says "added / set / done"
after the row was really written.

uv run python tests/wording_eval.py     (throwaway DB; no LLM, no audio)
"""
from __future__ import annotations

import os
import re
import sys
from datetime import datetime, timedelta

os.environ.setdefault("STITI_EVENTKIT", "off")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from stiti import say                                                    # noqa: E402
from stiti.brain import psych                                            # noqa: E402
from stiti.config import CFG                                             # noqa: E402
from stiti.db import one, q                                              # noqa: E402
from stiti.fastpath import handlers                                      # noqa: E402
from stiti.life import alarms                                            # noqa: E402

fails = 0
n_checks = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global fails, n_checks
    n_checks += 1
    print(f"  {'✓' if ok else '✗'} {name}" + (f" — {detail}" if not ok and detail else ""))
    fails += 0 if ok else 1


SLOTS = dict(item="“call mom”", due=", due tomorrow", names="“gym”, “laundry” or “call mom”", said="gym and laundry",
             n=4, k=3, slot="tomorrow at 6 AM", label="call the bank", mins="10 minutes", at="4:10 PM",
             when="today at 4 PM", what="alarm today at 9 PM", head="alarm today at 9 PM", more=".", kind="reminder",
             notes="you left Orbitly", facts="your exam is on Friday")
COVERED = ("todo_added", "todo_done", "todo_removed", "reminder_set", "alarm_set", "timer_set", "cancelled_one",
           "listed", "list_one", "list_some", "list_many", "ask_when", "ask_ampm", "todo_which_done", "clarify",
           "got_it", "update_ack")

print("variants")
for k in COVERED:
    check(f"{k}: 4–6 different wordings", 4 <= len(set(say.LINES[k])) == len(say.LINES[k]) <= 6, str(len(say.LINES[k])))
check("every other line has at least 3", all(len(set(v)) == len(v) >= 3 for v in say.LINES.values()))
check("acks while a slow action runs: 4 each, fillers ≥ 4", all(len(set(v)) == len(v) >= 4 for v in say.ACKS.values())
      and len(set(say.FILLERS)) == len(say.FILLERS) >= 4)
every = [(k, v) for k in say.LINES for v in say.variants(k, **SLOTS)]
spoken = [v for _, v in every] + [x for v in say.ACKS.values() for x in v] + say.FILLERS
check("no variant trips her own rules (banned phrases, machine-talk, guilt)", all(
    not psych.BANNED_RX.search(v) and not psych.MACHINE_RX.search(v) and psych.lint(v) == v for v in spoken),
    str([v for v in spoken if psych.BANNED_RX.search(v) or psych.MACHINE_RX.search(v) or psych.lint(v) != v][:3]))
check("short: a confirmation is ≤ 14 words", all(len(v.split()) <= 14 for k, v in every if k in say.CLOSES + ("todo_done",)),
      str([v for k, v in every if k in say.CLOSES and len(v.split()) > 14][:2]))
check("the slot is always said back (the item, the time)", all("“call mom”" in v for v in say.variants("todo_added", **SLOTS))
      and all("tomorrow at 6 AM" in v for k in ("alarm_set", "reminder_set", "reminder_ask_label") for v in say.variants(k, **SLOTS))
      and all("call the bank" in v for v in say.variants("reminder_set", **SLOTS))
      and all("10 minutes" in v for v in say.variants("timer_set", **SLOTS)))
check("at most one question per line; the 'ask' lines do ask", all(v.count("?") <= 1 for v in spoken)
      and all("?" in v for k in ("ask_when", "todo_which_done", "reminder_ask_label") for v in say.variants(k, **SLOTS)))
check("English only, apart from the one old example (“shaam 6 baje”)", [v for v in spoken if re.search(
    r"\b(haan|accha|theek|karo|bolo|baje|yaar|nahi|kal|aaj)\b", v, re.I)] == [say.LINES["ask_ampm"][0]])

print("rotation")
say.reset()
seq = [say.line("todo_added", item=f"“t{i}”", due="") for i in range(12)]
check("12 adds: never the same wording twice in a row", all(a.split("“")[0] != b.split("“")[0] for a, b in zip(seq, seq[1:])), str(seq[:4]))
check("…and every wording gets used", len({s.split("“")[0] + s.split("”")[1] for s in seq}) == len(say.LINES["todo_added"]))
check("the first one is the old wording", seq[0] == "Got it — added “t0”.")
say.reset()
check("deterministic: the same calls give the same lines", seq == [say.line("todo_added", item=f"“t{i}”", due="") for i in range(12)])
say.reset()
mixed = [say.line("todo_added", **SLOTS), say.line("reminder_set", **SLOTS), say.line("label_set", said="call mom", when="today at 4 PM"),
         say.line("update_ack", **SLOTS), say.line("todo_added", **SLOTS), say.line("alarm_set", **SLOTS), say.line("todo_removed", **SLOTS)]
first = [re.match(r"[A-Za-z']+", m).group(0) for m in mixed]
check("different kinds of line in a row don't open with the same word either", all(a != b for a, b in zip(first, first[1:])), str(mixed))
for k in say.LINES:
    say.reset()
    out = [say.line(k, **SLOTS) for _ in range(9)]
    if any(a == b for a, b in zip(out, out[1:])):
        check(f"{k}: no immediate repeat", False, str(out[:3]))
        break
else:
    check("no line of any kind repeats itself back to back", True)
say.reset()
idx = [say.turn("ack:web", 4) for _ in range(8)]
check("pre-made ack audio rotates too", idx == [0, 1, 2, 3, 0, 1, 2, 3])

print("she only says it when it was done")
q("DELETE FROM tasks")
q("DELETE FROM intents")
say.reset()
said = []
for i, t in enumerate(("buy milk", "call the bank", "book train tickets", "renew passport", "water the plants", "pay rent")):
    r = handlers.todo(f"add {t}")
    said.append(r)
    check(f"add #{i + 1}: the row is there and she names it", f"“{t}”" in r and say.confirms(r.split(" (task #")[0])
          and one("SELECT count(*) n FROM tasks WHERE title=%s AND status='open'", (t,))["n"] == 1, r)
check("six adds → no wording twice in a row", all(a.split("“")[0] != b.split("“")[0] for a, b in zip(said, said[1:])), str(said))
r = handlers.todo("mark buy milk as done")
check("done → the row is done and she names it", "“buy milk”" in r and one("SELECT status FROM tasks WHERE title='buy milk'")["status"] == "done", r)
r2 = handlers.todo("mark call the bank as done")
check("a second 'done' is worded differently", r.split("“")[0] != r2.split("“")[0] or r.split("”")[1] != r2.split("”")[1], f"{r} | {r2}")
r = handlers.todo("remove renew passport from my list")
check("removed → the row is cancelled and she names it", "renew passport" in r
      and one("SELECT status FROM tasks WHERE title='renew passport'")["status"] == "cancelled", r)
before = one("SELECT count(*) n FROM tasks WHERE status='open'")["n"]
r = handlers.todo("remove fly to the moon from my list")
check("nothing like it on the list → she says so, claims nothing, changes nothing",
      r in say.variants("todo_not_found", item="“fly to moon”") and not say.confirms(r) and one("SELECT count(*) n FROM tasks WHERE status='open'")["n"] == before, r)
q("UPDATE tasks SET status='done' WHERE status='open'")
r = handlers.todo("it's done")
check("nothing open + 'it's done' → 'your list is clear', no claim", r in say.variants("list_already_clear") and not say.confirms(r), r)

NOW = datetime.now(CFG.tz)
got = []
for text, slot in (("set an alarm for 6 am", "6 AM"), ("wake me up at 7 am", "7 AM"), ("set an alarm for 8:30 am", "8:30 AM"),
                   ("remind me at 9 pm to call mom", "9 PM"), ("remind me at 10 pm to lock the door", "10 PM")):
    r = alarms.handle(text)
    m = re.search(r"\(#(\d+)\)", r or "")
    row = one("SELECT state, fire_at FROM intents WHERE id=%s", (int(m.group(1)),)) if m else None
    got.append(r)
    check(f"{text!r} → the row is pending and she says the time", row is not None and row["state"] == "pending"
          and slot in r and say.confirms(re.sub(r"\s*\(#\d+\)", "", r)), str(r))
check("alarms / reminders in a row: no wording twice running", all(
    re.sub(r"\d.*", "", a) != re.sub(r"\d.*", "", b) for a, b in zip(got, got[1:])), str(got))
r = alarms.handle("set a timer for 10 minutes")
check("timer → a row, '10 minutes' said back", "10 minutes" in r and one("SELECT count(*) n FROM intents WHERE payload->>'kind'='timer'")["n"] == 1, r)
r = alarms.handle("cancel my 6 am alarm")
check("cancel → that row is cancelled and she names it", "6 AM" in r and one(
    "SELECT count(*) n FROM intents WHERE state='cancelled'")["n"] == 1, r)
q("UPDATE intents SET state='cancelled'")
r = alarms.handle("cancel my alarm")
check("nothing set → 'nothing to cancel', no claim", r in say.variants("nothing_to_cancel"), r)
r = alarms.handle("what alarms do I have")
check("nothing set → she says so", r in say.variants("none_set"), r)
r = alarms.create("remind me today to call mom", ref=NOW.replace(hour=23, minute=50))
check("no usable time → she asks for it and sets nothing", r is not None and "?" in r
      and one("SELECT count(*) n FROM intents WHERE state='pending'")["n"] == 0, str(r))

print("confirm-and-close only after a finished action")
check("an 'added / set / removed' line earns “Anything else?”", all(say.confirms(v) for k in say.CLOSES for v in say.variants(k, **SLOTS)
                                                                     if not v.endswith("?")))
check("a question, a 'not found', a list or a 'done' does not", not any(
    say.confirms(v) for k in ("reminder_ask_label", "todo_not_found", "list_one", "list_empty", "nothing_to_cancel", "ask_when",
                              "got_it", "clarify") for v in say.variants(k, **SLOTS)))

print("voice: the ack she says while a slow action runs")
import queue                                                             # noqa: E402

from stiti.voice import speaker as S                                     # noqa: E402


class _Loop:
    acks = {"web": [(f"audio{i}", 24000) for i in range(4)]}
    ack_text = S.ACKS


sp = S.Speaker.__new__(S.Speaker)
sp.loop, sp.texts, sp.audio = _Loop(), queue.Queue(), queue.Queue()
import threading                                                         # noqa: E402

sp.cancelled = threading.Event()
say.reset()
for _ in range(5):
    sp.texts.put(("ack", "web"))
sp.texts.put(S._END)
sp._synth()
heard = []
while True:
    item = sp.audio.get_nowait()
    if item is S._END:
        break
    heard.append((item[0][1], item[1]))
check("five web look-ups in a row → the ack changes every time, text matches its audio",
      all(a != b for a, b in zip(heard, heard[1:])) and all(t == S.ACKS["web"][int(a[-1])] for t, a in heard), str(heard))
_Loop.acks, _Loop.ack_text = {"calendar": ("one", 24000)}, {"calendar": "Checking your calendar."}
sp.texts.put(("ack", "calendar"))
sp.texts.put(S._END)
sp._synth()
check("a single pre-made ack (old shape) still plays", sp.audio.get_nowait()[0] == ("ack", "Checking your calendar."))

total = sum(len(v) for v in say.LINES.values())
print(f"wording: {n_checks - fails}/{n_checks} checks passed · {len(say.LINES)} lines, {total} wordings "
      f"(+ {sum(len(v) for v in say.ACKS.values())} acks, {len(say.FILLERS)} fillers)")
sys.exit(1 if fails else 0)
