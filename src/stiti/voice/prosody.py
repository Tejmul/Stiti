"""Voice emotion v1: prosody vs. Tejmul's own baseline (loudness, pitch, pace). numpy only, ~1 ms.

Research: naturalistic SER is ~41% accurate generic, much better speaker-adapted -> so we compare
him to HIM. Output is a soft hint (conf ≤0.6 until 20 utterances of baseline). emotion2vec+ base
can be added behind STITI_VOICE_EMOTION=emotion2vec later.
"""
from __future__ import annotations

import json

import numpy as np

from ..config import CFG

BASE = CFG.home / "voice_baseline.json"


def features(audio: np.ndarray, sr: int, n_words: int) -> dict:
    a = audio.astype(np.float32)
    rms = float(np.sqrt(np.mean(a ** 2)) + 1e-9)
    db = 20 * np.log10(rms)
    # frame-wise autocorrelation pitch (75–400 Hz) on voiced frames
    hop, win = int(sr * 0.02), int(sr * 0.04)
    pitches = []
    for i in range(0, len(a) - win, hop):
        f = a[i:i + win] * np.hanning(win)
        if np.sqrt(np.mean(f ** 2)) < rms * 0.5:
            continue
        ac = np.correlate(f, f, "full")[win - 1:]
        lo, hi = int(sr / 400), int(sr / 75)
        if hi >= len(ac):
            continue
        k = lo + int(np.argmax(ac[lo:hi]))
        if ac[k] > 0.3 * ac[0]:
            pitches.append(sr / k)
    dur = len(a) / sr
    return {"db": db, "pitch": float(np.median(pitches)) if pitches else 0.0,
            "pitch_sd": float(np.std(pitches)) if len(pitches) > 2 else 0.0,
            "rate": n_words / max(dur, 0.5)}


def _load() -> dict:
    if BASE.exists():
        return json.loads(BASE.read_text())
    return {"n": 0, "mean": {}, "var": {}}


def update_and_score(feat: dict) -> tuple[str | None, float, float]:
    """Update running baseline (Welford-ish EMA); return (label, conf, arousal z)."""
    b = _load()
    z = {}
    for k, v in feat.items():
        if k == "pitch" and v == 0:
            continue
        m, var = b["mean"].get(k, v), b["var"].get(k, 1.0)
        z[k] = (v - m) / (var ** 0.5 + 1e-6) if b["n"] >= 5 else 0.0
        alpha = 1 / min(b["n"] + 1, 50)
        b["mean"][k] = m + alpha * (v - m)
        b["var"][k] = (1 - alpha) * var + alpha * (v - m) ** 2
    b["n"] += 1
    BASE.write_text(json.dumps(b))
    arousal = float(np.mean([z.get("db", 0), z.get("pitch", 0), z.get("rate", 0), z.get("pitch_sd", 0)]))
    label, conf = _rule(b["n"], arousal)
    from ..learn import personal                 # D28: his own head, only when it beat this rule on his data
    p = personal.predict("prosody", feat)
    if p is not None:
        personal.note(p[0], p[1], "personal")
        return p[0], p[1], arousal
    personal.note(label, conf, "generic")
    return label, conf, arousal


def _rule(n: int, arousal: float) -> tuple[str | None, float]:
    """The generic rule: arousal vs his baseline → stressed / tired / calm."""
    if n < 5:
        return None, 0.0
    cap = 0.6 if n >= 20 else 0.45
    if arousal > 1.0:
        return "stressed", min(cap, 0.3 + 0.15 * arousal)    # high arousal; text decides angry vs happy
    if arousal < -1.0:
        return "tired", min(cap, 0.3 + 0.15 * -arousal)
    return "calm", 0.3


def generic_label(feat: dict) -> str | None:
    """What the generic rule says for these features vs the current baseline — read-only (for the recorder)."""
    b = _load()
    if b["n"] < 5:
        return None
    z = [(feat[k] - b["mean"][k]) / (b["var"].get(k, 1.0) ** 0.5 + 1e-6)
         for k in ("db", "pitch", "rate", "pitch_sd") if k in feat and k in b["mean"] and not (k == "pitch" and feat[k] == 0)]
    return _rule(b["n"], float(np.sum(z) / 4))[0]
