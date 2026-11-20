# Tutor answer grading — local grader + a free-LLM second opinion (D54)

**Problem (2026-11-20).** The tutor asks a question after every short step and grades his *spoken* answer locally
(`src/stiti/tutor/grade.py`: keyword overlap + the local embedder against the check's `expectations`). Speech-to-text
paraphrases and mis-hears ("the FA" for DFA, "see oh two" for CO2, "f equals m a" for F = ma, "grassy ass" for
gracias), so a right answer is marked "not quite" and he gets a hint he didn't need. That is the most frustrating
mistake a tutor can make (it punishes the right answer), so it is the one to fix first.

## Research (≥ 10 approaches)

| # | Work / system | Mechanism | Strengths | Weaknesses | Fits free + 8 GB M2? |
|---|---|---|---|---|---|
| 1 | AutoTutor, expectation–misconception tailored dialogue (Graesser et al., 2004–2005) | Each question has expectations + misconceptions; LSA similarity decides coverage; hint → prompt → assertion ladder | The pedagogy we already use (hints, then reveal) | LSA misses paraphrase; thresholds per domain | Yes (it is what `grade.py` copies) |
| 2 | SemEval-2013 Task 7, Student Response Analysis (Dzikovska et al., 2013) | Label a student answer vs reference answers: correct / partially correct / contradictory / irrelevant | Gives the verdict scheme (our correct / partial / wrong) and shows "contradictory" is the hard class | Typed answers, no speech noise | Labels only |
| 3 | Mohler, Bunescu & Mihalcea, ACL 2011 — short-answer grading with semantic similarity + dependency-graph alignment | Align student and reference answers; combine lexical + corpus similarity features | Beats bag-of-words on paraphrase | Needs parsing + training data per course | Partly (no training data here) |
| 4 | Sultan, Salazar & Sumner, NAACL 2016 — fast and easy short answer grading | Word alignment + sentence-embedding similarity + length ratio into a small regressor | Strong baseline with tiny features — close to our keywords + embedder | Still lexical; mis-heard words never align | Yes (we already run this kind of thing) |
| 5 | Burrows, Gurevych & Stein, IJAIED 2015 — "The eras and trends of ASAG" (survey) | Survey: concept mapping → IE patterns → corpus → ML → evaluation eras | Shows every lexical grader fails on unseen paraphrase without per-question data | Pre-LLM | Background |
| 6 | Sentence-BERT (Reimers & Gurevych, 2019) | Siamese sentence embeddings, cosine similarity | Fast, local, catches many paraphrases ("frozen water is lighter") | Similar topic ≠ right answer ("white blood cells" ≈ "red blood cells"); blind to sound-alikes | Yes — our embeddinggemma-300m plays this role |
| 7 | Sung, Dhamecha & Mukhi, AIED 2019 — transformer pre-training for short answer grading | Fine-tuned BERT cross-encoder on reference/answer pairs | Much better than similarity on entailment-like judgements | Needs labelled data per domain; fine-tuning | No (no labelled data per topic; fine-tuning against principles) |
| 8 | Zheng et al., 2023 — "Judging LLM-as-a-Judge" (MT-Bench) | Strong LLM grades answers against a rubric; position/verbosity biases measured | Zero-shot, any subject, explains its verdict | Leniency + verbosity bias; latency; needs a cloud call | Yes on free tiers, if bounded |
| 9 | Kortemeyer, 2023 — GPT-4 on automated short answer grading (SciEntsBank / Beetle) | Zero-shot LLM grading against reference answers | Close to specialised graders without any training | Cloud, cost on paid tiers, run-to-run variance | Free tiers: yes |
| 10 | Chamieh et al., BEA 2024 — LLMs in short answer scoring (zero-/few-shot) | Compare zero- and few-shot prompting of open LLMs on ASAG sets | Rubric-in-prompt matters more than model size; small open models are usable | Still below fine-tuned graders on some sets | Yes (prompt design lesson) |
| 11 | SpeechRater (Zechner et al., 2009) — automated scoring of spontaneous spoken responses | Score on ASR output with features robust to recognition errors | Spoken answers must be judged with ASR noise in mind | Scores fluency/proficiency, not content correctness | Lesson only: tell the judge it's ASR text |
| 12 | FrugalGPT (Chen, Zaharia & Zou, 2023) — LLM cascades | Cheap model first; call the expensive one only when the cheap answer is unreliable | Exactly our shape: local grader first, LLM only on doubtful cases | Needs a good "unsure" signal | Yes — "local said wrong/partial" is the signal |
| 13 | Double Metaphone (Philips, 2000) / phonetic matching | Map words to sound codes, match sound-alikes | Catches "passer" ≈ "parser" locally, no cloud | Fails on letter spelling ("see oh two"), multi-word slips ("grassy ass") | Yes, but narrow — a possible later local layer |

**What the research says for us.** Lexical + embedding graders (1, 3–6) are fast and local but structurally miss
mis-heard words and some paraphrases; fine-tuned cross-encoders (7) need labelled data we don't have; LLM judges
(8–10) are zero-shot and good at meaning, and the cascade idea (12) keeps their cost and latency to the doubtful
cases only. Speech systems (11) show the judge must be *told* the text is ASR output.

## Design (smallest version that fits: free, local-first, fast)

- **Local first, always.** `grade.grade()` runs the old local grader. Its verdict is final for: correct, I-don't-know,
  predict, an MCQ option he picked (letter / number / ordinal / option words), answers of < 3 words, and checks with
  no expectations. These never leave the Mac.
- **Second opinion only on doubt.** Local wrong/partial on ≥ 3 words → one strict-JSON call via
  `planner._call(..., route="tutor_answer", reasoning="low", temperature=0)` with a 3-field schema
  `{verdict: correct|partial|wrong, missing: [expectation numbers], reason}`. The system prompt says the answer came
  through speech recognition (sound-alikes, split words, spelled letters, numbers said as words) and to be *fair,
  not lenient*. MCQs that the picker couldn't match ("I'd say the passer") are judged with the options shown, the
  correct one marked.
- **Never blocks the lesson.** The call runs in a daemon thread; we wait on a `Future` for `grade.LLM_TIMEOUT_S`
  (2.0 s). Timeout / NoProvider / malformed reply → the local verdict stands (`llm_error` says why). A late reply is
  dropped.
- **Hint targeting.** The result adds `missing_text` (the expectations still missing) — partial answers now say
  *which* expectation is missing, ready for a targeted hint. (The hint ladder itself is unchanged in this step.)
- **Backward compatible.** Same signature + keys; new keyword args `llm=False, call=None, timeout_s=None`; new keys
  `source` (local|llm), `local_verdict`, `missing_text`, `llm_ms`, `reason`, `llm_error`.
- **Wiring.** Player `_run_check` and `_doubt_check`: `llm=grade.llm_for(self.planner)` — only a real cloud
  `Planner` (which `answerer()` creates only when a free key exists), so offline lessons and test fakes stay local.
  Coach probes: `llm=True, call=self.call` (its own injectable LLM call). The player logs
  `[grade] second opinion: partial → correct (412 ms) …`.
- **Switch.** `STITI_TUTOR_LLM_GRADE=off` → local only.
- **Local bug fixed on the way:** "the one that builds the tree" was read as "option one" (the `one` ordinal); it
  now describes an option and goes to the meaning check.

## Results

Set: **72 spoken answers to 31 questions** (programming, science, history, math, languages): 39 right (paraphrases,
speech-to-text slips, short answers, MCQ picks by letter / word / ordinal / description), 6 partial, 22 confidently
wrong, 5 "I don't know" variants. Labels = what a fair teacher would say. Measured 2026-11-20 on this Mac with the
real free models (`tests/tutor_grade_live.py --runs 3 --gap 3`; keys from `.env`, a `stiti_test*` database).

| | Accuracy | Right answers marked not-right | Wrong/partial answers marked right | Latency per answer |
|---|---|---|---|---|
| Local grader, before (main @ 101d895) | **73.6 %** (53/72) | 12 | 2 | median 7 ms, max ~25 ms |
| Local grader + "the one that…" fix | 75.0 % (54/72) | 11 | 2 | same |
| **Local + LLM second opinion** (3 runs) | **94.4 % / 91.7 % / 94.4 %** (mean 93.5 %) | **1–2** | 2 (both from the local grader) | median ~30 ms; when the LLM is asked: median 300–400 ms, p90 650–730 ms, max 1.6 s |

Confusion matrix, local only (rows = truth, columns = graded):

| truth \ graded | correct | partial | wrong | idk |
|---|---|---|---|---|
| correct (39) | 28 | 6 | 5 | 0 |
| partial (6) | 0 | 6 | 0 | 0 |
| wrong (22) | 2 | 5 | 15 | 0 |
| idk (5) | 0 | 0 | 0 | 5 |

Confusion matrix, local + LLM (run 1 = run 3):

| truth \ graded | correct | partial | wrong | idk |
|---|---|---|---|---|
| correct (39) | **38** | 0 | 1 | 0 |
| partial (6) | 0 | 6 | 0 | 0 |
| wrong (22) | 2 | 1 | **19** | 0 |
| idk (5) | 0 | 0 | 0 | 5 |

- The LLM was asked on **32 of 72** answers (the rest were final locally) and changed 12–14 verdicts. It never turned
  a wrong answer into "correct"; it fixed both directions: mis-heard right answers up ("see oh two", "f equals m a",
  "I'd say the passer", "it's grassy ass", "big o of one"), and confident wrong answers down from "partial"
  ("it can go to many states at the same time", "we use it before plural nouns", "I think it is just x").
- Models that answered (route `tutor_answer`): Groq `qwen/qwen3.8-27b` and `openai/gpt-oss-20b` (fallback after the
  first's per-minute limit), rarely `gpt-oss-120b` / Cloudflare.
- **Burst test** (33 calls back to back, no gap — much harsher than a lesson, where he answers every 30 s or so):
  accuracy 90–94 %, LLM median 450–1,150 ms; in the worst run 6 calls hit the 2 s deadline and fell back to the
  local verdict exactly as designed (that run: 91.7 %). Spaced 3–4 s apart: 0 timeouts in 5 runs.
- Remaining misses: "the white blood cells" and "because zero means nothing" (local false "correct" — the LLM is
  never asked), "Abraham Lincoln" (2 words, under the gate), "it's sha" for *chat* (the LLM won't accept it — fair),
  and once "the a l u and the control you need" judged partial.
- Temperature 0 + "fair, not lenient" wording: with temperature 0.4 and a looser "on the right track = partial", one
  run turned "because it is cold" (ice floats) into partial; after the change it did not recur in 5 runs.

## Tests

- `tests/tutor_grade_eval.py` (offline, fake LLM; in `run_all.sh`): local accuracy floor on the set, LLM upgrade of a
  mis-heard answer, partial → which expectation is missing, MCQ said in words, the cases that must NOT call the LLM,
  timeout / NoProvider / malformed-reply fallbacks, the env switch, and the wiring through a real lesson check, a
  doubt check and the coach's probes.
- `tests/tutor_grade_live.py` (not in `run_all`; calls the real free models): prints the confusion matrices,
  misses, which models answered and latency. `--local`, `--runs N`, `--gap S` (space the calls like a real lesson).
- Labelled set: `tests/fixtures/tutor_grade_cases.json`.

## Not yet / next

- Local false "correct" on topic-similar wrong answers ("the white blood cells" for red blood cells, "because zero
  means nothing" sharing the word "zero") — the second opinion never sees them because local said correct. Options:
  a negation/antonym guard in the keyword scorer, or asking the LLM on low-margin local corrects.
- 2-word confident wrong answers ("Abraham Lincoln") are graded partial by the embedder (names are close in vector
  space) and are below the 3-word LLM gate.
- Use `missing_text` to pick or write a hint that targets the missing expectation.
- Measure on his real voice transcripts (this set is hand-written in the shape STT produces).
