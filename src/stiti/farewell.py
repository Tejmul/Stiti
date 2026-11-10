"""Goodbyes: instant (no LLM), warm, varied, and aware of time of day, mood and his language mix."""
from __future__ import annotations

import random
import re
from datetime import datetime

from .config import CFG

HINGLISH = re.compile(r"\b(chalo|theek|so jao|soja|bas|kal|milte|accha|acha|haan|nahi|hai|karo)\b", re.I)

_LINES = {
    ("night", "en"): ["Good night! Sleep well — talk tomorrow.", "Night night! Rest up, you've earned it.",
                      "Good night. Tomorrow's a fresh start.", "Sleep well! I'll be right here tomorrow."],
    ("night", "hi"): ["Good night! Achhe se sona, kal milte hain.", "Chalo, shubh ratri! Kal baat karte hain.",
                      "Good night! Aaram karo, kal fresh start.", "So jao ab, kal milte hain. Good night!"],
    ("morning", "en"): ["Bye! Have a great day.", "Go get 'em! Talk later.", "Bye! Make it a good one."],
    ("morning", "hi"): ["Bye! Din achha jaaye.", "Chalo, all the best aaj ke liye! Baad mein baat karte hain."],
    ("day", "en"): ["Bye! Ping me anytime.", "Catch you later!", "Okay, bye! I'm here when you need me."],
    ("day", "hi"): ["Chalo bye! Jab chahiye, bula lena.", "Theek hai, baad mein milte hain!",
                    "Okay bye! Kuch bhi ho toh bula lena."],
}
_MOOD = {
    "tired": {"en": "Go rest — you've earned it.", "hi": "Thoda aaram kar lo."},
    "sad": {"en": "Be gentle with yourself tonight.", "hi": "Apna khayal rakhna."},
    "stressed": {"en": "One thing at a time — you've got this.", "hi": "Ek ek karke, ho jayega."},
    "angry": {"en": "Take a breather.", "hi": "Thoda break le lo."},
    "happy": {"en": "Love the energy today!", "hi": "Aaj mood badhiya hai!"},
}
_last: str | None = None


def farewell(heard: str = "", mood: str | None = None, now: datetime | None = None) -> str:
    """A short goodbye that never repeats the previous one back to back."""
    global _last
    now = now or datetime.now(CFG.tz)
    h = now.hour
    part = "night" if (h >= 21 or h < 4 or re.search(r"good ?night|gn|so jao|soja|sleep", heard, re.I)) \
        else "morning" if h < 12 else "day"
    lang = "hi" if HINGLISH.search(heard) else "en"
    options = [l for l in _LINES[(part, lang)] if l != _last] or _LINES[(part, lang)]
    line = random.choice(options)
    _last = line
    extra = _MOOD.get(mood or "", {}).get(lang)
    return f"{extra} {line}" if extra and random.random() < 0.7 else line
