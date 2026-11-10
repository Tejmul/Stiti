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

## D22: Hinglish voice — Kokoro Hindi voice + code-switch phonemizer (2026-11-10)
Research + measurements: `docs/research/hinglish_voice.md` (18 TTS and 15 STT options compared). Roman Hinglish read
by `af_heart`/`en-us` sounded foreign (round-trip WER 68%).
- **TTS** (`voice/hinglish.py`): every word is tagged Hindi or English. A ~650-spelling Roman→Devanagari lexicon of
  everyday Hinglish words is used; words that are also English (to, do, main, me, hi, the…) follow the nearest
  clear word in the same clause (Hinglish puts English words into a Hindi sentence frame). Hindi runs go through
  espeak `hi` and English runs through `en-us`. The joined phonemes go to Kokoro's Hindi voice
  (`STITI_HI_VOICE`, default `hf_alpha`, `off` disables) with `is_phonemes=True`. Plain English (fewer than
  2 Hindi words and under a third of the line) returns None and keeps `af_heart` exactly as before.
- Measured on the M2: round-trip WER 68% → 26–32%. First clause has a median of ~245 ms, the same as English. G2P
  takes 0.06 ms because the two espeak backends are cached; phonemizer's default rebuilt a backend on every call
  (~70 ms). The model is unchanged, so RAM is unchanged.
- Known limits: English words in a Hinglish line keep a US accent. One reply can switch voice between an English
  chunk and a Hinglish chunk. Spellings outside the lexicon are read as English. Next steps: Lekhani (0.88 MB) for
  those spellings, then goonj-1-82M (Kokoro fine-tune with Indian-English voices).
- **STT unchanged for now.** Next: record real clips, then A/B Oriserve Hindi2Hinglish-Swift and add a Groq turbo
  escalation for low-confidence turns.


## D23: Web frontend in Next.js (static export), Memory page, memory receipts (2026-11-10)
Owner asked for the frontend in Next.js and for a page that shows what Stiti knows about him.
- **Next.js 16 (App Router, TypeScript) in `frontend/`, built with `output: "export"`** into `frontend/out/`. The
  Python server (`web/server.py`, inside Stiti.app) serves those files plus the API and WebSocket on 127.0.0.1:7317.
  No Node process runs at runtime, which matters on 8 GB RAM. Next is only a build tool, and the brain stays
  Python. Fonts come through `next/font` and are self-hosted at build time, so no Google request at runtime. GSAP
  and Lenis come from npm, not CDNs.
- **Dev:** `cd frontend && pnpm dev` (:3017) with `STITI_WEB_DEV=1 uv run stiti web`. `/api` is proxied by Next
  rewrites. The WebSocket goes straight to :7317, whose origin allow-list adds :3017 only with that env var.
- **Always on:** Stiti.app starts the web server in a thread (`web.serve_in_thread()`). Menu item "Open Stiti
  (chat + memory)".
- **Memory page** (`/memory`, data from `web/mind.py`): facts grouped by topic, people, rules and lessons, habits,
  14-day mood, searchable conversations, files and plans, plus a still SVG map of all of it. The owner can add a
  fact or forget one (retracted and kept in history). Owner edits to USER.md are synced in first so none are
  overwritten, then USER.md is re-rendered.
- **Memory receipts:** `Engine.last_used` records the memories, facts, files and lessons the brain handed the LLM.
  The chat shows them under each reply ("Remembered 4 things"), so the brain-not-LLM design is visible.

## D24: Privacy — conversations never shown in the UI; separate public build (2026-11-10)
Owner rule: "my chat history should not be on the website… that is my data."
- **No conversation text leaves the brain for a page.** `/api/moments` and the Memory page's conversation list are
  removed. Chat no longer preloads history (`hello` has no `history`), so each visit starts fresh.
  `Engine.last_used["memories"]` is now a count, so receipts say "4 recalled — kept private". Facts, files and rules
  can still be shown, since he can see and edit those in USER.md anyway.
- **Public site = `STITI_PUBLIC=1 pnpm build`.** A Turbopack alias swaps `@/components/private-pages` for stand-ins:
  `/chat` and `/memory` render "This part lives on your own Mac", and the chat/memory code is not in the bundle.
  Verified by grepping the build for API paths and personal data.
- **No personal data in code**, not even as placeholder examples. A sub-agent had used his employer's name in an
  example phrase; it's removed.

## D25: Persona + psychology — the brain picks HOW to reply, code enforces it (2026-11-11)
Owner: "it behaves like an AI model… asks me random things… Hinglish doesn't suit… I want it like JARVIS." Research:
`docs/research/jarvis_persona_psychology.md` (21 frameworks + JARVIS transcripts) and the reply rules of
`docs/research/conversation_turn_taking.md` §3.4. Kang et al. 2024 shows LLMs pick support strategies badly, so the
strategy is chosen **locally**; weak free models ignore prompt rules, so the shape is **enforced in code**.
- **`brain/strategy.py`** (rules, < 1 ms): CRISIS · REPAIR · DO · QUIET · SOLVE · LISTEN (+ reframe) · ANSWER · BANTER ·
  ACKNOWLEDGE, plus NUDGE (late night + an early event, once, then "As you wish."). Each carries a word cap, question
  yes/no, humour, memory callbacks, advice. Text-only mood switches to LISTEN only with words that show it (text mood
  is ~50% reliable); the voice mood can. Standing directives change the shape in code ("fewer questions" → no
  questions; "keep it short" → cap). Logged in `decisions` (`reply_strategy`, `reply_lang`); his next reaction labels
  it, so a Laya `reply_strategy` head can be calibrated later.
- **Language decided locally:** an active language directive wins; else Hinglish only if *this* message is clearly
  Hinglish (≥ 2 Hindi function words and ≥ 25% Hindi tokens); else English. Stiti's Hindi is feminine
  ("samajh gayi", "karungi"), fixed in code too.
- **Enforcement (`psych.enforce`, `psych.StreamLint`):** questions dropped when not allowed, generic closers
  ("anything else?", "how does that sound?") dropped from chat, banned tics (therapy-speak, cheerleading, "as an AI",
  "I can't see files"), promises ("from now on…") dropped unless a rule was saved this turn, advice dropped while
  listening, emojis / "!!" / masculine first-person Hindi fixed, cut at the cap. `StreamLint()` reads the turn's policy
  from the engine thread, so the voice loop needed no change.
- **Memory gating G1–G8 (`brain/gate.py`):** sim ≥ 0.45 or a shared person/project; free use when he asks; pain only
  if he raised it; only wins when he's low; nothing minor > 30 days; ≤ 1 unprompted callback/hour and never the same
  one within 7 days (`episodes.last_volunteered_at`, migration 008 — apply to the real DB too).
- **Local replies, no LLM:** crisis script with Tele-MANAS 14416 (P2), "Mm?" for "So.", "Nothing about X in my
  memory.", short goodbyes, "Okay, I'm here." after "Anything else?" + "not yet", silence for "ek sec / let me think"
  (`skip_turn`). Fast-path confirmations repeat the slot, then "Anything else?" (only after a completed action).
- **Compiler:** `[THIS TURN]` + `[REPLY RULES]` replace `CONTRACT` (no more "mirror their language mix"), plus a
  "you CAN read his ingested documents…" line and `[HIS WINS]` for reframes. New JARVIS SOUL default
  (`docs/persona/SOUL.jarvis.md` is the version for his own `~/.stiti/SOUL.md`).
- Cost: 0 new models, 0 MB RAM, < 1 ms strategy + ~2 ms gate. Tests: `tests/persona_eval.py` (the 15 dialogues of §3f,
  offline checks with a fake "bad" LLM + pass@3 on the real free router).

## D28: Personal emotion learning + opt-in local conversation recorder (2026-11-11)
Owner: "the emotion detection could be trained by using [the system we] build" — Stiti should learn HIS voice from
real use. Research: `docs/research/personal_emotion.md` (19 sources: emotion2vec/SUPERB frozen-feature heads,
PAPE/Sridhar-Busso personalization, IFN per-speaker normalization, SER test-time adaptation, cross-modal transfer +
co-training, complementary labels, noisy labels, active/continual learning, temperature scaling, Hindi/Hinglish
corpora, VoicePrivacy). No public Hinglish *speech* emotion corpus exists → his own data is the dataset.
- **Recorder (`learn/recorder.py`, migration 009), default OFF.** Menubar "Record our chats (local)" or
  `stiti recordings on|off|status|delete [--before DATE]|train`. Per committed voice turn: 16 kHz FLAC in
  `~/.stiti/recordings/YYYY-MM-DD/` (0700/0600) + a `voice_turns` row (transcript, speech/pause ms, turn state, STT
  confidence, prosody, generic prosody/emotion2vec reads, voice/text/fused mood, 768-d embedding). One hook line in
  `voice/loop.py` (background thread; a no-op when OFF). Retention 30 days / 2 GB (`recorder_days`,
  `recorder_max_gb`): expired audio is deleted, compact features + labels stay. P2 (crisis) turns are never kept.
  Never uploaded, never on a web page, not in backups. `delete` (no date) also removes the personal models.
- **Labels from his words, no forms (`learn/labels.py`):** first-person self-reports EN + Hinglish ("I'm so tired",
  "thak gaya hoon", "tension ho rahi hai") → +1.0 on the turn, +0.5 on ±2 neighbouring turns (≤3 min);
  corrections ("I'm not angry", "main udaas nahi hoon", "why do you think I'm sad") → NOT-label 1.0, and 0.7 on the
  previous turn when she had read that mood; text mood ≥0.8 agreeing with the generic voice read → pseudo 0.3;
  opt-in end-of-day check-in → 0.2 (`daily_checkin`, asking flow not built). Rebuilt nightly from scratch.
- **Personal heads (`learn/emotion_train.py`, nightly in `brain/sleep.py`):** numpy softmax regression + L2 +
  class-balanced weights + complementary-label loss for NOT-labels. `e2v`: embedding − his mean → PCA 32 whitened
  (a 768×768 covariance, not an SVD of all rows). `prosody`: [db, pitch, pitch SD, rate] z-scored on his data (works
  with emotion2vec OFF). Missing embeddings are filled by a **subprocess** that loads emotion2vec once and exits
  (measured: 11 s incl. load for a backlog, 1.2 GB peak RSS, returned on exit). Retrain from all kept features each
  night = full rehearsal, no forgetting.
- **Gate:** k-fold grouped by day, truth = human-sourced labels only (pseudo-labels agree with generic by
  construction), macro-F1. Activate only if Δ ≥ 0.05 over the generic predictor of the same turns AND over chance
  (1/K), more folds won than lost, ≥ 12 eval turns, ≥ 3 days. Otherwise (or if tonight's check fails) → generic.
  Temperature fitted on out-of-fold logits; live head abstains below max(0.5, 1/K + 0.2).
  Versioned `~/.stiti/models/personal_emotion/{kind}-vN.npz|json`, `active.json`, `metrics.jsonl`; runs logged in
  `consolidation_runs` (job `emotion_train`).
- **Live:** `emotion_model.classify()` now asks for the embedding in the same pass (no extra cost) and uses the
  active `e2v` head; `prosody.update_and_score()` uses the active `prosody` head; `personal.note/provenance` tells
  `fuse()` which reads are personal → a calibrated personal read is trusted at conf ≥ 0.55 (generic keeps 0.75);
  his denial still wins.
- Cost: 0 new models, live +~10 µs, nightly train ~1.4 s CPU / +~90 MB for 3,000 turns (both heads, 5 folds).
  Synthetic: activates at personal-signal 0.1 (F1 0.80 vs generic 0.56), stays generic at 0.06 (0.33 vs 0.56) and
  with no signal. Tests: `tests/emotion_learning_eval.py` 31/31.
