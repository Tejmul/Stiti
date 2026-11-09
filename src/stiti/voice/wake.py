"""Wake & sleep phrases (Tejmul's spec): "Stiti", "Hey Stiti", "Wake up baby girl".

ASR keyword spotting: whisper-base (biased with a wake prompt) runs only on VAD speech segments
while asleep; fuzzy match tolerates mishearings ("Stuti", "Steeti", "Sti ti").
Zero training, any phrase can be added. A dedicated ~7 MB wake model can replace it later.
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher

NAME_VARIANTS = ["stiti", "stithi", "stuti", "steeti", "stety", "sthiti", "stiti's", "stitty", "stii"]
WAKE_PHRASES = ["wake up baby girl", "wake up baby", "hey stiti", "hi stiti", "ok stiti", "suno stiti"]
SLEEP_RX = re.compile(r"\b(so jao|soja|go to sleep|sleep now|bas itna hi|bye stiti|good ?night stiti|chup ho jao)\b", re.I)


def _norm(t: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9\s']", " ", t.lower()).split())


def _name_hit(word: str) -> bool:
    w = word.strip("'")
    if w in NAME_VARIANTS:
        return True
    return len(w) >= 4 and SequenceMatcher(None, w, "stiti").ratio() >= 0.8


def detect(transcript: str) -> tuple[bool, str]:
    """Returns (woke, remainder_after_wake_phrase) — remainder keeps the original text (numbers, a.m.)."""
    orig = transcript.split()
    words = [_norm(w) for w in orig]
    keep = [i for i, w in enumerate(words) if w]
    orig = [orig[i] for i in keep]
    words = [words[i] for i in keep]
    if not words:
        return False, ""

    def rest(j: int) -> str:
        return " ".join(orig[j:]).lstrip(" ,.!?-")
    # multi-word phrases (fuzzy over sliding windows)
    for ph in WAKE_PHRASES:
        n = len(ph.split())
        for i in range(0, max(1, len(words) - n + 1)):
            window = " ".join(words[i:i + n])
            if SequenceMatcher(None, window, ph).ratio() >= 0.82:
                return True, rest(i + n)
    # the name alone, in the first 4 words ("Stiti, what are my todos")
    for i, w in enumerate(words[:4]):
        if _name_hit(w):
            return True, rest(i + 1)
    return False, ""


def is_sleep(transcript: str) -> bool:
    return bool(SLEEP_RX.search(transcript))
