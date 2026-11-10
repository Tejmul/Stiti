"""Speech-to-text with mlx-whisper (Apple GPU). Whisper-family only: SenseVoice/Parakeet can't hear Hindi.

Hinglish trick: language="en" + a Romanized-Hinglish initial prompt biases Whisper to write
Hinglish in Latin script (what the fast path and memory expect). A/B vs Hinglish-tuned models later.

Contextual biasing (ElevenLabs `asr.keywords`, the brain fixing the ears): the owner's name and the top people /
project names from the knowledge graph go into the prompt, cached and refreshed in the background.
Confidence: `transcribe_ex()` also returns Whisper's own no_speech_prob / avg_logprob (duration-weighted over its
segments) so the loop can refuse a phantom "Bye." and ask "Sorry, say that again?" instead of answering garbage.
"""
from __future__ import annotations

import os
import re
import threading
import time
from dataclasses import dataclass

import numpy as np

from .models import WHISPER_MAIN

# one model, one pass: the prompt biases toward both the wake phrases and Romanized Hinglish
# (mlx-whisper caches a single model, so a separate wake model would reload on every switch)
HINGLISH_PROMPT = ("Hey Stiti. Wake up baby girl. Haan Stiti, kal subah 6 baje alarm laga do. "
                   "Meri todos kya hain? Aaj bahut kaam tha yaar. Remind me to call mummy.")
WAKE_PROMPT = HINGLISH_PROMPT

# "confident" = good enough to act on a one-word stop/goodbye; "unclear" = ask him to repeat
CONF_NO_SPEECH, CONF_LOGPROB = 0.4, -0.8
UNCLEAR_NO_SPEECH = float(os.getenv("STITI_UNCLEAR_NOSPEECH", "0.5"))
UNCLEAR_LOGPROB = float(os.getenv("STITI_UNCLEAR_LOGPROB", "-1.0"))
BIAS_REFRESH_S = 300
BIAS_MAX_NAMES = 10


@dataclass
class STTResult:
    text: str
    ms: float = 0.0
    no_speech_prob: float = 0.0
    avg_logprob: float = 0.0

    @property
    def confident(self) -> bool:
        return bool(self.text) and self.no_speech_prob < CONF_NO_SPEECH and self.avg_logprob > CONF_LOGPROB

    @property
    def unclear(self) -> bool:
        return bool(self.text) and (self.no_speech_prob > UNCLEAR_NO_SPEECH or self.avg_logprob < UNCLEAR_LOGPROB)


_cache_capped = False


def _cap_mlx_cache() -> None:
    """MLX keeps GPU buffers cached: 1.2 GB → 0.33 GB with a 64 MB cap (STT 283 → ~320 ms). Worth it on 8 GB."""
    global _cache_capped
    if not _cache_capped:
        import mlx.core as mx
        mx.set_cache_limit(int(os.getenv("STITI_MLX_CACHE_MB", "64")) * 1024 * 1024)
        _cache_capped = True


def score(segs: list[dict]) -> tuple[float, float]:
    """Duration-weighted (no_speech_prob, avg_logprob) over Whisper's segments."""
    if not segs:
        return 1.0, -9.0
    w = [max(0.05, float(s.get("end", 0)) - float(s.get("start", 0))) for s in segs]
    tot = sum(w)
    nsp = sum(float(s.get("no_speech_prob", 0.0)) * x for s, x in zip(segs, w)) / tot
    lp = sum(float(s.get("avg_logprob", 0.0)) * x for s, x in zip(segs, w)) / tot
    return nsp, lp


def _transcribe(audio: np.ndarray, repo: str, prompt: str) -> STTResult:
    import mlx_whisper
    _cap_mlx_cache()
    t = time.perf_counter()
    r = mlx_whisper.transcribe(np.asarray(audio, dtype=np.float32), path_or_hf_repo=repo,
                               language=os.getenv("STITI_STT_LANG", "en"), initial_prompt=prompt,
                               condition_on_previous_text=False, temperature=0.0,
                               no_speech_threshold=0.6, verbose=None)
    text = (r.get("text") or "").strip()
    segs = r.get("segments") or []
    # whisper hallucinates on non-speech: trust its own no-speech + confidence scores, not string matching
    if segs and all(sg.get("no_speech_prob", 0) > 0.6 or sg.get("avg_logprob", 0) < -1.2 for sg in segs):
        text = ""
    low = text.strip(" .").lower()
    if low and low in (prompt.strip(" .").lower(), HINGLISH_PROMPT.strip(" .").lower()):   # verbatim prompt echo
        text = ""
    nsp, lp = score(segs)
    return STTResult(text, (time.perf_counter() - t) * 1000, nsp, lp)


# ---------------------------------------------------------------- contextual biasing
_bias = ""
_bias_at = 0.0
_bias_lock = threading.Lock()


def _bias_names() -> list[str]:
    """Owner name + the most-connected people/projects/places in the graph (local DB, a few ms)."""
    from .. import profile
    from ..db import q
    names: list[str] = []
    for k in ("call_me", "name"):
        v = profile.get(k)
        if v and v.lower() not in {x.lower() for x in names}:
            names.append(v)
    rows = q("""SELECT e.name FROM entities e
                LEFT JOIN facts f ON (f.subj_id = e.id OR f.obj_id = e.id) AND upper_inf(f.recorded)
                WHERE e.merged_into IS NULL AND e.kind IN ('person','project','place','org')
                GROUP BY e.id, e.name ORDER BY count(f.id) DESC, max(e.created_at) DESC LIMIT 25""")
    for r in rows:
        n = " ".join(str(r["name"]).split())
        if 2 <= len(n) <= 30 and re.fullmatch(r"[\w .'-]+", n) and n.lower() not in {x.lower() for x in names}:
            names.append(n)
        if len(names) >= BIAS_MAX_NAMES:
            break
    return names


def _refresh_bias() -> None:
    global _bias
    try:
        names = _bias_names()
        _bias = (", ".join(names) + ". ") if names else ""
    except Exception:
        pass


def prompt() -> str:
    """The Whisper initial prompt: graph names (cached, refreshed in the background every 5 min) + Hinglish."""
    global _bias_at
    if os.getenv("STITI_STT_BIAS", "on") != "off" and time.time() - _bias_at > BIAS_REFRESH_S:
        with _bias_lock:
            if time.time() - _bias_at > BIAS_REFRESH_S:
                _bias_at = time.time()          # one refresh at a time; never blocks the transcription
                threading.Thread(target=_refresh_bias, daemon=True).start()
    return _bias + HINGLISH_PROMPT


def transcribe_ex(audio: np.ndarray) -> STTResult:
    return _transcribe(audio, os.getenv("STITI_WHISPER", WHISPER_MAIN), prompt())


def transcribe(audio: np.ndarray) -> tuple[str, float]:
    r = transcribe_ex(audio)
    return r.text, r.ms


def transcribe_wake(audio: np.ndarray) -> tuple[str, float]:
    return transcribe(audio)
