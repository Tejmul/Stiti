"""She never says she did something she didn't (audit 2026-11-11: "Also add call the placement cell" → the LLM said
"Added call the placement cell." and nothing was added), and lists sound like a person ("Just one: …").

STITI_DB=postgresql:///stiti_test STITI_HOME=<tmp> uv run python tests/honest_actions_eval.py
"""
from __future__ import annotations

import os
import sys

db = os.environ.get("STITI_DB", "")
if not db.rstrip("/").split("/")[-1].startswith("stiti_test"):
    sys.exit(f"refusing to run against {db!r}: use a stiti_test* database")
os.environ.setdefault("STITI_LIVE_WARM", "0")
os.environ.setdefault("STITI_EVENTKIT", "off")

passed = total = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global passed, total
    total += 1
    passed += bool(cond)
    print(f"  {'✓' if cond else '✗'} {name}" + (f" — {detail}" if detail and not cond else ""))


from stiti.brain import psych, strategy                                 # noqa: E402
from stiti import say                                                    # noqa: E402
from stiti.db import one, q                                              # noqa: E402
from stiti.fastpath import handlers                                      # noqa: E402

print("claims")
for t in ("Added call the placement cell.", "Done — added it.", "I've set a reminder for 4.", "Reminder set for 4 PM."):
    check(f"claim: {t!r}", bool(psych.CLAIM_RX.match(t)))
for t in ("Noted.", "Got it, take it easy.", "Done! Nice work.", "Added bonus: it's short.", "Sounds good."):
    check(f"not a claim: {t!r}", not psych.CLAIM_RX.match(t))
sl = psych.StreamLint(policy=strategy.make("ACKNOWLEDGE", "english"))
check("streamed claim is never spoken", sl.feed("Added call the placement cell.") is None and sl.said == 0)

print("'Also add …' really adds")
q("DELETE FROM tasks")
said = []
for t, title in (("Also add call the placement cell", "call the placement cell"), ("And add buy milk to my list", "buy milk"),
                 ("Okay, add gym", "gym")):
    r = handlers.todo(t)
    said.append(r)
    # D50: the wording varies; what must hold is that the row is there and she names the item she added
    check(f"{t!r} → the row exists and she names it", r is not None and f"“{title}”" in r
          and one("SELECT 1 AS x FROM tasks WHERE title=%s AND status='open'", (title,)) is not None
          and say.confirms(r.split(" (task #")[0]), str(r))
check("three adds in a row → three different wordings", len({s.split("“")[0] for s in said}) == 3, str(said))
titles = [x["title"] for x in q("SELECT title FROM tasks ORDER BY id")]
check("titles are clean (no 'Also', 'to my list')", titles == ["call the placement cell", "buy milk", "gym"], str(titles))
check("'I added sugar to tea' is not a to-do", handlers.todo("I added sugar to tea") is None
      or "added" not in (handlers.todo("I added sugar to tea") or ""))

print("lists sound like a person")
q("DELETE FROM tasks")
handlers.todo("add revise DBMS notes")
r = handlers.todo_list()
check("one → one of her 'just one' lines, with the item", r in say.variants("list_one", said="revise DBMS notes"), r)
handlers.todo("add gym")
handlers.todo("add call home")
r = handlers.todo_list()
check("three → the count and 'a, b and c'", r in say.variants("list_some", n=3, said="revise DBMS notes, gym and call home"), r)
handlers.todo("add buy milk")
r = handlers.todo_list()
check("more than three → the count, the top three + 'say more'", r in say.variants(
    "list_many", n=4, k=3, said="revise DBMS notes, gym and call home") and "buy milk" not in r and "“more”" in r, r)
check("never '1 open. Top 1'", "open. Top" not in handlers.todo_list())

print("through the engine")
from stiti import router                                                 # noqa: E402
from stiti.engine import Engine                                          # noqa: E402

q("DELETE FROM tasks")
e = Engine("text")
r = e.turn("Also add call the placement cell")
check("engine: 'Also add …' goes to the to-do fast path", e.last_route == "fast_path"
      and q("SELECT 1 FROM tasks WHERE title='call the placement cell'"), r)
orig = router.complete
router.complete = lambda msgs, **kw: {"text": "Added it to your list.", "provider": "fake", "model": "fake", "ms": 1}
r = e.turn("Put that somewhere I'll remember")
router.complete = orig
check("engine: LLM claims 'Added …' but nothing ran → honest line", r == psych.HONEST_NOT_DONE, r)

print("never claims it opened the whiteboard (2026-11-11 23:45)")
for t in ("Opened the whiteboard app. Lexical analysis scans source code.", "Got it, I'll open the whiteboard for you.",
          "I've opened the whiteboard app for you.", "I can't draw on a whiteboard, but I can walk you through it."):
    check(f"open claim: {t[:50]!r}", bool(psych.OPEN_CLAIM_RX.search(t)))
for t in ("Lexical analysis scans source code into tokens.", "I started college in 2022, you said.",
          "Sure, I'll start with the basics: tokens.", "The board meeting went well.", "Let me open up about that."):
    check(f"not an open claim: {t!r}", not psych.OPEN_CLAIM_RX.search(t))
sl = psych.StreamLint(policy=strategy.make("ACKNOWLEDGE", "english"))
check("streamed 'Opened the whiteboard app.' is never spoken", sl.feed("Opened the whiteboard app.") is None)
router.complete = lambda msgs, **kw: {"text": "I've opened the whiteboard app for you.", "provider": "fake",
                                      "model": "fake", "ms": 1}
r = e.turn("Is the whiteboard thing working these days?")
router.complete = orig
check("engine: LLM claims it opened the board → honest line", r.startswith("I haven't opened the whiteboard"), r)

q("DELETE FROM tasks")
print(f"honest actions: {passed}/{total} checks passed")
sys.exit(0 if passed == total else 1)
