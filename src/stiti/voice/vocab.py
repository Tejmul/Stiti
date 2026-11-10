"""His personal dictionary: words learned from his corrections, so a mis-hearing is fixed once, for good (D27).

Wispr Flow learns words when the user edits a transcript (re_wispr_flow.md §3: align old/new text, keep ≤ 4 word
substitutions, store `phrase + observedSource`). Stiti has no text box to watch, so the voice version listens for a
correction right after a mis-hearing:
  "no, I said Tejmul" · "it's Stiti, not City" · "Tejmul, not Tejmal" · "spell it T-E-J-M-U-L" ·
  "nahi, maine Tejmul bola" · and explicit: "add 'Zonuly' to your vocabulary", "remember the word Zonuly".
The heard form comes from the correction itself ("not City") or from the previous utterance (the closest-sounding
span). Learned terms go into the Whisper glossary (top priority, like Wispr's manual words) and the snap step; the
heard form becomes a rewrite rule — unless it is an ordinary single word ("City" stays "City" elsewhere).

Local only: `~/.stiti/vocab.json`, plain JSON he can read and edit. Parsing is rules (< 1 ms), no LLM.
"""
from __future__ import annotations

import difflib
import json
import re
import threading
import time
from dataclasses import dataclass
from pathlib import Path

_lock = threading.Lock()
_cache: dict | None = None
_cache_mtime = 0.0


@dataclass
class Learned:
    term: str
    heard: str | None
    source: str                  # correction | spelled | explicit


def _path() -> Path:
    from ..config import CFG
    return CFG.home / "vocab.json"


# ---------------------------------------------------------------- store
def load() -> dict:
    """{'terms': {term: {'heard': [...], 'source': str, 'added': iso, 'count': n}}}; re-read when he edits it."""
    global _cache, _cache_mtime
    p = _path()
    try:
        m = p.stat().st_mtime
    except OSError:
        return {"terms": {}}
    if _cache is None or m != _cache_mtime:
        try:
            data = json.loads(p.read_text())
            _cache = data if isinstance(data.get("terms"), dict) else {"terms": {}}
        except (OSError, ValueError, AttributeError):
            _cache = {"terms": {}}
        _cache_mtime = m
    return _cache


def terms() -> list[str]:
    """Learned terms, most recently confirmed last."""
    t = load()["terms"]
    return sorted(t, key=lambda k: t[k].get("updated", t[k].get("added", "")))


def add(term: str, heard: str | None = None, source: str = "explicit") -> None:
    global _cache, _cache_mtime
    term = " ".join(term.split())
    with _lock:
        data = json.loads(json.dumps(load()))                     # copy
        e = data["terms"].setdefault(term, {"heard": [], "source": source, "added": time.strftime("%Y-%m-%d %H:%M"),
                                            "count": 0})
        e["count"] = int(e.get("count", 0)) + 1
        e["updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
        if heard and heard.lower() != term.lower() and heard.lower() not in (h.lower() for h in e["heard"]):
            e["heard"].append(heard)
        p = _path()
        tmp = p.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False))
        tmp.replace(p)
        _cache, _cache_mtime = data, p.stat().st_mtime
    from . import glossary
    glossary.learn(term)


# ---------------------------------------------------------------- rewrite known mis-hearings
def _safe_heard(h: str) -> bool:
    """Rewrite a heard form everywhere only if it can't be an ordinary word ('Tejmal', "Newton's Club" yes;
    'City' no — that one only biases the prompt)."""
    from .glossary import _is_ordinary
    words = h.split()
    return len(words) > 1 or not _is_ordinary(words[0])


def rewrite(text: str) -> str:
    if not text:
        return text
    for term, e in load()["terms"].items():
        for h in e.get("heard", []):
            if h and _safe_heard(h):
                text = re.sub(rf"(?<![\w']){re.escape(h)}(?![\w'])", term, text, flags=re.I)
    return text


# ---------------------------------------------------------------- parsing his corrections
_Q = "'\"“”‘’"
_TERM = r"[\w'’.&+-]+(?:[ -][\w'’.&+-]+){0,3}"
_NEG = r"(?:no|nope|nahi|nahin|arre|arey|not that|wrong)"
_LEAD = r"(?:(?:hey )?stiti[,]? )?"
_SPELLED = re.compile(r"(?<![\w])((?:[A-Za-z][\s.\-,]+){2,29}[A-Za-z])(?![\w])")
RX = [
    # "spell it T-E-J-M-U-L" / "it's spelled T E J M U L"
    ("spelled", re.compile(rf"^{_LEAD}(?:{_NEG}[,.!]?\s*)?(?:(?:you )?spell(?:ed|t)?(?: it| that| my name| the name)?"
                           rf"(?: as| like| is)?|it'?s spelled|spelling is|the spelling is)\s*[:,]?\s*(?P<s>.+)$", re.I)),
    # explicit: "add 'Zonuly' to your vocabulary", "remember the word Zonuly"
    ("explicit", re.compile(rf"^{_LEAD}(?:please )?(?:add|put|save)\s+(?:the word |the name )?[{_Q}]?(?P<good>{_TERM}?)"
                            rf"[{_Q}]?\s+(?:to|in|into)\s+(?:your|my|the)\s+(?:vocabulary|vocab|dictionary|word list|"
                            rf"words)\b.*$", re.I)),
    ("explicit", re.compile(rf"^{_LEAD}(?:please )?(?:remember|learn)\s+(?:the|this|my)\s+(?:word|name|spelling)\s*[:,]?\s*"
                            rf"[{_Q}]?(?P<good>{_TERM}?)[{_Q}]?[.!]?$", re.I)),
    # "not City, Stiti" / "not Tejmal, it's Tejmul"
    ("pair", re.compile(rf"^{_LEAD}(?:{_NEG}[,.!]?\s*)?not\s+[{_Q}]?(?P<bad>{_TERM}?)[{_Q}]?[,.;!]?\s+(?:it'?s |it is |"
                        rf"but |i said )?[{_Q}]?(?P<good>{_TERM}?)[{_Q}]?[.!]?$", re.I)),
    # "it's Stiti, not City" / "Tejmul, not Tejmal" / "my name is Tejmul not Tejmal" / "Tejmul bola, Tejmal nahi"
    ("pair", re.compile(rf"^{_LEAD}(?:{_NEG}[,.!]?\s*)?(?:it'?s |it is |its |i said |say |my name is |the name is |"
                        rf"call me |that'?s )?[{_Q}]?(?P<good>{_TERM}?)[{_Q}]?[,;]?\s+not\s+[{_Q}]?(?P<bad>{_TERM}?)"
                        rf"[{_Q}]?[.!?]?$", re.I)),
    ("pair", re.compile(rf"^{_LEAD}[{_Q}]?(?P<good>{_TERM}?)[{_Q}]?\s+(?:bola|kaha)[,]?\s+[{_Q}]?(?P<bad>{_TERM}?)[{_Q}]?"
                        rf"\s+nahi[n]?[.!]?$", re.I)),
    # "no, I said Tejmul" / "nahi, maine Tejmul bola" (needs the "no": "I said hello" alone is not a correction)
    ("said", re.compile(rf"^{_LEAD}{_NEG}[,.!]?\s*(?:i said|i say|i'?m saying|i meant|it'?s|it is|its|maine|main ne|"
                        rf"mera naam)\s+[{_Q}]?(?P<good>{_TERM}?)[{_Q}]?(?:\s+(?:bola|kaha|hai))?[.!]?$", re.I)),
]
_FILLER = {"i", "a", "an", "the", "it", "is", "its", "it's", "that", "this", "my", "your"}


def _clean(t: str) -> str:
    t = re.sub(rf"^[{_Q}\s,.:;!?-]+|[{_Q}\s,.:;!?-]+$", "", t or "")
    return " ".join(t.split())


def _letters(s: str) -> str | None:
    """'T-E-J-M-U-L' / 'T E J M U L' / 'Tee E J M U L.' → 'Tejmul' (single letters only)."""
    m = _SPELLED.search(s)
    if not m:
        return None
    ls = re.findall(r"[A-Za-z]", m.group(1))
    return (ls[0].upper() + "".join(ls[1:]).lower()) if 3 <= len(ls) <= 30 else None


def _sounds_alike(a: str, b: str) -> float:
    from .glossary import skeleton
    sa, sb = skeleton(a), skeleton(b)
    la, lb = re.sub(r"[^a-z]", "", a.lower()), re.sub(r"[^a-z]", "", b.lower())
    return max(difflib.SequenceMatcher(None, sa, sb).ratio(), difflib.SequenceMatcher(None, la, lb).ratio())


def heard_in(prev: str | None, term: str) -> str | None:
    """The span of the previous utterance that was most likely this term, mis-heard (same word count ±1)."""
    if not prev:
        return None
    words = [w.strip(".,!?;:\"“”'") for w in prev.split()]
    n = len(term.split())
    best, score = None, 0.0
    for k in {max(1, n - 1), n, n + 1}:
        for i in range(len(words) - k + 1):
            span = " ".join(words[i:i + k]).strip()
            if not span or span.lower() == term.lower() or span.lower() in _FILLER:
                continue
            s = _sounds_alike(span, term)
            if s > score:
                best, score = span, s
    return best if score >= 0.6 else None


def _worth_learning(term: str, source: str) -> bool:
    from .glossary import _is_ordinary
    words = term.split()
    if not words or len(words) > 4 or not 2 <= len(term) <= 40 or not re.search(r"[A-Za-z]", term):
        return False
    if source in ("spelled", "explicit"):
        return True
    # a correction teaches a NAME or a rare word, not "milk": capitalised (not just "I") or not a dictionary word
    return any((w[0].isupper() and w != "I") or not _is_ordinary(w) for w in words)


def parse(text: str, prev: str | None = None) -> Learned | None:
    """A correction or an explicit 'learn this word' in this utterance, else None. `prev` = his previous utterance
    (what Stiti heard wrong)."""
    t = " ".join((text or "").split())
    if not t or len(t.split()) > 14:
        return None
    for kind, rx in RX:
        m = rx.match(t)
        if not m:
            continue
        if kind == "spelled":
            term = _letters(m.group("s"))
            if not term:
                continue
            return Learned(term, heard_in(prev, term), "spelled")
        good = _clean(m.group("good"))
        if kind == "explicit":
            return Learned(good, None, "explicit") if _worth_learning(good, "explicit") else None
        bad = _clean(m.group("bad")) if "bad" in m.groupdict() else None
        if bad is not None:
            if len(bad.split()) != len(good.split()) or _sounds_alike(good, bad) < 0.5 or good.lower() == bad.lower():
                continue                                   # "call Rahul not Raju": a choice, not a mis-hearing
        else:
            bad = heard_in(prev, good)
            if bad is None:
                continue                                   # nothing in the last turn sounded like it
        if _worth_learning(good, "correction"):
            return Learned(good, bad, "correction")
    if prev and (term := _letters(t)) and len(t.split()) <= 12 and heard_in(prev, term):
        return Learned(term, heard_in(prev, term), "spelled")    # he just spelled it out: "T-E-J-M-U-L."
    return None


def learn(text: str, prev: str | None = None) -> Learned | None:
    """parse() + save. Returns what was learned."""
    lr = parse(text, prev)
    if lr:
        add(lr.term, lr.heard, lr.source)
    return lr


def confirm(lr: Learned) -> str:
    if lr.heard:
        return f"Got it — {lr.term}, not {lr.heard}. I'll hear it right from now on."
    return f"Got it — I've added {lr.term} to my vocabulary."
