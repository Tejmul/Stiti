"""LLM router: free cloud tiers only (no local LLM, D8). ~150 lines, no LiteLLM (D9).

Chains per route; privacy gate (P2 never leaves the Mac; Gemini only for P0);
quota + cooldown accounting in Postgres `llm_usage`; 429 -> cooldown -> next provider.
Model IDs are checked against each provider's /models list on first use.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

from openai import OpenAI

from .config import CFG
from .db import one, q


@dataclass(frozen=True)
class Provider:
    name: str
    base_url: str
    rpm: int
    rpd: int
    tpm: int  # tokens per minute (0 = unknown)


PROVIDERS = {
    "groq": Provider("groq", "https://api.groq.com/openai/v1", 30, 1000, 8000),
    "cerebras": Provider("cerebras", "https://api.cerebras.ai/v1", 5, 10_000, 0),
    "openrouter": Provider("openrouter", "https://openrouter.ai/api/v1", 20, 50, 0),
    "mistral": Provider("mistral", "https://api.mistral.ai/v1", 60, 10_000, 0),
    "gemini": Provider("gemini", "https://generativelanguage.googleapis.com/v1beta/openai/", 10, 500, 0),
}

# (provider, model) in order; first available wins. Confirm IDs in each console.
CHAINS = {
    "voice_fast": [("groq", "openai/gpt-oss-20b"), ("groq", "qwen/qwen3.8-27b"),
                   ("cerebras", "gpt-oss-120b"), ("groq", "openai/gpt-oss-120b"),
                   ("openrouter", "openai/gpt-oss-20b:free"), ("mistral", "mistral-small-latest")],
    "background_smart": [("cerebras", "gpt-oss-120b"), ("cerebras", "qwen-3.8-27b"),
                         ("groq", "openai/gpt-oss-120b"), ("mistral", "mistral-small-latest")],
}
P0_EXTRA = [("gemini", "gemini-flash-lite-latest")]


class NoProvider(RuntimeError):
    pass


_clients: dict[str, OpenAI] = {}
_models: dict[str, set[str] | None] = {}


def _client(p: str) -> OpenAI | None:
    key = CFG.keys.get(p)
    if not key:
        return None
    if p not in _clients:
        _clients[p] = OpenAI(api_key=key, base_url=PROVIDERS[p].base_url, timeout=20, max_retries=0)
    return _clients[p]


def _available_models(p: str) -> set[str] | None:
    if p not in _models:
        try:
            _models[p] = {m.id for m in _client(p).models.list().data}
        except Exception:
            _models[p] = None  # unknown: try anyway
    return _models[p]


def _gate_ok(p: str, model: str, est_tokens: int) -> bool:
    row = one("""SELECT requests, minute_start, minute_tokens, minute_requests, cooldown_until
                 FROM llm_usage WHERE provider=%s AND model=%s AND day=current_date""", (p, model))
    if not row:
        return True
    if row["cooldown_until"] and row["cooldown_until"] > _now():
        return False
    prov = PROVIDERS[p]
    if row["requests"] >= 0.95 * prov.rpd:
        return False
    if row["minute_start"] and (_now() - row["minute_start"]).total_seconds() < 60:
        if row["minute_requests"] >= prov.rpm or (prov.tpm and row["minute_tokens"] + est_tokens > 0.9 * prov.tpm):
            return False
    return True


def _now():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc)


def _record(p: str, model: str, tin: int, tout: int, err: str | None = None, cooldown_s: float = 0):
    q("""INSERT INTO llm_usage(provider, model, day, requests, tokens_in, tokens_out,
                               minute_start, minute_tokens, minute_requests, cooldown_until, last_error)
         VALUES (%(p)s,%(m)s,current_date,%(r)s,%(ti)s,%(to)s,now(),%(tt)s,%(r)s,
                 CASE WHEN %(cd)s > 0 THEN now() + make_interval(secs => %(cd)s) END, %(e)s)
         ON CONFLICT (provider, model, day) DO UPDATE SET
           requests = llm_usage.requests + EXCLUDED.requests,
           tokens_in = llm_usage.tokens_in + EXCLUDED.tokens_in,
           tokens_out = llm_usage.tokens_out + EXCLUDED.tokens_out,
           minute_tokens = CASE WHEN llm_usage.minute_start > now() - interval '60 s'
                                THEN llm_usage.minute_tokens + EXCLUDED.minute_tokens ELSE EXCLUDED.minute_tokens END,
           minute_requests = CASE WHEN llm_usage.minute_start > now() - interval '60 s'
                                THEN llm_usage.minute_requests + EXCLUDED.minute_requests ELSE EXCLUDED.minute_requests END,
           minute_start = CASE WHEN llm_usage.minute_start > now() - interval '60 s'
                                THEN llm_usage.minute_start ELSE now() END,
           cooldown_until = COALESCE(EXCLUDED.cooldown_until, llm_usage.cooldown_until),
           last_error = EXCLUDED.last_error""",
      {"p": p, "m": model, "r": 0 if err and not cooldown_s else 1, "ti": tin, "to": tout,
       "tt": tin + tout, "cd": cooldown_s, "e": err})


def complete(messages: list[dict], *, route: str = "voice_fast", privacy: int = 1,
             max_tokens: int = 400, temperature: float = 0.6, json_mode: bool = False) -> dict:
    """Returns {text, provider, model, ms, tokens_in, tokens_out}. Raises NoProvider if all fail."""
    if privacy >= 2:
        raise NoProvider("P2: sensitive content never leaves the Mac")
    chain = list(CHAINS[route]) + (P0_EXTRA if privacy == 0 else [])
    est = sum(len(m["content"]) for m in messages) // 4 + max_tokens
    errors = []
    for p, model in chain:
        cli = _client(p)
        if cli is None:
            continue
        avail = _available_models(p)
        if avail is not None and model not in avail:
            continue
        if not _gate_ok(p, model, est):
            errors.append(f"{p}/{model}: gated")
            continue
        kwargs = dict(model=model, messages=messages, max_tokens=max_tokens, temperature=temperature)
        if "gpt-oss" in model and p in ("groq", "cerebras", "openrouter"):
            kwargs["extra_body"] = {"reasoning_effort": "low"}  # fast voice turns; avoid empty content
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        t = time.perf_counter()
        try:
            r = cli.chat.completions.create(**kwargs)
        except Exception as e:
            status = getattr(e, "status_code", None)
            retry = 60.0
            hdrs = getattr(getattr(e, "response", None), "headers", {}) or {}
            if hdrs.get("retry-after"):
                try:
                    retry = float(hdrs["retry-after"])
                except ValueError:
                    pass
            _record(p, model, 0, 0, f"{status}: {str(e)[:200]}", cooldown_s=retry if status == 429 else 0)
            errors.append(f"{p}/{model}: {status or type(e).__name__}")
            continue
        text = (r.choices[0].message.content or "").strip()
        u = r.usage
        tin, tout = (u.prompt_tokens, u.completion_tokens) if u else (est, len(text) // 4)
        _record(p, model, tin, tout)
        if not text:
            errors.append(f"{p}/{model}: empty")
            continue
        return {"text": text, "provider": p, "model": model, "ms": (time.perf_counter() - t) * 1000,
                "tokens_in": tin, "tokens_out": tout}
    raise NoProvider("; ".join(errors) or "no API keys configured (.env)")


def status() -> list[dict]:
    out = []
    for p in PROVIDERS:
        out.append({"provider": p, "key": bool(CFG.keys.get(p))})
    return out
