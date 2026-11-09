"""Owner profile — Stiti works for whoever installs her (open source), not a hard-coded person.

Name, what to call them and pronouns come from the "Key Things to Know" intro and live in the brain
(owner_profile table, so they're backed up with everything else). Until the intro, Stiti says "you"
and uses they/them.
"""
from __future__ import annotations

from functools import lru_cache

from .db import one, q

PRONOUNS = {
    "he": {"subj": "he", "obj": "him", "poss": "his", "be": "is"},
    "she": {"subj": "she", "obj": "her", "poss": "her", "be": "is"},
    "they": {"subj": "they", "obj": "them", "poss": "their", "be": "are"},
}


@lru_cache(maxsize=1)
def _all() -> dict[str, str]:
    try:
        return {r["key"]: r["value"] for r in q("SELECT key, value FROM owner_profile")}
    except Exception:
        return {}


def get(key: str, default: str | None = None) -> str | None:
    return _all().get(key, default)


def set(key: str, value: str, source: str = "intake") -> None:  # noqa: A001
    q("""INSERT INTO owner_profile(key, value, source) VALUES (%s,%s,%s)
         ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value, source=EXCLUDED.source, updated_at=now()""",
      (key, value.strip(), source))
    _all.cache_clear()


def name() -> str:
    """Their real name for facts/graph ("Priya is <name>'s sister"); 'the owner' before the intro."""
    return get("name") or "the owner"


def call() -> str:
    """What Stiti calls them out loud."""
    return get("call_me") or get("name") or "you"


def p(form: str = "subj") -> str:
    return PRONOUNS.get(get("pronouns", "they") or "they", PRONOUNS["they"])[form]


def known() -> bool:
    return bool(one("SELECT 1 FROM owner_profile WHERE key='name'") if _table_ok() else False)


def _table_ok() -> bool:
    try:
        q("SELECT 1 FROM owner_profile LIMIT 1")
        return True
    except Exception:
        return False


def self_aliases() -> list[str]:
    al = ["me", "i", "main", "mujhe", "myself"]
    for k in ("name", "call_me"):
        v = get(k)
        if v:
            al.append(v.lower())
    return al
