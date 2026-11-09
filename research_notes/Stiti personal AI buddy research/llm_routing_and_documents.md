# LLM Routing (free providers + local models) and Local Document Intelligence for Stiti (8 GB M2, zero cost, Postgres + pgvector)

Research date: 2026-11-10. Free-tier limits change often; every limit below carries the date or "as-of" of its source. Items marked "(not re-verified this session)" come from well-known primary repos/papers whose link is given, but whose current details I did not re-fetch. Treat them as leads, not confirmed facts.

---

## 1. LLM routing / gateway: LiteLLM vs alternatives, and routing research

### Takeaway
LiteLLM's Router covers almost everything Stiti needs: ordered fallbacks, 429 cooldowns, per-deployment RPM/TPM/RPD/TPD limits, retries and caching. But on **March 24, 2026** LiteLLM's PyPI package was hit by a supply-chain attack: versions **1.82.7 and 1.82.8** shipped a credential stealer. If it is used, pin **>=1.83.0** with hash-checking, or ≤1.82.6. For a single-user voice buddy, a **thin custom router of about 150 lines**, which can optionally reuse the LiteLLM *SDK* Router in-process with no proxy server, is the best fit. Learned routers such as RouteLLM, Arch-Router and MixLLM add RAM and complexity, and the independent benchmarks (RouterBench, LLMRouterBench) show they often barely beat simple baselines.

### Cited Findings
**LiteLLM features (official docs, fetched 2026-11-10)**
- `routing_strategy` options: `simple-shuffle` (the docs call it "Default and Recommended for Production"), `least-busy`, `usage-based-routing`, `latency-based-routing` and `cost-based-routing`. The docs advise against usage-based routing in production because of Redis overhead. — [LiteLLM Routing docs](https://docs.litellm.ai/docs/routing)
- Per-deployment `rpm`, `tpm`, `weight`, plus `rpd`, `tpd` and `daily_reset_time` for daily limits, enforced with `enforce_model_rate_limits`. This maps directly onto free-tier daily quotas. — [LiteLLM Routing docs](https://docs.litellm.ai/docs/routing)
- Fallbacks: ordered deployments (`order`), `context_window_fallbacks`, content-policy fallbacks, and `enable_weighted_failover`. — [LiteLLM Routing docs](https://docs.litellm.ai/docs/routing)
- Cooldowns: without `allowed_fails`, a single 429 (and 401/404/408) cools the deployment immediately, for about 5 s by default. Related settings are `allowed_fails`, `cooldown_time`, `allowed_fails_policy` and `disable_cooldowns`. — [LiteLLM Routing docs](https://docs.litellm.ai/docs/routing)
- Retries: `num_retries`, `retry_after` and `retry_policy` (e.g. `RateLimitErrorRetries`). Rate-limit errors back off exponentially. — [LiteLLM Routing docs](https://docs.litellm.ai/docs/routing)
- Caching: `cache_responses`, with Redis recommended and in-memory caching for local testing. `enable_pre_call_checks` filters out deployments whose context window is too small. — [LiteLLM Routing docs](https://docs.litellm.ai/docs/routing)

**LiteLLM security incident (March 2026)**
- PyPI **v1.82.7 and v1.82.8** were malicious and live for about 40 minutes on 2026-03-24 before PyPI quarantined them. v1.82.8 added a `litellm_init.pth` file, which runs on every Python start. The payload stole env vars, SSH keys, AWS/GCP/Azure credentials, Kubernetes tokens and DB passwords, and sent them to `models.litellm.cloud`; `checkmarx[.]zone` is a second exfiltration domain. The official proxy Docker image was not affected. — [LiteLLM security advisory](https://docs.litellm.ai/blog/security-update-march-2026)
- Root cause per LiteLLM: a compromised Trivy dependency in its CI/CD scanning, which is part of the broader TeamPCP campaign. Safe versions are **v1.83.0**, rebuilt on the "CI/CD v2" pipeline, and the audited **v1.78.0–v1.82.6**. — [LiteLLM advisory](https://docs.litellm.ai/blog/security-update-march-2026); [JFrog](https://research.jfrog.com/post/litellm-compromised-teampcp/); [HiddenLayer](https://www.hiddenlayer.com/research/litellm-supply-chain-attack)
- Reported scale: about 95M monthly downloads; downstream projects such as DSPy and CrewAI were exposed. — [search summary of NetSPI / Xygeni / others](https://www.netspi.com/blog/executive-blog/ai-ml-pentesting/litellm-supply-chain-compromise/) (secondary)

**Alternatives and research: comparison table (≥10)**

| Name | Link | Year | Mechanism | Strengths | Weaknesses | Fits 8 GB M2 / free? |
|---|---|---|---|---|---|---|
| LiteLLM (SDK Router / Proxy) | [docs](https://docs.litellm.ai/docs/routing), [repo](https://github.com/BerriAI/litellm) | 2023– | Unified OpenAI-format client for 100+ providers; Router adds fallbacks, cooldowns, RPM/RPD limits, caching | Most complete feature set; per-day limits match free tiers | March 2026 supply-chain compromise; heavy dependency tree; the proxy needs Postgres/Redis for advanced features | SDK in-process: yes. Proxy: workable but wasteful for one user. MIT core, free |
| Portkey AI Gateway (OSS) | [repo](https://github.com/Portkey-AI/gateway) | 2024– | Node/TS gateway; config-driven fallbacks, retries, load balancing | Light; strong fallback/retry config; per one comparison the core gateway was open-sourced in 2026 | Observability features are mostly in the paid cloud product; another runtime (Node) to run | Yes, small. Free OSS — [comparison](https://llmgateway.io/blog/litellm-alternatives) |
| Bifrost (Maxim AI) | [repo](https://github.com/maximhq/bifrost) | 2025– | Go gateway, OpenAI-compatible, fallbacks, MCP gateway | Fast and low-overhead per its vendor | Rankings come from the vendor (Maxim), so they are biased; reported growth from about 2k to 6.6k stars — [Maxim](https://getmaxim.ai/articles/top-litellm-alternatives-in-2026/) | Yes. Free OSS |
| any-llm / any-llm-gateway / Otari (Mozilla.ai) | [blog](https://blog.mozilla.ai/control-llm-spend-and-access-with-any-llm-gateway/), [docs](https://docs.mozilla.ai/any-llm/gateway/overview/) | 2025– | Thin SDK built on official provider SDKs; FastAPI gateway adds budgets, virtual keys and analytics | Small surface; uses official SDKs | Less routing logic (fallback/cooldown) than LiteLLM; possibly rebranded as "Otari", and the relationship is unclear | Yes. Free OSS |
| OpenRouter (hosted) + Auto Router | [limits](https://openrouter.ai/docs/api/reference/limits) | 2023– | Hosted aggregator; `:free` models; provider fallback is done server-side | One key for many free models; no infrastructure | Free tier is 20 RPM and 50 RPD (1,000 RPD after ≥$10 lifetime credits); Auto Router picks mostly paid models (not re-verified this session) | Zero RAM. Free with caps |
| RouteLLM (LMSYS) | [paper](https://arxiv.org/abs/2406.18665), [repo](https://github.com/lm-sys/RouteLLM) | 2024 | Strong/weak binary router trained on Chatbot Arena preferences (matrix factorization, BERT, causal-LLM classifiers) | Principled cost/quality threshold | Trained for GPT-4 vs Mixtral pairs, so it does not transfer cleanly to new pairs; scores 48.1 vs 66.9 for the top entry on RouterArena — [RouterArena](https://alphaxiv.org/abs/2510.00202) | MF router is small; BERT router is about 0.5 GB. Free |
| Arch-Router-1.5B (Katanemo) | [paper](https://arxiv.org/html/2506.16655v1), [HF GGUF](https://huggingface.co/katanemo/Arch-Router-1.5B.gguf) | 2025 | 1.5B Qwen2.5-based model maps prompts to user-written route policies (domain/action) | Claims 93.17% routing accuracy, +7.71% vs GPT-4o/Claude 3.7; routes can be added without retraining | Katanemo research license (not OSI); 1.5B costs about 1 GB RAM plus latency on every turn | Tight on an 8 GB machine already running a 4B LLM plus voice. Free weights |
| FrugalGPT | [arXiv 2305.05176](https://arxiv.org/abs/2305.05176) | 2023 | LLM cascade: call cheap models first and escalate when a scorer judges the answer weak | Reported up to 98% cost cut at GPT-4 accuracy — [Stanford review blog](https://web.stanford.edu/~shuhuiq/blog/review-routing-cascades.html) | A cascade adds a full extra generation to latency, which hurts voice | Concept only |
| Hybrid LLM (Ding et al.) | [arXiv 2404.14618](https://arxiv.org/abs/2404.14618) | 2024 | Router predicts the query difficulty gap between a small and a large model; tunable threshold | Designed for an edge-small vs cloud-large setup, i.e. Stiti's case | Needs a trained router on your own data | Concept only |
| AutoMix | [arXiv 2310.12963](https://arxiv.org/abs/2310.12963) | 2023 | Small model answers, self-verifies, and a POMDP decides whether to escalate | No router training needed | Self-verification costs an extra small-model pass; method details not re-verified this session | Concept only |
| MixLLM | [arXiv 2502.18482](https://arxiv.org/abs/2502.18482) | 2025 | Contextual-bandit routing using quality, cost and latency | Adapts online | Gains shrink under distribution shift — [review](https://web.stanford.edu/~shuhuiq/blog/review-routing-cascades.html) | Concept only |
| RouterBench | [arXiv 2403.12031](https://arxiv.org/html/2403.12031v2) | 2024 | Benchmark with 405k inference outcomes | Neutral evaluation | Finding as cited: "none of the routing algorithms significantly outperform the baseline Zero router" — [review](https://web.stanford.edu/~shuhuiq/blog/review-routing-cascades.html) | n/a |
| LLMRouterBench | [arXiv 2601.07206](https://web3.arxiv.org/pdf/2601.07206) | 2026 | 400K instances, 21 datasets, 33 models, 10 baselines | Most recent large evaluation | Finds many routing methods perform similarly | n/a |
| Semantic Router (aurelio-labs) | [repo](https://github.com/aurelio-labs/semantic-router) | 2023– | Embedding similarity against example utterances per route | Millisecond decisions; reuses the embedding model already loaded | Needs example utterances per route (not re-verified this session) | Yes, with only the embedder resident. Free OSS |
| Custom rule-based router | — | — | if/else on intent, length, tool needs, privacy flag, quota state | Zero dependencies and fully auditable, which matters after the LiteLLM incident; this is what RouterBench's "Zero router" baseline effectively is | You maintain the quota and cooldown code yourself | Yes, no extra RAM |

### Inferences
- **Recommended design ("Stiti Router"):**
  1. **Privacy gate first.** Any turn that touches raw memories, documents or personal data defaults to **local**. Cloud calls get a minimized or redacted context, because Gemini and Mistral free tiers may train on or review data (see section 2).
  2. **Rule-plus-embedding router.** Route classes are: chit-chat, short answers and memory recall → local 4B; long reasoning, multi-step tool calls or long context → cloud. Use Semantic-Router-style cosine matching with the already-loaded embedding model. No LLM router model is added, which saves RAM and latency.
  3. **Cloud provider chain**, ordered by voice suitability (TTFT, tool calling) and privacy: **Groq → Cerebras → OpenRouter :free → Mistral (training opted out) → Gemini Flash-Lite (non-sensitive only)**. Each provider gets its RPM/RPD budget, cooldown on 429 using `Retry-After`, and an in-Postgres usage counter (or LiteLLM `rpd` and `enforce_model_rate_limits`).
  4. **Last resort is the local model**, which always answers. The voice UX never fails; it just degrades in quality.
  5. **Cascade only off the hot path.** If the local answer is low-confidence (e.g. a tool-call JSON parse failure), say a filler phrase while re-asking the cloud, AutoMix-style.
- If LiteLLM is used, use the **SDK `Router` only** (no proxy), pin `litellm==1.83.x` with `--require-hashes`, and keep API keys out of global env where possible. The `.pth` attack vector means simply having it installed is the risk.
- The research consensus from RouterBench, LLMRouterBench and the Stanford review is that learned routers give marginal gains over simple baselines. For a single-user app, the extra complexity is not justified.

### Gaps
- No source found for LiteLLM SDK or proxy **RAM footprint** on macOS. The coordinator should measure it, e.g. `python -c "import litellm"` RSS.
- OpenRouter Auto Router's current backend (Not Diamond) and whether it ever selects `:free` models was not verified.
- Whether any independent TTFT benchmark compares Groq, Cerebras and Gemini Flash-Lite in late 2026: a blog claims Groq about 120 ms and Cerebras about 150 ms TTFT, but unsourced — [blog](https://www.kunalganglani.com/blog/llm-latency-benchmark-optimization). Artificial Analysis is the recommended live source — [methodology](https://artificialanalysis.ai/methodology/performance-benchmarking).

---

## 2. Free LLM providers (as of Nov 2026): exact limits, privacy, tool calling, TTFT

### Takeaway
For voice, the best free cloud tiers are **Groq** (30 RPM / 1K RPD / 200K TPD on `openai/gpt-oss-20b|120b` and `qwen/qwen3.8-27b`, LPU low latency) and **Cerebras** (5 RPM, 1M TPD on `gpt-oss-120b` / `qwen-3.8-27b`). **Gemini's free tier has been cut hard**: reportedly 20 RPD on Flash and about 500 RPD on Flash-Lite. Google also uses free-tier data to improve products, with human review, outside the EU/UK/CH. **GitHub Models was retired on 2026-07-30**. OpenRouter `:free` gives only 50 RPD without $10 in lifetime credits.

### Cited Findings

| Provider | Link | Free limits (date) | Models of note | Data / training on free tier | Tool calling / streaming / TTFT | Fit for Stiti |
|---|---|---|---|---|---|---|
| **Groq** | [rate limits](https://console.groq.com/docs/rate-limits) | Base table (fetched 2026-11-10, labeled "Developer plan"; the free-plan tab was not rendered): `gpt-oss-120b`/`gpt-oss-20b`/`qwen/qwen3.8-27b` at **30 RPM, 1K RPD, 8K TPM, 200K TPD**; whisper-large-v3(-turbo) at 20 RPM / 2K RPD | gpt-oss, Qwen3.8-27B, Whisper, Orpheus TTS | OpenRouter's comparison says no training — [OpenRouter blog](https://openrouter.ai/blog/tutorials/free-llm-apis-compared/) | OpenAI-compatible, streaming, tool use; about 120 ms TTFT claimed (unsourced blog) — [blog](https://www.kunalganglani.com/blog/llm-latency-benchmark-optimization) | **Primary cloud for voice** |
| **Cerebras** | [rate limits](https://inference-docs.cerebras.ai/support/rate-limits) | Free trial (fetched 2026-11-10): `gpt-oss-120b`, `qwen-3.8-27b` at **5 RPM, 30K uncached TPM / 90K total TPM, 1M TPH, 1M TPD** | gpt-oss-120b, Qwen3.8-27B | "No" training per [OpenRouter blog](https://openrouter.ai/blog/tutorials/free-llm-apis-compared/) | Very high throughput; about 150 ms TTFT claimed (unsourced) | Secondary cloud; 5 RPM is low for chatty voice |
| **Google AI Studio (Gemini)** | [rate limits](https://aistudio.google.com/docs/rate-limits), [terms](https://aistudio.google.com/docs/terms) | Official page no longer lists free numbers ("View your active rate limits in AI Studio"). Third-party (Oct 2026): **Flash 5 RPM / 20 RPD; Flash-Lite 10–15 RPM / 500 RPD**; Pro has no free tier — [imisofts](https://imisofts.com/blog/gemini-api-free-tier-limits/), [scriptbyai](https://www.scriptbyai.com/gemini-api-free-tier-limits/). Conflicting report of about 1,500 RPD — [klymentiev](https://klymentiev.com/blog/gemini-api-free-tier). Limits are per project | Gemini 3.x Flash / Flash-Lite (names vary by source) | **Terms: "Google uses the content you submit… to provide, improve, and develop" products; "human reviewers may read, annotate, and process your API input and output"; "Do not submit sensitive, confidential, or personal information to the Unpaid Services."** EU/UK/CH users get paid-tier (no improvement) treatment — [terms](https://aistudio.google.com/docs/terms) | Strong tool calling and streaming | Non-personal queries only, unless the user is in the EU/UK/CH |
| **OpenRouter `:free`** | [limits](https://openrouter.ai/docs/api/reference/limits), [privacy](https://openrouter.ai/docs/guides/privacy/data-collection) | **20 RPM; 50 RPD if <10 credits purchased lifetime, 1,000 RPD at ≥10 credits** (fetched 2026-11-10) | 20+ free models, e.g. gpt-oss-120b, Llama 3.3 70B, Qwen3 Coder — [OpenRouter blog, upd. 2026-09-24](https://openrouter.ai/blog/tutorials/free-llm-apis-compared/); Nemotron 3 free variants — [awesome-freellm-apis](https://github.com/open-free-llm-api/awesome-freellm-apis) | OpenRouter stores no prompts unless you opt in; it documents which providers may train; "ZDR only" setting available — [privacy](https://openrouter.ai/docs/guides/privacy/data-collection). Free endpoints' upstream providers may log (check per model) | Depends on the upstream model | Good wide fallback; $10 one-time spend is not zero cost |
| **Mistral La Plateforme (Experiment / free)** | [help: training](https://help.mistral.ai/en/articles/323757-do-you-use-my-user-data-to-train-your-artificial-intelligence-models) | Third-party: about **1 RPS, 500K TPM, 1B tokens/month** per model; official limits are only in the console — [benchlm](https://benchlm.ai/md/free-tier/mistral.md) | Mistral Small/Medium, Codestral | **Free-tier data is used for training by default; opt-out available.** Opt-out is not zero retention. Phone verification required — [Mistral help](https://help.mistral.ai/en/articles/323757-do-you-use-my-user-data-to-train-your-artificial-intelligence-models) | Function calling supported | Usable fallback after opting out |
| **GitHub Models** | [changelog](https://github.blog/changelog/2026-07-01-github-models-is-being-fully-retired-on-july-30-2026) | **Retired 2026-07-30**; closed to new customers 2026-06-16 — [changelog](https://github.blog/changelog/2026-06-16-github-models-is-no-longer-available-to-new-customers), [now retired](https://github.blog/changelog/2026-08-09-github-models-is-now-retired/) | — | — | — | **Not available** |
| **Cloudflare Workers AI** | [pricing](https://developers.cloudflare.com/workers-ai/platform/pricing/) | **10,000 Neurons/day**, shared across models, resets 00:00 UTC; requests fail once exhausted on the free plan — [search summary of CF pricing](https://developers.cloudflare.com/workers-ai/platform/pricing/). Estimates range from about 15–25 to 100–500 LLM calls/day (third-party) | Llama 3.3 70B fp8, Mistral 7B, etc. — [awesome-freellm-apis](https://github.com/open-free-llm-api/awesome-freellm-apis) | No training per [OpenRouter blog](https://openrouter.ai/blog/tutorials/free-llm-apis-compared/) | Edge-hosted; some models support function calling | Minor fallback |
| **NVIDIA NIM (build.nvidia.com)** | — | "Up to 40 RPM", phone verification — [awesome-freellm-apis](https://github.com/open-free-llm-api/awesome-freellm-apis); about 1,000/day per [OpenRouter blog](https://openrouter.ai/blog/tutorials/free-llm-apis-compared/) | GLM-5.x, Nemotron, Llama | "No" training per the OpenRouter blog | OpenAI-compatible | Fallback; dev and trial use only |
| **SambaNova** | — | 20 RPM / 20 RPD / 200K TPD — [awesome-freellm-apis](https://github.com/open-free-llm-api/awesome-freellm-apis); OpenRouter blog says a $5 trial credit and a card at signup — conflicting | DeepSeek-V3.x, MiniMax | — | Fast | Too small to rely on |
| **Hugging Face Inference Providers** | — | Credit-metered, no fixed numbers — [awesome-freellm-apis](https://github.com/open-free-llm-api/awesome-freellm-apis) | Many small models | — | Varies | Minor |
| **Together AI** | — | Not covered by either aggregator; I found no confirmed free tier | — | — | — | Gap |
| **Cohere (trial key)** | — | Listed as a free-tier provider without numbers — [OpenRouter blog search summary](https://openrouter.ai/blog/tutorials/free-llm-apis-compared/) | Command models | — | Tool use supported (not re-verified this session) | Minor |

- Aggregator: awesome-freellm-apis, last updated 2026-11-09, lists 446+ free APIs from 31 providers, refreshed daily from freellm.net — [repo](https://github.com/open-free-llm-api/awesome-freellm-apis). The OpenRouter comparison says "Rate limits on free tiers change frequently; verify current numbers before committing" — [OpenRouter blog](https://openrouter.ai/blog/tutorials/free-llm-apis-compared/)
- Qwen3.8-27B (the "Qwen-27B" the user mentioned) is a **27B dense multimodal model, Apache 2.0, released about 2026-08-14 (ApX says 08-05), 262K context** — [datanorth](https://datanorth.ai/news/alibaba-releases-qwen3-8-27b), [ApX](https://apxml.com/models/qwen38-27b). It is free to call via Groq and Cerebras (tables above).

### Inferences
- **Daily free capacity estimate:** Groq gives about 1,000 requests/day per model, and spreading across gpt-oss-20b, gpt-oss-120b and qwen3.8-27b gives about 3,000. Add Cerebras at about 1M tokens/day, Mistral at about 1B tokens/month, and OpenRouter at 50/day. That is well above a single user's voice needs, about 100–500 turns/day. Groq's 200K TPD per model is the binding limit if long memory context is stuffed into prompts, so keep cloud prompts small.
- **Privacy ranking for personal data:** local > Groq ≈ Cerebras (no training per aggregator, but verify ToS) > OpenRouter with ZDR > Mistral (opted out) > Gemini free (reviewed and used, outside the EU).
- For voice TTFT, Groq's LPU and Cerebras's wafer-scale chips are the main reason to use them. Gemini's cut to 20 RPD on Flash makes it unsuitable as a primary.

### Gaps
- Groq's **free-plan** tab content was not rendered. The table fetched is labeled "Developer plan base limits", which most aggregators equate with free (30 RPM / 1K RPD), but the coordinator should confirm in the console.
- I found no official Google page with numeric free-tier limits in Nov 2026; the numbers are third-party.
- No primary ToS fetched for Groq, Cerebras, NVIDIA or SambaNova data retention; the "no training" claims come from OpenRouter's comparison.
- No measured TTFT for each provider's free tier.

---

## 3. Local LLMs on an 8 GB M2 (about 3 GB budget alongside voice)

### Takeaway
**Qwen3.8-27B cannot run.** At Q4 it needs about 15–16 GB for weights alone. Within a 3 GB budget, the candidates are **Qwen3.5-4B (4-bit MLX ≈ 2.5 GB weights, ≈ 3.2–4.2 GB peak; ~25–32 tok/s on M2 8 GB)**, **Gemma 4 E2B (≈ 1.3–1.5 GB quantized, native function calling, audio input)**, and **Qwen3.5-2B** as an ultra-light tool-calling fallback (BFCL-V4 43.6). Use **MLX (mlx-lm / oMLX)**. Ollama on 8 GB Macs falls back to llama.cpp.

### Cited Findings
- Qwen3.8-27B is 27B dense (one source says 27.8B) — [datanorth](https://datanorth.ai/news/alibaba-releases-qwen3-8-27b), [miraflow](https://miraflow.ai/blog/qwen3-8-27b-open-weight-dense-model-local-2026).
- macOS needs 2–3 GB itself, leaving about 5–6 GB for a model. The source advises skipping any 7B+ model at Q4 or higher on 8 GB, and calls 8 GB Macs "getting uncomfortable in 2026" — [InsiderLLM, upd. 2026-07-23](https://insiderllm.com/guides/best-local-llms-mac-2026/)
- **Ollama uses MLX on Apple Silicon only with ≥32 GB; on 8 GB it runs llama.cpp.** MLX is "typically 10–30% faster than llama.cpp" — [InsiderLLM](https://insiderllm.com/guides/best-local-llms-mac-2026/)
- **Measured (oMLX community, base M2 8 GB):** Qwen3.5-4B runs at about 32 tok/s at 1K context, about 30 at 4K and about 18 at 8K, with **peak about 4.2 GB at 4K**. Qwen3-4B-Thinking-2507 runs at about 25 tok/s at 4K with **peak 3.2 GB** — [oMLX benchmarks](https://omlx.ai/benchmarks/hhfwaa55) (search summary across several oMLX entries)
- Qwen3.5 small series (0.8B / 2B / 4B / 9B), released 2026-03-02, Apache 2.0. BFCL-V4 scores: 9B 66.1, 2B 43.6, 0.8B 25.3. 4B TAU2-Bench 79.9 (secondary) — [NYU Shanghai RITS](https://rits.shanghai.nyu.edu/ai/qwen-3-5-small-models-9b-parameters-that-beat-120b/), [DeepInfra card](https://deepinfra.com/Qwen/Qwen3.5-2B)
- Gemma 4 (2026-04-02): E2B and E4B are on-device models with native function calling, structured JSON, system instructions, and audio input up to 30 s. Quantized E2B is about 1.3–1.5 GB and E4B about 2.5 GB; one benchmark lists E2B Q4_0 at 3.2 GB total — [Google blog](https://blog.google/innovation-and-ai/technology/developers-tools/gemma-4/?hl=es), [thekodelab](https://thekodelab.com/en/posts/google-gemma-4/), [tech report](https://huggingface.co/papers/2607.02770.md)
- One source says even Qwen 3.5 9B doesn't reliably pass OpenClaw tool-calling validation at 8 GB, and recommends a cloud fallback for multi-step tool calls — [search summary of 8 GB guides](https://openclawdc.com/blog/best-local-llms-8gb-ram/)

| Model | Link | Year | Size / memory (4-bit) | Speed on base M2 8 GB | Tool calling | Fits 3 GB budget? |
|---|---|---|---|---|---|---|
| Qwen3.8-27B | [ApX](https://apxml.com/models/qwen38-27b) | 2026 | ~15–16 GB weights (inference: 27B × ~4.5 bits) | n/a | Strong (agentic) | **No.** Use via Groq/Cerebras |
| Qwen3.5-9B Q3 | [InsiderLLM](https://insiderllm.com/guides/best-local-llms-mac-2026/) | 2026 | ~4 GB | 10–15 tok/s (community range) | BFCL-V4 66.1 | No |
| **Qwen3.5-4B** | [RITS](https://rits.shanghai.nyu.edu/ai/qwen-3-5-small-models-9b-parameters-that-beat-120b/) | 2026 | ~2.5 GB weights; peak 4.2 GB at 4K ctx | ~32 tok/s (1K), ~30 (4K) measured MLX | TAU2 79.9 (secondary) | **Borderline.** OK at 2K ctx; set KV limits |
| **Qwen3.5-2B** | [DeepInfra](https://deepinfra.com/Qwen/Qwen3.5-2B) | 2026 | ~1.3 GB (inference) | not measured; faster than 4B | BFCL-V4 43.6 | **Yes** |
| Qwen3.5-0.8B | same | 2026 | <1 GB | — | BFCL-V4 25.3 (weak) | Yes, but only for classification |
| **Gemma 4 E2B** | [Google](https://blog.google/innovation-and-ai/technology/developers-tools/gemma-4/?hl=es) | 2026 | ~1.3–1.5 GB quantized | 30–45 tok/s (community range, InsiderLLM) | Native FC + JSON | **Yes, top pick** |
| Gemma 4 E4B | same | 2026 | ~2.5 GB quantized | — | Native FC | Borderline |
| Qwen3-4B-2507 (Instruct/Thinking) | [oMLX](https://omlx.ai/benchmarks/hhfwaa55) | 2025 | peak 3.2 GB | ~25 tok/s at 4K | Good (Qwen3 Hermes-style) | Borderline |
| Phi-4-mini 3.8B | [InsiderLLM](https://insiderllm.com/guides/best-local-llms-mac-2026/) | 2025 | ~2.3 GB | 25–40 tok/s (range) | Function calling supported (not re-verified this session) | Yes |
| Llama 3.2 3B | same | 2024 | ~2 GB | 25–35 tok/s | Basic | Yes, but older |
| SmolLM3-3B | [HF blog](https://huggingface.co/blog/smollm3) | 2025 | ~2 GB | — | Tool calling, dual reasoning mode (not re-verified this session) | Yes |
| Gemma 3n E2B/E4B | [HF](https://huggingface.co/google/gemma-3n-E2B-it) | 2025 | ~2–3 GB | — | Limited | Superseded by Gemma 4 |

Runtimes: **mlx-lm / oMLX** (fastest on Apple Silicon, OpenAI-compatible server), **llama.cpp** (GGUF, grammar-constrained JSON for reliable tool calls), **Ollama** (llama.cpp on 8 GB), and LM Studio (MLX + llama.cpp) — [InsiderLLM](https://insiderllm.com/guides/best-local-llms-mac-2026/).

### Inferences
- **Recommendation:** use **Gemma 4 E2B (4-bit, MLX)** as the always-loaded local brain, about 1.5 GB plus KV, leaving room for STT/TTS and the embedder. Swap to **Qwen3.5-4B 4-bit** when voice models are idle or for better reasoning, with a 2–4K context cap. Use **Qwen3.5-2B** if memory pressure appears. Use llama.cpp grammar / JSON-schema-constrained decoding, or mlx-lm structured output, so tool calls from small models parse reliably.
- Generation at about 25–30 tok/s is faster than speech, which is about 3 tokens/s spoken, so local TTFT (prompt prefill) matters more than throughput. Keep the system prompt short and use prompt or KV caching.
- The user's "local Qwen-27B/4B" should become "cloud Qwen3.8-27B (Groq/Cerebras free) + local 2–4B".

### Gaps
- No measured tool-calling accuracy (BFCL) for Qwen3.5-4B or Gemma 4 E2B specifically.
- No measured MLX tok/s for Gemma 4 E2B on a base M2.
- KV-cache and peak memory with a concurrent voice stack was not measured; it must be tested on-device.

---

## 4. Document parsing (Docling and alternatives) + embeddings + vector store

### Takeaway
Docling (MIT) is a sound default and its HybridChunker fits pgvector well. On an 8 GB M2, use the **standard pipeline with the pypdfium backend** (≈2.5 GB peak per the tech report) and run it **as a batch job when the voice stack is idle**. Use **PyMuPDF4LLM** (fast, about 1.7 s/page on M2) or MarkItDown (0.1 s/page, for Office/HTML) as the quick path. Call Granite-Docling-258M (MLX, about 7–8 s/page) only for hard scans or tables. For embeddings, **Qwen3-Embedding-0.6B** wins on quality (MTEB multilingual 64.33) and **EmbeddingGemma-300M** wins on RAM (about 200–700 MB). **Drop ChromaDB**: pgvector plus Postgres full-text gives hybrid search in the same DB as Stiti's memory engine.

### Cited Findings
**Docling**
- Tech report, M3 Max, 225 pages, OCR off: native backend 1.27–1.34 pages/s with **~6.2 GB peak RSS**; pypdfium backend 2.18–2.45 pages/s with **~2.56 GB peak**. pypdfium is about 40% faster but has worse table recovery — [Docling tech report arXiv 2408.09869](https://alphaxiv.org/overview/2408.09869v5)
- Independent benchmark (Needl.ai, June 2026, one 17-page financial PDF, **local Apple M2 CPU**): Docling took 187.5 s total, about 11 s/page with RapidOCR — [Needl.ai](https://needl.ai/technical-notes/benchmarking-pdf-extraction-tools)
- Granite-Docling-258M (IBM, about Sept 2025) runs at about 7–8 s/page on MLX; SmolDocling-256M about 6.2 s/page on MLX. The MLX backend is 2–3x faster and lighter than Transformers on M1–M4 — [Docling VLM guide](https://www.mintlify.com/docling-project/docling/guides/vlm-models), [Biblicus](https://anthusai.github.io/Biblicus/extractors/vlm-document/docling-granite.html). IBM published no memory or speed numbers — [NAND Research](https://nand-research.com/research-note-ibm-releases-granite-model-for-docling-document-processing/)

**Parser comparison (≥10)**

| Name | Link | Year | Mechanism | Needl.ai composite (rank of 42) / speed on M2 | Strengths | Weaknesses | Fits 8 GB / free? |
|---|---|---|---|---|---|---|---|
| **Docling** (standard) | [repo](https://github.com/docling-project/docling), [report](https://alphaxiv.org/overview/2408.09869v5) | 2024– | Layout model + TableFormer + OCR → DoclingDocument | 0.543 (32nd); ~11 s/page CPU | Table F1 1.00; structured JSON; HybridChunker; MIT | Slow on CPU; 2.5–6 GB peak | Yes, as a batch job with pypdfium backend. Free |
| **Granite-Docling-258M** (VLM) | [IBM](https://ibm.com/new/announcements/granite-docling-end-to-end-document-conversion), [example](https://docling-project.github.io/docling/examples/minimal_vlm_pipeline) | 2025 | End-to-end VLM → DocTags, MLX | ~7–8 s/page MLX | Single tiny model; equations, code | No published RAM | Yes. Apache 2.0 |
| SmolDocling-256M | [VLM guide](https://www.mintlify.com/docling-project/docling/guides/vlm-models) | 2025 | Predecessor VLM | ~6.2 s/page MLX | Low memory | Superseded | Yes |
| **PyMuPDF4LLM** | [repo](https://github.com/pymupdf/RAG) | 2024– | Rule-based PDF → Markdown (MuPDF) | 0.587 (27th); **~1.7 s/page** | Fast; coverage 0.93; good charts score | Weak tables (F1 0.29); **AGPL-3.0** (not re-verified this session) | Yes. Free (AGPL is fine for personal use) |
| **MarkItDown** (Microsoft) | [repo](https://github.com/microsoft/markitdown) | 2024– | Converters for Office/HTML/PDF → Markdown | 0.503 (33rd); **0.11 s/page** | DOCX/PPTX/XLSX/HTML/EPUB; MIT | Poor PDF tables (F1 0.14) | Yes. Free |
| **Marker** | [repo](https://github.com/datalab-to/marker) | 2023– | Surya OCR/layout models + optional LLM | 0.594 (26th); **~108 s/page CPU** on M2 (includes model download) | Good text similarity 0.74 | Very slow on CPU; GPL code plus restricted model license (not re-verified this session) | Marginal |
| **MinerU** | [repo](https://github.com/opendatalab/MinerU) | 2024– | Pipeline + MinerU2.5 VLM | 0.546 (31st) | Strong on academic papers (OmniDocBench) — [OmniDocBench](https://arxiv.org/abs/2412.07626) | Coverage 0.54; heavy; AGPL (not re-verified this session) | Marginal |
| olmOCR-2-7B | [repo](https://github.com/allenai/olmocr) | 2025 | 7B VLM OCR | **0.770 (11th)**; 30 s/page on L40S GPU | Best quality of these | 7B is too big for 8 GB | **No** (cloud GPU only) |
| PaddleOCR-VL | [repo](https://github.com/PaddlePaddle/PaddleOCR) | 2025 | 0.9B VLM | 0.614 (24th); 44.5 s/page on T4 | Table structure 0.96 | GPU-oriented | Marginal |
| Unstructured (OSS) | [repo](https://github.com/Unstructured-IO/unstructured) | 2022– | Partitioners for 25+ formats; email (.eml/.msg) | not in Needl.ai scores | Broad formats incl. email; Apache 2.0 | Heavy deps; quality varies | Yes |
| Apple Vision OCR (via `ocrmac` / Live Text) | [ocrmac](https://github.com/straussmaximilian/ocrmac) | — | On-device Neural Engine OCR | — | Built in, fast, zero RAM cost to Stiti | Text only, no layout (not re-verified this session) | Yes |

**Embeddings (MLX-capable)**

| Model | Params | MTEB | Context | Memory | Notes |
|---|---|---|---|---|---|
| **Qwen3-Embedding-0.6B** | 0.6B | Multilingual v2 64.33; Code 75.41; English v2 70.47 | 32K | Ollama pre-allocated about 5.8 GB due to a full 32K KV cache, so cap the context | Best quality small embedder — [SurrealDB comparison](https://surrealdb.com/blog/embedding-models-comparison), [regolo](https://regolo.ai/embeddinggemma-2-vs-qwen3-embedding-benchmarks.md) |
| **EmbeddingGemma-300M** | 308M | Multilingual v2 61.15; Code 68.76 | 2K | <200 MB quantized (claimed) to 685 MB measured | Matryoshka dimensions (768→128); fastest — [paper](https://alphaxiv.org/abs/2509.20354), [SurrealDB](https://surrealdb.com/blog/embedding-models-comparison) |
| EmbeddingGemma 2 (~270M) | ~270M | Multilingual 61.36 / English 68.46 | 8K | 542 MB at 8K | Secondary report — [regolo](https://regolo.ai/embeddinggemma-2-vs-qwen3-embedding-benchmarks.md) |
| bge-m3 | 568M | — (not re-verified this session) | 8K | ~1.1 GB fp16 | Dense + sparse + multi-vector in one model — [HF](https://huggingface.co/BAAI/bge-m3) |
| nomic-embed-text-v1.5 | 137M | — | 8K | ~0.3 GB | Matryoshka — [HF](https://huggingface.co/nomic-ai/nomic-embed-text-v1.5) |
| Runtime: **mlx-embeddings** | — | — | — | — | MLX port for BERT/XLM-R/Gemma-family embedders — [repo](https://github.com/Blaizzy/mlx-embeddings) (support for specific models not re-verified this session) |

**Vector store**
- pgvector offers full hybrid search (Postgres FTS plus vector in one SQL query) and HNSW/IVFFlat indexes; pgvectorscale adds StreamingDiskANN. Chroma is dense-only with partial hybrid support and post-filters metadata after ANN, which can hurt recall — [modern-datatools](https://www.modern-datatools.com/compare/chromadb-vs-pgvector), [dev.to shootout](https://dev.to/ayinedjimi-consultants/chromadb-vs-qdrant-vs-weaviate-vs-pgvector-vector-database-shootout-2026-14n7). Chroma's advantage is zero-setup in-process use — [pecollective](https://pecollective-com.pages.dev/tools/chroma-vs-pgvector/). Most of these sources are vendor or affiliate content.

### Inferences
- **Recommended pipeline:** a file watcher puts work on a queue in a Postgres table. A router by type sends:
  - DOCX/PPTX/XLSX/HTML/EPUB → MarkItDown
  - digital PDF → PyMuPDF4LLM, or Docling with pypdfium when a table-density heuristic fires
  - scanned PDF or image → Apple Vision OCR, or Granite-Docling MLX for complex layouts
  
  Output goes to Markdown or DoclingDocument, then to Docling HybridChunker (token-aware, about 512 tokens, heading breadcrumbs). Chunks get a header context (section 5), are embedded with **Qwen3-Embedding-0.6B (context capped at 2K)**, or EmbeddingGemma-300M if RAM is tight, and land in `pgvector` (HNSW, `halfvec` to save space) plus a `tsvector` column. Retrieval is hybrid with RRF. Ingest runs only when the voice stack is idle or on AC power.
- **Drop ChromaDB.** It duplicates storage, cannot join with Stiti's memory or KG tables, adds another process and RAM, and has weaker hybrid search. Keep Chroma only if a throwaway prototype is needed before Postgres exists.
- "MLX-Embed" in the user's suggestion maps to mlx-embeddings plus one of the models above.

### Gaps
- Granite-Docling peak RAM on an 8 GB M2 is unmeasured.
- Licenses for Marker, MinerU and PyMuPDF were not re-verified this session; the Needl.ai page does not state them.
- MTEB retrieval-only sub-scores for these embedders were not fetched.

---

## 5. Chunking strategies

### Takeaway
No single strategy wins across benchmarks. **Structure-aware chunking (Docling HybridChunker or a recursive splitter) plus prepended contextual headers** is the robust default. Anthropic-style **Contextual Retrieval** gave the largest reported gains: retrieval failure down 35%, 49% with BM25, 67% with reranking. It can be done for free by generating context with the *local* small model offline at ingest time. **Late chunking** is the cheap alternative but needs a long-context embedder.

### Cited Findings

| Strategy | Link | Year | Mechanism | Evidence | Strengths | Weaknesses | 8 GB / free? |
|---|---|---|---|---|---|---|---|
| Fixed-size token windows (+overlap) | — | — | N tokens with overlap | Baseline | Trivial | Splits meaning | Yes |
| Recursive character/structure splitting | [denser.ai](https://denser.ai/blog/rag-chunking-strategies/) | — | Split on headings → paragraphs → sentences | FloTorch/Vecta: **69% end-to-end accuracy vs 54% for semantic chunking** (secondary) | Robust default | Ignores semantics | Yes |
| Semantic chunking | [denser.ai](https://denser.ai/blog/rag-chunking-strategies/) | 2023– | Split where embedding similarity drops | Higher recall (92% vs 88%) but lower end-to-end accuracy | Coherent topics | Fragment sizes vary; costs embedding passes | Yes |
| **Contextual Retrieval** (Anthropic) | [Anthropic](https://www.anthropic.com/news/contextual-retrieval) | 2024-09 | LLM writes 50–100 tokens of context per chunk; contextual embeddings + contextual BM25 + rerank | Failure rate 5.7% → 3.7% (−35%), → 2.9% with BM25 (−49%), → 1.9% with rerank (−67%); top-20 retrieval; $1.02/M doc tokens with caching | Biggest measured gain | One LLM call per chunk | Yes, if the local 2–4B model runs it offline |
| **Late chunking** (Jina) | [arXiv 2409.04701](https://arxiv.org/abs/2409.04701) | 2024 | Embed the whole doc with a long-context model, then mean-pool tokens per chunk | Redis 2026: ~3% relative gain vs naive on BEIR long docs (secondary) — [summary](https://arxiv.org/abs/2504.19754) | No LLM cost | Needs a long-context embedder (Qwen3-Emb 32K is OK, EmbeddingGemma 2K too short) and more RAM | Partial |
| Late chunking vs contextual retrieval, head-to-head | [arXiv 2504.19754](https://arxiv.org/pdf/2504.19754) | 2025 | Comparison study | Contextual retrieval gives better coherence and accuracy but is costly; late chunking is cheaper but loses some relevance. CR was tested on only 20% of NFCorpus | — | — | — |
| Docling HybridChunker | [Docling example](https://docling-project.github.io/docling/_generated/examples/advanced_chunking_and_serialization/) | 2025 | Document-structure chunks split or merged to a token limit, with heading context | Integrated with the parser | Structure plus token aware | Docling-only input | Yes |
| Parent-child / small-to-big | (LlamaIndex/LangChain pattern) | — | Retrieve small chunks, return the parent section | Practitioner pattern (not re-verified this session) | Precise retrieval, full context | More storage | Yes |
| Proposition chunking (Dense X Retrieval) | [arXiv 2312.06648](https://arxiv.org/abs/2312.06648) | 2023 | LLM rewrites text into atomic propositions | Paper reports retrieval gains (not re-verified this session) | Great for facts in a memory KG | LLM cost per chunk | Offline with local LLM |
| RAPTOR | [arXiv 2401.18059](https://arxiv.org/abs/2401.18059) | 2024 | Recursive clustering and summarization tree | Helps multi-hop QA (not re-verified this session) | Long-doc summaries | Expensive to build | Offline only |
| Chunk-size effect | Weaviate 2025 (via blog) | 2025 | — | Up to a 9-point recall gap between best and worst methods (unverified) — [fast.io](https://fast.io/resources/best-chunking-strategies-for-rag/) | — | — | — |

### Inferences
- **Recommendation:** use Docling HybridChunker (or a recursive Markdown splitter for MarkItDown output) at about 300–512 tokens, and prepend a **deterministic header** (doc title, section path, date). Then run a **nightly offline "contextualizer" job** with the local 2–4B model that writes a 1–2 sentence context per chunk. Store both `chunk_text` and `context` in Postgres, embed `context + chunk`, and index the same text in `tsvector` for BM25-like FTS. Retrieve with hybrid RRF. An optional reranker (e.g. bge-reranker-v2-m3 or Qwen3-Reranker-0.6B, not researched here) runs only for document Q&A, not every voice turn.
- Propositions extracted at ingest can feed Stiti's memory or KG directly (facts, entities), which unifies document chunking with memory formation.

### Gaps
- No unified 2026 benchmark covers all strategies on personal-data corpora such as emails, chats and notes.
- Late-chunking support in MLX embedding runtimes was not verified.

---

## 6. Ingesting personal data sources (notes, emails, chats, PDFs, browser history) into memory/KG

### Takeaway
No existing open-source tool does everything Stiti needs on an 8 GB machine with a Postgres-centric brain. **Khoj** (AGPL; Obsidian, Notion, PDFs, org files, browser history) and **Screenpipe** (screen and audio capture, SQL/REST/MCP) are the closest references. **Graphiti** and **Cognee** are KG-ingestion engines, but they need graph DBs and/or structured-output-capable LLMs. Recommended approach: write **thin per-source connectors** that read local SQLite/mbox exports into Stiti's own Postgres tables, and borrow ideas (temporal facts from Graphiti, self-editing dedupe from Mem0) rather than adopting a framework.

### Cited Findings

| Tool | Link | Year | Mechanism / sources | Strengths | Weaknesses | 8 GB / free? |
|---|---|---|---|---|---|---|
| **Khoj** | [repo](https://github.com/khoj-ai/khoj), [star-history](https://www.star-history.com/blog/khoj) | 2023– | Self-host second brain; Obsidian, Notion, PDFs, org, browser history; local or online LLMs | Broad sources; ~35k stars | AGPL-3.0; its own Postgres (pgvector) stack; heavy for 8 GB | Partial. Free |
| **Reor** | [repo](https://github.com/reorproject/reor) | 2024– | Local Markdown-notes app with Ollama and auto-linking | Fully local | Notes only; AGPL | Yes |
| **AnythingLLM** | [listing](https://best-of-web.builder.io/library/khoj-ai/khoj) | 2023– | Desktop/Docker RAG workspace, agents | Easy doc RAG; Apache-2.0 (per listing) | Not memory-centric; own vector store | Partial |
| **Screenpipe** | [blog](https://www.screenpi.pe/blog/local-ai-assistant-private-2026) | 2024– | Continuous screen OCR and audio transcription to SQLite; SQL/REST/MCP | Captures everything, including chats and browsing | CPU, disk and privacy heavy; vendor-sourced claims | Risky on 8 GB |
| **Graphiti** (Zep) | [repo](https://github.com/getzep/graphiti), [comparison](https://atlan.com/know/best-ai-agent-memory-frameworks-2026/) | 2024– | Temporal KG: episodes → entities/edges with validity intervals | Tracks how facts change over time; Zep 63.8% vs Mem0 49.0% on LongMemEval (vendor-adjacent) | Needs Neo4j/FalkorDB; "Smaller LLMs that cannot produce structured output will fail ingestion" | Heavy; ideas only |
| **Cognee** | [repo](https://github.com/topoteretes/cognee) | 2024– | ECL pipeline into relational, vector and graph stores | Many source loaders; doc-pipeline style | Vendor-written comparisons | Partial |
| **Mem0** | [repo](https://github.com/mem0ai/mem0) | 2024– | LLM extracts facts and self-edits (update/delete) instead of appending | Lean memory; pgvector backend supported (not re-verified this session) | Weaker temporal reasoning | Yes with a small LLM |
| **Letta** (MemGPT) | [repo](https://github.com/letta-ai/letta) | 2023– | Agent runtime with tiered memory | Strong stateful agent model | "The agent is its memory": a heavy commitment | Overkill |
| LlamaIndex readers (LlamaHub) | [hub](https://llamahub.ai) | 2023– | Loaders for Gmail, IMAP, Obsidian, Notion, etc. | Ready-made connectors | Framework weight; quality varies (not re-verified this session) | Selective reuse |
| Unstructured (email partitioners) | [repo](https://github.com/Unstructured-IO/unstructured) | 2022– | `.eml`/`.msg` and attachments | Email plus attachment parsing | Heavy dependencies | Yes |
| Open WebUI knowledge | [repo](https://github.com/open-webui/open-webui) | 2023– | Chat UI plus doc RAG | — | Not a memory engine | n/a |

- No result confirmed email ingestion for Khoj, Reor, AnythingLLM or Screenpipe — [search summary](https://www.screenpi.pe/blog/local-ai-assistant-private-2026)

### Inferences
- **Recommended connectors**, all local, incremental, and writing to Postgres. File locations are standard macOS facts, not re-verified this session.
  - **Apple Notes**: export via AppleScript/Shortcuts, or read `NoteStore.sqlite`.
  - **Obsidian/Markdown**: file watcher.
  - **Email**: IMAP fetch, or Google Takeout mbox. Parse with Python `mailbox`/`email`; attachments go to the document pipeline.
  - **iMessage**: `~/Library/Messages/chat.db` (needs Full Disk Access).
  - **WhatsApp/Telegram**: their export files.
  - **Browser history**: Chrome `History` and Safari `History.db` SQLite. Copy the file first because it is locked while the browser is open.
  - **PDFs/Office**: section 4 pipeline.
- Each record becomes (a) raw chunks with embeddings in pgvector, and (b) facts and entities extracted offline by the local LLM into KG tables with `valid_from`/`valid_to` (Graphiti's temporal idea) and update-or-merge dedupe (Mem0's idea). Use grammar-constrained JSON so small models produce valid structured output, which addresses Graphiti's failure mode.
- Do all extraction locally. Personal data is exactly what Gemini/Mistral free-tier terms warn against sending.

### Gaps
- No independent benchmark of personal-data ingestion quality across these tools.
- Khoj's and Cognee's current connector lists (e.g. email) were not verified from their repos this session.
