# Language switching — English · Hinglish · Hindi · Telugu · Tenglish (D34, 2026-11-11)

**Ask:** "It should reply in whatever language we talk. English → English; suddenly Telugu → Telugu; 'Namaskar…' →
Hindi; back to English → English. 'Just talk in English, don't talk in any other language right now' → English only."

The hard part is not the reply — it is *hearing* the language: STT was pinned to English (+ a Hinglish prompt) because
free Whisper turns Hinglish into Devanagari/Urdu, and a pinned Whisper **translates** Telugu speech into English, so the
brain never saw the switch.

## Options looked at (spoken-language ID, text-language ID, Telugu speech)

| # | Option | Kind | Mechanism | Strengths | Weaknesses | Free + 8 GB M2? | Status |
|---|---|---|---|---|---|---|---|
| 1 | **Whisper-tiny `detect_language`** (mlx) | audio LID | encoder + 1 decoder step over 99 language tokens | 32 ms, ~40 MB, same lib as our STT | confuses Dravidian neighbours (te↔kn/bn) | ✅ | **measured — chosen** |
| 2 | Whisper-small q4 `detect_language` | audio LID | same, bigger encoder | better on Telugu (5/6 raw) | 345 ms extra per turn | ✅ but slow | measured |
| 3 | Whisper large-v3 auto-language (Groq) | cloud STT | LID inside large-v3 | best accuracy, writes Telugu script | cloud, audio leaves the Mac | free tier | used for the Telugu *transcription* |
| 4 | VoxLingua107 ECAPA-TDNN (SpeechBrain) | audio LID | x-vector classifier, 107 langs | strong LID accuracy in papers | needs SpeechBrain stack; another ~80 MB model + torch at runtime | ⚠️ | literature |
| 5 | MMS-LID-126/256 (Meta) | audio LID | wav2vec2 1B | covers Telugu well | ~1 B params — too big for the always-on loop | ❌ | literature |
| 6 | Silero language classifier | audio LID | small ONNX classifier | tiny, fast | coarse language set, Indic coverage limited | ✅ | literature |
| 7 | NVIDIA AmberNet / TitaNet-LID (NeMo) | audio LID | speaker-embedding style | good accuracy | NeMo stack is heavy | ⚠️ | literature |
| 8 | IndicLID (AI4Bharat) | text LID | fastText + IndicBERT, native + romanized | built for romanized Hindi/Telugu | ~1 GB with the BERT part; overkill for our 5 classes | ⚠️ | literature |
| 9 | fastText lid.176 / GlotLID | text LID | char n-gram fastText | fast | weak on romanized Indic and code-mixed lines | ✅ | literature |
| 10 | lingua-py / CLD3 | text LID | n-gram / NN | easy | no romanized Telugu/Hindi; short lines unreliable | ✅ | literature |
| 11 | **Script + Roman lexicons** (ours) | text LID | Telugu/Devanagari Unicode ranges + ~500 Hindi and ~170 Telugu Roman words | < 1 ms, 0 MB, exactly our 5 classes, explainable | only knows the words in the lexicons | ✅ | **built** (brain/lang.py) |

## Measured (M2, 27 synthetic clips: Jessica/Rishi English, hf_alpha Hinglish, Lekha/hf_alpha Hindi, Geeta/hf_alpha Telugu + Tenglish)

| | English | Hinglish + Hindi | Telugu | Tenglish | median |
|---|---|---|---|---|---|
| Whisper-small q4, raw top-1 | 6/6 | 9/9 | 5/6 (1 → Kannada) | 3/6 | 345 ms |
| Whisper-tiny, raw top-1 | 6/6 | 8/9 (1 → Bengali) | 3/6 (Bengali) | 1/6 | 32 ms |
| **Whisper-tiny, pooled to his 3 languages** (te+kn+ta+ml / hi+ur+mr+ne / en) | 6/6 | 9/9 | 6/6 | 3/6 | 32 ms |

Pooling works because he only speaks three base languages. Tenglish stays hard from audio alone (English-heavy lines);
once the turn is transcribed in Telugu script, the text classifier settles it.

## Design (built)

1. **Hear:** `voice/lid.py` (tiny, pooled, ≥ 50 % Telugu share) on the STT thread. Telugu → Groq large-v3 with
   `language=te` (cloud second opinion on) else local small with `language=te`. English/Hindi → the existing path.
2. **Decide:** `brain/lang.py` — lock › explicit "talk in Telugu" (held while he speaks Telugu/English) › this
   message's language › for "ok/bye", the previous one. Roman Hindi → Hinglish (casual), Devanagari → Hindi.
3. **Say:** the language line in the reply rules (`lang.PROMPT`), Telugu/Devanagari script for TTS accuracy.
4. **Speak:** script routing in `tts.pick` — Telugu → `voice_te`, Hindi/Hinglish → `voice_hi`, English → `voice`;
   a short English bit inside a Telugu/Hindi reply keeps the same voice (4 s hold).
5. **Commands:** only "just/only talk in X (no other language)" is saved (`Language lock: …`); "talk in X" switches;
   "talk in any language" unlocks. Old "Reply in English/Hinglish" rules no longer reach the LLM's MUST lines.

## Telugu voice (owner picked after a 6-voice local lineup)
Geeta (macOS), hf_alpha, hf_beta, goonj meera, goonj nisha, MMS-TTS-tel — all local. Owner picked **hf_alpha** (same as
Hinglish). Microsoft edge-tts Telugu was not run (it downloads and runs an outside package; cloud anyway).

## Not done yet
Telugu fast paths (to-dos / alarms said in Telugu go to the LLM for now); a real-voice check of LID on his own speech.
