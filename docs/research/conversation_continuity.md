# Conversation continuity — why she drops the conversation, and the fix (2026-11-20)

Owner's complaint (all four confirmed): (1) she **stops listening** mid-conversation; (2) she **loses the thread**
("and that one?", "why?" treated as new topics); (3) she **doesn't keep it going** (answers and stops); (4) **lessons
don't continue** (can't pick up where he left off; after a doubt she doesn't return smoothly).

Evidence: read-only look at `~/.stiti/logs/` (app.log, mic_restarts, tutor/lesson logs) and read-only SELECTs on the
`stiti` brain (timestamps, counts, lengths, briefing section sizes — no conversation content copied anywhere).
Decision: D62 in `docs/DECISIONS.md`. Tests: `tests/conversation_continuity_eval.py` (100 checks).

## 1. Diagnosis — numbers

### 1a. Restarts (the mic watchdog) and what each one wiped
| Measure | Value |
|---|---|
| Voice process starts (= new sessions) in 10 days | **62** (27 on one day, 2026-11-18) |
| Mic-watchdog restarts ("still silent after reopening") in app.log | **17**, of them **12 in 55 min** on 2026-11-18 18:18–19:13 |
| Cadence of that loop | exactly every ~5 min = the rate limit (2 restarts / 10 min) |
| Episodes stored during those 12 sessions | **0** (nobody was talking; the mic itself was silent) |
| Conversations that continued 1–20 min after a restart (new session) | **9** session pairs |

Root causes:
- The watchdog sees 30 s of digital zeros (lid closed / input muted / headset away), reopens, still zeros → `os._exit(75)`.
  A **fresh process doesn't help** when the device itself is silent, so it looped forever at the rate limit.
- It never checked whether a conversation was going. A **default-mic switch** (AirPods connecting) counted as a
  reopen, and a Bluetooth mic sends zeros for a few seconds while it changes mode → a restart 6 s later could hit
  mid-conversation.
- **Every restart started a new session**, and RECENT, "what did I tell you" (D48), the said-ledger (D36), `pending`
  ("haan?"), `last_reply_text`, `info_at`, `topic_hint`, language state are all keyed on the session or live only in
  the Engine object → after any restart (watchdog **or** every code update) she had an empty head.

### 1b. Falling asleep mid-conversation
| Measure | Value |
|---|---|
| `AWAKE_TIMEOUT_S` | 30 s of silence (D47/D48), counted from the end of her reply |
| His next line came 30 s – 10 min after her reply (same session) | **15 of 166 = 9 %** → she had already slept, he had to say the wake word |
| Timeout sleeps (💤) / stop-word stops (🤫) in app.log | 7 / 38 |
| Stops that were real goodbyes ("bye", "okay bye", "bye Stiti", "shut up") | 37 of 38 |
| A 49-word sentence ended the session because "bye Stiti" appeared inside it | 1 |

Root cause: one fixed 30 s window whether he just said "set a timer" or is in the middle of a talk and thinking
about his answer; after that only the wake word worked, even 5 s later.

### 1c. How much context the briefing carried
| Measure | Value |
|---|---|
| LLM turns with ≥ 10 earlier episodes in the session (RECENT window full) | 73 |
| …of which RECENT actually had only **5 lines** (≈ 2 exchanges) | **59 (81 %)** |
| Fixed briefing parts (rules 549 + soul 349 + profile 234 + markers 105 + now 48 tok) | **≈ 1,285 tok** |
| Budget | 1,500 tok → ≈ 215 tok left for RECENT + memory; RECENT averaged **50 tok** |

Root cause: RECENT was trimmed to `RECENT_KEEP = 4` lines by the budget in most turns; facts were never trimmed,
so they outlived the conversation. "A few turns back" was simply not in front of the LLM.

### 1d. Follow-ups and "keep it going"
- **No thread state.** A follow-up reached recall as its bare words ("why?", "and that one?") → retrieval found
  nothing useful; the LLM had only the 2-exchange RECENT to guess "it".
- **"Tell me more" about a topic** (not about him) took the D36 MORE path: nothing personal left → "That's most of
  what I know so far" without the LLM — wrong for "explain B-trees" → "tell me more".
- **Every strategy had `ask=False`** (only NUDGE allowed a question); ACKNOWLEDGE said "No follow-up question",
  ANSWER "then stop"; `psych.enforce` / `StreamLint` drop every question. So she could never carry a topic.
  Balance: his earlier complaint was the *same questions again* (fixed in D58 via `asked_questions`), and the D25
  research found an interview after every statement fake — so the fix must be strictly rationed.
- A bare "and?" after an answer was QUIET → "Mm?".

## 2. Fixes (symptoms 1–3) — on the main branch

| # | Fix | Where |
|---|---|---|
| 1 | Watchdog restarts only when asleep **and** ≥ 2 min after the last turn; a process that never heard a sound doesn't restart again within 30 min of the last restart (logs it once); only DEAD-mic reopens count, not default-mic switches | `voice/loop.py` `mic_restart_ok`, `voice/duplex.py` `dead_reopens`, `heard_once` |
| 2 | A restart < 15 min after the last turn **resumes the same session**; the engine's state (said-ledger + anchor, thread, last reply / user line, pending yes, language, topic hint, her/his last lines) is saved after every turn to `~/.stiti/conversation.json` (0600, atomic) and restored. Only the app / `stiti voice` resume; text/web never | `brain/memory.resume_session`, `brain/convstate.py`, `Engine(resume=True)` |
| 3 | Awake window 60 s once 2+ turns or after her question (30 s otherwise); after a timeout, a 90 s **drowsy window**: a follow-up-shaped line ("and why…", "what about…", "tell me more") or her name anywhere carries on without the wake word (not after bye/stop, not an unclear transcript); a sleep phrase inside a long sentence counts only at its end | `voice/loop.py` `awake_window`, `carries_on`; `voice/wake.is_sleep` |
| 4 | **Thread tracker**: topic, personal?, last question/answer, names in play, turns. Follow-ups recall with topic + names + his words and get a `[THREAD]` block (after RECENT); commands in the middle don't end it | `brain/thread.py`, engine |
| 5 | Briefing budget 1,500 → 1,900 (`STITI_BRIEF_BUDGET`); **last three exchanges always kept**; budget order: examples → loops → docs → memories → earlier gist → facts beyond 3 → her older replies shortened → old exchanges; `[EARLIER IN THIS CONVERSATION]` gist of his older lines | `brain/compiler.py`, `memory.earlier_this_conversation`, `config.py` |
| 6 | "Tell me more / what else" about a **topic** continues it through the LLM (60 words, ALREADY SAID kept); about **him** stays the D36 honest path; "and?" right after an answer = go on | engine |
| 7 | **One beat**: ACKNOWLEDGE / ANSWER / BANTER only, only in a running thread or a story (≥ 15 words); a question only if none of her last 3 replies asked one (never two in a row, ≤ 1 in 4), else one building sentence; off when terse, annoyed (words / angry voice), after commands / QUIET / REPAIR / recap / fetch / tools / flows, when she was cut off, or under "don't ask questions"; YOU ALREADY ASKED widened to 5 | `brain/thread.beat`, `engine._with_beat` |

Latency (measured offline): thread + beat **0.005 ms/turn**; `compiler.build` with a full RECENT **0.6 ms**; one
extra indexed SELECT for the earlier gist; one extra embedding (~7 ms) only on follow-up turns; the state save is a
small JSON write after the reply. Voice-to-first-audio path unchanged otherwise. Groq free 8K TPM ÷ ~2,000-token
briefings ≈ 3.5 turns/min before the router falls back.

Tests run (one at a time): `conversation_continuity_eval` 100/100 (new), `mic_watchdog` 53/53, `turn` 80/80,
`no_repeat` 60/60, `recap` 40/40, `persona` 53/53, `examples` 35/35, `realtime` 77/77, `asked_once` 31/31,
`conversation` 12/12, `memory` 12/12, `honest_actions` 33/33. NOT verified on his mic / speakers.

Not changed (his call): bare "okay" / "ok" / "chalo" / "that's it" are in his stop-word list (`wake.STOP_ONLY`), so
a bare "okay" mid-conversation ends it — no case in the logs, left as is.

## 3. Lessons (symptom 4) — diagnosis + plan (paused by the owner; WIP on branch `wip/lesson-resume`)

**Why "continue my lesson" can't resume a coached lesson:**
1. The coach writes concepts while he works (`Coach._writer`), but the player saved the plan **once, at the start**
   (`Tutor._persist_start` → `store.save_lesson`) — an almost empty plan. The cursor kept counting against segments
   that were never saved.
2. `save_lesson` dedupes by (title, plan): every coached session on the same file starts with the same empty plan →
   they all **share one lesson row**.
3. "continue my lesson" → `launch(resume=True)` → `--resume` → `_coach_target` is False for `--resume` → the
   **classic** `make_lesson` with `store.last_unfinished()` → the empty/truncated plan → nothing to play (or the
   wrong place), while `_finish` promises "say continue my lesson and I'll pick up right here".
4. A re-run "teach <same file>" only partly helps: the remembered goal (one confirm line), `returning` skips probes,
   day mode skips concepts done today — but there is no "where in this concept was he", and concepts taught but not
   checked have no mastery update, so they are taught again.

**Post-doubt return:** a doubt cut mid-sentence → "Back to where we were." + the cut cue replays (fine). A doubt
asked **between** sentences, in a pause or at a section end (`resume_cue=False`) → no word at all: the next sentence
just starts, which feels abrupt.

**Fix plan (implemented as WIP on `wip/lesson-resume`, head 0a73fd5, `lesson_resume_eval` 20/20; the tutor
regression evals were NOT run):**
- `store.update_plan(lesson_id, lesson)`; coached lessons always get their own row (`save_lesson(fresh=True)`).
- `Tutor.on_save` hook: before every cursor save / finish the coach writes its resume point into
  `lesson.source.coach` (`at` = segment + cue + concept + title, `taught`, `seg_concept`, `goal`) and the whole plan
  is updated.
- `coach.resume_point(plan)` + `Coach(resume=…)`: the rest of the concept he was in comes back from the saved plan
  (ids prefixed `r`, rebuilt through the lesson sanitizer, the board redrawn up to the cue), no goal question / probes
  / plan speech — "Welcome back. We were in the middle of X, so I'll pick up right there." — taught concepts are
  skipped, the writer skips the prefilled concept and writes the rest.
- `tutor --resume` → `coach_resume()` for a coached lesson (closes the old session so the next "continue" doesn't
  go back to it); the classic resume refuses a coached plan with an honest line.
- Player: a doubt that doesn't replay the cut sentence ends with "Okay, carrying on with <part title>." (rotated;
  generic titles not read out); the BRIDGES for the replay case stay as they were.
- Still to do before merging it: run `tutor_coach_eval`, `tutor_teacher_eval`, `tutor_launch_eval`,
  `web_lessons_eval` one at a time; a resume button on the Lessons page; a one-line recap of the last thing said
  before picking up.
