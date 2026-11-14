""""Ask me questions": a get-to-know-you round of 10 questions — no LLM, the brain learns (D37).

He says "ask me questions" / "get to know me better" / "mujhse sawaal pucho" / "nannu prashnalu adugu" and she asks
10 questions he hasn't answered yet, one per turn, round-robin across ~20 categories (dreams, anime, favourite
characters, shows, music, food, people he admires, what annoys him, values, fears …) so a round feels varied.
Each answer gets a short warm reflection (motivational-interviewing OARS: reflect, then the next question) and is
written straight into the brain, deterministically:
  - his words as a high-importance episode (the night job can extract more later),
  - a current self-fact per question key (`about_<key>`), superseding an older answer instead of duplicating,
  - names (anime, characters, shows, artists, places …) as entities linked to that fact, so recall finds them,
  - a user_directive where the answer is about how to talk to him or a boundary,
then the standing profile + USER.md are rebuilt so the very next LLM turn already knows it.
"skip"/"pass" skips · "bas"/"later"/"stop" pauses (saying it again continues the round) · "why?" explains.
Saying it again later → the next 10 unanswered. Bank exhausted → re-ask the oldest answers ("Still the same?").
Worries/fears are gentle, skippable, private (P2: never in the cloud briefing, never echoed back).
Research basis: research_notes/Key things to know intake/intake_research.md §5, §7, §9.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta

from ..config import CFG
from ..db import one, q

STATE = CFG.home / "askme.json"
ROUND = 10

# ---- triggers (English, Hinglish, a little Telugu) ----
_NOT_ABOUT_ME = r"(?!\s+(?:about|on|from|regarding)\s+(?!me\b|myself\b))(?!\s+(?:later|tomorrow|after|baad))"
START_RX = re.compile(
    rf"\bask me (?:some |a few |a couple of |few |more |\d+ |ten |a bunch of )?(?:more |random )?"
    rf"(?:questions?|something|anything|stuff)\b{_NOT_ABOUT_ME}|"
    r"\b(?:get(?:ting)? to )?(?<!\bi )know me better\b|"
    r"\bquiz me about (?:myself|me)\b|"
    r"^\W*(?:let'?s do |start |do )?(?:the )?key things\W*$|"            # what USER.md / the web memory page tell him to say
    r"\bmujh(?:se|e) (?:kuch |koi |\d+ |das |kuch aur )?(?:sawaal|sawal|savaal|questions?) (?:pucho|poocho|puchho|karo)\b|"
    r"\bmujh(?:se|e) kuch (?:pucho|poocho|puchho)\b|"
    r"\b(?:kuch|koi sawaal|koi sawal|sawaal|sawal) (?:pucho|poocho|puchho) (?:na )?mujh(?:se|e)\b|"
    r"\bnannu (?:emaina |konni |inka )?(?:prashnalu |questions )?adugu\b|\bnaa gurinchi telusuko\b|"
    r"నన్ను.{0,20}అడుగు",
    re.I)
SKIP_RX = re.compile(r"^\W*(skip|pass|next|next one|chhodo|chodo|aage|rehne do|agla|move on)\b", re.I)
PAUSE_RX = re.compile(r"^\W*(bas|stop|later|baad mein|ruk|ruko|pause|enough|that'?s enough|bas karo|aur nahi|"
                      r"that'?s (it|all)( for now)?|chalo bas|let'?s stop|stop asking)\b", re.I)
WHY_RX = re.compile(r"^\W*(why|kyun|kyu|kyon|why do you ask|why (that|this)|ye kyun|enduku)\W*$", re.I)
REPEAT_RX = re.compile(r"^\W*(what|huh|sorry|come again|say (that|it) again|repeat( that)?|kya|kya bola|phir se|"
                       r"one more time|pardon)\W*$", re.I)
NOTHING_RX = re.compile(r"^\W*(nothing( really| much| as such)?|none|no idea|not sure|i'?m not sure|(i )?don'?t know|"
                        r"dunno|idk|pata nahi|nahi pata|kuch nahi|kuch bhi nahi|no one|nobody|nah|nope|no|not really|"
                        r"can'?t think of (any|anything|one|anyone)|haven'?t thought about it)\W*$", re.I)
BARE_RX = re.compile(r"^\W*(ok|okay|hmm+|yes|yeah|yep|haan|han|sure|right|achha|acha|accha|cool)\W*$", re.I)
STILL_RX = re.compile(r"^\W*(yes|yeah|yep|yup|haan|han|ha|still|same|still (true|same|the same)|abhi bhi|of course|ofc|"
                      r"definitely|totally|correct|right|true|sahi|bilkul|pretty much)\b", re.I)
CHANGED_RX = re.compile(r"^\W*(no|nope|nah|nahi|not anymore|not really|changed)\b[\s,.!]*(now|ab|these days)?[\s,]*",
                        re.I)
# commands said in the middle of a round: the round pauses and the command runs as usual (engine.py)
ASIDE_RX = re.compile(r"^\W*(?:hey stiti[, ]+)?(set (an? |the )?(alarm|reminder|timer)|add\b|remind me|cancel|delete|"
                      r"show me|list my|what('?s| is) the time|what time is it|turn (on|off)|open (the )?whiteboard)", re.I)
FILLER_RX = re.compile(r"\b(u+m+|u+h+m*|h+m+|erm|uhh?|i think|i guess|i'?d say|i would say|mostly|probably|honestly|"
                       r"basically|actually|to be honest|tbh|you know|i mean|matlab|yaar)\b[,.]?|\blike,", re.I)
LEAD_RX = re.compile(r"^\W*(so|and|toh|bas|well|oh|ah|okay so|ok so|hmm so|see)\b[,\s]*", re.I)


@dataclass(frozen=True)
class Q:
    key: str
    cat: str
    ask: str
    fact: str                    # "{name}'s favourite anime: {a}" — {a} his answer (third person), {name} the owner
    say: str = ""                # second person for acks / summary / refresh: "you're into {a}"
    items: str | None = None     # entity kind for the names in the answer (topic / place) — None = free text
    item_fact: str = ""          # "{item} is one of {name}'s favourite anime"
    directive: tuple[str, str] | None = None   # (category, "template {a}") — about how to talk to him / a boundary
    char: bool = False           # "Zoro from One Piece, for his loyalty" → character, show, reason
    want: bool = False           # "I want to build an AI company" → "you want to build an AI company"
    summary: bool = True         # good enough to read back at the end of the round
    sensitive: bool = False      # P2: never leaves the Mac, never echoed, gentle lead, no re-ask for 30 days
    proper: bool = True          # list items are names (title-case "one piece") — False for "biryani", "guitar"


WHY = {
    "ambition": "Your dreams tell me what to push you towards.",
    "now": "So I can keep you on track with what you actually want right now.",
    "anime": "So I know what you're into — and can talk about it like a friend would.",
    "characters": "Who you like says a lot about what you value.",
    "fears": "Only so I can be gentle about it. It stays on this Mac, and you can skip it.",
    "talk": "So I talk to you the way you like, not the way some app does.",
    "annoys": "So I never become one of those things.",
}
WHY_DEFAULT = "So I know you as a person, not just your to-dos. It all stays on this Mac."

BANK: list[Q] = [
    # ambitions & dreams
    Q("ambition_big", "ambition", "What's your biggest dream — the thing you'd love to pull off one day?",
      "{name}'s big dream: {a}", "{a}", want=True),
    Q("ambition_5y", "ambition", "Where do you see yourself in five years, roughly?",
      "Where {name} sees {obj}self in five years: {a}", "five years from now: {a}", summary=False),
    Q("ambition_impact", "ambition", "What kind of difference do you want to make for people?",
      "The difference {name} wants to make for people: {a}", "you want to make this difference: {a}", summary=False),
    # anime
    Q("anime_fav", "anime", "What are your all-time favourite anime?",
      "{name}'s favourite anime: {a}", "you're into {a}", items="topic",
      item_fact="{item} is one of {name}'s favourite anime"),
    Q("anime_now", "anime", "Which anime are you watching these days?",
      "{name} is watching (anime): {a}", "you're watching {a}", items="topic",
      item_fact="{item} is an anime {name} is watching"),
    Q("anime_rec", "anime", "Which anime would you make a friend watch first?",
      "{name} would recommend (anime): {a}", "you'd make a friend watch {a}", items="topic",
      item_fact="{item} is an anime {name} recommends"),
    # favourite characters
    Q("char_fav", "characters", "Who's your favourite anime character, and why?",
      "{name} likes {a}", "you like {a}", items="topic", item_fact="{item} is a character {name} likes", char=True),
    Q("char_relate", "characters", "Which character do you relate to the most?",
      "{name} relates most to {a}", "you relate to {a}", items="topic",
      item_fact="{item} is a character {name} relates to", char=True),
    Q("char_lookup", "characters", "Any character from a show, movie or book you really look up to — kaun, and why?",
      "{name} looks up to the character {a}", "you look up to {a}", items="topic",
      item_fact="{item} is a character {name} looks up to", char=True),
    # what he wants right now
    Q("now_month", "now", "What do you want to get done this month?",
      "{name}'s goal this month: {a}", "this month {a}", want=True),
    Q("now_year", "now", "What's the one thing that would make this year a win for you?",
      "What would make this year a win for {name}: {a}", "this year is a win if: {a}", summary=False),
    Q("now_want", "now", "What's something you really want right now — big or small?",
      "Something {name} really wants right now: {a}", "right now {a}", want=True),
    # shows & movies
    Q("shows_now", "shows", "What shows are you binge-watching right now?",
      "{name} is watching (shows): {a}", "you're binging {a}", items="topic",
      item_fact="{item} is a show {name} is watching"),
    Q("movies_fav", "shows", "Favourite movies — the ones you can rewatch anytime?",
      "{name}'s favourite movies: {a}", "you can rewatch {a} anytime", items="topic",
      item_fact="{item} is one of {name}'s favourite movies"),
    # motivation
    Q("motiv_what", "motivates", "What really gets you going — what makes you want to work hard?",
      "What motivates {name}: {a}", "what drives you: {a}", summary=False),
    Q("motiv_low", "motivates", "When you're feeling lazy, what actually gets you moving again?",
      "What gets {name} moving when lazy: {a}", "when you're lazy, this works: {a}", summary=False,
      directive=("preference", "When {subj} feels lazy, what gets {obj} moving: {a}")),
    # music
    Q("music_now", "music", "What music is on repeat for you lately?",
      "{name}'s music on repeat: {a}", "you've got {a} on repeat", items="topic",
      item_fact="{item} is music {name} has on repeat"),
    Q("music_artist", "music", "Favourite artist or band?",
      "{name}'s favourite artists: {a}", "you love {a}", items="topic",
      item_fact="{item} is one of {name}'s favourite artists"),
    # people he admires
    Q("admire_who", "admire", "Who do you really admire — real people, anyone?",
      "{name} admires: {a}", "you admire {a}", items="topic", item_fact="{item} is someone {name} admires"),
    Q("admire_quality", "admire", "What's one quality you admire most in people?",
      "Quality {name} admires most in people: {a}", "you value {a} in people"),
    # food
    Q("food_fav", "food", "Comfort food — what could you eat any day?",
      "{name}'s comfort food: {a}", "your comfort food is {a}", items="topic",
      item_fact="{item} is {name}'s comfort food", proper=False),
    Q("food_hate", "food", "And a food you just can't stand?",
      "{name} can't stand (food): {a}", "you can't stand {a}", items="topic",
      item_fact="{item} is a food {name} can't stand", summary=False, proper=False),
    # learning
    Q("learn_next", "learn", "What do you want to learn next?",
      "{name} wants to learn: {a}", "you want to learn {a}", items="topic",
      item_fact="{item} is something {name} wants to learn", proper=False),
    Q("learn_skill", "learn", "If you could master one skill overnight, what would it be?",
      "Skill {name} would master overnight: {a}", "you'd master {a} overnight"),
    # games
    Q("games_fav", "games", "Do you game — which ones are your favourites?",
      "{name}'s favourite games: {a}", "you play {a}", items="topic",
      item_fact="{item} is one of {name}'s favourite games"),
    Q("games_now", "games", "What are you playing these days, if anything?",
      "{name} is playing (games): {a}", "you're playing {a}", items="topic",
      item_fact="{item} is a game {name} is playing"),
    # values
    Q("values_top", "values", "What matters most to you in life — top two or three things?",
      "What matters most to {name}: {a}", "what matters most to you: {a}"),
    Q("values_never", "values", "What's something you'd never compromise on?",
      "{name} would never compromise on: {a}", "you'd never compromise on {a}", summary=False),
    # places
    Q("places_go", "places", "Which place do you most want to travel to?",
      "Places {name} wants to go: {a}", "you want to go to {a}", items="place",
      item_fact="{item} is a place {name} wants to visit"),
    Q("places_loved", "places", "Which place have you been to that you loved?",
      "Places {name} loved visiting: {a}", "you loved {a}", items="place",
      item_fact="{item} is a place {name} loved visiting"),
    # career
    Q("career_dream", "career", "What's your dream job or role?",
      "{name}'s dream job: {a}", "your dream job is {a}"),
    Q("career_enjoy", "career", "What part of your work or studies do you enjoy the most?",
      "What {name} enjoys most in work or studies: {a}", "you enjoy {a} the most", summary=False),
    Q("career_good", "career", "What are you really good at — the thing people come to you for?",
      "What {name} is good at: {a}", "people come to you for {a}"),
    # relaxing
    Q("relax_how", "relax", "How do you usually relax after a long day?",
      "How {name} relaxes after a long day: {a}", "to unwind, {a}", summary=False),
    Q("relax_sunday", "relax", "What does a perfect lazy Sunday look like for you?",
      "{name}'s perfect lazy Sunday: {a}", "a lazy Sunday for you: {a}", summary=False),
    # books
    Q("books_fav", "books", "Any book that really stuck with you?",
      "{name}'s favourite books: {a}", "{a} stuck with you", items="topic",
      item_fact="{item} is a book that stuck with {name}"),
    Q("books_now", "books", "Reading anything right now — book, manga, anything?",
      "{name} is reading: {a}", "you're reading {a}", items="topic", item_fact="{item} is something {name} is reading"),
    # a perfect day
    Q("day_perfect", "day", "Describe your perfect day, start to finish.",
      "{name}'s perfect day: {a}", "your perfect day: {a}", summary=False),
    Q("day_best", "day", "What was the best day you've had recently?",
      "A recent best day for {name}: {a}", "a recent best day: {a}", summary=False),
    # what annoys him
    Q("annoy_most", "annoys", "What annoys you the most — your biggest pet peeve?",
      "{name}'s biggest pet peeve: {a}", "your pet peeve: {a}", summary=False),
    Q("annoy_talk", "annoys", "What's one thing people do while talking to you that irritates you?",
      "What irritates {name} when people talk to {obj}: {a}", "it irritates you when people {a}", summary=False,
      directive=("talk_style", "Never do this, it irritates {obj} when people talk to {obj}: {a}")),
    # sports
    Q("sports_play", "sports", "Do you play or follow any sport?",
      "{name}'s sports: {a}", "you're into {a}", items="topic", item_fact="{item} is a sport {name} plays or follows", proper=False),
    Q("sports_fav", "sports", "Favourite team or player?",
      "{name}'s favourite team or player: {a}", "you support {a}", items="topic",
      item_fact="{item} is {name}'s favourite team or player"),
    # how to talk to him / boundaries → directives
    Q("talk_wrong", "talk", "If I get something wrong, should I just fix it, or explain what happened?",
      "", "when I get something wrong: {a}", summary=False,
      directive=("talk_style", "When Stiti gets something wrong: {a}")),
    Q("talk_win", "talk", "When you share a win, should I hype you up or keep it chill?",
      "", "when you share a win: {a}", summary=False, directive=("talk_style", "When {subj} shares a win: {a}")),
    Q("talk_never", "talk", "Anything you never want me to joke about or bring up?",
      "", "never joke about {a}", summary=False, directive=("boundary", "Never joke about or bring up: {a}")),
    # worries / fears — gentle, skippable, private
    Q("fear_worry", "fears", "What's been on your mind or worrying you lately?",
      "What's been worrying {name} lately: {a}", "", summary=False, sensitive=True),
    Q("fear_scared", "fears", "Is there something you're scared of — big or small?",
      "{name} is scared of: {a}", "", summary=False, sensitive=True),
]
BY_KEY = {x.key: x for x in BANK}
# fun and deep interleaved, so every round of 10 mixes them; fears last
CAT_ORDER = ["anime", "ambition", "characters", "now", "shows", "motivates", "music", "admire", "food", "learn",
             "games", "values", "places", "career", "relax", "books", "day", "annoys", "sports", "talk", "fears"]

ACKS = {
    "anime": ["{s} — good taste.", "Ooh, {s}. Mast.", "{s}, noted."],
    "characters": ["Ah, {s}. Makes sense.", "{s} — I like that.", "Got it, {s}."],
    "shows": ["{s} — nice.", "Ooh, {s}. Noted."],
    "music": ["{s} — nice.", "Noted, {s}."],
    "ambition": ["{s}. Love that.", "{s} — that's a big one. Noted."],
    "now": ["{s}. Got it, I'll keep that in mind.", "Noted — {s}."],
    "food": ["{s} — solid.", "Noted, {s}."],
    "fears": ["Thanks for telling me. That stays with me.", "Okay. Thank you for sharing that."],
    "talk": ["Okay, I'll do that.", "Got it, noted."],
}
ACK_DEFAULT = ["Got it — {s}.", "Badhiya. {s}.", "Okay, {s}. Noted."]
ACK_LONG = ["Love that. Noted.", "Got it, noted.", "Okay, that's a good one. Noted."]


# ---------------- text helpers (no LLM) ----------------
def clean(text: str) -> str:
    """Strip fillers ("umm", "I think", "mostly"), keep his words."""
    t = FILLER_RX.sub(" ", text)
    t = re.sub(r"\s+", " ", t)
    for _ in range(3):
        t = LEAD_RX.sub("", t.strip(" ,"))
    t = re.sub(r"\s+([,.!?])", r"\1", t)
    t = re.sub(r"(^[,.\s]+)|([,\s]+$)", "", t)
    return t.strip().rstrip(".!")


def _hinglish(t: str) -> bool:
    from .strategy import is_hinglish
    return is_hinglish(t)


def _swap(t: str, table: list[tuple[str, str]]) -> str:
    def rep(m: re.Match) -> str:
        w = m.group(0)
        for pat, out in table:
            if re.fullmatch(pat, w, re.I):
                return out
        return w
    rx = "|".join(rf"\b{p}\b" for p, _ in table)
    return re.sub(rx, rep, t, flags=re.I)


def second(t: str) -> str:
    """His words, said back to him: "I want to build my company" → "you want to build your company"."""
    if _hinglish(t):
        return t
    return _swap(t, [(r"i'?m", "you're"), (r"i am", "you are"), (r"i'?ve", "you've"), (r"i'?d", "you'd"),
                     (r"i'?ll", "you'll"), (r"i was", "you were"), (r"myself", "yourself"), (r"mine", "yours"),
                     (r"my", "your"), (r"me", "you"), (r"i", "you")])


def third(t: str) -> str:
    """His words for a fact about him: "my own company" → "his own company"."""
    if _hinglish(t):
        return t
    from .. import profile
    s, o, p, be = profile.p("subj"), profile.p("obj"), profile.p("poss"), profile.p("be")
    has = "have" if s == "they" else "has"
    return _swap(t, [(r"i'?m", f"{s} {be}"), (r"i am", f"{s} {be}"), (r"i'?ve", f"{s} {has}"), (r"i'?d", f"{s}'d"),
                     (r"i'?ll", f"{s}'ll"), (r"myself", "themselves" if s == "they" else f"{o}self"),
                     (r"mine", f"{p}s" if p != "his" else "his"), (r"my", p), (r"me", o), (r"i", s)])


_ITEM_LEAD = re.compile(r"^\W*(now|ab|nowadays|i'?m (watching|reading|playing|into|listening to)|i (watch|read|play|like|love|follow|"
                        r"listen to|admire|support|enjoy)|i'?d (say|go with|pick)|i really like|definitely|obviously|"
                        r"currently|right now|these days|lately|abhi|recently|mainly|for sure|has to be|it'?s|its)\b"
                        r"[\s,:]*", re.I)
_ITEM_STOP = {"nothing", "stuff", "things", "anything", "all", "many", "lots", "a lot", "everything", "etc", "more",
              "and more", "others", "so on", "too", "many more", "some"}
_SMALL = {"of", "the", "a", "an", "on", "in", "no", "to", "and", "with", "for", "at", "is", "ka", "ki", "ke"}


def _title(x: str) -> str:
    if x != x.lower():
        return x                                     # he (or STT) already cased it: keep it
    ws = x.split()
    return " ".join(w if (i and w in _SMALL) else w[:1].upper() + w[1:] for i, w in enumerate(ws))


def items(text: str, proper: bool = True) -> list[str]:
    """Names in a list answer: "umm mostly Vinland Saga and one piece, also Frieren" → [Vinland Saga, One Piece, Frieren]."""
    t = text
    for _ in range(2):
        t = _ITEM_LEAD.sub("", t.strip())
    out: list[str] = []
    for part in re.split(r"[,;/&]|\band\b|\baur\b|\bplus\b|\balso\b|\bor\b|\bthen\b", t, flags=re.I):
        x = _ITEM_LEAD.sub("", part.strip(" .!-:'\""))
        x = re.sub(r"\s+(too|as well|for sure|obviously|definitely|bhi)$", "", x, flags=re.I).strip(" .!-:'\"")
        if not x or x.lower() in _ITEM_STOP or len(x) < 2 or len(x.split()) > 5:
            continue
        x = _title(x) if proper else x
        if x.lower() not in (o.lower() for o in out):
            out.append(x)
    return out[:5]


def _join(xs: list[str], last: str = " and ") -> str:
    return xs[0] if len(xs) == 1 else ", ".join(xs[:-1]) + last + xs[-1]


def _caps(s: str) -> str:
    """Every sentence starts with a capital ("Nice. your friends …" → "Nice. Your friends …")."""
    return re.sub(r"(^|[.!?]\s+)([a-z])", lambda m: m.group(1) + m.group(2).upper(), s)


_REASON = re.compile(r"\s*[,]?\s*\b(because|cause|'cause|coz|cuz|since|kyunki|kyuki|for)\b\s*", re.I)
_CHAR_LEAD = re.compile(r"^\W*(my favou?rite( character)? (is|would be)|i'?d (say|go with|pick)|i (like|love|relate to|"
                        r"look up to)|definitely|obviously|has to be|it'?s|probably)\b[\s,:]*", re.I)


def character(text: str) -> tuple[list[str], str | None, str]:
    """ "Zoro from One Piece, for his loyalty" → (["Zoro"], "One Piece", "for his loyalty")."""
    t = text
    for _ in range(2):
        t = _CHAR_LEAD.sub("", t.strip())
    reason = ""
    m = _REASON.search(t)
    if m and m.start() > 0:
        word = m.group(1).lower()
        word = "because" if word in ("cause", "'cause", "coz", "cuz", "kyunki", "kyuki", "since") else word
        reason = f"{word} {t[m.end():].strip(' .')}".strip()
        t = t[:m.start()]
    show = None
    sm = re.search(r"\s*\((?P<s>[^)]+)\)|\s+\b(?:from|in|of)\b\s+(?P<s2>.+)$", t, re.I)
    if sm:
        show = _title((sm.group("s") or sm.group("s2") or "").strip(" .,"))
        t = t[:sm.start()]
    names = [_title(x.strip(" .,'\"")) for x in re.split(r",|\band\b|\baur\b|&", t, flags=re.I)]
    names = [x for x in names if x and len(x.split()) <= 4 and x.lower() not in _ITEM_STOP]
    return names[:3], show or None, reason


_VERBS = set("""build start become make get crack learn go travel finish buy own run create open launch be have work move
live earn write clear pass join lose gain achieve help visit see meet find land ship grow save retire play win
""".split())
_WANT_LEAD = re.compile(r"^\W*(i (really )?(want|wanna|need|would like|'?d like|'?d love|would love|hope|plan|dream)"
                        r"( to| of)?|my (dream|goal|plan|aim) is( to)?|to)\b\s*", re.I)


def _want(a: str) -> tuple[str, str]:
    """(fact value, "you want …" phrase) for want-style answers."""
    m = _WANT_LEAD.match(a)
    v = a[m.end():] if m else a
    v = v.strip() or a
    first = v.split()[0].lower() if v.split() else ""
    you = f"you want to {second(v)}" if (first in _VERBS or (m and m.group(0).strip().lower().endswith("to"))) \
        else f"you want {second(v)}"
    return v, you


def _short(s: str, n: int = 8) -> str | None:
    """Something short enough to echo back by voice, or None (then the ack doesn't echo)."""
    first = re.split(r"[,;]|\bbecause\b|\bkyunki\b", s)[0].strip()
    return first if len(first.split()) <= n else None


# ---------------- state ----------------
def _state() -> dict:
    try:
        return json.loads(STATE.read_text()) if STATE.exists() else {}
    except Exception:
        return {}


def _save(st: dict) -> None:
    STATE.write_text(json.dumps(st))


def _me() -> int:
    from .. import profile
    from .sleep import resolve_entity
    return resolve_entity(profile.name(), "self")


def answered() -> set[str]:
    """Keys he has ever answered (a fact or directive exists, even if later edited or superseded)."""
    me = _me()
    preds = [f"about_{x.key}" for x in BANK]
    got = {r["predicate"][6:] for r in q("SELECT DISTINCT predicate FROM facts WHERE subj_id=%s AND predicate = ANY(%s)",
                                         (me, preds))}
    keys = [f"ask_{x.key}" for x in BANK if x.directive]
    got |= {r["supersession_key"][4:] for r in q(
        "SELECT DISTINCT supersession_key FROM user_directives WHERE supersession_key = ANY(%s)", (keys,))}
    return got


def _oldest_answers(n: int, exclude: set[str]) -> list[str]:
    me = _me()
    rows = q("""SELECT predicate FROM facts WHERE subj_id=%s AND predicate = ANY(%s) AND upper_inf(recorded)
                AND valid @> now() ORDER BY COALESCE((attrs->>'confirmed_at')::timestamptz, lower(valid)), id""",
             (me, [f"about_{x.key}" for x in BANK if not x.sensitive and x.say and x.key not in exclude]))
    return [r["predicate"][6:] for r in rows][:n]


def pick_round(st: dict, n: int = ROUND) -> tuple[list[str], list[str]]:
    """(keys to ask, keys that are refresh re-asks). Round-robin across categories from where the last round stopped."""
    done = answered()
    skipped: dict = st.get("skipped", {})
    now = datetime.now(CFG.tz)

    def later_ok(k: str) -> bool:
        if not BY_KEY[k].sensitive:
            return True
        try:
            return now - datetime.fromisoformat(skipped[k]) > timedelta(days=30)
        except Exception:
            return True

    per_cat = {c: [x.key for x in BANK if x.cat == c and x.key not in done and x.key not in skipped] for c in CAT_ORDER}
    ptr = st.get("cat_ptr", 0) % len(CAT_ORDER)
    picked: list[str] = []
    i = 0
    while len(picked) < n and any(per_cat.values()):
        c = CAT_ORDER[(ptr + i) % len(CAT_ORDER)]
        if per_cat[c]:
            picked.append(per_cat[c].pop(0))
            st["cat_ptr"] = (ptr + i + 1) % len(CAT_ORDER)
        i += 1
    for k in sorted((k for k in skipped if k in BY_KEY and k not in done and k not in picked),
                    key=lambda k: skipped[k]):
        if len(picked) >= n:
            break
        if later_ok(k):
            picked.append(k)
    refresh = _oldest_answers(n - len(picked), set(picked)) if len(picked) < n else []
    picked += refresh
    picked.sort(key=lambda k: BY_KEY[k].sensitive)          # easy first, personal last (Dillman; intake §5)
    return picked, refresh


def _refresh_line(k: str) -> str:
    row = one("""SELECT attrs, fact_text FROM facts WHERE subj_id=%s AND predicate=%s AND upper_inf(recorded)
                 AND valid @> now() ORDER BY id DESC LIMIT 1""", (_me(), f"about_{k}"))
    said = (row and (row["attrs"] or {}).get("said")) or ""
    if not said:
        return BY_KEY[k].ask
    return f"Quick check — {said}. Still the same?"


# ---------------- writing into the brain ----------------
def _rebuild() -> None:
    """The next LLM turn must already know it: standing profile + USER.md."""
    from .mdsync import render_all
    from .sleep import standing_profile
    standing_profile()
    try:
        render_all()
    except Exception as e:                      # a broken USER.md write must never break the flow
        print(f"[askme] render: {e}")


def _close(me: int, pred: str, ts) -> list[int]:
    """End his current answer at `ts` (kept in history, never deleted). Returns the ids that ended."""
    return [r["id"] for r in q("""UPDATE facts SET valid = tstzrange(lower(valid), GREATEST(lower(valid), %s))
                                  WHERE subj_id=%s AND predicate=%s AND upper_inf(recorded) AND valid @> %s::timestamptz
                                  RETURNING id""", (ts, me, pred, ts))]


def _now():
    return one("SELECT now() AS t")["t"]


def _entity(name: str, kind: str) -> int:
    from .sleep import resolve_entity
    return resolve_entity(name, kind)


def store(qn: Q, raw: str, episode_id: int | None = None) -> tuple[str, str]:
    """Write one answer into the brain. Returns (said — second person, short — for the ack or '')."""
    from .. import embed, profile
    a = clean(raw)
    name = profile.name()
    fmt = {"name": name, "subj": profile.p("subj"), "obj": profile.p("obj"), "poss": profile.p("poss")}
    ents: list[tuple[str, str]] = []                 # (name, kind)
    show = None
    if qn.char:
        names, show, reason = character(a)
        if names:
            val = _join(names) + (f" ({show})" if show else "") + (f" {third(reason)}" if reason else "")
            said_val = _join(names) + (f" {second(reason)}" if reason else "")
            short = _join(names) + (f", {second(reason)}" if reason and len(said_val.split()) <= 10 else "")
            ents = [(x, "topic") for x in names]
        else:
            val, said_val, short = third(a), second(a), _short(second(a)) or ""
    elif qn.items:
        its = items(a, qn.proper)
        if its:
            val = said_val = short = _join(its)
            ents = [(x, qn.items) for x in its]
        else:
            val, said_val, short = third(a), second(a), _short(second(a)) or ""
    elif qn.want:
        v, you = _want(a)
        val, said_val, short = third(v), you, _short(you, 10) or ""
    else:
        val, said_val, short = third(a), second(a), _short(second(a)) or ""
    said = qn.say.format(a=said_val) if qn.say else ""
    privacy = 2 if qn.sensitive else 1
    me = _me()
    if episode_id:
        q("UPDATE episodes SET importance = 8, privacy = GREATEST(privacy, %s) WHERE id=%s", (privacy, episode_id))
        q("INSERT INTO episode_mentions VALUES (%s,%s) ON CONFLICT DO NOTHING", (episode_id, me))
    ep_ids = [episode_id] if episode_id else []
    if qn.directive:
        from .sleep import apply_directive
        cat, tmpl = qn.directive
        apply_directive({"directive": tmpl.format(a=third(a), **fmt), "category": cat,
                         "supersession_key": f"ask_{qn.key}"}, ep_ids)
        q("UPDATE user_directives SET origin='ask_me' WHERE status='active' AND supersession_key=%s", (f"ask_{qn.key}",))
    if qn.fact:
        ids = {n: _entity(n, k) for n, k in ents}
        text = qn.fact.format(a=val, **fmt)
        vec = embed.embed_docs([text])[0]
        ts = _now()
        ended = _close(me, f"about_{qn.key}", ts)        # an older answer to the same question ends now (kept)
        new = one("""INSERT INTO facts(subj_id, predicate, obj_id, obj_literal, fact_text, attrs, functional, valid,
                                       confidence, privacy, source_episode_ids, embedding, origin)
                     VALUES (%s,%s,%s,%s,%s,%s,true,tstzrange(%s, NULL),0.95,%s,%s,%s,'ask_me') RETURNING id""",
                  (me, f"about_{qn.key}", ids[ents[0][0]] if ents else None, val, text,
                   json.dumps({"said": said, "answer": a, "question": qn.ask}), ts, privacy, ep_ids, vec))["id"]
        if ended:
            q("UPDATE facts SET invalidated_by=%s WHERE id = ANY(%s)", (new, ended))
        # names → entities, each linked to him (the old answer's links end too), so "Zoro" brings this fact back
        q("""UPDATE facts SET valid = tstzrange(lower(valid), GREATEST(lower(valid), %s)) WHERE predicate=%s
             AND obj_id=%s AND upper_inf(recorded) AND valid @> %s::timestamptz""", (ts, f"in_{qn.key}", me, ts))
        for n, eid in ids.items():
            it = qn.item_fact.format(item=n, **fmt) if qn.item_fact else f"{n} — {text}"
            q("""INSERT INTO facts(subj_id, predicate, obj_id, fact_text, confidence, privacy, source_episode_ids,
                                   embedding, origin) VALUES (%s,%s,%s,%s,0.9,%s,%s,%s,'ask_me')""",
              (eid, f"in_{qn.key}", me, it, privacy, ep_ids, embed.embed_docs([it])[0]))
            for ep in ep_ids:
                q("INSERT INTO episode_mentions VALUES (%s,%s) ON CONFLICT DO NOTHING", (ep, eid))
        if show and ents:
            from .sleep import apply_fact
            for n, _ in ents:
                apply_fact({"subject": n, "predicate": "character_in", "object": show,
                            "fact_text": f"{n} is a character in {show}", "confidence": 0.8}, ep_ids,
                           {n.lower(): "topic", show.lower(): "topic"})
    _rebuild()
    return said, ("" if qn.sensitive else short)


def confirm(k: str) -> None:
    """ "Still the same" → the old answer is fresh again (moves to the back of the refresh queue)."""
    q("""UPDATE facts SET attrs = COALESCE(attrs, '{}'::jsonb) || jsonb_build_object('confirmed_at', now()::text),
                confidence = LEAST(confidence + 0.02, 0.99)
         WHERE subj_id=%s AND predicate=%s AND upper_inf(recorded) AND valid @> now()""", (_me(), f"about_{k}"))


def retire(k: str) -> None:
    """ "Not anymore" with nothing new → it stops being true now (kept in history, never deleted)."""
    ts = _now()
    _close(_me(), f"about_{k}", ts)
    q("""UPDATE facts SET valid = tstzrange(lower(valid), GREATEST(lower(valid), %s)) WHERE predicate=%s
         AND obj_id=%s AND upper_inf(recorded) AND valid @> %s::timestamptz""", (ts, f"in_{k}", _me(), ts))
    _rebuild()


def summary(learned: list[str]) -> str:
    if not learned:
        return "No worries — we'll do this another time."
    pts = learned[:3]
    return f"That's the round. Got it — {_join(pts, ', and ' if len(pts) > 2 else ' and ')}."


def is_aside(text: str) -> bool:
    return bool(ASIDE_RX.match(text))


def active() -> bool:
    st = _state()
    return bool(st.get("active") and st.get("round"))


# ---------------- the flow ----------------
class AskMe:
    def __init__(self):
        self.st = _state()

    def _q(self) -> Q:
        return BY_KEY[self.st["round"][self.st["pos"]]]

    def _ask_line(self) -> str:
        k = self.st["round"][self.st["pos"]]
        if k in self.st.get("refresh", []):
            return _refresh_line(k)
        qn = BY_KEY[k]
        return ("This one's a bit personal, so skip it if you like. " if qn.sensitive else "") + qn.ask

    def start(self) -> tuple[str, bool]:
        """(reply, the round is on)."""
        st = self.st
        if st.get("active") and st.get("round") and st.get("pos", 0) < len(st["round"]):
            return "Okay, picking up where we left off. " + self._ask_line(), True
        first = not st.get("rounds") and not answered()
        keys, refresh = pick_round(st)
        if not keys:
            _save(st)
            return "I've asked you everything for now. Tell me anything new, anytime.", False
        st.update({"round": keys, "refresh": refresh, "pos": 0, "learned": [], "active": True, "nudged": False})
        _save(st)
        n = len(keys)
        if first:
            intro = (f"Chalo, {n} quick questions so I know you better. Say skip to skip one, or bas to stop. "
                     "Pehle fun stuff. ")
        elif len(refresh) == n:
            intro = "You've answered everything once, so let me check what's changed. "
        elif refresh:
            intro = f"Okay, {n - len(refresh)} new ones and a few quick checks on old answers. "
        elif n < ROUND:
            intro = f"Okay, {n} more questions. "
        else:
            intro = f"Okay, {n} new ones. "
        return intro + self._ask_line(), True

    def pause(self) -> None:
        _save(self.st)

    def _ack(self, qn: Q, short: str) -> str:
        n = self.st.get("acks", 0)
        self.st["acks"] = n + 1
        if qn.sensitive:
            opts = ACKS["fears"]
        elif short:
            opts = ACKS.get(qn.cat, ACK_DEFAULT)
        else:
            opts = ACK_LONG
        line = opts[n % len(opts)].format(s=short) if short or qn.sensitive else opts[n % len(opts)]
        return _caps(line.replace("?", "."))

    def answer(self, text: str, episode_id: int | None = None) -> tuple[str, bool]:
        """Returns (reply, finished)."""
        st = self.st
        k = st["round"][st["pos"]]
        qn = BY_KEY[k]
        refresh = k in st.get("refresh", [])
        t = text.strip()
        words = len(t.split())
        if WHY_RX.match(t):
            return f"{WHY.get(qn.cat, WHY_DEFAULT)} {self._ask_line()}", False
        if REPEAT_RX.match(t):
            return f"Sure. {self._ask_line()}", False
        if PAUSE_RX.match(t) and words <= 4:
            _save(st)
            got = len(st.get("learned", []))
            return ("Okay, we'll stop here" + (f" — got {got} new things about you" if got > 1 else "") +
                    ". Say “ask me questions” anytime and I'll pick up from here."), True
        a = clean(t)
        ack = ""
        if refresh:
            if STILL_RX.match(a) and len(a.split()) <= 4:
                confirm(k)
                ack = "Good, still the same then."
            elif SKIP_RX.match(a) or (NOTHING_RX.match(a) and not CHANGED_RX.match(a)):
                ack = "Okay."
            else:
                rest = CHANGED_RX.sub("", a, count=1).strip(" ,.")
                if not rest:
                    retire(k)
                    ack = "Okay, noted that's changed."
                else:
                    said, short = store(qn, rest, episode_id)
                    if said:
                        st.setdefault("learned", []).append(said)
                    ack = self._ack(qn, short).replace("Noted", "Updated")
        elif SKIP_RX.match(a) or NOTHING_RX.match(a) or not a:
            st.setdefault("skipped", {})[k] = datetime.now(CFG.tz).isoformat()
            ack = "No problem."
        elif BARE_RX.match(a):
            if not st.get("nudged"):
                st["nudged"] = True
                _save(st)
                return f"Tell me in a few words, or say skip. {self._ask_line()}", False
            st.setdefault("skipped", {})[k] = datetime.now(CFG.tz).isoformat()
            ack = "Okay, skipping that one."
        else:
            said, short = store(qn, t, episode_id)
            if said and qn.summary:
                st.setdefault("learned", []).append(said)
            st.get("skipped", {}).pop(k, None)
            ack = self._ack(qn, short)
        st["nudged"] = False
        st["pos"] += 1
        if st["pos"] >= len(st["round"]):
            st.update({"active": False, "round": [], "refresh": [], "pos": 0, "rounds": st.get("rounds", 0) + 1})
            _save(st)
            ack = ack.replace("Got it", "Okay")          # the summary itself opens with "Got it"
            return f"{ack} {summary(st.get('learned', []))}".strip(), True
        _save(st)
        hint = ""
        left = len(st["round"]) - st["pos"]
        if left == 1:
            hint = "Last one. "
        elif st["pos"] == len(st["round"]) // 2 and len(st["round"]) >= 6:
            hint = "Halfway there. "
        return f"{ack} {hint}{self._ask_line()}".strip(), False
