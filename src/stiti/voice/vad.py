"""Silero VAD v5 via onnxruntime (~2 MB, <1 ms per 32 ms frame). No torch."""
from __future__ import annotations

import numpy as np
import onnxruntime as ort

from .models import path

SR = 16000
FRAME = 512          # 32 ms at 16 kHz
CONTEXT = 64


class VAD:
    def __init__(self):
        o = ort.SessionOptions()
        o.intra_op_num_threads = 1
        o.inter_op_num_threads = 1
        self.sess = ort.InferenceSession(str(path("silero_vad.onnx")), o, providers=["CPUExecutionProvider"])
        self.reset()

    def reset(self):
        self.state = np.zeros((2, 1, 128), dtype=np.float32)
        self.context = np.zeros((1, CONTEXT), dtype=np.float32)

    def prob(self, frame: np.ndarray) -> float:
        x = np.concatenate([self.context, frame.reshape(1, -1).astype(np.float32)], axis=1)
        out, self.state = self.sess.run(None, {"input": x, "state": self.state, "sr": np.array(SR, dtype=np.int64)})
        self.context = x[:, -CONTEXT:]
        return float(out[0][0])


def segments(audio: np.ndarray, vad: VAD, threshold: float = 0.5, end_silence_ms: int = 800,
             preroll_ms: int = 300) -> list[np.ndarray]:
    """Offline helper (tests): split a 16 kHz mono array into speech segments."""
    vad.reset()
    out, cur, silence, ring = [], [], 0, []
    pre = preroll_ms // 32
    for i in range(0, len(audio) - FRAME + 1, FRAME):
        f = audio[i:i + FRAME]
        p = vad.prob(f)
        if cur:
            cur.append(f)
            silence = 0 if p >= threshold else silence + 32
            if silence >= end_silence_ms:
                out.append(np.concatenate(cur))
                cur, silence = [], 0
        elif p >= threshold:
            cur = ring[-pre:] + [f]
        ring.append(f)
        ring = ring[-pre:]
    if cur:
        out.append(np.concatenate(cur))
    return out
