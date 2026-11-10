"""Full-duplex audio with WebRTC AEC3 echo cancellation (LiveKit's AudioProcessingModule, free).

One 48 kHz duplex stream, 10 ms blocks: everything Stiti plays is fed to the APM as the far-end
reference, the mic is cleaned against it, then downsampled to 16 kHz for VAD/STT.
=> Tejmul can interrupt her on laptop speakers, no headphones needed (research: AEC was the blocker).

Barge-in controls (endpoint.py decides, this only does it): duck() lowers her to 30 % with a 30 ms ramp, pause()
fades out and HOLDS the queue, resume() fades back in where she paused, stop_playback() fades out over 30 ms and
drops the rest. Every play() gets an id and `done_id` says which pieces were fully played (= what he heard).
"""
from __future__ import annotations

import math
import threading
import time
from collections import deque

import numpy as np
import sounddevice as sd
from livekit import rtc

from ..overlay import level as _overlay_level

RATE = 48000
BLOCK = 480            # 10 ms — what the WebRTC APM expects
FADE_S = 0.03          # 30 ms ramps: no clicks on duck / pause / stop
DUCK_GAIN = 0.3


def resample(audio: np.ndarray, sr_in: int, sr_out: int) -> np.ndarray:
    if sr_in == sr_out:
        return audio.astype(np.float32)
    n = int(len(audio) * sr_out / sr_in)
    return np.interp(np.linspace(0, len(audio), n, endpoint=False), np.arange(len(audio)), audio).astype(np.float32)


def _to_i16(x: np.ndarray) -> bytes:
    return (np.clip(x, -1, 1) * 32767).astype(np.int16).tobytes()


class Duplex:
    def __init__(self, on_mic_16k, aec: bool = True):
        self.on_mic = on_mic_16k
        self.aec = aec
        self.apm = rtc.AudioProcessingModule(echo_cancellation=aec, noise_suppression=True,
                                             high_pass_filter=True, auto_gain_control=False)
        self._init_playback()
        self.stream = sd.Stream(samplerate=RATE, blocksize=BLOCK, channels=1, dtype="float32",
                                latency="low", callback=self._cb)

    def _init_playback(self) -> None:
        """Playback state only (tests build a Duplex without a sound device through this)."""
        self._buf: deque[tuple[int, np.ndarray]] = deque()
        self._cur = np.zeros(0, dtype=np.float32)
        self._cur_id = 0
        self._next_id = 0
        self.done_id = 0                  # every play() id <= this was played to the end
        self._lock = threading.Lock()
        self._gain, self._target, self._paused = 1.0, 1.0, False
        self.started_at: float | None = None   # time.monotonic() when the current playback began
        self.ended_at: float | None = None     # ... and when the last one ended
        self.drained = threading.Event()
        self.drained.set()
        self.mic_rms = 0.0                # his AEC-cleaned voice / her voice, per 10 ms block (desktop overlay dots)
        self.out_rms = 0.0

    # ---------- playback side ----------
    def play(self, audio: np.ndarray, sr: int) -> int:
        with self._lock:
            if self.drained.is_set():
                self.started_at = time.monotonic()
                self._gain, self._target, self._paused = 1.0, 1.0, False
            self._next_id += 1
            self._buf.append((self._next_id, resample(audio, sr, RATE)))
            self.drained.clear()
            return self._next_id

    def stop_playback(self) -> None:
        """Stop now: a 30 ms fade-out of what was playing, the rest is dropped."""
        with self._lock:
            n = int(FADE_S * RATE)
            g = 0.0 if self._paused else self._gain
            tail = self._cur[:n]
            while len(tail) < n and self._buf:
                tail = np.concatenate([tail, self._buf.popleft()[1][:n - len(tail)]])
            self._buf.clear()
            self._gain, self._target, self._paused = 1.0, 1.0, False
            if g > 0.01 and len(tail):
                self._cur = (tail * np.linspace(g, 0.0, len(tail))).astype(np.float32)
            else:
                self._cur = np.zeros(0, dtype=np.float32)
                self.drained.set()
                self.ended_at = time.monotonic()
            self._cur_id = 0                       # the fade tail isn't a "played" piece

    def duck(self, gain: float = DUCK_GAIN) -> None:
        with self._lock:
            self._target = gain

    def pause(self) -> None:
        """Fade out and hold the queue (he may only be saying "haan")."""
        with self._lock:
            self._paused = True

    def resume(self) -> None:
        """Back to full volume, from where she paused."""
        with self._lock:
            self._paused, self._target = False, 1.0

    @property
    def paused(self) -> bool:
        return self._paused

    @property
    def playing(self) -> bool:
        return not self.drained.is_set()

    def _pull(self, n: int) -> np.ndarray:
        out = np.zeros(n, dtype=np.float32)
        i = 0
        with self._lock:
            if self._paused and self._gain <= 0.0:
                return out                         # held: nothing consumed, still "playing"
            while i < n:
                if len(self._cur) == 0:
                    if self._cur_id:
                        self.done_id, self._cur_id = max(self.done_id, self._cur_id), 0
                    if not self._buf:
                        break
                    self._cur_id, self._cur = self._buf.popleft()
                k = min(n - i, len(self._cur))
                out[i:i + k], self._cur = self._cur[:k], self._cur[k:]
                i += k
            if len(self._cur) == 0 and self._cur_id:
                self.done_id, self._cur_id = max(self.done_id, self._cur_id), 0
            if not self._buf and len(self._cur) == 0 and not self.drained.is_set():
                self.drained.set()
                self.ended_at = time.monotonic()
            target = 0.0 if self._paused else self._target
            if self._gain != target:
                step = 1.0 / (FADE_S * RATE)
                g = self._gain + np.sign(target - self._gain) * step * np.arange(1, n + 1, dtype=np.float32)
                g = np.clip(g, min(self._gain, target), max(self._gain, target))
                out *= g
                self._gain = float(g[-1])
            elif target != 1.0:
                out *= target
        return out

    # ---------- the 10 ms audio callback ----------
    def _cb(self, indata, outdata, frames, t, status):
        out = self._pull(frames)
        outdata[:, 0] = out
        mic = indata[:, 0]
        if frames == BLOCK:
            self.apm.process_reverse_stream(rtc.AudioFrame(_to_i16(out), RATE, 1, BLOCK))
            mf = rtc.AudioFrame(_to_i16(mic), RATE, 1, BLOCK)
            self.apm.process_stream(mf)
            mic = np.frombuffer(mf.data, dtype=np.int16).astype(np.float32) / 32768.0
        if frames:                                 # two dot products: no arrays allocated (overlay dots)
            self.out_rms = math.sqrt(float(np.dot(out, out)) / frames)
            self.mic_rms = math.sqrt(float(np.dot(mic, mic)) / len(mic)) if len(mic) else 0.0
            _overlay_level(self.mic_rms, self.out_rms)
        self.on_mic(mic.reshape(-1, 3).mean(axis=1) if len(mic) % 3 == 0 else resample(mic, RATE, 16000))

    def __enter__(self):
        self.stream.start()
        lat = self.stream.latency
        try:
            self.apm.set_stream_delay_ms(int(sum(lat) * 1000) if isinstance(lat, (tuple, list)) else int(lat * 2000))
        except Exception:
            pass
        return self

    def __exit__(self, *a):
        self.stream.stop()
        self.stream.close()
