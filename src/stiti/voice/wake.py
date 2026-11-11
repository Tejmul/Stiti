"""Wake & sleep phrases (Tejmul's spec): "Stiti", "Hey Stiti", "Wake up baby girl".

ASR keyword spotting: whisper-base (biased with a wake prompt) runs only on VAD speech segments
while asleep; fuzzy match tolerates mishearings ("Stuti", "Steeti", "Sti ti").
Zero training, any phrase can be added. A dedicated ~7 MB wake model can replace it later.
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher

NAME_VARIANTS = ["stiti", "stithi", "stuti", "steeti", "stety", "sthiti", "stiti's", "stitty", "stii"]
WAKE_PHRASES = ["wake up baby girl", "wake up baby", "hey stiti", "hi stiti", "hello stiti", "ok stiti", "suno stiti",
                "uth jao stiti", "stiti uth jao"]
SLEEP_RX = re.compile(r"\b(so jao|soja|go to sleep|sleep now|bas itna hi|bye stiti|good ?night stiti|chup ho jao)\b", re.I)
# Tejmul's stop words: the WHOLE utterance is just one of these (optionally + "Stiti") -> stop + sleep.
# "okay, set an alarm…" is a command, not a stop.
STOP_ONLY = re.compile(
    r"^(shut up|chup|chup karo|chup ho jao|okay|ok|ok bye|okay bye|chalo|chalo bye|chalo theek hai|bye|bye bye|"
    r"bas|bas karo|bas bas|stop|stop it|that'?s it|that'?s all|band karo|theek hai bas|good ?night|gn|so jao|"
    r"go to sleep|leave it|rehne do)( stiti)?$", re.I)
BACKCHANNEL = re.compile(r"^(haan|han|ha|hmm+|hm+|acha|achha|accha|right|yeah|yes|ji|haan ji|sahi|uh huh)$", re.I)


def _norm(t: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9\s']", " ", t.lower()).split())


def near_miss(transcript: str) -> bool:
    """Close to a wake phrase but not one — logged so a failing wake can be diagnosed; ambient talk is never logged."""
    words = _norm(transcript).split()
    if not words or len(words) > 8:
        return False
    if "wake" in words or any(SequenceMatcher(None, w.strip("'"), "stiti").ratio() >= 0.6 for w in words if len(w) >= 4):
        return True
    return bool(re.search(r"[\u0C00-\u0C7F\u0900-\u097F]", transcript)) and len(words) <= 4   # a short wake in another script


def _name_hit(word: str) -> bool:
    w = word.strip("'")
    if w in NAME_VARIANTS:
        return True
    return len(w) >= 4 and SequenceMatcher(None, w, "stiti").ratio() >= 0.8


def detect(transcript: str) -> tuple[bool, str]:
    """Returns (woke, remainder_after_wake_phrase) — remainder keeps the original text (numbers, a.m.)."""
    if is_stop(transcript):          # "bye Stiti" contains her name but is a goodbye, never a wake
        return False, ""
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


# stop words that are a goodbye (she says bye back) vs a hush (she goes quiet at once, no words)
HUSH = re.compile(r"^(shut up|chup|chup karo|chup ho jao|bas|bas karo|bas bas|stop|stop it|band karo|leave it|"
                  r"rehne do|okay|ok)( stiti)?$", re.I)


def is_goodbye(transcript: str) -> bool:
    """'bye', 'chalo bye', 'good night', 'so jao', 'bye Stiti'… — but not 'shut up' / 'stop'."""
    return is_sleep(transcript) and not HUSH.match(_norm(transcript)) and not re.search(r"chup", transcript, re.I)


def is_sleep(transcript: str) -> bool:
    return bool(SLEEP_RX.search(transcript)) or is_stop(transcript)


def is_stop(transcript: str) -> bool:
    return bool(STOP_ONLY.match(_norm(transcript)))


def is_backchannel(transcript: str) -> bool:
    return bool(BACKCHANNEL.match(_norm(transcript)))
