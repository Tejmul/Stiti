# Stiti — Master Plan (v2, after deep research)

Motive and ground rules: [../CLAUDE.md](../CLAUDE.md) · Full research report (≈14k words,
≥10 papers/architectures per feature): [../reports/Stiti personal AI buddy research.md](<../reports/Stiti personal AI buddy research.md>)
· Raw notes: [../research_notes/](../research_notes/) · Decisions log: [DECISIONS.md](DECISIONS.md)

> **Build the brain before the mouth.** Every serious assistant studied works the same way:
> *the LLM proposes, plain code decides.* Stiti = one local Postgres memory engine + Laya
> decisions + a thin router to free cloud LLMs. Voice plugs into the same `turn()` later.

---

## 1. Architecture

```
 mic ─► VAD + Smart Turn ─► Whisper STT ─┬─► transcript ──┐
                            emotion2vec+ ─┘ (voice mood)  │
 text / Telegram ─────────────────────────────────────────┤
                                                          ▼
                        ┌──────────── STITI ENGINE (Python daemon) ────────────┐
                        │ 1. LAYA: one pass, 13 typed questions                 │
                        │    (domain, action, needs_llm, is_correction, mood,   │
                        │     tone, memory_needed, privacy_level, …)            │
                        │ 2. FAST PATH (no LLM): todos, alarms, recall, control │
                        │ 3. RECALL (Postgres, <100 ms):                        │
                        │    vector + full-text → RRF → recency/importance      │
                        │    + current facts 1–2 hops + matched lessons         │
                        │ 4. CONTEXT COMPILER → briefing ≤1,500 tokens          │
                        │ 5. ROUTER → Groq → Cerebras → OpenRouter → Mistral    │
                        │    (privacy gate: P2 never leaves the Mac)            │
                        │ 6. write episode + turn + decisions (after reply)     │
                        └───────────────────────────────────────────────────────┘
                                                          │
 speaker ◄── Kokoro TTS (sentence streaming, fillers) ◄───┘
 night: SLEEP job → facts, directives, lessons, digests, USER.md / LESSONS.md / GRAPH_REPORT.md
```

**No local LLM, no Ollama (D8).** On the Mac: Postgres, embedder, Laya, and later VAD,
Smart Turn, Whisper, emotion2vec+, Kokoro, wake word (≈1.8–3.7 GB est., budget 3 GB).

## 2. Decisions per feature (summary, details in the report)

| Feature | Decision |
|---|---|
| Store | **Postgres 18** + pgvector (halfvec, HNSW) + btree_gist + pg_trgm. Built-in FTS with `simple` config (Hinglish-safe). No AGE, no ChromaDB. |
| Episodic memory | `episodes`: every utterance verbatim, never deleted; privacy P0/P1/P2; origin (owner/agent/untrusted/system); importance, strength. |
| Retrieval | `recall()` SQL: vector top-50 + text top-50 → RRF(k=60) × recency (30-day half-life, 0.5 floor) × importance × strength. No reranker on voice path. |
| Knowledge graph | `entities` + bitemporal `facts` (Graphiti model in plain SQL); Postgres exclusion constraint blocks contradictory "current" facts; recursive CTEs for 1–2 hops. |
| User model | `user_directives`: one imperative rule per row, superseded in place → renders `USER.md`. `SOUL.md` owned by Tejmul. |
| Lessons | ACE-style itemized playbook: ADD/EDIT/MERGE/RETIRE/UP/DOWN per item. Owner corrections active at once; inferred ones need seen ≥2 & conf ≥0.72 (Leon). Hinglish correction lexicon. |
| Consolidation | Nightly "sleep" (03:00 or 30 min idle on AC): embed backlog → digests → extract facts (cloud, P0/P1 only) → resolve entities → bitemporal apply → directives → lessons → decay → precompile briefing → render md + backup. |
| Embeddings | EmbeddingGemma-300M in-process (≈200 MB); `embed_model` column for later swap (Qwen3-Embedding-0.6B if Hinglish recall is weak). |
| Decisions | **Laya** (multilingual checkpoint, INT8 if possible): 13 questions per turn, conservative gates, everything logged to `decisions` for weekly calibration. |
| LLM router | Custom ~150 lines, OpenAI-compatible SDK. **No LiteLLM** (March 2026 PyPI credential-stealer). Quotas/cooldowns in `llm_usage`. Gemini only for P0 (free tier may be human-reviewed). |
| Documents | Route by type: MarkItDown / PyMuPDF4LLM / Docling(pypdfium); structure chunks 300–512 tokens; contextual headers by night cloud job (P0/P1 only). |
| Voice | Pipecat + SmallWebRTC (echo cancellation), Silero VAD + Smart Turn v3.1 + filler-aware fallback, mlx-whisper turbo (A/B vs Hinglish models), Kokoro-82M, duck-then-confirm barge-in, LiveKit WakeWord "Hey Stiti". |
| Emotion | emotion2vec+ base + prosody + text mood + personal baseline → a *hint* with confidence, never a verdict. |
| Todos | Postgres `tasks`, Taskwarrior-style urgency + TMT avoidance risk via Laya; speak top 3. |
| Scheduling | OR-Tools CP-SAT, 1 s interactive limit (benchmarked on this M2: 12 tasks optimal in 10–60 ms). |
| Goals | Lazy 4-phase Socratic Chunker (ADaPT + WOOP); leaves become if-then plans. |
| Habits | Forgiving strength score + fading prompts; **no SM-2/spaced repetition, no streak shaming**. FSRS only for learning items. |
| Psychology | ≤3 items per spoken turn, no guilt words, minimum-viable-day mode, WOOP 5-turn script. |
| Nudges | Nudge Gate: 3–5 unprompted per day, breakpoint timing, bandit learning from accept/dismiss. |
| Alarms | `intents` table + EventKit mirror to Apple Reminders (rings on iPhone/Watch) + in-process spoken alarms + launchd. |
| Connectors | MCP client, top-5 tools per turn (tool-RAG), pin-and-diff servers, risk tiers + spoken/Telegram confirmation. Telegram + ntfy for phone. SearXNG for search. Playwright MCP on demand. |
| App shell | Signed `.app` (menubar, Login Item) so mic permission survives launchd. |

## 3. Budgets

| Thing | Target |
|---|---|
| Speech end → first audio | 0.9–1.6 s on M2 (estimated; measure) |
| Laya pass | < 100 ms |
| recall + facts + lessons | < 100 ms (SQL est. 5–30 ms) |
| Briefing | ≤ 1,500 tokens (Groq free = 8K tokens/min/model) |
| Local RAM, all models | ≤ 3 GB |

## 4. Roadmap

### Phase 1 — **Engine v0 (tonight)** · text-only brain — ✅ built 2026-11-10 (steps 1–8; Laya swapped for exemplar kNN, D10)
Spec: report section "Engine v0 build spec". Done when: after a restart **and** an LLM swap, Stiti remembers last week and lists todos instantly.

| # | Build | Done when |
|---|---|---|
| 1 | Postgres 18 + extensions + 14-table schema | `\dx` shows vector, btree_gist, pg_trgm; two overlapping functional facts are rejected |
| 2 | In-process embedder + REPL that writes episodes | 20 typed memories stored with vectors |
| 3 | `recall()`, `current_facts()`, lesson match | right memory in top 3 for 10 hand-made questions; < 100 ms |
| 4 | Laya + 13-question pass + decision log | accuracy / latency / RAM on 30 real Hinglish sentences recorded |
| 5 | Router (Groq + Cerebras keys) + `llm_usage` | forced 429 fails over with no visible error |
| 6 | Context compiler + chat loop + fast-path todo/alarm | add/list todos and set alarm work with LLM disabled |
| 7 | Lessons capture end-to-end | one correction changes the next reply in the same situation |
| 8 | `stiti sleep --now` (steps 1, 3–6, 9, 10) | facts + USER.md appear from the day's chat; restart + model swap keeps memory |

### Phase 2 — Voice v1 — ✅ v1 built (custom loop, whisper-small, Kokoro, wake phrases); Pipecat/AEC/Smart Turn next
Pipecat pipeline, Whisper A/B on Tejmul's voice, Kokoro + filler bank, barge-in with AEC, latency + RAM measured on M2.
**Wake phrases (Tejmul's spec): "Stiti", "Hey Stiti", "Wake up baby girl"** → always-listening tiny local
wake-word model (LiveKit WakeWord v2 / openWakeWord custom phrases, ~7 MB), chime + start listening,
conversation mode stays awake until ~20 s of silence, "bas"/"so jao"/"go to sleep" sends it back to sleep.
Hotkey as backup trigger.

### Phase 3 — Emotion — ✅ prosody + emotion2vec+ base + text fusion built
emotion2vec+ base, prosody, personal baseline, fusion, mood log; denials stored as labels.

### Phase 4 — Knowledge graph depth + documents — ✅ graph viewer + document ingestion built; eval set pending
Segments/reflections tables, `GRAPH_REPORT.md` + `graph.html` viewer, document ingestion queue, private LongMemEval-style eval set.

### Phase 5 — Life management — ✅ planner, habits, chunker, brief, nudge gate built; EventKit mirror pending
Tasks urgency, CP-SAT planner, Socratic Chunker, habits, WOOP, Nudge Gate, EventKit alarms.

### Phase 6 — Connectors — ✅ EventKit, mail (read), Telegram, tool loop, MCP bus built; SearXNG pending
MCP bus + tool-RAG + pin-and-diff; Google Workspace, Apple EventKit server, filesystem, GitHub (read-only), Telegram, ntfy, SearXNG, Playwright.

### Phase 7 — Always-on app — ✅ menubar Stiti.app at login built; Laya INT8 pending
Signed menubar `.app`, Login Item, wake word, Laya fine-tune on own decision log.

### Status 2026-11-10 (end of build night)
Built and tested without API keys: brain, onboarding, editable mind, backups, voice (wake/stop words, Smart Turn,
AEC, fillers), emotion, proactivity + learned nudge gate, life OS, Mac actions, OCR, learning loops, memory eval,
menubar app, CI. **Not yet verified:** anything that needs a cloud LLM (conversation, tool calling, night
extraction, reflections) and anything that needs Tejmul's real voice (Hinglish STT accuracy, false-wake rate).

## 5. Top risks (full table in the report)
- RAM on a base M2 unmeasured → measure every component on day one.
- Laya zero-shot accuracy (0.36 on its benchmark) and Hinglish handling unknown → 30-sentence pilot, conservative gates, LLM fallback.
- Free-tier limits change; Groq/Cerebras data policies need reading before sending P1 data.
- No local LLM → KG learning pauses offline (episodes still saved; backlog catches up).
- Hinglish STT error is high; "kal"/"parso" ambiguity → always read back absolute alarm dates.
- MCP tool poisoning → pin-and-diff, risk tiers, confirmation for irreversible actions.

## 6. Repo layout

```
Stiti/
├─ CLAUDE.md  docs/  reports/  research_notes/
├─ pyproject.toml            # uv, Python 3.12
├─ db/schema.sql             # Engine v0 schema + recall()/current_facts()
├─ stiti/
│  ├─ config.py  db.py  embed.py  laya_layer.py  router.py
│  ├─ brain/ (recall.py, compiler.py, lessons.py, sleep.py, facts.py)
│  ├─ fastpath/ (todos.py, alarms.py, dates.py)
│  ├─ cli.py                 # chat REPL, `stiti sleep --now`
│  └─ voice/ tools/ ui/      # later phases
└─ tests/
```
Personal data lives in Postgres + `~/.stiti/` (SOUL.md, USER.md, LESSONS.md), never in git.
