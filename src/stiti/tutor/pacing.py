"""Pacing of checks + the hint ladder's rungs — code-owned, no LLM (Feature 5).

Research: docs/research/apps/itutor.md "Techniques for Stiti" #1 (their own data: learners felt questions came too
early → explain first, one check per full idea) and the code-owned hint ladder (nudge → hint → worked example →
answer); docs/research/apps/coconote.md T4 (Blurt). The owner's two complaints pull both ways — "it keeps on saying,
saying" (too long without his turn) and "it asks the same questions again and again" — so:

- a check comes after a full idea: ≥ MIN_GAP spoken lesson sentences since the last one (a concept still gets one);
- when he sounds fed up — curt non-answers ("ok", "whatever", "just tell me"), "skip the questions" / "just teach",
  or a stressed voice on a curt answer — checks get sparser (SPARSE_GAP) for the rest of the session, said once;
- never the same question twice in a session, and not one he answered right in the last REASK_DAYS days.
"""
from __future__ import annotations

import re
import time

MIN_GAP = 3            # spoken lesson sentences between two checks (one full idea)
SPARSE_GAP = 7         # … after he showed he wants fewer questions (≈ one check per two concepts)
WINDOW = 5             # the last N check answers decide whether he is fed up
FED_UP = 2.5           # curt-signal sum in that window that makes checks sparser
REASK_DAYS = 3         # a question he answered right this recently is not asked again (across sessions)

# a non-answer that says "I'm done with questions" — not an honest "I don't know" (that gets the ladder)
CURT_RX = re.compile(r"^(ok(ay)?|k|yes|yeah|yep|no|nope|fine|whatever|hmm+|sure|next|pass|come on|ugh+|bas|"
                     r"chhodo|jo bhi|tell me|just tell( me)?( it)?|just say( it)?|leave it|forget it|move on)\W*$")
ANNOYED_RX = re.compile(r"\b(whatever|come on|ugh+|just tell me|seriously|again\?|enough)\b")

RUNGS = ["none", "nudge", "hint", "example", "answer"]   # rung index = how far down the ladder he needed to go


_SENT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(“‘])")


def sentences(text: str) -> int:
    """Spoken sentences in a line ('You seem to know X. Quick check.' = 2)."""
    return len([s for s in _SENT.split((text or "").strip()) if s.strip()]) if (text or "").strip() else 0


def norm_q(text: str) -> str:
    """'Quick one: What does the lexer OUTPUT?' ≈ 'what does the lexer output' — the same question, said again."""
    t = re.sub(r"[^a-z0-9 ]+", " ", (text or "").lower())
    t = re.sub(r"^\s*(quick one|quick check|okay|ok|so|now|and|tell me)\b\s*", "", t)
    return " ".join(t.split())


def rung_rating(verdict: str | None, rung: int = 0, confidence: int | None = None) -> str:
    """Where on the ladder he got it → an FSRS rating name: unaided → good (easy when sure) · after a nudge or a
    hint → hard · only after the worked example or the answer → again."""
    if verdict not in ("correct", "partial") or rung >= 3:
        return "again"
    if verdict == "partial" or rung >= 1 or (confidence is not None and confidence <= 2):
        return "hard"
    return "easy" if confidence == 5 else "good"


def mastery_verdict(verdict: str | None, rung: int = 0) -> str | None:
    """A right answer reached only with help is evidence of partial knowledge, not mastery (BKT input)."""
    if verdict == "correct" and rung >= 3:
        return "wrong"
    if verdict == "correct" and rung >= 1:
        return "partial"
    return verdict


class Pacing:
    """How often she asks. `store` (optional) remembers questions across sessions: an object with get_asked() ->
    {norm: {"t": ts, "ok": bool}} and note_asked(norm, ok) (the coach's Mastery)."""

    def __init__(self, min_gap: int = 0, store=None):
        self.min_gap = min_gap
        self.sparse = False
        self.sparse_why = ""
        self.sparse_at = -1
        self.since = 0                       # spoken lesson sentences since the last check
        self.gaps: list[int] = []            # `since` at every check asked (tests: ≥ MIN_GAP on average)
        self.seen: set[str] = set()
        self.signals: list[float] = []
        self.store = store

    @property
    def gap(self) -> int:
        return max(self.min_gap, SPARSE_GAP) if self.sparse else self.min_gap

    # ---- sentences and checks
    def taught(self, n: int = 1) -> None:
        self.since += n

    def asked(self, prompt: str | None = None) -> None:
        self.gaps.append(self.since)
        self.since = 0
        if prompt:
            self.seen.add(norm_q(prompt))

    def repeat(self, prompt: str) -> bool:
        """Asked already this session, or answered right in the last REASK_DAYS days (another session)."""
        n = norm_q(prompt)
        if not n:
            return False
        if n in self.seen:
            return True
        if self.store is not None:
            try:
                rec = self.store.get_asked().get(n)
            except Exception:
                rec = None
            if rec and rec.get("ok") and time.time() - float(rec.get("t", 0)) < REASK_DAYS * 86400:
                return True
        return False

    def answered(self, prompt: str, ok: bool) -> None:
        self.seen.add(norm_q(prompt))
        if self.store is not None:
            try:
                self.store.note_asked(norm_q(prompt), ok)
            except Exception:
                pass

    # ---- is he fed up with questions?
    def go_sparse(self, why: str) -> bool:
        """-> True only the first time (the caller says "Okay, fewer questions." once)."""
        if self.sparse:
            return False
        self.sparse, self.sparse_why = True, why
        self.sparse_at = len(self.gaps)      # checks asked before it (tests: the ones after are further apart)
        return True

    def note(self, text: str, verdict: str | None, emotion: str | None = None) -> bool:
        """One check answer → curt signal. -> True when he's now fed up and not sparse yet (the caller then calls
        go_sparse and says so once)."""
        t = " ".join(re.sub(r"[^\w\s?']", " ", (text or "").lower()).split())
        s = 0.0
        if CURT_RX.match(t) or ANNOYED_RX.search(t):
            s = 1.0
        elif len(t.split()) <= 2 and verdict in ("wrong", "idk") and emotion in ("stressed", "angry", "frustrated"):
            s = 1.0                         # a two-word miss in a tense voice
        if s and emotion in ("stressed", "angry", "frustrated"):
            s += 0.5
        self.signals = (self.signals + [s])[-WINDOW:]
        return sum(self.signals) >= FED_UP and not self.sparse
