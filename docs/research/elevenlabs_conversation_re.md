# Research: reverse-engineering commercial conversation engines (ElevenLabs first)

Date: 2026-11-11. Why: Tejmul says Stiti jumps in during his thinking pauses, interrupts, mishears and asks random
follow-ups. Scope: commercial leaders only, studied from public docs, API specs, changelogs, blogs and their **open-source
SDKs** (design learned, no code copied). Open-source frameworks (LiveKit, Pipecat, TEN, Unmute, Bolna, VAP) are covered elsewhere.
Code read: ElevenLabs `github.com/elevenlabs/packages` @ `fd3c20d` (2026-11-10) and `github.com/elevenlabs/elevenlabs-python`.
Defaults come from the official OpenAPI spec `https://api.elevenlabs.io/openapi.json` (fetched 2026-11-11, called "OAS" below),
and `openai-python` `src/openai/types/realtime/realtime_audio_input_turn_detection.py` ("OAI-types"). Our code read:
`voice/loop.py`, `turn.py`, `duplex.py`, `speaker.py`, `wake.py`, `stt.py`, `brain/compiler.py`, `brain/psych.py`, `engine.py`.

## 0. Sources compared (mechanism · strength · weakness · fits free + M2 8 GB?)

| # | Source | Mechanism | Strength | Weakness | Fits? |
|---|---|---|---|---|---|
| 1 | ElevenLabs Agents, `turn_v3` turn model + Scribe RT ([blog](https://elevenlabs.io/blog/interaction-models), OAS `TurnConfig`) | Server reads the transcript ("text") plus VAD to give a turn probability. Eagerness sets the probability bar. Optional speculative LLM | Best-tuned product knobs (ignore terms, skip_turn, soft timeout) | Closed model, paid, cloud audio | Design only |
| 2 | ElevenLabs client SDK (`packages/client/src`) | Thin client: 25 ms PCM chunks up, base64 PCM down. Server decides interruptions. Client drops stale `event_id`s and fades the gain | Shows exactly what stays on the client | — | Yes (pattern) |
| 3 | OpenAI Realtime `server_vad` (OAI-types) | Silence timer: threshold 0.5, prefix 300 ms, silence 500 ms | Simple, predictable | Cuts people off during thinking pauses | Yes |
| 4 | OpenAI Realtime `semantic_vad` ([guide](https://developers.openai.com/api/docs/guides/realtime-vad.md)) | Classifier on the user's words gives P(done). Low P means wait up to a max timeout (8/4/2 s) | Wait time scales with confidence | Model is closed | Logic yes |
| 5 | OpenAI `conversation.item.truncate` (openai-python `conversation_item_truncate_event.py`) | Client reports `audio_end_ms`. Server deletes the transcript the user never heard | Memory matches what was actually heard | — | Yes |
| 6 | Deepgram Flux ([config](https://developers.deepgram.com/docs/flux/configuration), [agent](https://developers.deepgram.com/docs/flux/agent)) | Turn-aware STT with events StartOfTurn, EagerEndOfTurn, TurnResumed, EndOfTurn | Published thresholds; eager + cancel pattern | Paid cloud STT | Logic yes |
| 7 | Deepgram Flux-TTS interrupt ([doc](https://developers.deepgram.com/docs/flux-tts/interrupt-handling)) | Stop playback locally at once, then send `playback_offset`. Server returns `text_spoken` / `text_remaining` | Clean split of heard vs unheard text | — | Yes |
| 8 | Deepgram backchannel study ([blog](https://deepgram.com/blog/backchannels-vs-interruptions-voice-agents)) | Word-list policy: hold on "mhmm", yield on negatives, yield if speech continues | Energy-only barge-in fired on 45% of backchannels and noise | No timing numbers | Yes |
| 9 | Hume EVI (turn-detection / interruption / timeouts config) | `end_of_turn_silence_ms`, `min_interruption_ms`. Marketing says prosody-aware | Exposes a minimum interruption length | Official page is client-rendered, so numbers are unverified (†) | Logic yes |
| 10 | Gemini Live ([capabilities](https://aistudio.google.com/docs/live-api/capabilities)) | Server VAD (~800 ms silence). `interrupted` flag. Interrupted generation is dropped | Keeps only the content already sent | Few knobs | Logic yes |
| 11 | Sesame CSM ([research](https://www.sesame.com/research/crossing_the_uncanny_valley_of_voice)) | 1B–8B backbone over Mimi RVQ tokens, using about 2 min of interleaved audio+text context | Defines "voice presence": timing, pauses, interruptions, emphasis | Far too large for 8 GB | Ideas only |

## 1. ElevenLabs protocol and event model (from the SDK source)

**Transport.** WebSocket `wss://api.elevenlabs.io/v1/convai/conversation?agent_id=…&source=…&version=…`
(`client/src/utils/WebSocketConnection.ts:24-25,130`), or WebRTC through LiveKit `wss://livekit.rtc.elevenlabs.io`, fetching a token
from `/v1/convai/conversation/token` (`WebRTCConnection.ts:42,278`). Over WebRTC the audio is fixed at `pcm_48000` both ways (`:330-331`).
Client-side `output.interrupt()` does nothing there because the server stops the track (`:230-231`).

**Audio.** Formats are `pcm_8000|16000|22050|24000|44100|48000|ulaw_8000` (`types/schemas/agent.asyncapi.yaml` `AudioFormat`).
The default is `pcm_16000` both ways (OAS `ASRConversationalConfig`, `TTSConversationalConfig`). The web mic worklet sends **25 ms chunks**
(`rawAudioProcessor.generated.ts:60`). The Python SDK recommends **4000 samples = 250 ms** in and plays 1000-frame (62.5 ms) buffers out
(`conversational_ai/default_audio_interface.py:10-11`). The browser mic uses `echoCancellation`, `noiseSuppression` and `autoGainControl`, all
true (`platform/web/input.ts:20-23`). Each `audio` event carries `alignment` (`chars`, `char_start_times_ms`, `char_durations_ms`), so the
client knows which words were actually played (`AudioAlignmentData`).

**Client → server** (asyncapi `publish`): `{user_audio_chunk}` (base64), `pong{event_id}`, `user_message`, `user_activity`
(throttled to one per **1000 ms**, `BaseConversation.ts:50`, resets the silence timers), `contextual_update` (adds non-interrupting context, optional `context_id`
dedupe), `client_tool_result`, `mcp_tool_approval_result`, `feedback`, `multimodal_message`, and `conversation_initiation_client_data`
(overrides plus dynamic variables, sent first).

**Server → client** (`ClientEvent` enum, 27 types): `conversation_initiation_metadata` (ids and formats), `audio`, `user_transcript`
(final), `tentative_user_transcript` (partial), `agent_response`, `agent_chat_response_part` (streaming text), `agent_response_correction`
(`original_agent_response` and `corrected_agent_response`, i.e. the reply **truncated to what was heard after an interruption**, per the
[client-events doc](https://elevenlabs.io/docs/eleven-agents/customization/events/client-events.md)), `interruption{event_id}`, `vad_score` (0–1),
`internal_turn_probability` (0–1), `internal_tentative_agent_response`, `ping{event_id, ping_ms}`, `client_tool_call`,
`agent_tool_request/response`, `mcp_tool_call`, `agent_typing`, `context_usage`, `guardrail_triggered`, `asr_initiation_metadata`, and more.

**What runs where.** The *server* runs VAD, Scribe Realtime ASR (~150 ms), the turn model, the LLM (default `gemini-3.5-flash`, `temperature` 0.0,
backup LLM after `cascade_timeout_seconds` 4.0), TTS (default `eleven_v4_turbo`), the interruption decision, soft-timeout fillers and the transcript
correction (OAS `PromptAgentAPIModel-Input`). The *client* only captures, resamples, plays audio, answers pings and runs client tools. Interruption on the
client (`BaseConversation.ts:294`, `VoiceConversation.ts:121-145`, `platform/web/output.ts:264-289`): store `lastInterruptTimestamp = event_id`, then
**drop every later `audio` whose `event_id` is below it**, tell the worklet `interrupt`, and ramp the gain exponentially to 0.0001 over
`resetDuration = 2000 ms`. After that the worklet flushes its queue (`clearInterrupted`) and the volume is restored. The Python SDK does the
same with `_last_interrupt_id` plus `audio_interface.interrupt()`, which empties the output queue (`conversation.py:615,657-660`).

```
user mic ──25ms PCM──▶ server: VAD ─▶ Scribe ─▶ tentative_user_transcript … ─▶ turn_v3 P(turn) [internal_turn_probability]
                               │                            P ≥ bar(eagerness)?  (speculative_turn: LLM may start earlier)
                               │                                       ▼ yes
                               │         user_transcript ◀── final ── LLM stream (agent_chat_response_part)
                               │                                       ▼ starts TTS after "enough words and a comma"
client ◀── audio{event_id:N, alignment} ◀── TTS     (soft_timeout: say "Hhmmmm...yeah." if LLM is slow)
user talks over agent ─▶ VAD+ASR: is it in interruption_ignore_terms? ─no─▶ interruption{event_id:N}
client: drop audio < N, fade gain, flush ─────────────▶ server: agent_response_correction (heard text only) ─▶ history
silence ≥ turn_timeout (7 s) ─▶ agent re-engages · skip_turn tool ─▶ agent stays silent until the user speaks
```

The "enough words and a comma" rule comes from the turn-eagerness section of the [conversation-flow doc](https://elevenlabs.io/docs/eleven-agents/customization/conversation-flow.md).
The [blog](https://elevenlabs.io/blog/interaction-models) (updated 2026-10-27) says turn completion is "inferred from meaning, not a fixed silence threshold".
For example, a trailing "or is it still processing?" reads "as a handoff rather than a pause". Speculative turn-taking starts while Scribe is still transcribing.

## 2. Every turn-taking and interruption knob, with defaults

† Hume numbers come from a [release-note summary](https://releasebot.io/updates/hume/hume) and could not be confirmed on the official page (client-rendered).

| Concept | ElevenLabs (OAS default) | OpenAI Realtime (OAI-types) | Deepgram Flux | Hume EVI / Gemini Live | Stiti today |
|---|---|---|---|---|---|
| End-of-turn signal | `turn.mode` `turn` (or `silence`); `turn_model` `turn_v3` | `server_vad` (silence) / `semantic_vad` (words → P(done) → dynamic timeout) | Model over audio and transcript | Hume: silence (+ prosody claim); Gemini: VAD silence | Silero + Smart Turn (audio only) `loop.py:103-109` |
| Eagerness / bar | `turn_eagerness` `normal` (`patient`/`eager`): "higher values make agent wait for **higher turn probability**" | `eagerness` `auto`=`medium` (`low`/`high`) | `eot_threshold` **0.7** (0.5–1.0); conservative 0.85 | Gemini `end_of_speech_sensitivity` enum | 0.5 → 0.4 → 0.3, a bar that *drops* over the pause (`loop.py:106`) |
| Max silence, then force end | n/a (model-driven) | `silence_duration_ms` **500**; semantic max **8 s / 4 s / 2 s** (low/med/high) | `eot_timeout_ms` **5000** (500–60000); low-latency 6000, conservative 8000 | Hume `end_of_turn_silence_ms` 800† (500–3000); Gemini ≈**800 ms** (rec. 500–800) | `FALLBACK_SILENCE_MS` **1500** (`loop.py:37`) |
| Pre-roll | — | `prefix_padding_ms` **300** | — | Hume 300†; Gemini example 20 ("0 clips word starts") | ~320 ms ring (`loop.py:113`) |
| VAD threshold | `vad.background_voice_detection` false | `threshold` **0.5** | — | Hume `speech_detection_threshold` 0.5† | 0.5 start / 0.6 barge |
| Speculative reply | `speculative_turn` **false** ("LLM during silence before full turn confidence") | — | `eager_eot_threshold` unset (0.3–0.9, ≤ eot); low-latency **0.4**; `TurnResumed` = cancel | — | Speculative STT only, at 160 ms (`loop.py:38`) |
| Interrupt on/off | `interruption` in `client_events`; `tool_interruption_mode` `allow`; `disable_first_message_interruptions` false | `interrupt_response` true | `StartOfTurn` (has non-empty transcript) → *you* stop | Hume `min_interruption_ms` **800**† (50–2000); Gemini `interrupted=true` | 450 ms of VAD speech, no transcript check (`loop.py:35,90`) |
| Backchannel ignore | `interruption_ignore_terms` (exact, case-insensitive) + per-language presets (`merge_with_default_ignore_terms` false) | — | Hold on mhmm/uh-huh; yield on uh-uh/negatives; yield if speech continues | — | Hard stop, then resume if `wake.BACKCHANNEL` matches (`loop.py:257`) |
| Heard-only history | `agent_response_correction` | `conversation.item.truncate{audio_end_ms}` deletes the unheard transcript | `Interrupt{playback_offset}` → `text_spoken` | Gemini keeps only content already sent | **Full reply kept** (`engine.py:439`): gap |
| Re-engage on silence | `turn_timeout` **7 s** (1–30); `initial_wait_time` null; `silence_end_call_timeout` −1 | `idle_timeout_ms` (server_vad only, counted from the end of playback) | — | Hume inactivity 120 s (30–1800)† | None; sleeps after `AWAKE_TIMEOUT_S` 20 s (good) |
| Think pause | **`skip_turn`** tool; `wait_timeout_secs` **−1** (stay silent until the user speaks) | — | — | — | **none** |
| Spelling / numbers | `spelling_patience` `auto` | — | — | — | none |
| Slow-LLM filler | `soft_timeout_config.timeout_seconds` **−1** (off; doc recommends **3.0**, range 0.5–8.0); msg "Hhmmmm...yeah."; `max_soft_timeouts_per_generation` **1** (1–8); `randomize_fillers` false; LLM-generated filler uses ≤4 msgs / 1000 chars | — | — | — | "Hmm" at **0.9 s** (`speaker.py:28`) |
| Tool preamble | `pre_tool_speech` `auto` (**decided by recent tool latency**) / `force` / `off`; `tool_call_sound` auto; `response_timeout_secs` 20 | Prompt rule: "say one short line, then call the tool" | — | — | Fixed `ACKS` by tool kind (`speaker.py:16`) |
| Noise / 2nd voice | `noisy_environment_detection` false (Enterprise) | — | Rely on AEC; drop transcripts that echo the agent | — | AEC3 + NS (`duplex.py:35`) |
| Language | `language` `en`; `hinglish_mode` false; `language_detection.only_at_conversation_start` false (locks after 2 turns) | Prompt "pin language" | `flux-general-multi` + `language_hint` | — | Whisper `language=en` + Hinglish prompt (`stt.py:39`) |
| LLM fallback / session | `cascade_timeout_seconds` **4.0** (2–15); `max_duration_seconds` **600** (60–7200) | — | — | Hume max 1800 s† | Router chain |

## 3. Voice-agent prompting rules → a ready block for Stiti

These are distilled from the [ElevenLabs prompting guide](https://elevenlabs.io/docs/eleven-agents/best-practices/prompting-guide.md) and the OpenAI Realtime
prompting guide (`openai-cookbook/examples/Realtime_prompting_guide.ipynb`). ElevenLabs uses `#` sections (Personality, Environment, Tone, Goal, Guardrails, Tools,
Error handling), "under 3 sentences unless asked", tone defined once, "This step is important" on critical lines and the 1–2 key rules
repeated. OpenAI says bullets beat paragraphs, use 2–3 sentences per turn, add a **Variety** rule ("Do not repeat the same sentence twice"),
CAPITALIZE key rules, write sample phrases with "DO NOT ALWAYS USE THESE EXAMPLES", pin the language, say one short preamble before a tool, add
"Do not include any sound effects", and for **unclear audio**: "Only respond to clear audio… if you did not fully hear or understand, ask for clarification"
("unintelligible" worked better than "inaudible"). Put the block in `brain/psych.py` `CONTRACT` (rendered as `[OUTPUT CONTRACT]` by `compiler.py:95`).
It is about 150 tokens, so it fits the briefing budget even on a weak model.

```
[VOICE RULES — you are SPEAKING, not writing]
- Length: 1–2 short sentences by default; 3 max unless he asks for detail. One idea per turn.
- NO FOLLOW-UP QUESTIONS by default. Ask a question ONLY if you cannot act without the answer.
  Never end with "anything else?", "kya aur kuch?", "how does that sound?" or "want me to…?". This step is important.
- If his words look cut off or half-finished, reply with a tiny "haan?" or "go on" and nothing else.
- If he says "ek sec", "ruko", "let me think", "hold on": say NOTHING. He is thinking.
- His words come from speech recognition and MAY BE MISHEARD. If a word doesn't fit, use the most likely meaning
  from MEMORY and context. If it's truly unclear, ask ONE short check: "Sorry, X bola ya Y?" Never answer a guess as fact.
- Language: mirror his mix. Hinglish in → Romanized Hinglish out (no Devanagari). Don't switch language on your own.
- Variety: don't reuse the same opener or acknowledgement twice in a row. Don't always start with "Achha" or "Okay".
- Talk like a friend: contractions, plain words, no lists/markdown/emojis/sound effects. Write numbers and times as spoken.
- Before a slow action, say one short line ("dekhti hoon"), then do it. Don't promise a time ("one second").
- Never invent memories. NO FOLLOW-UP QUESTIONS unless needed (repeat of the key rule).
```

## 4. What Stiti should copy (prioritized, exact numbers, where it goes)

1. **Stop jumping in during thinking pauses (patient turn bar).** `loop.py:36-37,103-109`. Today the Smart Turn bar *drops* from 0.5 to 0.3 by
   1 s, and 1.5 s of silence always ends the turn. Nobody else is that aggressive: Flux defaults to 0.7 / 5000 ms, OpenAI medium waits up to 4 s, and
   Gemini/Hume use ~800 ms **plus** a model. Replace it with eagerness profiles (ElevenLabs: eagerness = how high P(turn) must be):
   `normal`: checks at 300/700/1200/2000 ms with bars 0.6/0.55/0.5/0.45, fallback **3000 ms**.
   `patient`: checks at 500/1000/2000/3000 ms with bars 0.75/0.7/0.6/0.5, fallback **5000 ms**.
   `eager`: today's values. Default to `normal`. Re-run the false-cut test from `turn.py`'s docstring (32/80 cut-offs) on 50 Hinglish turns and tune.
2. **Text veto, like ElevenLabs and OpenAI semantic VAD reading the words.** The speculative transcript is already ready at 160 ms (`loop.py:100`). If it
   ends in a continuation word (aur, matlab, ki, toh, ya, jo, and, so, but, because, like, um, uh, the, a, to) or a trailing "…", do **not** end
   on Smart Turn. Wait for the fallback. Check `spec.done()` so it never blocks. This is the cheapest fix for "matlab…" pauses
   (Smart Turn is audio-only and English-trained).
3. **Laya picks the eagerness per turn** (ElevenLabs changes eagerness per workflow node and recommends `patient` for collecting info). Use `patient` when
   Stiti just asked an open question, during onboarding/intake/WOOP (`brain/onboarding.py`, `intake.py`), when the mood is tired/sad, or after a hold
   phrase. Use `eager` for yes/no confirmations. Add it as one more Laya question in the existing batch, then pass it to `_segmenter`.
4. **`skip_turn` as a fast path** (`wake.py` new `is_hold()`, checked in `loop.run` before `_handle`). "ek sec / ruko / soch ke batata hoon /
   let me think / hold on / one sec" means no LLM call and **no speech** (`wait_timeout_secs` −1). Switch the next turn to `patient`, and freeze
   `AWAKE_TIMEOUT_S` until he speaks again (ElevenLabs pauses its end-call timer during the wait).
5. **Two-stage, transcript-checked barge-in** (`loop.py:86-95`, plus `Duplex.set_gain()` in `duplex.py`). Energy-only barge-in fires on 45% of
   backchannels (Deepgram), and backchannels are about 7× more common than real interruptions.
   (a) At **250 ms** of speech, *duck* playback to 30% instead of stopping.
   (b) Transcribe the overlap when VAD drops, or at 700 ms. If it matches the backchannel/ignore list (existing `BACKCHANNEL` + okay, mhm, uh-huh, theek
   hai, sahi), restore the gain and keep talking. No more stop-then-re-say.
   (c) Negatives (nahi, no, wait, ruko, stop) or any other words mean stop.
   (d) Force a stop at **900 ms** of continuous speech (Hume `min_interruption_ms` 800†).
   (e) Drop barge transcripts that are a substring of the sentence currently playing, which is residual echo (Deepgram preprocessing guide).
   (f) Replace the hard cut in `stop_playback()` with a **30 ms fade**. ElevenLabs uses a gain ramp, but 2 s is too long for local playback.
6. **Heard-only history** (`agent_response_correction` / `item.truncate`). `Speaker.run()` already returns the unspoken pieces (`speaker.py:83`).
   In `loop._handle` after `sp.run()`, compute `heard = reply minus left` and call a new `engine.correct_last_reply(heard)`. That updates
   `last_reply_text`, the stored reply episode and the recent-turns context with `heard + " —(cut off)"`. Then Stiti never thinks he heard what he didn't.
7. **Kill random follow-ups in code too, not just the prompt.** `psych.py:82` says "at most one question", which reads as permission. Swap in the §3 block.
   In `StreamLint` (`psych.py:72`), drop a *final* sentence that matches generic closers (`anything else|kuch aur|how does that sound|want me to`)
   unless Laya's intent says a slot is missing.
8. **Mishearing.**
   (a) ASR keywords, like ElevenLabs `asr.keywords`: add the top ~15 people/project names from the graph to the Whisper `initial_prompt`
   (`stt.py:15-39`, ≤ 40 tokens, refreshed hourly). This is the brain fixing the ears.
   (b) Unclear-audio fast path (OpenAI): if `avg_logprob < -0.8`, or `no_speech_prob` is 0.4–0.6 (just under today's 0.6/−1.2 gate at `stt.py:45`), or the
   text has fewer than 2 characters, skip the LLM and say one short Hinglish clarifier ("Sorry, phir se bolo?"). Rotate several phrasings for variety.
9. **Soft-timeout filler like ElevenLabs** (`speaker.py:28,101`, `FILLERS`). Raise `filler_after` from 0.9 s to **1.6 s**. ElevenLabs recommends 3.0 s for
   their stack; our target first-audio time is < 1 s, so 1.6 s is about p90. Keep max 1 per turn, shuffle the fillers, and remove time promises ("Ek sec"
   in `ACKS`; ElevenLabs advises "avoid time indicators"). Make the ACKS **latency-adaptive** (`pre_tool_speech: auto`): play one only if that tool's rolling
   p50 is above 700 ms.
10. **Speculative LLM, later (P2)** (`speculative_turn`, Flux `EagerEndOfTurn` 0.4 / `TurnResumed`). When Smart Turn is at least 0.5 but below the
    profile's bar and the speculative transcript is ready, run `engine.turn()` with deltas *buffered, not spoken*. If he resumes, cancel. If the
    turn is confirmed with the same transcript, play the buffer. Allow at most 1 speculative call per pause because of Groq's free RPM. This hides
    the extra wait from items 1–2.
11. **Telemetry** (ElevenLabs `vad_score` / `internal_turn_probability`). With `--debug`, log every check as `(silence_ms, p_turn, bar, veto, decision)`
    and every barge as `(ms, transcript, action)`. Target: ≤ 5% mid-thought cut-offs and ≤ 10% false stops on a 50-turn Hinglish session.
12. **Don't copy:** the 7 s `turn_timeout` re-engagement or `idle_timeout_ms` nudges. A buddy shouldn't poke him for being silent, so keep sleep-on-silence.
    Also skip the `noisy_environment_detection` second-voice detector for now (it's Enterprise-only at ElevenLabs).
    From Sesame, take only the principle: timing, pauses and emphasis matter as much as words. Kokoro has no conversational context, so vary the
    speed by mood instead (ElevenLabs: natural speech is 0.9–1.1×, [voice design doc](https://elevenlabs.io/docs/eleven-agents/customization/voice/best-practices/conversational-voice-design.md)).
