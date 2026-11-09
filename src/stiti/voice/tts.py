"""Text-to-speech: Kokoro-82M INT8 ONNX (~88 MB). Sentence streaming; mood -> voice speed.

No emotion control in Kokoro, so mood comes through pace + wording (report §TTS).
"""
from __future__ import annotations

import os
import re
import threading

import numpy as np
import sounddevice as sd

from .models import path

SPEED_FOR_MOOD = {"stressed": 0.95, "angry": 0.95, "sad": 0.92, "tired": 0.92, "happy": 1.06, "calm": 1.0}
_EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿]")


def speakable(text: str) -> str:
    t = re.sub(r"\((task|lesson)? ?#?L?\d+\)", "", text)          # (task #5) (#3) (lesson L1)
    t = re.sub(r"\(lesson L\d+\)", "", t)
    t = _EMOJI.sub("", t)
    t = re.sub(r"[*_`#>]", "", t).replace("“", "").replace("”", "").replace("—", ", ")
    return re.sub(r"\s+", " ", t).strip()


def sentences(text: str) -> list[str]:
    """Sentence chunks; a long first sentence is split at its first comma so first audio comes sooner."""
    parts = [p for p in re.split(r"(?<=[.!?।])\s+", text) if p.strip()]
    if parts and len(parts[0].split()) > 8 and "," in parts[0]:
        head, tail = parts[0].split(",", 1)
        parts = [head + ",", tail.strip()] + parts[1:]
    return parts


class TTS:
    def __init__(self):
        from kokoro_onnx import Kokoro
        self.k = Kokoro(str(path("kokoro-v1.0.int8.onnx")), str(path("voices-v1.0.bin")))
        self.voice = os.getenv("STITI_VOICE", "af_heart")
        self.lang = os.getenv("STITI_VOICE_LANG", "en-us")
        self._stop = threading.Event()
        self.speaking = False

    def synth(self, text: str, mood: str = "calm") -> tuple[np.ndarray, int]:
        return self.k.create(text, voice=self.voice, speed=SPEED_FOR_MOOD.get(mood, 1.0), lang=self.lang)

    def say(self, text: str, mood: str = "calm") -> bool:
        """Speak sentence by sentence (first audio after the first sentence). Returns False if interrupted."""
        self._stop.clear()
        self.speaking = True
        try:
            for s in sentences(speakable(text)):
                if self._stop.is_set():
                    return False
                audio, sr = self.synth(s, mood)
                sd.play(audio, sr)
                while sd.get_stream().active:
                    if self._stop.wait(0.03):
                        sd.stop()
                        return False
            return True
        finally:
            self.speaking = False

    def stop(self):
        self._stop.set()


def chime_audio(up: bool = True, sr: int = 24000) -> tuple[np.ndarray, int]:
    """Short two-tone chime: rising = awake, falling = going to sleep."""
    f1, f2 = (660, 990) if up else (990, 660)
    t = np.linspace(0, 0.09, int(sr * 0.09), endpoint=False)
    tone = np.concatenate([np.sin(2 * np.pi * f1 * t), np.sin(2 * np.pi * f2 * t)]) * 0.25
    fade = np.minimum(1, np.minimum(np.arange(len(tone)), np.arange(len(tone))[::-1]) / 300)
    return (tone * fade).astype(np.float32), sr


def chime(up: bool = True) -> None:
    a, sr = chime_audio(up)
    sd.play(a, sr)
    sd.wait()
