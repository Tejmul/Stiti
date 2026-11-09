"""Key things, captured from everyday talk — no LLM, English + Hinglish patterns.

"I love biryani" / "mujhe biryani bahut pasand hai" → likes · "I hate long calls" / "mujhe X pasand nahi" →
dislikes · "I'm a night owl" / "main subah wala banda hoon" → chronotype · "main introvert hoon" →
social energy · "I'm vegetarian" → diet · "I'm allergic to peanuts" → allergy (health → P2, never to cloud).
Each becomes a self-fact (deduplicated) or a tentative trait the owner can see and correct in USER.md.
"""
from __future__ import annotations

import re

from ..db import one, q

_X = r"(?P<x>[\w][\w '&\-]{1,40}?)"
LIKES = [
    re.compile(rf"\bi (?:really |absolutely |totally )?(?:love|like|enjoy|adore) {_X}(?:[.,!]|$| a lot| so much| very much)", re.I),
    re.compile(rf"\bmy (?:all[- ]time )?favou?rite (?:\w+ )?is {_X}(?:[.,!]|$)", re.I),
    re.compile(rf"\bmujhe {_X} (?:bahut |bohot |kaafi )?(?:pasand hai|achha lagta hai|achchha lagta hai|acha lagta hai)", re.I),
    re.compile(rf"\b{_X} (?:mera|meri|mere) favou?rite(?: \w+)? (?:hai|hain)", re.I),
]
DISLIKES = [
    re.compile(rf"\bi (?:really )?(?:hate|dislike|can'?t stand|don'?t like|do not like) {_X}(?:[.,!]|$)", re.I),
    re.compile(rf"\bmujhe {_X} (?:bilkul )?(?:pasand nahi|achha nahi lagta|acha nahi lagta|nahi pasand)", re.I),
    re.compile(rf"\b{_X} se (?:nafrat hai|chidh hai|irritation hoti hai)", re.I),
]
TRAITS = [
    (re.compile(r"\b(i'?m|i am) (a )?(night owl|night person|evening person)\b|\braat (wala|ko kaam)", re.I),
     "chronotype", 1.0, "evening person"),
    (re.compile(r"\b(i'?m|i am) (a )?(morning person|early riser)\b|\bsubah (jaldi uthta|wala banda)", re.I),
     "chronotype", 0.0, "morning person"),
    (re.compile(r"\b(i'?m|i am|main) (an? |ek )?introvert\b", re.I), "social_energy", 0.25, "introvert-leaning"),
    (re.compile(r"\b(i'?m|i am|main) (an? |ek )?extrovert\b", re.I), "social_energy", 0.8, "extrovert-leaning"),
]
DIET = re.compile(r"\b(i'?m|i am|main) (a )?(vegetarian|vegan|eggetarian|jain|non[- ]?veg(etarian)?)\b", re.I)
ALLERGY = re.compile(r"\b(i'?m|i am|mujhe) allergic (to|hai) (?P<x>[\w ]{2,30})", re.I)
STOP_X = {"it", "this", "that", "you", "him", "her", "them", "u", "kar", "karna", "to", "the"}


def _clean(x: str) -> str | None:
    x = re.sub(r"\b(very|so|really|bahut|bohot|a lot|much)\b", "", x, flags=re.I).strip(" .,!'\"")
    x = re.sub(r"\s+", " ", x)
    if not x or x.lower() in STOP_X or len(x) < 2 or len(x.split()) > 6:
        return None
    return x


def _self_fact(pred: str, obj: str, text: str, privacy: int = 1, ep: int | None = None) -> bool:
    from .. import profile
    from .sleep import resolve_entity
    me = resolve_entity(profile.name(), "self")
    if one("""SELECT 1 FROM facts WHERE subj_id=%s AND predicate=%s AND lower(obj_literal)=lower(%s)
              AND upper_inf(recorded) AND valid @> now()""", (me, pred, obj)):
        return False
    opposite = {"likes": "dislikes", "dislikes": "likes"}.get(pred)
    if opposite:  # "I used to hate X, now I love X" → close the opposite
        q("""UPDATE facts SET valid = tstzrange(lower(valid), now()) WHERE subj_id=%s AND predicate=%s
             AND lower(obj_literal)=lower(%s) AND upper_inf(recorded) AND valid @> now()""", (me, opposite, obj))
    q("""INSERT INTO facts(subj_id, predicate, obj_literal, fact_text, confidence, privacy, source_episode_ids, origin)
         VALUES (%s,%s,%s,%s,0.85,%s,%s,'conversation')""", (me, pred, obj, text, privacy, [ep] if ep else []))
    return True


def set_trait(key: str, value: float | None, label: str, evidence: str, confidence: float = 0.6,
              source: str = "conversation") -> None:
    q("""INSERT INTO traits(key, value, label, confidence, evidence, source) VALUES (%s,%s,%s,%s,%s,%s)
         ON CONFLICT (key) DO UPDATE SET
           value = CASE WHEN traits.source='owner_edit' THEN traits.value ELSE EXCLUDED.value END,
           label = CASE WHEN traits.source='owner_edit' THEN traits.label ELSE EXCLUDED.label END,
           confidence = CASE WHEN traits.source='owner_edit' THEN traits.confidence
                             ELSE LEAST(0.95, GREATEST(traits.confidence, EXCLUDED.confidence)) END,
           evidence = left(EXCLUDED.evidence || ' | ' || coalesce(traits.evidence, ''), 400),
           source = CASE WHEN traits.source='owner_edit' THEN traits.source ELSE EXCLUDED.source END,
           updated_at = now()""", (key, value, label, confidence, evidence[:200], source))


def capture(text: str, episode_id: int | None = None) -> list[str]:
    """Returns short notes of what was learned (empty if nothing)."""
    from .. import profile
    if text.rstrip().endswith("?"):
        return []
    notes: list[str] = []
    who = profile.name()
    for rx in LIKES:
        for m in rx.finditer(text):
            x = _clean(m.group("x"))
            if x and _self_fact("likes", x, f"{who} likes {x}", ep=episode_id):
                notes.append(f"you like {x}")
    for rx in DISLIKES:
        for m in rx.finditer(text):
            x = _clean(m.group("x"))
            if x and _self_fact("dislikes", x, f"{who} dislikes {x}", ep=episode_id):
                notes.append(f"you don't like {x}")
    for rx, key, val, label in TRAITS:
        if rx.search(text):
            set_trait(key, val, label, text, confidence=0.75)
            word = label.replace("-leaning", "")
            notes.append(f"you're {'an' if word[0] in 'aeiou' else 'a'} {word}")
    m = DIET.search(text)
    if m and _self_fact("diet", m.group(3).lower(), f"{who} is {m.group(3).lower()}", ep=episode_id):
        notes.append(f"you're {m.group(3).lower()}")
    m = ALLERGY.search(text)
    if m:
        x = _clean(m.group("x"))
        if x and _self_fact("allergic_to", x, f"{who} is allergic to {x}", privacy=2, ep=episode_id):
            notes.append(f"you're allergic to {x} (kept private)")
    return notes
