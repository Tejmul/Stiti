"""An answered question is never asked again (owner, 2026-11-20: "it asks same questions again and again — I have
answered something and it forgets it and again it asks the same questions again"). Offline: fake LLM, fake weather,
made-up owner and answers.

Covers the question ledger (brain/asked.py, migration 012) and every place she asks him something:
  - the LLM's own questions in chat: kept with his answer, the same question (other words too) never asked again, and
    the briefing tells the LLM what he already answered;
  - the old intro (onboarding.py): skips what the brain already knows, survives a restart, no bare "shuru karo" start;
  - the weather "tell me your city" hint: once a week at most (it lived in process memory; the app restarts often),
    never after he told her, and a home city she learned in chat counts;
  - (ask-me rounds: tests/ask_me_eval.py — skipped questions wait 14 days, "Still the same?" only after 60).

STITI_DB=postgresql:///stiti_test STITI_HOME=<tmp> STITI_EVENTKIT=off python tests/asked_once_eval.py
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta

db = os.environ.get("STITI_DB", "")
if not db.rstrip("/").split("/")[-1].startswith("stiti_test"):
    sys.exit(f"refusing to run against {db!r}: use a stiti_test* database")
os.environ.setdefault("STITI_LIVE_WARM", "0")
os.environ["STITI_EVENTKIT"] = "off"
os.environ.pop("STITI_CITY", None)

passed = total = 0


def check(name: str, cond, detail: str = "") -> None:
    global passed, total
    total += 1
    passed += bool(cond)
    print(f"  {'✓' if cond else '✗'} {name}" + (f" — {detail}" if detail and not cond else ""))


from stiti import profile, router                                        # noqa: E402
from stiti.brain import asked as L, onboarding as O                      # noqa: E402
from stiti.config import CFG                                             # noqa: E402
from stiti.connectors import weather as W                                # noqa: E402
from stiti.db import one, q                                              # noqa: E402

briefs: list[str] = []
llm = {"text": "Hmm."}


def fake_complete(msgs, **kw):
    briefs.append(msgs[0]["content"])
    return {"text": llm["text"], "provider": "fake", "model": "fake", "ms": 1}


def fake_stream(msgs, **kw):
    briefs.append(msgs[0]["content"])
    yield llm["text"]


router.complete, router.stream = fake_complete, fake_stream
from stiti.engine import Engine                                          # noqa: E402

q("DELETE FROM owner_profile WHERE key IN ('city', 'name', 'call_me')")
profile._all.cache_clear()
q("TRUNCATE asked_questions RESTART IDENTITY")
O.STATE.unlink(missing_ok=True)

# ------------------------------------------------------------------------------------------------ the ledger
print("ledger: answered → never; skipped → not for 14 days; it lives in the brain")
check("a new question may be asked", L.ask_ok("test:q1"))
L.asked("test:q1", "What's your favourite colour?", "test")
check("asked, unanswered → may come back later", L.ask_ok("test:q1"))
check("…but not inside its repeat gap", not L.ask_ok("test:q1", repeat_days=7))
L.answered("test:q1", "teal")
check("answered → never again", not L.ask_ok("test:q1") and L.row("test:q1")["answer"] == "teal")
L.skipped("test:q2", question="Any pets?")
check("skipped → not now", not L.ask_ok("test:q2"))
check("…ok again after 14 days", L.ask_ok("test:q2", now=datetime.now(CFG.tz) + timedelta(days=15)))
L.answered("test:q3", "my worry", private=True)
check("a private answer is not kept as text", L.row("test:q3")["answer"] is None and not L.ask_ok("test:q3"))

print("which sentences are questions about him (not offers)")
from stiti.brain import strategy as S                                   # noqa: E402
_choose = S.choose


def asking_choose(*a, **k):        # most chat strategies forbid questions in code (D25); the ledger guards the rest
    s = _choose(*a, **k)
    s.ask = True
    return s


S.choose = asking_choose
qs = L.questions_in("Nice one. What are you studying these days? Want me to find notes? Anything else?")
check("keeps 'What are you studying these days', drops offers", qs == ["What are you studying these days"], str(qs))
check("'Shall we continue?' / 'Sound good?' are not questions about him",
      not L.questions_in("Shall we continue? Sound good? Ready?"))

# ------------------------------------------------------------------------------------------------ LLM questions
print("the LLM's questions: his answer is kept; the same question is never asked again")
q("TRUNCATE asked_questions RESTART IDENTITY")
profile.set("name", "Kiran")
profile.set("pronouns", "he")
e = Engine("text")
llm["text"] = "That sounds like a lot. What are you studying these days?"
r1 = e.turn("I had such a long day at college")
check("her question is in the ledger", one("SELECT count(*) n FROM asked_questions WHERE source='llm'")["n"] == 1, r1)
llm["text"] = "Nice, that's a solid field."
e.turn("Computer science, I'm in my final year")
row = one("SELECT answer, answered_at FROM asked_questions WHERE source='llm'")
check("his next line is its answer", row["answered_at"] is not None and "Computer science" in row["answer"], str(row))
llm["text"] = "Got it. What do you study right now?"
r3 = e.turn("I'm thinking about what to do next")
check("the same question in other words is dropped from her reply", "study" not in r3.lower() and r3.startswith("Got it"), r3)
check("the briefing tells the LLM he already answered it (with his answer)",
      "YOU ALREADY ASKED" in briefs[-1] and "Computer science" in briefs[-1], briefs[-1][-600:])
llm["text"] = "What are you studying these days?"
r4 = e.turn("hmm")
check("a reply that is ONLY that question is kept (never an empty reply)", r4.strip() != "", r4)

print("'I don't know' leaves it open; 'skip' skips it")
q("TRUNCATE asked_questions RESTART IDENTITY")
e = Engine("text")
llm["text"] = "Where do you want to travel next year?"
e.turn("I want a break soon")
llm["text"] = "Fair enough."
e.turn("I don't know")
check("'I don't know' → still unanswered", one("SELECT answered_at FROM asked_questions")["answered_at"] is None)
e.turn("skip")
check("'skip' → skipped, not asked for 14 days", one("SELECT skipped_at FROM asked_questions")["skipped_at"] is not None
      and not L.ask_ok(one("SELECT qkey FROM asked_questions")["qkey"]))
llm["text"] = "Okay."
e.turn("set an alarm for tomorrow at 6 am")
check("a command after her question is not taken as its answer",
      one("SELECT answered_at FROM asked_questions")["answered_at"] is None)

# ------------------------------------------------------------------------------------------------ onboarding
print("the intro: never re-asks what the brain knows, survives a restart")
q("TRUNCATE asked_questions RESTART IDENTITY")
O.STATE.unlink(missing_ok=True)
check("'lesson shuru karo' does NOT start the intro", not O.START_RX.search("lesson shuru karo")
      and not O.START_RX.search("chalo shuru karo") and O.START_RX.search("intro shuru karo"))
ob = O.Onboarding()
first = ob.start()
check("name already known → the intro skips 'what should I call you?'", "call you" not in first and O.QUESTIONS[1][1] in first,
      first)
r, fin = ob.answer("Pune, originally from Nagpur")
check("…next question follows", not fin and O.QUESTIONS[2][1] in r, r)
ob2 = O.Onboarding()                                       # a restart in the middle
s2 = ob2.start()
check("after a restart it picks up at the unanswered one", "Picking up" in s2 and O.QUESTIONS[2][1] in s2, s2)
r, fin = ob2.answer("skip")
O.STATE.unlink(missing_ok=True)                            # even with the state file gone…
ob3 = O.Onboarding()
s3 = ob3.start()
check("…answered and just-skipped questions are not asked again", O.QUESTIONS[1][1] not in s3
      and O.QUESTIONS[2][1] not in s3 and O.QUESTIONS[3][1] in s3, s3)
e = Engine("text")
for k, _ in O.QUESTIONS:
    L.answered(f"onboarding:{k}", "x", question=k, source="onboarding")
r = e.turn("let's do the intro")
check("everything known → no interview, she says so", e.onboarding is None and "already know" in r, r)
r = e.turn("how's it going")
check("…and the next line is normal chat", e.onboarding is None, r)

# ------------------------------------------------------------------------------------------------ weather city
print("weather: 'tell me your city' at most once a week, never after he told her")
q("DELETE FROM owner_profile WHERE key='city'")
profile._all.cache_clear()
q("TRUNCATE asked_questions RESTART IDENTITY")
fake_w = W.Weather(city="Kolkata", temp=24, feels=24, code=0, is_day=True)
W.get = lambda name=None, network=True: fake_w
W.speak = lambda w, focus="now", day=0, now=None: "It's 24 and sunny."
W._hinted[0] = False
a1 = W.answer("what's the weather like?")
check("first time: the hint", W.CITY_HINT in a1, a1)
W._hinted[0] = False                                         # the app restarted
a2 = W.answer("what's the weather like?")
check("after a restart: NOT again (remembered in the brain)", W.CITY_HINT not in a2, a2)
q("UPDATE asked_questions SET last_asked_at = now() - interval '8 days' WHERE qkey='weather:city'")
W._hinted[0] = False
check("…a week later it may be said once more", W.CITY_HINT in W.answer("weather?"))
W.geocode = lambda name: (0.0, 0.0, name)
W.refresh_async = lambda name=None: None
W.set_city("Pune")
q("DELETE FROM owner_profile WHERE key='city'")             # (even if the profile key were lost)
profile._all.cache_clear()
W._hinted[0] = False
q("UPDATE asked_questions SET last_asked_at = now() - interval '30 days' WHERE qkey='weather:city'")
check("once he told her, never again", W.CITY_HINT not in W.answer("weather?"))
from stiti.brain.sleep import resolve_entity                              # noqa: E402
me, city = resolve_entity("Kiran", "self"), resolve_entity("Indore", "place")
q("""INSERT INTO facts(subj_id, predicate, obj_id, fact_text, confidence) VALUES (%s, 'lives_in', %s, 'Kiran lives in Indore',
     0.9)""", (me, city))
check("a home city learned in chat is used (no need to ask)", W.city() == ("Indore", True), str(W.city()))

# ------------------------------------------------------------------------------------------------ no table
print("an un-migrated brain (no asked_questions) still works")
q("DROP TABLE asked_questions")
check("ask_ok degrades to 'ask'", L.ask_ok("x:y") is True)
llm["text"] = "Sure. What are you reading these days?"
try:
    r = Engine("text").turn("I'm bored")
    ok = bool(r)
except Exception as ex:
    ok, r = False, f"{type(ex).__name__}: {ex}"
check("a chat turn still answers", ok, r)

O.STATE.unlink(missing_ok=True)                            # leave no intro state behind for other suites
print(f"\n{passed}/{total} passed")
sys.exit(0 if passed == total else 1)
