"""Learning loops: undo + clarify + exemplar learning, inferred lesson promotion, lesson scoring, curation, segments.
STITI_DB=postgresql:///stiti_test STITI_HOME=<tmp> uv run python tests/learning_eval.py
"""
import os, sys
if "stiti_test" not in os.getenv("STITI_DB", ""):
    sys.exit("refusing: set STITI_DB=postgresql:///stiti_test")
from stiti.db import q, one
from stiti.engine import Engine
from stiti.brain import learning
from stiti.config import CFG
q("TRUNCATE lessons, tasks, intents, decisions, turns, segments RESTART IDENTITY CASCADE")
e = Engine("text")
r1 = e.turn("add todo buy eggs"); r2 = e.turn("nahi galat"); r3 = e.turn("I was just talking yaar")
task = one("SELECT status FROM tasks WHERE title ILIKE '%eggs%'")
learned = (CFG.home / "exemplars.jsonl").read_text() if (CFG.home / "exemplars.jsonl").exists() else ""
long_reply = " ".join(["This is a long winded answer"] * 10)
e.last_reply_text = long_reply; a1 = e.turn("short mein bolo yaar")
e.last_reply_text = long_reply; a2 = e.turn("short mein please")
les = one("SELECT status, seen_count, confidence FROM lessons WHERE situation='inferred:dont_long'")
# scoring + curation
lid = one("SELECT id FROM lessons WHERE situation='inferred:dont_long'")["id"]
for _ in range(4): learning.score_lessons([lid], was_corrected=True)
cur = learning.curate()
retired = one("SELECT status FROM lessons WHERE id=%s", (lid,))["status"]
seg = learning.build_segments()
outcomes = q("SELECT outcome, count(*) n FROM decisions WHERE outcome IS NOT NULL GROUP BY 1")
checks = {
    "undo removed the task": task and task["status"] == "cancelled",
    "asked what he meant": "what did you mean" in r2.lower(),
    "learned 'buy eggs' as chat": '"label": "chat"' in learned and "buy eggs" in learned,
    "1st 'short mein' → candidate (silent)": a1 != "Got it — from now on I'll keep it short. 👍",
    "2nd 'short mein' → promoted": les and les["status"] in ("active", "retired") and les["seen_count"] >= 2,
    "promotion acknowledged": "keep it short" in a2,
    "harmful lesson retired by curation": retired == "retired" and cur["retired"] >= 1,
    "segments built": seg >= 1,
    "decision outcomes recorded": bool(outcomes),
}
print(f"  replies: {r1!r} | {r2!r} | {r3!r} | {a2!r}")
for k, v in checks.items(): print(("OK  " if v else "FAIL"), k)
sys.exit(0 if all(checks.values()) else 1)
