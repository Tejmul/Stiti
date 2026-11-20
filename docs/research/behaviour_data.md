# Behaviour data for Stiti: what exists, what to integrate (research, 2026-11-18)

Question: "People have built Jarvis-like assistants. What data do they use for behaviour and for talking like a human? Find it so we can integrate it."
Builds on `jarvis_persona_psychology.md`, `conversation_turn_taking.md`, `agent_core.md`, `decision_layer_pilot.md`. Pages were fetched today unless marked **n.v.** (not verified). Sizes with "~" come from the paper, not re-checked.

## 1. The honest answer

- **Big assistants (Alexa, Siri, Google) learn phrasing from their own private logs** of real users, labelled by paid staff. They do not publish them. What is public are smaller copies made by crowd workers: MASSIVE, SLURP, PRESTO, TOPv2, MTOP. The Cortana reminder study (Graus 2016) never released its logs.
- **New voice agents get "human talk" from the LLM itself**, a system prompt, and private speech data (Sesame says about one million hours of audio). No one ships a "behaviour dataset".
- **Open-source Jarvis projects ship three things:** hand-written sentence templates (Home Assistant, OVOS), a system prompt with a few example turns (GLaDOS, character cards), and a memory schema (Letta, mem0). That is all.
- **With no LLM fine-tuning, data can do four jobs for Stiti:** (1) examples for the local kNN router, (2) a few example replies inside the briefing, (3) word lists and templates, (4) tests. It cannot change the cloud model's habits. `psych.py` must keep enforcing the rules in code.
- **Public data teaches general phrasing only.** His own confirmed sentences still win, because nobody else speaks his mix of English, Hinglish and Tenglish. I found no Roman-script Telugu data at all.
- **Casual-chat datasets are weak for Stiti.** They are typed by American crowd workers, long, full of questions, and often non-commercial. Use a few hand-picked lines, never in bulk.

## 2. Comparison tables

"Use" codes: **1** router examples / tiny local classifier · **2** example replies in the briefing · **3** templates and word lists · **4** tests and simulated users · **5** ideas only. Effort S / M / L.
Licence short guide: CC BY, CC0, MIT, Apache, BSD = fine with credit. CC BY-SA = fine, but keep it out of the MIT repo. NC = local personal use only, never commit, drop if Stiti is ever sold. NC-ND, "research only", no licence = do not use.

### A. How people phrase assistant requests
| Name | What | Size / languages | Licence | Use | Effort | Verdict |
|---|---|---|---|---|---|---|
| [MASSIVE 1.1](https://huggingface.co/datasets/AmazonScience/massive) | Alexa-style commands; SLURP's text translated and localised by professional translators | 19,521 per locale (11,514 train) × 52 locales, incl. hi-IN and te-IN in native script; 60 intents; card dated 2022 | CC BY 4.0 | 1, 4 | S | **Use first** |
| [SLURP](https://github.com/pswietojanski/slurp) | English source of MASSIVE, with audio | English | text CC BY 4.0, audio CC BY-NC 4.0 | 1 | — | Skip; MASSIVE en covers it |
| [Hinglish-TOP](https://github.com/google-research-datasets/Hinglish-TOP-Dataset) | **Roman-script Hinglish** commands ("jagao mujhe at 7 am"): alarm, reminder, timer, event, weather, music, messaging | 10K human + 170K machine-made | Apache-2.0 (archived 2024) | 1, 4 | S | **Use** the human part |
| [PRESTO](https://github.com/google-research-datasets/presto) | Assistant conversations with labelled disfluency, code-mixing (~14%) and user corrections (~27%); lists, notes, contacts | 550K+; en, de, es, fr, **hi**, ja | CC BY 4.0 (archived 2024) | 1, 4 | M | **Use** for "no, I meant…" cases |
| [CLINC150](https://huggingface.co/datasets/clinc/clinc_oos) | 150 intents (reminder, alarm, todo_list, calendar, timer, small talk) plus **out-of-scope** lines | 23.9K, English | CC BY 3.0 | 1, 4 | S | **Use** for the "none of these" class |
| [HWU64](https://github.com/xliuhw/NLU-Evaluation-Data) | Home-robot commands | 25,716, English | CC BY 4.0 | 1 | S | Optional extra English |
| MTOP ([mirror](https://huggingface.co/datasets/tasksource/mtop)) | Commands in 11 domains (alarm, reminder, timer…) | 100K; 6 languages incl. Hindi | CC BY-SA 4.0 on the mirror; official file n.v. | 4 | S | Test set only, not committed |
| TOPv2 | English source of Hinglish-TOP | 180K, 8 domains | n.v. | — | — | Skip |
| [Home Assistant intents](https://github.com/OHF-Voice/intents) | Hand-written sentence templates, reply templates and tests (timers, lists, date, weather) | 66 languages; Hindi has timers / date / weather (Devanagari), Telugu only on/off; updated 2026-11-17 | CC BY 4.0 | 1, 3, 4 | M | **Use** timers + lists |
| [MS-LaTTE](https://github.com/microsoft/MS-LaTTE) | Real to-do titles labelled with the usual time and place they get done | 10,101, English | MIT (archived) | 1, 4 | M | Later: default times for the planner |
| [PÂTÉ](https://zenodo.org/record/3697930) | Commands with annotated time expressions | 1,188, English | n.v. | 4 | S | Test for `dates.py` after a licence check |
| SNIPS, BANKING77, [Fluent Speech Commands](https://fluent.ai/fluent-speech-commands-a-dataset-for-spoken-language-understanding-research/) | Music / restaurant; bank; smart-home audio | English | CC0; CC BY 4.0; CC BY-NC-ND | — | — | Skip: wrong topics or licence |
| SGD, MultiWOZ, Taskmaster | Multi-turn booking through services | ~20K / ~10K / ~13K, English | CC BY-SA 4.0; MIT; CC BY 4.0 | 5 | — | Skip: typed booking chats |

### B. How humans talk casually
| Name | What | Size / languages | Licence | Use | Effort | Verdict |
|---|---|---|---|---|---|---|
| [CANDOR](https://huggingface.co/datasets/betterup/candor-tabular) | **Real spoken** video calls; turn tables with backchannels ("mm-hm"), pauses, overlaps | 1,656 calls, ~860 h, 9.8M words; tabular part 11 GB; US English | CANDOR Licence 2.1: free, commercial OK, no re-sharing; manual approval | 3, 4 | M | **Best real-speech source**; needs his application |
| [ESConv](https://github.com/thu-coai/Emotional-Support-Conversation) | Support chats; every helper turn labelled with 1 of 8 strategies | 1,300, English | CC BY-NC 4.0; GitHub says "academic research use only" | 2, 4 | M | Local only: test the strategy picker, borrow ~30 short lines |
| [EmpatheticDialogues](https://huggingface.co/datasets/facebook/empathetic_dialogues) | Situations labelled with 32 emotions | ~25K, English | CC BY-NC 4.0 | 1 | S | Local only: mood examples (mood kNN is 14/30) |
| [SODA](https://huggingface.co/datasets/allenai/soda) | LLM-written everyday dialogues | 1.49M, English | CC BY 4.0 | 2 | M | Sample short turns, he reviews |
| [Hinglish Everyday Conversations](https://huggingface.co/datasets/Abhishekcr448/Hinglish-Everyday-Conversations-1M) | One-turn Roman Hinglish pairs written by GPT-4o-mini | 1M | MIT | 1, 2 | S | Sample 200, he reviews; textbook-like |
| DailyDialog | Written daily dialogues | ~13K, English | CC BY-NC-SA 4.0 | — | — | Skip: formal, NC-SA |
| PersonaChat / ConvAI2, Blended Skill Talk, [Synthetic-Persona-Chat](https://huggingface.co/datasets/google/Synthetic-Persona-Chat) | Strangers interviewing each other from persona cards | ~11K / ~7K / 10K+ | none stated; unknown; CC BY 4.0 | 5 | — | Skip: teaches the "interview" habit Stiti bans |
| [Topical-Chat](https://github.com/alexa/Topical-Chat), ProsocialDialog, LIGHT | Fact chats; safety replies; fantasy role-play | 10,784 / ~58K / — | CDLA-Sharing-1.0; CC BY 4.0; MIT repo | — | — | Skip: long, preachy, or wrong world |
| [Switchboard](https://catalog.ldc.upenn.edu/LDC97S62) / Fisher | Phone calls from the 1990s–2000s | 2,400 calls, 260 h | LDC licence, fee | 5 | — | Skip: paid; CANDOR is newer and free |
| GupShup | Hinglish chats for summarising | n.v. | request form; no data licence stated | — | — | Skip |

### C. Timing and manner in voice
| Name | What | Size / languages | Licence | Use | Effort | Verdict |
|---|---|---|---|---|---|---|
| [Smart Turn v3.2 data](https://huggingface.co/datasets/pipecat-ai/smart-turn-data-v3.2-train) | Clips labelled "turn finished?" with mid / end filler flags | 270,946 clips, 41 GB; 23 languages incl. Hindi, no Telugu | CC BY 4.0; model BSD-2 | 5 | L | Keep the model; do not download |
| TurnGPT, VAP, MaAI | Turn-shift and backchannel predictors | en / zh / ja; trained on LDC data | MIT code | 5 | — | Covered in `conversation_turn_taking.md`; no change |
| CANDOR turn tables (see B) | Real gaps, overlaps, listener words | — | — | 3, 4 | M | Check our timing constants against real talk |
| [Full-Duplex-Bench](https://github.com/DanielLin94144/Full-Duplex-Bench) | Tests for pause handling, backchannels, turn-taking, interruption; v3 adds disfluent speech with tool calls | English | n.v. | 5 | L | Copy the four test types into `turn_eval.py` |
| PodcastFillers | 35K "uh / um" events | 145 h | labels research-only | — | — | Skip |
| [OpenAI realtime-agents metaprompt](https://github.com/openai/openai-realtime-agents) | Voice-prompt schema: Demeanor, Tone, Enthusiasm, Formality, Emotion, Filler Words, Pacing; "repeat names and numbers back" | one file | MIT | 3, 5 | S | Add the repeat-back rule to DO confirmations |

### D. Open-source assistants: behaviour assets
| Name | What it contains | Licence | Use | Effort | Verdict |
|---|---|---|---|---|---|
| Home Assistant Assist | See A | CC BY 4.0 | 1, 3, 4 | M | Most reusable asset found |
| [OVOS](https://github.com/OpenVoiceOS/ovos-skill-alerts) (Mycroft, archived) | Per-skill `.intent` / `.dialog` / `.vocab` files; alerts skill has 22 locales, no hi / te | BSD-3 (skill), Apache-2.0 (core) | 1, 3 | S | Borrow alarm / reminder wordings |
| [Leon](https://github.com/leon-ai/leon) | To-do and timer skills: answer lines and "missing detail" questions; no user sentence lists in the files I read | MIT | 3 | S | Borrow the follow-up questions |
| Rhasspy | Template grammars; archived 2025 | MIT | 5 | — | Idea only |
| [GLaDOS](https://github.com/dnhkng/GLaDOS) | YAML persona: one system line plus example user / assistant turns | MIT | 2 | S | **Copy the pattern**, not the text |
| SillyTavern + Character Card V2 | Card fields: `personality`, `scenario`, `first_mes`, `mes_example`. Cards on chub are user uploads | AGPL-3.0; spec has no licence | 5 | S | Take the `mes_example` idea only |
| Letta, mem0 | Persona / human memory blocks; fact-extraction prompt with examples | Apache-2.0 | 5 | — | Stiti already has both (SOUL.md, `sleep.extract`) |
| khoj, Open Interpreter | Prompts for search and computer control | AGPL-3.0; Apache-2.0 | 5 | — | Not about talking; never copy AGPL text |
| System-prompt collections; [Anthropic's published prompts](https://platform.claude.com/docs/en/release-notes/system-prompts) | Leaked vendor prompts (GPL label, 144K stars) vs official ones | unclear vs official | 5 | — | Read for ideas |
| AIRI, huggingface/speech-to-speech, "jarvis" repos | Pipeline plus one prompt | MIT / Apache-2.0 | — | — | No behaviour data |

### E. When to speak up, ask, or stay quiet
| Name | What | Size | Licence | Use | Effort | Verdict |
|---|---|---|---|---|---|---|
| [ProactiveBench](https://github.com/thunlp/ProactiveAgent) | Screen-activity events; did the user want the offered help? | 6,790 events (coding, writing, daily life) | Apache-2.0 | 5 | M | General LLMs judge this badly (F1 ≤ 0.67); the authors' tuned judge reaches 0.92. So learn the gate from his reactions, don't ask the LLM |
| ContextAgent (arXiv 2505.14668) | Proactive help from sensor context | 1,000 samples, 9 daily scenarios | n.v. | 5 | — | Idea only |
| Inner Thoughts (CHI 2025, arXiv 2501.00383) | Score each thing she could say by "how much it wants to be said" | — | paper | 5 | S | Small score gate for `proactive.py` |
| Cha 2020; Pielot 2017; Graus 2016 | Smart-speaker study (40 people, 3,572 answers); phone study (337 users); Cortana reminders | data private | — | 5 | — | Bad moments: studying, tired, busy hands. The user's own past reactions predict best. Confirms Stiti's per-kind bandit |
| ClariQ, Qulac, AmbigQA, CLAMBER | Ambiguous web-search questions | 237 topics / — / ~14K / ~12K | none; MIT; CC BY-SA 3.0; n.v. | 5 | — | Wrong domain |
| [IN3](https://github.com/OpenBMB/Tell_Me_More) | Tasks labelled vague or clear, with the missing details | n.v. | Apache-2.0 | 1, 4 | M | Closest fit for a "needs a question?" check |
| [τ-bench](https://github.com/sierra-research/tau-bench) / τ²-bench | An LLM plays the user; the test checks the final database state | airline, retail | MIT | 4 | M | Copy the method, not the data |

## 3. Recommended integration, smallest first

**Step 1 — A real yardstick (S).** Today: 30 synthetic turns plus 34 lines in `intent_eval.py`. Add `tests/public_intent_eval.py`: about 600 held-out lines from the MASSIVE *test* split (en, hi, te), Hinglish-TOP *test*, PRESTO Hindi code-mix and revision sets, and CLINC out-of-scope. Record the baseline: accuracy, and the share of decisions under 0.7 confidence (56% in the real log). Data is downloaded to `~/.stiti/data/`, never committed.

**Step 2 — Public examples for the router (S–M).** One script, `scripts/build_exemplars.py`, fills the `skill_examples` table planned in `agent_core.md` §3A (`source='massive'` …) with stored vectors. Label map: `alarm_*` → time; `lists_*` → todo; `calendar_set` with "remind" → time, else tool; `calendar_query/remove`, `weather_query`, `news_query`, `email_*`, `play_music` → tool; `general_*`, `qa_*` → chat; `audio_volume_*` → control. Hinglish-TOP alarm / reminder / timer → time, rest → tool. CLINC out-of-scope → a new `none` label.
- Size: 40 varied lines per intent per language, about 4,000 rows. RAM about 12 MB; one matrix product, under 1 ms. Vectors must be stored: `intent._index()` re-embeds every line at start, which would take about 30 s.
- Personal examples still win: owner rows get a small score bonus. MASSIVE Hindi and Telugu are in native script, but STT is pinned to English / Roman output by default, so Hinglish-TOP does the Hinglish work and Tenglish stays his own.
- Risk: more calendar lines may pull "Mummy is coming home tomorrow" to *time* again. Run in shadow mode first; `intent_eval.py` must not drop.
- Gain to expect: low-confidence share from 56% to under 30%, fewer regex trigger lists.

**Step 3 — Templates and word lists (S).** Home Assistant reply templates, Leon's missing-detail questions and OVOS alert dialogs give 4–6 wordings each for confirmations and for "For when?". They go into `fastpath/handlers.py` and `speaker.py` (`ACKS` has 5 lines, `FILLERS` 3), picked through `norepeat`. If CANDOR is approved, its most common listener words extend `BACKCHANNEL_WORDS` in `voice/endpoint.py`. Measure: false barge-ins in `turn_eval.py`; repeated confirmations in `no_repeat_eval.py`.

**Step 4 — Example replies in the briefing (M).** New `~/.stiti/EXAMPLES.md`, readable and editable like SOUL.md: 6–10 short pairs per strategy (LISTEN, ACKNOWLEDGE, BANTER, SOLVE, REPAIR). The compiler adds two pairs for the chosen strategy, nearest to his sentence, under `[EXAMPLES — style only, never copy the words]`: about 70 tokens, dropped first when over budget. Sources in order: replies he reacted well to (`learning.mark_outcome`), the lines in `jarvis_persona_psychology.md` §1.1, then filtered ESConv / SODA / Hinglish lines (≤ 20 words, must pass `psych.BANNED_RX`) that he approves. Measure on 30 fixed turns with two free models: how often `psych.enforce` must change the reply, question rate, word count. Risk: weak models copy examples; the said-ledger catches it.

**Step 5 — Tiny local heads (M).** Logistic regression on the 768-d vectors (numpy, no torch) for `is_correction` (PRESTO revisions plus his log), `needs_clarify` (IN3 plus his log) and mood (EmpatheticDialogues, local only). Test the strategy picker against ESConv's human labels: does LISTEN fire where humans chose reflection? Each head replaces a regex only when it beats it on the Step 1 set.

**Step 6 — Proactive and simulated days (L).** No dataset to import. Keep the bandit. Add an Inner-Thoughts style score, MS-LaTTE's "usual time" as a default reminder offer, and a scripted day replayed through `Engine.turn` that checks Postgres state (the τ-bench method).

**Licence duties.** Add `docs/THIRD_PARTY_DATA.md`: "Uses examples from MASSIVE 1.1 (FitzGerald et al. 2022, Amazon, CC BY 4.0), Hinglish-TOP (Agarwal et al. 2022, Google, Apache-2.0), CLINC150 (Larson et al. 2019, CC BY 3.0), PRESTO (Goel et al. 2023, Google, CC BY 4.0) and Home Assistant intents (CC BY 4.0). Changes: relabelled to Stiti's domains and subsampled." Copy each citation from the dataset's own README. Commit the script, never the rows.

## 4. What NOT to use, and why

- **Licence:** Switchboard / Fisher (paid), Fluent Speech Commands (NC-ND), PodcastFillers labels (research only), TOPv2, PÂTÉ, CLAMBER, ContextAgent and Full-Duplex-Bench (not verified), GupShup, ClariQ and PersonaChat (no data licence), chub character cards and leaked prompts (unclear rights), khoj and SillyTavern text (AGPL against our MIT repo).
- **Wrong register:** PersonaChat, Blended Skill Talk, Topical-Chat, DailyDialog, ProsocialDialog, LIGHT. Typed, long, question-heavy or preachy: the tics `psych.py` removes.
- **LLM-written sets in bulk** (SODA, Hinglish 1M, Synthetic-Persona-Chat): they carry the "AI voice". Sample and review only.
- **Size:** Smart Turn data (41 GB), CANDOR raw (950 GB).
- **Privacy:** never send his real conversations to any service for labelling. All tests on real chats stay on the Mac.
- **Fine-tuning a cloud or local LLM on any of this:** against the rules, and not needed.

## 5. Open questions for the owner

1. May a script download about 30 MB of public data into `~/.stiti/data/`? Nothing is committed.
2. NC data (ESConv, EmpatheticDialogues) for local use only: fine for a personal project, a problem if Stiti is ever sold. Use or skip?
3. Will you apply for CANDOR? It needs your email and 3–5 sentences about the use.
4. Will you spend 20 minutes approving about 60 example replies for `EXAMPLES.md`? This is the highest-value "data" in this document.
5. The 30 real sentences for `gold_turns.py` are still missing. Can you speak them once?
