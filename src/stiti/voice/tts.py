"""Text-to-speech: Kokoro-82M-family INT8 ONNX. Sentence streaming; mood -> voice speed.

D27: Stiti's voice is **goonj-1-82M** (a Kokoro fine-tune trained on Indian-English speech; Apache-2.0), exported to
ONNX int8 (114 MB, `stiti voices install`), run by the same `kokoro_onnx` runtime: English with an Indian accent,
first clause ~270 ms (af_heart: 291 ms). Pick a persona with STITI_VOICE=goonj:<persona> or the owner_profile key
`voice` (`stiti voices use en_tara`); default goonj:en_priya. ONE voice per reply: Hindi words inside a line still go
through hinglish.py (Hindi phonemes for lexicon words) but are spoken by the same persona — never a switch to the
stock Hindi voices he called "not suitable". Without the goonj files Stiti falls back to Kokoro `af_heart`.
No emotion control in Kokoro, so mood comes through pace + wording (report §TTS).
"""
from __future__ import annotations

import os
import re
import threading

import numpy as np
import sounddevice as sd

from . import hinglish, models
from .models import path

DEFAULT_VOICE = "goonj:en_priya"     # Stiti is "she"; the owner hasn't picked a persona yet (`stiti voices`)
FALLBACK_VOICE = "af_heart"          # stock Kokoro (American) when the goonj files are missing

SPEED_FOR_MOOD = {"stressed": 0.95, "angry": 0.95, "sad": 0.92, "tired": 0.92, "happy": 1.06, "calm": 1.0}
_EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿]")


def speakable(text: str) -> str:
    t = re.sub(r"\((task|lesson)? ?#?L?\d+\)", "", text)          # (task #5) (#3) (lesson L1)
    t = re.sub(r"\(lesson L\d+\)", "", t)
    t = _EMOJI.sub("", t)
    t = re.sub(r"[*_`#>]", "", t).replace("“", "").replace("”", "").replace("—", ", ")
    return re.sub(r"\s+", " ", t).strip()


def voice_setting() -> str:
    """STITI_VOICE wins, then owner_profile `voice`, then the default."""
    v = os.getenv("STITI_VOICE")
    if not v:
        try:
            from .. import profile
            v = profile.get("voice")
        except Exception:
            v = None
    return (v or DEFAULT_VOICE).strip()


def resolve(setting: str | None = None, ready: bool | None = None) -> tuple[str, str]:
    """'goonj:en_tara' → ('goonj', 'en_tara'); 'goonj' → default persona; 'af_heart' → ('kokoro', 'af_heart').
    goonj without its files → ('kokoro', af_heart)."""
    s = (setting if setting is not None else voice_setting()) or DEFAULT_VOICE
    ready = models.goonj_ready() if ready is None else ready
    if s.lower().startswith("goonj"):
        persona = s.split(":", 1)[1].strip() if ":" in s else DEFAULT_VOICE.split(":", 1)[1]
        return ("goonj", persona or DEFAULT_VOICE.split(":", 1)[1]) if ready else ("kokoro", FALLBACK_VOICE)
    return "kokoro", s


def sentences(text: str) -> list[str]:
    """Sentence chunks; a long first sentence is split at its first comma so first audio comes sooner."""
    parts = [p for p in re.split(r"(?<=[.!?।])\s+", text) if p.strip()]
    if parts and len(parts[0].split()) > 8 and "," in parts[0]:
        head, tail = parts[0].split(",", 1)
        parts = [head + ",", tail.strip()] + parts[1:]
    return parts


class TTS:
    def __init__(self, voice: str | None = None):
        from kokoro_onnx import Kokoro
        self.engine, self.voice = resolve(voice)
        if self.engine == "goonj":
            self.k = Kokoro(str(models.GOONJ_DIR / models.GOONJ_MODEL), str(models.GOONJ_DIR / models.GOONJ_VOICES))
            if self.voice not in self.k.voices:
                print(f"[tts] no goonj persona {self.voice!r}; using {DEFAULT_VOICE}")
                self.voice = DEFAULT_VOICE.split(":", 1)[1]
        else:
            self.k = Kokoro(str(path("kokoro-v1.0.int8.onnx")), str(path("voices-v1.0.bin")))
            if self.voice not in self.k.voices:
                self.voice = FALLBACK_VOICE
        self.lang = os.getenv("STITI_VOICE_LANG", "en-us")
        # Hindi words get Hindi phonemes (D22) but the SAME voice speaks the whole line; "off" = English phonemes only
        self.hindi_phonemes = os.getenv("STITI_HI_VOICE", "on") != "off"
        self._stop = threading.Event()
        self.speaking = False
        # Kokoro pays ~700 ms of setup the first time it runs in any new thread (measured on the M2), so all
        # pipeline synthesis goes through ONE long-lived worker thread, warmed up right away.
        from concurrent.futures import ThreadPoolExecutor
        self._worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix="kokoro")
        self._worker.submit(self.synth, "Warm up.", "calm")
        self._worker.submit(self.synth, "Haan, ho gaya.", "calm")   # warms espeak 'hi' (Hindi-word phonemes)

    def synth_on_worker(self, text: str, mood: str = "calm") -> tuple[np.ndarray, int]:
        """synth() on the persistent Kokoro thread (no per-thread warm-up cost)."""
        return self._worker.submit(self.synth, text, mood).result()

    @property
    def name(self) -> str:
        return f"goonj:{self.voice}" if self.engine == "goonj" else self.voice

    def synth(self, text: str, mood: str = "calm") -> tuple[np.ndarray, int]:
        """One voice for everything: Hinglish → mixed hi/en-us phonemes (hinglish.py), plain English → en-us."""
        speed = SPEED_FOR_MOOD.get(mood, 1.0)
        ph = hinglish.phonemize(text) if self.hindi_phonemes else None
        if ph:
            return self.k.create(ph, voice=self.voice, speed=speed, is_phonemes=True)
        return self.k.create(text, voice=self.voice, speed=speed, lang=self.lang)

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


class ClauseChunker:
    """Cut a streaming LLM reply into speakable pieces.

    The first piece is short so her voice starts fast (Kokoro: ~180 ms for 1–4 words, ~370 ms for 7): it ends at
    a sentence end (any length: "Honestly?"), a comma after ≥3 words, or is cut at ~7 words; later pieces are whole
    sentences (≤28 words).
    """
    FIRST_END = re.compile(r"[.!?।](?=\s)|[,;:—](?=\s)|\n")
    SENT_END = re.compile(r"[.!?।](?=\s)|\n")

    def __init__(self):
        self.buf, self.first = "", True

    def feed(self, delta: str) -> list[str]:
        self.buf += delta
        return self._cut(final=False)

    def flush(self) -> list[str]:
        return self._cut(final=True)

    def _cut(self, final: bool) -> list[str]:
        out = []
        while True:
            first = self.first
            piece = self._next()
            if piece is None:
                break
            if not speakable(piece):          # "\n", "**", an emoji: nothing to say → keep the short-first rule
                self.first = first
                continue
            out.append(piece)
        if final and self.buf.strip():
            out.append(self.buf.strip())
            self.buf = ""
        return [p for p in (speakable(x) for x in out) if p]

    def _next(self) -> str | None:
        rx, min_w, max_w = (self.FIRST_END, 3, 7) if self.first else (self.SENT_END, 1, 28)
        for m in rx.finditer(self.buf):
            sentence_end = m.group() in ".!?।\n"
            if sentence_end or len(self.buf[:m.end()].split()) >= min_w:
                return self._take(m.end())
        words = self.buf.split()
        if len(words) > max_w:                       # no boundary yet: cut at the last space before the limit
            cut = self.buf.rstrip().rfind(" ", 0, len(" ".join(words[:max_w])) + 1)
            if cut > 0:
                return self._take(cut)
        return None

    def _take(self, end: int) -> str:
        piece, self.buf, self.first = self.buf[:end].strip(), self.buf[end:], False
        return piece
