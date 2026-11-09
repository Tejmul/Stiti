"""Lessons: "in situation X, don't talk like Y" — an ACE-style itemized playbook.

Owner-explicit corrections become ACTIVE at once (conf 0.9). Repeats UPVOTE/MERGE instead of
duplicating. The night job curates (EDIT/RETIRE). LESSONS.md is a rendered, human-readable view.
"""
from __future__ import annotations

import re
from datetime import datetime

import numpy as np

from .. import embed
from ..config import CFG
from ..db import one, q

MOOD_WORDS = {
    "stressed": r"stress|tension|pressure|overwhelm|anxious|pareshan",
    "angry": r"gussa|angry|naraz|irritat|pissed|frustrat",
    "sad": r"\bsad\b|udaas|\blow\b|dukhi|upset|rona",
    "tired": r"tired|thak|sleepy|neend|exhaust",
    "happy": r"khush|happy|excited",
}
NEG = re.compile(r"\b(don'?t|do not|never|stop|mat|band karo|no more|avoid|nahi chahiye)\b", re.I)
HINGLISH = re.compile(r"\b(mat|karo|bolo|hai|hoon|yaar|jab|tab|kyun|mujhe|itna)\b", re.I)


def time_bucket(dt: datetime | None = None) -> str:
    h = (dt or datetime.now(CFG.tz)).hour
    return ("late_night" if h < 5 else "morning" if h < 12 else "afternoon" if h < 17
            else "evening" if h < 21 else "night")


def capture(text: str, *, mood: str | None, source_episode_ids: list[int]) -> tuple[int, str]:
    """Turn an owner correction into an active lesson. Returns (lesson_id, one-line acknowledgement)."""
    t = text.lower()
    trigger: dict = {}
    moods = [m for m, rx in MOOD_WORDS.items() if re.search(rx, t)]
    if moods and re.search(r"\b(when|jab|whenever|agar)\b", t):
        trigger["mood"] = moods
    if re.search(r"\b(raat|night|late)\b", t):
        trigger["time"] = "night" if "late" not in t else "late_night"
    elif re.search(r"\b(subah|morning)\b", t):
        trigger["time"] = "morning"
    polarity = "dont" if NEG.search(text) else "do"
    guidance = " ".join(text.strip().rstrip(".!").split()[:25])
    situation = (f"Tejmul is {'/'.join(trigger['mood'])}" if "mood" in trigger else "Any situation") + \
                (f", {trigger['time']}" if "time" in trigger else "") + f" (mood at the time: {mood or 'unknown'})"
    vec = embed.embed_docs([f"{situation}. {guidance}"])[0]

    # ACE delta: near-duplicate active lesson -> UPVOTE + merge evidence, don't add a second item
    dup = one("""SELECT id, 1 - (situation_embedding <=> %s) AS sim FROM lessons
                 WHERE status='active' ORDER BY situation_embedding <=> %s LIMIT 1""", (vec, vec))
    if dup and dup["sim"] >= 0.92:
        q("""UPDATE lessons SET seen_count = seen_count + 1, confidence = LEAST(confidence + 0.05, 0.99),
                    source_episode_ids = source_episode_ids || %s::bigint[] WHERE id = %s""",
          (source_episode_ids, dup["id"]))
        lid = dup["id"]
    else:
        lid = one("""INSERT INTO lessons(situation, trigger, guidance, polarity, source, status, confidence,
                                         situation_embedding, source_episode_ids)
                     VALUES (%s,%s,%s,%s,'owner_explicit','active',0.9,%s,%s) RETURNING id""",
                  (situation, __import__("json").dumps(trigger), guidance, polarity, vec, source_episode_ids))["id"]
    render_md()
    when = ""
    if "mood" in trigger:
        when = (f"jab tum {'/'.join(trigger['mood'])} ho, " if HINGLISH.search(text)
                else f"when you're {'/'.join(trigger['mood'])}, ")
    ack = (f"Samajh gaya — {when}dhyan rakhunga. (lesson L{lid})" if HINGLISH.search(text)
           else f"Got it — {when}I'll keep that in mind. (lesson L{lid})")
    return lid, ack


def match(qvec, *, mood: str | None, bucket: str, k: int = 5) -> list[dict]:
    """Active lessons whose trigger fits now (missing key = matches anything), nearest first."""
    rows = q("""SELECT id, guidance, polarity, situation, created_at FROM lessons
                WHERE status='active'
                  AND (NOT trigger ? 'mood' OR trigger->'mood' ? %(mood)s)
                  AND (NOT trigger ? 'time' OR trigger->>'time' = %(b)s)
                ORDER BY situation_embedding <=> %(v)s LIMIT %(k)s""",
             {"mood": mood or "", "b": bucket, "v": qvec, "k": k})
    return rows


def mark_applied(ids: list[int]) -> None:
    if ids:
        q("UPDATE lessons SET last_applied_at = now() WHERE id = ANY(%s)", (ids,))


def render_md() -> None:
    rows = q("""SELECT id, situation, guidance, polarity, confidence, seen_count, helpful_count, harmful_count
                FROM lessons WHERE status='active' ORDER BY id""")
    lines = ["# LESSONS — how Stiti should talk to Tejmul", "",
             "_Rendered from Postgres `lessons`. Edits here are imported by the night job (planned)._", ""]
    for r in rows:
        lines.append(f"- **L{r['id']}** [{'MUST NOT' if r['polarity'] == 'dont' else 'MUST'}] {r['guidance']}  "
                     f"\n  _when:_ {r['situation']} · conf {r['confidence']:.2f} · seen {r['seen_count']}")
    (CFG.home / "LESSONS.md").write_text("\n".join(lines) + "\n")


def _cos(a, b) -> float:
    a, b = np.asarray(a, dtype=np.float32), np.asarray(b, dtype=np.float32)
    return float(a @ b / (np.linalg.norm(a) * np.linalg.norm(b)))
