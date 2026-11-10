"""Gapless speech pipeline: text pieces in → Kokoro synth (own thread, one piece ahead) → duplex queue.

Pieces can arrive while the LLM is still writing (streaming). Instant acknowledgements ("Checking your
calendar.") and the "hmm" filler use pre-synthesised audio, so they cost ~0 ms. English by default and no time
promises ("one sec") — ElevenLabs' advice. The thinking filler waits 1.5 s (we usually speak by ~0.85 s), at
most one per turn. Barge-in stops playback and remembers what was left (so a mere "haan" resumes the cut
sentence) and what he actually HEARD (`heard`), so memory keeps only that.
"""
from __future__ import annotations

import queue
import random
import threading
import time

import numpy as np

ACKS = {
    "calendar": "Checking your calendar.",
    "mail": "Let me check your mail.",
    "plan": "Okay, let me plan your day.",
    "tools": "Let me look.",
    "web": "Let me look that up.",
}
FILLERS = ["Hmm.", "Hmm, let me think.", "Let me see."]
FILLER_AFTER_S = 1.5
_END = object()


class Speaker:
    def __init__(self, loop, mood: str = "calm", *, filler_after: float = FILLER_AFTER_S, on_first_audio=None):
        self.loop, self.mood, self.filler_after = loop, mood, filler_after
        self.on_first_audio = on_first_audio       # called with time.monotonic() when her first sound starts
        self.heard: list[str] = []                 # reply pieces played to the end before a barge-in
        self.interrupted = False                   # he cut her off (even between pieces)
        self.texts: queue.Queue = queue.Queue()
        self.audio: queue.Queue = queue.Queue()
        self.cancelled = threading.Event()
        self.spoke_something = False
        self.first_audio_ms: float | None = None
        self.first_text_ms: float | None = None
        self._t0 = time.perf_counter()
        threading.Thread(target=self._synth, daemon=True).start()

    # --- producers (any thread) ---
    def add(self, piece: str) -> None:
        if self.first_text_ms is None:
            self.first_text_ms = (time.perf_counter() - self._t0) * 1000
        if piece and not self.cancelled.is_set():
            self.texts.put(piece)

    def ack(self, kind: str) -> None:
        if kind in self.loop.acks and not self.cancelled.is_set():
            self.texts.put(("ack", kind))

    def close(self) -> None:
        self.texts.put(_END)

    # --- synth thread: stays one piece ahead of playback ---
    def _synth(self):
        while True:
            item = self.texts.get()
            if item is _END or self.cancelled.is_set():
                self.audio.put(_END)
                return
            if isinstance(item, tuple):
                a, sr = self.loop.acks[item[1]]
                self.audio.put((("ack", self.loop.ack_text[item[1]]), a, sr))
                continue
            try:
                a, sr = self.loop.tts.synth_on_worker(item, self.mood)
            except Exception:
                continue
            self.audio.put((item, a, sr))

    # --- playback (voice-loop thread) ---
    def run(self) -> list[str] | None:
        """Play everything until the end marker. Returns the unspoken pieces if he barged in, else None."""
        d, intr = self.loop.duplex, self.loop._interrupted
        timeline: list[tuple[str, int | None, float]] = []   # (reply piece, duplex id, expected end time)
        done = False
        filler_played = False
        end_t = time.time()
        while True:
            if intr.is_set():
                self.cancelled.set()
                self.interrupted = True
                played = getattr(d, "done_id", None)
                d.stop_playback()
                now = time.time()
                fin = [(p, (cid <= played) if (played is not None and cid is not None) else (t <= now))
                       for p, cid, t in timeline]
                self.heard = [p for p, ok in fin if ok]
                left = [p for p, ok in fin if not ok]
                while True:                             # whatever was already synthesised but not queued
                    try:
                        item = self.audio.get_nowait()
                    except queue.Empty:
                        break
                    if item is not _END and isinstance(item[0], str):
                        left.append(item[0])
                while True:                             # ... or not even synthesised yet
                    try:
                        item = self.texts.get_nowait()
                    except queue.Empty:
                        break
                    if isinstance(item, str) and item:
                        left.append(item)
                return left or None
            if done:
                if not d.playing:
                    return None
                time.sleep(0.02)
                continue
            try:
                item = self.audio.get(timeout=0.02)
            except queue.Empty:
                if (not self.spoke_something and not filler_played and self.loop.fillers
                        and time.perf_counter() - self._t0 > self.filler_after):
                    filler_played = True               # thinking out loud instead of dead air
                    a, sr = random.choice(self.loop.fillers)
                    end_t = self._enqueue(None, a, sr, end_t, timeline)
                continue
            if item is _END:
                done = True
                continue
            piece, a, sr = item
            if self.first_audio_ms is None:
                self.first_audio_ms = (time.perf_counter() - self._t0) * 1000
            self.spoke_something = True
            end_t = self._enqueue(piece if isinstance(piece, str) else None, a, sr, end_t, timeline)

    def _enqueue(self, piece: str | None, a: np.ndarray, sr: int, end_t: float, timeline) -> float:
        """piece=None: filler/ack (not part of the reply)."""
        now = time.time()
        if not self.loop.duplex.playing:
            end_t = now
        end_t = max(end_t, now) + len(a) / sr
        if self.on_first_audio is not None:
            cb, self.on_first_audio = self.on_first_audio, None
            try:
                cb(time.monotonic())
            except Exception:
                pass
        cid = self.loop.duplex.play(a, sr)
        if piece:
            timeline.append((piece, cid if isinstance(cid, int) else None, end_t))
        return end_t
