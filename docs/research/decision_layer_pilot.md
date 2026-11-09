# Decision layer pilot (build step 4) — 2026-11-10, Apple M2 8 GB

30 synthetic Hinglish/English turns with gold labels (`tests/gold_turns.py`, written by Claude —
**replace with 30 of Tejmul's real sentences** and re-run). Scripts: `tests/laya_pilot.py`.

| Decider | Domain | Correction* | Privacy | Mood | p50 latency | Max RSS |
|---|---|---|---|---|---|---|
| Laya 0.4.30 multilingual (torch, CPU) | 13/30 | 29/30 | 21/30 | 9/30 | 203 ms | 2,694 MB |
| Laya 0.4.30 english (torch, CPU) | 15/30 | 29/30 | 18/30 | 19/30 | 514 ms | 2,920 MB |
| **Exemplar kNN on EmbeddingGemma q4** (`stiti/intent.py`) | **26/30** | 29/30* | regex floor | 14/30 | **8 ms** | **613 MB total** (embedder shared) |

\* correction = Laya `is_correction` ≥ 0.6 OR the Hinglish/English correction lexicon; the lexicon does most of the work.

**Findings**
- Laya zero-shot domain accuracy ≈ coin-flip on Hinglish, matching the research warning (0.36 base on its own benchmark).
- With torch on CPU it alone uses ~2.1 GB beyond the embedder → blows the 3 GB local budget; 200–500 ms > 100 ms target.
- No ONNX exporter ships in the `laya` package (only an `ONNXAgent` loader), so the INT8 path needs a custom export.

**Decision (D10):** hot path uses exemplar kNN + rules; Laya stays integrated behind `STITI_LAYA=multilingual`
(default `off`) and returns when (a) an ONNX/INT8 export brings it under ~400 MB / 100 ms and (b) it is
calibrated/fine-tuned on Stiti's own `decisions` log.
