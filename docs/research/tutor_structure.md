# Tutor structure — what a real teaching agent should do

Scope: how Stiti's whiteboard tutor should structure, pace and re-plan a 1:1 spoken lesson.
Written 2026-11-20 after the failed real test: *"It keeps on saying, saying, saying. It's not
interactive. It's not taking my doubts. It doesn't understand where I am stuck. It does not have a
proper structure."* He had an exam the next day, wanted the whole notebook covered, and it started from
basics.

Scope cap from owner: **~5 core sources, depth over breadth** (the other researchers cover the rest).
Every source below was checked by search/fetch on 2026-11-20. Where a detail came from a secondary
source rather than the paper itself, that is said.

---

## The diagnosis in one paragraph

The current player is a **lecture with quizzes stuck on**: an outline, then 5–8 cues per idea played in
order, then one check per segment. The research below says the effective part of human tutoring is the
**step-level loop**: the tutor asks, the learner does something, the tutor reacts to exactly that, and
the next step is chosen from what the learner just showed. Stiti's tutor does almost no asking and
never changes the plan based on the answers. It also ignored the two inputs that should have driven
everything: **what he already knows** (expertise reversal: re-teaching basics to someone who knows them
*hurts*) and **how much time is left** (with an exam tomorrow, triage beats completeness-from-zero).

---

## The 5 core sources

### 1. VanLehn (2011): interaction granularity, and the "interaction plateau"

- **Citation:** Kurt VanLehn. *The Relative Effectiveness of Human Tutoring, Intelligent Tutoring
  Systems, and Other Tutoring Systems.* Educational Psychologist 46(4):197–221, 2011.
  DOI [10.1080/00461520.2011.611369](https://doi.org/10.1080/00461520.2011.611369) ·
  ERIC record: https://eric.ed.gov/?id=EJ946764 · preprint: https://arxiv.org/abs/1302.7081
- **Mechanism:** A meta-review that sorts tutoring by **granularity of interaction**: answer-based (the
  learner only gives a final answer), step-based (feedback and hints on each step), substep-based
  (dialogue inside each step), and human. Effect sizes against no tutoring: answer-based ≈ 0.31,
  step-based ITS ≈ 0.76, human tutoring ≈ 0.79. Substep-based systems were not clearly better than
  step-based ones. This is the **interaction plateau**: once the learner is acting and getting a
  response at every step, adding finer interaction gives little more.
- **What it means for Stiti:** The current design is roughly *answer-based* (one check per segment after
  a monologue). The jump from 0.31 to 0.76 comes from moving to **one learner action per step**. The plateau
  also says we don't need a deep Socratic dialogue on every sentence. One short learner turn per step is
  enough, which suits voice and a free LLM.
- **Strengths:** Large evidence base. Also corrects Bloom's famous "2 sigma" (human tutoring measured
  ≈0.79, not 2.0), so it sets realistic targets.
- **Weaknesses:** Mostly STEM problem-solving domains with clear steps. Conceptual, notebook-style
  subjects need "steps" defined as small questions or claims rather than solution steps. Effect sizes
  come from older, pre-LLM systems.
- **Fit (free cloud LLM + 8 GB M2 + voice):** **High.** It's a structural rule, not a model, so it costs
  nothing. It actually cuts LLM tokens per turn (short cue, then wait).

### 2. Graesser, Person & Magliano (1995): the 5-step tutoring frame (and AutoTutor's EMT dialogue)

- **Citation:** Arthur C. Graesser, Natalie K. Person, Joseph P. Magliano. *Collaborative Dialogue
  Patterns in Naturalistic One-to-One Tutoring.* Applied Cognitive Psychology 9(6):495–522, 1995.
  DOI [10.1002/acp.2350090604](https://doi.org/10.1002/acp.2350090604) · full text:
  https://talkbank.org/class/access/0docs/graesser1995.pdf
  Built on in: Nye, Graesser & Hu, *AutoTutor and Family: A Review of 17 Years of Natural Language
  Tutoring*, IJAIED 24(4), 2014, DOI [10.1007/s40593-014-0029-5](https://doi.org/10.1007/s40593-014-0029-5).
- **Mechanism:** The authors analysed real tutoring transcripts (graduate students teaching research
  methods; high-schoolers teaching 7th-grade algebra). Ordinary, *untrained* tutors still produced
  learning gains through a pervasive **5-step frame**:
  1. Tutor asks a question or poses a problem.
  2. Learner answers.
  3. Tutor gives short feedback.
  4. Tutor and learner **collaboratively improve the answer** (most of the time is spent here).
  5. Tutor checks the learner's understanding ("Do you see that?").

  AutoTutor turned step 4 into **Expectation & Misconception-Tailored (EMT) dialogue**. Each question has
  a list of *expectations* (the ideas a good answer contains) and known *misconceptions*. When an
  expectation is missing, the tutor escalates **pump → hint → prompt → assertion**. It moves on only when
  each expectation has been said by the learner or, as a last resort, stated by the tutor. A spotted
  misconception triggers a targeted correction.
- **What it means for Stiti:** This is the "proper structure" the owner asked for, *inside* each idea.
  The lesson unit should be a **question with an expectation list**, not a run of cue sentences. The
  learner's spoken answer is matched against the expectations. Only the missing ones get taught.
- **Strengths:** It comes from real human tutoring, and AutoTutor validated it across many studies and
  domains. EMT is mechanical, so the *brain* can run it (expectation coverage is a similarity check
  against local embeddings) and the LLM only phrases the hint. That matches Stiti's "brain is not the LLM"
  rule.
- **Weaknesses:** Step 5, the "Do you understand?" check, is weak evidence. Learners' self-reports of
  understanding are unreliable, so Stiti should ask a probe question instead. (This is widely reported
  from Graesser's tutoring-dialogue work. We did not re-verify the exact statistic in the 1995 text.)
  Writing expectations and misconceptions by hand is costly, so the LLM must generate them from the
  notebook at plan time. Matching in AutoTutor used LSA cosine thresholds (~0.40–0.75), which are noisy.
- **Fit:** **High.** Expectations are generated once per lesson by a free cloud LLM. Coverage is checked
  locally with embeddings already in Stiti (pgvector) in under 100 ms. Each spoken turn is short.

### 3. Kalyuga, Ayres, Chandler & Sweller (2003): the expertise reversal effect (+ rapid diagnosis)

- **Citation:** Slava Kalyuga, Paul Ayres, Paul Chandler, John Sweller. *The Expertise Reversal Effect.*
  Educational Psychologist 38(1):23–31, 2003. DOI
  [10.1207/S15326985EP3801_4](https://doi.org/10.1207/S15326985EP3801_4) · repository:
  https://ro.uow.edu.au/edupapers/136
  Follow-up on fast diagnosis: Kalyuga & Sweller, *Measuring Knowledge to Optimize Cognitive Load
  Factors During Instruction*, J. Educational Psychology 96(3):558–568, 2004, DOI
  [10.1037/0022-0663.96.3.558](https://doi.org/10.1037/0022-0663.96.3.558).
- **Mechanism:** This comes from cognitive load theory. Methods that help novices (full worked examples,
  step-by-step explanation, integrated diagrams) become **redundant and actually harmful** for learners
  who already hold the schemas. Processing the redundant explanation uses up working memory. The effect
  *reverses* with expertise. The 2004 follow-up proposes a **rapid "first-step" diagnostic**: show a task
  and ask for the *first step* (or the answer). Experts jump ahead, novices can't start. That takes
  seconds, and it predicts how to tailor instruction. (The details of the 2004 procedure come from
  abstracts and secondary sources.)
- **What it means for Stiti:** Starting from basics for a learner with an exam tomorrow was not just
  slow. Learning science predicts it is **counter-productive**. Stiti must **measure first**, then pick
  the instruction style per concept: a worked example and explanation for unknown concepts, and a quick
  problem or retrieval question with no re-explanation for known ones. In practice this is a "fading"
  rule driven by the learner model.
- **Strengths:** Directly explains the failure. The rapid first-step test fits a voice turn ("What's the
  first thing you'd do here?"). It's well replicated in the CLT literature.
- **Weaknesses:** Most evidence is from well-structured domains (math, physics, technical training).
  The "expert or novice" judgement is per concept, so Stiti needs a per-concept model (see source 5),
  not one global level.
- **Fit:** **High.** It's a decision rule plus 2–3 short probe questions. Laya / the brain can choose the
  instruction mode per concept from the learner-model score without an LLM call.

### 4. Metcalfe & Kornell (2005): the Region of Proximal Learning (+ Son & Metcalfe 2000 on time pressure)

- **Citation:** Janet Metcalfe, Nate Kornell. *A Region of Proximal Learning Model of Study Time
  Allocation.* Journal of Memory and Language 52(4):463–477, 2005. DOI
  [10.1016/j.jml.2004.12.001](https://doi.org/10.1016/j.jml.2004.12.001) · free PDF:
  https://psychology.columbia.edu/sites/default/files/2016-11/Metcalfe.Kornell.2005_0.pdf
  Time-pressure evidence: Lisa K. Son, Janet Metcalfe. *Metacognitive and Control Strategies in
  Study-Time Allocation.* JEP: Learning, Memory, and Cognition 26(1):204–221, 2000. DOI
  [10.1037/0278-7393.26.1.204](https://doi.org/10.1037/0278-7393.26.1.204)
- **Mechanism:** Study-time allocation has two parts.
  - **Choice:** drop items you already know, then study unlearned items **from easiest to hardest**.
    That means the items just beyond your current knowledge, the "region of proximal learning".
  - **Perseverance:** stay on an item while you feel you are still learning it. Stop when the perceived
    *rate* of learning drops (the judgement of rate of learning, jROL) instead of grinding on a hopeless
    item.

  Son & Metcalfe (2000): with **too little time**, people put more time on judged-easy items, especially
  when they expect a test. With enough time, they favour the hard ones. In other words, under time
  pressure the right move is to **secure the near-mastered material first**. (This finding is from the
  abstract and secondary summaries.)
- **What it means for Stiti:** This gives an "exam tomorrow" triage policy grounded in research, not
  hunches:
  1. Skip what he already knows, with only a 1-question confirmation.
  2. Next, teach what he *half-knows* (the highest gain per minute).
  3. Last, attempt the hardest unknown topics, and only if time remains.
  4. If he's stuck on one point and repeated hints aren't moving him (low rate of learning), park it,
     move on, and come back later instead of looping.

  Coverage of the whole notebook comes from a **map of every topic with a status**, not from lecturing
  every page.
- **Strengths:** Directly about allocating limited study time, which is the owner's exact situation. Very
  cheap to implement: sort topics by estimated mastery, with a time budget.
- **Weaknesses:** Lab studies of self-regulated study (word pairs, trivia, translations), not tutored
  lessons. Applying it to a tutor *choosing for* the learner is our extrapolation. "Easy" must be
  estimated per learner, which again needs a learner model.
- **Fit:** **High.** It's a sort-and-budget policy in the brain, with zero model cost.

### 5. Scarlatos, Baker & Lan (2025): knowledge tracing inside tutoring *dialogues* with LLMs

- **Citation:** Alexander Scarlatos, Ryan S. Baker, Andrew Lan. *Exploring Knowledge Tracing in
  Tutor-Student Dialogues using LLMs.* LAK 2025 (15th Int. Learning Analytics & Knowledge Conf.), ACM,
  pp. 249–259. arXiv: https://arxiv.org/abs/2409.16490
- **Mechanism:** A two-stage pipeline.
  1. An LLM (GPT-4o, zero-shot chain-of-thought) labels each tutor/learner turn pair with the
     **knowledge components (KCs)** it involves and whether the learner's answer was **correct**. These
     labels were validated against human experts.
  2. Classic knowledge-tracing models run on those labels to estimate per-KC mastery over the dialogue.
     They compared BKT, DKT, DKVMN, AKT, SAINT and simpleKT, and also proposed DKT-Sem and LLMKT, which
     fine-tunes Llama-3.1-8B.

  AUC for predicting the next answer's correctness (CoMTA / MathDial): LLMKT 65.8 / 76.7, BKT 52.5 / 64.2,
  DKT 53.2 / 63.2.
- **What it means for Stiti:** "It doesn't understand where I am stuck" is a **learner-model** failure.
  This paper gives the recipe. After each learner turn, tag it with *(concept id from the lesson's topic
  map, correct / partial / wrong / doubt)*, then update a per-concept mastery estimate. That estimate
  drives the next-step choice (sources 3 and 4) and the re-plan.
- **Strengths:** The first serious study of KT in *free-form dialogue*, not multiple-choice logs. It shows
  LLM labelling of KCs and correctness works well enough to build on, and it names the hard parts
  honestly.
- **Weaknesses / limits the authors report:** Short, unstructured dialogues give little signal, and the
  best AUC was about 0.77. GPT-4o mislabels correctness when arithmetic is involved and sometimes
  assigns too many or too few KCs. They annotated whole dialogues offline, so it was **not real-time**.
  Math only. **LLMKT itself needs a fine-tuned 8B model**, which Stiti can't run locally (rule: no local
  LLM, 8 GB RAM).
- **Fit:** **Partial.**
  - Take: per-turn tagging of (concept, correctness), done by the brain where possible: embedding match
    of the answer against the expectation list from source 2. Fall back to a free cloud LLM call batched
    into the same call that writes the next reply.
  - Take: **BKT** as the estimator. It has 4 parameters per concept, runs in microseconds and is
    explainable ("I think you've got X at 0.8").
  - Skip: LLMKT fine-tuning.

### Supporting background (verified, not counted in the 5)

- **Bloom (1984)**, *The 2 Sigma Problem*, Educational Researcher 13(6):4–16,
  DOI [10.3102/0013189X013006004](https://doi.org/10.3102/0013189X013006004). Tutoring combined with
  **mastery learning** (don't move on until the current unit is secured, with corrective feedback) gave
  very large gains. VanLehn (above) shows the real tutoring effect is closer to 0.8 SD, but the mastery
  gate is the transferable idea.
- **Chi & Wylie (2014)**, *The ICAP Framework*, Educational Psychologist 49(4):219–243,
  DOI [10.1080/00461520.2014.965823](https://doi.org/10.1080/00461520.2014.965823). Learning rises from
  **Passive < Active < Constructive < Interactive** engagement. Listening to Stiti's monologue is
  *Passive*. Answering a probe is *Active*. Explaining in his own words is *Constructive*. Back-and-forth
  on his doubt is *Interactive*. The current tutor sits almost entirely at the bottom rung.

---

## Comparison table

| # | Source | Core mechanism | Strengths | Weaknesses | Fits free LLM + 8 GB M2 + voice? |
|---|---|---|---|---|---|
| 1 | VanLehn 2011, *Educ. Psychologist* | Effect grows with interaction granularity up to **step level**, then plateaus (answer-based 0.31 → step-based 0.76 ≈ human 0.79) | Big meta-review; realistic effect sizes; says *how much* interaction is enough | STEM-heavy, pre-LLM systems; "step" needs redefining for conceptual notes | **Yes.** Pure structure; fewer tokens per turn |
| 2 | Graesser, Person & Magliano 1995, *Appl. Cog. Psych.* (+ AutoTutor EMT, Nye et al. 2014) | **5-step frame**: ask → answer → feedback → co-construct (pump → hint → prompt → assert vs. expectation list) → check | Comes from real tutors; mechanical and testable; validated in AutoTutor | "Do you understand?" check is unreliable; expectation authoring cost; noisy semantic matching | **Yes.** LLM writes expectations once; local embeddings check coverage; LLM only phrases hints |
| 3 | Kalyuga et al. 2003, *Educ. Psychologist* (+ Kalyuga & Sweller 2004 rapid test) | **Expertise reversal**: novice aids hurt knowers; **rapid first-step diagnosis** picks the mode | Explains the "started from basics" failure directly; diagnosis takes seconds | Evidence mainly well-structured domains; needs per-concept level | **Yes.** Decision rule + 2–3 voice probes; no LLM needed for the choice |
| 4 | Metcalfe & Kornell 2005, *JML* (+ Son & Metcalfe 2000, *JEP:LMC*) | **Region of proximal learning**: skip known, study near-known first; stop when learning rate stalls; under time pressure favour easier items | Directly models limited-time study (exam tomorrow) | Lab self-study tasks; tutor-chooses-for-learner is our extrapolation | **Yes.** Sort + time budget in the brain |
| 5 | Scarlatos, Baker & Lan 2025, *LAK* | LLM tags each dialogue turn with KCs + correctness → **BKT/DKT/LLMKT** estimate per-KC mastery | First real KT-in-dialogue study; honest about limits | AUC ≤ 0.77; offline, not real-time; math only; LLMKT needs fine-tuned 8B | **Partly.** Use tagging (embeddings first, batched cloud LLM fallback) + BKT; skip LLMKT |
| bg | Bloom 1984; Chi & Wylie 2014 | Mastery gate; ICAP engagement ladder | Classic, widely replicated framing | 2-sigma is overstated (see #1); ICAP is a taxonomy, not an algorithm | Yes, as design principles |

---

## Design rules for Stiti's tutor structure

These are derived from the sources above. Each one says which complaint it fixes.

**R1. Ask first, and decide in the first ~60–90 s where to start (fixes "started from basics, ignored
me").** Sources 3, 4, 5.
Before teaching anything, ask the goal and the deadline in one turn ("What's this for, and when?"). Then
use the topic map to ask **2–3 rapid first-step probes**: one easy, one middle, one hard concept from
the notebook ("Quick one: what's the first thing you'd do to…?"). Each answer seeds that concept's BKT
prior and gives you its neighbours. Start teaching at the **lowest concept he fails**, never at page 1
by default. If he says "I know the basics", believe it provisionally and confirm with one probe.

**R2. Build the plan as a topic map with statuses, not a fixed 3-idea outline (fixes "whole notebook not
covered" and "no structure").** Sources 4, 5.
At plan time, the cloud LLM turns the whole book or notebook into a flat list of **concepts**. Each
concept gets: id, one-line claim, 1–3 expectations, common misconceptions, one probe question, and
prerequisites. Each concept has a status (`unknown → shaky → known`) and a mastery score. The board
header shows the map and his progress, so "where am I" is always visible. The unit of coverage is the
**map**, not the narration.

**R3. Triage by time budget when there's a deadline (the exam-tomorrow mode).** Source 4.
Given `minutes_left`, order concepts by **known → confirm in 1 question** (seconds), then
**shaky / near-known → teach** (highest gain per minute), then **unknown and hard → only if time
remains**, then **parked** items last. Respect prerequisites. Say the plan out loud in one sentence
("You've got X and Y. We'll lock in Z and W, then try V if there's time."). If time runs out, end with
a 2-minute rapid-fire recap of the shaky items rather than starting new material.

**R4. Every teaching step is one ask → answer → react loop. Never more than ~2 spoken sentences before
he has to do something (fixes "saying, saying, saying").** Sources 1, 2, ICAP.
Replace the "5–8 cues then 1 check" segment with **micro-steps**: at most 2 sentences of explanation
plus a board op, then a question he must answer (a prediction, a next step, or "say it in your words").
This moves Stiti from answer-based (≈0.3 SD) to step-based (≈0.76 SD), which is the plateau, so don't
over-engineer beyond it. The player must **stop and wait for his answer**, not continue on a timer.

**R5. Use EMT for the reaction: match his answer to expectations, then escalate pump → hint → prompt →
tell (fixes "doesn't understand where I'm stuck").** Sources 2, 5.
Score his spoken answer against the concept's expectations with local embeddings (brain, < 100 ms).
- All expectations covered: brief confirm, mastery up, next concept.
- Some missing: a **pump** ("and what else?"), then a **hint** aimed at the specific missing
  expectation, then a fill-in **prompt**, then **assert** it and re-probe later.
- A misconception matched: correct that exact misconception.

Log every turn as `(concept, correct | partial | wrong | doubt)` and update BKT. "Where he's stuck" is
then the concept with the lowest mastery and the latest failed expectation. Stiti can say this aloud.

**R6. Treat his doubts and interruptions as the highest-priority plan input, then re-plan.** Sources 2,
4, 5.
A barge-in or a doubt pauses the current step. Classify it (Laya): a question about this concept, a
question about a prerequisite, "I already know this", "go faster/slower", "skip", or "I'm lost". Answer
it in that same loop, tied to the board. Then **re-plan from the topic map**:
- "Already know": mark known after a 1-question confirmation, jump ahead.
- "Lost": drop to the prerequisite and switch to worked-example mode.
- A doubt on another concept: move that concept up the queue.

Never resume the old script as if nothing happened.

**R7. Choose the instruction mode per concept from mastery (expertise reversal).** Source 3.
- Low mastery: a **worked example** on the board, explained step by step, then a faded version where he
  supplies a step.
- Medium mastery: go straight to a problem or question, with hints only if needed.
- High mastery: one retrieval question, no explanation, move on.

Don't re-explain what he has just shown he knows. Redundant explanation actively hurts the knowledgeable
learner.

**R8. Close each concept with a probe, not "Do you understand?"; and park when he stalls.** Sources 2,
4, Bloom.
The mastery gate is **his correct answer to a fresh probe**, not his self-report. If two full EMT cycles
on a concept don't raise mastery (the rate of learning has stalled), **park** it ("let's come back to
this one"), move on, and revisit it later in the session or in a spaced review. Quiz and flashcards at
the end come from the concepts still `shaky`, not from a generic list.

---

## How this maps onto the current Stiti design (suggested shape, not code)

| Current | Proposed |
|---|---|
| Outline: title, thesis, **3 ideas**, hook, quiz, flashcards | **Topic map** of all concepts in the source, each with expectations, misconceptions, probe and prerequisites, plus a goal/deadline header |
| Segment = 5–8 one-sentence cues + 1 check, played in order | Micro-step = ≤2 sentences + board op + **question → wait → EMT reaction** |
| Starts at idea 1 for everyone | **Diagnose (R1)** then **triage order (R3)** |
| No learner model | Per-concept **BKT** updated from tagged turns (R5) |
| Interruptions are side questions | Interruptions **re-plan** the queue (R6) |
| Same explanation style throughout | Mode per concept from mastery (R7) |

The brain (topic map, BKT, triage sort, embedding-based expectation matching, Laya classification of
doubts) makes every decision locally. The free cloud LLM is used **once at plan time** to build the
topic map, and per turn only to *phrase* a short hint or explanation from the brain's briefing. That
keeps to the project rule that the LLM is the mouth, not the brain, and keeps each turn's latency and
token use small.

## Open questions / not verified

- The exact unreliability statistic for "Do you understand?" checks was not re-verified in the 1995
  full text.
- The Son & Metcalfe (2000) time-pressure finding and the Kalyuga & Sweller (2004) rapid-test procedure
  were confirmed from abstracts and secondary summaries, not the full papers.
- Expectation matching by embeddings (rather than AutoTutor's LSA) is our design choice. It needs a
  small eval on real spoken answers (Whisper transcripts are noisy) to set the thresholds.
