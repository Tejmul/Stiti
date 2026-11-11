"""Which language he is speaking, and which one she replies in (owner, 2026-11-11):

"It should reply in whatever language we talk. English → English; suddenly Telugu → Telugu; 'Namaskar…' → Hindi;
back to English → English. If I say 'just talk in English, don't talk in any other language right now', English only."

Five ways he talks: english · hinglish (Hindi + English in Roman letters) · hindi · telugu · tenglish (Telugu +
English). Decided locally from the transcript in < 1 ms (scripts + two small Roman lexicons), never by the LLM:
- Telugu script (the STT writes Telugu speech in Telugu script, voice/lid.py) → telugu, or tenglish with English words
- Devanagari → hindi (hinglish if half of it is English words)
- Roman: Telugu words ("nenu", "cheppu", "ledu"…) → tenglish; Hindi words (voice/hinglish.py lexicon) → hinglish
  (Roman Hindi, even with no English words: a Devanagari reply to "yaar thak gaya hoon" came out stiff); else english
Reply = a lock if he set one ("only English") › his explicit "talk in Telugu" (until he speaks another non-English
language) › the language of THIS message › for a tiny "ok / haan / bye", the previous reply language.
"""
from __future__ import annotations

import re

LANGS = ("english", "hinglish", "hindi", "telugu", "tenglish")
NAMES = {"english": "English", "hinglish": "Hinglish", "hindi": "Hindi", "telugu": "Telugu", "tenglish": "Tenglish"}

TE_CHARS = re.compile(r"[ఀ-౿]")
DEV_CHARS = re.compile(r"[ऀ-ॿ]")
_WORD = re.compile(r"[ఀ-౿‌]+|[ऀ-ॿ]+|[A-Za-z]+(?:'[A-Za-z]+)?")

# Roman Telugu ("Tenglish" typed/heard in English letters): everyday words that are not also English words.
TE_ROMAN = set("""
nenu nuvvu meeru memu manam vaadu aame vallu naaku naku neeku niku meeku maaku manaki naa nee mee mana
emi emiti enti endi enduku ela elaa eppudu ekkada evaru entha enni inka ippudu appudu ikkada akkada
cheppu cheppandi cheppara cheppu chesanu chesa chesaanu chestanu chestha chey cheyyi cheyandi cheyali cheyyali
ledu ledhu leru undi unnadi unnanu unnav unnava unnaru undhi kavali kaavali kaadu kadu avunu avnu sare sari
ayindi aindi ayyindi avvaledu avaledu kadha kada ante kaani kani mari emaindi emaindhi bagundi baagundi bagunnava
bagunnara bagunna thinnava tinnava padukunna padukunnava vellu vellanu vellali vachanu vacchanu vastanu vasta
raa randi ra matladu matladandi maatladu telugu gurthu gurtu pettu pettandi pettanu chusko chudu choodu chusa
chusanu repu ninna ivala eeroju ee roju poddunna poddune podduna raatri ratri saayantram madhyanam pani panulu
inti illu intlo office lo kosam tho lekunda kuda kooda chala chaala konchem koncham baaga bagaa ippude anni
""".split())
# Short Roman words that are also English or too ambiguous to count alone
TE_AMBIGUOUS = {"lo", "ra", "tho", "ante", "mari", "anni", "kosam", "office", "sari", "sare"}

SHORT_WORDS = 2          # "ok", "haan", "bye", "thanks" don't flip the language

LOCK_PREFIX = "Language lock:"


def tokens(text: str) -> list[str]:
    return _WORD.findall(text or "")


def telugu_roman_hits(words: list[str]) -> int:
    return sum(1 for w in words if w.lower() in TE_ROMAN and w.lower() not in TE_AMBIGUOUS)


def classify(text: str) -> str:
    """The language of one message (see the module doc)."""
    words = tokens(text)
    if not words:
        return "english"
    latin = [w for w in words if w[0].isascii()]
    te_script = sum(1 for w in words if TE_CHARS.match(w))
    dev_script = sum(1 for w in words if DEV_CHARS.match(w))
    if te_script and te_script >= dev_script:
        return "tenglish" if len(latin) >= max(2, 0.25 * len(words)) else "telugu"
    if dev_script:
        return "hinglish" if len(latin) >= 0.5 * len(words) else "hindi"
    from ..voice import hinglish
    te = telugu_roman_hits(latin)
    hi, n = hinglish.evidence(text)
    if te >= 2 or (te >= 1 and n <= 3):
        if te >= hi:
            return "tenglish"
    if hi >= 2 or (hi >= 1 and 3 * hi >= n):
        return "hinglish"        # Hindi in Roman letters (how the STT writes his Hindi): reply the same casual way
    return "english"


def is_short(text: str) -> bool:
    return len(tokens(text)) <= SHORT_WORDS


# ---------------------------------------------------------------- locks and explicit switches
_L = r"(english|hinglish|hindi|telugu|tenglish)"
LOCK_RX = re.compile(rf"\b(only|just)\s+(talk|speak|reply|answer|respond)\s+in\s+{_L}\b|"
                     rf"\b(talk|speak|reply|answer|respond)\s+only\s+in\s+{_L}\b|"
                     rf"\b(talk|speak|reply|answer|respond)\s+(only\s+)?in\s+{_L}\s+only\b|"
                     rf"\b{_L}\s+only\b|"
                     rf"\b(talk|speak|reply|answer|respond)\s+in\s+{_L}\b.*\b(don'?t|do not|never)\b.*\b(other|any other|another)\s+language",
                     re.I)
UNLOCK_RX = re.compile(r"\b(any language|whatever language|whichever language|switch (languages? )?freely|"
                       r"(you can|feel free to|it'?s ok(ay)? to) (switch|change|mix) (the )?languages?|"
                       r"(unlock|remove|drop|stop) (the )?language lock|talk in (the )?(language|whatever) i (talk|speak)|"
                       r"reply in (the )?(language|whatever) i (talk|speak)|match my language)\b", re.I)
SWITCH_RX = re.compile(rf"\b(talk|speak|reply|answer|respond|switch|change)\b[^.?!]{{0,20}}?\b(?:in|to|into)\s+{_L}\b|"
                       rf"\b{_L}\s+(mein|me|lo|lone)\s+(bolo|baat\s*karo|matladu|matladandi|cheppu)\b|"
                       r"\b(telugu)\s*lo\s*(matladu|matladandi|maatladu|cheppu)\b|"
                       r"\b(hindi|hinglish)\s+(mein|me)\s+(bolo|baat\s*karo)\b", re.I)


def _lang_in(m: re.Match) -> str | None:
    for g in m.groups():
        if g and g.lower() in LANGS:
            return g.lower()
    return None


def command(text: str) -> tuple[str, str | None] | None:
    """("lock", lang) / ("unlock", None) / ("switch", lang), or None. "I speak English at work" is not a command."""
    t = text.strip()
    if re.match(r"^\s*(i|we|they|he|she|people)\b", t, re.I) and not re.search(r"\b(you|stiti)\b", t, re.I):
        return None
    if UNLOCK_RX.search(t):
        return "unlock", None
    if (m := LOCK_RX.search(t)) and (lg := _lang_in(m)):
        return "lock", lg
    if (m := SWITCH_RX.search(t)) and (lg := _lang_in(m)):
        return "switch", lg
    return None


def lock_directive(lang: str) -> str:
    return f"{LOCK_PREFIX} reply only in {NAMES[lang]} until he says you can switch languages."


def locked(directives: list[str] | None) -> str | None:
    """The language he LOCKED ("Language lock: …", newest first). Older "Reply in English" style rules are not locks:
    a one-off "talk in English" used to become a forever-rule; now it's a switch (engine.lang_pref)."""
    for d in reversed(directives or []):
        if d.startswith(LOCK_PREFIX):
            m = re.search(r"reply only in (\w+)", d.lower())
            if m and m.group(1) in LANGS:
                return m.group(1)
    return None


LANG_RULE_RX = re.compile(r"\b(reply|talk|speak|respond|answer)\b.{0,20}\b(english|hinglish|hindi|telugu|tenglish)\b", re.I)


def is_language_rule(directive: str) -> bool:
    """A talk-style rule about which language to use (a lock or an old-style one). The language line in the reply
    rules is the only place the LLM hears the language from, so these stay out of the MUST lines."""
    return directive.startswith(LOCK_PREFIX) or bool(LANG_RULE_RX.search(directive))


def decide(text: str, *, prev: str | None = None, lock: str | None = None, pref: str | None = None) -> str:
    """The reply language for this message."""
    if lock:
        return lock
    heard = classify(text)
    if pref and heard in ("english", pref):
        return pref                              # he asked for Telugu and keeps talking English/Telugu: stay Telugu
    if is_short(text) and prev and heard == "english":
        return prev                              # "ok" / "bye" / "thanks" don't flip it
    return heard


# ---------------------------------------------------------------- what the LLM is told + her own short lines
PROMPT = {
    "english": "English. Not Hindi, not Hinglish, not Telugu — even if earlier turns were",
    "hinglish": "Hinglish (Hindi + English in Roman script, no Devanagari). You are female: \"main dekh rahi hoon\", "
                "\"samajh gayi\", \"karungi\" — never raha/gaya/karunga",
    "hindi": "Hindi in Devanagari script (हिंदी), simple spoken Hindi; English words only for tech terms. You are female: "
             "\"मैं देख रही हूँ\", \"समझ गई\", \"करूँगी\"",
    "telugu": "Telugu in Telugu script (తెలుగు), simple spoken Telugu like a friend; English only for tech terms",
    "tenglish": "Tenglish like he speaks: Telugu in Telugu script mixed with everyday English words in English letters "
                "(e.g. \"రేపు morning six కి alarm set చేశాను\")",
}
PHRASE = {
    "got_it": {"english": "Got it.", "hinglish": "Samajh gayi.", "hindi": "समझ गई।", "telugu": "అర్థమైంది.",
               "tenglish": "Okay, అర్థమైంది."},
    "here": {"english": "Okay, I'm here.", "hinglish": "Theek hai, main yahin hoon.", "hindi": "ठीक है, मैं यहीं हूँ।",
             "telugu": "సరే, నేను ఇక్కడే ఉన్నాను.", "tenglish": "Okay, నేను ఇక్కడే ఉన్నాను."},
    "switched": {"english": "Sure, English it is.", "hinglish": "Theek hai, Hinglish mein baat karte hain.",
                 "hindi": "ठीक है, अब हिंदी में बात करते हैं।", "telugu": "సరే, ఇప్పుడు తెలుగులో మాట్లాడదాం.",
                 "tenglish": "సరే, Tenglish లో మాట్లాడదాం."},
    "locked": {"english": "Got it. English only until you say otherwise.",
               "hinglish": "Theek hai, sirf Hinglish jab tak tum na kaho.", "hindi": "ठीक है, जब तक आप न कहें, सिर्फ़ हिंदी।",
               "telugu": "సరే, మీరు చెప్పే వరకు తెలుగులోనే మాట్లాడతాను.", "tenglish": "సరే, Tenglish లోనే మాట్లాడతాను."},
    "unlocked": {"english": "Okay, I'll reply in whatever language you speak."},
}


def phrase(key: str, lang: str) -> str:
    d = PHRASE[key]
    return d.get(lang) or d["english"]


def native(lang: str) -> bool:
    """Replies in a script the Hindi/Telugu voices should read (not the English voice)."""
    return lang in ("hinglish", "hindi", "telugu", "tenglish")
