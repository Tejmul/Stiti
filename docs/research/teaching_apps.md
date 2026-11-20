# Four study apps, compared — what Stiti adopts (2026-11-20)

He asked: reverse-engineer **Google NotebookLM** (now "Gemini Notebook"), **Turbo AI** (turbo.ai / Turbolearn),
**iTutor** (itutor.study by Intrazero) and **Coconote** (coconote.app, bought by Quizlet), list their features, compare,
choose, then build — each feature with its own UI. Design study only: public pages, help centres, official blogs,
app-store listings, reviews (no logins, no code). Full reports with sources: [apps/notebooklm.md](apps/notebooklm.md),
[apps/turbo_ai.md](apps/turbo_ai.md), [apps/itutor.md](apps/itutor.md), [apps/coconote.md](apps/coconote.md).

## What each one is
| App | Core | Strong at | Weak at (reviews) |
|---|---|---|---|
| NotebookLM / Gemini Notebook | notebooks of sources → grounded chat, audio/video overviews, study tools | citations to the exact line; audio "podcast" with join-in; learning guide | errors pile up near the end of long audio; Socratic mode frustrates when it withholds too long; no spaced repetition |
| Turbo AI | record / upload → notes → flashcards, quizzes, chat; new "Learn Mode" lessons | lesson structure (contents → warm-up → check per section → final quiz); course from a bare topic | transcript errors propagate into everything; answers beyond the notes; skipped files; English only |
| iTutor | AI tutor: voice lectures synced to a whiteboard, hint ladder, study plans | board pointer follows the voice; hint ladder owned by code; evidence-based memory (40 → 91 % on their benchmark); plans with code-made dates | few independent reviews; its own ratings were incentivised |
| Coconote | record a lecture → transcript → notes, quizzes, flashcards, narrated recap, chat | the record → notes loop; per-concept explanations after a wrong quiz answer | lost recordings (#1 complaint); thin notes for long lectures; rigid quizzes; no offline |

## Feature matrix (✓ = the app has it; Stiti today)
| Feature | NotebookLM | Turbo | iTutor | Coconote | Stiti now |
|---|---|---|---|---|---|
| Answers cite the exact line of HIS file | ✓ | ~ | ✓ | ✓ | ✗ (doubts use the file, no citation) |
| Honest "your file doesn't cover this" | ✓ | ✗ | ✓ | ~ | ✗ |
| Spaced-repetition review (cards come back when due) | ✗ | ~ | ✓ | ✓ | backend only (srs.py, FSRS) — no review session / UI |
| Mastery map: strong / focus / not started | ✓ (study notebooks) | ~ | ✓ | ~ | mastery stored, not shown |
| Record a lecture → transcript → notes | ✗ | ✓ | ~ | ✓ | ✗ |
| Narrated audio recap (one or two voices) | ✓ | ✓ | ✗ | ✓ | ✗ |
| Lesson structure + check per section | ✓ | ✓ | ✓ | ~ | ✓ (coach, D53) |
| Hint ladder (nudge → hint → worked example → answer) | ~ | ✓ | ✓ | ✗ | partial (2 hints → reveal) |
| Explain-it-back at the end | ~ | ✗ | ✓ | ✗ | ✗ |
| Board pointer / highlight follows the voice | ✗ | ✗ | ✓ | ✗ | ops exist, not synced to words |
| Day / exam plan with spaced reviews | ✗ | ✓ | ✓ | ✗ | day/exam mode (D53), no review dates |
| Games, 3D worlds, short videos | ~ | ✓ | ✓ | ✓ | — (skip: <8 % use at iTutor; Coconote shut its own) |

## Chosen — build order (each with its UI, its tests, its own PR)
_Refined after the REA pass (sections below): a shared job table first; quotes checked verbatim; Coconote-style
crash-proof capture; Blurt replaces plain explain-back; fewer, later checks (iTutor's own data); word-timed board._

0. **Jobs (foundation)** — one Postgres `stiti_job` table (recipe, source hashes, step, percent, error, not-before),
   re-queued on start, `LISTEN/NOTIFY` → a server-sent-events stream so the Lessons page shows live progress
   (Turbo's upload rows, NotebookLM's "generate later", iTutor's queue) — no Redis, no new server.
1. **Cited answers + honest "not in your file"** — chunks stored with (file, page, span); one hybrid SQL query
   (Postgres full-text + pgvector) with a score gate (below it: "your file doesn't cover this"); the LLM must quote
   verbatim and a local check drops any quote not found in the file; repeated doubts answered from a per-file answer bank. UI: a source chip on the board's doubt card
   ("p. 42 · Unit 2") that opens the passage.
2. **Review session (spaced repetition)** — every concept taught makes a card; FSRS schedules it; "review" by voice
   or a "Review · N due" button on the Lessons page runs a short spoken quiz of the due cards; misses feed mastery.
3. **Mastery map** — per file: Strong / Focus / Not started (from mastery), on the Lessons page and as a "Map" page
   on the board; clicking a concept starts a lesson focused on it.
4. **Record a lecture → notes** — `tutor/capture.py`: 5 s FLAC chunks fsync'd + a row per chunk, mic-health
   monitor (silent mic → swap device, gaps logged), recovery on start; local Whisper transcribes chunk by chunk WHILE
   recording, then the coach's concept map + notes from the transcript (each part summarised separately, every line
   linked to its timestamp). UI: Record on the Lessons page, with a live timer and level.
5. **Audio recap** — a 2–4 minute spoken recap of today's weak concepts (Kokoro, two voices: teacher + a student who
   voices the common mistake), rendered in the background; play it from the Lessons page.
6. **Hint ladder + Blurt + fewer, later checks** — nudge → hint → worked example → answer; "Blurt": after a concept he
   says everything he remembers, graded per concept (recalled / partial / missed) locally → FSRS + mastery; one check
   per full idea (not every 2 sentences — iTutor moved to "explain first, fewer checks" after students complained),
   spaced further when answers get curt or the voice sounds annoyed; repeated misses → a worked example.
7. **Board follows the voice** — Kokoro's per-word timings → each highlight fires on its word (`at_word`), a
   word-by-word caption; a one-line recap per board written with the plan, so "back" / "go to board N" need no LLM.

**Not adopted:** games, 3D worlds, short videos, generated art (pictures stay real, from Commons), paywalls, cloud
storage of his files.

## REA findings (public pages, 2026-11-20)

REA was run against logged-out public pages only, on a throwaway headless Chrome. Each app's full evidence (with
evidence ids) is in its report under "REA evidence (public pages)".

### NotebookLM / Gemini Notebook
- **Stack.** The public site is a three-route Google **Boq + Wiz/Angular** marketing shell (`/`, `/plans`, `/app`;
  app id `LabsTailwindMarketing`). It sits behind Google's `ESF` front end with a strict nonce CSP plus Trusted Types,
  uses GTM and Clearcut analytics, and sends upgrades through Google One. The product app (`notebook.google.com`)
  requires sign-in, so its API was not observed. No network calls or WebSockets were seen on the public pages.
- **New features found** (asset names and Help Center navigation): a ninth Studio output, **Data Tables**. Also
  **Generate sites** (interactive dashboards built from sources), **Connected apps** toggled per notebook, agentic chat
  (web, code, files, visible "thinking steps", Stop), notes that act as cited sources, per-source scoping, and
  **Generate later** with a usage meter. Sources per notebook are 50 / 100 / 300 / 600 by plan.
- **Design lessons.** Every output is a *snapshot artifact* built by the same generator contract: customise → now or
  later → background → view prompt → feedback. Slides and video have a **review the outline first** step.
- **Effect on the build list.** **No change** to the seven items. Three refinements fold into existing items:
  - #1 Cited answers: the LLM must return a verbatim quote per sentence, and a local checker (substring, then fuzzy
    match) drops anything unverified, with a stricter check on the last third of long answers.
  - #5 Audio recap: show the outline on the board for one spoken "ok / change" round before rendering. Write a JSON
    timeline next to the WAV so barge-in can resume at a segment and the board can show the cited line.
  - Cross-cutting: add a small `jobs` table (recipe, source hashes, `not_before`). It gives "generate later" when the
    free tier runs out, and marks stale recaps or cards when a file changes.
- Techniques per feature, with a free, local, 8 GB sketch, are in [apps/notebooklm.md § Techniques for Stiti](apps/notebooklm.md#techniques-for-stiti).

### iTutor
- **Stack.**
  - Frontend: Next.js App Router (`[locale]` routes) with GSAP and Framer Motion, and an axios client with a
    sliding JWT.
  - Backend: a FastAPI-shaped REST API (`api.itutor.study/v1`). Its admin health checks name **Qdrant, Redis, S3
    and a job queue**.
  - Storage, voice and models: files on Cloudflare R2. A separate realtime voice service at
    `wss://voice.intrazero.app`, likely for the metered Live Session. **MediaPipe** for on-device presence checks.
    **Pyodide + Monaco** for code blocks.
  - Payments and analytics: Paddle and Paymob, GA4 and Ads, and a custom web-vitals beacon.
  - The app itself is behind login, so only the public bundle and CSP were read.
- **LLM layer seen through endpoint names:**
  - multi-provider analytics
  - **routing policies with a `/test` endpoint**
  - **versioned "reasoning templates"**
  - mastery served as an event series (`/mastery/{u}/heatmap`, `/trends?days=30`)
  - `analytics/risk`, `recommendations` and `diagnostic/quiz`
- **Public `/api/ask`:**
  - hybrid retrieval, which falls back to `retrieval: "lexical"`, `matched: false` when nothing fits
  - returns related answers with a relevance score
  - a pattern for honest "not in your file" doubts
- **Behaviour found:**
  - The Voice room mic **ignores input while the tutor speaks and for a moment after**, and interrupting is
    tap-to-interrupt. Live Session uses unmute-to-barge-in.
  - The light voice is about 60 MB and the best voice 200/400 MB. On a slow device the room offers a lighter voice
    instead of going silent.
  - Teach-me data: 29% chose it and 71% never touched the default. On 29 Sep they **changed it to "explain first,
    fewer checks"** because students said the questions came too early.
- **Effect on the build list.** **No change** to the seven items. Refinements:
  - #6: ration checks to one per full idea, not every 2 sentences. Add a tap-to-stop beside VAD barge-in.
  - #7: drive the pointer, underline and caption from Kokoro word timestamps (`at_word` on board ops). Pre-write a
    one-line recap per board for "back" and "go to board N".
  - #3: log mastery as append-only events in Postgres, which gives a heatmap and trends on Progress.
  - Cross-cutting: per-task LLM routing policies plus a `stiti route test` command. Use a Postgres
    `SKIP LOCKED` job queue with `LISTEN/NOTIFY` instead of Redis.
- Techniques are in [apps/itutor.md § Techniques for Stiti](apps/itutor.md#techniques-for-stiti).

### Turbo AI
- **Why the public pages reveal the app.** The marketing site and the app are one Next.js deployment. The shared
  chunks on the logged-out home page therefore carry the app's data layer, about 290 distinct analytics event names
  and the paywall enum. All of this is static strings only; no app traffic was observed.
- **Stack:**
  - Next.js App Router on Vercel, React Compiler, Radix, sonner, Lottie and Rive.
  - Supabase auth, with anonymous-first sessions that are linked to Google later, plus magic link and Apple.
  - Writes go through Supabase Edge Functions, one per table (`lesson-pages-insert`, `content-update`…).
  - Reads are live rows: **ElectricSQL shapes + TanStack DB** collections with optimistic writes.
  - Modal endpoints handle collaboration access control; content processing is likely on Modal.
  - Analytics: PostHog plus a first-party batched analytics SDK with a dead-letter sink.
  - Payments: Stripe custom checkout with regional pricing from geo-IP, and Churnkey for cancellations.
  - No AI, speech-to-text or text-to-speech vendor appears client-side.
- **Data model found:**
  - `lessons → lesson_sections → lesson_pages(type, payload, status)`.
  - Each upload is a job row with `current_generation_step`, `percent_completed`, `eta_seconds` and `error_message`.
  - `last_opened(student, object_type, object_id)` powers "Jump back in".
- **New features found:**
  - Lessons generate **section by section**: started / stalled / failed / retry, plus a jump to the section being
    generated.
  - Narrated lesson pages with voice preview, speed control and a persona toggle.
  - Voice chat in both lessons and notes, and dictation in chat.
  - Podcast **"raise hand"** to interrupt and ask.
  - **Citation badges**, highlight-to-chat, @-mentioning another document.
  - Chat that runs **plans and tools** and can create a lesson from a conversation.
  - `achieved_quiz_mastery`, and flashcard "learn mode" that grades a typed answer.
  - **Recording drafts with a repair step**, and an idempotent kickoff + **reconciler** for processing jobs.
  - Paywall placements, including one halfway through notes generation and a section wall inside lessons.
- **Effect on the build list.** **No change** to the seven items. Refinements:
  - Lessons (D53): add a stream-ahead section worker with a stall watchdog and per-section status in the
    contents rail.
  - #4: 30 s segments + a manifest + repair on startup + map-reduce notes with timestamps.
  - #5: spoken "raise hand" barge-in on a recap whose script carries timestamps.
  - #1: citation chips + "Ask about this" on a highlighted line.
  - Cross-cutting: one `stiti_job` table (step, %, ETA) with a startup reconciler. Use Postgres `NOTIFY` → SSE as
    the single live channel to the UI. Keep a local `tutor_events` log for Laya calibration.
- Techniques are in [apps/turbo_ai.md § Techniques for Stiti](apps/turbo_ai.md#techniques-for-stiti).

### Coconote
- **Stack:**
  - React Router v7 framework mode (Vite) with TanStack Query.
  - A typed OpenAPI client to a separate backend (Bearer token).
  - Chat runs on the Vercel AI SDK v5 with resumable streams and server tools. Its generative UI is json-render: the model streams JSONL patches that are validated against a chart catalog.
  - Uploads go to Cloudflare R2 through presigned URLs.
  - Payments and monitoring: Stripe, RevenueCat Web Billing and Churnkey. Sentry with sampled recorder logs.
  - A new Electron Mac app streams mixed mic and system audio as PCM to a native recorder.
  - No ASR, LLM or TTS vendor is visible client-side.
- **How they keep recordings safe** (the #1 complaint, now heavily engineered):
  - `MediaRecorder` 5 s slices (opus, 64 kbps). Each slice goes to IndexedDB `chunks[sessionId, seq]` before anything else, and the session row is created first.
  - An input-health monitor (silent input, auto device swap, gaps of 1 s or more logged, auto-pause when there is no input).
  - Wake Lock re-acquired on tab focus, and a guard on leaving the page or route.
  - At stop, the WebM duration is stamped into the file and gaps in the timeline are closed.
  - An upload state machine: countdown backoff, waiting for internet, parked, needs credits. A cross-tab Web Lock, already-uploaded files reused, and a "Recording recovered" list.
- **New features found:**
  - **Blurt**: typed or spoken free recall, graded per concept as recalled / partial / missed with a score %.
  - **Feynman tutor**: the learner explains, the AI asks.
  - Six quiz types (fill-blank word bank, written answer, numeric range…), with an editor and regenerate.
  - Podcast templates: one host or two voices, with formats such as "The Classroom" and "Point Counterpoint". Length is set as a character budget (about 800 chars/min). Word-level captions and a one-time consent note.
  - Chat that **rewrites the note** with an undo toggle.
  - Per-page document reading with per-page retry ("N of M pages read").
  - A DMCA admin workflow.
- **Effect on the build list.** **No change** to the seven items. Refinements:
  - #4 Record: 5 s FLAC chunks + fsync + a manifest row + health / gap log + startup recovery. Mic in Python, so closing a tab can't kill it.
  - #4 Pipeline: staged and resumable: `transcribe` (per chunk, *while recording*) → segment → concepts → notes → cards.
  - #6 Explain-back: becomes **Blurt**, graded locally per concept by `grade.py` with no LLM, which also feeds FSRS and mastery. Add a "teach it to Stiti" Feynman flip.
  - #5 Recap: character budget + two Kokoro voices + word captions from proportional timing.
  - #1 Cited answers: source chips also open audio clips by timestamp.
- Techniques are in [apps/coconote.md § Techniques for Stiti](apps/coconote.md#techniques-for-stiti).
