# Build Stiti's Brain Before Its Mouth

Stiti should be built as **one local PostgreSQL memory engine** with five parts. The first is an append-only episode log with hybrid vector and full-text recall. The second is a bitemporal knowledge graph that re-implements Zep/Graphiti in plain tables. The third is an ACE-style itemized lessons table, the fourth a directive-style user model, and the fifth a nightly "sleep" consolidation job. Around that engine sit **Laya**, which makes every per-turn decision locally, and a **~150-line router** that treats the Groq, Cerebras, OpenRouter, Mistral and Gemini free tiers as interchangeable mouths. About 40 comparison tables, each with 10 or more papers, repos or models, point to the rule Tejmul already chose: *the LLM proposes, deterministic code disposes*. OpenClaw, Hermes, Leon, isair/jarvis and AIRI all run that way. No open-source system combines a bitemporal KG, lessons and briefing compilation inside Postgres, so Stiti builds its own engine from borrowed parts. Voice is a cascaded Pipecat pipeline: Silero VAD, Smart Turn v3.1, a Hinglish-capable Whisper, Kokoro and emotion2vec+. It fits in roughly 2–3 GB, and the estimated voice-to-first-audio on an M2 is 0.9–1.6 s. That estimate is extrapolated, because nobody has published base-M2 measurements. The life-management features follow the psychology evidence:

- Rank tasks with a transparent Taskwarrior-style urgency score that adds Temporal Motivation Theory (TMT) terms.
- Plan days with CP-SAT, which solves a 12-task day in 10–60 ms on this Mac.
- Model habits as a forgiving strength score, not as spaced repetition.
- Say at most 3 items per spoken turn, allow 3–5 unsolicited nudges a day, and never use guilt language.

Tejmul's hard constraints change the researchers' advice in about a dozen places. Every local-LLM job moves to batched free cloud tiers behind a three-level privacy gate, and every SQLite or ChromaDB store moves into Postgres. Engine v0, specified near the end, is 14 tables, one SQL recall function, a fixed briefing template, a Laya question set, a lessons capture path and a consolidation job. It can be built tonight.

## Tejmul's four constraints rewrote a dozen researcher recommendations

The research notes were written partly before D8 ("no local LLM, no Ollama") and D6 ("Postgres replaces SQLite") were final. Several recommendations therefore assume a local 2–4B model or a SQLite file. The table records every place this report overrides a note. The constraint column says which rule forced the change.

| Note & feature | Researcher recommended | This report uses instead | Constraint |
|---|---|---|---|
| LLM routing §3 | Gemma 4 E2B as the "always-loaded local brain", Qwen3.5-4B when voice is idle, Qwen3.5-2B under pressure | No local LLM at all. Cloud chain only. When every provider is down, Laya and rules run the fast path and Stiti says deep thinking is unavailable. | No local LLM (D8). Qwen3.5-4B alone peaks at **~4.2 GB at 4K context on a base M2 8 GB** ([oMLX](https://omlx.ai/benchmarks/hhfwaa55)), more than the whole 3 GB model budget. |
| LLM routing §1 | Privacy gate defaults personal turns to the *local* model, which is also the last resort | Privacy gate either minimizes context for no-training providers or keeps sensitive (P2) turns on the Mac with no LLM. Last resort is the fast path. | No local LLM, zero cost |
| LLM routing §1 | Semantic-Router-style embedding router plus local 4B classes | Laya's typed questions plus rules | Decisions belong to Laya (D5) |
| LLM routing §5 | Nightly "contextualizer" writes chunk context with a local 2–4B model | Cloud batch job on Cerebras/Groq for P0/P1 documents. P2 documents get only deterministic headers (title, section path, date). | No local LLM; privacy |
| LLM routing §6, memory §3 | "Do all extraction locally"; consolidation as "small-LLM jobs" | Batched free-cloud jobs at idle time, gated by privacy class. P2 episodes get embeddings, FTS and Laya tags but no LLM extraction. | No local LLM; Gemini's terms forbid personal data on the unpaid tier |
| Productivity §3 | Socratic Chunker on a local 3–4B model with JSON-schema output | Cloud LLM with JSON-schema output. Laya validates each step. Offline, it falls back to fixed template questions. | No local LLM |
| Productivity §1 | SQLite task store "owned by the memory engine" | `tasks` table in the brain database | Postgres only (D6) |
| Productivity §7 | APScheduler with a SQLite jobstore | `intents` table in Postgres. An in-process scheduler reads it, and LISTEN/NOTIFY wakes it. | Postgres only |
| LLM routing §4 | Chroma considered for documents | `pgvector` `halfvec` + HNSW in the same database as memory and KG | Postgres only |
| Memory §6, connectors §1 | Embeddings "via Ollama or MLX"; a separate bge-small/nomic model for tool-RAG | One in-process MLX/ONNX embedder shared by memory, documents and tool-RAG | No Ollama; RAM. Ollama pre-allocated **~5.8 GB** for Qwen3-Embedding's 32K KV cache ([SurrealDB](https://surrealdb.com/blog/embedding-models-comparison)). |
| Personal assistants §Q3 | Graphiti/Kuzu, or Apache AGE "if Cypher is needed" | Plain tables plus recursive CTEs. AGE only if multi-hop paths become slow. | One Postgres; 8 GB |
| Voice §1 | Reference repos run Gemma3n-4B / Qwen3.5-4B locally | Copy only their speech wiring. The LLM hop goes to the cloud. | No local LLM |

**The privacy gate replaces "send it to the local model".** Laya labels every turn and every consolidation batch with a privacy class. A deterministic secret-pattern scan sets a floor that Laya cannot lower, modeled on Omi's `memory_secret_patterns` ([Omi backend](https://github.com/BasedHardware/omi/tree/main/backend)).

- **P0 (public or generic):** web summaries, general knowledge, public documents. Any provider may handle these, including Gemini Flash-Lite.
- **P1 (personal):** the default for memory-backed chat. Goes only to Groq, Cerebras, OpenRouter zero-data-retention endpoints, or Mistral with training opted out, always with a minimized briefing. Never to Gemini.
- **P2 (sensitive):** health, money, credentials, other people's private messages, anything tagged private. Never leaves the Mac. Stiti answers it from the fast path, reads stored memory back verbatim, or asks "can I send this to the cloud to think about it?"

The P2 rule follows Google's own terms: "Google uses the content you submit… human reviewers may read… Do not submit sensitive, confidential, or personal information to the Unpaid Services" ([AI Studio terms](https://aistudio.google.com/docs/terms)). Mistral trains on free-tier data unless you opt out ([Mistral help](https://help.mistral.ai/en/articles/323757-do-you-use-my-user-data-to-train-your-artificial-intelligence-models)). The claim that Groq and Cerebras do not train comes from OpenRouter's comparison post, not their primary ToS ([OpenRouter blog](https://openrouter.ai/blog/tutorials/free-llm-apis-compared/)), so it remains an open question.

The local-model budget is tight but feasible. The table combines measured component numbers from Apple-Silicon sources. None of them were measured on a base M2, so the column is an estimate to verify on day one.

| Resident component | Pick | Approx. RAM | Source |
|---|---|---|---|
| Postgres (tuned: `shared_buffers=256MB`, `max_connections=20`) | Homebrew PG 18 + pgvector + btree_gist | 0.1–0.3 GB | D6; memory notes §7 |
| Wake word | LiveKit WakeWord v2, custom "Hey Stiti" | ~7–10 MB | [livekit-wakeword](https://github.com/livekit/livekit-wakeword) |
| VAD + turn | Silero VAD + Smart Turn v3.1 int8 | <10 MB | [Smart Turn card](https://huggingface.co/pipecat-ai/smart-turn-v3) |
| STT | mlx-whisper large-v3-turbo q4 (A/B against Oriserve Hindi2Hinglish-Apex, Qwen3-ASR 0.6B) | 0.4–1.0 GB | [soniqo](https://soniqo.audio/benchmarks) |
| TTS | Kokoro-82M | 0.17–0.6 GB | [soniqo](https://soniqo.audio/benchmarks); [kokoro-tts-mcp](https://github.com/scottschram/kokoro-tts) |
| Speech emotion | emotion2vec+ base (~90M params) | ~0.4 GB (estimate) | [emotion2vec](https://github.com/ddlBoJack/emotion2vec) |
| Embeddings | EmbeddingGemma-300M | <0.2 GB quantized (vendor) to 0.7 GB measured | [Google](https://developers.googleblog.com/en/introducing-embeddinggemma/); [SurrealDB](https://surrealdb.com/blog/embedding-models-comparison) |
| Decision layer | Laya multilingual (mmBERT-base, 322M, 647 MB download) | ~0.4–0.7 GB (unmeasured) | [Laya source tour](https://pyshine.com/laya-typed-decision-engine-source-tour/) |
| **Total** | | **≈1.8–3.7 GB** | |

The top of that range breaks the budget. One builder's "small" Parakeet + Kokoro speech stack already peaked at **3.63 GiB RSS** ([mthomas100/local-voice](https://github.com/mthomas100/local-voice)). Four rules keep Stiti inside 3 GB:

- Quantize Laya and the embedder (ONNX INT8).
- Load emotion2vec+ lazily and run it on finished turns only.
- Run every model inside one process and one runtime, so there are no duplicate PyTorch/MLX copies.
- Measure RSS per component before adding the next one.

## The brain: eight memory features converge on one Postgres engine

### Architecture: state lives outside the model, behind deterministic gates

Thirteen architectures were compared: CoALA, MemGPT, ReAct, Generative Agents, MemOS, OpenClaw, Hermes Agent, Letta, Leon, nanobot, isair/jarvis, Home Assistant Assist and OpenVoiceOS. Every serious one keeps state *outside* the model.

- **CoALA's four memory types** (working, episodic, semantic, procedural) are the cleanest schema vocabulary ([CoALA](https://arxiv.org/abs/2309.02427)).
- **MemGPT's LLM-driven paging** is the wrong pattern for Stiti. It needs a strong tool-calling model to manage its own memory ([MemGPT](https://arxiv.org/abs/2310.08560)), which makes the LLM the brain.
- **OpenClaw's memory design** is the best-documented runtime blueprint. In its words: "Deterministic gates, model judgment inside them. Scoring, thresholds, eligibility, matching, and lifecycle are deterministic code", and "No hidden state. The model only remembers what is written to files." Its recall has two lanes. Lane 1 makes zero model calls and scores "hybrid relevance multiplied by an exponential recency decay (30-day half-life) and an importance multiplier". Lane 2 is a recall sub-agent used only when lane 1 has no strong hit ([OpenClaw memory-architecture.md](https://github.com/openclaw/openclaw/blob/main/docs/concepts/memory-architecture.md)).
- **Provenance rules worth copying.** OpenClaw tags every entry with an origin (`owner|agent|untrusted|system`). Content injected from memory "is structurally marked and never re-extracted… A fact recalled one hundred times stays one fact." Durable memory has exactly one writer, the dreaming pass, and it keeps a pre-image so changes can be rolled back.
- **Deterministic intent first, LLM second.** Leon's "controlled" mode and Home Assistant's typed intents run common voice commands without an LLM ([Leon](https://github.com/leon-ai/leon); [HA intents](https://developers.home-assistant.io/docs/voice/intents/)).
- **Reject the Letta server.** It duplicates the Postgres brain and is heavy on 8 GB. Keep only its "memory block" idea ([Letta blog](https://letta.com/blog/memory-blocks)).

**Decision:** CoALA vocabulary, OpenClaw's gates and provenance as invariants, and the Leon/HA deterministic fast path, all implemented on Postgres in Python. **Reverse-engineer:** OpenClaw's `dreaming-*`, `agent-runner-memory-*` and `context-engine-*` dist chunks with rea (see the rea section). Read the Hermes and jarvis Python source directly.

### Episodic memory: keep every turn verbatim, retrieve with a composite score

The twelve episodic designs differ mainly in the *retrieval unit* and the *score*:

- **Generative Agents** ranks by recency + importance + relevance, with recency decaying at 0.995 per game-hour and an LLM rating importance from 1 to 10 ([Park et al.](https://arxiv.org/abs/2304.03442)).
- **MemoryBank** adds Ebbinghaus-style decay with reinforcement on recall ([MemoryBank](https://arxiv.org/abs/2305.10250)).
- **LongMemEval** recommends three things, backed by ablations: round-level decomposition, **fact-augmented keys** (index each turn under the facts extracted from it) and **time-aware query expansion**. Commercial assistants lose about 30% accuracy over sustained interactions ([LongMemEval](https://arxiv.org/abs/2410.10813)).
- **SeCom and Nemori** argue for topical segments as a second retrieval unit ([SeCom](https://arxiv.org/abs/2502.05589); [Nemori](https://arxiv.org/abs/2508.03341)).
- **Zep and MemMachine** keep raw episodes as non-lossy ground truth, with derived facts pointing back to them ([Zep](https://arxiv.org/abs/2501.13956); [MemMachine](https://arxiv.org/html/2604.04853v1)).
- **Mem0** stores only LLM-extracted facts. That approach is compact but lossy. An independent test found **32–49% LongMemEval R@5** for Mem0 OSS, against vendor claims above 90% ([DEV independent benchmark](https://dev.to/everest_an/-i-benchmarked-ai-agent-memory-in-2026-and-the-numbers-tell-a-different-story-than-the-marketing-2ae4)).
- **Letta's plain filesystem storage** reached **74% on LoCoMo** with gpt-4o-mini ([Mem0 state of memory](https://mem0.ai/blog/state-of-ai-agent-memory-2026)).

Those last two results are the strongest argument for Stiti's plain-Postgres design: clean storage with decent retrieval beats exotic architecture.

**Decision:** an immutable `episodes` table, one row per utterance, never hard-deleted. Each row carries an embedding, a `tsvector`, `importance`, `strength`, access stats, emotion and provenance. A nightly job adds `segments`. "Forgetting" lowers a row's rank, not its existence. The memory notes estimate about 0.3 GB of 768-d `halfvec` vectors after ten years at 50 turns a day.

### Hybrid retrieval: one SQL statement, reciprocal rank fusion, no reranker on the voice path

The twelve retrieval approaches agree on vector kNN plus lexical search, fused with **Reciprocal Rank Fusion at k = 60** ([Cormack et al.](https://plg.uwaterloo.ca/~gvcormac/cormacksigir09-rrf.pdf)). On top of that come optional graph expansion and an optional cross-encoder.

- **Supabase** publishes the canonical single-function Postgres RRF pattern ([Supabase hybrid search](https://supabase.com/docs/guides/ai/hybrid-search)).
- **pgvector 0.8** added iterative index scans, which fix over-filtering when a time filter is combined with HNSW ([PostgreSQL news](https://www.postgresql.org/about/news/pgvector-080-released-2952/)).
- **Real BM25** is available through `pg_textsearch` (PostgreSQL license, PG 17/18) or ParadeDB `pg_search` (AGPL). Their benchmarks conflict ([Particula](https://particula.tech/blog/pg-search-vs-pg-textsearch-bm25-postgres); [pg_textsearch announcement](https://www.postgresql.org/about/news/pg_textsearch-v10-3264)).
- **HippoRAG's Personalized PageRank** gives single-step multi-hop recall ([HippoRAG](https://arxiv.org/abs/2405.14831)), but it belongs in the background.
- **Rerankers** have no measured M2 latency. One unattributed figure is about 12 ms per pair for bge-reranker-v2-m3 ([mixpeek](https://www.mixpeek.com/curated-lists/best-rerankers)), which already breaks a 100 ms budget at 20 candidates.

One Hinglish detail matters and is this report's inference. Postgres's `english` text-search configuration stems English and drops stop words. That would mangle Roman-script Hindi ("kal", "mujhe", "bhai"), so Stiti indexes with the **`simple` configuration** plus `pg_trgm` for spelling variants. Hinglish has no standard spelling ([Oriserve card](https://huggingface.co/Oriserve/Whisper-Hindi2Hinglish-Apex)).

**Decision:** one `recall()` SQL function (spec in Engine v0). It runs vector and `simple`-FTS legs, fuses with RRF, multiplies by recency/importance/strength priors, applies a time-range filter, and expands 1–2 hops to current facts. MMR runs in Python. There is no reranker on the hot path. Start with built-in FTS and adopt `pg_textsearch` only if a measured recall gap appears.

### Temporal knowledge graph: copy Graphiti's model, not its code

The twelve KG systems split into two groups:

- **Batch graph-RAG builders:** GraphRAG ([arXiv](https://arxiv.org/abs/2404.16130)), LightRAG ([arXiv](https://arxiv.org/abs/2410.05779)), nano-graphrag and graphify. None of them models time.
- **Incremental agent memories:** Zep/Graphiti, Mem0g, nxlabscc/agent-memory, Cognee and Basic Memory.

**Graphiti's bitemporal edge model is the reference.** A fact has world time (`valid_at/invalid_at`) and system time (`created_at/expired_at`). A contradiction *invalidates* the old edge instead of deleting it. Zep reports DMR 94.8% vs MemGPT 93.4% in its own paper ([Zep](https://arxiv.org/abs/2501.13956)).

Graphiti itself is unusable here. Its drivers cover only Neo4j, FalkorDB, Kuzu and Neptune ([Graphiti drivers](https://www.mintlify.com/getzep/graphiti/api/drivers/overview)), and its maintainers warn that small LLMs without structured output "will fail ingestion" ([Atlan comparison](https://atlan.com/know/best-ai-agent-memory-frameworks-2026/)). Two Postgres-native projects show the model can be ported:

- **nxlabscc/agent-memory** (Apache-2.0, a 1-commit reference) implements two time axes, interval-closing instead of deletes, MinHash entity resolution, and "LLM judges contradictions but code decides which interval closes", all in Postgres + pgvector ([repo](https://github.com/nxlabscc/agent-memory)).
- **Cognee 1.0** runs graph, vectors and sessions in one Postgres and claims about 10% faster search (vendor) ([Cognee](https://www.cognee.ai/graph-on-postgres)).

**Postgres enforces the time logic natively.** A `tstzrange` validity column plus a GiST exclusion constraint (`btree_gist`), or PG 18's `WITHOUT OVERLAPS`, prevents two values of a *functional* predicate (`lives_in`, `works_at`) from both being valid at once ([Neon PG 18 temporal constraints](https://neon.com/postgresql/postgresql-18/temporal-constraints)). Apache AGE supports PG 18 since 1.7.0 ([AGE release notes](https://age.apache.org/release-notes)). It is still unnecessary at personal-graph scale, and its `agtype` composes poorly with pgvector filters.

**graphify contributes the output format, not the store.** Its `GRAPH_REPORT.md` lists god nodes, surprising connections and suggested questions, and the model reads it first ([Better Stack](https://betterstack.com/community/guides/ai/ai-development/graphify-codebase/)). A critical review found graphify's `query` gave a confidently wrong answer ([Vijayan](https://praveenvijayan.substack.com/p/your-knowledge-graph-is-making-your)). That is a reason to expose only compiled reports to the LLM, never raw graph queries.

**Decision:** `entities`, `facts` (bitemporal, partial exclusion constraint on functional predicates) and `episode_mentions` tables. Traverse with `WITH RECURSIVE`. Feelings are first-class time-scoped edges (`tejmul —feels{valence:-0.6}→ project_X`). The LLM only *flags* contradictions, and code closes intervals. Weekly communities and god nodes are computed in Python (igraph/networkx). **Reverse-engineer:** read Graphiti's Python source for its resolution and invalidation prompts (rea isn't needed for Python). Run rea on graphify's report builder only if a JS/Rust build is the easiest target.

### Consolidation: a nightly "sleep" pipeline of SQL plus batched free-cloud calls

Twelve consolidation designs were compared. They agree that heavy memory work belongs *between* conversations:

- Generative Agents writes reflections once summed importance crosses a threshold.
- RAPTOR and GraphRAG build summary hierarchies ([RAPTOR](https://arxiv.org/abs/2401.18059)).
- MemoryOS moves pages between tiers by "heat" ([MemoryOS](https://arxiv.org/html/2506.06326v1)).
- LightMem does an offline long-term update ([LightMem](https://arxiv.org/abs/2510.18866)).
- RMM adds prospective topic summaries ([RMM](https://arxiv.org/abs/2503.08026)).
- **Letta's sleep-time compute** pre-computes context while idle so the primary agent never waits ([Letta](https://letta.com/blog/sleep-time-compute)). This is the biggest latency lever for voice.

The one design that consolidates into model weights ("Language Models Need Sleep") is rejected because it would weld memory to one model ([alphaXiv](https://www.alphaxiv.org/abs/2605.26099v1)).

OpenClaw's implementation adds production-grade safety, which rea confirmed. Its dist exposes `runLightDreaming`, `runRemDreaming`, `selectRemCandidateTruths`, `calculateCandidateTruthConfidence`, `writeDreamsFileAtomic` and `withMemoryWorkspaceLock`, plus a `"0 3 * * *"` literal that suggests a 03:00 nightly default. Before any rewrite is accepted it must pass a deterministic gate, structural validation, a budget check, and a "does not drop more than a bounded fraction" rule ([memory-architecture.md](https://github.com/openclaw/openclaw/blob/main/docs/concepts/memory-architecture.md)).

**Constraint override.** The notes run these jobs on a "small LLM". Stiti runs them as batched calls to Cerebras first (1M tokens/day, high throughput, and its 5 RPM limit doesn't matter for batch work), then Groq ([Cerebras limits](https://inference-docs.cerebras.ai/support/rate-limits)). P2 rows are excluded from every LLM step.

**Decision:** an idempotent job chain, watermarked in `consolidation_runs`, at 03:00 or after 30 idle minutes on AC power. Full spec in Engine v0.

### Lessons: an itemized playbook updated by deltas, never rewritten

Fourteen "learning without fine-tuning" designs converge on the same loop: store natural-language rules, retrieve them by situation, and inject them as constraints.

- MemPrompt prepends stored user feedback to similar future queries ([MemPrompt](https://arxiv.org/abs/2201.06009)).
- Reflexion stores verbal self-reflections ([Reflexion](https://arxiv.org/abs/2303.11366)).
- **ExpeL** manages insights with ADD/EDIT/UPVOTE/DOWNVOTE ([ExpeL](https://arxiv.org/abs/2308.10144)).
- ReasoningBank learns from failures too ([ReasoningBank](https://arxiv.org/abs/2509.25140)).
- PAHF updates memory from post-action feedback when preferences drift ([PAHF](https://arxiv.org/abs/2602.16173)).
- AdaMem learns memory-writing policies from feedback ([AdaMem](https://arxiv.org/html/2606.21144)).

**ACE supplies the key engineering rule** ([ACE](https://arxiv.org/abs/2510.04618)). Its playbooks gained +10.6% on agent benchmarks, and it identified "brevity bias" and "context collapse" as the failure modes of letting an LLM rewrite the whole rule list. The fix is incremental, itemized deltas.

**Leon's self-model supplies the guard against one-off overfitting.** It keeps a behavioural principle only if it was seen at least twice with confidence ≥ 0.72, and caps the list at 6 ([self-model-manager.ts](https://github.com/leon-ai/leon/blob/develop/server/src/core/self-model-manager.ts)). Hermes stages self-written skills behind `write_approval` ([Hermes curator](https://github.com/NousResearch/hermes-agent/blob/main/agent/curator.py)). Jarvis lets "explicit user corrections determine the supported claim, preserving its subject and temporal scope" ([jarvis graph.spec](https://github.com/isair/jarvis/blob/main/src/jarvis/memory/graph.spec.md)).

**Decision:** a `lessons` table with a structured trigger (mood, topic, person, time bucket), a situation embedding, imperative guidance, polarity, owner/inferred source, `seen_count`, confidence, helpful/harmful counters and lifecycle status. The rules:

- **Explicit corrections become `active` immediately.** This follows MemPrompt and jarvis.
- **Inferred lessons start as candidates.** They need ≥2 sightings and ≥0.72 confidence (Leon).
- **The LLM may only propose per-item operations.** Code applies them (ACE).
- **`LESSONS.md` is rendered from the table** and re-imported when Tejmul edits it.

### User model and persona: directives superseded in place, soul owned by Tejmul

Fourteen user-modeling sources and eleven persona sources were compared.

- **PrefEval** shows preference-following decays over long conversations, which argues for restating directives *near the query* ([PrefEval](https://arxiv.org/abs/2502.09597)).
- **HorizonBench and PersonaMem** show that stale preferences are the dominant failure ([HorizonBench](https://arxiv.org/abs/2604.17283); [PersonaMem](https://arxiv.org/abs/2504.14225)).
- **OpenClaw's USER.md contract** answers both. Each row is one imperative directive, annotated `observed: date | status: active`, and superseded in place under a small budget ([user-model.md](https://github.com/openclaw/openclaw/blob/main/docs/concepts/user-model.md)).
- **Hermes** caps `USER.md` at 1,375 characters and freezes the snapshot per session to protect the prompt cache ([Hermes memory](https://hermes-agent.nousresearch.com/docs/user-guide/features/memory)).
- **AIRI** does the opposite: it re-reads identity every run, so "a card edit reaches the next run" ([AIRI ADR](https://github.com/moeru-ai/airi/blob/main/docs/ai/adr/2026-10-10-skills-automations-and-memory.md)).
- **Weight-level persona (Character-LLM)** is rejected because it ties identity to one model ([Character-LLM](https://arxiv.org/abs/2310.10158)).
- **Khoj** is the only mature assistant already on Postgres + pgvector, with `UserMemory` and `Entry` models ([Khoj models](https://github.com/khoj-ai/khoj/blob/master/src/khoj/database/models/__init__.py)). Its schema is worth reading, but it is AGPL, so don't copy code.

**Decision:** `SOUL.md` stays a human-owned markdown file, read fresh each turn (AIRI rule). Stiti may only *propose* diffs, keeping OpenClaw's SOUL/AGENTS split between voice and operating rules ([soul.md](https://github.com/openclaw/openclaw/blob/main/docs/concepts/soul.md)). `USER.md` is rendered from a `user_directives` table, and facts about Tejmul's world live in the KG. Mem0's ADD/UPDATE/DELETE/NOOP decides how a new fact reconciles with an old one ([Mem0](https://arxiv.org/abs/2504.19413)). Omi-style confidence thresholds (0.5 / 0.85) decide which facts heard in ambient speech get stored ([Omi](https://github.com/BasedHardware/omi/tree/main/backend)).

### Embeddings: EmbeddingGemma now, Qwen3-Embedding if Hinglish recall disappoints

Thirteen embedders were compared.

- **Qwen3-Embedding-0.6B** has the best quality: MMTEB ≈64.3, 32K context, Apache-2.0, about 1.2 GB fp16 ([Qwen3-Embedding](https://arxiv.org/abs/2506.05176)).
- **EmbeddingGemma-300M** has the best quality per MB: MMTEB ≈61.2, 768-d with Matryoshka truncation, under 200 MB quantized by Google's claim ([Google](https://developers.googleblog.com/en/introducing-embeddinggemma/); scores via [fourweekmba](https://fourweekmba.com/ai-google-paper-embeddinggemma-2-trails-qwen-on-text-not-code/)).
- **bge-m3** trails at 59.56 ([codesota](https://codesota.com/tasks/text-embeddings)).
- **jina-v3** is non-commercial.

**Decision:** EmbeddingGemma-300M in-process (MLX or ONNX, no Ollama), stored as `halfvec(768)`, with `embed_model` recorded on every row and a background `reembed` job so the embedder is as swappable as the LLM. The same model serves memory, documents and MCP tool-RAG. Run a 200-query Hinglish recall test against Qwen3-Embedding-0.6B in week one. Switch only if the gap justifies about +1 GB.

### Context compiler: a graphify-style briefing, cached standing context plus per-turn deltas

No single paper defines a "context compiler". Eleven designs inform it:

- graphify's read-the-report-first workflow.
- OpenClaw's bootstrap injection and trigger-phrase injection (score ≥ 0.72, at most 3 per turn).
- Hermes's frozen snapshot.
- MemGPT's explicit context budget.
- Letta memory blocks.
- Sleep-time pre-compilation.
- PrefEval's "restate near the query".
- jarvis's deterministic, no-LLM **recall gate**, which skips memory enrichment when the hot window already answers the question ([recall_gate.spec](https://github.com/isair/jarvis/blob/main/src/jarvis/memory/recall_gate.spec.md)).
- AIRI's "index plus one entry per fact".
- LongMemEval's separate "reading" stage.
- OpenClaw's rule that recalled content is structurally marked so it is never re-extracted.

**Groq's free tier puts a hard number on the budget.** It allows **8K tokens per minute per model** ([Groq rate limits](https://console.groq.com/docs/rate-limits)). A 2K-token briefing therefore caps one model at about four voice turns a minute, which is why the briefing target is **≤1,500 tokens**.

**Decision:** a fixed briefing template (Engine v0). Standing context (who Tejmul is, active projects, open loops, active lessons) is precompiled nightly into `briefing_cache`. Each turn appends only retrieved memory, current facts, matched lessons and a filtered tool list. Directives and lessons sit *after* memory and immediately before the user's words. Recalled text is quoted and labeled as data.

## Laya decides, a thin router speaks through free clouds

### Laya: one forward pass answers every typed question about the moment

Stiti's "System 1" draws on eleven decision-layer designs:

- RouteLLM's strong/weak router ([RouteLLM](https://arxiv.org/abs/2406.18665)).
- Arch-Router-1.5B, which maps prompts to written policies and claims 93% routing accuracy, but under a research license at ~1 GB ([Arch-Router](https://arxiv.org/html/2506.16655v1)).
- Semantic Router's embedding match ([repo](https://github.com/aurelio-labs/semantic-router)).
- Home Assistant typed intents.
- OVOS Adapt/Padatious ([OVOS intents](https://openvoiceos.github.io/ovos-technical-manual/399-intents)).
- jarvis's recall gate.
- OpenClaw's deterministic gates.
- Leon's controlled mode.
- ProactiveBench's accept/reject reward model ([Proactive Agent](https://arxiv.org/html/2410.12361v3)).
- CoLabScience's small observer model that decides whether to speak ([CoLabScience](https://arxiv.org/pdf/2604.15588)).
- The Progent-style policy monitor.

Two findings stand out. **Independent router benchmarks find learned routers barely beat simple baselines.** RouterBench reports that "none of the routing algorithms significantly outperform the baseline Zero router" ([Stanford review](https://web.stanford.edu/~shuhuiq/blog/review-routing-cascades.html)), and LLMRouterBench finds many methods perform alike ([LLMRouterBench](https://web3.arxiv.org/pdf/2601.07206)). And **a small dedicated decision model** is the pattern recent proactivity work converges on.

**Laya fits that slot.** It is an encoder-only model (ModernBERT-large, 421M, English; or mmBERT-base, 322M, multilingual with 1,024 tokens). It answers `choice`, `score` and yes/no questions over one tokenized state in a single pass, with calibrated confidence and a `min_confidence` abstain ([Laya repo](https://github.com/NandhaKishorM/laya); [HF card](https://huggingface.co/convaiinnovations/laya)). Its weaknesses are documented:

- **Zero-shot accuracy is 0.36** on its own benchmark, against 0.77 after fine-tuning.
- **Accuracy falls as option lists grow.**
- **The only speed figures are vendor T4-GPU numbers:** 33 ms for one question and ~7 ms per question batched ([source tour](https://pyshine.com/laya-typed-decision-engine-source-tour/); [Menon Lab](https://themenonlab.blog/blog/laya-local-system-1-decision-model)).

**Decision:** Laya multilingual, run as ONNX INT8 in-process, makes one call per turn with the question set in Engine v0. Four rules govern it:

- **Keep option lists short.** Use a two-level intent: domain first, then action.
- **Hard thresholds gate side effects.** Fall back to the LLM or ask Tejmul below them.
- **Risk tiers and privacy floors are deterministic rules, not Laya outputs.**
- **Log every decision with its outcome**, so Phase 4 can calibrate Laya on Tejmul's own data. That is the one form of training Stiti allows.

**Reverse-engineer:** read `laya/agent.py` (abstention gate), `laya/common.py` (sequence builder) and the calibration code. Use rea's model-file inspection on the safetensors/ONNX files to confirm sizes and quantization before downloading onto the 8 GB Mac.

### LLM router: a custom fallback chain with quota accounting in Postgres

Fourteen gateway and router options were compared. LiteLLM's Router has everything Stiti needs: ordered fallbacks, a cooldown on the first 429, per-deployment RPM/RPD/TPD limits with `enforce_model_rate_limits`, and retries ([LiteLLM routing](https://docs.litellm.ai/docs/routing)). But **PyPI versions 1.82.7 and 1.82.8 shipped a credential stealer on 2026-03-24**, delivered by a `.pth` file that runs on every Python start ([LiteLLM advisory](https://docs.litellm.ai/blog/security-update-march-2026)). Merely installing an affected version is the risk.

The other options each lose on a specific point:

- **Portkey** adds a Node runtime.
- **Bifrost**'s rankings come from its own vendor.
- **OpenRouter's Auto Router** mostly picks paid models.
- **FrugalGPT, AutoMix and MixLLM** cascades add a full extra generation, which voice cannot afford ([FrugalGPT](https://arxiv.org/abs/2305.05176); [AutoMix](https://arxiv.org/abs/2310.12963); [MixLLM](https://arxiv.org/abs/2502.18482)).
- **The "Hybrid LLM" edge/cloud router** needs training data Stiti doesn't have yet ([Hybrid LLM](https://arxiv.org/abs/2404.14618)).

The free tiers set the order. Limits were fetched on 2026-11-10, and the notes warn they change often.

| Provider | Free limits | Privacy class allowed | Role |
|---|---|---|---|
| Groq | `gpt-oss-20b`, `gpt-oss-120b`, `qwen/qwen3.8-27b`: **30 RPM, 1K RPD, 8K TPM, 200K TPD each**; whisper-large-v3: 20 RPM, 2K RPD ([Groq](https://console.groq.com/docs/rate-limits)) | P0, P1 | Primary voice mouth (LPU latency) |
| Cerebras | `gpt-oss-120b`, `qwen-3.8-27b`: **5 RPM, 1M TPD** ([Cerebras](https://inference-docs.cerebras.ai/support/rate-limits)) | P0, P1 | Voice fallback; primary for night batch jobs |
| OpenRouter `:free` | **20 RPM, 50 RPD** (1,000 RPD only after $10 of lifetime credits, which breaks zero-cost) ([OpenRouter limits](https://openrouter.ai/docs/api/reference/limits)) | P0; P1 only on ZDR endpoints | Wide fallback |
| Mistral (free) | ~1 RPS, ~1B tokens/month (third-party); trains by default, opt-out available | P0; P1 after opt-out | Fallback |
| Gemini AI Studio | Flash ~5 RPM / **20 RPD**; Flash-Lite ~10–15 RPM / ~500 RPD (third-party, Oct 2026) ([imisofts](https://imisofts.com/blog/gemini-api-free-tier-limits/)) | **P0 only** | Non-personal jobs only |
| GitHub Models | **Retired 2026-07-30** ([GitHub changelog](https://github.blog/changelog/2026-08-09-github-models-is-now-retired/)) | n/a | Dropped |

The capacity math works for one person. Groq alone gives about 3,000 requests a day across its three models, Cerebras adds a million tokens, and a voice buddy needs a few hundred turns. **The binding limit is Groq's 8K TPM per model.** That limit is why the ≤1,500-token briefing and the no-LLM fast path both matter. The 27B model Tejmul asked about, Qwen3.8-27B, is available free through Groq and Cerebras. Running it locally is impossible at roughly 15–16 GB in 4-bit ([datanorth](https://datanorth.ai/news/alibaba-releases-qwen3-8-27b)).

**Decision:** a custom ~150-line router on the OpenAI-compatible client. It has no LiteLLM dependency; if LiteLLM is ever added, use its SDK only, pinned to ≥1.83 with `--require-hashes`.

- **Quota and cooldown accounting** lives in an `llm_usage` table, with cooldowns taken from `Retry-After`.
- **Two routes.** `voice_fast` and `background_smart`, order in Engine v0.
- **The privacy class filters providers** before the chain runs.
- **Total failure degrades, never breaks.** Laya's fast path still runs todos, alarms and recall, and Stiti says it "can't think deeply right now" (D8).

### Documents: route by file type, chunk by structure, contextualize in the cloud only when allowed

Eleven parsers and ten chunking strategies were compared.

- **Docling** produces structured output and has a HybridChunker. Its standard pipeline with the pypdfium backend peaks around **2.56 GB**, versus ~6.2 GB for the native backend ([Docling report](https://alphaxiv.org/overview/2408.09869v5)).
- **Docling is slow on an M2 CPU.** It took about 11 s per page with OCR ([Needl.ai](https://needl.ai/technical-notes/benchmarking-pdf-extraction-tools)).
- **The fast paths:** PyMuPDF4LLM at ~1.7 s/page (AGPL) and MarkItDown at 0.11 s/page for Office/HTML ([MarkItDown](https://github.com/microsoft/markitdown)).
- **Hard scans:** Granite-Docling-258M on MLX at about 7–8 s/page ([Docling VLM guide](https://www.mintlify.com/docling-project/docling/guides/vlm-models)).
- **Anthropic's Contextual Retrieval had the largest measured chunking gain.** Retrieval failure fell 35%, then 49% with BM25, then 67% with reranking ([Anthropic](https://www.anthropic.com/news/contextual-retrieval)). It costs one LLM call per chunk.
- **Late chunking** costs no LLM call but needs a long-context embedder, and EmbeddingGemma's 2K context is too short ([late chunking](https://arxiv.org/abs/2409.04701); [head-to-head](https://arxiv.org/pdf/2504.19754)).

**Decision (constraint-adjusted):** a Postgres work-queue table plus a type router: MarkItDown → PyMuPDF4LLM → Docling (pypdfium) on table-dense PDFs → Apple Vision OCR for scans. Docling runs only when the voice stack is idle. Chunks are 300–512 tokens with deterministic headers.

- **Cloud contextual-retrieval sentences only for P0/P1 documents**, as a Cerebras batch job.
- **Drop Chroma.**
- **Documents enter the KG the same way episodes do**, so document facts and life facts share one graph.

## Voice can reach about one second on an M2 if the LLM is the only cloud hop

### Orchestration and latency budget

Fifteen orchestration options were compared. **Pipecat** is the clear fit:

- MIT license.
- Silero VAD with `stop_secs=0.2` plus Smart Turn v3 is its default turn stack.
- Interruptions cancel in-flight LLM/TTS by default ([Pipecat docs](https://docs.pipecat.ai/guides/learn/speech-input)).
- At least four public Apple-Silicon reference repos exist.

The rejected options:

- **LiveKit Agents** needs a server.
- **TEN's turn model** is a 7B LLM.
- **Kyutai Unmute** needs a 16 GB CUDA GPU ([Apoorva87](https://github.com/Apoorva87/local-voice-agent)).
- **Vocode** looks stalled.

The best measured breakdown comes from an M5 Max: VAD stop 200 ms, STT 24–78 ms, Smart Turn 2–40 ms, LLM first token 312–353 ms and TTS first chunk 277–292 ms, for an **874 ms median** ([mthomas100](https://github.com/mthomas100/local-voice)). On an M4 Max, Apoorva87 measured 1.4–1.6 s. The same repo documents a practical lesson: running the model server at "Background" QoS stretched first-token time to 2.7–6.8 s, and Interactive priority fixed it.

With the LLM in the cloud, an M2 needs to host only speech models. This report estimates **0.9–1.6 s** voice-to-first-audio for LLM turns and about 0.6–0.9 s for fast-path turns. Fast-path turns skip the LLM and speak a templated sentence.

**Decision:** Pipecat 1.x with SmallWebRTCTransport, which gets browser echo cancellation for free. Four techniques push latency down:

- Start the cloud LLM call speculatively as soon as Smart Turn says "complete".
- Keep a pre-rendered filler bank in Kokoro's voice ("hmm", "acha", "ek sec, dekhta hoon…").
- Keep every model warm (`HF_HUB_OFFLINE=1`, preload at login).
- Run at Interactive QoS.

Copy mthomas100's per-stage instrumentation. **Reverse-engineer:** read the Python source of kwindla/macos-local-voice-agents, Apoorva87 and HF speech-to-speech. rea isn't needed.

### VAD and turn-taking: tuned for Hinglish pauses

Fifteen VAD and turn detectors were compared.

- **Silero VAD** costs about 2 MB and under 1 ms per chunk, with FLEURS F1 95%.
- **Smart Turn v3.1** is 8M params and 8 MB int8, takes ~12 ms on CPU, covers 23 languages including Hindi, and is BSD-2 licensed ([Daily v3 blog](https://www.daily.co/blog/announcing-smart-turn-v3-with-cpu-inference-in-just-12ms/)). It still **cut off 32 of 80 mid-sentence pauses** in a real deployment. The shipped fix was a 2.0 s silence fallback ([mthomas100](https://github.com/mthomas100/local-voice)).
- **LiveKit's text detector** reports Hindi TPR of 99.4%, but it needs transcripts and ~400 MB ([LiveKit blog](https://livekit.com/blog/improved-end-of-turn-model-cuts-voice-ai-interruptions-39)).
- **A community smart-turn-hinglish fine-tune** reaches only 72.4% balanced accuracy ([HF](https://huggingface.co/abhishek-040010/smart-turn-hinglish)).
- **Easy Turn** adds a "backchannel" state that is exactly right for "haan/hmm" ([Easy Turn](https://arxiv.org/pdf/2509.23938)).

**Decision:** Silero (stop 0.2 s) plus Smart Turn v3.1, with an adaptive 1.2–2.0 s fallback. A cheap text rule extends the wait when the transcript ends in a filler or conjunction ("matlab…", "aur…", "toh…"). Later, fine-tune Smart Turn on Tejmul's own recordings.

### STT: Whisper-family is the only local option that hears Hindi mid-sentence

Nineteen STT models were compared. The English-only speed leaders cannot transcribe Hinglish:

- Parakeet TDT v3: 117× realtime, 0.9 GB.
- Moonshine v2: 107 ms streaming.
- Kyutai STT.
- SenseVoice.

All of them lack Hindi ([soniqo](https://soniqo.audio/benchmarks); [Moonshine v2](https://arxiv.org/html/2602.12241v1)). The candidates that do handle Hindi:

| Candidate | Size / speed | Hindi / Hinglish quality |
|---|---|---|
| WhisperKit / mlx-whisper large-v3-turbo | ~0.4 GB RSS; ~245 ms per turn on an M4 Max | Multilingual Whisper |
| Oriserve Whisper-Hindi2Hinglish-Apex (Apache-2.0) | Not stated | Roman-script output; WER 29.8 on FLEURS, 47.6 on Indic-Voices against transliterated references ([Apex](https://huggingface.co/Oriserve/Whisper-Hindi2Hinglish-Apex)) |
| Qwen3-ASR 0.6B | ~1 GB | FLEURS-Hindi WER 18.6–25.9% |

**Personal fine-tuning is the biggest lever.** A community LoRA cut Whisper-small from 71% to 17% WER on Hinglish ([Hinglish LoRA](https://github.com/catherine621/Hinglish-Speech-Recognition-Whisper-Fine-tuning-and-Quantization)). Fine-tuning a speech model is allowed: it is not the LLM. Whisper's default text normaliser understates Indic WER by about 18 points, so cross-paper comparisons are unreliable ([indic-asr-eval](https://github.com/Shekhar-Jha22/indic-asr-eval)).

**Decision:** mlx-whisper large-v3-turbo q4, run per turn after Smart Turn fires, so it hides inside the turn hold. In week one, run a 30-minute A/B on Tejmul's own speech against Apex and Qwen3-ASR 0.6B. Groq whisper-large-v3 is the free fallback for long or noisy audio: 28,800 audio-seconds a day ([eesel](https://www.eesel.ai/blog/groq-pricing)).

### TTS: Kokoro for speed, emotion through voice, speed and wording

Sixteen TTS models were compared. **Kokoro-82M** wins on the latency/quality/RAM balance:

- About 170 MB as CoreML.
- 74 ms sentence synthesis on Apple GPU.
- Round-trip WER 3.90% and UTMOS 4.44 ([soniqo](https://soniqo.audio/benchmarks)).
- Apache-2.0, with Hindi among mlx-audio's languages ([mlx-audio](https://github.com/Blaizzy/mlx-audio)).

The emotion-capable models all lose on one point:

- **Qwen3-TTS 0.6B** has 9.7–15.6% round-trip WER and artefacts.
- **Chatterbox** was "retired research, no longer maintained" as of August 2026 and watermarks its output ([Chatterbox](https://github.com/resemble-ai/chatterbox)).
- **Indic Parler-TTS** is 0.9B with no latency data ([Indic Parler](https://huggingface.co/ai4bharat/indic-parler-tts)).

Two practical traps: mlx-audio's player buffers about 1.5 s before playback ([kokoro-tts](https://github.com/scottschram/kokoro-tts)), and leading silence of 0.4–0.9 s must be trimmed.

**Decision:** Kokoro streamed per sentence, bypassing the mlx-audio buffer. Mood sets the voice preset and speed: slower and softer when Tejmul is tired or sad. Pocket TTS (MIT, ~100M) is an optional expressive second voice later.

### Barge-in and full duplex: engineer it in the cascade

Thirteen full-duplex and barge-in systems were compared. True duplex models do not fit: Moshi's q4 MLX checkpoint alone is 4.8 GB ([Moshi](https://arxiv.org/html/2410.00037v1)), and PersonaPlex needs about 6.4 GB. Full-Duplex-Bench also shows fast duplex models often interrupt users prematurely ([FDB v1.5](https://arxiv.org/pdf/2507.23159)).

**Decision:** "duck-then-confirm" barge-in. Pause playback on the first speech frame, which mthomas100 measured at a 72 ms median. Stop TTS and cancel the LLM stream only after Silero confirms 200–250 ms of non-backchannel speech. This reproduces the measured ~240–270 ms stop latency without the false interruptions from coughs. Echo cancellation through WebRTC is mandatory on laptop speakers.

### Wake word

Twelve wake-word engines were compared.

- **LiveKit WakeWord v2** is about 7 MB, takes ~1 ms per 80 ms step and trains with one command. Its vendor reports 0.08 false accepts per hour against openWakeWord's 8.50 ([LiveKit blog](https://livekit.com/blog/livekit-wakeword)).
- **Porcupine** is commercial, quoted from $6,000/yr ([micdrop](https://micdrop.dev/blog/wake-word-detection-web-app)).

**Decision:** LiveKit WakeWord v2 for "Hey Stiti", openWakeWord as fallback, plus a hotkey and a 30-second "conversation mode" after each reply. Validate false accepts against an hour of Tejmul's own TV and Hinglish background audio.

### Emotion detection: a soft, personally calibrated, fused signal

Eighteen emotion sources were compared, and the evidence says to be humble.

- **Real-world accuracy is low.** Naturalistic 8-class SER peaks around **41% accuracy** in the INTERSPEECH 2025 challenge, even for trimodal systems ([MEDUSA/IS2025](https://arxiv.org/pdf/2506.09556)). Vox-Profile's categorical score is 0.392 ([Vox-Profile](https://arxiv.org/html/2505.14648)).
- **Personal calibration is the biggest gain.** Speaker-dependent recognition reaches **81.9% vs 55.1%** speaker-independent ([ICASSP 2012](http://www2.ee.unsw.edu.au/~speechgroup/vidhya/pdf/icassp12.pdf)). A 2026 audit warns that normalization gains are overstated when statistics leak from test data ([Beyond Accuracy](https://arxiv.org/html/2610.33952)).
- **Speech plus text beats either alone** ([MemoCMT](https://www.nature.com/articles/s41598-025-89202-x)).
- **emotion2vec+ base** is the best small model: ~90M params, 9 classes, trained on 4,788 h of pseudo-labelled data, MIT code ([emotion2vec](https://github.com/ddlBoJack/emotion2vec)).
- **audeering's valence/arousal model** is CC-BY-NC-SA. That is acceptable for personal use, but flag it ([audeering](https://huggingface.co/audeering/wav2vec2-large-robust-12-ft-emotion-msp-dim)).

**Decision:** emotion2vec+ base runs asynchronously on each finished user turn, in parallel with STT. It is fused with three other signals: Laya's `text_emotion`, simple prosody features (energy, pitch variance, speech rate from Whisper word timestamps), and a rolling per-user baseline that flags z-score deviations. The signal is smoothed with an exponential moving average over 2–3 turns.

- **"Stressed" and "tired" are derived states**, not native classes.
- **The briefing carries a hint with confidence** ("voice: tense 0.62"). Stiti never declares "you are angry".
- **Tejmul's denials ("main gussa nahi hoon") are stored as labels** for later calibration.

## Life management: rank transparently, nudge rarely, never shame

### Todos: Taskwarrior semantics plus TMT avoidance risk, computed by Laya

Twelve task systems and models were compared. No open-source tool combines task storage, explainable ranking and voice.

- **Taskwarrior's urgency** is "a simple sum of terms, each weighted by a configurable coefficient", for example `+next` 15.0, due 12.0 and priority H/M/L 6.0/3.9/1.8. It is transparent and explainable ([Taskwarrior urgency](https://taskwarrior.org/docs/urgency/)).
- **Temporal Motivation Theory** adds what Taskwarrior lacks. Motivation = E×V / (1 + I×D), so it predicts which tasks Tejmul will *avoid* ([TMT](https://en.wikipedia.org/wiki/Temporal_motivation_theory)). Steel's meta-analysis of 691 correlations identifies task aversiveness, delay, self-efficacy and impulsiveness as the strong predictors ([Steel 2007](https://prism.ucalgary.ca/handle/1880/47914)).
- **Vikunja and Super Productivity** add a server or Electron process.
- **Apple Reminders through EventKit** reaches the iPhone for free ([EKReminder](https://developer.apple.com/documentation/eventkit/ekreminder.md)).

**Decision (constraint-adjusted from SQLite to Postgres):** a `tasks` table with Taskwarrior fields plus `energy`, `context`, `value`, `expectancy`, `aversiveness`, `done_when` and `if_then`. Laya computes `urgency = Σ coef·term`. The terms are due proximity, scheduled, age, blocking/blocked, value, energy fit and `avoidance_risk = 1 − sigmoid(E·V/(1+I·D))`. Coefficients live in config and adjust slightly from accept/skip feedback. The LLM never ranks.

- **Voice output is the top 3 only**, each explained by its two largest terms.
- **Tasks with a time are mirrored to Apple Reminders.**
- The TMT parameterization is an engineering inference. No validated software operationalization exists.

### Scheduling: CP-SAT plans a day in tens of milliseconds on this M2

Fourteen schedulers were compared:

- **CP-SAT** (Apache-2.0) has native optional intervals and `AddNoOverlap`, and it is anytime: it returns the best plan found within the time limit ([OR-Tools](https://developers.google.cn/optimization/cp?hl=en)).
- **An independent benchmark of 9,000+ instances** found it "highly competitive" with commercial CP Optimizer ([arXiv 2502.13483](https://web3.arxiv.org/pdf/2502.13483)).
- **Timefold's Python repo** was archived in October 2025 ([repo](https://github.com/TimefoldAI/timefold-solver-python)).
- **FluidCalendar, Clock Panda and Reclaim** are UX references only.

The productivity researcher benchmarked CP-SAT on this Mac (OR-Tools 9.15) with 5-minute slots, fixed events and energy windows:

- 12 tasks solved to proven optimality in **0.01–0.06 s**.
- 20 tasks in 0.23–2.6 s.
- An over-full 50-task day reached a 7–11% gap at 2 s.
- Peak RSS was about 113 MB.

That is a local single-machine test with three seeds per configuration, not a published benchmark.

**Decision:** Laya pre-filters the top 10–20 tasks by urgency, then CP-SAT runs.

- **Hard constraints:** no-overlap with calendar events, buffered meetings, dependencies, and a cap at 70–80% of free time.
- **Soft objective:** value, lateness, peak-energy fit, context switches, and avoidance-risk tasks early in the day.
- **Time limits:** 1 s interactive, 5 s overnight.
- **Re-planning** uses `solution_hint` and a stability penalty so the plan doesn't churn.
- **Greedy earliest-deadline-first** is the timeout fallback.

### Goal breakdown: a lazy, four-phase Socratic Chunker

Thirteen sources were compared. The planning side:

- **ADaPT** decomposes recursively only when a step isn't directly doable, which avoids over-planning ([ADaPT](https://ar5iv.labs.arxiv.org/html/2311.05772)).
- **ChatHTN** asks an LLM for a decomposition only when the symbolic planner has no method ([ChatHTN](https://api.emergentmind.com/topics/chathtn-planner)). That matches "Laya decides".
- **BabyAGI-style loops** let the LLM generate and rank unbounded tasks. They are the anti-pattern here.

The coaching evidence is real but modest:

- **A CHI 2026 RCT (N=543)** found that "the feedback mechanism significantly enhances goal quality, whereas the impact of adaptive suggestions is limited" ([Schimpf et al.](https://arxiv.org/abs/2602.08636)).
- **An AI career-coach RCT (N=517)** found d = 0.33 on goal progress, mediated by *perceived accountability*. It showed no gain over a structured written questionnaire ([career coach RCT](https://arxiv.org/html/2603.17887v1)).
- **Implementation intentions shrink under scrutiny.** The original estimate of d = 0.65 falls to about 0.15 after bias correction in a 2024 update (secondary source) ([Gollwitzer & Sheeran](https://kops.uni-konstanz.de/entities/publication/2e749bfb-8533-437c-8203-7e788c910c5f); [2024 summary](https://idtips.substack.com/p/implementation-intentions-the-science)).

**Decision (constraint-adjusted):** four short voice phases. Each runs as a cloud LLM call with a JSON schema, and Laya validates every step.

1. **Clarify "done".** Give explicit feedback on goal quality.
2. **WOOP.** Wish, outcome, obstacle, plan.
3. **Lazy split.** Propose only the next 1–3 children and ask "could you start this in under 10 minutes?" until a 2–25-minute first action appears. Depth is at most 4.
4. **Anchor.** Turn the first leaf into an if-then plan with a scheduled check-in. Accountability is the active ingredient.

The tree lives in `tasks.parent_id`. Offline, Stiti asks the same four fixed questions without generated suggestions.

### Habits: strength and fading cues, not spaced repetition

Thirteen sources were compared. They show SM-2 and FSRS model *memory decay* and schedule ever-wider gaps. Habits need consistent, cue-linked repetition.

- **Formation time is long and variable.** Habit formation took a median of 59–66 days, with a range of 4–335 days, and only 23% of people reached the threshold ([Singh et al. 2024](https://www.sciencedaily.com/releases/2025/01/250124151347.htm); [Lally](https://www.surrey.ac.uk/news/does-it-really-take-66-days-form-habit-we-asked-expert-dr-pippa-lally)).
- **Reminders backfire.** "Reminders increased repetition but hindered habit development", while event-based cues increased automaticity ([Stawarz et al.](https://discovery.ucl.ac.uk/id/eprint/1468224/)).
- **Broken streaks cost motivation.** Framing the same behaviour as a broken streak cut continuation from 66% to 58%, and offering a repair blunted the drop ([Silverman & Barasch](https://udel.edu/udaily/2024/march/power-of-streaks-motivation-jackie-silverman)).
- **Loop Habit Tracker** uses an exponentially smoothed "habit strength" that a few misses don't erase ([uhabits](https://github.com/iSoron/uhabits)).
- **FSRS** remains right for genuine learning items ([py-fsrs](https://pypi.org/project/fsrs)).

**Decision:** habits are rows with an anchor cue, an if-then plan, a "2-minute version", and strength updated by `s ← s + α(done − s)` with α ≈ 0.05–0.07. α is a suggested starting value to tune.

- **Prompts fade with strength.** Prompt at the cue below 0.6, check at end of day above 0.6, check weekly above 0.8, and restore cue prompts below 0.4.
- **Report "X of the last 14 days", never streaks.** Offer repair tokens after a miss.
- **Offer restarts on fresh-start landmarks** ([Dai et al.](https://faculty.wharton.upenn.edu/wp-content/uploads/2014/06/Dai_Fresh_Start_2014_Mgmt_Sci.pdf)).
- **Never promise "21 days".**

FSRS is reserved for vocabulary and facts Tejmul wants to learn.

### Motivation psychology becomes four Laya modules

Twenty-two psychology sources were compared. They map onto four modules.

**WOOP/MCII is the goal script.** Its effect is reliable but small: g = 0.336 across N = 15,907 ([Wang et al.](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC8149892/)).

**TMT is the diagnostic.** Stiti nudges the weakest of four terms:

| Weak term | Nudge |
|---|---|
| Low expectancy | Shrink the step |
| Low value | Reconnect to the "why" |
| High delay | Set a near mini-deadline |
| High impulsiveness | Add an if-then plan |

**Cognitive load sets the speech budget.**

- **At most 3 items per turn.** Working memory holds about 3–5 chunks ([Cowan](https://www.cambridge.org/core/services/aop-cambridge-core/content/view/44023F1147D4A1D44BDC0AD226838496/S0140525X01003922a.pdf/magical_number_4_in_shortterm_memory_a_reconsideration_of_mental_storage_capacity.pdf)), and Google's voice guidance follows the "rule of three" ([Google Design](https://design.google/library/rule-of-three)).
- **One decision per turn.**
- **About 8–20 seconds of speech.**
- **User-paced "next".** Learner-paced segmenting has a median d = 0.79.
- **Skip confirmation sub-dialogues for low-stakes actions.** Wolters et al. found fewer turns can beat fewer items.

**Self-compassion sets the tone.**

- Self-forgiveness after procrastinating predicted less procrastination next time ([Wohl et al.](https://bps.org.uk/research-digest/cure-procrastination-forgive-yourself)).
- Self-compassion after failure *increased* motivation to improve ([Breines & Chen](https://static1.squarespace.com/static/50f6f441e4b08191027c661d/t/51663d46e4b060cd9194ed75/1365654854068/Breines+&+Chen+2012+PSPB.pdf)).
- Self-compassion RCTs show g = 0.75 ([Ferrari et al.](https://acuresearchbank.acu.edu.au/item/87545/self-compassion-interventions-and-psychosocial-outcomes-a-meta-analysis-of-rcts)).

**Decision:** a post-generation "speech linter" runs between the LLM and TTS. It does four things:

- **Enforces the CLT budget:** trims to 3 items and appends "aur sunna hai?" (want to hear more?).
- **Blocks guilt words:** "failed", "broke your streak", "behind", "should have", "overdue". Their replacements are "still open" and "carried over".
- **Proposes parking the backlog** for tasks carried over more than 7 days.
- **Switches to a "minimum viable day" of 1–3 tasks** when Stiti detects stress.

### Proactive nudges: a budgeted gate, learned per user

Sixteen proactivity sources and twelve assistant implementations were compared.

- **LLMs over-intervene.** They act "more frequently and earlier than humans" ([Overassist](https://arxiv.org/html/2607.21306)), and Pare-Bench scores proposal rate as "lower is better" ([Pare-Bench](https://arxiv.org/html/2604.00842v1)).
- **Timing matters.** Interrupting at task breakpoints lowers the cost ([Iqbal & Bailey](https://www.interruptions.net/literature/Iqbal-TOCHI10.pdf)).
- **Receptivity needs content** that is interesting, relevant and actionable ([Mehrotra et al.](https://discovery.ucl.ac.uk/1502364/1/CHI16.pdf)).
- **Notifications have no long-term payoff.** In a micro-randomized trial they raised short-term opening but made **no difference in time to disengagement** ([Drink Less MRT](https://mhealth.jmir.org/2023/1/e38342/PDF)).
- **Intentions must be compiled out of the LLM.** TriggerBench shows LLMs forget to act on stored intentions as context grows ([TriggerBench](https://arxiv.org/abs/2606.23459)).
- **Implementation patterns to copy:**
  - OpenClaw's standing intents: lifecycle states, 24 h cooldown, 3 fires, 90-day expiry, at most 3 per turn ([standing-intents.md](https://github.com/openclaw/openclaw/blob/main/docs/concepts/standing-intents.md)).
  - Leon's pulse: a 2-minute grace during active conversation, and the rule "Proactive work must not displace an owner task waiting to resume" ([pulse-manager.ts](https://github.com/leon-ai/leon/blob/develop/server/src/core/pulse-manager.ts)).
  - AIRI's code-decided return-from-idle trigger.

**Decision:** a Laya "Nudge Gate".

- **Score:** `relevance × actionability × urgency × receptivity − annoyance − habituation`.
- **Budget:** 3–5 unsolicited spoken nudges a day. User-set alarms are never suppressed.
- **Modality ladder:** log → menu-bar badge → banner → voice → alarm.
- **Learning:** log `(context, action, outcome)` so a small contextual bandit can learn Tejmul's receptivity, an n-of-1 micro-randomized trial ([JITAI/MRT](https://arxiv.org/pdf/2107.03544)).
- **Rituals:** a morning plan and an evening wins-first review are user-invited, so they don't count against the budget.

### Alarms and reminders: three layers so nothing depends on Stiti being awake

Fourteen macOS mechanisms were compared.

1. **EventKit reminders** with `EKAlarm`, written via PyObjC, live in Apple's store. They ring on Mac, iPhone and Watch even if Stiti has crashed ([EKAlarm](https://developer.apple.com/documentation/eventkit/ekalarm.md); [PyObjC template](https://glama.ai/mcp/servers/@pongsapakl/mcp-reminders/blob/4208caee7acba410ee5126ad46bdd7962aba82b0/src/mcp_reminders/reminders.py)).
2. **A launchd LaunchAgent** keeps the daemon alive. It **cannot wake a sleeping Mac**, and it coalesces missed jobs into one run on wake ([Apple forum](https://developer.apple.com/forums/thread/815034)).
3. **`pmset schedule wake`** is the only way to wake the Mac for a spoken alarm. It needs sudo.

**Decision (constraint-adjusted):** durable alarms go to EventKit. Spoken alarms and check-ins live in the Postgres `intents` table, read by an in-process scheduler. On wake, Laya reconciles missed jobs and drops stale nudges. `pmset` is optional for a spoken morning brief. Shortcuts is used only for Focus toggles.

## Connectors: MCP is the bus, Laya is the gatekeeper

### MCP client and tool selection

The current MCP spec is **2026-07-28**:

- The core is stateless: no initialize handshake, no session ID.
- `tools/list` results are cacheable, which makes hash-pinning tool descriptions practical.
- Multi Round-Trip Requests replace server-initiated elicitation, which suits voice confirmations.
- Sampling and Roots are deprecated ([MCP blog](https://blog.modelcontextprotocol.io/posts/2026-07-28/)).

`pip install mcp` now installs SDK v2, whose `ClientSessionGroup` manages many servers ([SDK v2](https://py.sdk.modelcontextprotocol.io/v2/client/session-groups/)).

Thirteen tool-selection approaches were compared. They agree on "tool RAG": embed the tool descriptions and expose only the top few each turn.

- **RAG-MCP** "more than triples" selection accuracy ([RAG-MCP](https://arxiv.org/abs/2505.03275)).
- **MCP-Zero** reports ~98% token reduction ([MCP-Zero](https://arxiv.org/abs/2506.01056)).
- **Semantic Tool Discovery** reaches 97.1% hit@3 over 121 tools in under 100 ms ([arXiv 2603.20313](https://arxiv.org/abs/2603.20313)).
- **ToolRet** warns that generic embedders are weak at tool retrieval, around 33.8 nDCG@10 ([ToolRet](https://arxiv.org/pdf/2503.01763)).

**Decision:** an `mcpServers` JSON config is the plug-in point.

- **Transports:** stdio for local servers; streamable HTTP only for hosted servers.
- **Tool selection:** Laya's `tool_category` picks the server, the shared embedder plus BM25 picks the top 5 tools, and 3–5 tools are always on (time, memory.search, notify, confirm).
- **Each tool gets hand-written "when to use" examples.**
- **Stiti is also an MCP server**, built with FastMCP 3, so Claude Code can query Tejmul's preferences.

### Which connectors to plug in first

Thirteen connector servers were compared, plus thirteen Mac-control mechanisms, thirteen phone channels and ten browser/search options.

| Need | Pick | Free? | Notes |
|---|---|---|---|
| Gmail, Calendar, Drive | `uvx workspace-mcp --tools gmail calendar drive`, core tier, own GCP OAuth client ([workspace-mcp](https://glama.ai/mcp/servers/%40taylorwilsdon/google_workspace_mcp)) | Yes | Google's official servers are still developer preview |
| Apple Calendar, Reminders | Stiti's own ~150-line FastMCP + PyObjC EventKit server (or iMCP) ([iMCP](https://github.com/mattt/iMCP)) | Yes | Keep EventKit in-process for TCC |
| Files | Official filesystem server, allowlisted folders, read-only by default | Yes | — |
| GitHub | Official server with `--read-only --lockdown-mode` | Yes | Lockdown is best-effort |
| Phone | Telegram Bot API (long-polling, own chat_id only) + ntfy one-way push + iCloud Reminders ([ntfy](https://docs.ntfy.sh/faq/)) | Yes | Avoid WhatsApp bridges: ToS and ban risk, and the main project has been unmaintained since Jul 2025 ([dragapp](https://www.dragapp.com/blog/whatsapp-mcp-server/)) |
| Web search | Self-hosted SearXNG + `searxng-http-mcp` ([mcp-searxng](https://mcpservers.org/zh-CN/servers/ihor-sokoliuk/mcp-searxng)) | Yes | Brave dropped its free tier in Feb 2026 ([implicator](https://www.implicator.ai/brave-drops-free-search-api-tier-puts-all-developers-on-metered-billing.md)) |
| Browser actions | Playwright MCP, started on demand, logged-out profile ([comparison](https://mcp.directory/blog/chrome-devtools-mcp-vs-playwright-mcp-2026)) | Yes | Never attach to the real Chrome profile |
| Mac control | Allowlisted osascript tools (`set_volume`, `open_app`, `now_playing`); no generic AppleScript runner | Yes | — |

Packaging matters more than it looks. macOS attributes microphone and Reminders permissions to a "responsible" app bundle. A bare `python` launched by launchd can lose that attribution and record silence ([Apple forum 805245](https://developer.apple.com/forums/thread/805245)). **Decision:**

- **Ship Stiti as a signed `Stiti.app`** built with py2app: a `LSUIElement` menu-bar app with `NSMicrophoneUsageDescription` and the Reminders/Calendars full-access usage strings.
- **Launch it as a Login Item, or as a LaunchAgent that execs the app binary.**
- **Capture the mic in-process.**
- **Use desktop-notifier for UN notifications.** It requires a signed executable ([desktop-notifier](https://desktop-notifier.readthedocs.io/en/latest/)).

### Security: Laya is the policy monitor that stronger models are not

Seventeen incidents and defenses were compared. The threats are real:

- Invariant Labs showed a poisoned tool description hijacking WhatsApp sends ([Invariant](https://invariantlabs.ai/blog/whatsapp-mcp-exploited)).
- A malicious GitHub issue leaked private repo data through a "toxic flow" ([Invariant](https://invariantlabs.ai/blog/mcp-github-vulnerability)).
- **ClawHavoc** found **341 of 2,857 ClawHub skills malicious**, many installing the AMOS stealer on macOS ([The Hacker News](https://thehackernews.com/2026/02/researchers-find-341-malicious-clawhub.html)).
- **MCPTox** measured a 72.8% attack success rate on o1-mini and found that *more capable models were often more susceptible* ([MCPTox](https://arxiv.org/abs/2508.14925)).

So the model cannot be the defense. **CaMeL's split** works by design: a privileged planner sees only trusted input, a quarantined parser handles untrusted data, and capabilities block exfiltration ([CaMeL](https://arxiv.org/abs/2503.18813)).

**Decision:** six controls.

1. **Pin and diff.** Hash each server's command, version and `tools/list`, and disable the server on any change until Tejmul re-approves.
2. **Risk tiers in Stiti's own config:** read, local-write, external/irreversible. The last tier always needs a spoken or Telegram-button confirmation that shows the exact arguments.
3. **Taint after untrusted reads.** After any untrusted-content tool runs, Laya marks the context tainted, and outbound tools then need confirmation.
4. **Quarantined summarization of tool output.**
5. **No hub installs.** Pin versions, run `mcp-scan --local-only` ([mcp-scan](https://invariantlabs.ai/blog/introducing-mcp-scan)), and treat "paste this into Terminal" as malware.
6. **Secrets live in the Keychain**, never in context.

## Feature decisions at a glance

| Feature | Compared (from notes) | Reuse | Build in Stiti | rea / source study | Final decision |
|---|---|---|---|---|---|
| Overall architecture | 13 | OpenClaw gates & provenance, CoALA vocabulary | Python daemon + Postgres brain | rea: OpenClaw dist subsets; read Hermes, jarvis | Brain = Postgres engine; LLM = plug |
| Episodic memory | 12 | Generative Agents score, LongMemEval keys | `episodes`, `segments` | read nxlabscc | Verbatim, never deleted |
| Hybrid retrieval | 12 | Supabase RRF SQL | `recall()` function | — | Vector + `simple` FTS + RRF + priors + 1–2 hop facts |
| Temporal KG | 12 (+17 PG options) | Graphiti bitemporal model | `entities`, `facts`, exclusion constraint | read Graphiti source | Recursive CTEs; no AGE |
| Consolidation | 12 | Sleep-time compute, OpenClaw dreaming gates | Nightly job chain | rea: `dreaming-*` chunks | Cerebras/Groq batch, P2 excluded |
| Lessons | 14 + 14 | ACE deltas, ExpeL votes, Leon gate | `lessons` + `LESSONS.md` view | rea: Leon self-model; read Hermes curator | Owner corrections active at once |
| User model / persona | 14 + 11 | OpenClaw USER.md contract, AIRI no-snapshot | `user_directives`; `SOUL.md` file | read Khoj models (AGPL) | Directives near query |
| Embeddings | 13 | EmbeddingGemma-300M | `embed_model` column + re-embed job | rea: inspect model files | One shared in-process embedder |
| Context compiler | 11 (assembled) | graphify report, jarvis recall gate | Briefing template + cache | — | ≤1,500 tokens |
| Decision layer (Laya) | 11 (assembled) | Laya, HA typed intents | Question set + decision log | read `laya/agent.py` | Laya multilingual INT8, gated |
| LLM router | 14 + 11 providers | OpenAI-compatible SDK | ~150-line router + `llm_usage` | — | Groq → Cerebras → OpenRouter → Mistral; Gemini P0 only |
| Documents | 11 + 10 | MarkItDown, PyMuPDF4LLM, Docling | Queue + chunker | — | Cloud context only for P0/P1 |
| Voice orchestration | 15 | Pipecat | Pipeline + instrumentation | read kwindla/Apoorva87/mthomas100 | Pipecat + SmallWebRTC |
| VAD / turn | 15 | Silero, Smart Turn v3.1 | Filler-aware fallback | — | 1.2–2.0 s adaptive |
| STT | 19 | mlx-whisper | A/B harness | — | Whisper turbo; personal LoRA later |
| TTS | 16 | Kokoro-82M | Sentence streamer, filler bank | — | Kokoro; mood → preset/speed |
| Barge-in | 13 | mthomas100 pattern | Duck-then-confirm | — | WebRTC AEC mandatory |
| Wake word | 12 | LiveKit WakeWord v2 | Custom "Hey Stiti" | — | Plus hotkey + conversation mode |
| Emotion | 18 | emotion2vec+ base | Fusion + personal baseline | — | Hint with confidence, never a verdict |
| Todos | 12 | Taskwarrior formula, TMT | `tasks` (Postgres) | — | Laya urgency, top 3 spoken |
| Scheduling | 14 | OR-Tools CP-SAT | ~200-line model | — | 1 s interactive limit |
| Goal breakdown | 13 | ADaPT, WOOP | 4-phase chunker | — | Lazy split, accountability check-in |
| Habits | 13 | Loop strength idea | `habits` + fading prompts | — | No SR, no streaks |
| Psychology / speech | 22 | CLT, self-compassion | Speech linter | — | ≤3 items, no guilt words |
| Proactive nudges | 16 + 12 | OpenClaw intents, Leon pulse | Nudge Gate + bandit log | rea: Leon pulse, AIRI automations | 3–5/day budget |
| Alarms | 14 | EventKit, launchd | `intents` + EventKit mirror | — | Durable alarms in Apple's store |
| MCP + tool-RAG | 13 | mcp v2 SDK, FastMCP 3 | Config bus + tool index | rea: Node MCP servers before install | Top-5 tools per turn |
| Connectors / phone | 13 + 13 + 10 | workspace-mcp, Telegram, SearXNG | EventKit server | rea: apple-mcp, Peekaboo | Telegram + ntfy; no WhatsApp |
| Security | 17 | CaMeL ideas, mcp-scan | Pin-and-diff, taint, tiers | — | Confirmation for irreversible actions |

## Engine v0 build spec: the minimal brain to build tonight

Engine v0 is text-only Phase 1 of `docs/PLAN.md`. Its "done" test: after a restart, and after swapping the LLM, Stiti still remembers last week and lists todos instantly. Voice plugs into the same `turn()` entry point later.

Everything below follows the decisions above. Two kinds of numbers appear:

- **Starting thresholds and weights** are this report's engineering defaults. Calibrate them against the decision log.
- **Provider limits** come from the provider pages cited earlier and must be re-checked in each console.

### Install and schema (14 tables)

Install with `brew install postgresql@18 pgvector`, then `createdb stiti`, following D6. If the Homebrew `pgvector` formula doesn't match PG 18, fall back to Postgres.app, which bundles pgvector and btree_gist ([Postgres.app extensions](https://postgresapp.com/extensions/)). Apply the 8 GB tuning: `shared_buffers=256MB`, `effective_cache_size=1GB`, `work_mem=16MB`, `maintenance_work_mem=256MB`, `max_connections=20`.

```sql
CREATE EXTENSION IF NOT EXISTS vector;      -- pgvector >= 0.8 (halfvec, iterative scans)
CREATE EXTENSION IF NOT EXISTS btree_gist;  -- equality inside GiST exclusion constraints
CREATE EXTENSION IF NOT EXISTS pg_trgm;     -- fuzzy names / Hinglish spelling variants

-- 1. sessions
CREATE TABLE sessions (
  id          bigserial PRIMARY KEY,
  channel     text NOT NULL CHECK (channel IN ('voice','text','telegram')),
  started_at  timestamptz NOT NULL DEFAULT now(),
  ended_at    timestamptz
);

-- 2. episodes: immutable ground truth, one row per utterance, never deleted
CREATE TABLE episodes (
  id               bigserial PRIMARY KEY,
  session_id       bigint REFERENCES sessions(id),
  speaker          text NOT NULL CHECK (speaker IN ('user','stiti','tool','system')),
  origin           text NOT NULL DEFAULT 'owner'
                   CHECK (origin IN ('owner','agent','untrusted','system')),   -- OpenClaw provenance
  text             text NOT NULL,
  occurred_at      timestamptz NOT NULL DEFAULT now(),   -- world time
  ingested_at      timestamptz NOT NULL DEFAULT now(),   -- system time
  privacy          smallint NOT NULL DEFAULT 1 CHECK (privacy BETWEEN 0 AND 2),  -- P0/P1/P2
  emotion          jsonb,          -- {"voice":"tense","conf":0.62,"text":"stressed","arousal":0.7}
  importance       smallint NOT NULL DEFAULT 3 CHECK (importance BETWEEN 1 AND 10),
  strength         real NOT NULL DEFAULT 1.0,            -- MemoryBank-style; decays, never deletes
  access_count     int  NOT NULL DEFAULT 0,
  last_accessed_at timestamptz,
  embedding        halfvec(768),
  embed_model      text,
  tsv              tsvector GENERATED ALWAYS AS (to_tsvector('simple', text)) STORED,
  extracted_at     timestamptz                           -- consolidation watermark
);
CREATE INDEX episodes_vec  ON episodes USING hnsw (embedding halfvec_cosine_ops);
CREATE INDEX episodes_tsv  ON episodes USING gin (tsv);
CREATE INDEX episodes_trgm ON episodes USING gin (text gin_trgm_ops);
CREATE INDEX episodes_time ON episodes (occurred_at);

-- 3. entities: people, projects, places, feelings...
CREATE TABLE entities (
  id          bigserial PRIMARY KEY,
  kind        text NOT NULL CHECK (kind IN ('self','person','project','place','org','event','feeling','topic','thing')),
  name        text NOT NULL,
  aliases     text[] NOT NULL DEFAULT '{}',
  summary     text,
  embedding   halfvec(768),
  privacy     smallint NOT NULL DEFAULT 1,
  merged_into bigint REFERENCES entities(id),
  created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX entities_name_trgm ON entities USING gin (name gin_trgm_ops);
CREATE INDEX entities_vec ON entities USING hnsw (embedding halfvec_cosine_ops);

-- 4. facts: bitemporal edges (Graphiti model, Postgres-enforced)
CREATE TABLE facts (
  id                 bigserial PRIMARY KEY,
  subj_id            bigint NOT NULL REFERENCES entities(id),
  predicate          text   NOT NULL,              -- works_at, lives_in, feels_about, knows...
  obj_id             bigint REFERENCES entities(id),
  obj_literal        text,
  fact_text          text   NOT NULL,              -- "Tejmul works at X"
  attrs              jsonb,                        -- {"valence":-0.6}
  functional         boolean NOT NULL DEFAULT false,
  valid              tstzrange NOT NULL DEFAULT tstzrange(now(), NULL),  -- world time
  recorded           tstzrange NOT NULL DEFAULT tstzrange(now(), NULL),  -- system time
  confidence         real NOT NULL DEFAULT 0.7,
  privacy            smallint NOT NULL DEFAULT 1,
  source_episode_ids bigint[] NOT NULL DEFAULT '{}',
  invalidated_by     bigint REFERENCES facts(id),
  embedding          halfvec(768),
  CHECK (obj_id IS NOT NULL OR obj_literal IS NOT NULL),
  -- two values of a functional predicate can never be valid at the same time
  EXCLUDE USING gist (subj_id WITH =, predicate WITH =, valid WITH &&)
    WHERE (functional AND upper_inf(recorded))
);
CREATE INDEX facts_subj  ON facts (subj_id);
CREATE INDEX facts_obj   ON facts (obj_id);
CREATE INDEX facts_valid ON facts USING gist (valid);

-- 5. provenance join (Zep episode-mentions)
CREATE TABLE episode_mentions (
  episode_id bigint REFERENCES episodes(id),
  entity_id  bigint REFERENCES entities(id),
  PRIMARY KEY (episode_id, entity_id)
);

-- 6. user model: one imperative directive per row, superseded in place (renders USER.md)
CREATE TABLE user_directives (
  id                 bigserial PRIMARY KEY,
  directive          text NOT NULL,     -- "Reply in Hinglish when I speak Hinglish"
  category           text NOT NULL CHECK (category IN ('talk_style','routine','preference','boundary','goal')),
  supersession_key   text NOT NULL,     -- e.g. 'reply_language'
  status             text NOT NULL DEFAULT 'active' CHECK (status IN ('proposed','active','superseded')),
  observed_at        timestamptz NOT NULL DEFAULT now(),
  superseded_by      bigint REFERENCES user_directives(id),
  source_episode_ids bigint[] NOT NULL DEFAULT '{}',
  privacy            smallint NOT NULL DEFAULT 1
);
CREATE UNIQUE INDEX one_active_directive ON user_directives (supersession_key) WHERE status = 'active';

-- 7. lessons: ACE-style itemized playbook (renders LESSONS.md)
CREATE TABLE lessons (
  id                  bigserial PRIMARY KEY,
  situation           text  NOT NULL,                 -- "Tejmul stressed, late night, work topic"
  trigger             jsonb NOT NULL DEFAULT '{}',    -- {"mood":["stressed"],"topic":["work"],"time":"late_night","person":[12]}
  guidance            text  NOT NULL,                 -- imperative, <= 25 words
  polarity            text  NOT NULL CHECK (polarity IN ('do','dont')),
  source              text  NOT NULL CHECK (source IN ('owner_explicit','inferred')),
  status              text  NOT NULL DEFAULT 'candidate' CHECK (status IN ('candidate','active','retired')),
  seen_count          int   NOT NULL DEFAULT 1,
  confidence          real  NOT NULL DEFAULT 0.5,
  helpful_count       int   NOT NULL DEFAULT 0,
  harmful_count       int   NOT NULL DEFAULT 0,
  situation_embedding halfvec(768),
  source_episode_ids  bigint[] NOT NULL DEFAULT '{}',
  supersedes          bigint REFERENCES lessons(id),
  created_at          timestamptz NOT NULL DEFAULT now(),
  last_applied_at     timestamptz
);
CREATE INDEX lessons_trigger ON lessons USING gin (trigger jsonb_path_ops);

-- 8. tasks (was SQLite in the productivity notes)
CREATE TABLE tasks (
  id            bigserial PRIMARY KEY,
  title         text NOT NULL,
  notes         text,
  status        text NOT NULL DEFAULT 'open' CHECK (status IN ('open','done','parked','cancelled')),
  created_at    timestamptz NOT NULL DEFAULT now(),
  due           timestamptz, scheduled timestamptz, wait_until timestamptz,
  est_minutes   int,
  energy        text CHECK (energy IN ('low','med','high')),
  context       text,                                     -- home, desk, errand, phone
  value         smallint CHECK (value BETWEEN 1 AND 5),   -- TMT V
  expectancy    real,                                     -- TMT E (0-1)
  aversiveness  real,                                     -- 0-1
  parent_id     bigint REFERENCES tasks(id),              -- Socratic Chunker tree
  depends_on    bigint[] NOT NULL DEFAULT '{}',
  done_when     text, if_then text, recur_rule text,
  carried_over  int NOT NULL DEFAULT 0,
  source        text NOT NULL DEFAULT 'voice',
  ek_identifier text,                                     -- Apple Reminders mirror
  privacy       smallint NOT NULL DEFAULT 1
);

-- 9. intents: alarms, reminders, check-ins, nudges (was APScheduler+SQLite)
CREATE TABLE intents (
  id            bigserial PRIMARY KEY,
  kind          text NOT NULL CHECK (kind IN ('alarm','reminder','checkin','nudge','event_trigger')),
  task_id       bigint REFERENCES tasks(id),
  fire_at       timestamptz, rrule text, trigger jsonb,
  payload       jsonb NOT NULL,                  -- what to say/do
  user_set      boolean NOT NULL DEFAULT true,   -- user-set alarms are never suppressed
  state         text NOT NULL DEFAULT 'pending'
                CHECK (state IN ('pending','armed','fired','done','cancelled','expired')),
  cooldown      interval DEFAULT '24 hours',     -- OpenClaw standing-intent defaults for nudges
  fires_left    int DEFAULT 3,
  expires_at    timestamptz,
  last_fired_at timestamptz,
  ek_identifier text
);
CREATE INDEX intents_due ON intents (fire_at) WHERE state IN ('pending','armed');

-- 10. turns: one row per exchange (latency + what was recalled)
CREATE TABLE turns (
  id              bigserial PRIMARY KEY,
  session_id      bigint REFERENCES sessions(id),
  user_episode_id bigint REFERENCES episodes(id),
  reply_episode_id bigint REFERENCES episodes(id),
  route           text NOT NULL CHECK (route IN ('fast_path','llm','degraded')),
  provider        text, model text, privacy smallint,
  briefing        text, briefing_tokens int,
  recalled        jsonb,       -- {"episodes":[..],"facts":[..],"lessons":[..]}
  latency_ms      jsonb,       -- {"stt":..,"laya":..,"recall":..,"ttft":..,"tts_first":..}
  created_at      timestamptz NOT NULL DEFAULT now()
);

-- 11. decisions: every Laya answer + outcome (calibration data)
CREATE TABLE decisions (
  id           bigserial PRIMARY KEY,
  turn_id      bigint REFERENCES turns(id),
  question     text NOT NULL,
  answer       text NOT NULL,
  confidence   real NOT NULL,
  acted        boolean NOT NULL,
  laya_version text NOT NULL,
  outcome      text CHECK (outcome IN ('confirmed','corrected','ignored','unknown')),
  corrected_to text,
  created_at   timestamptz NOT NULL DEFAULT now()
);

-- 12. llm_usage: quota + cooldown per provider/model/day
CREATE TABLE llm_usage (
  provider        text, model text, day date,
  requests        int NOT NULL DEFAULT 0,
  tokens_in       int NOT NULL DEFAULT 0,
  tokens_out      int NOT NULL DEFAULT 0,
  minute_start    timestamptz, minute_tokens int NOT NULL DEFAULT 0, minute_requests int NOT NULL DEFAULT 0,
  cooldown_until  timestamptz,
  last_error      text,
  PRIMARY KEY (provider, model, day)
);

-- 13. briefing_cache: sleep-time precompiled standing context + daily digests
CREATE TABLE briefing_cache (
  key         text PRIMARY KEY,   -- 'standing_profile','open_loops','active_projects','digest:2026-11-10'
  content     text NOT NULL,
  tokens      int  NOT NULL,
  built_at    timestamptz NOT NULL DEFAULT now(),
  valid_until timestamptz,
  run_id      bigint
);

-- 14. consolidation_runs: idempotent, watermarked night jobs
CREATE TABLE consolidation_runs (
  id          bigserial PRIMARY KEY,
  job         text NOT NULL,
  started_at  timestamptz NOT NULL DEFAULT now(),
  finished_at timestamptz,
  status      text NOT NULL DEFAULT 'running' CHECK (status IN ('running','ok','partial','failed')),
  watermark   bigint,           -- last episode id processed
  provider    text, tokens_used int,
  stats       jsonb,            -- counts + every ACE delta applied
  error       text
);

-- wake workers right after a turn (payload = id only, < 8 KB)
CREATE FUNCTION notify_episode() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN PERFORM pg_notify('stiti_mem', NEW.id::text); RETURN NEW; END $$;
CREATE TRIGGER episodes_notify AFTER INSERT ON episodes
  FOR EACH ROW EXECUTE FUNCTION notify_episode();
```

Six tables are deferred to v0.1: `segments`, `reflections`, `habits`, `habit_events`, `mcp_servers`/`tools` (for pin-and-diff and tool-RAG), and `documents`/`chunks`. They slot in without changing anything above.

**Provenance rule.** Consolidation extracts facts only from `origin='owner'` episodes. Stiti's own replies (`origin='agent'`) are context, never a source of new facts. This is OpenClaw's "a fact recalled one hundred times stays one fact" rule, and it stops self-echo.

### Retrieval function design

The Python side runs four steps:

1. Embed the transcript, in parallel with the Laya call.
2. Turn Laya's `has_time_reference`, plus a date parser, into `t_from`/`t_to`.
3. Build an OR-joined `tsquery` over content words, after dropping an English+Hinglish stop list.
4. Skip recall entirely when Laya says `memory_needed = none` with ≥0.8 confidence, or when the jarvis-style recall gate finds the hot window sufficient.

Before a time-filtered call, run `SET hnsw.iterative_scan = relaxed_order` so the filter doesn't starve the HNSW leg (pgvector 0.8).

```sql
CREATE FUNCTION recall(q_tsq tsquery, q_vec halfvec(768),
                       t_from timestamptz DEFAULT NULL, t_to timestamptz DEFAULT NULL,
                       max_privacy smallint DEFAULT 1, k int DEFAULT 12)
RETURNS TABLE (episode_id bigint, score double precision, occurred_at timestamptz, text text)
LANGUAGE sql STABLE AS $$
WITH v AS (                         -- semantic leg: LIMIT inside so HNSW is used, rank after
  SELECT id, row_number() OVER (ORDER BY d) AS r
  FROM (SELECT id, embedding <=> q_vec AS d
        FROM episodes
        WHERE embedding IS NOT NULL AND privacy <= max_privacy
          AND (t_from IS NULL OR occurred_at >= t_from) AND (t_to IS NULL OR occurred_at < t_to)
        ORDER BY embedding <=> q_vec LIMIT 50) s
), t AS (                           -- lexical leg ('simple' config: safe for Hinglish)
  SELECT id, row_number() OVER (ORDER BY rk DESC) AS r
  FROM (SELECT id, ts_rank_cd(tsv, q_tsq) AS rk
        FROM episodes
        WHERE tsv @@ q_tsq AND privacy <= max_privacy
          AND (t_from IS NULL OR occurred_at >= t_from) AND (t_to IS NULL OR occurred_at < t_to)
        ORDER BY rk DESC LIMIT 50) s
), fused AS (                       -- Reciprocal Rank Fusion, k = 60
  SELECT COALESCE(v.id, t.id) AS id,
         COALESCE(1.0/(60 + v.r), 0) + COALESCE(1.0/(60 + t.r), 0) AS rrf
  FROM v FULL OUTER JOIN t ON v.id = t.id
)
SELECT e.id,
       f.rrf
       -- recency: 30-day half-life with a 0.5 floor, so old memories still surface ("infinite memory")
       * (0.5 + 0.5 * exp(-ln(2) * extract(epoch FROM now() - COALESCE(e.last_accessed_at, e.occurred_at)) / (30*86400)))
       * (0.7 + 0.03 * e.importance)                     -- importance 1-10
       * (0.8 + 0.2 * LEAST(e.strength, 1.0))            -- MemoryBank strength
       AS score,
       e.occurred_at, e.text
FROM fused f JOIN episodes e ON e.id = f.id
ORDER BY score DESC
LIMIT k;
$$;

-- current facts around the entities in play (1-2 hops, valid now, not retracted)
CREATE FUNCTION current_facts(seed_ids bigint[], max_depth int DEFAULT 2, max_privacy smallint DEFAULT 1)
RETURNS TABLE (fact_id bigint, fact_text text, valid tstzrange, depth int)
LANGUAGE sql STABLE AS $$
WITH RECURSIVE nb(entity_id, depth, path) AS (
  SELECT unnest(seed_ids), 0, ARRAY[]::bigint[]
  UNION ALL
  SELECT CASE WHEN f.subj_id = nb.entity_id THEN f.obj_id ELSE f.subj_id END,
         nb.depth + 1, nb.path || f.id
  FROM nb JOIN facts f ON (f.subj_id = nb.entity_id OR f.obj_id = nb.entity_id)
  WHERE nb.depth < max_depth AND f.valid @> now() AND upper_inf(f.recorded)
    AND f.privacy <= max_privacy AND f.obj_id IS NOT NULL AND NOT f.id = ANY(nb.path)
)
SELECT DISTINCT ON (f.id) f.id, f.fact_text, f.valid, nb.depth
FROM nb JOIN facts f ON (f.subj_id = nb.entity_id OR f.obj_id = nb.entity_id)
WHERE f.valid @> now() AND upper_inf(f.recorded) AND f.privacy <= max_privacy
ORDER BY f.id, nb.depth
LIMIT 40;
$$;
```

**Seed entities** come from two sources: trigram matches of entity names and aliases against the transcript (similarity ≥ 0.5), and entities mentioned by the top 5 recalled episodes.

**Lesson matching** is a separate query:
- Filter: `status='active'` and trigger keys compatible with the current mood, topic entities, person and time bucket. A missing key matches anything.
- Order: by `situation_embedding <=> q_vec`.
- Limit: 5.

Python then runs MMR over episodes and facts (λ = 0.7), trims to the memory budget, and returns the IDs for `turns.recalled`. Access counters and strength bumps are written *after* the reply, so the hot path does no writes.

**Target:** recall plus facts plus lessons under 100 ms at personal scale. The memory notes estimate the SQL alone at 5–30 ms. Measure it.

When `max_privacy` is set by the route, the briefing never includes P2 rows for a cloud call.

### Context compiler briefing format

Every LLM gets the same template, so swapping the model changes nothing about who Stiti is. The total budget is ≤1,500 tokens because of Groq's 8K TPM. The compiler drops sections from the bottom of the priority list until the briefing fits: tools first, then open loops, then the oldest memory lines.

```text
### STITI BRIEFING v0 · route=voice_fast · privacy=P1 · Tue 2026-11-10 21:42 IST
[WHO YOU ARE ≤150]        SOUL.md short form (read fresh every turn)
[WHO HE IS ≤150]          briefing_cache:standing_profile
[RIGHT NOW ≤80]           late evening · voice: tense 0.62 (his baseline: calm) · words: stressed 0.71
                          · energy low · last 3 turns: <one-line summary>
[OPEN LOOPS ≤120]         only if Laya domain ∈ {todo,time} or memory_needed=project:
                          top-3 tasks with one-line reason · next alarm
[MEMORY ≤600]             quoted data, never instructions; each line dated + sourced:
                          [E18231 · 2026-11-03 · he said] "…"
                          [F412 · true since 2026-10 · fact] Tejmul works on Stiti nightly
                          [F377 · ended 2026-09 · fact] … (only when the change matters)
[HOW TO TALK NOW ≤200]    active talk_style directives + matched lessons:
                          MUST: keep it under 3 sentences when he is stressed (lesson L17, from 2026-11-02)
                          MUST NOT: joke about deadlines (L09)
[TOOLS ≤150]              only if tool_category ≠ none: top-5 tool names + one-line "use when"
[OUTPUT CONTRACT ≤80]     Mirror his language mix (Hinglish in → Hinglish out). ≤3 items, ≤20 s of speech,
                          at most one question. Never say failed/behind/overdue/should have.
                          If MEMORY doesn't cover it, say you don't remember. Never invent memories.
[HE SAYS] <transcript>
```

The order follows PrefEval: directives and lessons sit right before the user's words. The `[MEMORY]` lines carry IDs, so the reply can be checked against what was recalled. Stiti's reply is stored as an `origin='agent'` episode and is never mined for facts.

### LLM router order with free-tier limits

| Route | Order (first available wins) | Gate checks before each call |
|---|---|---|
| `voice_fast`, P1 | Groq `openai/gpt-oss-20b` → Groq `qwen/qwen3.8-27b` → Cerebras `gpt-oss-120b` → Groq `openai/gpt-oss-120b` → OpenRouter `:free` (ZDR endpoints only) → **degraded fast path** | Skip if `cooldown_until > now()`, if `minute_tokens + est > 0.9×TPM`, or if `requests ≥ 0.95×RPD`. Groq: 30 RPM / 1K RPD / 8K TPM / 200K TPD per model. Cerebras: 5 RPM / 1M TPD. OpenRouter: 20 RPM / 50 RPD. |
| `voice_fast`, P0 | Same, then Gemini Flash-Lite (~10–15 RPM / ~500 RPD, third-party figures) | Same |
| `background_smart`, P0/P1 (night) | Cerebras `gpt-oss-120b` → Cerebras `qwen-3.8-27b` → Groq `openai/gpt-oss-120b` → Mistral (training opt-out confirmed) → **stop and resume next idle window** | Nightly caps: about 600K tokens on Cerebras, 150K per Groq model, so daytime voice keeps its headroom |
| any, P2 | **No cloud.** Fast path, verbatim recall, or ask permission to send | Deterministic privacy floor plus Laya `privacy_level` |

Mechanics:

- On 429, set `cooldown_until` from `Retry-After` (default 60 s) and continue down the chain.
- On the voice route, if the first token hasn't arrived within 1.5 s, play a filler clip and fail over.
- Use the lowest reasoning effort the model allows on voice turns. Hybrid-reasoning models can return empty content otherwise ([Apoorva87](https://github.com/Apoorva87/local-voice-agent)).
- Every call writes `llm_usage` and `turns.provider`.
- Model IDs are the ones in the notes. Confirm them in each console before hard-coding, and read limits from response headers where available rather than trusting the constants.

### Laya question set

The state string Laya reads must fit mmBERT's 1,024 tokens:

- the transcript;
- the last 3 turns, truncated;
- the voice-emotion tag;
- the time-of-day bucket;
- the top 5 open task titles;
- the current domain.

One `predict_batch` call answers all of the following:

| Question | Type | Options | Starting gate | Drives |
|---|---|---|---|---|
| `domain` | choice | todo · time (alarm/reminder/timer) · memory · chat · tool · feedback · control (stop/repeat/louder) | act ≥ 0.75, else LLM | First-level route |
| `action` | choice, per domain, ≤6 options (e.g. todo: add/list/done/plan/breakdown/park) | — | writes ≥ 0.85; reads ≥ 0.7 | Fast-path handler |
| `needs_llm` | yes/no | — | skip the LLM if p(no) ≥ 0.8 and a handler exists | LLM cost |
| `is_correction` | yes/no | — | ≥ 0.6 → lesson capture | Lessons |
| `text_emotion` | choice | calm · happy · stressed · angry · sad · tired | fuse with voice; never act alone | Briefing [RIGHT NOW] |
| `tone_to_use` | choice | brief · warm · playful · serious · supportive | < 0.5 → default to warm | Briefing |
| `urgency` | score 1–5 | — | — | Task urgency, Nudge Gate |
| `memory_needed` | choice | none · recent · people · project · past_event | `none` ≥ 0.8 → skip recall | Retrieval |
| `has_time_reference` | yes/no | — | ≥ 0.5 → run the date parser | `t_from`/`t_to` |
| `tool_category` | choice | calendar · mail · files · mac · web · github · none | ≥ 0.6, else expose memory tools only | Tool-RAG |
| `privacy_level` | choice | P0 · P1 · P2 | P2 if p(P2) ≥ 0.3 (deliberately cautious); can't go below the regex floor | Router |
| `worth_remembering` | score 1–10 | — | — | `episodes.importance` |
| `is_backchannel` | yes/no | for speech during Stiti's TTS ("haan", "hmm", "acha") | ≥ 0.7 → don't barge in | Voice |

Every answer is logged to `decisions` with `acted` and, later, `outcome`.

**Day-one test:** run all 13 questions on 30 real Hinglish sentences from Tejmul, on both the English and the multilingual checkpoint. Record accuracy, latency and RSS. The gates above are deliberately conservative starting points, to be recalibrated weekly from the log. Irreversible tool actions never rely on Laya alone: the risk-tier confirmation still applies.

### Lessons capture

**1. Detect.** Capture starts when, within two turns of a Stiti reply, either `is_correction ≥ 0.6` or a deterministic English+Hinglish lexicon fires: "don't…", "stop…", "too long", "mat bolo", "aise mat", "band karo", "itna lamba", "pehle bhi bola tha".

**2. Snapshot the situation** of the corrected turn: mood, topic entities, person mentioned, time bucket, Laya domain. Attach evidence: the corrected reply's episode ID and the correction's episode ID.

**3. Write the guidance.**
- If the correction is already imperative, a template turns it into guidance directly ("don't X" → `polarity='dont'`, guidance X).
- Otherwise the night job asks the P1 cloud route for one imperative sentence of at most 25 words. Code accepts it only if it passes the schema and mentions the situation.

**4. Set status.**
- Owner-explicit corrections become `active` with confidence 0.9.
- Inferred lessons (for example, repeated "bas bas" after long replies) stay `candidate` until `seen_count ≥ 2` and `confidence ≥ 0.72`, per Leon's gate.

**5. Acknowledge in one sentence** so Tejmul can fix a mis-learned rule on the spot: "Samajh gaya, jab tum stressed ho main chhota bolunga" ("Got it, when you're stressed I'll keep it short"). This is PAHF's clarify-before-acting idea.

**6. Score.** If the lesson is applied and the next two turns bring no renewed correction, increment `helpful_count`. If the same correction comes back in the same situation, increment `harmful_count` and queue the lesson for an EDIT.

**7. Curate nightly** with ACE/ExpeL per-item operations only: ADD, EDIT, MERGE, RETIRE, UPVOTE, DOWNVOTE. Each is logged in `consolidation_runs.stats`. Retire a lesson when `harmful_count > helpful_count + 2`.

**8. Render `LESSONS.md`.** If Tejmul edits the file, its hash changes and the diff is imported as owner edits.

### Consolidation job ("sleep")

**Trigger:** 03:00, or after 30 idle minutes on AC power. Never during an active session (Leon's 2-minute grace rule). Every step is idempotent and records a watermark in `consolidation_runs`. A step that hits its token cap ends as `partial` and resumes in the next window. P2 rows never enter an LLM step.

| # | Step | Engine | Output |
|---|---|---|---|
| 1 | Embed backlog (`embedding IS NULL`) | Local embedder | Vectors + `embed_model` |
| 2 | Day digest per session/topic | Cloud (`background_smart`), P0/P1 only | `briefing_cache['digest:<date>']`; `segments` table in v0.1 |
| 3 | Extract entities, facts and directive proposals from owner episodes since the watermark, about 20 episodes per request, strict JSON schema | Cloud | Candidates with `evidence_ids` and confidence |
| 4 | Resolve entities: exact alias → trigram ≥ 0.6 → embedding cosine ≥ 0.85 within the same kind → else create new | SQL/Python, no LLM | `entities`, `episode_mentions` |
| 5 | Apply facts. A new functional fact closes the old interval (`valid = tstzrange(lower, new_from)`, `invalidated_by`) in the same transaction. "Was never true" corrections close `recorded` instead. The LLM only flags conflicts. | SQL | Bitemporal `facts` |
| 6 | Supersede directives in place by `supersession_key` | SQL | `user_directives` |
| 7 | Curate lessons (ACE deltas, retire harmful ones) | Cloud proposes, code applies | `lessons` |
| 8 | Strength and importance upkeep: decay `strength` toward a 0.2 floor, slower for frequently accessed rows; nothing deleted | SQL | `episodes.strength` |
| 9 | Precompile standing context: `standing_profile` (≤150 tokens), `active_projects` (god nodes = entity degree × 30-day recency), `open_loops` | SQL + cloud phrasing (P1) | `briefing_cache` |
| 10 | Render views and back up: `USER.md`, `LESSONS.md`, `GRAPH_REPORT.md`; encrypted `pg_dump` | Local | `~/.stiti/` |

### Build order for tonight

| Step | Build | Done when |
|---|---|---|
| 1 | Postgres + extensions + schema | `\dx` shows vector, btree_gist, pg_trgm; inserting two overlapping functional facts fails |
| 2 | Embedder process (EmbeddingGemma, in-process) + REPL that writes episodes | 20 typed memories stored with vectors |
| 3 | `recall()`, `current_facts()`, lesson match | Right memory in top 3 for 10 hand-made questions; <100 ms |
| 4 | Laya install + 13-question pass + decision log | Accuracy/latency/RSS on 30 real sentences recorded |
| 5 | Router with Groq + Cerebras keys + `llm_usage` | Forced 429 fails over with no user-visible error |
| 6 | Context compiler + text chat loop + fast-path todo/alarm handlers | "add todo / list todos / set alarm" work with the LLM disabled |
| 7 | Lessons capture end-to-end | One correction changes the next reply in the same situation |
| 8 | `stiti sleep --now` running steps 1, 3–6, 9, 10 | Facts and USER.md appear from the day's chat; restart + model swap keeps memory |

## rea reverse-engineering targets

rea is most useful on JS/TS, Electron or minified bundles, and on model files. Python projects should simply be read. The researchers' hands-on run produced five lessons:

- rea needs Node ≥26.12.1. The Mac now has 26.13.0.
- macOS lacks GNU `timeout`, so use `gtimeout`.
- **A whole-package run on OpenClaw (7,538 files) failed** after about 6 minutes and logged 1,413 resource-limit notices.
- **A 26-chunk memory subset succeeded in under a minute** and recovered 368 named functions.
- Point rea at `dist/` subsets, never whole packages.

| # | Target | Kind | What to extract | Status / method |
|---|---|---|---|---|
| 1 | OpenClaw `openclaw@2026.11.2` dist: `dreaming-*`, `agent-runner-memory-*`, `context-engine-*`, `cron-tool-*`, standing-intent chunks | npm/TS bundle | Promotion weights, candidate-truth confidence, compaction flush, intent lifecycle, the 03:00 default | Subset run done on 2026.9.2. Re-run on the latest version alongside `docs/concepts/*.md`. |
| 2 | AIRI desktop build (Electron/Tauri) | TS app | Code-decided automation triggers (return-from-idle), memory index + per-fact entries | rea on the desktop bundle; read the ADR first |
| 3 | Leon `pulse-manager`, `self-model-manager`, `persona.ts` | TS server | Suppression policies, decline cooldowns, principle gates | Source is readable. Use rea for the call graph only. |
| 4 | letta-code | TS | How sleep-time agents edit memory blocks | rea + source |
| 5 | SillyTavern world-info (`world-info.js`) | JS | Keyword-triggered lore injection, as a template for lesson triggers | Source + rea |
| 6 | MemOS (TS) | TS | MemCube provenance/versioning fields | Source + rea |
| 7 | Node MCP servers before installing: Playwright MCP, supermemoryai apple-mcp, Peekaboo MCP, filesystem server | npm packages | Exposed tools, child processes, network endpoints. This is the security baseline for pin-and-diff. | rea per package, `--ignore-scripts` |
| 8 | Model files: Laya (safetensors/ONNX), emotion2vec+ base, Kokoro, EmbeddingGemma, Smart Turn | Weights | Parameter count, dtype, quantization, true on-disk/RAM size before download | rea model-file inspection |
| — | Read as source (no rea): Hermes `agent/curator.py`, `memory_manager.py`; jarvis `*.spec.md`; Graphiti resolution/invalidation; Mem0 update ops; Laya `agent.py`/`common.py`; Pipecat Mac examples; Khoj models (AGPL, read only); Omi `config/memory_confidence.py` | Python | Algorithms and thresholds | Read and take notes; don't copy AGPL or non-commercial (jarvis) code |

## Risks and open questions

| Risk / unknown | Why it matters | Mitigation or test |
|---|---|---|
| RAM budget is unmeasured on a base M2 (estimate 1.8–3.7 GB) | Swapping kills voice latency | Measure RSS per component on day one; INT8 Laya and embedder; lazy-load emotion; one process |
| Laya's zero-shot accuracy (0.36 on its benchmark) and Hinglish behavior are unknown; only T4 GPU latency exists | Wrong fast-path actions erode trust | 30-sentence pilot; conservative gates; LLM fallback; weekly calibration from `decisions`; local Laya fine-tune later |
| Free tiers change and some limits are third-party (Gemini) or unrendered (Groq free-plan tab) | The router could hard-fail | Read limits from headers into `llm_usage`; multi-provider chain; degraded mode |
| Groq/Cerebras "no training" rests on OpenRouter's blog, not their ToS | P1 personal data leaves the Mac | Read each ToS before enabling P1; keep briefings minimal; P2 never leaves |
| KG learning depends on the cloud (no local LLM) | Offline days add episodes but no facts | Episodes stay searchable; watermarked backlog catches up |
| Fact extraction by free 20–27B models may be noisy; Graphiti warns weak models fail ingestion | A polluted graph is worse than none | Strict JSON schema, deterministic resolver, confidence thresholds, provenance on every fact, weekly spot-check |
| Hinglish STT error is high (Apex WER 29.8–47.6 against transliterated references) | Memory and Laya inherit transcript errors | Week-one A/B; personal LoRA; Groq Whisper fallback |
| Smart Turn cut off 32 of 80 pauses in one deployment; Hinglish fillers make it worse | Stiti interrupts Tejmul | Adaptive fallback + filler rule; fine-tune on own recordings |
| Laptop-speaker echo | Barge-in triggers on Stiti's own voice | WebRTC AEC; headphones until verified |
| Naturalistic emotion accuracy is around 41% | Mis-read moods annoy | Hint only; personal baseline; ask, don't declare; store denials as labels |
| macOS TCC under launchd can silence the mic | Stiti goes deaf after a reboot | Signed `.app`, in-process mic, Login Item |
| Homebrew pgvector vs PG 18 compatibility; `pg_textsearch` and AGE builds on macOS arm64 are untested | Install friction tonight | Postgres.app fallback; built-in FTS first |
| MCP tool poisoning, rug pulls, malicious skills | Data exfiltration from the Mac | Pin-and-diff, risk tiers, taint flag, no hub installs |
| "kal" means both yesterday and tomorrow; "parso" means the day before yesterday or after tomorrow | Wrong alarm dates | Resolve by verb tense; always read back the absolute date for alarms |
| No benchmark tests memory with free mid-size reader models | Vendor numbers don't transfer | Build a private eval set in the LongMemEval taxonomy (extraction, multi-session, temporal, knowledge updates, abstention) from consented history |
| Over-eager proactivity | A buddy that nags gets muted | 3–5 per day budget, bandit learning, "stop doing X" becomes a permanent directive |

## Conclusion

The research moves the bottleneck. With no local LLM, the scarce resource is not GPU memory for a model. It is three other things:

- **Groq's 8K tokens per minute.** This turns the context compiler from a nicety into the component that sets Stiti's conversation rate.
- **Laya's calibration.** Its zero-shot accuracy is too low to trust without Tejmul's own decision log.
- **The privacy gate.** It decides what the cloud may think about.

Stiti's quality will therefore track its decision log, its private eval set and its briefing discipline more closely than any model choice. That vindicates D1: the brain really is the engine. It also clarifies what "local-first" means here. State, memory, decisions and sensitive data stay on the Mac. Language, extraction and nightly reflection are rented from interchangeable free providers that never hold state.

The psychology evidence adds a counter-intuitive design goal for a "Jarvis": restraint. Reminders hinder habits, notifications show no long-term engagement gain, LLM agents over-intervene, and accountability beats cleverness. The version of Stiti most likely to help is the one that says three things at most, nudges a handful of times a day, fades its prompts as habits form, and never says "overdue".

