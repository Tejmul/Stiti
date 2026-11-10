# Conversation turn-taking: when Stiti should speak, wait, stop, and what she should say (research, 2026-11-11)

**Problem (his words + `~/.stiti/logs/app.log`):** it doesn't feel like a conversation. She jumps in while he's still
thinking ("So..." → instant reply, once just "…"), cuts him mid-sentence (the next segment starts with "and…": "and web. It
contains…", "And I'll put the chat."), sometimes "doesn't hear him", speaks Hinglish when he asked for English, nags with the
onboarding line on every wake, and asks follow-ups about old memories that have nothing to do with the topic.
**Target:** "Hey Stiti" → "Hey Tej, how are you?" → long reminder sentence with pauses → "Got it, 4 PM. Anything else?" →
"Not yet. Any new research paper?" → answer. Commercial systems (ElevenLabs, OpenAI, Deepgram, Hume) are covered by a
separate doc; here they get one line each. **This doc reads the open-source stacks at source level.**

## 0. What Stiti does today and why it fails (code read: `voice/loop.py`, `turn.py`, `speaker.py`, `wake.py`, `engine.py`)
| Symptom | Root cause in our code |
|---|---|
| "So..." gets answered | End of turn is **audio-only** (Smart Turn) with a **falling bar** 0.5/0.4/0.3 at 300/600/1000 ms and a 1.5 s fallback. Nobody does a falling bar: Pipecat asks once at 0.5 and then waits up to **3 s**; LiveKit waits **3 s** when the text says "unfinished". A word like "So" has falling pitch, so the audio model says "done". |
| Mid-sentence cut, continuation becomes a new turn | `_handle()` blocks the loop while she answers, so when he keeps talking 0.5 s later, his second half is a *new* turn. Nobody cancels the answer that's on its way (Bolna/LiveKit do). |
| Smart Turn is weak on his speech | Smart Turn v3.2's own benchmark: Hindi **FPR 8.6%** (EN 3.8%). On real *human Hinglish* (518 clips) the stock model holds an unfinished turn only **67.8%** of the time (balanced acc. 70%, AUC 0.75) [smart-turn-hinglish]. Audio alone can't fix Hinglish. |
| "Doesn't hear him" | **17 of 41** logged user lines are just "Bye." and most come right after her long replies → probably Whisper making up "Bye." from the echo tail/noise → `is_goodbye` → she goes to sleep. The barge-in also cuts her off hard after 450 ms of VAD, even for a cough. |
| Hinglish / nagging / random memories | SOUL says "Hinglish when they speak Hinglish", the acks/fillers are Hindi ("Ek sec, calendar dekhti hoon"), and the greeting says "Haan, bolo?". `greet()` repeats the onboarding offer on every wake. Memories with sim ≥ 0.25 go into the briefing, and SOUL says "brings it up naturally", so the LLM brings them up. |

Measured on this M2: Smart Turn v3.2 int8 = **28 ms p50 / 33 ms p90** per check (`turn.complete_prob`, 20 runs). Whisper
transcript is ready about 233–368 ms after he stops (D18), so **a text check costs nothing extra in time**: the LLM can't start
before that transcript exists anyway.

## 1. Comparison (16 systems/papers)
| # | System / paper | Mechanism | Latency | Hindi / Hinglish | Size / RAM | License · free? | Fits M2 8 GB? |
|---|---|---|---|---|---|---|---|
| 1 | **LiveKit Agents turn detector** (read source) | Text EOU: Qwen2.5-0.5B (pruned, distilled from 7B) gives P(`<|im_end|>`) over the last 6 turns / 128 tokens; per-language "unlikely" threshold; below it → wait `max_delay` | tens of ms on CPU (reported, [LK-blog]) | **hi: thr 0.0398, TPR 99.4%, TNR 96.3%** (`languages.json` v0.4.1-intl); Devanagari-trained, romanised Hinglish untested | 396 MB q8 ONNX, <500 MB RAM | **LiveKit Model License: may only be used *with LiveKit Agents*** | ⛔ licence (copy the *logic*, not the model) |
| 2 | **LiveKit endpointing + interruption** (`voice/turn.py`, `endpointing.py`, `agent_activity.py`) | min/max delay, dynamic EMA of user pauses, pause→resume on false barge-in, AEC warm-up | — | language-agnostic | code only | Apache-2.0 · free | ✅ copy |
| 3 | **Pipecat Smart Turn v3.2** (in use) | Audio: Whisper-tiny encoder + head, last 8 s, sigmoid > 0.5 | **28 ms measured** | 23 langs; hi acc 90.1%, FPR 8.6%; human-Hinglish bal. acc 70% | 8.7 MB | BSD-2 · free | ✅ keep |
| 4 | **Pipecat turn strategies** (`pipecat/turns/*`) | VAD stop 0.2 s → Smart Turn once; else wait `stop_secs`=3 s; `MinWordsUserTurnStartStrategy`; **LLM turn markers ● ◐ ○**; `SpeculationGate` | +1 token for markers | prompt-level, any language | code only | BSD-2 · free | ✅ copy |
| 5 | **TEN Turn Detection** (+ `ten_turn_detection/extension.py`) | Text classifier with 3 classes: finished / **wait** / unfinished; unfinished → force-reply timer 5 s | GPU-server | EN + ZH only | Qwen2.5-**7B** (~15 GB) | Apache-2.0 (w/ conditions) | ⛔ too big; ✅ copy the 3 classes + test set |
| 6 | **Kyutai Unmute** (`unmute_handler.py`, `stt/speech_to_text.py`) | Semantic VAD: STT model's pause head `prs[2]`, attack/release EMA (0.01 s); end if > 0.6; barge-in if bot speaking and < 0.4 | STT delay 0.5 s, 80 ms frames | en/fr only | 1B STT, GPU | MIT/CC-BY · free | ⛔ model; ✅ copy rules + prompt |
| 7 | **Bolna** (Indian telephony agents; `interruption_manager.py`, `task_manager.py`) | STT endpointing 400–500 ms, **900 ms "user continues" grace that cancels the pending reply**, word-count barge-in + stop-phrase list, timed backchannels | — | `hinglish_mode` → hints [hi,en] for Deepgram | code only | MIT · free | ✅ copy |
| 8 | **VAP** — Ekstedt & Skantze 2022 (read repo) | Transformer on CPC features at 50 Hz, predicts both speakers' voice activity in bins 0.2/0.4/0.6/0.8 s → p(shift), p(backchannel) | real-time | trained on English Switchboard; no Hindi | 23 MB state dict | MIT · free | 🟡 needs stereo (his + her channel) and retraining |
| 9 | VAP real-time CPU / multilingual (Inoue et al. 2024; MaAI) | Same, CPU real-time; one en+zh+ja model as good as mono models | real-time CPU | no Hindi; a model trained on one language transfers badly | small | MIT-ish · free | 🟡 later, backchannel timing |
| 10 | TurnGPT (Ekstedt & Skantze 2020) | GPT-2 trained to predict a turn-shift token from the words | LM forward pass | EN | 124M+ | research | 🟡 the idea behind #1 |
| 11 | SpeculativeETD (Ok et al. 2025) | Tiny on-device GRU says "maybe done", a server model confirms | ~ms on device | EN | tiny + server | research | ✅ idea: cheap local check first, confirm later |
| 12 | Moshi (Kyutai 2024) | Full-duplex speech-to-speech 7B, no explicit turns, 160–200 ms | GPU | EN | 7B | CC-BY | ⛔ it *is* a local LLM |
| 13 | ElevenLabs Agents | turn model + `turn_eagerness` low/standard/high, `turn_timeout` 1–30 s (examples use 7), `soft_timeout` 3 s → filler | ~ | many | cloud | paid | ⛔ (other doc) |
| 14 | OpenAI Realtime | `server_vad` (thr 0.5, prefix 300 ms, silence 500 ms) or `semantic_vad`, eagerness max wait **8/4/2 s** | ~ | many | cloud | paid | ⛔ (other doc) |
| 15 | Deepgram Flux / AssemblyAI U-Streaming | STT that also predicts end of turn: Flux `eot_threshold` 0.7, eager 0.3–0.9, `eot_timeout_ms` 5000; AAI EoT conf 0.4, `min_turn_silence` 160 ms (U3-Pro 100), max 1000 ms | ~ | Flux-multi: hi hints | cloud | paid (free credits) | ⛔ not free-forever |
| 16 | Hume EVI · Gemini Live · Speechmatics · Sesame CSM | prosody-aware EOT (Hume); `automaticActivityDetection` sensitivity + `silenceDurationMs` (Gemini); `end_of_utterance_silence_trigger` (Speechmatics); CSM-1B is TTS only, no open turn model | ~ | varies | cloud / 1B | mixed | ⛔ |

Human baseline: the gap between turns is about **200 ms** in all 10 languages studied (Stivers et al. 2009). That's possible
only because people *predict* the end of a turn. Silence alone is a bad signal.

## 2. What the best ones actually do: rules and numbers to copy (from source)
**LiveKit** (`livekit-agents/voice/turn.py`, `audio_recognition.py::_run_eou_detection`, `endpointing.py`, `agent_activity.py`)
- Endpointing: `min_delay` **0.5 s**, `max_delay` **3.0 s** (streaming detector: 0.3 / 2.5). In `_bounce_eou_task`: delay = min_delay;
  if `p_eou < unlikely_threshold(lang)` → delay = max_delay. Sleep `delay − (now − last_speaking_time)`; **any new speech
  cancels the task**. When the text says "unfinished", the STT flush waits `max_delay/2` first, so the transcript keeps context.
- `DynamicEndpointing`: min_delay is learned with `ExpFilter(alpha=0.9, min=min_delay, max=max_delay)` from (a) his pauses
  between utterances inside one turn and (b) **"immediate interruption"**: he starts talking again ≤ min_delay after the agent
  starts. That means the agent cut in too early, so the pause before it is learned as a "keep waiting" pause. Speech that starts
  within **0.25 s** of agent audio isn't treated as a backchannel (TTS leading silence).
- Interruption: `min_duration` **0.5 s** of VAD speech, `min_words` 0 (STT word gate), `resume_false_interruption` **True**,
  `false_interruption_timeout` **2.0 s**: on speech the agent's audio is **paused, not cancelled**; if no real transcript
  follows within 2 s it **resumes**. `aec_warmup_duration` **3.0 s**: no barge-in from audio at session start.
  `backchannel_boundary` (1.0, 1.0) s: backchannels in the first/last 1 s of an agent turn are ignored.
- Preemptive generation: the LLM starts on the final transcript before the turn is committed (not TTS by default); skipped for
  speech > 10 s; max 3 retries per turn. `_FillerScheduler`: filler after `delay` of idle, optional `interval`, `max_steps`.

**Pipecat** (`audio/turn/smart_turn/base_smart_turn.py`, `local_smart_turn_v3.py`, `turns/*`)
- VAD `start_secs` 0.2, `stop_secs` 0.2. Smart Turn runs **once** per VAD stop: `prediction = 1 if probability > 0.5`. If the
  answer is "incomplete", the turn ends only on new speech or `stop_secs` = **3 s** of silence. `pre_speech_ms` 500, window 8 s.
- `MinWordsUserTurnStartStrategy`: while the bot is speaking, a user turn (= barge-in) needs `min_words` (the examples use 3).
  When the bot is silent, 1 word is enough.
- **LLM turn-completion markers** (`user_turn_completion_mixin.py`): the reply LLM must start with `●` (complete → answer),
  `◐` (cut off mid-phrase → output nothing, re-prompt after **5 s**), or `○` (needs time: "hold on", "let me think", or only
  reacted "hmm/that's interesting" → re-prompt after **10 s**). The rules: "complete = conversationally complete, not long";
  "ends on a conjunction, preposition, article, 'because', an unfinished list or number → ◐; do not answer it, do not guess
  the rest"; "join the fragments after a ◐/○ and judge them as one turn". Each marker is a single token.
- `SpeculationGate`: a reply started on an *eager* end of turn is HELD until the turn is confirmed, and DROPPED if he goes on.

**TEN** (`ten_turn_detection/extension.py`): on each STT final, the text is added to `cached_text` and classified as finished → send,
**wait** ("shut up", "hold on") → drop it and stay quiet, unfinished → start a `force_threshold_ms` **5000** timer, then send anyway.
The agent's audio is flushed as soon as ≥ 2 characters of new speech arrive.

**Kyutai Unmute** (`unmute_handler.py`): pause score EMA (attack = release = 0.01 s, first 12 steps ≈ 1 s ignored); turn ends
when **> 0.6**; while the bot speaks, a score **< 0.4** = barge-in, but never in the first **3 s** (`UNINTERRUPTIBLE_BY_VAD_TIME_SEC`).
Silence **7 s** → a "..." message goes to the LLM; the prompt says to vary the nudge, and after 3 unanswered nudges say bye. Prompt:
"If the user's message seems to end abruptly … answer with a **very short response prompting them to continue**"; "if a
transcript looks wrong, guess what they meant rather than asking"; "Be brief"; "respond in the language the user is speaking".

**Bolna** (`agent_manager/interruption_manager.py`, `task_manager.py`, `constants.py`): `incremental_delay` **900 ms**. If he starts
talking again within 900 ms of his last utterance and a reply is pending, the pending reply is **cancelled** and the two parts
are joined ("user continuation detected"). Barge-in while the agent talks needs `word_count > number_of_words_for_interruption`
(task default **3**) **or** a phrase from `ACCIDENTAL_INTERRUPTION_PHRASES` (stop, wait, no, hold on, enough, shush…). A final
transcript with ≤ N words that isn't a stop phrase, heard while she talks, is **dropped** (it's a backchannel). Backchannels:
pre-recorded clips, only after he has talked ≥ `backchanneling_start_delay` (5 s), then every `gap` (5 s, task default 2).
"Are you still there?" after 10 s; hang up after 20 s of silence.

## 3. Recommended design for Stiti (keep Smart Turn, add text + timing + conversation rules)
**3.1 End of turn = audio score + text check + adaptive wait** (0 MB new RAM, < 1 ms for the rules, no new latency)
- Keep Silero VAD + Smart Turn v3.2, but ask Smart Turn **once** at 300 ms with a fixed bar of 0.5. **Drop the falling bar.**
- **Text check** on the transcript we already start at 160 ms (`text_state()` in §4): **finished / unfinished / wait**,
  TEN's 3 classes. Rules: the last word is a connector (EN + Hindi), it ends in a filler, it's a lone opener ("So", "And",
  "Okay so"), an action without its slot ("remind me at 4 to"), or a wait phrase ("hold on", "ek sec", "ruko", "let me think").
  A cheap local check first, then a stronger check (the SpeculativeETD pattern).
- **Wait table** (copied from LiveKit/Pipecat/TEN/OpenAI): finished & audio ≥ 0.5 → answer now (≈ 450 ms after he stops, when
  the transcript is ready); finished & audio < 0.5 → wait `min_delay` (learned, starts at 0.6 s); **unfinished → wait 3.0 s**;
  **wait-phrase → hold up to 8 s** silently (OpenAI "low" eagerness max), then a soft "Take your time." only once.
- **Second opinion from the LLM** (the Pipecat ● ◐ ○ protocol, added to the `[OUTPUT CONTRACT]`): the reply LLM starts with a
  marker anyway, so this costs ~1 token. ◐/○ → drop the reply without speaking, keep listening, and join the next segment onto
  this one. A missing marker counts as ●, so a weak model never blocks a reply.
- **Continuation grace (Bolna 900 ms / LiveKit cancel-on-speech):** after a turn is committed, if he speaks ≥ 300 ms (VAD)
  *before her first audio* or within **0.9 s** of it, cancel the reply, **join the texts**, and re-decide. This needs the
  segmenter to keep running while `_handle` works. It already does; only the main loop has to check a "pending reply".
- **Learn his pace (LiveKit DynamicEndpointing):** EMA α = 0.9 of his within-turn pauses and of his "immediate interruptions",
  clamped to 0.5–3.0 s, saved in `~/.stiti/turn_stats.json`. Every committed segment is auto-labelled (he kept talking / barged
  in within 1 s ⇒ *unfinished*). That gives free training data for a later **Laya `turn_state` head** (CLAUDE.md allows
  calibrating Laya on our own decisions). Test sets: TEN-Turn-TestSet (EN part) + a Hinglish list taken from his logs.

**3.2 Barge-in** (fixes "doesn't hear him" + false stops)
- At VAD ≥ **300 ms** while she speaks → **pause** playback (hold the duplex buffer, don't clear it). Then transcribe the overlap:
  a stop phrase (shut up/stop/bas/chup/wait/ruko/hold on) or **≥ 2 words** → real stop, handle his turn. A backchannel
  (haan/hmm/ok/achha/right/yeah) or ≤ 1 word or nothing within **1.5 s** → **resume** where she paused (LiveKit pause/resume).
- Echo guard: no audio barge-in in the first **3 s** after the loop starts (AEC warm-up) or in the first **250 ms** of each
  playback; VAD bar 0.6 → 0.7 while she speaks.
- **"Bye" gate:** a stop/goodbye only counts if VAD speech ≥ 300 ms, Whisper `no_speech_prob` < 0.4 and `avg_logprob` > −0.8,
  and it doesn't start < 0.6 s after her audio ends. A lone "bye" right after her long reply → ask "Going?" instead of
  sleeping.

**3.3 Fillers and backchannels**
- Keep the instant tool acks, but in **English by default** ("One sec, checking your calendar.").
- The thinking filler moves from 0.9 s to **1.2 s** (ElevenLabs soft timeout is 3 s, and we're usually at about 0.85 s),
  at most 1 per turn, and **never** for a turn that was judged unfinished. That removes the "So..." → "…" bug.
- No spoken backchannels from her while he talks (v1). They overlap his speech, fight the AEC, and Whisper hears them. Only as
  an experiment: a soft "mm-hm" if he has talked ≥ 6 s and pauses 400–700 ms with Smart Turn "incomplete", at most 1 per 8 s
  (Bolna-style).
- His backchannels: while she talks → resume (as now). While she's silent, "ok/hmm/achha" alone isn't a turn unless she just
  asked something (Pipecat "acknowledged, not answered" rule).

**3.4 Conversation design for the reply prompt** (`compiler.py` `[OUTPUT CONTRACT]` + SOUL defaults + fast-path templates)
- **English by default.** Use Hinglish only when *this* utterance is mostly Hindi words. Never switch because of memory or
  old turns. Fillers, acks and the greeting follow the same rule. No emojis or "(laughs)" in speech (Unmute rule).
- **Short turns:** chit-chat ≤ 1–2 sentences (~25 words), facts ≤ 60 words, at most one question and only when needed.
  **Actions are confirmed by repeating the key slot, then "Anything else?"**: "Got it, 4 PM. Anything else?" (fast-path
  template, no LLM).
- **Memory etiquette:** mention a memory only if he asked about the past or it's about *the same topic as his sentence*
  (raise the briefing threshold from sim 0.25 to ~0.45 for small talk). Label the block "background: don't bring up unless
  asked". **Never ask a follow-up question about an old memory he didn't raise.**
- **Fragments:** if a turn is committed by timeout but still looks unfinished, say only "Mm-hm?" / "Go on." (Unmute). Never guess
  the rest.
- **Wake greeting:** ≤ 6 words, time-aware, varied ("Hey Tej, how are you?", "Morning! What's up?"). The onboarding offer is
  made at most once a day and never after he declines. The morning brief only when he asks for it.
- **Ending:** after "Not yet / that's it / nothing" in reply to "Anything else?" → "Okay, I'm here." and go quiet (stay awake
  until the timeout, no chime). She never ends the conversation on her own ("Since it's late, I'll let you go").

**Budget:** VAD 1 ms/frame · Smart Turn 28 ms (once) · text rules < 1 ms · LLM marker +1 token · learned delay O(1) ·
RAM +0 MB (later a Laya head: shares Laya's RAM). Complete turns: answer at ≈ 450 ms of silence → first audio ≈ 0.85 s (same as
D18). "So..." turns: wait 3 s instead of answering. Barge-in decision ≈ 300 ms + ~280 ms STT of the overlap.

## 4. Exact logic to copy (pseudo-code for `voice/loop.py` + a new `voice/endpoint.py`)
```python
CONNECT = {"and","but","so","or","because","cause","then","if","that","which","like","to","of","for","with","the","a","an",
  "my","your","in","on","at","from","about","is","was","i","i'll","i'm","we","you","um","uh","umm","hmm","well","actually",
  "basically","aur","lekin","par","magar","toh","to","kyunki","kyonki","matlab","yaani","ki","ke","ka","ko","se","mein","pe",
  "jaise","phir","fir","ya","agar","jab","haan toh","and then","so like","i mean","you know"}
OPENERS = {"so","and","okay so","ok so","well","um","hmm","acha","achha","toh","aur","listen","suno","hey"}
WAIT_RX = r"\b(hold on|wait|one (sec|second|min)|let me think|give me a (sec|second|minute)|ek (sec|second|minute)|ruko|"
          r"ruk(o|na)|soch(ne do| ke batata| raha)|hang on)\b"
SLOT_RX = r"\b(remind me|set (an )?alarm|add|call|message|text)\b(?!.*\b(\d|am|pm|baje|tomorrow|kal|to \w+ \w+))"

def text_state(t: str) -> str:            # "finished" | "unfinished" | "wait"   (<1 ms)
    w = normalize(t).rstrip(".?!…,").split()
    if not w: return "unfinished"
    s = " ".join(w)
    if re.search(WAIT_RX, s) and len(w) <= 8: return "wait"
    if s in OPENERS or t.rstrip().endswith(("...", "…", ",", "-")): return "unfinished"
    if w[-1] in CONNECT or " ".join(w[-2:]) in CONNECT: return "unfinished"
    if re.search(SLOT_RX, s) and w[-1] in {"to","at","for","about"}: return "unfinished"
    return "finished"

# segmenter: on a pause (VAD < 0.5)
silence += 32
if silence >= 160 and spec is None: spec = stt.submit(cur)                      # as now
if silence >= 300 and pa is None:   pa = smart_turn(cur)                         # ONCE, bar 0.5
if spec and spec.done() and wait_for is None:
    ts = text_state(prefix_text + spec.text)          # prefix_text = fragments joined after a ◐ / cancelled reply
    wait_for = {"wait": 8.0, "unfinished": 3.0}.get(ts) or (0.0 if pa >= 0.5 else stats.min_delay)
if wait_for is not None and silence/1000 >= wait_for: commit(prefix_text + spec.text, ts)
if speech resumes: silence = 0; pa = wait_for = None; stats.pause(silence_before)   # LiveKit "pause between utterances"

# commit → reply with a grace window
pending = start_reply(text)                  # LLM streams; first char ● ◐ ○ (missing → ●)
on marker in "◐○": pending.drop(); prefix_text = text; keep listening (re-prompt "Mm-hm?" after 5 s / 10 s)
on user VAD >= 300 ms while pending and (not pending.audio_started or now - pending.first_audio < 0.9):
    pending.cancel(); prefix_text = text; stats.immediate_interrupt(pause_before_commit)   # learn: wait longer

# barge-in while she speaks (after AEC warm-up 3 s and 250 ms into each playback; VAD bar 0.7)
if speech_ms >= 300: duplex.pause(); overlap = stt(overlap_audio)
    if is_stop(overlap) or words(overlap) >= 2: duplex.clear(); handle(overlap)
    elif is_backchannel(overlap) or quiet_for(1.5): duplex.resume()

# stats: min_delay = clamp(0.9*min_delay + 0.1*pause, 0.5, 3.0); persisted; labels → Laya turn_state head later
```

## 5. Sources (code read 2026-11-11 unless noted)
- LiveKit Agents: https://github.com/livekit/agents (`livekit-agents/livekit/agents/voice/{turn,endpointing,audio_recognition,agent_activity,filler_scheduler}.py`, `livekit-plugins-turn-detector/.../base.py`) · model card + `languages.json`: https://huggingface.co/livekit/turn-detector · licence: https://huggingface.co/livekit/turn-detector/blob/main/LICENSE · [LK-blog] https://blog.livekit.io/improved-end-of-turn-model-cuts-voice-ai-interruptions-39/
- Pipecat: https://github.com/pipecat-ai/pipecat (`src/pipecat/audio/turn/smart_turn/*`, `src/pipecat/turns/{user_turn_completion_mixin,speculation_gate}.py`, `turns/user_start/min_words_user_turn_start_strategy.py`, `turns/user_stop/*`)
- Smart Turn: https://github.com/pipecat-ai/smart-turn · benchmarks https://huggingface.co/pipecat-ai/smart-turn-v3/tree/main/benchmarks · https://www.daily.co/blog/announcing-smart-turn-v3-with-cpu-inference-in-just-12ms/ · [smart-turn-hinglish] https://huggingface.co/abhishek-040010/smart-turn-hinglish
- TEN: https://github.com/TEN-framework/ten-turn-detection (+ TEN-Turn-TestSet) · https://github.com/TEN-framework/ten-framework/tree/main/ai_agents/agents/ten_packages/extension/ten_turn_detection
- Kyutai Unmute: https://github.com/kyutai-labs/unmute (`unmute/unmute_handler.py`, `unmute/stt/speech_to_text.py`, `unmute/llm/system_prompt.py`) · Moshi https://arxiv.org/abs/2410.00037
- Bolna: https://github.com/bolna-ai/bolna (`bolna/agent_manager/interruption_manager.py`, `task_manager.py`, `constants.py`, `models.py`)
- VAP: https://github.com/ErikEkstedt/VoiceActivityProjection · https://arxiv.org/abs/2205.09812 · prosody https://arxiv.org/abs/2209.05161 · real-time CPU https://arxiv.org/abs/2401.04868 · multilingual https://arxiv.org/abs/2403.06487 · MaAI https://github.com/MaAI-Kyoto/MaAI
- TurnGPT https://arxiv.org/abs/2010.10874 · SpeculativeETD https://arxiv.org/abs/2503.23439 · Thai semantic EOT https://arxiv.org/abs/2510.04016 · Stivers et al. 2009, PNAS 106(26) "Universals and cultural variation in turn-taking in conversation"
- Commercial (one-liners only): https://elevenlabs.io/docs/eleven-agents/customization/conversation-flow · https://developers.openai.com/api/docs/guides/realtime-vad · https://developers.deepgram.com/docs/flux/configuration · https://www.assemblyai.com/docs/speech-to-text/universal-streaming/turn-detection
