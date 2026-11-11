"""Reply strategy — Stiti decides HOW to answer each turn, locally, before any LLM (D25).

docs/research/jarvis_persona_psychology.md §3a. Rules over the signals the brain already has (decide → domain,
emotion.fuse → mood, the last reply, standing directives, the clock). No model, < 1 ms. The first matching row wins:

  CRISIS      self-harm words                      → fixed local text with Tele-MANAS 14416, no LLM
  REPAIR      a correction, or "didn't understand / what language" right after her reply
  DO          todo / time / control (fast paths)   → confirm the key slot, then "Anything else?"
  QUIET       "so", "ok", "hmm", "cool" (≤3 words, nothing open) → "Mm?" or one word
  SOLVE       he asks for help or advice, or is frustrated with something broken
  LISTEN      low mood (conf ≥ 0.75), venting, bad news, thinking traps — reflect, no advice, no pep talk
  ANSWER      a question
  BANTER      a win, a joke, high-energy happy
  ACKNOWLEDGE (default) a statement or an update — react briefly, no follow-up question

Each strategy carries its shape (word cap, question allowed?, humour?, memory callbacks?, advice allowed?) and a one-line
instruction for the briefing. `psych.enforce` / `psych.StreamLint` enforce the shape IN CODE, so a weak free model can't
turn it back into an interview. The choice is logged in `decisions` (question `reply_strategy`); his reaction on the next
turn (`learning.mark_outcome`) is the label a Laya `reply_strategy` head can later be calibrated on.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta

VERSION = "rules-strategy-v1"

# ---------------------------------------------------------------- signals (English + Hinglish)
SELF_HARM_RX = re.compile(
    r"\b(kill (my ?self|me)|end (my life|it all)|want to die|wanna die|wish i (was|were) dead|don'?t want to (live|be alive|exist)|"
    r"no (point|reason) (in )?(living|to live)|better off dead|suicid\w*|hurt (my ?self)|self[- ]harm|cut (my ?self)|"
    r"mar(na)? jaana? chaht[ai]|marna chaht[ai]|mar jaun|mar jaaun|jeena nahi|jeene ka (mann|man) nahi|zinda nahi rehna|"
    r"khud ko (khatam|maar)|sab khatam kar (dun|du|dena)|khudkushi|aatmahatya)\b", re.I)
CONFUSION_RX = re.compile(
    r"\b(i )?(didn'?t|did not|don'?t|do not|couldn'?t) (understand|get (it|that|you)|follow)|what language|which language|"
    r"what (do|did) you mean|what are you (saying|talking about)|makes no sense|doesn'?t make sense|"
    r"samajh (nahi|nhi) aaya|samjha nahi|samjhi nahi|kya bol rahi ho|kya bola|kya matlab|huh\??$|^what\??$", re.I)
OPENER_RX = re.compile(r"^(so+|and|um+|uh+|well|toh|to|matlab|aur|listen|suno|achha so|okay so|ok so)[.?!…]*$", re.I)
CLOSER_RX = re.compile(r"^(ok(ay)?|k|hmm+|hm+|cool|nice|achha|acha|accha|theek hai|thik hai|alright|right|got it|fine|"
                       r"sahi|haan theek|okay cool|ok cool|great|perfect|nice one|oh|ohh|ah|i see)[.!…]*$", re.I)
HELP_RX = re.compile(r"\b(what should i|should i\b|kya karu|kya karun|kya karoon|how (do|can|should) i|how to\b|help me|"
                     r"suggest|any (advice|tips|ideas)|what do i do|kaise karu|kaise karun|recommend|which (one|is better)|"
                     r"give me (a|some) (plan|idea)|batao kya karu)\b", re.I)
VENT_RX = re.compile(r"\b(so done|i'?m done|fed up|sick of|tired of|can'?t take|hate (this|it|my)|stupid|useless|"
                     r"pissed|frustrat\w*|annoy\w*|irritat\w*|thak gay[ai]|thak gya|thaka hua|thaki hui|bakwas|pareshan|"
                     r"dimaag kharab|bore ho|bahut bura|worst day|rough day|bad day|exhausted|drained|overwhelm\w*|"
                     r"stressed|tension|udaas|low feel|feeling low|lonely|akela|akeli|sad|upset|awful|terrible|crying|"
                     r"hurt|depressed|anxious|nervous|scared|worried|ghabra\w*|dukhi|bura lag|mann nahi)\b", re.I)
BAD_NEWS_RX = re.compile(r"\b(didn'?t get|did not get|not (get )?(shortlisted|selected)|rejected|rejection|failed|"
                         r"got fired|laid off|broke up|breakup|fight with|lost (my|the)|passed away|died|"
                         r"select nahi|nahi hua|nahi mila|fail ho gay[ai])\b", re.I)
TRAP_RX = re.compile(r"\b(i'?m (so |such a |a )?(useless|worthless|stupid|failure|loser|dumb|idiot)|"
                     r"i (can'?t|cannot) (do|code|get) anything|i never (get|do)|nothing (ever )?works|everyone (hates|is better)|"
                     r"i'?ll never|main (bekaar|nikamma|nikammi) hoon|mujhse kuch nahi hota)\b", re.I)
TECH_RX = re.compile(r"\b(code|bug|error|build|compile|crash\w*|test(s)?|server|deploy|api|function|script|laptop|"
                     r"wifi|internet|app|not working|isn'?t working|doesn'?t work|broken|chal nahi raha)\b", re.I)
WIN_RX = re.compile(r"\b(cracked|cleared|got (the |an |my )?(offer|job|internship|selected)|selected|shortlisted|passed|"
                    r"nailed|aced|won|shipped|finished|launched|got placed|ho gaya select|clear ho gaya|mil gay[ai])\b", re.I)
JOKE_RX = re.compile(r"(\bhaha+\b|\blol\b|\blmao\b|\bhehe\b|😂|🤣|😄|\bjk\b|just kidding|mazaak)", re.I)
QUESTION_RX = re.compile(r"\?\s*$|^(what|who|when|where|why|how|which|is|are|do|does|did|can|could|will|would|"
                         r"kya|kaun|kab|kahan|kyun|kyu|kaise|kitna|kitne)\b|\b(batao|bata do|tell me|explain)\b", re.I)
MEMORY_CUE_RX = re.compile(r"\b(remember|recall|yaad hai|yaad h|last time|pichli baar|that time|kya bola tha|"
                           r"what did i (say|tell)|did i (tell|say|mention)|when did i|i told you|maine bataya|bataya tha|"
                           r"you know (about|what)|previously|earlier)\b", re.I)
PUSHBACK_RX = re.compile(r"\b(\d+|five|ten|paanch|das|ek|one|two|do) (more )?(min(ute)?s?|minat)( more| aur)?\b|"
                         r"\bone more\b|\bjust (a|one|this)\b|\bthoda aur\b|\bbas (thoda|ek)\b|\bafter this\b|\blet me finish\b|"
                         r"\bi'?ll sleep\b|\bin a bit\b|\bsoon\b", re.I)

# Hindi function words that mark a Hinglish sentence (Roman script). Ambiguous English words are left out.
HINDI_WORDS = set("""
hai hain nahi nahin nhi kya yaar karo kar karna karte karti karta mujhe hoon hun tum aap kaise kyun kyu haan
accha achha acha theek thik bahut bohot bhot aaj abhi toh bhi gaya gayi gaye raha rahi rahe tha thi batao bolo chalo
matlab kuch mera meri mere tera teri yeh woh kal kab kahan kaun thak thaka thaki baje wala wali chahiye lagta lag
hoga hogi samajh dekho suno baat jaldi phir fir pehle baad sab bas ekdum sahi pata mein mai main hum humko apna apni
kitna kitne raat subah shaam dopahar bhai bro yaha waha idhar udhar kyunki lekin aur ya na
""".split())
_TOKEN = re.compile(r"[a-zA-Z']+")


def hindi_share(text: str) -> tuple[int, float]:
    """(# distinct Hindi function words, share of Hindi tokens) — Roman-script Hinglish detector."""
    toks = [t.lower() for t in _TOKEN.findall(text or "")]
    if not toks:
        return 0, 0.0
    hits = [t for t in toks if t in HINDI_WORDS]
    if re.search(r"[ऀ-ॿ]", text or ""):        # Devanagari → clearly Hindi
        return 5, 1.0
    return len(set(hits)), len(hits) / len(toks)


def is_hinglish(text: str) -> bool:
    n, share = hindi_share(text)
    return n >= 2 and share >= 0.25


def directive_language(directives: list[str]) -> str | None:
    """The language he locked ("just talk in English, no other language"), or None (brain/lang.py)."""
    from . import lang
    return lang.locked(directives)


def reply_lang(text: str, directives: list[str] | None = None, prev: str | None = None, pref: str | None = None) -> str:
    """Mirror him (D34): the language of THIS message — english / hinglish / hindi / telugu / tenglish — unless he
    locked one; his explicit "talk in Telugu" holds while he speaks Telugu or English; "ok"/"bye" keep the last one."""
    from . import lang
    return lang.decide(text, prev=prev, lock=lang.locked(directives), pref=pref)


def asks_about_past(text: str, domain: str | None = None) -> bool:
    return domain == "memory" or bool(MEMORY_CUE_RX.search(text))


def is_crisis(text: str) -> bool:
    return bool(SELF_HARM_RX.search(text))


# ---------------------------------------------------------------- the strategy object
@dataclass
class Strategy:
    name: str
    max_words: int
    ask: bool                       # may the reply contain a question?
    humour: bool
    callbacks: bool                 # may she volunteer a memory?
    line: str                       # the [THIS TURN] instruction for the LLM
    lang: str = "english"
    advice: bool = True             # LISTEN: no advice, no tips
    max_items: int = 3
    reframe: bool = False           # LISTEN + thinking trap: one reframe backed by a real fact
    allow_promise: bool = False     # "from now on…" only if a rule was really saved this turn
    avoid_terms: list[str] = field(default_factory=list)   # recalled entities he didn't mention: never ask about them

    def ask_rule(self) -> str:
        return ("at most one short offer to act (e.g. \"Want me to set it?\"), only if truly needed"
                if self.ask else "NONE this turn — end on a statement")


_LINES = {
    "CRISIS": "He may be in danger. Calm, short, human. Give Tele-MANAS 14416. No jokes, no lectures.",
    "REPAIR": "He didn't follow your last reply, or is correcting you. Start with \"Sorry —\" and say the same point "
              "again simply and plainly. Don't defend or explain yourself.",
    "DO": "Confirm the action in a few words, repeating the key detail.",
    "QUIET": "He said almost nothing. Reply with one or two words at most.",
    "SOLVE": "He wants help. Give ONE clear recommendation first, with the reason in one sentence. At most 3 short "
             "points, said as speech, not a list. If it's his choice, end with \"Your call.\"",
    "SOLVE_TECH": "He's frustrated with something broken. One short human reaction (\"Ugh.\"), then the single most "
                  "useful next step. No jokes, no pep talk, no lecture about breaks.",
    "LISTEN": "He's low or venting. Name what happened plainly in one sentence and show you get why it matters. "
              "Reflect — don't fix, and don't repeat his words back. No advice, no tips, no pep talk, no silver linings.",
    "REFRAME": "He's being harsh on himself (all-or-nothing). Don't agree with it and don't gush. Give ONE realistic "
               "reframe backed by a real fact from HIS WINS or MEMORY, in plain words.",
    "ANSWER": "Answer exactly what he asked, first, then stop.",
    "BANTER": "He's in a good mood or joking. Match it with dry, understated wit in one short line. "
              "No exclamation spam, no \"how do you feel\".",
    "ACKNOWLEDGE": "He's telling you something. React briefly and specifically, as a statement. "
                   "No follow-up question, no advice he didn't ask for, don't restate what he said.",
    "NUDGE": "Point out the one fact that matters, once, politely. Then respect his choice.",
}


def make(name: str, lang: str = "english", **over) -> Strategy:
    shapes = {   # name: (max_words, ask, humour, callbacks)
        "CRISIS": (60, False, False, False), "REPAIR": (25, False, False, False), "DO": (14, False, False, False),
        "QUIET": (4, False, False, False), "SOLVE": (60, False, False, True), "ANSWER": (45, False, False, True),
        "LISTEN": (30, False, False, True), "NUDGE": (30, True, True, True), "BANTER": (20, False, True, False),
        "ACKNOWLEDGE": (25, False, True, True),
    }
    mw, ask, hum, cb = shapes[name]
    s = Strategy(name, mw, ask, hum, cb, _LINES[name], lang=lang)
    if name == "LISTEN":
        s.advice, s.max_items = False, 0
    elif name == "ACKNOWLEDGE":
        s.advice = False                 # MI: advise only when asked
    return replace(s, **over) if over else s


# ---------------------------------------------------------------- the selector
def choose(text: str, *, domain: str | None, mood: str | None = None, mood_conf: float = 0.0,
           arousal: float = 0.3, corrected: bool = False, last_reply: str | None = None,
           directives: list[str] | None = None, live: bool = False, crisis_recent: bool = False,
           pending_offer: bool = False, voice_mood: bool = False, prev_lang: str | None = None,
           pref_lang: str | None = None) -> Strategy:
    """Pick the reply strategy for this turn. Pure function of local signals, < 1 ms.
    A low mood alone switches to LISTEN only when the VOICE says so too (text-only mood is ~50% reliable); in text,
    his words must show it (venting, bad news)."""
    t = (text or "").strip()
    lang = reply_lang(t, directives, prev=prev_lang, pref=pref_lang)
    words = len(t.split())
    dirs = " ".join(directives or []).lower()
    s: Strategy

    if is_crisis(t):
        s = make("CRISIS", lang)
    elif last_reply is not None and (corrected or CONFUSION_RX.search(t)) and domain not in ("todo", "time"):
        s = make("REPAIR", lang)
    elif words <= 3 and (OPENER_RX.match(t) or CLOSER_RX.match(t)) and not pending_offer:
        s = make("QUIET", lang)
    elif domain in ("todo", "time", "control"):
        s = make("DO", lang)
    elif live:                                                   # live news/web info: read it, offer more
        s = make("ANSWER", lang, max_words=90, ask=True, callbacks=False)
    elif HELP_RX.search(t):
        s = make("SOLVE", lang)
    elif TRAP_RX.search(t):
        s = make("LISTEN", lang, reframe=True, line=_LINES["REFRAME"], max_words=35)
    elif (VENT_RX.search(t) or (mood == "angry" and mood_conf >= 0.75 and voice_mood)) and TECH_RX.search(t):
        s = make("SOLVE", lang, max_words=30, line=_LINES["SOLVE_TECH"], callbacks=False)
    elif (mood in ("sad", "stressed", "angry", "tired") and mood_conf >= 0.75 and voice_mood) or VENT_RX.search(t) \
            or BAD_NEWS_RX.search(t) or crisis_recent:
        s = make("LISTEN", lang)
    elif QUESTION_RX.search(t):
        s = make("ANSWER", lang)
    elif WIN_RX.search(t) or JOKE_RX.search(t) or (mood == "happy" and mood_conf >= 0.75 and arousal >= 0.5):
        s = make("BANTER", lang)
    else:
        s = make("ACKNOWLEDGE", lang)

    # standing instructions change the shape IN CODE (not only as a MUST line)
    if re.search(r"don'?t ask (him )?questions|fewer questions|no questions", dirs):
        s.ask = False
    if re.search(r"keep replies short|short and to the point|1–2 sentences|one or two sentences", dirs):
        s.max_words = min(s.max_words, 35 if s.name in ("SOLVE", "ANSWER") else 25)
    # never end two replies in a row with a question
    if last_reply and last_reply.rstrip().endswith("?") and s.name not in ("QUIET",):
        s.ask = False
    if crisis_recent:
        s.humour = False
    return s


# ---------------------------------------------------------------- fixed local replies (no LLM)
def crisis_reply(lang: str = "english") -> str:
    if lang in ("hinglish", "hindi"):
        return ("Mujhe khushi hai ki tumne mujhe bataya. Please abhi Tele-MANAS ko call karo — 14416, free hai, "
                "24 ghante. Kisi apne ko bhi bula lo. Main yahin hoon.")
    return ("I'm really glad you told me. Please call Tele-MANAS now — 14416, it's free and open 24×7. "
            "If you can, get someone you trust to be with you. I'm right here.")


def quiet_reply(text: str, lang: str = "english", last: str | None = None) -> str:
    if OPENER_RX.match(text.strip()):
        return {"hinglish": "Haan?", "hindi": "हाँ?", "telugu": "హా?", "tenglish": "హా?"}.get(lang, "Mm?")
    opts = {"hinglish": ["Theek.", "Hmm."], "hindi": ["ठीक है।", "हम्म।"], "telugu": ["సరే.", "హ్మ్."],
            "tenglish": ["Okay.", "సరే."]}.get(lang, ["Cool.", "Mm-hm.", "Okay."])
    return next((o for o in opts if o != last), opts[0])


# ---------------------------------------------------------------- NUDGE: late night + an early event
def nudge_fact(now: datetime) -> dict | None:
    """Late at night (00:00–04:59) with a reminder or a due task in the next 10 hours → the one fact worth saying."""
    if not (0 <= now.hour < 5):
        return None
    from ..db import one
    row = one("""SELECT fire_at AS at, coalesce(payload->>'label', payload->>'say') AS what FROM intents
                 WHERE state IN ('pending','armed') AND kind='reminder' AND fire_at BETWEEN %(a)s AND %(b)s
                 UNION ALL
                 SELECT due AS at, title AS what FROM tasks WHERE status='open' AND due BETWEEN %(a)s AND %(b)s
                 ORDER BY at LIMIT 1""", {"a": now + timedelta(minutes=30), "b": now + timedelta(hours=10)})
    return row


def nudge_text(fact: dict, now: datetime, name: str | None) -> str:
    from ..config import CFG
    at = fact["at"].astimezone(CFG.tz)
    when = at.strftime("%I:%M").lstrip("0").replace(":00", "")
    what = re.sub(r"^(my|the)\s+", "", (fact.get("what") or "your thing").strip(), flags=re.I)
    who = f"{name}, " if name else ""
    return f"{who}it's {now.strftime('%I:%M').lstrip('0')} and your {what} is at {when}."


def nudge_followup(now: datetime) -> str:
    from ..db import one
    alarm = one("""SELECT fire_at FROM intents WHERE state IN ('pending','armed') AND kind='alarm'
                   AND fire_at BETWEEN %s AND %s ORDER BY fire_at LIMIT 1""", (now, now + timedelta(hours=10)))
    if alarm:
        from ..config import CFG
        return f"As you wish. Your {alarm['fire_at'].astimezone(CFG.tz).strftime('%I:%M %p').lstrip('0')} alarm's set."
    return "As you wish."


# ---------------------------------------------------------------- logging (future Laya labels)
def log(turn_id: int, s: Strategy) -> None:
    from ..db import q
    for qn, ans in (("reply_strategy", s.name), ("reply_lang", s.lang)):
        q("""INSERT INTO decisions(turn_id, question, answer, confidence, acted, laya_version)
             VALUES (%s,%s,%s,1.0,true,%s)""", (turn_id, qn, ans, VERSION))
