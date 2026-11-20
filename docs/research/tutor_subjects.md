# The coach on ANY subject, and on a syllabus (2026-11-20)

**Why:** "I am training it in a way where it should teach me ANYTHING, not any specific topic from compiler design"
and "if I give my entire syllabus it should be able to teach me in a day". The coach (D53, `tutor/coach.py`) had only
ever been tried on his compiler notes. This note is the evaluation on other subjects with the real free models, what
was wrong, and what changed. Decision: D54 in `docs/DECISIONS.md`.

## How it was tested
- **Inputs (9):** six topics — *photosynthesis* (biology), *causes of World War I* (history), *supply and demand*
  (economics), *integration by parts* (maths), *Python decorators* (programming), *English passive voice*
  (language) — and three syllabus files: a university **Operating Systems** syllabus (5 "UNIT I:" units, 4–5 bullet
  topics each, plus a "Text books:" list), a **Microbiology** syllabus ("Module 1 – …" headings, numbered topics),
  and a flat **Statistics revision list** (11 bullets, no units).
- **For each:** `concept_map` → `make_probes` → `concept_segments` for 2 concepts (first + middle), with the real
  router (Groq gpt-oss-120b / qwen3.8-27b / gpt-oss-20b, Cerebras, Cloudflare gpt-oss-120b, Z.ai… whatever was free
  at that minute; 4 s pause between calls). Scripts: `eval_subjects.py` (maps, probes, steps + metrics) and
  `grade_eval.py` (grading) in the session scratchpad.
- **Grading check:** for every probe and every open check, an LLM plays a student and writes one plausible RIGHT
  spoken answer (casual, own words) and one plausible WRONG one (a common misconception); for step checks it is shown
  what the tutor just said and drew. Then `tutor.grade.grade` decides. Same simulated answers before and after.

## What was wrong (before)
| # | Problem | Evidence |
|---|---|---|
| 1 | **A syllabus file taught nothing from its own list.** `book.py` found the 5 units, but all sat on one pseudo-page, so `sources_for` gave every unit the same 2 sentences — the *text-book citations* — and the bullet topics (no full stops) were dropped. The map came from unit names + "only what the SOURCES cover". | OS syllabus: missing *kernel vs user mode*, *interrupts and traps*, *system calls*, *TLB*, **page replacement (FIFO/LRU/Optimal)**, *RAID*; invented *Thrashing*, *File Protection*, *Inode*; Unit II got Unit III's *Synchronization Primitives*; points like "Explain safe state concept" put on the board. 10.3 s. |
| 2 | **Topic maps: one "unit" per concept.** | 28 of 43 units held a single concept (ibp 8/8, decorators 8/8, photosynthesis 6/7) — units drive the probe spread and "right answer ⇒ earlier concepts of that unit known". |
| 3 | **Expectations the grader can't use.** Alternatives as separate required items, 3 items for a one-sentence answer, rubric phrasing, words copied from the question, and one factually wrong. | "Name one metric…" → `['throughput','turnaround time','waiting time']` (all required); `['G3P','glyceraldehyde-3-phosphate']`; "Mentions printing before the call", "Answer contains 'have/has'…"; "…when the doer is unknown?" → `['never use by','unknown doer']`; Triple Entente → `['Germany','France','Britain']`. 19 of 21 probes had > 1 expected item. |
| 4 | **The grader:** numbers ignored ("ten shirts" = "Surplus quantity = 30 shirts"), spoken numbers not matched ("five" ≠ "5"), a comma list read as alternatives (any ONE country passed), echoing the question passed, one keyword of two passed. | right answers graded correct **23/44 (52 %)**; wrong answers rejected **35/44 (80 %)**. |
| 5 | **Steps:** a model packed 4–5 sentences into one `say` item (≤ 2 sentences broken); step 1 without a figure (2 of 14); fallback key points duplicating the model's (6 near-duplicates, e.g. "Derivative of u·v = u'v + uv'" + "Derivative of u·v equals u'v + uv'"); compiler-only figure examples in the prompt (DFA, phase pipeline); a made-up "what if Italy switches sides" as history's "worked example"; a Remember line that was a question; forced analogies in maths ("paint a wall while moving a ladder"). | — |
| 6 | Small: the ear was biased to *lexer, parser, compiler, grammar* for every subject; text cut mid-word ("…Gram-negative bac"); an edited syllabus kept its old cached map; the "known" quick check put the answer in the question ("<fact>. Why?"). | — |

## What changed
- **Syllabus = outline** (`book.py`): `is_outline()` (short file, ≥ 70 % short / list lines, not hard-wrapped
  prose), `unit_text()` (raw text under one heading, stops at "Text books / References / Course outcomes…"),
  `outline_topics()`; "Module N" and "Week N" are unit headings too. In `coach.concept_map` an outline unit gets
  `OUTLINE_PROMPT`: COURSE + UNIT + its LISTED TOPICS, "cover EVERY listed topic, in order, from accurate standard
  textbook knowledge" (2–8 concepts per unit). A flat list with no units is one call that groups the listed topics.
  Concepts get `general=True`; their steps get no fake SOURCES and `FACTS_GENERAL` ("never claim 'the book says'").
  The cache key includes the file's mtime + size.
- **Topic maps:** 2–5 units of 2–4 concepts, *this* topic's concepts (what it is and why it matters first, at most
  one prerequisite refresher), points as facts. A model that still gives one unit per concept is regrouped in threes;
  a lazy one-concept answer is asked once more.
- **Probes:** asked for n + 2, one per concept, one per unit first; expected = usually ONE point from that concept's
  facts, with the spoken paraphrases joined by " or ".
- **Steps:** the LLM fills named fields `points`, `figure` (required in step 1), `example`, instead of "one of the
  board items must have slot figure" (the old `board` list is still read). The board ops and slots are unchanged.
  Figures for any subject (process / cause→effect / cycle / timeline graph, comparison table, formula, key-term box);
  step 2 = a solved problem for methods, a real case or timeline for facts — no made-up "what if". Code: ≤ 2 spoken
  sentences per step whatever the model packs in, a missing step-1 figure borrowed from step 2, fuzzy de-dup of
  fallback points, word-boundary clipping, at most 6 example lines.
- **Expectations** (`clean_expectations`): rubric prefixes stripped, at most 2; when the question doesn't ask for
  several things ("two / both / list / steps / compare / and why…"), separate items become ONE "A or B" point — the
  free models list ways of saying one answer as separate items even when told not to (`['tuberculosis','TB']`).
- **Grader** (`grade.py`): spoken ↔ written numbers ("thirty" = 30, "eight point four" = 8.4, "x squared" = x^2,
  "+ / –" = plus / minus); a number in the expectation must be said; a comma list is one answer; words the question
  already says don't count; a light stemmer (saves / saving, manages / management); two key words need both, 2 of 3,
  and half of a long (≥ 4-word) expectation.

## Before → after (same 6 topics + OS syllabus; after also Microbiology + flat list)
| Metric | Before | After |
|---|---|---|
| OS syllabus: its 20 listed topic lines with their own concept | 6 major topics missing, 3 invented, 1 in the wrong unit | **20 of 20** (21 concepts), nothing outside the list |
| Syllabus map time (5 units) | 10.3 s (embedding junk) | 2.6–4.5 s quiet minute, 12–20 s when free tiers throttle |
| Units holding a single concept | 28 of 43 | 4 of 29 (one is a lazy 1-concept map, now asked again) |
| Probes with > 1 required expected item | 19 / 21 | 5 / 25 (then merged to "A or B" unless two things are asked) |
| Step 1 with a figure | 12 / 14 | 17 / 17 |
| Steps over 2 sentences | 1 / 14 | 0 / 17 (and cut in code) |
| Near-duplicate key points on a page | 6 | 1 |
| Checks with ≤ 1 expectation | 10 / 28 | 25 / 34 |
| Right spoken answers graded correct | 23 / 44 (52 %) | **33 / 52 (63 %)** |
| Wrong spoken answers NOT graded correct | 35 / 44 (80 %) | **44 / 52 (85 %)** |

Grader vs prompts, on the *after* items: old grader 32 / 52 right · 41 / 52 wrong rejected; old grader + merged
expectations 40 / 52 · 38 / 52 (lenient: praises more misconceptions); new grader + merged 33 / 52 · 44 / 52. The new
grader trades some "partial" on right-but-differently-worded answers (the tutor then asks "and…?" with a hint) for
fewer praised misconceptions, which is the worse error for a teacher.

## Examples (after)
- **OS syllabus, Unit IV:** *Contiguous Allocation and Fragmentation* · *Paging and Page Tables* · *Translation
  Lookaside Buffer* · *Segmentation* · *Virtual Memory and Page Replacement* ("FIFO replaces the oldest page…; LRU
  replaces the least recently used…"). Probe: "What is another name for the SCAN disk scheduling algorithm?" →
  `elevator algorithm`.
- **Microbiology:** Module 4 → *Bacterial growth curve* (lag / log / stationary), *Culture media types*,
  *Sterilization methods* ("Autoclave: 121 °C, 15 psi, 15 min"), *Disinfectants and antiseptics*.
- **Integration by parts:** starts at *What is Integration by Parts* (was: *Derivative definition, Power rule,
  Exponential derivative*); step 2 works ∫x sin x dx line by line; check "Write the final antiderivative of ∫x sin x
  dx" → `-x cos x + sin x`.
- **History:** step 2 of *July Crisis* is the real timeline (28 June assassination → Austria's demands → Russia backs
  Serbia → 28 July declaration), not a counterfactual.
- **Grading:** "The surplus is thirty shirts" ✓ / "ten shirts" ✗ for `30 shirts`; "Germany, France and Britain" ✗ for
  `Germany, Austria-Hungary, Italy`; "you put it after the function" ✗ for `above the function` ("function" is the
  question's word).

## Still weak (honest)
- **Bag-of-words grading** can't see order or negation: "The dog was chased the cat" passes `The cat was chased by the
  dog`; "x ln x plus x" vs `x ln x − x` only fails because of the plus/minus words. Paraphrases with no shared words
  ("people buy less" for `decreases`) stay partial. A local NLI/cross-encoder check is the next step if it fits 8 GB.
- **Facts depend on the free model of the minute.** One run put the Sarajevo assassination on "July 28" (it was 28
  June) and called Franz Ferdinand "Kaiser"; another run was right. Maps are cached per topic/file, so a bad map
  sticks until the file changes — a "re-plan this" command or a second-model fact check is worth adding.
- Example numbers in economics steps are invented (fine for a worked example, but not real data).
- The flat-list call may regroup topics out of the listed order inside a unit.
