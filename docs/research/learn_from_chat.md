# Learning from normal conversation — memory extraction + real-time updates (D38)

**Problem (his real brain, 2026-11-14, 4 days, ~270 episodes):** 12 current facts, all from a day-one resume import.
Two night runs extracted `{}` and `{"added": 1}` (a mishearing). 2 entities, 1 lesson. "Actually, I left MVRX Labs…"
got "Noted. I will mark that down." and nothing was written.

## How others turn chat into long-term memory

| # | System / paper | Mechanism | Strengths | Weaknesses | Fits free + 8 GB M2? |
|---|---|---|---|---|---|
| 1 | **Mem0** (arXiv 2504.19413, mem0ai/mem0) | LLM extracts candidate facts from the last exchange + rolling summary; retrieves similar existing memories; a 2nd LLM call picks ADD / UPDATE / DELETE / NOOP | Dedup + updates by design; small prompts | 2 LLM calls per message; deletes overwrite history | Yes — the "show existing memories, let it decide" idea taken (KNOWN FACTS + `ends`) |
| 2 | **Zep / Graphiti** (arXiv 2501.13956, getzep/graphiti) | Episodes → entity + edge extraction; entity resolution; edges get `valid_at`/`invalid_at`; new edges invalidate contradicting old ones | Bi-temporal, never deletes, graph-native | Several LLM calls per episode; Neo4j | Model already used (our facts table is Graphiti-shaped); invalidation via `ends` |
| 3 | **MemGPT / Letta** (arXiv 2310.08560) | The LLM edits its own core memory with tools during the conversation | Real-time | LLM decides what to store (against rule 1); tool-calling on hot path | No — memory writes stay in code |
| 4 | **A-MEM** (arXiv 2502.12110) | Zettelkasten notes with LLM-written keywords/links; new notes trigger updates of linked old ones | Rich linking | Many LLM calls | Partly — entity mentions as links |
| 5 | **LangMem** (langchain-ai/langmem) | Background "memory manager" extracts / updates profile + semantic memories after a conversation; hot-path tools optional | Clear split hot path vs background | LangChain stack | Yes — the split (deterministic in-turn, LLM after/at night) |
| 6 | **Generative Agents** (arXiv 2304.03442) | Memory stream + importance scoring + periodic reflection | Reflection = higher-level facts | Costly; reflections can drift | Already have `reflect()`; importance used to skip commands |
| 7 | **MemoryBank** (arXiv 2305.10250) | Ebbinghaus strength decay + per-day summaries + user portrait | Cheap portrait | Portrait from summaries loses detail | `standing_profile` = portrait, now newest-first |
| 8 | **ChatGPT memory** (OpenAI, 2024–25) | Explicit "remember X" saved at once + "Memory updated" receipt; implicit memories later | Honest receipt only when saved | Proprietary | Yes — the honesty rule ("noted" only if saved) |
| 9 | **LongMemEval** (arXiv 2410.10813) | Benchmark: knowledge updates + temporal reasoning are where assistants fail most | Shows updates must supersede | Benchmark only | Our eval covers "knowledge update" |
| 10 | **HippoRAG** (arXiv 2405.14831) | OpenIE triples → KG + personalised PageRank for recall | Good multi-hop recall | Triples are noisy without validation | Validation layer (evidence/grounding) is the lesson |
| 11 | **Cognee** (topoteretes/cognee) | Pipeline: chunk → LLM graph extraction with a fixed ontology → dedup | Ontology keeps predicates sane | Heavy | Predicate synonym map + functional list |
| 12 | **SeCom / segment-level memory** (arXiv 2502.05589) | Memory units = topic segments, denoised before storage | Context for each line | Extra compression model | We send her preceding reply as context for each of his lines |
| 13 | **Structured outputs** (Groq / Cerebras json_schema strict) | Constrained decoding to a JSON Schema | No malformed JSON | Only some models | `router.complete(schema=…)` → strict on gpt-oss/qwen |

## What we took (smallest version that fits free / local / fast)
- **Night/nap extraction (Mem0 + Graphiti):** his lines + Stiti's previous reply as context; KNOWN FACTS (current, P≤1)
  given with ids so the model can return `ends` (no longer true) / `wrong` (never true). Strict JSON schema.
  Validation in code (evidence ids must be his lines, confidence ≥ 0.6, grounding words, contradiction check, nothing
  "about Stiti"). Merge: same (subj, pred, obj) or ≥ 0.92 embedding similarity → confirm instead of insert.
- **Real time (ChatGPT/LangMem split):** deterministic patterns in the turn (≈1 ms + one embedding per fact) for the
  clear cases; anything else that smells like an update goes to the same extractor in a background thread after the
  reply. Never an LLM on the hot path.
- **Honesty:** "noted / I'll remember / updated" only when something was written this turn (code-enforced filter).
