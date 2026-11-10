# Research: making Stiti's voice feel instant and alive

Date: 2026-11-10. Scope: voice-to-first-audio latency and "aliveness" (fillers, backchannels, acting while talking)
for Stiti's cascaded pipeline on an M2 with 8 GB of RAM. Constraints: no local LLM, free only, local models ≤ ~3 GB.
Code read: `src/stiti/voice/loop.py`, `tts.py`, `stt.py`, `models.py`, `router.py`.

## 0. What the code does today (facts behind the budget)

- **Turn end**: after VAD sees 300 ms of silence (`PAUSE_CHECK_MS`), Smart Turn v3.2 runs **once**. If it says "unfinished",
  nothing re-checks: the turn only ends after **2,000 ms** of silence (`FALLBACK_SILENCE_MS`) unless he speaks again.
- **STT** runs on the whole segment only *after* the turn is closed. Whisper-small q4 takes ~283 ms on the M2 (`models.py`).
- **LLM**: `engine.turn()` returns the whole reply. Nothing is streamed (`loop._handle`). The filler fires at 0.8 s.
- **TTS**: `_speak` runs synth(sentence i) → play → synth(sentence i+1). Synthesis is **not overlapped with playback**, so
  every sentence boundary leaves a silent gap as long as the next sentence's Kokoro synth time.
- **HTTP**: `router._client` caches one `OpenAI(...)` client per provider (good). But httpx's default
  `keepalive_expiry` is 5 s, so after any pause longer than 5 s the next turn pays a new TCP + TLS handshake.
  Groq and Cloudflare are far from India, so that handshake is ~2–3 RTT, or roughly 150–500 ms.

## 1. Latency budget (end of user speech → first audible Stiti audio)

| Stage | Good 2025–26 systems | Stiti today (est.) | Stiti after top fixes (est.) |
|---|---|---|---|
| Endpointing silence + turn model | 150–300 ms (Retell [9]); LiveKit default `min_delay` 500 ms [3]; Smart Turn infer 9–60 ms [2] | 300 ms + ~20 ms; **2,000 ms** when Smart Turn misjudges "unfinished" | 300 ms (+ re-checks so a misjudged pause costs ~600 ms, not 2 s) |
| STT finalisation | streaming: ~0–150 ms after end (Unmute "flush trick" 125 ms [5]) | ~283 ms (whole segment, after turn end) | ~0–50 ms (transcribed during the 300 ms pause) |
| Brain (recall, rules, Laya) | n/a (usually 0–50 ms of RAG) | 20–60 ms | 20–60 ms (starts on the speculative transcript) |
| Network handshake | 0 (warm pool) [19] | 0 warm / **150–500 ms cold** (5 s keepalive) | 0 (keepalive 120 s + pre-warm) |
| LLM time to first token | 200–500 ms (Vapi 400 ms budget [9]; playbook P50 566 ms [4]) | Groq ~190 ms; fallbacks 0.5–2 s | same |
| Rest of LLM reply (non-streamed wait) | 0 (streamed) | +150 ms (Groq) to +1.5 s (fallbacks) | 0 (TTS starts on first clause) |
| TTS first chunk | 90–250 ms (Kyutai 220 ms [5]; playbook 243 ms [4]; Kokoro-MLX ~120–200 ms [18]) | Kokoro int8 ONNX, first sentence ~150–400 ms (measure) | ~80–150 ms (3–6-word first clause, warm session) |
| Audio out + AEC buffer | 20–50 ms | ~30–50 ms | ~30–50 ms |
| **Total, Groq happy path** | **~500–800 ms** | **~1.2–1.5 s** (2–4 s on fallbacks or misjudged turns) | **~0.7–0.85 s** real; **~350 ms** to an acknowledgement |

Measure, don't trust: log `t_vad_end, t_turn, t_stt, t_brain, t_ttft, t_first_clause, t_tts_first, t_play` per turn.
The playbook's own traces show TTFT P95 hitting 2.2–4.4 s, so tail latency matters as much as the median [4].

## 2. Sources compared (≥ 12)

| # | Source | Mechanism | Strengths | Weaknesses | Fits free + 8 GB M2 + no local LLM? |
|---|---|---|---|---|---|
| 1 | Pipecat / Daily voice-AI primer — https://voiceaiandvoiceagents.com/ | Frame pipeline: streaming STT → LLM → TTS; interruptions cancel downstream frames | Reference 1,293 ms breakdown: STT + endpoint + LLM TTFT + TTS TTFB = 83% of it | 500 ms demos need co-located GPUs | **Yes** (design pattern; Stiti already uses Pipecat ideas) |
| 2 | Smart Turn v3 / v3.1 — https://www.daily.co/blog/announcing-smart-turn-v3-with-cpu-inference-in-just-12ms/ , https://www.daily.co/blog/improved-accuracy-in-smart-turn-v3-1/ | 8 MB int8 audio-only end-of-turn classifier on top of VAD | 9–60 ms CPU; English 94.7% accuracy (v3.1); recommends `OMP_NUM_THREADS=1` | One-shot use leaves a fallback timeout; Hinglish accuracy unmeasured | **Yes** (in use) |
| 3 | LiveKit Agents turn tuning + preemptive generation — https://docs.livekit.io/agents/logic/turns/tuning/ | Start LLM (optionally TTS) on the final transcript before the turn is confirmed; cancel if transcript changes; `min/max_delay` 0.5/3 s, `dynamic` mode; adaptive interruption ignores "uh-huh"; resume after false interruption (2 s) | Mature knobs; skip preemption for >10 s utterances; max 3 retries per turn | Docs warn preemption "doesn't always reduce latency"; wasted calls | **Yes** (logic only) |
| 4 | Voice Agent Latency Playbook (HF, 2026) — https://huggingface.co/blog/dvalle08/voice-agent-latency-playbook | Traces per stage; perceived = EOU + TTFT + TTS TTFB | Real P50/P95 numbers; pre-rendered audio saves ~240 ms per covered turn; tool turns give two silences (1.7 s + 1.4 s) | Most fixes not quantified | **Yes** |
| 5 | Kyutai Unmute + DSM (arXiv 2509.08753) — https://kyutai.org/stt , https://github.com/kyutai-labs/delayed-streams-modeling | Delayed-streams STT/TTS; TTS takes LLM text as it streams (220 ms to first audio); "flush trick" runs STT 4× real time at VAD end (125 ms vs 500 ms); semantic VAD | Cascaded but feels full-duplex; best public write-up of stream-everything | 1B models need a GPU (L40S); English/French only | **Partly** (copy the ideas: flush, text-streamed TTS; not the models) |
| 6 | Moshi (arXiv 2410.00037) — https://arxiv.org/abs/2410.00037 | Full-duplex speech-text LM; "inner monologue" text tokens; Mimi codec 80 ms frames | 160 ms theoretical, ~200 ms practical latency; natural overlaps | 7B local model, GPU; weak reasoning; can't plug in Stiti's brain | **No** (local LLM) |
| 7 | Sesame CSM — https://www.sesame.com/research/crossing_the_uncanny_valley_of_voice | Llama backbone predicts codebook 0, tiny decoder fills the rest → low first-chunk latency | Defines "voice presence": timing, pauses, interruptions, emotion, consistent personality | 1B+ model; no turn-taking modelling (authors' own limit) | **No** for the model; **yes** for the presence checklist |
| 8 | OpenAI Realtime `semantic_vad` + `eagerness` — https://developers.openai.com/api/docs/guides/realtime-vad ; Gemini Live (server-side activity detection, can be disabled) | A word-level classifier decides turn end; eagerness low/med/high = max wait 8/4/2 s | Same idea as Smart Turn + transcript; explicit latency-vs-cutoff knob | Paid / cloud audio, not free-tier friendly | **Partly** (idea: a text-side "finished?" check from Laya) |
| 9 | Vapi playbook + Retell explainer — https://vapi.ai/playbook/build , https://www.retellai.com/blog/how-real-time-voice-ai-works-stt-llm-tts | Budgets: Vapi ~1,000 ms (STT 200, LLM 400, TTS 200, net 200); Retell ~600 ms with a turn-taking model (150–300 ms) that handles backchannels | Industry targets; <500 ms natural, <800 ms OK, >1 s broken | Vendor numbers, not comparable start/end points | **Yes** (targets) |
| 10 | PredGen (arXiv 2506.15556) — https://arxiv.org/abs/2506.15556 | Generate candidate replies on partial input while the user speaks; verify at the end | ~2× lower latency (simulated); notes the bottleneck is "time to first sentence" | Simulation only; needs many LLM calls (free-tier rate limits) | **Partly** (only on high-confidence pauses) |
| 11 | DDTSR dual-track (arXiv 2602.23266) — https://arxiv.org/html/2602.23266v1 | Tiny model speaks a content-free discourse connective (commit on entropy) while a big model reasons; streaming partial ASR | Waiting latency 1,003 → 548 ms (−45%); quality unchanged | Uses a local 0.6B LLM for connectives | **Partly** (swap the 0.6B LLM for Laya + templates) |
| 12 | ConvFill (arXiv 2511.07397) — https://arxiv.org/html/2511.07397v1 | On-device 360M model speaks context-aware fillers, then voices cloud "knowledge chunks" as they arrive | TTFT ~0.17 s on an M2 Pro vs 0.74–10.9 s for cloud backends | Local LLM; 5–8% contradictions; accuracy below the backend | **No** (local LLM), but validates "local ack first, cloud content after" |
| 13 | Speculative tool calling — https://getstream.io/blog/speculative-tool-calling-voice/ ; Speculative Interaction Agents (arXiv 2605.13360) https://arxiv.org/abs/2605.13360 | Track A speaks an acknowledgement; Track B predicts and runs read-only tools early; results stay separate until used | Hides 1.5–2 s; 1.6–2.2× speedups; read-only tools are safe to guess | Write actions must not be speculative | **Yes** (Laya = router; tools are local or MCP) |
| 14 | Endpoint anticipation / Voice-Light / RelayS2S — https://arxiv.org/pdf/2606.13450 , https://arxiv.org/pdf/2609.20995 , https://arxiv.org/pdf/2603.23346 | Open private speculative candidates after short silences; release only after final-ASR checks; RelayS2S drafts a prefix (96% good prefixes, 8% fallback) | Formal latency-vs-waste metrics | Research systems, GPUs | **Partly** (the commit/verify pattern) |
| 15 | Backchannel prediction with VAP, "Yeah, Un, Oh" (NAACL 2025) — https://arxiv.org/abs/2410.15929 ; fillers/backchannels in LMs https://www.arxiv.org/pdf/2509.20237 | Continuous model predicts *when* and *which type* of backchannel | Timing and type beat baselines | Japanese/English data; a separate model to run | **Partly** (tiny VAP-style head later; heuristics now) |
| 16 | Whisper-Streaming LocalAgreement-2 (arXiv 2307.14743) — https://arxiv.org/abs/2307.14743 ; WhisperLiveKit https://github.com/QuentinFuxa/WhisperLiveKit | Re-decode a growing buffer; commit the prefix that 2 passes agree on | Streaming from any Whisper (keeps Hinglish); MLX base.en ~70 ms/chunk on M4 | ~3.3 s average lag for long-form; repeated GPU passes | **Yes** (or simply transcribe during the pause, §3 #2) |
| 17 | Moonshine streaming — https://moonshine-voice.readthedocs.io/en/latest/moonshine-vs-whisper/ ; Parakeet (parakeet-mlx) — https://github.com/senstella/parakeet-mlx | Cached incremental encoder (Moonshine); TDT transducer (Parakeet) | Moonshine Small: 38 ms vs Whisper-small 1,940 ms on a MacBook Pro, better WER; parakeet-mlx ~37× real time on an M2 | **English-only / no Hindi**, so Hinglish breaks (already noted in `stt.py`) | **No** for Hinglish (maybe an English-only fast lane) |
| 18 | Kokoro streaming and clause chunking — https://github.com/gabrimatic/kokoro-mlx ; https://simbavoice.ai/resources/streaming-llm-outputs-to-voice-the-engineering ; https://docs.kugelaudio.com/streaming/chunking-and-latency | Flush TTS at sentence end, fall back to a comma or clause when the buffer grows; Kokoro-MLX ~120–200 ms reported | Cheapest big win once the LLM streams | Comma chunks can sound choppy; each chunk pays TTS overhead | **Yes** |
| 19 | Connection reuse / warm pools — https://www.assemblyai.com/docs/tts/getting-started/optimizing-accuracy-and-latency ; https://www.callsphere.ai/blog/reducing-time-to-first-token-ai-agents-connection-reuse-warm-pools | Long idle timeouts (≥2 min), shared TLS context, HTTP/2, pre-warm before the first request | Measured: about 145 ms saved per request when idle sockets weren't dropped; 25 ms from TLS reuse | Blog numbers vary | **Yes** (zero RAM) |

## 3. Ranked techniques for Stiti

Savings are estimates for the Groq happy path. Measure each one with the per-stage log from §1.

1. **Stream LLM tokens and speak the first clause early** (sources 1, 5, 10, 18). Use `stream=True` in `router.complete`, and
   make `engine.turn` a generator. A clause chunker flushes on `. ! ? ।`, or on `,` once there are ≥4 words, or after
   ~12 words. A **producer/consumer TTS queue** synthesises chunk *n+1* while chunk *n* plays, which also fixes today's
   silent gap between sentences. Strip `<think>`/gpt-oss channel tokens on the stream.
   **Saves 150 ms (Groq) to 1.5 s (fallbacks) before first audio, plus 150–400 ms at every sentence boundary.** Effort **M**, RAM ~0.
2. **Speculative STT plus preemptive brain at the 300 ms pause** (the Unmute flush idea [5], LiveKit preemption [3], PredGen [10]).
   At `silence ≥ 300 ms`, run Whisper on the segment *in parallel* with Smart Turn, then start brain recall right away.
   Fire the LLM only when Smart Turn p ≥ 0.5 (or p ≥ 0.3 and Laya says the text is a complete request), to protect
   free-tier quotas. If he keeps talking, cancel and discard. Use LiveKit's guards: no preemption for >10 s turns, ≤3 retries per turn.
   **Saves ~280 ms (STT) + 20–60 ms (brain).** Effort **M**, RAM 0 (same Whisper).
3. **Instant context-aware acknowledgement chosen locally, before any LLM** (DDTSR [11], ConvFill [12], Stream [13], playbook [4]).
   Laya already knows the intent and tool in ~10 ms. Map them to a **pre-synthesised Hinglish template bank**: "Ek sec,
   calendar dekhti hoon", "Haan, yaad hai…", "Achha, sochti hoon", plus mood variants ("Arre, relax, dekhte hain").
   Play it at ~0 ms after turn end, but **only when Laya predicts a slow path** (tool call, deep LLM, fallback provider).
   Never play it on fast-path todos/alarms, and never on every turn (Sesame's "presence" point: repetition kills it).
   Keep the ack content-free (DDTSR's rule) so the LLM's reply always fits after it. Tell the LLM the ack was
   already said so it doesn't repeat it. **Perceived first audio is ~300–350 ms on slow turns; it hides 0.5–2 s.**
   Effort **S**, RAM: a few MB of cached audio.
4. **Keep HTTP connections warm** [19]. Pass `http_client=httpx.Client(http2=True, limits=httpx.Limits(keepalive_expiry=120))`
   to each `OpenAI(...)`. **Pre-warm on VAD speech start** with a cheap `GET /models` to the provider Laya expects to use,
   so the socket is hot by the time he finishes. Add a background ping every ~60 s while awake.
   Also move `_gate_ok`/`_record` Postgres writes off the critical path (record after streaming starts).
   **Saves 150–500 ms on any turn after a >5 s pause**, which is most turns. Effort **S**, RAM 0.
5. **Run tools while she talks (speculative read-only tools)** [13]. When Laya's intent says calendar, mail, todos, recall or
   GitHub with high confidence, start that read-only MCP call at the same moment as the ack (#3), even on the
   speculative transcript (#2). Feed the result into the LLM prompt when it arrives, or have the LLM say the first clause
   first ("Haan, kal teen meetings hain…") while the details load. Never speculate on writes (send mail, delete).
   **Saves 200 ms–2 s per tool turn and removes the playbook's "second silence".** Effort **M**, RAM 0.
6. **Fix the "unfinished" dead air in turn-taking** [2][3][8]. Re-run Smart Turn at 300, 600 and 1,000 ms of silence
   instead of once, and lower the fallback to ~1.2 s (LiveKit-style `dynamic` delay). Add a text-side check: if
   Laya/regex sees a complete command ("add todo X"), end the turn on the first p ≥ 0.35. Keep the adaptive barge-in
   rule (only "haan/hmm" → resume), which already matches LiveKit's false-interruption resume.
   **Saves 0.4–1.7 s whenever Smart Turn misjudges a pause** (common with Hinglish "matlab…"). Effort **S**, RAM 0.
7. **Make the first TTS chunk small and warm** [5][18]. Run a dummy `synth("Hmm.")` at startup so ONNX graph and session init
   happen before the first real turn. Cap the first chunk at 3–6 words. Try `kokoro_onnx`'s `create_stream` (or
   kokoro-mlx on the GPU) and set `intra_op_num_threads` so Kokoro doesn't fight Whisper/Smart Turn for cores. Cache
   audio for frequent fast-path replies ("Done, todo add ho gaya"). **Saves 100–250 ms.** Effort **S**, RAM 0–100 MB.
8. **Backchannels and "thinking aloud" while he talks** [15][3]. When Smart Turn returns mid-range p (0.2–0.5) on a pause
   inside a long (>4 s) utterance, play a quiet pre-synth "hmm"/"haan" at most once per ~8 s, and gate it so AEC and
   Whisper don't transcribe it. Later, train a tiny VAP-style head on logged turns (allowed under the Laya calibration
   exception). **No ms saved; it's what makes her feel alive.** Effort **M**, RAM <10 MB.

Not recommended: Moshi, Sesame CSM, Unmute's 1B models, ConvFill/DDTSR small LLMs (all are local LLMs or need a GPU).
Moonshine and Parakeet can't do Hindi, so keep Whisper-small q4; an English-only fast lane is optional later.
LocalAgreement streaming is unnecessary once #2 hides STT inside the pause.

**Combined estimate:** Groq happy path drops from ~1.2–1.5 s to ~0.7–0.85 s of real first audio. Slow or tool turns
start talking in ~350 ms (ack) instead of 0.8 s ("hmm") or 2–4 s. The biggest single cuts are #1, #2 and #4 together
(~0.6–1.0 s); #6 removes the worst-case 2 s stalls.

## 4. Sources

1. Daily, Voice AI & Voice Agents primer — https://voiceaiandvoiceagents.com/
2. Smart Turn v3 — https://www.daily.co/blog/announcing-smart-turn-v3-with-cpu-inference-in-just-12ms/ · v3.1 — https://www.daily.co/blog/improved-accuracy-in-smart-turn-v3-1/ · repo https://github.com/pipecat-ai/smart-turn
3. LiveKit turn tuning / preemptive generation — https://docs.livekit.io/agents/logic/turns/tuning/
4. Voice Agent Latency Playbook — https://huggingface.co/blog/dvalle08/voice-agent-latency-playbook
5. Kyutai STT/Unmute — https://kyutai.org/stt · TTS https://kyutai.org/next/tts · DSM https://arxiv.org/abs/2509.08753 · https://github.com/kyutai-labs/delayed-streams-modeling
6. Moshi — https://arxiv.org/abs/2410.00037
7. Sesame, Crossing the uncanny valley of voice — https://www.sesame.com/research/crossing_the_uncanny_valley_of_voice
8. OpenAI Realtime VAD — https://developers.openai.com/api/docs/guides/realtime-vad · LiveKit on Gemini Live turn detection https://docs.livekit.io/agents/build/turn-detection
9. Vapi playbook — https://vapi.ai/playbook/build · Retell — https://www.retellai.com/blog/how-real-time-voice-ai-works-stt-llm-tts
10. PredGen — https://arxiv.org/abs/2506.15556
11. DDTSR — https://arxiv.org/html/2602.23266v1
12. ConvFill — https://arxiv.org/html/2511.07397v1
13. Stream, speculative tool calling — https://getstream.io/blog/speculative-tool-calling-voice/ · Speculative Interaction Agents https://arxiv.org/abs/2605.13360 · Deepgram speculative replies https://developers.deepgram.com/docs/voice-agent-speculative-replies
14. Endpoint anticipation https://arxiv.org/pdf/2606.13450 · Voice-Light https://arxiv.org/pdf/2609.20995 · RelayS2S https://arxiv.org/pdf/2603.23346
15. Inoue et al., "Yeah, Un, Oh" — https://arxiv.org/abs/2410.15929 · Backchannels & fillers in LMs — https://www.arxiv.org/pdf/2509.20237
16. Whisper-Streaming — https://arxiv.org/abs/2307.14743 · WhisperLiveKit https://github.com/QuentinFuxa/WhisperLiveKit
17. Moonshine vs Whisper — https://moonshine-voice.readthedocs.io/en/latest/moonshine-vs-whisper/ · parakeet-mlx https://github.com/senstella/parakeet-mlx
18. kokoro-mlx — https://github.com/gabrimatic/kokoro-mlx · Simba streaming LLM→voice https://simbavoice.ai/resources/streaming-llm-outputs-to-voice-the-engineering · KugelAudio chunking https://docs.kugelaudio.com/streaming/chunking-and-latency
19. AssemblyAI latency guide — https://www.assemblyai.com/docs/tts/getting-started/optimizing-accuracy-and-latency · CallSphere warm pools https://www.callsphere.ai/blog/reducing-time-to-first-token-ai-agents-connection-reuse-warm-pools
