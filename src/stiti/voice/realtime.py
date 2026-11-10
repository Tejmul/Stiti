"""Real-time "feels human" layer for the voice loop (D29). Kept out of loop.py so the loop only has 5 call sites.

1. Preemptive reply (LiveKit preemptive generation, Pipecat SpeculationGate, ElevenLabs speculative_turn): the
   moment the early transcript reads "finished" (endpoint.TurnTaker emits "speculate", usually 0.3–0.6 s before the
   commit lands) the engine turn starts — LLM streaming into a BUFFER, nothing played. If the turn is committed with
   the same words, the buffer is handed to her voice at once and the stream continues live (the turn is stored as
   usual). If he goes on talking ("unspeculate") or the commit goes elsewhere (bye, backchannel, wake…), it is
   dropped: the stream aborts, every DB write is rolled back (engine.turn(speculative=True) holds them in one
   transaction) and the engine state is restored. Only plain LLM chat turns are speculated (engine.spec_block):
   a fast path never runs early, so nothing ever has to be undone. ≤ 6 dropped speculations a minute (Groq RPM).
2. Pre-warm (Wispr's GET /warmup on the first audio chunk): his speech starting while she's awake → router.warm()
   (de-duplicated: one per 20 s), so the LLM's TLS connection is hot when the turn lands.
3. Turn-completion markers (Pipecat ● ◐ ○, brain/turnmark.py): the engine strips them; on ◐/○ she says nothing,
   his words are kept as the TurnTaker prefix (joined to what he says next) and "Mm-hm?" comes after 5 s / 10 s.
4. Media pause (Wispr shouldPauseAudio, voice/media.py): music that is playing pauses while she's awake.
"""
from __future__ import annotations

import os
import threading
import time
from typing import Callable

from .. import router
from ..brain import psych, turnmark
from .media import MediaPauser

PREEMPT = os.getenv("STITI_PREEMPTIVE", "on").lower() not in ("off", "0", "no")
MAX_DROPS_PER_MIN = 6           # a dropped speculation still costs one free-tier request (Groq: 30 RPM)
REPROMPT = "Mm-hm?"


class _Abort(BaseException):
    """Raised inside a dropped speculation's LLM stream (BaseException: no `except Exception` may swallow it)."""


class Speculation:
    def __init__(self, text: str, start_t: float, audio, t0: float):
        self.text, self.start_t, self.audio = text, start_t, audio
        self.voice = None
        self.lock = threading.Lock()
        self.buf: list[str] = []
        self.sink: Callable | None = None          # her voice's on_delta, once adopted
        self.policy = None                         # the strategy StreamLint must use (set on the engine thread)
        self.cancelled = self.adopted = self.ok = False
        self.reply: str | None = None
        self.exc: BaseException | None = None
        self.sink_exc: BaseException | None = None
        self.why: str | None = None
        self.done = threading.Event()              # the engine call returned
        self.final = threading.Event()             # its transaction was committed / rolled back
        self._finalizing = False
        self.t0, self.t_first, self.t_adopt = t0, None, None
        self.gain_ms: float | None = None


class Speculator:
    """One speculative engine turn at a time. Thread-safe: start/drop from the segmenter, take/run_adopted from the
    reply thread, settle from anyone who's about to use the engine."""

    def __init__(self, engine: Callable, *, voice_fn: Callable | None = None, clock: Callable = time.monotonic,
                 log: Callable | None = None, max_drops_per_min: int = MAX_DROPS_PER_MIN):
        self.engine = engine                       # () -> the Engine (the loop may swap it)
        self.voice_fn = voice_fn or (lambda audio, text: None)
        self.clock, self.log, self.max_drops = clock, log or (lambda m: None), max_drops_per_min
        self.cur: Speculation | None = None
        self._lock = threading.Lock()
        self._drops: list[float] = []
        self.stats = {"started": 0, "adopted": 0, "dropped": 0, "not_speculable": 0, "fallback": 0, "gain_ms": []}

    # ---- segmenter side
    def start(self, text: str, start_t: float, audio=None) -> Speculation | None:
        with self._lock:
            old = self.cur
            if old is not None and not old.final.is_set():
                if not old.adopted and old.start_t != start_t:
                    self._drop(old, "replaced")
                return None                        # the engine is still busy with it: never block the segmenter
            now = self.clock()
            self._drops = [t for t in self._drops if now - t < 60]
            if len(self._drops) >= self.max_drops:
                self.log("speculation paused: too many dropped this minute")
                return None
            s = self.cur = Speculation(text, start_t, audio, now)
            self.stats["started"] += 1
        threading.Thread(target=self._run, args=(s,), daemon=True, name="stiti-speculate").start()
        self.log(f"speculating on {text!r}")
        return s

    def drop(self, start_t: float | None = None, why: str = "") -> None:
        with self._lock:
            s = self.cur
            if s is None or (start_t is not None and s.start_t != start_t):
                return
            self._drop(s, why)

    def _drop(self, s: Speculation, why: str) -> None:
        with s.lock:
            if s.adopted or s.cancelled:
                return
            s.cancelled = True
        self._drops.append(self.clock())
        self.stats["dropped"] += 1
        self.log(f"speculation dropped ({why}): {s.text!r}")
        if s.done.is_set():                        # finished already: roll it back now (off this thread)
            threading.Thread(target=self._finalize, args=(s,), daemon=True).start()

    # ---- the speculative engine call
    def _run(self, s: Speculation) -> None:
        def buffer(piece: str) -> None:
            if s.cancelled:
                raise _Abort()
            with s.lock:
                if s.t_first is None:
                    s.t_first = self.clock()
                if s.sink is None:
                    if s.policy is None:
                        s.policy = psych.current_policy()
                    s.buf.append(piece)
                    return
                sink = s.sink
            try:
                sink(piece)                         # adopted: straight to her voice
            except BaseException as e:
                s.sink_exc = e
                raise

        eng = self.engine()
        try:
            if s.audio is not None:
                s.voice = self.voice_fn(s.audio, s.text)
            if s.cancelled:
                raise _Abort()
            s.reply = eng.turn(s.text, voice_emotion=s.voice, on_delta=buffer, speculative=True)
            s.ok = True
        except _Abort:
            s.why = "dropped"
        except BaseException as e:
            if type(e).__name__ == "NotSpeculable":
                s.why = f"not speculable: {e}"
                self.stats["not_speculable"] += 1
            else:
                s.exc = e
                s.why = f"{type(e).__name__}: {e}"
        finally:
            s.done.set()
            if not s.ok:
                s.final.set()                       # engine already rolled back (or never wrote)
            elif s.cancelled:
                self._finalize(s)

    def _finalize(self, s: Speculation, commit: bool | None = None) -> None:
        """Commit (adopted, not cancelled) or roll back (everything else) — exactly once."""
        with s.lock:
            if s._finalizing or not s.ok:
                return
            s._finalizing = True
        eng = self.engine()
        try:
            if commit is None:
                commit = s.adopted and not s.cancelled
            (eng.speculation_commit if commit else eng.speculation_discard)()
        except Exception as e:
            self.log(f"speculation finalize: {type(e).__name__}: {e}")
        finally:
            s.final.set()

    def settle(self, timeout: float = 8.0) -> None:
        """Before the engine is used for a normal turn: any speculation that wasn't adopted is dropped and its
        rollback has finished (the engine is single-turn)."""
        s = self.cur
        if s is None or s.final.is_set():
            return
        if not s.adopted:
            with self._lock:
                self._drop(s, "not used")
        s.done.wait(timeout)
        if s.ok and s.cancelled:
            self._finalize(s)
        s.final.wait(timeout)

    # ---- reply side
    def take(self, text: str, start_t: float | None) -> Speculation | None:
        with self._lock:
            s = self.cur
            if s is None or s.cancelled or s.adopted or s.text != text or s.start_t != start_t:
                return None
            with s.lock:
                s.adopted = True
            s.t_adopt = self.clock()
            return s

    def run_adopted(self, s: Speculation, on_delta: Callable | None, fallback: Callable[[], str]) -> str:
        """Play what's buffered, keep streaming live, then commit the turn. Same result as a normal engine.turn()."""
        replay_exc = None
        with s.lock:
            pending, s.buf = s.buf, []
            if pending:
                psych.set_policy(s.policy)          # StreamLint binds on THIS thread for the buffered pieces
            try:
                for p in pending:
                    if on_delta is not None:
                        on_delta(p)
            except BaseException as e:              # he went on talking after the commit (continuation grace)
                s.cancelled, replay_exc = True, e
            else:
                s.sink = on_delta
        s.done.wait()
        if replay_exc is not None:
            self._finalize(s, commit=False)
            raise replay_exc
        if s.sink_exc is not None:                  # the same, raised on the engine thread (engine rolled back)
            raise s.sink_exc
        relayed = bool(pending) or s.t_first is not None
        if not s.ok:
            if s.exc is not None and relayed:
                raise s.exc
            self.stats["fallback"] += 1
            self.log(f"speculation unusable ({s.why}) → normal turn")
            return fallback()
        eng = self.engine()
        mark = getattr(eng, "last_marker", None)
        if turnmark.is_incomplete(mark) and getattr(eng, "skip_turn", False):
            self._finalize(s, commit=False)         # a fragment: nothing is stored, the joined turn stores it all
            eng.skip_turn, eng.last_marker, eng.incomplete_at = True, mark, time.time()
        else:
            self._finalize(s, commit=True)
        first = s.t_first if s.t_first is not None else self.clock()
        s.gain_ms = max(0.0, min(first - s.t0, s.t_adopt - s.t0)) * 1000
        self.stats["adopted"] += 1
        self.stats["gain_ms"].append(round(s.gain_ms))
        dbg = getattr(eng, "last_debug", None)
        if isinstance(dbg, dict):
            dbg["preemptive_gain_ms"] = round(s.gain_ms)
        self.log(f"speculation used: {s.gain_ms:.0f} ms earlier")
        return s.reply or ""


def peek_voice(audio, text: str):
    """The voice-emotion hint _handle computes (prosody vs his baseline), WITHOUT updating the baseline — the
    commit-time call does that once. Runs on the speculation thread (it costs tens of ms)."""
    label, conf = None, 0.0
    try:
        import numpy as np
        from . import prosody
        from .vad import SR
        feat = prosody.features(np.asarray(audio, dtype=np.float32), SR, len(text.split()))
        b = prosody._load()
        n = int(b.get("n", 0))
        z = {k: ((v - b["mean"].get(k, v)) / (b["var"].get(k, 1.0) ** 0.5 + 1e-6) if n >= 5 else 0.0)
             for k, v in feat.items() if not (k == "pitch" and v == 0)}
        arousal = float(np.mean([z.get("db", 0), z.get("pitch", 0), z.get("rate", 0), z.get("pitch_sd", 0)]))
        n += 1
        if n >= 5:
            cap = 0.6 if n >= 20 else 0.45
            label, conf = (("stressed", min(cap, 0.3 + 0.15 * arousal)) if arousal > 1.0 else
                           ("tired", min(cap, 0.3 + 0.15 * -arousal)) if arousal < -1.0 else ("calm", 0.3))
    except Exception:
        pass
    try:
        from . import loop as L
        deep = L._deep_last
        if deep and deep[1] > conf:
            label, conf = deep
    except Exception:
        pass
    return (label, conf) if label else None


class Realtime:
    """Glue between VoiceLoop and the pieces above. The loop calls: on_event(ev) (segmenter thread), tick(c) (main
    loop, every ≤ 0.5 s), turn(...) (reply thread, instead of engine.turn)."""

    def __init__(self, loop, *, media: MediaPauser | None = None, start_threads: bool = True,
                 log: Callable | None = None):
        self.loop = loop
        self.log = log or ((lambda m: print(f"   [rt] {m}")) if getattr(loop, "debug", False) else (lambda m: None))
        self.spec = Speculator(lambda: self.loop.engine, voice_fn=peek_voice, log=self.log)
        self.media = media if media is not None else MediaPauser(log=lambda m: print(f"   (music {m})"))
        self.current_start: float | None = None    # start_t of the commit the main loop is handling
        self._seen: float | None = None            # … and of the one it handled in the previous round
        self.reprompt: tuple[float, str] | None = None
        self._stop = threading.Event()
        loop.tt.rt_events = True
        if start_threads:
            threading.Thread(target=self._media_loop, daemon=True, name="stiti-media").start()

    # ---- segmenter thread
    def on_event(self, ev: tuple) -> bool:
        kind = ev[0]
        if kind == "speech_start":
            self.reprompt = None                    # he's talking again: no "Mm-hm?"
            if self.loop.awake and not self.loop.silenced:
                router.warm()
            return True
        if kind == "speculate":
            _, text, audio, start_t = ev
            if self.may_speculate():
                self.spec.start(text, start_t, audio)
            return True
        if kind == "unspeculate":
            self.spec.drop(ev[1], "he went on talking")
            return True
        return False

    def may_speculate(self) -> bool:
        lp = self.loop
        if not PREEMPT or not lp.awake or lp.silenced or getattr(lp, "ring_control", None) is not None:
            return False
        w = getattr(lp, "_work", None)
        if w is not None and w.is_alive():
            return False                            # her previous reply is still being worked on
        pend = lp.tt.pending
        if pend is not None and not pend.expired(time.monotonic()):
            return False                            # her last reply can still be joined to
        d = getattr(lp, "duplex", None)
        if d is not None and d.playing:
            return False
        try:
            from .loop import _tutor_active
            return not _tutor_active()
        except Exception:
            return True

    # ---- main loop thread
    def tick(self, c=None) -> None:
        s = self.spec.cur
        if s is not None and not s.adopted and not s.cancelled and (
                (self._seen is not None and s.start_t == self._seen)          # its commit went elsewhere
                or (c is not None and s.start_t < c.start_t)):                # an older segment's
            self.spec.drop(s.start_t, "not used")
        if c is not None:
            self.current_start = c.start_t
        self._seen = c.start_t if c is not None else None
        r = self.reprompt
        if r is not None and time.monotonic() >= r[0]:
            self.reprompt = None
            lp, tt = self.loop, self.loop.tt
            d = getattr(lp, "duplex", None)
            if tt.prefix == r[1] and not tt.busy and lp.awake and not (d is not None and d.playing):
                tt.reprompted = True
                lp.say(REPROMPT)

    # ---- reply thread
    def turn(self, text: str, voice_emotion=None, on_delta=None, on_ack=None) -> str:
        eng = self.loop.engine
        s = self.spec.take(text, self.current_start)
        if s is not None:
            reply = self.spec.run_adopted(s, on_delta, lambda: eng.turn(text, voice_emotion=voice_emotion,
                                                                        on_delta=on_delta, on_ack=on_ack))
        else:
            self.spec.settle()
            reply = eng.turn(text, voice_emotion=voice_emotion, on_delta=on_delta, on_ack=on_ack)
        self.after_turn(text)
        return reply

    def after_turn(self, text: str) -> None:
        """◐ / ○: keep his words as the fragment the next segment is joined to; "Mm-hm?" after 5 s / 10 s."""
        eng = self.loop.engine
        mark = getattr(eng, "last_marker", None)
        if not (turnmark.is_incomplete(mark) and getattr(eng, "skip_turn", False)):
            return
        tt = self.loop.tt
        tt.prefix, tt.prefix_t, tt.reprompted = text, time.monotonic(), False
        self.reprompt = (time.monotonic() + turnmark.REPROMPT_AFTER_S[mark], text)
        print(f"   ({mark} you weren't done — listening for the rest)")

    # ---- media thread
    def _media_loop(self) -> None:
        while not self._stop.wait(0.25):
            lp = self.loop
            try:
                d = getattr(lp, "duplex", None)
                self.media.update(bool(lp.awake and not lp.silenced), time.monotonic(),
                                  idle_s=time.time() - lp.last_activity,
                                  busy=lp.tt.busy or (d is not None and d.playing))
            except Exception as e:
                self.log(f"media: {type(e).__name__}: {e}")

    def close(self) -> None:
        self._stop.set()
        if self.media.paused:
            self.media.resume()
