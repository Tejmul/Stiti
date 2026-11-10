"""Read-only views of Stiti's brain for the web Memory page, plus the two owner edits it allows
(tell Stiti a fact, forget a fact). Postgres stays the source; USER.md is re-rendered after each edit
so the markdown and the page never disagree. Only privacy < 2 rows are shown (P2 never leaves the brain)."""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta

from ..config import CFG
from ..db import one, q

# Facts have free-text predicates ("noted"), so the page groups them by what they're about.
GROUPS = [
    ("Work", r"\b(intern|engineer|job|work(ed|s)? at|company|startup|lead intern|founding team)\b"),
    ("Study", r"\b(student|b\.?tech|degree|college|university|school|cgpa|exam|semester|course)\b"),
    ("Projects", r"\b(built|building|project|app|system|agent)\b"),
    ("Skills", r"\b(stack|skills?|competitive programm|codeforces|leetcode|python|typescript)\b"),
    ("Ventures", r"\b(found(ed|er)|ngo|freelanc|content|instagram|community|mrr)\b"),
    ("Life", r"\b(football|sport|family|lives?|home|likes?|loves?|hates?|music|food|health|sleep)\b"),
]


def group_of(text: str) -> str:
    t = text.lower()
    for name, rx in GROUPS:
        if re.search(rx, t):
            return name
    return "Other"


def _iso(d) -> str | None:
    return d.isoformat() if isinstance(d, (datetime, date)) else None


def overview() -> dict:
    from .. import profile
    facts = q("""SELECT f.id, f.fact_text, f.origin, lower(f.valid) AS since FROM facts f JOIN entities e ON e.id=f.subj_id
                 WHERE e.kind='self' AND upper_inf(f.recorded) AND f.valid @> now() AND f.privacy < 2 ORDER BY f.id""")
    people = q("""SELECT e.id, e.kind, e.name, e.summary,
                         (SELECT count(*) FROM facts f WHERE (f.subj_id=e.id OR f.obj_id=e.id) AND upper_inf(f.recorded)) AS n,
                         (SELECT array_agg(f.fact_text ORDER BY f.id) FROM facts f WHERE f.subj_id=e.id
                            AND upper_inf(f.recorded) AND f.privacy < 2) AS facts
                  FROM entities e WHERE e.kind<>'self' AND e.merged_into IS NULL AND e.privacy < 2
                  ORDER BY n DESC, e.name LIMIT 60""")
    directives = q("""SELECT id, category, directive, origin FROM user_directives WHERE status='active'
                      ORDER BY category, id""")
    lessons = q("""SELECT id, situation, guidance, polarity, confidence, seen_count FROM lessons
                   WHERE status='active' ORDER BY confidence DESC, id LIMIT 40""")
    traits = q("SELECT key, label, confidence, source FROM traits WHERE label IS NOT NULL ORDER BY key")
    reflections = q("SELECT text, confidence, created_at FROM reflections ORDER BY created_at DESC LIMIT 6")
    docs = q("""SELECT d.id, d.title, d.path, d.kind, d.ingested_at, count(c.id) AS chunks FROM documents d
                LEFT JOIN chunks c ON c.document_id=d.id WHERE d.privacy < 2
                GROUP BY d.id ORDER BY d.ingested_at DESC LIMIT 40""")
    today = datetime.now(CFG.tz).date()
    days = [today - timedelta(days=i) for i in range(13, -1, -1)]
    habits = []
    for h in q("SELECT id, name, cue, target_per_week, strength, status FROM habits WHERE status<>'retired' ORDER BY id"):
        ev = {r["day"]: r["done"] for r in q("SELECT day, done FROM habit_events WHERE habit_id=%s AND day >= %s",
                                               (h["id"], days[0]))}
        habits.append({"name": h["name"], "cue": h["cue"], "target": h["target_per_week"],
                       "strength": round(float(h["strength"] or 0), 2), "status": h["status"],
                       "days": [ev.get(d) for d in days]})
    mood_rows = q("""SELECT (occurred_at AT TIME ZONE %s)::date AS day, emotion->>'label' AS label, count(*) AS n
                     FROM episodes WHERE speaker='user' AND emotion IS NOT NULL AND occurred_at >= %s
                     GROUP BY 1, 2""", (str(CFG.tz), days[0]))
    mood = []
    for d in days:
        rows = sorted([r for r in mood_rows if r["day"] == d], key=lambda r: -r["n"])
        mood.append({"day": d.isoformat(), "label": rows[0]["label"] if rows else None,
                     "n": sum(r["n"] for r in rows), "mix": {r["label"]: r["n"] for r in rows}})
    counts = one("""SELECT (SELECT count(*) FROM episodes WHERE speaker IN ('user','stiti') AND privacy < 2) AS moments,
                           (SELECT count(*) FROM sessions) AS conversations,
                           (SELECT min(occurred_at) FROM episodes) AS since""")
    todos = q("""SELECT id, title, due FROM tasks WHERE status='open' AND parent_id IS NULL
                 ORDER BY due NULLS LAST, created_at DESC LIMIT 20""")
    alarms = q("""SELECT id, kind, fire_at, rrule, COALESCE(payload->>'say', payload->>'text') AS text FROM intents
                  WHERE state IN ('pending','armed') AND fire_at IS NOT NULL ORDER BY fire_at LIMIT 20""")
    courses = q("SELECT id, title, status, cursor, updated_at FROM tutor_courses ORDER BY updated_at DESC LIMIT 10")
    return {
        "name": profile.name() if profile.get("name") else None,
        "counts": {"facts": len(facts), "people": len(people), "rules": len(directives) + len(lessons),
                   "habits": len(habits), "docs": len(docs), "moments": counts["moments"],
                   "conversations": counts["conversations"], "since": _iso(counts["since"])},
        "facts": [{"id": f["id"], "text": f["fact_text"], "group": group_of(f["fact_text"]),
                   "mine": f["origin"] == "owner_edit", "since": _iso(f["since"])} for f in facts],
        "people": [{"id": p["id"], "kind": p["kind"], "name": p["name"], "summary": p["summary"],
                    "facts": (p["facts"] or [])[:4]} for p in people],
        "directives": [{"id": d["id"], "category": d["category"], "text": d["directive"]} for d in directives],
        "lessons": [{"id": l["id"], "when": l["situation"], "text": l["guidance"], "dont": l["polarity"] == "dont",
                     "confidence": round(float(l["confidence"] or 0), 2), "seen": l["seen_count"]} for l in lessons],
        "traits": [{"key": t["key"], "label": t["label"], "confidence": round(float(t["confidence"] or 0), 2)}
                   for t in traits],
        "reflections": [{"text": r["text"], "at": _iso(r["created_at"])} for r in reflections],
        "habits": habits, "mood": mood,
        "docs": [{"title": d["title"], "kind": d["kind"], "chunks": d["chunks"], "at": _iso(d["ingested_at"])}
                 for d in docs],
        "todos": [{"id": t["id"], "title": t["title"], "due": _iso(t["due"])} for t in todos],
        "alarms": [{"id": a["id"], "kind": a["kind"], "at": _iso(a["fire_at"]), "repeats": bool(a["rrule"]),
                    "text": a["text"] or ""} for a in alarms],
        "courses": [{"title": c["title"], "status": c["status"], "at": _iso(c["updated_at"])} for c in courses],
    }


def moments(query: str = "", before: str | None = None, limit: int = 60) -> list[dict]:
    """Conversation history, newest first; optional keyword search (full-text, then substring)."""
    args: list = []
    where = "speaker IN ('user','stiti') AND privacy < 2"
    if before:
        where += " AND occurred_at < %s"
        args.append(before)
    if query.strip():
        where += " AND (tsv @@ plainto_tsquery('simple', %s) OR text ILIKE %s)"
        args += [query.strip(), f"%{query.strip()}%"]
    rows = q(f"""SELECT id, speaker, text, occurred_at, emotion->>'label' AS mood FROM episodes WHERE {where}
                 ORDER BY occurred_at DESC LIMIT %s""", (*args, min(limit, 200)))
    return [{"id": r["id"], "who": "you" if r["speaker"] == "user" else "stiti", "text": r["text"],
             "at": r["occurred_at"].isoformat(), "mood": r["mood"] if r["speaker"] == "user" else None} for r in rows]


def add_fact(text: str) -> dict:
    from ..brain import mdsync
    text = re.sub(r"\s+", " ", text).strip(" -•")[:400]
    if len(text) < 3:
        raise ValueError("too short")
    mdsync.sync()                                  # import his own USER.md edits first, so none are overwritten
    row = one("""INSERT INTO facts(subj_id, predicate, obj_literal, fact_text, confidence, origin)
                 VALUES (%s,'noted',%s,%s,0.95,'owner_edit') RETURNING id""", (mdsync._self_id(), text, text))
    mdsync.render_all()
    return {"id": row["id"], "text": text, "group": group_of(text), "mine": True}


def forget_fact(fid: int) -> bool:
    """Retract (kept in history, like deleting the line from USER.md)."""
    from ..brain import mdsync
    mdsync.sync()
    n = q("UPDATE facts SET recorded = tstzrange(lower(recorded), now()) WHERE id=%s AND upper_inf(recorded) RETURNING id",
          (fid,))
    mdsync.render_all()
    return bool(n)
