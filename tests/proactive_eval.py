"""Proactivity checks with simulated presence/time (no mic, no calendar needed).
STITI_DB=postgresql:///stiti_test uv run python tests/proactive_eval.py
"""
import os, sys, random
from datetime import datetime, timedelta
if "stiti_test" not in os.getenv("STITI_DB", ""):
    sys.exit("refusing: set STITI_DB=postgresql:///stiti_test")
from stiti.config import CFG
from stiti.db import q, one
from stiti.life import proactive as P
random.seed(7)   # the nudge gate samples (Thompson); fix the seed so the test is deterministic

q("TRUNCATE tasks, intents, nudges, nudge_arms RESTART IDENTITY CASCADE")
now = datetime.now(CFG.tz).replace(hour=15, minute=0, second=0, microsecond=0)
q("INSERT INTO tasks(title, due) VALUES ('Send the invoice', now() + interval '90 minutes')")
fid = P.maybe_followup("kal mera interview hai 11 baje, thoda nervous hoon")
dup_blocked = P.maybe_followup("kal mera interview hai 11 baje") is None      # same event mentioned again
q("UPDATE intents SET fire_at = now() - interval '1 minute' WHERE id=%s", (fid,))   # pretend it's tomorrow afternoon
pres = P.Presence(present=True, idle_s=3, locked=False, app="Code", active_minutes=170)
cands = P.candidates(pres, now)
kinds = [k for k, _, _ in cands]
for k, t, _ in cands: print(f"  candidate {k:12} {t}")
log = []
sent = P.tick(pres, lambda text, kind, present: log.append((kind, text)) or "voice", now=now)
checks = {
    "follow-up created from 'interview kal hai'": fid is not None,
    "follow-up asks how it went": any("How did the interview go?" in t for _, t, _ in cands),
    "deadline nudge": "deadline" in kinds,
    "break nudge after 170 min": "break" in kinds,
    "urgent + one non-urgent delivered": len(sent) >= 2 and sum(k not in ("meeting_soon", "deadline") for _, k, _ in sent) == 1,
    "no duplicate follow-up": dup_blocked,
    "question doesn't create follow-up": P.maybe_followup("kal interview hai kya?") is None,
}
nid = sent[0][0]
P.feedback(nid, "dismissed")
arm = one("SELECT alpha, beta FROM nudge_arms WHERE kind=%s", (sent[0][1],))
checks["dismiss lowers the arm"] = arm["beta"] > 1
checks["'don't remind me about breaks' disables"] = P.disable_from_text("please don't remind me about breaks") == "break" \
    and not P.want("break")
quiet_now = now.replace(hour=23, minute=30)
q("TRUNCATE nudges")
s2 = P.tick(P.Presence(True, 3, False, "Code", 10), lambda *a: "voice", now=quiet_now)
checks["quiet hours: only urgent"] = all(k in ("meeting_soon", "deadline") for _, k, _ in s2)
for k, v in checks.items(): print(("OK  " if v else "FAIL"), k)
print("presence now:", P.PresenceTracker().sample())
sys.exit(0 if all(checks.values()) else 1)
