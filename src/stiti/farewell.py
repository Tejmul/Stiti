"""Goodbyes: instant (no LLM), short, warm, varied; aware of time of day, mood and his language.

JARVIS rule 17 + the companion-AI research (De Freitas 2025: guilt-trip goodbyes read as manipulative): she lets him
go in a few words. No "wait, before you go", no "I'll miss you", no pep talk.
"""
from __future__ import annotations

import random
import re
from datetime import datetime

from .config import CFG

HINGLISH = re.compile(r"\b(chalo|theek|so jao|soja|bas|kal|milte|accha|acha|haan|nahi|hai|karo|ja raha|ja rahi|"
                      r"sone|neend)\b", re.I)
# "Bye, going to sleep." · "ok good night" · "talk later" · "chalo so raha hoon" — a goodbye that isn't a bare stop word
BYE_RX = re.compile(r"^\s*((ok(ay)?|chalo|acha|achha|alright|right|so|hmm)[,!. ]+)*(bye+|bye bye|good ?night|gn|"
                    r"see (you|ya)|talk (to you )?later|ttyl|catch you later|going to (sleep|bed)|off to (sleep|bed)|"
                    r"i'?m (going to )?(sleep|bed)|sleeping now|time to sleep|so(ne)? ja (raha|rahi) (hoon|hu)|"
                    r"so raha hoon|so rahi hoon|kal milte|shubh ratri)\b", re.I)

_LINES = {   # {n} = ", Tejmul" (or nothing when she doesn't know the name)
    ("night", "en"): ["Night{n}.", "Sleep well{n}.", "Good night{n}."],
    ("night", "hi"): ["Good night{n}. Kal milte hain.", "Chalo, so jao. Good night.", "Shubh ratri. Kal milte hain."],
    ("morning", "en"): ["Have a good one{n}.", "Later{n}.", "Go get it{n}."],
    ("morning", "hi"): ["Chalo, all the best.", "Bye! Baad mein baat karte hain.", "Chalo, din achha jaaye."],
    ("day", "en"): ["Later{n}.", "Bye{n}.", "Catch you later."],
    ("day", "hi"): ["Chalo bye{n}.", "Theek hai, baad mein milte hain.", "Chalo, bula lena jab chahiye."],
}
_MOOD = {"tired": {"en": "Rest well.", "hi": "Aaram karo."}, "sad": {"en": "Take it easy.", "hi": "Apna khayal rakhna."},
         "stressed": {"en": "One thing at a time.", "hi": "Ek ek karke."}, "angry": {"en": "Breathe.", "hi": "Thoda break lo."}}
_last: str | None = None


def is_bye(text: str) -> bool:
    t = (text or "").strip()
    return len(t.split()) <= 8 and bool(BYE_RX.match(t)) and not t.rstrip().endswith("?")


def _name() -> str | None:
    try:
        from . import profile
        return profile.call() if profile.get("name") else None
    except Exception:
        return None


def farewell(heard: str = "", mood: str | None = None, now: datetime | None = None) -> str:
    """A short goodbye that never repeats the previous one back to back."""
    global _last
    now = now or datetime.now(CFG.tz)
    h = now.hour
    part = "night" if (h >= 21 or h < 4 or re.search(r"good ?night|\bgn\b|so jao|soja|sleep|sone|so raha|so rahi|bed", heard, re.I)) \
        else "morning" if h < 12 else "day"
    lang = "hi" if HINGLISH.search(heard) else "en"
    name = _name()
    options = [l for l in _LINES[(part, lang)] if l != _last] or _LINES[(part, lang)]
    line = random.choice(options)
    _last = line
    line = line.replace("{n}", f", {name}" if name else "")
    extra = _MOOD.get(mood or "", {}).get(lang)
    return f"{extra} {line}" if extra and part != "night" and random.random() < 0.5 else line
