# Research: personal emotion learning (Stiti learns HIS voice) + local conversation recorder

Date: 2026-11-11. Owner's ask: "the emotion detection could be trained by using [the system we] build" — Stiti should
learn Tejmul's own voice from real use, with no forms, on an Apple M2 / 8 GB, free, with no local LLM.

What exists today (read before this research):
- `voice/prosody.py` — loudness / pitch / pitch-SD / speaking rate, z-scored against his own running baseline
  (`~/.stiti/voice_baseline.json`). Rule: arousal z > 1 → "stressed", < −1 → "tired", else "calm". About 1 ms.
- `voice/emotion_model.py` — emotion2vec+ base (FunASR, ~90M params). 9 generic classes mapped to Stiti moods.
  Measured on the M2: ~165 ms per utterance, **+1.55 GB** RAM (funasr + torch). OFF by default (menubar toggle).
  It called `generate(..., extract_embedding=False)`, so the 768-d utterance embedding was **thrown away**.
- `brain/emotion.py` `fuse()` — weighted vote of text mood (exemplar kNN, ~50% reliable) and voice mood. A non-calm
  label needs conf ≥ 0.75. Denials ("I'm not angry") force calm.
- Stiti moods: calm · happy · stressed · angry · sad · tired (from `decide.py` `text_emotion`).

## 1. Sources compared (17)

| # | Source | Mechanism | Strengths | Weaknesses | Fits free + 8 GB M2? |
|---|---|---|---|---|---|
| 1 | **emotion2vec** — Ma et al., ACL Findings 2024, arXiv 2312.15185 [1] | data2vec-style self-supervised pre-training on emotion speech; utterance + frame distillation. Frozen 768-d features + a **linear** head. | Linear probe on frozen features beat other SSL models on IEMOCAP and 9+ languages. That means a tiny head on top is the intended use. | Pre-training data is mostly English/Chinese acted + podcast speech. | Yes. The model is already on disk; a linear head is a few KB. |
| 2 | **emotion2vec+ base** (FunASR / HF `emotion2vec/emotion2vec_plus_base`) [2] | emotion2vec fine-tuned on ~4.8k h of filtered pseudo-labelled data. 9 classes. `extract_embedding=True` returns `feats` (768-d pooled). | One forward pass gives BOTH the generic 9-class scores and the 768-d embedding. No second model. | Generic naturalistic accuracy is weak (~41% on in-the-wild speech, earlier Stiti research). No "tired". | Yes, but 1.55 GB → run live only when he turns it on; run nightly in a **subprocess** so the RAM is returned. |
| 3 | **SUPERB ER task** — Yang et al., Interspeech 2021 [3] | Benchmark protocol: frozen SSL upstream (wav2vec2/HuBERT/WavLM) + lightweight downstream, weighted layer sum. | Shows a frozen encoder + small head gets most of the accuracy of full fine-tuning. | Acted data (IEMOCAP 4-class). | Yes (we copy the protocol, not the models). |
| 4 | **wav2vec2 embeddings for SER** — Pepino, Riera, Ferrer, Interspeech 2021 [4] | Frozen wav2vec 2.0 layers pooled + a small dense head; adding eGeMAPS-style prosody features helps a little. | Small heads on frozen SSL features are strong; prosody is complementary. | Full wav2vec2-large is 1.2 GB+. | Partly: the idea (frozen features + prosody) yes, the model no (we already have emotion2vec). |
| 5 | **"Dawn of the transformer era in SER"** — Wagner et al., IEEE TPAMI 2023 [5] | wav2vec2/HuBERT-large fine-tuned on MSP-Podcast; studies robustness, fairness, and speaker effects. | Valence becomes usable with transformers; shows the models pick up linguistic content implicitly. | Models are large; arousal is still easier than valence; individual-speaker variance is high. | No (size). Takeaway: expect arousal-type moods (stressed/angry/tired) to be easier than sad/happy. |
| 6 | **Sridhar & Busso, "Unsupervised personalization of an emotion recognition system"** — IEEE TAC 2022, arXiv 2201.07876 [6] | Find training speakers acoustically similar to the target speaker; oversample/weight them to adapt a valence model. | Up to 13.5% relative gain with no target labels. Shows valence cues are **speaker-dependent**. | Needs a big multi-speaker labelled pool. | No pool on the Mac. Takeaway: personal data matters most for valence (happy/sad). |
| 7 | **PAPE** — Tran, Yin, Soleymani, "Personalized adaptation with pre-trained speech encoders", Interspeech 2023, arXiv 2309.02418 [7] | Continue SSL pre-training of HuBERT with learnable speaker embeddings, then an unsupervised per-speaker **label-distribution calibration**. | SOTA personalised valence on MSP-Podcast; per-speaker calibration of the output is cheap and effective. | Re-pre-training HuBERT is a GPU job. | The calibration half yes (per-speaker priors/temperature); the pre-training half no. |
| 8 | **Iterative feature normalization (IFN)** — Busso, Mariooryad, Metallinou, Narayanan, IEEE TAC 2013 [8] | Per-speaker normalization of acoustic features, estimated on the speaker's (mostly neutral) speech. | A big, cheap gain for prosodic features; the reason Stiti's prosody is already z-scored vs his baseline. | Assumes most speech is neutral. | Yes (numpy). We apply it to the embedding too: subtract his mean embedding. |
| 9 | **Test-time adaptation for SER** — Dong, Jia, Dang, arXiv 2601.16240 (2026) [9] | Benchmarks 11 TTA methods on intra-corpus personalization, acted→natural and cross-corpus shift. | Backprop-free TTA is the most promising. | Entropy-minimisation and pseudo-label TTA **generally fail**: emotion is ambiguous, there is no single confident label. | Takeaway: don't self-train on our own confident predictions alone; use outside signals (his words) as labels. |
| 10 | **Cross-modal transfer** — Albanie, Nagrani, Vedaldi, Zisserman, ACM MM 2018 [10] | A face-emotion "teacher" labels unlabelled video; a speech "student" learns from those soft labels. | Learns voice emotion with **zero** hand labels from another modality's predictions. | Teacher errors propagate. | Yes, as an idea: Stiti's text mood + explicit self-reports are the teacher for the voice head. |
| 11 | **Co-training** — Blum & Mitchell, COLT 1998 [11] | Two views (text, voice) that are conditionally independent label each other only where confident. | Agreement of two independent views is a much cleaner pseudo-label than either alone. | Views are not fully independent (he says "I'm tired" in a tired voice). | Yes: text–voice **agreement** → a pseudo-label with a low weight. |
| 12 | **Learning from complementary labels** — Ishida et al., NeurIPS 2017 [12] | Train from "this is NOT class k" labels with a loss on 1 − p(k). | Exactly the shape of his corrections ("I'm not angry", "main udaas nahi hoon"). | A negative label carries less information than a positive one. | Yes: an extra term in the logistic-regression loss. |
| 13 | **Noisy labels**: Generalized Cross Entropy (Zhang & Sabuncu, NeurIPS 2018) [13]; Co-teaching (Han et al., NeurIPS 2018) [14] | Bound the loss of mislabeled examples; trust small-loss samples. | Weak labels from regexes and pseudo-labels will be noisy. | Extra machinery is overkill for a few hundred rows. | Partly: we use **per-source sample weights** + strong L2 (the simplest noise-robust choice) and evaluate on human-sourced labels only. |
| 14 | **Active learning for SER** — Abdelwahab & Busso, ACII 2019 [15]; Settles, survey 2009 [16] | Ask for labels only for the most uncertain / most informative samples. | Few labels go a long way. | Needs a human to answer. | Yes, with a strict budget: at most an **opt-in** end-of-day "how was your mood today?" — never a form, never mid-conversation. |
| 15 | **Continual learning**: EWC (Kirkpatrick et al., PNAS 2017) [17]; iCaRL rehearsal (Rebuffi et al., CVPR 2017) [18] | Protect old knowledge with a weight penalty, or replay stored examples. | Avoids catastrophic forgetting. | — | Simplest: **keep every labelled feature vector** (768 floats ≈ 3 KB) after the audio expires and retrain the head from scratch nightly = full rehearsal, zero forgetting. |
| 16 | **Calibration**: temperature scaling (Guo et al., ICML 2017) [19]; selective prediction (Geifman & El-Yaniv, NeurIPS 2017) [20] | One scalar T fitted on held-out logits; abstain below a confidence threshold. | Makes "conf 0.7" mean ~70% right; abstaining avoids wrong mood reads. | Needs held-out data (we have out-of-fold predictions). | Yes: T fitted on out-of-fold logits; Stiti acts only above the threshold. |
| 17 | **Indian / Hindi / Hinglish data**: IITKGP-SEHSC (Koolagudi et al., IC3 2009) [21]; EmoInHindi (Singh et al., LREC 2022) [22]; SemEval-2024 Task 10 / E-MASAC Hinglish ERC [23]; Hinglish tweets (Wadhawan & Aggarwal 2021) [24] | IITKGP-SEHSC: 10 radio artists, 8 **acted** emotions, Hindi. The others are **text** (dialogue / tweets). | Lexicons for self-report words ("udaas", "gussa", "thak gaya", "tension") come from these. | **No public code-switched Hinglish speech emotion corpus** found; acted Hindi speech does not match his natural voice. | Takeaway: no dataset can replace his own data → personal learning is the only route for his voice. |
| 18 | **Evaluation on small data**: UAR / macro-F1 (Schuller et al., INTERSPEECH challenges) [25]; grouped CV + baseline gating (common practice) | Macro-F1/UAR weights every class equally; group folds by session/day so neighbouring turns don't leak. | Prevents "always calm" from looking good. | Small n → noisy estimates. | Yes: grouped-by-day k-fold, macro-F1, switch only if it beats generic by a margin AND wins most folds. |
| 19 | **Voice privacy**: VoicePrivacy Challenge (Tomashenko et al., 2020–24) [26]; GDPR Art. 9 (biometric data) | Raw voice = biometric + content; anonymisation removes identity. | — | Raw audio is the riskiest artifact Stiti would hold. | Recorder **opt-in, default OFF**, local only, 30-day / 2 GB cap, one-command delete, not in backups; keep only compact features after expiry. |

## 2. Findings that decide the design

1. **Frozen emotion2vec features + a tiny head is the intended, best-supported recipe** [1][3][4]. The 768-d embedding is
   produced by the same forward pass Stiti already runs, so a personal head costs ~0 extra live latency (a 768×6
   matrix multiply ≈ 10 µs).
2. **Personal data beats generic for one person**, especially for valence-type moods [6][7], and per-speaker
   normalization is the cheapest big win [8]. Generic in-the-wild accuracy is ~41% → plenty of room.
3. **Labels must come from outside the voice model.** Self-training on its own confident outputs fails for emotion
   [9]. Use his words: explicit self-reports, his corrections (negative labels [12]), and text–voice agreement
   (co-training [10][11]) at a low weight.
4. **Evaluate on human-sourced labels only.** Pseudo-labels come from agreement with the generic model, so they would
   flatter the generic baseline; they are used for training, never as ground truth.
5. **Gate the switch.** Only activate the personal head when it beats generic emotion2vec on his held-out turns
   (grouped by day) by ≥ 0.05 macro-F1 and wins the majority of folds; otherwise keep generic. Re-check nightly.
6. **Calibrate and abstain** [19][20]: temperature-scale on out-of-fold logits; the live predictor returns nothing
   below its threshold.
7. **No forgetting problem at this size** [17][18]: keep features after the audio expires, retrain from scratch each
   night (seconds).
8. **Hindi/Hinglish:** no matching speech corpus exists [21]–[24]; his own data is the dataset. Self-report patterns
   must cover Hinglish ("thak gaya hoon", "tension ho rahi hai", "udaas hoon", "gussa aa raha hai", "khush hoon").
9. **Privacy** [26]: opt-in recorder, local FLAC, retention caps, delete command, never in a web page, never uploaded,
   not in the encrypted backup, crisis (P2) turns are never recorded.

## 3. Recommended design (fits the M2: 0 new models, < 1 MB of new RAM live)

```
committed voice turn ──► loop.py hook ──► recorder.on_turn()  (background thread; no-op when recorder is OFF)
                                   ├─ ~/.stiti/recordings/YYYY-MM-DD/<id>.flac   (16 kHz, ~20 KB/s)
                                   └─ voice_turns row: transcript, speech_ms, pause_ms, turn state, STT conf,
                                      prosody features, generic prosody label, voice/text/fused mood,
                                      emotion2vec embedding + scores (when the live model ran), episode id
nightly (brain/sleep.py) ──► learn.emotion_train.nightly()
   1. retention: delete audio older than 30 days or over 2 GB (features + labels stay)
   2. embed backlog: rows with audio but no embedding → subprocess loads emotion2vec once, exits (RAM returned)
   3. labels.rebuild(): self-reports (EN + Hinglish, first person, not questions) → +1.0 on the turn, +0.5 on
      neighbours (same session, ±2 turns, ≤ 3 min); corrections ("I'm not angry") → NOT-label 1.0 on the turn and
      0.7 on the previous one; text–emotion2vec agreement (text ≥ 0.8, voice ≥ 0.5) → pseudo-label 0.3
   4. train two heads (numpy multinomial logistic regression + complementary-label loss + L2, sample weights):
        e2v head:     768-d embedding − his mean embedding → PCA(≤32, whitened) → 6 moods
        prosody head: [loudness, pitch, pitch SD, rate] z-scored on his own data → 6 moods (works with e2v OFF)
   5. grouped-by-day k-fold eval (human-sourced labels only), macro-F1 vs the generic predictor of the same rows;
      temperature fitted on out-of-fold logits; ACTIVATE only if Δ ≥ 0.05, majority of folds won, ≥ 12 eval
      turns, ≥ 3 days; else keep generic. Model + metrics versioned in ~/.stiti/models/personal_emotion/.
live ──► prosody.update_and_score() and emotion_model.classify() use the active personal head (calibrated,
         abstains below threshold) → fuse() trusts a personal voice read more (calibrated conf, lower bar 0.55)
```

## References
[1] Ma Z. et al. "emotion2vec: Self-Supervised Pre-Training for Speech Emotion Representation." Findings of ACL 2024. arXiv:2312.15185. https://github.com/ddlBoJack/emotion2vec
[2] emotion2vec+ base model card. https://huggingface.co/emotion2vec/emotion2vec_plus_base
[3] Yang S. et al. "SUPERB: Speech processing Universal PERformance Benchmark." Interspeech 2021. arXiv:2105.01051.
[4] Pepino L., Riera P., Ferrer L. "Emotion Recognition from Speech Using wav2vec 2.0 Embeddings." Interspeech 2021. arXiv:2104.03502.
[5] Wagner J. et al. "Dawn of the Transformer Era in Speech Emotion Recognition: Closing the Valence Gap." IEEE TPAMI 2023. arXiv:2203.07378.
[6] Sridhar K., Busso C. "Unsupervised Personalization of an Emotion Recognition System: The Unique Properties of the Externalization of Valence in Speech." IEEE TAC 2022. arXiv:2201.07876.
[7] Tran M., Yin Y., Soleymani M. "Personalized Adaptation with Pre-trained Speech Encoders for Continuous Emotion Recognition." Interspeech 2023. arXiv:2309.02418. https://www.isca-archive.org/interspeech_2023/tran23c_interspeech.html
[8] Busso C., Mariooryad S., Metallinou A., Narayanan S. "Iterative Feature Normalization Scheme for Automatic Emotion Detection from Speech." IEEE TAC 2013.
[9] Dong J., Jia et al., Dang. "Test-Time Adaptation for Speech Emotion Recognition." arXiv:2601.16240 (2026).
[10] Albanie S., Nagrani A., Vedaldi A., Zisserman A. "Emotion Recognition in Speech using Cross-Modal Transfer in the Wild." ACM MM 2018. arXiv:1808.05561.
[11] Blum A., Mitchell T. "Combining Labeled and Unlabeled Data with Co-Training." COLT 1998.
[12] Ishida T., Niu G., Hu W., Sugiyama M. "Learning from Complementary Labels." NeurIPS 2017. arXiv:1705.07541.
[13] Zhang Z., Sabuncu M. "Generalized Cross Entropy Loss for Training Deep Neural Networks with Noisy Labels." NeurIPS 2018.
[14] Han B. et al. "Co-teaching: Robust Training of Deep Neural Networks with Extremely Noisy Labels." NeurIPS 2018.
[15] Abdelwahab M., Busso C. "Active Learning for Speech Emotion Recognition Using Deep Neural Network." ACII 2019.
[16] Settles B. "Active Learning Literature Survey." UW-Madison TR 1648, 2009.
[17] Kirkpatrick J. et al. "Overcoming catastrophic forgetting in neural networks." PNAS 2017.
[18] Rebuffi S.-A. et al. "iCaRL: Incremental Classifier and Representation Learning." CVPR 2017.
[19] Guo C., Pleiss G., Sun Y., Weinberger K. "On Calibration of Modern Neural Networks." ICML 2017.
[20] Geifman Y., El-Yaniv R. "Selective Classification for Deep Neural Networks." NeurIPS 2017.
[21] Koolagudi S. G. et al. "IITKGP-SEHSC: Hindi Speech Corpus for Emotion Analysis." IC3 2011 / Springer CCIS.
[22] Singh G. V. et al. "EmoInHindi: A Multi-label Emotion and Intensity Annotated Dataset in Hindi for Emotion Recognition in Dialogues." LREC 2022.
[23] Kumar S. et al. "SemEval-2024 Task 10: Emotion Discovery and Reasoning its Flip in Conversation (EDiReF)." SemEval 2024 (E-MASAC Hinglish dialogue).
[24] Wadhawan A., Aggarwal A. "Towards Emotion Recognition in Hindi-English Code-Mixed Data: A Transformer Based Approach." WASSA 2021. arXiv:2102.09943.
[25] Schuller B. et al. "The INTERSPEECH 2009 Emotion Challenge." (UAR as the standard unweighted metric.)
[26] Tomashenko N. et al. "The VoicePrivacy 2020 Challenge: Results and findings." Computer Speech & Language 2022.
