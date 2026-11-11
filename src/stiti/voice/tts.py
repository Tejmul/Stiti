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


def _profile(key: str) -> str | None:
    try:
        from .. import profile
        return profile.get(key)
    except Exception:
        return None


def hindi_voice_setting() -> str | None:
    """The voice for Hinglish / Hindi lines: STITI_VOICE_HI, then owner_profile `voice_hi`; None = same as English."""
    v = os.getenv("STITI_VOICE_HI") or _profile("voice_hi")
    return v.strip() if v and v.strip() else None


def speed_setting() -> float:
    """Owner's base speed (owner_profile `voice_speed`, STITI_VOICE_SPEED wins), 0.8–1.3; moods scale it."""
    try:
        v = float(os.getenv("STITI_VOICE_SPEED") or _profile("voice_speed") or 1.0)
    except ValueError:
        v = 1.0
    return min(1.3, max(0.8, v))


def say_as_setting() -> dict[str, str]:
    """{word: respelling} from owner_profile `say_as` (JSON), e.g. a name an American voice says wrong.
    Kept in his local brain, never in code."""
    import json
    try:
        d = json.loads(_profile("say_as") or "{}")
        return {str(k): str(v) for k, v in d.items() if str(k).strip() and str(v).strip()} if isinstance(d, dict) else {}
    except Exception:
        return {}


def apply_say_as(text: str, table: dict[str, str]) -> str:
    """Whole-word, case-insensitive respelling ("Tej" → "Tayj"); longer words first so "Tejmul" wins over "Tej"."""
    for w in sorted(table, key=len, reverse=True):
        text = re.sub(rf"(?<!\w){re.escape(w)}(?!\w)", table[w], text, flags=re.I)
    return text


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


_MODELS: dict[str, object] = {}     # one Kokoro per model file, shared by both voices


def _model(engine: str):
    from kokoro_onnx import Kokoro
    if engine not in _MODELS:
        _MODELS[engine] = (Kokoro(str(models.GOONJ_DIR / models.GOONJ_MODEL), str(models.GOONJ_DIR / models.GOONJ_VOICES))
                           if engine == "goonj" else Kokoro(str(path("kokoro-v1.0.int8.onnx")), str(path("voices-v1.0.bin"))))
    return _MODELS[engine]


def _load(setting: str | None) -> tuple[str, str, object]:
    engine, voice = resolve(setting)
    k = _model(engine)
    if voice not in k.voices:
        if engine == "goonj":
            print(f"[tts] no goonj persona {voice!r}; using {DEFAULT_VOICE}")
            voice = DEFAULT_VOICE.split(":", 1)[1]
        else:
            voice = FALLBACK_VOICE
    return engine, voice, k


class TTS:
    """Two voices (owner's choice, 2026-11-11): `voice` for English lines, `voice_hi` for Hinglish/Hindi lines
    (a line is Hinglish when hinglish.phonemize() finds 2+ Hindi words). No `voice_hi` = one voice for everything."""

    def __init__(self, voice: str | None = None, voice_hi: str | None = None):
        self.engine, self.voice, self.k = _load(voice)
        hi = voice_hi if voice_hi is not None else (hindi_voice_setting() if voice is None else None)
        self.hi = _load(hi) if hi else None             # (engine, voice, model) for Hinglish lines
        self.base_speed = speed_setting()
        self.say_as = say_as_setting()
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
        n = f"goonj:{self.voice}" if self.engine == "goonj" else self.voice
        if self.hi:
            n += " + " + (f"goonj:{self.hi[1]}" if self.hi[0] == "goonj" else self.hi[1]) + " (Hinglish)"
        return n

    def pick(self, text: str) -> tuple[str, object, str | None]:
        """(voice, model, phonemes-or-None) for this line: Hinglish → the Hinglish voice + mixed hi/en phonemes."""
        ph = hinglish.phonemize(text) if self.hindi_phonemes else None
        if ph and self.hi:
            return self.hi[1], self.hi[2], ph
        return self.voice, self.k, ph

    def synth(self, text: str, mood: str = "calm") -> tuple[np.ndarray, int]:
        """English line → the English voice; Hinglish line → the Hinglish voice (or the same one), Hindi words with
        Hindi phonemes (hinglish.py). His say-as respellings apply to stock Kokoro voices (the American ones)."""
        speed = SPEED_FOR_MOOD.get(mood, 1.0) * self.base_speed
        voice, k, ph = self.pick(text)
        if ph:
            return k.create(ph, voice=voice, speed=speed, is_phonemes=True)
        if self.say_as and self.engine == "kokoro":
            text = apply_say_as(text, self.say_as)
        return k.create(text, voice=voice, speed=speed, lang=self.lang)

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
