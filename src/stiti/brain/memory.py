"""Episodic memory: write every utterance verbatim (never deleted), recall with hybrid search.

recall() SQL lives in db/schema.sql: vector top-50 + full-text top-50 -> RRF(k=60)
x recency (30-day half-life, 0.5 floor) x importance x strength.
"""
from __future__ import annotations

import json
import re
from datetime import datetime

from pgvector import HalfVector

from .. import embed
from ..db import conn, one, q

# English + Hinglish function words dropped from the lexical leg
STOP = set("""
a an the is am are was were be been being i me my mine you your yours he she it we they them
his her its our their this that these those of to in on at for from with by about as into
and or but if so than then do does did done have has had what which who whom when where why how
can could will would shall should may might must not no yes ok okay please tell show give any
some all just also very too more most much many there here up down out over again
hai hain ho hoon hu tha thi the kya kaun kab kahan kaise kyu kyun ka ki ke ko se me mein mai main
mujhe mera meri mere tum tera teri tere aap apna apni apne woh wo yeh ye aur ya bhi to toh na nahi
nahin haan ha ji acha accha bas wala wali wale raha rahi rahe kar karo karna kiya diya liya hua
now currently recently still ever already abhi ab aajkal filhaal bhi abhi tak
""".split())

_WORD = re.compile(r"[a-z0-9ऀ-ॿ]+")


def start_session(channel: str = "text") -> int:
    return one("INSERT INTO sessions(channel) VALUES (%s) RETURNING id", (channel,))["id"]


def add_episode(session_id: int | None, speaker: str, text: str, *, origin: str = "owner",
                privacy: int = 1, importance: int = 3, emotion: dict | None = None,
                vec: HalfVector | None = None) -> int:
    if vec is None:
        vec = embed.embed_docs([text])[0]
    row = one(
        """INSERT INTO episodes(session_id, speaker, origin, text, privacy, importance, emotion,
                                embedding, embed_model)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
        (session_id, speaker, origin, text, privacy, max(1, min(10, importance)),
         json.dumps(emotion) if emotion else None, vec, embed.EMBED_MODEL),
    )
    return row["id"]


def tsquery_text(text: str) -> str:
    words = [w for w in _WORD.findall(text.lower()) if w not in STOP and len(w) > 1]
    return " | ".join(dict.fromkeys(words))  # OR-joined, de-duplicated, order kept


def recall(text: str, qvec: HalfVector, *, t_from: datetime | None = None,
           t_to: datetime | None = None, max_privacy: int = 1, k: int = 12) -> list[dict]:
    with conn().cursor() as cur:
        cur.execute("SET hnsw.iterative_scan = relaxed_order")
    return q(
        """SELECT * FROM recall(to_tsquery('simple', %s), %s, %s, %s, %s::smallint, %s)""",
        (tsquery_text(text), qvec, t_from, t_to, max_privacy, k),
    )


def seed_entities(text: str, episode_ids: list[int]) -> list[int]:
    """Entities named in the text (trigram >= 0.5 on name/aliases) + mentioned by top episodes."""
    rows = q(
        """SELECT DISTINCT id FROM entities e
           WHERE merged_into IS NULL AND (
                 word_similarity(lower(e.name), lower(%(t)s)) >= 0.5
              OR EXISTS (SELECT 1 FROM unnest(e.aliases) a WHERE word_similarity(lower(a), lower(%(t)s)) >= 0.5))
           UNION
           SELECT entity_id FROM episode_mentions WHERE episode_id = ANY(%(ids)s)""",
        {"t": text, "ids": episode_ids[:5]},
    )
    return [r["id"] for r in rows]


def current_facts(seed_ids: list[int], max_privacy: int = 1) -> list[dict]:
    if not seed_ids:
        return []
    return q("SELECT * FROM current_facts(%s, 2, %s::smallint)", (seed_ids, max_privacy))


def recent_turns(session_id: int, n: int = 6) -> list[dict]:
    rows = q(
        """SELECT speaker, text, occurred_at FROM episodes
           WHERE session_id = %s ORDER BY id DESC LIMIT %s""", (session_id, n))
    return list(reversed(rows))


TOLD_WINDOW_MIN = 90      # "this conversation" for "what did I tell you?"
TOLD_CHARS = 3200         # ≈ 800 tokens of his own words; the newest win when there is more


def told_this_conversation(session_id: int, *, exclude: int | None = None, max_privacy: int = 1) -> list[str]:
    """What HE said in this conversation, oldest first: statements only (no questions / commands / "ok"), cut-off
    half sentences folded into the full one. For "what did I tell you till now?" (D48) — the 10-line RECENT window
    gave him back only the ending."""
    from . import norepeat
    rows = q("""SELECT id, speaker, text FROM episodes
                WHERE session_id = %s AND speaker = 'user' AND privacy <= %s
                  AND occurred_at > now() - make_interval(mins => %s) ORDER BY id""",
             (session_id, max_privacy, TOLD_WINDOW_MIN))
    rows = norepeat.collapse_fragments([r for r in rows if r["id"] != exclude])
    out = [" ".join(r["text"].split()) for r in rows
           if len(r["text"].split()) >= 4 and not norepeat.is_ask(r["text"]) and not _command_like(r["text"])]
    while out and sum(len(x) for x in out) > TOLD_CHARS:
        out.pop(0)
    return out


def _command_like(text: str) -> bool:
    import re
    return bool(re.match(r"^\W*(?:(?:hey|hi|ok(?:ay)?|so|please|stiti)\W+)*(?:remind me|set (?:an? )?(?:alarm|timer|reminder)|add\b|"
                         r"talk in|speak in|open\b|play\b|stop\b|teach me|search\b|find\b|read\b|bye\b|good ?night)", text, re.I))


def touch(episode_ids: list[int]) -> None:
    """After the reply (never on the hot path): access stats + MemoryBank-style strength bump."""
    if episode_ids:
        q("""UPDATE episodes SET access_count = access_count + 1, last_accessed_at = now(),
                    strength = LEAST(strength + 0.1, 1.5) WHERE id = ANY(%s)""", (episode_ids,))
