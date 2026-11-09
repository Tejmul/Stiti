"""Full-duplex audio with WebRTC AEC3 echo cancellation (LiveKit's AudioProcessingModule, free).

One 48 kHz duplex stream, 10 ms blocks: everything Stiti plays is fed to the APM as the far-end
reference, the mic is cleaned against it, then downsampled to 16 kHz for VAD/STT.
=> Tejmul can interrupt her on laptop speakers, no headphones needed (research: AEC was the blocker).
"""
from __future__ import annotations

import threading
from collections import deque

import numpy as np
import sounddevice as sd
from livekit import rtc

RATE = 48000
BLOCK = 480            # 10 ms — what the WebRTC APM expects


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
        self._buf: deque[np.ndarray] = deque()
        self._cur = np.zeros(0, dtype=np.float32)
        self._lock = threading.Lock()
        self.drained = threading.Event()
        self.drained.set()
        self.stream = sd.Stream(samplerate=RATE, blocksize=BLOCK, channels=1, dtype="float32",
                                latency="low", callback=self._cb)

    # ---------- playback side ----------
    def play(self, audio: np.ndarray, sr: int) -> None:
        with self._lock:
            self._buf.append(resample(audio, sr, RATE))
            self.drained.clear()

    def stop_playback(self) -> None:
        with self._lock:
            self._buf.clear()
            self._cur = np.zeros(0, dtype=np.float32)
            self.drained.set()

    @property
    def playing(self) -> bool:
        return not self.drained.is_set()

    def _pull(self, n: int) -> np.ndarray:
        out = np.zeros(n, dtype=np.float32)
        i = 0
        with self._lock:
            while i < n:
                if len(self._cur) == 0:
                    if not self._buf:
                        break
                    self._cur = self._buf.popleft()
                k = min(n - i, len(self._cur))
                out[i:i + k], self._cur = self._cur[:k], self._cur[k:]
                i += k
            if not self._buf and len(self._cur) == 0:
                self.drained.set()
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
