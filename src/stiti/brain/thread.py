"""The conversation thread — what the two of them are talking about right now (2026-11-20, docs/research/
conversation_continuity.md).

Owner: "she loses the thread … 'and that one?', 'why?' are treated as new topics … she answers and stops". Before, a
follow-up reached the brain as its bare words: recall searched for "why?" (finds nothing useful), the briefing had only
the last two exchanges (the token budget squeezed RECENT out, measured: 5 lines in 59 of 66 long-conversation turns),
and every strategy forbade any question. The brain now keeps the thread itself, in code:

  Thread      topic (his last substantive line), whether it is about HIM (personal), his last question, her last
              answer, the names / key words in play, how many turns it has run. Immutable (the engine's speculative
              snapshot restores it exactly), plain data (saved across restarts by convstate.py).
  follow-up   short ellipsis / pronoun lines ("and that one?", "why?", "the second one", "what about Pune?", "tell me
              more", "aur?", "kyun?") within THREAD_S of the last turn → recall searches with the topic + his words,
              and the briefing gets a [THREAD] block that says what "it / that / why" refer to.
  beat        whether she may add ONE beat that keeps it going (a specific follow-up question, or a sentence that
              builds on what he said) — rules in `beat()`, decided here, enforced by the strategy shape (psych).
Pure regex + set maths: microseconds, no model call.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, replace

THREAD_S = 10 * 60          # a thread older than this is over: a short line is a new topic again
TOPIC_CHARS = 200
ANSWER_CHARS = 300

_FOLLOW_START = re.compile(
    r"^\W*(?:(?:ok(?:ay)?|achha|accha|acha|hmm+|haan|right|so|wait|hold on|oh)\W+)*"
    r"(?:and|but|also|or|aur|phir|par|lekin|"
    r"why|why not|how come|how so|really|seriously|matlab|kyun|kyu|"
    r"what about|how about|and what about|what if|which one|"
    r"the (?:first|second|third|fourth|last|other|next|previous|same) (?:one|thing|point|option|part)?|"
    r"(?:that|this|the other) one|both|neither|either|"
    r"it|that|this|those|these|they|them|he|she|his|her|its|there)\b", re.I)
_ANAPHOR = re.compile(r"\b(it|that|this|those|these|them|they|he|she|one|ones|there|then|same|wo|woh|ye|yeh|usko|uska|"
                      r"iska|isko)\b", re.I)
_MORE = re.compile(r"\b(tell me more|more about (?:it|that|this)|go on|keep going|continue|what else|and then|"
                   r"aur batao|aage batao|phir kya|then what|what happened next|elaborate|explain (?:it|that) more|"
                   r"in detail)\b", re.I)
_BARE = re.compile(r"^\W*(why|how|really|seriously|and|so|then|kyun|kyu|kaise|matlab|aur|phir|example|"
                   r"for example|like what|such as|meaning|means)\W*$", re.I)
_PERSONAL = re.compile(r"\b(about me|myself|know me|my (life|profile|family|friends?|projects?|plans?|goals?|day|week)|"
                       r"what do you know|who am i|mere baare|mujhe kitna jaanti)\b", re.I)
_CAP = re.compile(r"(?<![.!?]\s)(?<!^)\b([A-Z][a-zA-Z0-9+#-]{2,})\b")
_WORD = re.compile(r"[a-z][a-z0-9+#-]{4,}")
_STOP = set("""about after again against always another because before being below between could doing during every
everything going having little might never other people really should something still their there these thing things
think those through under until where which while would yours about maybe actually basically right today tomorrow
yesterday tell know want need like just okay yeah please thanks thank sorry gonna wanna""".split())


@dataclass(frozen=True)
class Thread:
    topic: str = ""                  # his last substantive line (what the conversation is about)
    personal: bool = False           # is the topic HIM (profile / memory questions): "what else" pages his facts
    last_q: str = ""                 # his last line in this thread
    last_a: str = ""                 # her last answer in this thread (what he heard)
    terms: tuple[str, ...] = ()      # names / key words in play, newest first
    turns: int = 0                   # exchanges on this topic after the first one
    at: float = 0.0                  # time of the last turn

    def live(self, now: float | None = None) -> bool:
        now = time.time() if now is None else now
        return bool(self.topic) and now - self.at < THREAD_S

    def as_dict(self) -> dict:
        return {"topic": self.topic, "personal": self.personal, "last_q": self.last_q, "last_a": self.last_a,
                "terms": list(self.terms), "turns": self.turns, "at": self.at}

    @classmethod
    def from_dict(cls, d: dict | None) -> "Thread":
        if not d:
            return cls()
        return cls(str(d.get("topic") or ""), bool(d.get("personal")), str(d.get("last_q") or ""),
                   str(d.get("last_a") or ""), tuple(str(t) for t in d.get("terms") or ())[:8],
                   int(d.get("turns") or 0), float(d.get("at") or 0.0))


def terms_of(text: str) -> list[str]:
    """Names (capitalised, not sentence-initial) + long content words — what a follow-up's "it" can point at."""
    caps = [m.group(1) for m in _CAP.finditer(text or "")]
    words = [w for w in _WORD.findall((text or "").lower()) if w not in _STOP]
    out: list[str] = []
    for t in caps + words:
        if t.lower() not in (x.lower() for x in out):
            out.append(t)
    return out[:8]


def is_followup(text: str, th: Thread | None, now: float | None = None) -> bool:
    """A line that only makes sense with the thread: short and elliptical ("why?", "and that one?", "what about
    Pune?", "the second one", "tell me more", "aur?"). Needs a live thread."""
    if th is None or not th.live(now):
        return False
    return cue(text)


def cue(text: str) -> bool:
    """Shaped like a follow-up (no thread needed) — also what lets him carry on right after she dozed off."""
    t = (text or "").strip()
    n = len(t.split())
    if not t or n > 14:
        return False
    if _BARE.match(t) or (n <= 8 and _MORE.search(t)):
        return True
    if _FOLLOW_START.match(t) and (n <= 6 or _ANAPHOR.search(t)):
        return True                      # "and why is it faster than a binary tree?" — "it" is the thread
    return n <= 6 and t.endswith("?") and bool(_ANAPHOR.search(t))


def same_topic(text: str, th: Thread | None, now: float | None = None) -> bool:
    """Not elliptical, but still on the thread: he names something in play ("is Pune cheaper than that?")."""
    if th is None or not th.live(now) or not th.terms:
        return False
    mine = {t.lower() for t in terms_of(text)}
    return bool(mine & {t.lower() for t in th.terms})


def is_personal(text: str, domain: str | None = None) -> bool:
    from .strategy import asks_about_past
    return bool(_PERSONAL.search(text or "")) or asks_about_past(text or "", domain)


def update(th: Thread, text: str, reply: str, *, follow: bool, domain: str | None, route: str | None,
           strategy: str | None, now: float | None = None) -> Thread:
    """After a turn. Commands, fast-path actions and one-word turns don't touch the thread (a "set an alarm" in the
    middle of a chat must not end it). A follow-up / same-topic line continues it; anything else starts a new one."""
    now = time.time() if now is None else now
    t = " ".join((text or "").split())
    if (domain in ("todo", "time", "control") or strategy in ("DO", "QUIET", "CRISIS")
            or (route == "fast_path" and not follow) or not t):
        return th
    a = " ".join((reply or "").split())[:ANSWER_CHARS]
    if follow or same_topic(t, th, now):
        terms = tuple(dict.fromkeys(terms_of(t) + terms_of(a) + list(th.terms)))[:8]
        return replace(th, last_q=t[:TOPIC_CHARS], last_a=a, terms=terms, turns=th.turns + 1, at=now)
    if len(t.split()) < 3:
        return replace(th, at=now) if th.live(now) else th
    return Thread(topic=t[:TOPIC_CHARS], personal=is_personal(t, domain), last_q=t[:TOPIC_CHARS], last_a=a,
                  terms=tuple(terms_of(t) + [x for x in terms_of(a) if x not in terms_of(t)])[:8], turns=0, at=now)


def query(th: Thread, text: str) -> str:
    """What recall should search with for a follow-up: the topic + the names in play + his words."""
    extra = " ".join(x for x in th.terms[:4] if x.lower() not in th.topic.lower())
    return " ".join(x for x in (th.topic, extra, text) if x).strip()


def block(th: Thread, text: str, *, more: bool = False) -> str:
    """[THREAD] for the briefing: what "it / that / why / the second one" refer to. ≤ ~90 tokens."""
    lines = [f"Topic: “{th.topic}”"]
    if th.last_q and th.last_q != th.topic:
        lines.append(f"His last line on it: “{th.last_q}”")
    if th.last_a:
        lines.append(f"You last said: “{th.last_a}”")
    if more:
        lines.append(f"He wants MORE on this same topic (“{text}”): go one step further with points you haven't made "
                     "(see ALREADY SAID) — don't restart it, don't change the subject.")
    else:
        lines.append(f"His new line (“{text}”) most likely follows up on this: read “it / that / why / the other one” as "
                     "being about it and answer in that context. Only if it is clearly a new subject, just answer that.")
    return "[THREAD — what you two are talking about right now]\n" + "\n".join(lines)


# ---------------------------------------------------------------- one beat: keep the conversation going
BEAT_ASK = ("Then keep the conversation going with ONE short, specific follow-up question about what he just said — "
            "something a friend would really wonder. Not generic (no \"how do you feel?\", no \"anything else?\"), "
            "nothing he already told you, nothing under YOU ALREADY ASKED.")
BEAT_BUILD = ("Then add ONE short sentence that builds on it — link it to the topic or to something he said earlier in "
              "this conversation. No question.")
ANNOYED_RX = re.compile(r"\b(annoy\w*|irritat\w*|fed up|pissed|shut up|stop asking|too many questions|just answer|"
                        r"leave me|not now|chup|bas karo|dimaag mat)\b", re.I)
NO_Q_RX = re.compile(r"don'?t ask (him )?questions|fewer questions|no questions|keep replies short|short and to the point",
                     re.I)
BEAT_STRATEGIES = ("ACKNOWLEDGE", "ANSWER", "BANTER")


def beat(*, strategy: str, text: str, th: Thread, follow: bool, her_last: list[str], his_last: list[str],
         mood: str | None = None, mood_conf: float = 0.0, directives: list[str] | None = None,
         interrupted: bool = False, blocked: bool = False) -> str | None:
    """"ask" (one follow-up question), "build" (one sentence that builds on it) or None. The rules (owner: keep it
    going like a person — but he also hated being asked the same things, and the D25 research found an interview
    after every statement felt fake):
      - only ACKNOWLEDGE / ANSWER / BANTER turns; never after a command, a QUIET "ok", a correction, a recap, a fetch,
        a flow or a crisis (`blocked`), never when she was just cut off (too long already);
      - only once a conversation is going: this line continues the thread, or he is telling a story (≥ 15 words);
      - off when he is terse (≤ 3 words now, or his last two lines ≤ 4 words) or annoyed (words / angry voice), or
        his standing rule says no questions / short replies;
      - a question only if none of her last three replies asked one (never two in a row; ≤ 1 in 4), else "build"."""
    if blocked or interrupted or strategy not in BEAT_STRATEGIES:
        return None
    words = len((text or "").split())
    if words <= 3 or (len(his_last) >= 2 and all(len(x.split()) <= 4 for x in his_last[-2:])):
        return None
    if ANNOYED_RX.search(text or "") or (mood == "angry" and mood_conf >= 0.6):
        return None
    dirs = " ".join(directives or [])
    going = follow or th.turns >= 1 or (strategy == "ACKNOWLEDGE" and words >= 15)
    if not going:
        return None
    if NO_Q_RX.search(dirs):
        return None
    if not any("?" in (r or "") for r in her_last[-3:]):
        return "ask"
    return "build" if th.turns >= 1 or follow else None
