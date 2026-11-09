"""Two-way USER.md / LESSONS.md sync: owner edits (change / delete / add) must land in Postgres.
STITI_DB=postgresql:///stiti_test STITI_HOME=<tmp> uv run python tests/mdsync_eval.py
"""
import os, sys
if "stiti_test" not in os.getenv("STITI_DB", ""):
    sys.exit("refusing: set STITI_DB=postgresql:///stiti_test")
from stiti.brain import mdsync, sleep, lessons
from stiti.db import q, one

q("TRUNCATE facts, entities, episode_mentions, user_directives, lessons RESTART IDENTITY CASCADE")
for f in [dict(subject="Tejmul", predicate="lives_in", object="Pune", fact_text="Tejmul lives in Pune", functional=True),
          dict(subject="Tejmul", predicate="works_as", object="backend developer", object_is_entity=False, fact_text="Tejmul is a backend developer"),
          dict(subject="Priya", predicate="sister_of", object="Tejmul", fact_text="Priya is Tejmul's sister")]:
    sleep.apply_fact(f, [], {"tejmul": "self", "priya": "person", "pune": "place"})
sleep.apply_directive({"directive": "Reply in Hinglish when I speak Hinglish", "category": "talk_style", "supersession_key": "reply_language"}, [])
sleep.apply_directive({"directive": "Wake me at 7 on weekdays", "category": "routine", "supersession_key": "wake_time"}, [])
lessons.capture("don't give me long answers", mood=None, source_episode_ids=[])
lessons.capture("jab main stressed hoon tab joke mat karna", mood="stressed", source_episode_ids=[])
mdsync.render_all()

u = mdsync.USER.read_text()
u = u.replace("Tejmul lives in Pune", "Tejmul lives in Mumbai now")                     # change a fact
u = "\n".join(l for l in u.splitlines() if "backend developer" not in l) + "\n"         # delete a fact
u = u.replace("Wake me at 7 on weekdays", "Wake me at 6:30 on weekdays")                # change a directive
u = u.replace("## Never do\n- (nothing yet)", "## Never do\n- Never call me sir")       # add a directive
u = u.replace("## About me\n", "## About me\n- I am vegetarian\n")                       # add a fact
mdsync.USER.write_text(u)
l = mdsync.LESSONS.read_text()
l = l.replace("don't give me long answers", "keep answers under 3 sentences")             # edit a lesson
l = "\n".join(x for x in l.splitlines() if "joke mat karna" not in x and "stressed" not in x) + "\n"  # retire a lesson
l += "- [MUST NOT] use emojis\n"                                                           # add a lesson
mdsync.LESSONS.write_text(l)

print("sync:", mdsync.sync())
cur = [r["fact_text"] for r in q("SELECT fact_text FROM facts WHERE upper_inf(recorded) AND valid @> now() ORDER BY id")]
dirs = [r["directive"] for r in q("SELECT directive FROM user_directives WHERE status='active' ORDER BY id")]
les = [(r["guidance"], r["status"]) for r in q("SELECT guidance, status FROM lessons ORDER BY id")]
checks = {
    "fact changed": "Tejmul lives in Mumbai now" in cur and "Tejmul lives in Pune" not in cur,
    "old fact kept in history": one("SELECT 1 FROM facts WHERE fact_text='Tejmul lives in Pune' AND NOT upper_inf(recorded)") is not None,
    "fact deleted": "Tejmul is a backend developer" not in cur,
    "fact added": "I am vegetarian" in cur,
    "directive changed": "Wake me at 6:30 on weekdays" in dirs and "Wake me at 7 on weekdays" not in dirs,
    "directive added": "Never call me sir" in dirs,
    "lesson edited": ("keep answers under 3 sentences", "active") in les,
    "lesson retired": any("joke mat karna" in g and s == "retired" for g, s in les),
    "lesson added": ("use emojis", "active") in les,
    "re-rendered with ids": "[D" in mdsync.USER.read_text() and "**L" in mdsync.LESSONS.read_text(),
}
for k, v in checks.items(): print(("OK  " if v else "FAIL"), k)
print("second sync (no edits):", mdsync.sync())
sys.exit(0 if all(checks.values()) else 1)
