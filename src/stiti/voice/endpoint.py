"""Turn-taking decisions: when has he FINISHED, when should she STOP, and what to learn about his pace.

Pure logic: no audio libraries, no threads, no clocks of its own. The voice loop feeds `TurnTaker.feed()` one
32 ms frame at a time (frame + Silero VAD probability + the time + "is she playing?") and gets back events
(duck / pause / resume / stop her playback, cancel the pending reply, commit a turn). Tests drive the same
class with synthetic VAD sequences and a fake STT (tests/turn_eval.py).

Design + numbers: docs/research/conversation_turn_taking.md §3–§4 and the ElevenLabs/Deepgram notes.
- End of turn = Smart Turn ONCE at 300 ms (bar 0.5, Pipecat) + a text check on the transcript we already start at
  160 ms (TEN's finished / unfinished / wait) + an adaptive wait (LiveKit min/max delay, OpenAI "low" 8 s):
    finished & audio ≥ 0.5 → commit when the transcript is ready (~450 ms)
    finished & audio < 0.5 → learned min_delay (starts at 0.6 s)
    unfinished             → 3.0 s           wait phrase ("hold on", "ek sec", "ruko") → 8 s, then silence
- Continuation grace (Bolna 900 ms / LiveKit cancel-on-speech): ≥300 ms of his speech after a commit and before
  her first audio (or within 0.9 s of it) cancels the pending reply and the texts are joined.
- His pace is learned (LiveKit DynamicEndpointing): EMA α=0.9 of his in-turn pauses and of "immediate
  interruptions", clamped 0.5–3.0 s, saved in ~/.stiti/turn_stats.json.
- Barge-in, two stages (ElevenLabs/Deepgram + LiveKit pause/resume): 250 ms of his speech → duck her to 30 %;
  900 ms → pause (buffer kept). His words decide: a stop word or ≥2 words → stop; a backchannel, one word or
  1.5 s of quiet → resume. Echo guard: none in the first 3 s after start-up or the first 250 ms of a playback,
  VAD bar 0.7 while she speaks.
"""
from __future__ import annotations

import json
import os
import re
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

# ---------------------------------------------------------------- numbers (research doc §3/§4)
FRAME_MS = 32
SPEC_STT_MS = 160            # start transcribing this early in a pause (thrown away if he goes on)
SMART_TURN_MS = 300          # ask Smart Turn once, here
SMART_BAR = 0.5              # fixed bar (Pipecat); no falling bar, no 1.5 s hard cut
UNFINISHED_WAIT_S = 3.0      # LiveKit max_delay / Pipecat stop_secs
WAIT_PHRASE_S = 8.0          # "hold on" / "ek sec": OpenAI semantic VAD "low" eagerness max
MAX_UTTER_MS = 30000         # safety: a 30 s monologue is committed anyway
PREROLL_FRAMES = 10          # ~320 ms of audio before the first speech frame
VAD_BAR = 0.5
VAD_BAR_SPEAKING = 0.7       # stricter while she talks (echo residue)
AEC_WARMUP_S = 3.0           # no barge-in right after start-up (LiveKit aec_warmup_duration)
PLAYBACK_GUARD_S = 0.25      # ... nor in the first 250 ms of each playback
DUCK_MS = 250                # stage 1: duck her voice
FORCE_PAUSE_MS = 900         # stage 2: pause her if his words still haven't decided (Hume min_interruption 800)
BARGE_QUIET_S = 1.5          # paused/ducked and nothing real came → resume
CONT_MIN_SPEECH_MS = 300     # continuation grace: this much of his speech after a commit …
CONT_GRACE_S = 0.9           # … before her first audio or within 0.9 s of it (Bolna incremental_delay)
PREFIX_TTL_S = 20.0          # a kept fragment ("Mm-hm?") is joined only if he goes on within this
BYE_MIN_SPEECH_MS = 300      # "bye" gate
BLIP_MS = 500                # less speech than this AND an unsure transcript = a blip: ignored, never "Sorry?" (Wispr)
ECHO_TAIL_S = 1.2            # speech that starts this soon after her audio ended is suspect
MIN_DELAY_START, MIN_DELAY_MIN, MIN_DELAY_MAX = 0.6, 0.5, 3.0
EMA_ALPHA = 0.9
LEARN_PAUSE_MIN_S = 0.3      # shorter gaps are VAD jitter, not "his pauses"

# ---------------------------------------------------------------- text check: finished / unfinished / wait
CONNECT = {
    # English: conjunctions, prepositions, articles, possessives, fillers (a sentence can't end on these)
    "and", "but", "so", "or", "because", "cause", "cuz", "if", "like", "to", "of", "for", "with", "the", "a", "an",
    "my", "your", "his", "her", "our", "their", "at", "from", "about", "into", "than", "very", "every", "just",
    "plus", "until", "unless", "whether", "although", "i'll", "i'm", "i've", "i'd", "um", "uh", "umm", "uhh", "erm",
    "hmm", "basically",
    # Hindi / Hinglish
    "aur", "lekin", "par", "magar", "toh", "kyunki", "kyonki", "kyuki", "matlab", "yaani", "ki", "ke", "ka", "ko",
    "se", "mein", "pe", "jaise", "phir", "fir", "ya", "agar", "jab", "jo",
    # two-word tails
    "and then", "so like", "i mean", "haan toh", "aur phir", "and i", "so i", "but i", "then i", "if i",
    "because i", "that i", "when i", "and so", "so that", "and um", "and uh", "so um", "so uh",
}
# a "?" from Whisper doesn't rescue these ("Mujhe lagta hai ki?" is Whisper hearing a rising pitch, not a question)
HARD_CONNECT = {"and", "but", "or", "because", "cause", "cuz", "the", "a", "an", "my", "your", "um", "uh", "umm",
                "uhh", "erm", "aur", "lekin", "magar", "kyunki", "kyonki", "kyuki", "yaani", "ki", "ke", "ka", "ko",
                "jo", "agar", "jab"}
# common endings that LOOK like a connector but close the sentence ("I think so", "I'd love to", "chalo phir")
FINISHED_TAILS = {
    "think so", "hope so", "guess so", "said so", "believe so", "suppose so", "why so", "do so", "so so", "or so",
    "love to", "like to", "have to", "used to", "just because", "as if", "oh my", "you like", "you'd like",
    "chalo phir", "okay phir", "ok phir", "theek hai phir", "acha phir", "achha phir",
}
OPENERS = {
    "so", "and", "okay so", "ok so", "well", "um", "uh", "umm", "hmm", "acha", "achha", "accha", "toh", "to", "aur",
    "listen", "suno", "hey", "but", "also", "and also", "actually", "basically", "and then", "so basically",
    "okay and", "haan toh", "achha toh", "acha toh", "i mean", "see", "dekho", "like", "so um", "so uh", "and um",
}
WAIT_RX = re.compile(
    r"\b(hold on|wait|one (sec|second|min|minute)|let me think|give me a (sec|second|minute|moment)|"
    r"ek (sec|second|min|minute)|ruko|ruk ja|rukna|soch(ne do| ke batata| ke bataunga| raha)|hang on|"
    r"just a (sec|second|moment)|a moment)\b")
# an action that still lacks its slot: "remind me", "set an alarm for", "add to"
SLOT_END_RX = re.compile(r"\b(remind me( to| at| about| on)?|set (an? )?(alarm|timer|reminder)( for| at)?|"
                         r"add( to)?|wake me( up)?( at)?)$")
BACKCHANNEL_WORDS = {
    "haan", "han", "ha", "hmm", "hm", "mhm", "mm", "mmhmm", "uh", "huh", "ok", "okay", "yeah", "yes", "yep", "ya",
    "acha", "achha", "accha", "right", "sure", "ji", "theek", "thik", "hai", "sahi", "cool", "nice", "got", "it",
}
STOP_WORDS = {"stop", "wait", "ruko", "ruk", "bas", "chup", "enough", "no", "nahi", "nope", "suno", "listen", "shh",
              "shush"}


def normalize(t: str) -> str:
    return " ".join(re.sub(r"[^\w\s']", " ", (t or "").lower().replace("’", "'")).split())


def words(t: str) -> list[str]:
    return normalize(t).split()


def text_state(t: str) -> str:
    """'finished' | 'unfinished' | 'wait' for a (joined) transcript. Pure string rules, < 1 ms."""
    raw = (t or "").strip()
    w = words(raw)
    if not w:
        return "unfinished"
    s = " ".join(w)
    m = None
    for m in WAIT_RX.finditer(s):
        pass
    if m is not None and len(w) <= 8 and len(s[m.end():].split()) <= 1:   # "hold on", "ek sec yaar" — not "wait, what's…"
        return "wait"
    question = raw.endswith("?")
    if s in OPENERS and not question:
        return "unfinished"
    if raw.endswith(("...", "…", ",", "-", "—")):
        return "unfinished"
    if question and not (len(w) > 1 and w[-1] in HARD_CONNECT):
        return "finished"
    tail2 = " ".join(w[-2:])
    if tail2 in FINISHED_TAILS or " ".join(w[-3:]) in FINISHED_TAILS:
        return "finished"
    if w[-1] in CONNECT or tail2 in CONNECT:
        return "unfinished"
    if SLOT_END_RX.search(s):
        return "unfinished"
    return "finished"


def join_text(prefix: str, text: str) -> str:
    """Glue a kept fragment and its continuation: "So..." + "I was thinking" → "So I was thinking"."""
    prefix, text = (prefix or "").strip(), (text or "").strip()
    if not prefix:
        return text
    if not text:
        return prefix
    first = words(text)[:1]
    if prefix.endswith(("...", "…", ",", "-", "—")) or (first and (first[0] in CONNECT or first[0] in OPENERS)):
        prefix = prefix.rstrip(" .…,-—")
        if first and text[:1].isupper() and not text.startswith(("I ", "I'")):
            text = text[:1].lower() + text[1:]
    return f"{prefix} {text}"


def wait_for(state: str, p_audio: float | None, min_delay: float) -> float:
    """Seconds of silence before committing. Confident turns stay at D18 speed (0 extra) unless he has taught
    her to wait longer (learned min_delay above its start value)."""
    if state == "noise":
        return 0.0
    if state == "wait":
        return WAIT_PHRASE_S
    if state == "unfinished":
        return UNFINISHED_WAIT_S
    if p_audio is not None and p_audio >= SMART_BAR:
        return max(0.0, min_delay - MIN_DELAY_START)
    return min_delay


def barge_verdict(text: str, confident: bool = True) -> str:
    """While she talks: 'stop' (a stop word, or ≥2 real words) or 'resume' (backchannel, one word, nothing)."""
    w = words(text)
    if not w:
        return "resume"
    if all(x in BACKCHANNEL_WORDS for x in w):
        return "resume"
    if w[0] in STOP_WORDS or " ".join(w[:2]) in ("shut up", "hold on", "hang on", "bas karo", "chup karo",
                                                 "band karo", "rehne do", "ek sec", "one sec"):
        return "stop" if (confident or len(w) >= 2) else "resume"
    return "stop" if len(w) >= 2 else "resume"


# ---------------------------------------------------------------- his pace (LiveKit DynamicEndpointing)
class TurnStats:
    """min_delay = EMA(α=0.9) of his in-turn pauses and of the pauses she cut into, clamped 0.5–3.0 s."""

    def __init__(self, path: Path | str | None = None):
        if path is None:
            from ..config import CFG
            path = CFG.home / "turn_stats.json"
        self.path = Path(path)
        self.min_delay = MIN_DELAY_START
        self.pauses = self.interrupts = self.commits = 0
        self._lock = threading.Lock()
        try:
            d = json.loads(self.path.read_text())
            self.min_delay = _clamp(float(d.get("min_delay", MIN_DELAY_START)))
            self.pauses, self.interrupts = int(d.get("pauses", 0)), int(d.get("interrupts", 0))
            self.commits = int(d.get("commits", 0))
        except Exception:
            pass

    def _ema(self, x: float) -> None:
        self.min_delay = _clamp(EMA_ALPHA * self.min_delay + (1 - EMA_ALPHA) * x)

    def observe_pause(self, seconds: float) -> None:
        """He paused this long inside one turn and went on (we correctly waited)."""
        with self._lock:
            self.pauses += 1
            self._ema(seconds)
        self.save()

    def immediate_interrupt(self, seconds: float) -> None:
        """She answered and he went on talking: his real pause was `seconds` → learn to wait a bit longer than
        that (never shorter than now: being cut off is never a reason to hurry)."""
        with self._lock:
            self.interrupts += 1
            self._ema(max(seconds + 0.1, self.min_delay))
        self.save()

    def committed(self) -> None:
        self.commits += 1

    def save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps({"min_delay": round(self.min_delay, 3), "pauses": self.pauses,
                                       "interrupts": self.interrupts, "commits": self.commits}))
            os.replace(tmp, self.path)
        except Exception:
            pass


def _clamp(x: float) -> float:
    return max(MIN_DELAY_MIN, min(MIN_DELAY_MAX, x))


# ---------------------------------------------------------------- results the loop acts on
@dataclass
class Pending:
    """A committed turn she's answering. Cancellable while his continuation can still be joined to it."""
    text: str
    committed_t: float
    speech_end_t: float
    first_audio_t: float | None = None
    cancelled: bool = False
    action: dict | None = None        # fast-path write the engine did for it (undone if it gets joined)
    work: Any = None                  # the engine thread

    def covers(self, start_t: float) -> bool:
        return start_t >= self.committed_t - 0.05 and (
            self.first_audio_t is None or start_t <= self.first_audio_t + CONT_GRACE_S)

    def expired(self, now: float) -> bool:
        return self.first_audio_t is not None and now > self.first_audio_t + CONT_GRACE_S


@dataclass
class Commit:
    """One finished user turn. Behaves like the audio array for old callers (len(), np.asarray())."""
    audio: Any
    spec: Any = None                  # Future[STTResult] started in the pause (None if cut by max length)
    res: Any = None                   # STTResult if it was ready at commit
    prefix: str = ""                  # fragment(s) this one continues
    state: str | None = None          # finished | unfinished | wait (None: no transcript yet)
    timed_out: bool = False           # committed by the 3 s / 8 s timeout, not because he finished
    speech_ms: int = 0
    start_t: float = 0.0
    end_t: float = 0.0                # his last speech frame
    commit_t: float = 0.0
    overlap: bool = False             # began while she was speaking
    barged: bool = False              # a confirmed barge-in (his words stopped her)
    reprompted: bool = False          # the prefix already got a "Mm-hm?" once
    replaces: Pending | None = None   # the reply this continuation cancelled

    @property
    def text(self) -> str | None:
        """Prefix + what he said; "" for noise (an empty transcript never re-sends a kept fragment) and for a blip:
        under 0.5 s of speech that Whisper wasn't sure about (a cough, a tap: Wispr drops these instead of asking)."""
        if self.res is None:
            return None
        if not (self.res.text or "").strip() or self.blip:
            return ""
        return join_text(self.prefix, self.res.text)

    @property
    def blip(self) -> bool:
        return 0 < self.speech_ms < BLIP_MS and bool(getattr(self.res, "unclear", False)) and not self.barged

    def __len__(self) -> int:
        return len(self.audio)

    def __bool__(self) -> bool:                       # a commit is always "something", even with no audio
        return True

    def __array__(self, dtype=None, copy=None):
        import numpy as np
        return np.asarray(self.audio, dtype=dtype)


def goodbye_counts(c: Commit, res, audio_ended_at: float | None) -> bool:
    """'Bye'/'stop' only counts if it was real speech: long enough, confidently heard, and not the echo tail
    of her own reply (17 of 41 logged lines were a phantom "Bye." right after she spoke)."""
    if res is None or not getattr(res, "confident", False):
        return False
    if c.barged:
        return True
    if c.speech_ms < BYE_MIN_SPEECH_MS:
        return False
    return not in_echo_tail(c, audio_ended_at)


def in_echo_tail(c: Commit, audio_ended_at: float | None) -> bool:
    return (not c.barged and audio_ended_at is not None and c.start_t - audio_ended_at < ECHO_TAIL_S
            and c.start_t > audio_ended_at - 30)


# ---------------------------------------------------------------- the frame-by-frame state machine
class TurnTaker:
    """Segmenter + endpointer + barge-in + continuation grace. `submit_stt(audio) -> Future[STTResult]`,
    `smart_turn(audio) -> float`. `concat(frames) -> audio`. All times in seconds (any monotonic clock)."""

    def __init__(self, stats: TurnStats, submit_stt: Callable, smart_turn: Callable, *, aec: bool = True,
                 start_t: float = 0.0, concat: Callable | None = None, log: Callable | None = None):
        self.stats, self.submit_stt, self.smart_turn = stats, submit_stt, smart_turn
        self.aec, self.started_t = aec, start_t
        self.concat = concat or _concat
        self.log = log
        self.ring: list = []
        self.pending: Pending | None = None
        self.prefix, self.prefix_t, self.reprompted = "", 0.0, False
        self.replaces: Pending | None = None
        self.barge: str | None = None          # None | "ducked" | "paused"
        self.run_ms = 0                        # consecutive speech
        self._reset()

    # ----- segment state
    def _reset(self) -> None:
        self.cur: list = []
        self.silence_ms = self.speech_ms = 0
        self.spec = self.res = self.pa = self.ts = self.wait_s = None
        self.start_t = self.last_speech_t = 0.0
        self.overlap = self.barged = False

    @property
    def busy(self) -> bool:
        """He's in the middle of a turn (don't fall asleep on him)."""
        return bool(self.cur)

    def clear_prefix(self) -> None:
        self.prefix, self.reprompted, self.replaces = "", False, None

    def _audio(self):
        return self.concat(self.cur)

    def _say(self, msg: str) -> None:
        if self.log:
            self.log(msg)

    # ----- main entry
    def feed(self, frame, p: float, now: float, playing: bool = False, play_started: float | None = None) -> list:
        ev: list = []
        if playing and not self.aec:                 # half-duplex: ignore everything while she talks
            self._reset()
            self.ring, self.run_ms = [], 0
            return ev
        if not playing and self.barge:               # she finished while ducked/paused: restore the gain
            self.barge = None
            ev.append(("resume",))
        guard = playing and (now - self.started_t < AEC_WARMUP_S or
                             (play_started is not None and now - play_started < PLAYBACK_GUARD_S))
        speech = (not guard) and p >= (VAD_BAR_SPEAKING if playing else VAD_BAR)
        self.run_ms = self.run_ms + FRAME_MS if speech else 0
        if self.cur:
            self.cur.append(frame)
            if speech:
                if self.silence_ms >= LEARN_PAUSE_MIN_S * 1000:
                    self.stats.observe_pause(self.silence_ms / 1000)     # he paused and went on: we waited right
                self.silence_ms = 0
                self.spec = self.res = self.pa = self.ts = self.wait_s = None   # the early transcript is stale
                self.speech_ms += FRAME_MS
                self.last_speech_t = now
            else:
                self.silence_ms += FRAME_MS
        elif speech:
            if self.prefix and now - self.prefix_t > PREFIX_TTL_S:
                self.clear_prefix()
            self.cur = self.ring[-PREROLL_FRAMES:] + [frame]
            self.speech_ms, self.silence_ms = FRAME_MS, 0
            self.start_t = self.last_speech_t = now
            self.overlap = playing
        self.ring = (self.ring + [frame])[-PREROLL_FRAMES:]
        if self.pending is not None and not self.cur and self.pending.expired(now):
            self.pending = None
        if self.cur:
            ev += self._continuation(now)
        if self.cur:
            ev += self._barge_in(now, playing)
        if self.cur:
            ev += self._endpoint(now)
        return ev

    # ----- he went on talking right after she was handed the turn → cancel + join
    def _continuation(self, now: float) -> list:
        pend = self.pending
        if pend is None or pend.cancelled or not pend.covers(self.start_t):
            return []
        if self.speech_ms < CONT_MIN_SPEECH_MS:
            return []
        pend.cancelled, self.pending = True, None
        self.prefix, self.prefix_t, self.reprompted, self.replaces = pend.text, now, False, pend
        self.stats.immediate_interrupt(max(0.0, self.start_t - pend.speech_end_t))
        self.barge = None
        self._say(f"continuation → cancel reply, join to {pend.text!r} (min_delay {self.stats.min_delay:.2f}s)")
        return [("cancel", pend)]

    # ----- he talks while she speaks
    def _barge_in(self, now: float, playing: bool) -> list:
        if self.barge is None:
            if (playing and self.run_ms >= DUCK_MS and
                    not (self.pending is not None and self.pending.covers(self.start_t))):
                self.barge = "ducked"
                self.overlap = True
                self._say("barge-in: duck")
                return [("duck",)]
            return []
        ev: list = []
        if self.barge == "ducked" and self.speech_ms >= FORCE_PAUSE_MS:
            self.barge = "paused"
            self._say("barge-in: pause")
            ev.append(("pause",))
        if self.silence_ms > 0 and self.res is None and self.spec is not None and self.spec.done():
            self._take_spec()
        if self.res is not None:
            v = barge_verdict(self.res.text, getattr(self.res, "confident", True))
            self._say(f"barge-in verdict {v} on {self.res.text!r}")
            self.barge = None
            if v == "stop":
                self.barged = True
                ev.append(("stop",))
            else:
                ev.append(("resume",))
                self._reset()                       # a backchannel is not a turn
        elif self.silence_ms >= BARGE_QUIET_S * 1000:
            self.barge = None
            self._say("barge-in: quiet → resume")
            ev.append(("resume",))
            self._reset()
        return ev

    def _take_spec(self) -> None:
        try:
            self.res = self.spec.result()
        except Exception:
            self.res = _Empty()

    # ----- end of turn
    def _endpoint(self, now: float) -> list:
        if len(self.cur) * FRAME_MS > MAX_UTTER_MS:
            if self.res is None and self.spec is not None and self.spec.done():
                self._take_spec()
            return self._commit(now, timed_out=False)
        if self.silence_ms == 0:
            return []
        if self.spec is None and self.silence_ms >= SPEC_STT_MS:
            self.spec = self.submit_stt(self._audio())
        if self.pa is None and self.silence_ms >= SMART_TURN_MS:
            try:
                self.pa = float(self.smart_turn(self._audio()))
            except Exception:
                self.pa = -1.0                       # unknown → treated as "not sure" (min_delay)
        if self.res is None and self.spec is not None and self.spec.done():
            self._take_spec()
        if self.res is not None and self.ts is None:
            heard = (self.res.text or "").strip()
            self.ts = text_state(join_text(self.prefix, heard)) if heard else "noise"   # the loop drops noise
        if self.ts is not None and self.wait_s is None and self.pa is not None:
            self.wait_s = wait_for(self.ts, self.pa if self.pa >= 0 else None, self.stats.min_delay)
            self._say(f"pause {self.silence_ms} ms: text={self.ts} audio={self.pa:.2f} → wait {self.wait_s:.2f}s")
        if self.wait_s is not None and self.silence_ms >= self.wait_s * 1000:
            return self._commit(now, timed_out=self.ts in ("unfinished", "wait"))
        if self.spec is not None and self.res is None and self.silence_ms >= WAIT_PHRASE_S * 1000:
            return self._commit(now, timed_out=False)          # STT stuck: hand it over, the loop waits for it
        return []

    def _commit(self, now: float, timed_out: bool) -> list:
        c = Commit(audio=self._audio(), spec=self.spec, res=self.res, prefix=self.prefix, state=self.ts,
                   timed_out=timed_out, speech_ms=self.speech_ms, start_t=self.start_t, end_t=self.last_speech_t,
                   commit_t=now, overlap=self.overlap, barged=self.barged, reprompted=self.reprompted,
                   replaces=self.replaces)
        noise = self.ts == "noise" or (c.res is not None and c.blip)
        if noise:
            pass                                                   # keep any fragment for his real words
        elif timed_out and self.ts == "unfinished" and not self.reprompted and c.text:
            self.prefix, self.prefix_t, self.reprompted = c.text, now, True   # "Mm-hm?" — keep it for the rest
        else:
            self.prefix, self.reprompted = "", False
        if not noise:
            self.replaces = None
        self.stats.committed()
        self._reset()
        ev: list = []
        if self.barge:                                             # (only on a max-length cut)
            self.barge = None
            ev.append(("resume",))
        return ev + [("commit", c)]


class _Empty:
    text, ms, no_speech_prob, avg_logprob, confident, unclear = "", 0.0, 1.0, -9.0, False, True


def _concat(frames: list):
    import numpy as np
    return np.concatenate(frames) if frames else np.zeros(0, dtype=np.float32)
