# Whiteboard Tutor: Pedagogy for a 30-Minute "Friend and Tutor" Voice Session

Research date: 2026-11-10. Scope: how Stiti should teach a topic or a book in about 30 minutes by voice, with a live whiteboard, to one adult learner who speaks casual Indian English or Hinglish and may interrupt at any time. Stiti's LLM is a free cloud mid-size model (gpt-oss-20b/120b, Qwen ~27B class).

**Confidence markers**
- **(verified)**: I checked the figure against the primary source or its abstract this session.
- **(not re-verified)**: a well-known primary result whose numbers I give from memory or from secondary summaries. Check before quoting.
- **(unverified)**: vendor claims, secondary blogs, or my own inference.
- **Design heuristic**: my recommendation, derived from the evidence but not directly tested.

---

## 0. TL;DR

1. **Shape.** Run 30 minutes as about 26 minutes of planned content plus about 4 minutes of slack for interruptions:
   - warm-up and big-picture map;
   - 3 teaching segments of about 5–6 minutes each, every one ending in an active check;
   - a learner "teach it back" plus apply block;
   - a no-notes retrieval quiz;
   - a 3-line wrap that creates FSRS cards.
2. **Speech chunks.** Never speak more than about 60–90 s, which is about 150–200 words, without handing the turn to the learner.
3. **The board** is drawn while speaking, not before (dynamic drawing, temporal contiguity). It holds keywords and diagrams only, never the narration as paragraphs (redundancy, coherence).
4. **Explain freely, but make the learner generate.** Bastani et al. found that answer-giving AI harms learning on practice problems. Kestin et al. found that a scaffolded, step-at-a-time tutor beat active-learning class. The difference is guardrails: telling is fine for a first-pass explanation, but every segment must end with the learner doing something (predict, recall, explain, apply).
5. **Questions.** Classify each interruption, answer clarifications directly and briefly, and use Socratic hints only for things the learner can work out in 1–2 steps. Cap hints at 2, then tell. Resume through a focus stack with a one-sentence bridge and a board re-highlight.
6. **Books.** Build a page-cited outline first: thesis, 3 key ideas, 1 example each. Every book claim in the script carries page refs and is claim-checked before the session. Things not in the book are labelled "meri taraf se example". Caveats, secondary frameworks and long case studies go to sessions 2 and 3.
7. **Small-model pipeline.** Generate in four steps (outline JSON → per-segment JSON, one call each → validator → repair), with enums, short strings, layout slots instead of coordinates, and reasoning before the JSON. Plan before the session starts. Judge with a bigger free model using a LearnLM/MRBench-style rubric, and run simulated-learner tests.

---

## 1. Learning science for a 30-minute session

### 1.1 Comparison table

| # | Name | Link | Year | Mechanism | Evidence / effect size | Strengths | Weaknesses | Fit for Stiti |
|---|---|---|---|---|---|---|---|---|
| 1 | Bloom "2 sigma problem" | [Educ. Researcher](https://doi.org/10.3102/0013189X013006004) | 1984 | 1:1 tutoring + mastery learning with formative tests and correctives | Tutored students about 2 SD above conventional class (not re-verified) | Sets the aim: 1:1 + feedback + mastery | Small, short studies. Later syntheses find far smaller effects (row 2) | Motivates the format; don't promise 2 SD |
| 2 | VanLehn tutoring meta-review | [Educ. Psychologist 46(4)](https://doi.org/10.1080/00461520.2011.611369) | 2011 | Compares human tutors and ITS by interaction granularity | Human d=0.79; step-based ITS d=0.76; substep 0.40; answer-based 0.31 (verified via abstract summaries) | "Interaction plateau": step-level interaction gets nearly all the benefit | Mostly STEM problem-solving | Interact at the **step/idea level** (check after each idea), not only at the end |
| 3 | Nickow, Oreopoulos & Quan tutoring meta-analysis | [NBER w27476](https://www.nber.org/papers/w27476) | 2020 | 96 RCTs of PreK-12 tutoring | Pooled about 0.37 SD (not re-verified) | Large RCT base | Children, human tutors, many sessions | Realistic expectation: tutoring helps, in multiple sessions |
| 4 | Retrieval practice (Roediger & Karpicke; meta-analyses) | [Psych Sci 2006](https://doi.org/10.1111/j.1467-9280.2006.01693.x); [Rowland 2014](https://doi.org/10.1037/a0037559); [Adesope 2017](https://doi.org/10.3102/0034654316689306) | 2006–2017 | Recalling from memory strengthens it more than re-reading | Testing beat restudy at 1 week despite feeling worse. Meta g≈0.50 (Rowland) and g≈0.61 (Adesope) (not re-verified) | Cheap; works by voice; also diagnostic | Needs feedback after errors; low-stakes framing matters | **Core.** Checks after every segment plus a final no-notes quiz |
| 5 | Dunlosky et al. "Improving students' learning" | [PSPI](https://doi.org/10.1177/1529100612453266) | 2013 | Rates 10 study techniques | High utility: practice testing, distributed practice. Moderate: elaborative interrogation, self-explanation, interleaving. Low: rereading, highlighting, summarizing (not re-verified) | Practical ranking | Utility ratings, not a meta-effect | Use testing + spacing as backbone, elaboration as filler |
| 6 | Worked examples / CLT (Sweller; expertise reversal) | [Sweller & Cooper 1985](https://doi.org/10.1207/s1532690xci0201_3); [Kalyuga et al. 2003](https://doi.org/10.1207/S15326985EP3801_4) | 1985–2003 | Studying a solved example frees working memory for schema building. Fade steps as skill grows | Robust for novices. Reverses for experts (expertise reversal) | Ideal for procedures and frameworks | Must fade; boring for experts | One worked example per procedural idea; skip or fade when the learner already knows it |
| 7 | Cognitive Load Theory + working-memory limits | [Sweller 1988](https://doi.org/10.1207/s15516709cog1202_4); [Cowan 2001](https://doi.org/10.1017/S0140525X01003922) | 1988/2001 | Working memory holds about 4 chunks. Separates intrinsic, extraneous and germane load | Foundational theory; effects come through the derived principles | Explains *why* to segment and keep the board clean | Load is hard to measure | **At most 3–4 key ideas per 30 min.** At most 1 new idea per narration chunk |
| 8 | Mayer multimedia principles | [Multimedia Learning 3e](https://doi.org/10.1017/9781316941355); [Mayer 2017 JCAL](https://doi.org/10.1111/jcal.12197) | 2001–2021 | Narration + graphics; coherence, signaling, segmenting, pretraining, modality, redundancy, temporal contiguity, personalization | Median d (2021 table, partial): coherence 0.86, pretraining 0.78. Older 2017 review: signaling 0.46, segmenting 0.70, modality 0.72, temporal contiguity 1.30, redundancy 0.87. Editions differ; don't mix (verified via search excerpts) | Directly maps to "narrate + draw" | Mostly short lab lessons (≤ about 10 min) | **Core design spec** for board + narration (§1.3) |
| 9 | Dynamic instructor drawing | [Fiorella & Mayer 2016](https://doi.org/10.1037/edu0000065); [Fiorella et al. 2019](https://doi.org/10.1037/edu0000325) | 2016/2019 | Watching diagrams being drawn while explained, versus static diagrams | Hand-drawing condition beat static on transfer, d≈0.35. The benefit vanished when the hand wasn't visible in one experiment (verified via search) | Directly supports progressive whiteboard rendering | The "hand/agent" cue may matter; Stiti has no hand | Draw strokes progressively with a visible pen cursor. Don't pop full diagrams in |
| 10 | Dual coding | [Clark & Paivio 1991](https://doi.org/10.1007/BF01320076) | 1971–1991 | Verbal + imagery codes give two retrieval routes | Theory; empirical support comes through the multimedia effect (Mayer d≈1.3+, not re-verified) | Justifies a diagram for every idea | Not every idea is drawable | Every key idea gets one picture: flow, 2x2, timeline, cycle or analogy sketch |
| 11 | Self-explanation / elaboration | [Chi et al. 1994](https://doi.org/10.1207/s15516709cog1803_3); [Bisra et al. 2018](https://doi.org/10.1007/s10648-018-9434-x) | 1994/2018 | Learner explains *why* a step or idea holds, linking it to prior knowledge | Meta g≈0.55 (not re-verified) | Works by voice; cheap | Quality of explanations varies; needs prompting | "Yeh kyun hota hai, apne words mein?" prompts. Explain-back block |
| 12 | Learning-by-teaching / "Feynman technique" | [Fiorella & Mayer 2013](https://doi.org/10.1016/j.cedpsych.2013.06.001) | 2013 (Feynman folk method) | Explain simply to a novice and find the gaps | Actually teaching (explaining on video) beat merely expecting to teach on delayed tests (not re-verified). **The "Feynman technique" itself has no direct RCT (unverified)** | High engagement; reveals gaps | Time-costly; anxious learners dislike it | One 3–4 min "teach me back like I'm your cousin" block near the end |
| 13 | Interleaving | [Brunmair & Richter 2019](https://doi.org/10.1037/bul0000209) | 2019 | Mix related categories so learners must discriminate | Meta g≈0.42 overall; strongest for similar-looking categories, can hurt for some materials (not re-verified) | Good for "which concept applies here?" | Needs ≥2 learned concepts; few items in 30 min | Final quiz mixes ideas 1–3 in random order; "which idea is this?" scenario questions |
| 14 | Spacing | [Cepeda et al. 2006](https://doi.org/10.1037/0033-2909.132.3.354); [Cepeda et al. 2008](https://doi.org/10.1111/j.1467-9280.2008.02209.x) | 2006/2008 | Distributed review beats massed review; best gap ≈10–20% of retention interval (not re-verified) | Among the most robust effects | Free, automatable | Happens *after* the session | FSRS cards from every session; session 2 opens with spaced retrieval |
| 15 | Advance organizers / pretraining | [Ausubel 1960](https://doi.org/10.1037/h0046669); [Luiten et al. 1980](https://doi.org/10.3102/00028312017002211) | 1960–1980 (+Mayer pretraining) | Give the big-picture structure and key terms before details | AO meta: small positive (~0.2, not re-verified). Mayer pretraining d≈0.78 (2021) | Cheap; reduces load during the main explanation | Weak if the organizer is just a summary | 60–90 s "map" of 3 boxes on the board + key terms at minute 1.5 |
| 16 | Pretesting / prediction questions | [Richland, Kornell & Kao 2009](https://doi.org/10.1037/a0016496) | 2009 | Guessing before being taught, even wrongly, improves later learning | Robust in lab (not re-verified) | Creates curiosity; good hook | Can frustrate if overused | One "guess first" question per session (hook) and optional per-segment predictions |
| 17 | Interpolated tests in online lectures | [Szpunar, Khan & Schacter 2013](https://doi.org/10.1073/pnas.1221764110) | 2013 | Short quizzes between lecture segments | Mind-wandering halved (~40%→~20% of probes); better final test; 21-min lecture (verified) | Directly about attention in recorded explanations | Single lecture/topic | **Evidence for "check every ~5 min"** |
| 18 | Video segment length (edX) | [Guo, Kim & Rubin 2014](https://doi.org/10.1145/2556325.2566239) | 2014 | Watch-time on 6.9M sessions | Engagement drops after ~6 min; Khan-style tablet drawing more engaging than slides (verified) | Huge observational dataset | Engagement, not learning; MOOC context | Segments ≤ 6 min; freehand-style drawing |
| 19 | "Attention span is 10–15 min" critique | [Bradbury 2016](https://doi.org/10.1152/advan.00109.2016) | 2016 | Review of attention-span claims | Fixed 10–15 min span is not well supported (not re-verified) | Corrects a myth | — | Use segment length for *interaction rhythm*, not as a hard "attention limit" |
| 20 | ICAP framework | [Chi & Wylie 2014](https://doi.org/10.1080/00461520.2014.965823) | 2014 | Interactive > Constructive > Active > Passive engagement | Synthesis of many studies (not re-verified) | Simple rubric for designing checks | Coarse categories | Prefer constructive checks (explain, apply) over MCQ when time allows |

### 1.2 What this means for a single 30-minute session

- **Content budget:** 1 thesis/big idea + **3 key ideas** (4 at most). Cowan's ~4 chunks and Mayer's segmenting and pretraining all point the same way. More ideas go to session 2. (Design heuristic.)
- **Rhythm:** a segment of about 5–6 min = (1) a narration chunk of ≤ 60–90 s while drawing → (2) a micro-interaction (a "make sense?" never counts; use a real prompt) → (3) a second chunk + example → (4) an end-of-segment check of 45–90 s. Sources: Guo 2014 (< 6 min), Szpunar 2013, VanLehn's step-level interaction. (Design heuristic.)
- **Speech rate:** at about 140–160 wpm a 60–90 s chunk is about 150–220 words, i.e. 8–12 sentences of ≤ 20 words. Short sentences also help TTS and barge-in. (Design heuristic.)
- **Ordering:** hook/prediction → map → ideas (concrete example *before* abstraction for novices) → connect ideas → learner generates (teach back, apply) → retrieval → spaced follow-up.

### 1.3 Mayer principles translated into whiteboard rules

| Principle | Rule for Stiti's board + voice |
|---|---|
| Multimedia | Every key idea has a visual. Words alone are a fallback. |
| Temporal contiguity | Draw an element **in the same sentence** that names it. Cue anchored to sentence index. |
| Spatial contiguity | Labels sit on or next to the shape they name. No legends. |
| Redundancy / modality | Board shows **keywords (≤ 5 words/label)**, not the spoken sentences. No subtitles of narration. |
| Coherence | No decorative clip art, no "fun facts" not tied to the goal. Erase finished sketches or move them to a "done" corner. |
| Signaling | Highlight/circle/underline the element being discussed; title each segment on the board; "pehli baat… doosri baat…" verbal signposts. |
| Segmenting | Learner-paced: pause after each chunk; "continue / repeat / slow" always allowed. |
| Pretraining | Key terms + 3-box map before the details. |
| Personalization | Conversational "you/we/apan" style, the learner's own examples. Ginns et al. meta ([2013](https://doi.org/10.1007/s10648-013-9228-0)) supports conversational style (effect sizes not re-verified). |
| Voice | Mayer's original "human voice > machine voice" weakens with modern TTS ([Craig & Schroeder 2017](https://doi.org/10.1016/j.compedu.2017.08.006), not re-verified). Use the best natural TTS available. |
| Generative activity | Ask the learner to predict, sort or label. "Board pe kya likhna chahiye yahan?" lets the learner name a label before it is drawn. |

---

## 2. AI tutor systems and their pedagogy rules

### 2.1 Comparison table

| # | System / study | Link | Year | Mechanism | Evidence / effect size | Strengths | Weaknesses | Fit / lesson for Stiti |
|---|---|---|---|---|---|---|---|---|
| 1 | Google LearnLM-Tutor tech report | [arXiv 2407.12687](https://arxiv.org/abs/2407.12687) | 2024 | Gemini 1.0 fine-tuned for 1:1 tutoring. Five principles: **encourage active learning, manage cognitive load, deepen metacognition, motivate/stimulate curiosity, adapt to learners' goals and needs** | Educators preferred it over prompted Gemini. Learners: only "confidence to apply later" significant. Shorter turns (297.6 vs 423 tokens) (verified) | Most detailed public pedagogy rubric + automatic "critics" | Text-only; gains modest on learner side | **Adopt the 5 principles + critic list** as eval rubric (§6) |
| 2 | LearnLM: "pedagogical instruction following" | [arXiv 2412.16429](https://arxiv.org/abs/2412.16429) | 2024–25 | Pedagogy specified in the system prompt; SFT + RLHF to follow it | Expert raters preferred LearnLM by 31% over GPT-4o, 11% over Claude 3.5 Sonnet, 13% over Gemini 1.5 Pro (verified) | Shows **system-prompt pedagogy works** if the model follows it | We can't fine-tune; free models follow instructions less reliably | Put pedagogy in a short, concrete system prompt + per-turn reminders |
| 3 | Kestin et al., Harvard physics AI tutor RCT ("PS2 Pal") | [Sci. Reports 15:17458](https://doi.org/10.1038/s41598-025-97652-6) | 2025 | GPT-4 tutor with prompt built on active learning, cognitive load, growth mindset, scaffolding, accuracy (solutions supplied in the prompt), timely feedback; self-paced | Crossover RCT, N=194. Median post 4.5 vs 3.5. Effect 0.63 SD by OLS; 0.73–1.3 by quantile regression (verified). Critics: no delayed retention test; small re-analysis effect | **Key design evidence: ground the tutor with expert-written content, scaffold one step at a time** | Two weeks, elite students, ceiling effects | Feed the tutor the **verified book chunks / plan** rather than letting it free-generate facts |
| 4 | Bastani et al. "Generative AI without guardrails can harm learning" | [PNAS 122(26)](https://doi.org/10.1073/pnas.2422633122); [SSRN](https://papers.ssrn.com/abstract=4895486) | 2024–25 | ~1,000 Turkish HS students; GPT Base (ChatGPT-like) vs GPT Tutor (hints, no answers, teacher solutions in prompt) | Practice +48% (Base) / +127% (Tutor). On the unassisted exam Base was **−17%** vs control (preprint); Tutor ≈ control. Tutor users **overestimated** their learning (verified via abstract) | Clean causal evidence of "crutch" harm | Practice-problem setting, not concept teaching | **Never let the learner skip the generation step.** Don't trust "haan samajh gaya". Measure with checks |
| 5 | Stanford Tutor CoPilot | [arXiv 2410.03017](https://arxiv.org/abs/2410.03017) | 2024 | LLM suggests expert-like moves to human tutors in real time | RCT, 900 tutors / 1,800 students: +4 pp mastery (p<0.01); +9 pp for weaker tutors; more guiding questions, fewer giveaways; ~$20/tutor/yr (verified) | Shows *which moves* matter: guiding questions, prompting explanation | Human in the loop | Encode expert moves as **explicit strategy labels** the model must pick before speaking |
| 6 | Bridge (Wang et al., NAACL) | [ACL 2024.naacl-long.120](https://aclanthology.org/2024.naacl-long.120) | 2024 | Expert decision model: identify **error type → choose strategy → state intention**, then write response | Giving the LLM error + strategy improved response quality a lot (+75% in v1); random strategies hurt (verified, version-dependent numbers) | Concrete, cheap decomposition that helps smaller models | Math-only data | **Use "diagnose → strategy → say" as hidden fields** in the tutor's JSON turn |
| 7 | AutoTutor (Graesser et al.) | [Graesser 2004](https://doi.org/10.3758/BF03195563); [Nye, Graesser & Hu 2014](https://doi.org/10.1007/s40593-014-0029-5) | 1997–2014 | **Expectation–Misconception Tailored (EMT) dialogue**: each question has expected answer parts + known misconceptions. Moves: pump → hint → prompt → assertion → summary; corrects misconceptions | ~0.8 SD vs reading textbooks across studies (not re-verified) | 20+ years of evidence; maps cleanly to JSON | Hand-authored; scripts rigid | **Adopt EMT**: each check has `expectations[]`, `misconceptions[]`, hint ladder |
| 8 | Khanmigo (Khan Academy) | [khanmigo.ai](https://www.khanmigo.ai/) | 2023– | GPT-4-based Socratic tutor; won't give answers; "tutor me" mode; teacher tools | No peer-reviewed RCT found (unverified); public reports of early struggles with math accuracy (unverified) | Mature product rules: don't do the work for the learner; ask what they think first | Can feel withholding/annoying for adults; evidence thin | Borrow "ask what they think first", **not** strict refusal, for an adult first-pass learner |
| 9 | Duolingo Max (Explain My Answer, Roleplay, Video Call) | [Duolingo blog](https://blog.duolingo.com/duolingo-max/) | 2023–24 | GPT-4 explanations of mistakes; voice roleplay persona | No published learning effect (unverified) | Persona + friendly voice; short explanations right at the error | Language-only; evidence internal | Explain the learner's **own** mistake right after it, short |
| 10 | OATutor + ChatGPT hints (Pardos & Bhandari) | [arXiv 2302.06871](https://arxiv.org/abs/2302.06871); OATutor CHI'23 (not re-verified) | 2023–24 | Open-source ITS; compared ChatGPT vs human-authored hints | 2023: 70% of ChatGPT hints passed checks; human hints gave larger gains. 2024 PLoS ONE version (N=274): ChatGPT hints gave significant gains vs control (verified via summary) | Open content; shows LLM hints need checking | Algebra only | **Quality-check generated hints** (pre-session validation) |
| 11 | Ruffle & Riley (Schmucker et al.) | [arXiv 2404.17460](https://arxiv.org/abs/2404.17460) | 2023–24 | Induces a tutoring script from lesson text; learner teaches agent "Ruffle", professor agent "Riley" helps | N=200: **no significant learning gain vs reading**, but higher engagement and helpfulness ratings; took more time (verified) | Lesson-text → script automation, close to our book pipeline | Engagement ≠ learning | Script induction from text is viable; **measure learning, not just liking** |
| 12 | Socratic LLM tutors: MathDial, SocraticLM | [MathDial arXiv 2305.14536](https://arxiv.org/abs/2305.14536); SocraticLM (NeurIPS 2024, not re-verified) | 2023–24 | Teacher–LLM-student dialogues; fine-tuned Socratic models | MathDial found LLM tutors often **"tell" too early** and are factually unreliable about student errors (not re-verified) | Data + failure modes | Pure-Socratic is slow and can frustrate | Use Socratic moves selectively (§3.4) |
| 13 | Pedagogical RL (Dinucu-Jianu et al.) | [arXiv 2505.15607](https://arxiv.org/abs/2505.15607) | 2025 | Online RL with simulated students; reward = student solves + pedagogy score, with a penalty for leaking | 7B tutor approaches LearnLM; tunable pedagogy-vs-solve Pareto (verified via abstract) | **Simulated-student eval** pattern | Training not feasible for us | Reuse the *simulated learner* idea for eval (§6) |
| 14 | World Bank Nigeria (De Simone et al.) | [WB WPS 11125](https://openknowledge.worldbank.org/entities/publication/15e1ff08-15ae-4f7a-b2a8-d146e6c113ee/full) | 2025 | Copilot (GPT-4) after-school English, 6 weeks, teacher-guided prompts | 0.31 SD overall; English ~0.23 SD; dose–response with attendance (verified) | LMIC setting; teacher-designed prompts | Teacher present; volunteers only | Structured, guided prompts + repeated sessions work outside rich-country labs |
| 15 | Rori (Henkel et al., Ghana) | [arXiv 2402.09809](https://arxiv.org/abs/2402.09809) | 2024 | WhatsApp math tutor, **2×30-min sessions/week** for 8 months | 0.36–0.37 SD (verified, version-dependent) | 30-min format at scale, chat-based | Kids, math | 30-min sessions repeated over weeks are a proven unit |
| 16 | ChatGPT Study Mode / Gemini Guided Learning / Claude learning mode | [OpenAI](https://openai.com/index/chatgpt-study-mode/); [TechCrunch on Guided Learning](https://techcrunch.com/2025/08/06/google-takes-on-chatgpts-study-mode-with-new-guided-learning-tool-in-gemini/) | 2025 | System-instruction modes: Socratic questions, hints, check-ins, quizzes, visuals (Gemini) | No published learning RCTs (unverified); OpenAI says it was built with teachers and learning scientists | Shows industry consensus on rules | Learners can toggle them off; no outcome data | Consensus rules: scaffold, check, don't dump, offer quizzes |
| 17 | Google "Learn Your Way" (AI-augmented textbooks) | [Google Research blog](https://research.google/blog/learn-your-way-reimagining-textbooks-with-generative-ai/); [arXiv 2509.18664](https://arxiv.org/abs/2509.18664) | 2025 | Textbook personalized to learner interests + multiple representations (mind map, narrated slides, audio lesson, quizzes) | N=60 teens: retention test 3–5 days later +11 pp (≈78% vs 67%) vs standard reader (verified via blog) | Closest to "teach from a book" | Small N; Google-run | **Personalize examples to the learner's interests, keep the book's facts** |
| 18 | Lehmann et al. "When do LLMs harm learning?" | [arXiv 2409.09047](https://arxiv.org/abs/2409.09047) | 2024 | Experiments where LLM substitutes vs complements learner effort | LLM use reduced learning when it substituted for practice; helped when complementary (not re-verified) | Replicates the Bastani pattern | Lab setting | Same lesson: keep the learner's effort in the loop |

### 2.2 Extracted rules (consensus across rows 1–18)

**DO**
1. Ground every factual claim in supplied content (book chunks, verified plan). Kestin supplied solutions; Bastani's GPT Tutor had teacher solutions; LearnLM measured factuality separately.
2. Teach in steps, one idea at a time; keep turns short (LearnLM: shorter turns rated better; "wall of text" adds load).
3. Ask one question at a time, and wait.
4. Before responding to an error, decide silently: what kind of error → which strategy → what intention (Bridge, Tutor CoPilot).
5. Use expectation/misconception lists for each check, with a hint ladder: pump → hint → prompt → tell (AutoTutor).
6. Prompt the learner to explain, predict and apply (Tutor CoPilot's "guiding questions"; ICAP).
7. Praise effort and strategy specifically; treat mistakes as normal (LearnLM, Kestin growth mindset).
8. Adapt to the learner's level and goals; check in proactively when they're struggling (LearnLM principle 5).
9. Stimulate curiosity: hooks, predictions, "guess karo" (LearnLM principle 4).
10. Build metacognition: "How sure are you, 1–5?"; "What was the hardest part?" (LearnLM principle 3).

**DON'T**
1. Don't give the answer to a *check question* before the learner has tried (Bastani; LearnLM critic "don't reveal the answer").
2. Don't accept "haan samajh gaya" as evidence. Learners overestimate their learning (Bastani GPT-Tutor group; Graesser & Person, §3).
3. Don't produce monologues > 90 s or more than 1 new idea per chunk.
4. Don't invent facts, page numbers or quotes. Say "book mein yeh nahi hai, but generally…".
5. Don't be Socratic for its own sake. Withholding simple information from an adult who asked frustrates them and wastes time (assistance dilemma, §3).
6. Don't use generic praise ("Great job!") or person-praise ("you're so smart").
7. Don't go off-topic for long; park tangents.
8. Don't measure success by engagement alone (Ruffle & Riley: liked more, didn't learn more).

---

## 3. Checking understanding and handling questions

### 3.1 Comparison table

| # | Name | Link | Year | Mechanism | Evidence / effect | Strengths | Weaknesses | Fit |
|---|---|---|---|---|---|---|---|---|
| 1 | Black & Wiliam "Assessment and classroom learning" | [Assess. in Educ.](https://doi.org/10.1080/0969595980050102) | 1998 | Formative assessment: elicit evidence → feedback → adjust teaching | Claimed 0.4–0.7 SD (later contested, not re-verified) | Foundational framing | Effect sizes debated | The whole session is a formative loop |
| 2 | Kingston & Nash formative-assessment meta | [EM:IP](https://doi.org/10.1111/j.1745-3992.2011.00220.x) | 2011 | Re-estimate of formative-assessment effects | ~0.20 weighted mean (not re-verified) | Sober estimate | Heterogeneous studies | Expect modest gains per check; value is in adaptation |
| 3 | Wiliam: hinge questions / diagnostic MCQ | *Embedded Formative Assessment* (Wiliam 2011, book) | 2011 | One quick question where each wrong option maps to a specific misconception | Practitioner framework (no meta-ES) | Fast (30 s), diagnostic | Needs good distractors | **MCQ distractors = known misconceptions**; wrong pick triggers that misconception's remediation |
| 4 | Hattie & Timperley feedback model; Wisniewski meta | [RER 2007](https://doi.org/10.3102/003465430298487); [Front. Psych 2020](https://doi.org/10.3389/fpsyg.2019.03087) | 2007/2020 | Feedback at task, process and self-regulation levels; avoid "self" level | Feedback d≈0.48 (Wisniewski) (not re-verified) | Clear levels | Wide variance | Feedback names *what* was right/wrong and *the next step* |
| 5 | Kluger & DeNisi feedback intervention meta | [Psych Bull](https://doi.org/10.1037/0033-2909.119.2.254) | 1996 | Feedback can hurt when it directs attention to the self | d≈0.41, but >1/3 of effects negative (not re-verified) | Warns against ego-focused feedback | Old | No "you're smart / bad"; task-focused only |
| 6 | Shute "Focus on formative feedback" | [RER](https://doi.org/10.3102/0034654307313795) | 2008 | Guidelines: specific, elaborated, timely for novices, manageable chunks | Review (no single ES) | Practical do/don't list | — | Elaborated feedback right after errors; brief "sahi!" + why after correct answers |
| 7 | Graesser & Person "Question asking during tutoring"; comprehension-gauging questions | [AERJ 1994](https://doi.org/10.3102/00028312031001104); [Graesser, Person & Magliano 1995](https://doi.org/10.1002/acp.2350090604) | 1994–95 | Analysis of real tutoring dialogue | "Do you understand?" answers are unreliable; poorer students often say yes (not re-verified) | Explains why "samjha?" fails | Older corpus | **Ban "samjha?" as a check.** Use generative checks |
| 8 | Illusion of explanatory depth | [Rozenblit & Keil 2002](https://doi.org/10.1207/s15516709cog2605_1) | 2002 | People overrate understanding until asked to explain step by step | Robust (not re-verified) | Motivates explain-back | — | Explain-back reveals gaps; frame kindly |
| 9 | Hypercorrection effect | [Butterfield & Metcalfe 2001](https://doi.org/10.1037/0278-7393.27.6.1491) | 2001 | High-confidence errors, once corrected, are remembered better | Robust lab effect (not re-verified) | Justifies confidence ratings | — | Ask "kitna sure ho?" on the final quiz; dwell on confident errors |
| 10 | Pretesting / prediction-error | [Richland et al. 2009](https://doi.org/10.1037/a0016496) | 2009 | Predict before seeing the answer | Robust (not re-verified) | Hook + diagnostic | Overuse frustrates | One prediction per segment at most |
| 11 | AutoTutor EMT + hint ladder | [Graesser 2004](https://doi.org/10.3758/BF03195563) | 2004 | Compare learner answer to expectations; pump/hint/prompt/assert | ~0.8 SD vs textbook (not re-verified) | Precise, scriptable | Needs semantic matching (LLM can do it) | **Core check-grading mechanism** |
| 12 | Assistance dilemma | [Koedinger & Aleven 2007](https://doi.org/10.1007/s10648-007-9049-0) | 2007 | Balance giving vs withholding information; depends on learner, task, timing | Theory + ITS studies | **The right frame for "answer directly vs Socratic"** | No single rule | Decision policy in §3.4 |
| 13 | Productive failure meta | [Sinha & Kapur 2021](https://doi.org/10.3102/00346543211019105) | 2021 | Struggle with a problem before instruction | d≈0.36 for conceptual knowledge when well designed (not re-verified) | Supports "guess first" | Needs time; procedural gains weaker | Short (≤ 60 s) struggle only, for the hook |
| 14 | Contingent tutoring / scaffolding | [Wood, Bruner & Ross 1976](https://doi.org/10.1111/j.1469-7610.1976.tb00381.x) | 1975–76 | If the learner fails, give more help; if they succeed, give less | Classic observational/experimental work | Simple adaptive rule | — | Hint ladder up on failure, fade on success |
| 15 | Bridge / Tutor CoPilot moves | see §2 | 2024 | Error → strategy → intention | §2 | Concrete for LLMs | — | Hidden reasoning fields per turn |
| 16 | Discourse focus stack (Grosz & Sidner) | [Comp. Ling. 12(3)](https://aclanthology.org/J86-3001/) | 1986 | Discourse segments push/pop on a focus stack; interruptions are segments that pop back | Theory, widely used in dialog managers | **Clean model for digression + resume** | — | Runtime keeps `lesson_stack` (§3.5) |
| 17 | Teach-back (health literacy) | [Talevski et al. 2020, PLoS ONE](https://doi.org/10.1371/journal.pone.0231350) | 2020 | "Explain back in your own words" as a comprehension check | Systematic review: improves comprehension/recall in health settings (not re-verified) | Field-tested phrasing that isn't patronizing | Health context | "Mujhe apne words mein samjhao, jaise kisi dost ko batate" |

### 3.2 Check types (with 30-min time cost)

| Check | When | Time | Grading |
|---|---|---|---|
| **Predict** ("Guess karo, kya hoga agar…?") | Before an idea (hook) | 20–40 s | Any answer OK; reveal; contrast with the guess |
| **Quick MCQ (2–3 options, spoken)** | Mid-segment | 20–30 s | Each distractor = 1 misconception |
| **Recall** ("Pehle idea ka naam kya tha?") | Start of next segment; final quiz | 15–30 s | Expectation match |
| **Explain-back / self-explain** ("Kyun?") | End of segment | 45–90 s | EMT: covered expectations, flagged misconceptions |
| **Apply / transfer** ("Tumhari life mein yeh kahan dikhta hai?") | Apply block | 60–120 s | Rubric: uses the concept correctly |
| **Discriminate / interleave** ("Yeh scenario idea 1 hai ya idea 3?") | Final quiz | 20–40 s | Correct category + reason |
| **Confidence 1–5** | With final quiz items | 5 s | Hypercorrection: dwell on confident errors |
| **Board-label** ("Is arrow pe kya likhein?") | During drawing | 10–20 s | Accept synonyms |

Never use "Samjha? / Clear hai? / Any doubts?" as a check. You may use them as a *pause invitation*, but follow with a real check. (Design heuristic, from row 7.)

### 3.3 Misconception detection

1. **Pre-generate misconceptions** per key idea at planning time (2–3 each), drawn from the book's own warnings or common misreadings. Store them as `misconceptions[]` with `signal` (what a learner saying it sounds like) and `fix` (contrast example + board cue).
2. **At runtime** the LLM classifies the learner's answer as `{covered_expectations[], misconception_ids[], off_topic, unsure}`. This is a classification task, which is more reliable for small models with structured output than open generation (Tam et al. 2024, §6).
3. **Remediation:** for a misconception, use contrast/counter-example + redraw; for a missing expectation, use the hint ladder; for "don't know", give a smaller sub-question or a worked example.

### 3.4 Question-handling policy: answer directly vs Socratically

The decision applies the assistance dilemma to an *adult, voluntary, first-pass* learner.

```
On learner interruption (barge-in):
  1. Stop TTS at the current sentence boundary. Push {segment_id, sentence_idx, board_snapshot} onto lesson_stack.
  2. Classify the utterance:
     a. CONTROL   ("ruko", "repeat", "slow", "skip", "Hindi mein bolo", "break")  → obey immediately. Autonomy.
     b. CLARIFY   (about the point just made: term, step, "matlab?")             → DIRECT answer, ≤3 sentences, new angle
                                                                                   (analogy/example/redraw), then a 1-line micro-check.
     c. AHEAD     (about something planned later)                                → "Badiya sawaal — wahi 2 min mein aa raha hai."
                                                                                   Give a 1-sentence preview; mark the segment "asked-for".
     d. TANGENT   (related curiosity, not in plan)                                → ≤30 s answer if grounded, else park it:
                                                                                   write in the board's "Parking lot" corner; cover after the wrap or next session.
     e. ATTEMPT / ANSWER to a check                                              → grade with EMT; correct → specific praise + why;
                                                                                   partial/wrong → diagnose (error→strategy→intention), hint ladder.
     f. CHALLENGE ("but I think author is wrong…")                               → welcome it; separate "book says (p. X)" from
                                                                                   "evidence/other views"; don't capitulate on facts, don't defend the book blindly.
     g. OUT-OF-SCOPE / not in book                                               → say so; answer from general knowledge marked "book se nahi".
     h. AFFECT ("boring", "confusing", "thak gaya")                              → acknowledge, offer a choice (example / break / faster / shorter).
  3. Socratic (guide, don't tell) ONLY IF all hold:
       - the answer is derivable in 1–2 steps from what was already taught, AND
       - the learner hasn't explicitly asked "just tell me", AND
       - affect is not frustrated/tired, AND
       - remaining slack ≥ 2 min.
     Otherwise answer directly, then ask one "why/apply" follow-up so the learner still generates.
  4. Hint ladder cap: pump ("aur?") → hint → prompt (fill-in) → tell + explain. Max 2 hints before telling.
  5. Resume (pop the stack): see §3.5.
```

Why this policy: Bastani's harm came from learners *outsourcing practice*. A clarifying question during an explanation is not practice, so answering it directly costs no learning. The generation step is protected by the post-answer follow-up and by the segment checks. (Design heuristic.)

### 3.5 Resuming after a digression

1. **Bridge sentence** (1 line): "Achha, wapas aate hain. Hum yahan the: [last key point in ≤ 12 words]."
2. **Board re-anchor:** restore the snapshot and highlight the last element discussed (signaling).
3. **Re-enter one sentence earlier**, not mid-thought. Re-say the last sentence in paraphrase, then continue.
4. **Time re-plan:** if the stack-pop shows slack < 0, drop `optional` content in this order: second example → mid-session break → one quiz item → compress segment 3 to its core sentence + 1 check. Never drop the final retrieval or the wrap.
5. **If the digression revealed a gap** in a prerequisite, insert a 60-s "mini-segment" and log it for session 2.
6. **Nested digressions:** allow a stack depth of 2; at depth 3, park in the parking lot.

---

## 4. Teaching from a book

### 4.1 Comparison table

| # | Name | Link | Year | Mechanism | Evidence | Strengths | Weaknesses | Fit |
|---|---|---|---|---|---|---|---|---|
| 1 | Inspectional reading (Adler & Van Doren, *How to Read a Book*) | book (1940/1972) | 1972 | Skim structure first: title, TOC, intro, conclusion, chapter openings → "what is the book about as a whole" | Practitioner method | **Exactly a "first pass"** | Not empirical | Extract thesis from intro, conclusion and TOC first |
| 2 | SQ3R / PQ4R | Robinson 1946 (book) | 1946 | Survey → Question → Read → Recite → Review | Mixed evidence (not re-verified) | Builds questions-first habit | Dated | "Question" step = prediction hook; "Recite" = retrieval |
| 3 | Key-idea summary apps (Blinkist, Shortform, Headway) | [blinkist.com](https://www.blinkist.com) | 2012– | ~15-min "blinks": 8–12 key ideas, one per card | No learning studies (unverified) | Proven consumer format for books | Too many ideas, no retrieval; Shortform adds commentary | Use fewer ideas (3) + retrieval |
| 4 | Google Learn Your Way | [blog](https://research.google/blog/learn-your-way-reimagining-textbooks-with-generative-ai/) | 2025 | Personalized re-rendering of textbook + mind map + narrated slides + quizzes | +11 pp retention (§2) | Grounded in source text, multi-representation | Textbooks, not trade books | Personalize examples, keep source facts |
| 5 | NotebookLM (Audio/Video Overviews, learning guides) | [notebooklm.google](https://notebooklm.google) | 2023– | Source-grounded chat with inline citations; generated podcast/explainer video | Product; no learning RCTs (unverified) | Inline citation UX; "source-only" norm | Cloud, Google | Reference UX: cite spoken pages lightly; show source on tap |
| 6 | Book2Dial (ETH) | [ACL Findings 2024](https://aclanthology.org/2024.findings-acl.578) | 2024 | Generate teacher–student dialogues grounded in textbook sections; persona role-play best | Best method still hallucinates and repeats itself (verified) | Evidence that **textbook-grounded dialogue generation needs checks** | Dataset work, no learners | Validate scripts claim-by-claim |
| 7 | Ruffle & Riley script induction | [arXiv 2404.17460](https://arxiv.org/abs/2404.17460) | 2024 | Lesson text → editable tutoring script (questions + expectations) | §2 | Close to our pipeline | No learning gain over reading | Produce scripts as editable JSON |
| 8 | RAPTOR (recursive summarization tree) | [arXiv 2401.18059](https://arxiv.org/abs/2401.18059) | 2024 | Cluster chunks, summarize recursively, retrieve across levels | Gains on NarrativeQA/QuALITY (not re-verified) | Fits book "big idea + detail" levels | Indexing cost (many LLM calls) | Chapter → section summaries with page ranges = our outline source |
| 9 | GraphRAG (Microsoft) | [arXiv 2404.16130](https://arxiv.org/abs/2404.16130) | 2024 | Entity graph + community summaries for "global" questions | Better on global sensemaking (not re-verified) | Good for "main themes" | Expensive indexing for a free tier | Overkill; RAPTOR-lite is enough |
| 10 | Anthropic Contextual Retrieval | [anthropic.com](https://www.anthropic.com/news/contextual-retrieval) | 2024 | Prepend a chunk-specific context line before embedding + BM25 hybrid + rerank | −49% retrieval failures, −67% with rerank (vendor, not re-verified) | Simple; works with pgvector + tsvector | One LLM call per chunk at index time | Prepend "Book › Chapter › Section, p. X–Y" header (no LLM call needed) |
| 11 | ALCE citations benchmark | [arXiv 2305.14627](https://arxiv.org/abs/2305.14627) | 2023 | Measures whether generated citations support claims | Even strong models miss citation support often (not re-verified) | Defines citation recall/precision | QA, not tutoring | Per-sentence `source_pages` + check |
| 12 | FABLES (book-length summary faithfulness) | [arXiv 2404.01261](https://arxiv.org/abs/2404.01261) | 2024 | Claim-level human annotation of LLM book summaries | 3,158 claims / 26 books; **no LLM rater reliably detected unfaithful claims**, especially late-book (verified) | Shows where summaries fail | Expensive human eval | Keep claims short + page-cited so checks are local, not whole-book |
| 13 | BooookScore | [arXiv 2310.00785](https://arxiv.org/abs/2310.00785) | 2023–24 | Coherence errors in book summaries; hierarchical vs incremental | Hierarchical merging: more coherent, less detail (verified) | Choose summarization strategy | Coherence ≠ faithfulness | Hierarchical (chapter-first) for the outline |
| 14 | "Lost in the middle" | [arXiv 2307.03172](https://arxiv.org/abs/2307.03172) | 2023 | Models use start/end of long context better than middle | Robust (not re-verified) | Explains long-context failure | Newer models improved | Feed only the 3–6 retrieved chunks for the segment, not the whole book |
| 15 | FSRS (Free Spaced Repetition Scheduler) | [fsrs4anki](https://github.com/open-spaced-repetition/fsrs4anki); [Ye et al. KDD 2022](https://doi.org/10.1145/3534678.3539081); [srs-benchmark](https://github.com/open-spaced-repetition/srs-benchmark) | 2022– | DSR memory model (difficulty, stability, retrievability); schedules to target retention | Beats SM-2 on log-loss in the open benchmark (not re-verified this session) | Open, Python lib, default in Anki | Needs ratings; cold-start params | Cards from each session; voice-rated (again/hard/good/easy) |
| 16 | Card-writing rules (Wozniak; Matuschak) | [20 rules](https://www.supermemo.com/en/blog/twenty-rules-of-formulating-knowledge); [Matuschak](https://andymatuschak.org/prompts/) | 1999/2020 | Minimum information, one fact per card, cloze, avoid sets/lists, context cues | Practitioner consensus | Prevents bad LLM cards | — | Validator rules for generated cards |
| 17 | Shiksha copilot (MSR India) | [arXiv 2507.00456](https://arxiv.org/abs/2507.00456) | 2024–25 | Textbook → lesson plans (English + Kannada) for teachers | >1,000 teachers; time saved; **almost every Kannada plan needed edits** (verified via news + arXiv) | Indian context, textbook-to-plan | LLM Indian-language output quality weak | Keep plan in English internally; Hinglish only at speech surface |

### 4.2 Book pipeline (recommended)

```
INGEST (once per book; offline)
 1. Parse PDF/EPUB with page numbers (or EPUB location → "loc"). Keep chapter/section headings.
 2. Chunk 300–500 tokens on paragraph boundaries; each chunk = {book_id, chapter, section, page_start, page_end, text}.
 3. Contextual header: prepend "«Book» › Ch 3 «Title» › Section «X» (pp. 41–43)" before embedding (Contextual-Retrieval-lite).
 4. Embed → pgvector; also a tsvector for BM25-style hybrid search (Stiti already uses Postgres + pgvector).
 5. Hierarchical summaries (RAPTOR-lite / BooookScore-hierarchical): section → chapter → book.
    Every summary sentence keeps [p. X–Y] refs. Prioritize intro, conclusion, chapter openings/closings (inspectional reading).

FIRST-PASS SELECTION (per session; before the session starts)
 6. Extract a "book skeleton" JSON: thesis (1 sentence), candidate key ideas (5–8), named frameworks/models,
    best stories/examples, key terms, author's own summaries — all page-cited.
 7. Rank key ideas: score = centrality (in intro/conclusion? referenced across chapters?) + diagrammability
    + learner-goal relevance (from the warm-up / USER.md) + "foundation for others" (prereq of other ideas).
    Pick thesis + 3 ideas (4 max). Each idea: 1 book example + 1 personalized example (labelled origin=tutor) + 1 diagram type.
 8. Defer to later sessions: secondary frameworks, caveats/nuance, long case studies, statistics, critiques,
    chapter-by-chapter detail, the author's biography. Store as `next_sessions[]` with page refs.

PLAN + VERIFY
 9. Outline → per-segment scripts (see §6 JSON). Each narration sentence: origin ∈ {book, tutor_example, tutor_bridge}
    and, if book, source_pages.
10. Claim check: for each origin=book sentence, retrieve its cited chunks; a checker call labels
    {supported, partial, unsupported}. Unsupported → rewrite from chunk text or relabel as tutor's take.
    (FABLES shows whole-book judging is unreliable → keep checks local to cited chunks.)
11. Quote rule: direct quotes only if string-matched in the chunk text.

RUNTIME
12. Learner questions → hybrid retrieval over the book (top 4–6 chunks) + current segment context → answer with a light
    spoken cite ("author page 47 pe bolte hain…") and show the ref on the board's corner.
13. No book file available (learner just names a famous book)? Teach "about the book" from general knowledge, clearly
    flagged: "Mere paas book ka text nahi hai, toh yeh general summary hai — details galat ho sakte hain." No page cites.

FOLLOW-UP (spacing)
14. Generate 5–8 FSRS cards: 1 thesis, 1 per key idea (cue → response), 1–2 "why" cards, 1 application card,
    and one card per misconception actually shown in session. Validate: one fact per card, ≤ 25-word answer,
    no lists > 3, book page in the card's back.
15. Schedule with FSRS (target retention ~0.9). Due cards are spoken in Stiti's normal day ("2-min quick recall?").
16. Session 2 opens with a 3-min spaced retrieval of session-1 cards, then the next layer (deferred list).
```

### 4.3 Suggested multi-session arc for one book (design heuristic)

| Session | Content |
|---|---|
| 1 (first pass) | Thesis + 3 core ideas + 1 example each + apply to own life |
| 2 (+2–4 days) | Retrieval warm-up → 2–3 secondary frameworks → connect to session 1 |
| 3 (+1 week) | Caveats, critiques, edge cases, "where the author is weak" → learner's own action plan |
| Later | FSRS reviews only; optional deep-dive on chapters the learner flagged |

---

## 5. Friendly tone and motivation

### 5.1 Comparison table

| # | Name | Link | Year | Mechanism | Evidence | Strengths | Weaknesses | Fit |
|---|---|---|---|---|---|---|---|---|
| 1 | Self-Determination Theory | [Ryan & Deci 2000](https://doi.org/10.1037/0003-066X.55.1.68); [Niemiec & Ryan 2009](https://doi.org/10.1177/1477878509104318) | 2000/2009 | Autonomy, competence, relatedness → intrinsic motivation | Large literature (not re-verified) | Maps directly to friend + tutor | Broad theory | Offer choices (autonomy), achievable checks (competence), warm talk (relatedness) |
| 2 | Autonomy-support interventions meta | [Su & Reeve 2011](https://doi.org/10.1007/s10648-010-9142-7) | 2011 | Training instructors to be autonomy-supportive | Sizeable effects on teacher behavior (not re-verified) | Concrete behaviors: rationale, choice, acknowledge feelings | Teacher-side | Give rationale for activities ("ek quick recall, kyunki isse yaad rehta hai") |
| 3 | Growth-mindset interventions meta | [Sisk et al. 2018](https://doi.org/10.1177/0956797617739704) | 2018 | Teach that ability grows | Overall d≈0.08; larger for at-risk/low-SES (not re-verified) | Cheap | Tiny average effect | Don't preach mindset. Just use process feedback |
| 4 | National mindset study | [Yeager et al. 2019, Nature](https://doi.org/10.1038/s41586-019-1466-y) | 2019 | 1-hour online mindset intervention | ~0.10 GPA gain for lower achievers (not re-verified) | Large RCT | Small, context-dependent | Same: low-cost framing, not a centerpiece |
| 5 | Process vs person praise | [Mueller & Dweck 1998](https://doi.org/10.1037/0022-3514.75.1.33) | 1998 | Praise for intelligence lowers persistence after failure | Classic experiments (not re-verified; some replication debate) | Clear rule | Kids, lab | Praise strategy/effort specifically, never "smart" |
| 6 | Feedback to the self harms | [Kluger & DeNisi 1996](https://doi.org/10.1037/0033-2909.119.2.254) | 1996 | Self-focused feedback distracts from the task | §3 | — | — | Task-focused feedback |
| 7 | Teacher immediacy meta | [Witt, Wheeless & Allen 2004](https://doi.org/10.1080/0363775042000250994) | 2004 | Warm verbal/nonverbal closeness | Strong with affective learning; weaker with cognitive (not re-verified) | Supports warmth | Mostly self-report | Warmth helps motivation, not a substitute for checks |
| 8 | Humor in education review | [Banas et al. 2011](https://doi.org/10.1080/03634523.2010.496867) | 2011 | Topic-related humor | Related humor can aid attention/retention; unrelated or disparaging humor hurts (not re-verified) | Light, cheap | Can be distracting (coherence principle) | ≤1 light, on-topic joke per segment; never at the learner's expense |
| 9 | Rapport (Tickle-Degnen & Rosenthal; Sinha & Cassell) | [Psych Inquiry 1990](https://doi.org/10.1207/s15327965pli0104_1); Sinha & Cassell 2015 (ICMI, not re-verified) | 1990/2015 | Mutual attention, positivity, coordination; rapport in peer tutoring linked to learning | Correlational | Explains the "friend" value | Hard to engineer | Use the learner's name, refer back to their goals/life (memory), mirror register |
| 10 | "Rudeness and rapport" in peer tutoring | Ogan et al. 2012, ITS conf. (not re-verified) | 2012 | Friends' playful teasing correlated with learning in peer tutoring | Small study (unverified details) | Friend-style banter can be fine | Risky for an AI | Light, affectionate teasing **only if** the owner's profile says they like it; never about ability |
| 11 | Polite pedagogical agents | [Wang et al. 2008](https://doi.org/10.1016/j.ijhcs.2007.09.003) | 2008 | Polite vs direct agent feedback | Polite agent improved learning, esp. for learners preferring indirect help (not re-verified) | Supports soft phrasing | Small lab | "Ek baar aur try karein?" over "Wrong." |
| 12 | Conversational style (personalization) meta | [Ginns, Martin & Marsh 2013](https://doi.org/10.1007/s10648-013-9228-0) | 2013 | First/second-person conversational text vs formal | Positive, larger on transfer (not re-verified) | Directly supports casual tone | Text materials | Casual "tum/aap + we" register |
| 13 | Affect dynamics in learning | [D'Mello & Graesser 2012](https://doi.org/10.1016/j.learninstruc.2011.10.001); [D'Mello et al. 2014](https://doi.org/10.1016/j.learninstruc.2012.05.003) | 2012–14 | Confusion can be productive if resolved; boredom/frustration harmful | Lab + ITS studies (not re-verified) | Tells when to intervene | Detection by voice is noisy | Confusion → give time + hint; boredom → speed up/choice; frustration → direct help + break |
| 14 | Code-switching / translanguaging (India) | [NCERT 2006 English position paper](https://ncert.nic.in/pdf/nc-framework/nf2005-english.pdf); [Pallavi 2016, JIE](https://ejournals.ncert.gov.in/index.php/jie/article/view/2139); García & Li Wei 2014 (book) | 2006–2016 | Using learners' full repertoire (Hindi+English) to make meaning; NCERT: purism "must yield to a tolerance of code-switching" | **Mostly qualitative/small studies; no strong causal outcome evidence** (verified via search) | Matches learner's natural speech; lowers anxiety | Weak causal evidence; English-medium institutions less tolerant | Mirror the learner: Hinglish for talk, English for technical terms (as Indian classrooms do) |
| 15 | Hinglish/multilingual edtech (BELA, CodeVaani) | [BELA 2022](https://preview.aclanthology.org/author-url/2022.nlp4pi-1.17.pdf); [CodeVaani arXiv 2511.20654](https://arxiv.org/abs/2511.20654) | 2022/2025 | Chat/voice learning assistants accepting Hindi/Hinglish | CodeVaani: 54.7% of IIT-B students preferred voice for code Q&A; ASR misrecognition is a major issue (verified via search) | Indian learners, voice | Few learning outcomes | Expect ASR errors on technical terms; confirm key terms by echoing them |

### 5.2 Tone rules ("friend + tutor")

- **Relatedness:** greet by the preferred name (owner profile); remember their goal for this book; connect examples to their life (from USER.md / knowledge graph). One personal touch per segment at most, to stay coherent.
- **Autonomy:** offer 1 choice at the start ("story se shuru karein ya seedha diagram?") and at the mid-point ("2-min break, ya chalte rahein?"). Always honour "skip", "slow", "Hindi mein", "break". Give a one-line rationale for activities.
- **Competence:** start checks easy and get harder; say what improved ("pehle wala galat tha, ab bilkul sahi reasoning hai"). Normalize errors ("yeh mistake 90% log karte hain" only if true; otherwise "common confusion hai").
- **Process feedback:** praise the *move* ("tumne example se reason kiya — that's exactly the way"), never the person.
- **Humor:** light, on-topic, optional; never sarcasm about mistakes.
- **Energy and mood adaptation** (uses Stiti's existing mood/chronotype signals):
  - Low energy or late night → shorter session (15-min version: map + 2 ideas + quiz), more examples, fewer open questions, more MCQ.
  - High energy → more prediction/challenge questions, faster pace.
  - Frustration (sighs, "nahi samajh aa raha", repeated wrong) → stop Socratic, explain directly with a new representation, then an easy win check.
  - Boredom ("haan haan", short answers, "aage badho") → skip the examples they know, offer to jump ahead, raise the challenge.
- **Hinglish policy:** match the learner's code-mix ratio from their last few utterances; keep technical terms and book terms in English; Roman-script Hinglish in plan text only if the TTS handles it well (see the voice notes in the sibling research folder; TTS pronunciation of Romanized Hindi is a known risk, unverified for the chosen engine). Plans are generated in English and Hinglish-ified at the speech layer. Shiksha copilot showed LLM Indian-language generation needs heavy editing; Hinglish is easier than Kannada, but quality is unverified for gpt-oss/Qwen.

---

## 6. Prompt and pipeline design for a mid-size free LLM

### 6.1 Comparison table

| # | Name | Link | Year | Mechanism | Evidence | Strengths | Weaknesses | Fit |
|---|---|---|---|---|---|---|---|---|
| 1 | Plan-and-Solve prompting | [arXiv 2305.04091](https://arxiv.org/abs/2305.04091) | 2023 | Make a plan, then execute | Beats zero-shot CoT on reasoning (not re-verified) | Simple | Single-call | Outline-first stage |
| 2 | Skeleton-of-Thought | [arXiv 2307.15337](https://arxiv.org/abs/2307.15337) | 2023 | Skeleton outline, then expand points in parallel | Faster, often comparable quality (not re-verified) | Parallel per-segment calls → lower latency | Weak cross-point coherence | Per-segment calls in parallel with outline context |
| 3 | Re3 / DOC (long-form outline control) | [Re3 2210.06774](https://arxiv.org/abs/2210.06774); [DOC 2212.10077](https://arxiv.org/abs/2212.10077) | 2022–23 | Hierarchical outline + controller for long coherent text | Better coherence in human eval (not re-verified) | Proven for long-form | Story domain | Hierarchy: lesson → segment → chunk |
| 4 | Structured generation (Outlines, XGrammar, provider JSON schema) | [Outlines 2307.09702](https://arxiv.org/abs/2307.09702); [XGrammar 2411.15100](https://arxiv.org/abs/2411.15100) | 2023–24 | Constrain decoding to a grammar/JSON schema | Guarantees syntax; near-zero overhead in XGrammar (not re-verified) | Kills parse failures | Free cloud providers vary in `json_schema` support (unverified per provider) | Use `response_format: json_schema` where supported; otherwise JSON mode + Pydantic validate + repair |
| 5 | "Let Me Speak Freely?" (format restriction cost) | [arXiv 2408.02442](https://arxiv.org/abs/2408.02442) | 2024 | Compares JSON-mode vs NL-then-convert | JSON-mode hurts *reasoning*; NL-to-format ≈ natural language; classification can improve (verified via abstract) | Explains small-model degradation | Older models | **Think first, then emit JSON**: gpt-oss reasons in its separate reasoning channel (harmony format; unverified per provider). For Qwen, use a short `"plan_notes"` field *first* in the schema, or a 2-step NL→JSON |
| 6 | Self-Refine | [arXiv 2303.17651](https://arxiv.org/abs/2303.17651) | 2023 | Generate → self-feedback → revise | Gains across tasks (not re-verified) | No extra model | Small models' self-critique weak | Only targeted revise: validator error messages, not open "improve it" |
| 7 | Chain-of-Verification | [arXiv 2309.11495](https://arxiv.org/abs/2309.11495) | 2023 | Draft → plan verification questions → answer independently → revise | Reduced hallucination (not re-verified) | Fits claim checking | Extra calls | Book claim check (§4.2 step 10) |
| 8 | LLM-as-a-judge (MT-Bench) | [arXiv 2306.05685](https://arxiv.org/abs/2306.05685) | 2023 | Strong LLM grades outputs | ~80% agreement with humans; position/verbosity/self bias (not re-verified) | Cheap eval | Bias, esp. self-preference | Judge with a different/bigger model (gpt-oss-120b judges 20b output) |
| 9 | Prometheus 2 (open rubric judge) | [arXiv 2405.01535](https://arxiv.org/abs/2405.01535) | 2024 | Open model trained for rubric-based grading | Correlates well with GPT-4/human (not re-verified) | Rubric-native | 7B/8x7B, local RAM | Optional; a free cloud judge is easier |
| 10 | LearnLM pedagogy rubric + critics | [arXiv 2407.12687](https://arxiv.org/abs/2407.12687) | 2024 | 5 principles; critics: stay on topic, don't reveal answer, guide, active engagement, misconceptions, affect cues, positive tone, adapt level | §2 | Tutor-specific dimensions | Built for text chat | **Base of our rubric** |
| 11 | MRBench (Unifying AI Tutor Evaluation) | [NAACL 2025](https://aclanthology.org/2025.naacl-long.57); [arXiv 2412.09416](https://arxiv.org/abs/2412.09416); [code](https://github.com/kaushal0494/UnifyingAITutorEvaluation) | 2025 | 8 dimensions for mistake remediation: mistake identification, mistake location, revealing of the answer, providing guidance, actionability, coherence, tutor tone, human-likeness | 192 conversations / 1,596 responses, 7 LLM + human tutors (verified) | Precise turn-level criteria | Math mistakes only | Use its 8 dims for **check-feedback turns** |
| 12 | MathTutorBench | [arXiv 2502.18940](https://arxiv.org/abs/2502.18940) | 2025 | Expertise / student understanding / pedagogy; reward model scores teacher replies | Solving skill ≠ teaching skill (verified) | Shows trade-off | Math-only | Don't pick the model by MMLU; test pedagogy |
| 13 | BEA 2025 shared task (pedagogical ability) | [sig-edu.org](https://sig-edu.org/sharedtask/2025) (not re-verified) | 2025 | Shared task on MRBench dims | Many systems; automatic classifiers of tutor moves (not re-verified) | Ready-made classifiers | — | Optional automatic scoring |
| 14 | TutorEval / TutorChat | [arXiv 2402.11111](https://arxiv.org/abs/2402.11111) (not re-verified) | 2024 | Questions about long textbook chapters, judged by GPT-4 | (not re-verified) | **Long-context, textbook-grounded** tutoring eval | STEM textbooks | Template for "Q about the book" eval items |
| 15 | Pedagogical RL with simulated students | [arXiv 2505.15607](https://arxiv.org/abs/2505.15607) | 2025 | Simulated learner dialogues as the eval/training environment | §2 | Scalable eval | Simulators can be unrealistic | Persona-simulated learners for offline eval |
| 16 | gpt-oss model card | [OpenAI](https://openai.com/index/gpt-oss-model-card/) | 2025 | Open-weight MoE (20b/120b); harmony chat format; adjustable reasoning effort; tool use | Vendor (unverified here) | Free on several clouds; good instruction following | Hinglish quality unknown; provider-specific JSON support | Planner: 120b, reasoning "medium". Live turns: 20b, reasoning "low" for latency |

### 6.2 Pipeline (recommended)

```
PRE-SESSION (≈ 30–90 s, while warm-up chat happens or before session)
 A. Intake (from warm-up): topic/book, goal, prior knowledge (1–2 Qs), energy, time budget, language mix.
 B. OUTLINE call (planner model, e.g. gpt-oss-120b): → LessonOutline JSON (≤ 1k tokens):
    thesis, 3 key ideas {title, why_it_matters, diagram_type, source_pages}, hook question, misconceptions per idea,
    time budget per segment.
 C. SEGMENT calls (parallel, one per segment; outline + that idea's retrieved chunks only): → Segment JSON
    (narration sentences with cue ids, board cues, checks with expectations/misconceptions/hints).
 D. VALIDATE (code, no LLM): JSON schema; total minutes ≤ budget − slack; every cue_id referenced exists;
    sentence ≤ 25 words; ≤ 12 sentences per chunk; ≤ 5 words per board label; each segment has ≥ 1 check;
    each origin=book sentence has source_pages; MCQ distractors map to misconception ids.
 E. REPAIR: on failure, re-prompt that segment with the exact validator errors (max 2 tries) → else fall back to a
    simpler template segment (narration only + 1 recall check).
 F. CLAIM CHECK (book mode): per book sentence vs cited chunks (20b model, classification output).
 G. Pre-render: TTS for segment 1 first; others lazily.

LIVE (per learner turn; latency-critical)
 H. Turn classifier + responder (20b, low reasoning): input = system prompt + current segment JSON + stack + last 6 turns
    + retrieved chunks if question; output = TutorTurn JSON {intent, diagnosis, strategy, say[], board_ops[], next_action}.
 I. Orchestrator (code) owns time, stack, segment pointer — the LLM never tracks the clock.

POST-SESSION
 J. Session summary + misconceptions seen + FSRS cards (validated) + deferred topics → memory.
```

Small-model constraints (design heuristics, informed by rows 4–5 and LearnLM):
- One job per call. Keep outputs ≤ ~1.5k tokens. Pass the outline, not the whole book.
- Flat schemas, enums for types, explicit max lengths, ids as short strings (`s1`, `c3`).
- **Layout slots, not coordinates**, for board cues (`region: "left|center|right|top|bottom|corner"`, `row: 1–4`). A deterministic layout engine places things. Small models are poor at geometry.
- Diagram *types* from a fixed menu (flow, cycle, 2x2, timeline, tree, venn, compare_table, equation, sketch_label). The renderer has templates per type.
- Provide **one compact few-shot segment** in the prompt. Small models copy structure well.
- Temperature ~0.3–0.5 for plans; 0.6–0.7 for live chit-chat lines.
- Reasoning before JSON (gpt-oss reasoning channel, or a short first field `plan_notes`).
- The code, not the LLM, enforces timing, stack and repair loops.

### 6.3 Evaluation (tutor quality)

**Offline eval set (design heuristic):**
1. **Deterministic tests** (pytest, no network): schema validity, timing sum, cue integrity, sentence/label length, presence of checks, book citations present, no "samjha?" as a check text.
2. **Simulated learners** (LLM persona plays the learner): `confused_novice`, `confident_wrong` (holds a misconception), `bored_expert`, `interrupter` (asks a tangent every 2 min), `hinglish_casual`, `just_tell_me`. Run the live loop for a full session against each.
3. **LLM judge** (different/bigger model) with the rubric below, scoring 1–5 per dimension per session and per feedback turn. Human spot-check ~10% of sessions to calibrate.
4. **Real outcome metric** (the one that matters): delayed recall from the FSRS reviews at day 1–3 and the session's own final-quiz accuracy. Track per session; don't optimize engagement alone (Ruffle & Riley).

**Rubric (merge of LearnLM principles + critics and MRBench dimensions):**

| Dimension | Pass criterion |
|---|---|
| Active learning | A learner-generative check at least every ~6 min; learner speaks ≥ 25% of turns (heuristic) |
| Cognitive load | ≤ 1 new idea/chunk; chunk ≤ 90 s; board labels ≤ 5 words; no wall of text |
| No premature reveal (checks only) | Answer to a check not given before ≥ 1 learner attempt + ≤ 2 hints |
| Mistake identification & location (MRBench) | Feedback names what was wrong and where |
| Guidance & actionability (MRBench) | Feedback gives a concrete next step |
| Misconception handling | Detected misconception addressed with a contrast/example |
| Accuracy & grounding | Book claims supported by cited pages; non-book content labelled |
| Adaptivity | Responds to affect/energy and level signals; honours control requests |
| Curiosity & metacognition | Hook/prediction present; confidence or reflection prompt present |
| Tone & human-likeness (MRBench) | Warm, specific, process-focused; natural Hinglish; no generic praise |
| Digression recovery | After interruption: bridge + board re-anchor + correct resume point |
| Time adherence | Session ends 28–32 min with wrap + cards, or the agreed short version |

---

## 7. Deliverables

### 7.1 Recommended 30-minute session template

Planned content is about 26 min plus about 4 min of slack. Timings are targets; the orchestrator compresses `optional` items when slack is consumed.

| Clock | Block | Segment type | What happens | Board |
|---|---|---|---|---|
| 00:00–01:30 | Warm-up and contract | `warmup` | Greet by name. Mood/energy check (1 line). Goal ("is book se kya chahiye?"). 1 prior-knowledge question. Autonomy choice: story-first vs diagram-first; the 30-min vs 15-min version | Title + learner's goal in the corner |
| 01:30–02:30 | Hook | `hook` (predict) | One prediction/"guess karo" question tied to the thesis; no correction yet ("hold that thought") | Question mark sketch |
| 02:30–03:30 | Map (advance organizer) | `organizer` | Thesis in 1 sentence + 3 boxes = 3 key ideas + 2–3 key terms (pretraining) | 3-box map (persistent, top strip) |
| 03:30–09:00 | Idea 1 | `teach` (2 chunks ≤ 90 s) + `example` + `check` | Concrete example → idea → diagram drawn while speaking → check (MCQ with misconception distractors or explain-why) | Diagram 1; box 1 highlighted on map |
| 09:00–14:30 | Idea 2 | `teach` + `worked_example` + `check` | Starts with a 15-s recall of idea 1 (spacing within the session); worked example if procedural | Diagram 2; idea 1 shrinks to a thumbnail |
| 14:30–15:30 | Breather (optional) | `pulse` | Energy check + choice: 1-min break / continue / speed up. Hook answer revealed if it fits here | — |
| 15:30–21:00 | Idea 3 + connect | `teach` + `contrast` + `check` | Idea 3, then "how do 1-2-3 connect?" (learner draws the arrows verbally: generative) | Diagram 3 → connecting arrows on the map |
| 21:00–24:30 | Teach-back and apply | `explain_back` + `apply` | "Mujhe 1 minute mein samjhao jaise kisi dost ko." EMT grading → targeted fix. Then "tumhari life/kaam mein kahan use hoga?" | Learner's keywords written as they speak |
| 24:30–27:30 | Retrieval quiz | `quiz` (interleaved) | 3 no-notes questions: 1 recall, 1 discriminate ("kaunsa idea hai?"), 1 apply. Confidence 1–5 each; dwell on confident errors. Board map hidden during the quiz | Board cleared (no peeking), then revealed |
| 27:30–29:30 | Wrap | `summary` + `next` | Learner says the 3 ideas first, tutor completes. Hook revisited. Parking-lot items scheduled. "Next session: X" | Final 3-line summary |
| 29:30–30:00 | Close | `close` | FSRS cards confirmed ("6 quick cards bana diye, kal 2 min mein revise karenge"); warm sign-off | — |

**Segment length rules:** teaching segments 5–6 min. Narration chunks ≤ 60–90 s (≤ 12 sentences, ≤ 20–25 words each). An interaction at least every ~2 min (micro: board-label or 1-line question) and a real check at least every ~6 min.

**Short version (15 min, low energy):** warm-up 1 → map 1 → idea 1 (4) → idea 2 (4) → quiz 2 (2 Qs) → wrap 2 → idea 3 deferred.

### 7.2 Tutor rules

**DO**
1. Teach one idea at a time; ≤ 90 s of talk, then hand the turn over.
2. Draw while you speak; name each thing in the sentence that draws it; highlight what you're talking about.
3. Board = keywords + diagrams; speech = explanation. Never read the board aloud word for word.
4. Start with a concrete example, then the idea, then the label.
5. Check with real questions (predict, MCQ, why, apply, teach-back), never with "samjha?".
6. Before replying to a wrong or partial answer, silently decide: what's wrong → which strategy → why.
7. Hint ladder: "aur?" → hint → fill-in prompt → tell. Max 2 hints, then explain kindly.
8. Answer clarifying questions directly and briefly, then ask one follow-up that makes the learner think.
9. Cite the book lightly for book facts ("page 47"). Label your own examples as yours.
10. Praise the move, specifically ("example se reason kiya — perfect").
11. Mirror the learner's Hinglish; keep technical terms in English.
12. Offer choices (pace, order, break); obey "ruko / repeat / skip / slow / Hindi mein" instantly.
13. Recap and re-anchor after every digression; park big tangents.
14. End with learner-first recall of the key ideas and set up spaced review.

**DON'T**
1. Don't monologue or introduce > 1 new idea per chunk.
2. Don't give a check's answer before the learner tries.
3. Don't be Socratic about simple facts the learner asked for, or when they're frustrated or tired.
4. Don't invent page numbers, quotes, statistics or book content. If unsure: "book mein confirm nahi hai".
5. Don't use generic or person praise ("genius!"), sarcasm about errors, or long jokes.
6. Don't fill the board with sentences or decorations.
7. Don't let a tangent run > ~30 s without parking it.
8. Don't track time in your head. The orchestrator tells you the remaining budget.
9. Don't trust self-reports of understanding over check performance.
10. Don't lecture about growth mindset; show it through feedback.

### 7.3 Question-handling policy

See §3.4 (classification + Socratic gate + hint cap) and §3.5 (resume protocol). In one line: **control → obey; clarify → tell briefly + follow-up; ahead → preview + defer; tangent → ≤ 30 s or park; answer → EMT grade + hint ladder; challenge → separate "book says" from evidence; out-of-book → say so; affect → acknowledge + choice; then pop the stack with a bridge sentence + board re-highlight, and re-plan the time.**

### 7.4 Book pipeline

See §4.2: ingest with pages → contextual chunks → hierarchical page-cited summaries → skeleton (thesis + 5–8 candidate ideas) → pick 3 by centrality/diagrammability/goal → outline → segments → validator → local claim check → live RAG with spoken cites → FSRS cards + deferred list → session 2 opens with spaced retrieval.

### 7.5 JSON schema proposal (lesson plan)

Design goals: shallow, enum-heavy, short strings, ids for cross-references, layout slots instead of coordinates, AutoTutor-style checks. Generated in two stages (`LessonOutline`, then one `Segment` per call) and assembled by code into `LessonPlan`.

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "stiti/lesson_plan.v1",
  "title": "LessonPlan",
  "type": "object",
  "required": ["lesson_id", "topic", "source", "learner", "time_budget_min", "thesis", "segments", "wrap"],
  "properties": {
    "lesson_id": {"type": "string"},
    "topic": {"type": "string", "maxLength": 120},
    "source": {
      "type": "object",
      "required": ["kind"],
      "properties": {
        "kind": {"enum": ["book", "topic", "document"]},
        "book_id": {"type": "string"},
        "title": {"type": "string"},
        "author": {"type": "string"},
        "has_full_text": {"type": "boolean"}
      }
    },
    "learner": {
      "type": "object",
      "properties": {
        "goal": {"type": "string", "maxLength": 160},
        "prior_knowledge": {"enum": ["none", "some", "solid"]},
        "energy": {"enum": ["low", "normal", "high"]},
        "language_mix": {"enum": ["english", "light_hinglish", "heavy_hinglish"]},
        "interests": {"type": "array", "items": {"type": "string"}, "maxItems": 5}
      }
    },
    "time_budget_min": {"type": "integer", "minimum": 10, "maximum": 45},
    "slack_min": {"type": "integer", "default": 4},
    "thesis": {
      "type": "object",
      "required": ["text"],
      "properties": {
        "text": {"type": "string", "maxLength": 200},
        "source_pages": {"type": "array", "items": {"type": "string"}}
      }
    },
    "hook": {"$ref": "#/$defs/check"},
    "key_terms": {
      "type": "array", "maxItems": 4,
      "items": {"type": "object", "required": ["term", "plain"],
        "properties": {"term": {"type": "string", "maxLength": 30}, "plain": {"type": "string", "maxLength": 100}}}
    },
    "segments": {"type": "array", "minItems": 3, "maxItems": 7, "items": {"$ref": "#/$defs/segment"}},
    "wrap": {
      "type": "object",
      "required": ["summary_lines", "cards"],
      "properties": {
        "summary_lines": {"type": "array", "maxItems": 3, "items": {"type": "string", "maxLength": 80}},
        "cards": {"type": "array", "maxItems": 8, "items": {"$ref": "#/$defs/card"}},
        "next_sessions": {"type": "array", "items": {"type": "object",
          "properties": {"topic": {"type": "string"}, "source_pages": {"type": "array", "items": {"type": "string"}}}}}
      }
    }
  },
  "$defs": {
    "segment": {
      "type": "object",
      "required": ["id", "type", "title", "minutes", "chunks"],
      "properties": {
        "id": {"type": "string", "pattern": "^seg[0-9]+$"},
        "type": {"enum": ["warmup", "hook", "organizer", "teach", "worked_example", "contrast",
                          "pulse", "explain_back", "apply", "quiz", "summary", "close"]},
        "title": {"type": "string", "maxLength": 40},
        "minutes": {"type": "number", "minimum": 0.5, "maximum": 7},
        "optional": {"type": "boolean", "default": false},
        "plan_notes": {"type": "string", "maxLength": 300,
          "description": "Model writes its brief reasoning FIRST (small-model 'think then format')."},
        "diagram": {
          "type": "object",
          "properties": {
            "kind": {"enum": ["flow", "cycle", "2x2", "timeline", "tree", "venn", "compare_table",
                              "equation", "sketch_label", "map_boxes", "none"]},
            "caption": {"type": "string", "maxLength": 40}
          }
        },
        "chunks": {
          "type": "array", "minItems": 1, "maxItems": 4,
          "items": {
            "type": "object",
            "required": ["id", "sentences"],
            "properties": {
              "id": {"type": "string"},
              "sentences": {"type": "array", "minItems": 1, "maxItems": 12, "items": {"$ref": "#/$defs/sentence"}},
              "board": {"type": "array", "maxItems": 10, "items": {"$ref": "#/$defs/board_cue"}},
              "micro_prompt": {"type": "string", "maxLength": 120,
                "description": "Optional 1-line interaction after the chunk (board-label, quick why)."}
            }
          }
        },
        "checks": {"type": "array", "maxItems": 2, "items": {"$ref": "#/$defs/check"}},
        "misconceptions": {"type": "array", "maxItems": 3, "items": {"$ref": "#/$defs/misconception"}}
      }
    },
    "sentence": {
      "type": "object",
      "required": ["id", "text", "origin"],
      "properties": {
        "id": {"type": "string"},
        "text": {"type": "string", "maxLength": 160, "description": "≤ ~25 words, speakable, may be Hinglish"},
        "origin": {"enum": ["book", "tutor_example", "tutor_bridge", "general_knowledge"]},
        "source_pages": {"type": "array", "items": {"type": "string"}},
        "cue_ids": {"type": "array", "items": {"type": "string"},
          "description": "Board cues that START when this sentence starts (temporal contiguity)."},
        "emphasis": {"enum": ["none", "key_point", "signpost"], "default": "none"}
      }
    },
    "board_cue": {
      "type": "object",
      "required": ["id", "op"],
      "properties": {
        "id": {"type": "string"},
        "op": {"enum": ["title", "box", "circle", "arrow", "text", "list_item", "icon",
                        "highlight", "underline", "cross_out", "erase", "clear", "snapshot", "restore"]},
        "label": {"type": "string", "maxLength": 32, "description": "≤ 5 words"},
        "region": {"enum": ["top", "left", "center", "right", "bottom", "corner_parking", "corner_goal"]},
        "slot": {"type": "integer", "minimum": 1, "maximum": 6},
        "from": {"type": "string", "description": "cue id (arrows)"},
        "to": {"type": "string", "description": "cue id (arrows)"},
        "target": {"type": "string", "description": "cue id (highlight/underline/erase)"},
        "style": {"enum": ["normal", "accent", "muted", "warning"], "default": "normal"}
      }
    },
    "check": {
      "type": "object",
      "required": ["id", "kind", "prompt", "expectations"],
      "properties": {
        "id": {"type": "string"},
        "kind": {"enum": ["predict", "mcq", "recall", "explain_why", "explain_back", "apply",
                          "discriminate", "board_label", "confidence"]},
        "prompt": {"type": "string", "maxLength": 200},
        "options": {"type": "array", "maxItems": 3, "items": {"type": "object",
          "required": ["text", "correct"],
          "properties": {"text": {"type": "string", "maxLength": 80}, "correct": {"type": "boolean"},
                         "misconception_id": {"type": "string"}}}},
        "expectations": {"type": "array", "minItems": 1, "maxItems": 3, "items": {"type": "string", "maxLength": 100},
          "description": "Key points a good answer covers (AutoTutor EMT)."},
        "hints": {"type": "array", "maxItems": 2, "items": {"type": "string", "maxLength": 120}},
        "reveal": {"type": "string", "maxLength": 240, "description": "Explanation given after attempt(s)."},
        "on_correct": {"type": "string", "maxLength": 120},
        "seconds": {"type": "integer", "minimum": 10, "maximum": 150},
        "source_pages": {"type": "array", "items": {"type": "string"}}
      }
    },
    "misconception": {
      "type": "object",
      "required": ["id", "wrong_idea", "fix"],
      "properties": {
        "id": {"type": "string"},
        "wrong_idea": {"type": "string", "maxLength": 120},
        "signal": {"type": "string", "maxLength": 120, "description": "What a learner saying it sounds like"},
        "fix": {"type": "string", "maxLength": 200, "description": "Contrast example / counter-example"},
        "fix_cue": {"$ref": "#/$defs/board_cue"}
      }
    },
    "card": {
      "type": "object",
      "required": ["front", "back"],
      "properties": {
        "front": {"type": "string", "maxLength": 120},
        "back": {"type": "string", "maxLength": 160},
        "kind": {"enum": ["fact", "why", "apply", "misconception", "cloze"]},
        "source_pages": {"type": "array", "items": {"type": "string"}}
      }
    }
  }
}
```

**Live turn output** (per learner utterance, small and fast):

```json
{
  "intent": "control|clarify|ahead|tangent|answer|challenge|out_of_scope|affect|chitchat",
  "diagnosis": {"covered": ["e1"], "misconception_ids": ["m2"], "affect": "neutral|confused|frustrated|bored|tired"},
  "strategy": "direct_explain|hint|prompt|contrast_example|redraw|defer|park|praise_and_extend|offer_choice|obey",
  "say": ["≤ 3 short sentences"],
  "board_ops": [{"id": "x1", "op": "highlight", "target": "c4"}],
  "source_pages": ["47"],
  "next_action": "resume|ask_followup|next_hint|reveal|next_check|replan|end"
}
```

`diagnosis` and `strategy` come before `say` in key order on purpose. The Bridge and Tutor CoPilot decomposition, plus "Let Me Speak Freely"'s key-ordering finding, suggest the decision should be emitted before the words.

### 7.6 Short system prompt (live tutor)

```
You are Stiti, {name}'s friend who is also a great tutor. You are teaching "{topic}" ({source_line}) on a shared
whiteboard, by voice, in about {minutes} minutes. Speak like a warm, casual Indian friend; mirror {name}'s
Hinglish level ({language_mix}); keep technical and book terms in English.

How you teach:
- One idea at a time. Say at most 3 short sentences per turn when responding (the plan holds the longer narration).
- Draw while you talk: emit board_ops for what you name. Board gets keywords (≤5 words) and diagrams, never paragraphs.
- Check understanding with real questions (guess, choose, why, apply, teach-back). Never "samjha?" as a check.
- When they answer: decide what's right, what's wrong and why, then pick a strategy. Hints: "aur?" → hint → fill-in →
  explain. Max 2 hints, then explain kindly. Praise the thinking specifically, never "you're smart".
- Questions: obey control requests at once (repeat, slow, skip, break, Hindi). Answer clarifications directly and
  briefly, then ask one thinking follow-up. Things coming later: preview in one line. Big tangents: ≤30 seconds or park
  them in the board's parking corner. Then return with: "Achha, wapas — hum yahan the: …" and highlight that spot.
- Only use Socratic guiding when they can work it out in 1–2 steps, they haven't asked you to just tell, and they're
  not frustrated or tired.
- Facts about the book come only from SOURCES below; mention the page lightly. If it isn't there, say "book mein yeh
  nahi hai" and label anything else as your own example or general knowledge. Never invent quotes or page numbers.
- If they sound tired, bored or frustrated, acknowledge it and offer a choice.
- You don't track time; follow ORCHESTRATOR notes about remaining time and what to skip.

Output ONLY the TutorTurn JSON (diagnosis and strategy first, then say, board_ops, source_pages, next_action).

CURRENT SEGMENT: {segment_json}
LESSON STACK: {stack}
ORCHESTRATOR: {time_left, slack, notes}
SOURCES: {retrieved_chunks_with_pages}
```

(About 330 words. Keep the static part identical across turns so provider-side prompt caching can work where supported; unverified per provider.)

### 7.7 Planner prompt sketch (segment call)

```
Role: lesson designer. Write ONE segment of a spoken whiteboard lesson as JSON matching the Segment schema.
Inputs: OUTLINE (thesis, 3 ideas, this segment's idea), LEARNER (goal, level, interests, language_mix), SOURCES (pages).
Rules: write plan_notes first (≤3 lines). 1–3 chunks; ≤12 sentences per chunk; ≤25 words per sentence.
Start with a concrete example (prefer the learner's interests; mark origin="tutor_example").
Every sentence stating what the book says → origin="book" + source_pages from SOURCES only.
Board: ≤5 words per label, use regions/slots (no coordinates), one diagram of kind {diagram_kind};
attach each cue to the sentence that names it (cue_ids). End with 1 check: expectations (1–3), 2 hints,
MCQ distractors tied to misconception ids. No "samjha?" checks.
Example segment: {one compact few-shot}
```

---

## 8. Open questions and risks

1. **Hinglish generation quality** of gpt-oss-20b/Qwen-27B-class models is unmeasured here. Run a 20-utterance A/B with the owner before committing (unverified).
2. **Provider JSON-schema support** for free gpt-oss/Qwen endpoints varies (Groq/Cerebras/OpenRouter routing). Keep the Pydantic validate + repair path regardless (unverified per provider).
3. **Barge-in timing:** stopping TTS at a sentence boundary vs immediately is a UX trade-off. The voice notes cover VAD/barge-in. The pedagogy only needs the resume pointer.
4. **Evidence gaps:** there is no RCT of *voice + whiteboard* LLM tutoring for adults learning books. The template extrapolates from multimedia-lab studies, ITS research and text-chat LLM RCTs. Treat the minute-by-minute plan as a design heuristic to tune with the owner's own quiz and FSRS data.
5. **Kestin's effect** may not transfer: elite students, two weeks, no delayed retention test. Bastani shows the downside if guardrails slip. Re-check the "no reveal on checks" rule in eval after every prompt change.
