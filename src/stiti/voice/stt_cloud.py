"""Cloud second opinion for hard turns: Groq whisper-large-v3 (free tier), only when the local ear is unsure (D27).

Measured on the research set (docs/research/stt_tts_indian_english.md): Groq large-v3 + the owner glossary = 5.5% WER
at 297 ms; the local-first hybrid (escalate when Whisper's avg_logprob < -0.5 or the text is empty) = 6.3% WER at
p50 272 ms, with 16% of turns escalated. Turbo is NOT used: it ignored the glossary and echoed the prompt.

Privacy: audio leaves the Mac only on escalated turns, and only the glossary terms that aren't private (P2) go with
it. Switch: STITI_STT_CLOUD=on|off (env wins), else owner_profile key `stt_cloud` (on|off), default on. The Groq key
comes from .env through the router's client (shared keep-alive connection); it is never printed or logged.
A failure, a timeout or a 429 cools the lane down for a while so a dead network never adds 700 ms to every turn.
"""
from __future__ import annotations

import io
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutTimeout
from dataclasses import dataclass, field

import numpy as np

MODEL = "whisper-large-v3"
CAP_MS = float(os.getenv("STITI_STT_CLOUD_MS", "700"))
PROMPT_TOKENS = 200                # Groq / Whisper keep ≤ 224 prompt tokens; stay under it
COOL_TIMEOUT_S, COOL_ERROR_S, COOL_RATE_S = 5.0, 60.0, 60.0   # a timed-out request still warms the connection
IDLE_REWARM_S = 240.0             # httpx keep-alive is 300 s; re-open TLS before it is needed
_OFF = {"off", "0", "false", "no", "never"}

_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="stt-cloud")
_cool_until = 0.0
_last_use = 0.0
_lock = threading.Lock()
stats = {"calls": 0, "ok": 0, "timeouts": 0, "errors": 0}


@dataclass
class CloudResult:
    text: str
    ms: float
    segments: list[dict] = field(default_factory=list)


def setting() -> str:
    """'on' or 'off' (env STITI_STT_CLOUD wins over the owner_profile key stt_cloud)."""
    v = os.getenv("STITI_STT_CLOUD")
    if not v:
        try:
            from .. import profile
            v = profile.get("stt_cloud") or "on"
        except Exception:
            v = "on"
    return "off" if v.strip().lower() in _OFF else "on"


def has_key() -> bool:
    from ..config import CFG
    return bool(CFG.keys.get("groq"))


def enabled() -> bool:
    return setting() == "on" and has_key() and time.monotonic() >= _cool_until


def _cool(seconds: float) -> None:
    global _cool_until
    with _lock:
        _cool_until = max(_cool_until, time.monotonic() + seconds)


def reset() -> None:
    global _cool_until
    _cool_until = 0.0


def prewarm() -> None:
    """Called when a turn starts transcribing: if the Groq connection may have gone cold, re-open it in the
    background while local Whisper runs (~270 ms), so an escalation doesn't pay the TLS handshake (Wispr warm-up).
    A cold first call measured ~1 s and blew the 700 ms cap."""
    global _last_use
    if not enabled() or time.monotonic() - _last_use < IDLE_REWARM_S:
        return
    _last_use = time.monotonic()

    def ping():
        try:
            from .. import router
            c = router._client("groq")
            if c is not None:
                c.with_options(timeout=5.0).models.list()
        except Exception:
            pass
    _pool.submit(ping)


def trim_prompt(prompt: str, budget: int = PROMPT_TOKENS) -> str:
    """Drop words from the FRONT (the least important glossary terms) until the prompt fits."""
    from .glossary import _tokens
    words = prompt.split()
    while words and _tokens(" ".join(words)) > budget:
        words.pop(0)
    return " ".join(words)


def _flac(audio: np.ndarray) -> bytes:
    import soundfile as sf
    buf = io.BytesIO()
    sf.write(buf, np.clip(np.asarray(audio, dtype=np.float32), -1, 1), 16000, format="FLAC", subtype="PCM_16")
    return buf.getvalue()


def _call(audio: np.ndarray, prompt: str) -> CloudResult:
    from .. import router
    client = router._client("groq")
    if client is None:
        raise RuntimeError("no groq key")
    t = time.perf_counter()
    r = client.with_options(timeout=5.0).audio.transcriptions.create(
        model=MODEL, file=("turn.flac", _flac(audio)), language="en", prompt=trim_prompt(prompt),
        temperature=0.0, response_format="verbose_json")
    ms = (time.perf_counter() - t) * 1000
    segs = [s.model_dump() if hasattr(s, "model_dump") else dict(s) for s in (getattr(r, "segments", None) or [])]
    try:
        router._record("groq", MODEL, 0, 0)          # shows up in llm_usage next to the chat models
    except Exception:
        pass
    return CloudResult((getattr(r, "text", "") or "").strip(), ms, segs)


def transcribe(audio: np.ndarray, prompt: str, cap_ms: float | None = None, call=None) -> CloudResult | None:
    """Re-transcribe one turn in the cloud. None when off, cooling down, too slow (cap) or failed: keep local."""
    if not enabled():
        return None
    global _last_use
    stats["calls"] += 1
    _last_use = time.monotonic()
    fut = _pool.submit(call or _call, audio, prompt)
    try:
        res = fut.result(timeout=(cap_ms if cap_ms is not None else CAP_MS) / 1000)
        stats["ok"] += 1
        return res
    except FutTimeout:
        stats["timeouts"] += 1
        _cool(COOL_TIMEOUT_S)                         # the request finishes in the background and is ignored
        return None
    except Exception as e:                            # never print the request: it carries the key header
        stats["errors"] += 1
        status = getattr(e, "status_code", None)
        retry = None
        try:
            retry = float(e.response.headers.get("retry-after"))
        except Exception:
            pass
        _cool((retry or COOL_RATE_S) if status == 429 else COOL_ERROR_S)
        if os.getenv("STITI_STT_DEBUG"):
            print(f"[stt-cloud] {type(e).__name__} {status or ''}")
        return None
