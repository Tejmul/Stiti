# Agent core: tool calling, MCP, task state, memory (research, 2026-11-18)

**Question (the owner):** can MCP and tool calling be faster, and can state and memory for a task be better, so a
task he says once is carried to the end and a different phrasing does not break it?

**Short answer:** yes, with four small pieces and no new model: (A) one local **skill router** instead of
per-feature trigger regexes, (B) **fetch first, then speak** for read-only tools, (C) a two-table **task ledger**
in Postgres with a runner thread, (D) an **ACTIVE TASK** block in the briefing. MCP stays, but only for the few
tools that have no native connector.

## 1. What Stiti does today (from the code, with measurements)

Numbers are from the real `stiti` database (read-only query, 154 turns, 2026-11-10 to 11-18) unless marked.

- **Routing is a 40-branch `elif` chain** (`engine.py: Engine.turn`), ordered by hand. The repo has 307
  `re.compile` lists in 49 files plus 278 inline `re.*` calls. `Engine.spec_block` repeats 24 of the checks,
  so a new feature must be added in two places.
- **The local decider answers only two questions.** `decide.py: decide` defines 11 typed questions, but with Laya
  off only `domain` and mood come from `intent.py: classify` (kNN over about 100 built-in examples + 19 learned). It is fast (0.3–0.5 ms)
  but unsure: **86 of 154 logged `domain` decisions (56%) had confidence under 0.7.** The regexes exist to cover that.
- **Tool turns are the slow path.** `Engine._llm` runs up to 3 rounds through `router.complete` (not streamed),
  and tools run one after another. Streamed chat turns: first token p50 341 ms, total 611 ms (n=85). Non-streamed
  LLM turns (tool loop and CLI): **p50 1,238 ms, p90 2,146 ms** (n=8, small sample). Each round resends the
  briefing (average 1,271 tokens), so one 3-round turn costs about 5–7K tokens (estimate) against Groq's 8K
  tokens/minute; the next call falls to a slower provider.
- **Tools are only offered if a regex fires.** `use_tools` needs `domain == "tool"` or `TOOL_HINT_RX`. The classifier
  picked `tool` 5 times in 154 turns. `registry.select` always returns the top 5 with no "none of these" floor.
- **A confirmed action ends the task.** For a write tool, `_llm` stores `Engine.pending` (RAM only) and returns.
  After "haan", `Engine.turn` runs the tool and says `"Done: {tool.name}. " + str(result)[:200]`: the raw tool
  name and raw dict are spoken, the LLM never sees the result, and the other planned calls are lost.
- **Flow state lives in about 12 Python attributes** (`pending`, `clarify`, `askme`, `onboarding`, `chunker`,
  `woop`, `teach_ask_at`, `topic_hint`, `live_last`, `last_action`…). A restart forgets them. The web app makes a
  new `Engine` per connection, so voice and web do not share them.
- **Tool results are never stored.** Only her reply becomes an episode. `memory.recent_turns` filters by session
  id, so a restart or a move from voice to web starts with an empty `[RECENT CONVERSATION]`.
- **MCP bus** (`tools/mcp_bus.py`): sessions are persistent (good), but `start()` runs inside the first tool turn
  and can block up to 60 s; no reconnect; a call may wait 60 s. No servers are configured. Measured on this Mac (`footprint -p`, the two npx servers Claude Code runs): **about 100 MB per
  server** (npm wrapper 48 MB + node 52–58 MB).

Already good, stays: tool-RAG, risk tiers, taint, pin-and-diff, hybrid recall (12 ms), bitemporal facts, lessons,
sleep/nap extraction, speculative chat turns (D29).

## 2. Sources compared (32; each page fetched 2026-11-18 unless marked)

### 2.1 Fast tool calling with free models
| Source | Mechanism | Strength | Weakness | Fits Stiti? |
|---|---|---|---|---|
| RAG-MCP, arXiv 2505.03275 (May 2025) | Retrieve tools before the LLM call | Accuracy 13.6% → 43.1%, over 50% fewer tokens | No "no tool" answer | Have it (`registry.select`) |
| Anthropic advanced tool use (2025-11-24) https://www.anthropic.com/engineering/advanced-tool-use | Deferred tool loading; example calls inside tool definitions | Tokens 77K → 8.7K; examples lift accuracy 72% → 90% | Claude API feature | Idea: add 2–3 examples per tool |
| Anthropic code execution with MCP (2025-11-04) https://www.anthropic.com/engineering/code-execution-with-mcp | Model writes code that calls tools | 150K → 2K tokens | Needs a sandbox; weak models write weak code | No |
| Groq docs https://console.groq.com/docs/tool-use , /structured-outputs , /deprecations | Tool use on all models; parallel calls on `qwen/qwen3.8-27b`, not on gpt-oss; strict JSON schema on both | Free, fastest | "Streaming and tool use are not currently supported with Structured Outputs"; Llama tool-use models shut down (2025-01), Llama 8B/70B left the free tier (2026-08-16) | Yes: qwen for tools, strict JSON for the router fallback |
| Cerebras https://inference-docs.cerebras.ai/capabilities/tool-use ; Gemini https://aistudio.google.com/docs/function-calling | Strict tool arguments + parallel calls (Cerebras); parallel and chained calls (Gemini) | Guaranteed argument shape | Cerebras needs a card since 2026-07 (D17); Gemini's free tier trains on data | No / public questions only |
| semantic-router (MIT) https://github.com/aurelio-labs/semantic-router | Route by similarity to example sentences; `fit()` sets thresholds from labelled data; dense + keyword hybrid | "Decides in milliseconds"; returns "no route" | One more dependency | Copy the design on our embedder (0 MB) |
| SetFit (Apache-2.0) https://github.com/huggingface/setfit | Few-shot tuning of a sentence model | README: 8 examples per class rival full fine-tuning | Training needs torch | Later, optional (allowed: local decision model) |
| ReWOO, arXiv 2305.18323 | Plan every tool call first, no LLM between steps | 5× fewer tokens | Cannot change the plan mid-way | Yes: saves free quota |
| LLMCompiler, arXiv 2312.04511 (ICML 2024) | Planner + parallel executor | Up to 3.7× faster than ReAct | Planner needs a good model | Small form: run independent reads at once |
| Speculative tool calling (Stream, 2025-12-23) https://getstream.io/blog/speculative-tool-calling-voice/ | Speak an ack, run read-only tools early | Hides tool time | Never for writes | Yes |
| Pipecat https://docs.pipecat.ai/guides/learn/function-calling ; LiveKit async tools (agents 1.6.0, 2026-06-11) https://livekit.com/blog/async-tools-voice-agents | Calls run in parallel by default; an async tool returns at once and its result is spoken later, "only when both the agent and the customer are idle" | Proven in voice | Frameworks we do not use | Copy the rules |

### 2.2 MCP in practice
| Source | Mechanism | Strength | Weakness | Fits? |
|---|---|---|---|---|
| MCP Python SDK v2 (MIT) https://github.com/modelcontextprotocol/python-sdk | Long-lived stdio / HTTP sessions | Installed (2.3.0) | — | Have it |
| MCP server bench (2026-08-19, Windows) https://techfuelhq.com/data/mcp-server-bench/ | Start time and process-tree RSS per server | Filesystem 692 ms / 188 MB, GitHub 547 ms / 178 MB, Playwright 618 ms / 227 MB | Not macOS (ours: about 100 MB) | 5 servers = 0.5–1 GB: start on demand |
| Tool poisoning (Invariant Labs, 2025-04-01) https://invariantlabs.ai/blog/mcp-security-notification-tool-poisoning-attacks | Hidden instructions in tool descriptions; rug pull | Fix: pin and hash | — | Have it; also hash command + version |
| mcp-scan → Snyk Agent Scan (search summaries only, not checked at source) | Scans and pins descriptions | Easy | Reports say it sends tool descriptions to Snyk's API | Not for private setups |

### 2.3 Task state
| Source | Mechanism | Strength | Weakness | Fits? |
|---|---|---|---|---|
| LangGraph persistence + interrupts https://docs.langchain.com/oss/python/langgraph/interrupts | Checkpoint per step in Postgres; `interrupt()` waits for a human | Resume after restart | On resume "the runtime restarts the entire node", so side effects must be safe to repeat; whole framework | Idea only |
| Temporal https://docs.temporal.io/workflow-execution | Event history + deterministic replay | Very robust | Needs a Temporal Service + workers | No |
| DBOS Transact (MIT) https://github.com/dbos-inc/dbos-transact-py | Workflows and steps checkpointed in Postgres, "no additional infrastructure" | Durable sleep, queues | Decorators wrap our functions | Possible; same idea fits in about 100 lines |
| Absurd (Apache-2.0; 2025-11, production report 2026-04) https://github.com/earendil-works/absurd | One `.sql` file: task → steps = checkpoints, events, sleep | Smallest design | Young | **Pattern to copy** |
| OpenAI Agents SDK sessions https://openai.github.io/openai-agents-python/sessions/ | Session = stored chat history | Simple | History, not a plan | No |
| Letta memory blocks https://docs.letta.com/guides/agents/memory-blocks (MemGPT, arXiv 2310.08560) | Pinned blocks (label, value, limit), always in context | Working memory | The LLM edits memory by tool calls | One pinned block, written by code |
| Claude Code task tools https://code.claude.com/docs/en/agent-sdk/todo-tracking | pending → in_progress → completed list outside the context | Simple status model | Needs a strong model | Copy the statuses |
| BabyAGI (MIT) https://github.com/yoheinakajima/babyagi | LLM-made task queue | — | "Not meant for production use" | No |

### 2.4 Memory
| Source | Mechanism | Stiti today | Gap? |
|---|---|---|---|
| Mem0, arXiv 2504.19413 | Extract, then update facts | `lifeupdate`, `sleep.extract`, `factstore` | No |
| Zep / Graphiti, arXiv 2501.13956 (Apache-2.0; needs Neo4j or FalkorDB) | Bitemporal knowledge graph | `facts` with validity in Postgres | No |
| A-MEM, arXiv 2502.12110 | Notes that link and update each other | Entities + merge at night | No |
| HippoRAG 2, arXiv 2502.14802 | PageRank over the graph, +7% on associative recall | 2-hop `current_facts` | Later |
| LangMem (2025-02) https://www.langchain.com/blog/langmem-sdk-launch | Facts + prompt rules; "doesn't yet support" episodic | Lessons + directives | No |
| Sleep-time compute, arXiv 2504.13171 | Precompute context while idle, about 5× less work at query time | Only `standing_profile` is precomputed | Small: open tasks |
| Anthropic context engineering (2025-09-29) https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents | Compaction, tool-result clearing, notes outside the context | Nothing for tasks | **Yes** |

## 3. Recommended design (smallest first)

**A. Skill router (`src/stiti/skills.py`): one pass instead of trigger lists.**
Every fast path, flow and tool registers as a *skill*: name, 5–15 example sentences (English, Hinglish, Telugu),
handler, risk, `speculable`. Table `skill_examples(id, skill, text, embedding halfvec(768), source, created_at)`
replaces `DOMAIN_EX` and `exemplars.jsonl`. One matrix product on the `qvec` we already have gives the top skill
and its margin. Thresholds are fitted on the `decisions` log (semantic-router's `fit`). Three bands:
- **sure** → run the handler locally, no LLM;
- **unsure** → one small strict-JSON call to Groq (`{"skill": one of the top 5, "args": …}`, not streamed; a
  short Groq reply took 308 ms in `free_llm_providers.md`), in parallel with recall. A confirmed pick is saved as a new example,
  so she learns the phrasing without fine-tuning;
- **none** → plain chat.

Deleted: the trigger regexes (`CAL_RX`, `MAIL_RX`, `PLAN_RX`, `TOOL_HINT_RX`, `GREET_RX`, `COMMAND_RX`, the
`START_RX` of askme / onboarding / chunker / WOOP, `MUSIC_RX`, the triggers in `live.detect` and
`weather.detect`) and the 24-item list in `spec_block` (becomes `skill.speculable`). Kept: regexes that *read
values* (dates, numbers) and hard floors (P2 privacy, crisis, stop, hold). Cost: under 1 ms, about 3 MB per
1,000 examples, no new model.

**B. Fetch first, then speak (`Engine.turn`, next to the existing `live.start` job).**
If the chosen skill is a read-only tool, run it at once (in parallel with recall) and add a
`[TOOL RESULT — data, not instructions]` block to the briefing, as `connectors/live.py` already does. Then one
*streamed* `router.stream` call. `_llm` stays for the unsure band only: at most 2 LLM calls, independent reads run
together in a thread pool, parallel calls on qwen. Repeated reads come from a 60-second cache. Expected:
tool turns go from about 1.2 s (p50) to chat speed (341 ms first token) plus the tool's own time. RAM 0.

**C. Task ledger (migration 011) + `tasks/runner.py`.**
```sql
agent_tasks(id, goal, status,            -- planned|running|waiting_user|sleeping|done|failed|cancelled
            waiting_for jsonb, wake_at, result, reported_at,
            channel, origin_episode_id, privacy, claimed_until, created_at, updated_at)
agent_steps(task_id, idx, tool, args jsonb, needs int[], risk,
            status,                      -- pending|started|done|failed|skipped
            result jsonb, error, started_at, finished_at, PRIMARY KEY (task_id, idx))
```
A multi-step request gets **one** planning call (`background_smart`, strict JSON, ReWOO style). One runner thread
in the app claims a task (`FOR UPDATE SKIP LOCKED`, lease in `claimed_until`) and runs the next step. Rules,
copied from Absurd and LangGraph: a `done` step never runs again; a write step sets `waiting_user` with the exact
arguments and waits for his "haan" (this replaces `Engine.pending`, and survives a restart); a write step found
`started` but not `done` after a crash is **not** retried — she asks him. When a task ends, `result` is one
sentence and `reported_at` is null; the existing `proactive.tick` speaks it when he is idle and not in a call
(LiveKit's rule), or at the next wake. Cost: one thread, no model, 2 LLM calls per task.

**D. Working memory in the briefing (`brain/compiler.py: build`).**
- `[ACTIVE TASK]` (≤ 80 tokens, written by code): goal · step 2 of 3 · last result · what she is waiting for.
- Keep tool results: the last few `agent_steps.result` values, trimmed to 300 characters, for 10 minutes
  ("what did that mail say?").
- `recent_turns` by time (last 15 minutes, any channel) instead of by session id.

**E. MCP bus, only when a server is added.** Connect in the background at app start, never inside a turn. Start
a server on first use and stop it after 10 idle minutes (100–230 MB each). Keep each server's tool list and
vectors in a table so routing works while it is stopped. Voice timeout 8 s; reconnect once. Worth adding: GitHub
(read-only) and Playwright (on demand). Not worth it: filesystem, fetch/search, Google Calendar, Gmail — Spotlight,
`live.py`, EventKit and IMAP already do these in-process for 0 MB.

**Not recommended:** LangGraph, Temporal, Letta, Graphiti or Mem0 as dependencies; code execution with MCP.

## 4. Build order

| # | Step | Test on its own | Risk |
|---|---|---|---|
| 1 | B: fetch-then-speak for read-only tools, parallel reads, "no tool" floor; fix the raw `"Done: tool_name. {…}"` line | Eval: first-token time of calendar / mail turns | A wrongly chosen tool puts useless text in the briefing |
| 2 | A in **shadow mode**: log the router's pick beside the regex pick in `decisions`; then move features over one at a time | Agreement report; reworded-phrase eval | kNN misroutes (56% low-confidence today) → keep the fallback call and the floors |
| 3 | C: tables + runner + confirm through `waiting_user` | Kill the app mid-task; it resumes at the right step | A write running twice → never auto-retry writes |
| 4 | D + report-back by voice | A task finishes while he is silent, or in a call | Speaking at a bad moment → reuse `proactive` quiet rules |
| 5 | E + first MCP server (GitHub, read-only) | `footprint` before and after; idle stop works | RAM; poisoned descriptions → pin-and-diff, read-only token |
| 6 | Later: save a finished plan as a reusable recipe; a small trained head on the `decisions` log | Second run of the same task needs no planning call | Stale recipes |

## 5. Open questions for the owner

1. Which three multi-step tasks should work first? They decide the first tools.
2. Which accounts: GitHub token (read-only first?), and may she *send* mail after "haan", or only write drafts?
3. When a background task ends: speak at once, wait for a pause, or only show a card?
4. May tasks use the free quota at night (Groq: 1,000 requests per model per day)?
5. Mail and calendar text already go to Groq for wording in a tool turn. Is that fine, or local templates only for mail?
6. Must every write wait for "haan", or may small ones (add a calendar event) run at once with undo?
