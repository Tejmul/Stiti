# A real teaching agent — research summary and rebuild plan (2026-11-20)

**Why:** his first real lesson ("The Compiler Notebook.html", exam the next day) failed: *"It keeps on saying, saying,
saying. It's not interactive. It's not taking my doubts. It doesn't understand where I'm stuck. It doesn't give me time
to finish my question. It's hearing wrong and then answering me anything. It draws wherever it wants."*

**Research (15 sources, three angles, every source opened and checked):**
- [tutor_structure.md](tutor_structure.md): learning science and lesson structure. VanLehn 2011, Graesser 1995 /
  AutoTutor, Kalyuga 2003 (expertise reversal), Metcalfe & Kornell 2005 (study what's nearly known, triage under time),
  Scarlatos et al. LAK 2025 (LLM-tagged knowledge tracing); Bloom 1984 and Chi & Wylie 2014 as background.
- [tutor_doubts.md](tutor_doubts.md): doubts and dialogue. Bridge (NAACL 2024), MRBench (NAACL 2025), LearnLM (2024),
  Smart Turn v3, Whisper rare-word prompt biasing (SLT 2024); MathDial, Tutor CoPilot and SocraticLM as support.
- [tutor_systems.md](tutor_systems.md): open-source systems to study. OpenMAIC, DeepTutor, ChatTutor (design only, AGPL),
  OATutor, ChatGPT Study Mode prompt; plus a "whiteboard as notes" layout spec.
- [re_wispr_flow.md](re_wispr_flow.md): our own 2026-11-11 reverse-engineering of Wispr Flow (hearing).

## What was wrong, in one line each
| His words | Root cause (code) | Research says |
|---|---|---|
| "keeps on saying" | the player plays 5–8 cues per idea on a timer; a check only at the end | VanLehn: gains come from the learner acting at **every step**; ≤ 2 sentences, then his turn |
| "no proper structure" | always starts at the outline's idea 1; never asks his goal or what he knows | Kalyuga: re-teaching what he knows hurts; **diagnose first** (goal, deadline, 2–3 probes) |
| exam tomorrow | no deadline in the plan | Metcalfe & Kornell: triage — confirm known, teach nearly-known, skip hard-unknown if short of time |
| "doesn't understand where I'm stuck" | a doubt gets a generic 2–4 sentence answer | Bridge: decide **error type → strategy → intention** before replying; AutoTutor pump → hint → prompt → tell |
| "not taking my doubts" | "other" ignored; requests graded as quiz answers | taxonomy: HOLD / CONTROL / DOUBT / ANSWER / **STEER** / AFFECT; STEER beats ANSWER |
| "no time to finish" | acted on the first transcript piece | Smart Turn + a completeness check; wait longer when the sentence ends mid-thought |
| "hearing wrong" | lessons never used the cloud ear; lesson words not in the prompt | Wispr: big ASR + context every time; prompt biasing −24 % rare-word errors; confirm only when unsure |
| "draws wherever it wants" | the LLM picks places ("right_of", "below") | every readable board takes positions away from the LLM: **fixed note slots**, a deterministic layout |

## The rebuilt tutor (target design)
1. **Open with him, not the slides (60–90 s):** "What do you need: exam prep, or learn it properly? When's the exam?"
   Then 2–3 quick first-step probes over the file's units ("How would you turn `if` into a token?"). Each probe goes to
   one LLM call that tags concept + right / partly / wrong.
2. **Concept map with mastery:** the file's units → concepts (one LLM pass, cached per file). Each concept keeps
   BKT-lite mastery (OATutor's ~12 lines). The plan is a **queue ordered by gap × exam weight × time left**, re-planned
   after every answer, doubt or steer (DeepTutor mastery gate).
3. **Teach one concept as a loop, not a script:** say ≤ 2 sentences → ask him something (predict / first step / fill
   the gap) → judge locally (embeddings vs expected points) → pump / hint / prompt / tell → a fresh check →
   mastery update → next concept. Teaching style by mastery: worked example (new), problem (partial), one recall
   question (known).
4. **Doubts like Bridge:** one LLM call returns `stuck_at`, `error_type`, `strategy`, `intention`, then `say`, `board`
   and `check`. Answer, draw it on the doubts strip, ask one targeted check, then resume at the interrupted sentence
   (OpenMAIC playback engine).
5. **Board = his notes:** one page per concept with fixed slots (title + progress · key points 60 % · figure 40 % ·
   worked example · his doubts as stickies · "Remember"). The LLM returns `{slot, text}` only; a Python layout engine
   places, wraps and spills to a new page. Ids like `p3.point2`, so speech can highlight. "Save my notes" exports pages.
6. **Ears:** cloud large-v3 + lesson words (done); confirm when unsure ("lexer or lecture?"); show the live transcript;
   "no, I said…" within 2 s corrects instead of answering.

## Build order (each step small, tested, measured)
| # | Step | Status |
|---|---|---|
| 1 | Whole sentence, steer (skip / restart / switch / crash course), cloud ear + lesson words (D52) | **done**, `fix/tutor-listens` |
| 2 | Diagnose-first opening: goal + deadline + 2–3 probes → start point / exam mode | next |
| 3 | Concept map from his file + BKT-lite mastery + exam triage queue | |
| 4 | Concept loop: ≤ 2 sentences → his turn → pump / hint / prompt / tell → check → mastery | |
| 5 | Board as notes: slot layout engine, no coordinates from the LLM, notes export | |
| 6 | Bridge-style doubt call (stuck_at / error_type / strategy) + targeted check + resume | |
| 7 | Hearing: confirm-when-unsure, "no, I said…" correction window, WER on his voice | needs the recorder |

**Measure every step on a real lesson from his file:** his talk time vs hers (target ≥ 30 % his), sentences before his
turn (≤ 2), doubts answered vs ignored (0 ignored), board overlaps (0), and a 5-question quiz before and after.
