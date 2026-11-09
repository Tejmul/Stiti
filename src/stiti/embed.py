"""In-process embedder: EmbeddingGemma-300M, 4-bit ONNX (~197 MB disk, ~600 MB RSS, ~7 ms/query on M2), 768-dim.

Ungated ONNX build from onnx-community (Gemma Terms of Use apply). No torch, no Ollama.
Every stored vector records EMBED_MODEL so a later model swap can re-embed (report D9).
"""
from __future__ import annotations

import threading
from functools import lru_cache

import numpy as np
from pgvector import HalfVector

REPO_ID = "onnx-community/embeddinggemma-300m-ONNX"
VARIANT = "model_q4"
EMBED_MODEL = f"embeddinggemma-300m-onnx-{VARIANT}"
DIM = 768
MAX_TOKENS = 512

QUERY_PREFIX = "task: search result | query: "
DOC_PREFIX = "title: none | text: "

_lock = threading.Lock()


@lru_cache(maxsize=1)
def _load():
    import onnxruntime as ort
    from huggingface_hub import hf_hub_download
    from tokenizers import Tokenizer

    from .config import CFG

    # real files (not HF-cache symlinks): onnxruntime rejects external data behind symlinks
    local = CFG.home / "models" / "embeddinggemma-300m-onnx"
    path = hf_hub_download(REPO_ID, subfolder="onnx", filename=f"{VARIANT}.onnx", local_dir=local)
    hf_hub_download(REPO_ID, subfolder="onnx", filename=f"{VARIANT}.onnx_data", local_dir=local)
    tok = Tokenizer.from_file(hf_hub_download(REPO_ID, filename="tokenizer.json", local_dir=local))
    tok.enable_truncation(MAX_TOKENS)
    tok.enable_padding()
    opts = ort.SessionOptions()
    opts.intra_op_num_threads = 4
    sess = ort.InferenceSession(path, opts, providers=["CPUExecutionProvider"])
    return tok, sess


def _embed(texts: list[str]) -> np.ndarray:
    tok, sess = _load()
    enc = tok.encode_batch(texts)
    feeds = {
        "input_ids": np.array([e.ids for e in enc], dtype=np.int64),
        "attention_mask": np.array([e.attention_mask for e in enc], dtype=np.int64),
    }
    names = {i.name for i in sess.get_inputs()}
    feeds = {k: v for k, v in feeds.items() if k in names}
    with _lock:
        out = sess.run(None, feeds)
    vecs = out[1] if len(out) > 1 else out[0]
    vecs = vecs / np.linalg.norm(vecs, axis=1, keepdims=True)
    return vecs.astype(np.float32)


def embed_query(text: str) -> HalfVector:
    return HalfVector(_embed([QUERY_PREFIX + text])[0])


def embed_docs(texts: list[str]) -> list[HalfVector]:
    return [HalfVector(v) for v in _embed([DOC_PREFIX + t for t in texts])]
