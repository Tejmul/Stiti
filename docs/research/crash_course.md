# Research: "Teach me this in one night" — crash course from a book or a bare subject

Date: 2026-11-10. Scope: turn the one-lesson tutor (`src/stiti/tutor/`, D14/D15) into a whole-night crash course: pick and
order topics, skip what he knows, pace a long night, check progress, review at the end, and schedule next-day revision.
Constraints: free cloud LLMs only (Groq gpt-oss-120b / gpt-oss-20b / qwen3.8-27b: **30 RPM, 1K RPD, 8K TPM, 200K TPD each**
[22]), M2 8 GB, no local LLM. Code read: `planner.py` (1 outline call + 1 call per idea, sources ≤9,000 chars per call),
`book.py` (TOC → sections, `sources_for` = embedding-centroid extractive chunks), `db/migrations/006_tutor.sql` (`study_cards`).

## 1. Sources compared

| # | Source | Mechanism | Strengths | Weaknesses | Fits free + 8 GB + no local LLM? |
|---|---|---|---|---|---|
| 1 | Google LearnLM, *Towards an AI-Augmented Textbook* / **Learn Your Way** (2025) [1][2] | Textbook PDF → re-levelled, interest-personalised text → mind map, section quizzes, narrated slides, audio "teacher + student" lesson; quizzes route back to weak content | RCT n=60: +9% immediate, **78% vs 67% retention at 3–5 days**; multiple representations of the *same* source | Gemini 2.5 Pro reads the whole text (costly); one 40-min chapter, not a whole book | **Partly** — copy the shape (map + section quiz + route back), not the full-text regeneration |
| 2 | Khan Academy, Khanmigo prompt-engineering learnings [3][4] | Split big prompts into small targeted ones; re-run each prompt many times in evals; structured learner history | Long prompts made the model skip instructions; structured history gave +2.7–3.4% next-item correctness | Product internals not public | **Yes** — confirms Stiti's "code owns structure, small strict-JSON calls" |
| 3 | Khan Academy mastery + **Course Challenge** [5] | Skills Familiar→Proficient→Mastered; a course-wide challenge (pass ≥90) lets you skip ahead | Placement by test, not by self-report | Many items per skill; no time budget | **Yes** — pattern for diagnostic skip |
| 4 | OpenAI **Study mode** (Jul 2025) [6] | Custom system instructions on the normal model: Socratic questions, hints, scaffolded sections, knowledge checks, memory | Shows behaviour lives in instructions, not a special model | Single chat, no course plan, no scheduler | **Yes** (ideas only) |
| 5 | Anthropic Claude **Learning mode** (Apr 2025, all users Aug 2025) [7] | Socratic style toggle; in code, leaves TODOs for the learner | Learner does the thinking | No curriculum/time model | **Yes** (ideas only) |
| 6 | **NotebookLM** study guide, flashcards, quizzes, audio overviews (Sep 2025) [8] | Source-grounded generation with citations; "explain why I got it wrong" | Everything cites the user's sources | LLM reads all sources (Gemini long context) | **Partly** — keep citations, replace "read everything" with local extraction |
| 7 | Alpha School **2 Hour Learning / TimeBack** [9] | Adaptive apps find exact gaps; **90% mastery before advancing**; short focused academic block | Time-boxed + mastery-gated | Self-reported results, expensive, real day is ~3 h | **Yes** — mastery gate + time box idea |
| 8 | Duolingo **half-life regression** (Settles & Meeder 2016) [10] | Per-item recall half-life from features; pick items to review | −45% recall-prediction error, +12% daily engagement | Superseded by FSRS on Anki data [12] | **Yes**, but FSRS is better |
| 9 | **FSRS** / py-fsrs + Expertium benchmark [11][12] | DSR memory model (difficulty, stability, retrievability), power-law forgetting, 21 params | 350M reviews, 10K users: FSRS-6 beats SM-2 on 99.6% of collections; defaults are a reasonable start | Needs ~hundreds of reviews before optimising pays | **Yes** — 22.8 kB pure-Python wheel |
| 10 | **BKT** (Corbett & Anderson) + **pyBKT** (Badrinath et al. 2021, MIT) + threshold studies [13][14] | HMM per skill: P(init), P(learn), P(guess), P(slip); mastered at P ≥ 0.95 (best per-skill 0.90–0.97) | 4 numbers, explainable, works with 2–3 answers | Binary, no forgetting; DKT needs data Stiti lacks | **Yes** — 10 lines of code, no library needed |
| 11 | **Instructional Agents** (ASU, arXiv 2508.19611, 2025) [15] | Multi-agent ADDIE pipeline: objectives → syllabus → scripts → slides → assessments, aligned | Objective↔assessment alignment | Many LLM calls per course; teacher-facing | **Partly** — keep objective↔quiz alignment, not the agent swarm |
| 12 | **CourseBlueprint** (arXiv 2606.20608, 2026) [16] | LLM predicts prerequisite edges with confidence; code enforces a DAG by dropping the lowest-confidence edge in each cycle | Cheap, robust ordering; code validates the model | Edges are still LLM guesses | **Yes** — exactly the bare-subject recipe |
| 13 | Prerequisite graphs from lecture PDFs (arXiv 2606.10736) [17] | Extract topics + prerequisite edges from course material; drop ambiguous / bidirectional edges | Gap detection by walking prerequisites | GPT-4 over all material | **Partly** — use local term-reference edges instead |
| 14 | Dunlosky et al. 2013 [18] + Adesope et al. 2017 [19] | Review of 10 techniques; meta-analysis of 118 practice-test studies | Practice testing and distributed practice = **high utility**; rereading/highlighting/summarising = low; testing g≈0.6–0.7 | Lab-heavy; motivation matters | **Yes** — the night must be quiz-heavy, not read-heavy |
| 15 | Pan & Carpenter 2023, pretesting review [20] | Guessing before study (even wrongly) improves later memory if the answer is studied afterwards | Diagnostic doubles as a learning boost | Weak transfer to untested material | **Yes** — diagnostic = "guess first" |
| 16 | Brunmair & Richter 2019, interleaving meta-analysis [21] | Mix related categories in practice | g = 0.42; strongest for similar, confusable topics | Weaker for expository text and words | **Yes** — interleave in checkpoints, not in teaching |
| 17 | Cepeda et al. 2008, *temporal ridgeline* [23] | Optimal study gap grows with the retention interval (≈20–40% of a 1-week delay) | For "exam tomorrow", a short gap (same night + morning) is right | Gap ratio shrinks for long delays | **Yes** — night checkpoints + morning review |
| 18 | Biwer et al. 2023 (BJEP) [24]; Bradbury 2016 [25] | Systematic breaks (24 min/6 min, 12/3) vs self-regulated; critique of the "10–15-min attention span" | Pre-set breaks: less fatigue, more concentration, same output in less time; no hard attention cliff | Small samples; a 2025 preprint finds the opposite on fatigue | **Yes** — fixed, short breaks; interactivity matters more than a magic number |
| 19 | Yoo et al. 2007 (Nat. Neurosci.) + sleep-consolidation reviews [26] | One night without sleep cuts hippocampal encoding; sleep after learning consolidates | Strong case to end the night with sleep, not an all-nighter | — | **Yes** — Stiti caps the night and sends him to bed |
| 20 | Extractive summarisation: TextRank / LexRank / embedding centroid (+ MMR) [27] | Rank sentences by graph centrality or closeness to the document centroid | No LLM, fast, page-traceable | Misses implicit ideas; no ordering | **Yes** — Stiti already does centroid extraction per section |

Context already in D14: Bastani 2025 (answer-giving AI → −17% exam) and Kestin 2025 (scaffolded AI tutor ≥ active learning).

## 2. Recommended design: "one-night crash course"

**Principle:** the brain plans the course (local scoring, ordering, diagnostic, mastery, scheduling). The LLM is called once
for the course map and then only to fill each lesson's slots, one lesson ahead of playback. Teaching uses the existing 15-min
lesson unchanged. Most of the night is retrieval (pretest, checks, checkpoints, final quiz), not reading [18][19].

### 2.1 Time budget (default night = 3 h, he can say 2–4 h; Stiti refuses > 4 h and plans to end before his bedtime [26])
| Part | Minutes | What happens |
|---|---|---|
| Kick-off | 10–12 | 1-sentence goal ("exam tomorrow on X?"), course map on the board, **diagnostic** (≤10 items), plan confirmed by voice |
| Block (repeat) | ~40 | 3-min interleaved **checkpoint** → lesson → lesson → **6-min break** (≈5:1 work:break; Biwer's 24/6 [24]) |
| Long break | 15 | Replaces every 3rd short break (~every 2 h) |
| Final review | 15–20 | Brain dump → cumulative quiz → board of green/amber/red topics → cheat sheet → morning alarm → "go sleep" |

**Lessons per night ≈ ⌊(minutes − 30) / 20⌋, max 10:** 2 h → 4, 3 h → 7, 4 h → 10. Lesson 1 is always the **"whole subject
in 15 minutes" overview** (big-picture organiser and mind map of the full course [1]); lessons 2…N are the top topics, 3 ideas
each (3 h ≈ 6 topics, ~18 ideas). Stiti says up front what is covered (e.g. "~55% of the book's weight") and what is left for
night 2. A course spans nights; "continue my crash course" resumes.

### 2.2 Picking and ordering topics from a **book** (no LLM reads the book)
1. **Index once, locally, in the background during kick-off** (~1–3 min for 900 pages; cached in Postgres): TOC → section tree
   (`book.py`); choose units of ~10–40 pages (split big chapters, merge tiny sections). Per unit: page share; centroid embedding
   of ≤200 sampled sentences; top TF-IDF terms; definition sentences (`is called|is defined as|Definition|we say`);
   signals (summary / key-points boxes, exercise count, bold-term density); first-occurrence page of each key term.
2. **High-yield score per unit** (0–1, all local):
   `0.30·foundation` (how many later units use the terms it defines) + `0.25·centrality` (cosine of its centroid to the book
   centroid) + `0.20·goal match` (cosine to his goal / syllabus / past paper, if he gives one; else weight moves to foundation)
   + `0.15·size share` + `0.10·signals`, then multiplied by `(1 − P(known))` after the diagnostic. This is the 80/20 step:
   foundation + centrality find the few units the rest of the book depends on.
3. **Prerequisite edges**: unit A → B if B uses ≥2 terms first defined in A. Book order is the tie-breaker (authors already order
   by prerequisite). Take units greedily by score; pull in a prerequisite if it is unknown, otherwise give B a 1-minute bridge
   in its warm-up. Order by topological sort (Kahn), book order inside a level.
4. **One "course map" LLM call** (~6–8K tokens): input = level-≤2 TOC with page counts, the top ~25 units with scores and key
   terms, his goal. Output (strict JSON): ordered lessons → unit ids, a one-line "why it matters", and **one diagnostic MCQ per
   lesson** written from that unit's central sentences. Code validates ids, page refs and the DAG; anything invalid falls back to
   the local ranking.

**Bare subject (no book):** the same call returns 10–14 candidate topics with `importance 1–5`, prerequisite edges with
confidence, and a diagnostic MCQ for each. Code removes cycles by dropping the lowest-confidence edge [16], toposorts, and picks
by importance under the time budget. Every lesson is tagged `origin=general_knowledge` (no page citations).

### 2.3 Diagnostic and skip logic (BKT-lite, local)
- ≤10 items, ~5 min, framed as "guess first, no pressure". Pretesting helps even wrong guesses, as long as the topic is then
  taught [20]. Every item asks for confidence 1–5 (already in `grade.py`).
- Per topic: P(known) prior 0.3, slip 0.1, guess 0.25 for MCQ and 0.05 for free recall. A correct MCQ gives ≈0.61. If it was
  correct with confidence ≥4, ask one free-recall follow-up ("say it in one line", graded by keywords + embedder). Correct → ≈0.97.
- **Skip** if P ≥ 0.9 [13][14]. The topic gets 1 quick question in a checkpoint and its cards. **Compress** to 2 teach
  segments (~11 min) if 0.6 ≤ P < 0.9. **Full lesson** if P < 0.6. Freed minutes go to the next-ranked topic.
- "I already know X" by voice → the same 2-question check. Self-report alone never skips (Khan Course Challenge pattern [5]).
- **In-night mastery gate** (Alpha's 90% idea [9], softened for 2–3 items): lesson quiz score ≥ 0.8 → green. Otherwise amber:
  a 3-minute repair (re-ask + one re-explanation) goes into the next checkpoint, and the topic is first in the final review.

### 2.4 Checkpoints, breaks, fatigue
- **Checkpoint** (after each break, 3 min, ≤6 questions): cards due from py-fsrs with in-night `learning_steps=(10 min, 60 min)`.
  Cards from earlier lessons resurface, so the night spaces and interleaves itself [21][23]. Similar, confusable topics are mixed
  on purpose.
- **Break** (voice only, board dimmed): "stand up, water, look away from the screen". The next lesson is generated during the break.
- **Fatigue signals:** voice-emotion "tired/stressed", checkpoint accuracy down ≥30% from the first checkpoint, or answers slowing
  by 2× → offer a 15-min break, the 15-min low-energy lesson variant, or "save and stop". Stop is always one word away (resume exists).

### 2.5 Free-LLM budget (per night)
| Item | Calls | Tokens (est.) |
|---|---|---|
| Course map + diagnostic | 1 | 6–8K |
| Lesson × 7 (1 outline + 3 segments) | 28 | 7 × ~30–35K ≈ 230K (needs per-idea sources ≤1.5K tokens instead of 9,000 chars to every call) |
| Side questions (~10) | 10 | ~30K |
| Final review, cheat sheet, cards | 0 | 0 (built in code from saved lesson JSON) |
| **Night total** | **~40 calls** | **~270–300K tokens** = about half of Groq's 3 × 200K TPD; RPD is not the limit |

- **TPM 8K/model** → keep every call ≤6K tokens and rotate the 3 Groq models. Lesson k+1 is generated while lesson k plays,
  which gives 15+ min of slack against ~2–4 min of generation. Lesson 1 (overview) is generated during the diagnostic.
- **Quota guard:** before each lesson, `remaining_tokens_today ≥ 1.5 × lesson_cost` (tracked by the router), else
  Cloudflare / NVIDIA (P0 only) [D17]. If all are exhausted → **extractive mode** with no LLM: Stiti reads the unit's top
  central sentences aloud with page refs and builds cloze cards and recall checks in code. The night never dies.
- Lessons are saved, so resuming or re-teaching costs 0 calls. A 900-page book is never fully processed by an LLM; only ~7
  units' extracts (~10K tokens of source text) go out.

### 2.6 End of night (15–20 min, mostly code)
1. **Brain dump** (90 s): "tell me the whole subject". Graded against the lesson ideas by the embedder, missing ones listed.
2. **Cumulative quiz**: 8–10 questions, 1–2 per lesson, interleaved, amber topics first, confidence asked.
3. **Course-map board** with each topic green/amber/red. Skipped and uncovered topics shown faintly ("night 2").
4. **Cheat sheet** `~/.stiti/courses/<id>/cheatsheet.md`: lesson summaries, key terms, page refs (human-readable truth).
5. Set the morning-review alarm through Stiti's alarms, then tell him to sleep (sleep consolidates; an all-nighter hurts [26]).

### 2.7 Next-day revision (FSRS)
- Every check answered during the night goes through the scheduler. Rating map: wrong / revealed → `Again`; right after a hint
  or confidence ≤2 → `Hard`; right → `Good`; right, confidence 5, no hint → `Easy`.
- Default `Scheduler(desired_retention=0.9)`. Night cards then graduate to ~2–3-day intervals (FSRS-6 default initial
  stability for Good ≈ 2.3 days).
- **Morning session** 10–15 min, ≤30 cards, lowest retrievability first, voice-only possible.
- **Exam mode** (exam time known): in addition, 1–2 h before the exam, review every card with
  `get_card_retrievability(card, exam_at) < 0.9`, whatever the due date. Cramming goal = short gap [23]. After the exam,
  normal FSRS keeps the important cards.
- Optimise parameters only after ≥1,000 reviews (optimizer extra is heavy). Until then the defaults are fine [12].
- **Schema delta:** new table `tutor_courses` (id, title, source, goal, exam_at, plan jsonb with per-topic P(known)/status,
  night_minutes); `tutor_lessons.course_id, position`; `study_cards.step smallint` (py-fsrs needs it). Map Stiti
  `state 0 = new` to "not yet reviewed" (py-fsrs has no New state). Use UTC datetimes (py-fsrs is UTC-only).

## 3. py-fsrs

- **Package:** `fsrs` on PyPI (repo `open-spaced-repetition/py-fsrs`), **v6.3.2 (2026-08-09)**, **MIT**, Python ≥ 3.10.
  Wheel `fsrs-6.3.2-py3-none-any.whl` = **22.8 kB, pure Python, no required dependencies** [11]. The `fsrs[optimizer]`
  extra is lazy-loaded "heavy dependencies" (PyTorch-based); don't install it for now.
- **API sketch:**
```python
from datetime import datetime, timedelta, timezone
from fsrs import Scheduler, Card, Rating, State, ReviewLog

night = Scheduler(desired_retention=0.9, learning_steps=(timedelta(minutes=10), timedelta(minutes=60)),
                  relearning_steps=(timedelta(minutes=10),), maximum_interval=36500, enable_fuzzing=True)
card = Card()                                   # due now; fields: card_id, state, step, stability, difficulty, due, last_review
card, log = night.review_card(card, Rating.Good, review_datetime=datetime.now(timezone.utc), review_duration=None)
r = night.get_card_retrievability(card, current_datetime=exam_at)   # float 0..1
row = card.to_dict()                            # / Card.from_dict(row); also to_json/from_json on Card, Scheduler, ReviewLog
# Rating: Again=1 Hard=2 Good=3 Easy=4 · State: Learning=1 Review=2 Relearning=3
# Later: Optimizer(review_logs).compute_optimal_parameters() → Scheduler(params, retention); reschedule_card(card, logs)
```
- Alternatives: `fsrs-rs` (Rust, used by Anki), ts-fsrs. HLR [10] and SM-2 lose to FSRS on the benchmark [12].

## 4. Sources
1. LearnLM Team, *Towards an AI-Augmented Textbook*, arXiv 2509.13348 (2025) — https://arxiv.org/abs/2509.13348
2. Google Research blog, *Learn Your Way* (2025) — https://research.google/blog/learn-your-way-reimagining-textbooks-with-generative-ai/
3. Khan Academy, *7-step approach to prompt engineering for Khanmigo* — https://blog.khanacademy.org/khan-academys-7-step-approach-to-prompt-engineering-for-khanmigo
4. Khan Academy, *How Khan Academy is building a better AI tutor* — https://blog.khanacademy.org/?p=21314 ; GrowthBook on Khan A/B tests — https://blog.growthbook.io/what-i-learned-from-khan-academy-about-a-b-testing-ai/
5. Khan Academy mastery / Course Challenge — https://support.khanacademy.org/hc/en-us/articles/360030753412 ; https://districts.khanacademy.org/mastery-learning
6. OpenAI Study mode coverage (Jul 2025) — https://www.axios.com/2025/07/29/openai-chatgpt-study-mode ; https://www.searchenginejournal.com/openai-study-mode-brings-guided-learning-to-chatgpt/552423/
7. Anthropic, *Introducing Claude for Education* (learning mode) — https://www.anthropic.com/news/introducing-claude-for-education
8. Google, NotebookLM flashcards / quizzes / study features — https://blog.google/technology/google-labs/notebooklm-student-features/ ; https://9to5google.com/2025/09/08/notebooklm-flashcards-quizzes/
9. Alpha School 2 Hour Learning — https://www.cbsnews.com/news/alpha-school-ai-teaching-2-hour-a-day/ ; https://vanja.io/alpha-school/
10. Settles & Meeder, half-life regression (ACL 2016) — https://github.com/duolingo/halflife-regression ; https://blog.duolingo.com/how-we-learn-how-you-learn
11. py-fsrs — https://github.com/open-spaced-repetition/py-fsrs ; https://pypi.org/project/fsrs/ ; https://open-spaced-repetition.github.io/py-fsrs/fsrs.html
12. Expertium, *Benchmark of spaced repetition algorithms* — https://expertium.github.io/Benchmark.html ; Anki FAQ — https://docs.ankiweb.net/faqs/what-spaced-repetition-algorithm.md
13. Badrinath, Wang, Pardos, *pyBKT* (EDM 2021, MIT) — https://arxiv.org/abs/2105.00385
14. BKT mastery thresholds (EDM 2025 short paper) — https://educationaldatamining.org/edm2025/proceedings/2025.EDM.short-papers.4/2025.EDM.short-papers.4.pdf ; DKT limits (EDM 2021) — https://educationaldatamining.org/EDM2021/virtual/static/pdf/EDM21_paper_144.pdf
15. Yao et al., *Instructional Agents*, arXiv 2508.19611 (2025) — https://arxiv.org/abs/2508.19611
16. *CourseBlueprint*, arXiv 2606.20608 (2026) — https://arxiv.org/pdf/2606.20608
17. *Detecting Knowledge Gaps … Using Curriculum Prerequisite Graphs*, arXiv 2606.10736 — https://arxiv.org/pdf/2606.10736
18. Dunlosky et al. 2013, *Improving Students' Learning With Effective Learning Techniques* — https://www.psychologicalscience.org/news/releases/which-study-strategies-make-the-grade.html
19. Adesope, Trevisan & Sundararajan 2017, practice-test meta-analysis — https://www.learningscientists.org/blog/2017/2/9-1
20. Pan & Carpenter 2023, *Prequestioning and Pretesting Effects* (Educ. Psych. Review) — https://sc-pan.github.io/pdf/PR_2023.pdf
21. Brunmair & Richter 2019, interleaving meta-analysis — https://pubmed.ncbi.nlm.nih.gov/31556629/
22. Groq rate limits — https://console.groq.com/docs/rate-limits
23. Cepeda et al. 2008, *Spacing effects in learning: a temporal ridgeline* — https://www.evullab.org/pdf/CepedaVulRohrerWixtedPashler-PS-2008.pdf
24. Biwer et al. 2023, *Comparing 'Pomodoro' breaks and self-regulated breaks* (BJEP) — https://pubmed.ncbi.nlm.nih.gov/36859717/ ; 2025 counter-preprint — https://www.preprints.org/manuscript/202503.0845
25. Bradbury 2016, *Attention span during lectures* — https://pubmed.ncbi.nlm.nih.gov/28145268/
26. Yoo et al. 2007, *A deficit in the ability to form new human memories without sleep* — https://pubmed.ncbi.nlm.nih.gov/17293859/
27. Extractive summarisation (SciSummPip, centroid/TextRank/LexRank) — https://arxiv.org/pdf/2010.09190 ; https://arxiv.org/pdf/1804.08875
