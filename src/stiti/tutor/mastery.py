"""What he knows, per concept — BKT-lite (D53; research: docs/research/tutor_agent.md, OATutor's BKT, Scarlatos et al.
LAK 2025: tag each answer with its concept, keep a tiny probability per concept).

p(known) moves with every graded answer:
  correct → posterior given P(correct | known) = 1 − SLIP, P(correct | unknown) = GUESS, then learning transit
  partial → half a step;  wrong / idk → the "incorrect" posterior
Stored per source (his file, or a topic) in ~/.stiti/tutor/mastery/<key>.json — plain JSON he can read; the lesson
queue is ordered from it, so the next lesson starts where he really is.
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


class Mastery:
    def __init__(self, source: str, home: Path | None = None):
        if home is None:
            from ..config import CFG
            home = CFG.home
        self.path = home / "tutor" / "mastery" / f"{key_for(source)}.json"
        self.source = source
        self.p: dict[str, float] = {}
        self.seen: dict[str, float] = {}
        try:
            d = json.loads(self.path.read_text())
            self.p, self.seen = d.get("p", {}), d.get("seen", {})
        except Exception:
            pass

    def get(self, concept: str) -> float:
        return float(self.p.get(concept, PRIOR))

    def set(self, concept: str, p: float) -> None:
        self.p[concept] = round(min(0.99, max(0.01, p)), 3)
        self.seen[concept] = time.time()
        self.save()

    def update(self, concept: str, verdict: str) -> float:
        self.set(concept, bkt(self.get(concept), verdict))
        return self.p[concept]

    def level(self, concept: str) -> str:
        p = self.get(concept)
        return "known" if p >= KNOWN else "shaky" if p >= SHAKY else "new"

    def save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps({"source": self.source, "p": self.p, "seen": self.seen}, indent=1))
        except Exception:
            pass
