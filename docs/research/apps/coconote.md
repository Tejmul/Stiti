# Coconote (coconote.app): feature inventory for Stiti's voice tutor

Researched 2026-11-20. This is a design study only. No proprietary code or content was copied, and no logged-in pages were visited.
The REA page tools need a running browser CDP endpoint, which this session did not have, so I used them nowhere. Evidence comes from
fetching public pages (the homepage HTML, the privacy page, store listings) and from third-party write-ups.

## 0. Context in one paragraph

Coconote is a student-focused AI note-taker. Its core loop: record a lecture (or upload audio/PDF/YouTube/link), get a transcript and
structured notes, then generate study material from them (quizzes, flashcards, podcast, games, chat, slides). Co-founders Brett Bauman and
Zack Hargett launched the scoped mobile v1 in April 2024. They bootstrapped it, with growth almost entirely from organic TikTok/IG
short-form video (1B+ "study hack" views in 18 months). Quizlet acquired it in Feb 2026, and the site footer now reads "© 2026 Quizlet, Inc.".
Platforms: iPhone, iPad, Apple Watch, Mac (Apple-silicon iPad build), visionOS, Android, web. There is no native Windows app.
Ratings: App Store 4.8 (about 17K ratings), Google Play 4.4 (5.93K reviews, updated Nov 19 2026).
Business model: a hard paywall after one free note, a 7-day trial, roughly $99–129/yr or $19.99/mo, and a $189.99 family plan.

Key mechanic insight from the founders: **transcription costs more than the LLM calls**, and they said local transcription would cut that
cost if they rebuilt today [S12]. Stiti already runs Whisper locally, so the most expensive part of Coconote is free for Stiti.

## 1. Feature-by-feature inventory

Confidence: **[O]** = official (site, store listing, version notes), **[F]** = founder interview, **[3P]** = third-party review or blog
(often a competitor, so biased), **[U]** = user reviews.

### 1.1 Record a lecture, then transcript, then notes (the core loop)
- **What it does:** You record class audio in the app. It transcribes the audio and generates "organized notes and transcripts in seconds" [O, S1].
- **Trigger:** A record button, with a per-recording language choice ("auto-detect" recommended) and a session type: Meeting / Lecture / Other [3P, S4]. The UI does not explain what the session type changes.
- **During recording:** You can add **bookmarks, photos and text notes** while it runs [3P, S9 (screen recording)].
- **Output:** A note hub holding a structured AI note and a timestamped transcript. A tester describes the note's sections as *overview, key concepts, definitions, a summary table, next steps* [3P, S7]. Clicking a transcript timestamp plays that audio [3P, S4]. Notes are editable like a word processor (headings, styles, links) [3P, S5].
- **Mechanics:** Audio is uploaded and processed in the cloud. Processing needs the internet, and there is no offline mode [3P, S4]. Transcription is the main cost [F, S12]. Diarization uses generic "SPEAKER_06" labels and miscounts speakers [3P, S4].
- **Limits and complaints:**
  - **Lost recordings are the top complaint:** a 15-minute lecture saved as 10 s, crashes on stop, phone calls or screen timeout killing a recording, failures with headphones connected, and losses on weak connectivity [U, S8; U, S2]. The founders confirm that Apple audio-session reliability was hard and that losing a recording destroys trust [F, S12]. Version 2.53 (Nov 2026) still lists "recording-save issues" fixes [O, S2].
  - **Notes thin out on long recordings:** a 1h40 lecture gave notes covering only a "small fraction" [3P, S4], and 2–3 h recordings gave under a page [U, S8]. Notes read as a "structured summary rather than a step-by-step explanation" [3P, S7].
  - Transcripts lack punctuation or contain hallucinated or repeated words [U, S8; 3P, S4]. Language mismatch can produce a Russian lesson that yields untranslated notes [3P, S4].
  - Users asked to jump from a note line to its place in the recording, and for a visible recording timer [U, S8; S2].
- **Praise:** Peace of mind ("never miss a key detail" became the core store message [F, S12]), handling of accented professors [3P, S5], and ADHD / auditory-processing support [O testimonial, S1].

### 1.2 Live / "real-time" capture
- Marketing says it "captures content live during lectures" [3P, S11]. I found **no evidence of a live, streaming transcript shown during recording**. The transcript and notes appear after you stop. Treat live transcription as **not confirmed**.

### 1.3 Import: PDF, documents, YouTube, web links, Drive, audio files
- **What:** Use "links, audio, video, documents, websites, videos" [O, S1]. Reviews also cite Google Drive URLs and text files [3P, S5; S4].
- **Trigger:** Upload file, or paste a URL (YouTube recommended with auto-detect language) [3P, S4].
- **Limits:** One tester found that PDF and document upload required a paid plan [3P, S7]. Older reviews asked for PDF/Word/PPT upload, multi-file upload and laptop recording [U, S8].
- **Combine multiple sources into one note** shipped in v2.41 [O, S2]. A user's #1 request had been to "merge class notes and audio into one place" [U, S2].

### 1.4 Summaries and key takeaways
- These live inside the note hub as a summary and key-takeaways section [3P, S9]. No standalone length or depth control is documented.
- **"Adjustable explanation levels"** are praised in one App Store review [U, S2]. The mechanism is not documented (probably a regenerate-at-level option).

### 1.5 AI chat with notes ("Coco"), text and voice
- **What:** "Ask your notes anything" [O, S1]. The assistant persona is named **Coco**.
- **Scope:** Chat can be scoped to **one note, a folder, or the whole library** [3P, S9]. An Oct 2025 reviewer still wanted all-notes search, so library scope may be newer [U, S2].
- **Voice chat:** Spoken Q&A with spoken replies [3P, S5]. It was pulled at some point, then "restored with faster conversations" in v2.53 (Nov 2026) [O, S2].
- **Coupling with quizzes:** A wrong quiz answer opens the chat to explain [3P, S4].
- **Complaint:** One tester had to ask the chat several times before notes were translated [3P, S4].

### 1.6 Quizzes and practice exams
- **What:** Auto-generated multiple-choice quiz from a note, with instant right/wrong feedback [3P, S5]. A wrong answer shows feedback, and the reasoning needs an extra tap on **"Review why"** [3P, S9]. Some reviews mention follow-up questions on wrong answers [3P, S7]. The FAQ also lists "practice exams" [O, S1].
- **Limits:**
  - Capped at **15 questions** [3P, S5].
  - **No prompt or customization** of the quiz [3P, S4].
  - **Editing a note does not regenerate** its quiz or flashcards [3P, S5].
  - Users want multiple quizzes per recording and an adjustable question count [U, S8].
  - Quizzes sometimes target *discussion topics rather than the actual lesson content* [3P, S4].
  - One user saw the answer key disagree with the marked option [U, S8].

### 1.7 Flashcards
- **What:** Q/A cards you flip, generated automatically [3P, S5]. Cards can be **marked by how well you know them, so weaker cards come back more often** (a light spaced-repetition layer) [3P, S7].
- **Limits:**
  - No prompt option, and manual editing only [3P, S4].
  - Card count is not adjustable [U, S8].
  - Long answers get cut off on screen [U, S8].
  - Cards miss the core vocabulary in language lessons [3P, S4].

### 1.8 AI podcast (audio study)
- **What:** "Turn your note into a podcast, narrated by Coco, your AI host" [O, S1], in multiple languages [3P, S5].
- **Mechanics:** audio, then text, then a shorter audio summary. Users replay it passively on commutes [F, S12]. Reviews call it a "podcast-style breakdown" [U, S7].
- **Value signal:** It is listed alongside quizzes as a reason people pay [U, S2]. Auditory learners are the stated audience of the acquisition [O, S10].

### 1.9 Study games and mind map
- Games reported:
  - **Mind map** generated from the note
  - **"Memory Palace"**, a 3D town where coconuts hold flashcard questions
  - **Card Match**
  - **Study Run**, an endless runner
  - **StudyBee**
  - **Studyblocks** [3P, S4; S5; S9]
- None of them can be customized [3P, S4]. A learning-disability user praised the "quizzes and mini-games" [U, S2].

### 1.10 Short videos ("brainrot") and speed reading
- Notes can become short narrated videos [3P, S5]. The founders' earlier separate product *pdftobrainrot* attracted attention but no paying users, so they **sunset** it [F, S12]. A sister product, *speedreadit*, flashes text with ElevenLabs background audio [F, S12].

### 1.11 Slides generation
- v2.50 (Aug 2026) "added slide generation from notes" [O, S2]. A student praised slides for exam prep [U, S2].

### 1.12 Translations / 100+ languages
- "Capture audio or translate in 100+ languages" [O, S1]. The note hub has a translate action [3P, S9]. The App Store UI ships in 33 languages [O, S2].
- One complaint: translation depends on the source-language setting [3P, S4].

### 1.13 Folders / library
- Create folders and move notes between them [3P, S9]. A student praised "unlimited folders" [U, S2].
- Older reviews asked for folders, in-note search, bulk delete and folder previews [U, S8; S2].
- Founder insight: notes **accumulate into a per-course corpus that students revisit**, which drives retention [F, S12].

### 1.14 Export / share
- Share is by link or text [3P, S4]. Settings lets you **export notes, transcripts, recordings, uploaded files and account details** [O, S6].
- Users asked for formatted copy, print and PDF export [U, S8]. There are no Notion/LMS integrations [3P, S4].

### 1.15 Sync, devices, Apple Watch
- Synced across iPhone, iPad, Android and web [O, S1]. The Apple Watch app starts recordings from the wrist [O, S2].
- A user asked to store data in their own iCloud instead of Coconote's servers [U, S8].

### 1.16 Offline
- **Not supported** for processing (needs the internet) [3P, S4]. Recordings made with weak connectivity have been lost [U, S2].

### 1.17 Privacy
- The policy names **no** AI or transcription vendors and does not say whether data is used for training [O, S6]. Play's data-safety section says "no data shared with third parties" and "data encrypted in transit" [O, S3].

### 1.18 Other
- **Break reminders** [3P, S11].
- **"Doesn't break your honor code"** positioning, with record-only-with-permission guidance [O, S1].
- Onboarding of about 15–19 screens with personalization, ending in a paywall [F, S12; 3P, S9].
- Aggressive upsell is a common 1-star theme (unexpected $127 charge after the trial, unanswered support email) [U, S3; S8]. This is not relevant to Stiti, except as a lesson about the cost of trust.

## 2. Value for Stiti

Stiti constraints: 8 GB M2, local Whisper and Kokoro, free cloud LLM tiers only, Postgres + pgvector brain, Laya decisions, markdown notes.

| Coconote feature | Value for voice whiteboard tutor | Free + local on 8 GB? | Build idea in Stiti terms |
|---|---|---|---|
| Record lecture, then transcript, then notes | **High** | Yes. Local Whisper (mlx/whisper.cpp small/base) runs in the background, so the biggest cost driver is free. One LLM pass for notes. | "Capture" mode: stream mic to a crash-safe chunked WAV/Opus on disk every ~5 s. Whisper works chunk by chunk after the turn (never on the hot path). The coach maps the transcript to concepts, and the whiteboard draws a notes page. The markdown note is saved with section anchors. |
| **Never lose a recording** (their #1 complaint) | **High** | Yes, pure engineering | Append-only chunk files + a manifest row in Postgres. Recovery on restart. Mic-device-change handling. A visible timer and a spoken "still recording" check. |
| Long recordings without thin notes | **High** | Yes, map-reduce over chunks via a free LLM, queued | Segment the transcript by coach concepts (topic shift), summarize each segment separately, then build a concept-ordered note. Never compress 2 h into one prompt. Spread rate-limited calls through the existing fallback router. |
| Timestamped transcript, click to play audio, note line to source | **High** | Yes | Each note bullet stores `(recording_id, t_start, t_end)`. Clicking a whiteboard line, or saying "where did he say that?", plays that clip. This feeds doubt answering with citations. |
| Bookmarks / photos / text during recording | Med-High | Yes. Apple Vision OCR (pyobjc) is local and free. | Voice cue "mark this" / "this is important" (Laya intent) drops a bookmark that boosts concept importance. A board photo goes through OCR into the note page. A Wikimedia picture can be matched to the concept. |
| Import PDF / YouTube / web / combine sources into one note | **High** | Yes. pypdf/pymupdf local. YouTube captions via yt-dlp first, Whisper only as fallback. | "Learner file" ingestion already feeds the coach. Add multi-source merge: lecture audio + slides PDF land in one concept map, with each concept linked to its slide page and audio timestamps. |
| Session type (Lecture / Meeting / Other), per-recording language | Med | Yes | Laya classifies the session type automatically and picks the note template (lecture: concepts, definitions, examples; meeting: decisions, todos into Stiti todos). English-first, with auto language ID from Whisper. |
| Summary + key takeaways + "next steps" structure | **High** | Yes (one LLM call, or reuse the coach output) | Fixed markdown template for whiteboard note pages: Overview, Key concepts, Definitions, Summary table, Next steps. "Next steps" come from low-mastery concepts. |
| Adjustable explanation level | **High** | Yes | A per-learner `explain_level` in USER.md / lessons. Voice: "simpler" / "go deeper" re-teaches the current concept at that level and remembers the preference per subject. |
| Chat with notes, scoped note / folder / library | **High** | Yes. pgvector + FTS is already the brain. | Doubt answering with an explicit scope filter (this lecture / this course / everything), answers cite timestamps. Cross-lecture recall ("what did we cover on X last month?") uses infinite memory. Stiti already has this through RAG. |
| Voice chat with the notes ("Coco" voice) | **High** (core) | Yes (Whisper + Kokoro exist) | Already Stiti's core. The lesson: Coconote pulled voice chat, then restored it as "faster". Latency is the feature, so keep the <1 s first audio. |
| Quiz with wrong answer, then "Review why", then explanation | **High** | Yes | Maps directly onto **probes**. A wrong answer goes straight to a short teach-then-ask step on that concept (no extra tap: it is voice), then mastery is updated. Avoid their flaws: no 15-question cap, questions generated per concept from the coach map (not discussion topics), regenerated when the source note's hash changes. |
| Practice exam | **High** | Yes | Exam mode: timed mixed probes weighted by low mastery and by the syllabus. A spoken score report at the end, and weak concepts queued for day mode. |
| Flashcards + "how well do you know it" weighting | **High** | Yes. py-fsrs (open-source FSRS) is tiny. | Per-concept FSRS scheduling backed by coach mastery. Day mode opens with "3 cards due". Cards are spoken (Kokoro) and answered by voice, with a short card face drawn on the whiteboard. User-adjustable count. |
| AI podcast from notes | Med-High | Yes. Kokoro (82M) local. Script from a free LLM, rendered in the background. | "Listen mode": a 3–5 min spoken recap of a note or today's weak concepts, saved as an audio file. An optional two-voice teacher/student dialogue uses two Kokoro voices. Good for walks or commutes. Pre-render in the background so playback is instant. |
| Mind map | **High** (whiteboard-native) | Yes | Render the coach's concept graph (nodes coloured by mastery) as a whiteboard page. This also gives the "view my knowledge graph" moment. |
| Memory Palace / Card Match / Study Run / StudyBee | Low | Possible, but off-mission | Skip. At most a voice "rapid-fire round" game in day mode. |
| Brainrot short videos / speed reading | Low | Not worth it | Skip. The founders sunset it themselves: attention without value. |
| Slides from notes | Low-Med | Yes | Whiteboard pages already do this. Maybe "export pages to PDF". |
| Translation, 100+ languages | Low-Med (English-first priority) | Yes, via a free LLM | An on-demand "explain this in Hindi/Hinglish" for one concept. No bulk note translation now. |
| Folders / library / per-course corpus | Med | Yes | Group by course/subject node in the knowledge graph rather than folders. Notes are markdown files in `~/.stiti/notes/<course>/`. |
| Export (notes, transcripts, recordings) | Med | Yes | Already markdown, so add PDF export and "copy formatted". Recordings stay local. |
| Multi-device sync / Apple Watch recording | Low | Conflicts with local-first | Later: an optional phone voice-memo drop folder that Stiti ingests. |
| Offline | **High** (Stiti advantage) | Yes for capture + STT + probes + recall. LLM notes queue until a provider is reachable. | Record and transcribe fully offline. Quiz and flashcard review from cached items with no LLM. Note generation is queued and spoken as "I'll write the notes when I'm back online". |
| Speaker diarization | Low-Med | pyannote is heavy for 8 GB, so tentatively no | Skip. Lectures are single-speaker. Coconote's own is poor. |
| Break reminders | Low-Med | Yes | Day-mode pacing: after N minutes or detected fatigue (emotion model), suggest a break. |
| Data privacy (own storage) | **High** (Stiti advantage) | Yes | Users asked Coconote for "own iCloud, not your servers". Stiti is local by design, so say so plainly in the UI. |

## 3. Takeaways
1. **Reliability of capture is the product.** Coconote's #1 complaint, and the thing the founders say breaks trust, is lost recordings. Build crash-safe chunked recording before anything fancy.
2. **Their weakest spot is depth, which is Stiti's strongest.** Notes thin out on long recordings and quizzes drift off-topic, with no customization or regeneration. Stiti's coach (concept map + mastery) fixes this structurally: questions and notes are keyed to concepts, not to one summary.
3. **The quiz-to-explanation link is their best learning loop.** In Stiti it becomes seamless: wrong probe answer, then a teach-then-ask step, then a mastery update, all by voice.
4. **Passive audio (podcast) and a spaced-repetition-ish flashcard layer drive daily habit.** Both are cheap for Stiti (Kokoro + FSRS).
5. **Timestamp linking and scoped chat make notes trustworthy:** every claim points back to the source audio or page.
6. **Skip the gimmicks** (brainrot videos, 3D games, aggressive paywall). The founders themselves said the novelty framing hurt.

## 4. Sources (all fetched 2026-11-20 unless noted)
- [S1] Coconote homepage and FAQ: https://coconote.app (raw HTML text extracted)
- [S2] App Store listing (description, version history 2.41–2.53, IAPs, reviews): https://apps.apple.com/us/app/scripty-ai-note-taker/id6479320349
- [S3] Google Play listing (rating 4.4 / 5.93K, data safety, developer Quizlet Inc, reviews Oct–Nov 2026): https://play.google.com/store/apps/details?id=app.coconote
- [S4] tl;dv review, Feb 17 2026 (competitor; hands-on): https://tldv.io/blog/coconote-review/
- [S5] UPDF review, c. Aug 2025 (competitor): https://updf.com/edit-pdf/coconote-review/
- [S6] Coconote privacy policy: https://coconote.app/privacy
- [S7] Rimo review, updated Oct 1 2026 (competitor; hands-on): https://rimo.app/blogs/coconote-review_en-US
- [S8] JustUseApp aggregated App Store reviews: https://justuseapp.com/en/app/6479320349/coconote-ai-note-taker/reviews
- [S9] ScreensDesign UX walkthrough (onboarding, record screen, quiz "Review why", Study Run, scoped chat, folders): https://screensdesign.com/showcase/coconote-ai-note-taker
- [S10] EdTech Innovation Hub on the Quizlet acquisition (Feb 2026): https://www.edtechinnovationhub.com/news/quizlet-acquires-note-taking-app-coconote-launches-new-ai-powered-learning-experience
- [S10b] THE Journal, Feb 13 2026: https://thejournal.com/Articles/2026/02/13/Quizlet-Adds-AI-Powered-Tools-for-Active-Practice-Notetaking.aspx
- [S10c] Pulse 2.0 on the acquisition: https://pulse2.com/quizlet-acquires-coconote-and-adds-new-ai-study-experience
- [S11] Venture Radar newsletter, Jun 21 2025: https://www.readventureradar.com/p/this-ai-note-taking-app-built-for
- [S12] Sub Club podcast with the founders, "Bootstrapped to $6.7M ARR and an Exit to Quizlet in 2 Years" (transcript): https://share.transistor.fm/s/07d90e73 (transcript at https://share.transistor.fm/s/07d90e73/transcript.txt)
- [S13] AlternativeTo entry (feature tags, platforms): https://alternativeto.net/software/coconote/about
- [S14] Quizlet on Wikipedia (acquisition dated Feb 2026): https://en.wikipedia.org/wiki/Quizlet
- Context only, not fetched (bot-blocked with 403): TechCrunch on the "PDF to brainrot" trend, Nov 20 2024: https://techcrunch.com/2024/11/20/pdf-to-brainrot-study-tools-are-a-strange-iteration-on-a-tiktok-trend/

Caveats:
- Several hands-on reviews come from competitors (tl;dv, UPDF, Rimo), so their weaknesses may be exaggerated.
- Pricing differs between sources ($59–$129/yr). The App Store IAP list ($9.99 to $189.99) is authoritative per region.
- I found no Reddit threads directly. The search surfaced only review blogs.
- Live in-recording transcription is not confirmed.

## REA evidence (public pages)

Added 2026-11-20 in a second pass. I used REA against a throwaway logged-out headless Chrome (CDP on 127.0.0.1:9333) and looked only at
public pages: `/` and `/professionals`. Nothing was logged in or signed up, and no auth was bypassed. I also downloaded the **public**
static JS chunks that the logged-out homepage itself loads or lists in its route manifest (58 chunks, about 2.2 MB), and read them as
inert text (grep and context windows, never executed). The source maps are **advertised** (`sourceMappingURL=*.js.map` on every chunk),
but I deliberately did **not** fetch them. No code was copied into this repo. What follows describes design only. I found no secrets,
and I record none.

**REA evidence ids**

| What | Evidence id |
|---|---|
| Target list (Coconote tab `BD4CE2A1…`) | `ev_fefb548c…` |
| `inspect_web_page` of `/` (104 scripts, all same-origin `/assets/*`, a11y text) | `ev_084c7876…` |
| `analyze_web_bundle` parent | `ev_f40e5ea1…` |
| `analyze_web_bundle` javascript-routes summary receipt (97 sources, 12 route patterns) | `ev_3ff13c3f…` |
| `analyze_web_bundle` routes view | `ev_4ee28395…` |
| `capture_web_screenshot` of `/` (1440×813) | `ev_c705d9f5…` |
| `inspect_web_page` of `/professionals` | `ev_4f6662c2…` |
| `inspect_web_event_listeners` on `button` (no direct match) | `ev_e2e5d417…` |
| `inspect_web_event_listeners` on `body` | `ev_cea8ea67…` |

The `body` listeners on `/professionals` are the full React root-delegation set, and they are owned by a `framerusercontent.com/…/react.mjs`
module, so that marketing page is a Framer-hosted build.

**Prompt-injection check:** none found. The only instruction-like text is the LLM *prompt templates* bundled inside the chat's
generative-UI library (for example "You are a UI generator that outputs JSON…", "Output ONLY JSONL patches…"). That is the app's own
prompt to its model, so I treated it as data. A mic-permission help link points to a public chatgpt.com share, which I did not open.

### R1. Tech stack (fingerprints)

| Layer | Evidence | Finding |
|---|---|---|
| Web framework | `window.__reactRouterManifest`, `entry.client`, `root`, `routes/_public+/…` ids (`manifest-3544216d.js`) | **React Router v7 framework mode** (Remix lineage) with remix-flat-routes `+` folders. Vite-hashed `/assets/*`. Same-origin chunks only. |
| Data layer | `react-query-*.js`, `QueryClientProvider`, `HydrationBoundary`, `useMutationState` | TanStack Query. The recorder list uses `networkMode:"always"` and refetches on focus/reconnect. |
| API client | `GET/POST("/user/input-sources/{inputSourceId}/pages", {params:{path}})`, `Authorization: Bearer <accessToken>` | Typed **OpenAPI client** (openapi-fetch style) against a separate backend, plus a few same-origin `/api/*` routes (`/api/chat`, `/api/auth/logout`, catch-all `api/*`). |
| Chat | `ai-sdk/<ver>` header, `DefaultChatTransport` default `/api/chat`, resumable `GET /api/chat/{chatId}/stream`, UI-message parts `tool-input-*`/`tool-output-*` | **Vercel AI SDK v5** `useChat` with server tools and resumable streams. |
| Generative UI | `[json-render]` error strings, catalog `BarChart / LineChart / PieChart / ComposedChart`, Recharts | The LLM streams a **JSON UI spec as JSONL patches** (`{"op":"add","path":"/root"…}`). The spec is validated against a component catalog and rendered with a per-element error boundary. |
| Recording (web) | `NewNoteModal-*.js`: `MediaRecorder`, `AudioContext`, `getDisplayMedia`, `audioWorklet.addModule("/assets/dual-stream-mixer-worklet-*.js")`, `wakeLock`, `devicechange`, `visibilitychange`, `beforeunload` | Custom crash-safe recorder (details in R3). |
| Local persistence | `CoconoteAudioRecorderDB` v1 (idb wrapper): stores `sessions` (keyPath `id`, index `by-featureKey`) and `chunks` (keyPath `[sessionId, seq]`). Legacy `localforage` instance `failedRecordings`. `navigator.storage.persist()`. | Every 5 s audio slice is written to IndexedDB **before** upload. |
| Upload / storage | `POST /user/uploadUrl` and `/user/documentUploadUrl` return `{url, cloudflarePath, maxFileSize}` | Presigned PUT to **Cloudflare R2**. CDN `assets.coconote.app`. Cloudflare in front (`cdn-cgi`, `static.cloudflareinsights.com`). |
| Media tooling | `mediabunny` messages and an embedded LAME-style MP3 WASM in `file-upload-*.js`. WebCodecs `canDecode`/`getSample` in `podcast-*.js`. | Imported `.mp4/.m4a/.mov` files are **transcoded to MP3 in the browser** before upload. Podcast **video export is rendered client-side**. |
| Desktop | `window.electron.coconote`, `recorder.start/pause/resume/stop/sendPCM`, `requestSystemAudioPermission`, `core.readFile/deleteFile`, `recordingMetadata.setItem`, `electron-auth-browser` route. "Download for Mac" on `/professionals`. | A new **Electron Mac app**. The renderer mixes mic and system audio into 16 kHz PCM and streams it to the native side, which writes the file. Login is handed off through the browser. |
| Payments | `react-stripe`, `pay.rev.cat/<app>/…`, `churnkey`, `EtherPaywall`, credits (`credits >= n`), `PENDING_AUTH` | Stripe plus **RevenueCat Web Billing** for cross-platform entitlements, Churnkey cancel flows, and per-note credits. |
| Monitoring | `_sentryDebugIds` in every chunk. Sampled logs (`Math.random() <= 0.05`, `0.005`). | Sentry, with **sampled** client logs for the recorder (5 % pre-flight, 0.5 % chunk failures). |
| Other libs | three.js + react-three-fiber + FBXLoader, Mermaid, Vidstack, dnd-kit sortable, Floating UI, framer-motion, Lucide, react-confetti, Monaco (admin) | Memory-palace 3D game, mind maps, video player, reorderable quiz/flashcard editors. |
| ASR / LLM / TTS vendors | Not visible in public JS (server-side) | **Unknown.** Podcast voices use UUID-format ids for some and plain names (`bella`, `elowen`, `warrick`…) for others, which suggests two TTS backends. An apparent "cartesia" hit was a false positive (Recharts' `cartesian`). |

### R2. Route and feature map (from the public route manifest; 86 routes)

REA's static route detector found only the 12 public nav paths (`ev_4ee28395…`). The manifest gives the whole map:
- **Per note (`/notes/:id/…`)**: `transcript`, `bookmarks`, `quiz`, `flashcards`, `mindmap`, `podcast`, `slides`, `video-overview`,
  `blurt`, `quizlet` (export), `opengraph-image` (share cards). Games: `cardmatch`, `memorypalace`, `studyrun`, plus `mobile-arcade` and `mobile-mindmap` web views for the native apps.
- **"Drops" (`/_drops+/…`)**: standalone single-purpose tools that each take one input (PDF / URL / audio / pasted text) and produce one
  artifact: `blurt`, **`feynman`**, `podcast`, `slides`, `speedread`, `video`, `video-overview`, `cardmatch`, `memorypalace`, `studyrun`.
  Each one is a free-trial funnel that ends at a paywall (`use-drop-teaser-paywall-intent`).
- **App shell**: `home`, `settings`, `settings/notifications`, `support`, `privacy`, `onboarding`, `legacy-onboarding`, `arcade`,
  `quiz` (a marketing onboarding questionnaire that ends at RevenueCat), `gift`, `gift-redeem`, `upgrade`, `checkout/*`, `bundle-checkout`, `creator-program`.
- **Ops**: `admin/*` with a full **DMCA workflow** (`dmca`, `dmca/audit`, `dmca/banned-users`, `dmca/users-needing-warning`). The share modal says "notes created from web links cannot be made public". Copyright policing is part of the product.
- **Integrations**: `oauth/quizlet/callback`, `electron-auth`, `apple-confirmation`, `unsubscribe/:userId`.

### R3. How recordings are kept safe (the core finding)

From `NewNoteModal-*.js` and `use-failed-recordings-*.js` (public chunks), reading constants and state names only:

1. **Pre-flight**: login, `MediaRecorder` support and IndexedDB availability are checked first. Failures are logged (5 % sampled) and shown as typed errors (`UNSUPPORTED_BROWSER`, `MICROPHONE_ERROR`, `LOGIN_REQUIRED`).
2. **Audio graph**:
   - mic → gain node → `MediaStreamDestination` → `MediaRecorder` (`audio/webm;codecs=opus`, **64 kbps**).
   - Optional system/tab audio comes from `getDisplayMedia`. Its video tracks are stopped at once and its audio is mixed into the same destination.
   - Lecture mic constraints: mono, **echoCancellation off**, noiseSuppression on, AGC on. The Blurt mic turns both off.
3. **Timeslice 5 s**: `recorder.start(5000)`. Each `dataavailable` blob is written as `chunks[{sessionId, seq, blob, recordedAt}]` in **one IndexedDB transaction** with the session's `durationMs`.
   - The session row `{id, status:"recording", mimeType, startedAt, folderId, audioLanguage, recordingType, showSpeakerLabels}` is created **before** the first chunk.
   - On a write failure the `persistenceHealth` flag turns `"degraded"`, and the UI can warn while recording continues.
4. **Input health monitor**:
   - Every 1 s it samples an analyser. `noSignalTicks`/`mutedTicks` drive `inputHealth` (`"ok"`, `"silent-input"`, `"no-input"`). A probe checks for near-zero RMS (`< 1e-4`) after 1.5 s.
   - `devicechange` events are debounced at **250 ms**, and a lost track triggers an **automatic input swap** to a fallback device.
   - The missing span is recorded as a **capture gap** `{fromMs, toMs}` when it is ≥ 1 s. Gaps that start while the tab is hidden are attributed to the hidden period (5 s window).
   - AudioContext `statechange` is tracked, `micGrantExpired` is surfaced, and if input vanishes the recorder **auto-pauses** (reason `"no-input"`) instead of recording silence.
5. **Keep alive and guard**:
   - A Screen **Wake Lock** is requested and **re-acquired on `visibilitychange`**.
   - `beforeunload` and an in-app **router navigation blocker** both confirm before leaving.
   - `document.title` shows a recording or paused prefix.
   - Max duration is **5 h**, and there is a 300 MB size constant.
6. **Finalize**:
   - On stop, `requestData()` flushes the last partial slice. The chunks are concatenated into one Blob.
   - A built-in **WebM/EBML patcher** writes the missing `Duration` (EBML id `0x4489`) into the segment header and **closes timeline gaps** (Cluster/Timecode/SimpleBlock ids are present). Telemetry events: `recordingDurationStamped`, `recordingTimelineGapClosed`.
   - The session is marked `stopped`, with the persisted chunk count checked against the in-memory count.
7. **Upload state machine** (one per recording):
   - Phases: `attempting` → `done` | `countdown` (backoff on `transient`) | `waiting-offline` (driven by `navigator.onLine` plus `online`/`offline` events) | `parked` (`permanent`) | `needs-credits`. A `missing` outcome drops the record.
   - Each phase has its own UI line: "Uploading… N%", "Retrying in 12s", "Waiting for internet connection", "Out of credits".
   - The inner upload: presign, then PUT with progress and **stall detection** (`kind:"stall"`), 2 retries at 500 ms, and only while online. `uploadAttemptedAt` and `uploadedPath` are stored on the session, so a retry **reuses an already-uploaded file**.
   - A **cross-tab Web Lock** (`navigator.locks`, `coconote:upload-retry:<user>:<id>`, `ifAvailable`) stops two tabs uploading the same recording ("This recording is uploading in another tab.").
   - An IndexedDB `VersionError` marks the tab as stale, and the DB connection is released for a newer tab.
8. **Recovery UI**:
   - A `FailedRecordingsProvider` lists sessions found on load as `interrupted` (never uploaded) or `upload-failed` (upload attempted). It also loads the legacy localforage blobs, after a schema check.
   - Actions: save the recovered recording, keep it for retry, or delete it (with a "This recording will not be recoverable" confirmation). A "Recording recovered" toast appears.
9. **Server pipeline status** (polled through React Query):
   - `TRANSCRIBING` → `SUMMARIZING` → `COMPLETED`, or `TRANSCRIPTION_FAILED` / `SUMMARIZING_FAILED` with `errorMessage`.
   - Study-tool generation has its own statuses: `PENDING` / `PROCESSING` / `COMPLETED` / `FAILED`, `PENDING_CARDS_GENERATION`, and `contentBlocked` for sensitive notes (for example "this note covers sensitive topics, so we couldn't turn it into a podcast").

### R4. Other UI and technique evidence

- **Sources**:
  - A note has `inputSources` (audio, upload, web link, photos) and an endpoint for each source's transcript.
  - Documents expose **per-page** extraction results with a per-page `error`. The UI shows "N of M pages read" and has a **retry endpoint for each page**.
  - "Editing is paused while the note updates from its sources." The note is locked while it is regenerated from merged sources.
- **Chat agent tools**:
  - `tool-rewriteNotes` lets chat **edit the note itself**. It shows "Editing notes…" then "Notes edited", with a `previousNote` toggle that works as an undo.
  - `tool-removeCharts` removes charts. Charts are generative-UI specs saved into the note (there is a `DeleteChartModal`).
- **Blurt (free recall)**:
  - The learner types or **speaks** "everything you remember". Voice is recorded with MediaRecorder and transcribed, with retry if transcription fails.
  - Grading is **per concept** as `recalled / partial / missed`, with a `detail` line for each concept, an overall `score %`, and score bands from about 40 % up to about 90 %.
  - The result page shows "From your notes" and "What you blurted" side by side, plus "Coach's feedback" and a printable report.
- **Feynman tutor**: a drop that turns a source into "a Feynman tutor you can chat with". The learner explains, and the AI probes.
- **Quiz**:
  - Six question types: `multiple_choice`, `multiple_answer`, `true_false`, `fill_blank` (word-bank cards you tap or drag into blanks), `written_answer`, and `range` (numeric slider).
  - Each question has a hint line and "Review why". There is a full editor (add, delete, reorder, regenerate), a "show only multiple choice" filter, and confetti.
  - This answers the older "no customization" complaints in §1.6.
- **Flashcards**: an editor (add, delete, reorder), regenerate, space-to-flip, a corrupted-data recovery screen, and print/CSV export.
- **Podcast** (`podcast-v2-templates`):
  - Template families: `podcast` (one host, 4 voices), `dialogue` (two voices: "The Daily", "Coffee Talk", "The Classroom", "Point Counterpoint"), `brainrot` and `prof` (persona voices).
  - Length is set as a **character budget**: short 4 000 chars ≈ 5 min, medium 8 000 ≈ 10 min, long 12 000 ≈ 15 min (about 800 chars per minute). There are 21 languages.
  - A one-time **consent modal** (stored in localStorage) says it is AI-generated, to review it for accuracy, to keep personal information out, and that the content goes to a third-party service.
  - Generation runs in the background with a status. **Word-level captions** (`{word, startTime, endTime}`) show one word at a time with a short pop.
  - The podcast is played by a global audio player that persists across pages, with background playback and a download URL.
- **Mind map**: Mermaid-rendered, with zoom and export to PNG/SVG.
- **Slides**: "choose a slide style" (one visual direction for the whole deck), then PDF export.
- **Video overview**: a narrated MP4 explainer. Users keep the tab open and get a browser notification when it is ready, then rate it.
- **Share**: a public link, copy notes text, copy transcript, and export to PDF/CSV (note, transcript, quiz, flashcards, slides).
- **Home hero** (screenshot `ev_c705d9f5…`): an Instagram-story-style phone mock with progress bars, a cycling feature ticker (Podcasts / Notes / AI Chat / Quizzes), and two CTAs (download app, continue on web).

## Techniques for Stiti

Each item gives the likely technique Coconote uses, then a free, local Stiti version: libraries, data flow, where it lives in Stiti's
code, and the UI entry point. Constraints: 8 GB M2, local mlx-whisper and Kokoro, free cloud LLMs only, Postgres + pgvector, no local LLM.

### T1. Crash-safe lecture capture (their #1 complaint and best engineering) — **build first**

**Technique:** small timeslices persisted *before* anything else, a session manifest row, health monitoring, gap logging,
duration stamping, and a recovery list.

**Stiti version:** Stiti owns the mic in Python on the Mac, which is better than a browser tab: closing the tab cannot kill the recording.
- **Module:** `src/stiti/tutor/capture.py` (new).
  - A `sounddevice.InputStream` at 16 kHz mono feeds a writer thread. Every **5 s** it writes `~/.stiti/recordings/<rec_id>/<seq:06d>.flac` (soundfile, FLAC level 5, about 0.5 MB/min), then calls `os.fsync`.
  - It inserts a `recording_chunks(rec_id, seq, path, t0_ms, dur_ms, rms, sha256)` row in the same step.
  - The session row `recordings(id, status, started_at, duration_ms, chunks_persisted, gaps jsonb, device, source_kind, course_id)` is written before the first chunk.
- **Health:**
  - Per-second RMS. A silent-input flag after 3 s below about −60 dBFS.
  - A device-change watcher (CoreAudio default-device listener via the existing `voice/coreaudio.py`, or re-querying sounddevice) reopens the stream and appends a gap `{from_ms, to_ms}` when the gap is ≥ 1 s.
  - Auto-pause on lost input, with a spoken "I lost the mic, paused".
  - Keep the Mac awake with `caffeinate -i -w <pid>` while recording.
- **Mic settings:** use a **separate capture profile** with no echo cancellation (the duplex conversation path does AEC) and a light noise gate, as Coconote does for lectures.
- **Recovery:** on Stiti start, `status='recording'` rows become `interrupted`, and the Lessons page shows "Recording recovered · 42 min" with *Make notes / Keep / Delete*. Concatenation is trivial because FLAC chunks are self-describing, so no WebM duration patching is needed.
- **UI:**
  - A Record button on the Lessons page (`frontend/src/components/lessons/`) with a live timer, a level meter, a health chip (ok / silent / mic changed), and a "saved ✓ 84 chunks" counter.
  - `document.title` gets a "● Recording" prefix, and a `beforeunload` confirm appears only for in-browser capture.
  - Voice entry: Laya intent `record_lecture` ("Stiti, record this class").
- **Optional:** phone capture on the LAN uses the same browser design as Coconote: `MediaRecorder(timeslice 5000)`, then IndexedDB `chunks[sessionId, seq]`, then POST each chunk to `/api/capture/<id>/<seq>`, which is idempotent by `(id, seq)`.

### T2. Staged, resumable processing pipeline with explicit statuses

**Technique:** `TRANSCRIBING → SUMMARIZING → COMPLETED` / `*_FAILED + errorMessage`, polled by the UI. Each study tool has its own status.

**Stiti version:**
- **Table:** `capture_jobs(rec_id, stage, status, error, attempts, next_attempt_at)`.
- **Stages:**
  1. `transcribe`: mlx-whisper runs **incrementally per chunk while recording is still going**, in the background at low priority and paused during a live conversation through `voice/stt.py`'s `conversation_active()`. The transcript is nearly finished at stop.
  2. `segment`: topic shifts from embedding drift with the local embedder.
  3. `concepts`: the coach maps segments to concepts.
  4. `notes`: free LLM, map-reduce per segment.
  5. `cards`: probes and FSRS cards.
- Each stage is idempotent and keyed by an input hash, so a crash resumes at the failed stage.
- **LLM stages:** use Coconote's upload phase machine for LLM calls (`attempting / countdown / waiting-offline / parked`) on top of the existing fallback router. Offline means the job waits, and Stiti says "notes will be ready when I'm back online".
- **Where:** `src/stiti/tutor/capture_pipeline.py`, with status at `GET /api/lessons/captures` in `src/stiti/web/lessons.py`.
- **UI:** a progress row: Transcribing 63 % → Mapping concepts → Writing notes → Ready.

### T3. Every note line traceable to source: per-page and per-timestamp

**Technique:** `inputSources` per note, per-page extraction status with per-page retry, and editing locked while regenerating.

**Stiti version:**
- `book.py` already reads pages. Add a `source_pages(source_id, page, status, error, method)` row, where method is text, Apple Vision OCR via pyobjc, or failed. The UI shows "212 of 214 pages read" with a retry on a failed page (OCR fallback).
- Audio note bullets keep `(rec_id, t_start, t_end)`. The board's doubt card source chip (build-order #1 in teaching_apps) opens either the page or the audio clip.
- Lock note editing while the coach regenerates from merged sources (lecture audio + slides PDF in one concept map).

### T4. Free recall ("Blurt") graded per concept — Stiti's explain-back, fully local

**Technique:** dump everything you remember (typed or spoken). Grade each concept as recalled / partial / missed with a detail line, give a
score % with bands, and show "from your notes" next to "what you said".

**Stiti version:**
- The voice prompt "Tell me everything you remember about Unit 2" records until a long pause (existing VAD and endpointing), then Whisper transcribes.
- **Grading with no LLM:** for each concept in the coach map, reuse `tutor/grade.py` (keyword stems + local-embedding similarity) against the concept's expectation sentence.
  - ≥ 0.75 is recalled, 0.45–0.75 is partial, otherwise missed. Thresholds to be tuned on logged answers.
  - Map to FSRS: recalled → Good, partial → Hard, missed → Again (`srs.rating_for`). Update `mastery.py`.
- **Feedback:** the LLM is optional and only writes one encouraging line from the already-computed table. Stiti speaks the 2 biggest misses and offers a 30-second re-teach of each (teach-then-ask).
- **Where:** a `blurt` step type in `coach.py` / `lesson.py`. In exam/day modes it ends a session.
- **UI:** a board page with three columns (Recalled ✓ / Partial ~ / Missed ✗) and a score ring, plus a "Blurt" button on each Lessons file card.

### T5. Feynman role-flip ("teach me")

**Technique:** an AI "student" built from the source asks naive follow-ups while the learner explains.

**Stiti version:**
- Laya intent `teach_back`. The Context Compiler sends the concept's expectation and its common misconceptions to the free LLM with a "curious 12-year-old" persona.
- After each learner turn, a local check flags expectation points not yet covered. The student asks about exactly those, so the brain decides the gaps, not the LLM.
- It ends with a coverage score that writes to mastery.
- **UI:** a Lessons action "Teach it to Stiti", with a board showing a checklist of points covered so far.

### T6. Typed question bank with voice-friendly types

**Technique:** six quiz types, hints, "Review why", and editable / regenerable sets.

**Stiti version:**
- Store a `probe.kind` from {`mcq`, `multi`, `true_false`, `cloze`, `short_answer`, `numeric_range`}. For voice:
  - `true_false`, `mcq`, `short_answer` and `numeric_range` are spoken.
  - `cloze` is drawn on the Excalidraw board with tappable word chips, which also works for voice ("the second word goes in blank one").
- "Review why" goes straight into teach-then-ask with no extra tap.
- Regenerate when the source hash changes (fixing their old "editing doesn't regenerate" flaw).
- Export Anki-compatible CSV.

### T7. Narrated recap / two-voice "podcast" with word captions

**Technique:** a template picks the voice count and persona, length is a **character budget** (about 800 chars per minute), it renders in the background with a status, has word-level captions, and runs on a persistent global player. A consent note appears once.

**Stiti version:**
- **Script:** the free LLM gets the compiled briefing of today's weak concepts and a budget (2 min ≈ 1 600 chars). Formats:
  - Classroom: teacher plus a student voicing the common mistake.
  - Point / Counterpoint: for contested topics.
- **Rendering:** Kokoro renders it locally sentence by sentence with two voices from `voice/voices.py`.
- **Captions:** take each sentence's measured audio duration and split it across words in proportion to character length. That is good enough for one-word captions, and an optional local Whisper word-timestamp pass can refine it.
- **Storage:** `~/.stiti/recaps/<id>.wav` + `<id>.captions.json`.
- **UI:** "Listen · 2 min" on the Lessons page. A mini-player stays docked across app pages (like their global audio player).
- No consent modal is needed, because nothing leaves the Mac except the briefing.

### T8. Chat that edits the note, with undo, and a strict render catalog

**Technique:** AI-SDK tool calls `rewriteNotes` / `removeCharts` with a previous-version toggle. Generative UI is a JSON spec streamed as JSONL patches, validated against a catalog, with a per-element error boundary.

**Stiti version:**
- In doubt mode, the LLM may return `edit_note(section_id, new_markdown)`. **Laya** gates it: only when the intent is `edit_note` and confidence is high.
- Notes stay markdown in `~/.stiti/notes/`. Keep `<name>.md.prev` (or a `note_versions` table) for one-click undo on the NoteView.
- Use the same **catalog + patch-stream + pydantic validation + skip-bad-element** pattern for board ops, so a weak free model can never break the board. Invalid elements are dropped and logged, never rendered.
- **Where:** `src/stiti/tutor/player.py` board op intake, and `frontend/src/components/lessons/NoteView.tsx` for undo.

### T9. Concept mind map as a board page

**Technique:** Mermaid mind map with zoom and PNG/SVG export.

**Stiti version:**
- Generate the layout from the coach's concept graph (Postgres nodes/edges) with no LLM. Lay it out as Excalidraw elements (simple radial or tree layout in Python, or Mermaid flowchart → `@excalidraw/mermaid-to-excalidraw` in the frontend).
- Colour nodes by mastery (Strong / Focus / Not started). Clicking a node starts a lesson on that concept.
- Export through Excalidraw's built-in PNG/SVG.

### T10. Voice bookmarks and photos during capture

**Technique:** bookmarks route and photos attached to a source.

**Stiti version:**
- Laya intent `mark_this` ("this is important") adds a bookmark `(rec_id, t_ms, label)`, which boosts that segment's concept importance in T2.
- A board photo from the phone or webcam goes through Apple Vision OCR into the same source, and is placed into the note at the matching timestamp.

### T11. System-audio capture for online lectures

**Technique:** `getDisplayMedia` audio, or Electron native system audio, mixed with the mic at 16 kHz by an AudioWorklet.

**Stiti version:**
- macOS ScreenCaptureKit audio-only capture through `pyobjc-framework-ScreenCaptureKit` (macOS 13+, free, needs Screen Recording permission). Mix it with the mic in the capture writer as two sources and one FLAC stream, and keep each source's RMS separately for health.
- Entry point: Record → "This Mac's audio (online class)".

### T12. Import robustness (local equivalents)

**Technique:** in-browser transcode to MP3 (mediabunny), size checks from the presign response, upload with stall detection.

**Stiti version:**
- Decode any `m4a/mp4/mov/webm` locally with PyAV, which bundles ffmpeg libs, straight to 16 kHz mono for Whisper. No transcode-for-upload is needed because nothing is uploaded.
- YouTube: captions via yt-dlp first, Whisper only as a fallback.
- Reject empty files and show readable errors as typed codes (`empty-file`, `too-large`, `unsupported-type`), like their `d(code, msg)` errors.

### Not adopted (and why)

- Credits / paywalls / drops funnels (free product).
- 3D Memory Palace and runner games (heavy three.js, low learning value).
- Brainrot and persona voices ("Prof Profane"): off-mission.
- Client-side video export (WebCodecs) and video overviews (expensive, low value for a voice tutor).
- Public share links (local-first, and no chat or personal data on any public page).
