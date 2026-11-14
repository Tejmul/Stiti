"""Writing facts with temporal validity — shared by the night job (sleep.py) and real-time capture (lifeupdate.py).

Facts are never deleted (D38):
  * end     — it WAS true and stopped being true ("I left Ledgerly"): `valid` gets an upper bound.
  * retract — it was NEVER true (a mishearing he corrects): `recorded` gets an upper bound (kept in history).
  * add     — insert, unless the same (or a near-identical) current fact exists → confirm it instead (merge).
A functional predicate (works_at, lives_in…) can have one current value: a new one ends the old one.
"""
from __future__ import annotations

import re
import threading
from datetime import datetime

from .. import embed
from ..config import CFG
from ..db import one, q

# one value at a time per subject
FUNCTIONAL = {"works_at", "interns_at", "lives_in", "studies_at", "relationship_status", "job_title", "role",
              "age", "year_of_study", "dating", "married_to", "current_project"}
# links that end when he says he left / quit / stopped the thing at the other end
TIES = FUNCTIONAL | {"member_of", "plays", "works_on", "volunteers_at", "leads", "founded", "is", "noted",
                     "attends", "part_of", "employed_by", "interned_at"}
_SYN = {"employed_at": "works_at", "employed_by": "works_at", "job_at": "works_at", "working_at": "works_at",
        "works_for": "works_at", "interning_at": "interns_at", "intern_at": "interns_at", "is_intern_at": "interns_at",
        "lives_at": "lives_in", "living_in": "lives_in", "stays_in": "lives_in", "based_in": "lives_in",
        "resides_in": "lives_in", "moved_to": "lives_in", "student_at": "studies_at", "studying_at": "studies_at",
        "is_student_at": "studies_at", "goes_to": "studies_at", "enjoys": "likes", "loves": "likes",
        "hates": "dislikes", "does_not_like": "dislikes", "plays_sport": "plays"}
PAST_RX = re.compile(r"\b(was|were|used to|former(ly)?|worked|interned|studied|lived|ex-|previously|had been|"
                     r"left|quit|ended|finished|completed|until|till)\b", re.I)


def norm_predicate(p: str) -> str:
    p = re.sub(r"[^a-z0-9_]+", "_", (p or "").strip().lower()).strip("_") or "noted"
    return _SYN.get(p, p)


def _ts(d) -> datetime | None:
    if d is None or isinstance(d, datetime):
        return d
    try:
        return datetime.fromisoformat(str(d)[:10]).replace(tzinfo=CFG.tz)
    except ValueError:
        return None


def end_fact(fid: int, at=None, by: int | None = None) -> bool:
    """It stopped being true at `at` (default now). Never produces an empty range (lower(valid) must stay readable)."""
    r = q("""UPDATE facts SET valid = tstzrange(lower(valid),
                    GREATEST(lower(valid) + interval '1 microsecond', COALESCE(%s, now()))),
                    invalidated_by = COALESCE(%s, invalidated_by)
             WHERE id=%s AND upper_inf(recorded) AND valid @> now() RETURNING id""", (_ts(at), by, fid))
    return bool(r)


def retract_fact(fid: int, by: int | None = None) -> bool:
    """It was never true (misheard / wrong): out of the current record, kept in history."""
    r = q("""UPDATE facts SET recorded = tstzrange(lower(recorded), now()), invalidated_by = COALESCE(%s, invalidated_by)
             WHERE id=%s AND upper_inf(recorded) RETURNING id""", (by, fid))
    return bool(r)


def _words(s: str) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9][a-z0-9'&-]{2,}", (s or "").lower())
            if w not in {"the", "and", "for", "with", "labs", "lab", "inc", "ltd", "llc", "pvt", "company"}]


def mentions_current(subj: int, needle: str, exclude: tuple[str, ...] = ()) -> list[dict]:
    """Current facts of `subj` whose text or object names `needle` (all its distinctive words)."""
    ws = _words(needle) or [needle.lower()]
    rows = q("""SELECT f.id, f.predicate, f.fact_text, coalesce(o.name, f.obj_literal, '') obj
                FROM facts f LEFT JOIN entities o ON o.id=f.obj_id
                WHERE f.subj_id=%s AND upper_inf(f.recorded) AND f.valid @> now()""", (subj,))
    out = []
    for r in rows:
        hay = f"{r['fact_text']} {r['obj']}".lower()
        if r["predicate"] in exclude:
            continue
        if all(re.search(rf"\b{re.escape(w)}", hay) for w in ws):
            out.append(r)
    return out


def close_ties(subj: int, needle: str, at=None, by: int | None = None, keep_past: bool = True) -> list[int]:
    """"I left X" / "I don't play X anymore": end his current facts about X (works_at X, "is an intern at X",
    "plays X"). Facts already in the past tense ("was an intern at X, Aug–Sep") stay true — they're history."""
    ended = []
    for r in mentions_current(subj, needle, exclude=("likes", "dislikes", "left", "stopped", "joined")):
        if r["id"] == by or re.match(r"(left|stopped|quit|no_longer|gave_up|resigned|finished)", r["predicate"]):
            continue                                    # the change itself is not a tie
        if r["predicate"] not in TIES and not r["predicate"].endswith(("_at", "_in", "_on", "_of")):
            continue
        if keep_past and PAST_RX.search(r["fact_text"]):
            continue
        if end_fact(r["id"], at, by):
            ended.append(r["id"])
    return ended


def add(subj: int, pred: str, fact_text: str, *, obj_id: int | None = None, obj_literal: str | None = None,
        functional: bool | None = None, start=None, confidence: float = 0.8, privacy: int = 1,
        ep_ids: list[int] | None = None, origin: str = "stiti") -> tuple[str, int]:
    """Insert a fact, or confirm the same/near-identical current one (merge). Returns (outcome, fact_id):
    outcome ∈ added | confirmed | superseded."""
    pred = norm_predicate(pred)
    ep_ids = ep_ids or []
    if obj_id is None and not obj_literal:
        obj_literal = fact_text.strip()                 # a free-text fact is its own object (facts_check)
    functional = (pred in FUNCTIONAL) if functional is None else (functional or pred in FUNCTIONAL)
    same = one("""SELECT id FROM facts WHERE subj_id=%s AND predicate=%s AND upper_inf(recorded) AND valid @> now()
                    AND obj_id IS NOT DISTINCT FROM %s AND lower(coalesce(obj_literal,'')) = lower(coalesce(%s,''))
                  LIMIT 1""", (subj, pred, obj_id, obj_literal))
    vec = embed.embed_docs([fact_text])[0]
    if not same:  # near-duplicate wording ("Riya is his sister" / "His sister is Riya")
        same = one("""SELECT id FROM facts WHERE subj_id=%s AND upper_inf(recorded) AND valid @> now()
                        AND embedding IS NOT NULL AND (predicate=%s OR predicate='noted' OR %s='noted')
                        AND 1 - (embedding <=> %s) >= 0.92
                      ORDER BY embedding <=> %s LIMIT 1""", (subj, pred, pred, vec, vec))
    if same:
        q("""UPDATE facts SET confidence = LEAST(GREATEST(confidence, %s) + 0.05, 0.99),
                    source_episode_ids = ARRAY(SELECT DISTINCT unnest(source_episode_ids || %s::bigint[]))
             WHERE id=%s""", (confidence, ep_ids, same["id"]))
        return "confirmed", same["id"]
    start, now = _ts(start), datetime.now(CFG.tz)
    start = min(start, now) if start else None          # a future plan starts counting today
    old = one("""SELECT id FROM facts WHERE subj_id=%s AND predicate=%s AND functional AND upper_inf(recorded)
                   AND valid @> now() LIMIT 1""", (subj, pred)) if functional else None
    if old:  # close the old interval first (the exclusion constraint allows one current value)
        end_fact(old["id"], start)
        up = one("SELECT upper(valid) u FROM facts WHERE id=%s", (old["id"],))["u"]
        start = max(start or now, up) if up else start   # never overlap the old one
    new = one("""INSERT INTO facts(subj_id, predicate, obj_id, obj_literal, fact_text, functional, valid, confidence,
                                   privacy, source_episode_ids, embedding, origin)
                 VALUES (%s,%s,%s,%s,%s,%s,tstzrange(COALESCE(%s, now()), NULL),%s,%s,%s,%s,%s)
                 RETURNING id""",
              (subj, pred, obj_id, obj_literal, fact_text.strip(), functional, start, float(confidence), privacy,
               ep_ids, vec, origin))["id"]
    if old:
        q("UPDATE facts SET invalidated_by=%s WHERE id=%s", (new, old["id"]))
    link(ep_ids, [subj, obj_id])
    return ("superseded" if old else "added"), new


def link(ep_ids: list[int], entity_ids: list[int | None]) -> int:
    n = 0
    for e in entity_ids:
        if e:
            for ep in ep_ids:
                n += len(q("INSERT INTO episode_mentions VALUES (%s,%s) ON CONFLICT DO NOTHING RETURNING 1", (ep, e)))
    return n


# ---------- after new facts: the standing profile + USER.md follow at once ----------
_last: threading.Thread | None = None
_lock = threading.Lock()              # one render at a time (USER.md + .sync.json are shared files)


def refresh(background: bool = True) -> None:
    """Rebuild briefing_cache 'standing_profile' and re-render USER.md / LESSONS.md (owner edits imported first)."""
    def job():
        try:
            from .mdsync import render_all, sync
            from .sleep import standing_profile
            with _lock:
                sync()
                standing_profile()
                render_all()
        except Exception as e:                 # never break a turn over a file render
            print(f"[facts] refresh failed: {e}", flush=True)
    global _last
    if not background:
        job()
        return
    _last = threading.Thread(target=job, daemon=True)
    _last.start()


def join(timeout: float = 10.0) -> None:
    """Tests: wait for the last background refresh / extraction."""
    if _last is not None:
        _last.join(timeout)
