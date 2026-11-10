# Hinglish voice: speaking and hearing code-mixed Hindi-English (research, 2026-11-10)

**Question:** Tejmul speaks Hinglish ("Haan, note kar liya. Aaj ka interview kaisa raha?"), mostly in Roman script.
Today Kokoro (`af_heart`, `en-us`) reads it with American phonemes, so it sounds foreign, and whisper-small q4
sometimes returns nonsense on his real voice ("Chuk chaa saan baat kare kale"). What is the smallest fix that stays
free, local-first, inside the ~3 GB model budget, with TTS first chunk around 200–400 ms and STT under ~400 ms?

## Live measurements (this Mac, M2 8 GB, 2026-11-10)
**TTS, judged by round-trip intelligibility:** 4 Hinglish sentences → TTS → whisper-large-v3-turbo q4
(`language="en"` + the Stiti Hinglish prompt) → word error rate against the Roman text. This is a proxy: it
checks whether the words are clear, not whether the voice sounds nice. Synthesis time is per full sentence, warm.

| Variant | Synth / sentence | Round-trip WER | Example heard back |
|---|---|---|---|
| A Kokoro `af_heart`, `en-us`, Roman (**today**) | 456 ms | **68%** | "Haan Notkarliya. Ajka interview Kaisar Raha." |
| B Kokoro `hf_alpha`, espeak `hi`, full Devanagari (hand-transliterated) | 647 ms | 35% | "Haan, note kar liya. Aaj ka interview kaisa raha." |
| C Kokoro `hf_alpha`, **mixed phonemes** (Hindi words → `hi` G2P, English → `en-us`) | 451 ms | **26%** | "Haan note kar liya. Aaj ka interview kaisa raha?" |
| D Kokoro `hm_omega`, full Devanagari | 636 ms | 26% | "Thoda stress lag rahe ho, break lelo yaar." |
| C′ same as C but driven **from Roman text** via a 40-word Hinglish lexicon | 458–641 ms (4 voices) | 26–29% | (all four Hindi voices) |
| E macOS `say -v Lekha` (hi-IN), Roman | 1,027 ms | 51% | "Haan, no car liao…" |
| F macOS `say -v Lekha`, Devanagari | 586 ms | 40% | |
| G macOS `say -v Rishi` (en-IN), Roman | 797 ms | 35% | "Aaj car interview kaisa raha?" |

- First-clause latency for C′ (`hf_alpha`, warm): **262 ms** for "Haan, note kar liya." and 384 ms for "Thoda
  stressed lag rahe ho,". The lexicon lookup plus espeak takes <1 ms per sentence once warm (the first espeak `hi`
  call costs ~170 ms one time, so warm it up at start the way `tts.py` already warms Kokoro).
- Passing Roman text straight to espeak `hi` does **not** work: espeak switches to English for Latin letters
  (`(en)hˈɑːn(hi)…`). Strict transliteration schemes are no better: `indic-transliteration` ITRANS/OPTITRANS turned
  "interview kaisa raha" into "इन्तेर्विएव् कैस रह". Casual Hinglish spelling needs a lexicon or a learned model.
- The `voices-v1.0.bin` Stiti already downloads includes `hf_alpha`, `hf_beta`, `hm_omega`, `hm_psi`, so this needs
  **no new download and no extra RAM**. Listen-test samples (before and after) are in the session scratchpad
  (`samples/0_today_af_heart.wav` vs `samples/0_new_hf_alpha.wav`). Kokoro rates its Hindi voices grade C, so
  Tejmul's ear is the final judge.

**STT, on clean synthetic Hinglish (Kokoro Hindi voices speaking 4 commands):**
| Model / setting | Latency | Output |
|---|---|---|
| whisper-small q4, `language="en"` + Hinglish prompt (**today**) | 263–274 ms | "Kal subah 6 baje ka alarm laga do." · "Meri entadu list hi mai kya kya hain?" |
| whisper-small q4, `language="hi"` | 345–386 ms | Devanagari, more errors ("चहे बजी का रान") |
| whisper-small q4, no language (auto-detect) | 522–583 ms | same as `hi`, plus a slow detection pass. Never use. |
| whisper-large-v3-turbo q4, `en` + prompt | ~1,020 ms | "Mammy ko call karna yaad dilana sham ko." |
| whisper-large-v3-turbo q4, `hi` | ~1,080 ms | best Devanagari, but 4× slower |

Today's `en` + prompt setup already works on **clean** speech. So the garbage comes from real-mic conditions
(accent, speed, room noise, and possibly VAD clipping the start), where whisper-small's weak Hindi breaks down. The
fix needs a test set of **Tejmul's own recorded clips**, not synthetic audio. I could not measure Groq here; check it
in that A/B.

## (A) Hinglish / Hindi TTS (≥10 options)
| # | Option | Mechanism | Size / RAM | Latency (M2 or reported) | Hinglish quality | License / free | Fits? |
|---|---|---|---|---|---|---|---|
| 1 | **Kokoro Hindi voices + code-switch phonemizer** (variant C′) | Roman word → lexicon → Devanagari → espeak `hi`; other words → espeak `en-us`; one phoneme string → Kokoro `is_phonemes=True` | 0 extra (same 88 MB model) | **262–384 ms first clause (measured)** | WER 68%→26% (measured); English words keep a US accent | Apache-2.0 / GPL espeak, free | ✅ **do now** |
| 2 | Kokoro Hindi voices + full Devanagari via transliterator | Whole reply → Devanagari, espeak `hi` | 0 extra | 636–647 ms/sentence | 26–35%; English words get a natural "Indian" reading | free | ✅ variant of #1 |
| 3 | **Lekhani** (Udgam Labs, 2026-11) | 812K-param char transformer, q4, with a 200k-word list | **0.88 MB** | ~2 ms/word (WASM) | 113/122 on a Hinglish chat set, Aksharantar 65.9%; word-level, so "main/mein" are ambiguous | Apache-2.0, list CC0; JS runner (port needed) | ✅ OOV fallback for #1 |
| 4 | AI4Bharat IndicXlit (`ai4bharat-transliteration`) | Fairseq char transformer + 358 MB re-rank list | 11M params, ~46 MB model, **358 MB** with list | ms/word | 68.7% Aksharantar, 112/122 Hinglish | MIT; **Fairseq breaks on Py ≥3.11** | 🟡 too heavy, wrong Python |
| 5 | `indic-transliteration` / libindic (rule schemes) | ITRANS/HK rules | KB | µs | **Bad** for casual spelling (measured) | MIT | ⛔ alone; OK Devanagari→Roman |
| 6 | Google Input Tools transliteration | Unofficial cloud endpoint | 0 | network RTT | good | free but unofficial, sends text out | 🟡 P0 only, no |
| 7 | **goonj-1-82M** (BH-Builds) | Kokoro-82M fine-tune; Hindi + **Indian-English** voices; ~300-word Hinglish lexicon routing | 82M (same as Kokoro) | ≈ Kokoro once exported | built for Hinglish; synthetic-data artifacts noted | Apache-2.0; **PyTorch only** → needs ONNX export + voice-pack conversion | ✅ **next step** (Indian accent) |
| 8 | macOS `say` / AVSpeechSynthesizer (Lekha hi-IN, Rishi/Aman/Tara en-IN) | Apple's built-in local voices | 0 (OS) | 586–1,027 ms via `say` CLI (process start) | 35–51% WER; Rishi reads Roman Hinglish acceptably | free, local | 🟡 offline fallback only |
| 9 | edge-tts `hi-IN-SwaraNeural` / `MadhurNeural` | Unofficial Microsoft Edge read-aloud websocket | 0 | network (not measured) | very natural Hindi; English words Hindi-ised | free but unofficial, can break; text leaves the Mac | 🟡 P0 only |
| 10 | Piper `hi_IN` (pratham, rohan, priyamvada) | VITS + espeak `hi` | ~60 MB ONNX | fast on CPU | Devanagari only; same Roman problem | MIT; one voice may have been removed upstream | 🟡 no gain over Kokoro |
| 11 | Meta MMS-TTS `hin` | VITS, character input | 36M | fast | Devanagari only, flat prosody | **CC-BY-NC** | ⛔ license |
| 12 | AI4Bharat Indic Parler-TTS | Parler (T5 + decoder LM, text-described voice) | 0.9B, ~4 GB file | 2.6 s+ per short line on an L4 GPU | good Hindi | Apache-2.0 | ⛔ RAM + speed |
| 13 | AI4Bharat IndicF5 | F5-TTS flow matching, needs reference audio | 0.4B (int8 ~350 MB) | multi-step diffusion, slow on CPU | good, cloned voice | gated, research terms | ⛔ latency |
| 14 | Veena (Maya Research) | Llama-3B → SNAC tokens, code-mixed trained | 3B | <80 ms on H100; one forward pass per audio token on a Mac | very good Hinglish | Apache-2.0 | ⛔ 3B (= a local LLM) |
| 15 | Svara-TTS v1 (Kenpath) | Orpheus/Llama-3.2-3B + SNAC, 19 Indic langs | 3B (q4f16 ONNX 1.95 GB) | slow on M2 | good | Apache-2.0 | ⛔ |
| 16 | Chatterbox Multilingual v3 (Hindi pack) | 0.5B Llama backbone + S3 tokens | 0.5B | ~real-time on GPU | good, with watermark | MIT | ⛔ budget/latency |
| 17 | Sarvam Bulbul v2/v3 | Cloud API | 0 | ~fast | excellent Hinglish | ₹15–30 / 10k chars; ₹100 one-time credit | ⛔ not free |
| 18 | KittenTTS | 15–25 MB ONNX | tiny | fast | **English-only** | Apache-2.0 | ⛔ |

## (B) Hinglish STT (≥10 options)
| # | Option | Mechanism | Size / RAM | Latency | Hinglish quality | License / free | Fits? |
|---|---|---|---|---|---|---|---|
| 1 | whisper-small q4 MLX, `en` + Roman-Hinglish prompt (**today**) | Forces Latin output, prompt biases spelling | ~250 MB | **263–274 ms (measured)** | fine on clean speech, fails on real mic | MIT | ✅ keep as base |
| 2 | whisper-small, `language="hi"` → romanize | Devanagari out → rule-based Devanagari→Roman | same | 345–386 ms | worse than #1 (measured) | MIT | ⛔ |
| 3 | whisper-medium | 769M | ~0.8 GB q4 | ~2× small | better Hindi, still translates/garbles | MIT | 🟡 RAM + latency |
| 4 | whisper-large-v3-turbo q4 MLX | 809M, 4 decoder layers | ~0.5 GB | **~1,020 ms (measured)** | best of stock Whisper | MIT | 🟡 too slow for every turn |
| 5 | **Oriserve Whisper-Hindi2Hinglish-Swift** | whisper-base fine-tuned on ~550 h noisy Indian audio, **Roman Hinglish output** | **72.6M** (< small) | ≈ whisper-base (≤ ~150 ms, est.) | WER 35.1 FLEURS / 38.7 CV vs 104–107 for base | Apache-2.0; HF/PyTorch → convert to MLX | ✅ **A/B first** |
| 6 | Oriserve Hindi2Hinglish-Prime / Apex | large-v3 fine-tune (Apex: >800M params, 1,000+ h) | 1.5B / ~0.8B | ≥ turbo (>1 s) | Prime 28.7 FLEURS / 32.4 CV / 60.8 IndicVoices (vs 50.8/61.9/82.6 for large-v3) | Apache-2.0 | 🟡 too slow locally; ct2/ggml builds exist |
| 7 | Trelis whisper-hinglish-preview / Tara | Whisper fine-tune, `|mixedcode|` token | small/large (card unclear) | — | outputs **mixed script** (Devanagari Hindi + Latin English) | open weights | 🟡 needs romanizing |
| 8 | whisper-tiny-hinglish (community) | tiny fine-tuned on romanized targets | 39M | very fast | unbenchmarked | open | 🟡 wake/backup only |
| 9 | AI4Bharat IndicWhisper (Vistaar) | whisper-medium fine-tuned on 10.7k h Indic | 769M | ~2× small | best Hindi on Vistaar (avg 13.6 WER), **Devanagari** | MIT | 🟡 heavy, wrong script |
| 10 | AI4Bharat IndicConformer-600M | Conformer CTC/RNNT, 22 langs | 600M (int8 ONNX, WER 15%→29%) | fast (non-autoregressive) | good pure Hindi; Devanagari, English words get transliterated | MIT, gated | 🟡 RAM, script |
| 11 | **Groq whisper-large-v3-turbo** (cloud) | Hosted Whisper, 216× real-time | 0 local | ~300–800 ms for short clips (reported) | = turbo (#4), not tuned for Hinglish | free: 20 RPM, 2k req/day, **28,800 audio-sec/day**; no training on API data | ✅ escalation lane (audio leaves the Mac) |
| 12 | Sarvam Saarika/Saaras | Cloud, Indic-tuned, Hinglish codemix mode | 0 | fast | best-in-class Hinglish | ₹30/h; ₹100 one-time credit | ⛔ not free |
| 13 | Gemini audio input | Multimodal LLM transcription | 0 | 2–5 s | good | free tier trains on data | ⛔ P0 only, slow |
| 14 | Moonshine / Parakeet / Canary | Streaming English-first ASR | 30–600M | 37–60 ms | **no Hindi** | MIT/CC | ⛔ (see voice_latency.md) |
| 15 | Apple SpeechAnalyzer (macOS 26) | On-device OS ASR | 0 | fast | hi-IN not in documented locales | free | ⛔ (re-check `supportedLocales`) |

## Recommendation
**TTS: smallest fix = code-switch phonemizer + Kokoro Hindi voice (no new model).** In `tts.py`, keep the reply text
in Roman. Per word: if it is in a Hinglish lexicon (Roman→Devanagari, start with the ~500 most common words: hai,
ka/ki/ko, kar, raha, aaj, kal, nahi, haan, yaar, toh, bhi, mein…), phonemize it with espeak `hi`. Otherwise use
`en-us`. Join runs into one phoneme string and call `k.create(ph, voice="hf_alpha"|"hm_omega", is_phonemes=True)`.
Measured: round-trip WER drops from 68% to 26%, first clause takes 262–384 ms, and RAM stays the same. Ambiguous
words (main/mein/maine, to/toh, hi) use a context rule: Hindi if the neighbouring words are Hindi. Fully English
replies keep `af_heart`. Make the voice a setting (`STITI_VOICE=hf_alpha`). **Next:** use Lekhani (0.88 MB) for
Roman words found in neither the lexicon nor `/usr/share/dict/words`. **Then:** export goonj-1-82M to ONNX for
Indian-English accents with the same runtime and RAM.

**STT: first measure, then make the smallest swap.** (1) Record 20–30 of Tejmul's real Hinglish commands. Check
`segments()` for VAD clipping, and log `avg_logprob`. (2) A/B on that set: today's whisper-small `en`+prompt vs
**Oriserve Hindi2Hinglish-Swift**. Swift is whisper-base sized, needs a one-time conversion to MLX, outputs Roman
Hinglish, and is smaller and faster than small, so it costs nothing to try. Pick the winner by WER and fast-path
intent accuracy. (3) Add **Groq whisper-large-v3-turbo as an escalation lane**: only re-transcribe a turn when local
confidence is low (`avg_logprob < -0.8` or Laya can't parse an intent). Most turns stay local and fast; hard turns cost
~0.5 s more and use a small part of the 8 h/day free quota. Groq doesn't train on API data, but audio leaves the Mac,
so let Tejmul switch it off. Don't use `language=None` (it adds a 250 ms detection pass) or `language="hi"` (it gives
Devanagari and is worse in our test).

## Sources
- Kokoro voices (Hindi grade C, espeak `hi`): https://huggingface.co/hexgrad/Kokoro-82M/blob/main/VOICES.md
- goonj-1-82M (Kokoro Hinglish fine-tune): https://huggingface.co/BH-Builds/goonj-1-82M
- Lekhani transliterator: https://huggingface.co/udgamlabs/Lekhani
- IndicXlit / Aksharantar (arXiv 2205.03018): https://github.com/AI4Bharat/IndicXlit · https://pypi.org/project/ai4bharat-transliteration/
- Indic Parler-TTS: https://huggingface.co/ai4bharat/indic-parler-tts-pretrained/discussions/1 ·
  https://sachinsshetty.github.io/onwards/idea/dhwani/server/2025-03-16-tts-latency
- IndicF5: https://huggingface.co/ai4bharat/IndicF5 · https://huggingface.co/developerabu/IndicF5-MNN
- Veena: https://huggingface.co/maya-research/Veena · Svara: https://huggingface.co/blog/kenpath/svara-tts-open-multilingual-speech-for-india
- Chatterbox Multilingual v3: https://www.resemble.ai/resources/chatterbox-multilingual-v3-tts-with-embedded-watermarking-for-25-languages
- Piper voices: https://huggingface.co/rhasspy/piper-voices · MMS-TTS hin: https://huggingface.co/facebook/mms-tts-hin
- edge-tts: https://pypi.org/project/edge-tts/ · KittenTTS (English-only): https://rits.shanghai.nyu.edu/ai/kittentts-state-of-the-art-voice-synthesis-in-under-25-mb/
- Sarvam pricing/credits: https://docs.sarvam.ai/api-reference-docs/pricing · https://docs.sarvam.ai/api-reference-docs/changelog
- Oriserve Swift / Prime / Apex: https://huggingface.co/Oriserve/Whisper-Hindi2Hinglish-Swift ·
  https://huggingface.co/Oriserve/Whisper-Hindi2Hinglish-Prime · https://cxotoday.com/media-coverage/oriserve-launches-whisper-hindi-to-english-apex-engine-to-power-next-gen-ai-for-indias-multilingual-business-needs/
- Trelis Hinglish: https://huggingface.co/Trelis/whisper-hinglish-preview · https://huggingface.co/abhishekgautamm/whisper-tiny-hinglish
- Vistaar / IndicWhisper (arXiv 2305.15386): https://github.com/AI4Bharat/vistaar
- IndicConformer: https://huggingface.co/ai4bharat/indic-conformer-600m-multilingual · https://huggingface.co/atharva-again/indic-conformer-600m-quantized
- Groq STT limits + speed: https://console.groq.com/docs/rate-limits · https://console.groq.com/docs/model/whisper-large-v3-turbo ·
  https://groq.com/whisper-large-v3-turbo-now-available-on-groq-combining-speed-quality-for-speech-recognition/
- Hinglish ASR benchmarks: HiACC https://www.ncbi.nlm.nih.gov/pmc/articles/PMC12329218/ · CLEAR https://aclanthology.org/2025.icnlsp-1.33.pdf ·
  LAHAJA https://arxiv.org/pdf/2408.11440
- Apple SpeechAnalyzer locales: https://developer.apple.com/documentation/speech/speechtranscriber
