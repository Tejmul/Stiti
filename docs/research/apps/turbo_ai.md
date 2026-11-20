# Turbo AI / Turbolearn: feature inventory for Stiti's tutor

Researched 2026-11-20. This is a design study only. No proprietary code or content was copied, nothing was logged into, and no app code was inspected. REA was not used: the public marketing pages, store listings and hands-on reviews were enough, and nothing here needs a logged-in UI.

## 0. Identifying the product

- **The product:** turbo.ai, sold by **TurboLearn LLC / TurboLearn, Inc.** It was founded by Sarthak Dhawan and Rudy Arora (Duke and Northwestern dropouts) and launched in early 2024 as "TurboLearn AI".
  - It was renamed **"Turbo AI"** in late 2025. On **2026-11-16** it went back to **"Turbolearn"**. The domain stays turbo.ai, and turbolearn.ai redirects there.
  - Sources: the blog post "Turbo AI is now Turbolearn" (https://www.turbo.ai/blog/turbo-ai-is-now-turbolearn) and the AIxploria history (https://www.aixploria.com/turbolearn-ai-notetaking/).
- **How I picked it among same-name products:**
  1. It is the product TechCrunch covers as "AI notetaker Turbo AI" with 5M users (https://techcrunch.com/2025/10/23/20-year-old-dropouts-built-ai-notetaker-turbo-ai-to-5-million-users/).
  2. Its blog claims **10M learners** (July 2026). Its App Store listing has **4.75★ from about 34.6k ratings** (iTunes lookup API, 2026-11-20; app id 6502794561, version 1.5.14 released 2026-11-16).
  3. Android package `ai.turbolearn` shows **2M+ installs and a 4.7★ rating** on mirror sites.
- **Excluded look-alikes:**
  - **TurboScribe:** a transcription-only service.
  - **"TurboLearn AI Note Taker Pro"** (App Store id 6745137452): developer "Do Anh", now titled "SuperLearn". This is an unrelated copycat.
  - **Linguix Turbo** and other "Turbo" products that are not study tools.
- **Scale and business:**
  - About 20k new users a day (Oct 2025), eight-figure ARR, profitable, $750k raised, team of about 15 in Los Angeles (TechCrunch).
  - Core users are students. Professionals (consultants, lawyers, doctors, analysts) are a growing group.
- **Models:** The Terms of Service (effective 2026-05-27) say outputs are made with third-party AI: "Grok, Claude, OpenAI, Anthropic, Together AI, Google, and Modal Labs", and that they "may change AI tools at any time" (https://www.turbo.ai/terms-of-service).
  - In other words, Turbo is a **multi-provider LLM wrapper**, the same "LLM is a plug" stance Stiti takes.
- **Stated philosophy (ToS preamble):** "enhance one's learning experience, not to replace the hard work and understanding". Academic dishonesty is banned.
  - TechCrunch positions it between manual tools (Google Docs) and fully automatic notetakers (Otter or Fireflies): you can "write alongside" the AI.

## 1. The core loop

**Source → notes (editable doc) → derived study objects (flashcards, quiz, podcast, lesson) → chat grounded in the note → sync and share.**

- Each upload becomes **its own folder/notebook** with notes, plus buttons for each study tool (Turbo vs ChatGPT post: https://www.turbo.ai/blog/turbo-vs-chatgpt).
- All study tools are made **from the note**, not from the raw source. That is why reviewers see errors **cascade**: a bad transcript gives bad notes, which give bad cards and bad quizzes (tl;dv review: https://tldv.io/ko/blog/turbo-ai/).

## 2. Feature-by-feature inventory

### 2.1 Live lecture recording → notes
- **What it does:** Records audio on the phone or the web ("one tap"). After the recording ends, it makes structured notes "with key points, timestamps, and highlights" (https://www.turbo.ai/ai-note-taker).
- **Trigger:** "Record or Upload Audio" on the dashboard (tl;dv). It records device audio directly; no meeting bot joins a call.
- **Output:** Notes with headers, key terms and concepts. A transcript is under "Uploaded content → Full Transcript". Timestamps are shown as numbers.
- **Mechanics:** Batch processing after recording. A one-hour recording gave notes in about 1 minute (tl;dv). No source says notes appear live during the lecture.
  - UPDF says "the app must stay open during recordings".
  - The audio file is kept, and "playback alongside the chatbot" was promised as coming soon (maker reply on Product Hunt: https://www.producthunt.com/products/turbo-ai-turbolearn-ai-2).
- **Limits and complaints:**
  - tl;dv recorded a Russian language lesson. The transcript was "completely unusable": garbled, with no speaker labels and mixed or translated languages. Notes called the student "the lecturer" and listed languages never spoken. Timestamps were not clickable and pointed to the wrong places.
  - TechCrunch: **uploads now outnumber live recordings**, because lecture halls are noisy.
  - Unanswered Product Hunt question: how does it handle heavy accents and dense spoken math?
- **Praise:** Fast, and lets you "listen instead of scribble" (the founder's origin story).

### 2.2 Upload → notes (PDF, DOCX, slides, YouTube, websites, video, text)
- **What it does:** You drag and drop a file, paste a YouTube link or start from a blank page. You can also say which part of the source you need (Unite.ai, 2026-11-15: https://www.unite.ai/turbolearn-ai-review/).
- **Output:** Notes with an overview, key points, definitions, **tables** (for example a "hypothesis table" or "key terms table"), **captioned figures**, rendered equations, emojis and "diagrams" (Turbo vs ChatGPT; AIxploria).
  - The FAQ claims support for "math formulas, chemical equations, physics diagrams, and code snippets" (https://www.turbo.ai/).
- **Multi-file:** tl;dv uploaded up to 5 PDFs into one combined note. Coverage was uneven: PDF 1 got 9 subsections, PDF 2 got 4, and PDFs 3–5 were **silently skipped** until the reviewer asked for them.
- **Complaints:**
  - Scanned or image PDFs work poorly (mspoweruser, UPDF), although the maker claims handwritten and scanned input works.
  - Tables and graphs inside PDFs are read badly (App Store review, Product Hunt).
  - Some notes "overstated the research paper's claims" (Unite).
  - The layout is fixed and hard to customise (older Unite/UPDF reviews).

### 2.3 Notes editor ("Google Docs style") + AI co-writer
- **What it does:** A rich-text editor with headings, bullets, equations, tables, **version history** and real-time sharing (Unite).
  - The AI "works alongside you by making comments, suggestions and rewrites" ("Edit alongside AI in real-time with smart suggestions": https://www.turbo.ai/for-students).
- **Organisation:** Smart folders that sync across devices. Turbo can also auto-organise ("integrations coming soon").
- **Export:** Notes can be "exported to an external notebook" (Turbo vs ChatGPT). Formats are not documented. The only download advertised on a public page is the podcast (macaron guide: https://macaron.im/blog/how-to-use-turbolearn-ai).
- **User asks:** Cornell-style notes, editable summaries, and image generation for graphs (App Store reviews).

### 2.4 AI chat with your material ("Chat with Turbo" / "Talk to Turbo")
- **What it does:** A side-panel assistant inside each note that indexes and "deeply comprehends" it (ai-note-taker page).
  - **"@" mentions bring in other documents.**
  - **"Talk to Turbo" is a voice mode** (Unite, Nov 2026).
  - Answers match the level of the material (Turbo vs ChatGPT).
- **Trigger:** "Chatbot" in the left toolbar, then type (UPDF), or the panel next to a note.
- **Complaints:**
  - **Confident wrong answers when the notes lack the detail** (Unite). This is the classic failure of grounded chat with no "I don't know".
  - No chat history (App Store review, Jan 2025).
  - The free tier is about 10 messages a month (UPDF; not confirmed by Turbo).

### 2.5 Flashcards
- **Trigger:** The "Flashcards" button on a note.
- **Options:** Sets of **10/20/30/50** cards, plus a free-text instruction box (Unite). tl;dv asked for 30 and got 43.
- **Output:** Flip cards (question on the front, answer and explanation on the back), navigated with arrow keys.
  - Progress buckets are **New → Learning → Mastered** (Unite, AIxploria).
  - Marketing claims "Smart spaced repetition adapts to your pace; track progress and identify weak areas" (for-students page). No reviewer describes a real schedule (due dates, intervals). It looks like a Leitner-style bucket system rather than FSRS/SM-2. That is my inference.
- **Praise:** Cards respond well to custom prompts (tl;dv).
- **Complaints:** Default cards inherit hallucinations from the transcript. Some cards are ambiguous with no context, for example a card that just says "Accusative case" (tl;dv).

### 2.6 Quizzes / practice questions
- **Trigger:** The "Quiz" button. Quiz Settings allow **custom topics** and **short-answer questions** (Unite).
- **Types:** Multiple choice, fill-in-the-blank, short answer, and open-ended "explain" prompts (homepage).
- **Settings:** Marketing says you can pick topics/chapters and set difficulty "from basic to exam-level"; questions are unlimited (for-students page).
- **Mechanics:**
  - Questions are **grouped by topic**, with **hints** and **explanations that address the specific wrong answer**.
  - **Missed questions come back** later in the quiz. This is an adaptive re-queue (Unite).
  - Homepage tagline: "Endless questions until you lock in understanding."
- **Complaints:**
  - Questions lean on calculation and repeat concepts. Some formulas render badly (Unite).
  - From audio sources, questions were off-context and one was malformed. Quiz from audio had no prompt option (tl;dv).
  - "Quizzes aren't always that helpful" (Play reviews via mirrors).
  - The free tier is about 5 quizzes a month (UPDF).

### 2.7 Generate Lesson / Learn Mode / Microlearning (the newest and most relevant feature)
- **What it does:** "Generate Lesson" builds a **structured interactive lesson** from a source. It has a contents list of sections that follow the source order, **warm-up questions, knowledge checks between sections, and a final quiz**.
  - A 40-minute lecture became an **11-section lesson in under a minute** (Unite, 2026-11-15).
- **Learn Mode** (July 2026) "turns anything from as little as a few simple words into a structured course" (https://www.turbo.ai/blog/july-2026-announcement-10-million-users). It is topic-to-course with no source upload. Unite also describes making a course "through chat".
- **Microlearning:** "bite-sized lessons on topics of personal interest… instead of passive scrolling" (App Store). Version 1.5.13 (Nov 2026) notes say "added more lessons and better audio".
- **Complaints:**
  - Wrong-answer feedback inside lessons **only shows the correct answer**, with no explanation (Unite).
  - The free plan allowed **one lesson** (Unite).

### 2.8 Podcasts (two-host audio overview)
- **Trigger:** The "Podcast" option. You choose the **language, two of five voices, length (quick summary / deep dive, or short/medium/long), depth (overview / detailed)** and **custom instructions** (Unite; for-students page).
- **Output:** A two-host conversation with **chapters and a transcript**, downloadable for offline listening.
- **Complaints:**
  - Voice choice is "extremely limited". Podcasts can't be edited (App Store review).
  - Foreign words are read phonetically by English voices. tl;dv found it "gimmicky" for language learning.
  - It repeats any errors in the note (macaron).
- **Praise:** Professionals turn reports into audio for the commute (TechCrunch).

### 2.9 Summaries
Summaries are part of the notes overview and the "exam cramming" use case: summaries, practice quizzes and flashcards "focused on key content" (App Store). There is no separate mechanism beyond the overview at the top of the note.

### 2.10 Pre-made library: AP study guides + books
- **Trigger:** "Study Guides" in the dashboard's left panel → pick an AP class → it is added to your dashboard.
- **Structure:** **One folder per unit**, each with detailed, editable notes (for example AP Calculus: limits → derivatives → integrals → differential equations), plus the same chat, flashcard, quiz and podcast tools (https://www.turbo.ai/blog/ap-calculus-study-guide).
- **Suggested exam-prep loop:** a weekly quiz on the current unit; before the exam, "re-quiz each unit, **rank the units by score**, and focus on the weakest sections."
- **Books library:** read, highlight and annotate textbooks, then make notes and flashcards from any chapter, with search across books (for-students page).

### 2.11 Turbolearn Anatomy (Oct 2026)
- A browser **3D anatomy explorer** (turbo.ai/anatomy). You search a structure to focus it, browse regions and systems, rotate and zoom, and **fade layers** to see what is underneath.
- It is labelled a "first version", uses one adult male model, and is "an educational reference, not a tool for clinical decisions" (https://www.turbo.ai/blog/introducing-turbo-anatomy).
- This is a first move into **subject-specific interactive visuals**.

### 2.12 Collaboration and sharing
Share in one click, see live co-editing and highlights, comment inline, and make a note public. The "AI assists everyone simultaneously" (for-students and ai-note-taker pages).

### 2.13 Platforms, languages, sync
- **Platforms:** Web, iOS/iPadOS 16.4+ and Android 8+, with real-time sync.
- **Languages:** The app and website are **English only** (App Store; AIxploria). Podcasts let you choose a language. Support for transcribing or writing notes in other languages is not documented. tl;dv wanted transcripts in the spoken language but notes in English, and it did not work well.
- **UI:** Dark mode by default. One reviewer switched to light mode for readability. There is no onboarding guide, and flashcards were hard to find (tl;dv).

### 2.14 Pricing and paywall (a big complaint)
- **Plan:** One paid tier, "Turbolearn Unlimited".
  - App Store prices: 1 week $9.99; 1 month $14.99–$19.99; 1 year $19.99–$119.99; promo "50% off forever" $7.49/month (App Store listing).
  - Per Turbo's own blog: $20/month monthly, or $10/month annual ($120/year).
  - Prices are **A/B tested**. There is **no public pricing page** (turbo.ai/pricing returns 404), and "all sales are final" (Zemith: https://www.zemith.com/en/contents/is-turbo-ai-worth-it).
- **Free tier:** About 2 hours of lecture, 1 PDF, 5 quizzes and 10 chats a month (UPDF; unconfirmed).
- **Complaints:**
  - Blocked after the first upload (App Store, Jul 2025).
  - Cut off mid-quiz with no usage meter (tl;dv).
  - One free lesson only (Unite).
  - Support is email only, with about 48 h response (https://www.turbo.ai/support).

## 3. What students praise and complain about overall

**Praise:**
- Speed (an hour of audio becomes notes in about 1 minute).
- Clean, skimmable notes with good math rendering.
- Many input types.
- Everything in one place (notes plus cards plus quiz plus podcast).
- Explanations aimed at the specific wrong answer.
- Prompting works for cards.
- Syncs across devices.

**Complaints:**
- Hallucinations and errors that **cascade** from source to notes to study objects.
- Gaps skipped silently in multi-file summaries.
- Weak transcripts (no speaker labels, poor with mixed languages).
- Confident wrong chat answers.
- Repetitive quizzes.
- Aggressive, unclear paywalls with no usage meter.
- English only.
- Limited podcast voices.
- No chat history.
- Weak on scanned PDFs and tables.

## 4. Lessons for Stiti

1. **"Learn Mode" is the right direction.** Turbo started as a notetaker and is pivoting to *structured teaching*: sections, warm-up, check-per-section, final quiz, and topic-to-course. Stiti's coach (concepts → teach → ask) already does this more deeply, because it keeps **per-concept mastery** across sessions. Turbo only has a quiz score per upload and card buckets.
2. **Make study objects from verified concepts, not raw transcript.** This avoids Turbo's error cascade.
   - Stiti should **ground every generated card, probe or answer in the source chunk ID**.
   - It should say "that's not in your file" instead of answering confidently.
   - It should show a **coverage check**, for example "I covered 5 of 5 files; file 3 had only 2 concepts".
3. **Explanations aimed at the wrong answer + re-queue of misses** is the single most praised quiz mechanic. Stiti can do both by voice.
4. **Rank weak units → focus** (from the AP guide loop) maps directly onto exam mode.
5. **Audio overview with chapters** is cheap with Kokoro, and works offline by nature.
6. **Avoid their mistakes:** paywall surprises (not relevant to Stiti), English-only (Stiti speaks English and Hinglish), unclickable timestamps, no chat history (Stiti keeps memory forever).

## 5. Adoption table

| Feature | Value for a voice whiteboard tutor | Doable free + local-first on 8 GB M2? | Rough build idea in Stiti terms |
|---|---|---|---|
| Generate Lesson (sections + warm-up + per-section check + final quiz) | **High** | Yes: one free-tier LLM call per section, with the plan cached locally | Coach turns the file's concept map into an ordered lesson plan (`lesson.json`). For each concept: a warm-up probe, a 60–90 s whiteboard teach, then a check question. Final mixed quiz updates per-concept mastery in Postgres. Show the plan as a contents rail on the whiteboard. |
| Learn Mode (few words → course) | **High** | Yes: LLM outlines the topic into a concept graph; Wikimedia supplies pictures | "Teach me X": the coach builds a concept graph with no file (LLM outline → nodes/edges in the graph tables), then runs the same lesson loop. Mark concepts as "unsourced" so later doubts flag lower confidence. |
| Adaptive quiz: topic grouping, hints, explanation aimed at the wrong answer, misses re-queued | **High** | Yes: re-queue and hint logic are local; only the explanation needs an LLM, and it is short | Probe engine: on a miss, Laya classifies the error type and the LLM gives a one-sentence fix aimed at *that* answer. Push the concept back in the queue at +3 items and lower its mastery. Hint ladder by voice: nudge → partial → answer. |
| Grounded chat with the material (+ "@" other docs, voice "Talk to Turbo") | **High** (this is the doubt mode) | Yes: pgvector + FTS retrieval under 100 ms, then a free LLM | Doubt answering: retrieve chunks from the active file (and an "@ other file" by voice: "also look in my physics notes"). Answer must quote the chunk ID. Below a retrieval-score threshold, say "not in your file; here's general knowledge" (this fixes Turbo's confident-wrong failure). |
| Flashcards with New→Learning→Mastered + "spaced repetition" | Med–High | Yes: FSRS (py-fsrs) is tiny and runs locally | Turn mastered concepts into voice recall cards. Use FSRS due dates per concept, not per card. "Day mode" opens with due cards spoken aloud. Show bucket counts on the whiteboard. |
| Rank weak units → focus (AP exam loop) | **High** (exam mode) | Yes: a pure SQL query over mastery | Exam mode: sort concepts by mastery × exam weight, then drill the bottom 5 first. Spoken "you're weakest on X, Y" briefing. |
| Structured notes with tables, key terms, equations, captioned figures | **High** (whiteboard output) | Yes: markdown + KaTeX locally; LLM drafts the structure | Whiteboard "notes page" template: overview, key-terms table, formula box, one Wikimedia figure with caption and licence, then save as markdown in `~/.stiti`. |
| Version history + editable notes + AI suggestions | Med | Yes: git-like snapshots of the markdown files | Keep each saved note revision (simple timestamped copies or a local git repo). Voice edits: "change that definition to…". |
| Coverage check across multiple uploaded files | **High** (trust) | Yes: count concepts per source chunk, locally | After mapping, Stiti says "File 3 produced only 2 concepts. Want me to look again?" Never skip silently. |
| Lecture recording → notes | Med (Stiti is a tutor, but "record my class" is useful) | Partly: Whisper on an M2 is fine for short clips; long lectures should run in the background in chunks | Background job: chunked Whisper (small/turbo) → transcript → concept map → notes page. Clickable timestamps, which Turbo gets wrong: link each note line to its audio offset. |
| YouTube / web / PDF / DOCX ingest | Med–High | Yes: yt-dlp captions, pypdf, python-docx, all local | Feed into the existing file → concept-map pipeline. Captions first, Whisper only when there are no captions. |
| Podcast / two-host audio overview with chapters | Med (good for revising on the go) | Yes: Kokoro has several voices; script from a free LLM; render offline | "Revise X as audio": an LLM writes a two-voice script from the concept map plus mastery (focus on weak concepts), Kokoro renders it, and it is saved as MP3 with chapter markers. Unlike Turbo, it is personalised to weak spots. |
| Summaries / cram sheet | Med | Yes | Exam-mode "one-page cram sheet" made from the concept map on the whiteboard. |
| Pre-made AP study-guide library | Low (copyrighted content; Stiti is personal) | Not applicable | Skip. Learn Mode for any syllabus topic covers the need. |
| Books library (read, highlight → cards) | Low–Med | Content: no. Mechanism: yes, for the learner's own PDFs | Highlight in your own PDF → concept → card. No library. |
| 3D anatomy explorer | Low (niche) | Heavy for 8 GB in a browser; skip | Use Wikimedia diagrams with labelled callouts on the whiteboard instead. |
| Real-time collaboration and public sharing | Low (single user, local-first) | Against local-first | Skip. At most, export a note as markdown or PDF. |
| Export (notes, cards) | Med | Yes | Markdown is already the source of truth. Add an Anki `.apkg` export (genanki) and PDF from the whiteboard. |
| Multi-language podcast/notes | Med (Hinglish) | Kokoro covers English and Hindi voices; Whisper is multilingual | Mirror the learner's language by voice (D51 English default, Hinglish in mirror mode). |
| Usage caps / paywall | Not applicable (negative example) | — | Stiti is free. Show provider quota health instead of surprise failures. |

## 6. Top 5 to adopt (priority order)

1. **Lesson structure from Generate Lesson / Learn Mode:** a contents rail, warm-up, per-section check and final quiz, plus topic-to-course with no file.
2. **Adaptive probing:** explanation aimed at the wrong answer, a hint ladder, misses re-queued, and mastery updated per concept.
3. **Grounded doubt chat with an honest fallback** and voice "@ other file". Fix Turbo's confident-wrong failure with a retrieval threshold and quoted source chunks.
4. **Exam mode "rank weak units → drill"** plus FSRS-scheduled voice recall cards in day mode.
5. **A structured whiteboard notes page** (overview, key-terms table, formulas, captioned real picture, coverage check), saved as markdown, with an optional two-voice Kokoro audio recap focused on weak concepts.

## Sources (checked 2026-11-20)

- Official: https://www.turbo.ai/ · https://www.turbo.ai/for-students · https://www.turbo.ai/ai-note-taker · https://www.turbo.ai/support · https://www.turbo.ai/terms-of-service · https://www.turbo.ai/blog · https://www.turbo.ai/blog/turbo-ai-is-now-turbolearn · https://www.turbo.ai/blog/july-2026-announcement-10-million-users · https://www.turbo.ai/blog/introducing-turbo-anatomy · https://www.turbo.ai/blog/turbo-vs-chatgpt · https://www.turbo.ai/blog/ap-calculus-study-guide · https://www.turbo.ai/blog/cant-keep-up-during-lectures
- Stores: https://apps.apple.com/us/app/turbo-ai-learn-faster/id6502794561 · https://play.google.com/store/apps/details?id=ai.turbolearn · copycat (excluded): https://apps.apple.com/us/app/turbolearn-ai-note-taker-pro/id6745137452
- Press and reviews: https://techcrunch.com/2025/10/23/20-year-old-dropouts-built-ai-notetaker-turbo-ai-to-5-million-users/ (blocks bots; read via a fetcher) · https://www.unite.ai/turbolearn-ai-review/ (hands-on, 2026-11-15) · https://tldv.io/ko/blog/turbo-ai/ (hands-on, 2026-03-19) · https://www.producthunt.com/products/turbo-ai-turbolearn-ai-2 · https://www.aixploria.com/turbolearn-ai-notetaking/ · https://macaron.im/blog/how-to-use-turbolearn-ai
- Competitor-authored (treat with care): https://www.zemith.com/en/contents/is-turbo-ai-worth-it · https://updf.com/chatgpt/turbolearn-ai-review/
- Not reachable or not verified: mspoweruser review (403), aigearbase free-cap figures (cited by Zemith, unreachable). Reddit could not be searched directly (the domain is blocked for this crawler), so Reddit sentiment is second-hand via AIxploria.

## REA evidence (public pages)

Added 2026-11-20. This pass **did use REA**, so the "REA was not used" note at the top only applies to sections 0–6.

**Method and rules.** I used a throwaway, logged-out headless Chrome over CDP and opened public marketing pages only. I did not log in, sign up, or bypass anything. REA inspects without running code: it read the DOM and accessibility tree, the script sources Chrome had already loaded, and listener locations, and it took screenshots. Nothing was clicked and no page JavaScript was run.

I scanned the exported scripts with plain text search for vendor and feature strings. No code is copied here; only names, shapes and design facts are recorded.

**Secrets.** The bundles contain public client-side keys: a PostHog project key, an ipdata.co geo-IP key, a Better Stack ingest token, Stripe price IDs, and GTM, Google Ads and Churnkey IDs. They are shipped to every visitor by design, but I left them all out of this doc on purpose.

**Prompt injection.** None found. Page text and script strings contained no instructions aimed at agents. PostHog's bot list contains "Claude/" and "ChatGPT/" user-agent strings; those are only used to detect bots.

### Evidence index

| What | REA evidence id |
|---|---|
| Home `/`: DOM + accessibility + resources | `ev_329ea3ca7c03560ea9ac26b98acff9728dbc76a0405f5e3b58e9632f5a3aefe0` |
| Home with script sources (2.1 MB capture) | `ev_f50db734f1afa0d683ae6cfbc3e7f3c7a5b84913ce0f06ac9a5ee564fdaab032` |
| Script export of that capture (37 scripts, manifest) | `ev_e8c14d8f5b791a0e8f0d7674a62473d934d7c4e4c19beb6a22069cd21c6fe46f` |
| `analyze_web_bundle` on home (complete) | `ev_f5b5da7b1d322a58737354d018ed1ada939d6be34d8a95d0b400ebf219b591c5` |
| Same bundle: javascript-routes summary / routes views | `ev_4d70e0f66c5ff2ec7e065a20268ea32734d6512dab71fce26827546dac863cd4` / `ev_d76a62a022cf292183ae562074b63981659db8b78d36d1d860afb6241682eef6` |
| `/for-students` page / bundle (routes view parent) | `ev_2e42fb2a985b2d6f2200561747460c2554fe3820cee244e4697037f6b1f2ca88` / `ev_194d4cc2379c7ef2e6a184687c35da6f9e0e3609795913db23ed4b8241a52c2d` |
| `/ai-note-taker` | `ev_23e1624470fbbc4e0d61464c8fe699533b23aba9a7aace14e148373e189e99e4` |
| `/anatomy` → redirected to `/login` (gated; inspected only the login shell, then closed it) | `ev_4a3cc6a4677b9543ee6dfa8bdc191f12c59a5290e38230708fe2f2c72d78d434` |
| `/blog` index; July-2026 "10M users / Learn Mode" post | `ev_d81dcfb1f145743fdf64953bd160f75c756e6c5ff1cec276fc0684b9cb71a95f`; `ev_e2d259ce98c8db9681b5aa7006c8aff798bbdd81a062dbe2c07d1ab174e191ff` |
| `/support` | `ev_bf7d4b5f9eb75e5448ebe190772f9e826c21b01ec8ae27fb05bdff3fd951f77d` |
| Listeners: podcast-demo `<audio>`; "Next flashcard" button | `ev_3a28747356e4d5ee64bff4ebd267915fdf248efee12079d1b6df3cbdf29ea3d7`; `ev_9f99e8f9d31f4e36c3289009cecd7b8bd14a686cdfb3c7d6d0fa86417c554c52` |
| Screenshots: home hero; for-students hero | `ev_02b151e9042ce961347b04850b3ec2435f8b8edea5012956990c9b49b7af650d`; `ev_8db2356c4f381ac9a4fe3691a05643358a327a3af9511f7a33f66b75bdb5b32c` |

**Why the marketing pages reveal the app.** The marketing site and the app are one Next.js deployment. All pages share the root layout chunk `app/layout-*.js` and several large shared chunks. Those chunks carry the app's data layer, analytics event catalogue and paywall code.

That is why a logged-out home page shows how the logged-in app is built. All of it comes from static strings. None of it was observed running: REA reports `network.requests: []` for every capture, so no app API traffic was seen.

### Tech stack (fingerprints)

**Frontend**
- **Next.js App Router on Vercel**, with React and Tailwind:
  - `analyze_web_bundle` inferences give `vendor_fingerprint: Next.js` (detector `next-runtime`, high) and `React` (`react-runtime`).
  - Assets carry `?dpl=dpl_…` deployment IDs, and `/_vercel/insights/script.js` is loaded.
  - Route groups include `app/(marketing)/layout`, `app/(marketing)/for-students/page`, `app/page` and `app/global-error`.
  - Server actions are used: a `callServer` reference named `fetchStripePrices`.
- **React Compiler output:** `react.memo_cache_sentinel` and `useMemoCache`-style `c(n)` slots appear everywhere.
- **UI kit:**
  - Radix primitives, with a Radix dialog overlay class.
  - `sonner` toasts (126 hits).
  - `framer-motion`-style layout animation.
  - Lottie (377 hits) and Rive (37 hits) for animation. The mascot bird is likely Rive; that is an inference.
  - Self-hosted `next/font` TTF/WOFF2 files (resources list).

**Auth: Supabase**
- Sign-in methods: email + password, **magic link** (`POST /api/send-magic-link {email,userId}`), Google and Apple OAuth.
- **Anonymous-first sessions:** `auth.signInAnonymously()`, then `auth.linkIdentity({provider:"google"})` upgrades the anonymous user in place. The analytics events include `anonymous_session_started`.
- `/login` shows Google, Apple, email/password and "Forgot password?".

**Writes: Supabase Edge Functions on a custom domain** (`api.turbolearn.ai/functions/v1/…`)
- `content-insert`, `content-update`, `folder-insert`, `folder-update`, `folder-delete`, `last-opened-insert`, `last-opened-update`, `student-update`.
- `lessons-insert` / `-update`, `lesson-sections-insert` / `-update`, `lesson-pages-insert` / `-update`.
- Each call carries a `Bearer <supabase access_token>`. `content-insert` uses a `keepalive` fetch for small bodies (<60 kB), so a save survives closing the tab.

**Reads: live sync with ElectricSQL "shapes" + TanStack DB**
- Shapes are served from `electric-production.workers-turbo.ai/v1/shape`. The bundle includes the Electric client (`electric-handle` / `electric-offset` / `electric-cursor` headers, SSE `text/event-stream` live mode, and "MissingShapeHandle" errors).
- TanStack DB collections (`@tanstack/db`, `useLiveQuery`) are named `content`, `folders`, `students`, `last_opened`, `lessons`, `lesson_sections` and `lesson_pages`.
- Each collection pairs an Electric shape (read) with `onInsert` / `onUpdate` handlers that call the matching edge function (write). This gives **optimistic local writes with server confirmation**, a local-first client on top of Postgres.
- A 401/403 on a shape refreshes the Supabase session and retries.

**Server functions: Modal**
- `*.modal.run` endpoints handle collaboration ACLs: `accept-invitation`, `create-collaborator-acl`, `update-collaborator-acl`, `remove-collaborator-acl`, `sync-acl` and `get-collaborators`.
- The `content` row has a `modal_slug` column, and an event is named `modal_request_proxied`. Content processing (transcription, notes generation) most likely runs on Modal, which fits the ToS listing "Modal Labs". That is an inference.

**Analytics**
- **PostHog** is configured with `autocapture:false` and manual pageviews, and it serves feature flags (`$enabled_feature_flags`).
- A first-party **"TurboAnalytics" SDK, v2.7.1**, posts to `api-production.workers-turbo.ai`:
  - `/api/init?platform=` fetches flags; `/api/sync` posts event batches.
  - It batches 100 events or every 30 s, retries up to 11 times, keeps a 512 kB offline queue and a 30-min session timeout.
  - Failed batches go to a **dead-letter** sink at Better Stack.
- Every event carries a typed context: `student_id`, `country_code`, `user_type`, `subscription_tier`, `subscription_source` and `is_anonymous`.

**Payments**
- **Stripe** custom checkout (`/api/stripe/create-checkout-session`), with Elements card form, express pay, promo codes and trial days.
- **Regional pricing:** an ipdata.co geo-IP lookup feeds per-country Stripe lookup keys. A discount popup is shown only in eligible countries. The default price pair is $20/month monthly or $10/month on the yearly plan, which matches section 2.14.
- **Churnkey** runs the cancel flow.

**Ads and attribution**
- GTM / Google Ads, a TikTok pixel, and events for mobile attribution links (`visited_mobile_attribution_link_meta` / `_tiktok`).

**AI, ASR and TTS vendors:** none appear in any public bundle; all model calls are server-side. Turbo is also a client of an **audio service** (`encountered_audio_service_error`). The model list stays as the ToS gives it (section 0).

### Route and feature map

**Routes**
- **Public routes (REA javascript-routes + DOM links):** `/`, `/for-students`, `/ai-note-taker`, `/blog`, `/blog/<slug>`, `/careers`, `/support`, `/privacy-policy`, `/terms-of-service`, `/login`, `/signup`.
- **Gated routes:** `/dashboard` (the CTA switches to "Continue learning →" when logged in), `/anatomy` (redirects to `/login`), and `/pricing` (404, see section 2.14).
- **App page names**, from the `viewed_*` events, are a proxy for the logged-in screens:
  - dashboard, folder, note, source, flashcards, quiz, podcast
  - lesson home, document chat, catalog, study guides, draft uploads
  - onboarding (with steps), account settings, and a shared-lesson gate

**Data model** (the `content_all` shape's column list and the lesson collections' insert payloads)

- **`content`** is one row per upload or note. Columns:
  - `content_id`, `student_id`, `folder_id`, `content_type`, `content_title`, `class_subject`
  - `content_status`, `current_generation_step`, `percent_completed`, `eta_seconds`, `error_message`, `not_enough_credits`
  - `file_link`, `multi_file_links`, `yt_video_id`, `device_type`, `duration`
  - `is_public` / `is_public_view` / `is_public_edit`, `is_system_generated`, `source_catalog_item_id`
  - `note_priority_index`, `pm_schema_version`, `modal_slug`, `uploaded_at` / `created_at` / `last_modified`, `is_deleted`
  - Every upload is therefore a **job row with a visible pipeline state** (step, %, ETA, error). Notes are rich-text documents with a schema version: `pm_` suggests ProseMirror/Tiptap, which is an inference.
- **`lessons`**: `{lesson_id, content_id, student_id, lesson_status}`. **`lesson_sections`**: `{section_id, lesson_id, title, content, index}`. **`lesson_pages`**: `{page_id, lesson_id, index, type, payload, status}`.
  - A lesson is an ordered list of **typed pages with a JSON payload and a per-page status**. This is the backbone of "Generate Lesson" and Learn Mode.
- **`last_opened`** is keyed `student_id + object_type + object_id`; it powers "Jump back in".

**Feature catalogue.** The first-party analytics catalogue has 303 call sites and about 290 distinct event names, shipped in the shared chunk. Grouped:

- **Lesson generation (streamed by section):**
  - `pressed_generate_lesson`, `generate_lesson_prepared`, `watched_lesson_generation`
  - `section_generation_started` / `succeeded` / `failed` / `stalled`, `waited_for_section_generation`, `waited_for_generating_page`
  - `clicked_lesson_stream_jump`, `pressed_retry_lesson_generation`, `lesson_start_ensured`
  - `created_lesson_from_chat`, `failed_lesson_generation_kickoff_from_chat`, `lesson_source_upload_succeeded` / `failed`
- **Lesson play:**
  - `started_lesson_section`, `completed_lesson_section`, `exited_lesson_section`, `clicked_lesson_section_row`
  - `answered_lesson_question`, `lesson_question_wrong_attempt`, `toggled_lesson_feedback_detail`
  - `pressed_lesson_continue`, `pressed_lesson_jump_back_in`, `clicked_reset_lesson_progress`, `finished_lesson_review`
  - `completed_entire_lesson`, `clicked_lesson_celebration_cta`, `lesson_progress_persist_failed`
  - `submitted_learn_ask_box`, `resized_learn_side_panel`
- **Lesson audio:**
  - `lesson_audio_generation_requested` / `failed`, `pressed_lesson_audio_button`, `toggled_lesson_audio_playback`
  - `changed_lesson_audio_speed`, `seeked_lesson_audio`, `lesson_audio_completed`
  - `previewed_lesson_voice`, `started_listening_lesson_page`
- **Voice:**
  - `started_voice_chat` / `ended_voice_chat`, `toggled_voice_persona`, `voice_chat_capped`, `voice_chat_paywalled`, `voice_chat_error`
  - Chat dictation: `started_chat_dictation`, `confirmed_chat_dictation`, `cancelled_chat_dictation`
  - Paywall placements show voice chat exists in both **lessons** (`lesson_voice_chat`) and **notes** (`notes_voice_chat`).
- **Podcast:**
  - `clicked_generate_podcast`, `toggled_podcast_playback`, `seeked_podcast_position`, `changed_podcast_playback_rate`
  - `skipped_podcast_playback`, `downloaded_podcast`, `shared_podcast`, `opened_podcast_chat`
  - **`clicked_podcast_raise_hand`** (interrupt the podcast and ask), gated as the premium placement `raise_hand`. Podcast lengths and voices are also premium placements.
- **Chat:**
  - Chat opens from four places: folder, note page sidebar, flashcards and quiz, each with a fullscreen toggle.
  - Context: `added_chat_mention` / `added_doc_chat_mention` (@-mention docs), `added_chat_attachment`, `added_chat_quote_attachment`, `highlighted_source_to_chat`, `highlighted_pdf_text_to_chat_page`
  - Citations: **`clicked_citation_badge`**, `clicked_mention_go_to_note`
  - Agent: `answered_chat_tool`, `cancelled_chat_plan`, plus the paywall placement `plan_execution_limit`. Chat runs **plans and tools**.
  - Control: `stopped_chat_generation`, `retried_chat_message`, `retried_chat_execution`
  - Guard: `context_regression_blocked`
- **Quiz:**
  - `clicked_generate_quiz_topics`, `added_quiz_topic` / `deleted_quiz_topic`, `changed_quiz_topic_selection`, `changed_quiz_question_type`
  - `clicked_show_quiz_hint`, `clicked_show_quiz_explanation`, `selected_quiz_answer_choice`, `submitted_quiz_answer`
  - **`achieved_quiz_mastery`**, `reset_quiz_progress`
- **Flashcards:**
  - `clicked_generate_flashcards`, `flipped_flashcard`, `toggled_flashcard_shuffle`, `toggled_flashcard_favorite`, `changed_flashcard_filter`, `changed_flashcard_front_card`
  - **"learn mode" with typed answers:** `toggled_flashcard_learn_mode`, `submitted_flashcard_learn_mode_response`, `completed_flashcard_learn_mode`
  - Editing: `entered_flashcard_edit_mode`, `added_flashcard`, `deleted_flashcard`, `exported_flashcards`, `reset_flashcard_progress`
- **Recording:**
  - `opened_recording_dialog`, `changed_recording_device`, `started_recording`, `paused_recording`, `resumed_recording`, `stopped_recording`, `cancelled_recording`, `failed_recording`, `denied_microphone_access`
  - **Drafts:** `recording_saved_to_drafts`, `saved_recording_draft_audio`, `played_recording_draft`, **`repaired_recording_draft`**, `discarded_recording_draft`, `viewed_draft_uploads_notice` / `page`, `uploaded_recording`
- **Content pipeline:**
  - `submitted_note_generation`, `selected_note_processing_option`
  - `content_processing_kickoff_attempted` / `succeeded` / `failed` / **`reconciled`**, `pressed_retry_content_processing`, `content_insert_traced`, `loaded_note_content`
- **Notes editor:**
  - `applied_note_text_format`, `changed_note_heading`, `inserted_note_table`, `opened_note_editor_math_dialog`
  - `uploaded_note_image`, `added_note_source` / `removed_note_source`, `switched_source_tab`, **`restored_doc_version`**, `clicked_export_pdf_button`
  - Comments: `added_note_comment`, `resolved_note_comment`, `deleted_note_comment`
- **Engagement signals:** `page_active_heartbeat`, `tab_switched_away`, `tab_switched_back`, `flag_exposure`.
- **Paywall placements** (an enum of 24 values):
  - Sidebar and app bar.
  - `notes_generation_50_percent`: the paywall appears halfway through notes generation.
  - `note_blur_paywall`, `lesson_section_wall`, plus `*_not_enough_credits` for notes, chat, podcast and lesson.
  - `chat_message_limit`, `plan_execution_limit`, `discount_popup`, `onboarding`.
  - This confirms the **credit-metered** model reviewers complain about.

### UI patterns (public pages, screenshots + accessibility tree)

- **Home hero (screenshot):**
  - The headline reads "The fastest way to learn anything." on a lavender textured background.
  - The right-hand card is a **drop zone** ("Drop files here · PDFs, videos, and recordings") with four input-type chips: DOCX, PDF, YouTube, mic.
  - A purple mascot bird perches on the card.
  - A single purple CTA reads "Start for free →", with the social proof "Join 10,000,000+ learners" and a logo strip below.
  - A hand-pointer animation demos a "Generate study materials" button.
- **For-students page:** a pill-shaped white nav and a single centred CTA, followed by **live mini-demos** for each feature:
  - A flip-card deck ("Use arrows to navigate • Click card to flip").
  - An MCQ ("Select an answer to see if you're correct").
  - A podcast player with ±15 s skip and a 0:00 timer.
  - A sample notes doc. It shows emoji section headings, a prokaryote/eukaryote **comparison table**, a formula line, and "Key Concepts to Remember" and "Important:" callouts.
  - Collaborator cursors ("Sarah", "You").
- **Listeners:**
  - The demo `<audio>` has React's standard media listeners plus the page's own `loadeddata` and `timeupdate` handlers. The progress UI is a custom bar driven by `timeupdate`, not native controls.
  - The flashcard "Next" button carries a single React `click` listener.
- **App UI hints from events:**
  - A resizable **learn side panel**.
  - A per-section **row list** for lessons, with a "stream jump" to the section being generated.
  - A celebration screen at the end of a lesson.
  - Voice **persona** toggle and voice preview.
  - A dashboard search dialog.

### API and streaming patterns

1. **Read path:** Postgres → Electric shape log over HTTP (initial snapshot, then `live` long-poll or SSE) → TanStack DB in-memory collections → `useLiveQuery` re-renders.
   - Progress fields (`percent_completed`, `eta_seconds`, `current_generation_step`, section and page `status`) therefore reach the UI **by row sync, not by a bespoke progress socket**.
2. **Write path:** an optimistic local mutation → a table-specific edge function `<table>-insert` / `<table>-update` → the row comes back through the shape stream, which confirms it via txid.
3. **Long jobs:**
   - An idempotent "kickoff" call is followed by a **reconciler** (`content_processing_kickoff_reconciled`, `lesson_start_ensured`).
   - Watchdog events (`section_generation_stalled`) and explicit retry buttons back it up.
   - Lessons are generated **section by section** while the learner watches or starts reading.
4. **Telemetry:** batched, retried, persisted offline, with a dead-letter sink, and typed per-student context on every event.

## Techniques for Stiti

Free, local-first, 8 GB M2 and no local LLM throughout. File paths are where each piece would live in the current tree. Every item gets its own branch and PR, per the build-order rules in `../teaching_apps.md`.

### 1. Lessons stream in section by section (start teaching before the plan is finished)

- **Turbo's technique:** `lessons → lesson_sections → lesson_pages(type, payload, status)`.
  - Sections are generated one at a time, each with started / succeeded / failed / stalled states.
  - The UI lets the learner start section 1 and "jump" to whichever section is generating.
- **Stiti design:**
  1. **One** free-tier LLM call makes the outline: concepts → sections, from the existing `concept_map()` in `src/stiti/tutor/coach.py`.
  2. A background worker generates section *k+1* while section *k* is taught, always staying one section ahead of the learner.
  3. Storage: Postgres tables `tutor_lesson`, `tutor_section(status: queued|generating|ready|failed|stalled, started_at)` and `tutor_page(type: warmup|teach|check|recap, payload jsonb, status)`, added to `src/stiti/tutor/store.py`.
  4. **Watchdog:** a section stuck in `generating` for more than 45 s is marked `stalled` and retried on the next provider in the router's fallback chain.
  5. **Fallback:** if every provider is down, Stiti falls back to a deterministic "read the source chunk + ask the stored probe" page, so a lesson never dead-ends.
- **Where:** coach.py (plan), lesson.py (page types), player.py (consumes pages as they turn `ready`).
- **UI:** a contents rail in `frontend/src/components/lessons/Progress.tsx`, showing per-section status dots (ready / generating spinner / stalled with Retry).

### 2. Every job is a database row that shows its progress and resumes itself

- **Turbo's technique:** each `content` row carries `content_status`, `current_generation_step`, `percent_completed`, `eta_seconds` and `error_message`. Kickoffs are idempotent, and a reconciler picks up lost jobs.
- **Stiti design:**
  - A table `stiti_job(id, kind, source, step, pct, eta_s, error, updated_at)` covers ingest, concept map, lecture transcription and audio recap.
  - Workers update the row as they go.
  - **Startup reconciler** in `src/stiti/web/server.py` lifespan: jobs whose `updated_at` is older than 2 minutes and not done get re-queued from their last step.
  - Each step is idempotent and checkpointed: chunks, embeddings and concepts are written once, keyed by content hash.
  - ETA = remaining units × the measured seconds per unit.
- **Live UI without Electric:** Postgres `NOTIFY job_progress, '<id>'` → a Starlette **SSE** endpoint `/api/events` in `src/stiti/web/lessons.py` → a small client store.
  - This is the same "rows are the progress channel" idea, at zero cost, local and single-user.
- **UI:** progress card on the Lessons page: step label, %, "about 40 s left", Retry on error.

### 3. Optimistic writes + live rows (a local copy of the Electric + TanStack DB idea)

- **Turbo's technique:** a collection = a read stream + `onInsert` / `onUpdate` handlers. The UI changes instantly and the server confirms.
- **Stiti design:**
  - In the Next.js frontend, keep a tiny `useLiveRows(topic)` hook. It opens the SSE stream and holds a keyed map.
  - Mutations go to `POST /api/lessons/...`: apply locally, then reconcile with the row that comes back on the stream.
  - No new dependency is needed. TanStack DB is MIT-licensed and could be added later if the client state grows.
- **Where:** `frontend/src/lib/stiti.ts` (hook), and the `lessons.py` endpoints.

### 4. Crash-safe recordings stored as drafts, with a repair step

- **Turbo's technique:** recordings are saved to **drafts**. A "repair" step fixes broken drafts, which can be played back or discarded, and there is a draft-uploads notice. The user can pause and resume a recording and pick the microphone.
- **Stiti design** (build-order item 4):
  1. The mic is captured in `src/stiti/tutor/audio.py` / `ears.py`.
  2. Audio goes into **30 s WAV/FLAC segments** in `~/.stiti/recordings/<id>/seg-0001.flac`, plus a `manifest.json` (device, started_at, segments, paused spans), written after every segment.
  3. **Repair on startup:** any manifest with no `ended_at` gets its last segment's header fixed, is concatenated, and is marked `draft`. A recording is never lost.
  4. **Transcription:** a background Whisper job (`stiti_job` kind=`transcribe`, one segment at a time, so RAM stays under 1 GB).
  5. **Notes:** each finished segment is summarised separately, then merged (map-reduce), so long lectures do not get thin notes. Every line keeps its `seg + offset` timestamp, which makes timestamps clickable, unlike Turbo's.
- **UI:** a Record button on the Lessons page with a timer and input level, a device picker and pause/resume, and a "Drafts (2)" list with Play / Make notes / Discard.

### 5. "Raise hand" during the audio recap (interrupt and ask)

- **Turbo's technique:** a premium `raise_hand` button on podcasts, plus a podcast chat.
- **Stiti design:** Stiti already listens with barge-in, so "raise hand" can be **spoken**.
  1. While a Kokoro recap plays, the VAD in `ears.py` hears the learner start talking.
  2. Playback pauses at its current timestamp.
  3. The doubt is answered with context = the recap script around that timestamp + the cited source chunks.
  4. Stiti says "back to it", rewinds 3 s and resumes.
  - The recap script is stored as `[{t0, t1, speaker, text, chunk_ids}]`, so the paused position maps straight to grounded context.
- **Where:** a new `src/stiti/tutor/recap.py` (script + render), with player.py handling pause and resume.
- **UI:** the recap player on the Lessons page with a hand icon, as a mouse alternative to speaking.

### 6. Narrated lesson pages: voice preview, speed control, pre-rendering

- **Turbo's technique:** lesson-page audio is generated on request. The learner can preview a voice, change speed and seek, and a voice persona toggle exists.
- **Stiti design:**
  - Each `ready` page is **pre-rendered** with Kokoro in the background, one page ahead, cached at `~/.stiti/cache/tts/<sha1(text+voice+speed)>.wav`.
  - Speed is set on the client with `audio.playbackRate`, so there is no re-render. Kokoro's speed parameter is used only for the default.
  - "Voice preview" = one cached sample sentence per voice.
  - Persona = Kokoro voice + speaking-style hints passed to the LLM prompt (formal teacher / friendly peer). It is stored in `USER.md` preferences, so it survives a model swap.
- **Where:** `audio.py` (cache), `player.py`.
- **UI:** a voice/speed popover in the lesson app bar.

### 7. Citation badges + "highlight → ask" + @-mention another file

- **Turbo's technique:**
  - `clicked_citation_badge`.
  - Highlighting text in a source or PDF and sending it to chat.
  - Quote attachments.
  - @-mentioning other docs.
  - Source tabs.
- **Stiti design** (build-order item 1):
  1. Retrieval returns `chunk_id, file, page, span` (pgvector + FTS, under 100 ms).
  2. Answers are prompted to cite `[c:<id>]`, and a post-check strips any id that was not retrieved.
  3. **No-coverage rule:** if the top score is below a threshold, Stiti says "your file doesn't cover this" before giving general knowledge.
  4. **Highlight → ask:** selecting text in `NoteView.tsx` (or on the board) shows "Ask about this", which sends `{quote, chunk_id}` as a pinned context item.
  5. **Voice @-mention:** Laya's intent "also check <file>" adds that file to the retrieval scope.
- **Where:** `src/stiti/brain` retrieval, `coach.py` doubt path, `lessons.py`, `NoteView.tsx`.
- **UI:** a chip on the doubt card ("p. 42 · Unit 2") that opens the passage in a side panel.

### 8. Mastery-gated quizzes and typed or spoken "learn mode" cards

- **Turbo's technique:**
  - Quiz topics can be added or removed and the question type changed.
  - Each question has hint and explanation buttons.
  - `achieved_quiz_mastery` fires at a threshold.
  - Flashcard "learn mode" grades a typed answer, not just a flip.
  - Lessons log `wrong_attempt` and have a "feedback detail" toggle.
- **Stiti design:**
  - Mastery is already BKT-lite in `mastery.py`, and answers are already graded locally in `grade.py` (expectation coverage + embedder, no LLM).
  - Add a **mastery gate**: a concept counts as mastered at p(known) ≥ 0.85 with 2 correct answers in a row. Stiti then celebrates and the concept leaves the queue, with FSRS (`srs.py`) scheduling its return.
  - **Wrong attempt:** first a hint (cheap, stored in the probe), then an explanation aimed at *that* answer (one short LLM call), then a worked example. The feedback detail can be opened on the board but is not read aloud by default.
- **UI:** a topic-chip picker before a quiz, and "Mastered N / M" on the Lessons page.

### 9. Chat that plans and uses tools, with a guard against losing context

- **Turbo's technique:** chat runs **plans** that the user can cancel, answers tool calls, and can create a lesson from a conversation. An event named `context_regression_blocked` exists.
- **Stiti design:**
  - **Laya decides, not the LLM.** Requests like "make this a lesson" / "quiz me on this" / "save these notes" are fast-path intents: the coach is called with the current doubt thread as the source, with no LLM planning.
  - A multi-step request is shown as a **plan card** ("1 map concepts → 2 build 4 sections → 3 start"), and Stiti speaks "hmm, let me set that up".
  - **Context guard** in the Context Compiler: while a lesson is active, the active file and concept stay pinned in the briefing even if a turn's retrieval drifts.
  - The meaning of `context_regression_blocked` is not visible from public code, so the guard is our own design, not a copy.
- **Where:** `src/stiti/decide.py` (intents), `coach.py`.

### 10. Pick up where you left off ("Jump back in") + end-of-lesson summary

- **Turbo's technique:** `last_opened` keyed by `(student, object_type, object_id)`, `pressed_lesson_jump_back_in`, `lesson_start_ensured`, reset progress, a celebration CTA and lesson review.
- **Stiti design:**
  - A `tutor_last_opened` table (or reuse the session resume cursor in `store.py`).
  - The Lessons page top card shows "Continue: Compiler phases, section 3 of 6".
  - A voice "carry on" resumes from the same cursor.
  - **End-of-lesson summary card:** mastery delta per concept, the next FSRS review date, and one "explain it back" prompt.
- **UI:** `StartCard.tsx`.

### 11. Attention signals: kept on this Mac, used only to pace the lesson

- **Turbo's technique:** `page_active_heartbeat` and `tab_switched_away` / `back` go to cloud analytics.
- **Stiti design:**
  - The board tab's `visibilitychange` pauses the lesson after 10 s hidden. On return Stiti asks "want a 1-line recap?"
  - Active minutes are logged locally to `tutor_events` and power day-mode pacing ("you studied 42 min today").
  - **Nothing is uploaded.**
- **Where:** `src/stiti/tutor/web` board client, `store.py`.

### 12. A local event log of Stiti's own decisions (for Laya calibration)

- **Turbo's technique:** a typed event catalogue with batching, retry, an offline queue and dead-letter.
- **Stiti design:**
  - A `tutor_events(ts, kind, concept, payload jsonb)` table in local Postgres, with names from one enum module like Turbo's catalogue: `hint_shown`, `wrong_attempt`, `mastered`, `raise_hand`, `section_stalled`…
  - This is the training data CLAUDE.md allows for calibrating Laya ("is this a doubt or an answer?", "frustrated?").
  - No network sink and no retries are needed; one `INSERT` costs about 1 ms.
- **Where:** `src/stiti/tutor/store.py`, with the enum in `src/stiti/tutor/events.py`.

### 13. Skipped (and why)

- Anonymous sessions linked to an account later, OAuth and magic links: single user, local.
- Stripe, regional pricing, Churnkey, the paywall placement enum: Stiti is free. Show provider quota health instead.
- Collaborator access control on Modal and public share links: against local-first.
- Ad pixels: privacy.
- The 3D anatomy viewer: gated, and too heavy for 8 GB.
- The notes "AI co-writer": low value for a voice tutor; revisit with markdown notes only.
