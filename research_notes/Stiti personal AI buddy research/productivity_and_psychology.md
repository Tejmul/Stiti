# Life-Management Layer for Stiti: Todos, Scheduling, Goal Breakdown, Habits, Motivation Psychology, Proactive Nudges, macOS Alarms

Scope note: researched 2026-11-10 for a local-first, zero-cost voice buddy on an Apple M2 / 8 GB Mac. Decisions belong to the deterministic decision model (Laya) and the memory engine. The LLM only phrases things and proposes decompositions. Each feature below covers 10+ papers, algorithms or projects in a comparison table before the recommendation. Items marked "(not re-verified this session)" are canonical projects whose URLs I know but did not fetch during this research. Everything else comes from search results retrieved this session. Several sources are secondary summaries; this is flagged where it matters.

**Original measurement in this session:** I benchmarked CP-SAT (OR-Tools 9.15, Python 3.14) on this Mac (Apple M2, 8 GB). The script is `/private/tmp/claude-501/-Users-tejmul-Stiti/438cc315-bb0b-4ab1-b313-887493e51886/scratchpad/bench_cpsat.py`. Results are in Feature 2.

---

## 1. Todo / task management: data model, prioritization and existing open-source tools

### Takeaway
No open-source tool combines task storage, explainable prioritization and voice. Stiti should own a small local SQLite task store, using Taskwarrior-style field semantics: due, scheduled, wait, depends, tags, priority and user-defined attributes. It should rank tasks with a transparent, Taskwarrior-style weighted urgency sum, extended with TMT terms (expectancy, value, delay, aversiveness). Apple Reminders should be a two-way sync target, not the source of truth.

### Cited Findings

| # | Name | Link | Year | Mechanism / evidence | Strengths | Weaknesses | Fit for local voice buddy |
|---|---|---|---|---|---|---|---|
| 1 | Taskwarrior urgency | [taskwarrior.org/docs/urgency](https://taskwarrior.org/docs/urgency/) | ongoing (v2/v3) | "Urgency is a simple sum of terms, each weighted by a configurable coefficient." Documented defaults include `+next` = 15.0 and due = 12.0. Tag and annotation terms are scaled 0.8/0.9/1.0. | Transparent, tunable and explainable ("this is first because it's due tomorrow"). Coefficients can be negative. | Hand-tuned weights, no learning, CLI-only | High as a *pattern*. Laya can compute it deterministically. |
| 2 | Taskwarrior priority/UDA coefficients | [taskwarrior.org/docs/priority](https://taskwarrior.org/docs/priority/), [UDAs](https://www.taskwarrior.org/docs/udas) | ongoing | Priority H/M/L = 6.0/3.9/1.8. A community config also lists age 2.0 (max 365 d), blocking 8.0, blocked −5.0, scheduled 5.0 and waiting −3.0 ([Taskwarrior urgency](https://taskwarrior.org/docs/urgency/); the community values may not match current defaults). User-defined attributes allow custom fields such as `energy` or `effort`. | Custom attributes map well to energy and effort fields | Same as above | High (field semantics) |
| 3 | Obsidian Tasks urgency (Taskwarrior clone) | [publish.obsidian.md/tasks/Advanced/Urgency](https://publish.obsidian.md/tasks/Advanced/Urgency) | 2022– | Re-implements Taskwarrior-style urgency for Markdown tasks. Its due-date gradient and age cap are its own approximation, not Taskwarrior's ([obsidian-todoseq](https://scross01.github.io/obsidian-todoseq/urgency.html)). | Shows the urgency formula ported to plain-text tasks | Plugin-specific | Medium (reference implementation) |
| 4 | Vikunja | [selfhosted guide](https://selfhosted-sh.pages.dev/vikunja-task-management); [community urgency request](https://community.vikunja.io/t/introduce-configurable-urgency-mechanism-akin-to-taskwarrior/4007) | 2018– | Go server, REST API, Docker, mobile apps. Imports from Todoist and Trello. Users have asked for Taskwarrior-like urgency, which it lacks. | Full API, multi-device | Needs a server process, which costs RAM on 8 GB | Low–Medium (overkill as the store; possible sync target) |
| 5 | Super Productivity | [dev.to comparison by its author](https://dev.to/johannesjo/open-source-productivity-apps-in-2025-a-careful-comparison-4l8e); [openalternative](https://openalternative.co/alternatives/super-productivity) | 2016– | MIT licence. Local IndexedDB storage. CalDAV and WebDAV sync. Jira, GitHub and GitLab integrations. Time tracking. | Local-first, no server, time-boxing built in | Electron (RAM), no voice/LLM API surface | Medium (UX reference) |
| 6 | Khoj | [openalternative.co/khoj](https://openalternative.co/khoj) | 2021– | AGPL-3.0 self-hostable AI assistant. Docs and web search, agents, scheduled automations. | "Scheduled automations" resemble proactive check-ins | It is a second-brain/research tool, not a task manager. AGPL. | Low–Medium (architecture reference) |
| 7 | FluidCalendar | [github.com/jjc6676/fluid-calendar](https://github.com/jjc6676/fluid-calendar); [Cloudron forum](https://forum.cloudron.io/topic/15072/fluidcalendar-open-source-alternative-to-motion-cal.com-for-intelligent-task-scheduling-time-scheduling-calendar-merging/2) | 2025– | Open-source Motion alternative that combines tasks and auto-scheduling. Self-hosted. "Still in active development." | Closest open product to Motion | Web stack, immature | Medium (feature checklist) |
| 8 | Atomic (rush86999) | [awesome.ecosyste.ms entry](https://awesome.ecosyste.ms/projects/github.com%2Frush86999%2Fatomic) | 2023– | Positions itself as an alternative to Motion, Clockwise and Reclaim. Docker Compose. Licence unclear. | Ambitious feature set | Licence unclear, heavy Docker stack | Low |
| 9 | Apple Reminders via EventKit | [EKReminder docs](https://developer.apple.com/documentation/eventkit/ekreminder.md) | macOS API | System store, iCloud-synced to iPhone and Watch, alarms via EKAlarm | Reaches the user's phone for free. Native alarms. | Permission prompts. Limited schema (no energy or effort fields). | High as a *mirror/sync* target |
| 10 | keith/reminders-cli and remindctl | [github.com/keith/reminders-cli](https://github.com/keith/reminders-cli) | 2019– | MIT Swift CLI for Reminders. `remindctl` adds JSON output and date views ([listing](https://mcpservers.org/agent-skills/deepgram/apple-reminders)). | Zero-code fallback for sync | Shell-out overhead, CLI parsing | Medium (fallback) |
| 11 | TMT-derived priority (Steel) | [Wikipedia summary of Steel & König 2006](https://en.wikipedia.org/wiki/Temporal_motivation_theory) | 2006 | Motivation = E×V / (1 + I×D). This predicts which tasks the user will avoid, as distinct from which matter. | Theory-grounded nudge targeting | Needs E, V and I estimates per user | High (feeds Laya; see Feature 5) |
| 12 | Obsidian TodoSeq urgency | [scross01.github.io/obsidian-todoseq/urgency](https://scross01.github.io/obsidian-todoseq/urgency.html) | 2024– | Another explicit-weights urgency implementation with documented formulas | Readable formulas to copy | Not authoritative for Taskwarrior | Medium |

### Inferences
- **Recommendation: build a local store and use Taskwarrior semantics.**
  - **Store:** SQLite, owned by the memory engine. Schema: `task(id, title, notes, status, created, due, scheduled, wait_until, est_minutes, actual_minutes, energy{low,med,high}, context{home,desk,errand,phone}, value 1–5, expectancy 0–1, aversiveness 0–1, parent_id, depends_on[], recur_rule, source{voice,reminders,…}, ek_identifier)`.
  - **Why:** zero RAM overhead and a deterministic, explainable ranking. Vikunja and Super Productivity add a process or Electron app on an 8 GB machine.
- **Ranking:** Laya computes `urgency = Σ coef_k × term_k`, with Taskwarrior-style terms (due proximity, scheduled, age, blocking, blocked) plus Stiti terms: value, energy match with the current time window, TMT "avoidance risk" (low E, high D, high aversiveness) and a recency-of-mention bonus.
  - Keep coefficients in config and learn small adjustments from accept/skip feedback. Never let the LLM rank.
  - Explanations come straight from the top two terms: "Top pick is the tax form: due Friday, and it's a morning-energy task."
- **Voice rule:** never read the full list. Laya returns the top 3 at most (see Feature 5, CLT), and the user can say "more".
- **Sync:** mirror only tasks with a due time or alarm to Apple Reminders via EventKit, so they reach the iPhone. Store the `calendarItemIdentifier` and reconcile on wake. Treat Reminders edits as user intent.

### Gaps
- I did not retrieve Taskwarrior's exact due-date and age formulas. The available ones come from the Obsidian clone.
- I found no published evaluation of urgency formulas against user satisfaction.
- I did not verify the current Vikunja and Super Productivity versions or their AI/LLM plugins (as of Nov 2026).

---

## 2. Day scheduling / time-blocking: OR-Tools CP-SAT and alternatives

### Takeaway
CP-SAT fits Stiti well. Model each todo as an optional interval with a no-overlap constraint against fixed calendar events, soft deadlines (lateness penalty) and energy-window bonuses. A one-day plan with 10–15 candidate tasks solves to proven optimality in about 10–60 ms on this M2. An over-full day of 50 candidates gives good feasible plans in 0.5–2 s, so a 1–2 s time limit is the right latency budget. Peak RSS was about 113 MB for 100 tasks over 7 days. No mature open-source CP-SAT personal time-blocker exists, so Stiti has to build its own (about 200 lines).

### Cited Findings

**Local benchmark (this session).** Setup: Apple M2, 8 GB, OR-Tools 9.15, 4 workers, 5-minute slots, 08:00–24:00 day, 6 fixed events per day, tasks of 15 min–2 h with random value and deadline, 30% of tasks needing a 09:00–12:00 high-energy window, all tasks optional.
- 12 tasks, 1 day: OPTIMAL in 0.01–0.06 s (3 seeds).
- 20 tasks, 1 day: OPTIMAL in 0.23–2.6 s.
- 50 tasks, 1 day (heavily over-subscribed): FEASIBLE. Gap to proven bound was 9.5–24% at 0.5 s, 7.8–21% at 1 s, 7.4–10.6% at 2 s and 5–9% at 5 s. The gap is measured against the solver's bound, so true sub-optimality is likely smaller.
- 50 tasks, 7 days: 0.5–7% gap at 2 s, with one instance OPTIMAL in 1.2–1.9 s.
- 100 tasks, 7 days: 14–34% gap at 10 s.
- Peak RSS for 100 tasks / 7 days: about 113 MB.

| # | Name | Link | Year | Mechanism / evidence | Strengths | Weaknesses | Fit |
|---|---|---|---|---|---|---|---|
| 1 | OR-Tools CP-SAT | [OR-Tools CP docs](https://developers.google.cn/optimization/cp?hl=en); [scheduling doc](https://github.com/farao-community/or-tools/blob/stable/ortools/sat/doc/scheduling.md) | 2018– (v9.15 tested) | Lazy-clause-generation CP/SAT hybrid. Native interval variables, optional intervals, `AddNoOverlap` and `AddCumulative`. The official recipe puts optional intervals into no-overlap with an objective. | Free (Apache-2.0), pip install, native ARM wheel, anytime (returns best-so-far within the time limit) | Modeling learning curve. Transition and setup constraints can explode solve time (one forum user saw no solution after 8 h on a 30-task model with transitions ([or-tools-discuss](https://groups.google.com/g/or-tools-discuss/c/4If32nsn0-M))). | **Best** |
| 2 | CP-SAT Primer (Krupke) | [d-krupke/cpsat-primer](https://docsearch.algolia.com/mcp/docs/repo/d-krupke/cpsat-primer) | 2023– | Community guide to CP-SAT modeling and performance tuning, about 522 stars | Best learning resource | Not a scheduler | High (reference) |
| 3 | OR-Tools vs CP Optimizer benchmark | [arXiv 2502.13483](https://web3.arxiv.org/pdf/2502.13483) | 2025 | More than 9,000 scheduling instances. "CP Optimizer performs better on permutation scheduling and large-scale problems, OR-Tools is highly competitive." | Independent evidence of CP-SAT quality | CP Optimizer is commercial | Supports choosing CP-SAT |
| 4 | Job-shop example (Google) | [developers.google.com job_shop](https://developers.google.com/optimization/scheduling/job_shop?hl=en) | — | Canonical interval and no-overlap model | Copyable template | Industrial framing | High (template) |
| 5 | HF Space "schedule_constraint_solving" | [huggingface.co/spaces/barakplasma/…](https://www.huggingface.co/spaces/barakplasma/schedule_constraint_solving/commit/30f018f0adc1959faf0ccc689a954962e5903a61) | 2025 | Gradio app plus a standalone personal scheduler using CP-SAT. Places personal time with no-overlap against commitments. | The only personal CP-SAT scheduler found | Toy-scale, licence unchecked | Medium (example) |
| 6 | Timefold Solver (ex-OptaPlanner) | [timefold-solver-python (archived)](https://github.com/TimefoldAI/timefold-solver-python); [docs](https://docs.timefold.ai/timefold-solver/latest/quickstart/hello-world/hello-world-quickstart) | 2023– | Metaheuristic local search with a constraint-streams score. The official Python repo was archived on Oct 6, 2025. The PyPI page says Python is "significantly slower than Java." | Excellent for rostering. Good at incremental re-planning. | JVM (heavy on 8 GB). Python path discontinued. | Low |
| 7 | SolverForge | [solverforge-quickstarts](https://github.com/solverforge/solverforge-quickstarts) | 2025– | Community fork claiming to be "100% Timefold-compatible." Includes employee and meeting scheduling quickstarts. | Keeps a Timefold-style API alive | Small community, fork's own claims | Low |
| 8 | Clock Panda | [github.com/Djei/clockpanda](https://github.com/Djei/clockpanda) | 2023– | Java/Gradle. Connects a work calendar and auto-creates personal and focus blocks. "Only local personal usage supported." | Same product goal | Unknown solver, Java, Google Calendar-centric | Low (idea reference) |
| 9 | FluidCalendar | [github.com/jjc6676/fluid-calendar](https://github.com/jjc6676/fluid-calendar) | 2025– | Open-source Motion clone with auto-scheduling of tasks into the calendar | Product reference for UX (auto-reschedule) | Heuristic scheduler, web stack | Medium (UX reference) |
| 10 | Atomic | [ecosyste.ms](https://awesome.ecosyste.ms/projects/github.com%2Frush86999%2Fatomic) | 2023– | AI scheduler aiming at Motion, Reclaim and Clockwise parity | Feature ideas | Licence unclear, heavy | Low |
| 11 | Reclaim.ai (proprietary, reference only) | [reclaim.ai time-blocking guide](https://reclaim.ai/blog/time-blocking-guide) | 2019– (now part of Dropbox) | Commercial habits, tasks and focus-time defense. Benchmark UX, not code. | Mature UX patterns (flexible habits, buffers) | Closed, cloud | Reference only |
| 12 | FlowSavvy (proprietary) | [flowsavvy.app](https://flowsavvy.app/best-scheduling-app-for-busy-people) | 2026 | Commercial auto-scheduler, vendor marketing | UX reference | Closed | Reference only |
| 13 | IBM CP Optimizer | [arXiv 2502.13483](https://web3.arxiv.org/pdf/2502.13483) | — | Commercial CP scheduler | Strong on large scheduling instances | Not free | Excluded (cost) |
| 14 | Greedy / earliest-deadline-first heuristic | (classical baseline; no source fetched) | — | Sort by urgency, then first-fit into free gaps | Microseconds. Trivially explainable. | Ignores energy windows and global trade-offs | Useful as a fallback when CP-SAT times out |

### Inferences
- **Recommendation: CP-SAT, run by Laya, with the LLM never in the loop.**
  - **Variables:** per task, an optional interval `(start, dur, present)` at 5-minute granularity over waking hours, one `day` variable per task for multi-day plans, and a `NoOverlap` over task intervals, fixed EventKit calendar events and hard blocks (sleep, meals, commute).
  - **Hard constraints:** dependencies (`end_a ≤ start_b`), user "not before" and "not after" times, max focus block length, a mandatory 5–10 minute buffer after meetings (model as an enlarged event interval), and a daily cap on scheduled minutes. Cap at 70–80% of free time, leaving slack.
  - **Soft objective:** `Σ 100·value·present − w_late·lateness + w_energy·[high-energy task in user's peak window] − w_switch·context_switches + w_TMT·[avoidance-risk task placed early in the day]`. Peak windows come from the memory engine's learned chronotype. Default to the morning until there is data.
  - **Latency budget:** `max_time_in_seconds=1.0` for interactive "plan my day" requests and 5 s for overnight weekly planning. Use 4 workers on the M2, then `solution_hint` from the previous plan for fast re-planning when something slips.
  - **Pre-filter:** Laya first selects the top 10–20 candidates by urgency. The benchmark shows ≤20 tasks solves to optimality in well under a second, and 50+ makes optimality slow.
- **Explainability:** report the plan as "3 blocks this morning, the rest after lunch" (see CLT). Keep the binding constraints so the buddy can say "I couldn't fit the gym because of the 4 pm meeting."
- **Re-planning:** on any slip, re-solve the remainder of the day with completed and in-progress intervals fixed. Penalize moving already-accepted blocks (`w_stability·|start_new − start_old|`) so the plan doesn't churn. Churn erodes trust.

### Gaps
- No published latency benchmark for personal CP-SAT scheduling exists. The numbers above are my single-machine synthetic test (3 seeds per configuration) and should be re-run on real data.
- I found no peer-reviewed user study comparing auto-scheduled with manually time-blocked days on wellbeing or completion.
- Energy-level scheduling (chronotype matching) evidence was not researched this session.

---

## 3. Goal decomposition: the "Socratic Chunker"

### Takeaway
Use **as-needed (lazy) decomposition**: ADaPT-style, splitting a step only when the user, or the system's own check, says it isn't directly doable, and terminating every leaf in an implementation intention ("When X, I will Y"). The LLM proposes child steps through short Socratic questions. A deterministic HTN-like tree in the memory engine stores and validates them. Evidence for chatbot goal-setting is real but modest. The best-supported active ingredients are **feedback on goal quality** and **accountability**, not pure Socratic questioning.

### Cited Findings

| # | Name | Link | Year | Mechanism / evidence | Strengths | Weaknesses | Fit |
|---|---|---|---|---|---|---|---|
| 1 | Goblin.tools "Magic ToDo" | [Warwick library guide](https://warwick.ac.uk/services/library/using/productivity-tools/magic-todo-gobin-tools); [Product Hunt](https://www.producthunt.com/posts/goblin-tools) | 2023– | LLM breaks a task into sub-steps, with a "spiciness" slider for granularity. Backend uses OpenAI models; the author states an intent to move to open-source models. | Beloved by ADHD users. Recursive breakdown on demand. | Cloud LLM, not open source, no follow-up questions | High as a UX pattern (recursive, adjustable granularity) |
| 2 | ADaPT: As-Needed Decomposition and Planning | [arXiv 2311.05772 / NAACL Findings 2024](https://ar5iv.labs.arxiv.org/html/2311.05772) | 2024 | Planner and executor LLMs. Decompose recursively only when execution fails. Decomposition depth tracks task complexity. Gains on ALFWorld, WebShop and TextCraft. | Avoids over-planning, which is exactly the "too many steps" problem | Agent benchmarks, not human tasks | **High (core algorithm)** |
| 3 | ChatHTN | [emergentmind summary](https://api.emergentmind.com/topics/chathtn-planner) | 2025 | Symbolic HTN planner (PyHop) that asks an LLM for a decomposition only when no method exists | Symbolic tree plus LLM fallback, which matches the "Laya decides" principle | Research prototype | High (architecture) |
| 4 | GTPyhop | [pypi gtpyhop 1.7.0](https://pypi.org/project/gtpyhop/1.7.0/) | 2021– (1.7.0) | Pure-Python HTN planner for both tasks and goals. Thread-safe session mode. | Tiny, pure Python, deterministic | Methods must be authored | Medium (if Stiti wants formal HTN templates for recurring goals) |
| 5 | Towards a General Framework for HTN Modeling with LLMs | [arXiv 2511.18165](https://arxiv.org/html/2511.18165v1) | 2025 | The LLM writes the planning model, which is parsed into structured Python classes, and a symbolic planner solves it | Verifiable output | Research | Medium |
| 6 | LLM-generated HTN heuristics | [arXiv 2605.07707](https://arxiv.org/abs/2605.07707) | 2026 | LLM-generated heuristics nearly match the best HTN planner's coverage and cut search effort on 83% of shared problems | Shows LLM plus symbolic works | Classical planning domains | Low–Medium |
| 7 | Supporting Effective Goal Setting with LLM-Based Chatbots (Schimpf, Maier et al.) | [arXiv 2602.08636](https://arxiv.org/abs/2602.08636) | 2026 (CHI) | RCT, N=543, 5 chatbot designs. Guidance and feedback raise goal quality. "The feedback mechanism significantly enhances goal quality, whereas the impact of adaptive suggestions is limited." | Rigorous, recent, directly relevant | Goal *quality*, not attainment | **High (design evidence)** |
| 8 | AI career coach RCT | [arXiv 2603.17887](https://arxiv.org/html/2603.17887v1) | 2026 (preprint) | 3-arm RCT, N=517. AI coach vs control d=0.33 on goal progress. No significant gain over a structured written questionnaire. Perceived accountability mediated the AI's effect. | Says *accountability* is the lever | Preprint, career domain | **High** |
| 9 | Implementation intentions meta-analysis (Gollwitzer & Sheeran 2006) | [Konstanz repository](https://kops.uni-konstanz.de/entities/publication/2e749bfb-8533-437c-8203-7e788c910c5f) | 2006 | 94 tests, >8,000 participants, d=0.65 | Gives the leaf format: "if-then" plans | Effect shrinks in later work (see #10) | High (leaf format) |
| 10 | Sheeran, Listrom & Gollwitzer 2024 update | [summary](https://idtips.substack.com/p/implementation-intentions-the-science) | 2024 | 642 tests. Reported d≈0.36 overall, 0.27 for behaviour, and 0.15 after robust Bayesian bias correction (secondary source; verify) | More honest effect size | Secondary summary | High (sets expectations) |
| 11 | BabyAGI-style task loop | [github.com/yoheinakajima/babyagi](https://github.com/yoheinakajima/babyagi) (not re-verified this session) | 2023 | LLM loop that creates, prioritizes and executes tasks | Popular template | Unbounded task explosion. LLM decides priority, which violates the Laya principle. | Low (anti-pattern for Stiti) |
| 12 | Local on-device breakdown (KickMint, vendor claim) | [kick-mint blog](https://kick-mint.pages.dev/blog/goblin-tools-alternative) | 2026 | Runs a small Qwen model on-device via llama.cpp for Magic-ToDo-style breakdown | Shows a small local model can do it | Marketing claim | Medium (feasibility signal) |
| 13 | Mayer segmenting principle | [Cambridge Handbook chapter](https://cambridge.org/core/books/cambridge-handbook-of-multimedia-learning/principles-for-managing-essential-processing-in-multimedia-learning-segmenting-pretraining-and-modality-principles/DD24C2F48B9B1277CE59F78276110258); [summary](https://chameleon-buttercup-c34z.squarespace.com/blog/managing-intrinsic-load) | 2005/2014 | Learner-paced segments beat continuous presentation, with a median d≈0.79 across 10/10 tests | Supports one-step-at-a-time delivery | Multimedia learning, not task planning | High (delivery) |

### Inferences
- **Recommendation: a four-phase Socratic Chunker, each phase one short voice turn.**
  1. **Clarify outcome:** "What does done look like?" Laya checks that the answer is specific and observable. Schimpf et al. show that *feedback on goal quality* is the effective ingredient, so give feedback such as "That's a bit broad. Would 'submit the visa form' be the finish line?"
  2. **WOOP pass** (see Feature 5): wish, outcome, main obstacle, then the plan.
  3. **Lazy split, ADaPT-style:** propose only the *next 1–3* children. For each, ask "Could you start this in under 10 minutes?" If not, recurse on that child only. Stop at a 2-to-25-minute "first physical action." Granularity is a per-user "spiciness" setting, learned from how often the user asks to split further.
  4. **Anchor:** convert the first leaf to an if-then plan ("When I sit down after coffee tomorrow, I'll open the form"). Hand it to the scheduler and reminder system.
- **Division of labour:** the LLM generates candidate children and question wording. The memory engine stores the tree (`parent_id`). Laya validates each step: has a verb, an estimated duration and a measurable done condition, isn't a duplicate, and the depth is ≤4. Laya also decides when to ask the next question. Never generate a 20-step plan up front. BabyAGI-style loops are an anti-pattern here.
- **Accountability matters most:** schedule a check-in on the first leaf. The career-coach RCT found accountability, not the AI's cleverness, mediated the effect.
- **Small local model is enough:** a 3–4B instruct model with a JSON-schema-constrained output (`{steps:[{title, est_min, done_when}]}`) is sufficient. KickMint is a feasibility signal that a small Qwen model works on-device, but it is a marketing claim.

### Gaps
- No RCT isolates *Socratic questioning* as the active ingredient in coaching chatbots. Search found none, and the 2026 RCTs test guidance, feedback and accountability instead.
- I found no open-source code for a goblin.tools-equivalent "magic todo".
- I did not verify the BabyAGI repo's current state.

---

## 4. Habit tracking: SM-2 vs FSRS vs habit-formation science

### Takeaway
**Spaced repetition (SM-2 or FSRS) is the wrong model for habits.** SR schedules *fewer, more-spaced* reviews of memories so they decay as little as possible. Habit formation needs *consistent, context-cued repetition*: daily or same-context performance until automaticity, with a median of about 59–66 days and a huge spread (4–335 days). Use FSRS (`pip install fsrs`) only for genuine *learning* items (vocabulary, facts). Model habits with a Loop-style exponentially smoothed "habit strength" plus context-cue (implementation-intention) prompts that *fade* as automaticity grows, and use forgiving, non-streak framing.

### Cited Findings

| # | Name | Link | Year | Mechanism / evidence | Strengths | Weaknesses | Fit |
|---|---|---|---|---|---|---|---|
| 1 | SM-2 (Wozniak) | [SuperMemo archive](https://www-v1.supermemo.com/archives1990-2015/english/ol/sm2); [Wikipedia](https://en.wikipedia.org/wiki/SuperMemo) | 1987–90 | Intervals I(1)=1, I(2)=6, I(n)=I(n−1)×EF. EF starts at 2.5 with a floor of 1.3. EF' = EF + (0.1 − (5−q)(0.08 + (5−q)·0.02)). A grade <3 restarts the sequence. | Simple, about 20 lines | Not a probabilistic model. Rounding and failure rules differ between implementations. | Low for habits. Low–Medium for learning. |
| 2 | FSRS (DSR model) / py-fsrs | [pypi fsrs](https://pypi.org/project/fsrs); [docs](https://open-spaced-repetition.github.io/py-fsrs/fsrs.html) | 2022– (py-fsrs 6.3.x; FSRS-5 in v3+, FSRS-6 current) | Models Difficulty, Stability and Retrievability per item. Schedules a review when predicted recall drops to the target retention. Optional optimizer fits parameters to the user's review log (`fsrs[optimizer]`). A Rust backend exists. | State of the art for memory. Official Python package. | Designed for memory decay, not behaviour automaticity | **High for learning items only** |
| 3 | SRS benchmark (open-spaced-repetition) | [expertium.github.io/Benchmark](https://expertium.github.io/Benchmark.html) | 2023– | FSRS beats SM-2 on log loss for about 99.5% of collections (secondary reports). The benchmark authors note SM-2 "wasn't originally designed to predict probabilities." | Large real-data benchmark | Exact log-loss numbers conflict across secondary sources (0.616 vs 0.354 for SM-2) | Evidence for FSRS over SM-2 |
| 4 | SuperMemo's dissent | [supermemo.com blog](https://supermemo.com/en/blog/supermemo-is-better-than-fsrs-by-far) | 2024–25 | Argues log loss and AUC are inappropriate for measuring calibration | Valid methodological caveat | Vendor with a competing product | Note only |
| 5 | Lally et al. 2010 | [Surrey interview with Lally](https://www.surrey.ac.uk/news/does-it-really-take-66-days-form-habit-we-asked-expert-dr-pippa-lally); [reanalysis](https://www.thebehavioralscientist.com/articles/how-long-to-form-a-habit) | 2010 | 96 participants, 84 days. Median 66 days to 95% of the automaticity asymptote, with a range of 18 to a *projected* 254 days. Lally: "how long habit formation takes is highly variable." | Primary evidence that automaticity follows an asymptotic curve | Small sample. Values past 84 days are extrapolations. | High (model shape) |
| 6 | Singh et al. 2024 systematic review | [Adelaide repository](https://digital.library.adelaide.edu.au/items/fe6ba93e-1d6b-42b8-9ee7-a231a64ff006); [ScienceDaily](https://www.sciencedaily.com/releases/2025/01/250124151347.htm) | 2024 (*Healthcare*) | 20 studies, n=2,601. Only 4 measured formation time: medians 59–66 days, means 106–154 days, range 4–335 days. Only 23% reached the threshold. | Most recent synthesis | Small timing subset | **High: no fixed "21/66-day" promise** |
| 7 | Stawarz, Cox & Blandford 2015 (CHI) | [Cardiff ORCA](https://orca.cardiff.ac.uk/130626); [UCL PDF](https://discovery.ucl.ac.uk/id/eprint/1468224/) | 2015 | 4-week study plus a review of 115 habit apps. **Reminders increased repetition but hindered habit development.** Event-based cues increased automaticity. Positive reinforcement had little effect. Most apps rely only on tracking and reminders. | Directly about app design | Short study | **High: fade reminders, use event cues** |
| 8 | Harrison, Marshall, Stawarz & Cox (Lift app) | [core.ac.uk](https://core.ac.uk/download/79500911.pdf) | ~2016 | Interview follow-up flagging dependency risk when reminders act as the trigger | Real users | Qualitative | Medium |
| 9 | Wood & Rünger 2016, *Annual Review of Psychology* | [USC PDF](https://dornsife.usc.edu/wendy-wood/wp-content/uploads/sites/183/2023/10/wood.runger.2016.pdf) | 2016 | Habits are context-to-response associations learned through repeated, rewarded performance. Once formed, context cues trigger them independently of current goals. | Authoritative theory | — | High (cue design) |
| 10 | Gollwitzer & Sheeran 2006 implementation intentions | [Konstanz](https://kops.uni-konstanz.de/entities/publication/2e749bfb-8533-437c-8203-7e788c910c5f) | 2006 | d=0.65 across 94 tests. If-then plans link a situational cue to a response, which is the bridge to habit cues. | Large evidence base | Inflated vs 2024 estimates | High |
| 11 | Loop Habit Tracker "habit strength" | [github.com/iSoron/uhabits](https://github.com/iSoron/uhabits); [README](https://raw.githubusercontent.com/iSoron/uhabits/dev/README.md) | 2016– (GPL-3.0) | "Every repetition makes your habit stronger and every missed day makes it weaker." A few misses after a long run don't erase progress. The exact formula is in the code (exponential smoothing). | Forgiving, non-streak metric. Open source. | Android. GPL (re-implement, don't copy). | **High (metric design)** |
| 12 | Silverman & Barasch 2023, *JCR* (broken streaks) | [UDaily](https://udel.edu/udaily/2024/march/power-of-streaks-motivation-jackie-silverman); [Psychology Today](https://www.psychologytoday.com/us/blog/ulterior-motives/202306/how-broken-streaks-sap-motivation) | 2023 | Same behaviour framed as an intact vs broken streak: 66% vs 58% continued. The effect fades with time since the break and is reduced when a repair is offered. The authors advise apps against "you broke your streak!" messages. | Causal experiments | Secondary coverage; full paper not read | **High (anti-guilt streak design)** |
| 13 | Fresh start effect (Dai, Milkman & Riis 2014) | [Wharton PDF](https://faculty.wharton.upenn.edu/wp-content/uploads/2014/06/Dai_Fresh_Start_2014_Mgmt_Sci.pdf); [EconPapers](https://econpapers.repec.org/RePEc:inm:ormnsc:v:60:y:2014:i:10:p:2563-2582) | 2014, *Mgmt Sci* 60(10) | Diet searches, gym visits and goal commitments rise after temporal landmarks (new week, month, birthday) | Gives natural restart days | Resets may demotivate people on a winning run (secondary, unverified) | High (restart timing) |

### Inferences
- **Recommendation for learning items (language words, facts the user wants to remember):** FSRS via `fsrs`, desired retention about 0.9. Run the optimizer monthly once there are more than about 1,000 reviews. Voice grading maps "again / hard / good / easy" to FSRS ratings.
- **Recommendation for habits: "Cue → Plan → Fade," not SR.**
  - **Habit record:** `habit(id, behaviour, anchor_cue "after I pour coffee", if_then_plan, target_freq (daily | n/week), min_version "2-minute version", strength 0–1, created, last_done, prompt_level)`.
  - **Strength:** `s ← s + α·(done − s)` per scheduled occasion, with α≈0.05–0.07 (a Loop-like EMA), so a miss costs a few points instead of resetting. Tell the user strength ("your reading habit is about 70% set"), never a streak count. If streaks are shown at all, use "X of the last 14 days" windows, which can't be "broken." Offer a "repair" or "freeze" token after a miss, which Silverman & Barasch found blunts the drop.
  - **Fading prompts:** Stawarz shows reminders build dependency. Laya should start with a prompt at the cue time. Once strength exceeds about 0.6 and the behaviour is done before the prompt on most days, switch to an end-of-day check ("Did reading happen today?"). Above about 0.8, check weekly. If strength falls below 0.4, reinstate cue prompts.
  - **Expectation-setting:** never promise "21 days" or "66 days." Say "habits usually take two to five months to feel automatic, and it varies a lot" (Singh 2024: medians 59–66 days, range 4–335 days).
  - **Restarts:** after a lapse, Laya proposes restarting on the next landmark (Monday, 1st of the month, birthday), per the fresh-start effect. Avoid forcing resets on users who are on a winning run.
- **Why not SM-2 for habits:** SM-2 would schedule a habit on days 1, 6, 15… That is the opposite of daily context-consistent repetition, and it treats "forgot" as an item-memory failure rather than a cue or plan failure.

### Gaps
- I did not read Loop's exact strength formula from source. The α values above are my suggestion and need tuning.
- No study tests SR-style expanding schedules for *behaviours*. I found none, and the claim that "SR is inappropriate" is inferred from mechanism plus Lally/Stawarz.
- I could not confirm the current SM-2 vs FSRS log-loss numbers from the primary srs-benchmark repo, because secondary sources conflict.
- I could not verify Fogg's Tiny Habits and Kaushal & Rhodes 2015 in search results this session.

---

## 5. Motivation psychology: WOOP/MCII, TMT, Cognitive Load Theory for voice, and anti-guilt / self-compassion

### Takeaway
The four frameworks map onto four Laya modules:
- **WOOP/MCII** is the goal-setting script. It has a reliable small-to-medium effect (g≈0.28–0.34).
- **TMT** is the *diagnostic*: it predicts which task the user will avoid, and the nudge targets the term that is low (raise expectancy by shrinking the step, raise value by linking to the "why", cut delay with a near-term mini-deadline, block impulsiveness with an if-then plan).
- **CLT / working memory** is the *speech budget*: about 3 items, one decision per turn, under about 20 seconds of speech, user-paced.
- **Self-compassion and self-forgiveness** are the *tone*. Self-forgiveness after a failure predicted less later procrastination (via reduced negative affect), and self-compassion increases improvement motivation rather than reducing it.

### Cited Findings

| # | Name | Link | Year | Mechanism / evidence | Strengths | Weaknesses | Fit |
|---|---|---|---|---|---|---|---|
| 1 | MCII meta-analysis (Wang, Wang & Gai) | [PMC8149892](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC8149892/); [Frontiers](https://www.frontiersin.org/journals/psychology/articles/10.3389/fpsyg.2021.565202/full) | 2021 | 21 studies, 24 effect sizes, N=15,907. g=0.336 for goal attainment. Moderated by intervention style. Possible publication bias. | Large N | Few studies | **High** |
| 2 | Cross & Sheffield, mental contrasting for health behaviour | [Derby repository](https://repository.derby.ac.uk/item/93z0q/mental-contrasting-for-health-behaviour-change-a-systematic-review-and-meta-analysis-of-effects-and-moderator-variables) | 2019 | MCII (k=7) g=0.28 [0.14–0.42]. Adding implementation intentions did not clearly strengthen MC alone. | Health-specific | Small k | High |
| 3 | WOOP vs goal-setting in anesthesiology residents (RCT) | [PMC5410783](https://pmc.ncbi.nlm.nih.gov/articles/PMC5410783) | 2017 | Randomized WOOP vs standard goal-setting in ICU residents. Primary outcome: study time toward goals. One secondary page reports 4.3 vs 1.5 h/week (unverified). | Adult, real-world | Small, single site | Medium |
| 4 | Mental contrasting in low-income schoolchildren | [summary](https://www.goodreads.com/author_blog_posts/16482474-research-summaries-mental-contrasting-facilitates-academic-performance) | ~2013 | N=49 and N=63. Mental contrasting beat goal-only imagery on vocabulary learning. | Replication across countries | Children, small | Low–Medium |
| 5 | Steel 2007 procrastination meta-analysis | [PRISM Calgary](https://prism.ucalgary.ca/handle/1880/47914); [ScienceDaily](https://www.sciencedaily.com/releases/2007/01/070110090851.htm) | 2007, *Psych Bull* | 691 correlations. Strong predictors: task aversiveness, task delay, self-efficacy, impulsiveness, conscientiousness facets. About 15–20% of people are chronic procrastinators. | Large, foundational | Correlational | **High (TMT terms)** |
| 6 | Temporal Motivation Theory (Steel & König) | [Wikipedia summary](https://en.wikipedia.org/wiki/Temporal_motivation_theory); [LessWrong discussion incl. Steel](https://www.lesswrong.com/lw/3w3) | 2006, *AMR* 31(4) | Motivation = (Expectancy × Value) / (1 + Impulsiveness × Delay). The "1+" keeps the denominator finite, per a commenter who appears to be Steel. | Operationalizable | Sources differ on the "1+" term | **High** |
| 7 | Cognitive Load Theory / element interactivity (Sweller) | [Springer 2023 review](https://link.springer.com/article/10.1007/s10648-023-09782-w); [Syracuse summary](https://facultycenter.ischool.syr.edu/wp-content/uploads/2012/02/cognitive-load-theory.pdf) | 1988–2023 | Intrinsic load comes from element interactivity, meaning how many elements must be held simultaneously. Reducing extraneous load matters most when interactivity is high. | Explains why "plan + reasons + options" in one utterance overloads | Developed for instruction | High |
| 8 | Cowan's "magical number 4" | [Cambridge BBS PDF](https://www.cambridge.org/core/services/aop-cambridge-core/content/view/44023F1147D4A1D44BDC0AD226838496/S0140525X01003922a.pdf/magical_number_4_in_shortterm_memory_a_reconsideration_of_mental_storage_capacity.pdf); [2024 modelling paper](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC11259112/) | 2001 / 2024 | Working-memory capacity is about 3–5 chunks. A 2024 study finds that longer presentation time raises estimated capacity through chunking. | Robust | Lab tasks | High (≤3 items) |
| 9 | Mayer segmenting principle | [Cambridge Handbook](https://cambridge.org/core/books/cambridge-handbook-of-multimedia-learning/principles-for-managing-essential-processing-in-multimedia-learning-segmenting-pretraining-and-modality-principles/DD24C2F48B9B1277CE59F78276110258) | 2014 | Learner-paced segments: 10/10 tests, median d=0.79 | Strong | Multimedia learning | High (user-paced "next") |
| 10 | IVR menu breadth (Commarford) | [UCF STARS](https://stars.library.ucf.edu/facultybib2000/233) | ~2006 | Broad menus beat deep ones, especially for low-working-memory users. Challenges the "≤5 items" rule derived from Miller. | Counter-evidence | Menus ≠ conversation | Medium |
| 11 | More options per turn in spoken booking (Wolters et al.) | [Teesside](https://research.tees.ac.uk/en/publications/reducing-working-memory-load-in-spoken-dialogue-systems/) | ~2009 | More options per turn plus no explicit confirmation subdialogues gave faster booking with no loss in success, for both older and younger users | Nuance: fewer turns can beat fewer items | Specific task | Medium |
| 12 | Auditory memory and utterance duration (CMU, Interspeech 2006) | [CMU PDF](https://www.shot.org/mirrors/pc110/www.cs.cmu.edu/~awb/papers/is2006/IS062075.PDF) | 2006 | Suggests utterance *length* (about 2 s of auditory memory), not item count, is the limit | Measure duration, not count | Older | Medium |
| 13 | Practitioner VUI guidance (Google "rule of three", CareerFoundry) | [Google Design](https://design.google/library/rule-of-three); [CareerFoundry](https://careerfoundry.com/en/blog/ux-design/voice-ui-design-and-cognitive-load) | — | 3–5 options per turn. For longer lists, stop and offer to continue. | Industry consensus | Not research | High |
| 14 | Wohl, Pychyl & Bennett 2010 (self-forgiveness) | [BPS Research Digest](https://bps.org.uk/research-digest/cure-procrastination-forgive-yourself); [Psychology Today (Pychyl)](https://psychologytoday.com/blog/dont-delay/201002/forgive-yourself-stop-procrastinating) | 2010, *PAID* 48(7) | 134 (analysed about 119) first-years over two midterms. Forgiving oneself for procrastinating on exam 1 predicted less procrastination before exam 2, mediated by less negative affect. The effect held only among high procrastinators. | Directly on target | Self-report, correlational | **High** |
| 15 | Sirois 2014, procrastination and stress | [White Rose eprint](https://eprints.whiterose.ac.uk/id/eprint/91791/) | 2014, *Self & Identity* 13(2) | 4 samples. Procrastinators have lower self-compassion and more stress. Self-compassion mediated procrastination and stress in all 4. | Replicated across samples | Correlational | High |
| 16 | Breines & Chen 2012 | [PSPB PDF](https://static1.squarespace.com/static/50f6f441e4b08191027c661d/t/51663d46e4b060cd9194ed75/1365654854068/Breines+&+Chen+2012+PSPB.pdf) | 2012, *PSPB* | 4 experiments. Self-compassion after failure led to more studying after a failed test and more motivation to fix a weakness, vs self-esteem and control conditions. | Causal. Refutes "kindness = complacency." | Lab tasks | **High** |
| 17 | Ferrari et al. 2019 meta-analysis of self-compassion RCTs | [ACU repository](https://acuresearchbank.acu.edu.au/item/87545/self-compassion-interventions-and-psychosocial-outcomes-a-meta-analysis-of-rcts) | 2019, *Mindfulness* | 27 RCTs. Self-compassion g=0.75, stress g=0.67, depression g=0.66. Possible publication bias. | RCT-level | Heterogeneous interventions | High |
| 18 | Han & Kim 2023 update | [PMC10239723](https://pmc.ncbi.nlm.nih.gov/articles/PMC10239723/) | 2023 | 56 RCTs, small-to-medium effects on depression, anxiety and stress | Newer | — | Medium |
| 19 | Fresh start effect | [Wharton PDF](https://faculty.wharton.upenn.edu/wp-content/uploads/2014/06/Dai_Fresh_Start_2014_Mgmt_Sci.pdf); [APS](https://www.psychologicalscience.org/news/minds-business/why-monday-is-the-best-day-for-setting-new-goals.html) | 2014 / 2015 | Landmarks spur aspirational behaviour. Framing a date as a fresh start made people choose it as a reminder date 3.5× more often (26% vs 7%). | Cheap to apply | Effect on *completion* is less clear | High |
| 20 | Broken-streak effect | [UDaily](https://udel.edu/udaily/2024/march/power-of-streaks-motivation-jackie-silverman) | 2023 | See Feature 4 | | | High |
| 21 | ADHD and self-regulation AI (conceptual and HCI) | [arXiv 2507.06864](https://arxiv.org/html/2507.06864v1); [arXiv 2603.17258](https://arxiv.org/pdf/2603.17258); [MR body doubling roadmap](https://arxiv.org/html/2605.07851) | 2025–26 | Existing tools mostly "correct behaviour" and rarely support emotional regulation. Calendars and to-do lists poorly support task *initiation* and *time estimation*. Body doubling (working alongside someone) helps attention. | Points to initiation support and "co-working" mode | Mostly preprints and conceptual | Medium–High |
| 22 | Tiimo (ADHD visual planner) | [tiimoapp.com](https://tiimoapp.com/resource-hub/inclusive-planning) | 2015– | Visual timelines, transition timers, color coding. "Research-backed" claims are vendor marketing; no peer-reviewed evaluation found. | Strong UX for time blindness | Proprietary, no evidence | UX reference |

### Inferences
- **WOOP, run conversationally.** Five voice turns, Laya-driven, each a single question:
  1. **Wish:** "What's one thing you'd love to get done this week? Just a few words."
  2. **Outcome:** "Imagine it's done. What's the best part?" Pause and let the user picture it. Oettingen's protocol uses imagery, and Wang 2021 found intervention style moderates effects.
  3. **Obstacle:** "What inside *you* is most likely to get in the way?" Steer from external to internal obstacles: tiredness, phone, dread.
  4. **Plan:** "So: if [obstacle] happens, what will you do?" Store the result as an if-then plan.
  5. **Confirm and schedule:** read back one sentence and offer a reminder at the cue.

  Expect a small-to-medium effect (g≈0.3). Use WOOP for weekly goals and stuck tasks, not every todo.
- **TMT operationalized in Laya.** For each task, estimate four terms and nudge the weakest one:
  - **E (expectancy):** from the user's completion history on similar tasks (memory engine) and the size of the next step.
  - **V (value):** from the user-stated "why" and its link to goals. The UI asks once: "how much does this matter, 1–5?"
  - **D (delay):** time to the reward or deadline.
  - **I (impulsiveness):** a per-user trait estimate from snooze and skip history, global rather than per-task.
  - **Nudge per low term:** low E means shrink the step ("just open the doc for 2 minutes"). Low V means reconnect to the why ("this gets you closer to the Lisbon trip"). High D means create an artificial near deadline or a reward now ("do 15 minutes then coffee"). High I means remove the cue for the distraction or add an if-then plan.
  - **Ranking:** `avoidance_risk = 1 − sigmoid(E×V/(1+I×D))` feeds the urgency sum (Feature 1) and the scheduler's "eat the frog early" bonus. This is an engineering use of TMT. No validated parameterization exists.
- **CLT speech budget for every utterance** (Laya enforces it as a post-generation check on the LLM output):
  1. At most 3 list items per turn, then "Want the rest?" (Cowan 3–5 chunks; Google rule of three).
  2. One question or one decision per turn.
  3. Target about 8–20 seconds of TTS. Measure duration, not tokens, per the CMU auditory-duration point. Front-load the key info: "Three things today. First…".
  4. User-paced continuation ("next", "more"), per Mayer segmenting d≈0.79.
  5. No reasons or meta-talk unless asked. Reasons are extraneous load.
  6. Offer a screen summary (menu-bar or notification) for lists longer than 3, since the voice-only constraint doesn't apply when a screen is present (speechtechmag).
  7. Wolters' result means don't add confirmation sub-dialogues for low-stakes actions. Confirm only destructive or ambiguous ones.
- **Anti-guilt architecture.** This is a rules layer between Laya and TTS, plus lexicon checks on the LLM output.
  1. **Never** use the words "failed", "broke your streak", "behind", "should have" or "overdue" in speech. Say "still open" or "carried over".
  2. After a missed task, use **self-forgiveness framing**: normalize ("that happens to everyone"), separate from identity, then turn forward with one tiny next step (Wohl 2010; Breines & Chen 2012).
  3. Report **habit strength or windows instead of streaks**, and offer a streak repair (Silverman & Barasch).
  4. **Auto-triage the backlog:** when more than N tasks are carried over for more than 7 days, Laya *proposes* archiving them ("park these for later?"). That way the list never becomes a guilt pile.
  5. **Use fresh starts:** offer restarts on Mondays, the 1st of the month or after travel (Dai et al.).
  6. **Watch for stress:** if the user's language shows distress, the memory engine flags a high-stress state, and Laya switches to "minimum viable day" mode (1–3 tasks, more slack) rather than pushing. Sirois links low self-compassion and stress to procrastination.
  7. **Mirror ADHD-friendly patterns:** granular breakdown on demand (goblin.tools), visible time and transition warnings (Tiimo), and an optional "body double" mode where Stiti stays present with periodic quiet check-ins during a focus block.
  8. **Praise the process,** never compare the user with others.

### Gaps
- I did not retrieve the full WOOP/Duckworth 2011 data. The resident-RCT numbers come from a secondary page.
- There is no validated method for measuring TMT's E, V and I terms in software. The operationalization above is my engineering inference.
- No voice-specific CLT study gives a validated item or duration limit. Evidence conflicts (Commarford; Wolters).
- I found no peer-reviewed evaluation of Tiimo or goblin.tools.

---

## 6. Proactive nudging and interruption timing

### Takeaway
Proactivity research (2024–2026) consistently finds LLM agents **over-intervene** ("AI assistants overassist"), and benchmarks now penalize high proposal rates. HCI research says nudges cost least at **task breakpoints**, and receptivity depends on content being interesting, relevant and *actionable*. mHealth micro-randomized trials show notifications produce **short-term responses but no long-term engagement gain**, and habituation is a risk. So Stiti's proactivity should be sparse, breakpoint-timed, budgeted per day, learned per user (contextual bandit or MRT-style) and decided by Laya, with the LLM only phrasing.

### Cited Findings

| # | Name | Link | Year | Mechanism / evidence | Strengths | Weaknesses | Fit |
|---|---|---|---|---|---|---|---|
| 1 | Proactive Agent / ProactiveBench (Lu et al.) | [ICLR 2025](https://proceedings.iclr.cc/paper_files/paper/2025/hash/75c37811e830bf029584b1c6fac17726-Abstract-Conference.html); [arXiv 2410.12361](https://arxiv.org/html/2410.12361v3) | 2025 | 6,790 training events. A reward model is trained on human accept/reject of proactive suggestions. Fine-tuned model F1 66.47%; LLaMA-3.1-8B baseline 55.06%. | Accept/reject reward-model idea | Coding, writing and daily-life desktop events | **High (learn from accept/reject)** |
| 2 | Pare-Bench (Proactive Agent Research Environment) | [arXiv 2604.00842](https://arxiv.org/html/2604.00842v1) | 2026 | 143 tasks covering timing, goal inference and multi-app use, with a simulated active user. "Proposal Rate: lower is better, too many proposals can annoy the user." | Puts annoyance into a metric | Preprint, simulated users | High |
| 3 | ProAgentBench | [arXiv 2602.04482](https://arxiv.org/pdf/2602.04482) | 2026 | Built from real user workflow logs. Argues intervention timing must be learned from authentic behaviour. | Real logs | Preprint | High |
| 4 | "AI Assistants Overassist" (Int-Bench) | [arXiv 2607.21306](https://arxiv.org/html/2607.21306) | 2026 | LLMs intervene "more frequently and earlier than humans" with overly informative feedback (tutoring) | Direct warning | Tutoring domain | **High (design caution)** |
| 5 | ProACT | [arXiv 2607.03730](https://arxiv.org/pdf/2607.03730) | 2026 | Stay silent when people are progressing or a message would be duplicative or interruptive | Silence rules | Multi-user setting | Medium |
| 6 | ProVoice-Bench | [arXiv 2604.15037](https://arxiv.org/html/2604.15037) | 2026 | Proactivity of *voice* agents, including a dedicated "is intervention needed" task | Voice-specific | Preprint | High |
| 7 | ProactiveBench (multimodal) | [arXiv 2603.19466](https://arxiv.org/abs/2603.19466) | 2026 | MLLMs show limited proactiveness in asking for help, even when hinted | Different meaning of "proactive" (asking for help) | — | Low |
| 8 | ATRBench "Ask Now, Use Later" | [arXiv 2605.28108](https://arxiv.org/html/2605.28108v2) | 2026 | Proactive questioning in long-lived agents. Over-eliciting is intrusive. | Relevant to a buddy that asks questions | Preprint | Medium |
| 9 | CoLabScience (small RL observer decides when to intervene) | [arXiv 2604.15588](https://arxiv.org/pdf/2604.15588) | 2026 | A small observer model trained with GRPO decides whether to speak up | Supports "a small decision model, not the big LLM, decides" | Science discussions | Medium–High (architecture match for Laya) |
| 10 | Iqbal & Bailey, OASIS / breakpoints | [TOCHI 2010 PDF](https://www.interruptions.net/literature/Iqbal-TOCHI10.pdf) | 2008–2010 | Interrupting at breakpoints lowers cost. Coarser breakpoints give larger reductions. Breakpoint-scheduled notifications reduced frustration and reaction time vs immediate delivery. | Strong, classic | Desktop tasks | **High (when to nudge)** |
| 11 | Mehrotra et al., notification receptivity | [UCL CHI'16 PDF](https://discovery.ucl.ac.uk/1502364/1/CHI16.pdf) | 2016 | Receptivity depends on content being interesting, relevant and actionable, plus context | Content rules | Mobile | High |
| 12 | Pielot et al. 2018 (MobileHCI) | [PDF](https://www.interruptions.net/literature/Pielot-MobileHCI18.pdf) | 2018 | Predicting attentiveness and engagement with notifications | ML-timing precedent | Phone context | Medium |
| 13 | JITAI and micro-randomized trials (Klasnja, Qian, Nahum-Shani) | [arXiv 2107.03544](https://arxiv.org/pdf/2107.03544); [HeartSteps MRT](https://pmc.ncbi.nlm.nih.gov/articles/PMC6401341) | 2015–2022 | JITAIs deliver support "when users most need it and are most receptive." MRTs randomize each decision point to learn proximal effects. HeartSteps: 6-week MRT, n=44, then a 1-year HeartSteps II. | A rigorous method Stiti can copy on n=1 | Needs many decision points | **High (learning loop)** |
| 14 | Drink Less MRT (notifications) | [JMIR mHealth 2023 e38342](https://mhealth.jmir.org/2023/1/e38342/PDF) (best match from search results; verify) | 2023 | A notification raised app opening in the next hour, but there was **no difference in time to disengagement** across fixed, none or random notification policies | Honest null on long-term effect | Alcohol app | High (budget nudges) |
| 15 | Digital triggers viewpoint | [JMIR 2017 e147](https://www.jmir.org/2017/5/e147/) | 2017 | Names alert fatigue and habituation as common pitfalls | — | Viewpoint | Medium |
| 16 | Stawarz 2015 | [Cardiff ORCA](https://orca.cardiff.ac.uk/130626) | 2015 | Reminders hinder automaticity (see Feature 4) | | | High |

### Inferences
- **Recommendation: a "Nudge Gate" inside Laya.** Every candidate proactive utterance (check-in, reminder, suggestion) gets a score:
  `score = relevance × actionability × urgency × receptivity(context) − annoyance_cost(recent_nudges) − habituation_penalty`.
  Speak only if `score > θ` **and** the daily budget isn't exhausted.
- **Budget:** default about 3–5 unsolicited voice nudges per day, plus scheduled alarms the user explicitly set (those are never suppressed). Laya adapts the budget per user from responses.
- **Receptivity signals (local, on-device):**
  - Breakpoints: end of a calendar event, app switch, screen unlock or wake, end of a focus timer, Stiti's own conversation end.
  - Mic and camera in use (call in progress means suppress).
  - Focus/DND mode.
  - Time-of-day learned acceptance.
  - Keyboard idle more than N minutes. Prefer coarse breakpoints, per Iqbal & Bailey.
- **Learning:** log each decision point as `(context, action ∈ {silent, voice, banner}, outcome ∈ {accepted, dismissed, ignored, "stop"})`. Use epsilon-greedy or Thompson-sampling exploration between "voice" and "banner" at decision points. This is an n-of-1 MRT and fits Laya as a small contextual bandit, not an LLM. ProactiveBench's accept/reject reward model is the template.
- **Modality ladder:** silent log, then menu-bar badge, then macOS banner, then spoken nudge, then alarm. Default to the lowest rung that will plausibly work. Escalate only for user-set hard deadlines.
- **Content rules:** each nudge must be actionable in one step, carry one item, and offer an easy out ("Want me to push it to tomorrow?"). Never repeat an ignored nudge more than once. A "Stop doing X" command creates a permanent preference.
- **Morning and evening rituals** are user-invited and therefore not unsolicited:
  - **Morning plan:** the top 3 items plus the first if-then.
  - **Evening review:** wins first, then items carried over without guilt, then tomorrow's first step.

### Gaps
- Most 2026 proactive-agent benchmarks are preprints. I didn't verify peer-review status.
- No study gives an optimal daily nudge count for a voice companion. The 3–5 default is my inference.
- I could not retrieve Nahum-Shani's receptivity-specific papers.

---

## 7. Alarms and reminders on macOS from Python

### Takeaway
The most reliable zero-cost stack:
- **EventKit via PyObjC** writes reminders and calendar alarms into Apple's stores. iCloud then delivers them to the iPhone and Watch, and they fire even if Stiti is not running.
- **A launchd LaunchAgent** keeps Stiti's daemon alive and triggers scheduled check-ins.
- **Stiti's in-process scheduler** handles spoken alarms while it is running.
- **`pmset` / IOPMSchedulePowerEvent** is needed only to *wake* the Mac, because launchd cannot wake a sleeping machine.

Shortcuts CLI and AppleScript are fallbacks.

### Cited Findings

| # | Name | Link | Year | Mechanism / evidence | Strengths | Weaknesses | Fit |
|---|---|---|---|---|---|---|---|
| 1 | EventKit EKReminder | [Apple docs](https://developer.apple.com/documentation/eventkit/ekreminder.md); [Creating events and reminders](https://developer.apple.com/documentation/eventkit/creating-events-and-reminders.md) | macOS API | Create with `init(eventStore:)` (ObjC `reminderWithEventStore:`) and save through the store, handling errors | Native and synced. Fires on all devices. | Needs Reminders permission (TCC) | **High** |
| 2 | EKAlarm | [Apple docs](https://developer.apple.com/documentation/eventkit/ekalarm.md) | macOS API | `init(absoluteDate:)` / `init(relativeOffset:)`, attached with `addAlarm` | System-delivered alarm | Notification style is controlled by Reminders/Calendar settings | **High** |
| 3 | PyObjC EventKit usage (MCP reminders server) | [glama mcp-reminders source](https://glama.ai/mcp/servers/@pongsapakl/mcp-reminders/blob/4208caee7acba410ee5126ad46bdd7962aba82b0/src/mcp_reminders/reminders.py) | 2025 | Python: `EKReminder.reminderWithEventStore_(store)`, `setTitle_`, `setCalendar_` | Proves the PyObjC route works | Third-party code | High (template) |
| 4 | keith/reminders-cli | [github.com/keith/reminders-cli](https://github.com/keith/reminders-cli) | 2019– | MIT Swift CLI. Homebrew tap. | Simple fallback | Shell-out, limited fields | Medium |
| 5 | remindctl | [listing](https://mcpservers.org/agent-skills/deepgram/apple-reminders) | 2025– | Homebrew CLI with JSON output and date views. Terminal needs Reminders permission. | JSON output | Third-party | Medium |
| 6 | remind-cli (Swift, direct EventKit) | [github.com/tonyhth/remind-cli](https://github.com/tonyhth/remind-cli) | 2025– | No runtime dependencies. macOS 14+. | Lightweight | Small project | Medium |
| 7 | remi (Node CLI + MCP) | [mcpservers.org](https://mcpservers.org/zh-TW/servers/mattheworiordan/remi) | 2025– | Sections support and iCloud sync. macOS 13+. | Sections | Node dependency | Low–Medium |
| 8 | iMCP (mattt) | [Reminders.swift](https://glama.ai/mcp/servers/@mattt/iMCP/blob/abe4463269172e9fd615866cb9e9f483de8c6f25/App/Services/Reminders.swift) | 2025 | Swift app exposing Reminders and Calendar via MCP | A Swift reference if Stiti uses a helper app | App, not a library | Medium |
| 9 | eventkit-rs | [docs.rs](https://docs.rs/crate/eventkit-rs/latest) | 2025– | Rust EventKit bindings | Possible native helper | Rust | Low |
| 10 | launchd StartCalendarInterval | [Apple "Scheduling Timed Jobs"](https://developer.apple.com/library/mac/documentation/MacOSX/Conceptual/BPSystemStartup/Chapters/ScheduledJobs.html); [Apple forum on sleep behaviour](https://developer.apple.com/forums/thread/815034) | — | A job missed during sleep runs on wake. Multiple missed intervals are coalesced into one ([launchd-dev](https://lists.macosforge.org/archives/list/launchd-dev@lists.macosforge.org/thread/7663OVG5WTTYISGGCVMDXBFRMSFWKPSV)). On macOS 15/26 with the lid open, a dark wake can fire the job but it may be suspended until full wake. | Built in, robust, survives reboot | **Cannot wake the Mac** (Apple engineer). Behaviour varies with lid state. | **High (daemon + check-ins)** |
| 11 | pmset / IOPMSchedulePowerEvent | [scheduling guide](https://docs.plakar.io/docs/community/main/guides/setup-scheduler-daily-backups/macos/); [Apple forum](https://developer.apple.com/forums/thread/815034) | — | `sudo pmset repeat wakeorpoweron MTWRFSU hh:mm:ss` (or a one-shot `pmset schedule wake`) plus `caffeinate` to stay awake | The only way to wake for a spoken alarm | Needs sudo. Laptop lid closed limits behaviour. | Medium (spoken wake-up alarms only) |
| 12 | Shortcuts CLI (`shortcuts run`) | [Apple support](https://support.apple.com/en-ng/guide/shortcuts-mac/apd455c82f02/mac); [guide](https://blakecrosley.com/guides/shortcuts) | macOS 12+ | Exit code 0/1. `--input-path` for input. Avoid shortcuts with prompts. macOS Tahoe (26) adds personal automations on Mac (secondary source). | Access to Clock app or Focus actions not exposed elsewhere | Opaque, slower, prompts block | Medium (fallback; Focus/DND toggles) |
| 13 | osascript `display notification` | [dev.to guide](https://dev.to/bphogan/how-to-use-macos-notifications-with-your-command-line-programs-ma4); [blog example](https://verityj.github.io/2023/06/11/python.html) | — | Python calls `osascript` to show a banner with a sound | Zero dependencies | Attributed to Script Editor/Terminal. No actions or buttons. | Medium (banner fallback) |
| 14 | Private reminders not shown in the Reminders app | [Apple dev forum](https://developer.apple.com/forums/thread/127665) | — | Discussion of whether apps can keep private reminders. EventKit reminders are visible in Reminders.app. | Clarifies the limitation | — | Note |

### Inferences
- **Recommendation: a three-layer alarm system.**
  1. **Durable alarms** (anything with a time the user cares about) go to EventKit as an `EKReminder` with an `EKAlarm(absoluteDate)` in a dedicated "Stiti" list. Events go to the calendar with an alarm. These fire through Apple's notification system on Mac, iPhone and Watch even if Stiti has crashed or the Mac is asleep, because the phone still rings. This is the reliability backbone. The PyObjC pattern is `EKEventStore`, then request full access to reminders, then `EKReminder.reminderWithEventStore_`, `setTitle_`, `setCalendar_`, `setDueDateComponents_`, then `addAlarm_(EKAlarm.alarmWithAbsoluteDate_(nsdate))`, then `saveReminder_commit_error_`. The method names are inferred from ObjC naming and must be verified by running them.
  2. **Spoken alarms and check-ins:** Stiti's daemon, kept alive by a LaunchAgent (`KeepAlive`, `RunAtLoad`), holds an in-process scheduler such as APScheduler with a SQLite jobstore. On wake, Laya reconciles missed jobs (launchd coalesces missed intervals), drops stale nudges, and fires only still-relevant alarms with a "you missed this while the Mac was asleep" framing.
  3. **Waking for a spoken morning brief** (optional): `pmset schedule wake` a few minutes before the brief, then `caffeinate -i` while speaking. Document that this needs sudo and the lid open.
- **TCC and permissions:** run Stiti as a signed `.app` bundle (py2app or a small Swift wrapper) with `NSRemindersFullAccessUsageDescription` and `NSCalendarsFullAccessUsageDescription`, so permission prompts attach to "Stiti" and not to Terminal. Treat `remindctl` or `reminders-cli` as a dev-time fallback.
- **Two-way sync:** poll `EKEventStoreChangedNotification` or fetch on wake. Map by `calendarItemIdentifier`. When the user completes a reminder on the iPhone, Laya marks the task done and updates habit strength.
- **Don't** depend on Shortcuts for core alarms because of opacity and prompts. Use it only for Focus mode toggles.

### Gaps
- I did not verify the PyObjC method names for EKAlarm and saving by running code. The macOS 14+ `requestFullAccessToRemindersWithCompletion_` API name is also unverified for PyObjC.
- I found no source on `UNUserNotificationCenter` from PyObjC (actionable notifications) or on terminal-notifier and alerter maintenance status as of 2026.
- I did not research how Reminders alarms behave when Focus modes are active.
