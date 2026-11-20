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

## D27: Hearing his words, speaking Indian English — STT glossary + cloud second opinion, goonj voice (2026-11-11)
Owner: it mishears him ("Tejmul" → "Tejmal", "Newton School" → "Newton's Club") and the Hinglish/Hindi voice is "not
suitable"; he wants English with an Indian accent people understand. Research: `docs/research/stt_tts_indian_english.md`
(22 STT engines, 18 TTS options, measured on this M2) + `docs/research/re_wispr_flow.md` ("What Stiti should copy").
Names are a **biasing** problem, not a model-size problem, so the brain feeds the ears; the model stays whisper-small q4.
- **Glossary from the brain (`voice/glossary.py`):** owner name/call_me, proper nouns in `USER.md` (by frequency),
  top graph entities, ingested document titles, + fixed words every user says (Stiti, todos, resume, placements, DSA,
  GitHub, cursor). Near-duplicates of a better-ranked term are dropped, so a misheard fact (USER.md had "Tejmal …
  Newton's Club of Technology") can't teach the wrong spelling. ≤ 40 terms / ~150 tokens, most important last,
  refreshed in the background every 5 min. P2 terms never go to the cloud.
- **Prompt (`stt.build_prompt`):** `Glossary: …` + the **previous utterance** of this conversation (Wispr
  `prev_asr_text`; same-utterance speculative passes are recognised by an audio fingerprint) + a short English block
  and a short Hinglish block, ordered by the **language prior** (previous utterance's language from
  `hinglish.language()`: romanized-Hindi word counters, 0 MB). Both blocks always stay: an English-only prompt
  *translates* Hinglish (63% WER). The previous utterance sits before the examples: at the end it cost 8.6 → 12.2% when
  he switched language (9.9% before the examples).
- **Snap to glossary:** consonant skeleton + phonetic folding (sch→sk, c→k, z→s, v→w…), ratio ≥ 0.8, same first sound,
  anchor word for multi-word names; never rewrites a dictionary word (macOS word list + simple stemming), a Hinglish
  lexicon word or another glossary term. < 0.1 ms.
- **Guards + escalation (`stt.decide`, `voice/stt_cloud.py`):** a transcript that repeats a clause ×3 or lists glossary
  terms is not speech; a run of prompt words is accepted only when Whisper is confident ("Hey Stiti" is in the prompt
  and is the most common thing he says). Unsure text (avg_logprob < −0.5), empty text while Silero heard ≥ 0.5 s of
  speech, Whisper's own no-speech filter firing on real speech (it dropped "Add buy milk to my todos") or an unsure prompt
  copy → the same audio + glossary prompt goes to **Groq whisper-large-v3** (not turbo: it ignored the glossary and
  echoed the prompt ×3). 700 ms cap; local text kept on timeout/error; the lane cools down 5 s (timeout) / 60 s (error
  or 429); the Groq connection is pre-warmed while local Whisper runs if it was idle > 4 min (a cold call took ~1 s).
- **Privacy switch:** audio leaves the Mac **only** on escalated turns (~14% on the research set) **of an active
  conversation** (60 s after a voice turn or wake greeting, `stt.mark_active()` from the engine): while she's asleep
  the mic still transcribes everything for the wake phrase (TV, other people) and none of that goes to the cloud.
  `STITI_STT_CLOUD=off` (env wins) or owner_profile `stt_cloud=off` keeps all audio local. Key from `.env` via the router's client, never
  printed; each call is counted in `llm_usage` (groq / whisper-large-v3).
- **Learning words from his corrections (`voice/vocab.py`, Wispr §3 adapted to voice):** "no, I said Tejmul",
  "it's Stiti, not City", "Tejmul, not Tejmal", "spell it T-E-J-M-U-L", "nahi, maine Tejmul bola", and explicit "add
  'Zonuly' to your vocabulary" / "remember the word X". Rules, < 1 ms, no LLM. The heard form comes from the correction
  ("not City") or from the closest-sounding span of his previous utterance. A correction only teaches a name or a rare
  word ("no, I said milk" and "call Rahul not Raju" are not word corrections). Saved to `~/.stiti/vocab.json` (local,
  readable, editable); the term goes to the top of the glossary immediately and the heard form becomes an exact
  rewrite before the fuzzy snap — unless it is an ordinary single word ("City" is never rewritten elsewhere). The
  engine answers with a fast-path "Got it — Tejmul, not Tejmal." (no LLM, not treated as an undo or a talk-style
  lesson).
- **Blips:** < 0.5 s of speech that Whisper wasn't sure about is ignored (`endpoint.Commit.text`), not answered with
  "Sorry?" (Wispr). Sure short words ("haan", "stop") still count.
- **Voice = goonj-1-82M** (Kokoro fine-tune trained on Indian-English personas, Apache-2.0), ONNX int8 (114 MB) in
  `~/.stiti/models/goonj/`, same `kokoro_onnx` runtime. `STITI_VOICE=goonj:<persona>` or owner_profile `voice`; default
  `goonj:en_priya` (female; the owner hasn't picked yet — `stiti voices`, `stiti voices try en_tara`, `stiti voices use
  en_tara`). **One voice per reply:** Hindi words still get Hindi phonemes (D22 lexicon) but the same persona speaks
  the whole line; the stock Hindi voices (`hf_alpha`) are never used. `STITI_HI_VOICE=off` = English phonemes only.
  Missing files → Kokoro `af_heart`. No hosted ONNX exists, so `stiti voices install` runs `scripts/goonj_export.py`
  in a throwaway `uv run --with kokoro torch …` env (or `--from <dir>` copies an existing export).
- **Measured (M2 8 GB, 110 synthetic Indian-accent clips, 5 voices, 20 dB SNR, end to end through `transcribe_ex`):**
  whisper-small q4 WER **12.4% → 7.7% local** (owner terms 64 → 81/90, silent drops 2 → 0, commands 5.1%, Hinglish
  16.2%) → **6.8% with the Groq second opinion** (82/90; 15/110 turns escalated, on those errors 28 → 15 words).
  STT p50 278 → 280 ms, p90 381 → 594 ms (escalated turns 576–1,100 ms: play the "hmm" filler).
  Voice: first clause p50 230 ms (af_heart) vs 223–233 ms (goonj), RSS 279 → 336–349 MB (+57–70 MB).
  Caveat: synthetic speech; re-run on his real voice (research Next steps). An early prompt draft that reused test
  sentences scored ~2 points better than it really was; the shipped example lines are not in the test set.
- Tests: `tests/stt_voice_eval.py` (144 checks: glossary, correction learning (parsing + next-turn effect + engine
  reply), snap cases + untouched words, Hinglish detection, context,
  prompt-copy, decision table, mocked Groq incl. timeout/echo/privacy switch, blips, goonj selection/fallback/one voice,
  live Groq call when a key exists, WER regression on the research clips when present).

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

## D29: Feels-human real time — preemptive reply, pre-warm, ● ◐ ○ markers, media pause (2026-11-11)
Research: `docs/research/conversation_turn_taking.md` §3–§4 (LiveKit preemptive generation, Pipecat ● ◐ ○ +
`SpeculationGate`), `elevenlabs_conversation_re.md` §4 item 10 (speculative turn), `re_elevenlabs_live.md` (EL speaks
≈ 0.2 s after it commits → the reply is already in flight), `re_wispr_flow.md` (GET /warmup on the first audio chunk;
`shouldPauseAudio`). Code: `voice/realtime.py`, `voice/media.py`, `brain/turnmark.py`, `db.Held`, `engine.turn(speculative=)`.
- **Preemptive reply.** `TurnTaker` emits `speculate` the moment the early transcript (160 ms + STT) reads *finished*
  — before the commit lands (0 s after it when Smart Turn is sure, up to `min_delay` = 1.0 s when it isn't). The engine
  turn starts then: the LLM streams into a **buffer, nothing is played**. Commit with the same words → the buffer goes
  to the Speaker at once and the stream continues live. He goes on (`unspeculate`) or the commit goes elsewhere (bye,
  backchannel, wake, a different text) → dropped: stream aborted, DB rolled back, engine state restored. So it can
  never cause a false reply: playback still waits for the same commit as before.
- **Only plain chat is speculated.** `engine.spec_block()` (pure checks, no writes) refuses fast paths, actions,
  flows (WOOP, chunker, onboarding, pending "haan"), corrections, live/web, tools, music, holds, goodbyes; the engine
  re-checks the domain (chat/memory only) and refuses again before the LLM. A fast path is never run early, so there is
  nothing to undo (the continuation-grace `undo_last` path stays as it was).
- **No trace from a discarded speculation.** `engine.turn(speculative=True)` runs inside `db.Held` — one transaction
  on its own connection; every `q()/one()` of that thread goes to it — plus a snapshot of the engine state.
  `speculation_commit()` makes it a normal turn (same rows as without speculation); `speculation_discard()` rolls back
  episodes, turn, decisions, lesson scores, facts and restores `last_*`. USER.md/LESSONS.md are never touched by a
  speculation (no mdsync, no lesson/directive paths). LLM quota rows are written outside it (`db.unheld`) so rate
  limits stay honest. Budget: one speculation per pause, ≤ 6 dropped per minute (Groq free 30 RPM).
- **Pre-warm.** His speech starting while she's awake → `router.warm()`: de-duplicated (one per 20 s, never two at
  once), one `GET /models` on the first voice provider so its TLS connection is hot when the turn lands.
- **● ◐ ○ markers (voice only).** `[TURN MARKER]` rules at the end of the brief (compiler `markers=True`); the engine
  strips the marker from the stream (`MarkerStream`, split-anywhere safe, lookalike glyphs, "[●]") and from the stored
  reply, so it never reaches speech, memory, history, USER/LESSONS or the web. ◐/○ → the LLM is stopped, nothing is
  said, the fragment episode is kept out of recall, the loop keeps his words as the TurnTaker prefix (joined to what
  he says next) and says "Mm-hm?" after 5 s (◐) / 10 s (○). Missing/garbled → ●. Never for questions ("?"), tools,
  the web, or a turn right after a ◐ (a weak model that always answers ◐ can't silence her).
- **Media pause.** On wake, Spotify / Apple Music that is *actually playing* is paused (AppleScript `is running` first
  — never launches an app); on sleep (+1 s for the chime) or 20 s idle, only what she paused is resumed, and only if
  it's still paused (he started something himself → left alone). `owner_profile media_pause=on|off` (default on).
- **Measured (real Groq `qwen3.8-27b`, throwaway DB, 10 chat turns, speculation 0.64 s before the commit = the
  simulated min_delay case):** commit → first reply text **median 530 → 0 ms** (mean 488 → 71 ms; median gain per
  turn 378 ms). Simulated with the TurnTaker: unsure audio (waits min_delay) ≈ −380 ms; confident audio (commits as
  soon as the transcript is in) ≈ −35 ms — never slower. Markers: 9/9 complete sentences got ● (0 false drops; the
  question got no rules by design), 4/4 LLM-judged fragments got ◐/○.
- **Cost:** 0 new models, 0 MB RAM; a held transaction costs 3–7 ms to open (off the critical path); a dropped
  speculation costs one free LLM request. loop.py: 7 one-line call sites. Tests: `tests/realtime_eval.py`.

## D26: Desktop overlay — native Core Animation pill + AppKit cards (2026-11-11)
Owner: "when I say 'Hey Stiti' some animation should come on my desktop… when I ask what's on my to-do list it should
show me 'you have these to complete'." Research + prototypes: `docs/research/desktop_overlay.md` (16 references,
Core Animation vs WKWebView measured on the M2); behaviour tuned from `docs/research/re_wispr_flow.md` §1.
- **Native, in the rumps process (`src/stiti/overlay/`), no WebKit.** A borderless non-activating `NSPanel` at status
  level (set *after* `setFloatingPanel`), all Spaces + full-screen auxiliary, kept out of screen sharing, never key.
  White liquid glass (`NSGlassEffectView`, macOS 26) → `NSVisualEffectView` → solid paper under Reduce Transparency.
- **Pill** top-centre, 8 pt under the menu bar, on the display with the pointer: 7 navy/blue/sky dots shimmer while
  idle/listening, swell with his mic level (adaptive dB floor, 40 ms blocks, 150 ms average, slew 1.6/s), ripple
  while thinking ("Checking calendar" label for slow actions), swell with her voice, fade on sleep. 30 fps cap; the
  Python timer runs only while listening/speaking. Click-through while listening; click = stop her while she
  thinks/speaks. Reduce Motion = fades + brightness only.
- **Cards** from `Engine.last_card` (the brain's data, never the LLM's words; titles/items only, no captions — D24):
  todos / reminders / news drop out of the pill; `todo_added`/`reminder_set` widen the pill into a one-line ✓. Click a
  to-do = tick it (optimistic, written in a worker thread, reverted on failure). Closes on Esc, click elsewhere, when
  she sleeps, or 4 s + 1.2 s/row (≤ 15 s) after her speech ends (paused on hover).
- **API** `overlay.set_state / level / show_card / hide_card / speech_ended` is thread-safe and a no-op until
  `init()` runs on the main thread, so `stiti voice` in a terminal and the tests are unchanged. Menu toggle "Show
  Stiti on screen" → `owner_profile` `overlay=on/off` (default on).
- Cost (measured, display locked so WindowServer numbers are not valid): ~0.5–2 % of one core in our process;
  +5 MB for the pill and +2 MB with a card open in a rumps-like process, plateauing at ~+16 MB after hundreds of cards
  (font/symbol caches, no leak). Tests: `tests/overlay_eval.py`. Not verified yet: on-screen look with the display on,
  full-screen video (status vs `STITI_OVERLAY_LEVEL=screensaver`), notch Macs.

## D33: One lesson at a time — the tutor lock is taken at launch, not after loading (2026-11-11)

**Bug:** "while teaching… it was breaking in the middle… loading and taking time… multiple voices coming and corrupting."
"Can you teach me… lexical analysis in compiler design… using whiteboard?" said in three breaths ran three turns; each
launched a lesson (the reply was dropped as "you were still talking", the launch was not). The lesson only wrote
`tutor.lock` after loading its models, so all three saw no lock: three whiteboards, three voices, each hearing the
others as the learner ("You (voice): Chalo today, lexical analysis…"), three model loads on 8 GB, planner calls failing.

- `launch()` writes the lock with the child's pid the moment it spawns it; the lesson refuses to start if a different
  live pid holds it. Main Stiti also goes quiet from that moment (it already yields while `tutor_active()`).
- "Can you teach me?" with no topic asks "Sure! What should I teach you?"; his next short line (90 s) is the topic,
  "never mind" cancels. Never speculated.
- Lesson ears run whisper on the voice loop's single STT thread (a second thread loading MLX at the same time failed:
  "There is no Stream(cpu, 0) in current thread"); a bad segment can't kill the ears thread.
- "without my cloud brain" lines → "Good one. I've parked it in the corner…". Tests: `tests/tutor_launch_eval.py` (15).
## D32: Two voices — one for English, one for Hinglish; speed + say-as (2026-11-11)

**Owner:** goonj en_priya sounded "like an old woman"; wants sweet + energetic; picked Kokoro **af_jessica** (American)
from a 6-voice lineup; then: "there should be two voices: one for Hinglish and another for English."

- Measured 20 female voices on one line (pitch, pitch spread, Whisper round-trip, synth time): all equally clear
  (~4% WER, mostly "4" vs "four"); priya's pitch spread is 4.6 semitones vs ~2.7 for the rest (reads as older);
  brightest: goonj en_nisha 326 Hz, en_ananya 305 Hz, hi_meera 281 Hz. Every American/British Kokoro voice says
  "Tej" as "Tedge".
- `voice` (English lines) + optional `voice_hi` (lines where `hinglish.phonemize` finds 2+ Hindi words). One Kokoro
  model per model file, shared, so two stock voices cost no extra RAM; a goonj + stock pair adds ~115 MB.
- `voice_speed` (0.8–1.3, moods scale it) and `say_as` respellings ({"Tej": "Tayj"}) live in the local owner_profile —
  never in code — and apply to stock Kokoro voices only (goonj already says Indian names right).
- CLI: `stiti voices use-hi <voice|off>`, `stiti voices speed 1.05`, `stiti voices say-as <word> <how>`. Fixed: `try` /
  `use` treated every non-`af_` voice as a goonj persona (hf_beta broke). Tests: `tests/voice_pick_eval.py` (21).

## D34: Reply in the language he speaks — English · Hinglish · Hindi · Telugu · Tenglish (2026-11-11)

**Ask:** mirror his language turn by turn; "just talk in English, don't use any other language" locks it; saying the
language switches it. Research: `docs/research/language_switching.md` (11 options, Whisper LID measured on the M2).

- Hearing: Whisper-tiny language ID (32 ms), pooled into his three base languages → Telugu turns are transcribed as
  Telugu (Groq large-v3 `language=te`, else local) instead of being translated into English by the English-pinned STT.
- Deciding (local, < 1 ms, `brain/lang.py`): lock › "talk in X" › this message's language › previous one for "ok/bye".
  Roman Hindi → Hinglish (casual), Devanagari → Hindi. Only an explicit lock is saved (`Language lock: …`); one-off
  "talk in English" and confusion no longer create forever-rules (the old D25 auto-rule is gone), and old-style
  language rules are kept out of the LLM's MUST lines.
- Speaking: script routing — Telugu → `voice_te` (owner: hf_alpha), Hindi/Hinglish → `voice_hi` (hf_alpha), English →
  `voice` (af_jessica); Telugu/Tenglish phonemes via espeak `te` + `en-us` (`voice/telugu.py`).
- Tests: `tests/lang_switch_eval.py` (50, incl. his live flow); persona/conversation tests updated to the new rules.
## D31: She talks like a person — machine-talk cut in code, SOUL fits the briefing (2026-11-11)

**Complaint:** "Why is it reporting all the errors and technical terms while talking?" Real replies: "The voice model is
likely glitching or the audio stream is corrupted. I cannot control the synthesis engine…", "Functioning within normal
parameters. No errors to report.", "That is a word I do not recognize.", "My thinking brain (cloud LLM) is offline."

- **Cause 1 — SOUL:** "Stiti is Tejmul's own JARVIS … British-butler understatement" + "never claim feelings" made the
  model play a machine. **Cause 2 — truncation:** the briefing keeps only 1400 chars of SOUL; ours was ~1700, so the
  whole "Never" section was cut every turn. New SOUL (live + `docs/persona/SOUL.jarvis.md` + `DEFAULT_SOUL`): a friend
  who sounds like a person, "Sounds human" rules first, 1386 chars. No bare "Done." example (the model copied it).
- **In code, for any LLM:** `psych.MACHINE` drops sentences where she describes HERSELF as software (my model/engine/
  servers, normal parameters, synthesis engine, "word I do not recognize", rate-limited…) in `enforce`, `lint` and
  `StreamLint`. His tech talk ("Postgres is a database", "status code 404", "your API key") is untouched — 12/12 kept.
  If nothing human is left: `human_fallback` ("Good, thanks — quiet day on my side." / "Sorry, my voice is acting up a
  bit." / "Sorry, I didn't catch that."); the voice loop speaks the clean reply if every streamed piece was cut.
  A lone "Done." after a non-action reply is dropped.
- Fixed lines: offline → "My head's a bit foggy right now…"; Telegram/web errors no longer read out exception names;
  mail no longer mentions `.env`. Tests: `tests/human_talk_eval.py` (48, incl. 3 live-LLM lines).

## D35: Whole sentences — no missing words when she speaks (2026-11-11)

**Complaint:** "some words are getting missed in between, so people can't understand what you are talking about."
Measured on the streaming path (LLM deltas → ClauseChunker → StreamLint): "If you're tired, try to rest for ten minutes,
then start the DSA sheet" was spoken as "If you're tired," (the rest, judged alone, looked like advice); the word cap cut
"the placement test is tomorrow at" before "ten"; under the 14-word DO cap "Haan, kal subah chhe baje ka alarm" lost
"laga diya hai…".

- A sentence is judged when it STARTS; once started it is spoken whole. Machine-talk / banned words in the rest end the
  sentence there; a dropped start drops all of it; a sentence dropped after she has spoken ends the reply (later ones
  may lean on it). The cap stops only at sentence ends; a sentence may finish up to 1.6× the cap, then ends at a comma.
- `enforce()` (what's saved) judges sentence 1 by its first clause like the voice, so saved == spoken.
- No capitals inside sentences ("Laga", "Ten"). "I hear your frustration" joins the banned therapy-speak.
- Tests: `tests/whole_sentence_eval.py` (13).
## D30: Cards play the change — added / done / cancelled animate on the list (2026-11-11)

**Ask:** "I tell it a to-do → it's noted. I say 'okay, it has been done' → the card appears, the item is struck, and it
goes away from the list. Same for everything else."

- **What changed comes from the brain, not the reply text.** Fast-path writers call `cards.note(op, kind, ids)`
  (to-do added / done / removed / cleared / restored; reminder set / cancelled / moved); the engine clears it at the
  start of a turn and passes it to `cards.for_turn(event=)`. Cards are now always the whole list with a `focus`
  (`todo_added` / `reminder_set` one-line pill confirmations are no longer produced; the pill path still exists).
- **Timeline is pure** (`overlay/model.choreography` + `collapse`, unit-tested): rows rise in (45 ms stagger, ≤ 250 ms);
  an arriving row gets a blue wash + icon bounce, settles at 1.6 s; a leaving row gets ✓ / ✕ / slashed bell and a
  strike line drawn left → right at 0.55 s, holds 0.75 s, then folds (300 ms) while rows below close up, the card
  shortens from the bottom and the eyebrow counts down ("All clear" when the last one goes). All within ~1.9 s, i.e.
  while she is still saying it. Reduce Motion: no slides; strike + removal still happen.
- **"It's done" with no task named** resolves to the task he just added / was just shown (15 min), else the only open
  one, else she asks "Which one is done — …?" and shows the list. Guard: "I'm done" / "I am so done" is about HIM and
  never ticks a to-do; a bare "done" only counts right after a to-do was in play.
- Overlay panels stay excluded from screen capture; only `overlay.demo --shots` (fake data) lifts that, to check frames.
- Tests: `tests/card_motion_eval.py` (42). Verified visually with `python -m stiti.overlay.demo --motion --shots DIR`.

## D36: She never says the same thing twice in one conversation (2026-11-14)
**Problem (his real morning):** "what do you know about me?" → school, projects, sport. "Okay, what else?" → the same
school, projects, sport + one new line. "And what else?" → again. Causes: no record of what she'd already said; every
turn got the same top profile lines; RECENT cut her own replies to 160 chars; "what else" was not a request of its own;
cut-off half sentences sat in RECENT twice. Research: `docs/research/no_repeat.md` (16 approaches; all that fit keep
the state in code — grounding / information-state, Rasa slots, MMR, Alexa paging; sampling penalties only work inside
one reply and Groq doesn't support them).
- **Ledger** (`brain/norepeat.py`, immutable, on the Engine): the sentences she said in the last 20 min + their content
  words. Only what he HEARD counts (barge-in → `truncate_last_reply` replaces it).
- **MORE** (regex, en / Hinglish / Telugu: "what else", "is there some other thing", "aur batao", "inka cheppu"), only
  within 10 min of an informational answer: recall uses the PREVIOUS question (not the words "what else"); the
  compiler drops every profile / fact / memory line she already covered and lists the next ≤ 3 unsaid ones as
  [NOT SAID YET] (a weak model told "only new things" otherwise just says "that's all"). Nothing unsaid left →
  honest line from the brain, no LLM call, and a different wording the 2nd / 3rd time.
- **Filter in code** (StreamLint + `enforce`): a sentence whose ≥ 3 content words were all said already is dropped.
  Same question asked again, nothing new → the same answer stays (that's right). REPEAT ("say that again", "kya bola")
  and REPAIR turns switch it off. Regex + sets: microseconds, no embedding on the hot path.
- **RECENT**: last 10 episodes, her replies ≤ 480 chars, his ≤ 240; cut-off fragments collapsed; this conversation's
  own turns no longer come back as "memories". RECENT is trimmed (oldest first, last 2 exchanges kept) for the budget.
- **Fragments**: a half sentence joined into the next one is marked importance 1 (out of recall), like `_incomplete`.
- Verified: `tests/no_repeat_eval.py` (60); live Groq run on a made-up 11-line profile: 6 → 3 new → 3 new → 1 new →
  honest line, zero repeats. NOT verified on the mic yet.

## D38: She learns from normal conversation — night extraction that works, real-time life updates, honest "noted" (2026-11-14)
**Problem (measured on his real brain, 4 days, ~270 episodes):** 12 current facts, all from the day-one resume import;
the two night runs extracted `{}` and `{"added": 1}` (a mishearing, later retracted); 2 entities; 1 lesson.
"Actually, I left MVRX Labs… I left in September" → "Noted. I will mark that down." — nothing was written.
Research: `docs/research/learn_from_chat.md` (13 systems: Mem0, Graphiti, MemGPT, A-MEM, LangMem, ChatGPT memory…).

**Root causes found** (the old extractor is not dead: on a clean made-up English day it finds ~8 facts — it fails at
everything around that)
1. *Nothing in the turn.* Only keythings (likes/diet) wrote facts live; `REMEMBER_RX` replied "Noted — I'll remember
   that." and wrote nothing; the LLM said "noted" freely (no rule against it, unlike "Added …" / "from now on").
2. *The night job mostly didn't run* (Mac asleep at night; catch-up only once a day — 11-12/11-13 had no run), and the
   MVRX turn (ep 285/286) was after the last watermark anyway.
3. *His real windows had few durable statements, and the extractor saw them with no context*: of 127 lines sent, most
   were questions, commands, wake words, Telugu/garbled STT; no Stiti line, so short answers meant nothing; STT half
   sentences went twice.
4. *Prompt/schema:* free-form JSON (no strict schema), template showed `"confidence":0.0` next to a `< 0.5` drop rule,
   `object_is_entity` defaulted to true (junk "thing" entities), no examples, "skip … questions" with nothing about
   what TO keep (relations, changes), and no view of existing facts — so "I left X" could never end "intern at X"
   (resume facts are all predicate `noted`, no object entity).
5. *Validation:* facts with no valid evidence id were pinned to the batch's last episode (not rejected); a `null`
   confidence would crash the run; one bad JSON answer failed the whole run and the watermark never moved.
6. *Directives:* free supersession keys → "Switch to Hindi" and "Switch to English" both active forever; one-off
   commands ("shut up… get deactivated") became boundaries.
7. *Standing profile:* top-10 self facts by confidence → 0.95 resume lines always won; rebuilt only at night; an empty
   rebuild left the stale cache in place.

**Fixes**
- **Night/nap extraction** (`brain/sleep.py`): his statement sentences only (questions / greetings / commands / cut-off
  fragments / already-extracted dropped locally, P2 never selected), each with Stiti's previous reply as context;
  KNOWN FACTS (current, P≤1, his newest + those about entities named) with ids → the model returns `ends`
  (`wrong=true` → retracted, else `valid` closed). Strict JSON schema (`router.complete(schema=…)`, new `extract`
  chain: gpt-oss-120b → Groq's other models, each with its own TPM → weaker ones). Validation in code: evidence must be
  his line ids, confidence ≥ 0.6, a subject/object word must appear in what he said, nothing "about Stiti", a tie
  (works_at, plays…) whose sentence says it ended is rejected ("contradicted"), entities must be named in his lines.
  "X is Ravi's sister" text → `X —sister_of→ owner` whatever direction the model used; relation placeholders
  ("Ravi's sister") never fuzzy-merge. Directives: canonical keys (brevity / questions / call_me…), language rules and
  `standing=false` skipped (D34 decides language per turn). Bad batch → skipped and counted, run continues; no
  provider → wait 61 s once, then `partial` with the watermark. Rejection counts + a few examples in the stats.
- **Writes with temporal validity** (`brain/factstore.py`, shared): add = merge on same (subj, pred, obj) or ≥ 0.92
  embedding similarity; functional predicates end the old value (no overlapping ranges, never an empty range);
  `close_ties` ends present-tense facts about X but keeps past-tense history ("was an intern at X, Aug–Sep").
- **Real time** (`brain/lifeupdate.py`, deterministic, in the turn): I left / quit X, my internship at X is over,
  maine X chhod diya · I joined / work at / intern at X (as role) · I moved to / live in X · my sister (Riya) moved to X ·
  Riya is my sister · I don't play X anymore / I quit smoking · remember that … / "…, yaad rakhna" · actually it's X,
  not Y (retract + restate, entity renamed). Month phrases date it ("in September" → valid from 1 Sep). Hypotheticals
  ("if I left…"), questions, "remember to …" and reminder/todo/alarm turns are skipped. Saved → fast reply "Got it —
  updated: you left MVRX Labs (September)." (no LLM), episode importance 7, standing profile + USER.md re-rendered in a
  background thread. A life-update/correction the patterns can't parse ("actually…", "change it", job/moved words) →
  the same extractor for that one turn, in a background thread after the reply (`background_smart`, never the voice
  chain's model; P2 never).
- **Honesty** (`psych.MEMORY_CLAIM_RX`, `Strategy.allow_memory_claim`): "noted / I'll remember / mark that down /
  updated / yaad rakh liya" is cut (enforce + StreamLint, also mid-sentence) unless this turn really saved something;
  the brief says "Nothing was saved to memory this turn" or lists what was. "I haven't saved that yet" is not a claim.
  The hollow REMEMBER fast path is gone. A life update is no longer taken as a talk-style lesson / correction.
- **Standing profile:** newest self facts first, then surest, then his people, then rules (≤ 900 chars, whole lines);
  rebuilt after every real-time save and after each nap/night; deleted when empty.
- **Night job runs and says so** (`app.py`): night run tracked as its own `consolidation_runs` row (`job='night'`);
  plus a **nap** (extract → profile → USER.md, no backup) once ≥ 6 new lines are pending and he's been quiet 10 min, at
  most every 2 h; one job at a time; each step isolated (a failing step doesn't stop the rest); one `[sleep]` log line
  with counts (lines, facts +added =confirmed ~superseded, ended, corrected, entities, mentions, directives, rejected,
  profile lines). Fixed: `busy` was undefined in the scheduler until the first 60-s pass; GRAPH_REPORT crashed on an
  empty/ended range.

**Numbers**
- Selection on his real brain (read-only dry run, no LLM): 127 lines would have been sent before → 72 now (+ 66 with
  her reply as context); 71 skipped locally (questions, greetings, commands, fragments). Real-time patterns would have
  caught the MVRX turn and "Pugal is my son"; the to-do/alarm turns are not touched.
- Live check (made-up 15-line day with a resume-style "intern at Ledgerly" + "hockey player", real Groq gpt-oss-120b,
  ~3.2k tokens, ~5 s): **new** → 10 facts (Meera is his sister / works at Finlo / moving to Pune, "left Ledgerly in
  September 2026", full-time on Tilecraft, Arjun is his friend, badminton, no longer hockey, biryani, no spicy food
  after 9), **2 ended** (the internship + "hockey player"), 1 rule, "Switch to Hindi" skipped, 0 junk. **Old** prompt on
  the same lines → 8 facts, **0 ended** (profile still said "intern at Ledgerly" and "hockey player"), no sister
  relation, "Switch to Hindi for replies" saved as a forever-rule, 3 junk "thing" entities. When Groq's TPM is used up
  the chain falls to GLM-4.7-Flash, which is clearly weaker (missed relations/ends in one run) — the code-side
  safety net (`left`/`stopped` facts close ties, contradiction check) covers the worst of it.

**Tests:** `tests/learn_from_chat_eval.py` (55, fake router → offline/deterministic): chat → facts/entities/mentions/
rule; questions/commands/greetings/fragments/P2 not sent; Stiti's line, invented ids and low confidence rejected;
"left Ledgerly" ends the internship (kept in history); repeat merged; standing profile + USER.md + GRAPH_REPORT;
real-time "I left Orbitly" (dated September, no LLM), "I don't play hockey anymore" (not a lesson), "Pugal is my son",
"remember that…", no hollow "noted" (complete + stream), background extraction for an unparsed update, hypotheticals /
questions write nothing. Existing suites re-run green: learning, memory, mdsync, persona, honest_actions, no_repeat,
intent, conversation, human_talk, whole_sentence, lang_switch, turn, realtime, card_motion, web, speed, proactive,
emotion_learning, recall.

**NOT verified:** on his mic/real conversations (only made-up data went to the LLM); the nap trigger inside the
running Stiti.app; Telugu/Hindi-script lines through the extractor; the existing junk in his real brain (e.g. both
"Switch to Hindi" and "Switch to English" active, "I said shut up…" as a boundary) is left as it is — his call.

## D37: Ask me questions — a get-to-know-you round of 10, learned by the brain, no LLM (2026-11-14)
**Ask:** "for knowing me you have to ask questions — ask me 10 questions when I say to ask, which gathers info about
what I want, ambitions, shows, animes I see, characters I like, etc." Research basis: `research_notes/Key things to
know intake/intake_research.md` §5 (OARS reflections, summary read-back, easy → personal order, skip / pause), §7
(consent, P2 for worries, no re-ask of a skipped sensitive item for 30 days), §9.4 (drip-feed, not one long form).
- **`brain/askme.py`** replaces the never-wired `brain/intake.py` (it imported a `guide.py` that never existed; deleted).
  The old 10-Q `onboarding.py` stays as the first intro (name, people, routine…); this is the open-ended follow-up.
- **Bank: 48 questions, 21 categories** (dreams, this month / year, career, anime, favourite characters + why, shows &
  movies, music, books, games, sports, food, people he admires, relaxing, what annoys him, what drives him, values,
  worries / fears, a perfect day, places, learning, how to talk to him). Each has a key, a fact template, a
  second-person "said" template, and optionally an entity kind for the names in it or a directive template.
- **Triggers** (en / Hinglish / Telugu): "ask me questions / something", "get to know me better", "know me better",
  "quiz me about myself", "mujhse sawaal pucho", "kuch pucho mujhse", "nannu prashnalu adugu". Not: "ask me later",
  "can you ask Priya", "ask me questions about python", "quiz me on …". Plain "get to know me" stays the onboarding
  intro until that's done, then it means this.
- **A round** = 10 unanswered questions, round-robin over the categories from where the last round stopped (fun and
  deep interleaved, worries last). Again later → the next 10. All answered → the skipped ones, then the oldest
  answers come back as "Quick check — you're into X. Still the same?" ("yes" refreshes it, a new answer supersedes,
  "not anymore" ends it). One question per turn, a short reflection of his answer from templates ("Vinland Saga and
  One Piece — good taste."), "Halfway there." / "Last one.", and a one-line read-back at the end ("That's the round.
  Got it — you're into …, you want to build …, and you like Zoro for his loyalty."). "skip / pass / nothing / pata
  nahi" skip; "bas / later / stop / that's it" pause (the next "ask me questions" picks up the same question); "why?"
  explains; a bare "ok" gets one nudge; a command mid-round ("set an alarm…") pauses the round and runs; "bye" says
  goodbye and keeps the round. Answers: fillers stripped ("umm", "I think", "mostly"), his words kept.
- **Storage (the learning):** his words → episode importance 8 (+ P2 for worries); one current self-fact per question
  (`about_<key>`, functional, origin `ask_me`, embedded; the old answer's interval is closed and `invalidated_by`
  set — history kept, never duplicated); names (anime, characters, shows, artists, places…) → `topic` / `place`
  entities, each with its own fact linked to him (`in_<key>`), plus "Zoro is a character in One Piece"; directives
  for how to talk to him / boundaries (`ask_<key>` supersession keys). After every answer the standing profile and
  USER.md are rebuilt, so the next LLM turn already knows it, and a pause loses nothing.
- **`sleep.standing_profile()`**: directives are now always kept and facts fill the remaining room (1,000 chars,
  up to 14 facts) — before, ten facts came first and a 700-char cut could drop every directive, i.e. his boundaries.
- Keythings capture and the "she was cut off / too long" lesson inference are skipped on round answers (no double
  facts, no fake lessons from "what annoys you?"); the undo path too. Spec: the trigger and every mid-round turn are
  never speculative (`spec_block`).
- Tests: `tests/ask_me_eval.py` (129): triggers, bank, cleanup, a full engine round with zero LLM calls, skip / pause
  / resume, supersede, P2, profile + USER.md, round two all new, refresh. Engine turn ≈ 50–200 ms on the M2.
  NOT verified on the mic yet.

## D39: Anticipating him — weather, brief, meeting heads-up, reminders that don't give up (2026-11-14)
**Ask:** Jarvis moments where she speaks first, without being annoying. Research reused (not redone):
`docs/research/alarms.md` §2c/§2e (nag policy, ring caps, presence → channel, "in a call → banner only"),
`docs/research/live_info.md` §5 (Open-Meteo is the easy keyless weather), `research_notes/…/productivity_and_psychology.md`
§6 (budgeted, breakpoint-timed nudges; over-intervention is the failure mode), public-apis list → Open-Meteo.
- **Weather** (`connectors/weather.py`): Open-Meteo geocoding (cached forever on disk, `~/.stiti/cache/geo.json`) +
  forecast (current + today/tomorrow high/low/rain %, cached 30 min in memory, 1.5 s timeout per call, a failed refresh
  answers from a copy < 6 h old, offline → None). Fast path in `Engine.turn` before live news, no LLM: "what's the
  weather / mausam kaisa hai / will it rain today / kal baarish hogi / bahar kitni garmi hai / weather in Porto" →
  "It's 24 and sunny in Lisbon, up to 31 later, no rain." / "Probably not — only 10% chance of rain in Lisbon today."
  "Later" is judged on the city's own clock. Cold cache → the "Let me look that up." ack. Its regex is in `spec_block`.
  **City is never hard-coded:** owner_profile `city` (by voice: "my city is …", "I live in …", "main … mein rehta hoon";
  checked with the geocoder) → `STITI_CITY` → the timezone's city (said out loud, plus a one-time "tell me your city").
  Only the city name leaves the Mac. **Licence (checked on Open-Meteo's own README, 2026-11-14; the /terms page
  reset the connection):** free for non-commercial use, no key, fair use — contact them above 10,000 requests/day
  (Stiti makes ~50/day); data CC BY 4.0 (credit Open-Meteo where data is displayed); server code AGPLv3 (not used).
- **Morning brief** (`life/brief.py`, same gates: once a day, nudge budget): ≤ 3 sentences — greeting + cached
  weather one-liner · next 1–2 timed calendar events + to-do / reminder count (or "first up, …") · ONE cached headline
  (`live.cached_headline`, else a habit). Nothing waits on the network: the app refreshes weather every 30 min
  (05–23 h) and `live.warm()` fills news. Calendar is read only if access was already granted
  (`eventkit.events_quiet` never prompts — from a terminal the prompt blocked 60 s). Low energy → "Just one thing
  matters today: …", no news.
- **Meeting heads-up** (`proactive.meeting_headsups`): "Heads-up — Design review in 10 minutes." once per event
  (dedupe key in `nudges`), window 10.5 → 1 min before (says the real minutes if caught late), all-day skipped.
  Facts (meeting / deadline) no longer go through the bandit coin-flip — only his "don't remind me about meetings"
  stops them. Same `_deliver` path as reminders; `_deliver` now gives the banner only during a whiteboard lesson or a
  call (`proactive.in_call`: Zoom's in-meeting `CptHost` process or FaceTime frontmost — heuristic).
- **Reminders that don't give up** (`alarms.nag_*`, migration 010 `reminder_nags`): delivered and not acknowledged →
  again at +2 min ("Reminder again: …"), then +5 min ("Last nudge on this one — …") = 3 in all; "important / zaroor /
  must / don't let me forget" (flag saved at creation) → every 10 min, 3 more ("This one's important — …"). Ack =
  "ok / got it / done / haan / theek hai / ho gaya / thanks" (≤ 6 words): voice hook in the loop (no wake word for
  90 s after she said it, 5 min while awake), any typed channel through the engine, the menu "Stop alarm" item, or
  ticking it in Apple Reminders. Repeats wait (uncounted) while he's away or in quiet hours, and while she's speaking
  (max 2 min); dropped after 3 h. Logged per reminder: channel of every delivery, ack channel, ack latency (Laya data).
- **Ring caps split:** alarm 10 min, timer 5 min (`RING_MAX_S` dict, `ring_limit_s`); the ring log line now has
  ack latency + channel.
- Tests: `tests/anticipate_eval.py` (121; fake HTTP, fake calendar, fake clock — no real network); alarms 44,
  proactive, conversation 12, realtime 77, live 91, overlay 78, no_repeat 60, honest 32, human_talk 45, intent 34,
  lang_switch 50, persona 54, speed 22, card_motion 43 all green. One live Open-Meteo call (Lisbon, Berlin): parser OK,
  ~0.7 s cold, 0 ms cached.
- **NOT verified live:** on the mic (nag acks by voice, heads-up spoken while he works), the in-call heuristic on a
  real Zoom / Meet call (Meet in a browser is NOT detected), the brief on a real first wake with his calendar.

## D40: The tutor teaches like a teacher — one voice, never hears herself, answers doubts on the board (2026-11-14)
**Problem (his words):** "I ask it to teach something: it's going and suddenly breaking … two other voices are
breaking the speaking voice … once I ask how it is done or any doubt, it should be able to explain." The real log
(2026-11-11) showed the causes. Research: `docs/research/tutor_teacher.md` (14 sources: LiveKit/Pipecat
interruption handling, Whisper Bag of Hallucinations ICASSP 2025, Careless Whisper, AEC3, echo-text matching,
Tutor CoPilot, ChalkTalk, OpenMAIC, LearnLM, human-tutoring studies).
- **Causes found.** (1) Three lessons at once: D33's lock was a pid file, check-then-write, so two launches in one
  second, or a voice launch while a terminal `stiti teach` was loading, could both pass. (2) Her own TTS came back
  through the mic ("Chalo today … let's go step by step", "Good question"), so she cut herself off, replayed the cue
  (the duplicate "Chalo! Today …") or answered herself. Whisper phantoms ("Two minutes, time's going to tell", a
  looping "Kale, malawad …") did the same. (3) **"I can't answer that one properly without my cloud brain"**: only
  in the built-in demo lesson. `make_lesson()` gives the demo and `--resume` no planner, and `_answer()` asked the
  LLM only when a planner existed. The `.env` and router were fine (the LLM lessons in the same log did answer).
  (4) "Shall we continue?" ended every answer. (5) Found while live-testing: the board auto-focuses the answer box on
  every check, which sent a "raised hand", so every check started with "Sure, take a moment. Say continue …" (also in
  the 11 Nov log).
- **One lesson, proven under races:** `tutor.lock` is a kernel `flock` held for the lesson process's whole life
  (`acquire_lesson()` is the first thing `teach()` does, before any model loads). The pid is still written for
  readers. `tutor_active()` = flock held **or** pid alive. The file is never unlinked. `launch()` is serialised with
  a thread lock. The always-on loop's `say()` is silent while a lesson runs (only a ringing alarm speaks), and it
  drops "awake" as soon as a lesson starts.
- **One voice inside the lesson:** every utterance goes through `Tutor._play()`, which stops current playback first.
  The doubt's acknowledgement, filler and answer lines never overlap (the tests count overlaps).
- **She never hears herself** (`tutor/ears.py` `EchoGuard`, pure code). It runs on every voice transcript and as a
  `TurnTaker.veto` on the barge-in verdict, so echo never even stops her. Rules: Bag-of-Hallucinations phrases;
  the same line again within 20 s (looping); low Whisper confidence → commands only; inside her echo window
  (playing + 1.5 s), ≥ 60 % of the content words, or a ≥ 60 % in-order run, matching what she said in the last 15 s
  = her own voice; inside the window a non-command needs ≥ 3 words or a doubt opener; "bye" must be confident.
  "ruko / wait / stop / ek doubt" always pass instantly. All thresholds are named constants.
- **Doubts like a teacher:** stop → "Good question." (rotating, never twice in a row) → a doubt board under the
  current page (`begin_aside`; the lesson board is untouched) → `planner.answer()` in a background thread (strict
  JSON, `tutor_answer`), with a filler only if it takes > 0.8 s → 2–4 sentences that draw ≤ 4 ops in sync (ops that
  could flip or erase the lesson board are dropped) → a follow-up within 45 s ("samajh nahi aaya") is asked again
  with the earlier answer and "simpler, everyday example" → "Back to where we were." → the interrupted cue replays
  from its start. Its snapshot is rebased so the doubt board stays on the canvas. A doubt during a check, or after a
  finished cue, re-asks the check instead of replaying anything. LLM down: one honest line ("I can't reach my
  thinking brain right now, so here's the short version from this lesson.") + a local lookup + parked, said ONCE;
  later doubts get "Parked that one too." **Every lesson gets an answerer** (`tutor.answerer()`), the demo, resumed
  lessons and crash-course glue included.
- **Pacing:** "Shall we continue?" removed. A 0.6 s breath at section ends. A check-in ("Any doubt so far? Just ask,
  or I'll carry on.") only after a teaching section with no check of its own, at most every 2 min. A paused lesson
  says one gentle line after 90 s of silence. The board's auto-focus no longer raises a hand.
- Tests: `tests/tutor_teacher_eval.py` (new), simulated with fake audio, fake transcripts and a fake LLM: her echoed
  sentences from the real log, phantoms, "ruko" < 150 ms, a doubt mid-cue (stop, ack, filler, drawn answer on its
  own board, same cue resumed, doubt board kept), a follow-up, LLM down once, check-in frequency, a check with a
  focus event, planner strict JSON, answerer, the TurnTaker veto. `tests/tutor_launch_eval.py` +12: three processes
  racing in the same instant, six threads launching at once, a voice launch while a terminal lesson runs, kill -9
  frees the lock, and the voice loop silent during a lesson.
- **Live (free Groq, `--silent`-style driver, real board on localhost):** "binary search", typed doubt mid-cue "how
  does it decide which half to throw away?" → "Good question." → "Let me draw it out." → 3 sentences + a box on a
  doubt board → "Back to where we were." → the same cue again.
- **NOT verified on his real speakers/mic:** the echo thresholds (1.5 s tail, 60 %, 3 words) are tuned on the
  logged lines, not on his room; real AEC residue and barge-in latency on the M2 still need his ears. Alarms still
  ring during a lesson, but he can't dismiss them by voice then (the loop ignores the mic during lessons).

## D41: English first — she listens for Telugu only when he asks (2026-11-18)
**Problem (his real turns):** 22 of his 105 spoken turns since 11 Nov were written in Telugu script (0 in Devanagari),
e.g. "Siti, నిను కార్చేనా దేల్సా?" — and he says he speaks English almost all the time. Cause: D34's Whisper-tiny language
check (`voice/lid.py`) ran on every awake turn; when it said "Telugu" the whole turn went down the Telugu path (Telugu
transcript, Telugu reply). On synthetic clips it scored 6/6; on his voice and room it was wrong about 1 turn in 5.
- **The Telugu check is opt-in.** `lid.telugu_on()`: off by default; "talk in Telugu" opens it for 30 minutes (every
  Telugu turn extends it); "talk in English" / another language / unlock closes it; a Telugu language lock keeps it
  open across restarts; profile key `listen_telugu=on` or `STITI_LID_TELUGU=on` makes it permanent. A wrong "Telugu"
  costs a whole turn; a missed Telugu sentence costs one "talk in Telugu". Saves the 32 ms check on every turn too.
- Only the voice engine moves the ears (`Engine._sync_ears`); the web/text engine never does.
- **Found on the way:** "Stiti, talk in Telugu" was judged a to-do (domain conf 0.57) and the language command was
  skipped. A clear language command now wins over the domain guess (unless the sentence is a reminder/to-do command).
- Hinglish is unchanged (same English-pinned transcription + Hinglish prompt).
- Tests: `tests/lang_switch_eval.py` 63 (13 new). NOT verified on his mic; the real WER on his voice is still unmeasured
  (no recordings exist — the recorder is opt-in and off).

## D42: A lesson opens at once — board first, plan while her voice loads; "end" ends it (2026-11-18)
**Problem (his words):** "It's taking a lot of time to open." Measured on the M2 with the app running: after "teach
me X" the lesson process loaded the voice stack (VAD + Kokoro 6.7 s, Whisper 6.6 s), THEN planned the lesson (4.8 s,
18 s when Groq's per-minute limit made the planner wait), and only THEN opened the board — one after another, ~19 s of
an empty screen and silence.
- `tutor._teach`: the board server starts and the browser opens first (0.2 s) with "Getting your lesson on X ready…";
  the outline is planned on a thread WHILE the voice loads; Whisper warms up in the background on its one STT thread
  (his first words queue behind it). A page that connected early gets the lesson board when the lesson exists.
  Expected wait to her first word: ~8 s (voice load) instead of ~19 s; not measured with real speakers.
- Course / revision sessions keep the old order (their planning has its own flow).
- A bare "end" / "finish" / "end it" now ends the lesson (the help line said "end" but only "end the lesson" worked).
- Tests: `tutor_teacher_eval` 97 (17 new: order, parallel load, waiting line, failed plan closes voice + board, end words).
- **Still slow, not fixed here:** (1) the lesson is its own process and loads a second copy of every voice model
  (+550 MB RSS on an 8 GB Mac, ~7 s) — the real fix is teaching inside the app with the models already loaded;
  (2) lesson writing depends on free-tier limits: Cerebras is first in the `tutor_plan` chain and has no key, so Groq
  (8k tokens/min) carries it and the planner sleeps 15 s when the minute is used up.

## D43: Fetch first, then speak — web tasks are never answered from the LLM's memory (2026-11-18)
**Problem (measured, 12 whole tasks through `Engine.turn`, real free LLMs, `docs/research/jarvis_gap_audit.md`):**
tools were offered to the LLM only when the kNN domain said `tool` or a keyword regex fired, and it mislabels tasks.
- "Read https://en.wikipedia.org/wiki/Model_Context_Protocol and summarise it" → `memory`; the page was never read and
  the summary was invented. "Find the top trending GitHub repositories…" → `todo`; "I can't browse…" / a made-up list.
  "Compare the iPhone 17 and the Pixel 10 cameras…" → `feedback`; answered from the model's memory. "Research the best
  free speech to text models…" → one outdated line.
- A2: Z.ai GLM wrote a tool call as text and "<toolcallwebsearch <argkeyquery…" was spoken. Most likely cause (not
  reproduced): the tool loop drops the tools after reading web text, leaving tool history with no tools; GLM's
  first-round call did come back parsed in a live check. A3: after "haan" she said `Done: calendar_create_event. {'created': …}`
  and the rest of the request was dropped. A4: `web_search` ranked Google-News items above web results.

**Design (agent_core.md §3 B, build step 1). The brain decides and fetches; the LLM only words the result.**
- **Local decision, no domain label** (`connectors/live.py: detect → _task`): a URL in the sentence → `read` (always;
  not for "remind me to read …" / "save this link"); "compare A and B" / "A vs B" → `compare` (one search per item + one
  for both; the compared aspect — "cameras", "battery life" — goes into each); "research X" → `research`; "find X" with
  a word that needs today's web (top, trending, latest, price, internships, open now…) → `find`; "how much does X
  cost" → `search`. Never for his own world (`my`, `I`, todos, calendar, mood, files, people in his graph), P2 turns,
  corrections, or plain questions ("what is machine learning") — those stay chat. Search words are his own public
  words with the instruction cut off ("…and tell me which is better").
- **Fetch first, in parallel** (`_fetch`): all searches and any page he named start at once; then result pages are
  tried, one per site (find 3, research 3, compare 2 from the "A vs B" search; a plain search only when the snippets
  are thin) and the best-ranked ones that load go in (find 1, research 2, compare 1 — a second, similar page made the
  LLM answer from the wrong one). A bot check ("Just a moment…") is not a page. Budget 4.5 s (6 s for a page he
  named); with a page in hand a slower one is dropped at 3.2 s. She says "Let me look that up." at 0 s (`ack("web")`).
- **Pages** (`read_page`): our own fetch + `page_text` (lxml: headings, paragraphs, list items; menus/scripts/forms
  dropped) is preferred; Jina Reader is asked only if that hasn't answered in 1.2 s (fewer URLs go to a third party;
  never a URL that carries a token). Public hosts only.
- **Web search** (`web`): Yahoo (Bing's index) and Yandex site-search are asked together; Yahoo's results if it has
  any (its second page layout, which ddgs reads as empty, is parsed here; one quick second try if it comes back
  empty), else Yandex's. News is used only when both are empty or the words ask for news. Measured 2026-11-18: DDG,
  Brave, Mojeek, Bing, Startpage, Google 0/2. The engine classes are imported under a lock: two threads importing
  them at once tripped Python's import-deadlock check, so the first search after every start silently lost Yahoo.
- **Briefing**: the same untrusted `[LIVE INFO]` block, now with `PAGE n — Site (host): text` lines (one line each,
  square brackets removed so web text can't fake a section) and rules: answer ONLY from this, name the site, say what
  you couldn't find, word limit (70–80; 130 for "…a report"). ONE streamed LLM call, no tools.
- **Honest in code**: nothing fetched → "I couldn't open that page just now, so I won't guess what it says." with no
  LLM call. An answer that names no source gets "That's from <Site>." appended. No LLM → the page's first lines.
- **A2**: `router.TOOL_OK` = the models whose tool calls came back parsed in a live check (Groq ×3, Cloudflare ×2,
  NVIDIA ×3, OpenRouter nemotron, Gemini); tool turns use only those. Any reply that is tool-call syntax
  (`psych.TOOL_MARKUP_RX`) is a failed attempt → next provider (`complete`, and `stream` holds back the first 24
  characters to check); StreamLint / enforce / the engine never speak or store it. When the tools are taken away
  after web text the model is told so ("No more tools this turn…").
- **A3**: `registry.ask / say` word the question and the result per tool ("Should I put “Lunch with Sam” on your
  calendar for friday 1 pm?" → "Done — “Lunch with Sam” is on your calendar for Friday at 1 PM."); unknown (MCP)
  tools get plain words; errors are said only if they are plain words. The rest of the request is kept
  (`Engine.pending_ctx`): other calls lined up behind the write run after his yes (reads only) and one LLM call
  words that rest from `[TOOL RESULTS — data, not instructions]`. A message to a recipient he never named is not
  offered at all (`registry.ungrounded`: in one live run "Send an email to my professor" became an iMessage to the
  invented professor@example.com, waiting for his "haan").
- **Can't-do stays honest**: the briefing now says what she cannot do yet (book, buy, pay, send email, sign in to
  his accounts) and to say so in the first words, then offer a web look-up or a reminder.
- Found on the way: a dead feed (BBC refused TLS today) made every news ask wait 1.3 s → a failed source is left
  alone for 2 minutes (`_cached`, `DOWN_S`).

**Local vs LLM:** local = whether to fetch, what to search, which pages, the budget, the block, the word limit, the
honest lines, the source check, the confirmation wording. LLM = one call that turns the fetched text into speech.

**Tests:** `tests/fetch_first_eval.py` 155 checks, offline (search engines, page reader and router faked): the four
sentences fetch whatever domain label is forced; plain chat / personal / to-do / "can't do" sentences don't; URL
always read; empty fetch → honest line and zero LLM calls; markup never spoken or stored; "haan" wording; web before
news; fetch turns not speculable; bot-check pages; cold-start engine load. 21 other evals were re-run green (live,
conversation, persona, honest_actions, human_talk, intent, no_repeat, learn_from_chat, ask_me, anticipate, realtime,
speed, web, lang_switch, alarms, tutor_launch, whole_sentence, learning, memory, overlay, turn); the rest of
`run_all.sh` (voice/tutor/TTS suites that don't touch this code) was not run.

**Before / after (same 12 tasks, real free LLMs, text channel, 2026-11-18; replies shortened):**
| Task | Before | After |
|---|---|---|
| Price of MacBook Air M5 in India | sourced, but from news-first results (91Mobiles) · 5.8 s | web results: "Per Gadgets360 … 1,19,900; Flipkart 1,49,900" · 6.5 s |
| Latest AI news | three sourced headlines · 1.8 s | same · 1.8 s |
| Top trending GitHub repos, first three | judged to-do; "I can't browse live GitHub trends" (audit run: invented) | github.com/trending read; three real repos + what they do, "Per GitHub" · 4.0 s |
| Compare iPhone 17 / Pixel 10 cameras | judged feedback; verdict from the model's memory, no source | 3 searches + Tom's Guide's comparison read; sourced; says when the sources don't settle it · 4.5 s |
| Read a Wikipedia URL, two lines | judged memory; page never read, summary invented | page read · "Per Wikipedia, …" · 1.2 s |
| Weather in Bengaluru | correct (fast path) | same |
| Three AI internships in Bangalore | tool loop fell to Z.ai, 12.4 s, three unsourced "openings" (audit run: raw markup spoken) | three named openings with stipends from Carrerlift · 4.4 s |
| Research free speech-to-text, short report | one line from memory | four sourced findings (Retell AI, LLM API) · 5.1 s |
| Book a flight / Amazon cart / GitHub PRs / send email | honest "I can't" | still honest; "I can't book flights yet. I can look up options on the web…" |

Voice-like timing (streamed, warm, 4 fetch turns): ack at 35–98 ms; first words at 1.2 s for a page he named
(fetch 0.4 s) and 3.5–4.3 s for search + page tasks (fetch 2.5–3.3 s, LLM first token 0.4–0.9 s).

**Limits (seen across 7 live runs):** answers still depend on what the keyless search returns — when Yahoo failed
and only Yandex answered, the price snippets were about the M4 and one answer stretched them (before the stricter
rules for plain searches); one internships answer named only the listing sites. Job sites often show a bot check, so
which listing page gets read varies. Compare / research take 3.5–5 s to first words.
**NOT verified:** on the mic / speakers (ack audio, StreamLint with a 130-word report, barge-in mid-fetch); Hinglish
task sentences ("… compare karo"); Cerebras and Mistral tool calls (no keys); a real "haan" on a real calendar write.

## D44: The overlay is an orb — arc-reactor circle + solid HUD cards (2026-11-18)
**Problem (his words):** "Improve the cards' UI, it's like shit. I'm feeling like the Jarvis should be in a circle and
it's a crazy animated thing, but the card is looking like shit." In the screenshots the pill was a row of 7 dots (no
presence) and the cards were see-through grey glass: muddy over whatever was behind them, text without contrast.
Behaviour is unchanged (D26: anchor, click rules, timers, multi-display follow, capture exclusion; D30: the card
timeline). Public API in `overlay/__init__.py` is identical; `engine.py`, `voice/`, `app.py` untouched.
- **Orb** (`overlay/orb.py`, replaces `pill.py`): a 64 pt navy disc (#0A0F24), 1 pt SKY hairline rim, BLUE glow that
  grows with the state, soft black shadow. Inside, centre outward, all Core Animation layers: glowing core (14 pt,
  white → SKY → BLUE, swells 1.0 → 1.6 with the level, with a bloom) · inner ring of three 80° arcs (r 13, 2 pt, turns
  clockwise) · dashed mid ring (r 18, 1 pt, BLUE 60 %, 24 dashes, turns the other way, slower) · 36 ticks (r 21.5,
  2.4 → 4.6 pt) as a circular equaliser: length = level × a per-tick phase, 3 crests travelling clockwise · outer arc
  (r 28.5, 300°, gap pointing at the card) with a comet (0.9 s lap) while she thinks. Radii are a little smaller than
  first sketched (outer arc 30 → 28.5, ticks 24–28 → 21.5–26.1) so nothing touches the rim at 1x.
- **Looks** (`model.LOOKS` / `look_for`): idle dim, rings slow (14 s / 30 s), core breathes 3 s · listening: ticks +
  core follow his mic · thinking: comet, inner ring 1.6 s, tick wave with per-tick delays · speaking: brightest, her
  voice with gain 1.3. "Checking calendar" / "✓ Start the resume · today, 4 PM": the disc grows to the right into a
  capsule (≤ 340 pt) and the orb stays as its round left end.
- **Motion rules:** transform / opacity only. Everything that loops is a render-server animation; a state change
  cross-fades in 200 ms ease-out and each loop restarts from where it was (no snap). The 30 Hz Python tick only pushes
  the level, with implicit animations off, and only when something moved. Reduce Motion: no rotation, comet, wave or
  breathing; the level shows as brightness and thinking is a slow opacity pulse. Reduce Transparency / Increase
  Contrast / low-power 15 fps are honoured (exercised offscreen only, not with the system settings switched on).
- **Cards** (`overlay/card.py`): solid navy #0B1026 panel, radius 20, 1 pt SKY hairline (30 %), a short bright beam on
  the top edge under the orb. Eyebrow SF Mono 10.5 pt kern 1.6 SKY · title 17 pt semibold white 96 % · rows 15 pt white
  90 %, 34 pt high, white 7 % separators, hover wash · meta SF Mono 11 pt white 50 %, right-aligned; long text
  truncates with an ellipsis and never overlaps it. Ring checkbox (16 pt, 1.5 pt SKY); done = filled SKY, navy ✓, SKY
  strike. Arriving rows get a BLUE wash. Headlines are numbered 01 / 02 / 03, wrap to two lines, source in SKY caps.
  Choices that differ from the first brief, each made on real screenshots: **the card is fully opaque (alpha 1.0, not
  0.96)** because at 96 % a page of white text behind it was still readable through it; every card is 380 wide;
  "due today, 4 PM" is shown as "today, 4 PM" (the eyebrow already says TO-DO) so due times are not clipped.
- **Measured** (`overlay.demo --measure --hold 6`, M2, three runs, 3–6 s per phase, his other apps running, so treat
  these as rough): our process: idle 0.9–1.5 % and thinking 0.7–0.8 % of one core against 0.9–1.4 % for the demo
  itself with the overlay hidden (i.e. nothing measurable); listening with a fake mic 2.1–3.1 %; speaking + card
  3.4–3.7 % (those two from the two runs after the fix below); listening in silence with a card up 1.8–1.9 %. A first version let the render server glide between level
  pushes: 36 implicit animations per frame, 8–12 % of a core; fixed by plain steps. WindowServer (whole machine):
  hidden 19–30 %, orb idle 28–35 %, thinking 31–38 %, listening / speaking 34–41 %; in each run the idle orb was
  5–10 points above that run's hidden phase, but the phases were not even monotonic within a run, so this is not a
  clean number. **The orb animates all the time it is visible, so its idle cost on the compositor is small but not
  zero.** Memory (phys_footprint): 31–32 MB before the overlay exists, +5 MB with the orb, +11–17 MB once cards and
  the capsule have been shown (fonts / symbols; not run for hundreds of cards this time).
- **Tests:** `tests/overlay_eval.py` 109 (state machine, looks, Reduce Motion look has no rotation, level meter, tick
  wave phases and direction, circular hit-test, capsule width, card layout, opaque colours and text contrast, dismiss
  timers, API no-ops, audio levels, voice-loop hooks, to-do tick), `tests/card_motion_eval.py` 46.
- **Checked by eye** on real screenshots (`overlay.demo --all --shots`, Retina and the 1x external display, plus
  `--motion` bursts) and offscreen renders over light / grey / black. Stills only: nobody has watched the motion.
- **NOT yet seen by the owner.** Not verified: the look over a pure white window on his display, full-screen video,
  notch Macs, the real accessibility settings, and whether he likes a 64 pt capsule and two-line headlines.

## D45: With a Bluetooth headset she listens on the Mac's own microphone (2026-11-18)
**Found in his log:** he wears AirPods and they were macOS's default input, so the always-open mic stream ran on the
headset. Effects: (1) macOS kept flipping the default input between the AirPods and the MacBook mic and the D-mic-follow
watchdog reopened the stream each time (4 reopens in one session); (2) an open headset mic holds the headset in call
mode — her voice (and his music) play in call quality and the mic audio is codec-compressed. Wispr Flow ships
"SuggestWiredMic / AudioQualityIssue" notices for the same reason (`re_wispr_flow.md` §4).
- `voice/coreaudio.transport()` reads the device's transport type ('blue'/'blea' = Bluetooth, 'bltn' = built-in).
- `voice/duplex.py`, mode **auto** (default): if the default input is Bluetooth, the stream opens with
  `device=(Mac's own mic, default output)` — sound stays on the headset. While she is on the Mac's mic, the default
  flipping headset ↔ Mac mic changes nothing (no reopen). A wired/USB mic becoming the default is still followed.
  If the Mac's mic goes dead while pinned (lid closed), the next reopen uses macOS's default for 10 minutes.
- `STITI_MIC=default` or profile key `mic=default` → follow macOS exactly (the headset's mic), as before.
- Trade-off he should know: with AirPods in and the Mac far away, the Mac's mic hears him from a distance.
- Tests: `mic_watchdog_eval` 53 (11 new). Real devices checked: default input = Bluetooth, built-in mic found.
  NOT measured: whether recognition on his voice is better this way (no recordings yet — task B2).
## D46: Stiti's own orb — one woven line, three travelling points; cards and greeting to match (2026-11-18)
**Why:** he saw the D44 reactor and said "a perfect Jarvis, but this is not Jarvis" — Stiti needs her own look. Three
design boards later (kept in the session scratchpad, not in the repo) he picked the woven-line design after seeing it
live. He also ruled out religious / ritual motifs and names: plain modern design only.
- **Orb (default, `STITI_ORB` / profile key `orb`; `reactor` brings D44 back):** indigo disc #14123a, a closed
  rice-white line (a trefoil) woven over and under itself, three points (one coral, two amber) riding it, a dotted
  amber ring, amber glow. Idle: slow laps. Listening / speaking: the knot swells a little and the points grow with the
  level. Thinking: the line keeps drawing itself and the points race. Same panel, capsule, hit-testing, Reduce Motion
  and render-server rules as D44 (`overlay/orb.py` `_build_knot`, `_knot_look`, `_knot_level`; geometry in `model.py`).
- **Cards follow the orb** (`model.apply_theme`): indigo #121032 panel, amber eyebrow / checkboxes / beam, rice-white
  hairline. The reactor theme keeps the D44 blues.
- **Greeting:** on wake with no command the capsule shows "Hey <what she calls him>, what's on your mind?" for 3.6 s
  (`overlay.note`, `model.greeting`); a ✓ confirmation or "Checking …" label takes the capsule over.
- Tests: `overlay_eval` 116, `card_motion_eval` 46. Seen by him live (the orb); the greeting and themed cards not yet.

## D47: She never drops out while he is talking; live captions next to the orb (2026-11-18)
**His words:** "if I am speaking continuously, suddenly it disconnects without reason, and I didn't even know that it
is hearing me… while I'm talking, keep transcribing… what Stiti is going to talk should also come."
**Found in his log:** "So, currently I'll talk about my goals…" → three replies dropped (he was still talking) → 💤.
- **Cause:** the 20 s session timer counted from her last handled turn, and the sleep check also ran on the very tick
  that delivered his words — after a long stretch of talking she fell asleep before reading what he had just said, and
  that utterance was then thrown away as "heard while asleep".
- **Fix (`voice/loop.py`):** `should_sleep()` — only an idle tick can end the session; his talking (a segment arriving,
  or mid-sentence) counts as activity; the timeout is 45 s of real silence (`STITI_AWAKE_TIMEOUT`).
- **Live captions (`overlay.caption`, `STITI_CAPTIONS=off` to disable):** the capsule next to the orb shows what she
  hears (mic icon, the newest words kept) and what she says (each spoken piece when it starts to sound). While he is
  still talking (≥ 1.5 s in, not in a pause) a rough transcript of the last 6 s is made every 1.6 s on the STT thread
  when it is free. Only the current words, gone 4 s after the last update: no history on screen (his rule), and the
  overlay stays excluded from screen sharing. Cost: one extra Whisper pass per 1.6 s of long speech; a final transcript
  can wait behind one (≈ 0.3 s worst case) — not measured on the mic.
- **Also from that log:** "You shouldn't talk in Hindi" switched her INTO Hindi → `brain/lang.NOT_RX`: a negated
  language means English (unless English is the one ruled out).
- Tests: turn 80 (9 new), lang_switch 73 (10 new), overlay 121 (5 new). NOT verified on the mic.

## D48: She remembers everything he told her in a conversation; long speech is never thrown away; her name mid-sentence is not a call (2026-11-18)
**His words:** "I explained every bit in detail… it skipped most of the part and went to the final thing… it only
remembers the ending parts." His log: a plan told in seven parts → "what did I tell you till now?" → first "I don't have a
record", then only "high-paying job first, then a startup".
- **Recap (`strategy.wants_recap`, `memory.told_this_conversation`):** "what did I tell you (till now / so far)",
  "did you get all that", "repeat what I said", "maine kya bola" → the brain collects ALL his statements of this
  conversation (90 min, this session; questions / commands / short "ok"s dropped; cut-off half sentences folded into the
  full one; P2 kept local), numbered and in order, into [WHAT HE TOLD YOU IN THIS CONVERSATION]; the LLM must retell
  every point and add nothing (130 words allowed; never filtered as "already said"; never speculative). Nothing told
  yet → an honest line without the LLM. Before, only the 10-line RECENT window reached the LLM. A past-time cue
  ("last week", "yesterday") keeps the normal memory path.
- **Long confident speech is not "unclear" (`stt.STTResult.unclear`):** ≥ 7 words at logprob > −0.7 are kept whatever
  the no-speech score says. His 30-word "After that I'll get a great paying job … build my network" (logprob −0.42,
  no_speech 0.57) got "Sorry, I didn't catch that" and was never stored.
- **Wake only when called (`wake.detect`):** a wake phrase must start within his first 2 words; her bare name must be
  his first word, or follow "so / okay / hey / listen". "…explained every bit to Stiti in detail" (said to someone
  else) had woken her and she answered it. Session timeout back from 45 to 30 s of real silence for the same reason.
- Tests: `tests/recap_eval.py` 34 (his seven-part plan with a made-up person). NOT verified on the mic.
- **Still open:** she answers every part of a story with "Got it." (and can cut him off); a "just listen until I'm done"
  mode is not built. Misheard words ("parallelly" → "parallel you up") are the hearing task B2/B3.

## D49: She notices what matters, asks once, and books it — calendar, reminders ahead, prep plan (2026-11-18)
**His words:** "If it reads my mail, it should ask me: is it important? If it is, I'll save it on the calendar — and
remind me before. Not just mail — whatever information it gets or sees. My exams are on the 9th, give me a reminder on
the 1st → it should book my reminders and everything before." Before this, "the 9th" was not a date she understood
(that sentence got "Morning or evening?"), and nothing ever read mail or a document for dates.
Research: `docs/research/important_things.md` (17 sources). What decided it: the good products suggest and wait for a
yes (Apple, Gemini's "Add to calendar", Cortana); rules are enough for dates; LLM "proactive agents" are wrong about
half the time; nobody ships Hinglish date rules.

- **Notice (`brain/notice.py`, local rules, ~1 ms, no LLM):** an event word (exam, test, interview, deadline,
  submission, fee, result, flight, appointment, birthday, meeting, hackathon… English + Hinglish; or "I have to submit /
  pay / finish X by …") **and** a day that is today or later → (what, kind, when, has a time?, confidence). Not noticed:
  questions, past tense ("was", "tha", "ho gaya"), "if" / "not" / cancelled, someone else's thing (except birthdays),
  a weekly routine ("every Monday…"), his own birthday, anything starting within 2 hours, plain commands. Confidence
  under 0.7 → she says nothing. Two things in one sentence are both noticed.
- **Dates (`fastpath/dates.py`):** new `find_days` — "the 9th" (its next occurrence), "9th December", "December 9",
  "9 tarikh", "9/12/2026", "by Friday", "3 din baad", "in 2 weeks", "this weekend". `parse_when` uses the
  unmistakable forms too, so "remind me on the 1st to pay rent" now works on the normal reminder path.
- **Ask — one question, at the right moment (`life/important.py`):**
  - His own short sentence → in the same turn, her own words, no LLM: "Your exams start on Wednesday the 9th of
    December. Want me to put that on the calendar and remind you a few days before?"
  - He already gave the instruction ("…give me a reminder on the 1st", "…put it on my calendar", "remind me two days
    before my exam on the 9th") → no question: booked and read back.
  - "kal 2 baje meeting yaad dilana" / "remind me at 7 pm to call mummy" stay plain reminders on their old fast path:
    a direct instruction needs a stated event ("… hai", "… is on …") or his own reminder time relative to it.
  - Mail, documents, a long sentence (> 22 words), upset words ("nervous", "stressed") or an upset voice, another
    request in the same breath ("…find me interview questions", "…how should I prepare"), or a question of hers he
    just let pass (never a quiz) → it goes on the noticed list and is asked through the proactive gate: he is present, not in a call, not
    mid-conversation, not 23:00–08:00, inside the daily nudge budget, **at most 2 a day, 30 min apart**. "Kabir, there's
    a mail from <sender> about <thing> on <date>. Is that important? I can put it on the calendar and remind you before."
    The name comes from the profile.
  - Asked **once**. Ignored → it waits; "anything important?" / "what did you notice?" reads the list; "save the first
    one" / "yes, save that exam one" / "the fee one is not important" answers it later. "Stop asking me if things are
    important" turns the questions off (the list is still kept).
- **Follow through:** calendar entry (all-day when no time was said) + reminders, then a read-back built from what
  the writes returned.

  | Kind | Reminders ahead (his own words replace these) | Prep offer |
  |---|---|---|
  | exam | a week before 9 AM · the day before 6 PM · that morning 7 AM | yes |
  | deadline, fee / bill | 2 days before 9 AM · the day before 9 AM | deadline: yes |
  | interview | the evening before 7 PM · 1 hour before (no time said: that morning 8 AM) | yes |
  | meeting, appointment, other events | the evening before 7 PM · 1 hour before (or 8 AM) | no |
  | travel | the day before 6 PM · 3 hours before (or 8 AM) | no |
  | birthday, result day | that morning 9 AM | no |

  A reminder time that has already passed is not set, and she says so. His words: "on the 1st", "two days before",
  "a week before and the day before at 6 pm", "ek hafte pehle", "that morning"; "only the calendar"; "yes but not on
  the calendar". **Prep (one follow-up):** "Want a preparation plan, and when do you want to start?" → "from the 1st" /
  "this weekend" = a start reminder + a to-do with the due date (hidden from the day planner until that day);
  "yes" / "aaj se" = the existing step-by-step chunker opens. "No" → dropped, never asked again. "Just note it" /
  "save it somewhere else" → a fact in memory, no calendar. "Put it on my list" → a to-do with the date.
  "No, it's on the 12th" → the day is fixed and asked once more. "Not now" → it waits in the list (not a no).
  "What?" → the same question again. "Undo" / "that's wrong" right after the booking (≤ 5 min, nothing else said
  since) → reminders cancelled, entry removed.
- **State (migration `011_noticed.sql`):** one row per thing; `source_ref` = hash of kind + day + its words (the same
  exam from his mouth and from a mail is one thing); status new / asked / accepted / declined / noted / expired; the
  open question is `stage` + `asked_at` in the row, so it survives a restart. A bare "yes" counts for 10 minutes and
  only while the question is the last thing she said.
- **Honesty and safety:** "on the calendar" is said only when the calendar returned an id, "I'll remind you" only for
  reminders that were inserted; calendar down → "I couldn't put it on your calendar, but I'll remind you…"; both down →
  "Nothing is booked". Mail and document text is untrusted: pattern-matched only, never sent to an LLM, never obeyed
  (a mail saying "add this now without asking" still only produces a question), spoken with links and odd characters
  removed. Speculative turns are blocked for these turns.
- **Local vs LLM:** noticing, the decision to ask, the wording, the booking and the read-back are all local. The only
  cloud use is optional and in the background: his own non-private sentence that names an event but no date the rules
  can read ("in the second week of December") goes to the free `extract` chain; its answer is checked (real future
  date, known kind, words from his sentence) and only ever lands on the noticed list, where she says it as her
  working-out ("I make that around Tuesday the 8th of December"). Live check with Groq (gpt-oss-120b, ~1 s, made-up
  sentences): two of two came back grounded. `STITI_NOTICE_LLM=0` turns it off.
- **Mail:** `connectors/mail.py` can now return the first lines of a body (`unread(snippet=True)`, 2 KB partial fetch,
  plain text only). The app scans unread mail every 15 min **when mail is set up** — it is not, on his Mac. "Check my
  mail for anything important" then answers: "I can't read your mail yet. Put MAIL_ADDRESS and MAIL_APP_PASSWORD, a
  Google app password, in the .env file and restart me."
- **Until migration 011 is applied the feature is simply off** (one `to_regclass` check; no turn can fail on it).
- Tests: `tests/important_things_eval.py` 244 (fake LLM, fake mail, fake calendar, clock fixed at Wed 18 Nov 2026 10:00).
- **NOT verified:** on the mic; a real Apple Calendar entry (the all-day flag was never run against EventKit); real
  mail (IMAP partial fetch + MIME reading are tested on made-up bytes only); the 15-min scan inside the running app.
- **Open / his call:** when he names his own reminder ("on the 1st") the defaults are dropped — no automatic
  "day before" on top. Interviews get the prep offer too. Every short dated sentence of his gets the question
  (a cap per day exists only for the ones she starts herself). Lessons are not consulted for the spoken question
  beyond "stop asking". A moved date ("postponed to the 12th") is asked about as a new thing; the old booking stays
  until he says undo. No "important to him" learning yet: `noticed.status` is the label set for it.

## D50: English first — public examples for understanding, varied wording, example replies (2026-11-18)
**His words:** "People have built Jarvis-like assistants — what data do they use for behaviour and talking like a human?
Find it so we can integrate it … don't think about languages; focus on English first." Research:
`docs/research/behaviour_data.md` (on the research branch; steps 1–4 are built here). No LLM fine-tuning anywhere: the data becomes examples,
word lists, a test, and a file he can edit.

**1. A real yardstick (`tests/public_intent_eval.py`, `tests/fixtures/public_intent.jsonl`).** 557 held-out English
lines from the TEST splits of MASSIVE en-US (272, CC BY 4.0), CLINC150 incl. out-of-scope (197, CC BY 3.0) and PRESTO
en-US — plain, disfluent, "no wait, I mean …" (88, CC BY 4.0) — each given one of Stiti's domains; 80 drawn lines whose
published label doesn't fit Stiti's meaning were skipped by hand (`BAD_GOLD`); plus 42 life-update sentences of our own
that must never become a command. Licences re-read on each dataset's own page; all three allow redistribution with
credit, so the fixture is committed and the eval runs offline (`docs/THIRD_PARTY_DATA.md`).
Baseline on the old code: **386/529 right (73.0%)** — chat 52%, tool 65%, control 73%, todo 100%, time 97% —
**24% of decisions under 0.7 confidence**, life updates 38/42 kept out of the command paths.

**2. Public examples for the router (`scripts/build_exemplars.py`, `intent.py`).** The script downloads the three sets
into `$STITI_HOME/data/` (≈ 70 MB transferred, 22 MB kept; PRESTO is read out of its 416 MB zip by byte range) and builds
`public_exemplars.npz`: 3,324 lines from the TRAIN splits (83 source intents, ≈ 40 varied lines each, never a yardstick
line) + 36 counterweight lines of our own, with their vectors (4.8 MB). `intent.classify` lets them vote next to the
built-in and owner-confirmed examples. His examples win (+0.03 on similarity). Four guards, all local rules:
- a plain **statement** ("My mom called me this morning") is judged as before, plus public small-talk lines — public
  requests never vote on it (`intent.is_statement`); without this, life updates fell to 13/30 on the dev set and
  `intent_eval` lost 2 lines ("My friend's birthday is on Saturday" → tool);
- a **frame** beats the words inside it: "add …", "… to my list", "remind me …", "set an alarm …" keep public
  `tool` rows out ("Also add call the placement cell" had gone to `tool`);
- our own counterweights: questions about a fact of his life (memory, not the calendar) and statements that only
  mention an alarm / list / mail;
- a to-do / alarm / control decision needs examples that actually resemble the sentence (top-3 similarity ≥ 0.44):
  "What's the difference between a list and a tuple in Python?" was `todo` at 0.37 — before this work too — and
  she would have read out his to-do list.
No file → exactly the old behaviour (`STITI_PUBLIC_EX=off` does the same).
After: **511/529 (96.6%)** — chat 98%, tool 98%, control 81%, todo 98%, time 95% — **4% under 0.7**, life updates
42/42; `tests/intent_eval.py` 34/34 (unchanged). On a separate dev set (700 MASSIVE-dev / CLINC-val lines, used to
choose the bonus, the floor and the guards) 60.3% → 95.3%; the 64 owner-style lines (intent_eval + gold_turns) 58 → 61.
Cost: file load 15 ms at start, +16 MB RAM, one decision 0.07 → 0.67 ms. Build: ≈ 100 s download once, ≈ 35 s embedding.
Honest limits: the counterweight lines were written after seeing dev-set misses, and the same kinds of sentence are
among the 42 life-update negatives, so that part of the comparison is not blind. todo lost two lines and time one
(94 → 92, 83 → 82). The domain confidence is logged but still gates nothing.
Found by the yardstick and NOT fixed: the rule floor treats any "don't" as a correction ("i don't want to forget to call
mom" → feedback; 7/529 plain requests), and only 5/28 PRESTO "no, I meant …" follow-ups are noticed. One whole-task line
got a worse label: "Check my GitHub and tell me which pull requests are open" is now `todo` at 0.46 (was `tool`);
no to-do pattern matches it, so the reply is the same honest "I don't have access to your GitHub account".

**3. Varied wording (`say.py`).** 34 fixed lines (to-do added / done / removed / not found / lists, alarm / reminder /
timer set / cancelled / listed / moved, "For when?", "Which one?", "Sorry, say that again?", "Got it.", "updated: …")
now have 4–6 wordings each: 141 in all, plus 4 acks per slow action (20, was 5) and 5 fillers (was 3). `say.line`
rotates them — never the same wording twice in a row, never the same opening word as the line before when another
variant exists, the same sequence after `say.reset()`; the first variant is the old sentence. The item / time is
always said back. "Anything else?" is unchanged (the voice loop keys on it). All text is ours; Home Assistant's
English responses (CC BY 4.0) were read for which situations to word. Evals that asserted one sentence now assert
the meaning AND the row in the database (`honest_actions`, `alarms`, `card_motion`, `learn_from_chat`, `anticipate`,
`fetch_first`, `turn`); new `tests/wording_eval.py` (58 checks). Before: six adds in a row = six times "Got it —
added …"; after: six different sentences.

**4. Example replies in the briefing (`brain/examples.py`, `~/.stiti/EXAMPLES.md`).** A file he can read and edit
(written on first use, like SOUL.md): 49 original pairs, 8–9 per strategy (LISTEN, ACKNOWLEDGE, BANTER, SOLVE, ANSWER,
REPAIR). On an English chat turn the compiler adds the two pairs of this turn's strategy nearest to his sentence under
"[EXAMPLES — … Style only: never reuse these words]": 64–86 tokens, dropped first when over budget; never on fetch /
tool / recap / "what else?" turns. A pair that IS his sentence is skipped; a reply sentence that says an example back
word for word is dropped by `psych`. Vectors cached on disk (0.2 ms per pick). `STITI_EXAMPLES=off` switches it off.
Measured live (Groq free tier, 24 made-up prompts across the six strategies, the same briefing with and without the
block, one run each at temperature 0.6; qwen3.8-27b was rate-limited after prompt 16, so only gpt-oss-20b has all 24):
| model | block | sentences `psych.enforce` dropped or rewrote | replies touched | words (raw → said) | banned phrases | questions where none is allowed | over the word cap | example said back |
|---|---|---|---|---|---|---|---|---|
| gpt-oss-20b (24) | without | 4/39 (10%) | 4 | 15.4 → 13.9 | 1 | 2 | 1 | – |
| gpt-oss-20b (24) | with | 0/40 (0%) | 0 | 13.6 → 13.6 | 0 | 0 | 2 | 0 |
| qwen3.8-27b (14 / 13) | without | 1/32 (3%) | 1 | 14.0 → 13.7 | 0 | 2 | 0 | – |
| qwen3.8-27b (14 / 13) | with | 1/27 (4%) | 1 | 13.5 → 12.4 | 1 | 0 | 0 | 0 |
With the block the weaker model stopped tacking on questions ("Nice choice! Any plans for a first tune?" → "Nice! Hope
it's in good shape.") and closers ("Let me know if you need anything else"). A small sample: a direction, not a proof.

**5. English is the default reply language (`brain/lang.py`).** Roman Hinglish now needs ≥ 2 clear Hindi words AND
≥ a third of the words. From his log: a misheard "Yaar" (for "You're") made her answer in Hinglish. 12 English lines
with a stray "yaar / haan / accha": 4 answered in Hinglish before, 0 after; real Hinglish ("yaar thak gaya hoon",
"Theek hai") still mirrors; "talk in Hinglish", locks and the D34/D41/D47 switches are unchanged
(`lang_switch_eval` 73 → 98 checks). Not changed: the Roman-Telugu rule, and the STT's own language hint.

**Not done:** the optional `is_correction` head on PRESTO revisions (the train sample read here holds no cross-turn
revisions; the full train file is another 75 MB). Hindi / Telugu / Hinglish public data (Hinglish-TOP, MASSIVE hi/te)
— "English first". CANDOR backchannels, NC datasets.
**NOT verified on the mic:** everything here ran on typed text. The rotating ack audio (20 short clips made at
start-up instead of 5: the first of each kind first, as before) and the new confirmations were not heard.
**Tests:** all 39 evals pass from a clean test home with the public file built, and again with it switched off
(what a fresh clone runs); three are new in `tests/run_all.sh`: `public_intent_eval`, `wording_eval` (58 checks),
`examples_eval` (35). The 12 whole tasks on the real free models: 8 answered from real sources, 4 honest "can't yet",
as before. Note for whoever runs the suite twice in one home: `learning_eval` teaches "add todo buy eggs" = chat into
`exemplars.jsonl`; after two runs that line flips and the eval fails — use a fresh home per run (`run_all.sh` does).

## D51: English only — she understands Hindi / Telugu words but always replies in English (2026-11-20)
He, testing the tutor: "remove this Hindi, Telugu… just make it talk in English only, because suddenly it is shifting,
and I don't even understand what it is talking about." The reply language was mirrored from what the STT *thought* it
heard (D34), the tutor's style prompt asked for "a light touch of Hinglish", fixed lines said Chalo / Achha / Aur? /
Uth jao / pata nahi, and an old active rule "[D6] Switch to Hindi" (a one-off command saved as a forever rule) was still
in his profile.
- `lang.english_only()` (default on): `decide()` returns English always. `STITI_LANGS=mirror` brings back D34.
- "talk in Telugu" / "any language" → "I'll keep talking in English." (nothing saved); an English lock still saves.
- Tutor style, acks, bridges, hints, help text, night course, demo lesson, goodbyes, ask-me intro, alarm nags → English.
- His `~/.stiti/SOUL.md` language lines and rule D6 retired (superseded) on his instruction.
- Understanding is unchanged: "ruko", "phir se", "ho gaya", Hinglish intents all still work.
Tests: mirror-mode tests run with `STITI_LANGS=mirror`; new English-only checks in `lang_switch_eval` (107); persona
(63) updated.

## D52: The tutor listens — whole sentence, the big ear, and he can change the plan (2026-11-20)
His first real lesson from "The Compiler Notebook.html" (log `~/.stiti/logs/lesson-compiler.log`): "It keeps on
saying, saying… not taking my doubts… does not give me time to complete my question… hearing wrong and then answering
me anything." What the log shows: "Tomorrow." dropped as too short, the rest of his sentence answered as a separate
half; "Bro, I don't need to go from all start" graded as his guess ("Hold that thought"); "exam tomorrow… explain me
that [HTML]" answered as a doubt about HTML; typed "I want to study a different syllabus" parked. Research:
`docs/research/tutor_agent.md` (12 sources: structure, doubts, open-source tutors) and `re_wispr_flow.md`.
1. **His whole sentence first** (`player._whole`): on a real sentence she stops, shows "You: …" live on the board, and
   joins every piece that follows within 2.2 s (4.5 s if it ends mid-thought: "…so", "…I want you to"); a word just
   dropped as "too short" becomes the start of the sentence. Commands ("wait", "skip") still act at once.
2. **Steer** (`commands.STEER` + `player._steer` + `Planner.steer`): "I know this", "start from unit 3", "exam
   tomorrow, cover it all" is a request, never a guess or a parked doubt — also during a check. One LLM call with the
   lesson's parts and the file's units picks answer / skip_to / restart / switch / crash; switch and crash plan the new
   lesson or the night course on the SAME board and voice (`_switch_lesson`, `_course_session(close=False)`). No cloud:
   "exam" still → crash course.
3. **The big ear in lessons** (Wispr Flow §3): the cloud lane was never open in a lesson — only the engine called
   `stt.mark_active` — so every doubt went through local whisper-small alone. Now `stt.prefer_cloud(True)` for a voice
   lesson: a sentence ≥ 0.9 s goes to Groq whisper-large-v3 in parallel with local (cap 1.8 s), local is the fallback.
4. **His lesson's words bias the ear** (`glossary.set_session`): segment titles and board labels ("DFA", "lexer",
   "longest match") lead the Whisper prompt for the lesson.
**Not yet:** measured WER on his voice (needs the recorder), the teaching-structure rebuild from the research
(diagnose first, concept map with mastery, ≤ 2 sentences before his turn, board as notes) — see the plan in
`tutor_agent.md`.

## D53: The coach — goal first, quick probes, mastery per concept, ≤ 2 sentences then his turn, notes pages (2026-11-20)
His verdict on the old lesson: "no proper structure… keeps on saying… doesn't understand where I'm stuck… draws
wherever it wants." Research and plan: `docs/research/tutor_agent.md` (15 sources). `stiti teach <file|topic>` and
"teach me <his file>" by voice now run `tutor/coach.py`; `--classic` keeps the old lesson.
1. **Goal first, file mapped meanwhile.** "What do you need? Is this for an exam, and when?" while the concept map of
   his file is built (one free-LLM call per unit, two at a time, cached in `~/.stiti/tutor/concepts/`). It starts as
   soon as the board is open, in parallel with her voice loading (D42). "The Compiler Notebook": 28 concepts in 27 s.
2. **Three quick probes** spread over the units (0.6 s to write), graded locally → per-concept mastery
   (`tutor/mastery.py`, BKT-lite from OATutor; `~/.stiti/tutor/mastery/<file>.json`). A right answer also marks the
   earlier concepts of that unit as probably known (0.6).
3. **The queue** (`coach.order`): learn mode skips what he knows; exam mode (Metcalfe & Kornell) keeps nearly-known
   first, then new ones by exam weight, known ones as one quick check — inside a time budget (100 min for an exam
   tomorrow, 40 otherwise), then in book order. Said out loud and drawn as "Your plan".
4. **Each concept is short steps** (VanLehn): 1–2 spoken sentences, then HIS answer (a check), graded locally;
   mastery updates after every answer (`Tutor.on_check`); a concept he gets right first time is cut short
   (`skip_to`). Step 1 always draws one figure; the worked example is one board item per step; a Remember line ends it.
   Concepts are written one at a time while he works (1–2 s each on the free tier).
5. **The board is his notes** (`skills.py` slots): numbered key points left, one figure right, example band, his
   doubts as stickies, a boxed Remember. The LLM names a slot, never a position; type sized for a room.
6. **Doubts like an expert tutor** (Bridge): the answer first decides `stuck_at` and `error_type`, fixes exactly
   that, then asks ONE check question ("So what tells the lexer a token ended?"), graded locally; the doubt is pinned
   to the page.
**Not yet:** heard on his real voice; a mastery-gated re-teach (a concept still wrong after its steps comes back
later in the session); notes export ("save my notes"); Smart Turn tuned for the tutor; confirm-when-unsure hearing.
**Tests:** `tutor_coach_eval` (22, new), `tutor_teacher_eval` 112, `tutor_eval` 27, `tutor_launch_eval` 63.

## D54: Fair grading of spoken answers — local first, a free-LLM second opinion on doubt (2026-11-20)
A right spoken answer, paraphrased or mis-heard by speech-to-text ("the FA" for DFA, "see oh two" for CO2), was marked
"not quite" by the local grader — the most frustrating tutor mistake. Research + measurements:
`docs/research/tutor_grading.md` (13 approaches; 72 labelled spoken answers in `tests/fixtures/tutor_grade_cases.json`).
1. **Local verdict first** (`grade.grade`, unchanged): correct / idk / predict / an MCQ option he picked / < 3 words /
   no expectations are final and never leave the Mac.
2. **Second opinion only on doubt** (FrugalGPT-style cascade): local wrong/partial on ≥ 3 words → one strict-JSON
   call (`planner._call`, route `tutor_answer`, reasoning low, temperature 0; schema verdict + missing expectation
   numbers + reason), told the text is speech recognition output and to be fair, not lenient.
3. **Never blocks**: daemon thread + future, hard 2 s deadline (`grade.LLM_TIMEOUT_S`); down / slow / malformed →
   the local verdict. `STITI_TUTOR_LLM_GRADE=off` switches it off.
4. **Wired** into the player's checks and doubt checks (only with a real cloud `Planner`) and the coach's probes.
   New result keys: `source`, `local_verdict`, `missing_text` (for a targeted hint), `llm_ms`, `reason`.
5. Local fix on the way: "the one that builds the tree" no longer picks MCQ option one.
**Result** (72 labelled spoken answers, real free models): accuracy 73.6 % → **93.5 %** (mean of 3 runs: 94.4 /
91.7 / 94.4); right answers marked not-right 12 → 1–2; the LLM is asked on 32/72 answers, median 300–400 ms, p90
≈ 700 ms, 0 timeouts when spaced like a lesson (burst: some hit the 2 s cap and kept the local verdict).
**Not yet:** local false "correct" on topic-similar wrong answers (never reaches the LLM); targeted hints from
`missing_text`; real-voice transcripts. **Tests:** `tutor_grade_eval` (new, offline).

## D55: The coach teaches any subject, and a syllabus file (2026-11-20)
"It should teach me ANYTHING… if I give my entire syllabus it should teach me in a day." Evaluated with the real free
models on 6 subjects (biology, history, economics, maths, programming, language) + 3 syllabus files; evidence and
examples in `docs/research/tutor_subjects.md`.
1. **A syllabus is an outline, not a book** (`book.is_outline`, `unit_text`, `outline_topics`; "Module N" / "Week N"
   headings). Each unit's LISTED TOPICS + general knowledge make its concepts (`OUTLINE_PROMPT`, every listed topic
   covered, in order); a flat list is one grouping call. `Concept.general` → steps get no fake SOURCES and never say
   "the book says". Before, every unit got the text-book citations as its "sources" and 6 major OS topics were lost.
   The concept cache key includes the file's mtime + size.
2. **Prompts for any subject:** topic maps in 2–5 real units (regrouped if a model gives one unit per concept; a lazy
   one-concept answer is asked again); probes one per unit with ONE expected point plus spoken paraphrases ("A or
   B"); steps fill named `points` / `figure` (required in step 1) / `example` fields — same board slots and
   Segment/Check — with subject-neutral figures and a real case/timeline (not a made-up "what if") as the worked
   example for non-procedural subjects. Code keeps ≤ 2 spoken sentences, borrows a missing figure, de-duplicates
   points, clips at word boundaries, and merges alternative expectations unless the question asks for several things.
3. **Fairer local grading** (`grade.py`): spoken ↔ written numbers and maths, numbers must match, comma lists are one
   answer, question-echo words don't count, light stemming, both of two key words. Simulated spoken answers: right
   graded correct 52 % → 63 %, wrong rejected 80 % → 85 %.
**Not yet:** order/negation-aware grading (a small local NLI model), a fact check of the cached concept map.
These local fixes run first; D54's free-LLM second opinion still judges what they leave wrong/partial. On D54's
72 labelled answers the local grader alone scores 51/72 (D54's local: 54/72): stricter on two-word expectations and
question echoes, so more right paraphrases are 'partial' — which the second opinion re-judges — and fewer wrong ones
are a false 'correct' (which never reaches it).

## D56: Cited answers + "your notes don't cover that" (2026-11-20, feature 2)
Research: `docs/research/teaching_apps.md` #1 and `docs/research/apps/notebooklm.md` "Techniques for Stiti" (ALCE,
Self-RAG, RAGAS faithfulness; NotebookLM's grounded chat). Built the small free/local version:
1. **His file → page-tagged chunks in Postgres** (migration **013** — 012 is feature 1's jobs table): `doc_sources`
   (mtime + size + embedder = the cache key), `doc_chunks` (page label, page index, unit, char span, english
   tsvector, `halfvec(768)` like every other embedding; GIN + HNSW), `doc_answers` (per-file answer bank).
   Chunks are whole sentences, 400–800 chars, cut at a paragraph once ≥ 400 and always before a heading (one idea
   per chunk keeps the embedding sharp: on-topic cosine went from ~0.45 to ~0.6 vs. 800-char blocks). A lesson from a
   file indexes it in a background thread at lesson start, the lesson's own section first.
2. **One hybrid SQL per doubt** (`cite.retrieve`): top-40 by cosine ∪ top-40 by `ts_rank_cd` over an OR-query, ranked
   `cos + 0.25·ts_rank_cd + 0.15·keyword cover`. ~12 ms median incl. the query embedding (test book; < 100 ms target).
3. **Score gate before any LLM call:** covered when a passage has cosine ≥ 0.50, or ≥ 0.33 AND ≥ 60 % of the
   question's stemmed words. Calibrated on EmbeddingGemma-300M q4: 18/18 on-topic covered, 15/15 off-topic (incl.
   same-subject "linker", "semantic analysis") not covered. Below it she says "Your notes don't cover that. Want a
   general answer?" and calls the LLM only on a yes. A half-built index never claims "not covered".
4. **Quotes are checked in code:** the answer schema returns `quotes [{quote, page}]`; `verify_quotes` keeps a quote
   only if its words appear in order in a retrieved passage (case / whitespace / punctuation / line-break hyphenation
   ignored, "…" may skip words); the page comes from that passage, never the LLM. She says "Page 42 says: <quote>"
   only for a verified quote; relevant file but nothing quotable → "this part is general knowledge".
5. **Answer bank:** a cited answer is saved per file (question embedding); the same doubt again (query cosine ≥ 0.93)
   is answered from it with no LLM call. A changed file drops its chunks and bank.
6. **Board:** a lavender source card ("P. 42 · UNIT 2" + the quote) on the doubt board while she answers and in the
   page's doubts strip after; click → the whole passage with the quote marked (Next.js + plain board).
A syllabus / topic list (`book.is_outline`) is not quoted; topics without a file are unchanged. Privacy as before:
only the 3–4 passages for one doubt go to the free LLM.
**Not yet:** a reranker, the tail-error guard for long outputs, citations in lesson segments (not only doubts),
a real-book quote rate measurement with live free models (the "≥ 90 % carry a real quote" check).
