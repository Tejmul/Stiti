"""Speech-to-text with mlx-whisper (Apple GPU). Whisper-family only: SenseVoice/Parakeet can't hear Hindi.

Hinglish trick: language="en" + a Romanized-Hinglish initial prompt biases Whisper to write
Hinglish in Latin script (what the fast path and memory expect). A/B vs Hinglish-tuned models later.
"""
from __future__ import annotations

import os
import time

import numpy as np

from .models import WHISPER_MAIN, WHISPER_WAKE

# one model, one pass: the prompt biases toward both the wake phrases and Romanized Hinglish
# (mlx-whisper caches a single model, so a separate wake model would reload on every switch)
HINGLISH_PROMPT = ("Hey Stiti. Wake up baby girl. Haan Stiti, kal subah 6 baje alarm laga do. "
                   "Meri todos kya hain? Aaj bahut kaam tha yaar. Remind me to call mummy.")
WAKE_PROMPT = HINGLISH_PROMPT


_cache_capped = False


def _cap_mlx_cache() -> None:
    """MLX keeps GPU buffers cached: 1.2 GB → 0.33 GB with a 64 MB cap (STT 283 → ~320 ms). Worth it on 8 GB."""
    global _cache_capped
    if not _cache_capped:
        import mlx.core as mx
        mx.set_cache_limit(int(os.getenv("STITI_MLX_CACHE_MB", "64")) * 1024 * 1024)
        _cache_capped = True


def _transcribe(audio: np.ndarray, repo: str, prompt: str) -> tuple[str, float]:
    import mlx_whisper
    _cap_mlx_cache()
    t = time.perf_counter()
    r = mlx_whisper.transcribe(audio.astype(np.float32), path_or_hf_repo=repo,
                               language=os.getenv("STITI_STT_LANG", "en"), initial_prompt=prompt,
                               condition_on_previous_text=False, temperature=0.0,
                               no_speech_threshold=0.6, verbose=None)
    text = (r.get("text") or "").strip()
    segs = r.get("segments") or []
    # whisper hallucinates on non-speech: trust its own no-speech + confidence scores, not string matching
    if segs and all(sg.get("no_speech_prob", 0) > 0.6 or sg.get("avg_logprob", 0) < -1.2 for sg in segs):
        text = ""
    if text.strip(" .").lower() == prompt.strip(" .").lower():   # verbatim prompt echo
        text = ""
    return text, (time.perf_counter() - t) * 1000


def transcribe(audio: np.ndarray) -> tuple[str, float]:
    return _transcribe(audio, os.getenv("STITI_WHISPER", WHISPER_MAIN), HINGLISH_PROMPT)


def transcribe_wake(audio: np.ndarray) -> tuple[str, float]:
    return transcribe(audio)
