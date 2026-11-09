"""Interview engine for "Key Things to Know" — sections, progress, skip / pause / resume, consent.

Question content and the psychology mapping live in `brain/guide.py` (research-backed, editable);
this file only knows HOW to ask and record:
  kind="text"     free answer → handler (facts / directives / key-things capture)
  kind="scale"    spoken agreement → 1..5 → trait update (reverse-keyed items supported)
  kind="choice"   one of a few options (matched by keywords) → trait label
Any answer can be "skip"; "bas / later" pauses and it resumes at the same question next time;
"why?" explains why Stiti asks. Nothing is diagnostic — traits are tentative and shown in USER.md.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Callable

from ..config import CFG
from ..db import q

STATE = CFG.home / "intake.json"
SKIP_RX = re.compile(r"^\s*(skip|pass|next|chhodo|chodo|aage|nahi pata|don'?t know|pata nahi|rehne do)\b", re.I)
PAUSE_RX = re.compile(r"^\s*(bas|stop|later|baad mein|ruk|pause|enough)\b", re.I)
WHY_RX = re.compile(r"^\s*(why|kyun|kyu|why do you ask|ye kyun)\b", re.I)

LIKERT = [  # (pattern, score) — checked in order, first hit wins
    (r"\b(strongly disagree|bilkul nahi|bilkul bhi nahi|not at all|never|kabhi nahi|totally not)\b", 1),
    (r"\b(strongly agree|bilkul|definitely|totally|absolutely|hamesha|always|100|ekdum|very much|so much)\b", 5),
    (r"\b(disagree|not really|zyada nahi|rarely|kam hi|nope|nahi|no)\b", 2),
    (r"\b(neutral|sometimes|kabhi kabhi|depends|thoda|a bit|somewhat|maybe|beech mein|50 50|so so)\b", 3),
    (r"\b(agree|yes|haan|han|mostly|usually|aksar|yeah|yep|sahi|true)\b", 4),
]
NUM_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "ek": 1, "do": 2, "teen": 3, "char": 4, "paanch": 5}


def likert(text: str) -> int | None:
    t = text.lower()
    m = re.search(r"\b([1-5])\b", t)
    if m:
        return int(m.group(1))
    for w, n in NUM_WORDS.items():
        if re.search(rf"\b{w}\b", t):
            return n
    for rx, score in LIKERT:
        if re.search(rx, t):
            return score
    return None


@dataclass
class Question:
    key: str
    section: str
    ask: str                          # simple English
    ask_hi: str = ""                  # Hinglish variant
    kind: str = "text"                # text | scale | choice
    trait: str | None = None          # scale/choice → traits.key
    reverse: bool = False             # reverse-keyed scale item
    options: dict[str, str] = field(default_factory=dict)   # choice: label → keyword regex
    why: str = ""                     # answer to "why do you ask?"
    handler: Callable[[str], str | None] | None = None      # text: writes to brain, returns a note


def _score_scale(qn: Question, n: int) -> None:
    from .keythings import set_trait
    v = (6 - n if qn.reverse else n)
    rows = q("SELECT value, evidence FROM traits WHERE key=%s", (qn.trait,))
    # average with earlier items of the same trait (each trait usually has 2 items)
    prev = json.loads(_state().get("scores", "{}")).get(qn.trait, [])
    prev.append(v)
    st = _state()
    scores = json.loads(st.get("scores", "{}"))
    scores[qn.trait] = prev
    st["scores"] = json.dumps(scores)
    _save(st)
    mean = sum(prev) / len(prev)
    norm = (mean - 1) / 4
    from .guide import label_for
    set_trait(qn.trait, norm, label_for(qn.trait, norm), f"{qn.key}={n}", confidence=0.45 + 0.1 * len(prev),
              source="intake")
    del rows


def _choice(qn: Question, text: str) -> str | None:
    for label, rx in qn.options.items():
        if re.search(rx, text, re.I):
            return label
    return None


def _state() -> dict:
    return json.loads(STATE.read_text()) if STATE.exists() else {"step": 0, "done": False}


def _save(st: dict) -> None:
    STATE.write_text(json.dumps(st))


def done() -> bool:
    return _state().get("done", False)


class Intake:
    def __init__(self, questions: list[Question], intro: str, outro: Callable[[list[str]], str]):
        self.qs = questions
        self.intro = intro
        self.outro = outro
        st = _state()
        self.step = 0 if st.get("done") else st.get("step", 0)
        self.notes: list[str] = st.get("notes", [])

    def _ask(self, i: int) -> str:
        qn = self.qs[i]
        prev = self.qs[i - 1].section if i else None
        lead = ""
        if qn.section != prev:
            lead = f"[{qn.section}] "
        if i == len(self.qs) // 2:
            lead = "Halfway there 🙂 " + lead
        return lead + qn.ask

    def start(self) -> str:
        if self.step == 0:
            return self.intro + " " + self._ask(0)
        return "Picking up where we left off. " + self._ask(self.step)

    def answer(self, text: str, episode_id: int | None = None) -> tuple[str, bool]:
        qn = self.qs[self.step]
        if WHY_RX.match(text) and len(text.split()) <= 5:
            return (qn.why or "It helps me talk to you the way you like.") + " " + qn.ask, False
        if PAUSE_RX.match(text) and len(text.split()) <= 3:
            st = _state()
            st.update({"step": self.step, "done": False, "notes": self.notes})
            _save(st)
            return "No problem — say “key things” anytime and we'll continue from here.", True
        if not SKIP_RX.match(text):
            if episode_id:
                q("UPDATE episodes SET importance = 8 WHERE id=%s", (episode_id,))
            note = None
            if qn.kind == "scale":
                n = likert(text)
                if n is None:
                    return "Just roughly — would you say yes, sometimes, or not really?", False
                _score_scale(qn, n)
            elif qn.kind == "choice":
                label = _choice(qn, text)
                if label and qn.trait:
                    from .guide import CHOICE_VALUES
                    from .keythings import set_trait
                    set_trait(qn.trait, CHOICE_VALUES.get(qn.trait, {}).get(label), label, text[:120],
                              confidence=0.7, source="intake")
                    note = label
                elif qn.handler:
                    note = qn.handler(text)
            elif qn.handler:
                note = qn.handler(text)
            from .keythings import capture
            capture(text, episode_id)                    # likes / dislikes said along the way
            if note:
                self.notes.append(note)
        self.step += 1
        if self.step < len(self.qs):
            st = _state()
            st.update({"step": self.step, "done": False, "notes": self.notes})
            _save(st)
            return self._ask(self.step), False
        st = _state()
        st.update({"step": 0, "done": True, "notes": self.notes})
        _save(st)
        return self.outro(self.notes), True
