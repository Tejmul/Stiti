# Agent Long-Term Memory Architectures & Temporal Knowledge Graphs — implemented in PostgreSQL (for Stiti, 8 GB M2, local-first, zero-cost)

> Research date: 2026-11-10. Researcher notes for the report writer.
> **Sourcing convention.** Every claim carries a link. Claims marked **†** come from the linked primary source (arXiv paper / official repo / official docs) **as I know it from prior reading. I did not re-fetch it this session**, so the writer should spot-check exact numbers. Claims marked **[vendor]** come from the vendor's own blog or docs and are self-reported. Unmarked claims were checked against search or fetch results this session.
> **Structure.** Per the coordinator's new requirement, each of the 7 features gets ≥10 papers/architectures, a comparison table, then a recommendation (under "Inferences"). Two more sections cover benchmarks and how the main OSS memory systems are built.

---

## Feature 1 — Episodic memory store & retrieval

### Takeaway
Every serious system keeps an **append-only, timestamped log of raw episodes** (Generative Agents' "memory stream", MemGPT's "recall storage", Zep's "episode subgraph", LongMemEval's "session/round" values). The variety lies in how they score retrieval: recency × importance × relevance (Generative Agents), decay/strength (MemoryBank), extracted facts as keys (LongMemEval, Mem0), or links between notes (A-MEM). For Stiti: store every turn verbatim in Postgres, never delete, and index it three ways (vector, BM25/FTS, time). Retrieve with a Generative-Agents-style composite score that LongMemEval-style fact-augmented keys and time-aware query expansion feed into.

### Comparison table
| # | Name | Link | Year | Core mechanism | Strengths | Weaknesses | Fits Postgres + 8 GB M2 / free? |
|---|---|---|---|---|---|---|---|
| 1 | Generative Agents (memory stream) | [arXiv 2304.03442](https://arxiv.org/abs/2304.03442) | 2023 | NL observations with timestamps. Retrieval score = recency + importance + relevance (each min-max normalized, α=1). Recency decays exponentially (0.995/game-hour since last access). An LLM rates importance 1–10. † | Simple, interpretable, and maps directly onto SQL columns | Calls the LLM for every importance rating. No entity structure. | Yes. Columns + an ORDER BY expression. Free. |
| 2 | MemGPT | [arXiv 2310.08560](https://arxiv.org/abs/2310.08560) | 2023 | OS-style virtual context. Main context (system prompt, working context, FIFO queue) vs external recall storage (all messages) and archival storage (vector DB). The LLM pages data in and out with function calls; a memory-pressure warning triggers flushes. † | Unbounded history and self-editing memory | Needs a strong tool-calling LLM to manage memory (conflicts with "LLM is a plug") | The storage pattern fits Postgres. The agentic control loop does not suit a small local LLM. |
| 3 | MemoryBank / SiliconFriend | [arXiv 2305.10250](https://arxiv.org/abs/2305.10250) | 2023 (AAAI'24) | Stores memories plus daily event summaries plus a global user portrait. Forgetting follows the Ebbinghaus curve R = e^(−t/S): each recall raises strength S and resets t. † | Human-like forgetting/reinforcement. Built for a companion use case. | Few rigorous evaluations. Forgetting can drop facts that matter. | Yes. `strength`, `last_recalled_at` columns. |
| 4 | LongMemEval (proposed design) | [arXiv 2410.10813](https://arxiv.org/abs/2410.10813) | 2024 (ICLR'25) | Frames memory as indexing → retrieval → reading. Recommends **session decomposition into rounds**, **fact-augmented key expansion** (index each value under extracted facts too), and **time-aware query expansion** (filter by an inferred time range). † | Evidence-backed design choices for chat-assistant memory | Benchmark paper, not a full system | Yes. Maps directly onto SQL. |
| 5 | Mem0 | [arXiv 2504.19413](https://arxiv.org/abs/2504.19413) | 2025 | Extraction phase: an LLM pulls salient facts from the new message pair plus a rolling summary. Update phase: compare with top-s similar memories, then ADD / UPDATE / DELETE / NOOP. † | Compact, low-token memory. pgvector is a supported store. | Lossy: raw episodes aren't the retrieval unit. Needs an LLM call per turn. | Yes (pgvector backend). Free OSS. |
| 6 | A-MEM | [arXiv 2502.12110](https://arxiv.org/abs/2502.12110) | 2025 (NeurIPS'25) | Zettelkasten notes (content, keywords, tags, context description, embedding). An LLM links each new note to its k nearest notes and "evolves" older notes' attributes. † | Self-organizing and associative | Many LLM calls per write. Evolution can drift. | Yes (notes + links tables). Write cost is high on a local LLM. |
| 7 | Zep episode subgraph | [arXiv 2501.13956](https://arxiv.org/abs/2501.13956) | 2025 | Raw episodes (messages/text/JSON) are non-lossy nodes linked to the semantic entities and facts extracted from them. † | Provenance from fact to episode | Graph DB required in the reference impl (Neo4j etc.) | The pattern ports to Postgres (`episode_mentions` join table). |
| 8 | SeCom | [arXiv 2502.05589](https://arxiv.org/abs/2502.05589) | 2025 (ICLR'25) | Segments conversations into topical segments (neither per turn nor per session) as the memory unit, plus compression-based denoising of retrieved text. † | Better granularity than turn or session | Needs a segmentation model | Yes |
| 9 | Nemori | [arXiv 2508.03341](https://arxiv.org/abs/2508.03341) | 2025 | Event-segmentation-inspired episodic memory: boundary detection turns dialogue into "episodes", plus a predict-calibrate loop for semantic memory. † | Human-cognition-aligned chunking | Research code | Yes |
| 10 | MemoriesDB | [arXiv 2511.06179](https://arxiv.org/pdf/2511.06179) | 2025 | A "temporal-semantic-relational" database for agent memory that models experience as a graph of temporal-semantic surfaces (found in search, abstract only) | Explicitly targets a time + vector + relation DB, like Stiti's | Not deeply evaluated here | Conceptually Postgres-friendly (gap: implementation details) |
| 11 | MemoryOS (BAI) | [arXiv 2506.06326](https://arxiv.org/html/2506.06326v1) | 2025 | OS-like short-, mid- and long-term tiers. Pages move tiers by "heat" (visit count, recency). Includes a persona module. † | Explicit tiering and a user persona | Heuristic thresholds | Yes |
| 12 | MemMachine | [arXiv 2604.04853](https://arxiv.org/html/2604.04853v1) | 2026 | "Ground-truth-preserving" memory for personalized agents: keeps raw episodes as the truth, with derived memories on top (from title/abstract) | Matches the never-lose-raw principle | Not evaluated here | Yes |

### Cited Findings
- Generative Agents retrieve by a weighted sum of recency, importance and relevance. Importance is LLM-rated 1–10; recency is exponential decay (factor 0.995). † — [Park et al. 2023](https://arxiv.org/abs/2304.03442)
- MemGPT splits memory into in-context (core) and out-of-context recall/archival storage, managed by LLM function calls. † — [Packer et al. 2023](https://arxiv.org/abs/2310.08560)
- MemoryBank applies the Ebbinghaus forgetting curve: memories decay over time and are reinforced when recalled. † — [Zhong et al. 2023](https://arxiv.org/abs/2305.10250)
- LongMemEval's unified framework (indexing/retrieval/reading) recommends round-level decomposition, fact-augmented key expansion and time-aware query expansion. These improve recall and QA. † — [Wu et al. 2024](https://arxiv.org/abs/2410.10813)
- Mem0's two-phase extract→update pipeline uses ADD/UPDATE/DELETE/NOOP operations chosen by an LLM tool call. † — [Chhikara et al. 2025](https://arxiv.org/abs/2504.19413)
- A-MEM builds interlinked Zettelkasten-style notes and evolves existing notes when new ones arrive. † — [Xu et al. 2025](https://arxiv.org/abs/2502.12110)
- MemoriesDB proposes a temporal-semantic-relational DB for long-term agent memory. — [arXiv 2511.06179](https://arxiv.org/pdf/2511.06179)
- MemMachine is a "ground-truth-preserving memory system for personalized AI agents". — [arXiv 2604.04853](https://arxiv.org/html/2604.04853v1)

### Inferences
**Recommendation for Stiti (episodic):**
1. **`episodes` table = immutable ground truth** (Zep/MemMachine principle). One row per user or assistant utterance (round-level, per LongMemEval), with `occurred_at`, `ingested_at`, `session_id`, `speaker`, `text`, `embedding halfvec(N)`, `tsv tsvector` (or a pg_textsearch BM25 index), `importance smallint`, `valence/arousal` (feelings), `access_count`, `last_accessed_at`, `strength real`.
2. **Segment rows** (SeCom/Nemori) are a second retrieval unit. A nightly job groups rounds into topical segments with a summary and embedding. Episode-level search answers detail questions; segment-level search answers "what happened that week".
3. **Fact-augmented keys** (LongMemEval): extracted facts and entities point back to episodes, so a query matching a fact retrieves its source episode.
4. **Retrieval score** = RRF(vector, BM25) fused with Generative-Agents-style recency (exponential decay on `last_accessed_at`) and importance, plus a MemoryBank strength bump on access. Run all of it as SQL.
5. **Never hard-delete.** "Forgetting" means rows drop in rank, not out of storage. Disk is cheap: about 180k turns over 10 years (50/day) × 768-dim halfvec ≈ 0.3 GB of vectors (back-of-envelope).
6. Avoid MemGPT's LLM-driven paging. Stiti's own engine, not the LLM, should decide what enters the briefing (this matches the "LLM is a plug" requirement).

### Gaps
- No independent head-to-head of retrieval units (turn vs segment vs session) on Stiti-like voice data. The LongMemEval paper's own ablations are the best evidence (†, numbers not re-fetched).
- MemoriesDB and MemMachine were seen only as abstract/listing; implementation details unverified.

---

## Feature 2 — Temporal knowledge graph (people, projects, events, feelings)

### Takeaway
**Zep/Graphiti's bitemporal edge model** is the reference design: facts are edges with `valid_at/invalid_at` (world time) and `created_at/expired_at` (system time). Contradictions *invalidate* old edges instead of deleting them. Graphiti has **no Postgres driver** (Neo4j, FalkorDB, Kuzu, Neptune only), so Stiti must re-implement the model in Postgres. PostgreSQL 18's `WITHOUT OVERLAPS` / `PERIOD` temporal constraints, or `tstzrange` + GiST exclusion constraints, make this natural.

### Comparison table
| # | Name | Link | Year | Core mechanism | Strengths | Weaknesses | Fits Postgres + 8 GB M2 / free? |
|---|---|---|---|---|---|---|---|
| 1 | Zep / Graphiti | [arXiv 2501.13956](https://arxiv.org/abs/2501.13956), [repo](https://github.com/getzep/graphiti) | 2025 | Three tiers: episode subgraph → semantic entity subgraph → community subgraph. **Bitemporal** edges (t_valid/t_invalid + t'_created/t'_expired). LLM entity resolution, edge dedup and contradiction-driven invalidation. † | Best-documented temporal KG for agents. Incremental (no batch recompute). | Many LLM calls per episode. No Postgres backend. | Model: yes. Library: needs Neo4j/FalkorDB/Kuzu (Neo4j JVM is heavy on 8 GB). Apache-2.0. |
| 2 | Mem0g (graph variant) | [arXiv 2504.19413](https://arxiv.org/abs/2504.19413), [docs](https://docs.mem0.ai/open-source/features/graph-memory) | 2025 | Entity extractor → relation generator → conflict detector. Obsolete relations are **marked invalid** rather than deleted. † | Simple triples, temporal reasoning gains in the paper | OSS graph backends are Neo4j/Memgraph/Neptune/Kuzu. Apache AGE appeared only in older versions. | Partially. pgvector for vectors, but no Postgres graph store in current OSS docs. |
| 3 | HippoRAG | [arXiv 2405.14831](https://arxiv.org/abs/2405.14831) | 2024 (NeurIPS) | OpenIE triples → schemaless KG plus synonymy edges. Query entities seed **Personalized PageRank** (hippocampal-indexing analogy). † | Single-step multi-hop. Reported 10–30× cheaper and 6–13× faster than iterative retrieval (IRCoT). † | No time model | PPR runs in SQL (iterative) or in Python over a small subgraph. Free. |
| 4 | HippoRAG 2 | [arXiv 2502.14802](https://arxiv.org/abs/2502.14802) | 2025 (ICML) | Adds passage nodes, dense+sparse seed fusion, query-to-triple matching and an LLM "recognition memory" filter. Framed as non-parametric continual learning. | Avg F1 59.8 vs NV-Embed-v2 57.0 and HippoRAG 53.1 (secondary summary) | LLM triple filter has a ~7% miss rate (secondary summary) | Same as above |
| 5 | Microsoft GraphRAG | [arXiv 2404.16130](https://arxiv.org/abs/2404.16130), [repo](https://github.com/microsoft/graphrag) | 2024 | LLM entity/relation extraction → Leiden communities → hierarchical community summaries. Global (map-reduce over summaries) vs local search. † | Strong "sensemaking" / global questions | Expensive batch indexing. Weak incremental updates. No time model. | Storage is files/parquet. Indexing a life log with a local LLM would be slow. |
| 6 | LightRAG | [arXiv 2410.05779](https://arxiv.org/abs/2410.05779), [repo](https://github.com/HKUDS/LightRAG) | 2024 | Graph-indexed RAG with dual-level (low-level entity / high-level theme) retrieval and incremental graph updates. Has PostgreSQL storage backends (KV, pgvector, and graph via Apache AGE). † | Incremental, cheaper than GraphRAG, Postgres option exists | Not time-aware. Document-RAG oriented. | Yes (PG + pgvector + AGE). MIT. |
| 7 | nano-graphrag | [repo](https://github.com/gusye1234/nano-graphrag) | 2024 | ~1.1k-line re-implementation of GraphRAG with pluggable storage (networkx/Neo4j, nano-vectordb etc.). † | Readable reference | Same limits as GraphRAG | Easy to port, but no PG backend out of the box |
| 8 | Cognee | [graph-on-postgres](https://www.cognee.ai/graph-on-postgres), [repo](https://github.com/topoteretes/cognee) | 2024–26 | ECL ("extract-cognify-load") pipelines build a KG plus embeddings. **Cognee 1.0 (June 2026) can run graph, vectors, sessions and metadata in one Postgres.** [vendor] | One-DB Postgres story. Claims ~10% faster search than graph+vector split. [vendor] | Schema/traversal method not disclosed in the post | Yes (pgvector). OSS (Apache-2.0 †). |
| 9 | graphify | [betterstack guide](https://betterstack.com/community/guides/ai/ai-development/graphify-codebase/), [emelia guide](https://emelia.io/hub/knowledge-graph-graphify-guide) | 2025–26 | Folder → KG (code via AST, docs/PDF/images/audio via LLM) → `graph.json`, `graph.html`, **`GRAPH_REPORT.md`** (god nodes, surprising connections, suggested questions, node/edge/community counts) | The "compiled report the LLM reads first" pattern Stiti wants | Report is a navigation aid. A critical review found `query`/`explain` gave a confidently wrong answer. | File-based (NetworkX †), not Postgres. MIT. |
| 10 | nxlabscc/agent-memory | [repo](https://github.com/nxlabscc/agent-memory) | 2026 | Postgres+pgvector. Facts as **edges with two time axes** (learned vs true). Nothing deleted; intervals close. Episodes keep pointer+hash provenance. MinHash/Jaccard entity resolution. LLM judges contradictions but code decides which interval closes. RRF hybrid recall + MMR. | Almost exactly Stiti's target design, all in Postgres | 0 stars, 1 commit, v0.1.0: a reference only | Yes. Apache-2.0. TypeScript/Bun. |
| 11 | Basic Memory | [aimemory comparison](https://aimemory.pro/blog/mcp-memory-server-comparison), [repo](https://github.com/basicmachines-co/basic-memory) | 2025 | Markdown files as the source of truth (entities, observations, `[[relations]]`), indexed into a local DB and served over MCP | Human-readable, editable, git-able | No temporal validity model. AGPL-3.0. | DB index is SQLite † (Postgres support unverified). Free (AGPL). |
| 12 | Temporal-KG literature (TKG embeddings, e.g., TTransE / RE-NET) | — | 2018–21 | Learned embeddings over (s,p,o,t) quads for link prediction | Theory for temporal reasoning | Needs training. Overkill for one user. | Not recommended (gap: not researched in depth) |

### Cited Findings
- Graphiti drivers: NEO4J, FALKORDB, KUZU, NEPTUNE, behind a `GraphDriver` ABC. Only Neo4j has full transactions; the others execute immediately. No Postgres driver found. — [Graphiti driver docs (Mintlify mirror)](https://www.mintlify.com/getzep/graphiti/api/drivers/overview); [graph drivers guide](https://mintlify.com/getzep/graphiti/guides/graph-drivers)
- Zep's paper reports DMR 94.8% vs MemGPT 93.4%, and LongMemEval accuracy gains up to 18.5% with ~90% lower response latency vs full-context baselines. † [vendor-authored paper] — [Rasmussen et al. 2025](https://arxiv.org/abs/2501.13956)
- Mem0 OSS graph stores: Neo4j, Memgraph, Neptune, Kuzu (Kuzu embedded, file path or in-memory). Platform docs say earlier versions supported external graph DBs including **Apache AGE**, now replaced by built-in graph memory on the hosted platform. One commentary says graph was removed from the v3 OSS rewrite (conflicting). — [Mem0 OSS graph docs](https://docs.mem0.ai/open-source/features/graph-memory); [Mem0 platform graph docs](https://docs.mem0.ai/platform/features/graph-memory); [codepointer commentary](https://codepointer.substack.com/p/agent-memory-systems-and-knowledge)
- Third-party `mem0-dbay` package implements a pgvector-based graph store plugin for Mem0 (MIT, not official). — [PyPI mem0-dbay](https://pypi.org/project/mem0-dbay/0.1.0/)
- HippoRAG 2: avg F1 59.8 vs NV-Embed-v2 57.0 vs HippoRAG 53.1. Indexing tokens about 9M vs 115M (for comparison system) on MuSiQue. Secondary summaries disagree on exact MuSiQue F1. — [emergentmind HippoRAG 2](https://www.emergentmind.com/topics/hipporag-2)
- Cognee 1.0 puts graph, embeddings (pgvector), sessions and metadata in one Postgres. "About 10% faster" than the split setup on an internal War-and-Peace CI baseline. Post dated 2026-06-26, updated 2026-09-03. [vendor] — [Cognee: Just Postgres](https://www.cognee.ai/graph-on-postgres)
- graphify outputs `graphify-out/` with `graph.html`, `graph.json`, and `GRAPH_REPORT.md` (god nodes, surprising connections, suggested questions). The recommended workflow is: read the report first, then `graphify query` for a subgraph. — [Better Stack guide](https://betterstack.com/community/guides/ai/ai-development/graphify-codebase/); [emelia guide](https://emelia.io/hub/knowledge-graph-graphify-guide); critical review: [Praveen Vijayan](https://praveenvijayan.substack.com/p/your-knowledge-graph-is-making-your)
- nxlabscc/agent-memory design: two time axes, interval-closing instead of deletes, episode provenance via pointer+hash, MinHash entity resolution, RRF + MMR recall. Apache-2.0, 1 commit, v0.1.0. — [GitHub](https://github.com/nxlabscc/agent-memory)
- PostgreSQL 18 adds `WITHOUT OVERLAPS` on PRIMARY KEY/UNIQUE (last column must be a range type) and `PERIOD` on FOREIGN KEY (checks range containment). Needs `btree_gist`; backed by GiST indexes. — [Neon PG18 temporal constraints](https://neon.com/postgresql/postgresql-18/temporal-constraints); [Better Stack](https://betterstack.com/community/guides/databases/postgres-temporal-constraints/); [depesz](https://www.depesz.com/?p=4270); [Aiven](https://aiven.io/blog/exploring-how-postgresql-18-conquered-time-with-temporal-constraints)

### Inferences
**Recommendation for Stiti (temporal KG): re-implement Graphiti's bitemporal model natively in Postgres 18 tables. Do not adopt Graphiti itself.**
- Reasons: Graphiti has no PG driver, and Neo4j's JVM is a bad neighbour on 8 GB. Every component (entity resolution, edge invalidation, hybrid search, BFS) is expressible in SQL. nxlabscc/agent-memory and Cognee 1.0 show it's viable.
- Proposed core tables (sketch):
  - `entities(id, kind ENUM('person','project','place','org','event','feeling','topic','thing'), name, aliases text[], summary text, embedding halfvec, created_at, merged_into)`
  - `facts(id, subj_id, predicate text, obj_id NULL, obj_literal text NULL, fact_text text, embedding halfvec, valid tstzrange, recorded tstzrange DEFAULT tstzrange(now(), NULL), confidence real, source_episode_ids bigint[], invalidated_by bigint)`. "Valid" is world time; "recorded" is system/transaction time, giving bitemporality as in Zep.
  - For **functional predicates** (e.g., `lives_in`, `works_at`, `relationship_status`) add a uniqueness rule `UNIQUE (subj_id, predicate, valid WITHOUT OVERLAPS)` (PG18) or `EXCLUDE USING gist (subj_id WITH =, predicate WITH =, valid WITH &&)` filtered to current-recorded rows. Postgres then *enforces* that two contradictory facts can't both be valid at once. Use non-functional predicates (`knows`, `feels_about`) without the constraint.
  - `episode_mentions(episode_id, entity_id)` gives Zep-style provenance and enables the "episode-mentions" reranker.
  - `communities(id, level, summary, embedding)` + `community_members`. Clustering runs in a nightly job (Leiden/Louvain in Python via `igraph`/`networkx` over an exported edge list), as in GraphRAG/Zep.
- **Contradiction handling (Graphiti/Mem0g/nxlabscc pattern):** the LLM (or a small NLI model) only *flags* a conflict. Deterministic code then closes `valid` (`upper = new_fact.valid_from`) and sets `invalidated_by`. Never delete.
- **Feelings** belong in the graph as first-class nodes or edge properties with time (`user —feels{valence:-0.6}→ project_X, valid [2026-10-01, …)`), so the briefing can say "user was stressed about X last week; this is improving."
- **graphify lesson:** produce a compiled `BRIEFING.md`-style report (top "god nodes" = most central people/projects, recent changes, open loops, active lessons). Don't expose raw graph queries to the LLM.

### Gaps
- Exact Graphiti prompts/latency with small local LLMs: not researched. A local 3–8B model extracting entities/relations may be unreliable. Needs testing.
- Whether Kuzu is still maintained: I recall the KuzuDB repo was archived in late 2025, but did not verify this session. Relevant only if a Graphiti fallback were considered.
- Cognee's actual Postgres graph schema/traversal (recursive CTE vs adjacency tables) is not disclosed in the blog. See docs.cognee.ai.
- PG18 does not (to my knowledge, unverified) include `UPDATE … FOR PORTION OF`. Interval splitting must be done by hand in app code or triggers.

---

## Feature 3 — Memory consolidation / reflection ("sleep")

### Takeaway
Consolidation runs **offline, between conversations**: summarize episodes into higher-level reflections/insights (Generative Agents), recursive summaries (RAPTOR, GraphRAG communities), tier migration (MemoryOS), forgetting/strengthening (MemoryBank), and "sleep-time compute" that pre-computes useful context (Letta). For Stiti this is a nightly/idle job pipeline (pg_cron or an app-side scheduler + LISTEN/NOTIFY) that writes `reflections`, `segment summaries`, `profile` updates and the precompiled briefing cache.

### Comparison table
| # | Name | Link | Year | Core mechanism | Strengths | Weaknesses | Fits PG + 8 GB / free? |
|---|---|---|---|---|---|---|---|
| 1 | Generative Agents reflection | [arXiv 2304.03442](https://arxiv.org/abs/2304.03442) | 2023 | When summed importance of recent memories exceeds a threshold (150 †), ask the LLM for salient questions, retrieve, and write higher-level "reflections" (with evidence pointers) back into the stream. Reflections form trees. † | Proven, simple | LLM-heavy | Yes |
| 2 | Sleep-time compute (Letta) | [arXiv 2504.13171](https://arxiv.org/abs/2504.13171), [Letta blog](https://letta.com/blog/sleep-time-compute) | 2025 | A second "sleep-time agent" reorganizes the primary agent's memory blocks during idle time. The primary agent reads the result without waiting. Shipped in Letta 0.7.0. | Moves latency off the hot path, ideal for voice | Gains depend on query predictability. Reported ~5× less test-time compute / 2.5× lower cost per query (secondary, unverified). | Yes. Idle-time jobs suit an always-on Mac. |
| 3 | MemoryBank | [arXiv 2305.10250](https://arxiv.org/abs/2305.10250) | 2023 | Daily summaries → global summary → user portrait, plus Ebbinghaus decay † | Companion-oriented | Weak evaluation | Yes |
| 4 | RAPTOR | [arXiv 2401.18059](https://arxiv.org/abs/2401.18059) | 2024 (ICLR) | Recursively cluster chunks (GMM over embeddings) and summarize into a tree. Retrieve across levels. † | Multi-granularity recall | Batch rebuilds | Yes (tree in a table) |
| 5 | GraphRAG communities | [arXiv 2404.16130](https://arxiv.org/abs/2404.16130) | 2024 | Leiden hierarchy plus community summaries † | Global "what's my life about" answers | Expensive | Nightly job only |
| 6 | MemoryOS | [arXiv 2506.06326](https://arxiv.org/html/2506.06326v1) | 2025 | Short → mid → long-term promotion by heat. Persona updated from long-term. † | Clear lifecycle | Heuristics | Yes |
| 7 | LightMem | [arXiv 2510.18866](https://arxiv.org/abs/2510.18866) | 2025 | Atkinson-Shiffrin-inspired sensory pre-compression → topic-aware short-term → **offline "sleep-time" long-term update**, cutting online tokens/calls † | Efficiency focus | Research code | Yes |
| 8 | MemOS (MemCube, MemScheduler) | [arXiv 2507.03724](https://arxiv.org/pdf/2507.03724v4), [docs](https://memos-docs.openmem.net/overview/algorithm) | 2025 | Memory as an OS resource. MemCube wraps content plus provenance/versioning across plaintext, activation (KV-cache) and parametric memory. A scheduler moves memories between types. | Lifecycle/versioning concepts | Heavy system. Activation/parametric memory needs model access. | Concepts only. LoCoMo LLM-judge 75.80 vs Mem0 59.22 (paper's own run). |
| 9 | Reflective Memory Management (RMM) | [arXiv 2503.08026](https://arxiv.org/abs/2503.08026) | 2025 (ACL) | Prospective reflection (summarize by topic at session end) + retrospective reflection (learn retrieval from LLM citation feedback, RL-tuned reranker) † | Retrieval improves with use | RL reranker training | Prospective part: yes. Retrospective: optional. |
| 10 | Towards Autonomous Memory Agents | [arXiv 2602.22406](https://arxiv.org/abs/2602.22406) | 2026 | Online consolidation that audits new memories against retrieved context, plus downstream feedback to improve retrieval | Self-auditing writes | New, unreplicated | Yes |
| 11 | Memobase "Dream Phase" | [aimemory comparison](https://aimemory.pro/blog/mcp-memory-server-comparison) | 2025–26 | Offline distillation of conversation logs into profiles [3rd-party description] | Profile-focused | Little documentation found | Self-hostable |
| 12 | "Language Models Need Sleep" | [arXiv 2605.26099](https://www.alphaxiv.org/abs/2605.26099v1) | 2026 | Converts recent context into **fast weights** offline | Parametric consolidation | Needs weight updates. Violates "swappable LLM plug". | **No** (noted for completeness) |

### Cited Findings
- Letta's sleep-time compute paper (arXiv 2504.13171, Apr 2025) runs a background agent that reorganizes memory during idle time. Sleep-time agents shipped in Letta 0.7.0. — [Letta blog](https://letta.com/blog/sleep-time-compute)
- Secondary summaries report ~5× less test-time compute at equal accuracy and 2.5× lower cost per query when context is shared. Not verified against the paper. Gains are largest when future queries are predictable from context. — [Letta blog](https://letta.com/blog/sleep-time-compute); [Ken Huang substack](https://kenhuangus.substack.com/p/why-ai-agents-are-starting-to-dream)
- MemOS: MemCube wraps memory plus metadata (provenance, versioning). Three memory types (plaintext, activation, parametric). LoCoMo LLM-judge 75.80 vs MIRIX 64.33 vs Mem0 59.22 (MemOS authors' runs). — [arXiv 2507.03724v4](https://arxiv.org/pdf/2507.03724v4); [emergentmind](https://www.emergentmind.com/articles/2507.03724)
- "Towards Autonomous Memory Agents" describes online consolidation that audits new memories against retrieved context. — [arXiv 2602.22406](https://arxiv.org/abs/2602.22406)
- "Language Models Need Sleep" (Lee, McLeish, Goldstein, Fanti) consolidates context into fast weights. It is unrelated to Letta. — [alphaXiv 2605.26099](https://www.alphaxiv.org/abs/2605.26099v1)
- Memobase described as having a "Dream Phase" for memory distillation [third-party]. — [aimemory.pro](https://aimemory.pro/blog/mcp-memory-server-comparison)

### Inferences
**Recommendation for Stiti (consolidation): a deterministic "sleep" pipeline of SQL + small-LLM jobs, run when the user is idle (e.g., 03:00 or after 30 min of silence).**
Jobs, in order, each idempotent and recorded in a `consolidation_runs` table:
1. **Segment** the day's rounds into topical segments (SeCom/Nemori). Summarize and embed each segment.
2. **Extract/refresh entities and facts** (Graphiti/Mem0g). Close contradicted intervals.
3. **Reflect** (Generative Agents): if Σimportance since the last reflection exceeds a threshold, generate 3–5 insights with `evidence_episode_ids`, stored as `reflections(level, text, embedding, evidence[])`.
4. **Profile update** (MemoryBank portrait / Memobase): update `user_profile` slots with confidence and validity intervals.
5. **Decay/strength** (MemoryBank): recompute `strength` and a recency score. Do not delete.
6. **Community/"god node" recompute** weekly (GraphRAG/graphify).
7. **Pre-compile briefing fragments** (sleep-time compute): "standing context" (who the user is, active projects, open loops, today's calendar-like items, active lessons). Store in `briefing_cache` so a per-turn briefing only appends query-specific retrieval. This is the biggest latency win for voice.
- Scheduling: `pg_cron` works but requires `shared_preload_libraries` and an extension build on macOS. A Python/Swift scheduler in the Stiti daemon is simpler. Use `LISTEN/NOTIFY` (`NOTIFY memory_events, '<episode_id>'` from an insert trigger) to wake workers immediately after a turn for cheap incremental work.
- Reject parametric/fast-weight consolidation: it couples memory to one model and breaks the swappable-LLM principle.

### Gaps
- No found benchmark that isolates *consolidation* benefit on a single-user, multi-year companion dataset.
- LightMem/RMM numbers marked † were not re-fetched.

---

## Feature 4 — Lessons / procedural memory from user feedback (no fine-tuning)

### Takeaway
The 2023–2026 literature converges on **"learning in context, not in weights"**: distill natural-language rules/insights from successes, failures and corrections (Reflexion, ExpeL, ReasoningBank, ACE, Dynamic Cheatsheet, AWM, Mem^p, PAHF, AdaMem). Store them as structured items, retrieve them by **situation similarity**, and inject them into the prompt. ACE's key finding is that such playbooks must be updated with **incremental, itemized deltas** rather than full rewrites, to avoid "context collapse" and "brevity bias". This maps directly onto Stiti's `lessons` table.

### Comparison table
| # | Name | Link | Year | Core mechanism | Strengths | Weaknesses | Fits PG + 8 GB / free? |
|---|---|---|---|---|---|---|---|
| 1 | Reflexion | [arXiv 2303.11366](https://arxiv.org/abs/2303.11366) | 2023 (NeurIPS) | Verbal self-reflection after failure, stored in an episodic buffer and prepended next attempt. 91% pass@1 HumanEval vs GPT-4 80%. † | Simple, no weights | Per-task, short-lived memory | Yes |
| 2 | ExpeL | [arXiv 2308.10144](https://arxiv.org/abs/2308.10144) | 2023 (AAAI'24) | Gathers trajectories, extracts **insights** via ADD/EDIT/UPVOTE/DOWNVOTE operations, and recalls similar successful examples † | Vote-weighted rule list, a good pattern for lessons | Task-agent setting | Yes (`votes` column) |
| 3 | Voyager skill library | [arXiv 2305.16291](https://arxiv.org/abs/2305.16291) | 2023 | Stores verified code skills indexed by description embedding † | Procedural reuse | Code-skill specific | Pattern only |
| 4 | Agent Workflow Memory (AWM) | [arXiv 2409.07429](https://arxiv.org/abs/2409.07429) | 2024 | Induces reusable workflows from experiences, online or offline † | Procedure abstraction | Web-agent focus | Pattern only |
| 5 | Dynamic Cheatsheet | [arXiv 2504.07952](https://arxiv.org/abs/2504.07952) | 2025 | Persistent, evolving test-time memory of strategies/snippets † | Test-time learning | Rewrite drift | Yes |
| 6 | ReasoningBank | [arXiv 2509.25140](https://arxiv.org/abs/2509.25140) | 2025 | Distills generalizable strategies from self-judged successes **and failures**. Retrieve → act → write back. | Learns from failures | Self-judgment can be wrong | Yes |
| 7 | ACE (Agentic Context Engineering) | [arXiv 2510.04618](https://arxiv.org/abs/2510.04618), [ICLR 2026](https://iclr.cc/virtual/2026/poster/10008343) | 2025–26 | Generator → Reflector → Curator. The context is an evolving **itemized playbook** with incremental delta updates. Avoids brevity bias and context collapse. +10.6% agent, +8.6% finance (versions differ). Works from execution feedback without labels. | Best current evidence for "lessons as editable bullet list" | Benchmarks are agent/finance, not companionship | Yes. Bullets map to table rows. |
| 8 | Mem^p (procedural memory) | [arXiv 2508.06433](https://arxiv.org/abs/2508.06433) | 2025 | Build/retrieve/update procedural memory (trajectories + script-like abstractions). Studies update strategies. † | Explicit procedural-memory lifecycle | Task-agent focus | Yes |
| 9 | PAHF — Learning Personalized Agents from Human Feedback | [arXiv 2602.16173](https://arxiv.org/abs/2602.16173) | 2026 | Ask clarification before acting, ground in retrieved preferences, **update memory from post-action feedback** when preferences drift | Closest to "learn from user corrections" | New | Yes |
| 10 | AdaMem | [arXiv 2606.21144](https://arxiv.org/html/2606.21144) | 2026 | Learns natural-language **Memory Policies** from user feedback, which decide what to write in which context | Feedback shapes writes, not just reads | New | Yes |
| 11 | PersonaAgent | [arXiv 2506.06254](https://arxiv.org/abs/2506.06254) | 2025 (ACL'26) | Personalized memory plus action module. Outcomes refine a persona prompt. | Persona as a living prompt | — | Yes |
| 12 | MIRIX | [arXiv 2507.07957](https://arxiv.org/abs/2507.07957) | 2025 | Six memory types incl. **procedural** and core/episodic/semantic/resource/knowledge-vault, each with a manager agent † | Typed memory taxonomy | Multi-agent overhead | Taxonomy only |
| 13 | "Beyond Recall: Behavioral Specification as an Interpretive Layer" | [arXiv 2605.28969](https://arxiv.org/pdf/2605.28969) | 2026 | Argues personalization needs a behavioral-spec layer, not just recall (from search listing) | Aligns with "don't talk like Y in situation X" | Not read in depth | Yes |

### Cited Findings
- ACE treats contexts as evolving playbooks via generation, reflection and curation. It names brevity bias and context collapse as the failure modes. It reports +10.6% on agent benchmarks and +8.6% on finance (another version cites 9.0%). It works from execution feedback without labeled supervision, and matched the top AppWorld production agent using a smaller open model. — [Microsoft Research](https://www.microsoft.com/en-us/research/publication/agentic-context-engineering-evolving-contexts-for-self-improving-language-models/); [arXiv 2510.04618](https://arxiv.org/abs/2510.04618); [ICLR 2026 poster](https://iclr.cc/virtual/2026/poster/10008343)
- ReasoningBank distills strategies from self-judged successes and failures, retrieves them at test time and writes new learnings back. It beats raw-trajectory and success-only memories on web/SWE benchmarks. — [arXiv 2509.25140 summary](https://fugumt.com/fugumt/paper_check/2509.25140v1_enmode)
- PAHF updates memory from post-action feedback when preferences drift. Explicit memory with two feedback channels beats no-memory and single-channel baselines. — [arXiv 2602.16173](https://arxiv.org/abs/2602.16173)
- AdaMem learns natural-language Memory Policies from user feedback that govern memory writing. — [arXiv 2606.21144](https://arxiv.org/html/2606.21144)
- Reflexion reaches 91% pass@1 on HumanEval through verbal reinforcement. † — [arXiv 2303.11366](https://arxiv.org/abs/2303.11366)

### Inferences
**Recommendation for Stiti (lessons): an ACE-style itemized playbook stored as rows, with ExpeL-style votes and PAHF-style correction capture.**
- Table `lessons(id, situation text, situation_embedding halfvec, trigger jsonb /* e.g. {"mood":"sad","topic":"work","time":"late_night","person":"mom"} */, guidance text /* "Don't joke; be brief and validating" */, polarity ENUM('do','dont'), source_episode_ids bigint[], created_at, valid tstzrange, helpful_count int, harmful_count int, last_applied_at, status ENUM('candidate','active','retired'), supersedes bigint)`.
- **Capture:** detect correction signals in user turns ("don't say that", "too long", "stop calling me…", or a tone shift / sigh, if voice prosody is available). Write a `candidate` lesson with the preceding assistant turn as evidence. Promote to `active` after confirmation (explicit, or a repeat within N days).
- **Curate (ACE):** never let the LLM rewrite the whole lessons list. Allow only per-item ops (ADD / EDIT / MERGE / RETIRE / UPVOTE / DOWNVOTE à la ExpeL), each logged. This prevents context collapse.
- **Retrieve:** at turn time, match the current situation (mood estimate, topic entities, people mentioned, time of day) against `trigger` (structured filter) plus `situation_embedding` (vector). Inject the top 3–7 active lessons into the briefing as hard style constraints.
- **Evaluate:** after a turn where a lesson was applied, lack of renewed correction increments `helpful_count`, and a repeat correction increments `harmful_count`. This is the cheap analogue of RMM's retrospective feedback.
- Lessons are model-agnostic text, so they survive swapping the LLM plug, which is a core requirement.

### Gaps
- No paper found that evaluates lesson memory specifically for *conversational tone/style* in companion chat. PAHF/AdaMem are the closest.
- Mem^p, AWM and ExpeL details are † (not re-fetched).

---

## Feature 5 — Hybrid retrieval & reranking

### Takeaway
The standard recipe is **vector kNN + lexical BM25 → Reciprocal Rank Fusion (k≈60) → optional graph-neighborhood expansion (1–2 hops, or PPR) → optional cross-encoder rerank of the top 20–50**. All of it except the cross-encoder runs inside one SQL query in Postgres. At personal scale (≤1M rows), the vector and BM25 legs should take milliseconds. A local cross-encoder is the main latency cost and should be capped (small model, ≤30 pairs) or skipped on the voice hot path.

### Comparison table
| # | Name | Link | Year | Core mechanism | Strengths | Weaknesses | Fits PG + 8 GB / free? |
|---|---|---|---|---|---|---|---|
| 1 | Reciprocal Rank Fusion | [Cormack et al. SIGIR'09](https://plg.uwaterloo.ca/~gvcormac/cormacksigir09-rrf.pdf) | 2009 | score = Σ 1/(k + rank_i), k=60 † | No score calibration needed. Trivial in SQL. | Ignores score magnitude | Yes |
| 2 | Supabase hybrid search (SQL RRF) | [Supabase docs](https://supabase.com/docs/guides/ai/hybrid-search) | 2024 | One SQL function: FTS CTE + pgvector CTE, FULL OUTER JOIN, weighted RRF (rrf_k param) † | Copy-paste Postgres pattern | tsvector ranking isn't true BM25 | Yes |
| 3 | Graphiti search recipes | [Zep paper](https://arxiv.org/abs/2501.13956) | 2025 | cosine + BM25 + BFS from seeds. Rerankers: RRF, MMR, episode-mentions, node-distance, cross-encoder. † | Graph-aware reranking | Needs graph DB | Re-implementable in SQL |
| 4 | HippoRAG PPR | [arXiv 2405.14831](https://arxiv.org/abs/2405.14831) | 2024 | Seed nodes from query → Personalized PageRank over KG † | Multi-hop association | Iterative compute | Python over a subgraph, or iterative SQL |
| 5 | MMR | [Carbonell & Goldstein 1998](https://www.cs.cmu.edu/~jgc/publication/The_Use_MMR_Diversity_Based_LTMIR_1998.pdf) | 1998 | Trade relevance vs redundancy † | Avoids 5 near-duplicate memories in the briefing | Extra pass | App-side |
| 6 | LongMemEval time-aware query expansion | [arXiv 2410.10813](https://arxiv.org/abs/2410.10813) | 2024 | Infer a time range from the query ("last spring") and filter values † | Big win for temporal questions | Needs a date parser | Yes (`WHERE occurred_at <@ range`) |
| 7 | ms-marco-MiniLM-L-6-v2 cross-encoder | [HF](https://huggingface.co/cross-encoder/ms-marco-MiniLM-L-6-v2) | 2021 | 22M-param cross-encoder † | Very fast on CPU | English, older | Yes. Apache-2.0. |
| 8 | bge-reranker-v2-m3 | [HF](https://huggingface.co/BAAI/bge-reranker-v2-m3), [superlinked](https://superlinked.com/models/baai-bge-reranker-v2-m3) | 2024 | 568M multilingual cross-encoder | Strong quality, multilingual | ~1 GB fp16 RAM. Unverified latency. | Yes. Apache-2.0. |
| 9 | Qwen3-Reranker-0.6B | [HF](https://huggingface.co/Qwen/Qwen3-Reranker-0.6B), [dev.co](https://dev.co/ai/llms/qwen3-reranker-0-6b) | 2025 | 0.6B LLM-based reranker (yes/no logit) | Latest small open reranker | Decoder model, slower per pair than encoder | Yes. Apache-2.0. |
| 10 | RMM retrospective reranker | [arXiv 2503.08026](https://arxiv.org/abs/2503.08026) | 2025 | Reranker refined online from the LLM's own citations of retrieved memories † | Personal adaptation | RL training loop | Optional later |
| 11 | ColBERT / late interaction; bge-m3 multi-vector | [bge-m3 arXiv 2402.03216](https://arxiv.org/abs/2402.03216) | 2024 | Dense + sparse + multi-vector from one model † | One model, three signals | Multi-vector storage heavier in PG | bge-m3 sparse could feed `sparsevec` |
| 12 | Mem0/A-MEM pure vector + metadata | [Mem0](https://arxiv.org/abs/2504.19413) | 2025 | Vector top-k on extracted facts † | Simple | Misses exact names/dates | — |

### Cited Findings
- ParadeDB `pg_search` wraps Tantivy (Rust). It is **AGPL-3.0** and has phrase/fuzzy/prefix queries. Tiger Data's `pg_textsearch` v1.0 (April 2026) is a from-scratch C BM25 index access method, **PostgreSQL license**, `ORDER BY content <@> 'terms' LIMIT k`. pg_textsearch 1.4.0 supports PG 17/18 only and scores phrases as bag-of-words. — [PostgreSQL.org announcement](https://www.postgresql.org/about/news/pg_textsearch-v10-3264); [Tiger Data blog [vendor]](https://www.tigerdata.com/blog/pg-textsearch-bm25-full-text-search-postgres); [Particula comparison](https://particula.tech/blog/pg-search-vs-pg-textsearch-bm25-postgres)
- Benchmarks conflict. Tiger Data [vendor] reports pg_textsearch beating ParadeDB on MS MARCO latency/throughput. A third-party test found pg_search top-100 p50 < 1 ms vs pg_textsearch 10.4 ms in a hybrid workload. — [Particula](https://particula.tech/blog/pg-search-vs-pg-textsearch-bm25-postgres); [Tiger Data [vendor]](https://www.tigerdata.com/blog/pg-textsearch-bm25-full-text-search-postgres)
- Reranker latency on Apple Silicon: no reproducible Qwen3-Reranker-0.6B vs bge-reranker-v2-m3 numbers found. A June 2026 blog on an **M5 Max** found bge-reranker-v2 (568M) ≈7× faster than Qwen3-Reranker-**4B**. An unattributed leaderboard lists ~12 ms/pair for bge-reranker-v2-m3 (≈1.2 s per 100 pairs), hardware unknown. — [contracollective (M5 Max)](https://contracollective.com/blog/bge-reranker-v2-vs-cohere-rerank-3-vs-qwen3-reranker-m5-max-mlx-2026); [mixpeek](https://www.mixpeek.com/curated-lists/best-rerankers)
- nxlabscc/agent-memory implements full-text + vector fused with RRF plus optional MMR, entirely in Postgres. — [GitHub](https://github.com/nxlabscc/agent-memory)

### Inferences
**Recommendation for Stiti (hybrid retrieval):**
- One SQL function `recall(query_text, query_vec, time_range, k)`:
  - CTE `v`: `ORDER BY embedding <=> $vec LIMIT 50` over episodes + facts + reflections (HNSW, `hnsw.iterative_scan = relaxed_order` when filtering by time).
  - CTE `t`: BM25 via `pg_textsearch` (permissive license, simple) or built-in `tsvector` + `ts_rank_cd` (zero install) `LIMIT 50`.
  - Fuse: `SUM(1.0/(60+rank))` over a FULL OUTER JOIN, then multiply by recency/importance/strength priors (Generative Agents).
  - Graph expansion: from top entities, a 1–2 hop recursive CTE over `facts WHERE valid @> now() AND upper_inf(recorded)` adds current facts about the people/projects mentioned.
- **Rerank only off the hot path, or tiny:** for voice, skip the cross-encoder, or use ms-marco-MiniLM-L-6 / bge-reranker-base on ≤20 candidates. Use bge-reranker-v2-m3 or Qwen3-Reranker-0.6B in background consolidation and for "deep recall" questions. Rough latency budget (inference): SQL hybrid ≈5–30 ms at personal scale; embedding the query ≈10–50 ms (small model on M2); MiniLM rerank of 20 pairs ≈ tens of ms. Measure locally.
- Start with built-in tsvector (it ships with Postgres.app). Adopt `pg_textsearch` if real BM25 helps. Avoid `pg_search` (AGPL) unless its features are needed. AGPL is fine for a private, local app, but it's a licensing consideration if Stiti is ever distributed.

### Gaps
- No verified M2-specific latency numbers for any reranker or for pgvector/pg_textsearch at personal scale. Must be benchmarked locally.
- Whether pg_textsearch / pg_search build cleanly on macOS arm64 with Postgres.app/Homebrew PG18 was not verified.

---

## Feature 6 — Local embeddings on an 8 GB M2

### Takeaway
On MTEB v2 the best small open model is **Qwen3-Embedding-0.6B** (MMTEB ≈64.3, English v2 ≈70.5–70.7, Apache-2.0, 1024-d with Matryoshka, 32k ctx), at ~1.2 GB fp16. **EmbeddingGemma-300M** (MMTEB ≈61.15, English v2 ≈69.67, 768-d MRL down to 128, Google says <200 MB RAM quantized) is the best quality-per-MB. bge-small/nomic are tiny fallbacks. For Stiti, with an LLM, STT and TTS competing for 8 GB: **EmbeddingGemma-300M (or Qwen3-0.6B if RAM allows), stored as `halfvec(768)` / MRL-truncated `halfvec(512)`**.

### Comparison table
| # | Model | Link | Year | Params / dims / ctx | MTEB (reported) | RAM (approx.) | License / M2 fit |
|---|---|---|---|---|---|---|---|
| 1 | Qwen3-Embedding-0.6B | [arXiv 2506.05176](https://arxiv.org/abs/2506.05176), [HF](https://huggingface.co/Qwen/Qwen3-Embedding-0.6B) | 2025 | 0.6B / up to 1024 (MRL) / 32k † | MMTEB 64.33–64.34. MTEB-Eng v2 70.47–70.70 (sources differ). | ~1.2 GB fp16. Less quantized (inference). | Apache-2.0. Ollama/MLX. Yes. |
| 2 | EmbeddingGemma-300M | [Google blog](https://developers.googleblog.com/en/introducing-embeddinggemma/), [datalearner](https://www.datalearner.com/ai-models/pretrained-models/embeddinggemma-300m) | 2025 | 308M / 768 (MRL 512/256/128) / 2k † | MMTEB 61.15, Eng v2 69.67 | <200 MB quantized [vendor] † | Gemma terms (free, not OSI). Yes. |
| 3 | EmbeddingGemma 2 | [fourweekmba summary](https://fourweekmba.com/ai-google-paper-embeddinggemma-2-trails-qwen-on-text-not-code/) | 2026 | — | MMTEB 61.36, Eng v2 68.46, Code 78.68 (vs Qwen3-0.6B 75.42) | — | Single secondary source |
| 4 | bge-m3 | [arXiv 2402.03216](https://arxiv.org/abs/2402.03216), [HF](https://huggingface.co/BAAI/bge-m3) | 2024 | 568M / 1024 / 8192. Dense+sparse+multi-vector. † | MMTEB ≈59.56 | ~1.1 GB fp16 | MIT. Yes. |
| 5 | nomic-embed-text-v1.5 | [arXiv 2402.01613](https://arxiv.org/abs/2402.01613), [HF](https://huggingface.co/nomic-ai/nomic-embed-text-v1.5) | 2024 | 137M / 768 MRL / 8192 † | MTEB v1 ≈62.3 † | ~0.3 GB | Apache-2.0. Ollama. Yes. |
| 6 | nomic-embed-text-v2-moe | [developersdigest](https://www.developersdigest.tech/blog/choosing-an-embedding-model-2026) | 2025 | 475M total (MoE) / 512-token input | No MTEB score found | — | Apache-2.0 † |
| 7 | bge-small-en-v1.5 | [HF](https://huggingface.co/BAAI/bge-small-en-v1.5) | 2023 | 33M / 384 / 512 † | MTEB v1 ≈62.2 † | ~0.13 GB | MIT. English only. |
| 8 | all-MiniLM-L6-v2 | [HF](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2) | 2021 | 22M / 384 / 256 † | MTEB v1 ≈56 † | <0.1 GB | Apache-2.0. Weak. |
| 9 | snowflake-arctic-embed-m-v2.0 | [HF](https://huggingface.co/Snowflake/snowflake-arctic-embed-m-v2.0) | 2024 | 305M / 768 MRL † | Strong retrieval (†, not re-fetched) | ~0.6 GB | Apache-2.0 |
| 10 | granite-embedding-small-english-r2 | [HF](https://huggingface.co/ibm-granite/granite-embedding-small-english-r2) | 2025 | 47M / 384 / 8k † | (not fetched) | ~0.1 GB | Apache-2.0 |
| 11 | mxbai-embed-large-v1 | [HF](https://huggingface.co/mixedbread-ai/mxbai-embed-large-v1) | 2024 | 335M / 1024 † | MTEB v1 ≈64.7 † | ~0.7 GB | Apache-2.0 |
| 12 | Model2Vec potion (static) | [repo](https://github.com/MinishLab/model2vec) | 2024 | Static token embeddings, no transformer † | Lower | ~30 MB, µs latency | MIT. Good "instant" first-pass. |
| 13 | jina-embeddings-v3 | [HF](https://huggingface.co/jinaai/jina-embeddings-v3) | 2024 | 570M / 1024 MRL † | Strong multilingual | ~1.1 GB | **CC-BY-NC**. Personal use only. |

Runtimes on M2: Ollama (ships nomic-embed-text, embeddinggemma, qwen3-embedding, bge-m3 †), `mlx-embeddings` (MLX-native †), sentence-transformers on MPS, ONNX Runtime CoreML EP, llama.cpp GGUF.

### Cited Findings
- Qwen3-Embedding-0.6B ≈64.34 MMTEB / 70.47 MTEB-Eng v2. EmbeddingGemma 2 ≈61.36 / 68.46 but leads on MTEB Code (78.68 vs 75.42). EmbeddingGemma 1 ≈61.15 multilingual / 69.67 English. Sources differ slightly (64.33 vs 64.34; 70.47 vs 70.70). — [fourweekmba (secondary)](https://fourweekmba.com/ai-google-paper-embeddinggemma-2-trails-qwen-on-text-not-code/); [regolo.ai](https://regolo.ai/embeddinggemma-2-vs-qwen3-embedding-benchmarks.md)
- bge-m3 59.56 vs Qwen3-0.6B 64.34 on multilingual MTEB average. — [codesota](https://codesota.com/tasks/text-embeddings)
- nomic-embed-text-v2-moe: 475M total params, 512-token input. No MTEB score found. — [developersdigest](https://www.developersdigest.tech/blog/choosing-an-embedding-model-2026)
- SurrealDB's 2026 embedding comparison blog covers these families (not fetched in detail). — [SurrealDB](https://surrealdb.com/blog/embedding-models-comparison)

### Inferences
**Recommendation for Stiti (embeddings):**
- **Default: EmbeddingGemma-300M** (768-d → store `halfvec(768)`, or MRL-truncate to 512 if you need space). Best quality per MB, and it leaves RAM for the LLM, STT and TTS. Run it via Ollama or MLX as a resident process. Personal voice turns are short, so the 2k context is fine.
- **Upgrade path: Qwen3-Embedding-0.6B** if the RAM budget allows (~+1 GB). It is the best small model on MMTEB and suits multilingual/code-mixed speech (e.g., Hinglish).
- **Store `model_id` with every vector**, plus a `reembed` job (nxlabscc pattern), so switching models is a background migration. This keeps embeddings swappable like the LLM.
- pgvector indexes `vector` up to 2,000 dims and `halfvec` up to 4,000. Both models fit with halfvec.

### Gaps
- No verified per-model RAM/latency on an 8 GB M2 under concurrent LLM load. Benchmark locally.
- Mid-2026 MTEB leaderboard state (e.g., newer sub-1B models released after June 2026) was not checked beyond the sources above.

---

## Feature 7 — Postgres graph / vector / text implementation (incl. install & RAM)

### Takeaway
On an 8 GB M2, use **Postgres 18 (Postgres.app or Homebrew) + pgvector (bundled in Postgres.app) + btree_gist + built-in FTS (or pg_textsearch)**, with the graph modeled as **plain relational tables traversed by recursive CTEs** (PG14+ `SEARCH`/`CYCLE`). Apache AGE now supports PG18 (1.7.0 Jan 2026; 1.8.0 Aug 2026) and LightRAG uses it, but it needs building from source on macOS, isn't in Postgres.app, and adds little at personal-graph scale (thousands to ~100k edges). pgvectorscale (DiskANN) is unnecessary below millions of vectors.

### Comparison table (implementation options & Postgres-native projects)
| # | Option / project | Link | Year | Core mechanism | Strengths | Weaknesses | Fits 8 GB M2 / free? |
|---|---|---|---|---|---|---|---|
| 1 | pgvector (HNSW/IVFFlat, halfvec, sparsevec, bit) | [repo](https://github.com/pgvector/pgvector), [0.8.0 news](https://www.postgresql.org/about/news/pgvector-080-released-2952/) | 2021–26 | ANN indexes in Postgres. 0.8.0 added **iterative index scans** (`hnsw.iterative_scan`, `hnsw.max_scan_tuples`) for filtered queries and better planner costing. 0.8.x is current (0.8.2 on PGXN; third party says 0.8.5). | Mature, bundled in Postgres.app, in Homebrew | HNSW build wants maintenance_work_mem | Yes. PostgreSQL license. |
| 2 | pgvectorscale | [repo](https://github.com/timescale/pgvectorscale) | 2024 | StreamingDiskANN + statistical binary quantization (Rust/pgrx) † | Large-scale cost/latency [vendor] | Build from source on macOS. Pointless at <1M vectors. | Optional. PostgreSQL license. |
| 3 | Built-in FTS (tsvector/GIN, ts_rank_cd) | [PG docs](https://www.postgresql.org/docs/current/textsearch.html) | — | Lexical match + ranking (not BM25: no corpus IDF) † | Zero install | Weaker ranking | Yes |
| 4 | pg_textsearch | [PG news](https://www.postgresql.org/about/news/pg_textsearch-v10-3264) | 2026 | Native BM25 index AM in C. PG17/18. | Permissive license | Phrase = bag-of-words | Yes (build) |
| 5 | ParadeDB pg_search | [particula](https://particula.tech/blog/pg-search-vs-pg-textsearch-bm25-postgres) | 2024–26 | Tantivy BM25 inside PG | Rich queries | AGPL. Heavier build. | Yes (license caveat) |
| 6 | Apache AGE | [release notes](https://age.apache.org/release-notes), [EDB 1.8.0 notes](https://www.enterprisedb.com/docs/pg_extensions/apache_age/rel_notes/apache_age_1.8.0_rel_notes/) | 2020–26 | openCypher via `cypher()` SQL function, agtype | Cypher queries in PG | Build from source on macOS. Version lag. Mixing agtype with pgvector is awkward. | Possible, not needed |
| 7 | Recursive CTE over edge tables | [PG docs WITH](https://www.postgresql.org/docs/current/queries-with.html) | — | `WITH RECURSIVE` + `SEARCH BREADTH FIRST` / `CYCLE` (PG14+) † | Joins freely with vectors, ranges, FTS | Verbose. Deep variable-length paths are slow. | **Recommended** |
| 8 | Temporal tables: tstzrange + EXCLUDE / PG18 WITHOUT OVERLAPS & PERIOD FK | [Neon](https://neon.com/postgresql/postgresql-18/temporal-constraints) | 2025 | DB-enforced non-overlapping validity | Integrity for bitemporal facts | `btree_gist` needed (contrib, bundled) | Yes |
| 9 | pg_cron | [repo](https://github.com/citusdata/pg_cron) | 2016–26 | Cron inside PG (needs shared_preload_libraries) † | DB-native scheduling | Build/config on Mac. LLM jobs live outside PG anyway. | Optional |
| 10 | LISTEN/NOTIFY | [PG docs NOTIFY](https://www.postgresql.org/docs/current/sql-notify.html) | — | Async pub/sub. Delivered at commit. Payload < 8000 bytes by default. † | Trigger-driven workers, no broker | Not durable (missed if no listener) | Yes |
| 11 | Cognee 1.0 on Postgres | [cognee](https://www.cognee.ai/graph-on-postgres) | 2026 | Graph + pgvector + sessions in one PG [vendor] | Full framework | Python framework, LLM-heavy | Yes |
| 12 | nxlabscc/agent-memory | [repo](https://github.com/nxlabscc/agent-memory) | 2026 | Bitemporal facts + RRF in PG+pgvector | Closest design match | Immature | Reference |
| 13 | Persistor | [site](https://persistor.ai/) | 2026 | "KG + vector hybrid memory, PostgreSQL-native, local-first, open-source core" [vendor] | Local-first | Paid tiers, unverified | Check |
| 14 | Constructive agentic-db | [press release](https://www.prnewswire.com/news-releases/constructive-open-sources-agentic-db-the-postgres-memory-layer-for-ai-agents-302755269.html) | 2026 | OSS Postgres DB for agents: memory, history and KG in one DB [vendor] | One-DB | Press release only | Check |
| 15 | Letta server | [repo](https://github.com/letta-ai/letta) | 2023–26 | Agents/memory blocks/messages in Postgres, archival passages in pgvector. SQLite for local default. † | Production PG usage | Agent-loop centric | Yes |
| 16 | LightRAG PG backends | [repo](https://github.com/HKUDS/LightRAG) | 2024–26 | PGKVStorage / PGVectorStorage / PGGraphStorage (AGE) † | Shows AGE + pgvector together | Not temporal | Yes (needs AGE) |
| 17 | Other PG memory repos: open-agent-memory, pg-agent-memory, agentic-graphrag-memory | [OAM](https://github.com/rocke2020/open-agent-memory), [pg-agent-memory](https://github.com/alexpota/pg-agent-memory), [agentic-graphrag-memory](https://github.com/tsantoso79/agentic-graphrag-memory) | 2025–26 | PG+pgvector memory layers (cited recall/profiles. TS context mgmt. LightRAG + entity graph + work queue in one PG.) | Patterns to borrow | Small projects | Reference |

### Cited Findings
- Apache AGE: 1.6.0 for PG17 (22 Sep 2025). 1.7.0 adds PG18 and RLS support (21 Jan 2026). EDB lists 1.7.0.1 (20 Mar 2026, PG17+18) and 1.8.0 (11 Aug 2026, adds pg_upgrade support). Debian/Ubuntu PG18 packages are at 1.8.0~rc0, and newreleases shows a PG18/v1.8.0-rc0 tag, so the dates conflict. — [Apache AGE release notes](https://age.apache.org/release-notes); [EDB 1.8.0](https://www.enterprisedb.com/docs/pg_extensions/apache_age/rel_notes/apache_age_1.8.0_rel_notes/); [EDB 1.7.0.1](https://www.enterprisedb.com/docs/pg_extensions/apache_age/rel_notes/apache_age_1.7.0.1_rel_notes/); [newreleases](https://newreleases.io/project/github/apache/age/release/PG18%2Fv1.8.0-rc0); [Debian tracker](https://tracker.debian.org/media/packages/p/postgresql-18-age/control-1.8.0rc0-2)
- Broadcom plans to bundle AGE with VMware Tanzu Postgres 18.4 (expected by end of May 2026), a sign of enterprise maturity. — [Broadcom KB](https://knowledge.broadcom.com/external/article/442082/apache-age-extension-availability-in-vmw.html)
- pgvector 0.8.0 (released 2024-10-30) added iterative index scans for HNSW/IVFFlat (fixes overfiltering), improved cost estimation for filtered queries, and faster HNSW scans/inserts. halfvec HNSW indexes support up to 4,000 dims. — [PostgreSQL news](https://www.postgresql.org/about/news/pgvector-080-released-2952/); [Nile](https://www.thenile.dev/blog/pgvector-080); [PGXN](https://pgxn.org/dist/vector)
- Postgres.app bundles pgvector (enable with `CREATE EXTENSION`). User-installed extensions go in `~/Library/Application Support/Postgres/Extensions/XX`, which survives app updates for PG18+. Binaries are in `/Applications/Postgres.app/Contents/Versions`. — [Postgres.app extensions](https://postgresapp.com/extensions/)
- Homebrew has a `pgvector` formula. — [formulae.brew.sh](https://formulae.brew.sh/formula/pgvector)
- PG18 temporal PK/UNIQUE `WITHOUT OVERLAPS` and FK `PERIOD` require btree_gist and use GiST. Converting temporal PK/FK to plain in one migration is rejected. — [Neon](https://neon.com/postgresql/postgresql-18/temporal-constraints); [Atlas changelog](https://atlasgo.io/changelog/postgres-temporal-constraints); [Xata](https://xata.io/blog/postgres-as-a-temporal-db)
- Cognee runs graph + vectors + sessions on one Postgres [vendor]. Persistor and Constructive agentic-db make similar "all-in-Postgres" claims [vendor]. — [Cognee](https://www.cognee.ai/graph-on-postgres); [Persistor](https://persistor.ai/); [PR Newswire](https://www.prnewswire.com/news-releases/constructive-open-sources-agentic-db-the-postgres-memory-layer-for-ai-agents-302755269.html)

### Inferences
**Recommendation for Stiti (Postgres stack):**
- **Install:** Postgres.app (PG18; pgvector and btree_gist included) is the lowest-friction option. Homebrew `postgresql@18` + `pgvector` is the alternative. Add `pg_textsearch` later if BM25 quality matters. **Skip AGE** for v1: recursive CTEs over `facts` are sufficient for 1–3-hop neighborhoods on a single person's graph. They compose directly with `valid @> now()`, vector similarity and FTS in one statement, which AGE's agtype Cypher calls do poorly. Revisit AGE only for heavy variable-length path queries.
- **RAM tuning for 8 GB (inference, not measured):** `shared_buffers=256MB`, `effective_cache_size=1GB`, `work_mem=8–16MB`, `maintenance_work_mem=256MB` (raise temporarily for HNSW builds), `max_connections=20`, autovacuum on. Expected resident footprint is a few hundred MB, leaving most RAM for the LLM, STT, TTS and the embedder. Default `shared_buffers` is 128MB. Postgres.app memory numbers weren't found (gap).
- **Graph traversal pattern:**
  ```sql
  WITH RECURSIVE nb(entity_id, depth, path) AS (
    SELECT unnest($seed_ids), 0, ARRAY[]::bigint[]
    UNION ALL
    SELECT CASE WHEN f.subj_id = nb.entity_id THEN f.obj_id ELSE f.subj_id END, nb.depth+1, nb.path || f.id
    FROM nb JOIN facts f ON (f.subj_id = nb.entity_id OR f.obj_id = nb.entity_id)
    WHERE nb.depth < 2 AND f.valid @> now() AND upper_inf(f.recorded) AND NOT f.id = ANY(nb.path)
  ) SELECT ...
  ```
  Index `facts(subj_id)`, `facts(obj_id)`, plus GiST on `valid`. For PPR (HippoRAG), export the ≤2-hop subgraph to Python (networkx/igraph) during consolidation, or iterate ~10 power steps in SQL.
- **Event plumbing:** an `AFTER INSERT` trigger on `episodes` calls `pg_notify('stiti_mem', NEW.id::text)`. The Stiti worker listens and runs incremental extraction. A nightly scheduler (pg_cron or the app) runs the sleep pipeline. Keep notification payloads to IDs (< 8 KB limit).
- **Backups:** `pg_dump` nightly to an encrypted local file. Postgres gives Stiti's "infinite memory" a durable, inspectable home.

### Gaps
- Apache AGE on macOS arm64 with Postgres.app/Homebrew PG18: no first-hand build report found. Must be compiled from source. Exact 1.8.0 release status conflicts across sources.
- pg_cron, pg_textsearch and pgvectorscale macOS packaging was not verified.
- No measured Postgres RAM footprint on macOS found. The tuning above is inference.
- Performance of AGE vs recursive CTE: no benchmark found this session.

---

## Benchmarks & reported results (LongMemEval, LoCoMo, DMR, others)

### Takeaway
**LoCoMo** (≈300-turn, ≤35-session dialogues) and **LongMemEval** (500 questions over 5 abilities; ~115k-token "S" and ~1.5M-token "M" variants) are the de-facto memory benchmarks. **Nearly all headline numbers are vendor-reported, with different judges/LLMs**, and independent re-tests are often far lower. Stiti should build a **private eval set in the LongMemEval taxonomy** (info extraction, multi-session reasoning, temporal reasoning, knowledge updates, abstention) from the user's own (consented) history.

### Cited Findings
- LoCoMo: very long-term conversations averaging ~300 turns / ~9K tokens over up to 35 sessions. Tasks: QA (single-hop, multi-hop, temporal, open-domain, adversarial), event summarization, multimodal dialogue. † — [Maharana et al. ACL 2024, arXiv 2402.17753](https://arxiv.org/abs/2402.17753)
- LongMemEval: 500 curated questions testing information extraction, multi-session reasoning, temporal reasoning, knowledge updates and abstention. Commercial assistants and long-context LLMs show ~30% accuracy drop on sustained interactions. † — [Wu et al. ICLR 2025, arXiv 2410.10813](https://arxiv.org/abs/2410.10813)
- Mem0 paper (LoCoMo, LLM-as-judge): Mem0 ≈66.9, Mem0g ≈68.4, vs OpenAI memory ≈52.9 (≈26% relative gain), with ~91% lower p95 latency and ~90% fewer tokens than full-context. † [vendor-authored] — [arXiv 2504.19413](https://arxiv.org/abs/2504.19413)
- Mem0 now self-reports 92.5% LoCoMo and 94.4% LongMemEval (another post: 93.4%). An independent test of Mem0 OSS found ~32–49% LongMemEval R@5. — [Mem0 blog [vendor]](https://mem0.ai/blog/ai-memory-benchmarks-in-2026); [Mem0 state of memory [vendor]](https://mem0.ai/blog/state-of-ai-agent-memory-2026); [DEV independent test](https://dev.to/everest_an/-i-benchmarked-ai-agent-memory-in-2026-and-the-numbers-tell-a-different-story-than-the-marketing-2ae4)
- Zep claims 94.7% LoCoMo. A competitor table shows 75.1%, and other sources say ~80–83%. LongMemEval 71.2% (GPT-4o) is the most-cited figure. Zep's paper: DMR 94.8% vs MemGPT 93.4%. — [Mem0 blog [competitor vendor]](https://mem0.ai/blog/ai-memory-benchmarks-in-2026); [Agent Zero Memory arXiv 2608.29606](https://arxiv.org/pdf/2608.29606); [Zep paper †](https://arxiv.org/abs/2501.13956)
- Letta: 74.0% on LoCoMo with gpt-4o-mini + filesystem storage (simple file tools rival specialized memory). Another test cites ~83%. — [Mem0 blog](https://mem0.ai/blog/state-of-ai-agent-memory-2026); [DEV](https://dev.to/everest_an/-i-benchmarked-ai-agent-memory-in-2026-and-the-numbers-tell-a-different-story-than-the-marketing-2ae4)
- MemOS: LoCoMo LLM-judge 75.80 vs MIRIX 64.33 vs Mem0 59.22 (authors' runs). — [arXiv 2507.03724](https://arxiv.org/pdf/2507.03724v4)
- Agent Zero Memory claims 95.6% LongMemEval / 93.6% LoCoMo. ByteRover 2.0 is listed at 92.2% LoCoMo. — [arXiv 2608.29606](https://arxiv.org/pdf/2608.29606)
- Newer benchmarks: BEAM (discussed alongside LoCoMo/LongMemEval) and PERMA (event-driven preference evolution for personalized memory agents). — [Mem0 benchmarks blog](https://mem0.ai/blog/ai-memory-benchmarks-in-2026); [PERMA arXiv 2603.23231](https://arxiv.org/pdf/2603.23231)
- HippoRAG 2 (multi-hop/associative QA): avg F1 59.8 vs 57.0 (NV-Embed-v2). — [emergentmind](https://www.emergentmind.com/topics/hipporag-2)

### Inferences
- LoCoMo is near-saturated by vendor claims (>90%) and is criticized for judge variance. LongMemEval's **temporal reasoning** and **knowledge update** categories map best to Stiti's temporal KG, and **abstention** matters for a buddy that must not invent memories.
- PERMA (preference evolution) is the most relevant for the "lessons/user model" feature and should be examined by the writer or a follow-up.
- Letta's filesystem result suggests that clean storage plus decent retrieval matters more than an exotic architecture, which supports a plain-Postgres design.

### Gaps
- No neutral, third-party leaderboard with a fixed judge exists, as far as found. BEAM details were not fetched.
- No benchmark evaluates memory systems with small (≤8B) local reader LLMs, which is Stiti's actual setting.

---

## Open-source memory systems — how each is built (implementation survey)

### Takeaway
Architecturally there are four families: **(1) LLM-managed memory blocks** (Letta/MemGPT), **(2) fact-extraction stores** (Mem0, Memobase, Supermemory, OpenMemory), **(3) graph-RAG/temporal-KG builders** (Graphiti, Cognee, LightRAG, GraphRAG, nano-graphrag, graphify, HippoRAG), and **(4) file-first memory** (Basic Memory, graphify output). Postgres-first options exist: Cognee 1.0, Letta server, LightRAG-PG, Mem0 + pgvector, and small all-PG repos. None implements Zep-grade bitemporal KG + lessons + briefing compilation in Postgres off the shelf, so Stiti should build its own engine borrowing these patterns.

### Cited Findings
- **Graphiti:** Python. Drivers for Neo4j/FalkorDB/Kuzu/Neptune only. Bitemporal edges, LLM extraction, hybrid search. — [driver docs](https://www.mintlify.com/getzep/graphiti/api/drivers/overview); [paper †](https://arxiv.org/abs/2501.13956)
- **Mem0:** 20+ vector stores incl. pgvector. Graph stores Neo4j/Memgraph/Neptune/Kuzu (AGE historically). OSS graph status disputed. — [Mem0 OSS graph docs](https://docs.mem0.ai/open-source/features/graph-memory); [codepointer](https://codepointer.substack.com/p/agent-memory-systems-and-knowledge)
- **Letta:** sleep-time agents (primary + sleep-time agent sharing memory blocks), shipped in 0.7.0. Server persistence on Postgres + pgvector †. — [Letta blog](https://letta.com/blog/sleep-time-compute); [repo](https://github.com/letta-ai/letta)
- **Cognee:** 1.0 runs graph + pgvector + sessions on one Postgres [vendor]. — [Cognee](https://www.cognee.ai/graph-on-postgres)
- **graphify:** folder → KG → graph.json / graph.html / GRAPH_REPORT.md. MIT. Writes a CLAUDE.md hint telling the assistant to read the report first. Rust port `graphify-export` generates the report. — [Better Stack](https://betterstack.com/community/guides/ai/ai-development/graphify-codebase/); [docs.rs graphify-export report.rs](https://docs.rs/graphify-export/0.5.1/src/graphify_export/report.rs.html); [mcpservers](https://mcpservers.org/servers/graphify-labs/graphify)
- **MemOS:** MemCube units with provenance/versioning. Scheduler/operator layers. Plaintext + activation + parametric memory. — [arXiv 2507.03724](https://arxiv.org/pdf/2507.03724v4); [MemOS docs](https://memos-docs.openmem.net/overview/algorithm)
- **Memobase:** self-hosted, conversation-centric, profile-oriented, "Dream Phase" distillation [third-party]. — [aimemory.pro](https://aimemory.pro/blog/mcp-memory-server-comparison)
- **Supermemory:** hosted memory API with memory graph + user profiles. Self-host option claimed by an aggregator. — [Supermemory blog [vendor]](https://blog.supermemory.ai/best-memory-apis-stateful-ai-agents); [unabyss](https://unabyss.com/blog/supermemory-alternatives)
- **OpenMemory:** open-source local MCP server sharing memory across tools on one machine. 2026 plugins for Claude Code, Cursor, Codex. (Name collision: Mem0's OpenMemory MCP and a separate CaviraOSS "OpenMemory" project exist †. Clarify which one is meant.) — [memorylake](https://www.memorylake.ai/en/blogs/best-openmemory-alternatives)
- **Basic Memory:** Markdown files as a local knowledge graph over MCP. AGPL-3.0. Paid cloud tier. — [aimemory.pro](https://aimemory.pro/blog/mcp-memory-server-comparison)
- **LightRAG:** dual-level graph retrieval. PostgreSQL backends (pgvector + AGE graph). † — [repo](https://github.com/HKUDS/LightRAG)
- **All-in-Postgres repos:** nxlabscc/agent-memory (bitemporal, RRF, Apache-2.0, immature), open-agent-memory (FastAPI + psycopg + pgvector, profiles, cited recall), pg-agent-memory (TS), agentic-graphrag-memory (memories, vectors, entity graph, work queue and eval logs all in one PG). — [nxlabscc](https://github.com/nxlabscc/agent-memory); [OAM](https://github.com/rocke2020/open-agent-memory); [pg-agent-memory](https://github.com/alexpota/pg-agent-memory); [agentic-graphrag-memory](https://github.com/tsantoso79/agentic-graphrag-memory)

### Inferences
**Overall architecture recommendation for Stiti's memory engine (synthesis of the above):**
1. **Single Postgres 18 database** with schemas: `episodic` (episodes, segments), `semantic` (entities, facts [bitemporal], communities), `self` (user_profile slots with validity), `procedural` (lessons), `meta` (consolidation_runs, model registry, briefing_cache).
2. **Write path (per turn, cheap):** insert episode → embed → NOTIFY → async light extraction (entities mentioned, correction detection).
3. **Sleep path (idle):** segmentation, fact extraction + interval closing, reflections, profile, lessons curation (ACE deltas), communities/god-nodes, and briefing pre-compilation (sleep-time compute).
4. **Read path (per turn, <100 ms target):** query embed → one SQL hybrid recall (RRF + recency/importance priors + time filter + 1–2 hop current-fact expansion) → assemble a **graphify-style per-turn briefing**: standing context from cache + retrieved episodes/facts with dates + active lessons + profile. The LLM plug reads only this briefing.
5. **Swappability:** all memory is text + vectors tagged with `model_id`. The embedder can be re-run, and the LLM can be swapped without touching memory.

### Gaps
- Internals of Supermemory, Memobase and OpenMemory (storage engines, schemas) were not verified from primary repos this session. Descriptions rely on third-party comparisons.
- Whether Letta's current release still uses SQLite by default locally and Postgres for server deployments (†) was not re-verified.
