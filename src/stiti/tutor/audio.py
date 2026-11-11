"""Tutor audio: what she says (Kokoro, local) and what she hears (mic → VAD → whisper, local).

Three modes behind one tiny interface (synth / play / playing / stop):
  SilentAudio  — no sound; durations estimated from word count (tests, CI, `--silent`)
  SpeakerAudio — Kokoro through the speakers; you type or click (`--type`)
  VoiceAudio   — the default: full duplex with WebRTC echo cancellation, so you can talk over her
                 (barge-in); every transcript lands in the tutor's event queue as {"type": "voice"}.
All free and on-device: Kokoro-82M int8, Silero VAD, mlx-whisper small q4 (already used by Stiti).
"""
from __future__ import annotations

import os
import queue
import threading
import time
from types import SimpleNamespace

import numpy as np


class SilentAudio:
    """No sound. `scale` < 1 makes lessons run faster than real time (tests)."""

    def __init__(self, scale: float = 1.0):
        self.scale = scale
        self._until = 0.0

    def synth(self, text: str, speed: float = 1.0):
        ms = (len(text.split()) / 2.6 / speed) * 1000 + 300
        return None, int(ms)

    def play(self, audio, ms: int) -> None:
        self._until = time.time() + ms / 1000 * self.scale

    @property
    def playing(self) -> bool:
        return time.time() < self._until

    def stop(self) -> None:
        self._until = 0

    def close(self) -> None:
        pass


class _Kokoro:
    def __init__(self, tts=None):
        if tts is None:
            from ..voice.tts import TTS
            tts = TTS()
        self.tts = tts
        self._lock = threading.Lock()

    def synth(self, text: str, speed: float = 1.0):
        from ..voice.tts import speakable
        with self._lock:
            audio, sr = self.tts.k.create(speakable(text) or ".", voice=self.tts.voice, speed=speed,
                                          lang=self.tts.lang)
        return (audio, sr), int(len(audio) / sr * 1000)


class SpeakerAudio(_Kokoro):
    def play(self, audio, ms: int) -> None:
        import sounddevice as sd
        if audio is not None:
            sd.play(*audio)

    @property
    def playing(self) -> bool:
        import sounddevice as sd
        try:
            return bool(sd.get_stream().active)
        except Exception:
            return False

    def stop(self) -> None:
        import sounddevice as sd
        sd.stop()

    def close(self) -> None:
        self.stop()


def keep_heard(text: str, unclear: bool) -> bool:
    """A clear line always counts. An unclear one only if it's a lesson command (ruko / phir se / continue…):
    mis-heard noise must not become a 'question' the tutor stops to answer."""
    if not unclear:
        return True
    from .commands import classify
    return classify(text) not in ("question", "answer", "other")


class VoiceAudio(_Kokoro):
    """Reuses Stiti's VoiceLoop machinery (Duplex + AEC + VAD segmenter + Smart Turn + whisper)."""

    def __init__(self, events: queue.Queue, aec: bool = True, debug: bool = False):
        from ..voice import stt
        from ..voice.loop import VoiceLoop
        self.events, self.debug = events, debug
        self.vl = VoiceLoop(SimpleNamespace(last_interrupted=False), aec=aec, debug=debug)
        super().__init__(self.vl.tts)
        # load whisper now, not mid-lesson — on the loop's ONE STT thread: MLX streams belong to a thread, and a second
        # thread loading it at the same time failed with "There is no Stream(cpu, 0) in current thread" (2026-11-11)
        self.vl._stt.submit(stt.transcribe, np.zeros(16000, dtype=np.float32)).result()
        self.barged = threading.Event()
        self._stop = threading.Event()
        self._ctx = None

    def start(self) -> "VoiceAudio":
        from ..voice.duplex import Duplex
        self._ctx = Duplex(self.vl._on_mic, aec=self.vl.aec)
        self.vl.duplex = self._ctx.__enter__()
        threading.Thread(target=self.vl._segmenter, args=(self._stop,), daemon=True).start()
        threading.Thread(target=self._ears, daemon=True).start()
        return self

    def _ears(self):
        from ..voice import stt
        from ..voice.vad import SR
        while not self._stop.is_set():
            try:
                seg = self.vl.segq.get(timeout=0.5)
            except queue.Empty:
                continue
            if len(seg) < SR * 0.3:
                continue
            try:
                r = self.vl._stt.submit(stt.transcribe_ex, seg).result()
            except Exception as e:                       # never let one bad segment make the lesson deaf
                print(f"   [ears] {type(e).__name__}: {e}")
                continue
            text, ms = r.text, r.ms
            if text and not keep_heard(text, r.unclear):
                print(f"   (unclear, ignored: {text!r})")      # 2026-11-11: noise like "Nim nil to nara" got answered
                continue
            if text:
                if self.debug:
                    print(f"   (heard {text!r}, {ms:.0f} ms)")
                self.events.put({"type": "voice", "text": text})

    def play(self, audio, ms: int) -> None:
        self.vl._interrupted.clear()
        if audio is not None:
            self.vl.duplex.play(*audio)

    @property
    def playing(self) -> bool:
        return self.vl.duplex.playing

    @property
    def interrupted(self) -> bool:
        """True when the learner talked over her (barge-in stopped playback)."""
        return self.vl._interrupted.is_set()

    def stop(self) -> None:
        self.vl.duplex.stop_playback()

    def close(self) -> None:
        self._stop.set()
        if self._ctx is not None:
            self._ctx.__exit__(None, None, None)


def make(mode: str, events: queue.Queue, debug: bool = False, scale: float = 1.0):
    if mode == "silent":
        return SilentAudio(scale)
    if mode == "type":
        return SpeakerAudio()
    return VoiceAudio(events, aec=os.getenv("STITI_TUTOR_AEC", "1") != "0", debug=debug).start()
