"""No missing words (owner, 2026-11-11: "some words are getting missed in between, so people can't understand").

The streaming filter judged each spoken PIECE alone: "If you're tired, try to rest for ten minutes, then start the DSA
sheet" came out as "If you're tired," (the rest looked like advice), and the word cap cut "the placement test is tomorrow
at" before "ten". Now a sentence is judged when it starts and then spoken whole; the cap stops only at sentence ends.

uv run python tests/whole_sentence_eval.py   (offline, no DB)
"""
from __future__ import annotations

import re
import sys

from stiti.brain import psych, strategy
from stiti.voice.tts import ClauseChunker

passed = total = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global passed, total
    total += 1
    passed += bool(cond)
    print(f"  {'✓' if cond else '✗'} {name}" + (f" — {detail}" if detail and not cond else ""))


def speak(reply: str, s) -> str:
    """What the voice would say: LLM deltas → ClauseChunker → StreamLint, as in voice/loop.py."""
    ch, sl, out = ClauseChunker(), psych.StreamLint(policy=s), []
    for i in range(0, len(reply), 7):
        for p in ch.feed(reply[i:i + 7]):
            if (x := sl.feed(p)) is not None:
                out.append(x)
    for p in ch.flush():
        if (x := sl.feed(p)) is not None:
            out.append(x)
    return " ".join(out)


def norm(t: str) -> str:
    return re.sub(r"[^\w\s]", "", t).lower().split().__str__()


ACK, DO, SOLVE = (strategy.make(n, "english") for n in ("ACKNOWLEDGE", "DO", "SOLVE"))

print("his real cases")
r = "If you're tired, try to rest for ten minutes, then start the DSA sheet."
check("no hole: 'If you're tired,' is followed by the rest of the sentence", speak(r, ACK) == r, speak(r, ACK))
r = "Okay, the placement test is tomorrow at ten, make sure you sleep by midnight, and keep the notes ready."
check("never cut mid-phrase ('…tomorrow at' + 'ten')", "tomorrow at ten" in speak(r, DO), speak(r, DO))
r = "Haan, kal subah chhe baje ka alarm laga diya hai, aur placement wali call chaar baje hai, yaad rakhna."
check("Hinglish confirmation spoken whole under the short DO cap", speak(r, DO) == r, speak(r, DO))
check("no capital letters in the middle of a sentence ('Laga', 'Ten')", not re.search(r", [A-Z][a-z]", speak(r, DO)))

print("the word cap")
long2 = "Your call is at four today. The second thing is that the notes are ready on your desk for later."
said = speak(long2, DO)
check("cap reached → stops at a sentence end, not inside the next one", said == "Your call is at four today.", said)
run = " ".join(["word"] * 40) + "."
said = speak(run, DO)
check("a runaway sentence still ends (≤ 1.6× cap) with a full stop", len(said.split()) <= int(14 * 1.6) and said.endswith("."), said)

print("dropping")
r = "Sure, here's the plan. Try to finish the DBMS notes first. Then revise graphs for an hour."
check("a sentence dropped after she spoke ends the reply (no 'Then…' about something unsaid)",
      speak(r, ACK) == "Sure, here's the plan.", speak(r, ACK))
check("…but when he asked for help, the plan is spoken", "Try to finish" in speak(r, SOLVE), speak(r, SOLVE))
r = "Sorry about that, my voice model is glitching today, but I'm here."
check("machine-talk in the middle ends the sentence there", speak(r, ACK).startswith("Sorry about that") and
      "model" not in speak(r, ACK), speak(r, ACK))
r = "From now on I'll remind you an hour before. Your call is at four."
check("a dropped FIRST sentence doesn't end the reply", speak(r, ACK) == "Your call is at four.", speak(r, ACK))

print("what's saved = what was said")
cases = ["If you're tired, try to rest for ten minutes, then start the DSA sheet.",
         "Okay, the placement test is tomorrow at ten, make sure you sleep by midnight, and keep the notes ready.",
         "Your call is at four. From now on I'll remind you an hour before.",
         "Sure, here's the plan. Try to finish the DBMS notes first. Then revise graphs for an hour.",
         "Lexical analysis splits code into tokens, like keywords, identifiers and numbers. Want an example?"]
for s in (ACK, DO, SOLVE):
    same = [norm(speak(c, s)) == norm(psych.enforce(c, s)) for c in cases]
    check(f"{s.name}: spoken == saved for all {len(cases)} replies", all(same),
          str([c[:30] for c, ok in zip(cases, same) if not ok]))

print(f"whole sentences: {passed}/{total} checks passed")
sys.exit(0 if passed == total else 1)
