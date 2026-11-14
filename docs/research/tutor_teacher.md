# The tutor as a teacher: one voice, never hears herself, answers doubts on the board

Research for D40 (2026-11-14). Builds on `research_notes/Whiteboard tutor/whiteboard_tech.md` §5 (cue sync,
barge-in, resume), `research_notes/Whiteboard tutor/tutoring_pedagogy.md` §3.4–3.5 (question policy, resuming
after a digression) and `docs/research/crash_course.md`.

## What went wrong in the real lesson (log 2026-11-11)

| Symptom in the log | Cause found |
|---|---|
| Three titles ("How a compiler works", "Lexical Analysis Basics", "Lexical Analysis: Code to Tokens") talking at once | Three lesson processes. D33 fixed the launch path, but the lock was still a plain pid file written *after* a check (check-then-write race). Two launches in the same second, or the voice app launching while a terminal `stiti teach` was still loading, could both pass. |
| `You (voice): Chalo today … let's go step by step. Before I explain anything, can't answer that one.` and `You (voice): Good question.` | Her own TTS came back through the mic (AEC residue, room echo). Whisper transcribed it and the player treated it as his input: it cut her off and replayed the cue (the duplicate "Chalo! Today …"), or answered it as a question. |
| `Two minutes, time's going to tell.`, `Nim nil to nara.`, `Kale, malawad …` (repeated, identical) | Whisper hallucinating on noise or echo. The repeated identical lines are the "looping" type of hallucination. |
| `I can't answer that one properly without my cloud brain.` (only in "How a compiler works") | That lesson was the built-in demo. `make_lesson()` returns `planner=None` for the demo and for `--resume`, and `_answer()` only asks the LLM when a planner exists, so it never tried the cloud. The process environment was fine: `.env` loads from the repo path, and the LLM lessons in the same log did answer. |
| `Shall we continue?` after nearly every input | `_answer()` always ended with "Shall we continue?" and then waited. Every echo or noise line that was classified as a question set it off. |

## Sources (14)

| # | Source | Mechanism | Strengths | Weaknesses | Fits free + M2 8 GB? |
|---|---|---|---|---|---|
| 1 | **LiveKit Agents turn handling** ([docs](https://docs.livekit.io/agents/logic/turns/tuning/), [resume example](https://cdn.jsdelivr.net/gh/livekit/agents@main/examples/voice_agents/resume_interrupted_agent.py)) | `min_interruption_duration` 0.5 s plus `min_interruption_words` (needs STT). It pauses first and resumes after `false_interruption_timeout` (2 s) if no transcript comes. | Two-stage barge-in: pause on sound, decide on words. A false alarm costs a short pause, not a restart. | The defaults assume a headset or a good AEC. No echo-text check. | Yes (logic only) |
| 2 | **Pipecat interruption strategies** ([docs](https://docs.pipecat.ai/server/utilities/interruption-strategies)) | `MinWordsInterruptionStrategy(min_words=3)`, checked only while the bot is speaking. | Simple, and it removes one-word noise and backchannels. | Blunt: a real "ruko" is one word, so commands need their own rule. | Yes |
| 3 | **Barański et al., "Investigation of Whisper ASR hallucinations induced by non-speech audio"**, ICASSP 2025 ([arXiv 2501.11378](https://arxiv.org/abs/2501.11378)) | Runs Whisper on non-speech audio. About 40 % of clips give text. Proposes a **Bag of Hallucinations** (most frequent phantom outputs) for post-filtering, plus VAD. Treats looping as its own hallucination type. | A cheap, effective post-filter. | The list is English and YouTube-flavoured ("thanks for watching"), so local additions are needed. | Yes (a set lookup) |
| 4 | **Koenecke et al., "Careless Whisper: speech-to-text hallucination harms"**, FAccT 2024 ([arXiv 2402.08021](https://arxiv.org/abs/2402.08021)) | About 1 % of transcripts contain whole invented phrases, more often with long pauses and non-vocal noise. | Shows that hallucinations are fluent sentences, not just gibberish, so a confidence filter alone is not enough. | Analysis only. | n/a |
| 5 | **OpenAI Whisper decoding thresholds** ([transcribe.py](https://github.com/openai/whisper/blob/main/whisper/transcribe.py)) | `no_speech_threshold` 0.6, `logprob_threshold` −1.0, `compression_ratio_threshold` 2.4. | Per-segment confidence is already in `stt.STTResult` (`no_speech_prob`, `avg_logprob`). | Echo of real speech is *confident*, so these thresholds don't catch it. | Yes (already used) |
| 6 | **faster-whisper `hallucination_silence_threshold`** ([repo](https://github.com/SYSTRAN/faster-whisper)) | Skips segments surrounded by long silence when a hallucination is suspected. | Targets the silence-induced type. | Needs word timestamps (extra cost); Stiti uses mlx-whisper. | Concept only |
| 7 | **WebRTC AEC3** (Google; used by Stiti's `voice/duplex.py`) | Adaptive echo cancellation with a far-end reference. | Removes most self-echo on the same device. | Leaves residue at high volume or with laptop speakers. It can't cancel audio from *other* processes (a second lesson, YouTube). | Yes (already in) |
| 8 | **Echo-text / self-transcript matching** (the "echo suppression by transcript" pattern in Vapi/Retell write-ups; Stiti's own `endpoint.in_echo_tail` and `goodbye_counts` from D24) | Compares what was heard with what the bot just said, plus a timing window after playback ended. | Catches confident echo that AEC and the confidence thresholds miss. Needs no models. | Needs fuzzy matching (Whisper paraphrases the echo). The window must be bounded so his real repeats still count. | Yes |
| 9 | **Silero VAD** with a stricter threshold while the bot speaks (Stiti `VAD_BAR_SPEAKING` 0.7; Hume/ElevenLabs-style playback-aware VAD) | Raises the speech bar during playback. | Cheap first gate. | Echo is real speech to the VAD, so it is not enough alone. | Yes (already in) |
| 10 | **Tutor CoPilot** (Wang et al., 2024, [arXiv 2410.03017](https://arxiv.org/abs/2410.03017)) | Decides the intent and strategy first, then writes the words. Expert tutors acknowledge, diagnose, then explain briefly. | The ANSWER_SCHEMA already orders intent → strategy → say. | Text chat, not voice. | Yes |
| 11 | **ChalkTalk** ([post](https://dev.to/danial_mo/chalktalk-a-whiteboard-tutor-that-draws-like-a-teacher-and-lets-you-raise-your-hand-4jmd)) | "Raise your hand" stops the narration; the answer is drawn on the board; the lesson resumes from the interrupted sentence. Real clip durations drive draw timing. | The exact interaction he wants. | Hand-raise is a button; voice barge-in is harder. | Yes |
| 12 | **OpenMAIC action engine** ([engine.ts](https://github.com/THU-MAIC/OpenMAIC/blob/main/lib/action/engine.ts)) | Sequential action list with a resume index; speech actions await audio end. | Resume by index, deterministic. | Draws happen between speech, not during it. | Yes (pattern) |
| 13 | **Khanmigo / LearnLM guidance** (Google "Towards responsible development of generative AI for education", 2024, [arXiv 2407.12687](https://arxiv.org/abs/2407.12687)) | Answer clarifying questions directly and briefly. Check understanding at natural boundaries. Avoid over-checking ("Does that make sense?" after every turn reads as patronising). | Grounds the "check-ins only at section ends" rule. | Chat-oriented. | Yes |
| 14 | **Human tutoring studies** (Graesser & Person 1994, "Question asking during tutoring"; Chi et al. 2001, "Learning from human tutoring"; Lepper's INSPIRE model) | Tutors acknowledge, answer the doubt with an example or a new representation, then bridge back ("so, where were we …"). When the learner is still confused, they simplify and use a concrete example rather than repeat. Check-ins are sparse and happen after an idea is finished. | Defines the doubt → answer → follow-up → bridge loop. | Human-to-human. | n/a |

Also reviewed, without changing the design: Moshi (full-duplex speech LM; too heavy and needs a local LLM, which is
ruled out), OpenAI Realtime `server_vad` (paid), Deepgram endpointing (paid), and the existing Stiti research
`docs/research/conversation_turn_taking.md` (two-stage duck → pause → verdict, already in `voice/endpoint.py`).

## Design chosen (smallest version that fits free + local + fast)

**1. Exactly one lesson, proven under races.** `tutor.lock` becomes a kernel `flock` held by the lesson process for
its whole life. The pid is still written for readers. The kernel releases the lock when the process dies, so there
are no stale locks. `tutor_active()` = the pid is alive **or** the flock is held. A second process (another
`stiti teach`, a voice launch in the same second, a voice launch while a terminal lesson is still loading) fails to
take it and exits before it makes a single sound. `launch()` is serialised with a thread lock. The file is never
unlinked (unlinking breaks flock exclusivity).

**2. Exactly one voice inside the lesson.** Every utterance goes through one `Tutor._play()`, which stops whatever is
playing first. The always-on loop says nothing at all while a lesson runs (its `say()` returns early unless an alarm
is ringing), not just nudges.

**3. She never treats her own voice as his** (`tutor/ears.py` `EchoGuard`, pure code, ~0.1 ms). It runs on every
voice transcript before the player sees it, and as a veto on the barge-in verdict, so echo never even stops her.
The rules, in order:
- Bag of Hallucinations (source 3) plus phantom lines seen in his logs: dropped.
- Looping: the same transcript again within 20 s, and not a command: dropped.
- Low confidence (`no_speech_prob` > 0.5 or `avg_logprob` < −1.0): only a lesson command survives (as before).
- **Echo window** = from the moment she starts a clip until 1.5 s after it ends. Inside it, a transcript whose words
  are ≥ 60 % found (fuzzy: plural/stem plus a 0.8 string ratio) in what she said in the last 15 s is her own voice:
  dropped. A single word she just said ("continue", "tokens") is dropped too.
- Inside the echo window, a non-command needs **≥ 3 real words** (source 2) or an explicit doubt opener ("ek doubt",
  "wait what", "how/why/what …" with ≥ 2 words). "ruko / wait / stop / bas" always pass instantly.
- "bye" inside the echo window, or when not confidently heard, does not end the lesson (17 of 41 logged "Bye."s were
  phantoms, D24).

**4. Doubts answered like a teacher** (sources 10, 11, 14; pedagogy §3.4–3.5):
- Stop. Acknowledge ("Good question —"; the wording varies and never repeats back to back). Turn to a fresh doubt
  board under the current page (the existing `begin_aside`), so the lesson board stays intact.
- `planner.answer()` runs in a background thread (strict JSON on `tutor_answer`). If it isn't back in 0.8 s, she says a
  short filler ("Let me draw it out."). "ruko" and "bas karo" still work while she waits.
- The answer is 2–4 spoken sentences, each drawing its ops in sync (word bookmark → proportional time).
- Follow-up: "still didn't get it" / "samajh nahi aaya" within 45 s → asks again with the previous answer attached
  and "simpler, with an everyday example".
- Bridge: "Back to where we were —" and the interrupted cue replays from its start. Its snapshot is rebased so the
  doubt board stays on the canvas.
- LLM down: one honest line ("I can't reach my thinking brain right now, so here's the short version from this
  lesson.") plus a local embedder lookup drawn on the doubt board, or park it. The honest line is said **once** per
  lesson; afterwards only "Parked it, we'll come back to it."
- Every lesson gets an answerer, demo and resumed lessons included (the root cause of "cloud brain").

**5. Teacher pacing.** Cues are already drawn in sync with their sentence; a short pause is added between ideas
(segment ends). "Shall we continue?" is gone. A check-in ("Any doubt so far? Just ask, or I'll carry on.") is said
only at the end of a teaching section, at most once every 2 minutes, or after he paused and then went quiet for a
long time.

Not chosen: an LLM to judge "is this echo?" (slow, against the rules). Energy-ratio gating against playback level
(calibration depends on his speakers and volume; kept as a future knob). A second VAD model (RAM).
Half-duplex muting while she speaks (it would kill natural interruption, his core ask).
