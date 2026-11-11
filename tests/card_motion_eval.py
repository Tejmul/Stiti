"""Card motion eval: what the on-screen card PLAYS when a to-do / reminder changes (headless: no window, no mic).

Owner's ask (2026-11-11): "I tell it a to-do → it's noted on the card. I say 'okay, it has been done' → the card
appears, the item gets struck, and it goes away from the list. Same for everything else."
Covers: the change channel (handlers → cards.note → engine.last_card.focus), "it's done" with no task named, the
pure timeline (model.choreography) and the fold-away layout (model.collapse). Throwaway test DB only.

STITI_DB=postgresql:///stiti_test STITI_HOME=<tmp> uv run python tests/card_motion_eval.py
"""
from __future__ import annotations

import os
import sys

os.environ.setdefault("STITI_LIVE_WARM", "0")
os.environ.setdefault("STITI_EVENTKIT", "off")

db = os.environ.get("STITI_DB", "")
if not db.rstrip("/").split("/")[-1].startswith("stiti_test"):
    sys.exit(f"refusing to run against {db!r}: use a stiti_test* database")

from stiti import cards                                                # noqa: E402
from stiti.db import one, q                                            # noqa: E402
from stiti.fastpath import handlers                                    # noqa: E402
from stiti.overlay import model as M                                   # noqa: E402

passed = total = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global passed, total
    total += 1
    passed += bool(cond)
    print(f"  {'✓' if cond else '✗'} {name}" + (f" — {detail}" if detail and not cond else ""))


def reset() -> None:
    q("DELETE FROM tasks")
    q("DELETE FROM intents")
    cards.take()
    cards.remember_task(None)


# ================================================================ pure timeline
print("timeline")
card = {"kind": "todos", "title": "2 things to do", "focus": {"op": "done", "ids": [2]},
        "items": [{"id": 1, "text": "Start resume", "meta": ""}, {"id": 2, "text": "Drink water", "meta": ""},
                  {"id": 3, "text": "DSA practice", "meta": ""}]}
lay = M.layout(card)
check("done row is marked op=done, others aren't", [r.op for r in lay.rows] == [None, "done", None])
check("eyebrow still counts it before it leaves (3 OPEN)", lay.eyebrow == "TO-DO · 3 OPEN", lay.eyebrow)
steps = M.choreography(lay)
names = [(s, i) for _, s, i in steps]
check("every row enters, staggered top → bottom",
      [i for s, i in names if s == "enter"] == [0, 1, 2]
      and [t for t, s, _ in steps if s == "enter"] == sorted(t for t, s, _ in steps if s == "enter"))
t_strike = next(t for t, s, i in steps if s == "strike")
t_collapse = next(t for t, s, i in steps if s == "collapse")
t_enter = next(t for t, s, i in steps if s == "enter" and i == 1)
check("strike comes after the row is in, collapse after the strike has been seen",
      t_enter < t_strike and t_collapse >= t_strike + M.STRIKE_S + 0.5, f"{t_enter=} {t_strike=} {t_collapse=}")
check("whole done animation fits while she says it (< 2.5 s)", t_collapse + M.COLLAPSE_S < 2.5, f"{t_collapse=}")
new = M.collapse(lay, {1})
check("after fold: rows below move up by one row", new.rows[2].y == lay.rows[1].y and new.rows[0].y == lay.rows[0].y)
check("after fold: card is one row shorter", abs((lay.height - new.height) - M.ROW_H) < 1e-6, f"{lay.height} → {new.height}")
check("after fold: eyebrow counts down (2 OPEN)", new.eyebrow == "TO-DO · 2 OPEN", new.eyebrow)
check("folded row has no height (can't be clicked)", new.rows[1].h == 0 and M.row_at(new, lay.rows[1].y + 5) != 1)

last = M.layout({"kind": "todos", "title": "Nothing on your list", "focus": {"op": "done", "ids": [9]},
                 "items": [{"id": 9, "text": "Drink water", "meta": ""}]})
check("finishing the last to-do: 1 OPEN → 'All clear'", last.eyebrow == "TO-DO · 1 OPEN"
      and M.collapse(last, {0}).title == "All clear" and M.collapse(last, {0}).eyebrow == "TO-DO", last.eyebrow)

add = M.layout({"kind": "todos", "title": "2 things to do", "focus": {"op": "added", "ids": [5]},
                "items": [{"id": 4, "text": "Gym", "meta": ""}, {"id": 5, "text": "Buy milk", "meta": ""}]})
s_add = M.choreography(add)
check("added row: enter → arrive (tint + bounce) → settle", [s for _, s, i in s_add if i == 1] == ["enter", "arrive", "settle"])
check("added row: no strike / collapse", not any(s in ("strike", "collapse") for _, s, _ in s_add))
check("added: eyebrow is the new count", add.eyebrow == "TO-DO · 2 OPEN", add.eyebrow)

many = M.layout({"kind": "todos", "title": "Nothing on your list", "focus": {"op": "removed", "ids": [1, 2, 3]},
                 "items": [{"id": i, "text": f"t{i}", "meta": ""} for i in (1, 2, 3)]})
s_many = M.choreography(many)
strikes = [t for t, s, _ in s_many if s == "strike"]
collapses = {t for t, s, _ in s_many if s == "collapse"}
check("clearing many: strikes one after another, then all fold together",
      strikes == sorted(strikes) and len(set(strikes)) == 3 and len(collapses) == 1 and min(collapses) > max(strikes))

rm = M.choreography(lay, reduce_motion=True)
check("Reduce Motion: no slide-ins, but the strike + removal still happen",
      not any(s == "enter" for _, s, _ in rm) and any(s == "strike" for _, s, _ in rm) and any(s == "collapse" for _, s, _ in rm))
big = M.layout({"kind": "todos", "title": "6 things to do",
                "items": [{"id": i, "text": f"t{i}", "meta": ""} for i in range(6)]})
check("stagger stays short with 6 rows (≤ 0.4 s to the last row)",
      max(t for t, s, _ in M.choreography(big) if s == "enter") <= 0.4)
rem = M.layout({"kind": "reminders", "title": "Coming up", "focus": {"op": "cancelled", "ids": [7]},
                "items": [{"id": 7, "text": "Call mom", "meta": "today, 4 PM"}, {"id": 8, "text": "Alarm", "meta": "tomorrow, 6 AM"}]})
check("cancelled reminder: counted (2) until it folds, then 1",
      rem.eyebrow == "REMINDERS · 2" and M.collapse(rem, {0}).eyebrow == "REMINDERS · 1", rem.eyebrow)
check("plain list (no change): only enters", {s for _, s, _ in M.choreography(big)} == {"enter"})

# ================================================================ brain → card
print("brain → card")
reset()
r = handlers.todo("add buy milk to my todos")
ev = cards.take()
tid = one("SELECT id FROM tasks WHERE title ILIKE '%milk%'")["id"]
check("add → note(added, task id)", ev == {"op": "added", "kind": "task", "ids": [tid]}, str(ev))
c = cards.for_turn("add buy milk to my todos", "todo", r, {"type": "task", "id": tid}, event=ev)
check("add → the whole list with the new row focused", c and c["kind"] == "todos" and c["focus"]["op"] == "added"
      and any(i["id"] == tid for i in c["items"]), str(c))

r = handlers.todo("Okay, it has been done")
ev = cards.take()
check("'Okay, it has been done' → the task he just added is done",
      one("SELECT status FROM tasks WHERE id=%s", (tid,))["status"] == "done" and "milk" in r.lower(), r)
c = cards.for_turn("Okay, it has been done", "todo", r, None, event=ev)
check("done → card still shows that row (to strike it), focus=done",
      c and c["focus"] == {"op": "done", "ids": [tid]} and c["items"][0]["id"] == tid, str(c))
lay = M.layout(c)
check("… and the card plays strike + collapse on it", {s for _, s, i in M.choreography(lay) if i == 0} >= {"strike", "collapse"})

reset()
handlers.todo("add gym to my todos")
handlers.todo("add DSA practice to my todos")
cards.remember_task(None)
r = handlers.todo("it's done")
ev = cards.take()
check("two open, none recent: asks which one (names both), changes nothing",
      r.startswith("Which one") and "gym" in r.lower() and "dsa" in r.lower()
      and one("SELECT count(*) n FROM tasks WHERE status='open'")["n"] == 2, r)
c = cards.for_turn("it's done", "todo", r, None, event=ev)
check("… and shows the list he's choosing from", c and c["kind"] == "todos" and len(c["items"]) == 2, str(c))
r = handlers.todo("gym is done")
check("naming it still works ('gym is done')", "gym" in r.lower()
      and one("SELECT status FROM tasks WHERE title ILIKE 'gym'")["status"] == "done", r)
cards.take()
cards.remember_task(None)
r = handlers.todo("ho gaya")
check("one open left: 'ho gaya' finishes that one", "dsa" in r.lower()
      and one("SELECT count(*) n FROM tasks WHERE status='open'")["n"] == 0, r)
cards.take()
reset()
handlers.todo("add gym to my todos")
cards.take()
cards.remember_task(None)
for venting in ("I'm done", "I am so done", "I’m done"):
    check(f"'{venting}' never ticks a to-do (falls through to chat)", handlers.todo(venting) is None
          and one("SELECT count(*) n FROM tasks WHERE status='open'")["n"] == 1)
check("bare 'done' with nothing in play → not a to-do", handlers.todo("Okay done") is None)
cards.remember_task(one("SELECT id FROM tasks WHERE title ILIKE 'gym'")["id"])
check("bare 'done' right after a to-do was added → that one", "gym" in (handlers.todo("Done.") or "").lower())
cards.take()
check("nothing open: 'it's done' says the list is clear", handlers.todo("it's done") == "Your list is already clear.")
check("curly apostrophe too (‘it’s done’)", handlers.todo("it’s done") == "Your list is already clear.")

reset()
for t in ("gym", "laundry", "dsa practice", "call home", "buy notebook", "read paper", "reply to mail"):
    handlers.todo(f"add {t} to my todos")
last_id = one("SELECT max(id) m FROM tasks")["m"]
cards.take()
c = cards.todos(focus={"op": "added", "ids": [last_id]})
check("7 open: the new 7th row is still on the card (inside the 6 shown)",
      last_id in [i["id"] for i in c["items"][:cards.SHOWN]], str([i["id"] for i in c["items"]]))

reset()
handlers.todo("add laundry to my todos")
handlers.todo("add gym to my todos")
cards.take()
handlers.todo("clear my todos")
ev = cards.take()
check("clear → every row noted as removed", ev and ev["op"] == "removed" and len(ev["ids"]) == 2, str(ev))

# ---- reminders
from stiti.life import alarms                                          # noqa: E402
reset()
r = alarms.handle("remind me at 11 pm to call mom")
ev = cards.take()
check("reminder set → note(set, intent)", ev and ev["op"] == "set" and ev["kind"] == "intent", f"{r!r} {ev}")
c = cards.for_turn("remind me at 11 pm to call mom", "time", r, None, event=ev)
check("… reminders card with the new one focused", c and c["kind"] == "reminders" and c["focus"]["op"] == "set", str(c))
r = alarms.handle("cancel my 11 pm reminder")
ev = cards.take()
c = cards.for_turn("cancel my 11 pm reminder", "time", r, None, event=ev)
check("cancel → reminders card still shows it (to cross out), focus=cancelled, title says nothing left",
      ev and ev["op"] == "cancelled" and c and c["items"] and c["focus"]["op"] == "cancelled"
      and c["title"] == "Nothing coming up", f"{r!r} {c}")

# ---- through the engine (what the voice loop puts on screen)
from stiti.engine import Engine                                        # noqa: E402
reset()
eng = Engine("text")
eng.turn("add call the bank to my todos")
c1 = eng.last_card
eng.turn("Okay, it has been done")
c2 = eng.last_card
check("engine: add → last_card focus added", c1 and c1.get("focus", {}).get("op") == "added", str(c1))
check("engine: 'Okay, it has been done' → last_card focus done on that task",
      c2 and c2.get("focus", {}).get("op") == "done" and "bank" in c2["items"][0]["text"].lower(), str(c2))
eng.turn("what's on my to-do list today?")
check("engine: a plain list question → no leftover focus", eng.last_card and "focus" not in eng.last_card, str(eng.last_card))

reset()
print(f"card motion: {passed}/{total} checks passed")
sys.exit(0 if passed == total else 1)
