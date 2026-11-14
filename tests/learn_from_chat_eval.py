"""She learns from normal conversation (D38): night extraction, real-time life updates, honest "noted".

His real data (2026-11-14, 4 days, ~270 episodes): 12 facts, all from a resume import; two night runs extracted
{} and {"added": 1}; "Actually, I left MVRX Labs…" got "Noted. I will mark that down." and nothing was written.
Here the same shapes with a made-up person (Ravi). The cloud LLM is FAKED (router.complete returns realistic
extraction JSON), so this runs offline and deterministically.

STITI_DB=postgresql:///stiti_test STITI_HOME=<tmp> uv run python tests/learn_from_chat_eval.py
"""
from __future__ import annotations

import json
import os
import re
import sys

db = os.environ.get("STITI_DB", "")
if not db.rstrip("/").split("/")[-1].startswith("stiti_test"):
    sys.exit(f"refusing to run against {db!r}: use a stiti_test* database")
os.environ.setdefault("STITI_LIVE_WARM", "0")
os.environ.setdefault("STITI_EVENTKIT", "off")
os.environ["STITI_SLEEP_NO_WAIT"] = "1"

passed = total = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global passed, total
    total += 1
    passed += bool(cond)
    print(f"  {'✓' if cond else '✗'} {name}" + (f" — {detail}" if detail and not cond else ""))


from stiti import profile, router                                        # noqa: E402
from stiti.brain import factstore, lifeupdate, memory, psych, sleep, strategy   # noqa: E402
from stiti.db import one, q                                              # noqa: E402

q("""TRUNCATE facts, entities, episode_mentions, user_directives, lessons, episodes, sessions, turns, decisions,
     consolidation_runs, briefing_cache RESTART IDENTITY CASCADE""")
profile.set("name", "Ravi")
profile.set("pronouns", "he")

# ---------------------------------------------------------------- the fake cloud LLM
PROMPTS: list[str] = []
CHAT_REPLY = {"text": "Okay."}


def _lines(prompt: str) -> dict[str, int]:
    return {m["t"]: int(m["id"]) for m in re.finditer(r"^\[(?P<id>\d+)\] \([\d-]+\) Ravi: (?P<t>.+)$", prompt, re.M)}


def _known(prompt: str, word: str) -> int | None:
    m = re.search(rf"^F(\d+): [^\n]*{word}", prompt, re.M)
    return int(m.group(1)) if m else None


def fake_extract(prompt: str) -> dict:
    """What a decent free model returns for these lines — including the junk the validator must reject."""
    out = {"entities": [], "facts": [], "ends": [], "directives": []}
    E, F = out["entities"], out["facts"]

    def fact(s, p, o, kind, text, ev, conf=0.9, functional=False, vf=None):
        F.append({"subject": s, "predicate": p, "object": o, "object_kind": kind, "fact_text": text,
                  "functional": functional, "valid_from": vf, "evidence_ids": ev, "confidence": conf})
    for t, i in _lines(prompt).items():
        if "Meera" in t and "Pune" in t:
            E += [{"name": "Meera", "kind": "person", "aliases": ["my sister"]},
                  {"name": "Pune", "kind": "place", "aliases": []}]
            fact("Meera", "sister_of", "Ravi", "person", "Meera is Ravi's sister.", [i])
            fact("Meera", "lives_in", "Pune", "place", "Meera is moving to Pune.", [i], functional=True)
            if "Finlo" in t:
                E.append({"name": "Finlo", "kind": "org", "aliases": []})
                fact("Meera", "works_at", "Finlo", "org", "Meera has a new job at Finlo.", [i], functional=True)
            else:   # the same thing said again, worded differently → must merge, not duplicate
                fact("Meera", "sister_of", "Ravi", "person", "Meera is Ravi's younger sister.", [i])
        if "work at Ledgerly" in t:
            E.append({"name": "Ledgerly", "kind": "org", "aliases": []})
            fact("Ravi", "interns_at", "Ledgerly", "org", "Ravi is a backend intern at Ledgerly.", [i], functional=True)
        if "badminton" in t:
            fact("Ravi", "likes", "badminton", "literal", "Ravi loves playing badminton on weekends.", [i])
        if "Tilecraft" in t and "building" in t:
            E += [{"name": "Tilecraft", "kind": "project", "aliases": []}, {"name": "Arjun", "kind": "person", "aliases": []}]
            fact("Ravi", "works_on", "Tilecraft", "project", "Ravi is building Tilecraft, a tile design app.", [i])
            fact("Arjun", "works_on", "Tilecraft", "project", "Arjun builds Tilecraft with Ravi.", [i])
        if "keep replies short in the morning" in t:
            out["directives"].append({"directive": "Keep replies short in the morning.", "category": "talk_style",
                                      "topic": "reply_length", "standing": True, "evidence_ids": [i]})
        if "Switch to Hindi" in t:   # a one-off command the model wrongly offers as a rule
            out["directives"].append({"directive": "Switch to Hindi.", "category": "talk_style", "topic": "language",
                                      "standing": False, "evidence_ids": [i]})
        if "blorf" in t:             # garbled STT: the model is unsure
            fact("Ravi", "owns", "a blorf", "literal", "Ravi owns a blorf.", [i], conf=0.3)
        if "left" in t and "Ledgerly" in t and (fid := _known(prompt, "Ledgerly")):
            out["ends"].append({"fact_id": fid, "valid_to": "2026-09-30", "wrong": False, "evidence_ids": [i]})
            fact("Ravi", "left", "Ledgerly", "org", "Ravi left Ledgerly in September 2026 after his internship.", [i],
                 vf="2026-09-30")
        if "Tilecraft is dead" in t and (fid := _known(prompt, "building Tilecraft")):
            out["ends"].append({"fact_id": fid, "valid_to": None, "wrong": False, "evidence_ids": [i]})
            fact("Tilecraft", "status", "closed", "literal", "Tilecraft has been closed.", [i])
    # junk a weak model produces: a fact taken from Stiti's line (no owner evidence), and one with an invented id
    fact("Ravi", "studies_at", "Lakeview College", "org", "Ravi studies at Lakeview College.", [])
    fact("Ravi", "owns", "a red car", "literal", "Ravi owns a red car.", [999999])
    return out


def fake_complete(messages, **kw):
    text = messages[-1]["content"] if kw.get("schema") is None else messages[0]["content"]
    if kw.get("schema") is sleep.EXTRACT_SCHEMA:
        PROMPTS.append(text)
        return {"text": json.dumps(fake_extract(text)), "provider": "fake", "model": "fake", "ms": 1.0,
                "tokens_in": len(text) // 4, "tokens_out": 200, "tool_calls": []}
    if "insights" in text:
        return {"text": '{"insights": []}', "provider": "fake", "model": "fake", "ms": 1.0, "tokens_in": 1,
                "tokens_out": 1, "tool_calls": []}
    CHAT_REPLY.setdefault("calls", 0)
    CHAT_REPLY["calls"] += 1
    return {"text": CHAT_REPLY["text"], "provider": "fake", "model": "fake", "ms": 1.0, "tokens_in": 1,
            "tokens_out": 1, "tool_calls": []}


def fake_stream(messages, **kw):
    info = kw.get("info")
    t = fake_complete(messages)["text"]
    if info is not None:
        info.update({"provider": "fake", "model": "fake", "first_ms": 1.0, "ms": 1.0, "text": t})
    yield t


router.complete = fake_complete
router.stream = fake_stream


def ep(sess, speaker, text, importance=3, privacy=1):
    return memory.add_episode(sess, speaker, text, origin="owner" if speaker == "user" else "agent",
                              importance=importance, privacy=privacy)


def cur(where: str = "TRUE", args=()) -> list[dict]:
    return q(f"""SELECT f.*, s.name subj FROM facts f JOIN entities s ON s.id=f.subj_id
                 WHERE upper_inf(f.recorded) AND f.valid @> now() AND {where} ORDER BY f.id""", args)


# ---------------------------------------------------------------- 1. a normal chat day → facts, people, rules
print("night extraction: normal conversation becomes facts, people and rules")
s1 = memory.start_session("voice")
ids = {}
ids["hey"] = ep(s1, "user", "Hey Stiti.")
ep(s1, "stiti", "Hi Ravi!")
ids["meera"] = ep(s1, "user", "My sister Meera is moving to Pune for her new job at Finlo.")
ep(s1, "stiti", "That's big news. You're a final-year student at Lakeview College, right?")
ids["work"] = ep(s1, "user", "No yaar. I work at Ledgerly as a backend intern, it's been fun.")
ids["q"] = ep(s1, "user", "What's the weather like in Pune today?")
ids["cmd"] = ep(s1, "user", "Set an alarm for 7 am", importance=1)
ids["badminton"] = ep(s1, "user", "I really love playing badminton on weekends.")
ids["frag"] = ep(s1, "user", "I'm building")
ids["tile"] = ep(s1, "user", "I'm building Tilecraft, a tile design app, with Arjun.")
ids["rule"] = ep(s1, "user", "Please always keep replies short in the morning.")
ids["hindi"] = ep(s1, "user", "Switch to Hindi.")
ids["garble"] = ep(s1, "user", "Aave yas kono blorf maalu kocha.")
ids["p2"] = ep(s1, "user", "My therapist says the panic attacks are getting better.", privacy=2)
st = sleep.extract()
print(f"    stats: {st}")
facts = cur()
texts = [f["fact_text"] for f in facts]
check("facts extracted from plain chat (≥ 5)", st["facts"].get("added", 0) >= 5, str(st["facts"]))
check("his sister is a person linked to him", bool(cur("f.predicate='sister_of' AND s.name='Meera'")), str(texts))
check("where she's moving is a place entity (functional lives_in)",
      bool(cur("f.predicate='lives_in' AND f.functional AND s.name='Meera'")))
check("his internship → interns_at Ledgerly", bool(cur("f.predicate='interns_at' AND f.fact_text ILIKE '%%Ledgerly%%'")))
check("likes badminton", any("badminton" in t for t in texts))
ents = {r["name"]: r["kind"] for r in q("SELECT name, kind FROM entities WHERE merged_into IS NULL")}
check("entities: Meera, Pune, Finlo, Ledgerly, Tilecraft, Arjun",
      all(n in ents for n in ("Meera", "Pune", "Finlo", "Ledgerly", "Tilecraft", "Arjun")), str(ents))
check("episode_mentions link his line to Meera",
      bool(one("""SELECT 1 x FROM episode_mentions m JOIN entities e ON e.id=m.entity_id
                  WHERE m.episode_id=%s AND e.name='Meera'""", (ids["meera"],))))
check("a lasting rule became a directive", bool(one(
    "SELECT 1 x FROM user_directives WHERE status='active' AND directive ILIKE '%%short in the morning%%'")))
check("a one-off 'Switch to Hindi' is NOT a forever-rule",
      not one("SELECT 1 x FROM user_directives WHERE directive ILIKE '%%hindi%%'"))
check("nothing taken from Stiti's line (no 'studies at Lakeview')", not any("Lakeview" in t for t in texts), str(texts))
check("invented evidence id rejected (no 'red car')", not any("red car" in t for t in texts))
check("misheard/low-confidence rejected (no 'blorf')", not any("blorf" in t for t in texts))
sent = "\n".join(p.split("CONVERSATION:")[-1] for p in PROMPTS)
check("questions are not sent as facts", "weather" not in sent)
check("commands (importance 1) are not sent", "alarm" not in sent)
check("greetings are not sent", "Hey Stiti" not in sent)
check("a cut-off fragment is not sent twice", sent.count("I'm building") == 1)
check("Stiti's reply goes along only as context", "Stiti: That's big news" in sent)
check("the prompt asks for ends of KNOWN FACTS", "KNOWN FACTS" in PROMPTS[0])
check("P2 (private) never leaves the Mac", "therapist" not in sent)
check("rejections are counted", st["rejected"].get("no_evidence", 0) >= 2 and st["rejected"].get("low_confidence", 0) >= 1,
      str(st["rejected"]))
run = one("SELECT status, watermark FROM consolidation_runs WHERE job='extract' ORDER BY id DESC LIMIT 1")
check("run logged ok with a watermark", run["status"] == "ok" and run["watermark"] >= ids["garble"], str(run))
check("summary line has the counts", "facts +" in sleep.summary({"extract": st, "profile": "- a\n- b"}))

# ---------------------------------------------------------------- 2. next day: a correction + a repeat
print("night extraction: corrections end old facts, repeats merge")
s2 = memory.start_session("voice")
ep(s2, "stiti", "Morning, Ravi.")
ids["left"] = ep(s2, "user", "I finished my internship at Ledgerly in September, I left.")
ids["again"] = ep(s2, "user", "My sister Meera is moving to Pune, I told you na. So happy for her.")
n_sister = len(cur("f.predicate='sister_of'"))
st2 = sleep.extract()
print(f"    stats: {st2}")
old = one("""SELECT valid, upper_inf(recorded) rec FROM facts WHERE predicate='interns_at' AND fact_text ILIKE '%%Ledgerly%%'""")
check("'I left Ledgerly' ends the internship fact (valid gets an end)", old["valid"].upper is not None and old["rec"],
      str(old))
check("…and it's kept in history, not deleted", old is not None)
check("'left Ledgerly' is now a current fact", bool(cur("f.predicate='left'")))
check("the same sister said again is merged (confirmed), not duplicated",
      len(cur("f.predicate='sister_of'")) == n_sister and st2["facts"].get("confirmed", 0) >= 1, str(st2["facts"]))
prof = one("SELECT content FROM briefing_cache WHERE key='standing_profile'")
sleep.standing_profile()
prof = one("SELECT content FROM briefing_cache WHERE key='standing_profile'")["content"]
check("standing profile has the update, not the old internship",
      "left Ledgerly" in prof and "intern at Ledgerly" not in prof, prof)
sleep.render()
user_md = (sleep.CFG.home / "USER.md").read_text()
check("USER.md shows his people (Meera)", "Meera" in user_md)
report = (sleep.CFG.home / "GRAPH_REPORT.md").read_text()
check("GRAPH_REPORT lists the ended fact under 'Recently changed'", "Ledgerly" in report.split("Recently changed")[-1])

# ---------------------------------------------------------------- 3. real time: life updates in the turn
print("real time: 'I left X' is written in the turn, and her reply is honest")
from stiti.engine import Engine                                           # noqa: E402

me = sleep.resolve_entity("Ravi", "self")
factstore.add(me, "interns_at", "Ravi is an AI intern at Orbitly.", obj_id=sleep.resolve_entity("Orbitly", "org"))
factstore.add(me, "noted", "Ravi is a 2x state-level hockey player and a former team captain.")
eng = Engine("text")
CHAT_REPLY.update(text="Noted. I will mark that down.", calls=0)
r = eng.turn("Actually, I left Orbitly change it down. It's been around in September, my internship period is done "
             "and I left Orbitly.")
lifeupdate.join()
check("reply says what was really saved", r.startswith("Got it — updated: you left Orbitly"), r)
check("no LLM needed for it", CHAT_REPLY["calls"] == 0)
orb = one("SELECT valid FROM facts WHERE fact_text='Ravi is an AI intern at Orbitly.'")
check("the Orbitly internship fact is ended", orb["valid"].upper is not None)
lf = cur("f.predicate='left' AND f.fact_text ILIKE '%%Orbitly%%'")
check("'left Orbitly' saved once, dated September", len(lf) == 1 and lf[0]["valid"].lower.month == 9,
      str([(x["fact_text"], x["valid"]) for x in lf]))
check("the turn's episode is marked important", one("SELECT importance FROM episodes WHERE id=%s",
                                                     (eng.last_user_ep,))["importance"] >= 7)
n_les = one("SELECT count(*) n FROM lessons")["n"]
r = eng.turn("I don't play hockey anymore")
lifeupdate.join()
check("'I don't play hockey anymore' → updated", "hockey" in r and r.startswith("Got it"), r)
check("…the hockey fact is ended", not cur("f.fact_text ILIKE '%%hockey player%%'"))
check("…and it's not mistaken for a lesson about how she talks", one("SELECT count(*) n FROM lessons")["n"] == n_les)
r = eng.turn("Okay Pugal is my son. Do you know him?")
lifeupdate.join()
check("'Pugal is my son' → person + relation", bool(cur("s.name='Pugal' AND f.predicate='son_of'")), r)
prof = one("SELECT content FROM briefing_cache WHERE key='standing_profile'")["content"]
check("standing profile rebuilt right after the turn", "Pugal" in prof and "left Orbitly" in prof, prof)
check("USER.md re-rendered right after the turn", "Pugal" in (sleep.CFG.home / "USER.md").read_text())
r = eng.turn("Remember that my locker code is 4412.")
lifeupdate.join()
check("'remember that…' is saved before she says so", r == "Noted — I'll remember that."
      and bool(cur("f.fact_text ILIKE '%%locker code is 4412%%'")), r)
r = eng.turn("actually it's Lakeview School of Technology, not Lakeview College")
check("a correction with nothing to correct is not claimed", "updated" not in r.lower(), r)

print("real time: no hollow 'noted'")
CHAT_REPLY.update(text="Noted. I will mark that down.", calls=0)
r = eng.turn("Aave yas kono bhai maalu.")
check("LLM's 'Noted. I will mark that down.' is not said when nothing was saved",
      not psych.MEMORY_CLAIM_RX.search(r), r)
CHAT_REPLY.update(text="Got it, noted. Sounds like a fun weekend.")
r = eng.turn("We went to the lake and had chai there.")
check("'Got it, noted.' → the claim is dropped, the rest stays", "noted" not in r.lower() and "weekend" in r, r)
a = strategy.make("ACKNOWLEDGE", "english")
check("streamed 'Noted.' is not spoken without a save", psych.StreamLint(policy=a).feed("Noted. ") is None)
b = strategy.make("ACKNOWLEDGE", "english")
b.allow_memory_claim = True
check("…and is spoken when something was saved", psych.StreamLint(policy=b).feed("Noted. ") is not None)
check("brief tells the LLM nothing was saved", "Nothing was saved to memory" in psych.rules_block(a, can_do=""))
check("brief tells the LLM what was saved", "Saved to memory this turn: you left X" in
      psych.rules_block(b, can_do="", saved=["you left X"]))

print("real time: what the patterns can't parse goes to the extractor after the reply")
CHAT_REPLY.update(text="Okay, I've updated that.", calls=0)
r = eng.turn("Tilecraft is dead now, actually.")
check("no claim in the reply (nothing saved yet)", not psych.MEMORY_CLAIM_RX.search(r), r)
lifeupdate.join()
check("background extraction ended 'building Tilecraft'", not cur("f.fact_text ILIKE 'Ravi is building Tilecraft%%'"))
check("…and added the new state", bool(cur("f.fact_text ILIKE '%%been closed%%'")))
check("P2 turns never go to the background extractor", lifeupdate.after_reply(1, 2) is False)
n = len(cur())
r = eng.turn("If I left Orbitly I would be sad. Remember to call mom at 5.")
lifeupdate.join()
check("hypotheticals / 'remember to…' are not facts", not cur("f.fact_text ILIKE '%%call mom%%'")
      and not cur("f.fact_text ILIKE '%%would be sad%%'"), str([f["fact_text"] for f in cur()][n:]))
for qn in ("What do you know about me?", "Do you remember my sister?"):
    before = len(cur())
    eng.turn(qn)
    lifeupdate.join()
    check(f"a question writes nothing: {qn!r}", len(cur()) == before)

print(f"{passed}/{total} passed")
sys.exit(0 if passed == total else 1)
