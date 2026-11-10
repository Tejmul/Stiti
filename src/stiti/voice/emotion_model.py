"""emotion2vec+ base (FunASR, ~90M params): deep voice emotion, run in a background thread.

Measured on M2: ~165 ms/utterance, but +1.55 GB footprint (funasr + torch) → OFF by default on 8 GB;
turn it on from the menubar ("Deep voice emotion") or STITI_VOICE_EMOTION=emotion2vec. Generic naturalistic accuracy is
only ~41% (research), so confidence is scaled down and capped — prosody vs. his own baseline and
the text still vote. Set STITI_VOICE_EMOTION=off to skip it entirely.

D28: the same forward pass also returns the 768-d utterance embedding. When the nightly trainer has switched on a
PERSONAL head (it beat this generic mapping on his own held-out turns), that head decides; else the generic map.
The embedding is kept for the recorder (`recent()`), so learning costs no second pass.
"""
from __future__ import annotations

import threading
from collections import OrderedDict

import numpy as np

MAP = {"angry": "angry", "disgusted": "angry", "fearful": "stressed", "happy": "happy",
       "neutral": "calm", "sad": "sad", "surprised": None, "other": None, "<unk>": None, "unknown": None}
_model = None
_lock = threading.Lock()
_recent: OrderedDict[int, dict] = OrderedDict()   # id(audio) → {"emb", "scores"} of the last few turns


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


def analyze(audio16k: np.ndarray) -> dict:
    """One pass → {"emb": 768-d float32 | None, "scores": {generic class: prob}}."""
    m = _load()
    r = m.generate(np.asarray(audio16k, dtype=np.float32), granularity="utterance", extract_embedding=True,
                   disable_pbar=True)[0]
    feats = r.get("feats")
    emb = np.asarray(feats, dtype=np.float32).reshape(-1) if feats is not None else None
    return {"emb": emb, "scores": {str(lab).split("/")[-1]: float(s) for lab, s in zip(r["labels"], r["scores"])}}


def generic_label(scores: dict) -> tuple[str, float] | None:
    """The generic 9-class → Stiti mood map (the baseline the personal head must beat)."""
    if not scores:
        return None
    best, p = max(scores.items(), key=lambda kv: kv[1])
    label = MAP.get(best)
    if label is None:
        return None
    return label, float(min(0.7, p * 0.8))


def decide(res: dict) -> tuple[str, float] | None:
    """Personal head if active and confident, else the generic map. Pure (testable without the model)."""
    from ..learn import personal
    p = personal.predict("e2v", res.get("emb")) if res.get("emb") is not None else None
    if p is not None:
        personal.note(p[0], p[1], "personal")
        return p
    g = generic_label(res.get("scores") or {})
    if g is not None:
        personal.note(g[0], g[1], "generic")
    return g


def remember(audio, res: dict) -> None:
    with _lock:
        _recent[id(audio)] = res
        while len(_recent) > 8:
            _recent.popitem(last=False)


def recent(audio) -> dict | None:
    """The embedding/scores the live pass computed for this exact audio buffer (for the recorder)."""
    with _lock:
        return _recent.get(id(audio))


def classify(audio16k: np.ndarray) -> tuple[str, float] | None:
    res = analyze(audio16k)
    remember(audio16k, res)
    return decide(res)
