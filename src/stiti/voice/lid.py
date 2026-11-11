"""Which language he SPOKE, from the audio (D34) — so Telugu speech isn't silently translated into English.

STT is pinned to English (+ a Hinglish prompt) because Whisper without a language turns Hinglish into Devanagari or
Urdu and translates when forced. That pin also turns Telugu speech into English. So before transcribing, Whisper-tiny's
own language ID (32 ms on the M2, ~40 MB) asks: English, Hindi or Telugu? He speaks only those three, so the scores
are pooled into three groups (Kannada/Tamil/Malayalam count as Telugu — tiny confuses the Dravidian neighbours) and
Telugu wins only with ≥ 50 % of the pooled score. Measured on 27 synthetic clips (docs/research/language_switching.md):
English 6/6, Hindi + Hinglish 9/9, Telugu 6/6; Tenglish 3/6 (the transcript's Telugu script settles those).
STITI_LID=off disables it.
"""
from __future__ import annotations

import os
import threading

import numpy as np

MODEL = os.getenv("STITI_LID_MODEL", "mlx-community/whisper-tiny-mlx")
GROUPS = {"en": ("en",), "hi": ("hi", "ur", "mr", "ne"), "te": ("te", "kn", "ta", "ml")}
TE_SHARE = 0.6                     # Telugu needs a clear majority of the pooled score …
TE_SHARE_SHORT, SHORT_SECONDS = 0.75, 2.0   # … and a big one on short clips ("Suno Stiti" scored 0.55 as Telugu)
MIN_SECONDS = 0.8                  # shorter clips ("ok", "haan") carry too little to judge
_lock = threading.Lock()
_m: dict = {}


def enabled() -> bool:
    return os.getenv("STITI_LID", "on") != "off"


def _load():
    with _lock:
        if not _m:
            from mlx_whisper.load_models import load_model
            from mlx_whisper.tokenizer import get_tokenizer
            model = load_model(MODEL)
            _m["model"] = model
            _m["tok"] = get_tokenizer(model.is_multilingual, num_languages=model.num_languages)
    return _m["model"], _m["tok"]


def pooled(probs: dict[str, float]) -> dict[str, float]:
    g = {k: sum(probs.get(x, 0.0) for x in langs) for k, langs in GROUPS.items()}
    tot = sum(g.values()) or 1.0
    return {k: v / tot for k, v in g.items()}


def detect(audio: np.ndarray, sr: int = 16000) -> tuple[str, float] | None:
    """("en"|"hi"|"te", pooled share) or None (off, too short, model unavailable). Call on the STT thread."""
    if not enabled() or len(audio) < MIN_SECONDS * sr:
        return None
    try:
        import mlx.core as mx
        from mlx_whisper.audio import log_mel_spectrogram, pad_or_trim
        from mlx_whisper.decoding import detect_language
        model, tok = _load()
        mel = pad_or_trim(log_mel_spectrogram(mx.array(np.asarray(audio, dtype=np.float32)),
                                              n_mels=model.dims.n_mels), 3000, axis=-2)
        _, probs = detect_language(model, mel[None].astype(mx.float16), tok)
        share = pooled(probs[0])
    except Exception:
        return None
    best = max(share, key=share.get)
    if share["te"] >= (TE_SHARE_SHORT if len(audio) < SHORT_SECONDS * sr else TE_SHARE):
        return "te", share["te"]
    return best, share[best]
