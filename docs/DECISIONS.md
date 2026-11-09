# Decisions Log

One entry per decision: what, why, alternatives. Newest at the bottom.

## D1: The brain is a memory engine, not an LLM (2026-11-10)
**What:** Stiti's identity, memory, knowledge graph and lessons live in a local
store (Postgres + markdown). A Context Compiler builds a per-turn briefing; any LLM is a
plug-in that only turns the briefing into words.
**Why:** Tejmul wants Stiti to stay the same no matter which (free) LLM is used, and
fine-tuning is neither free nor portable.
**Alternatives rejected:** fine-tuning, relying on a provider's built-in memory,
an LLM-driven agent framework that owns the state.

## D2: Free-only, multi-provider LLM router (2026-11-10)
**What:** Groq → OpenRouter `:free` → Gemini AI Studio fallback chain (local Ollama removed by D8).
**Why:** Zero budget; each free tier alone is too small (OpenRouter ≈ 50 req/day).

## D3: Python + uv + Pipecat + SQLite (2026-11-10)
**What:** Python 3.12 core, Pipecat for voice, SQLite (FTS5 + sqlite-vec) for memory/graph.
**Why:** Voice/ML ecosystem (Pipecat, FunASR, MLX, Kokoro) is Python-first; SQLite
needs no server and fits 8 GB RAM. Revisit a dedicated graph DB only if SQLite gets slow.

## D4: Design for Apple M2 / 8 GB (2026-11-10)
**What:** ≤ ~3 GB for all local models; no local LLM (see D8).
**Why:** Hardware limit. Running voice stack + LLM locally together would swap and kill latency.

## D5: Laya as Stiti's local decision layer (2026-11-10)
**What:** One Laya call per turn answers all typed decisions (intent, needs_llm,
is_correction, tone, urgency, memory scope, tool category, importance). Low-confidence
answers fall back to the LLM. Decisions + outcomes are logged for calibration.
**Why:** Tejmul wants the brain, not the LLM, to make decisions, and wants many decisions
made at once, fast and free. Laya is local, small (≈0.4–0.9 GB), typed, calibrated, Apache-2.0.
**Trade-off:** Modest zero-shot accuracy → needs confidence gate + calibration on own data.
Fine-tuning Laya (not the LLM) is allowed because it is part of Stiti's brain.
**Alternatives:** hand-written rules only (brittle), LLM function-calling for every decision
(slow, burns free quota, makes the LLM the brain).

## D6: PostgreSQL replaces SQLite (2026-11-10, Tejmul's call)
**What:** One local Postgres (Homebrew) holds episodes, embeddings (`pgvector`),
full-text index, knowledge graph (nodes/edges with valid_from/valid_to), lessons,
todos, decision log. ChromaDB is not used: pgvector covers it in the same DB.
**Why:** Tejmul's choice. Also: real concurrency for voice + background jobs, one store
for vector + text + graph + relational data, mature extensions.
**Cost:** ~100–300 MB RAM for a tuned local server on the 8 GB Mac. D3's SQLite part is superseded.

## D7: Components Tejmul suggested, pending research (2026-11-10)
Being evaluated in the deep research (reports/Stiti personal AI buddy research.md):
- LiteLLM hybrid router (local + Gemini fallback). **Note:** local Qwen-27B won't fit
  8 GB RAM (~16 GB at 4-bit); local side must be ~4B or smaller.
- Google OR-Tools CP-SAT for day scheduling / time-blocking.
- IBM Docling for documents (+ MLX embeddings; vectors go to pgvector, not ChromaDB).
- Socratic Chunker: multi-phase goal breakdown.
- SM-2 spaced repetition for habits (compare with FSRS and habit-formation research).
- Psychology: WOOP, Cognitive Load Theory, Temporal Motivation Theory, anti-guilt design.

## D8: No local LLM, no Ollama (2026-11-10, Tejmul's call)
**What:** Stiti never runs an LLM on the Mac. All LLM calls go to free cloud tiers.
Local models are limited to small ones: VAD, STT, TTS, emotion, embeddings, Laya.
**Why:** Tejmul: running Ollama on the 8 GB Mac overloads it.
**Fallback:** if all cloud providers fail, Stiti still does fast-path actions
(todos, alarms, reminders, memory recall) via Laya + rules, and says deep thinking is unavailable.

## D9: Deep-research outcomes (2026-11-10)
Full reasoning: `reports/Stiti personal AI buddy research.md` (≥10 sources per feature).
- **Engine:** Postgres 18 + pgvector + btree_gist + pg_trgm; built-in FTS (`simple`); no Apache AGE; recursive CTEs.
- **Temporal KG:** Graphiti's bitemporal model re-implemented in SQL (Graphiti has no Postgres backend).
- **Lessons:** ACE itemized deltas + ExpeL votes + Leon promotion gate (seen ≥2, conf ≥0.72).
- **Memory design borrowed from OpenClaw:** provenance tags, nightly-only long-term writes, no-LLM recall lane, standing intents with anti-nag limits.
- **Router:** custom, not LiteLLM (PyPI compromise 2026-03-24). Groq → Cerebras → OpenRouter → Mistral; Gemini P0 only.
- **Privacy tiers:** P0 public, P1 personal (no Gemini), P2 sensitive (never leaves the Mac).
- **Voice:** Whisper family only (SenseVoice/Parakeet don't do Hindi); Kokoro; Smart Turn v3.1; emotion2vec+ base as a hint.
- **Habits:** not SM-2/spaced repetition (wrong model for habits); forgiving strength + fading cues. FSRS only for learning items.
- **Scheduling:** OR-Tools CP-SAT confirmed (benchmarked on this M2).
- **Embeddings:** EmbeddingGemma-300M first.

## D10: Hot-path decisions = exemplar kNN + rules; Laya parked until it fits (2026-11-10)
**What:** Domain/mood decided by nearest-exemplar classification on the already-loaded EmbeddingGemma
(`stiti/intent.py`), plus deterministic floors (privacy regex, Hinglish correction lexicon, time words).
Laya code stays (`stiti/decide.py`), off by default (`STITI_LAYA=off`).
**Why (measured on this M2, docs/research/decision_layer_pilot.md):** Laya zero-shot domain 13–15/30,
200–514 ms, 2.7–2.9 GB RSS. Exemplar kNN: 26/30, 8 ms, ~0 extra RAM. Still "the brain decides, not the LLM".
**Learning:** owner-confirmed examples append to `~/.stiti/exemplars.jsonl` (no training).
**Revisit:** ONNX/INT8 Laya export + calibration on the `decisions` log.
**Also:** embedder is EmbeddingGemma-300M **4-bit ONNX** (onnx-community, ungated): 7 ms/query,
~600 MB RSS, 10/10 recall test. INT8 variant was 81 ms / 1.4 GB.

## D11: Voice and connector build choices (2026-11-10, measured on this M2)
- **Echo cancellation:** WebRTC AEC3 via LiveKit's `AudioProcessingModule` on one 48 kHz duplex stream
  (TTS fed as far-end reference). Mic self-hearing during her speech: 84% → 0% frames. Barge-in on by default.
  Chosen over Pipecat+SmallWebRTC for v1: same AEC family, far fewer moving parts.
- **STT:** whisper-small 4-bit (283 ms) over large-v3-turbo 4-bit (1,064 ms) — ~same Hinglish accuracy on the
  synthetic test; one model, one pass serves wake detection + command (mlx-whisper caches one model).
- **Wake phrases:** ASR keyword spotting with fuzzy match ("Stiti", "Hey Stiti", "Wake up baby girl") — zero training.
- **Voice emotion:** emotion2vec+ base (FunASR) in a background thread, 70–165 ms, ~+800 MB; fused with prosody vs.
  personal baseline and text mood; confidence capped (generic SER ≈41% on natural speech).
- **Documents:** MarkItDown (MIT) instead of PyMuPDF4LLM (AGPL) / Docling (11 s/page); heading-aware chunks in Postgres.
- **EventKit needs an app bundle:** from VS Code/Terminal macOS silently refuses Calendar/Reminders (no usage
  strings → no prompt). `Stiti.app` (ad-hoc signed, usage strings, LaunchAgent → `open -a`) got both granted.
- **Mail:** read-only IMAP with an app password; content tagged untrusted; no send.
- **Tools:** native + MCP behind tool-RAG (top-5), risk tiers, taint, pin-and-diff approval.

## D12: Real RAM budget, measured on the running app (2026-11-10)
`footprint` of the full menubar app was **2,759 MB** — at the 3 GB limit. Per component:
embedder 280 · whisper-small (MLX) 1,215 · Kokoro 172 · VAD + Smart Turn 148 · emotion2vec+ (funasr+torch) 1,553 · AEC 5.
- **MLX cache capped at 64 MB:** whisper 1,213 → 326 MB, STT 283 → ~320 ms. Kept.
- **emotion2vec+ off by default:** prosody-vs-baseline + text mood still run; menubar toggle loads it on demand.
- Target after both: ~1.0–1.2 GB for the whole app.
