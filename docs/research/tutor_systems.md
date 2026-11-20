# Existing tutor systems to study for Stiti's voice whiteboard tutor

Researcher scope: **existing, verifiable systems** (open source first), not papers.
Cap set by owner: about 5 systems, depth over breadth, plus a **"Whiteboard as notes"** section.
All repos below were checked on GitHub on 2026-11-20 through the GitHub API (stars, license, last push), and the key
files were opened and read. File paths are real paths from each repo's current default branch.

Owner's four complaints, used as the lens for everything below:

| # | Complaint | Short name |
|---|-----------|------------|
| C1 | No proper teaching structure | **structure** |
| C2 | Doesn't take doubts mid-lesson | **doubts** |
| C3 | Doesn't understand where he is stuck | **stuck** |
| C4 | Talks over him | **turn-taking** |
| C5 | Board: "draws wherever it wants", should read like notes | **board** |

---

## The 5 systems

### 1. OpenMAIC (THU-MAIC): multi-agent interactive classroom with whiteboard and TTS  **[TOP 3]**

- **URL:** https://github.com/THU-MAIC/OpenMAIC (MIT, ~44k stars, pushed 2026-11-19). Live demo https://open.maic.chat/. Grew out of Tsinghua's MAIC ("From MOOC to MAIC") research.
- **What it is:** turns a topic or an uploaded document into a classroom. A two-stage generator (outline, then scenes) makes slides, quizzes, interactive HTML and project-based learning (PBL). An AI teacher and AI classmates narrate with TTS, draw on a whiteboard, and you can interrupt them by voice (ASR) or text.
- **Lesson structure (C1):** `course outline → scenes[] → actions[]`. Each scene is an ordered list of typed actions: `speech`, `spotlight`, `laser`, `discussion`, plus whiteboard draw actions (`lib/prompts/snippets/action-types.md`). A lesson is a script the engine plays, so an LLM is not improvising the sequence turn by turn.
- **Doubts mid-lesson (C2), the main thing to copy:** `lib/playback/engine.ts` is one state machine, `idle → playing ⇄ paused`, `playing → live` (Q&A), `live → idle`, with the lecture resumed afterwards:
  - `handleUserInterrupt(text)` saves the lecture cursor **at the interrupted sentence** (`savedActionIndex = actionIndex - 1`, so that sentence is replayed on resume). It does not overwrite an already-saved cursor, so a second question during Q&A doesn't lose the place. It **sets mode before stopping audio**, because cancelling TTS fires `onend` synchronously, and without that order the engine skips a sentence.
  - `invalidatePlaybackGeneration()`: a monotonically increasing generation counter. Every async callback (TTS end, timers) checks `isCurrentGeneration(gen)` and drops itself if stale. This is the clean cure for "the old answer keeps talking after I interrupted".
  - `handleEndDiscussion()` / `handleDiscussionError()` restore the saved cursor and go to `idle`. Resume is explicit ("continue"), not automatic.
  - **Proactive discussion cards:** a `discussion` action placed at the end of a scene raises a "want to discuss X?" trigger (`onProactiveShow`). The learner can Join (`confirmDiscussion`) or Skip, and consumed discussions are persisted so they don't re-fire.
- **Who answers in Q&A:** `lib/chat/pi/director-loop.ts` and `lib/chat/pi/prompts.ts` run a **director** agent with tools `call_agent`, `cue_user`, `close_session` and `read_scene`. Rules worth stealing verbatim: "if the latest user message is a clear question and no agent has answered it yet, call the teacher first"; "lead with the direct answer, then at most one short follow-up question"; `close_session` with `endReason: back_to_lesson | user_done`, and a visible closing line is required before closing.
- **Learner state (C3):** weak in lecture mode, which only tracks a playback position and consumed discussions. Stronger in PBL v3: `lib/pbl/v3/domain/orchestration/{state,transition,remediation,quiz}.ts`, `lib/pbl/v2/runtime/learner-state.ts`, and the evaluator prompts under `lib/pbl/v2/prompts/`. There is also a "ZPD exercise lesson" skill with a test plan at `eval/zone-of-proximal-development/README.md`. It explicitly checks that help is withdrawn after success, that independent, assisted and new-task performance are recorded separately, and that one turn never "computes mastery".
- **Board (C5):** the LLM places elements with x/y on a fixed 1000×563 canvas (`lib/chat/pi/tools/native-whiteboard.ts`). Because models "read bbox coordinates poorly", they wrote `lib/orchestration/summarizers/whiteboard-conflicts.ts`, which computes overlap (≥30% of the smaller area), lines through elements and edge clipping, and **feeds the conflicts back into the prompt as text**. `whiteboard-ledger.ts` gives the model a compact list of what is already on the board. `eval/whiteboard-layout/scorer.ts` is a VLM rubric (readability, overlap, rendering, completeness, layout_logic) used to score screenshots. In short: they hit Stiti's exact problem and patched around free placement, they didn't remove it.
- **Fit for Stiti:** TS/Next.js, so the design gets ported, not the code. Provider-neutral and OpenAI-compatible (OpenRouter and Gemini are listed), with optional local ASR (FunASR) and TTS. Its prompts are long and tuned for strong models; the playback state machine is LLM-free, so it suits a weak free model.
- **Weaknesses:** heavy (Next.js, multi-agent, many LLM calls per turn). Multi-agent "classmates" add latency Stiti doesn't need. Free-x/y whiteboard. Chinese-first eval docs.

### 2. DeepTutor (HKUDS): "Mastery Path" / Guided Learning over your own documents  **[TOP 3]**

- **URL:** https://github.com/HKUDS/DeepTutor (Apache-2.0, ~61k stars, pushed 2026-11-18). Python backend plus web UI, with RAG over the learner's PDFs (Docling/MinerU parsing, LightRAG/GraphRAG/PageIndex). It supports every OpenAI-compatible cloud provider, Gemini and Lemonade.
- **What it is:** the most complete open-source "learn from your own file" tutor. The **Mastery Path** capability is a separate agent loop with a hard mastery gate per objective, plus spaced review.
- **Lesson structure (C1):** three explicit **modes**, each with its own allowed tools:
  - `outline`: co-design an outline with the learner. Every module has an `objective` phrased as an *ability*, and every knowledge point is tagged `memory | procedure | concept | design`. Every chosen material must be covered, and the outline is organised **around the goal, not the book's table of contents**.
  - `study`: work the outline one knowledge point at a time through its gate.
  - `review`: re-test only already-mastered points when due.
  - First, an **intake** step (`intake_needed`): one short message asks what they already know, what "done" looks like, how much time they have and how they want to be taught. The answers are saved to `learner_profile` and used every round "without reading it back to them".
  - Per objective: `probe` (test-out first) or `teach` (teach-first if the learner prefers), then a check, a grade and the gate.
- **Gate / learner state (C3):** `deeptutor/learning/mastery.py` holds the whole policy in 40 lines. It is recency-weighted accuracy over the last 5 attempts (weights 0.5, 0.7, 0.85, 0.95, 1.0), **capped at 0.5 after 1 attempt and 0.8 after 2**, so one lucky answer never masters a point. It is designed to be swapped for BKT/IRT. `deeptutor/learning/review_strategy.py` sets review intervals per knowledge type, in days. Presets include "Exam cramming" (memory `[0,1,1,2,3,4,7]`, concept `[1,2,3,5,7]`) and "Science" (concept `[5,12,25,50]`). That covers the owner's "exam tomorrow" case.
- **Doubts (C2), the rule set to copy:** from `deeptutor/capabilities/mastery/prompts/en/mastery_loop.yaml`:
  - "A question is open and unanswered: if they asked you something else, **answer that and leave the question open**", then re-pose it verbatim later.
  - "When the learner questions a prompt, option, answer or grade, address the objection directly… Do not rush them to answer… discussion alone does not change grades."
  - **"Posing a question is always this round's last action."** "If what you wrote this round ends on a colon, this round must call `mastery_quiz`." Also, "not every round poses a question": quizzing is decided by the gate, never by "a sense that a question is due".
  - Explicit escape hatches: `mastery_defer_objective` ("move on" without marking it mastered), `mastery_skip_question`, and `mastery_repair_question` (the learner says the key is wrong, so the negative evidence is voided).
- **Stuck handling (C3):** a "teaching observations" protocol. On repeated confusion, **change the approach** (example, prerequisite, spatial explanation, figure) rather than "promising to simplify". Inferred difficulties stay `tentative`. A strategy's outcome stays `unknown` until a learner statement supports `helped` or `not_helped`, and that evidence must quote the learner literally. "Teaching, silence and unanswered cards do not prove understanding."
- **Question design:** "Questions must discriminate… every distractor should encode a specific plausible misconception… match the correct option in length". Always store an `explanation`. "Design each question once."
- **Fit for Stiti:** Python, the same language, and Apache-2.0. The gate math and interval tables can be copied almost directly into Postgres. It is text and chat-card UI, not voice, and its prompt pack is long (about 35 KB) and assumes good tool calling. For Stiti the **engine** (outline, gate, modes, intervals) should be deterministic Python, and only the "say this" text should come from the LLM.
- **Weaknesses:** very large codebase (4,600+ files). Agentic tool loops are fragile on weak free models. No voice turn-taking. No whiteboard (it has "Visualize"/Manim-style animation agents instead).

### 3. ChatTutor (HugeCatLab): visual tutor whose board is "pages + notes"  **[TOP 3, for the board]**

- **URL:** https://github.com/HugeCatLab/ChatTutor (**AGPL-3.0**, ~1.3k stars, last push 2026-01-09). Vue + TS. Article: https://blog.brightcoding.dev/2026/10/08/hugecatlabchattutor-visual-ai-tutor-with-interactive-electronic-whiteboard
- **What it is:** a STEM tutor with a multi-page whiteboard. The LLM never sends coordinates. It writes **typed fenced blocks** that target a named page:
  - ```` ```mermaid[page-id;Page title] ```` creates or updates a diagram page (auto-layout by Mermaid)
  - ```` ```ggbscript[page-id;title] ```` appends GeoGebra commands to a math page
  - ```` ```note[page-id] ```` **appends** short key points to that page's note area ("do NOT rewrite the note")
  - Page model (`packages/shared/src/page.ts`): `{id, title (<20 chars), type, steps[]}`. The parser is `packages/agent/src/utils/block-parser.ts`.
- **Board-as-notes rule (C5):** "the page and its attached notes is **a slide** you use in class. ONLY short, clear key points and summary go in notes; detailed explanation stays in speech/chat."
- **Lesson structure (C1):** the system prompt (`packages/agent/src/prompts/agent.ts`) has a **U → S → T** workflow. **U**nderstand: restate the question, formalise givens and unknowns, ask clarifying questions if underspecified. **S**olve privately and verify with an independent check. **T**each: restate, give the method and why, explain step by step while drawing, summarise. U and S go in a hidden `<plan>` block.
- **Turn-taking (C4):** "After introducing each new concept or visualization, **stop naturally**. The student will either ask questions or signal they're ready." "Never end with 'Shall we continue?'." "Draw as you explain, not before or after. Never announce what you're about to draw."
- **Fit for Stiti:** the typed-block idea is perfect for weak models: it's just fenced text, with no tool-calling and no coordinates. Mermaid can be turned into Excalidraw with `@excalidraw/mermaid-to-excalidraw` (see "Also noted").
- **Weaknesses:** AGPL, so **study the design, don't copy code**. Small project, no learner model, no mastery, no voice. Its "pause at breakpoints" is prompt-only, with no engine enforcing it.

### 4. OATutor (CAHLR, UC Berkeley): open-source ITS with BKT, hint ladders and an LLM office-hours tutor

- **URL:** https://github.com/CAHLR/OATutor (MIT, ~280 stars, pushed 2026-11-19). React and Firebase, with AWS Lambda for the AI parts. Paper: Pardos et al., CHI 2023.
- **Lesson structure (C1):** lesson plan → learning objectives (skills) → problems → steps → **hint ladders** (`hints[]` each with optional `subHints[]`, ending in a "bottom-out" hint that gives the answer, toggled by `ENABLE_BOTTOM_OUT_HINTS`).
- **Learner state (C3), copy as-is:** `src/models/BKT/BKT-brain.js` is classic Bayesian Knowledge Tracing in 12 lines:
  ```js
  // correct:   num = P(L)(1-slip);  other = (1-P(L))guess
  // incorrect: num = P(L)slip;      other = (1-P(L))(1-guess)
  P(L|obs) = num / (num + other);  P(L) = P(L|obs) + (1 - P(L|obs)) * transit
  ```
  `src/models/BKT/problem-select-heuristics/defaultHeuristic.js` picks the next problem from the **least-mastered skill below threshold**, breaking ties at random. `MASTERY_THRESHOLD = 0.95` is in `src/config/config.js`.
- **Doubts / stuck (C2, C3):** `src/components/problem-layout/HintSystem.js` has options to unlock the first hint automatically or to give a hint on an incorrect answer, and it penalises hint use in BKT. `aws/aiHintGeneration/` creates LLM hints from a template: problem, the student's answer and the correct answer, then "give a hint". `aws/aiAgentGeneration/prompts/PROMPT-officehours.txt` (and per-course variants) is a strong Socratic prompt: "give one useful next step at a time, 2–4 sentences"; "if the student says 'idk / just tell me', **shrink the step** or demonstrate on a different example, then return"; "when the student makes an error, don't correct immediately; ask 'walk me through how you got that'"; "end with ONE content-focused guiding question, not 'Does that help?'". It also has `conversation-memory.mjs` and `document-context.mjs` for course-doc grounding.
- **Fit:** BKT is free, instant and local, and needs no LLM at all, which matches the "brain is not the LLM" rule exactly. The hint-ladder data model maps well to voice ("want a hint?").
- **Weaknesses:** content must be hand-authored, or LLM-generated and then checked. No voice turn-taking, no whiteboard. The AI agent targets OpenAI/Bedrock (adaptable).

### 5. ChatGPT Study Mode (OpenAI): the compact pedagogy prompt

- **Sources:** OpenAI launch (2025-07-29): study mode is **custom system instructions written with teachers and pedagogy experts, not a separate model**. Extracted prompt: Simon Willison, https://simonwillison.net/2025/Jul/29/openai-introducing-study-mode/, full text gist https://gist.github.com/simonw/33d5fb67d6b8e1b1e2f6921ab0ccb9fb. He got identical output across runs, but OpenAI has not confirmed it is verbatim.
- **Content (about 400 words, ideal size for a weak free model):** five STRICT RULES:
  1. Get to know the user, lightweight; default to a 10th-grade level.
  2. Build on existing knowledge.
  3. Guide, don't give answers.
  4. Check and reinforce after hard parts (restate, mnemonics, mini-reviews).
  5. Vary the rhythm: explain, question, role-play, "teach it back to me".

  Also: "**never ask more than one question at a time**"; quizzes "one question at a time! Let the user **try twice** before you reveal answers"; "always know the next step, and switch or end activities once they've done their job"; "be brief, never essay-length… a good back-and-forth"; "talk through the problem one step at a time… give the user a chance to RESPOND TO EACH STEP before continuing."
- **Fit:** best "mouth" persona block for Stiti. It's short, provider-agnostic and works on 8B-class models. It has no state, no structure and no board; those must come from Stiti's brain.
- **Weakness:** all policy is in the prompt, so nothing enforces it. An LLM-only design like this is exactly what Stiti's principles reject for decisions.

---

## Also noted (verified, small, directly usable components; not counted in the 5)

| Component | URL / license | Why it matters for Stiti |
|---|---|---|
| **Pipecat Smart Turn v3.2** | https://github.com/pipecat-ai/smart-turn (BSD-2), weights `pipecat-ai/smart-turn-v3` on HF | **C4 "talks over him"**: a semantic end-of-turn audio model (Whisper-Tiny base, about 8M params, **8 MB int8 CPU, about 10–65 ms**, 23 languages). It runs locally in Pipecat as `LocalSmartTurnAnalyzerV3`. It stops the tutor from jumping in on a mid-sentence pause ("so the… umm… derivative is"). Fits 8 GB easily. |
| **py-fsrs** | https://github.com/open-spaced-repetition/py-fsrs (MIT) | `pip install fsrs`; `scheduler.review_card(card, Rating.Good)` with `desired_retention=0.9`. It replaces DeepTutor's fixed interval tables for "review" mode. Ratings map from voice ("forgot / hard / got it / easy"). |
| **@excalidraw/mermaid-to-excalidraw** | https://github.com/excalidraw/mermaid-to-excalidraw (MIT) | Converts Mermaid flowchart, sequence, class, ER, state, Gantt and timeline diagrams into **native, editable Excalidraw elements** (others become images). Mermaid does the graph layout, so the LLM never chooses coordinates for diagrams. |

---

## Comparison table

| System | License | Lesson structure (C1) | Doubts mid-lesson (C2) | Stuck / learner state (C3) | Turn-taking (C4) | Board layout (C5) | Free tiers / 8 GB M2 / voice / weak model |
|---|---|---|---|---|---|---|---|
| **OpenMAIC** | MIT | outline → scenes → typed actions (scripted lecture) | **State machine: interrupt saves cursor at the interrupted sentence → live Q&A → restore & resume**; director routes the answer | weak in lecture; PBL v3 has state/remediation; ZPD eval | Generation counter kills stale TTS; proactive "discuss?" cards | LLM picks x/y; conflict detector fed back into prompt; VLM layout scorer | OpenAI-compatible, OpenRouter/Gemini OK; heavy Next.js; has TTS/ASR; prompts long |
| **DeepTutor** | Apache-2.0 | intake → outline (ability objectives, typed KPs) → study → review modes | "Answer their question, leave the pending question open"; objections handled before grading; defer/skip/repair | **Hard gate**: recency-weighted accuracy with 1-/2-attempt caps; teaching observations tentative→helped/not_helped; spaced intervals per KP type incl. exam-cram | "Posing a question ends the round" | none (Visualize/animation instead) | Python, OpenAI-compatible; big repo; no voice; tool loops brittle on weak models |
| **ChatTutor** | AGPL-3.0 | U(nderstand) → S(olve+verify, hidden) → T(each) | prompt-only | none | "Stop after each new concept; no 'shall we continue?'" | **Typed blocks into named pages; append-only notes = slide; Mermaid/GeoGebra auto-layout** | Any LLM; light; no voice; great for weak models (plain fenced text) |
| **OATutor** | MIT | lesson → skills → problems → steps → hint ladders | Hint on request / on wrong answer; office-hours Socratic LLM | **BKT per skill (12 lines), pick least-mastered skill**; threshold 0.95 | n/a | n/a | BKT local and free; LLM parts adaptable; no voice |
| **ChatGPT Study Mode** | proprietary (prompt public) | prompt rules only | "one question at a time; try twice" | none (in-context only) | "brief, back-and-forth, respond to each step" | n/a | ~400-word prompt, perfect "mouth" for weak free models |

---

## Top 3 to reverse-engineer, with exact files to read

### #1 OpenMAIC: the runtime (interrupt, resume, director, board feedback)
Read in this order:
1. `lib/playback/types.ts`: `EngineMode = idle|playing|paused|live`, `TopicState`, callbacks (`onUserInterrupt`, `onDiscussionEnd`, `onProgress`).
2. `lib/playback/engine.ts`: `handleUserInterrupt`, `confirmDiscussion`, `handleEndDiscussion`, `handleDiscussionError`, `pause`/`resume`, `invalidatePlaybackGeneration`/`isCurrentGeneration`, `isExhausted`. **Port this almost 1:1 to Python as Stiti's tutor player.**
3. `lib/chat/pi/director-loop.ts` and `lib/chat/pi/prompts.ts` (`buildDirectorPrompt`, `buildChildPrompt`, `buildRoleGuideline`, `buildLengthGuidelines`): Q&A routing and length rules.
4. `lib/prompts/snippets/action-types.md` and `lib/server/generation/steps/{outline.ts,scene-content.ts,scene-actions.ts}` with `lib/server/generation/outline-schema.ts`: how a lecture script is generated.
5. Board: `lib/orchestration/summarizers/whiteboard-conflicts.ts`, `whiteboard-ledger.ts`, `eval/whiteboard-layout/scorer.ts` (rubric prompt), `eval/whiteboard-layout/scenarios/*.json`.
6. Pedagogy evals: `eval/zone-of-proximal-development/README.md`; PBL remediation in `lib/pbl/v3/domain/orchestration/{state,transition,remediation}.ts`.

### #2 DeepTutor: the brain of a lesson (structure, gate, doubts policy)
1. `deeptutor/capabilities/mastery/prompts/en/mastery_loop.yaml`: **the single most useful tutoring policy text found** (modes, intake, probe/teach, the "open question" rule, the "posing a question ends the round" rule, teaching observations, question-design rules).
2. `deeptutor/learning/mastery.py`: the gate formula (40 lines).
3. `deeptutor/learning/review_strategy.py` and `deeptutor/learning/scheduler.py`: per-type review intervals and the exam-cram preset.
4. `deeptutor/capabilities/mastery/{loop.py,mode.py,memory.py,tools.py,pipeline.py}`: the loop, mode gating of tools, and how the learner profile is merged.
5. `deeptutor/services/mastery_hints.py` and `deeptutor/api/routers/mastery_path.py`: state shape exposed to the UI.
6. Document grounding: `deeptutor/book/agents/{spine_agent.py,page_planner.py,source_explorer.py}` with `deeptutor/book/prompts/en/{spine_agent,page_planner}.yaml` (turning a PDF into a learning spine organised around the goal, not the TOC).

### #3 ChatTutor: board-as-notes protocol (design only, AGPL)
1. `packages/agent/src/prompts/agent.ts`: the whole system prompt (pages, notes, U/S/T workflow, pause rules).
2. `packages/agent/src/utils/block-parser.ts`: streaming parser for ```` ```type[page-id;title] ```` blocks (how the board is driven from plain text while streaming).
3. `packages/shared/src/page.ts`, `packages/agent/src/utils/note.ts`: page and notes data model.
4. `packages/web/src/components/chat/chat-board/{board.vue,page.vue,page-notes.vue,mermaid-page.vue}`: how a page is rendered with its notes area.

(OATutor is not in the top 3 only because what we need is tiny and already fully read: copy `src/models/BKT/BKT-brain.js` and `defaultHeuristic.js` logic, and adapt `aws/aiAgentGeneration/prompts/PROMPT-officehours.txt` rules into the "stuck" prompt block.)

---

## What to copy, mapped to the complaints (synthesis for Stiti)

**C1 structure: deterministic lesson engine in Python (brain), LLM only writes the words.**
- Intake (DeepTutor): one short spoken question covering what you know, the goal or deadline, and how you want it taught. Store the answers in USER/learner profile and act on them silently.
- Outline: 3–7 objectives phrased as abilities ("can explain why…", "can solve…"), each tagged memory/procedure/concept, built from the file or topic around the goal, not the TOC (DeepTutor).
- Per objective loop: **hook/probe → teach one chunk (board page) → check (one question) → grade → gate → next**. ChatTutor's U/S/T applies inside "teach": the LLM privately solves and verifies before explaining.
- The gate: BKT (OATutor) or DeepTutor's capped recency average. Either way it is a small Python function in Postgres, not an LLM judgement.

**C2 doubts: OpenMAIC's player state machine.**
- `playing → live` on any learner speech. Save the cursor at the interrupted sentence, kill stale audio with a generation counter, answer the doubt (teacher first, direct answer first, at most one follow-up), then `close_session(back_to_lesson)` restores the cursor and replays the interrupted sentence.
- DeepTutor rule: a pending check question **stays open** while a doubt is answered, then is re-posed verbatim.
- Laya decides the intent of each utterance: doubt, answer to the pending check, "continue", "repeat", "skip/defer", "I'm lost", or an objection to grading. So the routing itself needs no LLM.

**C3 stuck: evidence, not vibes.**
- BKT probability per objective, plus a hint ladder per check (OATutor): nudge, then a smaller step, then a worked different example, then the bottom-out answer.
- "idk / just tell me" means shrink the step or demo on a different example (OATutor office hours). Repeated confusion means **change the approach** (example, prerequisite, picture), recorded as `tentative` and updated to `helped`/`not_helped` only from his literal words (DeepTutor).
- Study Mode: let him try twice before revealing the answer.

**C4 talking over him:**
- Local **Smart Turn v3** end-of-turn detection on top of VAD (8 MB, CPU), so he can pause mid-thought.
- A barge-in stops TTS immediately through the generation counter (OpenMAIC).
- **"Asking a question ends the turn"** (DeepTutor): after a check question, Stiti says nothing more and waits.
- One question at a time (Study Mode). Stop after each new concept rather than chaining (ChatTutor).

---

## Whiteboard as notes: how the projects lay out the board, and a recommendation for Stiti

### What the projects do

| Project | Who decides positions? | Result |
|---|---|---|
| OpenMAIC | **LLM emits x/y** on a 1000×563 canvas; engine computes overlaps/clipping and feeds them back as text; VLM rubric scores screenshots ("new content must go to sensible empty areas", "related elements grouped", "natural reading order", "font size consistency") | Works with strong models only. They needed a conflict detector **because** free placement fails. This is Stiti's current failure mode. |
| ChatTutor | **Nobody: the LLM names a page and a block type**; notes are append-only text lists; diagrams are Mermaid/GeoGebra with their own layout engines | Board reads like slides plus notes. Weak-model friendly. |
| DeepTutor "Book" blocks (`deeptutor/book/blocks/*.py`: section, text, callout, figure, flash_cards, quiz, timeline, concept_graph) | **Typed content blocks** rendered by a fixed template | Same principle for documents: the LLM picks the block type, the renderer owns the layout. |
| mermaid-to-excalidraw | Mermaid's layout (dagre/ELK) | Native Excalidraw shapes and arrows with no LLM coordinates. |

**Lesson:** every system that reads well takes coordinates away from the LLM. The LLM picks *what* (a slot or block type plus content); a deterministic layout engine picks *where*.

### Concrete layout recommendation for Stiti (Excalidraw)

**1. The board is a notebook of pages, one page per objective (or per teaching chunk).** A page is a fixed frame, say 1600×900 Excalidraw units, placed left to right or top to bottom with a gap, and the camera scrolls to the current page. A full page is never shrunk; overflow opens "Page n (cont.)".

**2. Fixed page template (the teacher's notes grid):**

```
┌──────────────────────────────────────────────────────────────┐
│ ① TITLE  "3. Why the derivative is a slope"     [3/6] ●●●○○○ │  title strip: 1 line, large font, progress
├───────────────────────────────────────┬──────────────────────┤
│ ② KEY POINTS (numbered, flow down)    │ ③ FIGURE             │
│  1. Slope = rise / run                │  (Mermaid→Excalidraw │
│  2. Shrink run → tangent              │   or simple preset   │
│  3. f'(x) = lim (f(x+h)-f(x))/h       │   shape: graph/axes, │
│                                       │   number line, table)│
│                                       │   fitted into slot   │
├───────────────────────────────────────┴──────────────────────┤
│ ④ WORKED EXAMPLE  step 1 → step 2 → step 3  (one row per step) │
├──────────────────────────────────────┬───────────────────────┤
│ ⑤ YOUR DOUBTS (yellow sticky notes)  │ ⑥ REMEMBER (boxed     │
│   Q: "why h→0, not h=0?" → A: …      │   1–3 line summary,   │
│                                      │   written at the gate)│
└──────────────────────────────────────┴───────────────────────┘
```
- Columns are about 60/40, key points on the left and figure on the right, which is the classic teacher board. The bands are fixed. Slots fill top to bottom using a **y-cursor** inside each slot (flow layout), so nothing is placed "wherever".
- **Three font sizes only**, by role: title, body and small label. OpenMAIC's rubric penalises 2× size jumps.
- Colours by role: black for points, blue for the figure, green for the example, a yellow sticky for doubts, a bold box for "Remember". Six slots and four colours, nothing else.
- **Doubts get their own slot (⑤)**, so his questions become part of his notes and don't clutter the lesson flow. Each sticky can link to the point it's about with an arrow to its point id.

**3. LLM output contract (weak-model safe).** Per teaching step, the mouth returns small JSON or ChatTutor-style fenced blocks, never coordinates:
```json
{"say": "Imagine zooming into the curve until it looks straight…",
 "board": [
   {"slot": "point",   "text": "Shrink run → tangent line"},
   {"slot": "figure",  "mermaid": "flowchart LR\n A[secant] --> B[h smaller] --> C[tangent]"},
   {"slot": "example", "steps": ["f(x)=x²", "(f(x+h)-f(x))/h = 2x+h", "h→0 ⇒ 2x"]}
 ],
 "check": {"q": "If f(x)=x³, what's the slope rule?", "expect": "3x²"}}
```
- `figure` accepts either `mermaid` (converted with mermaid-to-excalidraw, then scaled to fit slot ③) or a **preset** from a small library Stiti owns: `axes+curve`, `number_line`, `table`, `labelled_box_arrow`, `venn`. Freehand-by-coordinates is not allowed.
- Points are **append-only** (ChatTutor). The engine dedupes near-identical lines. "Remember" ⑥ is written only when the gate clears, which is the page summary.

**4. Layout engine (Python, deterministic, about 200 lines):** measure text width approximately as characters × font-size × 0.55, wrap to the slot width, advance the y-cursor, and spill to a continuation page on overflow. Every element gets a **semantic id** (`p3.point2`, `p3.fig`, `p3.ex.step1`), so speech can **highlight or point** at it in sync, as OpenMAIC's `spotlight`/`laser` actions do. Tokens like "[[p3.point2]]" in `say` trigger a highlight when TTS reaches them.

**5. Checks borrowed from OpenMAIC:**
- Run the `whiteboard-conflicts.ts` logic (overlap ≥30%, lines through elements, edge clipping) as a **unit-test assertion** on every generated page. With slot layout it should always be zero.
- Optional offline eval: screenshot pages and score them with the `eval/whiteboard-layout/scorer.ts` rubric on a free Gemini vision tier. Run this occasionally in the background, not per turn.

**6. Export:** each page already is a notes page, so "save my notes" equals the pages exported as PNG/PDF or markdown (title, points, example, doubts, remember). This fits the "human-readable memory" principle.

---

## Sources (all opened on 2026-11-20)
- OpenMAIC: https://github.com/THU-MAIC/OpenMAIC, files listed above
- DeepTutor: https://github.com/HKUDS/DeepTutor, files listed above
- ChatTutor: https://github.com/HugeCatLab/ChatTutor, and https://blog.brightcoding.dev/2026/10/08/hugecatlabchattutor-visual-ai-tutor-with-interactive-electronic-whiteboard
- OATutor: https://github.com/CAHLR/OATutor
- ChatGPT Study Mode: https://simonwillison.net/2025/Jul/29/openai-introducing-study-mode/ · https://gist.github.com/simonw/33d5fb67d6b8e1b1e2f6921ab0ccb9fb · https://news.slashdot.org/story/25/07/29/2042244/chatgpts-new-study-mode-is-designed-to-help-you-learn-not-just-give-answers
- Smart Turn: https://github.com/pipecat-ai/smart-turn · https://huggingface.co/pipecat-ai/smart-turn-v3
- py-fsrs: https://github.com/open-spaced-repetition/py-fsrs
- mermaid-to-excalidraw: https://github.com/excalidraw/mermaid-to-excalidraw
- Other whiteboard tutors seen but not chosen (tiny, unverified quality or licence): mntrushmore/agathon (tldraw + voice), MathVoice (speech-synced board), e-roy/ai-math-tutor (Excalidraw), and many 0-star "ai-whiteboard-tutor" assignment repos.
