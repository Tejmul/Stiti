"""Smart Turn v3.2 (pipecat-ai, BSD-2, 8.7 MB int8 ONNX): "has he FINISHED his thought?"

Silence alone cuts people off mid-pause (research: 32/80 cut-offs with silence-only; Hinglish
fillers like "aur…", "matlab…" make it worse). On a short pause (~300 ms) we ask Smart Turn; if it
says complete, Stiti answers fast; if not, she waits up to the fallback (~2 s) of silence.
Reference: github.com/pipecat-ai/smart-turn inference.py (Whisper features, last 8 s, sigmoid out).
"""
from __future__ import annotations

import threading
import urllib.request

import numpy as np

from .models import DIR

URL = "https://huggingface.co/pipecat-ai/smart-turn-v3/resolve/main/smart-turn-v3.2-cpu.onnx"
_sess = None
_fe = None
_lock = threading.Lock()


def _load():
    global _sess, _fe
    with _lock:
        if _sess is None:
            import onnxruntime as ort
            from transformers import WhisperFeatureExtractor
            DIR.mkdir(parents=True, exist_ok=True)
            p = DIR / "smart-turn-v3.2-cpu.onnx"
            if not p.exists():
                urllib.request.urlretrieve(URL, p)
            so = ort.SessionOptions()
            so.inter_op_num_threads = 1
            so.intra_op_num_threads = 2
            so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
            _sess = ort.InferenceSession(str(p), sess_options=so, providers=["CPUExecutionProvider"])
            _fe = WhisperFeatureExtractor(chunk_length=8)
    return _sess, _fe


def complete_prob(audio16k: np.ndarray) -> float:
    sess, fe = _load()
    a = audio16k.astype(np.float32)[-8 * 16000:]
    if len(a) < 8 * 16000:
        a = np.pad(a, (8 * 16000 - len(a), 0))
    feats = fe(a, sampling_rate=16000, return_tensors="np", padding="max_length", max_length=8 * 16000,
               truncation=True, do_normalize=True).input_features.astype(np.float32)
    return float(sess.run(None, {"input_features": feats})[0][0].item())
