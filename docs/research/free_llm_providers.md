# Free LLM providers for Stiti's "mouth" (research, 2026-11-10)

**Question:** Which free cloud LLM APIs should Stiti's router use? The brain is local (D8), so the LLM only turns a
≤1,500-token briefing into words, and must be: free with no card, fast (voice target < 1 s to first audio),
OpenAI-compatible, and safe for personal (P1) context (no training on API data). Decision: **D17**.

## Live measurements (this Mac, 2026-11-10, streaming, first token / total, one short friendly reply)
| Provider / model | First token | Total | Note |
|---|---|---|---|
| Groq `qwen/qwen3.8-27b` | **192 ms** (147 ms warm) | 308 ms | best for voice |
| Groq `openai/gpt-oss-120b` | 508 ms | 510 ms | strict JSON ✓ (tutor planner test passed, 633 ms) |
| Groq `openai/gpt-oss-20b` | 1,094 ms | 1,108 ms | reasoning tokens delay first text |
| OpenRouter `nvidia/nemotron-3-ultra-550b-a55b:free` | 1,902 ms | 1,988 ms | **404 with `data_collection: deny`** → P0 only in practice |
| OpenRouter `google/gemma-4-31b-it:free` | — | — | 429 (shared free pool busy) |
| OpenRouter `nvidia/nemotron-3.5-lightning:free` | — | 2,507 ms | empty reply |
| Gemini `gemini-flash-lite-latest` | 2,407 ms | 2,408 ms | P0 only (free tier may train) |
| Gemini `gemini-3.5-flash-lite` | 4,987 ms | 5,061 ms | too slow for voice |

Found while probing: OpenRouter removed `openai/gpt-oss-20b:free` (it was in our chains), and Gemini's `/models`
returns IDs prefixed `models/`, so the router silently skipped Gemini. Both fixed.

## Comparison (≥10 providers/architectures)
| # | Provider | Free deal (no card) | Good models | Speed | Trains on API data? | Fits Stiti? |
|---|---|---|---|---|---|---|
| 1 | **Groq** | 30 RPM, ~1,000 RPD/model, TPM caps | Qwen3.8-27B, gpt-oss-20b/120b | fastest (LPU) | No | ✅ primary, P1 |
| 2 | **Z.ai (Zhipu GLM)** | GLM-4.7-Flash, GLM-4.5-Flash, GLM-4.6V-Flash priced $0; 1 concurrent request | GLM-4.7-Flash (30B MoE) | good | No for API (per their terms, verify in console) | ✅ add, P1 backup + night jobs |
| 3 | **Cloudflare Workers AI** | 10,000 neurons/day, OpenAI-compatible `/ai/v1` | gpt-oss-120b, Llama-3.3-70B, Qwen coder | good, edge | No (customer content not used for training) | ✅ add, P1 backup |
| 4 | **OpenRouter** | 20 RPM, 50 RPD on `:free` | Nemotron Ultra, Gemma 4 | 1–2 s | Some free hosts may train; `data_collection: deny` filters them | ✅ keep, mostly P0 |
| 5 | **NVIDIA NIM (build.nvidia.com)** | ~40 RPM, "prototyping" terms | DeepSeek, Kimi, Qwen3, GLM, gpt-oss (80–160 models) | variable, slow at peak | evaluation terms, unclear | ✅ add, **P0 only** |
| 6 | **Google Gemini** | AI Studio free quota | Gemini Flash / Flash-Lite | 2–5 s measured | **Yes** on unpaid tier | ✅ keep, P0 only |
| 7 | Mistral La Plateforme | Experiment plan, needs phone verification | Mistral Small/Large, Codestral | ok | Yes unless you opt out | 🟡 optional (opt out first) |
| 8 | Cerebras | **card required since 2026-07-21** ($5 trial credit) | gpt-oss-120b, Qwen | very fast | No | ⛔ not free any more |
| 9 | Hugging Face Inference Providers | free accounts lost monthly credits (2026-10) | 200+ routed | varies | per provider | ⛔ no longer free |
| 10 | GitHub Models | retired 2026-07-30 | — | — | — | ⛔ gone |
| 11 | SambaNova Cloud | 20 RPM but ~20 requests/day | DeepSeek-V3.1, Llama 70B | fast | No | 🟡 too small to matter |
| 12 | SiliconFlow (China) | free Qwen3-8B / GLM-4-9B; free set mainly on .cn (Chinese phone) | small Qwen/GLM | ok | unclear | 🟡 skip (signup barrier) |
| 13 | Alibaba Model Studio (Qwen/DashScope) | trial credits that expire | Qwen Plus/Turbo | ok | unclear | 🟡 trial, not permanent |
| 14 | Moonshot (Kimi) | needs a $1 top-up | Kimi K2 | ok | may train unless agreed | ⛔ not free (Kimi free via NVIDIA instead) |
| 15 | Ollama Cloud | free tier, 1 concurrent, 5-h sessions | GLM-4.7, Kimi K2, gpt-oss | ok | — | ⛔ skipped: Tejmul's "no Ollama" rule |
| 16 | Pollinations / LLM7 / Kilo (anonymous) | anonymous, tiny limits | gpt-oss-20b, misc | slow | unknown | ⛔ never for personal data |
| 17 | Cohere | trial key, 20 RPM | Command-A | ok | terms forbid personal use | ⛔ |

## Design (what we built)
- Each provider gets `max_privacy` (1 = may see personal P1 context, 0 = public questions only). P2 never leaves the
  Mac (unchanged). Chains list every (provider, model); missing keys and model IDs not in the provider's live `/models`
  list are skipped, so adding a key "just works".
- OpenRouter requests for P1 turns send `provider.data_collection = "deny"`.
- Voice chain starts with Groq Qwen3.8-27B (measured fastest). Personal backups: Z.ai GLM-4.7-Flash, Cloudflare
  gpt-oss-120b. P0 extras: NVIDIA (DeepSeek/Kimi/Qwen) and Gemini.

## Sources
- https://github.com/xyzs996/free-llm-api (catalog reviewed 2026-08-22)
- https://wotai.co/blog/best-free-llm-apis (live-probed list)
- https://www.developersdigest.tech/models/free-api (free tiers + data terms)
- https://docs.z.ai/guides/overview/pricing (GLM Flash models free)
- https://toolnavs.com/article/1100-zai-released-glm-47-flash-weights-and-api-free-tier-1-concurrency-and-launched-f
- https://developers.cloudflare.com/workers-ai/platform/pricing/ (10,000 neurons/day free)
- https://news.creeta.com/en/nvidia-nim-free-tier-limits-2026/ · https://forums.developer.nvidia.com/t/is-nim-free/369368
- https://ai.google.dev/gemini-api/docs/logs-policy · https://simonwillison.net/2024/Oct/17/gemini-terms-of-service
- https://help.mistral.ai/en/articles/455206-how-can-i-try-the-api-for-free-with-the-experiment-plan ·
  https://help.mistral.ai/en/articles/455207
- https://www.usagepricing.com/blueprint/activity/cerebras-2026-07-21-free-tier-credit-trial
- https://www.usagepricing.com/blueprint/activity/hugging-face-2026-10-15-free-inference-credits-removed
- https://openrouter.ai/docs/guides/privacy/logging · https://www.truefoundry.com/blog/openrouter-free-models-whats-actually-free-and-what-it-costs-you
- https://www.morphllm.com/llm-api (Kimi has no free tier)
