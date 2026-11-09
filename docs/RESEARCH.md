# Research: What Already Exists and What We Take From It

Snapshot taken 2026-11-10. Star counts and free-tier limits change often; re-check
before relying on them. Per-feature deep dives go in `docs/research/<feature>.md`.

## 1. Similar "Jarvis / personal assistant" projects

| Project | What it is | What Stiti takes | Reverse-engineer how |
|---|---|---|---|
| **OpenClaw** ([docs](https://docs.openclaw.ai), github.com/openclaw/openclaw) | Very popular self-hosted personal agent (TypeScript). Gateway hub + channel connectors (WhatsApp, Telegram, iMessage…) + skills registry (ClawHub). Memory = markdown files (`SOUL.md`, `USER.md`, `MEMORY.md`) + SQLite hybrid search (vector + BM25). | Markdown identity files, hub-and-spoke connectors, hybrid search. | Read source; `rea analyze-javascript-application` on the built package to map modules, routes, memory flow. |
| **Hermes Agent** (Nous Research, [docs](https://hermes-agent.nousresearch.com/docs)) | Self-improving agent: creates/updates skills from experience, background "nudges" to save memory, Curator prunes skills, SQLite FTS5 session search. Agent core separate from model, so switching LLM keeps learned state. | **Learning loop without fine-tuning**, lessons/skills as files, memory nudges, model-agnostic core. Closest to the "brain ≠ LLM" idea. | Read source (Python). Focus: skill_manage, curator, nudge scheduler. |
| **isair/jarvis** ([repo](https://github.com/isair/jarvis)) | Private local desktop assistant: voice + text, personal memory, MCP tools, Ollama/OpenAI-compatible, macOS. | Closest small-scale analog; check its voice + MCP wiring. | Read source. |
| **ZXyoukai/jarvis-voice-agent** ([repo](https://github.com/ZXyoukai/jarvis-voice-agent)) | Local STT/TTS + **OpenRouter free models** + SQLite session memory. | Proof the free-OpenRouter + local voice combo works. | Read source. |
| **amanimran786/jarvis-ai** ([repo](https://github.com/amanimran786/jarvis-ai)) | macOS assistant; mem0 + local Qdrant; faster-whisper + Kokoro planned; multi-model routing. | Model routing ideas. | Read source. |
| **Nitro70/ai-jarvis** ([repo](https://github.com/Nitro70/ai-jarvis)) | Wake word + local Whisper + Edge TTS + modular tools; memory = markdown file. | Wake word + modular tools pattern. | Read source. |
| **OpenJarvis** ([site](https://open-jarvis.github.io/OpenJarvis/)) | Research framework for on-device personal AI. | On-device design ideas. | Read docs/source. |

## 2. Memory & knowledge graph

| Project | Key idea | Take |
|---|---|---|
| **graphify** (github.com/graphify-labs/graphify, `pip install graphify`) | Turns a folder into a knowledge graph; writes `graph.json` + `GRAPH_REPORT.md` that an AI reads as compact context; exports SVG/GraphML/Cypher. | Exactly the "context briefing" pattern. Stiti's Context Compiler = graphify for a **life** instead of a codebase. Copy the report format + export idea. |
| **Graphiti** (by Zep, open source) | **Temporal** knowledge graph: facts have validity over time; contradictions invalidate old edges instead of deleting. Strong LongMemEval results. | Temporal edges (`valid_from`/`valid_to`), episode provenance. Implement lightweight version in SQLite. |
| **Mem0** (Apache-2.0) | Memory layer for user preferences / personalization. | Fact extraction + dedupe prompts. |
| **Letta** (ex-MemGPT) | Agent runtime with memory blocks + background "sleep-time" memory work. Finding: plain transcripts-in-files can beat fancy memory on LOCOMO. | Keep raw episodes forever (cheap, strong baseline); consolidation in background. |
| **Cognee** | Knowledge graph built from many document sources. | Ingesting docs/notes into the graph (later phase). |
| **Karpathy "LLM Wiki" idea** | Human-readable wiki maintained by the AI as memory. | Markdown-as-truth principle. |

Comparison sources: [atlan](https://atlan.com/know/best-ai-agent-memory-frameworks-2026/),
[codepointer](https://codepointer.substack.com/p/agent-memory-systems-and-knowledge),
[mcp.directory](https://mcp.directory/blog/mem0-vs-letta-vs-zep-vs-cognee-2026). Some are vendor-written; treat numbers as directional.

## 3. Real-time voice

| Piece | Best free options found | Notes |
|---|---|---|
| Orchestration | **Pipecat** (Python, v1.0 Apr 2026, 40+ plugins); LiveKit Agents (alt.) | Pipecat examples report sub-800 ms on M-series Macs. |
| Reference stack | **huggingface/speech-to-speech**: Silero VAD + Parakeet + local LLM + Kokoro/Qwen3-TTS | Good blueprint to reverse-engineer. |
| VAD | Silero VAD | Tiny, CPU. |
| Turn detection | Smart-Turn (Pipecat), TEN Turn Detection, Easy Turn | Decides "user finished talking" from audio + words; key for natural feel. |
| STT local | parakeet-mlx, mlx-whisper, faster-whisper, **SenseVoice-Small** | SenseVoice = transcript + emotion + audio events in one ~234 MB model. |
| STT cloud (free) | Groq `whisper-large-v3-turbo`: ~20 req/min, ~2,000 req/day, ~28.8k audio-sec/day ([Groq docs](https://console.groq.com/docs/rate-limits.md)) | Fallback when local is busy. |
| TTS local | **Kokoro-82M** (Apache-2.0, fast), Chatterbox (expressive/cloning), Orpheus 3B (heavy) | Start Kokoro. |
| Speech-to-speech (full duplex) | Kyutai Moshi (7B, ~200 ms), NVIDIA PersonaPlex | Too heavy for 8 GB; study design only. |
| Cloud live voice (free tier) | **Gemini Live API** via AI Studio (no card; supports tool calling; limits unpublished) | Optional "natural mode". Not on OpenRouter. |

Sources: [techsy](https://techsy.io/en/blog/best-open-source-voice-agent-frameworks),
[HF speech-to-speech](https://github.com/huggingface/speech-to-speech),
[localaimaster TTS](https://localaimaster.com/blog/best-local-tts-models),
[Gemini Live free tier](https://apidog.com/blog/gemini-3-8-live-api/).

## 4. Emotion from voice

| Model | Notes |
|---|---|
| **emotion2vec+** (FunASR; large ≈ 300M params, 9 emotions, language-agnostic) | Strongest open option for emotion alone; real-world F1 varies a lot (≈49–84%). |
| **SenseVoice-Small** (FunASR) | ASR + emotion + audio events in one small model: best fit for 8 GB. |
| FunASR toolkit | Runs both; has streaming + OpenAI-compatible server. |

Plan: benchmark both on Tejmul's own recordings (Phase 3) and build a personal baseline.
Sources: [FunASR](https://github.com/modelscope/FunASR), [SenseVoice vs emotion2vec discussion](https://huggingface.co/emotion2vec/emotion2vec_plus_large/discussions/1), [arXiv pilot](https://arxiv.org/pdf/2609.26054).

## 5. Free LLM access

| Provider | Free tier (verify live) |
|---|---|
| **OpenRouter `:free` models** | 20 req/min; **50 req/day** if < $10 lifetime credits, 1,000/day after a one-time $10 top-up ([pricing](https://openrouter.ai/pricing), [summary](https://www.developersdigest.tech/rate-limits/openrouter)). |
| **Groq** | Free, no card, fast inference; limits per model, org-wide. |
| **Google AI Studio (Gemini)** | Free key, no card; includes Live API. |
| ~~Ollama (local)~~ | **Not used** (D8): overloads the 8 GB Mac. |

50/day on OpenRouter alone is not enough for a voice buddy → router must spread load
and the intent fast-path must avoid LLM calls for simple commands.

## 6. Decision layer: Laya

[Laya](https://github.com/NandhaKishorM/laya) (Convai Innovations, Apache-2.0,
[HF model card](https://huggingface.co/convaiinnovations/laya)): a "System 1" typed decision model.
- Encoder-only (ModernBERT-large ≈ 421M, 512 tokens, English; mmBERT-base ≈ 322M multilingual, 1,024 tokens). Download ≈ 808 MB / 647 MB.
- State + many questions → **one forward pass**. Types: `choice`, `score`, `noul` (yes/no prob).
  State tokenized once and reused for all questions; `predict_batch` groups compatible requests.
- Speed (T4 GPU, vendor numbers): 33 ms for 1 question, ~7 ms/question batched. M2 numbers unknown → benchmark.
- Calibrated confidence + `min_confidence` abstain → perfect for "act or ask the LLM" gating.
- Ships CLI, `laya-serve` HTTP server, **MCP server**, LangChain/LlamaIndex/CrewAI integrations; ONNX INT8 path.
- Limits: base zero-shot accuracy low on its benchmark (0.36) vs fine-tuned (0.77); many options hurt
  accuracy; out-of-box over-confident until calibrated; English root checkpoint only English;
  `act_probability` not useful yet.
- Why it matters for Stiti: it's how **the brain decides without the LLM**.

Sources: [source tour](https://pyshine.com/laya-typed-decision-engine-source-tour/),
[Menon Lab write-up](https://themenonlab.blog/blog/laya-local-system-1-decision-model),
[Laya-MLX claim (unverified)](https://aiidelist.com/blog/what-is-laya-mlx).

Reverse-engineer target: `laya/agent.py` (abstention gate), `laya/common.py` (sequence builder),
calibration code, to learn how to log + calibrate on our own data.

## 7. Reverse-engineering tool: rea

[morluto/rea](https://github.com/morluto/rea), "Reverse Engineer Anything", MIT, runs locally as an **MCP server** for Claude Code.
- Setup: `npx rea-agents setup` (needs Node 22.23.4+ / 24.22.1+), then restart Claude Code.
- JS/Electron apps: `rea analyze-javascript-application /abs/path --json` → modules, imports, routes, IPC.
- Websites: page structure, scripts, network observations (needs Chrome).
- Model files: inspect GGUF/safetensors (useful to check model sizes/quantization before downloading into 8 GB).
- Also: native binaries (Ghidra/Hopper), Android APKs, SQLite DBs, process behaviour.
- Use only on software we're allowed to analyze (open source, or our own apps for learning/interoperability). Learn the design, don't copy proprietary code.

### First reverse-engineering targets (in order)
1. **OpenClaw**: gateway, connector interface, memory files + hybrid search.
2. **Hermes Agent**: learning loop, skills curator, memory nudges.
3. **graphify**: graph extraction + `GRAPH_REPORT.md` format.
4. **HF speech-to-speech / Pipecat examples**: lowest-latency local voice wiring on Mac.
5. **Graphiti**: temporal edge invalidation logic.
6. **Laya**: abstention gate, calibration, batching.
