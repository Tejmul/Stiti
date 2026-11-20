# NotebookLM (now "Gemini Notebook"): learning and teaching feature inventory for Stiti

Research date: 2026-11-20. Scope: design learning only. No proprietary code or content was copied, and no logged-in surface was touched.

**Method.** Sources are official Google pages (blog.google, support.google.com/notebooklm and /gemininotebook, Workspace Updates, Google Research, DeepMind), builder write-ups (Latent Space interview with the team, Simon Willison), academic evaluations (arXiv, the AGU/Pitt study) and press coverage. Every URL was fetched, or HTTP-checked (status 200). A few press sites return 403 to bots. Those are marked *(bot-blocked, seen in search)* and are only used for claims that other sources back up.

**REA.** `mcp__rea__inspect_web_page` needs a CDP browser target, and the public marketing page (`notebooklm.google`, which now 301-redirects to `notebook.google`) gave back only a title over plain fetch. The UI structure below therefore comes from Google's help-center descriptions, not from page inspection. No JS was looked at. *(Superseded on the same day: a CDP browser became available and REA was run. See "REA evidence (public pages)" at the end.)*

> **Naming note.** Google renamed NotebookLM to **Gemini Notebook** on **2026-07-16**. It is the same standalone product, now also inside the Gemini app, with notebooks coming to AI Mode in Search. Old links redirect.
> [blog.google/…/notebooklm-gemini-notebook](https://blog.google/innovation-and-ai/products/gemini-notebook/notebooklm-gemini-notebook/) · [Workspace Updates](https://workspaceupdates.googleblog.com/2026/07/notebooklm-now-gemini-notebook.html)
> This report uses "NotebookLM" for both names.

---

## 0. Product skeleton (the mental model)

- **Three panels: Sources | Chat | Studio** (since Dec 2024). Sources holds the material. Chat is grounded Q&A with citations. Studio holds one-click outputs (Audio and Video Overviews, mind maps, reports, flashcards, quizzes, slides, infographics). The panels adapt to the task, so you can read a source while editing notes, or chat while audio plays. [blog.google Dec 2024](https://blog.google/technology/google-labs/notebooklm-new-features-december-2024/)
- **Everything is grounded in the notebook's sources.** Sources include PDFs, Docs, Slides, Sheets, .docx, images (handwritten notes), web URLs, YouTube, Drive links and audio. Since Sep 2026 the mobile app also has a recorder for lectures. [Deep Research + file types, Nov 2025](https://blog.google/technology/google-labs/notebooklm-deep-research-file-types/) · [Sep 2026 study tools](https://blog.google/innovation-and-ai/products/gemini-notebook/new-study-tools-september-2026/)
- **Every Studio artifact keeps its generating prompt**, which you can see with ⋯ then "View custom prompt". This applies to audio, video, flashcards, quizzes and reports. [Create a notebook help](https://support.google.com/notebooklm/answer/16206563) · [Audio help](https://support.google.com/notebooklm/answer/16212820?hl=en)
- **The team's design philosophy** (Latent Space interview): keep the surface simple, and add a knob only when "the knob actually needs to work reliably". Judge by taste first and formalize evals later. Two personas with different angles let the model unpack dense material. [latent.space/p/notebooklm](https://www.latent.space/p/notebooklm)

---

## 1. Feature inventory

### 1.1 Source-grounded chat with citations
- **What it does.** Answers come only from the notebook's sources. Off-source creative requests can return "can't answer this question". [Use chat help](https://support.google.com/notebooklm/answer/16179559?hl=en)
- **Citation mechanics.** A citation is a direct quote, text or image taken from a source. You hover to see the full quote, and click to jump to the quote in its original context. If a source is very short, the citation may point to the whole document. Saving a reply as a note keeps its tables and clickable inline citations. [Use chat help](https://support.google.com/notebooklm/answer/16179559?hl=en) · [FAQ](https://support.google.com/notebooklm/answer/16269187?hl=en)
- **Configure Chat.** Three styles: Default, **Learning Guide**, and Custom (a persona or goal, e.g. "PhD advisor that challenges assumptions", or "Game Master with a step limit"). You also choose a response length. Since Oct 2025 chat uses the full 1M-token context, holds more than 6× more multi-turn conversation, and auto-saves chats, which stay private even in shared notebooks. Google reports +50% satisfaction on answers that draw on many sources. [Use chat help](https://support.google.com/notebooklm/answer/16179559?hl=en) · [Chat upgrade, Oct 29 2025](https://blog.google/innovation-and-ai/models-and-research/google-labs/notebooklm-custom-personas-engine-upgrade/)
- **Voice in chat.** "Talk mode" exists only in the mobile app (18+). Sep 2026 added **real-time voice conversations with a notebook**: grounded in sources, step-by-step guidance, interruptible at any time, nearly 100 languages. It reached Ultra subscribers first, with Pro "soon". [Use chat help](https://support.google.com/notebooklm/answer/16179559?hl=en) · [Sep 2026 blog](https://blog.google/innovation-and-ai/products/gemini-notebook/new-study-tools-september-2026/) · [Workspace Updates Sep 18 2026](https://workspaceupdates.googleblog.com/2026/09/new-back-to-school-features-and-learning-tools-available-in-Gemini-Notebook.html)
- **Praise.** Grounding measurably reduces fabrication. One newsroom study found 13% of NotebookLM outputs had a hallucination, against roughly 40% for general chatbots. Most of its errors were "interpretive overconfidence" (characterizing sources in ways they don't support), not invented facts. [Futurity summary](https://www.futurity.org/ai-generated-podcasts-3323312/)
- **Complaints.** A medical-education evaluation found it can still produce inaccurate output from accurate inputs. It also cannot flag misinformation inside the uploaded files, and cannot add relevant knowledge from outside them. [arXiv 2505.01955](https://arxiv.org/abs/2505.01955)
- **Complaint: figures.** PDFs are flattened to text, so graphs, flowcharts, formulas and schematics drop out, and the original PDF is hard to view in-app. This is an Oct 2025 report, while the current help text says images can be used as citations, so the gap may have narrowed. [Android Authority](https://www.androidauthority.com/p-3603778/)

### 1.2 Learning Guide (tutor mode)
- **What it does.** A chat style that "encourages participation with probing, open-ended questions". It breaks problems down step by step and adapts explanations instead of handing over answers. Press describes it as chunking concepts and walking through them one at a time. [blog.google, 6 ways (Sep 8 2025)](https://blog.google/technology/google-labs/notebooklm-student-features/) · [Workspace Updates Sep 23 2025](https://workspaceupdates.googleblog.com/2025/09/learning-guide-notebook-lm-workspace-education.html)
- **Trigger.** Chat panel, then Configure Chat, then Learning Guide, then Save. [Use chat help](https://support.google.com/notebooklm/answer/16179559?hl=en)
- **How it compares.** It is like ChatGPT Study Mode, but scoped to the uploaded documents. *(Neowin, bot-blocked, seen in search)*
- **Evidence from a builder.** A Padua physics teacher configured NotebookLM as a Socratic tutor. The setup was a "training manual" source, a custom persona, chat-only sharing so students can't see the sources, and pre-loaded solutions. [arXiv 2504.09720](https://arxiv.org/abs/2504.09720)
  - What worked: it mostly withheld answers, cited the teacher's sources, and kept its instructions confidential.
  - What didn't: there were small mistakes, and reliability dropped without pre-loaded solutions. Early prompts leaked full solutions. It has no LaTeX rendering and is text-only, so no visual collaboration.
  - The key finding for a tutor: **persistently withholding answers frustrated learners.** The author recommends *adaptive scaffolding that changes when students show frustration*.
- **Gap.** No mastery model or progress tracking inside Learning Guide itself. The Sep 2026 announcement made no tutor changes. [Sep 2026 blog](https://blog.google/innovation-and-ai/products/gemini-notebook/new-study-tools-september-2026/)

### 1.3 Flashcards and quizzes
- **Trigger.** Studio, then Flashcards or Quizzes for defaults. The pencil icon lets you customize first:
  - difficulty: easy, medium or hard
  - a free-text prompt (audience, style, focus)
  - quantity: fewer, standard or more

  Generation runs in the background. [Flashcards/Quizzes help](https://support.google.com/gemininotebook/answer/16958963?hl=en)
- **Flashcard UI.**
  - Each card is marked **"Got it!" or "Missed it!"**, and progress is saved so you can resume.
  - An **Explain** button gives a cited overview of the card.
  - Prev/next, full screen, **shuffle**, delete card, restart.
  - **Export to CSV.**
  - At the end you see results, then **retake "Same cards / All cards / Only cards you missed."**

  [Flashcards/Quizzes help](https://support.google.com/gemininotebook/answer/16958963?hl=en)
- **Quiz UI.** A **Hint** button, and an **Explain** button that says *why your answer was wrong*, with citations to the source. Results screen, review, retake. Quizzes can be shared by link. [blog.google, 6 ways](https://blog.google/technology/google-labs/notebooklm-student-features/) · [Help](https://support.google.com/gemininotebook/answer/16958963?hl=en)
- **Sep–Oct 2026 additions.**
  - Formats: **short answer, multi-select, fill-in-the-blank** alongside multiple choice.
  - You can **add or edit questions**. Earlier reviewers had complained that cards were not editable.
  - **"Performance chat"**: after a quiz or deck, you ask the notebook where you fell short and what to focus on next.

  [Sep 2026 blog](https://blog.google/innovation-and-ai/products/gemini-notebook/new-study-tools-september-2026/) · [Oct 16 2026 tips](https://blog.google/innovation-and-ai/products/gemini-notebook/three-tips-study-gemini-notebook/)
- **Mobile.** Arrived Nov 2025. [blog.google app quizzes](https://blog.google/technology/google-labs/notebooklm-app-quizzes-flashcards/)
- **Gaps** (none documented in any official source):
  - no spaced-repetition scheduling (FSRS/SM-2)
  - no long-term per-concept mastery inside the notebook
  - no adaptive difficulty during a session

### 1.4 Diagnostic and objective map (Gemini app "study notebooks", the sibling product)
This sits in the Gemini app, not NotebookLM proper, but sources are shared between them. It is the closest Google design to Stiti's "coach". [blog.google, Jun 25 2026](https://blog.google/innovation-and-ai/products/gemini-app/gemini-study-notebooks/)
- You upload a syllabus or notes, and it generates a **baseline diagnostic quiz** to find strengths and gaps.
- The learning goal is split into **100+ objectives grouped into topics**. Each is labelled **Strengths / Focus areas / Not started**, and the labels update as you complete follow-up quizzes.
- A dashboard ranks priority lessons and can be filtered by category.
- **Short targeted lessons** come with practice quizzes, and you can ask questions mid-lesson.
- Exam prep: SAT now (Princeton Review questions). JEE, NEET, ENEM, ACT and GRE were announced.
- No formal mastery model or score is disclosed.

### 1.5 Audio Overviews (AI podcast hosts)
- **Formats** [Audio help](https://support.google.com/notebooklm/answer/16212820?hl=en) · [6 ways](https://blog.google/technology/google-labs/notebooklm-student-features/):

  | Format | Hosts | What it is |
  |---|---|---|
  | **Deep Dive** (default) | 2 | Unpack and connect topics |
  | **Brief** | 1 | Under 2 min |
  | **Critique** | 2 | Constructive feedback on an essay or design doc |
  | **Debate** | 2 | Formal back-and-forth across perspectives |

- **Options.** Lengths are Shorter, Default or Longer (Longer is English only). There are 80+ output languages. A custom prompt sets focus and expertise level. Generation runs in the background and takes minutes.
- **How the script is built** (reported by Steven Johnson of the NotebookLM team, via Simon Willison): **outline → revised outline → detailed script → critique → revision → a final pass adding disfluencies** (pauses, banter). [simonwillison.net](https://simonwillison.net/2024/Sep/29/notebooklm-audio-overview/)
- **Team notes** (Latent Space) [latent.space](https://www.latent.space/p/notebooklm):
  - Interjections and "uh"s are produced mostly by the *audio model*. The text step only signals where pauses or laughter fit.
  - They tried both a single prompt and step-by-step prompting between two personas.
  - Agreeable hosts are dull, so the script **builds tension, withholds information early, and returns to the main thread after tangents**.
  - Hosts don't say their names.
  - Eval dimensions: entertainment, consistency, groundedness, format adherence, safety.
- **Audio model** (DeepMind): it turns a script with **speaker-turn markers** into about 2 minutes of dialogue per pass (more than 5,000 tokens), at over 40× real time. It was fine-tuned on unscripted voice-actor conversations so it learns realistic turn-switching, pauses and "umm"s. [DeepMind, Oct 30 2024](https://deepmind.google/discover/blog/pushing-the-frontiers-of-audio-generation/)
- **Interactive "Join" mode** (beta, Dec 2024):
  - Steps: make a new overview, choose Interactive mode, press play, then tap **Join**.
  - **A host "calls on you"**. You ask by voice, they answer from the sources, then **resume the original overview**.
  - Limits: English only, new overviews only, short delays when joining and after speaking, occasional voice glitches (speaker swaps, extra voice), not available to shared-link viewers. Voice and transcripts are not stored.

  [Audio help](https://support.google.com/notebooklm/answer/16212820?hl=en) · [Dec 2024 blog](https://blog.google/technology/google-labs/notebooklm-new-features-december-2024/)
- **Praise.** Engaging plain-language analogies. The Pitt planetary-science study called them "fairly accurate and creative analogies" that help accessibility. [Pittwire, Feb 2026](https://www.pittwire.pitt.edu/features-articles/2026/02/17/ian-flynn-notebooklm-podcasts-agu-perspectives)
- **Complaints.**
  - The same Pitt study found that **every overview had errors, all toward the end**. These were unjustified extrapolations: one overview inferred water and life on Mars from a volcanic feature. [Pittwire](https://www.pittwire.pitt.edu/features-articles/2026/02/17/ian-flynn-notebooklm-podcasts-agu-perspectives)
  - Hosts are excessively flattering, and instructions planted in sources can steer them. [simonwillison.net](https://simonwillison.net/2024/Sep/29/notebooklm-audio-overview/)

### 1.6 Video Overviews
- **Origin (Jul 29 2025).** The first format was **narrated slides** that pull **images, diagrams, quotes and numbers from the sources**. You can steer by topic, learning goal and audience. [Workspace Updates Jul 2025](https://workspaceupdates.googleblog.com/2025/07/video-overviews-studio-panel-updates-notebooklm.html)
- **Formats now.**
  - **Explainer**: structured and comprehensive.
  - **Short**: about 60 s. It replaced "Brief", and since Sep 2026 it adds "educational animations for formulas, diagrams, and scientific concepts" in 80+ languages.
  - **Cinematic**: 18+, English only.

  [Video help](https://support.google.com/notebooklm/answer/16454555) · [Sep 2026 blog](https://blog.google/innovation-and-ai/products/gemini-notebook/new-study-tools-september-2026/)
- **Styles.** Image model "Nano Banana", from Oct 2025: Classic, **Whiteboard**, Watercolor, Retro Print, Heritage, Paper-craft, Kawaii, Anime, plus Auto-select and a free-text Custom style. [Video help](https://support.google.com/notebooklm/answer/16454555) · [9to5Google Oct 2025](https://9to5google.com/2025/10/13/notebooklm-video-overviews-styles/)
- **Mechanics.** A steering prompt, plus optional **"producer notes"**: you review draft notes, give batch feedback, then press Proceed, after which it is locked. Generation can take **more than 30 minutes**. You can also trigger it from chat ("Create a video summarizing X") and customize through cards that appear. Good/bad video feedback buttons. [Video help](https://support.google.com/notebooklm/answer/16454555)

### 1.7 Mind maps
- **Trigger.** A **"Mind Map" chip in chat**. The map is saved as a note in Studio. To regenerate, delete it and make it again.
- **Interactions.** It is a branching diagram of topics and sub-ideas. You zoom and scroll, **expand or collapse branches**, and **click a node to ask chat about that topic**. It can be downloaded. Not on mobile. [Mind Maps help](https://support.google.com/notebooklm/answer/16212283?hl=en)
- Learners have called it a favorite feature (TechRadar headline "it's my new favorite feature", Mar 2025, seen in search).

### 1.8 Reports: study guide, briefing doc, FAQ, timeline, blog post, custom
- **Report types.** "Create your own", FAQ, study guide, briefing document, and **AI-suggested types picked from the content**. Examples: a glossary or magazine-style explainer for economics, a character analysis for fiction. [Create a notebook help](https://support.google.com/notebooklm/answer/16206563) · [6 ways](https://blog.google/technology/google-labs/notebooklm-student-features/)
- **FAQ and Timeline.** These lost their one-click presets in Sep 2025 and are now made via a custom prompt. Users complained on Reddit. [Android Authority, Sep 10 2025](https://www.androidauthority.com/notebooklm-loses-faq-timeline-suggestions-3596578/)
- **Interactive Learning Overviews** (under Reports, Sep–Oct 2026). A *step-by-step walkthrough* of a large set of notes, lectures and readings. It weaves summaries together with slides, infographics, mind maps, quizzes and flashcards. No independent review has explained how the embedded checks behave. [Oct 16 2026 tips](https://blog.google/innovation-and-ai/products/gemini-notebook/three-tips-study-gemini-notebook/) · [Workspace Updates Sep 2026](https://workspaceupdates.googleblog.com/2026/09/new-back-to-school-features-and-learning-tools-available-in-Gemini-Notebook.html)

### 1.9 Slide decks and infographics
- Launched Nov 2025 on the image model "Nano Banana Pro". Infographics visualize key insights. Slide decks turn documents or rough notes into styled decks for reading or presenting (18+ at first). [Workspace Updates Nov 2025](https://workspaceupdates.googleblog.com/2025/11/workspace-nano-banana-pro.html) · [blog.google, 8 ways with Slide Decks](https://blog.google/technology/google-labs/8-ways-to-make-the-most-out-of-slide-decks-in-notebooklm/)

### 1.10 Discover sources, Fast Research and Deep Research
- **Discover** (Apr 2025). You describe a topic. It scans hundreds of web pages and returns **up to 10 sources, each with an annotated "why it's relevant" summary**, which you import in one click. "I'm Feeling Curious" picks a random topic. [blog.google Apr 2 2025](https://blog.google/innovation-and-ai/models-and-research/google-labs/notebooklm-discover-sources/)
- **Nov 2025 changes.** Discover was renamed **Fast Research** ("quick search", review and import right away). **Deep Research** was added: a research plan, browsing that refines itself, a source-grounded report, background running, and import of the report plus its sources. [blog.google Nov 13 2025](https://blog.google/technology/google-labs/notebooklm-deep-research-file-types/)

### 1.11 Multi-source notebooks, notes, limits
- **Source limits.** 50 sources per notebook on the standard tier. 500k words per source. 200 MB per upload. [FAQ](https://support.google.com/notebooklm/answer/16269187?hl=en) · [Upgrade](https://support.google.com/notebooklm/answer/16213268)
- **Notes.** Since Sep 2026, notes sit beside sources and can themselves be chatted with, cited and built on. [Sep 2026 blog](https://blog.google/innovation-and-ai/products/gemini-notebook/new-study-tools-september-2026/)
- **Usage limits.** The older free caps were about 50 chats, 3 audio and 3 video per day, and 10 reports, flashcard sets or quizzes per day. **Since Sep 2 2026** usage is **compute-based**, refills every 5 hours up to a weekly cap, and shows a live usage meter and a per-generation cost bar. Expensive outputs can be deferred until the budget refills. [GCN](https://gcn.com/gemini-notebook-switches-compute-based-limits/21309/) · [Upgrade help](https://support.google.com/notebooklm/answer/16213268)
- **Ready-made textbook notebooks.** OpenStax notebooks for Biology, Chemistry, Psychology and others. [6 ways](https://blog.google/technology/google-labs/notebooklm-student-features/)

### 1.12 Output languages
- Set per notebook under Settings, then Output Language. It defaults to the Google-account language and affects chat and generated outputs from then on. [blog.google, 50 languages (Apr 2025)](https://blog.google/technology/google-labs/notebooklm-audio-overviews-50-languages)
- Audio covers 80+ languages, and interactive Join is English only. [Audio help](https://support.google.com/notebooklm/answer/16212820?hl=en)
- Real-time voice covers about 100 languages. [Sep 2026 blog](https://blog.google/innovation-and-ai/products/gemini-notebook/new-study-tools-september-2026/)

### 1.13 Sharing and classroom
- **Ways to share.** Share the whole notebook, or a public link (consumer accounts only). Deleting an artifact breaks its link. Chats stay private in shared notebooks. [Audio help](https://support.google.com/notebooklm/answer/16212820?hl=en) · [Video help](https://support.google.com/notebooklm/answer/16454555) · [Chat upgrade](https://blog.google/innovation-and-ai/models-and-research/google-labs/notebooklm-custom-personas-engine-upgrade/)
- **Chat-only sharing** lets a teacher hide the sources, as in the Padua tutor. [arXiv 2504.09720](https://arxiv.org/abs/2504.09720)
- **Classroom.** Students in Google Classroom can build personal class notebooks from the materials a teacher assigned (Apr 27 2026). [Workspace Updates](https://workspaceupdates.googleblog.com/2026/04/students-can-now-create-personal-class-notebooks-with-NotebookLM-in-Google-Classroom.html)

### 1.14 Research context: Google "Learn Your Way" (LearnLM textbook experiment)
This is not NotebookLM, but it is the same team family, and it is the clearest public design of Google's learning pipeline. [Google Research blog](https://research.google/blog/learn-your-way-reimagining-textbooks-with-generative-ai/) · [arXiv 2509.13348](https://arxiv.org/abs/2509.13348) · [demo](https://learnyourway.withgoogle.com/)
- **Two-stage personalization.** First the text is re-levelled to the learner's grade. Then generic examples are swapped for **examples drawn from the learner's interests** (sports, music, food). Every other format is built from this personalized text.
- **Five representations:**
  - immersive text with generated images and embedded questions
  - section quizzes
  - narrated slides with fill-in-the-blanks
  - an **audio lesson staged as a teacher and student, where the student voices misconceptions and the teacher corrects them**
  - a mind map

  **Quiz results route the learner back to weak sections.**
- **Results.** In an RCT with n=60 students aged 15–18, retention after 3–5 days was **78% vs 67%** against a PDF reader. Illustrations needed a fine-tuned image model because general models failed at educational diagrams.

---

## 2. Cross-cutting mechanics worth stealing (design patterns, not code)

1. **Every artifact is a reproducible recipe: (sources + prompt + format + length + language).** "View custom prompt" makes it inspectable and repeatable.
2. **Citations are quote spans, not doc-level links.** Hover shows the quote, click jumps to it in context, and citations survive being saved into notes.
3. **Use a multi-pass script for anything long-form:** outline → revise → script → critique → revise → disfluency or prosody pass. Two personas with *tension* beat one agreeable narrator.
4. **Interrupt-and-resume.** The host calls on the learner, answers from the sources, then returns to where it was. Sep 2026 voice drops the "wait to be called on" step and allows barge-in at any time.
5. **Hallucination risk clusters at the tail and in extrapolation.** The Pitt study found errors at the end of every overview. A grounding re-check on the *closing* segment is cheap insurance.
6. **Quiz loop: Hint → answer → Explain why wrong (cited) → results → retake only missed → "where should I focus?" chat.**
7. **Diagnostic → objectives map (Strengths / Focus / Not started) → ranked next lessons.** This is the Gemini study-notebooks design.
8. **Socratic withholding needs an escape hatch.** Learners get frustrated when answers are withheld for too long, so scaffolding should adapt.
9. **Expensive generations run in the background or are deferred.** A visible cost meter is shown, and the learner keeps working meanwhile.
10. **Personalize examples to the learner's interests.** In Learn Your Way this is the base layer, with every format generated from it.

---

## 3. Adoption table for Stiti

Stiti context: a local-first voice tutor on an M2 with 8 GB. It uses free cloud LLM tiers only, local Whisper for speech-to-text, local Kokoro for text-to-speech, a whiteboard that draws notes pages, a coach with per-concept mastery, probes, teach-then-ask steps, exam/day modes, doubts, markdown notes, Wikimedia Commons images, Postgres with pgvector, graph tables, and Laya.

| Feature | Value for a voice whiteboard tutor | Free + local-first on 8 GB? | Rough build idea in Stiti terms |
|---|---|---|---|
| Source-grounded answers with quote-span citations | **High** | **Yes.** Retrieval runs in local Postgres (pgvector + FTS); only the top chunks go to the free LLM. | Store the learner's file as chunks with `(file, page, char_span)`. The Context Compiler passes chunk ids, and the LLM must cite `[c12]`. Stiti *says* "from page 4 of your notes" and the whiteboard shows the quoted line, highlighted. Saved markdown notes keep `[[file#p4]]` links. Refuse, or flag "outside your file", when no chunk passes a score threshold. |
| Learning Guide (Socratic tutor) | **High** | **Yes.** It is mostly prompting plus Laya gating. | Add a `socratic` teaching policy: ask before telling, chunk into teach-then-ask steps. **Escape hatch:** Laya plus voice emotion (frustrated or tired) and N failed tries switch it to a worked example. This fixes the Padua frustration finding, and NotebookLM lacks voice-emotion input entirely. |
| Quiz/flashcard loop: Hint, Explain-why-wrong, retake-missed, performance chat | **High** | **Yes.** MCQ, multi-select and fill-blank are graded locally by exact or fuzzy match. Short answers go to the free LLM with a rubric and cited chunk. | Each item is tagged with a `concept_id`. Got-it/missed results update coach mastery (BKT- or Elo-style). Add **FSRS spaced repetition**, which NotebookLM doesn't have. "Where should I focus?" is answered from the mastery table, with no LLM needed (fast path). Export decks as CSV or markdown. |
| Diagnostic → objective map (Strengths / Focus / Not started) | **High** | **Yes.** It is graph tables plus a probe set. | The coach already maps the file into concepts. Run a short spoken diagnostic of 1 probe per concept, colour concept nodes on the whiteboard in three states, and rank the next lessons. Exam mode means a higher probe density with a time box. |
| Interactive Audio Overview ("join", interrupt and resume) | **High** (it *is* Stiti's medium) | **Mostly.** The script comes from the free LLM. Kokoro runs locally with two voices (each voice is just a voicepack on the same small model). Barge-in comes from Pipecat VAD. | Make a "lesson stack": the lesson is a sequence of script segments. On barge-in, push a *doubt frame*, answer it grounded, then pop back and resume at the segment boundary ("…so, back to where we were"). Optionally use a two-voice teacher+student format with **student misconceptions** (from Learn Your Way). Generate the script with the outline → critique → revise passes in the background, and stream TTS per segment so first audio comes in under 1 s. |
| Video Overview: narrated slides with quotes, numbers and diagrams | **High** (the whiteboard *is* this) | **Yes**, with no image-generation model. | Each whiteboard page is a narrated "slide". Pull quotes and numbers straight from the cited chunks. Images come from **Wikimedia Commons** search (free, with real licences) instead of generated art. Sync page reveals to TTS word timings. A "Short" mode means one 60-s page per concept for day mode. |
| Mind map from sources, click a node to ask | **Med-High** | **Yes.** The concept graph already exists in Postgres. | Render the coach's concept graph as a collapsible map on the whiteboard and colour nodes by mastery. Tapping a node, or saying "tell me about X", opens a teach-then-ask step for that node. |
| Reports: study guide, briefing, FAQ, timeline, glossary, auto-suggested types | **Med** | **Yes.** One free LLM call each over compiled context, run in the background. | Save them as markdown notes in `~/.stiti/`. Suggest a format based on content type (timeline for history, glossary for biology). Keep the generating recipe in the note's front-matter, the "view prompt" pattern. |
| Interactive Learning Overview (summary woven with embedded checks) | **High** | **Yes.** | This is exactly Stiti's teach-then-ask. Sequence = concept order from the graph, and each step = whiteboard page + 1 probe. Wrong answers route back to the weak concept, as in Learn Your Way. |
| Personalized examples drawn from learner interests | **High** | **Yes.** Stiti already has USER.md and the knowledge graph. | The Context Compiler injects 1–2 interests from USER.md, and the prompt says "use an example from {interest}". NotebookLM can't do this because it doesn't know the user. |
| Real-time voice chat with a notebook | **High** | **Already Stiti's core** (Whisper + Kokoro + Pipecat). | Keep the latency budget. Grounding stays local. Google gates this behind its top paid tier, so it is a differentiator for Stiti. |
| Discover / Fast Research (up to 10 sources + why relevant) | **Med** | **Yes**, through free APIs (Wikipedia, Wikimedia Commons, OpenStax, arXiv). | The doubt "I don't get X and it's not in my file" → offer up to 3–5 sources, each with a one-line "why". The learner confirms by voice and they are imported as extra chunks. Deep Research is low priority because it is costly on free tiers. Run it only in the background. |
| Lecture recorder → source | **Med** | **Yes.** Local Whisper in the background, chunked. | Record a class, transcribe it off the hot path, and add it as a source with timestamps as citation spans. |
| Multiple output languages | **Low-Med** (English-first priority) | Partly. Kokoro covers a few languages, and Whisper is multilingual. | Use a per-notebook language setting later. Keep English as the default, matching the current priority. |
| Debate / Critique audio formats | **Low-Med** | Yes (two Kokoro voices). | "Critique my answer or essay" fits exam mode: two-voice feedback on a learner's written answer. |
| Sharing and public links | **Low** | Conflicts with local-first and no-personal-data rules. | Skip it. At most, export a deck or notes as a file. |
| Slide decks and infographics (image-generated) | **Low** | No free local image generation fits in 8 GB. | Cover it with whiteboard pages plus Commons images instead. |
| Compute meter and deferred generation | **Med** (ops) | **Yes.** | Show "thinking in background" status, and queue heavy jobs (scripts, reports) for when the free tier has budget again. This fits the fallback-chain rule. |

---

## 4. Top 5 to adopt first (ranked)
1. **Quote-span grounding, spoken and drawn.** Every claim is tied to a chunk of the learner's file. Run an extra grounding check on the *last* segment of long explanations, because the Pitt study found errors cluster there.
2. **Socratic Learning Guide with an emotion-aware escape hatch.** Ask first, chunk the material, and switch to a worked example on frustration. Stiti hears tone of voice, which NotebookLM doesn't.
3. **The full quiz loop wired into mastery.** Hint, explain-why-wrong with a citation, retake-missed, "where should I focus" answered from the mastery table, plus FSRS scheduling, which NotebookLM lacks.
4. **Diagnostic → objective map.** One spoken probe per concept, then concept nodes in three states (Strengths / Focus / Not started) on the whiteboard mind map. Tapping or naming a node starts a lesson.
5. **Join-and-resume narrated whiteboard lessons.** Scripts go through outline → critique → revise, with optional teacher+student voices and student misconceptions. Barge-in pushes a doubt frame and then resumes the lesson. Visuals come from source quotes and numbers plus Wikimedia Commons images.

---

## REA evidence (public pages)

Captured 2026-11-20 with REA (https://github.com/morluto/rea) against a throwaway, logged-out headless Chrome (CDP on
127.0.0.1:9333). Only public pages were opened: `notebook.google/`, `/plans`, `/app`, and six Help Center articles.
The product app itself (`notebook.google.com`, where "Try Gemini Notebook" sends you) needs a Google sign-in, so it was
**not** opened. REA parses JavaScript statically and never runs it. Nothing was copied apart from the short identifiers
quoted below. **Prompt injection:** none found. No page text, script, or help article contained instructions aimed at
an agent.

| Evidence id (prefix) | Tool | Target |
|---|---|---|
| `ev_fc229481…` | inspect_web_page | `https://notebook.google/` (home) |
| `ev_29736900…` | inspect_web_page | `https://notebook.google/plans` |
| `ev_9a150686…` | inspect_web_page | `https://notebook.google/app` |
| `ev_5d47bb2d…`, `ev_ee58d7b4…`, `ev_58f2fd7b…`, `ev_9fa90595…` | inspect_web_page | Help: chat 16179559, audio 16212820, mind maps 16212283, flashcards/quizzes 16958963 |
| `ev_482d0d22…` (views `ev_67890387…`, `ev_a90f343a…`) | analyze_web_bundle (javascript-routes) | home page bundle |
| `ev_3b0cef05…` (view `ev_0af4af68…`) | analyze_web_bundle (javascript-routes) | plans page bundle. Same 3 routes |
| `ev_6a075ab4…`, `ev_e75d2477…` | inspect_web_event_listeners | first `button` on home, and `body` |
| `ev_c2c0ed3e…`, `ev_72c51379…`, `ev_2a2a29eb…` | capture_web_screenshot | home, plans, audio help (viewport only) |

More Help Center articles were read as static HTML over `curl` (public, same content as the browser view): sites
18945748, connected apps 18784282, notes 16262519, reports 18323649, usage limits 17670842, sources 16215270, video
16454555, slide decks 16757456, infographic 16758265, about 16164461.

### (a) Tech stack of the public site

| Layer | Finding | Evidence |
|---|---|---|
| Server / edge | Google front end. Response header `server: ESF`, HTTP/3 (`alt-svc: h3`), `x-frame-options: SAMEORIGIN` | `curl -I https://notebook.google/` |
| App framework | Google's internal **Boq** server framework, with a **Wiz/Angular** client. App id `LabsTailwindMarketing`. The page has `window.WIZ_global_data` (`MUE6Ne: "labs-tailwind-marketing"`, `Im6cmf: "/_/LabsTailwindMarketing"`) and `AF_initDataCallback` (server-injected data). The `m=_b` bundle carries Angular, Closure Library and RxJS licence banners | `scripts.items` (6 inline scripts), `boq_b.js` source from `ev_6a075ab4…` |
| JS delivery | Code-split modules from `www.gstatic.com/_/mss/boq-labs-tailwind/…/m=_b` (565 KB) and `…/m=qVnU4e` (833 KB, plans page) | `ev_29736900…` `scripts.items` |
| Styling | The name ("labs-tailwind") and the class-heavy DOM point to Tailwind CSS. Fonts come from `fonts.gstatic.com` | HTML, `_F_cssRowKey` |
| Security | Strict CSP: a per-request script nonce, **Trusted Types** (`require-trusted-types-for 'script'`), CSP reports to `/_/LabsTailwindMarketing/cspreport` | response headers |
| Analytics | Google Tag Manager `GTM-WQ7LTQ58` with a `dataLayer`, Clearcut logging (`play.google.com/log`), `ppConfig` privacy-reporting stub, `auditrecording-pa.googleapis.com` (consent audit) | HTML, bundle URL strings |
| Auth | None on the marketing site. The CTA goes to `https://notebook.google.com/` (Google account sign-in) | bundle URL strings, DOM links |
| Payments | No payment SDK on the page. Upgrades go through **Google One** (`one.google.com/ai`, `one.google.com/explore-plan/notebooklm`). Business plans go through Workspace / Gemini Enterprise (`g.co/cloud/gemini-notebook-enterprise`) | `m=qVnU4e` URL strings |
| AI / audio vendors | Not visible on public pages. Google's own models are named in the copy only ("built with the latest Gemini models") | a11y text |
| Mobile | iOS App Store id `6737527615`, plus Play Store, both through QR codes on `/app` | bundle strings, `/app` resources |
| Legacy domain | Customer logos are still served from `notebooklm.google/_/static/v4/logos/…` | `m=qVnU4e` strings |

### (b) Route map and feature names

- **Bundle routes** (`ev_a90f343a…`): only `/`, `/plans` and `/app`. The marketing site is a three-page shell. Every
  product feature lives in the separate signed-in app on `notebook.google.com`, which REA could not reach logged out.
- **Feature names from asset filenames** (`resources[]`, home). There are **nine Studio outputs**, each with its own
  image: `audio-overviews`, `mind-maps`, `reports`, `flashcards`, `quizzes`, `video-overviews`, **`data-table`**,
  `infographic`, `slides`. "Data Tables" is an output the earlier report missed.
- **Help Center navigation** (identical on all four captured help pages) gives the full public feature list:
  Learn about · Usage limits · Chat · **Connected apps** · Create a notebook · Add/discover sources · Notes · Mind Maps ·
  Audio Overview · Video Overviews · Flashcards/Quizzes · Infographic · Slide Decks · Reports · Public & featured
  notebooks · Community · Mobile app · Notebooks in Gemini Apps · Privacy · Notebooks in AI Mode in Search · **Generate sites**.
- **What this says about structure.** The product is one notebook object (sources + notes + chat history), with a
  plug-in set of **generators** in the Studio panel that write snapshot **artifacts** next to it. Help 16215270: "When
  you update or delete a source, studio outputs generated with that source do not change." Each generator shares the same
  controls: customise (pencil), Generate now / **Generate later**, background run, ⋯ → View custom prompt / share /
  download / delete, and thumbs feedback.

### Features found by REA that the earlier report missed

- **Generate sites** (18+, Help 18945748). You ask chat to "make a site", and it builds an interactive dashboard, tracker or
  visual narrative from the sources. The site **remembers each viewer's own inputs** (checkboxes, logged notes), and viewers never see each other's inputs.
- **Connected apps** (web only, Help 18784282). Chat calls actions in connected apps. Apps are switched on per account
  and toggled **per notebook** in Configure Chat. Turning off the "Web" app stops web research, but URLs you added
  as sources still work. This is the same idea as Stiti's MCP connectors with a per-notebook scope.
- **Agentic chat** (Help 16179559). Chat can search the web, run code, and create files, charts and images. It can
  "modify artifacts as versions" and expand its **"thinking steps"**. There is a **Stop** button to change a request
  while it is running. Chat also works with or without sources.
- **Notes are sources** (Help 16262519). Notes sit in the Sources panel with a checkbox. Checked notes are used for Q&A,
  can be cited, and feed artifact generation. You can pin a chat reply to the "noteboard", or save it as a note, which
  becomes editable only after its citations are stripped. Notes export to Google Docs.
- **Source Guide**: an automatic summary of each source. You can tick **individual sources** to scope one question.
  Help advises naming the source in the question ("…in the 'Dog Training 101' document") to narrow retrieval.
- **Source types** (16215270): audio (MP3/WAV), docx/txt/md/pdf/csv/pptx, images (heic, webp …), ePub, Play Books
  ebooks (text only), Google Docs/Slides (≤ 100 slides)/Sheets (≤ 100k tokens), web and YouTube URLs, and past Gemini
  chats. Each source is ≤ 500k words or 200 MB.
- **Sources per notebook by plan** (`/plans` a11y): 50 standard, 100 Plus, 300 Pro, 600 Ultra. Usage limits are 2×
  for Plus, 4× for Pro, and 5–20× Pro for Ultra.
- **Usage meter UX** (17670842). Chat shows lines like "You're almost at your AI usage limit. Limit resets at 3:00 PM."
  Studio shows a cost bar before you generate. **Generate later** queues the job and sends a notification when it is done.
- **Co-create before rendering.** Slide decks have "Review outline" and video has "Review producer notes". You give all
  feedback in one batch, then press Proceed, and after that it is locked. Both can also be started from chat, with
  customisation through **response cards**.
- **Infographic knobs** (16758265): detail level (Concise / Standard / Detailed beta), orientation (square /
  portrait / landscape), style (Sketch Note, Kawaii, Professional, auto), free-text prompt. Exports as PNG.
- **Interactive reports** (18323649). Reports → Interactive → template "Learning Overview". The generated report offers
  **suggested artifacts you can embed with one "Add" click**. Document reports use templates or suggested formats, each
  with Edit → Generate now / later.
- **Audio while you work** (16212820). An Audio Overview keeps playing while you browse quotes and citations and query
  sources. Playback speed is adjustable. In interactive mode, "your voice and transcribed interactions with the hosts
  won't be stored or shared".

### (c) UI patterns on the public pages

- **Home** (screenshot `ev_c2c0ed3e…`, a11y order). Plain white page. One-line kicker ("Your AI-powered research
  partner"), a huge two-tone headline ("Understand **anything**"), one sentence, and **one** dark pill CTA. Next comes "How it
  works" (one image showing a source turning into many formats), then a strip of the **nine Studio outputs as labelled
  images**, then "Explore featured public notebooks" (4 cards, each with an icon, a title, a **source count** of 17 / 46 /
  45 / 267, and "View notebook"). After that: press quotes, a privacy module ("never use your organization's data to
  train"), an 11-question FAQ accordion, and a footer (Overview, Plans, Discord, Reddit, X, Get the App).
- **Try before you sign up.** Featured public notebooks let a visitor test real notebooks first. A Stiti equivalent is a
  bundled demo lesson that works offline.
- **Plans.** A four-column tier table (Standard / Plus / Pro / Ultra) with rows for Usage limits, Gemini models,
  New features, and sources per notebook. Below it are **use-case sections**, each following "From X to Y" (study aids, research, customer
  support, sales, training, marketing). The order is the same everywhere: material in → named artifact out.
- **App page.** QR codes for both stores, plus five verb-first bullets: create notebooks, upload sources, "create & join audio
  discussions", "Ask Q's & get answers with in-line citations", "send sources from anywhere on your device" (share-sheet
  ingest).
- **Interaction.** The FAQ accordion has a direct `click` listener from the `m=_b` bundle (`ev_6a075ab4…`, line 669).
  `body` has no direct listeners (`ev_e75d2477…`). The bundle checks `prefers-reduced-motion` and `aria-expanded`.

### (d) Network / API patterns visible logged out

- In the 4 s REA window after load there were **zero network requests and zero WebSockets**, and storage was empty (no
  localStorage, IndexedDB or cache). The marketing pages are fully server-rendered, and the scripts loaded before REA attached.
- The bundles contain no `batchexecute`, `rpcids` or `WebSocket` strings (grep of `m=_b` and `m=qVnU4e`). The only
  same-origin path shapes are static ones (`/_/static/branding/v6/{dark_mode|light_mode}/…`, `/_/static/v4/…`) and
  the CSP report path. The app's real RPC surface (Boq apps normally use `/_/<App>/data/batchexecute` with `rpcids=`)
  is behind sign-in, so it was **not observed**. Nothing here says how Google streams chat or audio.

### (e) What this adds to the comparison for Stiti

1. **Artifacts are snapshots with a recipe.** Stiti should store `(source hashes, prompt, knobs, model)` with every
   generated note, deck or recap, and mark it *stale* when a source changes. NotebookLM leaves outputs silently out of date.
2. **One generator contract** (customise → now/later → background → view prompt → feedback) keeps nine outputs
   consistent. Stiti's lesson, recap, cards and map should share one job type and one UI card.
3. **Generate later plus a visible meter** fits Stiti's free-tier router. When quotas in `llm_usage` run out, queue
   the job and say "I'll have it ready after 3 pm", rather than failing.
4. **Per-notebook connector toggles** match MCP. Scope tools per lesson or file (for example, web off during an exam).
5. **Review the outline before rendering** (slides and video). Show the lesson or recap plan on the board, take one round of
   spoken feedback, then render. This is cheap, and it stops a 3-minute recap built on the wrong outline.
6. Not worth copying: Sites, image-model infographics/slides, public sharing. These conflict with 8 GB, free tiers, or local-first.

---

## Techniques for Stiti

For each NotebookLM feature: the *likely* technique (inferred from public docs, the team's public interviews and papers;
the app's code was **not** seen), followed by a concrete free/local sketch. The sketch reuses what Stiti already has:
`embed.py` (EmbeddingGemma-300M ONNX, 768-d, about 7 ms per query), Postgres 18 + pgvector + FTS, `router.py`
(free-tier chain, `complete(schema=…)` constrained JSON on Groq/Cerebras), `tutor/book.py` loader, mlx-whisper small
q4, Kokoro int8, FSRS (`srs.py`), board ops (`skills.py`, including graph nodes+edges), and the doubt-aside/resume flow.

**Hard limits behind every choice.**
- No local LLM.
- About 3 GB local model budget.
- Free tiers have small token-per-minute (TPM) caps (Groq around 8k TPM on some models), so we **cannot copy Google's
  "stuff 1M tokens" approach**. Stiti must retrieve narrowly and send roughly 1.5–4k tokens per call.

### Shared data flow (one pipeline, many generators)

```
file / URL / lecture.wav
  └─ book.py loader ─▶ sections (title path, page) ─▶ chunks 250–400 tok, 15% overlap
       └─ per chunk: (source_id, page, char_start, char_end, text, tsvector, emb vector(768))   ← Postgres
       └─ background: Source Guide = map-reduce summary per section → per source (free LLM, cached, front-matter recipe)
question / generator request
  └─ hybrid retrieve (FTS + pgvector, RRF) ─▶ optional MiniLM rerank ─▶ top 6–10 chunks, numbered [c1..cN]
       └─ Context Compiler briefing (≤ 1.5k tok) + chunks ─▶ router.complete(schema=…) ─▶ JSON with cite ids + verbatim quotes
            └─ local verifier: each quote must be found in its chunk (exact, then rapidfuzz ≥ 90) ─▶ drop or flag the rest
                 └─ speak (Kokoro) + draw (board: quote highlighted, chip "p. 42")
```

Hybrid retrieval as one SQL round trip, aiming for under 100 ms on a few thousand chunks:

```sql
WITH q AS (SELECT $1::vector AS v, websearch_to_tsquery('english', $2) AS t),
dense AS (SELECT id, row_number() OVER (ORDER BY emb <=> (SELECT v FROM q)) r
          FROM chunks WHERE source_id = ANY($3) ORDER BY emb <=> (SELECT v FROM q) LIMIT 40),
lex   AS (SELECT id, row_number() OVER (ORDER BY ts_rank_cd(tsv,(SELECT t FROM q)) DESC) r
          FROM chunks WHERE source_id = ANY($3) AND tsv @@ (SELECT t FROM q) LIMIT 40)
SELECT id, SUM(1.0/(60+r)) AS rrf FROM (SELECT * FROM dense UNION ALL SELECT * FROM lex) u
GROUP BY id ORDER BY rrf DESC LIMIT 10;
```

`source_id = ANY($3)` implements NotebookLM's "tick the sources to use". Naming a file in speech ("in my bio notes")
fills `$3` through the existing intent and decision step, with no LLM.

### Feature-by-feature

| NotebookLM feature | Likely technique | Stiti sketch (free, local, 8 GB) | Priority |
|---|---|---|---|
| **Grounded chat with quote citations** | Long-context grounding over all sources, plus attributed generation, where the model emits citation markers mapped to source spans, and a UI that resolves a marker to the quote. Related work: ALCE "Enabling LLMs to generate text with citations" (Gao et al. 2023), Self-RAG (Asai et al. 2023), RAGAS faithfulness | Hybrid retrieve (above). The prompt asks for JSON `{answer_sentences:[{text, cites:[c3], quote:"…verbatim…"}], covered: bool}`. The **local verifier** checks every quote as a substring of its chunk (rapidfuzz fallback). Any sentence without a verified quote is dropped, or said with "this part isn't in your file". If `covered=false` or the top RRF score is below a threshold, Stiti says the honest "your file doesn't cover this" line *before* calling any LLM (fast path). The board shows the quote with its `char_start/end` highlighted and a "p. 42 · Unit 2" chip | **Build first** (teaching_apps #1) |
| **Tail-error guard** (Pitt study: errors pile up at the end) | n/a (a gap in NotebookLM) | For any output over about 6 sentences, re-run the verifier with a *stricter* threshold on the last third, and rewrite or drop unsupported lines | With #1 |
| **Source Guide (auto summary per source)** | Map-reduce summarisation at ingest | Background job after ingest: summarise each section (≤ 2k tokens in, 80 words out), then reduce to a per-source summary plus 3 suggested questions. Store as markdown in `~/.stiti/` with a recipe front-matter. Free-tier friendly because calls are small and sequential with backoff | Med |
| **Learning Guide (Socratic)** | Persona prompt plus pedagogy rules (LearnLM-style principles: ask before telling, chunk, adapt) | The coach already does teach-then-ask. Add the hint ladder (nudge → hint → worked example → answer), owned by **code, not the LLM**. Escape to a worked example after N misses or when the voice-emotion model reports frustration or tiredness. NotebookLM has no emotion signal | teaching_apps #6 |
| **Configure chat (style, length, custom persona)** | System-prompt presets | A per-lesson `style` and `length` field in the compiler briefing. "Talk like a strict examiner" is stored as a lesson directive, not a global one | Low |
| **Flashcards / quizzes** (difficulty, count, Hint, Explain, Got it / Missed it, retake missed, CSV) | Question generation from chunks with a difficulty knob, and generated distractors. Explain = grounded answer on the card's source chunk | Generate in the background from the *concept* graph: per concept, `router.complete(schema={q, answer, distractors[3], difficulty, cite})`. Deduplicate by embedding cosine > 0.92. Grade locally (MCQ / fill-blank exact or fuzzy, short answer via embedder coverage, LLM only when unsure). Every card is an FSRS card (`srs.py`). "Only missed" is a SQL filter. "Where should I focus?" is a SQL query over mastery plus a spoken template, no LLM. Hint = the first rung of the ladder. Explain = cited answer from the card's chunk | teaching_apps #2 |
| **Mind map (click a node to ask)** | LLM extracts a hierarchical topic tree from sources. The UI is a collapsible tree whose nodes send a chat prompt | Primary: one schema-constrained call per source, `{id,label,children[],chunk_ids[]}`, depth ≤ 3, ≤ 40 nodes, merged into the existing concept graph tables. **Degraded (no LLM):** agglomerative clustering (scikit-learn) of chunk embeddings, labelled with top keyphrases from TF-IDF over each cluster. Render with the board's graph op, colour nodes Strong / Focus / Not started from mastery, and let a node tap or "teach me X" start a lesson | teaching_apps #3 |
| **Audio Overview (two hosts)** | Multi-pass script (outline → revised outline → script → critique → revision → disfluency pass), then a multi-speaker audio model fed speaker-turn markers (DeepMind). Open-source re-creations: Meta's NotebookLlama recipe, podcastfy, open-notebook | Background job with 4 small router calls: (1) outline over the weak concepts' chunks, (2) script as `[{speaker:"T"/"S", text, cites}]` where the student voices the common mistake (Learn Your Way), (3) critique and revise with a groundedness checklist, (4) the tail guard. Render with **two Kokoro voicepacks** sentence by sentence through `ClauseChunker`, add 150–350 ms gaps at turn changes and rare scripted "hmm" / "right". Kokoro won't invent disfluencies, so the script must place them. Write `recap.wav` plus a `.json` timeline (segment → start ms → cites) so the board can show the cited line during playback. Target 2–4 minutes, about 350–600 words | teaching_apps #5 |
| **Interactive audio "Join" / real-time voice with notebook** | Segmented playback, a voice turn answered from sources, then resume. Sep 2026 version: full-duplex, barge-in at any time | Already Stiti's core: VAD barge-in → `begin_aside` doubt frame → grounded answer (feature 1) → "back to where we were" → resume at the segment boundary from the recap's `.json` timeline. Unlike Google, Stiti keeps the exchange as a local memory episode, because remembering is the point | Exists; wire to recap |
| **Video overview / slide deck with outline review** | Producer notes or outline drafted first, reviewed by the user in one batch, then slides with images and narration rendered | Whiteboard pages are the slides. Step 1 drafts the lesson outline as board page titles and asks "good, or change something?" (one spoken round). Step 2 renders. Images come from Wikimedia Commons, and numbers and quotes are pulled verbatim from cited chunks. Kokoro has no word timings, so page reveals use proportional timing (existing) | Folded into the coach |
| **Reports** (study guide, briefing, FAQ, timeline, glossary, suggested formats) | Template prompts over map-reduce summaries, plus a format suggester based on content type | Suggest the format **locally**: many dates → timeline, many "X is …" definitions → glossary, Q-heavy → FAQ. Each report is one background router call over the Source Guide plus top chunks, saved as markdown with recipe front-matter and `[[file#p42]]` cite links | Low-Med |
| **Interactive Learning Overview** (report with embedded artifacts) | A walkthrough document whose sections embed quizzes, cards and maps | This is the coach's teach-then-ask lesson. The Stiti twist is a short "lesson summary" page at the end listing the cards made, the concepts that moved, and the next review date | Exists (coach) |
| **Data Tables** | Structured extraction into a table schema | `router.complete(schema={columns[], rows[[cell, cite]]})` over chosen chunks, shown as a board table and exportable as CSV. Useful for "compare the three treaties" | Low |
| **Discover / Fast Research / Deep Research** | Web search, relevance annotation, import. Deep Research adds iterative plan, browse and report | Free APIs only (Wikipedia REST, arXiv, OpenStax) behind a "find me sources" intent. Return ≤ 5 with a one-line "why" (embedding similarity to the doubt plus one LLM call for the reasons). Import on a spoken yes. Deep Research only as a background job | Later |
| **Lecture recorder → source** | On-device recording, server-side ASR | Write chunked WAV to disk every 10 s (crash-safe). mlx-whisper runs off the hot path. Timestamps become citation spans. Then the same ingest pipeline | teaching_apps #4 |
| **Notes as sources + noteboard** | Notes indexed exactly like sources | Stiti's markdown notes in `~/.stiti/` are ingested like any source (`source_kind='note'`), so they are cited too. "Pin that" saves the last answer as a note **with its cite links kept**. NotebookLM strips citations before a note can be edited; Stiti doesn't need to | Med |
| **Connected apps (per-notebook)** | Tool calling with per-scope enable flags | MCP connectors (already the rule), plus a per-lesson allowlist in the lesson row (for example, exam mode means web off) | Low |
| **Usage meter + Generate later** | Compute-based quota with deferred jobs | `router.py` already logs `llm_usage`. Add a `jobs` table `(kind, recipe, state, not_before)`. When the free chain is exhausted, set `not_before` to the next quota reset and say so. A small "⏳ 1 job waiting" chip on the Lessons page | Med (cheap) |
| **Artifacts as snapshots** | Generated outputs don't track source edits | Store `source_sha256[]` in each artifact's recipe. On re-ingest, mark it stale and offer "refresh the recap?" | With jobs table |
| **Agentic chat (thinking steps, Stop)** | Tool-using agent with a visible trace and cancel | Stiti already says "hmm, let me check". Barge-in "stop" cancels the running router call (`asyncio` task cancel) and keeps partial board state | Exists |
| **Sites, infographics, image-generated slides, public sharing** | Code generation and image models, cloud sharing | **Skip.** No free image model fits in 8 GB, and public sharing breaks local-first | Skip |

### Local RAM and latency budget for these techniques

| Piece | Where | Approx. RAM | Hot-path latency |
|---|---|---|---|
| EmbeddingGemma-300M ONNX (existing) | local | ~0.3 GB | ~7 ms / query |
| Optional reranker `cross-encoder/ms-marco-MiniLM-L-6-v2` ONNX | local | ~0.1 GB | ~20–40 ms for 20 pairs |
| Postgres hybrid SQL (HNSW + GIN) | local | shared | < 30 ms at ~10k chunks |
| rapidfuzz quote verifier | local | negligible | < 5 ms |
| mlx-whisper small q4 / Kokoro int8 (existing) | local | ~0.5 GB / ~0.3 GB | existing budgets |
| Script, cards, map, report generation | free cloud via router, **background** | none local | off the hot path |

Only the grounded answer sits on the voice hot path: retrieval and verification take under 100 ms, and one small LLM call
streams to Kokoro. Everything long (recap scripts, decks of cards, maps, reports) is a background job, as NotebookLM's
own "generated in the background, keep working" model does it.
