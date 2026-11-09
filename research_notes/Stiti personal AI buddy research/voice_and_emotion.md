# Real-time Local Voice Stack + Speech Emotion Recognition for "Stiti" (Apple M2, 8 GB RAM, ~3 GB model budget)

Scope note: research done 2026-11-10. Per coordinator instruction, each feature covers 10+ papers/models/projects in a comparison table before a recommendation. "Fits 8 GB M2?" is my judgement from the cited RAM/param numbers; almost no source benchmarks a base M2 8 GB directly (most numbers are M3/M4/M5 Max/Pro or CPU servers), so expect M2 latencies to be noticeably slower than the cited figures. Recommendations live in each "Inferences" block and are my synthesis, not source claims.

---

## 1. Orchestration framework (streaming, barge-in, turn-taking, Mac/MLX support)

### Takeaway
Pipecat (MIT, Python) is the clear fit: it ships Silero VAD + Smart Turn v3 as the default turn stack, interrupts by default, has MLX-Whisper and Kokoro/MLX-Audio integrations, and has at least four public "fully local on Apple Silicon" reference repos with measured sub-1 s to ~1.5 s voice-to-voice. LiveKit Agents is the main alternative (better for multi-party/WebRTC rooms, heavier); TEN, Unmute and Vocode are poor fits for an 8 GB Mac.

### Cited Findings

| # | Name | Link | Year | Mechanism / how it handles streaming, barge-in, turns | Latency / RAM evidence | Mac/MLX? | Fits 8 GB M2 / free? |
|---|---|---|---|---|---|---|---|
| 1 | Pipecat (v1.x) | [docs: speech input](https://docs.pipecat.ai/guides/learn/speech-input) | 2024– | Frame pipeline. Default user-turn stop strategy = `TurnAnalyzerUserTurnStopStrategy` + `LocalSmartTurnAnalyzerV3` (default since v0.0.102); Silero VAD with `stop_secs=0.2` recommended; with interruptions enabled (default) the bot "immediately stops speaking, in-flight work is cancelled"; if a turn is classed incomplete but silence exceeds Smart Turn `stop_secs`, the turn auto-completes | Pipecat assumes 1.0 s STT latency for unmeasured local Whisper unless you measure ([Evalgent](https://www.evalgent.com/blog/pipecat-voice-agent-testing-guide)) | Yes (MLX Whisper extra, Kokoro/MLX-Audio processors) | Yes; MIT ([Micdrop](https://micdrop.dev/blog/open-source-voice-agent-frameworks)) |
| 2 | kwindla/macos-local-voice-agents (Pipecat author's demo) | [GitHub](https://github.com/kwindla/macos-local-voice-agents) | 2025 | Silero VAD + smart-turn v2 + MLX Whisper + Gemma3n 4B (LM Studio) + Kokoro via MLX-Audio + SmallWebRTCTransport | "<800 ms" voice-to-voice on an M-series Mac; first start can take 30 s+; `HF_HUB_OFFLINE=1` speeds startup | Yes | Speech parts yes; local 4B LLM would not fit with budget (Stiti uses cloud LLM) |
| 3 | Apoorva87/local-voice-agent | [GitHub](https://github.com/Apoorva87/local-voice-agent) | 2026 | Pipecat 1.7.0, SmallWebRTC (browser echo cancellation), Silero, Smart Turn v3, MLX Whisper large-v3-turbo-q4, Ollama LLM, Kokoro-82M ONNX, Hindsight memory | M4 Max warm: turn hold ~430 ms, STT ~245 ms (hidden inside hold), LLM first token ~810 ms, TTS first audio ~620–830 ms, voice-to-voice ~1.4–1.6 s; dropped Kyutai Unmute because it needs a 16 GB VRAM CUDA GPU | Yes | Speech parts yes |
| 4 | mthomas100/local-voice | [GitHub](https://github.com/mthomas100/local-voice) | 2026 | Pipecat, Silero VAD, Smart Turn v3, Nemotron streaming ASR 0.6B 8-bit, Qwen3-TTS/Kokoro, local LLM | M5 Max 128 GB: median 874 ms end-of-speech→first audio (warm). Breakdown: VAD stop 200 ms, STT final 24–78 ms, Smart Turn 2–40 ms, LLM first token 312–353 ms, TTS first chunk 277–292 ms. Cold first turn 3.9 s. Speech stack peak RSS 3.63 GiB (Parakeet+Kokoro) to 5.36 GiB (Parakeet+Qwen3-TTS 0.6B) | Yes | Speech stack RSS already ≥3.6 GiB on that design → must slim down for 8 GB |
| 5 | dusterbloom/localcat | [GitHub](https://github.com/dusterbloom/localcat) | 2025 | Pipecat fork for macOS; Kokoro via MLX, Smart Turn v2, WebRTC | Claims "<800 ms end-to-end" (self-reported) ([search summary](https://github.com/dusterbloom/localcat)) | Yes | Likely |
| 6 | LiveKit Agents | [Micdrop](https://micdrop.dev/blog/open-source-voice-agent-frameworks) / [turn detector docs](https://docs.livekit.io/agents/logic/turns/turn-detector/) | 2024– | Agent framework + WebRTC SFU; own turn-detector models (text, and newer audio "Turn Detector v1"), own wakeword lib; Apache-2.0 | Text turn model 396 MB, 50–160 ms/turn CPU, <500 MB RAM | Runs on Mac (CPU); needs LiveKit server (self-hostable) | Free; heavier infra than Pipecat for a single-user desktop buddy |
| 7 | TEN Framework (Agora) | [Agora blog](https://www.agora.io/en/blog/making-voice-ai-agents-more-human-with-ten-vad-and-turn-detection/) | 2025 | Graph-based multimodal orchestration; ships TEN VAD and TEN Turn Detection | TEN Turn Detection is a 7B Qwen2.5 text model + needs separate ASR ([Easy Turn paper](https://arxiv.org/pdf/2509.23938)) | Partial | Framework yes, its turn model no (7B) |
| 8 | huggingface/speech-to-speech | [GitHub](https://github.com/huggingface/speech-to-speech) | 2024– | Cascaded VAD→STT→LLM→TTS, MLX path on Mac. README defaults now Silero + Parakeet TDT + Qwen3.5-4B + Qwen3-TTS; 16 GB unified memory guidance ([SmartScope](https://smartscope.blog/en/blog/huggingface-speech-to-speech-local-voice-agent/)) | Qwen3-TTS first audio 153 ms on MLX vs 341 ms GGML Q8; mlx 0.32.0 bug caused silent tails ([issue #646](https://github.com/huggingface/speech-to-speech/issues/646)) | Yes (MLX first-class) | 16 GB guidance → too heavy as-is; good reference code |
| 9 | Kyutai Unmute | [GitHub](https://github.com/kyutai-labs/unmute) | 2025 | Wraps any text LLM with Kyutai streaming STT + streaming-text-input TTS (delayed streams modeling); semantic VAD | TTS ~750 ms on single L40S, ~450 ms on unmute.sh multi-GPU ([search summary of Kyutai materials](https://github.com/kyutai-labs/delayed-streams-modeling/issues/101)); needs 16 GB VRAM CUDA ([Apoorva87](https://github.com/Apoorva87/local-voice-agent)) | Kyutai STT/TTS have MLX (`moshi-mlx`) but Unmute server is CUDA | No |
| 10 | RealtimeSTT / RealtimeTTS (KoljaB) | [GitHub](https://github.com/KoljaB/RealtimeSTT) | 2023– | Library: WebRTC VAD + Silero VAD, wake word via Porcupine or openWakeWord, realtime + final transcription; engines: faster-whisper (default), whisper.cpp, Moonshine, sherpa-onnx, Parakeet NeMo, FunASR, etc.; MIT | No numeric latency; Mac only via `brew install portaudio`, no stated Apple GPU acceleration | Weak | Free; building blocks rather than full orchestration |
| 11 | Open-LLM-VTuber | [GitHub](https://github.com/Open-LLM-VTuber/Open-LLM-VTuber) | 2024– | Full app: many ASR (sherpa-onnx, FunASR, whisper.cpp, Groq Whisper…) and TTS backends (sherpa-onnx, MeloTTS, CosyVoice, Edge TTS…); "voice interruption without headphones (AI won't hear its own voice)"; Live2D emotion→expression mapping | No latency numbers; no MLX mention | macOS supported | MIT; bundled Live2D models have separate commercial terms |
| 12 | Vocode | [Micdrop](https://micdrop.dev/blog/open-source-voice-agent-frameworks) | 2023 | Telephony-oriented voice agent lib | Flagged as "stalled core" maintenance risk | — | Avoid |
| 13 | eauchs/speech-to-speech-pipeline | [GitHub](https://github.com/eauchs/speech-to-speech-pipeline) | 2025 | Interruptible (barge-in) STT-LLM-TTS optimized for MLX | No numbers in snippet | Yes | Reference |
| 14 | ChipChat (Apple-adjacent paper) | [arXiv 2509.00078](https://arxiv.org/abs/2509.00078) | 2025 | Cascaded, streaming MoE ASR + state-action augmented LLM + TTS + neural vocoder + speaker modeling, all in MLX on a Mac Studio | "Sub-second response latency"; argues cascades still beat end-to-end on language understanding | Yes (MLX) | Mac Studio, not 8 GB |
| 15 | FireRedChat | [arXiv 2509.06502](https://arxiv.org/pdf/2509.06502) | 2025 | Pluggable full-duplex cascaded/semi-cascaded system with its own small turn-taking controller | Claims parity with TEN's 7B turn model using a smaller model ([search summary](https://arxiv.org/pdf/2509.06502)) | — | Design reference |

- Pipecat's documented barge-in semantics: user-turn start with `enable_interruptions` (default) → bot stops, in-flight LLM/TTS cancelled — [Pipecat docs](https://docs.pipecat.ai/guides/learn/speech-input)
- Builder lesson: running the LLM server as a macOS "Background" process stretched GPU keepalive to 4–7 s; switching to Interactive priority with 250 ms keepalive cut LLM first-token from 2.7–6.8 s to 0.31–0.40 s — [mthomas100/local-voice](https://github.com/mthomas100/local-voice)
- Builder lesson: `pipecat-ai[mlx-whisper]` alone fails to import; also install the `whisper` extra; set `reasoning_effort="none"` on hybrid reasoning LLMs or they return empty content — [Apoorva87](https://github.com/Apoorva87/local-voice-agent)
- Builder lesson: speaker echo unresolved on laptop speakers (agent answered its own reply tail); headphones recommended — [mthomas100](https://github.com/mthomas100/local-voice); Apoorva87 relies on browser AEC via SmallWebRTC — [Apoorva87](https://github.com/Apoorva87/local-voice-agent)

### Inferences
- **Recommendation: Pipecat 1.x** with SmallWebRTCTransport (gets browser/WebRTC echo cancellation for free, which directly addresses the laptop-speaker echo problem that makes barge-in unusable) or a local audio transport plus macOS voice-processing AEC. Reasons: (a) default turn stack (Silero + Smart Turn v3) already matches best practice; (b) interruption/cancellation is built in; (c) four public Apple-Silicon reference repos to copy wiring from (kwindla, localcat, Apoorva87, mthomas100); (d) MIT; (e) native support for cloud LLMs (Groq/Gemini) via OpenAI-compatible services, which matches Stiti's "heavy reasoning in the cloud" design.
- Use mthomas100's per-stage instrumentation as a template; its measured breakdown shows turn detection and STT are small shares — the LLM first token and TTS first audio dominate. With a cloud LLM, network TTFT replaces local TTFT.
- RealtimeSTT/RealtimeTTS are useful as component libraries (wake-word integration) but not as the orchestrator. Open-LLM-VTuber is worth mining for its no-headphones interruption and emotion→expression mapping ideas.

### Gaps
- No source measured Pipecat on a base M2 8 GB. All sub-second numbers are from M4/M5 Max-class machines.
- LiveKit Agents' own local-Mac latency numbers were not found.
- Open-LLM-VTuber's exact echo-suppression mechanism and latency are undocumented on its README.

---

## 2. STT on Apple Silicon (latency, RAM, WER, streaming, Hinglish / Indian English)

### Takeaway
English-only speed leaders (Parakeet TDT v3 int8: 0.9 GB, 117× realtime, 2.37% WER; Moonshine v2) do **not** cover Hindi, so they will mangle Hinglish. For Hinglish, the realistic local options are Whisper-family (large-v3-turbo via mlx-whisper/WhisperKit, ~0.4 GB RSS in WhisperKit) or Hinglish fine-tunes (Oriserve Whisper-Hindi2Hinglish Apex/Swift, Apache-2.0, Roman-script output) or Qwen3-ASR 0.6B (MLX, ~1 GB, Hindi supported but FLEURS-Hindi WER 18.6–25.9%). Groq whisper-large-v3 (free 8 h/day) is the cloud fallback.

### Cited Findings

| # | Model | Link | Year | Mechanism | Latency / RAM (hardware) | Quality | Streaming | Hindi/Hinglish | Fits 8 GB M2 / free? |
|---|---|---|---|---|---|---|---|---|---|
| 1 | Parakeet TDT 0.6B v3 (int8) | [soniqo benchmarks](https://soniqo.audio/benchmarks) | 2025 | FastConformer-TDT | RTF 0.009 (117×), peak RSS 0.9 GB (M5 Pro) | LibriSpeech-clean 2.37% WER; FLEURS en 9.30% | `stream=True` in mlx-audio ([mlx-audio](https://github.com/Blaizzy/mlx-audio)) | No (25 European langs) | Fits; free (NVIDIA CC-BY-4.0 — verify) |
| 2 | parakeet-mlx on M2 | [Spokenly](https://spokenly.app/blog/parakeet-models) | 2025 | same, MLX port | ~37× realtime on M2 GPU (Moondream test) | — | streaming was a TODO as of May 2025 ([mikeesto](https://mikeesto.com/posts/parakeet-tdt-06b-v2/)) | No | Fits |
| 3 | Qwen3-ASR 0.6B MLX (4/5/8-bit) | [soniqo](https://soniqo.audio/benchmarks) | 2025/26 | LLM-decoder ASR | 4-bit: RTF 0.012, RSS 1.0 GB; 5-bit RTF 0.014, 1.03 GB; 8-bit RTF 0.015, 1.3 GB | LS-clean 2.20/1.74/1.82% | offline | FLEURS Hindi 25.93% (4-bit) / 18.57% (8-bit) — table doesn't make clear whether 0.6B or 1.7B was used for the multilingual rows | Fits (~1 GB) |
| 4 | Qwen3-ASR 1.7B MLX 5-bit | [soniqo](https://soniqo.audio/benchmarks) | 2025/26 | same | RTF 0.027, RSS 1.92 GB | LS-clean 1.32% | offline | Hindi supported | Tight for 3 GB budget |
| 5 | WhisperKit large-v3-turbo (CoreML, FP16) | [soniqo](https://soniqo.audio/benchmarks); [WhisperKit paper](https://arxiv.org/pdf/2507.10860) | 2024–25 | Whisper on ANE, streaming hypothesis | RTF 0.084, peak RSS 0.4 GB (M5 Pro); paper: 2.2% WER, 0.46 s mean hypothesis latency | LS-clean 1.71% | Yes (paper) | Multilingual Whisper (Hindi) | Fits; Swift-native (MIT) |
| 6 | mlx-whisper large-v3-turbo-q4 | [Apoorva87](https://github.com/Apoorva87/local-voice-agent) | 2024– | Whisper on MLX GPU | ~245 ms STT per turn (M4 Max), hidden inside Smart Turn hold | — | Batch per turn | Multilingual | Fits; used in kwindla demo too |
| 7 | Moonshine v2 (Tiny/Small/Medium streaming) | [arXiv 2602.12241](https://arxiv.org/html/2602.12241v1); [modelslab](https://modelslab.com/blog/audio-generation/moonshine-vs-whisper-asr-real-time-speech-2026) | 2026 | Ergodic streaming encoder | M3: Tiny 50 ms, Small 148 ms; Medium streaming 107 ms vs Whisper large-v3 11,286 ms (MacBook Pro) | Medium 6.65% WER | Yes | English-only | Fits; but no Hindi |
| 8 | SenseVoice-Small | [GitHub](https://github.com/FunAudioLLM/SenseVoice) | 2024 | Non-autoregressive; also emits emotion + audio-event tags | "5× faster than Whisper-Small"; ~70 ms for 10 s on RTX 4090 ([builderai](https://builderai.tools/blog/speech-recognition-beyond-whisper-parakeet-sensevoice)) | — | Pseudo-streaming only (3rd party) | zh/yue/en/ja/ko only (no Hindi) | Fits (ONNX/sherpa-onnx/GGUF); FunASR model license |
| 9 | Kyutai STT 1B (en/fr) / 2.6B (en) | [Kyutai STT](https://kyutai.org/stt/) | 2025 | Delayed streams modeling | 1B: 500 ms delay; 2.6B: 2.5 s delay; MLX via `moshi-mlx` ([anil.recoil.org](https://anil.recoil.org/notes/kyutai-streaming-voice-mlx)) | — | True streaming, semantic VAD | No Hindi | 1B fits; free |
| 10 | Nemotron Speech Streaming 0.6B (int8) | [soniqo](https://soniqo.audio/benchmarks); [mthomas100](https://github.com/mthomas100/local-voice) | 2026 | Cache-aware streaming (80/160/560/1120 ms modes per [mlx-audio](https://github.com/Blaizzy/mlx-audio)) | RTF 0.058, RSS 961 MB; final transcript 24–78 ms in a live agent | LS-clean 2.82% | Yes | EN (Nemotron 3.5 streaming variant: 40 locales) | Fits |
| 11 | Voxtral Mini 3B / Voxtral Realtime 4B | [mlx-audio](https://github.com/Blaizzy/mlx-audio); [builderai](https://builderai.tools/blog/speech-recognition-beyond-whisper-parakeet-sensevoice) | 2025–26 | Audio-LLM ASR + understanding | ~4 GB; no Apple latency figure found | — | Realtime variant streams | Multilingual | Too big for 3 GB budget |
| 12 | Omnilingual CTC 300M MLX 4-bit | [soniqo](https://soniqo.audio/benchmarks) | 2025 | CTC | RTF 0.005, 0.4 GB | LS-clean 4.26% | — | 1600+ langs | Fits; quality lower |
| 13 | Oriserve Whisper-Hindi2Hinglish-Apex | [HF](https://huggingface.co/Oriserve/Whisper-Hindi2Hinglish-Apex) | 2025 | Whisper fine-tune, ~700 h noisy Indian-accented Hindi; outputs Roman Hinglish | "up to 8× faster than baseline"; ONNX ([onnx-community](https://huggingface.co/onnx-community/Whisper-Hindi2Hinglish-Apex-ONNX)) and GGML conversions exist | WER (vs transliterated refs) FLEURS 29.8, CV20 36.0, Indic-Voices 47.6 | Batch | Purpose-built | Apache-2.0; base size not stated on card |
| 14 | Oriserve Whisper-Hindi2Hinglish-Prime (large-v3, 1.55B) | [HF](https://huggingface.co/Oriserve/Whisper-Hindi2Hinglish-Prime) | 2024 | Full large-v3 fine-tune, ~550 h | — | FLEURS 28.68 vs 50.84 for Whisper large-v3; Indic-Voices 60.82 vs 82.56 | Batch | Yes | Too big unless quantized; superseded by Apex |
| 15 | Oriserve …-Swift (whisper-base) | [HF](https://huggingface.co/Oriserve/Whisper-Hindi2Hinglish-Swift) | 2024 | whisper-base fine-tune | small; GGUF exists ([rohitag13](https://huggingface.co/rohitag13/whisper-hindi2hinglish-swift-GGUF)) | FLEURS 35.1, CV 38.7, Indic-Voices 65.2 | Batch | Yes | Fits easily |
| 16 | Whisper-small LoRA Hinglish (community) | [GitHub](https://github.com/catherine621/Hinglish-Speech-Recognition-Whisper-Fine-tuning-and-Quantization) | 2025 | LoRA fine-tune | — | Zero-shot Whisper-small 71.11% WER → 16.88% after LoRA (229-clip test) | — | Yes | Shows fine-tuning on own voice is very effective |
| 17 | IndicWhisper (Vistaar) | [arXiv 2305.15386](https://arxiv.org/pdf/2305.15386) | 2023 | Whisper fine-tuned on Indian langs | — | Lowest avg WER across Vistaar benchmarks; not evaluated on code-switched speech | — | Hindi (Devanagari) | Free (AI4Bharat) |
| 18 | AI4Bharat IndicConformer-600M | [benchmark repo](https://github.com/Mohanaspiringcoder/indicconformer-asr-benchmark) | 2024 | Conformer RNNT/CTC | — | Kathbath monolingual only; Malayalam worst at 31.50% | — | Monolingual Indic, no code-switch eval found | Free |
| 19 | Groq whisper-large-v3 / -turbo (cloud) | [eesel](https://www.eesel.ai/blog/groq-pricing) | 2026 | Hosted Whisper | Free: 7,200 audio-s/hour, 28,800/day per model, 20 RPM, 2,000 RPD, 25 MB/file, per-org limits | Whisper large-v3 | Batch | Multilingual | Free fallback |

- Caveat: Whisper's default text normaliser understates Indic WER by ~18 points; Hinglish has no standard spelling so WER comparisons across papers are unreliable — [Shekhar-Jha22/indic-asr-eval](https://github.com/Shekhar-Jha22/indic-asr-eval); [Oriserve card](https://huggingface.co/Oriserve/Whisper-Hindi2Hinglish-Apex)
- A vendor blog states strong Hindi performance does not automatically carry over to Hinglish — [Shunya Labs](https://www.shunyalabs.ai/blog/best-hinglish-speech-to-text-models-0yw1) (marketing source)
- Pipecat docs: STT latency figures assume VAD `stop_secs`=0.2 since Smart Turn decides end of turn — [Evalgent](https://www.evalgent.com/blog/pipecat-voice-agent-testing-guide)

### Inferences
- **Recommendation: Whisper-family on MLX, Hinglish-tuned.** Default = `mlx-whisper` large-v3-turbo (q4) running per-turn after Smart Turn fires (STT hides inside the ~200–430 ms turn hold, as Apoorva87 measured). Run a 30-minute A/B on the user's own casual Hinglish against (a) Oriserve Whisper-Hindi2Hinglish-Apex (Apache-2.0, Roman-script output that the cloud LLM reads more naturally) and (b) Qwen3-ASR 0.6B 5-bit (~1 GB). Keep whichever wins; budget ≤1 GB.
- Do not choose Parakeet/Moonshine/Kyutai STT/SenseVoice as the primary STT: none supports Hindi, and casual Hinglish has Hindi words mid-sentence.
- Since streaming partials matter less when Smart Turn gates the turn (STT on a ~2–6 s utterance at 10–100× realtime is a few hundred ms), batch Whisper is acceptable; true streaming STT is a later optimization.
- Personal LoRA fine-tune on ~1–2 h of the user's own speech is the highest-leverage quality lever (community result: 71% → 17% WER).
- Groq Whisper as escape hatch for long/noisy utterances (8 h audio/day free).

### Gaps
- No M2-8 GB measurement for mlx-whisper turbo, Qwen3-ASR or Oriserve Apex; no head-to-head Hinglish WER across Whisper vs Qwen3-ASR vs Apex on the same test set.
- Oriserve Apex's base model size is not stated on its card.
- whisper.cpp + CoreML numbers on M2 not found in this pass.
- Sarvam (Saarika) and AI4Bharat code-switched streaming models: no results found.

---

## 3. TTS (time-to-first-audio, emotion/style control, Indian accent)

### Takeaway
Kokoro-82M (Apache-2.0, ~170 MB CoreML, has Hindi voices in mlx-audio) is the best latency/quality/RAM point and is what nearly every local Mac voice-agent repo uses; its weakness is no emotion control. Emotion-capable models that could fit (Qwen3-TTS 0.6B, Chatterbox Turbo/Nano, Pocket TTS, CosyVoice3) either cost 0.7–2 GB, have worse intelligibility at small sizes, or (Chatterbox) were retired in Aug 2026. Indian-accent options exist (Indic Parler-TTS 0.9B, Maya2, rumik-oss-1) but are heavier/slower.

### Cited Findings

| # | Model | Link | Year | Mechanism | Latency / RAM | Quality | Emotion / style | Indian accent | License / fits 8 GB? |
|---|---|---|---|---|---|---|---|---|---|
| 1 | Kokoro-82M | [soniqo](https://soniqo.audio/benchmarks); [mthomas100](https://github.com/mthomas100/local-voice); [heyneo CPU bench](https://heyneo.com/blog/kokoro-supertonic-inflect-nano-pocket-tts-cpu-benchmark) | 2025 | StyleTTS2-style non-AR | CoreML ~170 MB, RTF 0.17 (M5 Pro); 74 ms whole sentence, RTF 0.02 (M5 Max MLX); 4-core Xeon CPU ONNX RTF 0.641, 0.76 s tiny input; resident ~600 MB via mlx-audio MCP ([scottschram](https://github.com/scottschram/kokoro-tts-mcp)) | Round-trip WER 3.90%; UTMOS 4.44 | Voice presets + speed only | mlx-audio lists HI among 8 langs, 54 presets ([mlx-audio](https://github.com/Blaizzy/mlx-audio)) | Apache-2.0; fits |
| 2 | Pocket TTS (Kyutai, ~100M) | [heyneo](https://heyneo.com/blog/kokoro-supertonic-inflect-nano-pocket-tts-cpu-benchmark); [GetStream](https://getstream.io/blog/best-on-device-tts-models/) | 2026 | CPU-real-time, cloning from ~5 s | ~200 ms first audio (one source); CPU RTF 0.69–0.76 | UTMOS 4.10 | Cloning (can clone an expressive reference) | — | MIT; fits |
| 3 | Supertonic-3 (~99M) | [heyneo](https://heyneo.com/blog/kokoro-supertonic-inflect-nano-pocket-tts-cpu-benchmark) | 2026 | Flow-matching, ONNX | 5-step RTF 0.240 (0.50 s tiny); 2-step RTF 0.121 | UTMOS 4.32 (5-step), 1.53 (2-step) | — | 31 langs | OpenRAIL-M; fits |
| 4 | Kitten TTS (15–80M) | [GetStream](https://getstream.io/blog/best-on-device-tts-models/) | 2025 | Tiny CPU TTS | 25–80 MB on disk | — | — | EN only | Fits |
| 5 | Qwen3-TTS 0.6B / 1.7B | [soniqo](https://soniqo.audio/benchmarks); [mthomas100](https://github.com/mthomas100/local-voice) | 2026 | AR codec LM | 0.6B: first chunk 78 ms, RTF 0.20 (M5 Max); ~675 MB (4-bit)/~960 MB (8-bit). 1.7B 4-bit ~2.3 GB | Round-trip WER 15.58% (0.6B 4-bit), 9.74% (0.6B 8-bit), 3.47% (1.7B 4-bit); occasional laughs, pitch swings, slurring; one 10-word reply → 14 s audio | Emotion control, voice design/cloning ([mlx-audio](https://github.com/Blaizzy/mlx-audio)) | — | 0.6B fits; 1.7B too big; quality risk |
| 6 | CosyVoice3 0.5B 4-bit | [soniqo](https://soniqo.audio/benchmarks) | 2025 | LLM + flow-matching | ~1.9 GB, RTF 0.59 | WER 3.25% | Instruct/emotion (per family) | — | Heavy for budget |
| 7 | Chatterbox family (Resemble) | [GitHub](https://github.com/resemble-ai/chatterbox) | 2025–26 | 0.5B Llama-based + flow decoder; Turbo 350M (1-step decoder), Nano 110M (CPU, ~3× realtime on 8 cores), Multilingual V3 500M (23 langs incl. Hindi) | Sub-200 ms claim refers to hosted service, not OSS | — | `exaggeration` (default 0.5; ≥0.7 with cfg 0.3 for expressive); Turbo/Nano have `[laugh]`, `[cough]`, `[chuckle]` tags | Hindi in Multilingual + Hindi single-language pack | MIT, Perth watermark on all output; **"As of August 2026… retired research, no longer maintained"** |
| 8 | Orpheus 3B | [inferless/ocdevel summary](https://www.inferless.com/learn/comparing-different-text-to-speech---tts--models-part-2) | 2025 | Llama-3B → SNAC tokens | ~200 ms streaming (~100 ms with input streaming) per creators; 8–12 GB VRAM listed | — | Emotive tags | — | Too big |
| 9 | Sesame CSM-1B | [mlx-audio](https://github.com/Blaizzy/mlx-audio) | 2025 | Llama backbone + Mimi codes, context-aware | No Mac number found | — | Conversational prosody from context | EN | 1B: too big for budget |
| 10 | Dia 1.6B | [mlx-audio](https://github.com/Blaizzy/mlx-audio); [ocdevel](https://ocdevel.com/blog/20250720-tts) | 2025 | Dialogue TTS with nonverbals | Rated "Slow"; 8 GB+ | — | Nonverbal tags | EN | No |
| 11 | F5-TTS 336M | [soniqo](https://soniqo.audio/benchmarks) | 2024 | Flow-matching DiT, zero-shot clone | 0.8 GB; RTF 0.57 (16 steps), 1.13 (32 steps) — non-streaming | 1-word sub in roundtrip | Cloning | — | Fits RAM but too slow for TTFA |
| 12 | Kyutai TTS (DSM, 1.6B) | [Kyutai DSM issue](https://github.com/kyutai-labs/delayed-streams-modeling/issues/101); [erogol review](https://erogol.substack.com/p/model-check-kyutaitts-streaming-text) | 2025 | Delayed streams; accepts streaming text from LLM | ~220 ms first-text→first-audio (GPU); MLX available | — | — | EN/FR | Size heavy for budget |
| 13 | Marvis 250M / VibeVoice | [mthomas100](https://github.com/mthomas100/local-voice); [kwindla](https://github.com/kwindla/macos-local-voice-agents) | 2025 | Streaming small TTS | Marvis first chunk 117 ms RTF 0.25; VibeVoice 31 ms RTF 0.12 (but up to 0.86 s leading silence); Pocket 18 ms first chunk RTF 0.04 (M5 Max) | — | — | — | Fits |
| 14 | Indic Parler-TTS (AI4Bharat) | [HF](https://huggingface.co/ai4bharat/indic-parler-tts) | 2024 | Parler (caption-conditioned) | ~0.9B params, no latency figures | Native-speaker scores per language | Emotion prompts (Anger, Happy, Sad, Fear…) officially in 10 Indic langs (not Hindi/English) | 21 langs incl. Indian English, 69 named speakers | Apache-2.0; heavy/slow; card now recommends successor "Indic-Speak" |
| 15 | Maya2 Native / rumik-oss-1 | [mlx-audio](https://github.com/Blaizzy/mlx-audio) | 2026 | Indic TTS in MLX | rumik 3B (8/4-bit); Maya2 size not stated, streaming, 20 voices | — | rumik: description-conditioned delivery + vocalizations | 11 Indic+EN / 22 Indic+EN | Maya2 worth testing; rumik too big |
| 16 | Inflect-Nano-v1 (4.6M) | [heyneo](https://heyneo.com/blog/kokoro-supertonic-inflect-nano-pocket-tts-cpu-benchmark) | 2026 | Tiny | 0.14 s | Sounds "buzzy and robotic" | — | — | Not good enough |

- mlx-audio's AudioPlayer waits for ~1.5 s of buffered audio before playback (adds latency if used naively); cold start ~7.6 s vs ~1.5 s generation — [scottschram/kokoro-tts](https://github.com/scottschram/kokoro-tts)
- "First chunk is not first sound": leading silence ranges 0.42 s (Qwen3-TTS 0.6B) to 0.86 s (worst VibeVoice) — trim it — [mthomas100](https://github.com/mthomas100/local-voice)

### Inferences
- **Recommendation: Kokoro-82M via mlx-audio (or kokoro-onnx) as the main voice, kept resident.** Reasons: lowest RAM (~170–600 MB), best measured intelligibility among small models (3.90% roundtrip WER, UTMOS 4.44), ~74 ms sentence synth on Apple GPU, Apache-2.0, Hindi voice presets available for an Indian flavour. Stream per-sentence (split LLM output at punctuation), bypass mlx-audio's 1.5 s player buffer, trim leading silence.
- **Emotion/style**: emulate with Kokoro voice/speed choice per mood (slower/softer when user is sad/tired; brisker when happy) plus LLM-side wording; pre-render a bank of fillers/backchannels ("hmm", "acha", "ek sec, dekhta hoon…") in the same voice to play instantly while tools run (mthomas100's "Let me look that up" at 1.26 s on a 42 s tool turn is the pattern).
- Optional second engine for expressive moments: Pocket TTS (MIT, ~100M, cloning from an expressive 5 s reference). Qwen3-TTS 0.6B offers real emotion control but its 0.6B quality (9.7–15.6% roundtrip WER, artefacts) is not yet reliable. Avoid Chatterbox for new work (retired, watermark).
- Indian-accent: test Kokoro's Hindi voices on English text and Maya2 (mlx-audio) before considering Indic Parler-TTS (0.9B, no latency data).

### Gaps
- No time-to-first-audio measurement of any TTS on a base M2 8 GB.
- Kokoro Hindi-voice quality on Indian English text not evaluated by any source.
- Piper, Orpheus, CSM licences and Mac latencies not verified in this pass.

---

## 4. VAD + turn detection

### Takeaway
Use a two-stage gate: Silero VAD (~1–2 MB, <1 ms per 32 ms chunk) with a short 0.2 s stop, then Smart Turn v3.1 (8 M params, 8 MB int8 ONNX, ~12 ms CPU, 23 languages incl. Hindi, BSD-2) to decide whether the user is actually done, with a silence fallback. Text-based LLM detectors (TEN 7B, LiveKit text 396 MB) are heavier and depend on transcripts. Expect premature cut-offs on mid-sentence pauses; a Hinglish-tuned or LLM-gated fallback is the improvement path.

### Cited Findings

| # | Name | Link | Year | Mechanism | Size / latency | Accuracy | Languages | Free / fits? |
|---|---|---|---|---|---|---|---|---|
| 1 | Silero VAD v5/v6 | [Silero README mirror](https://github.com/kvrban/silero-vad); [soniqo VAD guide](https://soniqo.audio/guides/vad) | 2021– | Small RNN/CNN frame classifier, 512-sample (32 ms) chunks @16 kHz | ~309K params, ~1.2–2 MB; <1 ms per chunk on one CPU thread | FLEURS F1 95.13%, FAR 15.76% ([soniqo](https://soniqo.audio/benchmarks)) | Language-agnostic | MIT; fits |
| 2 | TEN VAD | [HF](https://huggingface.co/TEN-framework/ten-vad); [Agora blog](https://www.agora.io/en/blog/making-voice-ai-agents-more-human-with-ten-vad-and-turn-detection/) | 2025 | Lightweight streaming VAD | Claims less compute/memory than Silero and faster speech→non-speech transitions (Silero "delay of several hundred ms") — vendor claims | 3rd-party: ESC-50 noise clip accuracy 0.42 vs Silero v6 0.87 ([Cekura](https://www.cekura.ai/blogs/what-is-silero-vad)) | Agnostic | Check licence |
| 3 | FireRedVAD | [soniqo](https://soniqo.audio/benchmarks) | 2025 | 588K params, CoreML/ANE | RTF 0.007 | FLEURS F1 99.12%, FAR 2.52% (note: FLEURS ground truth was generated by FireRedVAD itself → biased); VoxConverse F1 94.21 vs Silero 97.52 | Agnostic | Fits |
| 4 | Pyannote VAD | [soniqo](https://soniqo.audio/benchmarks) | — | 1.5M params | RTF 0.358 (slow) | FLEURS F1 94.86 | — | Too slow for streaming |
| 5 | WebRTC VAD | [RealtimeSTT](https://github.com/KoljaB/RealtimeSTT); [Cekura](https://www.cekura.ai/blogs/what-is-silero-vad) | 2011 | GMM energy-based | negligible | ESC-50 noise accuracy 0 (fires on noise) | — | Only as a pre-filter |
| 6 | Smart Turn v3 / v3.1 (Pipecat) | [HF card](https://huggingface.co/pipecat-ai/smart-turn-v3); [Daily v3 blog](https://www.daily.co/blog/announcing-smart-turn-v3-with-cpu-inference-in-just-12ms/); [v3.1 blog](https://www.daily.co/blog/improved-accuracy-in-smart-turn-v3-1/) | 2025 | Whisper-Tiny encoder + linear head on raw audio (prosody, not transcript) | 8M params; 8 MB int8 / 32 MB fp32 ONNX; 12 ms modern CPU, 60 ms cheap AWS; 2–40 ms in a live agent ([mthomas100](https://github.com/mthomas100/local-voice)) | v3 ≥ v2 on all langs; v2 Hindi 91.20% (different test set) ([v2 blog](https://www.daily.co/blog/smart-turn-v2-faster-inference-and-13-new-languages-for-voice-ai/)); in practice cut off 32/80 mid-sentence pauses ([mthomas100](https://github.com/mthomas100/local-voice)) | 23 incl. Hindi | BSD-2; fits |
| 7 | smart-turn-hinglish (community) | [HF](https://huggingface.co/abhishek-040010/smart-turn-hinglish) | 2026 | Smart Turn fine-tune for code-switched speech + hesitation | same size class | 72.4% balanced acc, 0.777 ROC-AUC on 500-clip Hindi set (self-reported) | Hinglish | Free; immature |
| 8 | LiveKit turn-detector (text, multilingual) | [HF](https://huggingface.co/livekit/turn-detector); [docs](https://docs.livekit.io/agents/logic/turns/turn-detector/) | 2025 | Small LM on transcript | 396 MB disk, 50–160 ms/turn CPU, <500 MB RAM | Hindi TPR 99.4%, TNR 96.3%; v0.4.1 Hindi error 5.40%→3.70% ([LiveKit blog](https://livekit.com/blog/improved-end-of-turn-model-cuts-voice-ai-interruptions-39)) | 14 incl. Hindi | Free; reportedly slated for removal in SDK 2.0 (3rd-party claim) |
| 9 | LiveKit Turn Detector v1 (audio) | [LiveKit docs](https://docs.livekit.io/agents/logic/turns/turn-detector/) | 2026 | Audio-based, no transcript wait | — | — | 14 incl. Hindi | LiveKit-ecosystem |
| 10 | TEN Turn Detection | [GitHub](https://github.com/ten-framework/ten-turn-detection) | 2025 | Qwen2.5-7B text classifier: finished / unfinished / wait | 7B + separate ASR | EN: 90.64% finished, 98.44% unfinished, 91% wait | EN, ZH | Too heavy |
| 11 | Easy Turn | [arXiv 2509.23938](https://arxiv.org/pdf/2509.23938) | 2025 | Acoustic + linguistic fusion; 4 states: complete, incomplete, **backchannel**, wait; 1,145 h trainset | not stated | Claims SOTA vs TEN and Smart Turn v2 on its testset | (ZH-centric) | Open release |
| 12 | FastTurn | [arXiv 2604.01897](https://arxiv.org/pdf/2604.01897) | 2026 | Unifies acoustic + streaming semantic cues | — | — | — | Paper |
| 13 | TurnFSM | [arXiv 2609.04240](https://arxiv.org/pdf/2609.04240) | 2026 | Streaming semantic VAD with state-machine logic + utterance-level rejection | — | Uses TEN as baseline | — | Paper |
| 14 | Namo turn detector (LiveKit plugin) | [GitHub](https://github.com/dangvansam/livekit-plugins-namo-turn-detector) | 2025 | Text model | ~400 MB | — | 23 incl. Hindi | Free |
| 15 | indic-turn-detector | [HF](https://huggingface.co/tarun7r/indic-turn-detector) | 2026 | Text model | — | unverified | Hindi + 7 Indic + Hinglish | Free |

- Pipecat recommended config: Silero `stop_secs=0.2`; Smart Turn decides; incomplete + continued silence beyond Smart Turn `stop_secs` → auto-complete — [Pipecat docs](https://docs.pipecat.ai/guides/learn/speech-input)
- Real-world tuning: Smart Turn alone cut off 32/80 mid-sentence pauses; an 0.8 s early-end rule cut off 35/80 (37/44 with real ASR) so was disabled; shipped = Smart Turn + 2.0 s silence fallback — [mthomas100](https://github.com/mthomas100/local-voice)
- Apoorva87 adds an optional LLM veto on end-of-turn (`TURN_LLM_GATE`, off by default, costs a round trip) — [Apoorva87](https://github.com/Apoorva87/local-voice-agent)

### Inferences
- **Recommendation: Silero VAD (stop 0.2 s) + Smart Turn v3.1 int8 + adaptive silence fallback (~1.2–2.0 s).** Total <10 MB RAM and ~15 ms compute. Reasons: audio-based (works on Hinglish prosody without waiting for transcripts), Hindi in its 23 languages, Pipecat default, BSD-2.
- Hinglish speakers use fillers ("matlab…", "woh…") with long pauses; expect Smart Turn to cut early. Mitigations: (1) longer fallback when the transcript ends in a filler/conjunction (cheap text rule); (2) "soft commit" — start the cloud LLM call speculatively on Smart Turn "complete" but hold TTS ~150 ms and cancel if speech resumes; (3) later, fine-tune Smart Turn on the user's own recordings (the smart-turn-hinglish fine-tune shows it's feasible, though its accuracy is low).
- Easy Turn's "backchannel" state is the right concept for Stiti: user "hmm/haan" during the bot's speech should not count as barge-in.

### Gaps
- No published Smart Turn v3.x per-language accuracy table for Hindi was retrievable as text.
- No independent latency measurement of TEN VAD vs Silero in ms.
- Easy Turn model size / latency not stated in abstract.

---

## 5. Barge-in and full-duplex models

### Takeaway
True full-duplex speech models (Moshi, PersonaPlex, NemotronLabs VoiceChat) do not fit a ~3 GB budget on an 8 GB Mac (Moshi q4 checkpoint alone 4.8 GB; PersonaPlex 4-bit ~6.4 GB total) and are English-centric. Benchmarks show they respond fast (0.27–0.35 s) but interrupt users prematurely, while cascaded systems are slower but more relevant. So Stiti should be a cascaded half-duplex pipeline with engineered barge-in, backchannel suppression and fillers.

### Cited Findings

| # | Name | Link | Year | Mechanism | Latency | RAM / size | Notes | Fits 8 GB M2? |
|---|---|---|---|---|---|---|---|---|
| 1 | Moshi (Kyutai) | [arXiv 2410.00037](https://arxiv.org/html/2410.00037v1) | 2024 | 7B Helium temporal transformer + depth transformer over Mimi codec (24 kHz → 12.5 Hz, 1.1 kbps); models user+system streams in parallel; "inner monologue" text tokens | 160 ms theoretical (80 ms frame + 80 ms acoustic delay), ~200 ms practical on L4 | q4 MLX checkpoint 4.8 GB; q8 8.2 GB needs ≥24 GB ([full-duplex-model-lab PR](https://github.com/LiuQBinh/full-duplex-model-lab/pull/1)) | English; weak reasoning | No |
| 2 | PersonaPlex 7B (NVIDIA) | [NVIDIA repo](https://github.com/NVIDIA/personaplex); [speech-swift doc](https://github.com/soniqo/speech-swift/blob/main/docs/models/personaplex.md); [personaplex-mlx](https://github.com/Acelogic/personaplex-mlx) | 2026 | Moshi-style full-duplex with persona/voice prompts; 2048-frame context | — | 4-bit ~6.4 GB total, 16+ GB Mac recommended; one port claims ~8 GB RAM at 4-bit (conflicting) | MLX/Swift ports exist | No |
| 3 | llm-jp-moshi-v1 | [GitHub](https://github.com/sayonari/llm-jp-moshi-v1-macOS) | 2025 | Japanese Moshi on MLX | — | Moshi-class | Shows MLX ports are routine | No |
| 4 | Freeze-Omni | [Full-Duplex-Bench](https://www.alphaxiv.org/abs/2503.04721) | 2024 | Frozen LLM with speech I/O, hidden-state-level duplex ([survey](https://arxiv.org/html/2606.19453v1)) | 0.953 s response; user-interrupt stop latency 1.42 s, response rate 0.72 ([FDB v1.5](https://arxiv.org/pdf/2507.23159)) | 7B-class | Best contextual relevance, few backchannels | No |
| 5 | dGSLM | [Full-Duplex-Bench](https://www.alphaxiv.org/abs/2503.04721) | 2022 | Dual-tower GSLM | 0.265–0.352 s range (with Moshi) but premature | — | Research | No |
| 6 | Gemini Live / GPT-4o Realtime (cloud) | [FDB v1.5](https://arxiv.org/pdf/2507.23159) | 2025 | Proprietary | GPT-4o Realtime: stop latency 0.23 s, response rate 0.78 on user-interrupt | cloud | Gemini Live has a free tier (see §8) | Cloud only |
| 7 | NemotronLabs VoiceChat | [arXiv 2609.21967](https://arxiv.org/pdf/2609.21967); [mlx-audio](https://github.com/Blaizzy/mlx-audio) | 2026 | Open full-duplex S2S with tool calling | — | 11B (4-bit in mlx-audio) | Tool calling in duplex | No |
| 8 | LFM3-Audio 2B / Liquid2.5-Audio 1.5B | [mlx-audio](https://github.com/Blaizzy/mlx-audio) | 2026 | Speech-to-speech (+TTS/STT), 8-bit MLX | not measured | ~1.5–2B 8-bit (~1.5–2 GB est.) | Not documented as full-duplex | Maybe (experimental) |
| 9 | Qwen2.5/3/3.5-Omni | [survey](https://arxiv.org/html/2606.19453v1) | 2025–26 | Thinker-talker streaming omni models | — | 3B+ | "Adjacent streaming systems that do not claim full-duplex" | No |
| 10 | MiniCPM-o 4.5 | [FDB search summary](https://www.alphaxiv.org/abs/2503.04721) | 2026 | Omni-modal | — | 8B-class | 76.1 avg on a VoiceBench-style eval | No |
| 11 | FireRedChat | [arXiv 2509.06502](https://arxiv.org/pdf/2509.06502) | 2025 | Cascaded/semi-cascaded full-duplex with pluggable turn controller | — | small controller | Cascade can emulate duplex | Pattern to copy |
| 12 | Cascaded barge-in in practice (mthomas100) | [GitHub](https://github.com/mthomas100/local-voice) | 2026 | Pause playback on first speech frame (median 72 ms), interrupt only once Silero confirms | Audio stopped 238–267 ms after user speech start; interrupt msg at 325–346 ms | — | Faster Silero (0.15 s) → 24 false interruptions in 260 non-speech sounds (coughs/sneezes) | Yes |
| 13 | Open-LLM-VTuber | [GitHub](https://github.com/Open-LLM-VTuber/Open-LLM-VTuber) | 2024– | Interruption without headphones (self-voice suppression) | — | — | — | Yes |

- HumDial (ICASSP 2026) challenge and M3-DuplexBench exist as newer duplex evaluations — [HumDial](https://arxiv.org/pdf/2604.21406); [M3-DuplexBench](https://arxiv.org/pdf/2607.29125)
- Aborting long replies on a recurrent LLM server costs ~1 s replay per 1k tokens — [mthomas100](https://github.com/mthomas100/local-voice) (less relevant with a cloud LLM, but cancel the HTTP stream immediately)

### Inferences
- **Recommendation: cascaded half-duplex with "duck-then-confirm" barge-in.** On first VAD speech frame during bot playback: duck volume / pause (~70 ms); if Silero confirms ≥~200–250 ms of speech and it isn't a backchannel ("haan", "hmm", "acha" — detect via short duration + STT/keyword), stop TTS, cancel LLM stream, flush audio queue; otherwise resume. This reproduces mthomas100's measured ~240–270 ms stop latency without the cough false-positives.
- Echo is the #1 practical blocker for barge-in on a MacBook without headphones: use WebRTC AEC (SmallWebRTC in browser) or macOS voice-processing I/O; gate VAD on AEC'd mic signal.
- Design lessons from full-duplex research worth copying cheaply: (1) explicit backchannel state (Easy Turn); (2) fast responses alone are bad if they interrupt — tune for not cutting the user off (Full-Duplex-Bench); (3) model an "inner monologue"/text plan separately from speech (Moshi) ≈ in a cascade, let the cloud LLM output a short first clause quickly.
- Revisit full-duplex only if a ≤2 GB duplex model with Hindi appears; LFM3-Audio 2B in mlx-audio is the only one in a plausible size class and is unproven.

### Gaps
- No measurement of any full-duplex model on an 8 GB Mac; PersonaPlex RAM figures conflict (~6.4 GB vs ~8 GB).
- No Full-Duplex-Bench numbers for Qwen3-Omni, MiniCPM-o or LFM3-Audio.

---

## 6. Speech emotion recognition (+ fusion with text, personal baseline)

### Takeaway
emotion2vec+ base (~90M params, 9 classes, trained on 4,788 h pseudo-labelled data) is the best size/quality SER model for an 8 GB Mac; emotion2vec+ large (~300M) is better but ~3× heavier. Real-world (naturalistic) SER accuracy is low — ~41% on 8-class MSP-Podcast challenge data, categorical score 0.392 in Vox-Profile — so treat audio emotion as a soft, smoothed signal, fuse it with the transcript (text sentiment via the cloud LLM) and calibrate against the user's own baseline. The best dimensional model (audeering valence/arousal/dominance) is CC-BY-NC-SA (non-commercial).

### Cited Findings

| # | Name | Link | Year | Mechanism | Size / latency | Quality numbers | Output | License / fits 8 GB? |
|---|---|---|---|---|---|---|---|---|
| 1 | emotion2vec+ large | [HF](https://huggingface.co/emotion2vec/emotion2vec_plus_large); [GitHub](https://github.com/ddlBoJack/emotion2vec) | 2024 | data2vec-style SSL emotion representation, fine-tuned on 42,526 h pseudo-labelled data | ~300M params, 16 kHz; utterance or 50 Hz frame-level via FunASR | README claims it beats other popular HF SER models (radar chart only; no numeric table) | 9 classes: angry, disgusted, fearful, happy, neutral, other, sad, surprised, unknown | Code MIT; weights "model-license" (verify); fits but ~1.2 GB fp32 est. |
| 2 | emotion2vec+ base | [GitHub](https://github.com/ddlBoJack/emotion2vec) | 2024 | same, 4,788 h | ~90M params | — | 9 classes | Fits (~0.4 GB fp32 est.) |
| 3 | emotion2vec+ seed | [GitHub](https://github.com/ddlBoJack/emotion2vec) | 2024 | 201 h academic (EmoBox) data | — | — | 9 classes | Weaker; skip |
| 4 | emotion2vec (ACL 2024) | [GitHub](https://github.com/ddlBoJack/emotion2vec) | 2024 | Base representation; cross-lingual results (Mandarin, French, German, Italian…) | — | ACL 2024 paper | features | MIT |
| 5 | SenseVoice-Small (emotion + events) | [GitHub](https://github.com/FunAudioLLM/SenseVoice) | 2024 | Multi-task ASR+SER+AED, non-AR | 5× faster than Whisper-Small; ONNX/GGUF/sherpa-onnx | Zero-shot SER claimed to match/beat best open SER models on its test sets (numbers only in images) | happy, sad, angry, neutral, fearful, disgusted, surprised + events (laughter, cry, cough, sneeze, breath, BGM, applause) | FunASR model license (verify); fits |
| 6 | audeering wav2vec2-large-robust-12-ft-emotion-msp-dim | [HF](https://huggingface.co/audeering/wav2vec2-large-robust-12-ft-emotion-msp-dim) | 2022 | wav2vec2-large-robust pruned 24→12 layers, MSP-Podcast v1.7 | ~165M-class (12 layers); ONNX on Zenodo | CCC not found in this pass | arousal, dominance, valence (~0–1) | **CC-BY-NC-SA-4.0, research only** ([Azure catalog](https://ai.azure.com/catalog/models/audeering-wav2vec2-large-robust-12-ft-emotion-msp-dim)) — OK for personal non-commercial use; flag |
| 7 | Vox-Profile Whisper-large-v3 emotion | [HF](https://huggingface.co/tiantiaf/whisper-large-v3-msp-podcast-emotion); [arXiv 2505.14648](https://arxiv.org/html/2505.14648) | 2025 | Whisper-large-v3 encoder + head on MSP-Podcast v1.12 (card says SAILER pipeline, IS2025 top performer — uploader claim) | ~0.6B encoder (too big) | Categorical 0.392; arousal/valence 0.623/0.649 | categories + dims | Too heavy |
| 8 | Vox-Profile WavLM-large dim | [HF](https://huggingface.co/tiantiaf/wavlm-large-msp-podcast-emotion-dim) | 2025 | WavLM-large, dimensional | ~300M | see paper | arousal/valence/dominance | Fits but heavy; check license |
| 9 | EmoBox benchmark | [arXiv 2406.07162](https://arxiv.org/html/2406.07162) | 2024 | 32 datasets, 14 langs, 10 SSL models | — | Whisper-large-v3 encoder top-1 on 23/32 datasets; IEMOCAP UA: Whisper-v3 73.54, WavLM-L 69.47, HuBERT-L 67.42, wav2vec2-base 58.27; MELD UA 31.54 (Whisper) | benchmark | — |
| 10 | Qwen2-Audio 7B | [mlx-audio](https://github.com/Blaizzy/mlx-audio) | 2024 | Audio-LLM with emotion recognition task | 7B (4-bit MLX) | — | free-text | Too big |
| 11 | INTERSPEECH 2025 naturalistic SER challenge (MSP-Podcast) | [MEDUSA arXiv 2506.09556](https://arxiv.org/pdf/2506.09556); [IS2025 paper](https://www.isca-archive.org/interspeech_2025/uniyal25_interspeech.pdf) | 2025 | WavLM-large baseline; best systems multimodal | — | One trimodal (audio+text+other) system: macro-F1 0.4094, acc 0.4128 on 8-class; trimodal best | — | Real-world ceiling evidence |
| 12 | MemoCMT (text+audio cross-modal transformer) | [Sci Reports](https://www.nature.com/articles/s41598-025-89202-x) | 2025 | Cross-modal fusion | — | Speech+text > either alone | — | Design reference |
| 13 | Cross-modal gated attention, multi-corpus | [ScienceDirect](https://www.sciencedirect.com/science/article/abs/pii/S0167865525000662) | 2025 | Leave-one-corpus-out | — | Single-corpus training overfits | — | Design reference |
| 14 | Speaker normalization for SSL SER | [arXiv 2202.01252](https://arxiv.org/pdf/2202.01252) | 2022 | Remove speaker info from SSL features | — | +0.5% abs speaker-dependent SOTA; speaker-ID acc 60.7%→45.9% | — | Technique |
| 15 | Speaker variability in ER (ICASSP 2012) | [PDF](http://www2.ee.unsw.edu.au/~speechgroup/vidhya/pdf/icassp12.pdf) | 2012 | Speaker-dependent vs independent | — | Speaker-dependent 81.9% vs speaker-independent 55.1%; proposed normalization 70.4% | — | Evidence for personal calibration |
| 16 | "Beyond Accuracy" SER audit | [arXiv 2610.33952](https://arxiv.org/html/2610.33952) | 2026 | Audit of leakage | — | RAVDESS 84.3% with speaker normalization vs 75.7% speaker-disjoint (Pepino et al.) — gains overstated when stats use test data | — | Caution |
| 17 | Emotion-Aware-VoiceAssistant | [GitHub](https://github.com/Rohit-Seera/Emotion-Aware-VoiceAssistant) | 2026 | FastAPI, emotion detection → LLM response, interruptible, ElevenLabs TTS | — | — | — | Licence not published |
| 18 | Hume EVI (commercial reference) | [hume-api-examples](https://github.com/HumeAI/hume-api-examples) | 2024– | Hosted empathic voice | — | — | — | One vendor blog claims EVI shuts down 13 Nov 2026 — **unverified single source** ([forasoft](https://www.forasoft.com/blog/article/real-time-ai-emotion-software)) |

- MSP-Podcast (naturalistic) scores are dramatically lower than acted corpora in EmoBox (single-value extractions ~15.5–22.24 for MSP-Podcast vs 58–74 UA on IEMOCAP; MSP values may be extraction artifacts) — [EmoBox](https://arxiv.org/html/2406.07162)
- Open-LLM-VTuber maps LLM-declared emotions to avatar expressions (output side, not recognition) — [GitHub](https://github.com/Open-LLM-VTuber/Open-LLM-VTuber)

### Inferences
- **Recommendation: emotion2vec+ base (utterance-level, run asynchronously on each finished user turn, ~90M params) + text-side emotion from the cloud LLM + per-user baseline calibration.** Reasons: smallest model trained on large naturalistic pseudo-labelled data, 9 useful classes (angry/sad/happy/neutral/fearful…), MIT code, runs on the already-segmented turn audio so adds no latency to the critical path (run it in parallel with STT; result attached to the LLM prompt as `[voice: tense/angry 0.62, arousal high]`).
- Map Stiti's target states: angry ← angry/disgusted; stressed ← fearful + high arousal + fast speech rate; happy ← happy/surprised; tired ← sad/neutral + low arousal + low energy/slow rate. "Tired" and "stressed" are not native classes — derive them from cheap prosodic features (RMS energy, pitch variance, speech rate from STT word timestamps) relative to the user's baseline.
- **Personal baseline**: keep rolling per-user means/std of emotion2vec+ class logits and prosody features over the last N days; flag only z-score deviations (literature: speaker-dependent ≫ speaker-independent, 81.9% vs 55.1%). Smooth over 2–3 turns (EMA) and require agreement with text sentiment before acting strongly; let the user correct Stiti ("main gussa nahi hoon") and store as labels for a later small calibration head.
- **Fusion**: late fusion is enough — give the cloud LLM both transcript and acoustic tags and let it decide tone; literature consistently shows speech+text > either, and naturalistic SER alone is ~40% on 8 classes.
- Optional upgrade: SenseVoice-Small as a second opinion that also detects laughter/cough/crying events (useful for empathy cues), but it is English/CJK for ASR and has a FunASR model licence. audeering V-A-D is the best arousal/valence model but NC-licensed — acceptable for a personal non-commercial buddy, flag for any commercial path.

### Gaps
- No numeric EmoBox/benchmark table for emotion2vec+ base vs large was retrievable as text (README uses images).
- No SER accuracy data on Indian English / Hinglish speakers; cross-cultural transfer is unknown.
- No measured latency/RAM for emotion2vec+ on Apple Silicon; no MLX/CoreML port found (FunASR PyTorch on MPS/CPU or ONNX export needed).
- audeering CCC numbers not retrieved.

---

## 7. Wake word

### Takeaway
For a free, custom "Hey Stiti", openWakeWord (synthetic-speech training notebook) or LiveKit WakeWord v2 (one-command training, ~7 MB, ~1 ms per 80 ms step, claims far fewer false accepts than openWakeWord on its own benchmark) are the realistic choices. Porcupine is accurate and easy (type the phrase in the console) but is commercial (pricing cited from $6,000/yr). microWakeWord is microcontroller-oriented and scored poorly in LiveKit's comparison.

### Cited Findings

| # | Name | Link | Year | Mechanism | Size / CPU | Accuracy | Custom word | Free? |
|---|---|---|---|---|---|---|---|---|
| 1 | openWakeWord | [GitHub](https://github.com/dscripka/openWakeWord) | 2023 | Frozen Google speech-embedding + small head; trained on synthetic TTS speech | ~29.5 ms CPU per s audio ([LiveKit bench](https://livekit.com/blog/livekit-wakeword)) | Target <0.5 false accepts/h, <5% false rejects; claims > Porcupine on its "alexa" test | Training notebook | Apache-2.0 code (verify pretrained-model licence) |
| 2 | LiveKit WakeWord v2 | [GitHub](https://github.com/livekit/livekit-wakeword); [blog](https://livekit.com/blog/livekit-wakeword) | 2026 | Own architecture (no longer openWakeWord-based); single-command training | Standard ~7 MB ONNX, ~1 ms per 80 ms step, 16.5 ms CPU per s; micro ~451 KB int8 TFLite | Vendor: 0.08 FA/h vs openWakeWord 8.50 FA/h on "hey livekit" | Yes | Open source |
| 3 | Porcupine (Picovoice) | [Picovoice](https://picovoice.ai/products/voice/wake-word/) | 2018– | Proprietary | tiny | 97.3% accept at 1 FA/10 h @10 dB SNR (vendor) | Type phrase in console → .ppn | Commercial; "from $6,000/yr" ([micdrop](https://micdrop.dev/blog/wake-word-detection-web-app)) |
| 4 | microWakeWord | [dev.to comparison](https://dev.to/buguatec/microwakeword-vs-an-online-generator-custom-wake-words-on-the-esp32-s3-g77) | 2024 | TFLite Micro for ESP32 | 2.2 ms CPU per s | 0% at LiveKit's FA operating point (vendor test) | DIY | Free |
| 5 | sherpa-onnx KWS (Zipformer) | [sherpa-onnx](https://k2-fsa.github.io/sherpa/onnx/index.html) | 2023– | Open-vocabulary keyword spotting (phrase as text, no training) | ~3M-param models | No benchmark found | Text-defined | Apache-2.0 |
| 6 | onnx-wakeword (voicute) | [GitHub](https://github.com/voicute/onnx-wakeword) | 2025 | Multi-keyword single model | 128 KB fp32 / 74 KB int8, <5 ms per frame | Self-reported | Yes | Open |
| 7 | EfficientWord-Net | [arXiv 2111.00379](https://arxiv.org/pdf/2111.00379) | 2021 | One-shot (few reference recordings, siamese) | 0.071 ms | 94.51% vs Snowboy 88.43% (authors) | One-shot | Open |
| 8 | Mycroft Precise | [wiki](https://github.com/MycroftAI/mycroft-precise/wiki/Software-Comparison) | 2017 | GRU | — | — | Train offline | Apache-2.0; dormant since 2019 |
| 9 | Howl | [arXiv 2008.09606](https://arxiv.org/pdf/2008.09606) | 2020 | Common Voice trained | — | — | Yes | Open; RPi-oriented, limited data |
| 10 | Snowboy | [EfficientWord-Net paper](https://arxiv.org/pdf/2111.00379) | 2016 | Closed | — | 88.43% (per EWN) | — | Discontinued end-2020, archived |
| 11 | nanowakeword | [libhunt](https://www.libhunt.com/topic/wakeword) | 2025 | Lightweight Python | — | — | Yes | Small project |
| 12 | RealtimeSTT integration | [GitHub](https://github.com/KoljaB/RealtimeSTT) | — | Wraps Porcupine or openWakeWord | — | — | — | MIT |

### Inferences
- **Recommendation: LiveKit WakeWord v2 (custom "Hey Stiti"), with openWakeWord as fallback.** Reasons: free, ~7 MB, ~1 ms per step on one CPU thread (negligible battery), one-command custom training, and the only vendor benchmark shows dramatically fewer false accepts (treat as vendor claim; validate with an hour of your own TV/YouTube/Hinglish chatter audio). sherpa-onnx KWS is a zero-training alternative for quick prototyping. Also consider a hotkey / push-to-talk and "conversation mode" (stay listening for ~30 s after a reply) so the wake word is needed only to start sessions.

### Gaps
- No independent, same-test-set comparison of openWakeWord vs LiveKit vs Porcupine.
- Porcupine free/personal tier limits as of Nov 2026 not verified.
- openWakeWord pretrained-model licence not verified in this pass.

---

## 8. Free cloud fallbacks (STT / speech-to-speech)

### Takeaway
Groq Whisper's free tier (8 h of audio/day) is the best free STT fallback for hard Hinglish; Gemini Live (native audio) is free-tier listed but Google no longer publishes the limits; AssemblyAI and Deepgram give one-time credits only.

### Cited Findings
- Groq Whisper (large-v3, large-v3-turbo) free: 7,200 audio-seconds/hour and 28,800/day per model; 20 RPM, 2,000 RPD; 25 MB file cap; limits per organization (third-party summaries of Groq docs, Apr–Sep 2026; console is authoritative) — [eesel](https://www.eesel.ai/blog/groq-pricing); [localaimaster](https://localaimaster.com/blog/groq-api-free-guide)
- Gemini Live API: older Google quota page listed free-tier Gemini 2.5 Flash Preview Native Audio at 100 concurrent sessions, 1,000,000 TPM; 2026 sources say Google no longer publishes per-model free RPM/RPD and shows them per project in AI Studio; Gemini 2.5 Flash Native Audio listed as free on free tier — [Google quota page](https://ai.google.dev/docs/increase_quota); [benchlm](https://benchlm.ai/md/free-tier/google-ai-studio.md); unresolved forum thread on session limits — [Google AI forum](https://discuss.ai.google.dev/t/official-concurrent-session-rps-limits-for-gemini-live-api-where-are-they-documented/174664)
- AssemblyAI: vendor blog advertises up to 185 h pre-recorded and 333 h streaming free, no card; trackers describe it as $50 credit (~185 h), up to 5 concurrent streams — [AssemblyAI blog](https://assemblyai.com/blog/the-top-free-speech-to-text-apis-and-open-source-engines); [agentdeals](https://agentdeals.dev/vendor/assemblyai)
- Deepgram: $200 free credit (single aggregator, verify) — [costbench](https://costbench.com/compare/assemblyai-vs-deepgram/)
- Free-tier data may be used by providers for training (general caveat, not verified per provider in this pass).

### Inferences
- Use Groq Whisper as the STT fallback (and for any long dictation), and keep Gemini Live as an optional "cloud full-duplex mode" experiment — it would give barge-in and native audio emotion understanding for free but makes Stiti cloud-dependent and limits are opaque.
- AssemblyAI/Deepgram credits are one-time, so not a sustainable zero-cost path.

### Gaps
- Official Gemini Live free-tier daily/session caps for Nov 2026 not found.
- Deepgram official free credit amount not confirmed from Deepgram's own page.

---

## 9. Builder benchmarks on M-series Macs + recommended 8 GB M2 stack (synthesis)

### Takeaway
Every published sub-second local voice agent on a Mac ran on M4/M5 Max-class machines with a local LLM; with the LLM moved to the cloud, an M2 8 GB only needs to host VAD, turn detection, STT, TTS, SER and wake word, which can be kept around 2–2.5 GB if models are chosen carefully. A realistic target on M2 is ~0.9–1.3 s voice-to-first-audio, with instant pre-rendered fillers masking anything slower.

### Cited Findings
- Measured stage budget (M5 Max, warm): VAD stop 200 ms + STT 24–78 ms + Smart Turn 2–40 ms + LLM TTFT 312–353 ms + TTS first chunk 277–292 ms ≈ 874 ms median — [mthomas100](https://github.com/mthomas100/local-voice)
- Measured (M4 Max): Smart Turn hold ~430 ms, STT ~245 ms hidden in hold, LLM TTFT ~810 ms (incl. memory recall ~185 ms), TTS first audio 620–830 ms → 1.4–1.6 s — [Apoorva87](https://github.com/Apoorva87/local-voice-agent)
- Pipecat demo: <800 ms voice-to-voice "with relatively strong models" on M-series — [kwindla](https://github.com/kwindla/macos-local-voice-agents)
- Speech stack peak RSS 3.63 GiB (Parakeet + Kokoro server) — so even "small" stacks can exceed 3 GB if loaded naively — [mthomas100](https://github.com/mthomas100/local-voice)
- Component RSS (M5 Pro): WhisperKit large-v3-turbo 0.4 GB; Parakeet TDT v3 int8 0.9 GB; Qwen3-ASR 0.6B 4-bit 1.0 GB; Kokoro CoreML ~170 MB; Silero 309K params — [soniqo](https://soniqo.audio/benchmarks)
- Smart Turn v3.1 int8 8 MB — [HF](https://huggingface.co/pipecat-ai/smart-turn-v3); LiveKit WakeWord ~7 MB — [GitHub](https://github.com/livekit/livekit-wakeword); emotion2vec+ base ~90M params — [GitHub](https://github.com/ddlBoJack/emotion2vec)
- Cold-start penalties: Kokoro mlx-audio cold run ~7.6 s; Pipecat bot first start 30 s+ — [scottschram](https://github.com/scottschram/kokoro-tts); [kwindla](https://github.com/kwindla/macos-local-voice-agents)

### Inferences
**Recommended local voice stack for Stiti (8 GB M2, ≈2–2.5 GB resident):**

| Layer | Pick | Approx RAM | Why |
|---|---|---|---|
| Orchestrator | Pipecat 1.x + SmallWebRTCTransport (AEC) | Python process | Default Silero+Smart Turn, built-in interruption, Mac reference repos, MIT |
| Wake word | LiveKit WakeWord v2 custom "Hey Stiti" (fallback openWakeWord) | ~10 MB | Free, ~1 ms/step |
| VAD | Silero VAD, stop_secs 0.2 | ~2 MB | <1 ms/chunk, MIT |
| Turn detection | Smart Turn v3.1 int8 + 1.2–2.0 s fallback + filler-aware rule | ~8 MB | Audio-based, Hindi supported, ~12 ms |
| STT | mlx-whisper large-v3-turbo q4 (A/B vs Oriserve Hindi2Hinglish-Apex and Qwen3-ASR 0.6B 5-bit); Groq Whisper fallback | ~0.5–1.0 GB | Only Whisper-family/Qwen3-ASR handle Hinglish; Apex outputs Roman Hinglish |
| LLM | Cloud (Groq/Gemini free tiers) — out of scope here | 0 | — |
| TTS | Kokoro-82M (mlx-audio or kokoro-onnx), sentence streaming, Hindi/Indian voice presets; pre-rendered filler/backchannel bank | ~0.2–0.6 GB | Best quality/latency/RAM, Apache-2.0 |
| SER | emotion2vec+ base async per turn + prosody features + per-user baseline z-scores, fused with LLM text read | ~0.4 GB | Small, 9 classes, MIT code |
| Barge-in | duck-on-first-frame, cancel after ~200–250 ms confirmed non-backchannel speech | — | Measured ~240–270 ms stop in mthomas100 |

- Expected M2 latency budget (estimate): VAD 200 ms + Smart Turn ~20–60 ms + STT ~250–500 ms (overlapped with turn hold where possible) + cloud LLM TTFT ~300–600 ms + Kokoro first sentence ~100–300 ms ≈ 0.9–1.6 s; hitting <1 s reliably needs (a) speculative LLM start on Smart Turn "complete", (b) an instant filler/backchannel clip at turn end when the LLM/tool is slow, (c) all models warm and resident (set `HF_HUB_OFFLINE=1`, preload at login), (d) Interactive QoS priority for the audio/ML processes.
- Load SER and STT lazily on the same process to avoid duplicate PyTorch/MLX runtimes; prefer ONNX/MLX for all components to avoid a PyTorch footprint (emotion2vec+ is PyTorch/FunASR — consider ONNX export).

### Gaps
- No public benchmark of a complete local voice agent on a base M2 with 8 GB; all numbers above are extrapolated from M4/M5 Max/Pro measurements.
- No measured RAM for emotion2vec+ base on Apple Silicon or for a combined Whisper+Kokoro+emotion2vec+ process on MLX.
