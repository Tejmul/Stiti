# Hearing and speaking Indian English: STT + TTS for Tejmul's accent (research, 2026-11-11)

**Questions.** (1) Speech-to-text mishears Tejmul (Indian accent, English with Hindi words). Examples from his log
(whisper-small q4 via mlx, `language="en"`, Hinglish initial prompt, `src/stiti/voice/stt.py`): "Tejmul" → "Tejmal",
"Newton School of Technology" → "Newton's Club of Technology", "Karang li am preparing for placements" (garbled
"Currently"), "The curzle turns into square" (cursor), short "So..." fragments. Which **free** engine and settings work
best and still keep voice-to-first-audio < 1 s? (2) He finds the Hindi voice "not suitable at all". He wants Stiti to
speak **English with an accent that suits Indian speech**. Which voice should do that, and what happens to Hindi words
inside English replies?

Builds on [hinglish_voice.md](hinglish_voice.md), which covered Hindi/Hinglish TTS + STT options and the D22 code-switch
phonemizer. This doc does not redo that work. It adds Indian-*English*, the owner-vocabulary biasing, and real
measurements for ~20 engine/setting combinations on this M2 (8 GB).

## Method (how the numbers were made)
- **No recordings of his voice exist**, so the test set is synthetic Indian-accented speech: **22 sentences × 5 voices
  = 110 clips** (1.2–4.5 s, mean 3.1 s), with **pink noise + 50 Hz hum at 20 dB SNR** and 0.3 s of lead/tail.
  - Sentences: his 6 log lines (the reference text is my best guess of what he meant: "Currently I am preparing for
    placements", "Talk to me in English or Hindi?", "Hey bhai, padhai kaisi chal rahi hai?") + 10 English commands
    ("Remind me at 4 to start my resume", "Is any new research paper published?", "Add buy milk to my todos"…) + 6
    Hinglish commands ("Kal subah 6 baje alarm laga do", "Mera DSA ka contest kab hai?"…).
  - Voices: Kokoro `hf_alpha` and `hm_omega` (Hindi voices; Hinglish lines go through Stiti's own mixed phonemizer),
    macOS `Rishi` (en-IN), and **goonj-1-82M `en_arjun` / `en_priya`**, which were trained on Indian-English speech.
    macOS `Tara`/`Aman` were dropped because their output is broken on many lines. Every engine, including Groq
    large-v3, heard "Stiti, open my GitHub" spoken by Aman as "Pierre Clovis Thermal P … Sierra Leone".
- **WER** is computed after lowercasing, removing punctuation, mapping digits to words, folding "to-dos" to "todos",
  and folding Roman Hindi spelling variants to one form using Stiti's own `hinglish.LEX`, so kya = kia and hai = he.
  **Owner terms heard** counts how many of Tejmul, Stiti, Newton School of Technology, placements, cursor, todos,
  resume, GitHub, DSA, mummy and Rahul (90 occurrences in the set) came out right.
- **Latency** is the warm wall-clock time for the whole clip on the M2. Whisper is not streaming, so this is the time
  from end of speech to text. RTF = latency / clip length. RSS is the peak resident memory of the test process.
- **Prompts** compared: `none`; `hinglish` = today's `HINGLISH_PROMPT`; `owner` = `"Glossary: Stiti, Tejmul, Newton
  School of Technology, placements, DSA, GitHub, todos, resume, cursor."` + today's prompt. "Rahul" was left out on
  purpose as a control.
- **Caveat:** synthetic speech is cleaner and more regular than a real mic in a real room. On this set every engine
  already heard "Newton School" and "cursor" correctly. Absolute WER on his real voice **will be higher**. Use the
  *ranking* and the *deltas*, and re-run the harness on his own clips (see Next steps).

## (A) STT — live measurements (this Mac, M2 8 GB, 2026-11-11, 110 clips)
| # | Engine (runtime) | Prompt / bias | WER all | his 6 log lines | 10 cmds | 6 Hinglish | owner terms | p50 ms | p90 ms | RTF | RSS MB |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | whisper-small q4 (mlx) | none | 30.3 | 13.0 | 11.6 | **83.0** | 44/90 | 250 | 278 | 0.08 | 499 |
| 2 | whisper-small q4 (mlx) — **today** | hinglish | 12.4 | 9.2 | 9.9 | 20.5 | 64/90 | 259 | 285 | 0.08 | 499 |
| 3 | whisper-small q4 (mlx) | **owner** | **9.7** | **4.9** | 8.4 | 17.0 | 75/90 | 271 | 303 | 0.08 | 499 |
| 4 | ↳ + glossary snap post-fix (below) | owner | **9.1** | | | | **80/90** | +<1 | | | 0 |
| 5 | whisper-small 8-bit / fp16 (mlx) | owner | 10.4 / 9.9 | 6.5 / 6.5 | 7.8 / 6.8 | 19.0 / 19.0 | 74–75/90 | 270 | 300 | 0.08 | 713 / 895 |
| 6 | whisper-base q4 (mlx) | owner (hinglish: 49.4!) | 17.9 | 16.8 | 8.6 | 37.5 | 66/90 | **90** | 102 | 0.03 | 413 |
| 7 | whisper-medium q4 (mlx) | hinglish / **owner** | 7.6 / **5.6** | 8.6 / 3.2 | 6.6 / 5.6 | 8.5 / **8.0** | 62–73/90 | 749 | 791 | 0.23 | 781 |
| 8 | whisper-large-v3-turbo q4 (mlx) | hinglish / owner | 7.2 / 7.7 | 5.9 / 3.8 | 1.3 / 1.8 | 20.0 / 23.0 | 67–69/90 | 1,035 | 1,050–1,795 | 0.33 | 705 |
| 9 | whisper-large-v3-turbo 8-bit / fp16 (mlx) | hinglish / owner | 7.6 / 7.7 | 9.2 / 5.9 | 3.0 / 4.1 | 15.0 / 16.5 | 63–66/90 | 990–1,040 | 1,080 | 0.31–0.33 | 789 / 1,459 |
| 10 | distil-whisper-large-v3 (mlx) | any (prompt ignored) | 31.0 | 21.1 | 8.1 | 85.5 | 45/90 | 950 | 1,400 | 0.30 | 846 |
| 11 | **Oriserve Whisper-Hindi2Hinglish-Swift** fp16 (converted to mlx by me) | none / hinglish | 14.5 / 12.4 | 6.5 / 4.9 | 16.7 / 15.2 | 17.5 / **14.0** | 40–44/90 | **86** | 98 | **0.03** | 383 |
| 12 | ↳ same, q4 | none / hinglish / owner | 16.4 / 14.0 / **25.3** | | | | 38–42/90 | 80 | 90 | 0.02 | 274 |
| 13 | Groq whisper-large-v3-turbo (cloud) | none / hinglish / owner | 30.3 / 9.2 / 11.5 | 20.5 / 9.7 / 17.3 | 7.6 / 6.6 / 7.6 | 84 / 14 / 14 | 47–49/90 | **217–262** | 250–330 | 0.07–0.08 | 0 |
| 14 | **Groq whisper-large-v3** (cloud) | owner | **5.5** (4.7 with post-fix) | **3.2** | **4.6** | 9.5 | 66/90 | 297 | 327 | 0.09 | 0 |
| 15 | Apple SpeechTranscriber **en-IN** (macOS 26, on-device) | none / contextualStrings | 13.3 / 13.3 | 9.2 | 7.3 | 29.0 | 45/90 | **173** | 222 | 0.06 | ~0 in-process |
| 16 | Apple SpeechTranscriber en-US | none | 15.5 | 8.6 | 9.9 | 33.0 | 43/90 | 161 | 198 | 0.05 | ~0 |
| 17 | Apple DictationTranscriber en-IN | none / contextualStrings | 15.5 / 14.4 | 9.2 / 7.6 | 16.5 / 14.9 | 19.5 | 36–41/90 | 250–311 | 380–424 | 0.08–0.10 | ~0 |
| 18 | NVIDIA Parakeet-TDT-0.6B-v3 (parakeet-mlx) | none (no hook) | 26.4 | 17.8 | 7.3 | 72.0 | 46/90 | 156 | 192 | 0.05 | 712 |
| 19 | Moonshine-base v1 (transformers, CPU) | none | 34.1 | 25.9 | 11.1 | 87.0 | 47/90 | 110 | 148 | 0.03 | 426 |
| 20 | NVIDIA Nemotron-3.5-ASR-streaming-0.6B 8-bit (mlx-audio), `en-US` / `hi-IN` | none | 32.7 / 78.6 | 17.3 | 12.7 | 86.5 / 33.0 | 41/90 / 0 | 180–188 | 227–237 | 0.06 | 934–1,078 |
| 21 | **Hybrid:** #3 local, escalate to #14 when Whisper's mean `avg_logprob` < −0.5 or text is empty | owner + post-fix | **6.3** | | | | | **272** | **598** | | 499 |
| 22 | ↳ same, threshold −0.4 | | **5.1** | | | | | 273 | 602 | | |

Escalation rate for #21: 18/110 turns (16%). For #22: 27/110 (25%). The hybrid rows are simulated from the saved
per-clip results of #3 and #14 (local latency + Groq latency on escalated turns).

**What the numbers say**
- **The prompt is most of the win, and the prompt must carry his vocabulary.** With no prompt, `language="en"`
  **translates** Hinglish into English: "Kal subah 6 baje alarm laga do" → "tomorrow morning 6 o'clock alarm"; "Aaj
  bahut kaam tha yaar…" → "Today was a very good day, I am tired". Hinglish WER is 81–87% for every English-forced
  model. Today's Hinglish prompt brings small q4 to 12.4%. Adding a **9-word owner glossary** brings it to **9.7%**, with
  **"Tejmal" → "Tejmul" on all 5 voices** and "playsa mains" → "placements". The cost is +12 ms.
- **Without the glossary, engines almost always write "Tejmal"** ("Tajmal", "Mahal", "Mal"): 0/5 for every local
  Whisper size, Swift, Parakeet, Nemotron, Moonshine and Groq turbo, and 1/5 for Apple en-US. With it: small, medium
  5/5; turbo, base and Groq large-v3 4/5; Groq turbo still 0/5. Names are a biasing problem, not a model-size problem.
- **Groq: large-v3 honours the glossary, turbo mostly ignores it.** large-v3 heard 66/90 owner terms, turbo 49/90,
  and turbo still wrote "Tejmal" with the glossary. With the long Hinglish prompt, Groq turbo also produced a
  **prompt echo**: "Remind me to call mummy. Remind me to call mummy. Remind me to call mummy." for "Currently I am
  preparing for placements". Local turbo q4 turned 3 s of pure noise into "Aaj bahut kaam tha yaar." (a prompt
  sentence), and turbo/distil without a prompt turned it into "Thank you.". So prompts should hold words, not whole
  sentences, and outputs that copy the prompt must be rejected.
- **Local turbo is not worth it here.** On this M2 it takes ~1,035 ms (q4, 8-bit and fp16 all about the same) for
  7–8% WER, which is the same quality as **Groq large-v3 at 297 ms**. medium-q4 + owner (5.6%, 749 ms) is the best
  fully-offline option, but 750 ms of STT alone blows the < 1 s voice-to-first-audio budget.
- **Quantization barely matters for small** (q4 9.7 / 8-bit 10.4 / fp16 9.9). Keep q4: half the RAM of 8-bit.
- **Oriserve Swift** (whisper-base fine-tuned on ~550 h of noisy Indian audio, Roman Hinglish output) is the **fastest
  usable model: 86 ms**. It is the best on Hinglish *without any prompt* (14–17.5%). But it cannot take a glossary (the
  owner prompt makes it worse, 25.3%), it misses names (40/90) and it is weak on English commands (15–17%). Good as a
  second opinion or wake model, not as the main ear. My own HF→MLX converter matched the original PyTorch output
  (15.4% torch-CPU at 317 ms vs 14.5% MLX at 86 ms).
- **Apple's on-device SpeechTranscriber en-IN** is free, already installed on this Mac
  (`SpeechTranscriber.installedLocales` includes `en-IN`), adds no RAM to Stiti's process, and runs in 173 ms with
  13.3% WER. It is a decent fallback. But it hears "Hey Stiti" as "Hey Siri" and capitalises every Hindi word.
  `contextualStrings` changed nothing for SpeechTranscriber and helped DictationTranscriber only slightly
  (15.5 → 14.4).
- **Parakeet, Moonshine and Nemotron are English-strong but Hinglish-dead** (72–87% on Hinglish lines). Nemotron
  `hi-IN` writes Devanagari, so Stiti's Roman-script brain can't use it. Moonshine v1 base hallucinates on accent
  (25.9% on his lines). This matches hinglish_voice.md: only the Whisper family hears both languages in Latin script.
- **One silent drop:** with today's filter (drop the text if `avg_logprob < -1.2`), small-q4 returned **empty** for one
  goonj-voice "Add buy milk to my todos". The owner-prompt run heard it. Dropping low-confidence turns loses commands.
  Escalate them instead.

**Glossary snap post-correction** (`scratchpad/stt/postfix.py`). For each owner term, compare same-length word spans by
consonant skeleton (first letter + consonants, repeats collapsed; SequenceMatcher ≥ 0.8). Never rewrite a word found in
`/usr/share/dict/words`, and skip terms with a skeleton shorter than 3 letters (DSA). Measured fixes: Tajmal → Tejmul,
tadoos/todoos → todos. Early versions that allowed wider spans ate neighbouring Hindi words ("tadoos kya" → "todos";
"today's" → "todos"), so it stays this strict. Gain: 9.7 → 9.1 WER, 75 → 80/90 terms. It is cheap (< 1 ms) and is the
right home for names Whisper has never seen. "todos" itself is the hardest word in the set ("to-dos / daughters /
tattoos / orders"). A Laya/fast-path synonym ("to do", "to-dos", "todo list") helps more than any STT change.

## (B) STT options compared (≥10 papers / architectures)
| # | Option | Mechanism | Strengths | Weaknesses | Free + 8 GB M2? |
|---|---|---|---|---|---|
| 1 | **whisper-small q4, mlx** (today) | 244M enc-dec, 680k h weak supervision; `initial_prompt` = decoder prefix | 271 ms; takes a prompt; Roman Hinglish with `en` | weak on hard accents without biasing | ✅ keep |
| 2 | whisper-medium q4, mlx | 769M | best offline WER (5.6%) | 749 ms; 781 MB | 🟡 offline/night re-transcribe only |
| 3 | whisper-large-v3-turbo (q4/8b/fp16), mlx | 32-layer encoder, 4-layer decoder | good WER | ~1.0 s on M2 (the encoder dominates), prompt echo on noise | ⛔ per-turn |
| 4 | distil-whisper-large-v3 | 2-layer distilled decoder, **English-only training** | fast on GPU | translates Hinglish; ignores prompt; 950 ms on M2 | ⛔ |
| 5 | **Oriserve Hindi2Hinglish-Swift** | whisper-base FT on ~550 h noisy Indian speech, Roman output | **86 ms**, best no-prompt Hinglish | no names/glossary; weak English cmds | 🟡 2nd opinion / wake |
| 6 | Oriserve Hindi2Hinglish-Prime/Apex | large-v3 FT (1.5B) | reported 28.7 FLEURS-Hinglish vs 50.8 base | ≥ turbo latency, 3 GB fp16 | ⛔ local; not hosted free |
| 7 | **Groq whisper-large-v3** | hosted large-v3 on LPU | **5.5% WER at 297 ms**, honours glossary | audio leaves the Mac; 2k req/day, 28.8k audio-s/day; 10 s minimum billed per request | ✅ escalation lane |
| 8 | Groq whisper-large-v3-turbo | hosted turbo | 217–262 ms | ignores glossary, prompt echo | 🟡 prefer large-v3 (+40 ms) |
| 9 | **Apple SpeechTranscriber en-IN** (macOS 26) | on-device OS model, ANE | 173 ms, 0 RAM in-process, installed, private | no biasing effect, "Siri" confusion, Swift helper needed | ✅ fallback ear |
| 10 | Apple SFSpeechRecognizer `hi-IN-translit` | legacy on-device/server ASR with Roman Hindi output | listed by `supportedLocales()` on this Mac | needs TCC speech permission + app bundle; not tested | 🟡 try later |
| 11 | NVIDIA Parakeet-TDT-0.6B-v3 | FastConformer-TDT, 25 EU languages | 156 ms, strong English | no Hindi; 72% on Hinglish; no prompt | ⛔ |
| 12 | NVIDIA Nemotron-3.5-ASR-streaming 0.6B (2026-06) | cache-aware streaming FastConformer-RNNT, 40 locales incl. hi-IN, 80–1,120 ms chunks | real streaming, 180 ms | en-US mode fails Hinglish, hi-IN → Devanagari; ~1 GB; NVIDIA Open Model License | ⛔ now; watch the Hinglish FT (`addyo07/nemotron-3.5-0.6b-hinglish`, self-reported 24.6% Hinglish WER) |
| 13 | Moonshine v1 base / v2 streaming | encoder w/o positional emb.; v2 sliding-window streaming (arXiv 2602.12241) | 110 ms (v1); v2 reports 148–258 ms on M3 | English-only; 34% here | ⛔ |
| 14 | whisper.cpp + Core ML encoder | ggml decoder + ANE encoder | Core ML encoder ">3× vs CPU" (README) | same model limits; no faster than mlx on M-series GPU in public benchmarks | 🟡 not needed |
| 15 | faster-whisper `hotwords` | CTranslate2 Whisper with a hotword prefix | real hotword API | CPU-only on Mac (no Metal) → slower than mlx | ⛔ |
| 16 | AI4Bharat IndicWhisper / IndicConformer | Indic fine-tunes (Vistaar, arXiv 2305.15386) | best pure-Hindi WER | Devanagari output, 600–769M | ⛔ wrong script |
| 17 | Sarvam Saaras/Saarika | Indic-tuned cloud with codemix mode | best-in-class Hinglish | paid after ₹100 credit | ⛔ not free |
| 18 | Svarah benchmark (arXiv 2305.15760) | 9.6 h Indian-accented English, 117 speakers | Whisper base 13.6 / medium 8.3 / large 7.2 WER; Azure/Google IN 20–21 | — | evidence: Whisper family is the right family |
| 19 | Biasing: Whisper prompt (arXiv 2410.18363) | glossary as decoder prefix; 224-token cap; later tokens weigh more | zero training | long prompts → hallucination/echo | ✅ used (#3) |
| 20 | Biasing: CB-Whisper (arXiv 2309.09552) | KWS on audio picks which entities to put in the prompt | scales to big name lists | needs a KWS model | 🟡 later, when the glossary is > ~40 terms |
| 21 | Biasing: TCPGen / trie decoding (arXiv 2306.01942, 2508.17796) | pointer-generator or trie over rare words, TTS-made pronunciations | strong rare-word recall | changes the decoder; research code | 🟡 too invasive now |
| 22 | Biasing: post-ASR lexicon snap (ours) | fuzzy match to the owner's glossary | +5 terms, <1 ms, model-agnostic | can't fix what is far off | ✅ add |

## (C) TTS — Indian-accented English voice, live measurements
Two sentences per option. S1 = "Hey Tejmul, your meeting with the placement team is at three thirty. Should I remind you
at three?". S2 = "Okay yaar, I added buy milk to your todos. Aaj ka plan is ready, so let's start." (English with
Hindi words). **Intelligibility proxy:** 5 English reply sentences + S2 → whisper-large-v3-turbo q4, no prompt,
`language="en"` (a strong "listener") → WER. Like hinglish_voice.md, this checks clarity, not beauty. All voices hit
the ceiling on plain English (3.6–7.1%), so **listen to the samples**. "Clean" latency = idle machine, 20 first clauses
of 2–7 words, warm, p50.

| # | Voice option | Phonemes | First chunk p50 (clean) | Full S1 (5.5 s audio) | EN WER | S2 WER / what was heard | Size / RSS | License / cost | Verdict |
|---|---|---|---|---|---|---|---|---|---|
| 1 | Kokoro `af_heart` (**today, English**) | espeak en-us | **291 ms** | 833 ms (RTF 0.15) | 7.1 | 0 — "Okay, **Yar**… **Aj-ka** plan" (American) | 88 MB / 370 MB | Apache-2.0 | baseline, US accent |
| 2 | Kokoro `hf_alpha` speaking English | en-us | 321 ms | 835 ms | 5.4 | 12 — "Okay **yore**… **tadoos**" | same | Apache, grade C voice | Indian timbre, US vowels |
| 3 | Kokoro `hf_beta` / `hm_omega` English | en-us | ~440 ms* | ~1,070 ms* | 7.1 / 5.4 | 6 / 12 | same | grade C | same as #2 |
| 4 | Kokoro `bf_emma` (British) | en-gb | ~480 ms* | ~1,020 ms* | 5.4 | 18 — "**Arj car** plan" | same | grade B- | not Indian |
| 5 | Kokoro Hindi voice + Hindi words in `hi`, rest en-us (≈ **today's D22 Hinglish path**) | mixed | ~510 ms* | ~1,430 ms* | 5.4 | 6 — "tadous" | same | — | what he called "not suitable" |
| 6 | Kokoro + my "Indianized" phoneme rules (retroflex t/d, ʋ, tapped r, eː/oː, no θ/ð) | rewritten en-us | ~460–600 ms* | ~1,260 ms* | 7.1 (af_heart: 21.4) | **24–29** — "yaar" dropped, "taroos" | same | — | ⛔ rejected: a rule hack doesn't make an accent |
| 7 | **goonj-1-82M** (Kokoro FT on Indian-English + Hindi personas), PyTorch CPU | misaki US + hi | 566–1,132 ms* | 1,078–2,581 ms* | 5.4 | **0–6** | 330 MB .pth | Apache-2.0 | right voice, wrong runtime |
| 8 | **goonj-1-82M → ONNX int8 (exported by me), Stiti's own `kokoro_onnx` runtime**, `en_arjun` / `en_priya` / `en_tara` | Stiti's mixed phonemizer (espeak en-us + hi) | **269 / 275 ms** (p90 337–352) | **715–785 ms (RTF 0.13)** | 5.4–7.1 | **0 on all three** — "Okay yaar, I added buy milk to your to-dos. Aaj ka plan is ready" | **114 MB / 430 MB** | Apache-2.0 (data synthetic, see below) | ✅ **recommended** |
| 9 | goonj ONNX fp32 | same | ~740 ms* | ~1,700 ms* | same | same | 325 MB | — | int8 is free speed |
| 10 | macOS `say` Rishi (en-IN) | Apple | 624 ms (process spawn + file) | — | 5.4 | 12 — "**Tordas**" | 0 | free, OS | 🟡 robotic, slow via CLI |
| 11 | macOS Tara / Aman (en-IN), Lekha (hi-IN) | Apple | 655–1,019 ms | — | 5.4–10.7 | Aman **82 (gibberish)**, Tara 18, Lekha 12 | 0 | free | ⛔ Aman/Tara unreliable |
| 12 | Piper `en_IN` (navgurukul, SPICOR Indian-English data) | espeak en-us | **64 ms** | **141 ms** | 7.1 | 24 — "bay milk… to dues" | 63 MB | **AGPL-3.0** | 🟡 fastest; one LJSpeech-based voice, flatter |
| 13 | edge-tts `en-IN-NeerjaNeural` / `PrabhatNeural` | Microsoft neural, cloud | 884–932 ms (network) | — | 3.6 / 7.1 | 6 | 0 | free but unofficial; text leaves the Mac | ⛔ P0 fallback at most |
| 14 | Pocket-TTS Indian English (`prasadvittaldev/…-indictts`) | Kyutai pocket-tts FT, 110M, int4 86 MB, CPU real-time | not run | — | — | — | 86 MB | MIT | 🟡 watch (reference sample saved) |
| 15 | Indic Parler-TTS (AI4Bharat) | T5 + Parler decoder, 0.9B, prompt-described speakers incl. Indian English | 2.6 s+ per line on an L4 GPU (reported) | — | — | — | ~4 GB | Apache-2.0 | ⛔ RAM + speed |
| 16 | Groq `canopylabs/orpheus-v1-english` | hosted Orpheus 3B | not run | — | — | — | 0 | free 10 RPM / 100 req/day; American voices | ⛔ wrong accent, tiny quota |
| 17 | `jeevav62/kokoro-82m-indian-en` (single-speaker Kokoro FT) | — | — | — | — | — | — | repo now empty/private | ⛔ unavailable |
| 18 | Veena / Svara (3B Llama → SNAC) | LLM-style TTS | slow on M2 | — | — | — | 3B | Apache | ⛔ = a local LLM (Tejmul's rule) |

\* measured while STT benchmarks ran in parallel. These are relative numbers, roughly 1.5× the clean figures.

**Why goonj wins.** It is the same 82M StyleTTS2/Kokoro architecture Stiti already runs, so the exported ONNX drops
into `kokoro_onnx.Kokoro(model, voices)` with only config changes: two file paths and the voice names
(`STITI_VOICE`, `STITI_HI_VOICE`). It is *faster* than today
(first chunk 269–275 ms vs 291 ms for `af_heart`; RTF 0.13 vs 0.15). It costs +60 MB RSS. And its 10 `en_*` personas
were trained on **Indian-English** audio, so the accent comes from the voice itself, not from phoneme tricks (option
#6 proves that tricks fail). The same personas were also trained on romanized Hinglish (~690 clips) and Devanagari
Hindi, so Hindi words in S2 came out cleanly ("Okay yaar… Aaj ka plan") in **all three personas (S2 WER 0%)**. Every
Kokoro stock voice scored 6–18% there, and the stock Hindi voices are graded C by Kokoro's author. Caveats from the
model card: the training data is synthetic (personas created with ElevenLabs, bulk audio from Fish Audio S2 Pro), so
some quirks carry over, and English phonemes are US-based. It is fine for personal local use, but re-check the
upstream terms before any public build.

## Recommendation
**(a) STT — keep whisper-small q4 locally, give it his vocabulary, and escalate hard turns to Groq large-v3.**
1. Keep `mlx-community/whisper-small-mlx-q4` with `language="en"`, `temperature=0`, `condition_on_previous_text=False`.
2. **Owner glossary prompt, built by the brain, not hard-coded.** Write `"Glossary: <terms>."` + **one** short
   Hinglish line (drop most full sentences, which are the source of the prompt echoes). Terms come from `USER.md` + the
   top knowledge-graph entities: his name, Stiti, college, people, projects, and recurring nouns like todos, DSA,
   placements, resume. Cap at ~40 terms (< 150 tokens; Whisper's prompt limit is 224) and put the most important last.
   Measured: 12.4 → 9.7% WER, owner terms 64 → 75/90, cost +12 ms.
3. **Glossary snap post-fix** (consonant-skeleton match, dictionary words never rewritten): 9.7 → 9.1%, terms → 80/90,
   < 1 ms.
4. **Escalate, don't drop.** If mean `avg_logprob` < −0.5, or the text is empty while VAD heard speech, or Laya can't
   parse an intent: re-send the same audio and glossary to **Groq `whisper-large-v3`** (not turbo: it follows the
   glossary). Wait at most ~700 ms, then use the local text. Simulated on this set: **WER 6.3%, p50 272 ms, p90 598 ms,
   16% of turns escalated**. A −0.4 threshold gives 5.1% at 25% escalated. Daily cost at ~100 turns/day ≈ 16–25
   requests × 10 s billed minimum, under 1% of the 28,800 audio-s/day quota. Privacy: audio leaves the Mac only on
   escalated turns. Groq doesn't train on API data. Add a `STITI_STT_CLOUD=off` switch, and never escalate while the
   mood or context is marked P2.
5. **Prompt-echo guard:** reject a transcript that equals the prompt, contains a prompt sentence, or repeats the same
   clause 3+ times (seen on Groq turbo and on local turbo with noise). Treat it as "no speech" or escalate.
6. Fallback ear when the GPU is busy or MLX fails: Apple SpeechTranscriber `en-IN` (173 ms, 13.3%) through a tiny
   Swift helper (`scratchpad/stt/apple_stt.swift` works without any permission prompt).
7. Not now: local turbo (1 s), distil (English-only), Parakeet / Moonshine / Nemotron (no Hinglish), medium for live
   turns (750 ms). Possible later: medium-q4 to re-transcribe the day's low-confidence turns at night for memory, and
   Oriserve Swift (86 ms) as a Hinglish second opinion.

Total voice budget with this STT: VAD end 300 ms + STT 272 ms p50 (598 ms p90) + LLM first token ~190 ms (Groq Qwen,
free_llm_providers.md) + TTS first chunk ~270 ms ≈ **1.0 s p50**. Fast-path actions skip the LLM (≈ 0.85 s). The
escalated p90 turn is ~1.3 s, so play the "hmm" filler (voice_latency.md) when escalating.

**(b) Voice — switch Stiti to goonj-1-82M, Indian-English persona, ONNX int8, one voice for everything.**
1. One-time export (`scratchpad/tts/goonj_export.py`, run in a throwaway `uv run --with kokoro` env) →
   `~/.stiti/models/voice/goonj.int8.onnx` (114 MB) + `goonj-voices.bin` (15 personas). Load them with the existing
   `Kokoro(...)`. Keep Kokoro `af_heart` as the fallback if the files are missing.
2. Tejmul picks the persona by ear: **`en_priya`** or **`en_tara`** (female), **`en_arjun`** (male). Set
   `STITI_VOICE=en_priya`.
3. **Hindi words inside English replies:** keep D22's lexicon routing (lexicon words → espeak `hi` phonemes, the rest →
   `en-us`), but **speak the whole line with the same Indian-English persona** (`STITI_HI_VOICE` = the same persona).
   Never switch mid-conversation to `hf_alpha`/`hm_omega`, which is what he heard as "not suitable". Measured: S2
   heard perfectly by all three personas. Tell the LLM persona: "English by default; an occasional Hindi word (yaar,
   accha, chalo) is fine; reply in Hinglish only when he speaks Hinglish."
4. Do **not** use the Indianized-phoneme rules (#6): less intelligible, and they drop Hindi words.
5. Record as a decision (proposed D25) **after** he listens to the samples below.

## Listening samples (2 sentences each; s1 = English, s2 = English with Hindi words)
All in `/private/tmp/claude-501/-Users-tejmul-Desktop-Stiti/0e6c0a17-f92d-4e80-a621-98bf58ea090b/scratchpad/samples/indian_english/`
(the session scratchpad is temporary; copy anything worth keeping):
- **Recommended, goonj ONNX int8:** `go_en_priya_int8_s1.wav`, `go_en_priya_int8_s2.wav`, `go_en_arjun_int8_s1.wav`,
  `go_en_arjun_int8_s2.wav`, `go_en_tara_int8_s1.wav`, `go_en_tara_int8_s2.wav` (fp32: `go_*_fp32_s*.wav`; PyTorch
  originals: `g_en_priya_s*.wav`, `g_en_arjun_s*.wav`, `g_en_tara_s*.wav`, `g_en_kabir_s*.wav`; the model author's own demo:
  `ref_goonj_en_priya_official.wav`)
- Today: `k1_af_heart_us_s1.wav`, `k1_af_heart_us_s2.wav`; today's Hinglish path: `k9_hf_alpha_us_hiwords_s1.wav`,
  `k9_hf_alpha_us_hiwords_s2.wav`
- Kokoro Hindi voices speaking English: `k2_hf_alpha_us_s*.wav`, `k3_hf_beta_us_s*.wav`, `k4_hm_omega_us_s*.wav`; British:
  `k5_bf_emma_gb_s*.wav`; Indianized-phoneme hack: `k6_hf_alpha_indianized_s*.wav`, `k7_hm_omega_indianized_s*.wav`,
  `k8_af_heart_indianized_s*.wav`
- macOS: `m_Rishi_s*.wav`, `m_Tara_s*.wav`, `m_Aman_s*.wav`, `m_Lekha_s*.wav`; Piper en_IN: `p_piper_en_IN_s*.wav`;
  edge-tts (cloud): `e_NeerjaNeural_s*.mp3`, `e_PrabhatNeural_s*.mp3`; Pocket-TTS Indian male (author's sample):
  `ref_pocket_tts_indian_male_int4.wav`

STT test clips (110 noisy 16 kHz wavs + `meta.json`): `…/scratchpad/stt/clips/`. Per-clip results: `…/scratchpad/stt/results/`,
summary `…/scratchpad/stt/aggregate.json`. TTS round-trip: `…/scratchpad/tts_rt/rt_results.json`.
Scripts: `stt/gen_clips.py`, `gen_clips2.py`, `eval_mlx.py`, `eval_groq.py`, `eval_apple.py` + `apple_stt.swift`,
`eval_other.py`, `hf2mlx.py` (HF Whisper → mlx converter), `postfix.py`, `aggregate.py`; `tts/kokoro_variants.py`,
`goonj.py`, `goonj_export.py`, `goonj_onnx_run.py`, `piper_in.py`, `other_tts.py`, `rt_eval.py`, `latency_clean.py`.
If the A/B is adopted, move the harness into `tests/` or `scripts/`.

## Next steps
1. **Record his real voice** (the biggest gap). Keep it opt-in and local: save the audio of low-confidence or
   corrected turns to `~/.stiti/voice_eval/` with the corrected text, plus a 30-line read-aloud script (his log lines +
   commands). Re-run `eval_mlx.py`/`eval_groq.py` on it, then re-tune the escalation threshold and glossary.
2. Build the glossary generator from the brain (USER.md + top graph entities), and add the snap post-fix and
   prompt-echo guard in `stt.py`.
3. Groq large-v3 escalation lane with a 700 ms cap and a privacy switch.
4. goonj ONNX int8 voice after he picks a persona (+ D25), with Kokoro as the fallback.
5. Watch: the Nemotron-3.5 Hinglish fine-tune (streaming, ~0.5 s), Pocket-TTS Indian voices, Apple `hi-IN-translit`.

## Sources
- Svarah, Indian-accented English ASR benchmark (arXiv 2305.15760): https://arxiv.org/pdf/2305.15760 · https://github.com/AI4Bharat/Svarah
- Vistaar / IndicWhisper (arXiv 2305.15386): https://github.com/AI4Bharat/vistaar
- Whisper prompt biasing limits (arXiv 2410.18363): https://arxiv.org/pdf/2410.18363
- CB-Whisper, KWS-driven prompts (arXiv 2309.09552): https://arxiv.org/abs/2309.09552
- TCPGen with Whisper (arXiv 2306.01942): https://arxiv.org/abs/2306.01942 · trie biasing with TTS pronunciations (arXiv 2508.17796): https://arxiv.org/html/2508.17796v1
- Oriserve Swift / Prime: https://huggingface.co/Oriserve/Whisper-Hindi2Hinglish-Swift · https://huggingface.co/Oriserve/Whisper-Hindi2Hinglish-Prime
- mlx-whisper models: https://huggingface.co/mlx-community (whisper-small-mlx-q4, -8bit, whisper-medium-mlx-q4, whisper-large-v3-turbo(-q4/-8bit), distil-whisper-large-v3)
- Groq STT models + limits: https://console.groq.com/docs/rate-limits · https://console.groq.com/docs/model/whisper-large-v3-turbo
- Apple SpeechAnalyzer / SpeechTranscriber: https://developer.apple.com/documentation/speech/speechtranscriber · locale list checked live on this Mac
- Parakeet-TDT-0.6B-v3: https://huggingface.co/mlx-community/parakeet-tdt-0.6b-v3 · https://build.nvidia.com/nvidia/parakeet-tdt-0_6b-v2/modelcard
- Nemotron-3.5 ASR streaming: https://huggingface.co/mlx-community/nemotron-3.5-asr-streaming-0.6b · https://huggingface.co/onnx-community/nemotron-3.5-asr-streaming-0.6b-onnx-int4 · Hinglish FT https://huggingface.co/addyo07/nemotron-3.5-0.6b-hinglish
- Moonshine v2 (arXiv 2602.12241): https://arxiv.org/abs/2602.12241 · v1 https://huggingface.co/UsefulSensors/moonshine-base
- whisper.cpp Core ML / Mac speed comparisons: https://github.com/anvanvan/mac-whisper-speedtest · https://huggingface.co/argmaxinc/whisperkit-coreml
- goonj-1-82M: https://huggingface.co/BH-Builds/goonj-1-82M · Kokoro voices/grades: https://huggingface.co/hexgrad/Kokoro-82M/blob/main/VOICES.md · kokoro-onnx: https://github.com/thewh1teagle/kokoro-onnx
- Indian English phonology (retroflex stops, ʋ, no θ/ð, monophthong e:/o:): https://en.wikipedia.org/wiki/Indian_English#Phonology · Amazon Polly en-IN phoneme table: https://docs.aws.amazon.com/polly/latest/dg/ph-table-english-in.html
- Piper en_IN (SPICOR): https://huggingface.co/navgurukul-ai-labs/text-to-speech-en-IN-piper · Pocket-TTS Indian English: https://huggingface.co/prasadvittaldev/pocket-tts-indian-english-male-indictts
- edge-tts: https://pypi.org/project/edge-tts/ · Indic Parler-TTS: https://huggingface.co/ai4bharat/indic-parler-tts · earlier Hindi/Hinglish survey: [hinglish_voice.md](hinglish_voice.md)
