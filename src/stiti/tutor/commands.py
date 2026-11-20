"""What did the learner just say? Control word, question, or something else — local, instant, no LLM.

Voice-first: the owner talks to the laptop while the board is on a big monitor, so every control works
by voice (Hinglish too). Research §5: control requests are obeyed at once, before any LLM call.
"""
from __future__ import annotations

import re

_N = lambda s: re.sub(r"[^\w\s?']", " ", s.lower()).strip()  # noqa: E731

RULES: list[tuple[str, re.Pattern]] = [(k, re.compile(p)) for k, p in [
    ("end", r"^(end|finish)( it| here| now| this)?$|^(end|stop|finish|close) (the |this )?(lesson|class|session)|^(khatam|lesson khatam|class khatam)|"
            r"^(bas karo|band karo|aaj ke liye bas|that'?s enough( for today)?|chalo bye|bye|bye bye|good ?night)$"),
    ("pause", r"^(ruko|ruk|rukh|ruko ruko|ek (minute|min|second|sec)|wait|wait wait|hold on|pause|stop|"
              r"thoda ruko|ek second ruko|hang on|one (sec|second|minute))( please| na| stiti)?$"),
    ("repeat", r"^(repeat|phir se|fir se|dobara|again|say (that|it) again|kya bola|kya kaha|"
               r"phir se bolo|fir se bolo|one more time|ek baar aur|come again|repeat that|what did you say)"
               r"( please| na| stiti)?$"),
    ("back", r"^(go back|back|peeche|piche|pichla|previous|last (one|part|slide)|peeche jao|wapas jao)( please| na)?$"),
    ("next", r"^(skip|next|agla|agle|move on|next part|skip (this|it)|aage (wala|ka) part|ye skip karo)( please| na)?$"),
    ("slower", r"^(slow|slower|slowly|slow down|dheere|dheere bolo|aaram se|thoda dheere|too fast)( please| na)?$"),
    ("faster", r"^(fast|faster|speed up|jaldi|jaldi bolo|tez|thoda tez|too slow|go faster)( please| na)?$"),
    ("resume", r"^(continue|go on|carry on|resume|play|aage|aage badho|aage chalo|chalo|chalo aage|haan|han|ha|"
               r"yes|yeah|yep|ok|okay|okay continue|hmm+|ji|haan ji|theek hai|thik hai|sure|got it|samajh gaya|"
               r"samajh gayi|samjha|samjhi|done|ready|let'?s go|go|i'?m back|i am back|back now|i'?m ready)"
               r"( please| na| stiti)?$"),
    ("confused", r"(samajh nahi aaya|samjha nahi|samjhi nahi|didn'?t (get|understand)|don'?t (get|understand)|"
                 r"not clear|confus|explain (it )?again|explain differently|kuch samajh nahi)"),
    # Feature 5: he wants fewer checks ("skip the questions", "just teach") / to be tested now ("let me blurt")
    ("fewer", r"\b((skip|stop|no more|less|fewer|too many|enough( of)?|without)( the| these| your| with the)? "
              r"(questions|checks|quiz(zes|zing)?)|stop (asking|quizzing)( me)?|don'?t (ask|quiz) me|"
              r"^just (teach|explain)( me)?( it| please)?$|^(you )?just teach)\b"),
    ("blurt", r"\b(let me blurt|blurt( it| time)?|test me|quiz me|let me (tell|say) (you )?everything( i remember)?)\b"),
    ("hindi", r"(hindi mein|in hindi|hinglish mein)"),
    ("english", r"(english mein|in english)"),
]]
QUESTION = re.compile(r"(\?$|^(what|why|how|when|where|who|which|is|are|can|could|does|do|should|would|will|"
                      r"kya|kyun|kyu|kaise|kab|kahan|kaun|kaunsa|matlab|doubt|question|sawal|ek sawal|"
                      r"explain|tell me|batao|bata)\b)")
IDK = re.compile(r"(pata nahi|nahi pata|no idea|don'?t know|dont know|idk|not sure|pata ni|maloom nahi|"
                 r"hint|help|give up|skip)")
EXPLICIT_Q = re.compile(r"^(question|doubt|sawal|ek sawal|ek doubt|wait,? what|matlab kya|what is|what'?s|kya hota)")
# He wants to change WHAT she teaches, not ask about it. 2026-11-20 log: "Bro, I don't need to go from all start",
# "tomorrow I have exam, I gave you a HTML, explain me that", "I want to study a different syllabus" — one was taken
# as his guess ("Hold that thought"), one answered as a doubt about HTML, one parked. The steer handler (player) asks
# the LLM what he wants and falls back to answering, so a doubt caught here by mistake still gets answered.
STEER = re.compile(
    r"\b(i (already )?know (this|that|it|these|the basics)|(i )?(don'?t|do not) need (this|that|it|to|the|all)|"
    r"no need (to|for)|(start|go) (from|with|at) |from (the |all )?(start|beginning|scratch|basics)|"
    r"skip (the |this |these |all )?(basics|intro|introduction|part|chapter|unit|it|this|that)|"
    r"(have|got|is|are) (an? |my |the )?(exams?|tests?|viva|quiz|paper)\b|exams? (is |are )?(tomorrow|today|on|in)|"
    r"i want (to (study|learn|do|cover|go|start|revise)|you to (teach|explain|cover|start|go))|"
    r"teach me (the|about|this|that|everything|unit|chapter|from)|cover (the )?(whole|full|entire|all|everything)|"
    r"let'?s (do|study|go to|move to|start|jump|cover|skip|revise)|"
    r"can (we|you) (start|go|move|skip|do|study|jump|cover|teach)|"
    r"(different|another|other|next|new) (syllabus|topic|chapter|unit|part|subject|lesson)|"
    r"go to (unit|chapter|part|section|the)|jump to|move (on )?to (unit|chapter|part|section)|(unit|chapter) \d|"
    r"whole (syllabus|book|notebook|thing|html|file)|(the|this|that) (html|notebook|file|pdf|book) i (gave|sent|shared))\b")


# He corrects what she heard (D53, "it's hearing wrong and then answering me anything. I could not even correct it"):
# "no, I said lexer", "not that, I asked about the FIRST set", "I meant DFA". The rest is what he really said.
CORRECTION = re.compile(r"^(?:(?:no+|nope|nahi|not that|wrong|that'?s not what i (?:said|asked|meant))[,.! ]+)?"
                        r"(?:i (?:said|asked|meant|mean|was asking|am asking)|i'?m asking|my question (?:is|was))"
                        r"[,: ]+(?:about |for |that |if |whether )?(?P<rest>.+)$", re.I)


def correction(text: str) -> str | None:
    """"no, I said lexer" → "lexer" (what he really said), else None."""
    m = CORRECTION.match((text or "").strip())
    if not m:
        return None
    rest = m.group("rest").strip(" .!?,")
    if not rest or rest.lower() in ("it", "that", "this", "so", "yes", "no", "what", "the same"):
        return None                                   # "I mean it" is not a correction
    return rest


def classify(text: str, *, answering: bool = False) -> str:
    """-> correct | end | pause | repeat | back | next | slower | faster | resume | confused | fewer | blurt | hindi |
          english | steer | question | answer | other.  While a check is open, plain sentences are answers — but a request
          to change the lesson ("I don't need the basics", "exam tomorrow") is never taken as his answer."""
    t = _N(text)
    if not t:
        return "other"
    if correction(text):
        return "correct"
    if len(t.split()) <= 6:
        for name, rx in RULES:
            if name in ("confused", "hindi", "english", "fewer", "blurt"):
                continue
            if rx.search(t):
                if answering and name == "resume" and t in ("yes", "no", "haan", "ha", "han"):
                    return "answer"
                return name
    for name in ("fewer", "blurt", "confused", "hindi", "english"):
        if dict(RULES)[name].search(t):
            return name
    if len(t.split()) >= 3 and STEER.search(t):
        return "steer"
    if answering:
        if EXPLICIT_Q.search(t) or (t.endswith("?") and not IDK.search(t) and len(t.split()) > 3
                                    and QUESTION.search(t) and not re.match(r"^(is it|it'?s|maybe|i think)", t)):
            return "question"
        return "answer"
    if QUESTION.search(t) or text.strip().endswith("?"):
        return "question"
    return "question" if len(t.split()) >= 3 else "other"


def is_idk(text: str) -> bool:
    return bool(IDK.search(_N(text)))
