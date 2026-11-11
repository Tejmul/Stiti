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
    lang_cmd: tuple[str, str | None] | None = None   # ("lock"|"unlock"|"switch", lang) — brain/lang.py


def parse(text: str) -> Instruction | None:
    t = text.strip()
    from . import lang as L
    m = LANG_RX.search(t)
    if m and re.search(r"\b(i|we|they|he|she|people|everyone)\s+(\w+\s+)?$", t[:m.start()], re.I) \
            and not re.search(r"\b(can|could|will|would)\s+you\s+$", t[:m.start()], re.I):
        pass                                       # "I speak English at work" is a fact, not an instruction
    elif c := L.command(t):
        op, lg = c                                 # D34: only an explicit lock is saved; "talk in X" just switches
        if op == "lock":
            return Instruction(L.lock_directive(lg), "language", "talk_style", L.phrase("locked", lg), lang_cmd=c)
        if op == "unlock":
            return Instruction("", "language", "talk_style", L.phrase("unlocked", "english"), lang_cmd=c)
        return Instruction("", "language", "talk_style", L.phrase("switched", lg), lang_cmd=c)
    if SHORT_RX.search(t):
        return Instruction("Keep replies short: one or two sentences unless he asks for detail.",
                           "brevity", "talk_style", "Got it. Short from now on.")
    if FEWER_Q_RX.search(t):
        return Instruction("Don't ask him questions unless you truly need an answer to help; never more than one.",
                           "questions", "talk_style", "Understood. Fewer questions from now on.")
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
    if ins.lang_cmd and ins.lang_cmd[0] in ("switch", "unlock"):
        from ..db import q                         # a switch/unlock ends any language rule (lock or old-style)
        from .lang import LANG_RULE_RX
        rows = q("SELECT id, directive FROM user_directives WHERE status='active' AND category='talk_style'")
        ids = [r["id"] for r in rows if r["directive"].startswith("Language lock:") or LANG_RULE_RX.search(r["directive"])]
        if ids:
            q("UPDATE user_directives SET status='superseded' WHERE id = ANY(%s)", (ids,))
        render_all()
        return ins.ack
    apply_directive({"directive": ins.directive, "category": ins.category, "supersession_key": ins.key}, episode_ids)
    if ins.call_me:
        profile.set("call_me", ins.call_me, "owner_edit")
    render_all()
    return ins.ack
