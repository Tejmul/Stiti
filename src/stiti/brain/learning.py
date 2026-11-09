"""Learning loops — Stiti improves from his reactions, no LLM training (report §Lessons, D10).

1. Inferred lessons: "too long" / "short mein" / interrupting her long replies → a candidate
   lesson; promoted to active only after it's seen twice at ≥0.72 confidence (Leon's gate).
2. Lesson scoring: lessons applied in a turn score helpful if the next turn isn't a correction,
   harmful if it is (ACE/ExpeL votes). Nightly: merge near-duplicates, retire harmful ones.
3. Decision feedback: "nahi / galat / wrong" right after a fast-path action → undo it, ask what he
   meant, and learn his answer as a new exemplar (intent classifier improves without training).
"""
from __future__ import annotations

import json
import re

from .. import embed
from ..db import one, q

SHORTER_RX = re.compile(r"\b(too long|so long|shorter|short mein|chhota|chota|kam bolo|tl;?dr|bas bas|itna lamba|"
                        r"lecture mat|seedha bolo|to the point)\b", re.I)
UNDO_RX = re.compile(r"^\s*(nahi|nahin|no|nope|galat|wrong|that'?s wrong|not that|maine ye nahi|i didn'?t mean|"
                     r"cancel that|undo|wapas lo)\b", re.I)
LABEL_RX = {"todo": r"\b(todo|task|kaam|list)\b", "time": r"\b(alarm|reminder|timer|yaad)\b",
            "chat": r"\b(chat|baat|just talking|kuch nahi|nothing)\b", "memory": r"\b(remember|memory|yaad hai)\b",
            "tool": r"\b(calendar|mail|music|search|file)\b"}
BREVITY = ("Keep replies short — 1–2 sentences unless he asks for detail", "dont_long")


# ---------------- 1. inferred lessons ----------------
def infer_from_turn(text: str, prev_reply: str | None, interrupted: bool = False) -> str | None:
    """Returns an acknowledgement if a lesson was promoted, else None (candidates stay silent)."""
    long_prev = prev_reply is not None and len(prev_reply.split()) > 35
    if not (SHORTER_RX.search(text) or (interrupted and long_prev)):
        return None
    guidance, key = BREVITY
    row = one("SELECT id, seen_count, confidence, status FROM lessons WHERE situation=%s AND status<>'retired'",
              (f"inferred:{key}",))
    if row is None:
        vec = embed.embed_docs([f"Any situation. {guidance}"])[0]
        q("""INSERT INTO lessons(situation, guidance, polarity, source, status, confidence, situation_embedding)
             VALUES (%s,%s,'do','inferred','candidate',0.6,%s)""", (f"inferred:{key}", guidance, vec))
        return None
    if row["status"] == "active":
        return None
    seen, conf = row["seen_count"] + 1, min(0.95, row["confidence"] + 0.15)
    promote = seen >= 2 and conf >= 0.72
    q("UPDATE lessons SET seen_count=%s, confidence=%s, status=%s WHERE id=%s",
      (seen, conf, "active" if promote else "candidate", row["id"]))
    if promote:
        from .lessons import render_md
        render_md()
        return "Got it — from now on I'll keep it short. 👍"
    return None


# ---------------- 2. lesson scoring + nightly curation ----------------
def score_lessons(lesson_ids: list[int], was_corrected: bool) -> None:
    if not lesson_ids:
        return
    col = "harmful_count" if was_corrected else "helpful_count"
    q(f"UPDATE lessons SET {col} = {col} + 1 WHERE id = ANY(%s)", (lesson_ids,))


def curate() -> dict:
    """Night job: ACE-style per-item ops — RETIRE harmful, MERGE near-duplicates. Never deletes."""
    stats = {"retired": 0, "merged": 0}
    for r in q("""UPDATE lessons SET status='retired' WHERE status='active' AND harmful_count > helpful_count + 2
                  RETURNING id"""):
        stats["retired"] += 1
    rows = q("""SELECT a.id AS keep, b.id AS drop FROM lessons a JOIN lessons b ON a.id < b.id
                WHERE a.status='active' AND b.status='active' AND a.polarity=b.polarity
                  AND 1 - (a.situation_embedding <=> b.situation_embedding) >= 0.92""")
    dropped = set()
    for r in rows:
        if r["drop"] in dropped or r["keep"] in dropped:
            continue
        q("""UPDATE lessons k SET seen_count = k.seen_count + d.seen_count,
                    helpful_count = k.helpful_count + d.helpful_count, harmful_count = k.harmful_count + d.harmful_count,
                    source_episode_ids = k.source_episode_ids || d.source_episode_ids,
                    confidence = GREATEST(k.confidence, d.confidence)
             FROM lessons d WHERE k.id=%s AND d.id=%s""", (r["keep"], r["drop"]))
        q("UPDATE lessons SET status='retired', supersedes=NULL WHERE id=%s", (r["drop"],))
        dropped.add(r["drop"])
        stats["merged"] += 1
    return stats


# ---------------- 3. decision feedback ----------------
class Clarify:
    """After 'nahi/galat' on a fast-path action: undo it, ask what he meant, learn the answer."""

    def __init__(self, original_text: str, undo_note: str):
        self.original = original_text
        self.undo_note = undo_note

    def question(self) -> str:
        return f"{self.undo_note} What did you mean — a todo, an alarm/reminder, or were you just talking?"

    def answer(self, text: str) -> str:
        from .. import intent
        for label, rx in LABEL_RX.items():
            if re.search(rx, text, re.I):
                intent.learn("domain", label, self.original)
                return f"Samajh gayi — next time “{self.original[:40]}” means {label}. Say it again and I'll do it right."
        return "Okay, noted."


def undo_last(action: dict | None) -> str:
    """action = {'type': 'task'|'intent', 'id': ...} recorded by the engine for the last fast-path write."""
    if not action:
        return "Okay."
    if action["type"] == "task":
        q("UPDATE tasks SET status='cancelled' WHERE id=%s", (action["id"],))
        return "Removed that task."
    if action["type"] == "intent":
        row = one("UPDATE intents SET state='cancelled' WHERE id=%s RETURNING ek_identifier", (action["id"],))
        if row and row.get("ek_identifier"):
            from ..connectors import eventkit
            eventkit.remove_reminder(row["ek_identifier"])
        return "Cancelled that."
    return "Okay."


def mark_outcome(turn_id: int | None, outcome: str, corrected_to: str | None = None) -> None:
    if turn_id:
        q("UPDATE decisions SET outcome=%s, corrected_to=%s WHERE turn_id=%s AND outcome IS NULL",
          (outcome, corrected_to, turn_id))


# ---------------- segments (night job, no LLM) ----------------
def build_segments(gap_min: int = 30, drift: float = 0.25) -> int:
    """Group each session's episodes into topic segments: split on time gaps or embedding drift."""
    import numpy as np
    last = one("SELECT coalesce(max(last_ep), 0) m FROM segments")["m"]
    rows = q("""SELECT id, session_id, occurred_at, embedding, emotion FROM episodes
                WHERE id > %s AND embedding IS NOT NULL ORDER BY session_id, id""", (last,))
    made, cur = 0, []

    def flush():
        nonlocal made
        if len(cur) < 2:
            return
        vecs = np.stack([r["embedding"].to_numpy().astype(np.float32) for r in cur])
        mean = vecs.mean(axis=0)
        moods = [((r["emotion"] or {}).get("label")) for r in cur if r["emotion"]]
        mood = max(set(moods), key=moods.count) if moods else None
        from pgvector import HalfVector
        q("""INSERT INTO segments(session_id, first_ep, last_ep, started_at, ended_at, n_episodes, mood, embedding)
             VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
          (cur[0]["session_id"], cur[0]["id"], cur[-1]["id"], cur[0]["occurred_at"], cur[-1]["occurred_at"],
           len(cur), mood, HalfVector(mean / (np.linalg.norm(mean) + 1e-9))))
        made += 1

    for r in rows:
        if cur:
            prev = cur[-1]
            gap = (r["occurred_at"] - prev["occurred_at"]).total_seconds() / 60
            a = prev["embedding"].to_numpy().astype("float32")
            b = r["embedding"].to_numpy().astype("float32")
            sim = float(a @ b / ((np.linalg.norm(a) * np.linalg.norm(b)) + 1e-9))
            if r["session_id"] != prev["session_id"] or gap > gap_min or sim < drift:
                flush()
                cur = []
        cur.append(r)
    flush()
    return made


# ---------------- reflections (night job, cloud LLM when available) ----------------
def reflect(max_segments: int = 30) -> dict:
    from .. import router
    segs = q("""SELECT s.id, s.started_at, s.mood, string_agg(e.text, ' / ' ORDER BY e.id) AS txt
                FROM segments s JOIN episodes e ON e.id BETWEEN s.first_ep AND s.last_ep
                WHERE e.speaker='user' AND e.privacy <= 1 AND s.started_at > now() - interval '7 days'
                GROUP BY s.id ORDER BY s.id DESC LIMIT %s""", (max_segments,))
    if len(segs) < 3:
        return {"skipped": "not enough recent conversation"}
    body = "\n".join(f"[S{s['id']} · {s['started_at']:%a %d %b %H:%M} · mood {s['mood']}] {s['txt'][:400]}" for s in segs)
    try:
        r = router.complete([{"role": "user", "content":
                              "These are snippets of Tejmul's conversations with his assistant this week. Write up to 3 "
                              "short, kind, useful insights about his patterns (energy, stress triggers, what helps). "
                              "Only what the snippets support. Return JSON: {\"insights\":[{\"text\":\"\",\"evidence\":[segment ids]}]}"
                              "\n\n" + body}], route="background_smart", privacy=1, max_tokens=600, json_mode=True)
    except router.NoProvider as e:
        return {"skipped": f"no cloud LLM ({e})"}
    data = json.loads(r["text"][r["text"].find("{"):r["text"].rfind("}") + 1])
    n = 0
    for ins in data.get("insights", [])[:3]:
        vec = embed.embed_docs([ins["text"]])[0]
        q("INSERT INTO reflections(text, evidence, embedding) VALUES (%s,%s,%s)",
          (ins["text"], [int(x) for x in ins.get("evidence", []) if str(x).isdigit()], vec))
        n += 1
    return {"added": n}
