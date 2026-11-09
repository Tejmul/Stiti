"""What did the learner just say? Control word, question, or something else — local, instant, no LLM.

Voice-first: the owner talks to the laptop while the board is on a big monitor, so every control works
by voice (Hinglish too). Research §5: control requests are obeyed at once, before any LLM call.
"""
from __future__ import annotations

import re

_N = lambda s: re.sub(r"[^\w\s?']", " ", s.lower()).strip()  # noqa: E731

RULES: list[tuple[str, re.Pattern]] = [(k, re.compile(p)) for k, p in [
    ("end", r"^(end|stop|finish|close) (the )?(lesson|class|session)|^(khatam|lesson khatam|class khatam)|"
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
               r"samajh gayi|samjha|samjhi|done|ready|let'?s go|go)( please| na| stiti)?$"),
    ("confused", r"(samajh nahi aaya|samjha nahi|samjhi nahi|didn'?t (get|understand)|don'?t (get|understand)|"
                 r"not clear|confus|explain (it )?again|explain differently|kuch samajh nahi)"),
    ("hindi", r"(hindi mein|in hindi|hinglish mein)"),
    ("english", r"(english mein|in english)"),
]]
QUESTION = re.compile(r"(\?$|^(what|why|how|when|where|who|which|is|are|can|could|does|do|should|would|will|"
                      r"kya|kyun|kyu|kaise|kab|kahan|kaun|kaunsa|matlab|doubt|question|sawal|ek sawal|"
                      r"explain|tell me|batao|bata)\b)")
IDK = re.compile(r"(pata nahi|nahi pata|no idea|don'?t know|dont know|idk|not sure|pata ni|maloom nahi|"
                 r"hint|help|give up|skip)")
EXPLICIT_Q = re.compile(r"^(question|doubt|sawal|ek sawal|ek doubt|wait,? what|matlab kya|what is|what'?s|kya hota)")


def classify(text: str, *, answering: bool = False) -> str:
    """-> end | pause | repeat | back | next | slower | faster | resume | confused | hindi | english |
          question | answer | other.  While a check is open, plain sentences are answers."""
    t = _N(text)
    if not t:
        return "other"
    if len(t.split()) <= 6:
        for name, rx in RULES:
            if name in ("confused", "hindi", "english"):
                continue
            if rx.search(t):
                if answering and name == "resume" and t in ("yes", "no", "haan", "ha", "han"):
                    return "answer"
                return name
    for name in ("confused", "hindi", "english"):
        if dict(RULES)[name].search(t):
            return name
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
