"""Every question she asks him, and his answer — so an answered question is never asked again (no LLM).

Owner, 2026-11-20: "it asks same questions again and again — I have answered something and it forgets it and again
it asks the same questions again". The causes were all "state that didn't last" or "a different key for the same
question": the ask-me round put a skipped question back into the very next round, re-asked answers given days ago
("Still the same?"), the old intro restarted, the weather "tell me your city" hint lived in process memory (the app
restarts often), and nothing remembered the questions the LLM asked in chat.

One Postgres row per question key (`asked_questions`, migration 014):
  - `ask_ok(key)`      False once he answered it; False for SKIP_DAYS after he skipped it; optional repeat gap.
  - `asked / answered / skipped`   write the state (survives restarts — it's the brain, not the process).
  - LLM questions:   `note_reply(reply)` keeps every question about him that her reply ended with (key = a hash of
    the normalised words + an embedding), `note_answer(text)` marks the open one answered by his next real answer,
    `answered_like(question)` finds an answered one with the same meaning, `strip_repeats(reply)` drops a question
    he already answered from a reply, and `for_briefing(vec)` hands the LLM the nearest answered ones ("don't ask").
Everything degrades to "ask as before" if the table is missing (an un-migrated brain must never break a turn).
"""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta

from ..config import CFG
from ..db import one, q

SKIP_DAYS = 14                 # a question he skipped / declined isn't asked again for this long
LLM_OPEN_S = 10 * 60           # his next turn within this long can answer her question
SAME_MEANING = 0.90            # cosine between two questions (EmbeddingGemma docs) = the same question: paraphrases
                               # measured 0.95–0.97 ("siblings?" ~ "brothers or sisters?"), different ones 0.70–0.84
ANSWERED_DAYS = 180            # an LLM question he answered within this long is not asked again

_warned = [False]


def _safe(default):
    def wrap(fn):
        def inner(*a, **kw):
            try:
                return fn(*a, **kw)
            except Exception as e:                       # missing table (migration 014 not applied) / DB hiccup
                if not _warned[0]:
                    _warned[0] = True
                    print(f"[asked] {type(e).__name__}: {e} — questions are not remembered until "
                          "db/migrations/014_asked_questions.sql is applied", flush=True)
                return default
        inner.__name__ = fn.__name__
        inner.__doc__ = fn.__doc__
        return inner
    return wrap


def _now() -> datetime:
    return datetime.now(CFG.tz)


# ------------------------------------------------------------------------------------------------ keyed questions
@_safe(None)
def row(key: str) -> dict | None:
    return one("""SELECT qkey, question, asked_count, first_asked_at, last_asked_at, answered_at, answer, skipped_at
                  FROM asked_questions WHERE qkey=%s""", (key,))


@_safe(True)
def ask_ok(key: str, *, skip_days: float = SKIP_DAYS, repeat_days: float | None = None,
           now: datetime | None = None) -> bool:
    """May she ask this one now? Never once answered; not within skip_days of a skip; not within repeat_days of the
    last time she asked (None = no gap)."""
    r = row(key)
    if r is None:
        return True
    now = now or _now()
    if r["answered_at"] is not None:
        return False
    if r["skipped_at"] is not None and now - r["skipped_at"] < timedelta(days=skip_days):
        return False
    if repeat_days is not None and now - r["last_asked_at"] < timedelta(days=repeat_days):
        return False
    return True


@_safe(None)
def asked(key: str, question: str, source: str, *, vec=None, privacy: int = 1, now: datetime | None = None) -> None:
    now = now or _now()
    q("""INSERT INTO asked_questions(qkey, source, question, embedding, privacy, first_asked_at, last_asked_at)
         VALUES (%s,%s,%s,%s,%s,%s,%s)
         ON CONFLICT (qkey) DO UPDATE SET asked_count = asked_questions.asked_count + 1, last_asked_at = EXCLUDED.last_asked_at,
           question = EXCLUDED.question, embedding = COALESCE(EXCLUDED.embedding, asked_questions.embedding)""",
      (key, source, question[:400], vec, privacy, now, now))


@_safe(None)
def answered(key: str, answer: str | None = None, *, episode_id: int | None = None, question: str | None = None,
             source: str = "", private: bool = False, now: datetime | None = None) -> None:
    """He answered it (also for a question that was answered before this ledger existed: the row is created)."""
    now = now or _now()
    ans = None if private else (answer or "")[:400]
    q("""INSERT INTO asked_questions(qkey, source, question, answered_at, answer, answer_episode_id, privacy,
                                     first_asked_at, last_asked_at)
         VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
         ON CONFLICT (qkey) DO UPDATE SET answered_at = EXCLUDED.answered_at, answer = EXCLUDED.answer,
           answer_episode_id = EXCLUDED.answer_episode_id, skipped_at = NULL""",
      (key, source or key.split(":", 1)[0], (question or key)[:400], now, ans, episode_id, 2 if private else 1, now, now))


@_safe(None)
def skipped(key: str, *, question: str | None = None, source: str = "", now: datetime | None = None) -> None:
    now = now or _now()
    q("""INSERT INTO asked_questions(qkey, source, question, skipped_at, first_asked_at, last_asked_at)
         VALUES (%s,%s,%s,%s,%s,%s)
         ON CONFLICT (qkey) DO UPDATE SET skipped_at = EXCLUDED.skipped_at""",
      (key, source or key.split(":", 1)[0], (question or key)[:400], now, now, now))


@_safe(None)
def forget(key: str) -> None:
    """He wants to be asked again ("ask me that again")."""
    q("DELETE FROM asked_questions WHERE qkey=%s", (key,))


# ------------------------------------------------------------------------------------------------ the LLM's questions
_OFFER_RX = re.compile(r"^\W*(?:so\s+|and\s+|okay\s+|ok\s+)?(?:want|wanna|shall|should i|do you want|would you like|"
                       r"can i|may i|anything else|need (?:me|anything)|is there anything|how can i|what can i|"
                       r"ready|sound good|sounds good|right|okay|ok|got it|make sense|does that|is that|"
                       r"should we|shall we|want me)\b", re.I)
_ABOUT_HIM_RX = re.compile(r"\b(you|your|you're|youre|yours|yourself|tum|tumhara|tumhari|aap|aapka|aapki|tera|teri)\b",
                           re.I)
SKIP_RX = re.compile(r"^\W*(skip|pass|next|not now|later|baad mein|don'?t want to (say|talk|answer)|rather not|"
                     r"never ?mind|leave it|chhodo|chodo|rehne do)\b", re.I)
UNKNOWN_RX = re.compile(r"^\W*(i )?(don'?t know|dunno|idk|not sure|no idea|pata nahi|nahi pata|hmm+|umm+|uh+)\W*$", re.I)


def norm(question: str) -> str:
    t = re.sub(r"[^\w\s']", " ", question.lower())
    t = re.sub(r"\b(so|and|but|then|okay|ok|hey|tell me|by the way|btw|actually|just|really)\b", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def key_of(question: str) -> str:
    return "llm:" + hashlib.sha1(norm(question).encode()).hexdigest()[:16]


def questions_in(reply: str) -> list[str]:
    """The questions ABOUT HIM in her reply ("What are you studying these days?"), not offers ("Want more?")."""
    out = []
    for s in re.findall(r"[^.!?]*\?", reply or ""):
        s = s.strip(" —-–,\n").rstrip("?").strip()
        if len(s.split()) < 4 or _OFFER_RX.match(s) or not _ABOUT_HIM_RX.search(s):
            continue
        out.append(s)
    return out


def _vec(text: str):
    from .. import embed
    return embed.embed_docs([text])[0]


@_safe(None)
def answered_like(question: str, *, vec=None, threshold: float = SAME_MEANING, days: float = ANSWERED_DAYS,
                  now: datetime | None = None) -> dict | None:
    """An answered question with the same words, or the same meaning (embedding), answered within `days`."""
    now = now or _now()
    r = one("""SELECT qkey, question, answer, answered_at FROM asked_questions WHERE qkey=%s AND answered_at IS NOT NULL
               AND answered_at > %s""", (key_of(question), now - timedelta(days=days)))
    if r:
        return r
    vec = vec if vec is not None else _vec(question)
    r = one("""SELECT qkey, question, answer, answered_at, 1 - (embedding <=> %s) AS sim FROM asked_questions
               WHERE answered_at IS NOT NULL AND embedding IS NOT NULL AND answered_at > %s
               ORDER BY embedding <=> %s LIMIT 1""", (vec, now - timedelta(days=days), vec))
    return r if r and r["sim"] >= threshold else None


@_safe(0)
def note_reply(reply: str, *, privacy: int = 1, now: datetime | None = None) -> int:
    """Keep the questions about him her reply asked. Returns how many."""
    qs = questions_in(reply)
    for s in qs:
        asked(key_of(s), s, "llm", vec=_vec(s), privacy=privacy, now=now)
    return len(qs)


@_safe(None)
def open_question(now: datetime | None = None) -> dict | None:
    now = now or _now()
    return one("""SELECT qkey, question FROM asked_questions WHERE source='llm' AND answered_at IS NULL
                  AND last_asked_at > %s ORDER BY last_asked_at DESC LIMIT 1""", (now - timedelta(seconds=LLM_OPEN_S),))


@_safe(None)
def note_answer(text: str, *, episode_id: int | None = None, private: bool = False,
                now: datetime | None = None) -> str | None:
    """His turn right after her question: a real answer marks it answered, "skip / not now" skips it, a question
    back or "I don't know" leaves it open. Returns the key it settled, or None."""
    t = (text or "").strip()
    if not t:
        return None
    r = open_question(now)
    if r is None:
        return None
    if SKIP_RX.match(t):
        skipped(r["qkey"], now=now)
        return r["qkey"]
    if t.endswith("?") or UNKNOWN_RX.match(t):
        return None
    answered(r["qkey"], t, episode_id=episode_id, question=r["question"], source="llm", private=private, now=now)
    return r["qkey"]


def strip_repeats(reply: str, *, now: datetime | None = None) -> tuple[str, list[str]]:
    """Drop the questions in her reply that he already answered (same words or same meaning). The reply keeps
    everything else; a reply that was ONLY that question is left as it is (the caller decides)."""
    dropped: list[str] = []
    out = reply
    for s in questions_in(reply):
        if answered_like(s, now=now) is not None:
            dropped.append(s)
            out = out.replace(s + "?", "").replace(s, "")
    out = re.sub(r"\s{2,}", " ", out).strip(" —-–,")
    if dropped and len(out.split()) < 2:
        return reply, []
    return out, dropped


@_safe([])
def for_briefing(vec, *, k: int = 3, min_sim: float = 0.3, now: datetime | None = None) -> list[tuple[str, str]]:
    """The answered questions closest to this moment, with his answers (privacy 1 only) — so the LLM uses the answer
    instead of asking again."""
    now = now or _now()
    rows = q("""SELECT question, answer, 1 - (embedding <=> %s) AS sim FROM asked_questions
                WHERE answered_at IS NOT NULL AND embedding IS NOT NULL AND privacy <= 1 AND answer IS NOT NULL
                AND answered_at > %s ORDER BY embedding <=> %s LIMIT %s""",
             (vec, now - timedelta(days=ANSWERED_DAYS), vec, k))
    return [(r["question"], r["answer"]) for r in rows if r["sim"] >= min_sim]
