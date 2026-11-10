# Live black-box RE: how the ElevenLabs demo agent actually takes turns (measured 2026-11-11)

Companion to `elevenlabs_conversation_re.md` (SDK/docs study) and `conversation_turn_taking.md`. That doc covers what ElevenLabs
*says* it does. This one covers what their public demo agent *did* when it heard our test audio, compared with Stiti's
`src/stiti/voice/endpoint.py`. No Stiti code was changed.

## 1. Method
- **Target:** the public "Voice → Web call" demo on `elevenlabs.io/conversational-ai`. No login. I clicked their consent screen
  ("I agree": 18+, AI, recorded). The audio was synthetic speech (macOS `say`, voice Samantha), so no personal data was sent.
  There were 6 calls of 30–75 s each: 2 setup failures, 1 smoke test, then 3 scenario sessions.
- **Browser:** headless Chromium 1254 via `playwright-core`. Fake-media flags were on, plus `--remote-debugging-port`, so **rea**
  could attach (`list_browser_targets`, `inspect_web_page`, `analyze_web_bundle`).
- **Audio in:** at first I overrode `getUserMedia`, but the stream reached the SDK as silence. What worked was patching
  `AudioContext.createMediaStreamSource` inside the SDK's own 16 kHz context so it returned a gain bus. The driver plays each WAV
  into that bus *reactively*, e.g. "3 s after the agent's first voiced audio".
- **Measurement:** I recorded every WebSocket frame (Playwright/CDP) with a wall-clock time. Both PCM streams were decoded:
  `user_audio_chunk` 16 kHz up and `audio` 44.1 kHz down. Any |sample| > 600 counts as voiced, which gives
  exact "user speech sent" and "agent voice arrived" times. Tokens were redacted at capture: `persistent_session_token`, JWTs.
- **What rea found:** `inspect_web_page` (8 s window) saw no WebSocket because it attached before the call opened.
  `analyze_web_bundle` found 114 scripts and 6 route candidates, but **no client-side VAD or turn settings**. The demo uses
  `@elevenlabs/react` **0.14.0-beta.0 over WebSocket** (`source=react_sdk`, not WebRTC). It only overrides
  `first_message` and `language`, and its `getUserMedia` asks for `voiceIsolation, echoCancellation, noiseSuppression,
  autoGainControl` = true at 16 kHz mono. So every turn decision is made on the server.
- **Network:** server-reported `ping_ms` was **≈282 ms** RTT (India → ElevenLabs). Mic chunks were ≈100 ms (17 chunks per 1.66 s).
  So subtract **≈0.4 s** from client-side latencies to get server-side time.
- **Wire facts:**
  - Downlink audio is `pcm_44100`, **paced in real time in 300 ms chunks**. The stream never goes idle: between turns it carries
    silence chunks.
  - A new turn appears as a **new `event_id`** on the audio stream.
  - Event types seen (652 audio, 15 transcripts): `conversation_initiation_metadata`, `audio`, `agent_response`, `user_transcript`,
    `ping`. There were **no** `interruption`, `agent_response_correction`, `vad_score`, `internal_turn_probability` or
    `tentative_user_transcript` events, so the demo's `client_events` hides them.
  - Interruptions are only visible as "voiced audio stops, and the next chunks carry a new event_id".

## 2. Latency: end of user speech → transcript → first agent voice (client-side, 14 turns)

| Turn (clip) | end → `user_transcript` | end → first voiced audio | transcript → audio |
|---|---|---|---|
| "What is the capital of France?" (×2) | 1.70 / 1.73 s | 1.88 / 1.94 s | 0.18 / 0.21 s |
| "So, what time is it in Tokyo…" | 1.65 | 1.78 | 0.13 |
| "…Japan and I need help choosing a city." | 1.72 | 2.01 | 0.30 |
| "Hold on, let me think." (×2) | 1.10 / 1.60 | 1.26 / 1.79 | 0.16 / 0.19 |
| "What is a good name for a cat?" | 1.56 | 1.85 | 0.30 |
| long questions (L, L2, A2, H) | 1.92 / 1.81 / 2.28 / 2.12 | 2.15 / 3.02 / 2.49 / 3.95 | 0.2–1.8 |
| "Wait, stop." / "Mmh, mmh." / "OK, so." | 1.91 / 2.26 / 1.93 | 2.21 / 3.25 / 2.23 | 0.3 / 1.0 / 0.3 |
| **Median** | **1.81 s** | **2.08 s** (p25 1.85) | **≈0.2 s** |

What this shows:
- **Their commit wait is about 1.4 s server-side**, even for clean, complete questions.
- Once they commit, the voice starts in about 0.2 s. They must have the reply already in flight before the transcript is final
  (speculative LLM/TTS).
- **9 of 15 replies begin with "Um,"**. That "Um," arrives as an isolated first 300 ms chunk, then there's a gap before the rest:
  a lead-in that masks the LLM's time to first token. Short replies ("No problem…", "Oh, sorry!") don't use it.
- Re-engagement: after **≈9.3 s** of silence following the greeting, the server injected `user_transcript "..."` and the agent
  said "Are you still there?". When the silence continued, the call ended about 8 s later.

## 3. Scenarios: ElevenLabs measured vs Stiti's `endpoint.py`
Stiti's values were checked by calling `text_state`, `barge_verdict` and `wait_for` on the same transcripts.

| # | Scenario | ElevenLabs (measured) | Stiti design (`endpoint.py`) | Verdict |
|---|---|---|---|---|
| a | Complete question, then silence | Commits 1.6–1.8 s after speech end; voice at ≈1.9–2.0 s (≈1.5 s server-side) | `finished` + Smart Turn ≥0.5 → commits when the transcript is ready (≈0.45 s). Smart Turn <0.5 → `min_delay` **0.6 s** | Stiti is ~1 s faster. The unsure-audio path (0.6 s) is the riskiest number |
| b | "So..." + **1.2 s** + rest | **Waited.** One turn: "So, what time is it in Tokyo right now?" | `So...` → `unfinished` → waits **3.0 s**, joins the fragments | Both correct |
| c | "…Japan and" + **1.5 s** + rest | **Waited.** One turn, joined | `and` ∈ HARD_CONNECT → `unfinished` → 3.0 s | Both correct |
| c′ | "I was wondering" + **2.5 s** + rest | **Waited ≥2.5 s.** One turn: "I was wondering, how much…" | `text_state("I was wondering")` = **`finished`** → commits at 0.45–0.6 s and **cuts him off** | **Stiti gap** |
| c″ | "Okay so" + **2.0 s** + rest | **Did not wait.** Committed "OK, so." at 1.93 s and said a content-free "Um, ..." (0.6 s), which overlapped his continuation. The continuation became a new turn | `okay so` ∈ OPENERS → `unfinished` → 3.0 s, then one "Mm-hm?" and keeps the prefix. Continuation grace 0.9 s cancels and joins | Stiti better. Shows that < 2 s is too short for openers |
| d | "Hold on, let me think." + **4 s** + question | **Spoke anyway** (both runs): "No problem at all, take your time. I'm here whenever you're ready." That is ≈3 s of speech starting 1.3–1.8 s after. In 1 of 2 runs his question started while it was still talking | `wait` → **silent for 8.0 s**, then commits the joined text | Stiti better (that is ElevenLabs' own `skip_turn` idea, unused in their demo) |
| e | "mm-hm" while the agent speaks | **Stopped and yielded.** Last voiced chunk arrived 0.85 s after onset (≈0.5 s of heard speech server-side). Transcript "Mmh, mmh." was treated as a full turn: new reply "I hear you, but listing out every single product… might be a bit much". The original answer was lost | Duck to 30 % at 250 ms. Verdict on the transcript: `barge_verdict("Mm-hmm.")` = resume ✓, **but `barge_verdict("Mmh, mmh.")` = `stop`** (`mmh` is not in BACKCHANNEL_WORDS) | Stiti's design is better. Small vocabulary gap |
| f | "Wait, stop." while the agent speaks | **Stopped.** Last voiced chunk 0.55 s after onset (≈0.2–0.5 s of speech server-side). Reply "Oh, sorry! What would you like to know instead?" 2.2 s after he finished | Duck at 250 ms → `stop` (stop word). Silent by 0.9 s at the latest (`FORCE_PAUSE_MS`) or as soon as the transcript lands | Comparable. ElevenLabs' audible stop ≈0.85 s (last chunk + 300 ms buffer) |
| g | Silence after the agent speaks | "Are you still there?" after ≈9.3 s, then hangs up | No nudge; sleeps after `AWAKE_TIMEOUT_S` | Keep Stiti's way (a buddy doesn't poke) |
| h | Speech over the tail of a reply (3 cases) | Reply audio cut 0.3 s after his onset; any speech counts. A reply that hadn't started yet was dropped entirely | Continuation grace (cancel + join) inside 0.9 s of first audio; otherwise barge-in duck/pause | Both yield. Stiti also joins the text |

**Bottom line:** the live ElevenLabs demo is *patient on pauses but trigger-happy on overlap*:
- It waits up to about 2.5 s when the words are clearly unfinished.
- It answers "hold on" out loud.
- Any overlapping speech, backchannels included, stops it after about 0.5 s.

Stiti's new design already beats it on (d) and (e) and matches it on (b) and (c). Its two real gaps are (c′) and the backchannel
vocabulary in (e).

## 4. Tuning recommendations for `src/stiti/voice/endpoint.py` (exact numbers)

1. **Projection stems → `unfinished` (fixes c′).** Add a `PROJECT_RX` checked before the "finished" fall-through in
   `text_state`, matching the end of the normalized text:
   `(i was wondering|i was thinking|i wanted to (ask|say|know)|i want to (ask|know)|the (thing|question|problem) is|
   my question is|what i mean is|can you tell me|do you know|tell me|i think that|main soch raha tha|mujhe (ye )?puchna tha|
   baat (ye )?hai( ki)?|mujhe lagta hai)$`.
   Keep "just wondering" and "i was just wondering" as `finished` by adding both to `FINISHED_TAILS`. ElevenLabs held at least 2.5 s
   here, and with this change Stiti gets `UNFINISHED_WAIT_S` = 3.0 s.
2. **Backchannel vocabulary (fixes e).** Before the word-set test in `barge_verdict`, treat a transcript as a backchannel if
   every word matches
   `^(m+h*m*|h+m+|m+h+m*|u+h+|u+h+ ?h+u+h+|a+h+a*|o+h+|ok+a*y*|haan+(ji)?|ji+)$`.
   This catches "Mmh, mmh." (ElevenLabs/Scribe spelling), "mmm hmm", "uhhuh", "ohh" and "haanji". Also add `mmh`, `mhmm`,
   `hmmm`, `ohh`, `aha` and `haanji` to `BACKCHANNEL_WORDS`. Up to 3 backchannel tokens → `resume`.
3. **`MIN_DELAY_START` 0.6 → 1.0 s** (`MIN_DELAY_MIN` stays 0.5, max stays 3.0). This is the "text says finished but Smart Turn
   < 0.5" path.
   - ElevenLabs waits ≈1.4 s server-side even on clean questions.
   - Stiti's 0.6 s was the most aggressive number in the table.
   - The confident path is unchanged: `wait_for` subtracts `MIN_DELAY_START`, so finished + p ≥ 0.5 still commits at about 0.45 s.
   - The EMA still learns his pace from here.
4. **`FORCE_PAUSE_MS` 900 → 700.**
   - ElevenLabs goes silent after roughly 0.2–0.5 s of heard speech.
   - A pause is reversible: the buffer is kept, and `BARGE_QUIET_S` 1.5 s resumes it.
   - Natural backchannels last 200–600 ms, so most never reach the pause.
   - Keep `DUCK_MS` 250 and `VAD_BAR_SPEAKING` 0.7.
5. **Keep these values, now measured:**
   - `UNFINISHED_WAIT_S` 3.0: ElevenLabs committed "OK, so." at 1.9 s and collided with the continuation at 2.0 s, so < 2 s is
     too short.
   - `WAIT_PHRASE_S` 8.0, with **no spoken line**: ElevenLabs' 3 s "take your time" speech overlapped him in 1 of 2 runs. If
     anything, play a ≤ 0.4 s "mm".
   - `CONT_GRACE_S` 0.9 and `SPEC_STT_MS` 160.
6. **Keep the "Mm-hm?" reprompt after an unfinished timeout short (≤ 0.6 s)**, like ElevenLabs' "Um, ..." (0.6 s). Keep the prefix
   so the continuation joins. That's already the design; just cap its TTS length.
7. **Latency lesson (`loop.py`, not `endpoint.py`):** ElevenLabs gets transcript → voice down to about 0.2 s with two tricks.
   - It starts work before committing. For Stiti: on `finished` + p ≥ 0.5 at `SMART_TURN_MS`, run the engine on the
     speculative transcript with deltas buffered (P2 item 10 in the RE doc).
   - It speaks a 300 ms lead-in ("Um,") while the LLM runs. Stiti's filler is at 1.6 s; leave it, because Stiti's local
     commit is already about 1 s faster.
   - Target stays: first audio ≤ 1.0 s after his speech ends. ElevenLabs' demo measured a median of 2.08 s from India.
8. **Playback buffer ≤ 300 ms.** ElevenLabs paces audio in real time in 300 ms chunks, so a server-side stop is audible
   within about 0.3 s. Keep Stiti's `duck` and `pause` acting on a buffer no deeper than that.

Caveats:
- The sample is small (14 timed turns) and the voice is synthetic US English, not Hinglish.
- The demo agent's own config (eagerness, ignore terms, `speculative_turn`) is not visible. These numbers describe *this deployed
  agent*, not every ElevenLabs agent.
- Scenarios c′, c″ and d (run 1) started over the tail of a reply, so they also exercised barge-in.

## 5. Sources
- Live capture: `https://elevenlabs.io/conversational-ai` (Voice → Web call), WebSocket
  `wss://api.elevenlabs.io/v1/convai/conversation?…&source=react_sdk&version=0.14.0-beta.0`, captured 2026-11-11.
  Raw logs (redacted, not committed) are in the session scratchpad: `s1c.jsonl`, `s2.jsonl`, `s3.jsonl`.
- rea MCP: `list_browser_targets`, `inspect_web_page`, `analyze_web_bundle` (evidence `ev_2afd6809…`).
- `docs/research/elevenlabs_conversation_re.md` (event model, `interruption_ignore_terms`, `skip_turn`, `turn_timeout`, soft timeout).
- `docs/research/conversation_turn_taking.md`, and `src/stiti/voice/endpoint.py` (read and called, not edited).
