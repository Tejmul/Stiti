# iTutor (itutor.study): feature inventory for Stiti

> Research date: 2026-11-20. Scope: design learning only. No proprietary code or content was copied.
> Method: official site pages, the site's own sitemap (to find every public help, "how-to-use" and blog page),
> App Store and Google Play listings, Product Hunt / G2 / review aggregators, and web searches for Reddit
> and YouTube discussion. All pages were public and logged-out. They were read as plain HTML (curl / WebFetch)
> and treated as data. REA was not needed: everything useful was in the server-rendered HTML, and nothing
> was logged into, deobfuscated or extracted from code.

---

## 0. Which "iTutor"? How it was identified

Searching for "iTutor AI tutor" on the web and the App Store turns up **at least six unrelated products**.
The one this report covers is **iTutor by Intrazero, at itutor.study**. It was picked because:

1. It is the only "iTutor" that is a full AI tutor students use in 2026. It runs on the web, iOS/iPadOS/Mac/visionOS
   (App Store id 6780195130, v1.0.1, Oct 2026) and Android (`study.itutor.app`, 1K+ installs, updated 20 Oct 2026).
2. It shipped steadily all year: launched January 2026, with monthly changelogs (Feb, Mar, May, July…) and about 146 blog posts.
3. It has every feature in the brief: voice tutoring, step-by-step and Socratic teaching, photo input,
   whiteboard-style lessons, adaptive practice, progress reports, exam prep, and teacher/organisation views.
4. Its "itutor.ai" lead is a dead end. `itutor.ai` does not resolve (curl: no response). Every listing that
   names a website for the AI tutor points to itutor.study.

Company facts from public pages: Intrazero is an Egyptian software company. The Feb 2026 changelog adds Paymob
with Egyptian-pound billing, and the site lists Intrazero as seller and maker. Product Hunt credits
Next.js, Cloudflare and Llama as build tools, and names Mahmoud Ghonemi as maker.

### Close namesakes (not the subject of this report)

| Name | Who / where | What it is | Note for Stiti |
|---|---|---|---|
| **iTutor: AI Tutor** | Phu Cuong Nguyen, hoccungitutor.com, App Store id 6779886625 | Vietnamese grades 6–12 national-curriculum tutor. Each lesson is **Learn → Practice → Review**. Has a **placement test that suggests a learning path**, keeps progress **on the device with no account**, and exports a backup file. 505 lessons. | The on-device, no-account progress store and the placement test leading to a path are both relevant |
| **iTutor: Learn by teaching** | Leonardo Baratz, App Store id 6761188706 | You **explain a topic in your own words (typed or recorded)**. The AI scores it 0–100 and lists strengths, gaps and a summary. Covers History, Geography, Physics and Biology in EN/PT/ES. | Feynman-style explain-back scoring fits a voice tutor directly |
| **AiTutor / "AI Homework Helper: AiTutor"** | App Store id 6472601851 and others | A generic snap-and-solve homework app | Different brand spelling |
| **iTutorGroup** | Ping An unit; runs TutorABC / VIPABC | Human English tutoring for China. Known for the **first EEOC AI hiring-bias settlement** ($365k, Aug 2023) | Not a student AI tutor |
| **iTutor.com** | — | Now a "compare live online tutors and lesson rates" marketplace | Human tutoring |
| **iTutorOnline / iTutorzz** | — | Human online tutoring services | Not AI |

---

## 1. Product shape in one paragraph

The design rule is **material first**. A student makes a **Subject** and uploads PDFs, Word files, slides,
or **photos** of pages, whiteboards and handwritten notes. Every tool runs inside that subject and grounds
itself in those files with page citations. These tools include chat, voice, lessons, quizzes, the plan,
reels and videos. Inside the subject sit four things:
- a **tutor** with two modes, *Just answer* and *Teach me*
- a **Voice room**, whose text-to-speech runs on the device
- an **AI Studio** with roughly 27–36 generators
- a **Study Plan**, a **subject report**, and a **memory** that keeps episodes, a concept map and beliefs about the student

Free plan: 30 tutor messages a month, unlimited voice, and small monthly allowances of the heavy generators.

---

## 2. Feature inventory

Each entry covers: **what it does · how it is triggered · output · known mechanics · limits · praise/complaints**.
Praise and complaints are covered once in §3 because independent reviews barely exist.

### 2.1 Grounded tutor chat, "Just answer" mode
- **What:** Answers questions from the subject's own files, with sources.
- **Trigger:** Type in a subject chat. *Just answer* is the default mode.
- **Output:** A full answer. Each source has a **book button** that opens the cited page beside the chat with the passage highlighted.
- **Mechanics:**
  - A provenance tracer maps each claim to a line in the student's files.
  - An answer with too few traced claims is marked **"mostly ungrounded"**.
  - Each answer is tagged *answered / partial / cannot*. Reports use this tag to show which questions the files couldn't answer.
  - A reply keeps streaming on the server if the tab closes, and picks up where it stopped when reopened.
  - The "done" signal is sent before the database saves, which the company says cut perceived delay by 1–3 s.
- **Limits:** 30 messages a month on Free, 17× that on Basic. Usage is described only as multipliers.

### 2.2 "Teach me" mode (Socratic, step by step)
- **What:** Turns the same tutor into a teacher. Of everything here, this is closest to Stiti's teach-then-ask steps.
- **Trigger:** A **chip on the message box** switches between *Teach me* and *Just answer*. You can switch mid-chat, and the choice is remembered **per subject**. "Teach me this material" walks the whole upload **concept by concept**.
- **Output / loop:**
  1. **Asks first** to find what the student already knows.
  2. Teaches **one short step** with an example from the student's own material.
  3. **Checks:** the student must apply the step. It grades the reply as *right / nearly right / guess*.
  4. Under every check are **3 buttons: type answer · get a hint · see the answer**.
  5. Hints come as a **ladder: nudge → proper hint → worked example → answer**. The answer is always reachable, but only by a deliberate tap.
  6. **Stays on the lesson.** An off-topic question gets a one-sentence answer, then the tutor returns to the step. "Explain simpler" and "like I'm five" are supported.
  7. **Explain-back:** the student explains the idea in their own words, then gets a summary of what they now know and what to look at next.
- **Key mechanic:** *"The check does not live in the tutor's instructions alone. Our server remembers which question is still open and holds the lesson there."* The open check is **server state**, so "just tell me the answer" can't talk the LLM out of it.
- **Other details:** The Voice room follows the same mode. Parents and teachers can put a student in Teach me, and the setting follows them everywhere.
- **Limit:** Interactive answers (sliders etc.) appear only in Just answer mode for now.
- Source: https://itutor.study/blog/teach-me-or-just-answer

### 2.3 Voice: Voice room and voice mode in chat
- **What:** Spoken tutoring over the same subject material and conversation.
- **Trigger:** Two entry points:
  - **Voice room** under the subject's tools: pick a voice once, then tap **Start talking**.
  - **Voice button** next to the message box: the composer turns into a "voice dock".
- **Output:**
  - Spoken answers that **stream sentence by sentence** ("starting as soon as the first sentence is ready").
  - A **floating caption whose words light up one by one** as they are spoken.
  - Two avatars with a waveform act as the **turn signal**: blue while the tutor speaks, mint when it is your turn.
  - Mute, pause and end controls.
  - **The tutor greets first**, already aware of the subject history.
  - Every spoken turn is **saved into the chat as text**.
- **Mechanics (Voice room, "Its voice never leaves your device"):**
  - **TTS runs in the browser on the GPU.** It is a one-time download: a light voice of **~60 MB**, or the best voice at **200 MB or 400 MB** depending on quality. The best voice speaks **10 languages with one consistent voice**. For Malay and Urdu it falls back to the OS voice.
  - **STT uses the browser's built-in speech recognition.** Only **question text** reaches the server.
  - Phones get the light voice. If the device is slow, it **offers a lighter voice** rather than leaving the user in silence. A "Reset voice choices on this device" button is available.
  - Because nothing is metered, voice is **unlimited** even on Free. Users can interrupt, and a **language chip switches language from the next turn**.
- **Limits:** Figures are not drawn during voice; the tutor "talks the idea through instead". STT quality depends on the browser.
- Sources: https://itutor.study/blog/voice-tutoring-on-your-device · https://itutor.study/blog/voice-mode-talk-to-your-tutor
- **Note:** This is the same split Stiti already uses: local TTS and STT, with only text going to a cloud LLM. It confirms the approach is viable as a product.

### 2.4 Interactive Lesson: a talking tutor plus a board that fills in
- **What:** A lesson presented one board at a time, built from the uploaded material.
- **Trigger:** Subject → choose **Interactive Lesson**. It takes about a minute to build.
- **Output:** A tutor talks on one side while a **board fills in as she speaks** on the other. **Every board waits** for "go on".
- **Mechanics:**
  - An idea is built across **several boards before a question** is asked.
  - A good answer pushes the idea further.
  - **A typical wrong answer jumps to a segment written for that misconception**, takes it apart, and returns to the question.
  - The student can **ask their own question at any board**, and the lesson resumes after.
  - Everything is spoken as well as written, and the voice can be turned off.
  - **Resumes at board N** with completed segments marked. "Restart for a second pass" is available.
- **Limits:** 3 lessons a month on Free, then 5, 10 and 20 on the paid tiers. "A thin upload gives a short lesson."
- Source: https://itutor.study/blog/interactive-lesson-that-teaches-you

### 2.5 Live Session: a "real class" with a pointer and annotations synced to speech
- **What:** A video-call layout. The lesson board is the shared screen, the AI teacher is an orb tile, and the student's camera tile sits below.
- **Trigger:** Subject → Create → **Live Session**. The board is written from the material in about 30 seconds.
- **Output / mechanics:**
  - Slides have 4–7 substantive lines written from the material.
  - **A pointer glides to the exact word being spoken.** Key terms are **circled**, phrases worth remembering are **underlined**, and the teacher **writes short notes in the margin** when the student asks something worth writing down. **Pages turn with the voice, never ahead of it.**
  - **The mic starts muted, and the lecture runs on its own.** A quick check comes **every 2–3 slides**: 2–4 answer cards, answered by voice or tap. A right answer gets one line of praise and a reason. Silence gets the answer kindly, and the lesson moves on.
  - **Barge-in:** unmuting makes the teacher **stop mid-word**, answer on the current slide, then resume.
  - **Navigation:** Next/Prev works instantly (three clicks ahead and the teacher teaches the slide you landed on). Going back gets a **short recap**. Voice commands work too: "go to page eight", "I didn't understand the second slide".
  - **Presence:** checked from the camera **on the device only**. If the student drifts away, the teacher gives one recap on return.
  - **End report:** each slide is marked **covered / revisit**, plus an attention score, minutes spent, and "the one thing to review next". The report is **posted into the subject chat** so the tutor knows what was studied.
- **Limits:** Live minutes per month are 10 on Free, then 30, 90 and 180, counted to the second.
- Source: https://itutor.study/blog/live-session-a-real-class-with-your-teacher

### 2.6 Interactive answers and the page beside the chat
- **What:** Small widgets placed under an answer.
- **Trigger:** Added automatically, only when they help:
  - Numbers or a formula get **sliders**, and a graph redraws as they move.
  - A process or cycle gets a **step-through** with Back, Next and Play. Cycles are drawn as a loop, and some pictures change per step, e.g. mitosis.
  - A question about "page 3 of my notes" **opens that page beside the chat** with the used passage highlighted.
- **Mechanics:**
  - Each answer ends with a **"what if" sentence with new numbers**, so it teaches even if the widget is never touched.
  - The widget may **ask for your guess first** (optional, never marked).
  - An **"iTutor saw" line logs what you moved**, and the tutor reads it next turn: "why did the margin go up?"
  - On the page view:
    - **"Walk me through this page"** explains it part by part, with **numbered marks drawn on the page**.
    - **Tapping a sentence** explains that sentence in context.
    - **Tapping part of a picture** or handwritten scan explains that region.
  - Word files are laid out into real pages.
  - Asking for a page that doesn't exist gets the true page count instead of a made-up page.
  - Every widget has a plain-text equivalent.
- **Limits:** Not shown in Teach me mode. Never graded.
- Source: https://itutor.study/blog/interactive-answers

### 2.7 Figures in chat: verified labelled diagrams, and pictures
- **What:** Labelled diagrams, optionally with **one slider that changes one thing** (angle of refraction, a formula value, a process stage), with live numbers shown, e.g. "i = 45°, r = 32°". Also plain illustrations.
- **Trigger:** Ask "draw…/show me a diagram…", or tap the **"Draw it"** button the tutor offers when it judges a figure would help. Nothing is drawn or counted unless tapped.
- **Mechanics:**
  - Rendered **server-side in the background** and takes "a few minutes". The student can keep chatting.
  - A notice with a **Show** button appears when the figure is ready. At most 2 figures are drawn at once.
  - **Verification before showing**, with sliders checked at the start, middle and end:
    1. **Layout check:** labels pointing at nothing, overlapping words, lines crossing text, text overflowing.
    2. **"Teacher check":** writes a **list of facts that must be true** for the question (blood-flow direction, electrons per shell) and compares the drawing against it.
    3. **Topology check** for diagrams: wrong connections, a valve in the wrong place.
  - Redrawn **up to 3 times**. If all fail, the student gets a short note instead ("rather show no figure than a wrong one").
  - The tutor **knows what it drew**: labels, slider range, start values. Follow-up questions are about the figure on screen.
  - Buttons: Enlarge · Download · **Something's wrong**.
  - A safety policy for school-appropriate content.
- **Limits:** Figures per month are 3 on Free, then 30, 100, 200 and 2,000 on the paid tiers. Failed tries don't count. Not available in voice.
- Source: https://itutor.study/blog/figures-in-chat

### 2.8 Inline diagrams, and doing everything in one chat
- **Small diagrams** (a few boxes with short labels) are drawn automatically for sequences, cycles, hierarchies, cause → effect, timelines and experiment designs. Comparisons get **a table instead**. A greeting or a yes/no answer never gets a diagram. "Draw that as a diagram" works on request, and diagrams carry into **PDF export**.
- **Making items in chat:** "make me a quiz on X" puts a **setup card** inside the reply. It pre-fills what the student already said (count, language, files), with extras under "More choices". **Make it** turns the card into the item.
- **Background jobs:** a tray shows work in progress, and the card updates itself when the item is ready.
- **Editing by asking:** "make that quiz harder and add 3 questions on osmosis" gives a change card with **Undo**. **Edit with AI** offers presets: Shorter / Simpler / Harder / More detail / Fix wording / Translate. **Version history** with Restore.
  - Each edit is validated, e.g. a quiz keeps exactly one correct answer per question, and a mind map keeps at least three points per branch.
- **Quizzes play in chat.** **Each answer is saved**, so the quiz resumes at question 4 on any device. Every attempt is kept with the questions as they were when taken.
- **The tutor reads the student's own results** ("what did I get wrong?"). It **cannot see answers to questions not yet reached** in an unfinished quiz.
- Source: https://itutor.study/blog/study-in-one-chat

### 2.9 Proactive practice ("Made for you")
- **Triggers:**
  - A **quiz or exam scored under 70%** brings a short practice quiz on the missed questions.
  - **3 days before an exam date** in the plan, a revision quiz on weak ideas is ready.
  - A **broken question** (no correct answer set) is auto-fixed and attempts regraded, with Undo.
  - **New files** bring an offer to update old items. Nothing changes until the student taps.
- **Limits:** At most **3 a week**, only while the student is studying. Costs none of the student's allowance. Can be switched off in Settings.
- Source: https://itutor.study/blog/study-in-one-chat

### 2.10 Photo, scan and handwriting input
- **What:** Photograph a worksheet, whiteboard, textbook page or handwritten problem. The tutor reads it, including maths notation and handwriting, and teaches from exactly that. Worked solutions can take "paste a problem, upload a photo, or attach the PDF".
- **Data point:** iTutor's own usage report says **23% of uploaded files are photographs** (1,090 of 4,643, from 267 students). The company concluded that "image input is not an accessibility extra".
- Sources: https://itutor.study/mobile-app · https://itutor.study/blog/students-choose-flashcards-not-simulations · https://itutor.study/for-math

### 2.11 Worked solutions (step by step)
- **Output steps:** identify what is asked → list formulas and principles → set up → execute → **check units** → sanity-check. Conceptual leaps are named ("use conservation of energy because friction is negligible").
- **Per problem:** a **common-pitfall note**.
- **Generator options:** a difficulty filter (intro / medium / hard). Two PDF exports: full, and a **student version without answers**. CSV export for an LMS. It can also write **new problems in the same style**.
- **Math page:** "multiple solution methods" (algebraic / geometric / computational) and "adaptive practice problems: easier when you struggle, harder as you improve".
- **Positioning:** "try first, compare, find where you diverged".
- Sources: https://itutor.study/blog/ai-worked-solutions-step-by-step · https://itutor.study/features/study-tools · https://itutor.study/for-math

### 2.12 Concept Explainer: one concept at six levels
- **Tabs:** **ELI5 · Intuitive · Standard · University · Expert · Related concepts** (upstream and downstream). The student moves between levels of abstraction.
- Source: https://itutor.study/blog/ai-concept-explainer-deep-dive

### 2.13 Flashcards, quizzes, exam simulator, exam prep session
- **Flashcards:** front/back cards from the material. Weak cards can be edited or regenerated. Reviewed on a **spaced-repetition** schedule. Flashcards and mind maps make up **51% of everything students generate**.
- **Quiz:** set the number and type of questions. Instant feedback and explanations.
- **Exam simulator:** a **timed** exam (examples: 20 questions in 25 minutes; a 45:00 timer). Choose format and time limit. The scored report shows where marks were lost and what to revisit.
- **Exam prep session:** an "adaptive, coached revision run". The student enters the exam date and focus areas, and the session targets gaps, mixing explanation with practice.
  - The night-before guide describes a **triage** that ranks topics by *exam weight × current confidence × payoff per hour*, then does practice instead of re-reading, then uses summaries for breadth, with a sleep cutoff.
- Sources: https://itutor.study/how-to-use/flash-cards · https://itutor.study/how-to-use/quiz · https://itutor.study/how-to-use/exam-simulator · https://itutor.study/how-to-use/exam-prep-session · https://itutor.study/blog/ai-exam-prep-session-night-before

### 2.14 Study Plan (goal → calendar), spaced reviews, Rebalance
- **Trigger:** Three answers: **goal, deadline (optional), free days**.
- **Mechanics:**
  - The AI reads the uploads and makes an **ordered list of units**, deciding *what* to study and in which order.
  - **A fully deterministic scheduler** does the date math: "Calendars should not guess."
  - **Each session is a guided flow**, a mix of slides, flashcards, quiz and mind map chosen for that unit. **Finishing the quiz marks the unit complete.**
  - **Rebalance:** if the student falls behind, remaining work slides forward. If the work no longer fits, the student chooses to extend the deadline, open more days, or trim. Sessions can be dragged to new days.
  - **Spaced reviews** are booked automatically at **~2 days, ~1 week, ~2 weeks** after a unit is learned.
  - **Near the deadline** a full exam simulator is scheduled.
  - **Mastery indicators per unit** come from review and quiz results.
  - A combined **agenda across all subjects**, with an optional reminder 1 hour before each session.
- **Limit:** Included on Free.
- Source: https://itutor.study/blog/meet-the-new-study-plan

### 2.15 Subject memory: episodes, concept map, beliefs ("A Tutor That Remembers")
This is the most useful technical write-up on the site, and it is very close to Stiti's brain and coach design.
- **Three stores:**
  1. **Episodes:** an append-only log, **hash-chained** for tamper evidence. Each episode stores a summary, text, concepts, salience and evidence (file plus page plus **file fingerprint**).
     - Salience is set by event type: missed check 0.7, passed check 0.6, **taught by the student 0.85**, question 0.35.
  2. **Concept map:** each file is read once by an LLM pass that returns a bounded list of concepts (name, gist, definition, **builds-on prerequisites**, pages).
     - Section titles like "Introduction" are rejected by a validator.
     - Concepts merge by a normalised name or **embedding similarity > 0.86**.
     - An assumed prerequisite becomes a node only if **two** concepts assume it.
     - **Centrality** is a weighted PageRank over the edges.
     - **Readiness bands:** 0.35 named only · 0.60 explained by a file · 0.85 passed check · 1.0 taught by a person.
     - **Teaching order** is a topological layering: prerequisites first, hubs first within a tier. This replaced an LLM outline call.
  3. **Beliefs**, e.g. "struggles with osmosis":
     - Mastery bands: <0.3 struggles · 0.3–0.6 still learning · ≥0.6 understands.
     - **Rows are never updated into a different claim.** A new row supersedes the old one, so history is kept.
     - About 20 tokens each.
     - A check's topic must route to a concept. **"An utterance is evidence, never a topic"**, so a check on "ask me the questions" is never turned into a belief.
- **Recall:**
  - **Widen first, then slice.** Candidates come from four pools: the last 500, keyword matches, routed-concept matches, and vector neighbours.
  - Then score, with **relevance as a gate, not only a weight**, and recency as a tie-break. Identical repeats collapse ("what is a cell" asked 9×). **Time phrases ("in July", "last week") become filters.**
  - One embedding per turn, and **no generative model on the read path**.
  - Budget: map ≤700 tokens, then beliefs, then episodes. About 750–1,030 tokens in total.
  - Built off the request path. Median **295 ms**, p95 445 ms, with a hard **2.5 s cap**; past the cap the memory is dropped rather than waited for.
- **Honesty:**
  - "I don't have any record of what we covered in June" replaces made-up recollection.
  - The tutor's own past narrations are flagged and **never recalled as memories**.
  - Recalled memories are **cited like pages, labelled by date**.
  - Order matters: for "what did I get wrong?" questions the record goes before the map.
- **Self-check:** a memory is verified by file-fingerprint lookup as *holds / changed / unverifiable*.
- **Teaching the tutor:** "Remember that in our class we call mitochondria the powerhouse" attaches a taught note and sets readiness to 1.0. Questions never teach.
- **Nightly loop, with no LLM:**
  - consolidate the day into one episode
  - **decay beliefs untouched for 45 days by 15%** and flag them for a re-check
  - **calibrate predicted mastery against check verdicts** (expected calibration error, reported only after ≥5 checks)
  - verify citations
- **Benchmark** (420 questions × 4 designs over 45 real histories):
  - plain retrieval **40%** · last-20-turns window **65%** · ranked episodes only **83%** · full memory **91%**
  - Cost: +0.36 s time to first token and ~750 tokens. Run-to-run noise ≈10%.
  - On "what to revise before topic X", answers with the map score 96% against ~55% without. On "a month with no activity", full memory gets 128/132 against 1/132.
- Source: https://itutor.study/blog/a-tutor-that-remembers

### 2.16 Progress tracking and subject reports
- **Student:** a **subject report** with what is solid, what is shaky, and what to review next. Based "on how you answered rather than how long you sat there". Reports were rebuilt in app v1.0.1.
  - If checks can't be tied to concepts, the report says "32 checks are on record, but none could be tied to a concept yet" instead of inventing mastery.
- **Organisations:** six report tabs (**Summary, Performance, Progress, Materials, Exams, Mastery**) with a per-student selector and an "Overall" view. Marketing also mentions predictive "at-risk" analytics and a custom report builder.
- Sources: https://itutor.study/compare · https://itutor.study/blog/itutor-march-2026-whats-new · https://itutor.study/features/analytics

### 2.17 Reels: ten micro-lessons a day
- **What:** A vertical feed of **10 tiny narrated video lessons generated fresh each day** from the uploads.
- **Mechanics:**
  - Each reel is a timeline of scenes: hook → spoken beats with icons → **self-drawing diagram** → takeaway.
  - **9 of 10 teach and about 1 checks**, and the check lands late in the set.
  - Many visual "worlds", so no two reels look alike.
  - **The whole set is written and all audio pre-rendered before the first reel plays.** The first open takes about 1 minute, then it is instant all day.
  - Double-tap saves a reel, and saved reels can get a public share link.
- **Limits:** 2 sets a month on Free, then 5, 15 and 30.
- Source: https://itutor.study/blog/reels-ten-tiny-video-lessons-a-day

### 2.18 Quiz Arena: live multiplayer quiz from your notes
- **What:** A 6-letter room code (no I/O/0/1, so it can be read aloud), up to 20 players, 10 questions at 20 s each.
- **Scoring:** 1000 points falling to 600 with time, plus a capped streak bonus.
- **Quality checks:** **distractors must be real terms from the same material**; options that are conspicuously longer are rejected; duplicate facts are rejected; recall and application questions are mixed. A failed set is regenerated with the reasons attached.
- **Solo play** includes believable bot opponents.
- Source: https://itutor.study/blog/quiz-arena-live-quiz-with-your-friends

### 2.19 Lesson videos, audio lessons, podcasts, slides and other generators
- **Videos:** **14 styles**, including **Whiteboard** ("a hand draws the whole lesson on one board, which becomes a mind map at the end"), **Worked solution** ("a hand writes the solution step by step… checks the units, boxes the answer and sets a similar problem"), Equations & proofs, Virtual experiment, Code walkthrough, **Memory path** (facts become pictures, then labels hide for recall) and Conversation (a learner voices the common misconception).
  - 10 s up to the plan's maximum length; 14 narration languages; female or male voice; ready in 5–7 minutes; checked frame by frame.
  - Limits: 1 video a month on Free, then 2, 3, 10 and 200.
- **Other generators:**
  - Audio file / podcast script
  - PowerPoint slides, infographic
  - Mind map
  - Study guide (Brief / Standard / Comprehensive)
  - Chapter Summary Pack (auto-detects chapters; an "if you only remember one thing" box; key quotes with page numbers)
  - Glossary, Reading guide, Deep research (APA 7, web)
  - Storytelling, Interactive game, Survey/Form, Trainer manual
  - 3D immersive worlds
- **Exports:** PDF, DOCX, **Markdown**, CSV.
- **Demand signal:** all immersive and game formats combined are **7.5%** of what students generate. The company's own takeaway: "novelty is not demand".
- Sources: https://itutor.study/blog/videos-on-every-plan · https://itutor.study/features/study-tools · https://itutor.study/features · https://itutor.study/blog/students-choose-flashcards-not-simulations

### 2.20 Links and web search
- **What it reads:** pasted links to web pages, PDF, DOCX or PPTX files, public Google, OneDrive or Dropbox files, and images. Up to 2 links per message.
- **What it shows:** a chip that changes from "Opening…" to "Opened…" with the site icon, plus a **snapshot of what was read**, so the student can confirm it wasn't a cookie wall.
- **Add to subject** saves the page as a file.
- **Failure handling:** when a page can't be opened, a **one-line reason plus a workaround**. It never summarises an unread page.
- **Safety:** page text is "quoted, not obeyed".
- **Web search:** a globe toggle (paid tiers), with every source listed.
- Source: https://itutor.study/blog/open-links-and-web-search

### 2.21 Languages
- **12 UI languages**, with right-to-left layout for Arabic and Urdu. **Study items in 76 languages.** Answers follow the language of the question, and new items default to the language used on that subject.
- Source: https://itutor.study/blog/study-items-in-76-languages

### 2.22 Exam modes for organisations: live oral exams and the "Retake-Ready Program"
- **Oral exam:** an examiner who asks follow-up questions and probes the edge of what the student knows. It is **proctored**, with voice-identity integrity checks.
- **Scoring:** **per requirement of a competency framework**.
- **On a non-pass,** one click builds a program with **one module per missed requirement**, four ways to learn each, and a **capstone simulator** that rehearses the retake.
- Source: https://itutor.study/blog/live-oral-exams-comeback-plan

### 2.23 Teacher, school and parent views
- **For institutions:**
  - LMS and SIS
  - classes and assignments, teacher dashboards
  - role-based access (teachers see only their classes, students only their teachers' uploads)
  - SSO (SAML/OIDC), **SCORM export**, white-label multi-tenant hosting, connection to existing LMSs (Moodle, Canvas, Blackboard, Google Classroom)
  - from **$7 per seat a month**
- **Parents:** no dedicated parent dashboard was found. The parent lever is the **Teach me setting**, which "follows them everywhere", plus blog posts on parental guidance.
- Sources: https://itutor.study/faqs · https://itutor.study/compare · https://itutor.study/blog/itutor-march-2026-whats-new

### 2.24 Subjects covered
- **"Any subject."** The math page lists arithmetic through discrete maths, and the worked-solutions page lists math, physics, chemistry, engineering and economics. Its own usage data shows heavy use for biology, literature, computing, algebra, triple science and religion workbooks.

### 2.25 Pricing and limits

| Plan | Price | Tutor messages a month | Figures | Interactive lessons | Live minutes | Reel sets | Videos |
|---|---|---|---|---|---|---|---|
| Free | $0 | 30 | 3 | 3 | 10 | 2 | 1 (≤1 min) |
| Basic | $4.99 | 17× Free (~510) | 30 | 5 | 30 | 5 | 2 |
| Premium | $9.99 | 4× Basic (~2,040) | 100 | 10 | 90 | 15 | 3 (≤1.5 min) |
| Pro | $19.99 | 2× Premium | 200 | 20 | 180 | 30 | 10 (≤10 min) |
| Enterprise | $200 | 10× Pro | 2,000 | team | team | — | 200 |

Voice room is **unlimited on every plan**. Sources: https://itutor.study/pricing plus the per-feature blog posts above.
App Store in-app purchase prices: https://apps.apple.com/us/app/itutor-study/id6780195130

---

## 3. Praise and complaints (evidence is thin)
- **Independent reviews barely exist:**
  - App Store: "not enough ratings to display".
  - Google Play: 1K+ installs, no rating shown.
  - Product Hunt: 0 upvotes and no reviews, only the maker's launch post.
  - G2: shown in search snippets as 4.8/5 from **2 reviews**, one asking for an upload limit above **100 MB**. The G2 page itself returned 403 to automated fetches, so this is search-snippet evidence only.
  - **No Reddit threads or YouTube reviews were found.** The only videos are the company's own 48-second "How to use" guides, captioned in 12 languages.
- **Self-reported rating:** the site claims "4.7/5 from 385 learner reviews". It also says reviews left before 28 Oct 2026 **earned a free month whatever rating they gave**, so treat this figure as **incentivised**.
- **The company's own published usage research** is the most honest signal. It reports 3,624 students and 902 generated items, excludes staff and test accounts, and was corrected on 10 Oct 2026.
  - Students mostly want **flashcards and mind maps** (51%) and **photo input** (23% of uploads).
  - Flashy formats get little use (immersive and games together are 7.5%).
  - Study activity peaks **after 5 pm and about 5 days before a deadline** (https://itutor.study/when-students-study-with-ai).
- **Disclaimers the company makes:** "Answers are generated by AI and can be wrong; tap the flag" (Play listing). A figure takes minutes, a video 5–7 minutes, and a lesson needs enough material.
- **Likely pain points (inferred, not user-reported):** a tight free message allowance (30 a month), metered generators, slow figure and video generation, and voice STT quality tied to the browser.

---

## 4. Value table for Stiti (voice whiteboard tutor, 8 GB M2, free cloud LLMs, local Whisper + Kokoro)

| iTutor feature | Value for Stiti | Free + local-first on 8 GB? | Build idea in Stiti terms |
|---|---|---|---|
| **Teach me with a server-held open check and a hint ladder** (2.2) | **High** | Yes. Pure state logic. | Coach keeps an `open_probe` row (concept, question, expected answer, attempts, hint_rung 0–3) in Postgres. Laya routes each utterance: *answer to probe / hint request / reveal / off-topic*. Off-topic gets a one-line answer and a return to the probe. The LLM only words the next rung (nudge → hint → worked example → answer). The probe can't be dropped because the LLM was persuaded. End each mini-lesson with a **spoken explain-back**, graded into mastery evidence. |
| **Just answer / Teach me toggle per subject** (2.2) | High | Yes | A voice command ("just tell me" / "teach me") sets a per-subject mode in the user model. The default comes from a LESSONS.md rule. Doubt mode = Just answer; lesson mode = Teach me. |
| **Board-synced lecture: pointer on the spoken word, circle/underline, margin notes, barge-in, "go to page 8", check every 2–3 boards, covered/revisit report** (2.5, 2.4) | **High** | Yes. Kokoro gives word timings, or estimate from phonemes; the whiteboard is local HTML/SVG. | Whiteboard page = a list of "board blocks". The TTS stream sends word timestamps, so the whiteboard moves a pointer and runs `circle(term)` / `underline(phrase)` marks emitted by the lesson script. VAD barge-in stops TTS mid-word, answers on the current board, then resumes. Voice navigation goes through Laya (`goto_board`). At the end, write a markdown note listing each board as covered or revisit plus "one thing to review", and add it to memory. |
| **Misconception branches in lessons** (2.4) | High | Yes (needs the LLM at lesson build time) | When building a lesson, ask the LLM once for each probe's common wrong answers plus a fix segment. Store them as JSON. At run time, Laya or embedding similarity matches the learner's answer to a misconception and plays the fix segment with no LLM call. |
| **Resume at board N; restart for a second pass** (2.4) | Med | Yes | Store the lesson cursor per learner per file in Postgres. "Continue my lesson" is a fast-path action. |
| **Evidence-backed memory: episodes + concept map + belief rows with supersession, readiness bands, topological teaching order** (2.15) | **High** | Yes. Postgres + pgvector + recursive CTEs, with no LLM on the read path. | Coach already maps a file into concepts. Add `builds_on` edges (only if ≥2 concepts assume a prerequisite), merge by embedding >0.86, PageRank centrality, and a topological teaching order (prerequisites first, hubs first). Make mastery **belief rows that are never overwritten**, with evidence ids. Episode salience: taught 0.85, missed probe 0.7. Relevance-gated recall, time words as filters, "I have no record of that" as an explicit line. Their 295 ms median and 2.5 s drop cap fit Stiti's <100 ms memory target if precomputed. |
| **Nightly consolidation: decay 15% after 45 days, calibrate predicted vs actual, verify citations** (2.15) | High | Yes (cron, no LLM) | A background job in `~/.stiti`: decay stale mastery and queue a re-probe, compute calibration error of the coach's predicted mastery before each probe, and feed it to Laya's confidence calibration. |
| **Study plan: AI orders units, deterministic scheduler, Rebalance, spaced reviews at 2d/1w/2w, exam simulator near deadline** (2.14) | **High** | Yes | **Exam mode** = deadline + free days → the coach's topological order fills the calendar (pure Python). **Day mode** = "what should I do tonight?" picks today's session, made of a teach step, probes and a review. Rebalance is a fast-path action. Alarms and reminders already exist in Stiti. |
| **Proactive "made for you" practice** (<70% → practice on misses; 3 days before exam → weak-topic quiz; new material → offer to update) (2.9) | High | Yes | Background trigger. Laya decides when to surface a spoken nudge ("I made you 5 quick probes on the ones you missed"), at most 3 a week, with a setting to switch off. |
| **Verified figures with one slider, "Draw it" opt-in, background render, layout + fact-list + topology checks, up to 3 retries** (2.7) | High | Partly. LLM-generated SVG/JSON plus local render; checks are cheap geometry plus one LLM fact-list call. | Whiteboard draws figures as SVG from a JSON spec. Local checks: label anchors inside bounds, no text overlap or overflow. LLM writes "facts that must hold", and a second pass compares them with the spec. Retry ≤3, otherwise say "I'll explain it instead". Offer "want me to draw it?" by voice rather than always drawing. Keep **Wikimedia Commons** for real photos and use generated SVG for schematic diagrams. |
| **Interactive answers: sliders with a "what if" line, step-through processes, logging what the learner moved** (2.6) | Med | Yes (front-end only) | Whiteboard widgets: `slider(var, range, formula)`, `steps([...])`. Pass the "Stiti saw you move X to Y" event back as context so a spoken follow-up knows what happened. |
| **Page beside the chat with the cited passage highlighted; "walk me through this page" with numbered marks; tap a sentence or picture region** (2.6) | High | Yes. Local PDF render (pdf.js / PyMuPDF), OCR only if needed. | When the coach cites the learner's file, the whiteboard opens that page with the passage highlighted. "Walk me through page 3" puts numbered marks on the page while Kokoro explains each part. |
| **Photo / scan / handwriting input** (2.10; 23% of uploads) | High | Partly. Free cloud vision tiers (e.g. Gemini AI Studio) for reading; local Apple Vision OCR for printed text. | "Look at this" via iPhone Continuity Camera or a file drop. Apple Vision OCR runs locally; hard handwriting or maths goes to a free vision LLM. The result becomes a coach item: concepts plus a "doubt" thread. |
| **Worked solutions: units check, pitfall note, answer-free student version, similar problem** (2.11) | Med | Yes (LLM) | Whiteboard "worked solution" page renders step by step in sync with speech. Always add a **pitfall line** and a **"now you try"** similar problem. Teach me mode hides the final answer until the hint ladder ends. |
| **Concept explainer at six levels (ELI5 → expert + related)** (2.12) | Med | Yes | Voice commands "simpler" / "deeper" move the explanation level. "Related" comes from coach graph neighbours, not the LLM. |
| **Flashcards + spaced repetition; timed exam simulator with marks report; triage of exam weight × confidence × payoff** (2.13) | Med–High | Yes | Probes double as flashcards (FSRS locally). Exam mode runs a timed spoken mock with a report saved as markdown. Night-before triage ranks topics by coach mastery × exam weight. |
| **Voice: TTS sentence streaming, word-by-word captions, turn-signal visuals, greets first, language chip, local TTS + browser STT** (2.3) | High (mostly done) | Yes. Stiti already does local Whisper + Kokoro. | Add word-level karaoke captions on the whiteboard from Kokoro timings, a visible whose-turn signal, and a **memory-aware greeting** ("last time we stopped at osmosis, and you missed 2 probes"). Lower-quality voice fallback if the Mac is under load. |
| **Live presence via camera (on-device), recap on return** (2.5) | Low–Med | Possible (Vision face presence is cheap) but camera use is sensitive | Optional: if the learner leaves (no VAD and no face for N minutes), give one recap on return. Skip the camera at first and use silence and idle time instead. |
| **Memory as citation; "I have no record"; narration not stored as memory** (2.15) | High | Yes | When Stiti says "last week we…", show the episode date as the source. Flag Stiti's own recaps at write time so they never come back as memories. This fits Stiti's "never invent memories" principle. |
| **Edit item by asking, with Undo and version history** (2.8) | Med | Yes | Markdown notes in `~/.stiti`, versioned with git or rows. "Make that note shorter" makes an edit with spoken confirmation and "undo" as a fast-path action. |
| **Reels: 10 daily micro-lessons, audio pre-rendered before play** (2.17) | Low–Med | Yes (Kokoro pre-render offline) | "Daily 10": every morning a background job pre-renders 10 short spoken micro-lessons on concepts due for review. Play hands-free, instantly. The pre-render pattern matters more than the vertical feed. |
| **Quiz Arena (multiplayer) and distractor quality rules** (2.18) | Low (multiplayer) / Med (rules) | Yes | Skip multiplayer. Adopt the **distractor rules** for probes: wrong options must be real terms from the same file, no option conspicuously longer, no duplicate facts, a mix of recall and application. |
| **Lesson videos (14 styles), 3D worlds, games, podcasts** (2.19) | Low | Video rendering is heavy for 8 GB; skip | iTutor's own data shows little demand (7.5%). The whiteboard plus voice already gives the "whiteboard video" experience live. |
| **Links + web search with a "what I read" snapshot and honest failure** (2.20) | Med | Yes (MCP fetch connector) | A doubt can include a link. Fetch through an MCP connector, show a page snapshot on the whiteboard, cite it, and offer "add to this subject". Say plainly when it can't be read. |
| **Oral exam scored per requirement, plus a retake program** (2.22) | Med | Yes | Exam mode, oral: Stiti asks spoken questions with follow-ups and scores each concept against the coach map. Failed concepts become the next study-plan block. |
| **Subject report: solid / shaky / review next, "N checks not tied to a concept" honesty** (2.16) | High | Yes | A Memory-page card per file: mastery bands per concept, the next concept to study, and an honest count of evidence. No chat transcripts shown, per the owner's no-chat-history-in-UI rule. |
| **Teacher / LMS / SSO / SCORM / parent views** (2.23) | Low | n/a | Not relevant to a single-user local buddy. |

---

## 5. Top 5 to adopt (in order)

1. **A probe Stiti owns, not the LLM.** The open check lives in the coach's state, with the 3-rung hint ladder (nudge → hint → worked example → answer), a one-line return from off-topic questions, and a spoken explain-back at the end. The LLM can't be talked out of the step. This is Stiti's "decisions are made by Stiti, not the LLM" rule applied to tutoring.
2. **Board-synced voice lecture.** Use Kokoro word timings to move a pointer and circle/underline marks on the whiteboard. Add barge-in that stops mid-word and resumes, "go to board N" by voice, a check every 2–3 boards, misconception branches written at build time, resume-at-board-N, and a covered/revisit markdown report saved to notes.
3. **Evidence-backed learner memory.** Coach concepts with `builds_on` edges, PageRank hubs and topological teaching order. Mastery as belief rows that are never overwritten, with evidence ids. Relevance-gated recall with time filters. Explicit "I have no record". Nightly decay, calibration and verification with no LLM. Their benchmark (40% → 91%) is the strongest evidence that this design is worth building.
4. **Deterministic study plan with proactive practice.** For exam and day modes: the AI decides what to study and in what order, plain Python decides dates. Add Rebalance, spaced reviews at 2d/1w/2w, a mock exam near the deadline, and auto-practice after a score under 70% or 3 days before an exam (at most 3 a week).
5. **Verified, opt-in figures and the learner's own page beside the explanation.** Generate SVG figures with one slider and run layout, fact-list and topology checks with up to 3 retries ("no figure beats a wrong one"). Offer "want me to draw it?" instead of always drawing. Open the cited page of the learner's file with the passage highlighted and numbered marks while explaining. Also: photos are 23% of uploads, so add photo / Continuity Camera input to the coach.

---

## 6. Sources (all checked on 2026-11-20; HTTP 200 unless noted)

**Official, iTutor by Intrazero**
- https://itutor.study · https://itutor.study/for-students · https://itutor.study/features · https://itutor.study/features/study-tools
- https://itutor.study/pricing · https://itutor.study/faqs · https://itutor.study/compare · https://itutor.study/mobile-app · https://itutor.study/for-math
- https://itutor.study/how-to-use · https://itutor.study/how-to-use/flash-cards · https://itutor.study/how-to-use/quiz · https://itutor.study/how-to-use/exam-simulator · https://itutor.study/how-to-use/exam-prep-session · https://itutor.study/how-to-use/mind-map · https://itutor.study/how-to-use/live-session
- https://itutor.study/features/analytics · https://itutor.study/features/assessments · https://itutor.study/features/study-planner
- Blog:
  - https://itutor.study/blog/teach-me-or-just-answer
  - https://itutor.study/blog/voice-tutoring-on-your-device
  - https://itutor.study/blog/voice-mode-talk-to-your-tutor
  - https://itutor.study/blog/interactive-lesson-that-teaches-you
  - https://itutor.study/blog/live-session-a-real-class-with-your-teacher
  - https://itutor.study/blog/interactive-answers
  - https://itutor.study/blog/figures-in-chat
  - https://itutor.study/blog/study-in-one-chat
  - https://itutor.study/blog/meet-the-new-study-plan
  - https://itutor.study/blog/a-tutor-that-remembers
  - https://itutor.study/blog/ai-worked-solutions-step-by-step
  - https://itutor.study/blog/ai-concept-explainer-deep-dive
  - https://itutor.study/blog/ai-exam-prep-session-night-before
  - https://itutor.study/blog/reels-ten-tiny-video-lessons-a-day
  - https://itutor.study/blog/quiz-arena-live-quiz-with-your-friends
  - https://itutor.study/blog/videos-on-every-plan
  - https://itutor.study/blog/open-links-and-web-search
  - https://itutor.study/blog/study-items-in-76-languages
  - https://itutor.study/blog/live-oral-exams-comeback-plan
  - https://itutor.study/blog/students-choose-flashcards-not-simulations
  - https://itutor.study/blog/itutor-january-2026-launch
  - https://itutor.study/blog/itutor-february-2026-whats-new
  - https://itutor.study/blog/itutor-march-2026-whats-new
  - https://itutor.study/blog/itutor-may-2026-whats-new
- Usage research: https://itutor.study/when-students-study-with-ai

**Store listings**
- App Store, iTutor (Intrazero): https://apps.apple.com/us/app/itutor-study/id6780195130 (also https://apps.apple.com/app/id6780195130)
- Google Play: https://play.google.com/store/apps/details?id=study.itutor.app (1K+ installs, updated 20 Oct 2026)

**Third-party** (thin coverage)
- Product Hunt: https://www.producthunt.com/products/itutor (read via WebFetch; plain curl gets 403)
- G2: https://www.g2.com/products/itutor/reviews (403 to bots; review details from search snippets only)
- Stork.ai profile: https://www.stork.ai/en/itutor

**Namesakes**
- iTutor: AI Tutor (Vietnam): https://apps.apple.com/app/id6779886625 · https://hoccungitutor.com
- iTutor Learn by teaching: https://apps.apple.com/app/id6761188706
- AiTutor homework helper: https://apps.apple.com/app/id6472601851
- iTutorGroup EEOC settlement: https://www.scmp.com/tech/article/3230722/chinese-tutoring-firm-settles-us-agencys-first-bias-lawsuit-involving-ai-software · https://news.bloomberglaw.com/esg/eeoc-settles-first-of-its-kind-ai-bias-lawsuit-for-365-000
- iTutor.com (tutor marketplace): https://www.itutor.com
- itutor.ai: does not resolve (no DNS / HTTP response on 2026-11-20)

---

## REA evidence (public pages)

> Added 2026-11-20. This section extends the docs-based study above with REA captures of **public, logged-out pages
> only**. No login, no sign-up, no auth bypass, no admin calls, nothing deobfuscated beyond reading string literals
> in the JavaScript the public pages already ship. Everything REA returned was treated as data. **Prompt-injection
> check:** nothing found that asked an agent to run, install, download or send anything. `llms.txt` and `robots.txt`
> address AI agents directly (a request to cite with attribution, a `Content-Signal: ai-input=yes, ai-train=yes`
> line and an advertised query endpoint). These are licence notes and were only read, never acted on.

### Evidence index

| Evidence id | REA operation | Page | What it gave |
|---|---|---|---|
| `ev_4fde1154…0b3x2z` (pre-existing capture) | `inspect_web_page` | `/` | 37 scripts, 36 resources, 175 DOM URLs (the full public route map), a11y tree of the hero demo, empty storage on first load |
| `ev_7c2159bf…b35b` | `inspect_web_page` (+ storage keys, JSON/WS shapes) | `/ai-tutor-with-voice` | Voice-room claims (mic gating, tap to interrupt, 12 languages), the page's own route chunk, service-worker cache names, localStorage key `sidebarCollapsed` |
| `ev_4ccdb171…c42f` | `inspect_web_page` | `/changelog` | Release timeline (Pre-Aug 2025 → May 2026) |
| `ev_680151cc…967e` | `inspect_web_page` | `/blog/live-session-a-real-class-with-your-teacher` | Live Session mechanics (pointer, circle, underline, muted mic, camera on device) |
| `ev_80e8accb…4283` (parent), views `ev_dace4a42…e248` (summary), `ev_b1be989a…b4f6` (routes) | `analyze_web_bundle`, `javascript-routes` view | `/` | 24 sources, 44 route patterns, 100 occurrences. One Next.js App Router page (`/[locale]`), the rest are marketing links. `application_routes: unknown`, because the app itself is behind login |
| `ev_21ef9b01…26db` | `capture_web_screenshot` | `/` | Hero layout (screenshot only, not reproduced here) |
| `ev_14ba635e…e6b4` | `inspect_web_event_listeners` (`form button`) | `/` | No direct listeners. React delegates events to the root, so the marketing demo has no handler code worth reading |

Plain public fetches (curl) added: `robots.txt`, `llms.txt`, `manifest.json`, `sw.js`, the CSP response header, and
one call to the advertised public `/api/ask` endpoint, which `robots.txt` explicitly allows and `llms.txt` invites
machines to use. String literals were grepped from the 25 public `_next/static/chunks/*.js` files that REA listed in
the captures above.

### Tech stack (fingerprints)

| Layer | Finding | Evidence |
|---|---|---|
| Frontend | **Next.js App Router** with a `[locale]` segment and a `(website)` route group. Per-page chunks such as `app/[locale]/(website)/ai-tutor-with-voice/page-*.js`. **GSAP** (6 chunks) and **Framer Motion** for the animated hero. Self-hosted woff2 fonts plus Google Fonts. A separate `home2.min.css` design system (190 KB) | script URLs in `ev_4fde…`, `ev_7c21…`. Changelog: "new home2 design system" |
| HTTP client | **axios** instance, `baseURL` = `API_URL` env var or `https://itutor-api.intrazero.com`, `timeout: 120 s`, `withCredentials: true`. **Sliding JWT**: the response interceptor stores a fresh token from an `x-access-token` header. Errors are read from `response.data.detail` | chunk `22356-*.js` (string literals) |
| Backend | `api.itutor.study/v1/*`, a REST API that is **FastAPI-shaped** (`detail` errors, `page`/`page_size` paging, `subject_thread_id` filters). Admin health probes are named **`/v1/admin/health/{database,qdrant,redis,s3}`** plus `/v1/admin/queues` | same chunk. Stack inferred from names, not confirmed server-side |
| Vector store | **Qdrant** (a separate vector DB, unlike Stiti's single Postgres + pgvector) | `getQdrantHealth()` endpoint name |
| Jobs and cache | **Redis** plus a job queue (figures, videos, lessons and reels all run "in the background") | `/v1/admin/queues`, `/v1/admin/cache/{stats,clear}` |
| Files | S3-compatible **Cloudflare R2** (`*.r2.cloudflarestorage.com` in CSP `connect-src`/`media-src`) and `cdn.itutor.study` | CSP header |
| LLM layer | **Multi-provider**: `/v1/admin/analytics/providers`. **Routing policies** with CRUD and a **`/v1/routing-policies/test`** endpoint. **Reasoning templates** (prompt templates with `is_active`) with CRUD. Changelog: "multi-model support" (pre-Aug 2025). Product Hunt lists Llama | chunk `22356-*.js`. Model names are not in public code |
| Learner analytics API | `/v1/mastery/{user}` plus `/topics`, **`/heatmap` (date range, subject thread)**, **`/trends?days=30&topic=`**, `/subject/{id}`. `/v1/analytics/{at-risk-students, risk/{id}, recommendations/{id}, diagnostic/quiz, diagnostic/{id}/results, engagement, performance, progress, trends}`. `/v1/reports/{generate, history, {id}/status, {id}/download}` (async report jobs) | same chunk |
| Realtime voice | **`wss://voice.intrazero.app`** (a separate voice service on the parent company's domain) plus `wss://api.itutor.study` and `wss://itutor.study`. Changelog Sep 2025: "voice chat with real-time audio streaming" | CSP `connect-src` |
| On-device ML | **MediaPipe** (`cdn.jsdelivr.net/npm/@mediapipe/`, `storage.googleapis.com/mediapipe-models/`): the Live Session "presence on device only" check and the proctoring "no-face" cards. `worker-src blob:` and `'unsafe-eval'` are consistent with in-browser WASM/WebGPU inference (the Voice-room TTS) | CSP |
| In-browser code | **Pyodide** (`cdn.jsdelivr.net/pyodide/`) plus **Monaco editor 0.55.1**: "code challenge" interactive blocks and code walkthroughs run Python in the browser | CSP |
| Payments | **Paddle** (`cdn.paddle.com`, `buy.paddle.com`), **Paymob** (`accept.paymob.com`, Egypt). Changelog Nov 2025 also says Stripe | CSP + changelog |
| Auth | Google and Apple sign-in, email+password (10+ characters), **MFA challenge** state, **Cloudflare Turnstile** on forgot-password, SSO init (`/v1/public/sso/{id}/init`), admin **impersonation** | chunk literals, home a11y tree |
| Edge, analytics, PWA | Cloudflare (server header, NEL, Insights). GA4, Google Ads, GTM. **Custom web-vitals beacon** `POST /v1/public/vitals` with `{route, group, locale, device: phone/tablet/desktop, connection.effectiveType, metrics}` via `sendBeacon`. **PWA**: `sw.js` v1.1.1, network-first, never caches `/api/` or `/v1/`, offline page. Manifest shortcuts: Subjects, Reports, Planner | chunk `73884-*.js`, `sw.js`, `manifest.json` |
| Machine-facing | `llms.txt` (+ 11 translated answer banks + `llms-full.txt`). Public **`/api/ask?q=`** returns `{query, locale, retrieval: "hybrid" \| "lexical", matched: bool, answer, answer_id, canonical_url, detail, disambiguation, recommended_citation, related_answers[{id, question, answer, url, relevance}], related_pages, license}`. A nonsense query returned `retrieval: "lexical", matched: false`. `robots.txt` also allows `/api/a2a` (agent-to-agent) | curl of the advertised endpoint (value-free shape only) |

### Route and feature map (from public DOM links + `robots.txt` + manifest)

- **Marketing (public):** `/`, 12 locale roots (`/ar /de /es /fr /id /it /ms /nl /pt /tr /ur`), `/features`,
  `/pricing`, `/how-to-use`, `/help`, `/faqs`, `/answers/[slug]`, `/blog/[slug]`, `/changelog`, `/integrations`,
  `/compare/itutor-vs-{chatgpt, chegg, khan-academy, lorea, notebooklm, quizlet, studyfetch}`, about 30 SEO landing pages
  (`/ai-tutor-with-voice`, `/ai-exam-simulator-from-textbook`, `/ai-oral-exam-for-employees`,
  `/anti-ai-proctoring-oral-exams`, `/ai-3d-learning-world`…), and research pages (`/when-students-study-with-ai`,
  `/do-students-want-ai-answers`, `/how-students-use-ai`).
- **App (disallowed in robots, behind auth, not visited):** `/public/subjects`, `/public/reports`,
  `/public/planner-items`, `/subjects/`, `/materials/`, `/ai-chat/`, **`/voice-chat/`**, `/quizzes/`, `/progress/`,
  `/exam-share/`, `/settings/`, `/profile/`, plus institution areas `/lms/`, `/dashboard/`, `/admin/`, `/corporate/setup/`.
  Public verify pages exist for certificates and curricula (`/public/ld/verify/`, `/public/curriculum/`).
- **Changelog timeline** (`ev_4ccdb171…`): core multi-model tutor (pre-Aug 2025) → material analysis + **real-time
  voice streaming** (Sep 2025) → public chat with no account (Oct 2025) → subscriptions (Nov 2025) → **Study Planner
  with 23 plan types** + PWA (Dec 2025–Jan 2026) → 12 languages → mobile apps → AI Studio (Mar–Apr 2026) → **AI
  Curriculum Builder: an "8-pass" generator, Bloom-tagged learning outcomes, typed interactive blocks (ordering,
  matching, drag-drop, hotspot, timeline, code challenge), SCORM export** (Apr 2026) → L&D plans with **anti-AI
  exam probes (cough/clap/hum acoustic detector, multi-display detection, voiceprint speaker similarity)** and
  "affect analysis… per-requirement narration" (May 2026).

### UI patterns seen

- **Hero = the product's input→output in one picture:** a handwritten notes page on grid paper ("01 / 05 Calculus",
  a derivative worked line by line, a red "exam Friday!!" margin note) that cycles into Mind map → Study plan
  ("TUE · Derivatives · 25 min") → Flashcard → a clickable 3-option Quiz ("Correct!"). The sign-up card sits beside it
  (`ev_4fde…` a11y tree, screenshot `ev_21ef…`).
- **Voice dock** (blog text): two avatars with a live waveform between them as the turn signal (blue = tutor,
  mint = you), plus a floating caption whose words light up as they are spoken.
- **Live Session = meeting layout:** the board is the shared screen, the AI teacher is a "calm orb that breathes
  while it speaks", the learner's camera is a tile, and the mic is a single button (`ev_680151cc…`).
- **Mode chip on the composer** (Teach me / Just answer), a "Draw it" opt-in button, a background job tray, setup
  cards inside chat, a dark-mode toggle, a language picker with RTL, and a remembered collapsed sidebar
  (localStorage `sidebarCollapsed`).
- **Public honesty patterns:** the incentivised-review disclaimer is printed under the rating, and research pages
  state their method and limits (sample, window, "read the direction, not the percentage").

### New behavioural facts not in the docs study above

- **Voice room mic gating:** "While the tutor speaks, **and for a moment after**, the microphone ignores what it
  hears." In the Voice room, interrupting is **tap to interrupt**. Only the Live Session advertises unmute-to-barge-in
  (`ev_7c2159bf…`).
- **Two voice paths:** the Voice room uses on-device TTS (unlimited, unmetered) plus the browser's built-in speech
  recognition. Live Session minutes are **metered to the second**, which together with `wss://voice.intrazero.app`
  points to **server-side realtime voice** for Live Session and oral exams. This is an inference.
- **Voice-room TTS tiers:** light ≈ 60 MB; best = 200 MB or 400 MB (the size pattern of one ~100 M-parameter model at
  fp16/fp32), with one voice across 10 languages including Arabic and Turkish. If the device turns out to be slow,
  the room says so and offers a lighter voice; Malay and Urdu fall back to the OS voice. The exact model is not
  identifiable from public code.
- **Teach me usage data** (`/do-students-want-ai-answers`, 2,663 students, 8 Sep–9 Oct 2026):
  - 29% chose Teach me at least once, and **71% never touched the default** (Just answer).
  - Teach-me turns were 40% of chat turns and 35% of spoken turns, at **6.3 turns per exchange against 3.5**.
  - On 29 Sep they **changed Teach me to "explain first and ask fewer check questions"**, after feedback that
    "its questions came too early".
  - The mode is saved **per account**. The older blog post said per subject.

---

## Techniques for Stiti

Each entry: what iTutor does, then the **likely technique**, then a **Stiti sketch** (free, local, 8 GB M2, no local
LLM) with where it lives and the UI entry point. "Exists" marks what Stiti already has, so only the delta is new.

1. **Teach-me pacing: explain first, check later** (their 29 Sep fix)
   - *Technique:* checks are rationed per idea rather than per sentence. A check fires after a full explanation
     unit, and the open check is server state.
   - *Stiti:* `tutor/coach.py` currently asks after ≤ 2 sentences. Add a pacing knob: `CHECK_EVERY` = one full
     idea (organizer → teach → worked_example), then one check. If the learner shows the "too many questions"
     signal (short "yes/ok" answers, or an annoyed tone from `voice/emotion_model.py`), stretch it to every 2
     concepts. Keep Teach-me as Stiti's default (the opposite of iTutor's default, because the owner asked for a
     teacher). Store the mode per learner in the user model, with "just tell me" as a Laya intent.
   - *UI:* a mode chip on the board header.

2. **Mic gating with a tail, plus tap to interrupt**
   - *Technique:* half-duplex capture. Mic input is ignored while TTS plays and for a hangover of a few hundred ms
     after it stops. Explicit tap-to-interrupt in the voice room. Barge-in only where the mic is deliberately unmuted.
   - *Stiti (exists: `tutor/ears.py` `EchoGuard`, `player.py` barge-in):* make the post-speech hangover an explicit,
     measured constant (start at 300–500 ms, tune on recordings). Add a **tap/space-bar "stop and listen"** on the
     board as a second, never-wrong interrupt path beside VAD barge-in.
   - *Where:* `tutor/ears.py`, `frontend/src/components/board/BoardApp.tsx`.

3. **Word-timed captions and a pointer on the spoken word**
   - *Technique:* per-word timestamps from TTS drive a karaoke caption and a pointer, circle or underline anchored
     to a word index. Pages turn on audio progress, never ahead of it.
   - *Stiti:* Kokoro's `KPipeline` returns per-token `start_ts`/`end_ts` (English) from its predicted durations.
     Elsewhere, fall back to splitting the clip length by character or phoneme count. Send
     `{cue, words: [[w, t0, t1]]}` over the board WebSocket. `player.py` (around the "ops without their own word cue
     are spread across the sentence" code) fires each highlight op at its anchor word's `t0` instead of spreading
     ops evenly. Add an optional `at_word` to `Op` in `tutor/lesson.py`; the LLM already emits `at`.
   - *UI:* `board/runtime.ts` renders a one-line caption under the board with the current word lit.
     Cost: no model, under 1 ms per word.

4. **Auto-paced lecture: checks every 2–3 boards, silence handled kindly, jump-ahead and recap-on-back**
   - *Technique:* a precomputed lesson script with a cursor per learner. Navigation is instant and the narrator
     re-syncs to the landed board. Each board carries a pre-written one-line recap. Silence on a check, after a
     timeout, reveals the answer with one reason and moves on.
   - *Stiti:* `tutor/planner.py` already writes segments. Ask for one `recap` sentence per segment in the same
     strict JSON pass, so no extra LLM call is needed at play time. Add Laya intents `goto_board(n)`,
     `didnt_get(n)` and `back`. A silent check after about 8 s goes to `say(answer + why)`, and the concept is
     marked "shaky" in mastery.
   - *UI:* board page numbers become clickable. "Covered / revisit" chips go on the end-of-lesson note
     (`lessons/NoteView.tsx`).

5. **Mastery as a time series: heatmap and trends** (`/v1/mastery/{u}/heatmap`, `/trends?days=30`)
   - *Technique:* mastery is an append-only event log and the current value is a projection. Views are
     concept × day heatmaps and 30-day trends.
   - *Stiti:* today `tutor/mastery.py` stores the current BKT p per source in JSON. Add a Postgres
     `mastery_events(id, source_key, concept, verdict, hints, p_before, p_after, evidence_ref, ts)` table. Keep the
     JSON as the readable projection (principle 7). This gives iTutor's "beliefs never overwritten" history for free.
   - *UI:* `lessons/Progress.tsx` gets a small concept × day heatmap and a sparkline per concept. Recursive
     CTE / `date_trunc` queries take under 10 ms.

6. **"At risk", recommendations and a diagnostic quiz** (`/v1/analytics/risk`, `/recommendations`, `/diagnostic/quiz`)
   - *Technique:* risk = predicted recall at the exam date, recommendation = next best concept, diagnostic =
     placement probes.
   - *Stiti (exists: `srs.at_risk(course_id, at, threshold=0.9)`, coach probes):* compute "at risk on exam day" as
     FSRS retrievability at the exam timestamp below 0.9, weighted by concept centrality. "What should I study
     tonight?" (day mode) = top-k of `(1 − R_exam) × centrality × minutes-fit`, which matches their night-before
     triage formula. Pure Python, no LLM.
   - *UI:* a "Tonight" card on the Lessons page.

7. **Hybrid retrieval with an honest `matched` flag** (`/api/ask`: `retrieval: hybrid|lexical`, `matched`, `relevance`)
   - *Technique:* lexical + vector fusion. When fusion confidence is low, return `matched: false` (lexical-only
     related items) instead of an answer.
   - *Stiti:* for doubts over his file, combine Postgres FTS (`ts_rank_cd`) and pgvector cosine with Reciprocal
     Rank Fusion. Gate on the top fused score and on the vector similarity of the top chunk. Below the gate, say "your
     file doesn't cover this" and offer a general answer labelled as general (build-order item 1 in
     `teaching_apps.md`). Also keep a **canonical answer bank** per file: once a doubt has a good answer, store
     `(question embedding, answer, page)`. A repeat above about 0.9 cosine is answered from the bank with no LLM
     call, which fits the fast path.
   - *Where:* `brain/memory.py` retrieval plus a `tutor/book.py` doubt path.

8. **LLM routing policies, prompt templates and a test endpoint** (`/v1/routing-policies[/test]`, `/v1/reasoning-templates`, provider analytics)
   - *Technique:* each task (lesson plan, concept map, grading fallback, figure) has a policy, which is an ordered
     provider/model list with limits. Prompts are versioned templates with an active flag. A "test" button runs a
     fixed prompt through a policy. Per-provider latency and error analytics feed the ordering.
   - *Stiti (exists: `router.py` free-tier chain):* add `~/.stiti/routing.yaml` (task → providers, `max_tokens`,
     strict-schema yes/no, timeout) and `~/.stiti/prompts/<task>.md` with a version line. Log per call
     `(task, provider, ms, ok, schema_valid)` to Postgres. Add `stiti route test <task>` to run a golden input across
     the chain. Reorder automatically by rolling p50 latency and schema-valid rate. This keeps the brain/LLM split
     clean: the LLM is swappable per task.

9. **Background job queue with a "ready" notice** (Redis queue + `/v1/reports/{id}/status`)
   - *Technique:* heavy generation runs off the request path. The client polls a status endpoint or gets a push,
     then shows a "Show" toast.
   - *Stiti (Postgres only, no Redis):* a `jobs(id, kind, payload, state, result, ts)` table claimed with
     `SELECT … FOR UPDATE SKIP LOCKED` by one worker thread, with `LISTEN/NOTIFY` to push "ready" to the web server
     and then over the WebSocket to the page. Use it for concept-map builds, audio recaps (Kokoro pre-render),
     lecture transcription (Whisper) and verified figures.
   - *UI:* a small tray chip in `AppNav.tsx` ("1 thing cooking").

10. **Device-aware TTS tiers with a slow-device fallback**
    - *Technique:* measure the synthesis real-time factor. If it is too slow, offer a lighter voice and fall back to
      the OS voice for languages the model lacks.
    - *Stiti (exists: Kokoro in `voice/tts.py`):* track the RTF of the first two sentences. If RTF > 0.7 while
      Whisper is busy (8 GB contention), switch to Kokoro's int8 ONNX build or to macOS `AVSpeechSynthesizer` for
      that turn, and say so once. For Telugu/Hindi lines that Kokoro can't voice well, route to the OS voice the
      same way iTutor routes Malay and Urdu.
    - *Where:* `voice/tts.py`, `voice/voices.py`.

11. **Typed interactive checks** (Curriculum Builder blocks: ordering, matching, timeline, hotspot, code challenge)
    - *Technique:* a small set of typed blocks, each with a deterministic grader and a strict schema, written in a
      multi-pass generator (outline → outcomes → lessons → assessments → validate).
    - *Stiti:* extend `CHECK_KINDS` in `tutor/lesson.py` with `order`, `match` and `timeline`. Render them as
      draggable cards on the board. Answers can also come by voice ("osmosis first, then diffusion"), parsed in
      `tutor/grade.py` by matching item labels. Grading is exact, with no LLM. Keep generation multi-pass with one
      strict JSON schema per pass, which weak free models handle far better than one giant schema.
    - *Code challenges:* run them locally in a subprocess with a timeout and resource limits (or Pyodide in the
      board, ~10 MB, browser-side). Low priority.

12. **Presence and attention without recording** (MediaPipe on device)
    - *Technique:* in-browser face detection. Only an "away for N minutes" flag and an attention summary survive,
      and frames never leave the device.
    - *Stiti:* optional and off by default. MediaPipe Tasks Face Detector (BlazeFace short-range, about 200 KB) in
      the board page, sampled at 2 fps, emits `away`/`back` events. One recap on return. Start without the camera:
      no VAD activity for 3 or more minutes during a lecture is treated as "away".
    - *UI:* a camera toggle on the board, plus an attention line in the lesson note.

13. **Speaker check on answers** (their voiceprint similarity, used against cheating)
    - *Technique:* compare each answer's speaker embedding with the enrolled voice.
    - *Stiti (exists: `voice/speaker.py`):* use it the other way round. Only count a probe answer as the owner's when
      speaker similarity passes, so TV or a roommate never updates mastery. One cosine per utterance, about 5 ms.

14. **Local performance beacon** (their `/v1/public/vitals` per route/device)
    - *Technique:* real-user metrics per route.
    - *Stiti:* the web UI posts `{page, ttfb, lcp, first_audio_ms}` to the local server and they are stored in
      Postgres. This makes principle 4 ("fast, for every feature") measurable per page. Never sent off the Mac.

15. **Things learned but not adopted:** a separate vector DB (Qdrant) and Redis, because Postgres covers both at
    Stiti's scale. Server-side metered realtime voice, because Stiti's local Pipecat loop already plays that role.
    PWA offline caching, SCORM, impersonation and payments, because none of them matter for a single-user local
    buddy.
