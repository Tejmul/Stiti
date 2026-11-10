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
- **Measured after both: 1,254 MB** for the whole running app (was 2,759 MB).

## D13: "Key Things to Know" intake — licence-safe, any owner (2026-11-10)
Research: `research_notes/Key things to know intake/intake_research.md` (8 features, 12–18 sources each).
- **Ship verbatim only free instruments:** IPIP / Mini-IPIP (public domain), TIPI + TIVI/TwIVI (free for any use),
  VADER / Empath / AFINN for text. **Do not ship item wording** of BFI-2/-S/-XS, BFI-10, HEXACO, PVQ/SVS, BPNSFS,
  PSS, MEQ/rMEQ/MCTQ, NRC EmoLex, LIWC (non-commercial / permission / proprietary). Constructs aren't copyrighted
  → Stiti asks its own plainly worded questions, labelled "Stiti-original, unvalidated" (e.g., sleep times →
  MCTQ-style mid-sleep and social jetlag computed, not their questionnaire).
- **Design:** ~20 turns (~6 min est.): consent → name/pronouns → people → sleep times → peak hours → likes/peeves →
  5 Mini-IPIP items (spoken 5-point) → 2 values this-or-thats → goal → gain vs avoid → reply style + aap/tum →
  check-in frequency → consent gate → rough-day signs / what helps / own coping → boundaries → role → read-back.
  Remaining Mini-IPIP/TIVI items spread over 2–3 weeks, ≤1 question/day, opt-in.
- **Evidence limits:** don't infer personality from text (r ≈ .3–.4 at best); use explicit statements + behaviour
  counts. Tailoring effects are small (r ≈ .07) → adaptations serve the owner's own goals, logged, switchable off.
- **Ethics:** consent twice, no clinical words, "leans …" labels with source + confidence, "What do you know about
  me?" + correction; stress/coping answers are P2 (never leave the Mac); never infer religion, caste, orientation,
  politics, health; self-harm → stop + configurable helpline list.
- **Open item:** add a LICENSE file (MIT/Apache) — consistent with only shipping free instruments.

## D14: Whiteboard tutor — stack and pedagogy (2026-11-10)
Research: `research_notes/Whiteboard tutor/whiteboard_tech.md` (tested on this Mac) and `tutoring_pedagogy.md`.
- **Board:** Excalidraw `@excalidraw/excalidraw@0.18.1` (MIT) + React 19.2.0 via esm.sh import map; API:
  `convertToExcalidrawElements`, `updateScene({captureUpdate: NEVER})`, `newElementWith`, `scrollToContent`.
  Wait for `appState.isLoading=false` before the first update; frame whole sections (not single tiny elements);
  laser tool doesn't work in view mode. Offline bundle option (8.1 MB + 13 MB fonts). **tldraw rejected** (licence).
- **LLM output:** lesson JSON with board *regions*, never pixels; strict `json_schema` (Groq gpt-oss/Qwen; flat
  nullable schema for Cerebras); graphs as nodes/edges laid out by `@dagrejs/dagre@3.1.3`; Mermaid optional
  (mermaid-to-excalidraw pinned 2.3.0). Strict mode can't stream → generate the next segment while one plays.
- **Server:** Starlette WebSocket on uvicorn (already in uv.lock, ~38 MB), 127.0.0.1 random port, token in URL
  fragment, Host/Origin checks.
- **Sync:** one cue per spoken sentence carrying its board ops (offsets start/end/fraction/word), ops keyed by id
  (replay-safe), pause/resume-from-sentence, rewind via snapshots, voice barge-in.
- **Book → lesson:** structure from the file (pypdfium2 TOC/page labels; pdfplumber font-size headings fallback;
  MarkItDown for EPUB; avoid AGPL PyMuPDF/EbookLib), compress chapters locally (~3K tokens each, page tags),
  1 LLM call per chapter + 1 for the 30-min plan; citations = chunk ids checked in code; ~50–60K tokens/lesson.
- **Pedagogy:** ~26 min content + ~4 min slack: warm-up → "guess first" → 3-box map → 3×(5–6 min segment + real
  check) → teach-back/apply → 3-question no-notes quiz with confidence → learner-first recap + 5–8 FSRS cards;
  15-min low-energy variant. ≤60–90 s of tutor talk per turn; draw each item in the sentence that names it;
  never reveal a check's answer before the attempt, never accept "samjha?" as evidence (Bastani 2025: answer-
  giving AI → −17% exam; Kestin 2025: scaffolded tutor ≥ active learning). 8 interruption types, ≤2 hints then
  explain, resume stack + bridge sentence. Code owns time, resume stack and repairs; the model only fills slots.
- **Prior art to study:** ChalkTalk (Excalidraw + Kokoro + raise-hand), OpenMAIC (MIT, action engine/resume),
  official excalidraw-mcp (prompt cheat sheet, camera ops).

## D15: Whiteboard tutor — what was actually built (2026-11-10)
Refines D14 after building + testing on this Mac (`src/stiti/tutor/`, `tests/tutor_eval.py` 27/27).
- **Layout in Python, not dagre.** `skills.py` owns every pixel: pages per segment (1600×900, side by side),
  regions (title/main/side/parking/goal/notes), relative placement (right_of/below/…), collision push-down,
  and a tiny Sugiyama for graphs (longest-path ranks, barycentre order, children centred under parents,
  wrapped LR rows for long chains). Deterministic and unit-testable; one less CDN dependency.
- **Whiteboard skills:** title, text, bullet, box (rect/ellipse/diamond), arrow, graph, table, formula, sticky,
  highlight (underline/circle/marker/color/tick/cross/pointer; old pointers fade), strike, erase, focus,
  new_page, Q&A side boards, parking lot. Animations in the browser: sketch (outline drawn on), grow, type, fade.
- **Browser gotchas fixed:** load Excalifont/Comic Shanns via `document.fonts.load()` before the first draw
  (`fonts.check()` lies for unloaded faces → clipped text); camera computed in JS from a scene rect (no
  `scrollToContent` zoom bug); `[hidden]` must beat component `display`.
- **Checks graded locally** (`grade.py`): MCQ letter/word/ordinal, expectation coverage by keywords + the local
  embedder, partial credit, "pata nahi" → hint ladder (≤2) → kind reveal; confidence 1–5 on quiz items.
  The LLM never decides right/wrong (principle 1).
- **Voice-first:** every control works by voice (Hinglish), MCQ options are read aloud, `--no-board` runs a
  lesson with no screen. Backchannels ("haan") are ignored only while she narrates — never during prompts.
- **Questions without an LLM:** answered from the lesson itself (local embedder) on a side board, or parked.
- **LLM only fills slots:** code builds warm-up/hook/3-box map/quiz/wrap; 1 outline + 1 call per idea (strict
  json_schema on Groq/Cerebras via router `schema=`), written in a background thread while earlier parts play.
- **Books:** printed "Contents" pages are the best structure source for scanned PDFs (Aho: 654 headings in
  2.7 s); page labels = PDF index − median running-head offset; heading regex fallback; extractive sources.
- **Persistence:** migration 006 (`tutor_lessons`, `tutor_sessions` with resume cursor, `study_cards` with FSRS
  fields) + one memory episode per lesson. The always-on voice loop goes quiet while `~/.stiti/tutor.lock` exists.

## D16: Local web app — landing + chat (2026-11-10)
- `stiti web` serves `src/stiti/web/static` with Starlette on 127.0.0.1:7317 (STITI_WEB_PORT). Same safety model
  as the board: Host check on every request, Origin + per-install token (`~/.stiti/web_token`, handed over in the
  URL fragment, kept in localStorage) on the WebSocket and API.
- Chat goes through the normal `Engine("text")` → the web chat is the same Stiti (memory, fast paths, lessons).
  Side panel shows open todos (tick to finish) and upcoming alarms/reminders, refreshed after every turn.
- Look: owner's reference (light lavender paper, deep navy, blue particle sphere, light/bold Hanken Grotesk,
  Martian Mono labels), white glass navbar; particle motion only in the hero (+ the small "mind" in chat).
- No build step: plain ES modules; GSAP + Lenis from pinned CDNs (free). Icons: owner-supplied pictograms
  (`public/actions`, served at `/icons/<n>.png`).

## D17: Free LLM provider line-up + per-provider privacy (2026-11-10)
Research + live latency table: `docs/research/free_llm_providers.md` (17 providers compared).
- **Keep:** Groq (primary; Qwen3.8-27B first for voice, ~190 ms first token), OpenRouter `:free`, Gemini (P0 only).
- **Add:** Z.ai GLM-4.7-Flash (free, no training on API data → P1 backup), Cloudflare Workers AI (10k neurons/day,
  P1 backup), NVIDIA NIM (DeepSeek/Kimi/Qwen, evaluation terms → P0 only).
- **Drop / not free:** Cerebras (card since 2026-07), Hugging Face (no free credits since 2026-10), GitHub Models
  (retired), Moonshot ($1 top-up), Ollama Cloud (Tejmul's no-Ollama rule), anonymous endpoints (privacy).
- **Privacy:** each provider has `max_privacy`; P1 turns only go to providers that don't train on API data;
  OpenRouter P1 requests send `data_collection: deny` (in practice its free models then 404 → P0 only).
- **Zero cost enforced in code:** `router.is_free()` (OpenRouter `:free` only, Z.ai exact free list) filters every chain.
- **Measured after keys arrived:** NVIDIA Nemotron Lightning/Bolt ~0.3–0.5 s (P0 fallback); Z.ai free GLM overloaded
  (429 / 8–20 s) → last resort. Personal-chat backup when Groq is down = Cloudflare (needs the account ID).
- **Why:** with only Groq + OpenRouter, a Groq outage left personal chats with no backup (tested).

## D18: Conversation speed — stream, overlap, never dead air (2026-11-10)
Research: `docs/research/voice_latency.md` (19 sources). Measured on the M2 (simulated mic/speaker, real models + Groq):
voice-to-first-audio ≈ **0.85–1.0 s** (was ≈ 2.3 s): transcript ready 233–368 ms after he stops, first audio
≈ 0.3 s after the LLM's first token.
- **Stream the LLM** (`router.stream`, same chain/gates; fallback only before the first token) and speak the
  first short clause (`ClauseChunker`: a sentence end of any length, a comma after ≥3 words, or ~7 words).
- **Gapless speech** (`voice/speaker.py`): the next piece is synthesised while the current one plays (0 ms gaps).
- **One persistent Kokoro thread** — Kokoro pays ~700 ms the first time it runs in any new thread (measured).
- **Early STT**: whisper starts 160 ms into a pause on a persistent thread; thrown away if he keeps talking.
- **Turn-end**: Smart Turn re-asked at 300/600/1000 ms with a falling bar; fallback 1.5 s (was one check + 2 s).
- **Warm everything**: Smart Turn + whisper + Kokoro loaded at start; LLM connections opened on wake, kept alive 300 s.
- **Never dead air**: instant pre-synthesised acks for slow actions ("Ek sec, calendar dekhti hoon") fired by the
  engine (`on_ack`); "hmm" filler if nothing is ready by 0.9 s.
- **Goodbyes**: "bye / chalo bye / good night" → a warm local goodbye (`farewell.py`, time/mood/language aware,
  no LLM); "shut up / stop / chup" stay silent.
- `psych.StreamLint` applies the reply rules (guilt words, one question, ≤3 items) per streamed piece.

## D19: Any book + one-night crash course (2026-11-10)
Research: `docs/research/crash_course.md` (20 sources). Tutor fixes first (tests showed them): per-part source
selection (Groq's 8k TPM was rejecting every 9k-char prompt), patience + anonymised public-tier fallback, strict JSON
shape check in the router (Cloudflare returned the wrong shape → empty answers), fast `tutor_answer` route (Q&A 0.7–2.3 s),
chapter-first `find`, "p.109" citation normalisation.
- **Any book:** PDF (TOC → printed Contents → headings → page-range units), scanned PDF (Apple Vision OCR, lazy per
  page), EPUB/DOCX/HTML/PPTX via markitdown, TXT/MD with ~2,500-char pseudo-pages; chapter styles "Chapter 4",
  "CHAPTER IV", "XII. TITLE", "I\nTITLE", "Part Two"; Contents duplicates dropped (title + Roman→int number);
  Gutenberg licence stripped. Tested: Aho (PDF), Darwin + Wells (TXT), Wells (EPUB), notes/worksheets, a scanned PDF.
- **Crash course** (`tutor/course.py`, migration 007): lessons = ⌊(min−30)/20⌋ (2 h → 4, 3 h → 7, cap 10); lesson 1 =
  whole-book overview. Units scored locally (0.30 foundation · 0.25 centrality · 0.25 goal · 0.20 size); ONE LLM call
  orders the night + one diagnostic MCQ per lesson (fallback: local ranking). Subject without a book: one syllabus call
  (importance + prereqs) → topological order. Diagnostic: right + confidence ≥4 → skip, right → short (2 ideas), wrong →
  full. Night: next lesson written while this one plays; every 2 lessons a checkpoint (FSRS cards due) + 6-min break
  (every 3rd: 15); stops 15 min before the deadline for the final review; course map (green/amber/red), cheat sheet
  (`~/.stiti/courses/*.md`), 9 am revision reminder. Only "stop/bas karo" ends a night (a slow writer doesn't).
- **FSRS:** `fsrs` 6.3.2 (MIT, pure Python); learning steps 10/60 min; wrong→Again, hint/conf≤2→Hard, right→Good,
  conf 5→Easy; `teach --revise`; exam mode = cards with predicted recall < 0.9 at exam time.
- Voice: "teach me X tonight", "ek raat mein X sikha do", "crash course on <book name>" (finds the file in
  Downloads/Documents/Desktop; "this book" = newest), "continue my course", "revise karna hai".

## D20: Alarms, reminders, timers — one structure (2026-11-10)
Research: `docs/research/alarms.md` (25 sources). Real bugs found in his data: a 9 AM alarm rang at 8:19 PM (Mac was
off), "kal 2 baje" parsed as 2 AM, reminders without text said "Wake up", alarms never actually rang.
- `life/alarms.py`: create / list / cancel (by #id, time, words, all) / move / snooze; RRULE recurrence (roz, weekdays,
  weekends, har somvar…; dateutil). Parser: bare 1–6 baje = PM unless wake/raat/subah; saade/sawa/paune/dedh/dhai,
  "7 bajne mein 10", Hindi hour words.
- Firing policy: alarm ≤10 min late rings, 10–30 min → spoken note, >30 → missed (never rung late); timer ≤2 min;
  reminder ≤12 h ("late:" note after 15 min); missed told once. Recurring re-arm immediately.
- Ring: tone + voice line through the echo-cancelled duplex (so "band karo" is heard over it), louder each 30 s round;
  "band karo / uth gaya / stop" dismiss, "5 minute aur / snooze" (default 9, max 3) without the wake word; auto-stop
  10 min; menubar "⏰ Stop alarm". Quiet hours 23–07: reminders are notification + Telegram, not spoken.
- Todos: remove ("remove X from my list"), clear (+ "restore my todos"), titles cleaned ("to call the bank" → "call the bank").
- Tests never touch real Apple Reminders (`STITI_EVENTKIT=off` in run_all).

## D21: Live internet info — news, tech, papers, placements, web (2026-11-10)
Research + measured latencies: `docs/research/live_info.md` (24 sources measured, 13 systems compared). Question → first streamed token 0.7–1.8 s cold, 0.5–0.95 s cached. Weak spot: general web search (keyless engines captcha-wall this IP); a free Brave/Tavily key would fix it.
- **Intent by rules, not the LLM** (`connectors/live.py: detect`): world / India / tech / AI / papers(field) /
  jobs(placements) / topic(product) / search(words) / fresh-fact questions ("who won the last F1 race?"). ~0.05 ms.
  The exemplar kNN domain is *not* used — it labelled "any new update on Gemini 3?" as `todo` (0.60) and "what's
  happening with placements?" as `todo` (0.77). Reminders/todos/his files/mail/people never trigger a fetch
  (lexical guard + the engine checks the words against `person`/`self` entities in the graph, so people from his
  life are never sent to a search engine). P2 turns and corrections never fetch.
- **Fetch in parallel, budgeted**: each source ≤ 2.5 s; the turn waits until 1.3 s if it already has ≥ 4 items, else
  ≤ 2.8 s; late sources keep running and fill the cache. Memory recall + briefing are built **while** sources load.
- **Cache** in process memory: 10 min news, 15 min jobs/reddit/search, 30 min papers; stale copy (< 6 h) beats
  nothing when a source fails. `live.warm()` pre-fills world/tech/AI/jobs in the background once per process.
- **Rank**: recency (half-life 8 h world … 72 h papers) + query-term coverage + popularity (HN points, HF upvotes,
  number of outlets in the Google News cluster) + the source's own order; near-duplicate headlines merge (other
  outlets listed as "also"); at most half the items from one source.
- **Briefing**: a `LIVE INFO` block appended to the compiled briefing (data first, answer rules after): ≤ 60 words,
  cover items 1–3, name sources, no URLs/lists, never invent, "want more?". Then `router.stream` → voice starts at
  the first clause. "haan / aur batao" within 5 min → next items, no refetch.
- **Degraded**: no LLM → the top 3 headlines are read out directly. Nothing fetched → she says she couldn't reach
  the internet instead of answering from memory as if it were news.
- **Generic tool path** (registry): `live_news(topic)`, `research_papers(field)`, `web_search(query)` (now the live
  search; the old ddgs `auto` call returned nothing), `web_read(url)` (Jina Reader → markitdown; public hosts only) —
  all read-only and `untrusted_output=True`.
- **Privacy**: only words from his sentence leave the Mac (never memory/profile); generic User-Agent
  `Stiti/0.1 (…github…)`, no email, no account.
