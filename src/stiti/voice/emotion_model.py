"""emotion2vec+ base (FunASR, ~90M params): deep voice emotion, run in a background thread.

Measured on M2: ~165 ms/utterance, ~+800 MB RSS (torch + model). Generic naturalistic accuracy is
only ~41% (research), so confidence is scaled down and capped — prosody vs. his own baseline and
the text still vote. Set STITI_VOICE_EMOTION=off to skip it entirely.
"""
from __future__ import annotations

import threading

import numpy as np

MAP = {"angry": "angry", "disgusted": "angry", "fearful": "stressed", "happy": "happy",
       "neutral": "calm", "sad": "sad", "surprised": None, "other": None, "<unk>": None}
_model = None
_lock = threading.Lock()


def _load():
    global _model
    with _lock:
        if _model is None:
            from funasr import AutoModel
            _model = AutoModel(model="emotion2vec/emotion2vec_plus_base", hub="hf",
                               disable_update=True, log_level="ERROR")
    return _model


def preload_async() -> None:
    threading.Thread(target=_load, daemon=True).start()


def classify(audio16k: np.ndarray) -> tuple[str, float] | None:
    m = _load()
    r = m.generate(audio16k.astype(np.float32), granularity="utterance", extract_embedding=False,
                   disable_pbar=True)[0]
    best = max(zip(r["labels"], r["scores"]), key=lambda x: x[1])
    label = MAP.get(best[0].split("/")[-1])
    if label is None:
        return None
    return label, float(min(0.7, best[1] * 0.8))
