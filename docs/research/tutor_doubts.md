# Tutor doubts: understanding what he asks, letting him finish, doing the right thing

Research for the whiteboard tutor (`src/stiti/tutor/`), written 2026-11-20 after the owner's live test failed:

> "It's not taking my doubts. It's not understanding what I'm asking, just saying what it wants to say. It doesn't give
> me time to complete my question. When I ask a doubt it should understand where I am stuck and do the thing right."

Mis-handled utterances from that test: *"Bro, I don't need to go from all start"*, *"tomorrow I have exam, I gave you a
HTML, so I want you to explain me that"*, *"I want to study a different syllabus"*. These were parked, or taken as
answers to a quiz. Separately, local Whisper mis-hears technical words (DFA, lexer, token) and the tutor reacts at once to
the wrong text.

Scope cap from the owner: about 5 strong, verified sources (the three researchers aim for 10–15 in total). Below are
**5 primary sources**, read and checked, plus 4 supporting ones whose title, venue and URL were checked but which are
only used for one point each.

---

## 1. Primary sources

### S1. Bridge: expert decisions before the reply
**"Bridging the Novice-Expert Gap via Models of Decision-Making: A Case Study on Remediating Math Mistakes"**
Rose E. Wang, Qingyang Zhang, Carly Robinson, Susanna Loeb, Dorottya Demszky. **NAACL 2024** (long), pp. 2174–2199.
https://aclanthology.org/2024.naacl-long.120 · arXiv https://arxiv.org/abs/2310.10648 · data/code on GitHub (rosewang2008/bridge)

- **Mechanism.** Cognitive task analysis of expert tutors turns their hidden reasoning into **three decisions made before
  any words are written**: (A) *error type*: guess / misinterpret / careless / right-idea / imprecise / not-sure / N/A;
  (B) *strategy*: explain a concept, ask a question, give a hint, give a strategy, worked example, minor correction,
  similar problem, simplify the question, affirm, encourage; (C) *intention*: motivate, get them to elaborate, correct,
  hint at the mistake, clarify the misunderstanding, help them understand the topic, diagnose, support, explain the
  mistake, signal solved/not solved. The LLM then writes a reply that follows those decisions.
  700 real tutoring chats (grades 1–5 maths), annotated by experts.
- **Results.** GPT-4 given the expert decisions was ~76% more preferred and ~80% more useful than GPT-4 with no
  decisions. GPT-4 choosing its *own* decisions first did about as well (0.84 vs 0.83 overall). **Random decisions made it
  much worse** (0.26, below the no-decision baseline). Weaker models (GPT-3.5) fell back to "correct the mistake" every
  time. With no decision step, models "engage superficially": they say "try again" or give the answer away. That is
  exactly the owner's "just saying what it wants to say".
- **Strengths.** A small, explicit, typed decision before generation is cheap, can be logged, and Stiti's decision layer
  (Laya) can learn it. This matches the "decisions are made by Stiti" rule.
- **Weaknesses.** Elementary maths only. Covers "student made a mistake", not "student asked a doubt" or "student wants a
  different plan". Small models choose decisions badly. The abstract and introduction disagree on the size of the
  random-decision drop (−97% vs −67%); Table 1 fits −67 to −69%.
- **Fit (free cloud LLM + 8 GB M2 + voice).** Very good. The three decisions become typed fields in **one** JSON reply from a
  free Groq/Gemini model, or are pre-filled locally when confident. No extra model in RAM.

### S2. MRBench: what a good tutor reply contains
**"Unifying AI Tutor Evaluation: An Evaluation Taxonomy for Pedagogical Ability Assessment of LLM-Powered AI Tutors"**
Kaushal Kumar Maurya, KV Aditya Srivatsa, Kseniia Petukhova, Ekaterina Kochmar. **NAACL 2025** (long), pp. 1234–1251.
https://aclanthology.org/2025.naacl-long.57 · arXiv https://arxiv.org/abs/2412.09416

- **Mechanism.** Eight dimensions for judging a tutor turn: **mistake identification, mistake location** (does it point at
  *where* the learner is wrong?), **revealing the answer** (should be no), **providing guidance, actionability** (is the
  next step clear to the learner?), **coherence** with the learner's previous turns, **tutor tone, human-likeness**.
  MRBench: 192 conversations and 1,596 replies from 7 LLM and human tutors (built from MathDial and Bridge), with gold
  human labels.
- **Findings.** GPT-4 identifies the mistake ~94% of the time and locates it ~84%, but **reveals the answer ~47% of the
  time and is actionable only ~46%**. In the authors' words it is a good question-answering system but a poor tutor.
  Llama-3.1-405B was the most robust. Llama-3.1-8B did reasonably well for its size. Gemini was often incoherent.
  **LLM-as-judge (Prometheus2, Llama-3.1-8B) did not agree with humans** on these dimensions: most correlations were
  negative.
- **Strengths.** A ready-made rubric for Stiti's tutor evals. "Mistake location" and "coherence" are exactly what the owner
  means by "understand where I am stuck".
- **Weaknesses.** Maths only, and single-turn. It measures mistake remediation, not questions the learner starts.
  Its finding means we **cannot let an LLM grade our tutor automatically**: the eval needs human labels (Tejmul's).
- **Fit.** Good as an eval design (offline, free). Use free Llama-3.x-70B/405B-class models on Groq/OpenRouter for
  tutoring; skip small models for the doubt reply.

### S3. LearnLM: pedagogy principles and multi-turn evaluation
**"Towards Responsible Development of Generative AI for Education: An Evaluation-Driven Approach"**
Irina Jurenka, Markus Kunesch, Kevin R. McKee, Daniel Gillick, Shaojian Zhu, et al. (Google DeepMind). arXiv tech report,
2024 (v4 Dec 2025). https://arxiv.org/abs/2407.12687

- **Mechanism.** Turns learning science into five principles: *encourage active learning, manage cognitive load, deepen
  metacognition, motivate and stimulate curiosity, **adapt to learners' goals and needs*** ("assess the current state and
  goals, then plan to bridge the gap"). It also gives tutor behaviours used as critic checks: *stay on topic, don't reveal
  the answer, guide towards the answer, promote active engagement, **identify and address misconceptions, respond
  appropriately to explicit affect cues, adapt to the learner's level***. Gemini was fine-tuned on human-written "golden"
  conversations (LearnLM-Tutor). It was evaluated in 45-minute unguided learner sessions and by teachers rating whole
  conversations.
- **Findings.** Prompting alone gave **inconsistent pedagogy**. Default "helpful" assistants give answers away. Teachers
  preferred LearnLM-Tutor on most pedagogy items. Single-turn evaluation has low validity, because tutoring is multi-turn.
- **Strengths.** The clearest statement that the tutor must **adapt to the learner's stated goal**. "Exam tomorrow, explain
  my HTML" is a goal change, and the plan must change with it. Gives Stiti a checklist for its compiled "briefing".
- **Weaknesses.** Text chat, not voice. Depends on fine-tuning, which Stiti does not do to its LLM (no-LLM-fine-tuning
  rule). Small human samples. Google-specific.
- **Fit.** The principles fit as **briefing rules** for the plug-in LLM. The fine-tuning does not apply. The lesson for Stiti:
  because prompting alone is inconsistent, the **typed decision must be made outside the reply text** (S1) and checked by
  code.

### S4. Smart Turn v3: end-of-turn from audio, already in Stiti
**pipecat-ai/smart-turn: "An open source, community-driven, native audio turn detection model"** (Smart Turn v3.x,
Daily/Pipecat, 2025; BSD-2; open weights, data and training script).
https://github.com/pipecat-ai/smart-turn · weights https://huggingface.co/pipecat-ai/smart-turn-v3
Background theory: Gabriel Skantze, **"Turn-taking in Conversational Systems and Human-Robot Interaction: A Review"**,
*Computer Speech & Language* 67 (2021) 101178, doi:10.1016/j.csl.2020.101178.

- **Mechanism.** A Whisper-Tiny encoder plus a linear head (~8M parameters; 8 MB int8 ONNX) reads the last few seconds of
  **raw audio** (16 kHz) and outputs P(turn complete). Because it hears audio, it uses prosody: a falling pitch ends a
  turn, a held "so I want you to…" does not. Pipecat runs it locally (`LocalSmartTurnAnalyzerV3`) after a short VAD
  silence, with a hard `stop_secs` fallback. Skantze's review explains why silence alone fails: humans pause mid-turn
  for longer than the gap between turns, so end-of-turn must combine **prosody, syntactic/semantic completeness and
  context**. It also covers barge-in and backchannels ("hmm") that must not count as a turn.
- **Strengths.** Local, free, tiny, ~tens of ms. Stiti's `voice/endpoint.py` already uses it (`SMART_TURN_MS=300`,
  `UNFINISHED_WAIT_S=3.0`), and the tutor reuses that VoiceLoop.
- **Weaknesses.** Trained mostly on fluent conversational speech. A learner *thinking aloud* about a doubt pauses longer
  and trails off ("and the lexer… it gives… the tokens, so…"). Audio-only, so it misses "the words are not finished yet"
  cues. A fixed 3 s cap still cuts a slow thinker off.
- **Fit.** Already in place. The fix is to **tune it for tutor mode** and add a cheap transcript-completeness check (§3).

### S5. Prompt biasing for Whisper's rare words (hearing)
**"Improving Rare-Word Recognition of Whisper in Zero-Shot Settings"**
Yash Jogi, Vaibhav Aggarwal, Shabari S. Nair, Yash Verma, Aayush Kubba. **IEEE SLT 2024** (arXiv 2502.11572, 2025).
https://arxiv.org/abs/2502.11572

- **Mechanism.** Put a **list of biasing words in Whisper's prompt**. Plain Whisper with a prompt list lowered rare-word
  WER from 23.7% to 18.0% and OOV-word WER from 60% to 37.1%. The authors note Whisper's prompt slot was trained on
  the *previous transcript*, not on word lists. So they fine-tune it on 670 h of Common Voice with a biasing instruction:
  +45.6% rare-word recognition, +60.8% on words never seen in fine-tuning.
- **Strengths.** Shows that prompt biasing works **with no fine-tuning**, and that the best format is something that
  looks like prior text, not a bare list. Stiti's own measurements agree: the `voice/glossary.py` docstring records
  whisper-small 12.4 → 9.7% WER with a glossary prompt, and 9.1% with snapping near-misses afterwards.
- **Weaknesses.** The large gains need a fine-tuned Whisper, which is optional for Stiti. Long lists hurt (prompt copying
  and hallucination), and Stiti already guards against that in `stt.py`.
- **Fit.** Direct. A lesson has a known, small vocabulary (DFA, lexer, token, regex, NFA…), so prompt biasing is cheap and
  local (zero extra RAM).

### Supporting sources (checked, one point each)
| Source | Used for |
|---|---|
| **MathDial**: Macina et al., Findings of EMNLP 2023. https://aclanthology.org/2023.findings-emnlp.372 | Teacher-move taxonomy (Focus / Probing / Telling / Generic). LLM tutors "reveal solutions too early". |
| **Tutor CoPilot**: Wang, Ribeiro, Robinson, Loeb, Demszky, 2024. https://arxiv.org/abs/2410.03017 | RCT with ~1,000 students: expert-decision suggestions gave +4 pp mastery (+9 pp for weaker tutors), more guiding questions and less generic praise. Shows the Bridge decision step works in live sessions. |
| **SocraticLM**: Liu et al., NeurIPS 2024. https://proceedings.neurips.cc/paper_files/paper/2024/file/9bae399d1f34b8650351c1bd3692aeae-Paper-Conference.pdf | "Thought-provoking" Socratic teaching vs "question-answering". Useful for the Socratic-vs-direct rule below. |
| **Skantze 2021** (CSL review, above) | Theory for turn-taking, barge-in and backchannels. |

---

## 2. Comparison table

| # | Source | Mechanism | Strengths | Weaknesses | Fits free cloud + 8 GB M2 + voice? |
|---|---|---|---|---|---|
| S1 | Bridge (NAACL 2024) | 3 typed decisions (error type → strategy → intention) before the reply | Big quality gain. Fixes shallow "try again" replies. Decisions can be logged and learned. | Maths, mistakes only. Weak LLMs choose badly. | **Yes.** Decisions as JSON fields in one free LLM call, or pre-filled by Laya. 0 MB RAM. |
| S2 | MRBench (NAACL 2025) | 8-dimension rubric with human gold labels | Measures "mistake location", actionability, coherence. Shows GPT-4 gives answers away. | Single-turn maths. LLM judges unreliable. | **Yes**, as an offline eval. Needs owner labels, not an LLM judge. |
| S3 | LearnLM (DeepMind 2024) | Learning-science principles, critic behaviours, fine-tuned Gemini, multi-turn evaluation | "Adapt to the learner's goals". Prompting alone is inconsistent. Multi-turn evaluation is what counts. | Text only. Relies on fine-tuning. | **Partly.** Use the principles as briefing rules. No fine-tuning. |
| S4 | Smart Turn v3 + Skantze review | Audio end-of-turn classifier on prosody, VAD-gated, hard timeout | Local, 8 MB, fast. Already in Stiti. | Not tuned for learners who think aloud. Ignores the words. | **Yes.** Already running. Tune for tutor mode and add a text-completeness check. |
| S5 | Whisper rare-word biasing (SLT 2024) | Word list in Whisper's prompt (fine-tuning optional) | 24 → 18% rare-word WER and 60 → 37% OOV WER with no training. | Long lists hurt. Top gains need fine-tuning. | **Yes.** Add lesson terms to the existing glossary prompt. 0 MB RAM. |

---

## 3. Why the current tutor fails (diagnosis against the code)

Read from `src/stiti/tutor/commands.py`, `audio.py`, `ears.py`, `voice/endpoint.py`, `voice/stt.py`, `voice/glossary.py`
(on the `fix/tutor-listens` branch, which already has uncommitted edits adding `STEER`).

1. **A single regex label decides everything**, and the default is wrong. With a check open, `classify()` returns
   `answer` for any sentence that is not a clear question. So "I want to study a different syllabus" became a quiz
   answer. With no check open, a ≤2-word "other" is ignored. The new `STEER` regex helps, but it is still a list of
   phrasings. The next new phrasing ("this is too basic yaar, I know loops") will slip through again.
2. **No "where is he stuck" step.** A question gets a generic 2–4 sentence answer about the *topic*, not about the part of
   the *current board step* he is stuck on. That is Bridge's "superficial engagement" and MRBench's missing
   "mistake location".
3. **No plan change.** Doubt → answer → resume the *old* plan. A goal change ("exam tomorrow, explain my HTML") has to
   **re-plan**, as LearnLM's "adapt to goals" says.
4. **Cut off mid-doubt.** The tutor uses the global endpointer (Smart Turn at 300 ms, 3 s unfinished cap). Learners
   explaining a doubt pause to think and trail off ("so I want you to…"), so the turn is committed half-done and the tutor
   answers the fragment.
5. **Mis-hearing reaches the brain unchecked.** The glossary prompt holds Tejmul's personal words (name, USER.md, graph,
   document titles) but **not the current lesson's terms**. Nothing in `tutor/` adds them. A low-confidence transcript
   about "the lecture" (= "lexer") is acted on at once, with no chance to correct it.

---

## 4. Student-utterance taxonomy (what the tutor must tell apart)

Two levels: **act** (who holds the floor, what kind of move) and **sub-type** (what to do). Context features count as
much as words: *is a check open? what was on the board? how long did he speak? Whisper confidence? did he barge in?*

| Act | Sub-types (examples) | Tutor move (Bridge strategy / intention) |
|---|---|---|
| **HOLD**: still talking | filler or trailing words ("umm", "so…", "and the…", "I want you to…"), a mid-thought pause | Keep listening. Show "listening…" on the board. No reply. |
| **CONTROL** | pause, resume, repeat, back, next, slower, faster, end, language | Do it at once, with no LLM (existing regex). |
| **DOUBT**: he starts a question about the content | *concept* ("what is a token?") · *step* ("why did the DFA go to q2 there?") · *confusion* ("I didn't get that") · *verify* ("so the lexer runs first, right?") · *example* ("give me an example") · *contradiction* ("but you said earlier…") · *transfer* ("does this work for Python too?") | Find the stuck point (board step + concept). **Answer directly** and briefly, draw it, then ask one targeted check. |
| **ANSWER**: replies to an open check | correct · partial · wrong (Bridge error type: guess / misinterpret / careless / right-idea / imprecise) · "I don't know" | Grade it. For a wrong answer, **don't give the answer away**: hint, ask, or simplify (S1, S2). |
| **STEER**: change *what* or *how* is taught | *skip-known* ("I don't need to go from the start", "I know this") · *scope* ("different syllabus", "go to unit 3") · *source* ("explain the HTML I gave you") · *goal / deadline* ("exam tomorrow") · *level* ("too basic", "too hard") · *mode* ("just tell me", "quiz me", "only important questions") | Confirm in one sentence, re-plan in the background, then **continue on the new plan**, not the old one. |
| **AFFECT** | tired, bored, frustrated, anxious ("I'm going to fail") | Change tone and pace. Offer a shorter path. Combine with the voice-emotion signal. |
| **SOCIAL / OFF-TOPIC** | chit-chat, unrelated requests | One short line, then "back to X?". Unrelated tasks go to normal Stiti. |
| **UNCLEAR** | low Whisper confidence, or a fragment that matches no act | Implicit confirm or a two-choice clarification (§6). Never silently ignore it. |

Rules: (a) **STEER beats ANSWER** even when a check is open. (b) Only HOLD and noise may produce no response. Every
other act gets at least a short acknowledgement. (c) A DOUBT asked *while* a check is open pauses the check. It does
not count as a wrong answer.

---

## 5. Proposed doubt pipeline

```
 barge-in ─► [0] listen fully ─► [1] hear right ─► [2] fast local gate ─► [3] local act guess
          ─► [4] instant ack (local TTS) ─► [5] ONE LLM call: decide + speak ─► [6] act ─► [7] check & resume ─► [8] log
```

| Step | What happens | Runs | Budget |
|---|---|---|---|
| **0. Listen fully** | Barge-in: duck her voice at 250 ms, pause at 700 ms (existing). **Tutor mode:** once he has the floor, raise `UNFINISHED_WAIT_S` to 4–5 s and require Smart Turn ≥ threshold **and** a completeness check on the speculative transcript: not ending in a conjunction, preposition, "to", "the", "like", "so", "I want you to…", "because…". If unfinished, keep waiting and show "listening…". A "hmm" or "haan" in a gap is a backchannel, not a turn. Learn his pause length (`stats.observe_pause`, already there) **per mode**. | Local (Smart Turn 8 MB + regex) | Turn ends 0.3 s (clear finish) to 5 s (he is thinking). Speed is never worth cutting him off. |
| **1. Hear right** | Whisper prompt = his glossary **+ the lesson's key terms** (current section first, about 20–30 terms from the planner), as a prior-text sentence, not a bare list (S5). Snap near-misses to the lesson terms (existing `glossary.snap`). Keep `avg_logprob` / `no_speech` per span. | Local | +0 ms (same Whisper call) |
| **2. Fast gate** | Echo or noise → drop (ears.py). ≤ 6-word CONTROL → do it now. | Local regex | < 5 ms |
| **3. Act guess** | Laya, or an embedding nearest-neighbour on labelled examples (this file's taxonomy plus the owner's real utterances), plus context features (check open? board step, length, confidence). Output: act + sub-type + confidence. High-confidence CONTROL, ANSWER-to-a-yes/no-check and SOCIAL are handled with no LLM. **DOUBT, STEER, AFFECT and anything unsure go to step 5**, and the local guess is passed along as a hint. | Local | < 30 ms |
| **4. Instant ack** | Short pre-synthesised line per act, which also **echoes the key term** he said: "Hmm, the lexer part, let me look." / "Okay, exam tomorrow, got it." This is an implicit confirmation: if she heard it wrong, he hears it at once. | Local TTS (cached) | First audio < 400 ms after turn end |
| **5. One LLM call** | Compiled briefing: lesson outline + current step id + last ~3 spoken chunks + board items + learner model (known / weak concepts) + goal/deadline + his utterance (with low-confidence words marked) + the local act guess. **Streamed, fixed field order:** `ACT`, `STUCK_AT` (step id + concept + one-line restatement of his doubt), `ERROR_TYPE`, `STRATEGY`, `INTENTION` (Bridge), `PLAN_CHANGE` (skip_to / new_source / new_goal / null), then `SAY` (spoken, ≤ 4 sentences), `BOARD` (draw operations), `CHECK` (one targeted question). Code validates the fields. If `ACT` disagrees with a confident local guess, code decides (Stiti decides, not the LLM). Free fallback chain: Groq Llama-3.3-70B → Gemini Flash → OpenRouter `:free`. | 1 cloud call | Time to first token 0.3–0.8 s. TTS starts on the first `SAY` sentence. First real answer at about 1.0–1.5 s. |
| **6. Act** | **DOUBT:** speak `SAY`, draw `BOARD` next to the step he is stuck on. **STEER:** say one confirming sentence ("So: skip the basics, use your HTML file, aim for tomorrow's exam. Starting with forms, okay?"), then the planner re-plans in the background and the tutor continues on the **new** plan. **AFFECT:** change pace and tone. **No-LLM fallback** (all providers down): repeat the board step's own explanation, then say "I can't think deeply right now". | Local + planner | Re-plan in the background |
| **7. Check & resume** | Instead of "do you understand?", ask **one targeted question** about the exact stuck point (MRBench actionability; "do you understand?" mostly gets a polite "yes"). Offer two choices if unsure: "Is it the DFA states that are unclear, or how the lexer uses them?" Then resume **from the sentence where he interrupted**, with a one-line bridge ("So, back to the DFA, we were at q2…"). | LLM output from step 5 | — |
| **8. Log** | utterance, confidence, local act, LLM act, final act, his reaction (did he re-ask?) → Laya calibration data and `LESSONS.md` ("when he says 'from all start', he means skip the basics"). | Local Postgres | Background |

### Socratic or direct: the rule
- **He asks** (DOUBT) → **answer directly and clearly first**, then one check question. Making the learner work for an answer
  to their *own* question is what "just saying what it wants to say" feels like.
- **He answers a check wrongly** (ANSWER/wrong) → **Socratic**: hint, simplify, or point at the step. Don't reveal the
  answer (S1, S2, MathDial).
- **Goal is an exam tomorrow**, or he says "just tell me" (STEER/mode) → switch the whole lesson to direct, exam-focused
  mode until he changes it (LearnLM "adapt to goals").

---

## 6. Hearing & reacting (technical words, wrong text, slow speakers)

1. **Lesson glossary into Whisper.** When a lesson starts, the planner already knows its key terms. Add the
   top ~30 (current section first, refreshed per section) to `glossary.prompt_text()` and to the snap list. Write them
   as a natural sentence ("We are studying lexers, tokens, DFA, NFA and regular expressions."), because Whisper's prompt
   slot expects prior text (S5). Keep the existing prompt-copy guards. Cost: 0 RAM, 0 extra ms. Expected effect: in S5,
   prompt biasing alone cut rare-word WER ~24 → 18% and OOV WER 60 → 37%, and Stiti's own glossary test got 12.4 → 9.1%.
2. **Clarify by confidence, not always.** For each span, combine Whisper `avg_logprob` with "near-miss of a lesson term"
   (a snap happened, or the skeleton similarity is 0.6–0.8):
   - **high confidence** → act.
   - **medium** → act, but **echo the key term** in the instant ack (implicit confirmation, step 4). If he says "no, I said
     lexer", `vocab.py` learns it (that path exists already).
   - **low** → ask a **two-choice** question instead of guessing: "Did you mean the *lexer* or the *lecture*?" Never a bare
     "Sorry?", and never ask about a high-confidence span.
3. **Show what she heard before she acts on it.** Stream his live transcript into the board's subtitle dock while he
   speaks, with lesson terms highlighted and low-confidence words dimmed. When the turn ends, keep it on screen for
   ~0.6 s while the ack plays (the ack covers this time). If he says "no / nahi / wait, I said…" within 2 s, cancel
   the LLM call and re-transcribe or correct. This gives him a correction window **without** making replies slower.
4. **Never answer a fragment.** Combine step 0 (tutor-mode wait, completeness check) with "a continuation within 3 s
   merges into the same doubt": if he goes on after she has started the ack, stop TTS, merge the text, and re-send.
   The `CONT_MIN_SPEECH_MS` grace in `endpoint.py` already does this for the main loop. Make sure the tutor's ears use
   it too.
5. **Learn him.** Store his pause lengths per mode, and each mis-hearing he corrects (`~/.stiti/vocab.json`), so the
   same word is fixed for good.

---

## 7. How to measure it (before and after)
- **Act classification set:** the 3 failed utterances from today, plus ~60 owner-style utterances (Hinglish included)
  labelled with the §4 taxonomy. Target ≥ 90% act accuracy, and **0 STEER labelled as ANSWER**.
- **Doubt-reply rubric (human-labelled, S2):** stuck-point located? answer given directly when he asked? actionable
  next step? coherent with the board step? no answer given away on wrong check answers?
- **Turn-taking:** count of his doubts cut off (he keeps talking after she starts) per lesson. Target ~0.
- **Hearing:** WER on lesson terms, read from a 20-sentence script with DFA/lexer/token and similar words, with and
  without the lesson glossary.
- **Latency:** turn end → ack audio (< 0.4 s), turn end → first answer audio (< 1.5 s).
