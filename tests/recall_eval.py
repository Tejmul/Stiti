"""Recall eval (build step 3): 20 Hinglish/English memories, 10 questions, right memory in top-3, <100 ms.

Runs ONLY against a throwaway DB so fake memories never touch the real brain:
  createdb stiti_test && psql stiti_test -f db/schema.sql
  STITI_DB=postgresql:///stiti_test uv run python tests/recall_eval.py
Measured 2026-11-10 on M2 8 GB: 10/10 (all rank 1), avg 9 ms embed+recall.
"""
import os
import sys
import time

if "stiti_test" not in os.getenv("STITI_DB", ""):
    sys.exit("refusing: set STITI_DB=postgresql:///stiti_test (never run evals on the real brain)")

from stiti import embed  # noqa: E402
from stiti.brain import memory as M  # noqa: E402

MEMS = ["Meri sister Priya Pune mein rehti hai", "I work as a backend developer at a fintech startup",
        "Kal dentist appointment hai shaam 5 baje", "Mummy ka birthday 14 December ko hai",
        "I love Behrouz biryani, especially on Fridays", "Office mein manager Rahul se jhagda hua, bahut gussa aaya",
        "My best friend Arjun is moving to Bangalore next month", "Gym jaana start kiya hai, Monday Wednesday Friday",
        "I'm learning Japanese on Duolingo, 40 day streak", "Stiti project ka Postgres engine aaj raat banana hai",
        "I hate when people send voice notes longer than 2 minutes", "My car insurance renews in March",
        "Papa ki BP ki dawai khatam ho gayi, lani hai", "I want to visit Ladakh with Arjun next summer",
        "Netflix pe Dark dekh raha hoon, season 2", "My laptop is a MacBook Pro M2 with 8GB RAM",
        "Subah 6 baje uthna hai daily", "I prefer chai over coffee, adrak wali", "Priya ki shaadi February mein hai",
        "Rent 25 tareekh ko dena hota hai"]
QS = [("where does my sister live", 0), ("what do I do for work", 1), ("when is the dentist", 2),
      ("mom birthday kab hai", 3), ("which biryani do I like", 4), ("who did I fight with at office", 5),
      ("Arjun kahan shift ho raha hai", 6), ("which days do I go to gym", 7), ("what language am I learning", 8),
      ("rent kab dena hai", 19)]

sid = M.start_session("text")
ids = [M.add_episode(sid, "user", t, vec=v) for t, v in zip(MEMS, embed.embed_docs(MEMS))]
hits, lat = 0, []
for q, want in QS:
    t = time.perf_counter()
    rows = M.recall(q, embed.embed_query(q), k=3)
    lat.append((time.perf_counter() - t) * 1000)
    ok = ids[want] in [r["episode_id"] for r in rows]
    hits += ok
    print(("OK  " if ok else "MISS"), f"{q!r:38} -> {rows[0]['text'][:60]!r}")
print(f"\n{hits}/10 in top-3 · embed+recall avg {sum(lat) / len(lat):.0f} ms, max {max(lat):.0f} ms")
sys.exit(0 if hits >= 9 and max(lat) < 100 else 1)
