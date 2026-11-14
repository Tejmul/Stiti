"""What the tutor hears: her own voice, Whisper phantoms and noise never count as the learner (D40).

2026-11-11 log: "You (voice): Chalo today … let's go step by step. Before I explain anything, can't answer that one."
and "You (voice): Good question." were HER words coming back through the mic; "Two minutes, time's going to tell." and
"Kale, malawad, chendat …" (repeated) were Whisper hallucinating on noise. Each one cut her off, replayed the cue or
got "answered". Research: docs/research/tutor_teacher.md (LiveKit/Pipecat min-words barge-in, Bag of Hallucinations,
echo-text matching).

`EchoGuard.check()` runs on every voice transcript before the player sees it, and `barge_ok()` vetoes the barge-in
verdict (voice/endpoint.TurnTaker.veto) so her echo never even stops her. Pure code, ~0.1 ms, no models.
"""
from __future__ import annotations

import re
import threading
import time
from collections import deque
from difflib import SequenceMatcher

# ---- thresholds (tuned on the 2026-11-11 log; NOT yet calibrated on his real speakers/mic) ----
ECHO_WINDOW_S = 15.0       # her lines from the last 15 s are compared with what was heard
ECHO_TAIL_S = 1.5          # room echo / AEC residue: speech that STARTS this soon after her clip ended is suspect
ECHO_OVERLAP = 0.6         # ≥60% of the heard CONTENT words appear in her recent lines → her own voice …
ECHO_SEQUENCE = 0.6        # … or ≥60% of the heard words are runs (≥2 words, same order) of one of her lines
FUZZY_RATIO = 0.8          # "tokens" ≈ "token", "analysis" ≈ "analyses" (Whisper paraphrases the echo)
MIN_BARGE_WORDS = 3        # while she talks, a non-command needs ≥3 real words to count (Pipecat min_words=3)
DUP_WINDOW_S = 20.0        # the same transcript again this soon (and not a command) = a looping hallucination
UNCLEAR_NO_SPEECH = 0.5    # Whisper no_speech_prob above this = probably not speech (stt.UNCLEAR_NO_SPEECH)
UNCLEAR_LOGPROB = -1.0     # avg_logprob below this = Whisper wasn't sure (stt.UNCLEAR_LOGPROB)
CONFIDENT_NO_SPEECH, CONFIDENT_LOGPROB = 0.4, -0.8   # "bye" must be heard at least this clearly to end a lesson

# Bag of Hallucinations (Barański et al., ICASSP 2025) + phantoms seen in Stiti's own logs. Whole-line matches only.
PHANTOMS = {
    "thank you", "thank you very much", "thanks", "thanks for watching", "thank you for watching",
    "thanks for listening", "thank you for listening", "please subscribe", "subscribe", "like and subscribe",
    "see you next time", "see you in the next video", "you", "so", "the", "i", "um", "uh", "hmm",
    "music", "applause", "laughter", "silence", "foreign", "subtitles by the amara org community",
    "two minutes time's going to tell", "i'm sorry", "oh", "ah", "okay okay okay",
}
PHANTOM_RX = re.compile(r"(amara\.org|subtitles? by|transcri(bed|ption) by|www\.|\.com\b|thanks? (you )?for watching|"
                        r"\b(\w+)( \2){3,}\b)", re.I)          # last one: a word looping 4+ times
# heard while she speaks, these always stop her at once (a real "ruko" must never wait)
STOP_RX = re.compile(r"^(ruko|ruk|rukh|wait|stop|bas|hold on|hang on|pause|ek (second|sec|minute|min)|one sec|"
                     r"ek doubt|doubt|question|ek sawal|sawal|excuse me|sorry|suno|listen)\b")
# an explicit doubt opener: counts with only 2 words while she talks ("wait what", "how come", "matlab kya")
DOUBT_RX = re.compile(r"^(wait what|what|why|how|kya|kyun|kyu|kaise|matlab|doubt|question|but|lekin|explain|"
                      r"samajh nahi|didn'?t get|don'?t get|i don'?t understand)\b")


# function words don't prove anything: "what is a token?" shares "is a" with almost any sentence she says
STOPWORDS = set("""a an the is are was were be been am i you he she it we they me my your our this that these those
of to in on at for with by from and or but so if then than as do does did not no yes can could will would should
what why how when where who which there here just like very really also about into its it's i'm let's let us
hai hain ka ki ke ko se mein me toh to na ye yeh wo woh kya""".split())


def norm(t: str) -> str:
    return " ".join(re.sub(r"[^\w\s']", " ", (t or "").lower().replace("’", "'")).split())


def _stem(w: str) -> str:
    for suf in ("ing", "es", "ed", "s"):
        if len(w) > 4 and w.endswith(suf):
            return w[: -len(suf)]
    return w


def _in(w: str, pool: set[str]) -> bool:
    if w in pool or _stem(w) in pool:
        return True
    if len(w) < 4:
        return False
    return any(len(p) >= 4 and SequenceMatcher(None, w, p).ratio() >= FUZZY_RATIO for p in pool)


class EchoGuard:
    """Remembers what she said (and when it played) and judges each transcript: keep or drop, with a reason."""

    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self._said: deque[tuple[float, float, str]] = deque(maxlen=40)     # (start, end, text)
        self._heard: deque[tuple[float, str]] = deque(maxlen=8)
        self._lock = threading.Lock()
        self.dropped: list[tuple[str, str]] = []                           # (reason, text) — tests + debug

    # ---- her side
    def spoke(self, text: str, ms: int, start: float | None = None) -> None:
        t0 = self.clock() if start is None else start
        with self._lock:
            self._said.append((t0, t0 + max(0, ms) / 1000, text or ""))

    def stopped(self, at: float | None = None) -> None:
        """Playback was cut: her last clip ended now, not when it would have."""
        t = self.clock() if at is None else at
        with self._lock:
            if self._said and self._said[-1][1] > t:
                s, _, txt = self._said[-1]
                self._said[-1] = (s, t, txt)

    def speaking(self, at: float | None = None) -> bool:
        t = self.clock() if at is None else at
        return any(s <= t <= e for s, e, _ in self._said)

    def in_echo(self, at: float | None = None) -> bool:
        """`at` (when his speech started) falls while she was playing or within ECHO_TAIL_S after."""
        t = self.clock() if at is None else at
        return any(s - 0.2 <= t <= e + ECHO_TAIL_S for s, e, _ in self._said)

    def _recent(self, at: float) -> list[list[str]]:
        return [norm(txt).split() for s, e, txt in self._said if at - ECHO_WINDOW_S <= e and s <= at + 1.0]

    @staticmethod
    def echo_score(heard: list[str], lines: list[list[str]]) -> tuple[float, float]:
        """(content-word coverage, in-order run coverage) of `heard` against her recent `lines`."""
        pool = {w for x in lines for w in x}
        pool |= {_stem(w) for w in pool}
        cw = [x for x in heard if x not in STOPWORDS]
        cov = sum(_in(x, pool) for x in cw) / len(cw) if cw else 0.0
        seq = 0.0
        for line in lines:
            m = SequenceMatcher(None, heard, line, autojunk=False).get_matching_blocks()
            run = sum(b.size for b in m if b.size >= (1 if len(heard) <= 2 else 2))
            seq = max(seq, run / len(heard))
        return cov, seq

    # ---- his side
    def check(self, text: str, *, at: float | None = None, no_speech: float = 0.0, logprob: float = 0.0,
              barged: bool = False) -> tuple[bool, str]:
        """-> (keep, reason). `at` = when his speech started (TurnTaker start_t), default now."""
        from .commands import classify
        t = self.clock() if at is None else at
        n = norm(text)
        w = n.split()
        if not w:
            return self._drop("empty", text)
        cmd = classify(text)
        control = cmd not in ("question", "answer", "other", "confused", "end")
        stop = bool(STOP_RX.match(n))
        if n in PHANTOMS or PHANTOM_RX.search(text):
            return self._drop("phantom", text)
        now = self.clock()
        if not control and any(h == n and now - ht < DUP_WINDOW_S for ht, h in self._heard):
            return self._drop("looping", text)
        unclear = no_speech > UNCLEAR_NO_SPEECH or logprob < UNCLEAR_LOGPROB
        confident = no_speech < CONFIDENT_NO_SPEECH and logprob > CONFIDENT_LOGPROB
        if unclear and not (control or stop):
            return self._drop("unclear", text)
        echo = self.in_echo(t) and not barged
        doubt = bool(DOUBT_RX.match(n)) and len(w) >= 2
        if echo:
            lines = self._recent(t)
            if not stop and lines:
                cov, seq = self.echo_score(w, lines)
                if len(w) == 1 and (w[0] in lines[-1] or _stem(w[0]) in {_stem(x) for x in lines[-1]}):
                    return self._drop("her own voice", text)
                if len(w) >= 2 and (seq >= ECHO_SEQUENCE or (cov >= ECHO_OVERLAP and not doubt)):
                    return self._drop("her own voice", text)
            if cmd == "end" and not (confident and len(w) >= 2):
                return self._drop("unsure goodbye in her echo", text)
            if not (control or stop or doubt) and len(w) < MIN_BARGE_WORDS:
                return self._drop("too short to interrupt", text)
        elif cmd == "end" and len(w) == 1 and not confident:
            return self._drop("unsure goodbye", text)
        with self._lock:
            self._heard.append((now, n))
        return True, "ok"

    def barge_ok(self, text: str, res=None, at: float | None = None) -> bool:
        """Veto for the barge-in verdict: False = it was her echo / a phantom, keep talking."""
        keep, _ = self.check(text, at=at, no_speech=float(getattr(res, "no_speech_prob", 0.0) or 0.0),
                             logprob=float(getattr(res, "avg_logprob", 0.0) or 0.0))
        if keep:                                   # the real check runs again on the committed line; don't count twice
            with self._lock:
                if self._heard and self._heard[-1][1] == norm(text):
                    self._heard.pop()
        return keep

    def _drop(self, why: str, text: str) -> tuple[bool, str]:
        self.dropped.append((why, text))
        del self.dropped[:-50]
        return False, why
