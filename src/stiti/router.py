"""LLM router: free cloud tiers only (no local LLM, D8). ~150 lines, no LiteLLM (D9).

Chains per route; privacy gate (P2 never leaves the Mac; Gemini only for P0);
quota + cooldown accounting in Postgres `llm_usage`; 429 -> cooldown -> next provider.
Model IDs are checked against each provider's /models list on first use.
"""
from __future__ import annotations

import json
import re
import threading
import time
from dataclasses import dataclass
from typing import Iterator

import httpx

from openai import OpenAI

from .config import CFG
from .db import one, q, unheld


@dataclass(frozen=True)
class Provider:
    name: str
    base_url: str
    rpm: int
    rpd: int
    tpm: int          # tokens per minute (0 = unknown)
    max_privacy: int  # highest privacy tier this provider may see: 1 = personal OK, 0 = public questions only


# Free tiers only (D8, D17). max_privacy 1 = no training on API data per the provider's terms.
PROVIDERS = {
    "groq": Provider("groq", "https://api.groq.com/openai/v1", 30, 1000, 8000, 1),
    "cerebras": Provider("cerebras", "https://api.cerebras.ai/v1", 5, 10_000, 0, 1),        # now needs a card (2026-07)
    "zai": Provider("zai", "https://api.z.ai/api/paas/v4", 20, 10_000, 0, 1),                # GLM Flash: free, 1 at a time
    "cloudflare": Provider("cloudflare", "https://api.cloudflare.com/client/v4/accounts/{account}/ai/v1",
                           60, 300, 0, 1),                                                    # 10k neurons/day free
    "openrouter": Provider("openrouter", "https://openrouter.ai/api/v1", 20, 50, 0, 1),     # P1 only via data_collection=deny
    "mistral": Provider("mistral", "https://api.mistral.ai/v1", 60, 10_000, 0, 1),          # opt out of training first
    "nvidia": Provider("nvidia", "https://integrate.api.nvidia.com/v1", 40, 10_000, 0, 0),  # trial terms: public only
    "gemini": Provider("gemini", "https://generativelanguage.googleapis.com/v1beta/openai/", 10, 500, 0, 0),  # free tier trains
}

# (provider, model) in order; first available wins. Missing keys / unknown model IDs are skipped automatically
# (IDs are checked against each provider's /models list). Latencies measured 2026-11-10 (first token, streaming).
NV_FAST = [("nvidia", "nvidia/nemotron-3.5-lightning-30b-a3b"), ("nvidia", "nvidia/nemotron-3.5-bolt-e4b")]
# nvidia/gemini entries are skipped automatically for personal (P1) turns (max_privacy 0).
CHAINS = {
    "voice_fast": [("groq", "qwen/qwen3.8-27b"),                 # ~190 ms first token
                   ("groq", "openai/gpt-oss-120b"),               # ~510 ms
                   ("groq", "openai/gpt-oss-20b"),
                   ("cerebras", "gpt-oss-120b"),
                   ("cloudflare", "@cf/openai/gpt-oss-120b"),        # ~1 s with low reasoning; personal backup
                   ("cloudflare", "@cf/meta/llama-3.3-70b-instruct-fp8-fast"),  # 0.9–16 s (varies)
                   *NV_FAST,                                       # ~0.5 s, public questions only
                   ("openrouter", "nvidia/nemotron-3-ultra-550b-a55b:free"),  # ~1–2.5 s
                   ("openrouter", "google/gemma-4-31b-it:free"), ("mistral", "mistral-small-latest"),
                   ("zai", "glm-4.7-flash"), ("zai", "glm-4.5-flash")],     # free but overloaded: 429s / 8–20 s
    "background_smart": [("cerebras", "gpt-oss-120b"), ("groq", "openai/gpt-oss-120b"), ("zai", "glm-4.7-flash"),
                         ("cerebras", "qwen-3.8-27b"), ("zai", "glm-4.5-flash"),
                         ("cloudflare", "@cf/openai/gpt-oss-120b"), ("nvidia", "nvidia/nemotron-3-ultra-550b-a55b"),
                         ("openrouter", "nvidia/nemotron-3-ultra-550b-a55b:free"), ("mistral", "mistral-small-latest")],
    # whiteboard tutor: lesson writing (strict JSON) — big free models first, Groq TPD is precious
    "tutor_plan": [("cerebras", "gpt-oss-120b"), ("groq", "openai/gpt-oss-120b"), ("groq", "qwen/qwen3.8-27b"),
                   ("groq", "openai/gpt-oss-20b"), ("cerebras", "qwen-3.8-27b"), ("zai", "glm-4.7-flash"),
                   ("cloudflare", "@cf/openai/gpt-oss-120b"), ("nvidia", "nvidia/nemotron-3-ultra-550b-a55b"),
                   ("openrouter", "nvidia/nemotron-3-ultra-550b-a55b:free"), ("mistral", "mistral-small-latest")],
}
# night/nap memory extraction (D38): strict-JSON models first; Groq limits are per model, so its other models are real
# fallbacks before a weaker one. Runs only while he's quiet (the voice chain's Groq qwen is never starved mid-talk).
CHAINS["extract"] = [("cerebras", "gpt-oss-120b"), ("groq", "openai/gpt-oss-120b"), ("groq", "qwen/qwen3.8-27b"),
                     ("groq", "openai/gpt-oss-20b"), ("cerebras", "qwen-3.8-27b"), ("zai", "glm-4.7-flash"),
                     ("cloudflare", "@cf/openai/gpt-oss-120b"), ("openrouter", "nvidia/nemotron-3-ultra-550b-a55b:free"),
                     ("mistral", "mistral-small-latest"), ("zai", "glm-4.5-flash")]
CHAINS["tutor_answer"] = [("groq", "qwen/qwen3.8-27b"), ("groq", "openai/gpt-oss-20b"), ("groq", "openai/gpt-oss-120b"),
                          ("cloudflare", "@cf/openai/gpt-oss-120b"), *NV_FAST,
                          ("openrouter", "nvidia/nemotron-3-ultra-550b-a55b:free"), ("zai", "glm-4.7-flash")]
# providers/models with strict json_schema (constrained decoding); others get json_object + validation
STRICT_SCHEMA = {("groq", "openai/gpt-oss-20b"), ("groq", "openai/gpt-oss-120b"), ("groq", "qwen/qwen3.8-27b"),
                 ("cerebras", "gpt-oss-120b"), ("cerebras", "qwen-3.8-27b")}
# last-resort extras for public (P0) questions
P0_EXTRA = [("nvidia", "nvidia/nemotron-3-ultra-550b-a55b"), ("gemini", "gemini-flash-lite-latest")]


# Z.ai models priced at 0 (docs.z.ai pricing, 2026-11-10). Its /models list omits them, so they skip that check.
ZAI_FREE = {"glm-4.7-flash", "glm-4.5-flash", "glm-4.6v-flash"}


def is_free(p: str, model: str) -> bool:
    """Zero-cost guard: never call a model that could bill, even if a key later gets credit or a card attached."""
    if p == "openrouter":
        return model.endswith(":free")
    if p == "zai":
        return model in ZAI_FREE                 # exact list: e.g. glm-5.3-flash exists but is NOT free
    return p in PROVIDERS                         # others: free-tier accounts with no billing attached


_HARMONY = re.compile(r"<\|[a-z_]+\|>")


def _clean(text: str) -> str:
    """gpt-oss on some hosts (Cloudflare) can leak its 'harmony' channel tokens, mostly when cut off mid-turn."""
    if "<|" not in text:
        return text
    if "<|channel|>final<|message|>" in text:
        text = text.rsplit("<|channel|>final<|message|>", 1)[1]
    elif "<|channel|>" in text:
        return ""                                  # only analysis/header tokens → treat as empty, try next provider
    return _HARMONY.sub("", text).strip()


class NoProvider(RuntimeError):
    pass


_clients: dict[str, OpenAI] = {}
_models: dict[str, set[str] | None] = {}


def _client(p: str) -> OpenAI | None:
    key = CFG.keys.get(p)
    if not key:
        return None
    if p not in _clients:
        url = PROVIDERS[p].base_url
        if "{account}" in url:
            account = CFG.keys.get(p + "_account", "")
            if not account:
                return None
            url = url.format(account=account)
        # keep TLS connections alive between turns (httpx default drops them after 5 s idle)
        http = httpx.Client(timeout=20, limits=httpx.Limits(max_keepalive_connections=4, keepalive_expiry=300))
        _clients[p] = OpenAI(api_key=key, base_url=url, timeout=20, max_retries=0, http_client=http)
    return _clients[p]


def _available_models(p: str) -> set[str] | None:
    if p not in _models:
        try:
            _models[p] = {m.id.removeprefix("models/") for m in _client(p).models.list().data}  # Gemini: "models/…"
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
    with unheld():                                 # quota use is real even if a speculative turn is discarded
        _record_q(p, model, tin, tout, err, cooldown_s)


def _record_q(p: str, model: str, tin: int, tout: int, err: str | None, cooldown_s: float):
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


def _shape_ok(text: str, schema: dict) -> bool:
    """Structured output sanity: parses as a JSON object and has every required top-level key."""
    t = text.strip()
    if t.startswith("```"):
        t = t.strip("`").split("\n", 1)[-1]
    try:
        d = json.loads(t[t.find("{"): t.rfind("}") + 1])
    except ValueError:
        return False
    return isinstance(d, dict) and all(k in d for k in schema.get("required", []))


def _attempts(messages, route, privacy, max_tokens, temperature, json_mode, tools, schema, schema_name,
              reasoning, errors):
    """Yield (provider, model, client, kwargs, est) for each usable chain entry, in order."""
    if privacy >= 2:
        raise NoProvider("P2: sensitive content never leaves the Mac")
    chain = [(p, m) for p, m in dict.fromkeys(list(CHAINS[route]) + P0_EXTRA)   # de-dup, keep order
             if PROVIDERS[p].max_privacy >= privacy and is_free(p, m)]
    est = sum(len(str(m.get("content") or "")) for m in messages) // 4 + max_tokens + (300 if tools else 0)
    for p, model in chain:
        cli = _client(p)
        if cli is None:
            continue
        avail = _available_models(p)
        if avail is not None and model not in avail and p != "zai":
            continue
        if not _gate_ok(p, model, est):
            errors.append(f"{p}/{model}: gated")
            continue
        kwargs = dict(model=model, messages=messages, max_tokens=max_tokens, temperature=temperature)
        extra = {}
        if "gpt-oss" in model and p in ("groq", "cerebras", "openrouter", "cloudflare"):
            extra["reasoning_effort"] = reasoning  # "low" for voice turns; avoid empty content
        if p == "zai":
            extra["thinking"] = {"type": "disabled"}  # GLM Flash: answer directly (thinking adds seconds)
        if p == "openrouter" and privacy >= 1:
            extra["provider"] = {"data_collection": "deny"}  # personal turns: skip hosts that may train on prompts
        if extra:
            kwargs["extra_body"] = extra
        if schema is not None and (p, model) in STRICT_SCHEMA:
            kwargs["response_format"] = {"type": "json_schema",
                                         "json_schema": {"name": schema_name, "strict": True, "schema": schema}}
        elif json_mode or schema is not None:
            kwargs["response_format"] = {"type": "json_object"}
            if schema is not None:                     # no constrained decoding here: spell the shape out
                hint = "Reply with ONE JSON object matching this JSON Schema exactly (all required keys):\n" + \
                       json.dumps(schema, separators=(",", ":"))[:6000]
                kwargs["messages"] = list(messages) + [{"role": "system", "content": hint}]
        if tools:
            kwargs["tools"], kwargs["tool_choice"] = tools, "auto"
        yield p, model, cli, kwargs, est


def _failed(p: str, model: str, e: Exception, errors: list[str]) -> None:
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


def complete(messages: list[dict], *, route: str = "voice_fast", privacy: int = 1,
             max_tokens: int = 400, temperature: float = 0.6, json_mode: bool = False,
             tools: list[dict] | None = None, schema: dict | None = None, schema_name: str = "out",
             reasoning: str = "low") -> dict:
    """Returns {text, provider, model, ms, tokens_in, tokens_out}. Raises NoProvider if all fail."""
    errors: list[str] = []
    for p, model, cli, kwargs, est in _attempts(messages, route, privacy, max_tokens, temperature, json_mode,
                                                tools, schema, schema_name, reasoning, errors):
        t = time.perf_counter()
        try:
            r = cli.chat.completions.create(**kwargs)
        except Exception as e:
            _failed(p, model, e, errors)
            continue
        msg = r.choices[0].message
        text = _clean((msg.content or "").strip())
        calls = [{"id": c.id, "name": c.function.name, "arguments": c.function.arguments or "{}"}
                 for c in (msg.tool_calls or [])]
        u = r.usage
        tin, tout = (u.prompt_tokens, u.completion_tokens) if u else (est, len(text) // 4)
        _record(p, model, tin, tout)
        if not text and not calls:
            errors.append(f"{p}/{model}: empty")
            continue
        if schema is not None and not _shape_ok(text, schema):
            errors.append(f"{p}/{model}: wrong JSON shape")
            continue
        return {"text": text, "tool_calls": calls, "provider": p, "model": model,
                "ms": (time.perf_counter() - t) * 1000, "tokens_in": tin, "tokens_out": tout}
    raise NoProvider("; ".join(errors) or "no API keys configured (.env)")


def stream(messages: list[dict], *, route: str = "voice_fast", privacy: int = 1, max_tokens: int = 400,
           temperature: float = 0.6, reasoning: str = "low", info: dict | None = None) -> Iterator[str]:
    """Yield reply text as it arrives (same chain, gates and fallbacks as complete()).

    Falls back to the next provider only before the first token; a mid-stream drop keeps what was said.
    `info` (if given) is filled with provider, model, first_ms, ms, text. Raises NoProvider if all fail.
    """
    info = info if info is not None else {}
    errors: list[str] = []
    for p, model, cli, kwargs, est in _attempts(messages, route, privacy, max_tokens, temperature, False,
                                                None, None, "out", reasoning, errors):
        t = time.perf_counter()
        parts: list[str] = []
        if p == "cloudflare":                      # its gpt-oss stream can carry channel tokens: take it whole
            try:
                r = cli.chat.completions.create(**kwargs)
            except Exception as e:
                _failed(p, model, e, errors)
                continue
            text = _clean((r.choices[0].message.content or "").strip())
            if text:
                parts.append(text)
                info["first_ms"] = (time.perf_counter() - t) * 1000
                yield text
        else:
            try:
                for ch in cli.chat.completions.create(**kwargs, stream=True):
                    d = ch.choices[0].delta.content if ch.choices else None
                    if d:
                        if not parts:
                            info["first_ms"] = (time.perf_counter() - t) * 1000
                        parts.append(d)
                        yield d
            except Exception as e:
                if not parts:
                    _failed(p, model, e, errors)
                    continue
                errors.append(f"{p}/{model}: dropped mid-reply ({type(e).__name__})")
        text = "".join(parts).strip()
        _record(p, model, est - max_tokens, len(text) // 4)
        if not text:
            errors.append(f"{p}/{model}: empty")
            continue
        info.update(text=text, provider=p, model=model, ms=(time.perf_counter() - t) * 1000,
                    tokens_in=est - max_tokens, tokens_out=len(text) // 4)
        return
    raise NoProvider("; ".join(errors) or "no API keys configured (.env)")


WARM_GAP_S = 20.0                 # at most one warm-up per 20 s (he starts talking many times a minute)
_warm_lock = threading.Lock()
_warm_at = -1e9
_warm_busy = False


def warm(route: str = "voice_fast", *, min_gap_s: float = WARM_GAP_S) -> bool:
    """Open connections + fetch model lists now, so the first real reply doesn't pay TLS/handshake (~0.3–0.6 s).
    Called at start-up, on wake and when his speech starts (Wispr fires GET /warmup on the first audio chunk, D29).
    Cheap and de-duplicated: never two at once, at most one per `min_gap_s`; returns True if it started one.
    After the first call it keeps the first voice provider's TLS connection hot with one GET /models (no tokens)."""
    global _warm_at, _warm_busy
    now = time.monotonic()
    with _warm_lock:
        if _warm_busy or now - _warm_at < min_gap_s:
            return False
        _warm_busy, _warm_at = True, now
    threading.Thread(target=_warm_job, args=(route,), daemon=True).start()
    return True


def _warm_job(route: str) -> None:
    global _warm_busy
    try:
        first = next((p for p, m in CHAINS.get(route, []) if is_free(p, m) and _client(p) is not None), None)
        for p in PROVIDERS:
            if p != first and p not in _models and _client(p) is not None:
                threading.Thread(target=_available_models, args=(p,), daemon=True).start()
        if first is None:
            return
        if first not in _models:
            _available_models(first)                 # the first fetch is the warm-up
        else:
            try:
                _client(first).with_options(timeout=5).models.list()   # reuses the pooled connection → stays hot
            except Exception:
                pass
    finally:
        _warm_busy = False


def status() -> list[dict]:
    out = []
    for p in PROVIDERS:
        ready = bool(CFG.keys.get(p)) and ("{account}" not in PROVIDERS[p].base_url or bool(CFG.keys.get(p + "_account")))
        out.append({"provider": p, "key": ready, "personal": PROVIDERS[p].max_privacy >= 1})
    return out
