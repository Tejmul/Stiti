"""She talks like a person, never like a machine (2026-11-11 owner complaint: "why is it reporting all the errors,
functional errors and technical terms while talking?").

Real replies from that day: "The voice model is likely glitching or the audio stream is corrupted. I cannot control the
synthesis engine directly…", "Functioning within normal parameters. No errors to report.", "That is a word I do not
recognize.", "My thinking brain (cloud LLM) is offline right now."
Offline checks always run; the live-LLM checks run only when a free key is configured.

STITI_DB=postgresql:///stiti_test STITI_HOME=<tmp> uv run python tests/human_talk_eval.py
"""
from __future__ import annotations

import os
import sys

os.environ.setdefault("STITI_LIVE_WARM", "0")

passed = total = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global passed, total
    total += 1
    passed += bool(cond)
    print(f"  {'✓' if cond else '✗'} {name}" + (f" — {detail}" if detail and not cond else ""))


from stiti.brain import psych                                          # noqa: E402
from stiti.brain.compiler import DEFAULT_SOUL, _short                  # noqa: E402
from stiti.brain.strategy import choose                                # noqa: E402

print("machine-talk is cut")
ROBOT = ["The voice model is likely glitching or the audio stream is corrupted.",
         "I cannot control the synthesis engine directly, but I can reset the session if the issue persists.",
         "Functioning within normal parameters.", "No errors to report.", "That is a word I do not recognize.",
         "My thinking brain (cloud LLM) is offline right now.", "I'm just a program.", "All systems nominal.",
         "I was rate limited for a moment.", "My training data doesn't cover that.", "I don't have feelings.",
         "My servers are a bit slow today."]
for t in ROBOT:
    check(f"cut: {t[:60]}", psych.machine_talk(t))

print("his tech talk is NOT cut (he's a CS student)")
FINE = ["Postgres is a database with a strong planner.", "A language model predicts the next token.",
        "Status code 404 means the route doesn't exist.", "Restart the system and try again.",
        "Your API key goes in .env.", "The invalid request error comes from a missing header.",
        "Your model is overfitting — add dropout.", "Rate limits on Groq reset every minute.",
        "My bad, I'll keep it short.", "Good, quiet day here.", "The audio in your demo video is clipping.",
        "Your training data has duplicates."]
for t in FINE:
    check(f"kept: {t[:60]}", not psych.machine_talk(t))

print("what she says instead")
check("'How about you?' → a friend's answer",
      psych.lint("Functioning within normal parameters. No errors to report.", user_text="Yeah, great. How about you?")
      == "Good, thanks — quiet day on my side.")
check("'voice itna kharab…' → sorry, like a person",
      "voice is acting up" in psych.lint("The voice model is likely glitching or the audio stream is corrupted.",
                                         user_text="Voice itna kharab kaisa hogaya tumhara?"))
check("misheard → 'didn't catch that'",
      "didn't catch that" in psych.lint("That is a word I do not recognize.", user_text="Waka dan."))
check("mixed reply keeps the human part",
      psych.lint("Sorry about that. My voice model is glitching.", user_text="x") == "Sorry about that.")
s = choose("Yeah, great. How about you?", domain="chat", mood="happy", mood_conf=0.8)
check("enforce (LLM path) uses the same fallback",
      psych.enforce("Functioning within normal parameters. No errors to report.", s,
                    user_text="Yeah, great. How about you?") == "Good, thanks — quiet day on my side.")

check("a stray 'Done.' after a plain answer is dropped",
      psych.enforce("A rate limit caps requests per minute. Done.", choose("what's a rate limit", domain="chat"),
                    user_text="what's a rate limit") == "A rate limit caps requests per minute.")
for name, text in (("docs SOUL", open(os.path.join(os.path.dirname(__file__), "..", "docs", "persona", "SOUL.jarvis.md")).read()),
                   ("DEFAULT_SOUL", DEFAULT_SOUL)):
    check(f"{name}: no bare 'Done.' example for the model to copy", '"Done."' not in text)
sl = psych.StreamLint(policy=s)
out = [sl.feed(p) for p in ["Functioning within normal parameters.", "No errors to report."]]
check("streaming: robot pieces are never spoken, and said == 0 so the loop speaks the clean reply",
      out == [None, None] and sl.said == 0)
sl2 = psych.StreamLint(policy=s)
sl2.feed("Good, thanks.")
check("streaming: a normal piece counts as said", sl2.said == 1)

loop_src = open(os.path.join(os.path.dirname(__file__), "..", "src", "stiti", "voice", "loop.py")).read()
check("voice loop falls back to the clean reply when every streamed piece was cut", "not lint.said" in loop_src)

print("no technical words in her own fixed lines")
src = os.path.join(os.path.dirname(__file__), "..", "src", "stiti")
eng = open(os.path.join(src, "engine.py")).read()
check("offline line has no 'LLM' / 'cloud' / 'brain'", "cloud LLM" not in eng and "thinking brain" not in eng)
for f in ("connectors/telegram.py", "web/server.py"):
    check(f"{f}: no exception class names in what she says", "type(e).__name__}). Try again" not in open(os.path.join(src, f)).read())
check("mail: no '.env' in what she says", ".env." not in open(os.path.join(src, "connectors/mail.py")).read().split("def ")[-1])

print("SOUL reaches the model whole")
soul_doc = open(os.path.join(os.path.dirname(__file__), "..", "docs", "persona", "SOUL.jarvis.md")).read()
for name, text in (("docs/persona/SOUL.jarvis.md", soul_doc), ("DEFAULT_SOUL", DEFAULT_SOUL.format(name="Alex"))):
    body = _short(text, 10 ** 6)
    check(f"{name}: fits the 1400-char briefing cap ({len(body)})", len(body) <= 1400)
    check(f"{name}: says she never talks about herself as software", "Never talks about herself as software" in body)
    check(f"{name}: no 'butler' (it made her stiff)", "butler" not in body.lower())

# ---- live LLM (only with a free key): his exact lines from 2026-11-11
from stiti import router                                               # noqa: E402

if router.available() if hasattr(router, "available") else bool(os.getenv("GROQ_API_KEY")):
    db = os.environ.get("STITI_DB", "")
    if db.rstrip("/").split("/")[-1].startswith("stiti_test"):
        print("live LLM")
        from stiti.engine import Engine                                # noqa: E402
        e = Engine("text")
        for line in ("Yeah, great. How about you?", "Voice itna kharab kaisa hogaya tumhara?", "Are you working properly?"):
            r = e.turn(line)
            check(f"live: {line!r} → no machine-talk", r and not psych.machine_talk(r)
                  and not any(w in r.lower() for w in ("parameter", "synthesis", "audio stream", "glitching", "llm")), r)

print(f"human talk: {passed}/{total} checks passed")
sys.exit(0 if passed == total else 1)
