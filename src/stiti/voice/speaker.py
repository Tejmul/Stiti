"""Gapless speech pipeline: text pieces in → Kokoro synth (own thread, one piece ahead) → duplex queue.

Pieces can arrive while the LLM is still writing (streaming). Instant acknowledgements ("ek sec, calendar
dekhti hoon") and the "hmm" filler use pre-synthesised audio, so they cost ~0 ms. Barge-in stops playback
and remembers what was left (so a mere "haan" resumes the cut sentence).
"""
from __future__ import annotations

import queue
import random
import threading
import time

import numpy as np

ACKS = {
    "calendar": "Ek sec, calendar dekhti hoon.",
    "mail": "Haan, mail check karti hoon.",
    "plan": "Okay, let me plan your day.",
    "tools": "Ek second, dekhti hoon.",
}
FILLERS = ["Hmm.", "Hmm, let me think.", "Achha…"]
_END = object()


class Speaker:
    def __init__(self, loop, mood: str = "calm", *, filler_after: float = 0.9):
        self.loop, self.mood, self.filler_after = loop, mood, filler_after
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
                self.audio.put((self.loop.ack_text[item[1]], a, sr))
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
        timeline: list[tuple[str, float]] = []        # (piece, expected end time)
        pending: list[str] = []
        end_t, done = time.time(), False
        filler_played = False
        while True:
            if intr.is_set():
                self.cancelled.set()
                d.stop_playback()
                now = time.time()
                left = [p for p, t in timeline if t > now] + pending
                while True:                             # whatever was already synthesised but not queued
                    try:
                        item = self.audio.get_nowait()
                    except queue.Empty:
                        break
                    if item is not _END:
                        left.append(item[0])
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
                    end_t = self._enqueue("", a, sr, end_t, timeline)
                continue
            if item is _END:
                done = True
                continue
            piece, a, sr = item
            if self.first_audio_ms is None:
                self.first_audio_ms = (time.perf_counter() - self._t0) * 1000
            self.spoke_something = True
            end_t = self._enqueue(piece, a, sr, end_t, timeline)

    def _enqueue(self, piece: str, a: np.ndarray, sr: int, end_t: float, timeline) -> float:
        now = time.time()
        if not self.loop.duplex.playing:
            end_t = now
        end_t = max(end_t, now) + len(a) / sr
        self.loop.duplex.play(a, sr)
        if piece:
            timeline.append((piece, end_t))
        return end_t
