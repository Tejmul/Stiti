"""Noticing things that matter (D49): a dated event, deadline or commitment in a piece of text. Local rules, no LLM.

    "my exams start from the 9th"                      → exams · exam · 9 Dec · 0.85
    "I have an interview at Orbit Labs on 20th November at 3 pm"
    "mera DBMS ka exam 9 tarikh ko hai" · "kal mera interview hai"
    "I have to submit my project report by Friday"     → project report · deadline
    mail: "Fee payment due on 25 November"             → fee payment · bill

An item needs an event word AND a day that is today or later. Not items: questions, past tense ("was", "tha",
"ho gaya"), "if" / "not" / cancelled, somebody else's thing (except birthdays and weddings), plain commands.
Research: docs/research/important_things.md (Apple data detectors drop uncertain matches; tense + negation are the
cheap features that carry commitment detection; rules reach ~0.9 F1 on dates).
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from ..config import CFG
from ..fastpath import dates

ASK_MIN = 0.7           # below this she says nothing (Horvitz 1999: do nothing / ask / act)
SOON = timedelta(hours=2)   # something starting within 2 h is conversation, not planning

# kind → the words that name it (the first kind that matches wins; the LAST matching word before the date is the head)
NOUNS: list[tuple[str, str]] = [
    ("exam", r"exams?|examinations?|mid-?sems?|mid-?terms?|end-?sems?|vivas?|quiz(?:zes)?|tests?|pariksha|imtihaan|"
             r"boards|papers?"),
    ("interview", r"interviews?|hr rounds?|technical rounds?|placement drives?"),
    ("deadline", r"deadlines?|submissions?|assignments?|last date|due date|applications?|registrations?"),
    ("bill", r"bills?|fees?|rent|emi|premium|instal?lments?|recharge|payments?"),
    ("result", r"results?"),
    ("travel", r"flights?|trains?|trips?"),
    ("appointment", r"appointments?|doctor|dentist|check-?ups?|haircut|vaccination"),
    ("birthday", r"birthdays?|b'?days?|janamdin|anniversar(?:y|ies)"),
    ("meeting", r"meetings?|stand-?ups?|presentations?|demos?|seminars?|orientation|call(?= with\b)"),
    ("event", r"hackathons?|conferences?|workshops?|webinars?|concerts?|match(?:es)?|part(?:y|ies)|functions?|fests?|"
              r"weddings?|shaadi|sangeet|reception|contests?|competitions?|tournaments?|meetups?"),
]
_NOUN_RX = [(k, re.compile(rf"\b(?:{rx})\b", re.I)) for k, rx in NOUNS]
WEAK = {"event"}                                        # casual words: need more around them to be worth a question
HEAD_SAY = {"doctor": "doctor's appointment", "dentist": "dentist appointment"}
# "I have to submit the lab record by Monday" — a commitment with no event noun: the verb names it
VERB_RX = re.compile(r"\b(?:have to|need to|has to|must|should|got to|gotta|supposed to|hai ki)\s+"
                     r"(?P<verb>submit|pay|renew|apply for|register for|send|finish|complete|hand in|turn in|file)\s+"
                     r"(?P<obj>[^,.;]{2,60}?)\s+(?:by|before|on|till|until)\s*$", re.I)
# a word that only LOOKS like the noun: "I'll test it on Friday", "to train the model"
_VERBISH = re.compile(r"\b(?:to|will|i'?ll|we'?ll|gonna|can|could|should|must|let'?s|lets|i|we|you|they|and|then|"
                      r"please|just|not|don'?t|didn'?t)\s+$", re.I)
QUESTION = re.compile(r"\?\s*$|^\W*(?:(?:hey|hi|ok|okay|so|and|stiti)\W+)*(?:what|when|which|who|where|why|how|is|are|"
                      r"do|does|did|can|could|will|would|should|am|have|has|any|kya|kab|kaun|kahan|kitne|kaise|"
                      r"kyun|kyu)\b", re.I)
COMMAND = re.compile(r"^\W*(?:(?:hey|hi|ok|okay|so|and|also|please|stiti)\W+)*(?:find|search|book|show|tell|open|play|"
                     r"check|look|add|set|remind|cancel|delete|remove|move|change|list|read|google|teach|explain|"
                     r"plan|schedule|give|make|create|send|call|text|message|wake|start|stop)\b", re.I)
PAST = re.compile(r"\b(?:was|were|had|went|gave|attended|happened|got over|(?:is|are) over|finished|ended|completed|"
                  r"done with|yesterday|ago|last (?:week|month|year|night|time|sem|semester|" + "|".join(dates.WEEKDAYS)
                  + r")|tha|thi|ho gay[aie]|ho chuk[aie]|khatam|de di(?:ya)?|pichh?le|cleared|passed|cracked)\b", re.I)
UNSURE = re.compile(r"\b(?:if|agar|unless|whether|maybe|might|perhaps|probably|shayad|not sure|don'?t know|no|not|never|"
                    r"nahi|nahin|isn'?t|aren'?t|won'?t|don'?t have|doesn'?t|cancel\w*|called off|wish|hope\w*|"
                    r"suppose|imagine|what if|thinking (?:of|about)|pata nahi)\b", re.I)
REPEATS = re.compile(r"\b(?:every|each|har|daily|roz|rozana|weekly|everyday|weekdays?|weekends?)\b", re.I)
MINE = re.compile(r"\b(?:my|mine|our|i have|i'?ve got|i have got|i got|i need to|i have to|i must|we have|we'?ve got|"
                  r"mera|meri|mere|mujhe|hamara|hamari|humara|humari|apna|apni|main|maine)\b", re.I)
OTHERS = re.compile(r"\b(?:[A-Z][a-z]+'s|his|her|their|uska|uski|unka|unki|iska|iski)\s+(?:\w+\s+){0,2}$")
FAMILY = (r"(?:mom|mother|mum|mummy|maa|mumma|dad|father|papa|sister|didi|brother|bhai|bhaiya|wife|husband|girlfriend|"
          r"boyfriend|friend|son|daughter|uncle|aunt|cousin|nani|nana|dadi|dada|boss|manager)")
LINK = re.compile(r"(?:[\s,:\-–—]+(?:is|are|was|will|be|being|been|it'?s|its|starts?|start|starting|begins?|begin|"
                  r"beginning|happening|happens?|held|scheduled|due|coming|comes?|come|out|falls?|closes?|ends?|opens?|"
                  r"from|on|by|at|for|in|till|until|before|this|next|the|a|se|ko|tak|hai|hain|h|shuru|ho\w*|rah[aei]|"
                  r"hone|wal[aei]|ke|ka|ki|kal|aaj|parson?|tomorrow|today|that|which|to be|going to be|set|fixed|"
                  r"planned|confirmed|booked|dated|date))+[\s,:\-–—]*$", re.I)
LEAD = re.compile(r"^[\s,:\-–—]*(?:(?:so|and|also|btw|by the way|actually|hey|okay|ok|stiti|listen|yaar|arre|oh|well|"
                  r"you know|fyi|just so you know|reminder|re|fwd|fw|update|notice|important|urgent|dear \w+|hi \w+|"
                  r"hello \w+|hi|hello|ko|se|tak|ke din|i have|i'?ve got|i have got|i got|there is|there'?s|there are|"
                  r"we have|we'?ve got|mujhe|mera|meri|mere|my|our|your|the|a|an|one|ek|apna|apni|is|are|hai|toh|to|"
                  r"this is (?:a|to) (?:reminder|inform you|remind you)(?: that)?|please note(?: that)?|"
                  r"(?:i|we) (?:just )?(?:wanted to )?(?:tell|say|inform|let)\w*(?: you)?(?: know)?(?: that)?)\b[\s,:\-–—]*)+",
                  re.I)
STOP = {"my", "our", "your", "the", "a", "an", "have", "has", "had", "got", "is", "are", "am", "i", "we", "that", "this",
        "because", "since", "as", "so", "and", "but", "for", "of", "to", "in", "on", "at", "with", "mera", "meri", "mere",
        "mujhe", "ki", "kyunki", "aur", "hai", "hain", "ek", "there", "there's", "it", "its", "it's", "about", "going",
        "be", "will", "ko", "se", "tak", "also", "then", "when", "attend", "give", "take", "write", "appear", "need",
        "important", "big", "very", "really", "one", "another", "some", "any", "kal", "aaj", "tomorrow", "today"}
SUFFIX = re.compile(r"^\s+((?:at|with|to|for|of|in)\s+(?:(?:the|my|our)\s+)?[\w&.'-]+(?:\s+[\w&.'-]+){0,3})")
PROMO = re.compile(r"\b(?:sale|% ?off|discount|deal|coupon|cashback|newsletter|unsubscribe|limited time|offer ends|"
                   r"shop now|buy now|free trial|flash|promo|black friday|save up to|digest|weekly roundup)\b", re.I)
STARTS = re.compile(r"\b(?:starts?|starting|begins?|beginning|from|onwards|shuru|se)\b", re.I)


@dataclass
class Item:
    what: str                       # "exams", "interview at Orbit Labs" — as he said it, cleaned
    kind: str
    when: datetime                  # the day at 00:00, or the exact time when has_time
    has_time: bool
    confidence: float
    source: str = "said"            # said | mail | document | llm
    label: str | None = None        # mail sender / document title
    heard: str = ""
    meta: dict = field(default_factory=dict)        # mine · starts · plural

    @property
    def key(self) -> str:
        """Same thing, same day → same key, whoever mentioned it (dedup: never asked twice)."""
        words = sorted(set(re.findall(r"[a-z]{3,}", self.what.lower())) - STOP)
        return hashlib.sha1(f"{self.kind}|{self.when:%Y-%m-%d}|{' '.join(words)}".encode()).hexdigest()[:20]


def _clauses(sent: str) -> list[str]:
    return [c for c in re.split(r"\s*(?:,|;|\band\b|\bbut\b|\baur\b|\blekin\b|\bpar\b|\bso\b|\bbecause\b|\bkyunki\b)\s*",
                                sent) if c.strip()]


def _nouns(text: str) -> list[tuple[str, re.Match]]:
    """Event words in the text, in reading order (a verb that looks like one is skipped)."""
    out = []
    for kind, rx in _NOUN_RX:
        for m in rx.finditer(text):
            if _VERBISH.search(text[:m.start()]):
                continue
            if m[0].lower().startswith("paper") and not re.search(r"\b(?:my|mera|meri|our|ka|ke|ki)\s+$", text[:m.start()],
                                                                  re.I):
                continue                            # "mera paper hai" is an exam; "a paper on AI" is not
            out.append((kind, m))
    return sorted(out, key=lambda x: x[1].start())


def _phrase(text: str, head: re.Match) -> str:
    """The head word with the words that belong to it: "DBMS assignment submission", "interview at Orbit Labs"."""
    before = text[:head.start()].split()
    mods: list[str] = []
    of, whose = False, re.match(r"birthday|b'?day|janamdin|anniversar|wedding|shaadi", head[0], re.I)
    for w in reversed(before[-4:]):
        bare = w.strip(",.:;!()\"'").lower()
        if bare in ("ka", "ke", "ki"):
            of = True                               # "DBMS ka exam" → "DBMS exam" · "Mummy ka birthday" → "Mummy's birthday"
            continue
        if bare in STOP or not bare or len(mods) >= 3:
            break
        mods.insert(0, w.strip(",.:;!()\"'") + ("'s" if of and whose and not bare.endswith("'s") else ""))
        of = False
    word = HEAD_SAY.get(head[0].lower(), head[0])
    suffix = ""
    tail = SUFFIX.match(text[head.end():])          # "interview at Orbit Labs", "deadline for the scholarship form"
    if tail and not re.match(r"(?:in|for|at|to|of|with)\s+(?:the\s+)?(?:morning|evening|afternoon|night|\d+|next|this)\b",
                             tail[1], re.I):
        kept = LINK.sub("", " " + tail[1]).strip()
        if len(kept.split()) >= 2:
            suffix = " " + kept
    out = re.sub(r"\s+", " ", " ".join(mods + [word]) + suffix).strip(" ,.:;-")
    return out[:60]


def _one(sent: str, now: datetime, source: str) -> Item | None:
    s = sent.strip()
    if len(s) < 6 or QUESTION.search(s) or (source == "said" and COMMAND.search(s)):
        return None
    days = dates.find_days(s, now, loose=True)
    nouns = _nouns(s)
    if not days:
        return None
    verb = None
    if not nouns:
        for d in days:
            verb = VERB_RX.search(s[:d.start])
            if verb:
                days = [d]
                break
        if not verb:
            return None
    # the clause that holds the event word decides tense / negation ("I haven't studied, and my exams start on the 9th")
    anchor = verb.start() if verb else nouns[0][1].start()
    pos, clause = 0, s
    for c in _clauses(s):
        at = s.find(c, pos)
        if at <= anchor < at + len(c):
            clause = c
            break
        pos = at + len(c)
    scope = clause if dates.find_days(clause, now, loose=True) else s
    if PAST.search(scope) or UNSURE.search(scope) or REPEATS.search(scope):
        return None                                 # (a weekly thing is a routine, not a date to book)
    # the day: the one nearest after the event word, else the nearest before it
    after = [d for d in days if d.start >= anchor]
    day = after[0] if after else days[-1]
    if day.day < now.date():
        return None
    rest = s[:day.start] + " " + s[day.end:]
    clock = dates.clock_in(rest)
    when = datetime(day.day.year, day.day.month, day.day.day, *(clock or (0, 0)), tzinfo=CFG.tz)
    if (clock and when < now + SOON) or (not clock and day.day <= now.date()):
        return None
    if verb:
        kind = "bill" if verb["verb"].lower() in ("pay", "renew") else "deadline"
        what = LEAD.sub("", verb["obj"]).strip(" ,.") or verb["obj"].strip()
        mine, others, linked = True, False, True
    else:
        before = [n for n in nouns if n[1].start() < day.start]
        pool = before or nouns
        kind = next(k for k, _ in _NOUN_RX if any(k == nk for nk, _ in pool))      # the most specific kind present
        head = [m for k, m in pool if k == kind][-1]
        side = s[:day.start] if before else s[day.end:]
        off = 0 if before else day.end
        hm = re.compile(re.escape(head[0])).search(side, max(0, head.start() - off))
        cut = side if not before else LINK.sub("", side)
        if hm is None or hm.end() > len(cut):
            cut, hm = side, re.search(re.escape(head[0]), side)
        what = _phrase(cut, hm) if hm else head[0]
        mine = bool(MINE.search(scope))
        others = bool(OTHERS.search(s[:head.start()])) and not re.search(rf"\b{FAMILY}(?:'s| ka| ki| ke)\s+(?:\w+\s+)?$",
                                                                       s[:head.start()], re.I)
        linked = bool(re.search(r"\b(?:is|are|on|by|from|starts?|begins?|due|scheduled|held|hai|hain|se|ko|tak|till|"
                                r"until|before)\b", s[min(head.end(), day.start):max(head.end(), day.start)] or scope, re.I))
    what = re.sub(r"^(?:my|our|the|a|an|mera|meri|mere)\s+", "", what.strip(), flags=re.I)
    if len(what) < 3 or (source == "said" and mine and re.fullmatch(r"(?:birthday|b'?day|janamdin)", what, re.I)):
        return None                                 # his own birthday is a fact about him, not something to remind him of
    family = bool(re.match(rf"{FAMILY}(?:'s)?\b", what, re.I))
    conf = 0.5 if kind in WEAK else 0.6
    if source == "said":
        conf += 0.15 if (mine or family) else 0.0
        conf -= 0.2 if others and kind not in ("birthday", "event") else 0.0
    else:
        conf += 0.1                                 # a mail / document that names a date for it was written about it
    conf += 0.1 if linked else 0.0
    conf += 0.05 if day.exact else -0.1 if s[day.start:day.end].lower().endswith((" ko", " se", " tak")) else 0.0
    conf += 0.05 if clock else 0.0
    plural = bool(re.search(r"(?<!s)s$", what.split(" at ")[0].split(" with ")[0].split()[-1])) and kind != "result" \
        or what.lower().split()[-1] in ("results", "fees")
    span = s[min(anchor, day.start):max(anchor, day.end) + 12]
    return Item(what=what, kind=kind, when=when, has_time=bool(clock), confidence=round(min(conf, 0.95), 2),
                source=source, heard=s[:200],
                meta={"mine": bool(mine or family) and not others, "plural": plural,
                      "starts": kind == "exam" and bool(STARTS.search(span)) and not re.search(r"\bon\b", span[:day.start], re.I)})


def detect(text: str, now: datetime | None = None, source: str = "said", label: str | None = None) -> list[Item]:
    """Every thing that matters in this text (best first). Pure: no database, no network."""
    now = now or datetime.now(CFG.tz)
    out: dict[str, Item] = {}
    for sent in re.split(r"(?<=[.!?;])\s+|\n+", text or ""):
        try:
            it = _one(sent, now, source)
        except Exception as e:                      # a regex slip must never break a turn
            print(f"[notice] {type(e).__name__}: {e}")
            it = None
        found = [it] if it is not None else []
        if it is not None and len(dates.find_days(sent, now, loose=True)) > 1:
            for c in _clauses(sent):                # "my exam is on the 9th and the interview is on the 12th"
                try:
                    more = _one(c, now, source)
                except Exception:
                    more = None
                if more is not None and more.when.date() != it.when.date():
                    found.append(more)
        for it in found:
            it.label = label
            if it.key not in out or out[it.key].confidence < it.confidence:
                out[it.key] = it
    return sorted(out.values(), key=lambda i: -i.confidence)


def from_mail(sender: str, subject: str, snippet: str = "", now: datetime | None = None) -> list[Item]:
    """A mail is UNTRUSTED text: it is only pattern-matched here — never obeyed, never sent to an LLM. Sales and
    newsletters are dropped; the subject is read first, then the first lines."""
    subject = re.sub(r"^\s*(?:(?:re|fwd?|fw)\s*:\s*)+", "", subject or "", flags=re.I)
    if PROMO.search(f"{sender} {subject} {snippet[:200]}"):
        return []
    items = detect(subject, now, "mail", clean(sender, 40)) or detect(snippet[:400], now, "mail", clean(sender, 40))
    for it in items:
        it.what, it.heard = clean(it.what, 60), clean(subject, 120)
    return [it for it in items[:1] if it.what]


def clean(s: str, n: int = 60) -> str:
    """Untrusted words she may say aloud: plain characters only, no links, short."""
    s = re.sub(r"https?://\S+|www\.\S+|<[^>]*>", " ", s or "")
    s = re.sub(r"[^\w\s'’&.,:/()\-]", " ", s)
    return re.sub(r"\s+", " ", s).strip(" .,:-")[:n].strip()
