# Open-source personal AI assistants, companions and "Jarvis" projects: how they model the user and keep memory (for Stiti)

Research date: 2026-11-10. GitHub stars, licenses, and last-push dates come from the GitHub REST API (`gh api repos/<owner>/<repo>`) on that date, unless a note says otherwise. "Last push" is the `pushed_at` date. Stiti's constraints are an Apple M2 with 8 GB RAM, local-first operation, zero cost, Postgres as the brain, and a swappable LLM.

---

## Q1. Which existing projects are closest to Stiti? (catalogue of 26 projects)

### Takeaway
**OpenClaw** is the closest match and the best reference design. Its memory design is documented, plain-file, and independent of the LLM: SOUL.md, USER.md, MEMORY.md, daily notes, a SQLite index carrying provenance, "dreaming" consolidation, and standing intents. **Hermes Agent** is a slimmer Python version of the same pattern, with a strong self-improving skills loop. **isair/jarvis** is the closest voice-first, local, 8 GB-aware design (diary plus self-organising knowledge graph), but its license is non-commercial. **Leon** (TypeScript) contributes a self-model and a bounded proactive "pulse". **Khoj** is the only mature project already built on **Postgres + pgvector**. **Graphiti/Zep** is the reference temporal knowledge graph.

### Cited Findings

Catalogue (stars and last push as of 2026-11-10; source for all metadata: GitHub API):

| # | Project | Repo | Stars | License | Lang | Last push | Status |
|---|---|---|---|---|---|---|---|
| 1 | OpenClaw | https://github.com/openclaw/openclaw | 394,246 | MIT | TypeScript | 2026-11-09 | Very active; npm `openclaw` latest 2026.11.2 |
| 2 | Hermes Agent (Nous Research) | https://github.com/NousResearch/hermes-agent | 262,010 | MIT | Python | 2026-11-09 | Very active |
| 3 | Letta (ex-MemGPT) server | https://github.com/letta-ai/letta | 25,395 | Apache-2.0 | Python | 2026-10-18 | Active, but momentum has moved to letta-code |
| 3b | letta-code | https://github.com/letta-ai/letta-code | 3,807 | Apache-2.0 | TypeScript | 2026-11-09 | Active |
| 4 | Khoj | https://github.com/khoj-ai/khoj | 38,090 | **AGPL-3.0** | Python | 2026-08-02 | Slowing (no push for about 3 months) |
| 5 | Leon | https://github.com/leon-ai/leon | 17,652 | MIT | TypeScript | 2026-11-08 | Active, core being rebuilt |
| 6 | OpenVoiceOS ovos-core | https://github.com/OpenVoiceOS/ovos-core | 300 | Apache-2.0 | Python | 2026-11-02 | Active, small community |
| 6b | ovos-persona | https://github.com/OpenVoiceOS/ovos-persona | 8 | Apache-2.0 | Python | 2026-11-03 | Active |
| 7 | Home Assistant (Assist) | https://github.com/home-assistant/core | 92,105 | Apache-2.0 | Python | 2026-11-09 | Very active |
| 7b | Wyoming protocol | https://github.com/OHF-Voice/wyoming | 414 | MIT | Python | 2026-11-05 | Active |
| 8 | Open Interpreter | https://github.com/openinterpreter/openinterpreter | 68,848 | Apache-2.0 | **Rust** (rewritten) | 2026-11-09 | Active |
| 8b | Open Interpreter 01 | https://github.com/openinterpreter/01 | 5,166 | AGPL-3.0 | Python | **2024-11-01** | **Stale/abandoned** |
| 9 | isair/jarvis | https://github.com/isair/jarvis | 2,210 | **Custom non-commercial** ("free for personal use") | Python | 2026-10-20 | Active |
| 10 | Open-LLM-VTuber | https://github.com/Open-LLM-VTuber/Open-LLM-VTuber | 14,659 | Custom (NOASSERTION; Live2D assets under separate licenses) | Python | 2026-05-15 | Slowing; long-term memory removed |
| 11 | Project AIRI (moeru-ai) | https://github.com/moeru-ai/airi | 51,242 | MIT | TypeScript | 2026-11-09 | Very active |
| 12 | SillyTavern | https://github.com/SillyTavern/SillyTavern | 35,467 | **AGPL-3.0** | JavaScript | 2026-10-02 | Active |
| 13 | screenpipe | https://github.com/screenpipe/screenpipe (was mediar-ai/screenpipe) | 22,293 | **Source-available, non-commercial** | Rust | 2026-11-09 | Active |
| 14 | Omi (BasedHardware) | https://github.com/BasedHardware/omi | 13,935 | MIT | Python (backend) / Flutter | 2026-11-09 | Very active |
| 15 | nanobot (HKUDS) | https://github.com/HKUDS/nanobot | 49,974 | MIT | Python | 2026-11-09 | Very active |
| 16 | NanoClaw | https://github.com/nanocoai/nanoclaw | 31,099 | MIT | TypeScript | 2026-11-09 | Active |
| 17 | PicoClaw | https://github.com/sipeed/picoclaw | 30,116 | MIT | Go | 2026-11-05 | Active |
| 18 | ZeroClaw | https://github.com/zeroclaw-labs/zeroclaw | 33,300 | Apache-2.0 | Rust | 2026-11-09 | Active |
| 19 | Mem0 | https://github.com/mem0ai/mem0 | 68,701 | Apache-2.0 | Python | 2026-11-06 | Active (memory layer) |
| 20 | Graphiti (Zep) | https://github.com/getzep/graphiti | 32,683 | Apache-2.0 | Python | 2026-11-09 | Active (temporal KG) |
| 21 | Honcho (Plastic Labs) | https://github.com/plastic-labs/honcho | 8,037 | **AGPL-3.0** | Python | 2026-11-09 | Active (user-modeling memory) |
| 22 | Hindsight | https://github.com/vectorize-io/hindsight | 60,080 | MIT | Python | 2026-11-09 | Active (memory layer) |
| 23 | MemOS | https://github.com/MemTensor/MemOS | 12,337 | Apache-2.0 | TypeScript | 2026-11-09 | Active |
| 24 | cognee | https://github.com/topoteretes/cognee | 33,185 | Apache-2.0 | Python | 2026-11-09 | Active (KG memory) |
| 25 | LifeOS (Daniel Miessler, ex-Personal_AI_Infrastructure) | https://github.com/danielmiessler/LifeOS | 19,780 | MIT | TypeScript | 2026-11-05 | Active |
| 26 | GLaDOS (dnhkng) | https://github.com/dnhkng/GLaDOS | 5,770 | MIT | Python | 2026-10-11 | Active (local voice-persona pipeline) |
| 27 | elizaOS | https://github.com/elizaOS/eliza | 19,792 | MIT | TypeScript | 2026-11-09 | Active (character-file agents) |
| — | Mycroft core | https://github.com/MycroftAI/mycroft-core | 6,611 | Apache-2.0 | Python | 2024-09-08 | **Archived** (OVOS is the successor) |
| — | SillyTavern-Extras | https://github.com/SillyTavern/SillyTavern-Extras | 706 | AGPL-3.0 | Python | 2024-12-10 | **Obsolete** per its own description |
| — | Open-Assistant (LAION) | https://github.com/LAION-AI/Open-Assistant | 37,349 | Apache-2.0 | Python | 2024-08-17 | **Stale** |
| — | obot nanobot (Go) | https://github.com/obot-platform/nanobot | 1,359 | Apache-2.0 | Go | 2026-09-24 | **Archived** (not to be confused with HKUDS/nanobot) |
| — | byterover-cli (ex-campfirein/cipher) | https://github.com/campfirein/byterover-cli | 4,944 | NOASSERTION | TypeScript | 2026-06-25 | **Archived** |

Per-project architecture notes:

- **OpenClaw**: a multi-channel gateway ("Multi-channel AI gateway with extensible messaging integrations"). The npm package ships the full `docs/` folder, including `docs/concepts/{memory-architecture,soul,user-model,dreaming,active-memory,standing-intents,agent-workspace,memory-builtin,memory-honcho,context-engine,memory-provenance}.md`. The design rule is "OpenClaw memory is a set of plain files and one SQLite index, organized into tiers with different trust levels" and "No hidden state. The model only remembers what is written to files in the agent workspace." — openclaw npm tarball `docs/concepts/memory-architecture.md` ([repo](https://github.com/openclaw/openclaw/blob/main/docs/concepts/memory-architecture.md))
  - Memory tiers: Instructions (`AGENTS.md`, written by the human only); Curated core (`MEMORY.md`, `USER.md`, written by dreaming consolidation); Episodic (`memory/YYYY-MM-DD.md` daily notes plus transcripts, never auto-injected, search only); Prospective (standing intents in SQLite plus cron jobs); Review (`DREAMS.md`). — [memory-architecture.md](https://github.com/openclaw/openclaw/blob/main/docs/concepts/memory-architecture.md)
  - Recall has two lanes. Lane 1 makes zero model calls: bootstrap injection, `memory_search` scoring "hybrid relevance multiplied by an exponential recency decay (30-day half-life) and an importance multiplier" (importance 1–10 is set at write time), and trigger-phrase injection (score at or above 0.72, at most 3 per turn). Lane 2 is a recall sub-agent that runs only on recall intent and only when lane 1 has no strong hit. — same
  - Entries carry inline metadata: `- Keep the gateway on loopback. <!-- trigger: gateway setup, network safety --> <!-- importance: 9 -->` — same
  - Bundled dependencies include `kysely`, `croner`, `@modelcontextprotocol/sdk`, `grammy` (Telegram), `node-edge-tts`, `playwright-core`, `openai`, `@anthropic-ai/sdk`, and `@google/genai`. The bundle has 52 skills, including `apple-notes`, `apple-reminders`, `obsidian`, `openai-whisper`, `sherpa-onnx-tts`, `things-mac`, `spotify-player`, `weather`, `notion`, and `1password`. — openclaw npm tarball `package.json` and `skills/` (inspected locally)
  - Required Node is `>=22.22.3 <23 || >=24.15.0 <25 || >=25.9.0`, so it runs on this machine's Node 26.0.0. — openclaw `package.json`
- **Hermes Agent**: "the only agent with a built-in learning loop — it creates skills from experience, improves them during use, nudges itself to persist knowledge, searches its own past conversations". It has a single gateway for Telegram, Discord, Slack, WhatsApp, Signal, and CLI. It can import an OpenClaw `SOUL.md`, `MEMORY.md`/`USER.md` entries, and skills. — [README](https://github.com/NousResearch/hermes-agent)
  - Memory lives in `~/.hermes/memories/`. `MEMORY.md` is capped at 2,200 chars (`memory.memory_char_limit`) and `USER.md` at 1,375 chars (`memory.user_char_limit`). The snapshot is frozen at session start so the prefix cache is preserved. The `memory` tool has `add`, `patch`, and `remove` actions. Sessions are stored in SQLite `~/.hermes/state.db` with FTS5. Pluggable external providers are Honcho, Hindsight, Supermemory, Mem0, RetainDB, and ByteRover. A background review saves memory and creates or patches skills, gated by `skills.write_approval`. — [Hermes memory docs](https://hermes-agent.nousresearch.com/docs/user-guide/features/memory)
  - Source modules: `agent/memory_manager.py`, `agent/memory_provider.py`, `agent/memory_context.py`, `agent/curator.py` ("background skill maintenance orchestrator"; the deterministic inactivity prune always runs, while LLM consolidation is opt-in with `DEFAULT_CONSOLIDATE = False`), `agent/learning_graph.py`, `agent/learning_mutations.py`, `agent/learn_prompt.py`, and the repo-root `SOUL.md`. — [repo tree](https://github.com/NousResearch/hermes-agent/tree/main/agent)
- **Letta (MemGPT)**: "Platform for stateful agents: AI with advanced memory that can learn and self-improve over time". Core memory is made of "memory blocks individually persisted in the DB, with a unique block_id". Sleep-time agents "run in the background and can modify the memory blocks asynchronously" (marked experimental). — [GitHub](https://github.com/letta-ai/letta), [Letta blog: memory blocks](https://letta.com/blog/memory-blocks), [Letta docs: sleep-time](https://docs.letta.com/guides/agents/architectures/sleeptime/index.md)
- **Khoj**: Django plus Postgres with **pgvector** (`from pgvector.django import VectorField`). Models include `Entry` (embeddings), `UserMemory` (embeddings), `Agent` (persona, model, tools), `McpServer`, `ReflectiveQuestion`, `Conversation`, and `NotionConfig`/`GithubConfig` connectors. Content processors live in `src/khoj/processor/content/{markdown,docx,github,images,...}`. — [models/__init__.py](https://github.com/khoj-ai/khoj/blob/master/src/khoj/database/models/__init__.py). The README says "Create agents with custom knowledge, persona, chat model and tools" and "smart notifications". — [README](https://github.com/khoj-ai/khoj)
- **Leon**: "built around tools, context, memory, and agentic execution". It has three modes (smart, controlled, agent), `SKILL.md` agent skills, and "a compact self-model and a bounded proactive pulse system". — [README](https://github.com/leon-ai/leon)
  - `server/src/core/memory-manager/sql/schema.sql` defines `memory_items` with scope `persistent|daily|discussion|temporary`, kind `fact|preference|event|note|summary|knowledge|task`, `importance REAL DEFAULT 0.5`, `expires_at`, and `dedupe_hash`, plus `memory_chunks_fts` (FTS5) and `memory_facts`. — [schema.sql](https://github.com/leon-ai/leon/blob/develop/server/src/core/memory-manager/sql/schema.sql)
  - `server/src/core/self-model-manager.ts` writes `LEON_PRIVATE_DIARY.md` and `.leon-private-self-model.json`, with `MAX_BEHAVIORAL_PRINCIPLES = 6`, `MIN_BEHAVIORAL_PRINCIPLE_SEEN_COUNT = 2`, and `MIN_BEHAVIORAL_PRINCIPLE_CONFIDENCE = 0.72`. A principle is learned only after it has been seen at least twice with at least 0.72 confidence. — [self-model-manager.ts](https://github.com/leon-ai/leon/blob/develop/server/src/core/self-model-manager.ts)
  - `server/src/core/pulse-manager.ts` writes `PULSE.md` and `.leon-pulse-state.json`. Constants: `ACTIVE_CONVERSATION_GRACE_MS = 2 min`, `PULSE_COMPLETED_COOLDOWN_MS = 12 h`, `PULSE_FAILED_COOLDOWN_MS = 3 h`, `MAX_SUPPRESSION_POLICIES = 24`, `PULSE_MEMORY_TOKEN_BUDGET = 260`. A code comment reads "Proactive work must not displace an owner task waiting to resume." — [pulse-manager.ts](https://github.com/leon-ai/leon/blob/develop/server/src/core/pulse-manager.ts)
  - The persona is assembled in `server/src/core/llm-manager/persona.ts`, and memory includes a QMD backend (`qmd-store.ts`, `qmd-retrieval.ts`, `qmd-embed-worker.js`). — [repo tree](https://github.com/leon-ai/leon/tree/develop/server/src/core)
- **OpenVoiceOS**: `ovos-persona`'s `PersonaPipeline` "adds multi-persona management… each one assigns its own set of solver plugins". Personas are inserted into the intent pipeline (`ovos-persona-pipeline-plugin-high/low`) beside `padatious`/`adapt`, and the plugin replaces the old ChatGPT fallback skill. — [ovos-persona README](https://github.com/OpenVoiceOS/ovos-persona)
- **Home Assistant Assist**: the LLM tool bridge is in `homeassistant/helpers/llm.py` (29 KB). Conversation agents are in `components/conversation/` (`agent_manager.py`, `default_agent.py`, `chat_log.py`, `trigger.py`). A local LLM agent is in `components/ollama/` (`conversation.py`, `ai_task.py`). — [home-assistant/core](https://github.com/home-assistant/core/tree/dev/homeassistant/helpers). Voice satellites use the Wyoming peer-to-peer protocol. — [OHF-Voice/wyoming](https://github.com/OHF-Voice/wyoming)
- **Open Interpreter / 01**: 01 ("open-source voice interface for desktop, mobile, and ESP32") was last pushed 2024-11-01, so it is stale. The main repo is now Rust. — GitHub API
- **isair/jarvis**: "A private, local-first AI assistant with voice and text chat… Voice-first · Local AI · Personal memory · No subscription". It works with Ollama or an OpenAI-compatible server, has a memory-budget-aware setup ("Constrained memory | `gemma4:e2b`"), a Low Power Mode, a Memory Viewer for the "local diary and knowledge graph", stores data under `~/.local/share/jarvis`, and redacts sensitive info "before model context and saved diary entries". It is "free for personal use. For commercial use, get in touch". — [README](https://github.com/isair/jarvis), [LICENSE](https://github.com/isair/jarvis/blob/main/LICENSE) (non-commercial)
  - `src/jarvis/memory/graph.spec.md` describes a "self-organising node graph… hierarchical tree where nodes auto-split when they grow too large". It has three fixed branches (`user`, `directives`, `world`) and three fast-access entry points (recent nodes, top nodes, root). "Explicit user corrections determine the supported claim, preserving its subject and temporal scope." — [graph.spec.md](https://github.com/isair/jarvis/blob/main/src/jarvis/memory/graph.spec.md)
  - `src/jarvis/memory/recall_gate.spec.md` describes "A deterministic, no-LLM heuristic that lets the reply engine skip diary, graph and memory-digest enrichment". It skips when the hot window has a tool message and there is at least 50% content-word overlap, and it fails open. — [recall_gate.spec.md](https://github.com/isair/jarvis/blob/main/src/jarvis/memory/recall_gate.spec.md)
  - The repo has a dedicated memory eval suite (`evals/test_graph_*`, `evals/test_memory_digest_*`, `evals/test_diary_*`). — [repo tree](https://github.com/isair/jarvis/tree/main/evals)
- **Open-LLM-VTuber**: "voice-interactive AI companion… Live2D avatar", with "Voice interruption without headphones" and "AI proactive speaking". It supports many ASR/TTS backends, including sherpa-onnx, MeloTTS, and Edge TTS. "the long-term memory feature is temporarily removed (coming back soon)". — [README](https://github.com/Open-LLM-VTuber/Open-LLM-VTuber)
- **AIRI**: "a soul container of AI waifu / virtual characters", which runs in the browser via WebGPU and as a desktop app. The README roadmap lists "Memory Alaya (WIP)". — [README](https://github.com/moeru-ai/airi). ADR `docs/ai/adr/2026-10-10-skills-automations-and-memory.md` (Accepted) says:
  - "Memory is an index plus one entry per fact. The index lists every entry by its id and description, and joins the identity at the start of each run."
  - Entries are stored per character card in IndexedDB with UUIDv7 ids and tombstones, and can be promoted to "general".
  - Recipes are skills, and the tool description lists only names.
  - Automations fire on silence, interval, time of day, return-from-idle, or module observation. "Code decides each trigger from the clock and the observations, without a model call". Background tasks run in hidden sessions and report back as notices.
  - Source: [ADR](https://github.com/moeru-ai/airi/blob/main/docs/ai/adr/2026-10-10-skills-automations-and-memory.md). `packages/memory-pgvector/src/index.ts` exists but is a stub, with an empty `module:configure` handler. — [file](https://github.com/moeru-ai/airi/blob/main/packages/memory-pgvector/src/index.ts)
- **SillyTavern**: persona, character, and lorebook memory lives in `public/scripts/{personas.js,char-data.js,world-info.js}`. Extensions include `memory` (summarize), `vectors` (vector storage), `tts`, `expressions`, and `quick-reply`. — [repo tree](https://github.com/SillyTavern/SillyTavern/tree/release/public/scripts/extensions)
- **screenpipe**: "continuously captures your screen and audio, creating a searchable, AI-powered memory". It uses event-driven capture, local Whisper (Large-V3-Turbo) or Deepgram, a SQLite store, and a REST API on `localhost:3030` with a raw-SQL endpoint. "pipes" are agents with YAML-frontmatter permissions enforced deterministically. RAM use is "approximately 0.5-3 GB for capture"; "8 GB of system RAM is recommended". The license permits "personal, non-commercial use". — [README](https://github.com/screenpipe/screenpipe)
- **Omi**: "a necklace that captures conversations, apps for phone and desktop, and a backend that turns what you say into memory you can search and chat with". MIT. — [README](https://github.com/BasedHardware/omi). The backend has `backend/database/{memories.py,knowledge_graph.py,memory_ledger.py,memory_review_apply.py,memory_vector_metadata.py}`, `backend/config/memory_confidence.py` (`SOURCE_SIGNAL_CAPTURE_PRIORS`, `VERACITY_PRIORS`, `LOW_CAPTURE_THRESHOLD = 0.5`, `HIGH_CAPTURE_THRESHOLD = 0.85`), `backend/config/memory_secret_patterns.py`, and `backend/config/proactivity_v2.py` ("Small server-owned producer registry and integer budget policy"). — [backend tree](https://github.com/BasedHardware/omi/tree/main/backend)
- **nanobot (HKUDS)**: "ultra-lightweight… personal AI agent framework written in Python". It provides long-term memory through "Dream" (`/compact` then `/dream`, review via `/dream-log`), supports MCP and Ollama, and runs one Python gateway for WebUI, TUI, and chat apps. — [README](https://github.com/HKUDS/nanobot)
- **NanoClaw**: the README criticises OpenClaw's size ("nearly half a million lines"), runs each agent in a container, and follows "Skills over features". It uses the Claude Agent SDK, which means Anthropic-only by default and is not zero-cost. — [README](https://github.com/nanocoai/nanoclaw)

### Inferences
- The strongest current lineage is the "Claw" family (OpenClaw → Hermes, nanobot, NanoClaw, PicoClaw, ZeroClaw). It has converged on the same file-based identity and memory contract (SOUL.md, USER.md, MEMORY.md, daily notes, skills as SKILL.md, heartbeat/cron). Stiti can adopt the same contract as a *view* over Postgres, so it can import from and export to this ecosystem. Hermes already imports OpenClaw's files.
- None of the mature projects uses a temporal knowledge graph as its primary memory. Most use Markdown plus SQLite FTS/vector. KG memory appears as plug-ins (Graphiti, cognee, Honcho, Hindsight) or as jarvis's custom tree. Stiti's Postgres plus temporal-KG design is therefore a differentiator, not a copy.
- Khoj is the only mature reference that already uses Django ORM on Postgres with pgvector, and it has a `UserMemory` table. Its schema is the most directly reusable pattern for the "Postgres brain", but it is AGPL, so read it rather than copy code.

### Gaps
- I did not verify Khoj's or Open-LLM-VTuber's recent roadmap. Their last pushes (Aug 2026 and May 2026) suggest slowing, but not abandonment.
- I did not verify whether the Omi backend can be self-hosted with free local storage. Its database layer looked Firestore- and cloud-oriented, but I did not confirm this.
- "Awesome-llm-companions"-style lists and r/LocalLLaMA threads were not systematically mined because of time limits. Coverage of tiny or new projects (e.g. Mnemo, InnerZero, Rowboat from HN) is shallow. See [HN: Rowboat](https://hn.svelte.dev/item/46962641) and the [Mnemo write-up](https://eastondev.com/blog/en/posts/ai/20260718-mnemo-local-first-ai-memory-layer/).

---

## Q2. How does each project store identity/persona, memories, and learned behaviours, and how does it keep state independent of the LLM?

### Takeaway
Every serious project keeps state *outside* the model: Markdown files plus SQLite (OpenClaw, Hermes, Leon, nanobot), Postgres plus pgvector (Khoj, Letta), IndexedDB (AIRI), or a graph DB (Graphiti). The best ones split **persona** (SOUL.md, written by the human), **user model** (USER.md, as imperative directives that are superseded in place), **facts and episodes** (MEMORY.md plus daily logs or DB rows), **procedures** (skills or recipes), and **intentions** (cron or standing intents). The LLM is only a stateless worker inside deterministic gates.

### Cited Findings
- OpenClaw: "Deterministic gates, model judgment inside them. Scoring, thresholds, eligibility, matching, and lifecycle are deterministic code." Also: "Failures never block replies." — [memory-architecture.md](https://github.com/openclaw/openclaw/blob/main/docs/concepts/memory-architecture.md)
- OpenClaw provenance: every index entry has origin class `owner|agent|untrusted|system`, session kind, an observed timestamp, and a supersession key. Cron, heartbeat, and sub-agent sessions never produce durable memory. "Content that was injected into context from memory… is structurally marked and never re-extracted… A fact recalled one hundred times stays one fact." A web-fetch tool result taints the rest of the turn as `untrusted`. — same
- OpenClaw write path: "Durable memory has exactly one primary writer: the dreaming consolidation pass." Deep dreaming first applies a deterministic gate, ranking candidates by "retrieval relevance, recall frequency, query diversity, recency, multi-day recurrence, conceptual richness". A bounded consolidation model turn then follows. The rewrite is accepted only if it passes structural validation, fits the budget, and does not drop "more than a bounded fraction". A hash check provides optimistic concurrency, and the pre-image is stored in `DREAMS.md`. — same
- OpenClaw SOUL.md: "`SOUL.md` is where your agent's voice lives… tone, opinions, brevity, humor, boundaries… Keep `AGENTS.md` for operating rules; keep `SOUL.md` for voice". — [soul.md](https://github.com/openclaw/openclaw/blob/main/docs/concepts/soul.md)
- OpenClaw heartbeat: community guides describe a scheduled wake-up that reads `HEARTBEAT.md` (roughly a 30-minute default, keep under 50 lines). These are unofficial and unverified. — [stack-junkie](https://www.stack-junkie.com/blog/openclaw-workspace-architecture). A Jan 2026 "ClawHavoc" incident reportedly had malicious skills writing payloads into MEMORY.md/SOUL.md (single unofficial source). — [majid-mazouchi monograph](https://majid-mazouchi.github.io/autonomy/assets/posts/openclaw-architecture.html)
- Hermes: the memory snapshot is frozen per session to protect the prefix cache. Writes are scanned "for injection and exfiltration patterns and for invisible Unicode". If the char cap would be exceeded, the tool errors instead of silently dropping entries. — [Hermes memory docs](https://hermes-agent.nousresearch.com/docs/user-guide/features/memory)
- Leon: memory items carry scope, kind, importance, expiry, and dedupe hash in SQLite with FTS5. The self-model is in a private diary plus a JSON state file. — [schema.sql](https://github.com/leon-ai/leon/blob/develop/server/src/core/memory-manager/sql/schema.sql), [self-model-manager.ts](https://github.com/leon-ai/leon/blob/develop/server/src/core/self-model-manager.ts)
- jarvis: a diary of completed transactions, plus a graph whose fixed `user`, `directives`, and `world` branches feed a "warm profile". It runs on SQLite WAL. — [graph.spec.md](https://github.com/isair/jarvis/blob/main/src/jarvis/memory/graph.spec.md)
- AIRI: identity is "read… when it starts. Sessions store no system snapshot, so a card edit reaches the next run". Memory is per character card. — [AIRI ADR](https://github.com/moeru-ai/airi/blob/main/docs/ai/adr/2026-10-10-skills-automations-and-memory.md)
- Letta: memory blocks are DB rows with ids, editable by the agent, by sleep-time agents, and via API, and they can be shared across agents. — [Letta blog](https://letta.com/blog/memory-blocks)
- Khoj: `UserMemory` and `Entry` rows with pgvector embeddings in Postgres. — [models](https://github.com/khoj-ai/khoj/blob/master/src/khoj/database/models/__init__.py)

### Inferences
- For Stiti, the cleanest mapping into Postgres is:
  - `persona` (SOUL), human-edited and versioned
  - `user_directives` (USER), with `status active|superseded` and `observed_at`
  - `memories` (curated core), with importance, triggers, provenance, and supersession key
  - `episodes` (daily logs and transcripts)
  - `kg_entities` and `kg_edges`, with `valid_from`/`valid_to` (Graphiti-style)
  - `lessons` (corrections), `skills`, and `intents` (prospective)
  
  Optionally export them as Markdown for inspection and for Hermes/OpenClaw compatibility.
- Copy OpenClaw's provenance and recall-loop rules verbatim as invariants. They are cheap (a few columns) and address the main failure mode of always-on companions, which is memory filling with scaffolding and self-echo.

### Gaps
- I could not confirm the official OpenClaw HEARTBEAT.md defaults from first-party docs within the time budget. `docs/automation/` in the tarball covers this but was not read.

---

## Q3. Feature-by-feature comparison (each feature compares 10 or more papers and architectures before recommending)

### Takeaway
Recommended stack for Stiti:
- **Architecture**: a CoALA-style module split, implemented as an OpenClaw/Hermes-style local gateway with a MemGPT-style tiered context.
- **Persona**: a short human-owned SOUL record, kept separate from operating rules.
- **User model**: PrefEval/OpenClaw-style imperative directives, superseded in place, plus a Graphiti-style temporal KG for facts.
- **Learning from corrections**: Reflexion/ExpeL/MemPrompt-style "lessons" with Leon's seen-count and confidence gate, plus Hermes's skill write-approval.
- **Proactivity**: deterministic triggers (OpenClaw standing intents, AIRI automations, Leon pulse) with cooldowns and budgets.
- **Connectors**: MCP plus SKILL.md-style skills.

### Cited Findings

All arXiv titles and years below were verified via the arXiv API (`export.arxiv.org/api/query`).

#### Feature A: Overall assistant architecture

| Name | Link | Year | Core mechanism | Strengths | Weaknesses | 8 GB M2 / free? |
|---|---|---|---|---|---|---|
| CoALA: Cognitive Architectures for Language Agents | https://arxiv.org/abs/2309.02427 | 2023 | Working, episodic, semantic, and procedural memory plus a decision loop | Clean vocabulary for module boundaries | Conceptual only, no code | N/A (design) |
| MemGPT | https://arxiv.org/abs/2310.08560 | 2023 | LLM-as-OS: main context vs. archival/recall storage, paging via function calls | Explicit context budget, self-edits memory | Relies on a strong tool-calling LLM; small local models struggle | Design yes; Letta server is heavy |
| ReAct | https://arxiv.org/abs/2210.03629 | 2022 | Interleaved reasoning and tool actions | Basis of all tool loops | No memory story | Yes |
| Generative Agents | https://arxiv.org/abs/2304.03442 | 2023 | Memory stream, retrieval by recency, importance, and relevance, then reflection and planning | Proven retrieval score, reflections | Many LLM calls per tick | Scoring yes; full sim costly |
| MemOS (paper) | https://arxiv.org/abs/2507.03724 | 2025 | Memory as an OS resource (MemCube), scheduling across plaintext, activation, and parameter memory | Unifies memory types | Complex, research-grade | Partially |
| OpenClaw | https://github.com/openclaw/openclaw | 2026 | Node gateway, channels, workspace files, SQLite index, dreaming, cron, skills | Most complete documented design, MIT, LLM-agnostic | ~274 MB unpacked package, very large surface; security incidents reported | Gateway runs on Node, fine; local LLM is the bottleneck |
| Hermes Agent | https://github.com/NousResearch/hermes-agent | 2026 | Python gateway, capped MEMORY/USER, FTS5 sessions, skills learning loop, memory-provider plugins | Simpler than OpenClaw, Python | Fewer deterministic gates than OpenClaw | Yes (API LLM or Ollama) |
| Letta | https://github.com/letta-ai/letta | 2023–26 | Server with Postgres-persisted memory blocks, archival memory, sleep-time agents | Postgres-native, mature API | Server-heavy; sleep-time is experimental | Feasible but heavy beside a local LLM |
| Leon | https://github.com/leon-ai/leon | 2026 | TS server: smart, controlled, and agent modes; native skills (Skills → Actions → Tools → Functions); layered memory; self-model; pulse | Deterministic "controlled" path for cheap intents | Core mid-rebuild | Yes |
| nanobot (HKUDS) | https://github.com/HKUDS/nanobot | 2026 | Small Python core, gateway, Dream memory, MCP | Readable, small | Less memory rigor | Yes |
| isair/jarvis | https://github.com/isair/jarvis | 2026 | Voice daemon, planner, recall gate, diary plus KG, Ollama | Built for constrained local RAM | Non-commercial license | Yes (designed for it) |
| Home Assistant Assist | https://github.com/home-assistant/core | 2026 | Intent pipeline (default agent) with LLM agents falling back; `helpers/llm.py` exposes tools | Deterministic-first voice intents, Wyoming satellites | Home-centric, no user model | Yes |
| OVOS | https://github.com/OpenVoiceOS/ovos-core | 2026 | Message-bus voice OS, ordered intent pipeline (adapt/padatious, then persona solvers) | Mature offline voice pipeline | Small community, Python plugin sprawl | Yes |

Recommendation: Use CoALA's four memory types as the schema vocabulary. Use OpenClaw's gateway, workspace, dreaming, and two-lane recall design as the runtime blueprint, re-implemented on Postgres. Use Leon's and Home Assistant's "deterministic intent first, LLM second" routing for voice latency. Do not adopt the Letta server: it duplicates the Postgres brain and is heavy on 8 GB. Borrow only the memory-block concept.

#### Feature B: Persona and identity storage

| Name | Link | Year | Core mechanism | Strengths | Weaknesses | 8 GB / free? |
|---|---|---|---|---|---|---|
| OpenClaw SOUL.md / AGENTS.md | https://github.com/openclaw/openclaw/blob/main/docs/concepts/soul.md | 2026 | Short voice file injected each session; operating rules kept separately | Clear voice vs. rules split | Prompt-only, can be poisoned by skills | Yes |
| Hermes SOUL.md + `/personality` | https://github.com/NousResearch/hermes-agent | 2026 | Persona file plus switchable personalities per profile | Profiles isolate memory | Same prompt-only limit | Yes |
| AIRI character cards | https://github.com/moeru-ai/airi | 2026 | Identity read per run from the card; memory scoped per card | Edits apply on the next run, no stale snapshot | Browser IndexedDB storage | Yes |
| SillyTavern personas + character cards (`personas.js`, `char-data.js`) | https://github.com/SillyTavern/SillyTavern | 2023–26 | Character card JSON (description, personality, scenario, examples) plus user persona | De facto companion format, huge ecosystem | AGPL; roleplay-oriented | Yes |
| elizaOS character files | https://github.com/elizaOS/eliza | 2024–26 | JSON character (bio, lore, style, examples) | Structured persona fields | Crypto/social-bot focus | Yes |
| OVOS personas | https://github.com/OpenVoiceOS/ovos-persona | 2026 | Persona = named set of solver plugins in the intent pipeline | Persona as routing, not just prompt | Minimal style control | Yes |
| Leon `persona.ts` + self-model | https://github.com/leon-ai/leon/blob/develop/server/src/core/llm-manager/persona.ts | 2026 | Persona assembly plus private diary and self-model JSON | Persona evolves with bounded principles | Complexity | Yes |
| Character-LLM | https://arxiv.org/abs/2310.10158 | 2023 | Fine-tunes a model on character experiences | Deep consistency | Needs training; ties persona to weights (against Stiti's swappable-LLM rule) | No (training) |
| RoleLLM | https://arxiv.org/abs/2310.00746 | 2023 | Role-play benchmark plus role-conditioned prompting/tuning | Evaluation method for persona fidelity | Tuning-centric | Eval idea only |
| PersonaChat | https://arxiv.org/abs/1801.07243 | 2018 | Persona as a few profile sentences conditioning dialogue | Shows short persona statements work | Old models | Concept |
| Open-LLM-VTuber character config | https://github.com/Open-LLM-VTuber/Open-LLM-VTuber | 2026 | Persona prompt plus Live2D plus voice clone per character | Full embodiment | Memory removed | Yes |

Recommendation: Store persona as a versioned Postgres row (`persona_versions`) rendered to a short SOUL text. Only the owner edits it, and the agent may only propose diffs. Keep operating rules (AGENTS) separate from voice (SOUL), as OpenClaw does. Reject weight-level persona (Character-LLM) because the LLM must remain swappable. Adopt AIRI's "no system snapshot" rule so persona edits take effect on the next turn.

#### Feature C: User modeling

| Name | Link | Year | Core mechanism | Strengths | Weaknesses | 8 GB / free? |
|---|---|---|---|---|---|---|
| PrefEval | https://arxiv.org/abs/2502.09597 | 2025 | Benchmark: preference following decays over long conversations | Evidence for restating directives near the query | Benchmark only | N/A |
| HorizonBench | https://arxiv.org/abs/2604.17283 | 2026 | Long-horizon personalization with evolving preferences | Shows stale-preference failure | New, unreplicated | N/A |
| PersonaMem ("Know Me, Respond to Me") | https://arxiv.org/abs/2504.14225 | 2025 | Benchmark for dynamic user profiling | Tests profile evolution | Benchmark | N/A |
| LaMP | https://arxiv.org/abs/2304.11406 | 2023 | Retrieval of the user's own history for personalization | Simple retrieval baseline | Task-specific | Yes |
| Personalization of LLMs: survey | https://arxiv.org/abs/2411.00027 | 2024 | Taxonomy of personalization methods | Map of the field | Survey | N/A |
| Hello Again! (LD-Agent) | https://arxiv.org/abs/2406.05925 | 2024 | Event summaries plus persona extraction for user and agent | Dual persona modules | Research code | Yes |
| Reflective Memory Management (RMM) | https://arxiv.org/abs/2503.08026 | 2025 | Prospective (topic summaries) and retrospective (retrieval feedback) reflection | Learns what to retrieve | Extra LLM calls | Mostly |
| OpenClaw USER.md | https://github.com/openclaw/openclaw/blob/main/docs/concepts/user-model.md | 2026 | Imperative directives, `<!-- observed: date \| status: active -->`, supersede in place, small budget | Evidence-based, inspectable | File-based | Yes |
| Hermes USER.md (1,375 chars) | https://hermes-agent.nousresearch.com/docs/user-guide/features/memory | 2026 | Capped profile, agent add/patch/remove | Forces compaction | Tiny cap loses detail | Yes |
| Honcho | https://github.com/plastic-labs/honcho | 2026 | Memory library for "stateful agents" with peer/user representations (OpenClaw and Hermes plug-in) | Purpose-built user modeling | AGPL; server | Self-host feasible |
| Graphiti / Zep | https://github.com/getzep/graphiti · https://arxiv.org/abs/2501.13956 | 2025 | Temporal KG: episodes → entities and edges with validity intervals; invalidates rather than deletes | Temporal "what was true when" | Needs graph DB (Neo4j/FalkorDB/Kuzu) plus LLM extraction calls | Kuzu/FalkorDB light; extraction cost |
| Mem0 | https://github.com/mem0ai/mem0 · https://arxiv.org/abs/2504.19413 | 2025 | LLM extract, then ADD/UPDATE/DELETE/NOOP against existing memories; optional graph | Simple update ops | LLM call per write | Yes with pgvector |
| jarvis KG (`user`/`directives`/`world`) | https://github.com/isair/jarvis/blob/main/src/jarvis/memory/graph.spec.md | 2026 | Auto-splitting topic tree, warm profile | Directives separated from facts | Non-commercial | Yes |
| Omi memory confidence | https://github.com/BasedHardware/omi/tree/main/backend/config | 2026 | Source/veracity priors, capture thresholds 0.5/0.85 | Confidence-gated capture of ambient speech | Cloud-oriented backend | Partially |

Recommendation: Use two complementary structures:
1. A small **directive table** (OpenClaw USER.md contract: imperative, one directive per row, `status active|superseded`, `observed_at`, supersede in place). Render it near the query each turn, which PrefEval supports.
2. A **temporal KG** for facts about the user's world (Graphiti's bi-temporal edges and invalidation), implemented on Postgres tables, or Apache AGE if Cypher is needed, to avoid Neo4j on 8 GB.

Use Mem0-style ADD/UPDATE/DELETE/NOOP to reconcile new facts. Use Omi-style confidence priors to gate what voice-derived facts get stored.

#### Feature D: Learning from corrections ("learned lessons")

| Name | Link | Year | Core mechanism | Strengths | Weaknesses | 8 GB / free? |
|---|---|---|---|---|---|---|
| MemPrompt ("Memory-assisted prompt editing") | https://arxiv.org/abs/2201.06009 | 2022 | Store user feedback on misunderstandings; retrieve and prepend on similar queries | Exactly the "correction → lesson" pattern | Old models | Yes |
| Reflexion | https://arxiv.org/abs/2303.11366 | 2023 | Verbal self-reflection stored as episodic memory after failure | No weight updates | Needs a failure signal | Yes |
| ExpeL | https://arxiv.org/abs/2308.10144 | 2023 | Extract cross-task insights from successes and failures; ADD/EDIT/UPVOTE/DOWNVOTE insight ops | Vote-based insight lifecycle | Batch-oriented | Yes |
| CLIN | https://arxiv.org/abs/2310.10134 | 2023 | Continually updated causal-abstraction memory | Generalizes across tasks | Environment-specific | Yes |
| Self-Refine | https://arxiv.org/abs/2303.17651 | 2023 | Iterative self-feedback within a turn | Simple | Not persistent | Yes |
| Agent Workflow Memory | https://arxiv.org/abs/2409.07429 | 2024 | Induce reusable workflows from trajectories | Procedural memory | Web-task focus | Yes |
| AutoManual | https://arxiv.org/abs/2405.16247 | 2024 | Build rule "manuals" from interaction | Rules readable by humans | Env-specific | Yes |
| Voyager | https://arxiv.org/abs/2305.16291 | 2023 | Executable skill library grown from experience | Origin of the "skills from experience" idea | Minecraft | Concept |
| Hermes skills learning loop + curator | https://github.com/NousResearch/hermes-agent/blob/main/agent/curator.py | 2026 | Background review creates or patches skills; deterministic inactivity prune; optional write approval | Production self-improvement with staging (`/skills pending/diff/approve`) | Risk of skill bloat or poisoning | Yes |
| Leon self-model behavioural principles | https://github.com/leon-ai/leon/blob/develop/server/src/core/self-model-manager.ts | 2026 | Principles kept only if seen 2 or more times and confidence ≥ 0.72; max 6 | Hard gates against one-off overfitting | Small cap | Yes |
| OpenClaw dreaming promotion gate | https://github.com/openclaw/openclaw/blob/main/docs/concepts/dreaming.md | 2026 | Recall-frequency and recurrence ranking, then bounded consolidation with rollback | Memory "graduates because it kept being useful" | Many tuning knobs | Yes |
| jarvis corrections in KG | https://github.com/isair/jarvis/blob/main/src/jarvis/memory/graph.spec.md | 2026 | "Explicit user corrections determine the supported claim, preserving its subject and temporal scope" | Corrections override facts with temporal scope | Non-commercial | Yes |
| Sleep-time Compute | https://arxiv.org/abs/2504.13171 | 2025 | Pre-compute and digest context offline | Justifies night-time consolidation | — | Yes (cheap free-tier model at night) |
| A-MEM | https://arxiv.org/abs/2502.12110 | 2025 | Zettelkasten-style notes with links that evolve existing memories | Memory evolution | Many LLM calls | Yes |

Recommendation: Create a `lessons` table: trigger context (embedding plus keywords), the lesson as an imperative, source (explicit correction vs. inferred), `seen_count`, confidence, status, and `superseded_by`. Explicit user corrections ("no, I meant…", "don't do X") become lessons immediately with owner provenance, following MemPrompt and jarvis. Inferred lessons follow Leon's gate (seen at least 2 times, confidence ≥ 0.72) and ExpeL's upvote/downvote lifecycle. Consolidate them nightly in a "dreaming" job (OpenClaw, sleep-time compute) using a free-tier LLM. Procedural lessons become skills only with owner approval (Hermes `write_approval`).

#### Feature E: Proactivity

| Name | Link | Year | Core mechanism | Strengths | Weaknesses | 8 GB / free? |
|---|---|---|---|---|---|---|
| Proactive Agent | https://arxiv.org/abs/2410.12361 | 2024 | Predicts when to offer help from observed user activity; ProactiveBench | Learned "should I speak" model | Needs activity data | Concept |
| Survey on Proactive Dialogue Systems | https://arxiv.org/abs/2305.02750 | 2023 | Taxonomy: target-guided, non-collaborative, enriched dialogue | Field map | Survey | N/A |
| TriggerBench (prospective memory) | https://arxiv.org/abs/2606.23459 | 2026 | Benchmark: LLMs forget to act on stored intentions as context grows | Justifies compiling intents out of the LLM | New | N/A |
| Generative Agents planning | https://arxiv.org/abs/2304.03442 | 2023 | Daily plans, recursively decomposed, reactive replanning | Plans plus reflection | Costly | Partly |
| OpenClaw standing intents + cron | https://github.com/openclaw/openclaw/blob/main/docs/concepts/standing-intents.md | 2026 | Time intents → cron. Event intents → SQLite with keywords or embedding, scope, expiry, fire budget, cooldown. States pending/armed/fired/done/cancelled/expired. Defaults: 24 h cooldown, 3 fires, 90-day expiry, ≤ 3 per turn | Deterministic, anti-nagging by design | Reactive to inbound messages | Yes |
| OpenClaw heartbeat (HEARTBEAT.md) | community guide: https://www.stack-junkie.com/blog/openclaw-workspace-architecture | 2026 | Periodic wake-up that reads a checklist | Simple | Token cost per tick | Yes |
| Leon pulse | https://github.com/leon-ai/leon/blob/develop/server/src/core/pulse-manager.ts | 2026 | Periodic planner with pending matters, suppression policies, cooldowns (12 h done, 3 h failed, escalating declines), 2-minute grace during active conversation | Respects the user, learns suppression | Complex | Yes |
| AIRI automations | https://github.com/moeru-ai/airi/blob/main/docs/ai/adr/2026-10-10-skills-automations-and-memory.md | 2026 | Triggers: silence, interval, local time and weekday, return-from-idle (system idle time), module observation. Decided by code with no model call; cooldowns; background tasks report as notices | Return-from-idle trigger is a good fit for a desktop voice buddy | Owner-approved recipes only | Yes |
| Omi proactivity_v2 | https://github.com/BasedHardware/omi/blob/main/backend/config/proactivity_v2.py | 2026 | Producer registry plus integer budget policy | Budgeted interruptions | Cloud backend | Partly |
| Open-LLM-VTuber "AI proactive speaking" | https://github.com/Open-LLM-VTuber/Open-LLM-VTuber | 2025–26 | Companion speaks unprompted after silence | Companion feel | Shallow, no memory | Yes |
| Khoj automations / "smart notifications" | https://github.com/khoj-ai/khoj | 2024–26 | Scheduled research queries emailed to the user | Simple scheduled jobs | Email-centric | Yes |
| screenpipe pipes | https://github.com/screenpipe/screenpipe | 2026 | Agents triggered from screen and audio history, permissions in YAML frontmatter | Context-aware triggers | Non-commercial; 0.5–3 GB RAM | Tight on 8 GB with a local LLM |

Recommendation: Compile intentions out of the LLM, as TriggerBench and OpenClaw argue. Use an `intents` table with explicit lifecycle states and the OpenClaw defaults (cooldown, fire budget, expiry, per-turn cap), scheduled with pg_cron or a Node/Python scheduler. Add AIRI's code-decided triggers (return-from-idle, time-of-day) and Leon's suppression and decline cooldowns so Stiti does not nag. Speak proactively only when the budget allows, as in Omi's integer budget.

#### Feature F: Connectors / skills layer

| Name | Link | Year | Core mechanism | Strengths | Weaknesses | 8 GB / free? |
|---|---|---|---|---|---|---|
| Toolformer | https://arxiv.org/abs/2302.04761 | 2023 | Self-supervised learning of API calls | Origin of tool use | Requires training | No |
| Gorilla | https://arxiv.org/abs/2305.15334 | 2023 | Retrieval-aware API-call generation | Doc retrieval reduces hallucinated calls | Model-specific | Concept |
| ToolLLM | https://arxiv.org/abs/2307.16789 | 2023 | 16k+ APIs, DFS tool-planning | Scale | Training-centric | Concept |
| Voyager skill library | https://arxiv.org/abs/2305.16291 | 2023 | Code skills retrieved by embedding | Composable skills | Domain-specific | Concept |
| MCP (Model Context Protocol) | https://modelcontextprotocol.io | 2024–26 | Standard tool, resource, and prompt servers; OpenClaw bundles `@modelcontextprotocol/sdk` | Universal ecosystem, LLM-agnostic | Each server is a process (RAM) | Yes; watch server count |
| OpenClaw skills (52 bundled, ClawHub) | https://github.com/openclaw/openclaw | 2026 | SKILL.md folders, e.g. `apple-notes`, `apple-reminders`, `obsidian`, `things-mac`, `openai-whisper`, `sherpa-onnx-tts` | macOS connectors ready to copy | Supply-chain risk (ClawHavoc report) | Yes |
| Hermes skills + agentskills.io hub | https://github.com/NousResearch/hermes-agent | 2026 | SKILL.md procedural memory, auto-created, approval staging | Self-extending | Bloat | Yes |
| Leon native skills | https://github.com/leon-ai/leon | 2026 | Skills → Actions → Tools → Functions (→ Binaries), plus agent `SKILL.md` | Deterministic path for common voice commands | Heavier authoring | Yes |
| Home Assistant LLM API (`helpers/llm.py`) | https://github.com/home-assistant/core/blob/dev/homeassistant/helpers/llm.py | 2024–26 | Exposes HA intents and entities as LLM tools | Smart-home control | HA-only | Yes (can run HA separately) |
| OVOS skills + persona solvers | https://github.com/OpenVoiceOS/ovos-core | 2026 | Message-bus skills, intent parsers (adapt, padatious) | Offline voice intents | Python plugin sprawl | Yes |
| AIRI recipes | https://github.com/moeru-ai/airi/blob/main/docs/ai/adr/2026-10-10-skills-automations-and-memory.md | 2026 | Tool lists only recipe names; steps loaded on call; keyword triggers | Saves tokens (progressive disclosure) | Browser storage | Yes |
| screenpipe permissions model | https://github.com/screenpipe/screenpipe | 2026 | Deterministic three-layer gating (skill gating, agent interception, server middleware tokens) | Strong least-privilege model | Non-commercial license | Ideas only |

Recommendation: Use MCP as the connector bus, so connectors stay LLM-agnostic and can be reused from the ecosystem. Use SKILL.md-style skills (OpenClaw, Hermes, AIRI progressive disclosure) for procedures, indexed in Postgres. Port a handful of OpenClaw's macOS skills (apple-reminders, apple-notes, weather, obsidian) by reading their SKILL.md files. Add a Leon/Home Assistant-style deterministic intent layer for the top ~20 voice commands, so they need no LLM call. Enforce screenpipe/OpenClaw-style provenance and permission gating on any skill that writes memory.

### Inferences
- Across all six features, the same principle recurs: *the LLM proposes, deterministic code disposes*. OpenClaw's gates, jarvis's recall gate, AIRI's code-decided triggers, Leon's thresholds, and Hermes's write approval all follow it. This principle fits Stiti's "brain is the memory engine, LLM is a plug" thesis directly.
- 8 GB constraint: running a local LLM (3–4B at Q4, ~2.5–3.5 GB), Whisper, TTS, Postgres, and a KG extraction pipeline concurrently is tight. The jarvis README explicitly budgets memory for Whisper plus the chat and fast models. Offload KG extraction and dreaming to free-tier cloud LLMs at idle times, and keep local inference for the low-latency path.

### Gaps
- The OpenClaw `dreaming.md` and `standing-intents.md` pages in the tarball were summarised from `memory-architecture.md`, which restates them. They were not read in full.
- I found no benchmark comparing these personal-assistant memory systems head to head on the same hardware.
- I did not verify current MCP specification details (only the URL).

---

## Q4. Who documented building such systems? Useful write-ups

### Takeaway
The highest-value write-ups are first-party design docs, not blogs. OpenClaw's `docs/concepts/*` cites the research behind each decision (LongMemEval, Generative Agents, PrefEval, HorizonBench, TriggerBench, sleep-time compute). Other useful first-party sources are the Hermes memory docs, Letta's memory-blocks and sleep-time posts, jarvis's `*.spec.md` files, and AIRI's ADRs and devlogs. Community OpenClaw explainers are plentiful but unofficial.

### Cited Findings
- OpenClaw concept docs (memory architecture, user model, soul, dreaming, standing intents, active memory, memory provenance). The memory docs cite LongMemEval (arXiv:2410.10813), Generative Agents (2304.03442), sleep-time compute (2504.13171), PrefEval (2502.09597), HorizonBench (2604.17283), TriggerBench (2606.23459), OWASP Agentic ASI06, and MINJA. — [docs/concepts](https://github.com/openclaw/openclaw/tree/main/docs/concepts)
- Hermes Agent memory docs. — [hermes-agent.nousresearch.com](https://hermes-agent.nousresearch.com/docs/user-guide/features/memory)
- Letta blog: "Memory Blocks". — [letta.com/blog/memory-blocks](https://letta.com/blog/memory-blocks). Letta sleep-time docs. — [docs.letta.com](https://docs.letta.com/guides/agents/architectures/sleeptime/index.md)
- Zep paper "A Temporal Knowledge Graph Architecture for Agent Memory". — [arXiv:2501.13956](https://arxiv.org/abs/2501.13956). Mem0 paper. — [arXiv:2504.19413](https://arxiv.org/abs/2504.19413)
- AIRI devlogs (e.g. "DevLog @ 2026.01.01: AIRI Pocket and FlowChat memory experiments"). — [AIRI README](https://github.com/moeru-ai/airi). ADR on skills, automations, and memory. — [ADR](https://github.com/moeru-ai/airi/blob/main/docs/ai/adr/2026-10-10-skills-automations-and-memory.md)
- isair/jarvis (author Baris Sencan per LICENSE): spec-per-module docs (`graph.spec.md`, `recall_gate.spec.md`, `db.spec.md`, `summariser.spec.md`, `personal_context.spec.md`). — [repo](https://github.com/isair/jarvis/tree/main/src/jarvis/memory)
- NanoClaw README: an argument for small, auditable personal agents versus OpenClaw's size. — [README](https://github.com/nanocoai/nanoclaw)
- Community OpenClaw explainers (unofficial; quality varies):
  - [Four Things OpenClaw Got Right](https://deadneurons.substack.com/p/four-things-openclaw-got-right)
  - [How OpenClaw Works](https://notesfromzero.substack.com/p/how-openclaw-works)
  - [How AI Agents Remember: OpenClaw's Memory System](https://sameeraman.github.io/blog/2026/03/31/openclawmemory)
  - [I Studied OpenClaw Memory System](https://gaodalie.substack.com/p/i-studied-openclaw-memory-system)
  - [OpenClaw architecture monograph](https://majid-mazouchi.github.io/autonomy/assets/posts/openclaw-architecture.html)
  - [OpenClaw-inspired self-evolving assistant](https://cynthialmy.github.io/2026-02-27-self-evolving-ai-assistant/)
  - [DEV: personal AI assistant that remembers me](https://dev.to/openclaw_store/how-i-built-a-personal-ai-assistant-that-actually-remembers-me-e28) (the author sells setups)
- DEV: "Building a local AI assistant with memory, PostgreSQL and multi-model support" (Ollama plus Postgres, with an emphasis on filtering what gets stored). — [dev.to](https://dev.to/rohitrajvaidya5/building-a-local-ai-assistant-with-memory-postgresql-and-multi-model-support-update-4cod)
- Recent papers on person modeling: PersonaTree (2026, three-level evidence → pattern → persona-claim tree), via [alphaxiv](https://www.alphaxiv.org/abs/2606.04780.md). O-Mem, via [arXiv:2511.13593](https://arxiv.org/html/2511.13593v1). Neither was read in full.
- HN Show HN items: [Rowboat (work → knowledge graph)](https://hn.svelte.dev/item/46962641), [Echo (local journal/notes AI)](https://hn.svelte.dev/item/44923099), and [Mnemo (Rust, SQLite, petgraph memory layer)](https://eastondev.com/blog/en/posts/ai/20260718-mnemo-local-first-ai-memory-layer/).

### Inferences
- For Stiti's design doc, cite OpenClaw's research-backed rules directly. They have already done the literature-to-design translation.

### Gaps
- I found no first-party blog by OpenClaw's maintainers or by Simon Willison specifically on OpenClaw memory. A search for Willison returned only third-party guides.
- I did not locate talks or videos.

---

## Q5. Which projects are TypeScript/Electron/npm-packaged (rea targets) and which are Python (read source)? What did rea reveal?

### Takeaway
The TS/JS/npm targets for rea are OpenClaw (npm `openclaw`), AIRI (TS/Electron/Tauri), Leon, SillyTavern (JS), letta-code, NanoClaw, LifeOS, elizaOS, and MemOS (TS). Python projects should be read as source: Hermes, Khoj, jarvis, Open-LLM-VTuber, OVOS, Home Assistant, Omi backend, nanobot, Mem0, Graphiti, Honcho, Hindsight, and cognee. Rust/Go projects (screenpipe, Open Interpreter, ZeroClaw, PicoClaw) need neither. For OpenClaw, rea was barely necessary: the npm tarball ships its full `docs/` tree and readable `dist/` chunk names, which already exposed the memory architecture.

### Cited Findings
- Language and packaging (GitHub API, 2026-11-10): see the catalogue table in Q1.
- **rea hands-on (bounded ~10 minutes)**:
  - Setup: created a new empty directory `/private/tmp/claude-501/-Users-tejmul-Stiti/438cc315-bb0b-4ab1-b313-887493e51886/scratchpad/rea-openclaw/`, ran `npm pack openclaw --ignore-scripts`, and extracted the tarball to `extracted/`. No package code or install scripts were executed. The tarball was `openclaw-2026.9.2.tgz` (58 MB, 9,707 files, 194 MB extracted), even though `npm view openclaw dist-tags` reports `latest: 2026.11.2`, `beta: 2026.11.5-beta.1`, and `extended-stable: 2026.9.36`. The cause is likely the local npm cache or registry resolution. Re-run `npm pack openclaw@2026.11.2` to get the newest version.
  - Node version: rea (`rea-agents@6.8.0`) declares `engines: ^22.23.4 || ^24.22.1 || >=26.12.1`. On Node v26.0.0 npm printed `npm warn EBADENGINE Unsupported engine { package: 'rea-agents@6.8.0', required: { node: '^22.23.4 || ^24.22.1 || >=26.12.1' }, current: { node: 'v26.0.0', npm: '11.12.1' } }`, **but rea did not refuse**. It ran (`analyze_javascript_application` → "Processing 7538 selected application files"), using a worker with `--max-old-space-size=1024`. The fix for a clean run is to upgrade Node to ≥ 26.12.1, or use Node 24.22.1+ LTS (for example `brew upgrade node`, or `nvm install 24`).
  - Note: the first attempt failed with `(eval):1: command not found: timeout` because macOS has no GNU `timeout`. Use `gtimeout` from coreutils, or run without it.
  - **Run 1 (whole package, 7,538 files)**: it failed after about 6 minutes with `{"error":"JavaScript application analysis failed","code":"execution_failure", ... "diagnostics":{"source_path":"dist/control-ui/assets/sw-refresh.runtime-CfiqJg48.js","phase":"startup","message":"spawn /opt/homebrew/Cellar/node/26.0.0/bin/node ENOENT"}}`.
    - Cause: Homebrew Node was upgraded to **v26.13.0** while rea was running, apparently by another process on the machine, so the Cellar path of the old binary disappeared. Node 26.13.0 now satisfies rea's `>=26.12.1` requirement.
    - Partial output (243 MB JSON) before the failure: 1,538 files parsed, 5,864 skipped, 5.3M AST nodes, 19,021 findings, and a semantic graph of 51,486 nodes and 43,714 relations. It also recorded 1,413 "Resource constraint… exceed the parent's result budget" limitations, so whole-package runs are too big.
    - Electron summary: 0 BrowserWindows, 0 preload entrypoints, 0 IPC channels, and 0 native addon bindings. rea therefore confirms OpenClaw is a Node CLI/gateway plus a web control UI (`dist/control-ui/`), **not an Electron app**. It recovered 0 HTTP routes, with 6,011 unknowns.
  - **Run 2 (Node 26.13.0, bounded subset)**: 26 memory-related chunks were copied into a new directory (`dreaming-*`, `agent-runner-memory-*`, `context-engine-*`, `doctor-agent-memory-schema-*`, `cron-tool-*`), and rea was run against that directory. It **succeeded (exit 0)** in under a minute, producing 25,741 nodes, 26,767 relations, and 368 named functions. Function inventory revealing the memory pipeline:
    - Ingestion: `ingestSessionTranscriptSignals`, `ingestDailyMemorySignals`, `collectSessionIngestionBatches`, `seedHistoricalDailyMemorySignals`
    - Dreaming phases: `runLightDreaming`, `prioritizeLightEntriesByDiaryCoverage`, `runRemDreaming`, `buildRemReflections`, `selectRemCandidateTruths`, `calculateCandidateTruthConfidence`, `runDreamingSweepPhases`, `updateDeepDreamsFile`, `writeDeepDreamingReport`
    - Dream diary and narrative: `generateAndAppendDreamNarrative`, `dedupeDreamDiaryEntries`
    - Write safety: `writeDreamsFileAtomic`, `withMemoryWorkspaceLock`
    - Compaction flush: `shouldRunMemoryFlush`, `runMemoryFlushIfNeeded`, `hasAlreadyFlushedForCurrentCompaction`
    - Context engine and maintenance: the context-engine turn-intent queue (`enqueueContextEngineTurnIntent`, `acceptContextEngineTurnIntent`), `resolveMaintenanceGateState`, `repairDoctorAgentMemorySchemas`
    - String literals include `"0 3 * * *"`, `"## REM Sleep"`, `"DREAMS.md"`, `"memory-core"`, and phase names `"light"`/`"rem"`. The `"0 3 * * *"` literal suggests a 03:00 nightly dreaming cron default. This is inferred from the literal only, not confirmed in the docs.
- What the tarball revealed without rea:
  - `docs/concepts/` contains 60+ design docs: memory-architecture, soul, user-model, dreaming, active-memory, standing-intents, context-engine, memory-provenance, multi-user, presence, and others.
  - `dist/` has 5,804 bundled chunks with descriptive names: `dreaming-phases-*.js`, `dreaming-narrative-*.js`, `dreaming-ingestion-state-*.js`, `agent-runner-memory-*.js`, `context-engine-lifecycle-*.js`, `cron-tool-*.js`, `clawhub-skills-*.js`, `doctor-agent-memory-schema-*.js`, `doctor-heartbeat-cadence-migration-*.js`.
  - `skills/` holds 52 SKILL folders. Dependencies show `kysely` (SQL query builder) and `croner` (cron).
  - Source: local inspection of the npm tarball; the same files are at [github.com/openclaw/openclaw](https://github.com/openclaw/openclaw).

### Inferences
- For OpenClaw, read `docs/concepts/*.md` from the tarball or GitHub first, then the `dreaming-*` and `agent-runner-memory-*` dist chunks. rea is most valuable for closed or minified Electron apps (e.g. desktop builds of AIRI or the screenpipe app UI), not for projects with public source.
- On 8 GB, rea on a 7.5k-file bundle is CPU-heavy (99% CPU for one worker) and slow, at roughly 1,400 files in 3 minutes. Point it at `dist/` subsets, not whole packages.

### Gaps
- The full-package rea analysis did not finish because Node was upgraded mid-run. A clean full run should target `dist/` subsets now that Node 26.13.0 is installed. rea outputs are in the scratchpad: `/private/tmp/claude-501/-Users-tejmul-Stiti/438cc315-bb0b-4ab1-b313-887493e51886/scratchpad/rea-openclaw/rea-out.json` (partial, failed) and `/private/tmp/claude-501/-Users-tejmul-Stiti/438cc315-bb0b-4ab1-b313-887493e51886/scratchpad/rea-openclaw-memsubset/out.json` (succeeded).
- rea does not explain behaviour or thresholds. It gives structure (function names, literals, relations). Thresholds such as promotion weights are still best read in the docs or in the readable dist JS.
