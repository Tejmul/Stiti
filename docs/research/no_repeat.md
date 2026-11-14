# No-repeat: tracking what Stiti already said

Research for the "she re-lists the same facts" bug. 2026-11-14.

## 1. The problem (real logs, paraphrased)

| Turn | User | Stiti |
|---|---|---|
| 1 | "What do you know about me?" | School, two projects, football |
| 2 | "Okay, what else do you know?" | School, projects, football **again**, plus one new item |
| 3 | "And what else?" | The same three again, plus one more new item |
| 4 | (same question word for word) | Same reply word for word |

Root causes:

1. **No record of what was said.** `gate.mark_volunteered` only feeds the G4 cool-down for memories she brings up herself. When he *asks*, `asked=True` skips the gate entirely.
2. **History is cut short.** `compiler.build()` RECENT is the last 6 episodes, each cut to 160 chars. That is about 3 exchanges, and her own answers lose their tails.
3. **"What else" isn't detected.** `memory.recall()` embeds "what else do you know", which means nothing on its own. `standing_profile()` sits in *every* briefing, so the same profile lines return each turn. With the same briefing and temperature 0.6, the same question gets the same reply.
4. **Cancelled fragments stay.** `engine.turn()` writes the user episode early (line ~404). When `pend.cancelled` fires in `voice/loop.py`, that fragment is never removed, and the joined utterance is stored again as well.

## 2. Comparison

| # | Approach (source) | Mechanism | Strengths | Weaknesses | Fits free + 8 GB + no fine-tune? |
|---|---|---|---|---|---|
| 1 | Grounding / common ground: Clark & Brennan 1991 ([pdf](https://web.stanford.edu/~clark/1990s/Clark,%20H.H.%20_%20Brennan,%20S.E.%20_Grounding%20in%20communication_%201991.pdf)); Traum's grounding acts/units, applied in [arXiv 2403.16609](https://arxiv.org/abs/2403.16609) | Speakers keep a shared "we both know this now" set, updated each utterance | The right model: said and heard = known, so don't re-say it | Theory only. Needs evidence it was heard | **Yes**, as the said ledger |
| 2 | Information-state update: Larsson & Traum 2000 ([pdf](https://people.ict.usc.edu/~traum/Papers/is2000.pdf)) | Explicit dialogue state, changed by rules for each dialogue move | Deterministic and cheap. "More" is a move over the state | Hand-written rules | **Yes** (the pattern) |
| 3 | Dialogue state tracking: TRADE ([arXiv 1905.08743](https://arxiv.org/abs/1905.08743)) | A neural model fills slots every turn | Carried state beats re-reading history | Supervised training. Tracks slots, not "already said" | No (training); idea only |
| 4 | Rasa tracker + slots ([slots](https://legacy-docs-oss.rasa.com/docs/rasa/2.x/reference/rasa/shared/core/slots), [tracker](https://legacy-docs.rasa.com/docs/core/api/tracker/)) | Event-sourced conversation tracker. Slots can steer the policy | State lives in code, can be undone | Heavy framework | **Yes** (the pattern) |
| 5 | Unlikelihood training: Welleck et al. 2019 ([arXiv 1908.04319](https://arxiv.org/abs/1908.04319)) | A loss pushes down repeated tokens and n-grams | Large repetition drop | Trains the LLM | **No** |
| 6 | "Don't Say That!": Li et al. 2020 ([arXiv 1911.03860](https://arxiv.org/abs/1911.03860)) | Unlikelihood for dialogue: context copying, repeats, contradictions | Names our failure: dialogue models over-copy from context | Training | **No** |
| 7 | DITTO: Xu et al. 2022 ([arXiv 2206.02369](https://arxiv.org/abs/2206.02369)) | Shows repetition reinforces itself. Fix by training on fake repeats | Finding: **a sentence already in context is more likely to be produced again** | Fix needs training | The fix: no. The finding shapes §4 |
| 8 | Contrastive search: Su et al. 2022 ([arXiv 2202.06417](https://arxiv.org/abs/2202.06417)) | Decoding penalises candidates similar to the context | No training | Needs logits and hidden states, which APIs don't expose | No |
| 9 | `no_repeat_ngram_size` / `encoder_no_repeat_ngram_size` ([HF](https://huggingface.co/docs/transformers/en/main_classes/text_generation)) | Bans n-grams already generated (or present in the input) | Exactly "don't repeat context" | Local decoding only. Also blocks names that must repeat | Via API: no. **Copied as a post-filter** |
| 10 | `presence_penalty` / `frequency_penalty` | Logit penalty on tokens already in the **generated output**: "in the generated text so far" ([vLLM](https://docs.vllm.ai/en/latest/api/vllm/sampling_params.html)); only `repetition_penalty` also counts the prompt | One parameter | Works **inside one reply only**. Groq: "not yet supported by any of our models" ([ref](https://console.groq.com/docs/api-reference)). Z.ai doesn't list it ([ref](https://docs.z.ai/api-reference/llm/chat-completion)). Listed by Cerebras ([ref](https://inference-docs.cerebras.ai/api-reference/chat-completions)), Cloudflare ([ref](https://developers.cloudflare.com/workers-ai/models/gpt-oss-120b/)) and Mistral ([ref](https://docs.mistral.ai/api/)). OpenRouter: depends on the provider ([ref](https://openrouter.ai/docs/api/reference/parameters)) | Free, but **doesn't fix cross-turn repeats** |
| 11 | MMR: Carbonell & Goldstein 1998 ([doi](https://doi.org/10.1145/290941.291025)) | λ·relevance − (1−λ)·max similarity to items already picked | Diverse retrieval in microseconds | Needs a meaningful query | **Yes**, with already-said items in the "picked" set |
| 12 | MemGPT / Letta ([arXiv 2310.08560](https://arxiv.org/abs/2310.08560)) | FIFO queue plus recursive summary; full searchable recall store | Never loses history. Recent turns stay verbatim | The LLM pages its own memory, which means many slow calls | Partly: verbatim recent turns |
| 13 | Mem0 ([arXiv 2504.19413](https://arxiv.org/abs/2504.19413)) | Top-10 similar memories, then an LLM picks ADD/UPDATE/DELETE/NOOP | Dedups what is **stored** | One LLM call per fact. Doesn't dedup speech | Idea only |
| 14 | LangChain summary buffer ([ref](https://python.langchain.com/api_reference/langchain/memory/langchain.memory.summary_buffer.ConversationSummaryBufferMemory.html)); LlamaIndex `ChatSummaryMemoryBuffer` ([docs](https://developers.llamaindex.ai/python/examples/memory/chatsummarymemorybuffer/)) | Recent messages verbatim up to a token limit; older ones in an LLM summary | Verbatim recent window is the norm | The summary costs an LLM call. No "said" tracking | The window: yes |
| 15 | Alexa lists ([Alexa Haus](https://developer.amazon.com/en-US/alexa/alexa-haus/patterns-and-components/patterns-lists); [3–4 items](https://developer.amazon.com/blogs/alexa/post/151868d3-9a6e-45b7-8eb4-67542eeebe2e/things-every-alexa-skill-should-do-simplify-choices)) | Paginate. Support "next / more / repeat". The skill holds the cursor | "More" = **next page**. "Repeat" is a separate intent | Built for menus | **Yes** |
| 16 | Pipecat interruptions ([docs](https://docs.pipecat.ai/pipecat/fundamentals/interruptions)); LiveKit preemptive generation ([docs](https://docs.livekit.io/agents/logic/turns/tuning.md)) | Pipecat stores only the words actually spoken. LiveKit: "the preemptive response should be canceled when the final transcript changes" | Context = what was heard. Superseded replies are thrown away | Neither covers a stored *user* fragment | **Yes** |

**Takeaway:** everything that fits the rules is state kept in code (1, 2, 4, 11, 15, 16). The sampling-side fixes either need training (5–8) or only work inside one reply (9, 10). That is the principle: the brain decides, the LLM only words it.

## 3. Recommendation for Stiti

**3.1 Said ledger** (per session, in RAM on the Engine)
- `items`: ids she actually said: `F<fact>`, `E<episode>`, `D<chunk>`, plus **`U<n>` for each `standing_profile()` line** (that's where school, projects and football come from).
- Attribution runs after each reply, also on asked turns. Use `mark_volunteered`'s ≥ 2 content-word overlap, or cos(sentence, item) ≥ 0.80.
- `sent_vecs` (N×768): her spoken sentences, embedded with `task: sentence similarity | query: ` ([EmbeddingGemma card](https://ai.google.dev/gemma/docs/embeddinggemma/model_card)). Store only what was **heard**: drop vectors for text removed by `truncate_last_reply`.
- `anchor`: the last non-MORE question and its qvec, plus a `cursor`.
- For audit, log the ids in `turns.recalled` as `"said"`. No new table.

**3.2 MORE / REPEAT intent** (local regex, before Laya; later a `wants_more` Laya head)
- MORE (English): `what else`, `anything else (you know)`, `(tell me) more`, `go on`, `and?`.
- MORE (Hinglish): `aur (batao|kya|kuch)`, `iske alawa`, `aage`, `baaki`.
- MORE (Telugu): `inka (cheppu|emi|em|enti|emaina)`, `marinni`.
- **Change:** bare `inka` is "more" in Telugu but "their" in Hindi. Accept it only with Telugu language detection, a Telugu verb after it, or as a ≤ 3-word turn right after an informational answer.
- Fire only after an informational answer, never after a fast-path "Anything else?".
- REPEAT (`say that again`, `kya bola`, `malli cheppu`) **turns the dedup filter off**.
- **Addition:** an identical question (cos ≥ 0.95 to the last user turn) counts as REPEAT if her last reply was cut off, otherwise as MORE with a one-clause recap. That fixes the word-for-word identical reply.

**3.3 Compiler on MORE**
- Retrieve with the **anchor** qvec (k = 16) plus all current facts about him.
- Remove ledger items. Rank the rest with MMR (λ = 0.7), where redundancy covers both the picked items and `sent_vecs`.
- Serve 2–3 items (one "page") and move the cursor forward.
- Add an `[ALREADY SAID — don't repeat; only new items]` block of gists (≤ 120 tokens) before the rules block.
- If no unused item clears sim 0.25, **skip the LLM**: "That's most of what I know so far — tell me more and I'll remember it." (Hinglish: "Abhi itna hi pata hai — aur batao, yaad rakh lungi.")

**3.4 RECENT**
- Last 10 episodes. Her replies in full (≤ 480 chars; she's already capped at about 90 words), user turns ≤ 240 chars.
- That's about 400 more tokens. Add RECENT to the over-budget drop order: oldest pair after memory lines, never the last 2 exchanges.

**3.5 Near-duplicate sentence filter** (StreamLint + `enforce()`)
- At each sentence start (where StreamLint already judges), embed the first clause and compare it to `sent_vecs`.
- Drop it if cos ≥ **0.90** **and** it has no content word missing from the ledger's said words. The word guard is needed because a "same template, different fact" pair scored 0.875.
- A dedup drop sets `skip`, **not** `done`, so a following new sentence still plays.
- **Bug to fix with it:** when `lint.said == 0`, `voice/loop.py` speaks `result["reply"]` in full, which would replay the duplicates. Use the honest "that's most of what I know" line instead.
- Cost, measured on this M2 today: 11 ms median, 28 ms p90 per sentence (EmbeddingGemma q4, under load). The compare against an 80-row ledger is about 4 µs. That adds about 11 ms to first audio; later sentences overlap TTS. Skip it while the ledger is empty.

**3.6 Cancelled fragments.** On the `pend.cancelled` path (next to `_undo_replaced`), call `engine.drop_fragment(user_ep)`. It deletes the fragment episode, plus the reply episode and turn row if they were written. The joined utterance holds the full text, so nothing is lost. This is the LiveKit discard idea applied to user turns.

**3.7 presence/frequency_penalty: don't rely on them.** They only act inside one reply, and Groq (the top three `voice_fast` models) rejects them as unsupported. OpenRouter's `repetition_penalty` counts the prompt too, so it would also penalise names she *should* say. Optional and low value: `frequency_penalty=0.3` for Cerebras, Cloudflare and Mistral only.

## 4. Risks and thresholds

| Knob | Start | Risk / tuning |
|---|---|---|
| Dedup cosine | 0.90 + word guard | Measured: paraphrase 0.93–0.95, template with a different fact 0.875, subset sentence 0.82, unrelated 0.47–0.56. Hinglish↔English paraphrase is only 0.85 and slips through; the fact-id ledger catches it. Log each drop with its score. |
| Copy reinforcement (Xu 2022) | — | Full own replies in RECENT *raise* copying. Ship the ALREADY-SAID block and the output filter **together** with the RECENT change. |
| MORE false positives | ≤ 4 words, after an answer | "Aur?" after a todo, or Hindi *inka*. Log the trigger; move it into Laya with calibrated confidence later. |
| Attribution misses | 2 words / cos 0.80 | Short facts get offered again. Watch the logs. |
| Over-suppression | — | REPEAT and a one-clause recap must pass. |
| MMR λ | 0.7 | Lower it to 0.5 if MORE answers stay close to the first answer. |
| Exhaustion floor | sim 0.25 | Too high and she wrongly says she knows nothing more. |
| Ledger scope | session | A new session resets it. A recap the next day is human. |
| Latency | +11 / +28 ms | Within the < 1 s budget. Don't embed while recall holds `embed._lock`. |
