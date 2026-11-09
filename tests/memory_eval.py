"""Memory eval in the LongMemEval taxonomy (retrieval side — no LLM needed).

Five abilities, multi-session synthetic life of "Tejmul" across ~3 weeks, Hinglish + English:
  extraction      — a fact said once, asked later
  multi_session   — answer needs two different sessions
  temporal        — "what did I say last Monday" (time-filtered recall)
  knowledge_update— the NEWER fact must outrank the old one
  abstention      — nothing relevant exists → top similarity must stay low
Metric: hit@5 (all needed episodes in top-5); abstention = top sim below threshold.
STITI_DB=postgresql:///stiti_test uv run python tests/memory_eval.py
Replace the synthetic life with consented real history later (report: private eval set).
"""
import os
import sys
from datetime import datetime, timedelta

if "stiti_test" not in os.getenv("STITI_DB", ""):
    sys.exit("refusing: set STITI_DB=postgresql:///stiti_test")
from stiti import embed  # noqa: E402
from stiti.brain import memory as M  # noqa: E402
from stiti.config import CFG  # noqa: E402
from stiti.db import q  # noqa: E402

q("TRUNCATE episodes, sessions, turns, decisions, segments RESTART IDENTITY CASCADE")
T0 = datetime(2026, 10, 19, 20, 0, tzinfo=CFG.tz)          # a Monday
LIFE = [  # (day offset, text)
    (0, "Aaj Rahul ke saath 1:1 tha, usne bola Q4 mein promotion discuss karenge"),
    (0, "I started reading Atomic Habits"),
    (1, "My landlord said rent goes up to 27k from December"),
    (2, "Gym mein trainer ne bola deadlift form theek karo"),
    (3, "Priya ki shaadi ki date fix ho gayi, 14 February"),
    (4, "I'm thinking of switching to a standing desk"),
    (5, "Arjun ka birthday 3 November ko hai, gift lena hai"),
    (7, "Monday ko demo hai Stiti ka, bahut nervous hoon"),
    (8, "Demo achha gaya! Manager impressed tha"),
    (9, "My sister Priya moved from Pune to Mumbai for her new job"),
    (10, "Doctor ne bola Vitamin D low hai, supplements lene hain"),
    (12, "I finished Atomic Habits, next is Deep Work"),
    (14, "Rahul said the promotion is approved, effective January"),
    (15, "Arjun is now moving to Hyderabad instead of Bangalore"),
    (16, "Weekend pe Lonavala trip plan kar rahe hain college friends ke saath"),
    (17, "I switched my phone plan to Jio 5G"),
]
ids = []
for day, text in LIFE:
    sid = M.start_session("text")
    v = embed.embed_docs([text])[0]
    eid = M.add_episode(sid, "user", text, vec=v)
    q("UPDATE episodes SET occurred_at=%s, ingested_at=%s WHERE id=%s",
      (T0 + timedelta(days=day), T0 + timedelta(days=day), eid))
    ids.append(eid)
E = {t: i for (_, t), i in zip(LIFE, ids)}
pick = lambda frag: next(i for t, i in E.items() if frag in t)  # noqa: E731

CASES = [
    ("extraction", "what did my trainer say about deadlift", [pick("deadlift")], {}),
    ("extraction", "Priya ki shaadi kab hai", [pick("14 February")], {}),
    ("extraction", "how much will my rent be", [pick("27k")], {}),
    ("multi_session", "which books have I read or am reading", [pick("started reading Atomic"), pick("finished Atomic")], {}),
    ("multi_session", "promotion ka kya hua", [pick("Q4 mein promotion"), pick("promotion is approved")], {}),
    ("temporal", "what happened on the Monday I had the demo",
     [pick("demo hai")], {"t_from": T0 + timedelta(days=7), "t_to": T0 + timedelta(days=8)}),
    ("temporal", "what did I say in my first week", [pick("Rahul ke saath")], {"t_from": T0, "t_to": T0 + timedelta(days=7)}),
    ("knowledge_update", "where does my sister live now", [pick("moved from Pune to Mumbai")], {"newer_than": None}),
    ("knowledge_update", "where is Arjun moving", [pick("Hyderabad instead")], {}),
]
ABSTAIN = ["what's my passport number", "kab mera car service due hai", "what did my therapist say"]

res: dict[str, list[bool]] = {}
for cat, question, need, kw in CASES:
    kw = {k: v for k, v in kw.items() if k in ("t_from", "t_to")}
    rows = M.recall(question, embed.embed_query(question), k=5, **kw)
    got = [r["episode_id"] for r in rows]
    ok = all(n in got for n in need)
    if cat == "knowledge_update":
        ok = ok and got.index(need[0]) == 0          # the newest truth must come first
    res.setdefault(cat, []).append(ok)
    print(("OK  " if ok else "MISS"), f"{cat:16} {question!r:46} top: {rows[0]['text'][:50]!r}")
for question in ABSTAIN:
    rows = M.recall(question, embed.embed_query(question), k=1)
    sim = rows[0]["sim"] if rows else 0.0
    ok = sim < 0.45
    res.setdefault("abstention", []).append(ok)
    print(("OK  " if ok else "MISS"), f"{'abstention':16} {question!r:46} top sim {sim:.2f}")
print()
total = sum(sum(v) for v in res.values()); n = sum(len(v) for v in res.values())
for cat, v in res.items():
    print(f"  {cat:16} {sum(v)}/{len(v)}")
print(f"  OVERALL          {total}/{n}")
sys.exit(0 if total >= n - 1 else 1)
