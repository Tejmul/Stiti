"""She remembers everything he told her in a conversation (D48).

2026-11-18, his real conversation (retold here with a made-up person): he explained his plan in seven parts, then asked
"what did I tell you till now?" — she gave back only the last part. One long part had been thrown away as "unclear",
and a mention of her name in the middle of a sentence woke her while he was talking to someone else.

STITI_DB=postgresql:///stiti_test STITI_HOME=<tmp> python tests/recap_eval.py
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


from stiti import router                                                 # noqa: E402
from stiti.brain import memory, strategy                                 # noqa: E402
from stiti.engine import Engine                                          # noqa: E402
from stiti.voice import stt, wake                                        # noqa: E402

print("'what did I tell you till now?' is its own request")
for t in ("Ya, can you tell me what did I tell you? Till naf.", "What did I told you till now? Like I told you my future "
          "goals till now.", "what have I told you so far", "did you get all that", "repeat what I just said",
          "maine kya bola", "what did I tell you about my plan"):
    check(f"recap: {t!r}", strategy.wants_recap(t))
for t in ("what did I say about Priya last week", "what did you say", "what did I tell you yesterday", "tell me a joke",
          "what is my plan for today"):
    check(f"not a recap: {t!r}", not strategy.wants_recap(t))

print("the engine: seven parts told, all seven come back")
PARTS = ["Okay so I am in my final year right now and this is 2026.",
         "By June 2027 I will graduate.",
         "After that I will get a great paying job and settle down.",
         "Then I will build my network for a year or two.",
         "While working I will start my own startup on the side.",
         "The startup should pay really well too.",
         "Once the startup is successful I will leave the job and work as a founder."]
seen, script = [], []


def fake(msgs, **kw):
    seen.append(msgs[0]["content"])
    return {"text": script.pop(0) if script else "Got it.", "provider": "fake", "model": "fake", "ms": 1}


orig = router.complete
router.complete = fake
try:
    e = Engine("text")
    e.turn("Ya I will tell you about my future plans right now")
    frag = e.turn(PARTS[0][:30])                       # a cut-off half sentence, then the whole one
    e.forget_fragment(e.cur_user_ep)
    for part in PARTS:
        e.turn(part)
    e.turn("set an alarm for 6 am")                    # a command in the middle is not part of the story
    told = memory.told_this_conversation(e.session)
    check("all seven parts are kept, in order", [p for p in PARTS if p in told] == PARTS and
          [told.index(p) for p in PARTS] == sorted(told.index(p) for p in PARTS), str(told))
    check("the cut-off half sentence is folded into the full one", PARTS[0][:30] not in told)
    check("commands and questions are not 'things he told her'", not any("alarm" in x for x in told))
    n = len(seen)
    script.append("You're in your final year in 2026. You'll graduate by June 2027. Then a great paying job, and you'll "
                  "settle. You'll build your network. While working you'll start a startup that should pay well. Once "
                  "it works, you'll leave the job and be a founder.")
    r = e.turn("What did I told you till now? Like I told you my future goals till now.")
    brief = seen[-1] if len(seen) > n else ""
    block = brief.split("[WHAT HE TOLD YOU IN THIS CONVERSATION")[1].split("\n[")[0] if "[WHAT HE TOLD YOU" in brief else ""
    check("the LLM is given every part, numbered, in order", all(p in block for p in PARTS)
          and block.index(PARTS[0]) < block.index(PARTS[3]) < block.index(PARTS[6]), block[:400])
    check("it is told to retell all of it and add nothing", "Retell EVERY point" in brief)
    check("the reply keeps the first part AND the last (not cut at the normal 45 words)",
          "final year" in r and "founder" in r and "2027" in r, r)
    check("his own words are never filtered as 'already said'", "network" in r, r)
    e2 = Engine("text")
    n = len(seen)
    r2 = e2.turn("what did I tell you till now?")
    check("nothing told yet → an honest line, no LLM call", r2 == strategy.RECAP_NONE["english"] and len(seen) == n, r2)
finally:
    router.complete = orig

print("long, confident speech is never 'unclear' (it was thrown away with a 'Sorry, I didn't catch that')")
long_text = ("After that I'll get any fine, great paying job and once I get a great paying job I'll settle and build my "
             "network and after that and after building my network.")
check("his real case: 30 words, logprob −0.42, no_speech 0.57 → kept",
      not stt.STTResult(long_text, 300.0, 0.57, -0.42).unclear)
check("a short mumble with the same scores is still unclear", stt.STTResult("Amen.", 300.0, 0.57, -0.42).unclear)
check("long but badly guessed (logprob −1.2) is still unclear", stt.STTResult(long_text, 300.0, 0.2, -1.2).unclear)
check("clear short speech is fine", not stt.STTResult("Set an alarm for six.", 300.0, 0.05, -0.2).unclear)

print("her name in the middle of a sentence is not a call")
for t in ("bro, I even explained every bit of the thing to Stiti in detail", "I told Stiti about it",
          "and then hey Stiti came up in the talk", "what I told Stiti was right"):
    check(f"does not wake: {t!r}", not wake.detect(t)[0])
for t, rest in (("Hey Stiti", ""), ("Stiti, what are my todos", "what are my todos"), ("okay hey Stiti tell me", "tell me"),
                ("so Stiti listen", "listen"), ("hi stiti how are you", "how are you")):
    w = wake.detect(t)
    check(f"wakes: {t!r}", w[0] and w[1] == rest, str(w))

print("the owner's own wake phrase lives in the local profile, not in the code")
check("a personal phrase does not wake her by default", not wake.detect("Wake up sunshine")[0])
check("phrases are written the way she's called", wake.spoken("hey stiti") == "Hey Stiti" and
      wake.spoken("stiti uth jao") == "Stiti uth jao", wake.spoken("hey stiti"))
print("  " + wake.add_phrase("Wake up sunshine"))
check("… once added, it does", wake.detect("Wake up sunshine, what's next") == (True, "what's next"), str(wake.detect("Wake up sunshine, what's next")))
check("… Whisper is primed with it", "Wake up sunshine." in stt.wake_line(), stt.wake_line())
check("… and the status hint names it", "Wake up sunshine" in wake.hint(), wake.hint())
check("adding it twice changes nothing", "already" in wake.add_phrase("wake up sunshine") and len(wake.extra_phrases()) == 1)
print("  " + wake.remove_phrase("wake up sunshine"))
check("removed → back to the defaults", wake.phrases() == wake.DEFAULT_PHRASES and not wake.detect("Wake up sunshine")[0])

print(f"\n{passed}/{total} passed")
sys.exit(0 if passed == total else 1)
