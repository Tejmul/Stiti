"""Conversation-quality eval: greetings, the intro offer, and standing instructions ("talk in English").

STITI_DB=postgresql:///stiti_test STITI_HOME=<tmp> uv run python tests/conversation_eval.py
"""
from __future__ import annotations

import os
from datetime import datetime

os.environ.setdefault("STITI_LIVE_WARM", "0")

ok = fail = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global ok, fail
    ok += bool(cond)
    fail += not cond
    print(f"{'✅' if cond else '❌'} {name}" + (f" — {detail}" if detail and not cond else ""))


from stiti import profile  # noqa: E402
from stiti.brain import instructions  # noqa: E402
from stiti.config import CFG  # noqa: E402
from stiti.db import q  # noqa: E402
from stiti.engine import Engine, hello  # noqa: E402

# ---- instructions are parsed as instructions, statements are not
cases = {
    "Bro what language are you talking bro? Talk in English.": "language",
    "can you talk in English": "language", "Hindi mein bolo": "language", "keep it short": "brevity",
    "don't ask me so many questions": "questions", "stop asking about my interview": "topic:interview",
    "call me Tej": "call_me", "don't call me bro": "dont_call:bro",
    "I speak English at work": None, "remind me at 4 to start my resume": None, "bye": None,
    "turn off the lights": None, "my name is Tejmul and I study CS": None, "what is happening in tech": None,
}
got = {t: getattr(instructions.parse(t), "key", None) for t in cases}
check("instructions vs statements", got == cases, str({k: v for k, v in got.items() if v != cases[k]}))

# ---- greeting: a person's hello, never the same twice in a row; no intro offer once she knows him
hellos = [hello("Tejmul", datetime(2026, 11, 11, 15, 0, tzinfo=CFG.tz)) for _ in range(6)]
check("hello uses his name and doesn't repeat back-to-back",
      all("Tejmul" in h for h in hellos) and all(a != b for a, b in zip(hellos, hellos[1:])), str(hellos))
late = hello("Tejmul", datetime(2026, 11, 11, 1, 0, tzinfo=CFG.tz)).lower()
check("late-night hello fits the hour", "up" in late or "late" in late, late)

q("DELETE FROM owner_profile")
profile._all.cache_clear()
eng = Engine("text")
first = eng.greet()
check("knows nothing → offers the intro once, with a way to turn it off", "intro" in first and "turn this off" in first, first)
second = eng.greet()
check("…and not again on the next wake (once a week at most)", "intro" not in second, second)
q("DELETE FROM owner_profile WHERE key='intro_offered_at'")
profile._all.cache_clear()
eng.greet()
r = eng.turn("Hey Stiti, turn this off")
check("“turn this off” right after the offer disables it", "won't ask" in r.lower() and profile.get("intro_offer") == "off", r)
q("DELETE FROM owner_profile WHERE key='intro_offered_at'")
profile._all.cache_clear()
check("once off, never offered again", "intro" not in eng.greet())
profile.set("name", "Tejmul", "owner_edit")
check("once she knows his name → plain hello, no intro", "Tejmul" in eng.greet())

# ---- an instruction becomes a permanent rule immediately (and replaces the older one on the same topic)
r = eng.turn("Talk in English")
rules = [x["directive"] for x in q("SELECT directive FROM user_directives WHERE status='active' AND category='talk_style'")]
check("“talk in English” → active talk-style rule at once", any("English" in x for x in rules) and "english" in r.lower(),
      f"{r} | {rules}")
eng.turn("Hindi mein bolo")
rules = [x["directive"] for x in q("SELECT directive FROM user_directives WHERE status='active' AND category='talk_style'")]
check("a newer language instruction replaces the old one", sum("Reply in" in x for x in rules) == 1 and
      any("Hinglish" in x for x in rules), str(rules))
check("rules show in USER.md for him to edit", "Hinglish" in (CFG.home / "USER.md").read_text())

print(f"conversation: {ok}/{ok + fail} checks passed")
raise SystemExit(1 if fail else 0)
