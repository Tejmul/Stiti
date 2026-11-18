# Third-party data used by Stiti

Stiti's own code is MIT (see `LICENSE`). The files and downloads below come from other people's datasets and keep
their own licences. Licences were re-read on each dataset's own page on 2026-11-18.

## What is committed in this repository

`tests/fixtures/public_intent.jsonl` — 557 English sentences used only as a test (`tests/public_intent_eval.py`).
Each line names its source in the `src` field. All three licences allow redistribution with attribution.

| `src` prefix | Lines | Dataset | Licence | Where the licence is stated |
|---|---|---|---|---|
| `massive:` | 272 | **MASSIVE 1.1**, en-US, `test` partition. © Amazon.com Inc. or its affiliates. MASSIVE was made by localizing the English text of **SLURP** (Bastianelli et al. 2020), whose text is also CC BY 4.0. | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) | `NOTICE.md` in https://github.com/alexa/massive ; dataset card https://huggingface.co/datasets/AmazonScience/massive |
| `clinc150:` | 197 | **CLINC150** ("An Evaluation Dataset for Intent Classification and Out-of-Scope Prediction"), `data_full.json`, `test` and `oos_test`. | [CC BY 3.0](https://creativecommons.org/licenses/by/3.0/) | `LICENSE` in https://github.com/clinc/oos-eval |
| `presto:` | 88 | **PRESTO**, en-US test partitions (`no_phenomena`, `disfluency`, `revisions`). © Google. | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) | `README.md` in https://github.com/google-research-datasets/presto |

**Changes we made** (CC BY asks us to say so): a subset of each test split was drawn by a fixed hash order; every
line was given one of Stiti's own labels (`gold`: time / todo / tool / chat / control / memory) in place of the
dataset's intent, which is kept after the colon in `src`; MASSIVE lines lost the SLURP wake word ("olly") and had
"a. m." / "p. m." joined to "am" / "pm"; PRESTO lines keep only the last user sentence (and, for the 28 revision
lines, the user sentence before it as `prev`); 80 drawn lines whose published label does not fit Stiti's meaning of
the label were skipped (`BAD_GOLD` in `scripts/build_exemplars.py`). The life-update sentences inside
`tests/public_intent_eval.py` are our own.

## What is downloaded to the user's machine and never committed

`scripts/build_exemplars.py` downloads the same three datasets into `$STITI_HOME/data/` (default `~/.stiti/data/`,
about 22 MB kept) and builds `public_exemplars.npz`: about 3,300 sentences from the **train** splits with Stiti's
labels and their embedding vectors, used by the intent router as examples. No row from these datasets is committed
outside the test fixture above, and no test line is used as a router example. The 36 "counterweight" lines stored
in the same file (`GUARD_EX` in the script) are our own.

## Citations

- FitzGerald, J. et al. (2022). *MASSIVE: A 1M-Example Multilingual Natural Language Understanding Dataset with 51
  Typologically-Diverse Languages.* arXiv:2204.08582.
- Bastianelli, E., Vanzo, A., Swietojanski, P., Rieser, V. (2020). *SLURP: A Spoken Language Understanding Resource
  Package.* EMNLP 2020.
- Larson, S. et al. (2019). *An Evaluation Dataset for Intent Classification and Out-of-Scope Prediction.*
  EMNLP-IJCNLP 2019. https://www.aclweb.org/anthology/D19-1131
- Goel, R. et al. (2023). *PRESTO: A Multilingual Dataset for Parsing Realistic Task-Oriented Dialogs.*
  arXiv:2303.08954.

## Looked at for ideas only (no text copied)

Reply wordings in `src/stiti/say.py` and the example replies in `EXAMPLES.md` are original. Home Assistant
`intents` (CC BY 4.0), Leon (MIT) and OVOS `ovos-skill-alerts` (BSD-3-Clause / Apache-2.0) were read to see which
situations a voice assistant words (confirm, list, cancel, "for when?"); none of their sentences is reused.
