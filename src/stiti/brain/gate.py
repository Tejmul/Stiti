"""Memory-recall gating — which recalled memories may reach the LLM this turn (D25, research §3b).

Recall still finds everything (sim ≥ 0.25); this gate decides what she may USE. Without it every loosely similar old
episode went into [MEMORY] and the LLM "used" it — "Kya interview mein aisa hi kuch hua tha?" out of nowhere.

  G1 relevance  only sim ≥ 0.45, or an episode that names a person/project he named now or in the last 2 turns
  G2 he asked   ("remember…", "last time", domain=memory) → free use of everything recall found
  G3 no quizzes the entities of recalled memories he didn't mention go to the lint: a question about them is dropped
  G4 budget     ≤ 1 unprompted callback per hour; the same episode is never volunteered twice in 7 days
  G5 valence    never a painful memory he didn't raise; when he's low, only resource memories (wins, support)
  G6 privacy    P2 never volunteered (recall's max_privacy already enforces it for non-P2 turns)
  G8 friend     nothing minor (importance ≤ 3) older than 30 days unless he named it

No model, two small SQL queries (~1–2 ms). `episodes.last_volunteered_at` comes from migration 008; without it the
gate still works (G4's 7-day rule is then skipped).
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta

from ..db import q

REL_FLOOR = 0.45
PAINFUL_RX = re.compile(r"\b(reject\w*|didn'?t get|not (selected|shortlisted)|fight|fought|breakup|broke up|died|death|"
                        r"passed away|hospital|sick|ill\b|failed|fail ho|fired|laid off|lost|cried|crying|ro (raha|rahi)|"
                        r"went (badly|bad)|terrible|worst|ladai|jhagda)\b", re.I)
WIN_RX = re.compile(r"\b(cracked|cleared|selected|shortlisted|got (the |an |my )?(offer|job|internship)|passed|nailed|aced|"
                    r"won|shipped|built|launched|finished|completed|proud|placed|promotion)\b", re.I)
_LOW = ("sad", "stressed", "tired", "angry")
_warned = False


def entities_in(texts: list[str]) -> dict[int, str]:
    """People/projects/places named in these texts (trigram match, like engine._names_his_person). {id: name}"""
    blob = " \n ".join(t for t in texts if t)[:2000]
    if not blob.strip():
        return {}
    rows = q("""SELECT id, name FROM entities WHERE merged_into IS NULL AND kind <> 'self' AND length(name) >= 3 AND (
                  word_similarity(lower(name), lower(%(t)s)) >= 0.6
                  OR EXISTS (SELECT 1 FROM unnest(aliases) a WHERE length(a) >= 3 AND word_similarity(lower(a), lower(%(t)s)) >= 0.6))""",
             {"t": blob})
    return {r["id"]: r["name"] for r in rows}


def _meta(ids: list[int]) -> dict[int, dict]:
    global _warned
    if not ids:
        return {}
    try:
        rows = q("""SELECT e.id, e.last_volunteered_at, e.emotion->>'label' AS mood,
                           coalesce(array_agg(m.entity_id) FILTER (WHERE m.entity_id IS NOT NULL), '{}') AS ents,
                           coalesce(array_agg(n.name) FILTER (WHERE n.name IS NOT NULL), '{}') AS names
                    FROM episodes e LEFT JOIN episode_mentions m ON m.episode_id = e.id
                    LEFT JOIN entities n ON n.id = m.entity_id AND n.kind <> 'self'
                    WHERE e.id = ANY(%s) GROUP BY e.id""", (ids,))
    except Exception as e:                       # migration 008 not applied yet: same query without the column
        if not _warned:
            print(f"[gate] {type(e).__name__}: apply db/migrations/008_persona.sql")
            _warned = True
        rows = q("""SELECT e.id, NULL::timestamptz AS last_volunteered_at, e.emotion->>'label' AS mood,
                           coalesce(array_agg(m.entity_id) FILTER (WHERE m.entity_id IS NOT NULL), '{}') AS ents,
                           coalesce(array_agg(n.name) FILTER (WHERE n.name IS NOT NULL), '{}') AS names
                    FROM episodes e LEFT JOIN episode_mentions m ON m.episode_id = e.id
                    LEFT JOIN entities n ON n.id = m.entity_id AND n.kind <> 'self'
                    WHERE e.id = ANY(%s) GROUP BY e.id""", (ids,))
    return {r["id"]: r for r in rows}


def recent_callback(within: timedelta = timedelta(hours=1)) -> bool:
    try:
        r = q("SELECT 1 AS x FROM episodes WHERE last_volunteered_at > now() - %s LIMIT 1", (within,))
        return bool(r)
    except Exception:
        return False


def filter_memories(mems: list[dict], *, text: str, recent_texts: list[str], asked: bool, mood: str | None,
                    now: datetime, cap: int = 3) -> tuple[list[dict], list[str], list[int]]:
    """Returns (memories the LLM may see, entity names it must not ask about, ids that count as volunteered)."""
    if asked:                                                    # G2: he asked about the past → free use
        return mems, [], []
    if not mems:
        return [], [], []
    named_now = entities_in([text])
    named = {**entities_in(recent_texts[-2:]), **named_now}
    meta = _meta([m["episode_id"] for m in mems])
    budget_used = recent_callback()
    low = mood in _LOW
    kept, avoid = [], set()
    for m in mems:
        info = meta.get(m["episode_id"], {})
        ents = set(info.get("ents") or [])
        shared = bool(ents & set(named))
        if not (m["sim"] >= REL_FLOOR or shared):                                   # G1
            continue
        age = now - m["occurred_at"]
        if age > timedelta(days=30) and m.get("importance", 3) <= 3 and not shared:  # G8
            continue
        painful = (info.get("mood") in ("sad", "angry", "stressed")) or bool(PAINFUL_RX.search(m["text"]))
        raised = shared and bool(ents & set(named_now))
        if painful and not raised:                                                  # G5: pain only if he raised it
            continue
        if low and not raised and not (WIN_RX.search(m["text"]) or info.get("mood") == "happy"):
            continue                                                                # G5: only resource memories
        lv = info.get("last_volunteered_at")
        if lv is not None and now - lv < timedelta(days=7) and not raised:          # G4: not twice in 7 days
            continue
        if budget_used and not raised:                                              # G4: ≤ 1 per hour
            continue
        kept.append(m)
        avoid.update(n for n in (info.get("names") or []) if n and not re.search(rf"\b{re.escape(n)}\b", text, re.I))
        if len(kept) >= cap:
            break
    return kept, sorted(avoid), [m["episode_id"] for m in kept]


_STOPW = set("that this with have from your about what when they them were been just like know really then there "
             "going doing want also more some will would could should".split())


def mark_volunteered(reply: str, mems: list[dict]) -> list[int]:
    """After the reply: the memories she actually brought up (≥ 2 of their content words in her reply) start the
    G4 clocks. Unused memories stay free."""
    words = set(re.findall(r"[a-z]{4,}", (reply or "").lower())) - _STOPW
    used = [m["episode_id"] for m in mems
            if len((set(re.findall(r"[a-z]{4,}", m["text"].lower())) - _STOPW) & words) >= 2]
    if used:
        try:
            q("UPDATE episodes SET last_volunteered_at = now() WHERE id = ANY(%s)", (used,))
        except Exception:
            pass
    return used


def wins(max_privacy: int = 1, k: int = 3) -> list[str]:
    """His real wins (facts + what he said), for a LISTEN reframe — strength-based recall (SDT competence)."""
    rows = q("""SELECT text FROM episodes WHERE speaker='user' AND privacy <= %s AND importance > 1
                  AND text ~* %s ORDER BY occurred_at DESC LIMIT %s""",
             (max_privacy, r"\m(cracked|cleared|selected|shipped|built|launched|finished|completed|got (the |an )?offer|won|aced|nailed)\M", k))
    return [r["text"][:160] for r in rows]
