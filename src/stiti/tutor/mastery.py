"""What he knows, per concept — BKT-lite (D53; research: docs/research/tutor_agent.md, OATutor's BKT, Scarlatos et al.
LAK 2025: tag each answer with its concept, keep a tiny probability per concept).

p(known) moves with every graded answer:
  correct → posterior given P(correct | known) = 1 − SLIP, P(correct | unknown) = GUESS, then learning transit
  partial → half a step;  wrong / idk → the "incorrect" posterior
Stored per source (his file, or a topic) in ~/.stiti/tutor/mastery/<key>.json — plain JSON he can read; the lesson
queue is ordered from it, so the next lesson starts where he really is.

Every update with an origin is ALSO appended to Postgres `mastery_events` (feature 4; iTutor technique 5: beliefs are
never overwritten): concept, verdict, hints, p before/after and where it came from (probe / check / review / blurt).
The JSON stays the readable current value; the history gives the map's heatmap. A missing database never stops a
lesson — the event is just not logged.
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

PRIOR = 0.25          # a concept nobody has checked yet
SLIP, GUESS, TRANSIT = 0.10, 0.20, 0.15
KNOWN = 0.80          # ≥ this: confirm with one quick question, don't teach it again
SHAKY = 0.40          # between SHAKY and KNOWN: "nearly known" — first in line when time is short (Metcalfe & Kornell)
ORIGINS = ("probe", "check", "review", "blurt")


def bkt(p: float, verdict: str) -> float:
    """One BKT update for a graded answer (correct / partial / wrong / idk)."""
    if verdict not in ("correct", "partial", "wrong", "idk"):
        return p
    right = p * (1 - SLIP) / (p * (1 - SLIP) + (1 - p) * GUESS)
    wrong = p * SLIP / (p * SLIP + (1 - p) * (1 - GUESS))
    post = right if verdict == "correct" else wrong if verdict in ("wrong", "idk") else (right + wrong) / 2
    after = post + (1 - post) * TRANSIT
    return round(min(0.99, max(0.01, after)), 3)


def key_for(source: str) -> str:
    return hashlib.sha1(source.strip().lower().encode()).hexdigest()[:16]


def log_event(source_key: str, concept: str, verdict: str, p_before: float | None, p_after: float, origin: str,
              hints: int = 0) -> bool:
    """One row in mastery_events (append-only). False when it couldn't be written (never raises)."""
    if origin not in ORIGINS:
        return False
    try:
        from ..db import q
        q("""INSERT INTO mastery_events(source_key, concept_id, verdict, hints, p_before, p_after, origin)
             VALUES (%s,%s,%s,%s,%s,%s,%s)""",
          (source_key, str(concept)[:64], str(verdict)[:16], max(0, min(int(hints or 0), 9)), p_before, p_after,
           origin))
        return True
    except Exception:
        return False


class Mastery:
    def __init__(self, source: str, home: Path | None = None, events: bool = True):
        if home is None:
            from ..config import CFG
            home = CFG.home
        self.key = key_for(source)
        self.path = home / "tutor" / "mastery" / f"{self.key}.json"
        self.source = source
        self.events = events                         # False: the JSON only, no history rows
        self.p: dict[str, float] = {}
        self.seen: dict[str, float] = {}
        self.exam: str | None = None                 # ISO date of his exam, when a lesson's goal named one
        self.goal: dict | None = None             # his goal for this file: {mode, days, hours, exam_date, asked_at}
        self.asked: dict[str, dict] = {}          # normalised check question → {t, ok} (never re-ask a right one soon)
        try:
            d = json.loads(self.path.read_text())
            self.p, self.seen = d.get("p", {}), d.get("seen", {})
            self.exam = d.get("exam") if isinstance(d.get("exam"), str) else None
            self.goal = d.get("goal") if isinstance(d.get("goal"), dict) else None
            self.asked = d.get("asked") if isinstance(d.get("asked"), dict) else {}
        except Exception:
            pass

    def get(self, concept: str) -> float:
        return float(self.p.get(concept, PRIOR))

    def set(self, concept: str, p: float, *, verdict: str | None = None, origin: str | None = None,
            hints: int = 0) -> None:
        """Set p(known). With an origin (probe / check / review / blurt) the change is also logged as an event."""
        before = self.p.get(concept)
        self.p[concept] = round(min(0.99, max(0.01, p)), 3)
        self.seen[concept] = time.time()
        self.save()
        if origin and self.events:
            log_event(self.key, concept, verdict or "inferred", before, self.p[concept], origin, hints)

    def update(self, concept: str, verdict: str, *, origin: str = "check", hints: int = 0) -> float:
        self.set(concept, bkt(self.get(concept), verdict), verdict=verdict, origin=origin, hints=hints)
        return self.p[concept]

    def level(self, concept: str) -> str:
        p = self.get(concept)
        return "known" if p >= KNOWN else "shaky" if p >= SHAKY else "new"

    # ---- questions he already answered (pacing.Pacing's store: never the same question again too soon)
    def get_asked(self) -> dict[str, dict]:
        return self.asked

    def note_asked(self, question: str, ok: bool) -> None:
        if not question:
            return
        self.asked[question] = {"t": time.time(), "ok": bool(ok)}
        if len(self.asked) > 400:                 # keep the newest 400
            self.asked = dict(sorted(self.asked.items(), key=lambda kv: kv[1].get("t", 0))[-400:])
        self.save()

    # ---- his goal for this file, so the next lesson doesn't ask "is this for an exam?" again
    def set_goal(self, goal: dict) -> None:
        self.goal = {**{k: v for k, v in goal.items() if k in ("mode", "days", "hours", "hours_said")},
                     "asked_at": time.time()}
        if goal.get("mode") == "exam" and goal.get("days") is not None:   # a date, so "in 3 days" stays true
            self.goal["exam_date"] = time.strftime("%Y-%m-%d", time.localtime(time.time() + 86400 * int(goal["days"])))
            self.exam = self.goal["exam_date"]    # the map's "at risk on exam day" (D57) reads the same date
        self.save()

    def save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            d: dict = {"source": self.source, "p": self.p, "seen": self.seen}
            if self.exam:
                d["exam"] = self.exam
            if self.goal:
                d["goal"] = self.goal
            if self.asked:
                d["asked"] = self.asked
            self.path.write_text(json.dumps(d, indent=1))
        except Exception:
            pass
