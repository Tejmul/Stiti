"""Standing instructions about HOW Stiti should talk — saved the moment he says them, applied from the next reply.

"Talk in English", "keep it short", "don't ask so many questions", "stop asking about my interview", "call me Tej"
are instructions, not corrections (the decision layer scores them 0 as is_correction), so they used to wait for
the night job — which hadn't run — and were never remembered. Now they become active `user_directives`
(category talk_style / boundary) at once; the compiler puts talk_style rules into every briefing, and USER.md shows
them so he can edit them. A newer instruction on the same topic replaces the older one (supersession key).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

LANG_RX = re.compile(r"\b(talk|speak|reply|answer|respond|baat\s*kar\w*|bol\w*)\b[^.?!]*?\b(?:in\s+|mein\s+|me\s+)?"
                     r"(english|hindi|hinglish)\b|\b(english|hindi|hinglish)\s+(only|mein|me|please|bolo)\b", re.I)
SHORT_RX = re.compile(r"\b(keep (it|replies|answers|things) (short|brief)|be (brief|short|concise)|shorter (answers|replies)"
                      r"|chhota (bolo|rakho)|too long|less talk)\b", re.I)
FEWER_Q_RX = re.compile(r"\b(don'?t|do not|stop|never)\b[^.?!]*\bask\w*\b[^.?!]*\b(so many|too many|lots of|a lot of|many)?\s*"
                        r"questions?\b|\bask (fewer|less) questions\b|\bitne sawal\b", re.I)
STOP_TOPIC_RX = re.compile(r"\b(stop|don'?t|do not|never)\s+(ask(ing)?|bring(ing)? up|talk(ing)? about|mention(ing)?)\s+"
                           r"(me\s+)?(about\s+)?(?P<topic>(my |the )?[a-z][\w\s'-]{2,40}?)\s*(again|anymore)?[.!]?$", re.I)
CALL_ME_RX = re.compile(r"\b(?:call me|my name is|naam)\s+(?P<name>[A-Z][a-z]{1,20})\b(?!\s+(?:is|hai))")
DONT_CALL_RX = re.compile(r"\b(don'?t|do not|never|stop)\s+call(ing)? me\s+(?P<name>[\w ]{2,20}?)[.!]?$", re.I)


@dataclass
class Instruction:
    directive: str           # what goes into the briefing / USER.md
    key: str                 # supersession key: a newer one on the same topic replaces it
    category: str            # talk_style | boundary
    ack: str                 # what she says back (short, Jarvis-style)
    call_me: str | None = None


def parse(text: str) -> Instruction | None:
    t = text.strip()
    m = LANG_RX.search(t)
    if m and re.search(r"\b(i|we|they|he|she|people|everyone)\s+(\w+\s+)?$", t[:m.start()], re.I) \
            and not re.search(r"\b(can|could|will|would)\s+you\s+$", t[:m.start()], re.I):
        m = None                                   # "I speak English at work" is a fact, not an instruction
    if m:
        lang = (m.group(2) or m.group(3) or "").lower()
        if lang == "english":
            return Instruction("Reply in English. Use a Hindi word only if he speaks Hindi first.",
                               "language", "talk_style", "Sure, English from now on.")
        if lang in ("hindi", "hinglish"):
            return Instruction("Reply in Hinglish (Hindi + English, in Roman script).",
                               "language", "talk_style", "Theek hai, Hinglish mein baat karte hain.")
    if SHORT_RX.search(t):
        return Instruction("Keep replies short: one or two sentences unless he asks for detail.",
                           "brevity", "talk_style", "Got it, short and to the point.")
    if FEWER_Q_RX.search(t):
        return Instruction("Don't ask him questions unless you truly need an answer to help; never more than one.",
                           "questions", "talk_style", "Understood. Fewer questions.")
    if m := DONT_CALL_RX.search(t):
        name = m.group("name").strip()
        return Instruction(f"Never call him “{name}”.", f"dont_call:{name.lower()}", "boundary", "Noted, I won't.")
    if m := STOP_TOPIC_RX.search(t):
        topic = re.sub(r"^(my|the)\s+", "", m.group("topic").strip(), flags=re.I)
        if topic.lower() not in ("it", "that", "this", "me"):
            return Instruction(f"Don't bring up “{topic}” unless he mentions it first.", f"topic:{topic.lower()}",
                               "boundary", f"Okay, I won't bring up {topic} again.")
    if m := CALL_ME_RX.search(t):
        if re.match(r"^\s*(please\s+)?(call me|naam)\b", t, re.I):
            name = m.group("name")
            return Instruction(f"Call him “{name}”.", "call_me", "talk_style", f"Sure, {name}.", call_me=name)
    return None


def apply(ins: Instruction, episode_ids: list[int]) -> str:
    from .. import profile
    from .mdsync import render_all, sync
    from .sleep import apply_directive
    sync()                                         # never overwrite his own USER.md edits
    apply_directive({"directive": ins.directive, "category": ins.category, "supersession_key": ins.key}, episode_ids)
    if ins.call_me:
        profile.set("call_me", ins.call_me, "owner_edit")
    render_all()
    return ins.ack
