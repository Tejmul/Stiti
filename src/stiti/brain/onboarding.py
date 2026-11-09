"""Onboarding interview: Stiti gets to know Tejmul in ~3 minutes — no LLM needed.

10 short questions (voice or text). Each answer is stored verbatim as a high-importance episode
(the night job can extract more later) AND written straight into the brain deterministically:
facts about him, people in his life (name → relation), routine, goals, how to talk to him,
boundaries, what helps when he's low. "skip" skips a question; "bas / later" pauses and it
resumes where it stopped. Re-running it supersedes old answers (same keys), never duplicates.
"""
from __future__ import annotations

import json
import re

from ..config import CFG
from ..db import one, q

STATE = CFG.home / "onboarding.json"
START_RX = re.compile(r"\b(onboard(ing)?|get to know me|mujhe jaano|mere baare mein jaano|intro (karte|karo|shuru)|"
                      r"let'?s do the intro|shuru karo|start (the )?intro)\b", re.I)
SKIP_RX = re.compile(r"^\s*(skip|pass|next|chhodo|chodo|aage|nahi pata|don'?t know)\b", re.I)
PAUSE_RX = re.compile(r"^\s*(bas|stop|later|baad mein|ruk|pause)\b", re.I)
NOTHING_RX = re.compile(r"^\s*(nothing|none|no|kuch nahi|nahi|nope|kuch bhi nahi)\s*\.?$", re.I)

QUESTIONS = [
    ("name", "Pehle basics — what should I call you?"),
    ("home", "Where do you live right now, and where's home originally?"),
    ("work", "What do you do — job, studies, side projects?"),
    ("people", "Who are the most important people in your life? Say it like “Priya — sister, Arjun — best friend”."),
    ("day", "Walk me through a normal day — when do you wake up, work, and sleep?"),
    ("goals", "What are you working towards right now? One to three goals."),
    ("talk", "How should I talk to you — language, length, humour, anything that annoys you?"),
    ("never", "Anything I should never do or bring up?"),
    ("support", "When you're stressed or low, what actually helps — space, a joke, a plan, or just listening?"),
    ("role", "Last one: what do you want me to be for you?"),
]


def _state() -> dict:
    return json.loads(STATE.read_text()) if STATE.exists() else {"step": 0, "done": False}


def _save(st: dict) -> None:
    STATE.write_text(json.dumps(st))


def done() -> bool:
    return _state().get("done", False)


def _directive(text: str, category: str, key: str) -> None:
    from .sleep import apply_directive
    apply_directive({"directive": text, "category": category, "supersession_key": key}, [])
    q("UPDATE user_directives SET origin='onboarding' WHERE status='active' AND supersession_key=%s", (key,))


def _self_fact(key: str, text: str) -> None:
    """Functional self-fact keyed by `key`: re-onboarding closes the old value instead of duplicating."""
    from .sleep import resolve_entity
    from .. import profile
    me = resolve_entity(profile.name(), "self")
    pred = f"about_{key}"
    old = one("""SELECT id FROM facts WHERE subj_id=%s AND predicate=%s AND upper_inf(recorded) AND valid @> now()""",
              (me, pred))
    if old:
        q("UPDATE facts SET valid = tstzrange(lower(valid), now()) WHERE id=%s", (old["id"],))
    q("""INSERT INTO facts(subj_id, predicate, obj_literal, fact_text, functional, confidence, origin)
         VALUES (%s,%s,%s,%s,true,0.95,'onboarding')""", (me, pred, text, text))


PERSON_PATTERNS = [
    # "my sister Priya" / "meri sister Priya" / "mera dost Arjun"  (checked first)
    re.compile(r"^(?:my|meri|mera|mere)\s+(?P<rel>[a-z][a-z ]{1,25}?)\s+(?P<name>[A-Z][\w.']{1,30})\s*$", re.I),
    # "Priya — sister" / "Neha: cousin" / "Mummy (mom)" / "Rahul is my manager"
    re.compile(r"^(?P<name>[A-Za-z][\w.' ]{0,30}?)(?:\s*[—–:(-]\s*|\s+is\s+)(?:my\s+)?(?P<rel>[a-z][a-z ]{1,25}?)\)?\s*$",
               re.I),
]


def parse_people(text: str) -> list[tuple[str, str]]:
    out = []
    for item in re.split(r"[,;\n]|\band\b|\baur\b", text):
        item = item.strip(" .")
        if not item:
            continue
        for rx in PERSON_PATTERNS:
            m = rx.match(item)
            if m:
                name, rel = m["name"].strip().title(), m["rel"].strip().lower()
                if 1 < len(name) <= 30 and rel not in ("a", "the"):
                    out.append((name, rel))
                break
    return out


def _apply(key: str, ans: str) -> str | None:
    """Write one answer into the brain. Returns a short note of what was learned."""
    from .sleep import apply_fact
    a = ans.strip().rstrip(".")
    if key == "name":
        name = re.sub(r"^(call me|you can call me|mujhe|i'?m|main)\s+", "", a, flags=re.I).split()[0:3]
        name = " ".join(name).strip(" ,.") or a
        _directive(f"Call him “{name}”", "talk_style", "call_me")
        return f"what to call you ({name})"
    if key == "home":
        _self_fact("home", f"Home: {a}")
        return "where you live"
    if key == "work":
        _self_fact("work", f"Work: {a}")
        return "what you do"
    if key == "people":
        people = parse_people(a)
        for name, rel in people:
            from .. import profile
            owner = profile.name()
            apply_fact({"subject": name, "predicate": f"{rel.replace(' ', '_')}_of", "object": owner,
                        "fact_text": f"{name} is {owner}'s {rel}", "confidence": 0.95},
                       [], {name.lower(): "person", owner.lower(): "self"})
        if not people:
            _self_fact("people", f"Important people: {a}")
        return f"{len(people)} people" if people else "your people"
    if key == "day":
        _directive(f"His normal day: {a}", "routine", "routine_day")
        return "your routine"
    if key == "goals":
        goals = [g.strip(" .") for g in re.split(r"[,;\n]|\b\d[.)]\s*", a) if len(g.strip(" .")) > 2][:3]
        for i, g in enumerate(goals or [a], 1):
            _directive(f"Working towards: {g}", "goal", f"goal_{i}")
        return f"{len(goals) or 1} goal(s)"
    if key == "talk":
        _directive(f"How he wants to be talked to: {a}", "talk_style", "talk_pref")
        return "how to talk to you"
    if key == "never":
        if NOTHING_RX.match(a):
            return None
        rule = re.sub(r"^(please\s+)?(never|don'?t|do not|mat)\s+", "", a, flags=re.I)
        _directive(f"Never {rule}", "boundary", "boundary_main")
        return "what to never do"
    if key == "support":
        _directive(f"When he's stressed or low, what helps: {a}", "preference", "support_style")
        return "what helps when you're low"
    if key == "role":
        _directive(f"He wants Stiti to be: {a}", "preference", "stiti_role")
        return "what I should be for you"
    return None


class Onboarding:
    def __init__(self):
        st = _state()
        self.step = st.get("step", 0) if not st.get("done") else 0
        self.learned: list[str] = st.get("learned", [])

    def start(self) -> str:
        intro = ("Chalo, let's get to know each other — 10 quick questions. Say “skip” to skip one, "
                 "or “bas” to stop and continue later. ") if self.step == 0 else "Picking up where we left off. "
        return intro + QUESTIONS[self.step][1]

    def answer(self, text: str, episode_id: int | None = None) -> tuple[str, bool]:
        """Returns (reply, finished)."""
        if PAUSE_RX.match(text) and len(text.split()) <= 3:
            _save({"step": self.step, "done": False, "learned": self.learned})
            return "No problem — say “intro shuru karo” anytime and we'll continue from here.", True
        key, _ = QUESTIONS[self.step]
        if not SKIP_RX.match(text):
            if episode_id:
                q("UPDATE episodes SET importance = 8 WHERE id=%s", (episode_id,))
            note = _apply(key, text)
            if note:
                self.learned.append(note)
        self.step += 1
        if self.step < len(QUESTIONS):
            _save({"step": self.step, "done": False, "learned": self.learned})
            return QUESTIONS[self.step][1], False
        _save({"step": 0, "done": True, "learned": self.learned})
        from .mdsync import render_all
        from .sleep import standing_profile
        standing_profile()
        render_all()
        got = ", ".join(self.learned[:4]) + (", and more" if len(self.learned) > 4 else "")
        return (f"Thank you! 💛 Now I know {got}. It's all in ~/.stiti/USER.md — edit it anytime and "
                "I'll follow your version."), True
