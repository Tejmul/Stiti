"""She never says the same thing twice in one conversation (D36, docs/research/no_repeat.md).

His real morning (2026-11-14), paraphrased with a made-up person: "what do you know about me?" → school, projects,
sport. "Okay, what else?" → the same school, projects, sport + one new line. "And what else?" → again.

STITI_DB=postgresql:///stiti_test STITI_HOME=<tmp> uv run python tests/no_repeat_eval.py
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


from stiti import profile, router                                        # noqa: E402
from stiti.brain import norepeat as N, psych, strategy                   # noqa: E402
from stiti.db import q                                                   # noqa: E402

print("'what else?' is understood (English, Hinglish, Telugu)")
for t in ("Okay, what else do you know about me?", "And what else?", "and?", "Okay. And?",
          "Okay, this is okay, is there some other thing that you know?", "anything else you know?", "tell me more",
          "aur batao", "aur kya pata hai mere baare mein", "iske alawa?", "kuch aur?", "inka cheppu", "inka emi telusu",
          "ఇంకా ఏమి తెలుసు"):
    check(f"MORE: {t!r}", N.wants_more(t))
for t in ("What do you know about me?", "Do I have anything else today?", "is there anything else pending",
          "I want more sleep", "say that again", "set an alarm for 6", "inka kitna time lagega", "more or less fine"):
    check(f"not MORE: {t!r}", not N.wants_more(t))
for t in ("say that again", "Sorry, what did you say?", "kya bola?", "malli cheppu"):
    check(f"REPEAT: {t!r}", N.wants_repeat(t))

print("ledger")
L = N.Ledger().with_ignore({"ravi"})
L = L.add("You are a final-year CS student at Lakeview College. You built Tilecraft and Parkly, and you play "
          "national-level hockey.", ep=1)
check("profile line she said → covered", L.covered("- Ravi is a final-year CS student at Lakeview College."))
check("project line she said → covered", L.covered("- Ravi built Tilecraft (2026), a tile-design app, and Parkly."))
check("new line → not covered", not L.covered("- Ravi leads the technology team at the NGO GreenRoots."))
check("fact tag isn't content", L.covered("[F12 · true since 2026-09 · fact] Ravi studies at Lakeview College"))
check("same sentence again → repeat", L.is_repeat("You are a final-year CS student at Lakeview College."))
check("reworded, same words → repeat", L.is_repeat("You're a CS student in your final year at Lakeview College."))
check("same template, new fact → not a repeat", not L.is_repeat("You also lead tech at GreenRoots."))
check("short sentence never counts ('Good night.')", not L.add("Good night.").is_repeat("Good night."))
check("dedup keeps only the new sentence",
      N.dedup("You are a final-year CS student at Lakeview College. You also lead tech at GreenRoots.", L)
      == "You also lead tech at GreenRoots.")
L2 = L.replace(1, "You are a final-year CS student")
check("barge-in: only what he heard counts", not L2.is_repeat("You built Tilecraft and Parkly."))
check("ledger is immutable (speculation snapshot safe)", L2 is not L and L.is_repeat("You built Tilecraft and Parkly."))
old = L.add("Your sister lives in Pune and works at a design studio.", now=0)
check("older than 20 min → forgotten", not old.is_repeat("Your sister lives in Pune and works at a design studio."))

for t in ("Okay, and what else do you know about me?", "can you tell me about my projects", "kya pata hai?"):
    check(f"his question isn't a memory: {t!r}", N.is_ask(t))
check("a statement is a memory", not N.is_ask("I left the internship in September."))

print("cut-off half sentences don't show twice")
rec = [{"speaker": "user", "text": "Actually, I left the internship change it down."},
       {"speaker": "user", "text": "Actually, I left the internship change it down. It ended in September."},
       {"speaker": "stiti", "text": "Noted."}]
check("fragment collapsed", [r["text"] for r in N.collapse_fragments(rec)] == [rec[1]["text"], "Noted."])

print("spoken stream + stored reply")
s = strategy.make("ANSWER", "english")
s.said = L
sl = psych.StreamLint(policy=s)
out = [sl.feed(p) for p in ("You are a final-year CS student at Lakeview College.", "You also lead tech at GreenRoots.")]
check("StreamLint skips the repeat, speaks the new sentence", out[0] is None and out[1] is not None, str(out))
s.more = True
check("enforce: all repeats + 'what else' → honest line",
      psych.enforce("You are a final-year CS student at Lakeview College.", s) == N.HONEST["english"])
check("honest line rotates", N.honest("english", N.Ledger().add(N.HONEST["english"])) == N.HONEST_AGAIN["english"][0])
s.more = False
check("enforce: same question again → same answer is kept",
      "Lakeview" in psych.enforce("You are a final-year CS student at Lakeview College.", s))
s.said = None
check("REPEAT turn: no dedup", "Lakeview" in psych.enforce("You are a final-year CS student at Lakeview College.", s))

print("engine: the real conversation")
from stiti.engine import Engine                                          # noqa: E402

profile.set("name", "Ravi")
PROFILE = "\n".join([
    "- Ravi is a final-year CS student at Lakeview College.",
    "- Ravi built Tilecraft, a tile-design app, and Parkly, a parking finder.",
    "- Ravi is a national-level hockey player.",
    "- Ravi leads the technology team at the NGO GreenRoots.",
    "- Ravi is a competitive programmer: Codeforces Pupil with a long daily streak."])
q("""INSERT INTO briefing_cache(key, content, tokens) VALUES ('standing_profile', %s, 80)
     ON CONFLICT (key) DO UPDATE SET content = EXCLUDED.content""", (PROFILE,))
seen, script = [], []


def fake(msgs, **kw):
    seen.append(msgs[0]["content"])
    return {"text": script.pop(0), "provider": "fake", "model": "fake", "ms": 1}


orig = router.complete
router.complete = fake
try:
    e = Engine("text")
    script.append("You are a final-year CS student at Lakeview College. You built Tilecraft and Parkly, and you play "
                  "national-level hockey.")
    r1 = e.turn("Okay, can you tell me in detail what do you know about me?")
    check("first answer", "Lakeview" in r1, r1)
    # the weak model re-lists everything + one new thing (exactly what happened)
    script.append("You are a final-year CS student at Lakeview College. You built Tilecraft and Parkly. You also lead "
                  "tech at GreenRoots.")
    r2 = e.turn("Okay, and what else do you know about me?")
    b2 = seen[-1]
    check("MORE briefing: already-said lines left out", "Lakeview College." not in b2.split("[RECENT")[0], b2[:600])
    check("MORE briefing: new lines still there", "GreenRoots" in b2 and "Codeforces" in b2)
    check("MORE briefing: ALREADY SAID block", "[ALREADY SAID — he asked for MORE" in b2)
    nys = b2.split("[NOT SAID YET")[1] if "[NOT SAID YET" in b2 else ""
    check("MORE briefing: brain picks the next unsaid items", "GreenRoots" in nys and "Lakeview" not in nys, nys[:300])
    check("RECENT has her full first answer", "national-level hockey" in b2.split("[RECENT CONVERSATION]")[1][:700])
    check("reply = only the new thing", r2 == "You also lead tech at GreenRoots.", r2)
    script.append("You lead tech at GreenRoots. You're a Codeforces Pupil with a long daily streak.")
    r3 = e.turn("And what else?")
    check("third: only the new thing", r3.startswith("You're a Codeforces Pupil") and "GreenRoots" not in r3, r3)
    n = len(seen)
    r4 = e.turn("Okay, is there some other thing that you know?")
    check("nothing new left → honest line, no LLM call", r4 == N.HONEST["english"] and len(seen) == n, r4)
    r4b = e.turn("And what else?")
    check("asked again → a different honest line, not the same one", r4b in N.HONEST_AGAIN["english"] and r4b != r4, r4b)
    script.append("You are a final-year CS student at Lakeview College.")
    r5 = e.turn("Say that again?")
    check("REPEAT: she repeats when asked", "Lakeview" in r5, r5)
    ep = e.cur_user_ep
    e.forget_fragment(ep)
    check("a joined half sentence is kept out of recall", q("SELECT importance FROM episodes WHERE id=%s", (ep,))[0]["importance"] == 1)
finally:
    router.complete = orig

print(f"\n{passed}/{total} passed")
sys.exit(0 if passed == total else 1)
