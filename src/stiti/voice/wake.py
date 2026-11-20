"""Wake & sleep phrases: "Stiti", "Hey Stiti", "Hi Stiti" — plus the owner's own phrases.

Defaults are the same for every user. Extra, personal wake phrases live in the local profile (owner_profile key
`wake_phrases`, a JSON list), set with `stiti wake add "<phrase>"` — never in the code.

ASR keyword spotting: whisper-base (biased with a wake prompt) runs only on VAD speech segments
while asleep; fuzzy match tolerates mishearings ("Stuti", "Steeti", "Sti ti").
Zero training, any phrase can be added. A dedicated ~7 MB wake model can replace it later.
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher

NAME_VARIANTS = ["stiti", "stithi", "stuti", "steeti", "stety", "sthiti", "stiti's", "stitty", "stii"]
DEFAULT_PHRASES = ["hey stiti", "hi stiti", "hello stiti", "ok stiti", "suno stiti", "uth jao stiti", "stiti uth jao"]
WAKE_PHRASES = DEFAULT_PHRASES          # kept for old imports; detect() uses phrases() (defaults + the owner's own)
PROFILE_KEY = "wake_phrases"
SLEEP_RX = re.compile(r"\b(so jao|soja|go to sleep|sleep now|bas itna hi|bye stiti|good ?night stiti|chup ho jao)\b", re.I)
# the owner's stop words: the WHOLE utterance is just one of these (optionally + "Stiti") -> stop + sleep.
# "okay, set an alarm…" is a command, not a stop.
STOP_ONLY = re.compile(
    r"^(shut up|chup|chup karo|chup ho jao|okay|ok|ok bye|okay bye|chalo|chalo bye|chalo theek hai|bye|bye bye|"
    r"bas|bas karo|bas bas|stop|stop it|that'?s it|that'?s all|band karo|theek hai bas|good ?night|gn|so jao|"
    r"go to sleep|leave it|rehne do)( stiti)?$", re.I)
BACKCHANNEL = re.compile(r"^(haan|han|ha|hmm+|hm+|acha|achha|accha|right|yeah|yes|ji|haan ji|sahi|uh huh)$", re.I)


def _norm(t: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9\s']", " ", t.lower()).split())


def extra_phrases() -> list[str]:
    """The owner's own wake phrases from the local profile (owner_profile.wake_phrases, JSON list). [] if none."""
    import json
    try:
        from .. import profile
        raw = profile.get(PROFILE_KEY)
    except Exception:
        return []
    if not raw:
        return []
    try:
        items = json.loads(raw)
    except ValueError:
        items = re.split(r"[|\n]", raw)
    out: list[str] = []
    for it in items if isinstance(items, list) else []:
        n = _norm(str(it))
        if n and n not in out and n not in DEFAULT_PHRASES:
            out.append(n)
    return out


def phrases() -> list[str]:
    """Every phrase that wakes her: the owner's own first (longer, more specific), then the defaults."""
    return extra_phrases() + DEFAULT_PHRASES


def _save_extra(items: list[str]) -> None:
    import json
    from .. import profile
    profile.set(PROFILE_KEY, json.dumps(items, ensure_ascii=False), source="wake")


def add_phrase(phrase: str) -> str:
    n = _norm(phrase)
    if len(n.split()) < 2:
        return "A wake phrase needs at least two words (her name alone already wakes her)."
    cur = extra_phrases()
    if n in cur or n in DEFAULT_PHRASES:
        return f"“{n}” already wakes her."
    _save_extra(cur + [n])
    return f"Saved: “{n}” now wakes her (restart Stiti.app to pick it up)."


def remove_phrase(phrase: str) -> str:
    n = _norm(phrase)
    cur = extra_phrases()
    if n not in cur:
        return f"“{n}” isn't one of your own wake phrases."
    _save_extra([x for x in cur if x != n])
    return f"Removed “{n}”."


def spoken(phrase: str) -> str:
    """'hey stiti' → 'Hey Stiti' (for prompts and hints)."""
    s = " ".join(w.capitalize() if w.startswith("stiti") else w for w in phrase.split())
    return s[:1].upper() + s[1:]


def hint() -> str:
    """'“Hey Stiti”' or '“Hey Stiti” or “<the owner's first own phrase>”' — for status lines."""
    extra = extra_phrases()
    return "“Hey Stiti”" + (f" or “{spoken(extra[0])}”" if extra else "")


def cli(args: list[str]) -> None:
    """`stiti wake` lists · `stiti wake add "<phrase>"` · `stiti wake remove "<phrase>"`."""
    sub = args[1] if len(args) > 1 else ""
    phrase = " ".join(args[2:])
    if sub == "add" and phrase:
        print(add_phrase(phrase))
    elif sub in ("remove", "rm") and phrase:
        print(remove_phrase(phrase))
    elif sub in ("", "list"):
        print("Defaults: " + ", ".join(spoken(p) for p in DEFAULT_PHRASES))
        extra = extra_phrases()
        print("Your own: " + (", ".join(spoken(p) for p in extra) if extra else "(none — stiti wake add \"<phrase>\")"))
    else:
        print('usage: stiti wake [list | add "<phrase>" | remove "<phrase>"]')


def near_miss(transcript: str) -> bool:
    """Close to a wake phrase but not one — logged so a failing wake can be diagnosed; ambient talk is never logged."""
    if re.search(r"[\u0C00-\u0C7F\u0900-\u097F]", transcript):   # a short line in another script (checked first:
        return len(transcript.split()) <= 4                         # _norm() keeps only Latin letters)
    words = _norm(transcript).split()
    if not words or len(words) > 8:
        return False
    # ≥ 0.7: "stuti"/"sthiti"/"steeti" count; "start" (0.6) doesn't — "You can start with yours" got logged at 0.6
    return "wake" in words or any(SequenceMatcher(None, w.strip("'"), "stiti").ratio() >= 0.7 for w in words if len(w) >= 4)


def _name_hit(word: str) -> bool:
    w = word.strip("'")
    if w in NAME_VARIANTS:
        return True
    return len(w) >= 4 and SequenceMatcher(None, w, "stiti").ratio() >= 0.8


WAKE_START = 2     # a wake phrase must begin within his first 2 words (D48): talking ABOUT her is not calling her
LEAD_IN = {"hey", "hi", "hello", "ok", "okay", "so", "and", "yo", "arre", "are", "suno", "listen", "oye", "uh", "um", "well"}


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
    for ph in phrases():
        n = len(ph.split())
        for i in range(0, min(WAKE_START, max(1, len(words) - n + 1))):   # only at the START of what he says:
            window = " ".join(words[i:i + n])                             # "…explained it to Stiti in detail" woke her
            if SequenceMatcher(None, window, ph).ratio() >= 0.82:
                return True, rest(i + n)
    # the name alone, in the first 4 words ("Stiti, what are my todos")
    for i, w in enumerate(words[:WAKE_START]):       # her name first, or right after "so" / "okay" / "listen"
        if _name_hit(w) and (i == 0 or words[0] in LEAD_IN):
            return True, rest(i + 1)
    return False, ""


# stop words that are a goodbye (she says bye back) vs a hush (she goes quiet at once, no words)
HUSH = re.compile(r"^(shut up|chup|chup karo|chup ho jao|bas|bas karo|bas bas|stop|stop it|band karo|leave it|"
                  r"rehne do|okay|ok)( stiti)?$", re.I)


def is_goodbye(transcript: str) -> bool:
    """'bye', 'chalo bye', 'good night', 'so jao', 'bye Stiti'… — but not 'shut up' / 'stop'."""
    return is_sleep(transcript) and not HUSH.match(_norm(transcript)) and not re.search(r"chup", transcript, re.I)


def is_sleep(transcript: str) -> bool:
    """A sleep phrase — in a long sentence only at its end (2026-11-20: a 49-word line with "bye Stiti" in the middle
    ended the conversation)."""
    words = _norm(transcript).split()
    hay = " ".join(words[-5:]) if len(words) > 8 else transcript
    return bool(SLEEP_RX.search(hay)) or is_stop(transcript)


def is_stop(transcript: str) -> bool:
    return bool(STOP_ONLY.match(_norm(transcript)))


def is_backchannel(transcript: str) -> bool:
    return bool(BACKCHANNEL.match(_norm(transcript)))
