"""Don't say it twice (D36, docs/research/no_repeat.md).

2026-11-14, his real morning: "what do you know about me?" → school, projects, football. "Okay, what else?" → the same
school, projects, football + one new line. "And what else?" → again. The LLM never knew what she had already said:
every turn got the same top profile lines, and her own earlier replies were cut to 160 chars in RECENT.

The brain tracks it, not the LLM:
- Ledger: what she actually said this conversation (sentences + their content words), last ~20 min.
- MORE ("what else", "aur batao", "inka cheppu", "is there some other thing"): the briefing drops every profile / fact /
  memory line she already covered and gets an ALREADY-SAID block; nothing new left → an honest line, no LLM.
- A sentence whose content words were all said already is dropped before it is spoken (StreamLint) or stored
  (enforce). REPEAT ("say that again", "kya bola") and REPAIR turns switch that off — repeating is the point there.
Pure regex + set maths: microseconds, no model call on the hot path.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass

WINDOW_S = 20 * 60          # a "conversation" for repetition purposes
CAP = 60                    # sentences kept
MIN_WORDS = 3               # a sentence needs ≥ 3 content words to count as a repeat ("Good night." may be said twice)

_SENT = re.compile(r"(?<=[.!?।])\s+")
_WORD = re.compile(r"[a-z]{4,}|\d{2,}")
_STOP = set("""that this with have from your about what when they them were been just like know really then there
going doing want also more some will would could should their there here into over than very much many such only
other thing things stuff sure okay yeah well right still even ever every being does done make made tell told said
says best good great nice also mostly most less least lots plenty already again""".split())

_ASK_OK = r"(?:(?:ok(?:ay)?|hmm+|right|cool|got it|fine|alright|nice|achha|accha|acha|haan|theek hai|sari|sare)[\s,.!]*)*"
MORE_RX = re.compile(
    r"\bwhat else\b|\banything else\b(?!\s+(?:to do|today|pending|left|due|on my))|\bsomething else\b|"
    r"\bwhat more\b|\b(?:tell me|say|know)(?: some)? more\b|\bgo on\b|\bkeep going\b|"
    r"\b(?:some|any) ?other (?:thing|things|stuff|point|points|fact|facts)\b|\bother than (?:that|this)\b|"
    r"\baur (?:batao|bata|bolo|sunao|kya|kuch)\b|\bkuch aur\b|\biske (?:alawa|alava|siva|sivaay)\b|"
    r"\b(?:aage|baaki|baki) (?:batao|bolo|kya)\b|"
    r"\binka (?:cheppu|emi|em|enti|emaina|emanna|unda)\b|\binkem\b|\bmarinni\b|ఇంకా|ఇంకేం|ఇంకేమి|"
    rf"^\W*{_ASK_OK}(?:and|aur|then|more|phir)\W*$", re.I)
REPEAT_RX = re.compile(
    r"\b(?:say (?:that|it) again|repeat(?: that| it)?|come again|once more|what did you (?:just )?say|"
    r"kya bola|phir se (?:bolo|batao)|dobara|malli cheppu|em annav)\b", re.I)

HONEST_AGAIN = {"english": ["That's really all I have for now.", "Nothing new yet — tell me something and I'll keep it."],
                "hinglish": ["Bas itna hi abhi.", "Abhi kuch naya nahi — tum batao, main yaad rakhungi."],
                "hindi": ["बस इतना ही अभी।", "अभी कुछ नया नहीं — तुम बताओ, मैं याद रखूँगी।"],
                "telugu": ["ప్రస్తుతానికి ఇంతే.", "కొత్తది ఏమీ లేదు — నువ్వు చెప్పు, గుర్తుపెట్టుకుంటా."],
                "tenglish": ["Prasthuthaniki inte.", "Kotthadi emi ledu — nuvvu cheppu, gurthupettukunta."]}
HONEST = {"english": "That's most of what I know so far — tell me more and I'll remember it.",
          "hinglish": "Abhi itna hi pata hai — aur batao, yaad rakh lungi.",
          "hindi": "अभी इतना ही पता है — और बताओ, याद रख लूँगी।",
          "telugu": "ఇప్పటికి నాకు తెలిసింది ఇంతే — ఇంకా చెప్పు, గుర్తుపెట్టుకుంటా.",
          "tenglish": "Ippatiki naaku telisindi inte — inka cheppu, gurthupettukunta."}


def honest(lang: str, ledger: "Ledger | None" = None) -> str:
    """"That's most of what I know" — and not the same line three times in a row either."""
    first = HONEST.get(lang, HONEST["english"])
    again = HONEST_AGAIN.get(lang, HONEST_AGAIN["english"])
    if ledger is None:
        return first
    n = sum(1 for x in ledger.live() if x[2] == first or x[2] in again)
    return first if n == 0 else again[(n - 1) % len(again)]


def words(text: str, ignore: frozenset[str] = frozenset()) -> set[str]:
    """Content words, crude-stemmed (leads → lead, players → player)."""
    out = set()
    for w in _WORD.findall((text or "").lower()):
        if w in _STOP or w in ignore:
            continue
        if len(w) > 4 and w.endswith("s") and not w.endswith("ss"):
            w = w[:-1]
        out.add(w)
    return out


def sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENT.split(text or "") if s.strip()]


def wants_more(text: str) -> bool:
    return bool(MORE_RX.search(text or "")) and not REPEAT_RX.search(text or "")


_ASK_START = re.compile(r"^\W*(?:(?:ok(?:ay)?|so|and|hey|achha|accha)\W+)*(?:what|how|why|who|where|when|which|can you|"
                        r"could you|do you|did you|is there|are there|tell me|kya|kaun|kab|kaise|kitn[aei]|em|enti)\b",
                        re.I)


def is_ask(text: str) -> bool:
    """A question / request ("what else do you know?") — not a thing he told her."""
    t = (text or "").strip()
    return t.endswith("?") or bool(_ASK_START.match(t) or MORE_RX.search(t) or REPEAT_RX.search(t))


def wants_repeat(text: str) -> bool:
    return bool(REPEAT_RX.search(text or ""))


@dataclass(frozen=True)
class Ledger:
    """What she said this conversation. Immutable: every change returns a new Ledger, so the engine's speculative-turn
    snapshot (a shallow copy of its attributes) restores it exactly."""
    said: tuple[tuple[float, int | None, str, frozenset], ...] = ()    # (when, reply episode id, sentence, words)
    ignore: frozenset[str] = frozenset()                                # his name: in every profile line, not content
    anchor: tuple[str, object] | None = None                            # last real question + its vector (for MORE)

    def live(self, now: float | None = None) -> tuple:
        now = time.time() if now is None else now
        return tuple(x for x in self.said if now - x[0] < WINDOW_S)

    def add(self, reply: str, ep: int | None = None, now: float | None = None) -> "Ledger":
        now = time.time() if now is None else now
        new = tuple((now, ep, s, frozenset(words(s, self.ignore))) for s in sentences(reply))
        return Ledger((self.live(now) + new)[-CAP:], self.ignore, self.anchor)

    def replace(self, ep: int | None, heard: str) -> "Ledger":
        """After a barge-in he heard only part of the reply: only that part counts as said."""
        kept = tuple(x for x in self.said if ep is None or x[1] != ep)
        return Ledger(kept, self.ignore, self.anchor).add(heard, ep) if heard else Ledger(kept, self.ignore, self.anchor)

    def with_anchor(self, text: str, vec) -> "Ledger":
        return Ledger(self.said, self.ignore, (text, vec))

    def with_ignore(self, names: set[str]) -> "Ledger":
        return Ledger(self.said, frozenset(w.lower() for w in names if w), self.anchor)

    def said_words(self, now: float | None = None) -> set[str]:
        out: set[str] = set()
        for x in self.live(now):
            out |= x[3]
        return out

    def covered(self, line: str, now: float | None = None) -> bool:
        """Was this briefing line (profile / fact / memory) already told? ≥ 2 of its content words, and at least half
        of them, are in what she said."""
        body = re.sub(r"^\s*\[[^\]]*\]\s*", "", line).lstrip("-• ")   # "[F12 · true since 2026-09 · fact]" isn't content
        lw = words(body, self.ignore)
        if not lw:
            return False
        said = self.said_words(now)
        ov = lw & said
        if len(ov) >= 2 and len(ov) * 2 >= len(lw):
            return True
        # the names in a line are what it is about: "built Tilecraft, a tile-design app, and Parkly" was told once
        # "You built Tilecraft and Parkly" was said, even though "tile-design app" wasn't
        names = words(" ".join(re.findall(r"(?<=\s)[A-Z][\w+#-]{3,}", " " + body.split(" ", 1)[-1])), self.ignore)
        return len(ov) >= 2 and bool(names) and names <= said

    def is_repeat(self, sentence: str, now: float | None = None) -> bool:
        """Every content word of this sentence (≥ MIN_WORDS of them) was already said this conversation."""
        sw = words(sentence, self.ignore)
        return len(sw) >= MIN_WORDS and not (sw - self.said_words(now))

    def gists(self, max_chars: int = 480, now: float | None = None) -> list[str]:
        out, n = [], 0
        for x in reversed(self.live(now)):
            if len(x[3]) < 2:
                continue
            g = x[2][:160]
            if n + len(g) > max_chars:
                break
            out.append(g)
            n += len(g)
        return list(reversed(out))


def dedup(reply: str, ledger: Ledger | None) -> str:
    """Drop sentences that only repeat what she already said. '' when nothing new is left."""
    if ledger is None or not ledger.said:
        return reply
    return " ".join(s for s in sentences(reply) if not ledger.is_repeat(s))


def fresh(lines: list[str], ledger: Ledger | None) -> list[str]:
    """Briefing lines she hasn't covered yet."""
    if ledger is None:
        return list(lines)
    return [l for l in lines if not ledger.covered(l)]


def collapse_fragments(recent: list[dict]) -> list[dict]:
    """A cut-off half sentence that he then said in full ("I left MVRX Labs change it down." → "I left MVRX Labs
    change it down. It's been around in September…") shows up twice in RECENT: keep only the full one."""
    out: list[dict] = []
    for r in recent:
        if r["speaker"] == "user":
            cur = re.sub(r"\W+", " ", r["text"]).strip().lower()
            for j in range(len(out) - 1, max(-1, len(out) - 3), -1):
                prev = out[j]
                if prev["speaker"] != "user":
                    continue
                p = re.sub(r"\W+", " ", prev["text"]).strip().lower()
                if p and cur.startswith(p) and len(cur) > len(p):
                    out.pop(j)
                break
        out.append(r)
    return out

