"""Live side of the personal emotion head (D28): load the ACTIVE head, predict, remember provenance.

Two heads, trained nightly by `emotion_train.py` and switched on only when they beat the generic predictor on his
held-out turns:
  e2v      emotion2vec+ 768-d embedding − his mean → PCA (whitened) → softmax over his moods
  prosody  [loudness, pitch, pitch SD, rate] z-scored on his own data → softmax (works with emotion2vec OFF)
A prediction is temperature-calibrated and abstains (None) below the head's threshold → the generic path runs.
Cost: a ≤32×6 matrix multiply, ~10 µs; the model file is a few KB.
"""
from __future__ import annotations

import json
import os
import threading
import time
from collections import deque
from pathlib import Path

import numpy as np

from ..config import CFG

MOODS = ("calm", "happy", "stressed", "angry", "sad", "tired")
PROSODY_KEYS = ("db", "pitch", "pitch_sd", "rate")
_lock = threading.Lock()
_cache: dict[str, tuple[float, dict | None]] = {}
_recent: deque = deque(maxlen=16)          # (label, conf, src, t) of voice reads handed to the engine


def model_dir(create: bool = False) -> Path:
    """~/.stiti/models/personal_emotion (STITI_PERSONAL_EMOTION_DIR overrides). Only the trainer creates it."""
    d = Path(os.path.expanduser(os.getenv("STITI_PERSONAL_EMOTION_DIR", str(CFG.home / "models" / "personal_emotion"))))
    if create:
        d.mkdir(parents=True, exist_ok=True)
    return d


def _active_file() -> Path:
    return model_dir() / "active.json"


def active_versions() -> dict[str, int | None]:
    try:
        return json.loads(_active_file().read_text())
    except (OSError, ValueError):
        return {}


def load(kind: str, version: int) -> dict:
    with np.load(model_dir() / f"{kind}-v{version}.npz", allow_pickle=False) as z:
        m = {k: z[k] for k in z.files}
    m["classes"] = [str(c) for c in m["classes"]]
    m["T"], m["threshold"] = float(m["T"]), float(m["threshold"])
    return m


def active(kind: str) -> dict | None:
    """The active head of this kind, or None (generic). Re-read only when active.json changes."""
    f = _active_file()
    try:
        mt = f.stat().st_mtime
    except OSError:
        return None
    with _lock:
        hit = _cache.get(kind)
        if hit and hit[0] == mt:
            return hit[1]
        v = active_versions().get(kind)
        try:
            m = load(kind, int(v)) if v else None
        except (OSError, ValueError, KeyError):
            m = None
        _cache[kind] = (mt, m)
        return m


def features(kind: str, raw, m: dict) -> np.ndarray | None:
    """Raw input → the head's normalized feature vector (the same transform the trainer used)."""
    if kind == "e2v":
        x = np.asarray(raw, dtype=np.float32).reshape(-1)
        if x.shape[0] != m["mu"].shape[0]:
            return None
        return ((x - m["mu"]) @ m["comps"].T) / m["scale"]
    vals = []
    for i, k in enumerate(PROSODY_KEYS):
        v = float(raw.get(k, 0.0) or 0.0) if isinstance(raw, dict) else float(raw[i])
        if k == "pitch" and v == 0.0:
            v = float(m["mean"][i])            # unvoiced: impute his mean pitch
        vals.append(v)
    return (np.asarray(vals, dtype=np.float32) - m["mean"]) / m["std"]


def probs(m: dict, x: np.ndarray) -> np.ndarray:
    z = (x @ m["W"] + m["b"]) / m["T"]
    z = z - z.max()
    e = np.exp(z)
    return e / e.sum()


def predict(kind: str, raw) -> tuple[str, float] | None:
    """(label, calibrated conf) from the ACTIVE personal head, or None (no active head / abstain)."""
    m = active(kind)
    if m is None or raw is None:
        return None
    try:
        x = features(kind, raw, m)
    except Exception:
        return None
    if x is None:
        return None
    p = probs(m, x)
    k = int(np.argmax(p))
    conf = float(min(0.9, p[k]))
    if conf < m["threshold"]:
        return None
    return m["classes"][k], conf


def note(label: str | None, conf: float, src: str) -> None:
    """Remember where a voice read came from, so fuse() can trust a personal one more."""
    if label:
        _recent.append((label, round(float(conf), 4), src, time.time()))


def provenance(label: str | None, conf: float, within_s: float = 120.0) -> str | None:
    if not label:
        return None
    now, c = time.time(), round(float(conf), 4)
    for lab, cf, src, t in reversed(_recent):
        if lab == label and cf == c and now - t <= within_s:
            return src
    return None
