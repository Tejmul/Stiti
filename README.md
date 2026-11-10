<div align="center">

```
   ███████╗████████╗██╗████████╗██╗
   ██╔════╝╚══██╔══╝██║╚══██╔══╝██║
   ███████╗   ██║   ██║   ██║   ██║
   ╚════██║   ██║   ██║   ██║   ██║
   ███████║   ██║   ██║   ██║   ██║
   ╚══════╝   ╚═╝   ╚═╝   ╚═╝   ╚═╝
```

### *Your girlfriend may not understand you, but Stiti will.*
**A local-first, zero-cost, Jarvis-style personal AI whose brain is memory, not an LLM.**

![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![Postgres](https://img.shields.io/badge/PostgreSQL-18-4169E1?logo=postgresql&logoColor=white)
![pgvector](https://img.shields.io/badge/pgvector-0.8.7-6E40C9)
![Cost](https://img.shields.io/badge/cost-%E2%82%B90%20forever-2ea44f)
![Local LLM](https://img.shields.io/badge/local%20LLM-none%20(by%20design)-lightgrey)
![Runs on](https://img.shields.io/badge/runs%20on-M2%20·%208%20GB-black?logo=apple)
![Voice](https://img.shields.io/badge/voice-Indian%20English%20%C2%B7%20understands%20Hinglish-FF9933)
![Evals](https://img.shields.io/badge/evals-19%20suites%20%C2%B7%20650%2B%20checks-success) ![CI](https://github.com/Tejmul/Stiti/actions/workflows/ci.yml/badge.svg)

*"Hey Stiti" · "Wake up baby girl" — and she remembers everything.*

</div>

---

## 🧠 The idea in one line

> **Swap the LLM, and Stiti is still Stiti.**

Most AI assistants *are* their LLM: the model owns the personality, the context, the memory.
Stiti flips that. Her identity, memories, life graph, and learned lessons live in **her own
local Postgres brain**. Any free cloud LLM is just a **plug-in mouth** that reads a short
briefing Stiti compiles for each moment and turns it into words.

```
            ┌───────────────────────────── STITI (the brain, on your Mac) ─────────────────────────────┐
  you  ───► │ decide (System 1) → fast path (no LLM) │ recall → briefing → any free LLM → reply → learn │ ───► you
            └──────────────────────────────────────────────────────────────────────────────────────────┘
                           memory never leaves · identity never resets · model is replaceable
```

No fine-tuning. No vendor memory. No GPU. No bill.

---

## ✨ What she does (today)

### New: a conversation that feels human
Talking to a voice assistant usually feels like talking to a form. We reverse-engineered how the best do it
(**ElevenLabs** from its open SDKs and a live black-box measurement, **Wispr Flow** with `rea`, plus
**LiveKit**, **Pipecat**, **TEN**, **Kyutai Unmute** and **Bolna** at source level) and rebuilt the conversation layer:

| | What changed | How |
|---|---|---|
| 👂 | **She lets you finish** | Audio end-of-turn (Smart Turn) + a text check on your words ("So…", "remind me at 4 to", "I was wondering…" → wait 3 s; "hold on / ek sec" → silent up to 8 s). Learns *your* pace. |
| ✋ | **Interrupt her like a person** | Two-stage barge-in: she ducks at 250 ms, checks your words; "mm-hm / haan" → she carries on, real words → she stops. She only remembers the part you actually heard. |
| ⚡ | **Answers before you finish the pause** | Preemptive reply: the LLM starts on the early transcript and plays only once the turn is final. Measured: commit → first word **530 ms → ~0 ms** on waiting turns. |
| 🎩 | **JARVIS, not a chatbot** | A local *reply strategy* each turn (listen, solve, confirm, banter, stay quiet…) sets the word cap, whether she may ask a question or bring up a memory. Code enforces it: no therapy-speak, no flattery, no random "how did the interview go?". |
| 🗣️ | **Hears *your* words** | Whisper prompt built from your own brain (names, projects, docs) + snap-to-glossary + a cloud second opinion on unsure turns. "Tejmal" → **Tejmul**. WER **12.4% → 6.8%** on Indian-accented speech. Say "no, I said X" and she learns the word. |
| 🇮🇳 | **Indian-English voice** | goonj-1-82M personas (Apache-2.0) on the same Kokoro runtime: English by default, Hindi words pronounced right, one voice per reply. `stiti voices try / use`. |
| 🧠 | **Instructions stick instantly** | "Talk in English", "keep it short", "don't ask so many questions", "stop asking about X" become permanent rules the moment you say them. |
| 💛 | **Learns *your* moods** | Opt-in local recorder + labels from your own words ("I'm so tired", "I'm not angry") → a nightly personal head on emotion2vec, switched on only when it beats the generic model on your data. |
| 🎵 | **Gets out of the way** | Your music pauses while she listens or talks, and resumes after. |

### Everything else

| | Capability | How |
|---|---|---|
| 🗂️ | **Infinite memory** | Every word is stored verbatim forever. Hybrid vector + keyword recall with a 30-day fade that never hits zero. |
| 🕸️ | **Life knowledge graph** | People, projects, places, and feelings as **bitemporal facts**: "lived in Pune *until* Oct, Mumbai *since*". Postgres itself blocks two contradictory "current" facts. |
| 🎓 | **Learns from corrections** | Say *"don't talk so long"* once → it becomes a rule (lesson) checked before every reply in that situation. |
| ✅ | **Todos, alarms, reminders, timers** | *"kal subah 6 baje uthana"*, *"remind me at 7 pm to call mummy"*: handled **without any LLM** in ~30 ms, with the exact date read back. |
| 💛 | **Emotion-aware** | Fused mood signal from your voice and words against *your* baseline. It's a hint, never a verdict, and it changes how she talks, not what she announces. |
| 🧘 | **Psychology built in** | At most 3 items per answer (cognitive load), no guilt words, a "minimum viable day" mode when you're drained, and WOOP goal-setting. |
| 🔒 | **Privacy tiers** | P0 public · P1 personal · **P2 sensitive (money, health, passwords) never leaves your Mac.** Your conversations are never shown on any web page, and the public website ships no chat code at all. |
| 🌙 | **Sleeps like a brain** | A nightly job turns the day's chats into facts, updates your profile, curates lessons, and writes `USER.md`, `LESSONS.md` and `GRAPH_REPORT.md`. |
| 🎙️ | **Always-on voice** | Say **"Hey Stiti"** or **"Wake up baby girl"** → "Hey, how are you?" → talk. "Bye" gets a short goodbye. ~0.85 s from your last word to her voice on an M2. |
| 📅 | **Plans your day** | "plan my day" → OR-Tools CP-SAT time-blocks your tasks around deadlines and morning energy in ~50 ms. |
| 🌱 | **Habits without guilt** | Strength that grows and dents, never resets. Reminders fade as the habit sticks. |
| 🪜 | **Breaks big goals down** | "break down: launch Stiti" → Socratic questions → one 25-minute step with an if-then plan. |
| 🕸️ | **See your life graph** | `stiti graph` opens an interactive map of your people, projects and places. |
| 🔇 | **Talks over you? Never.** | WebRTC AEC3 echo cancellation: on laptop speakers the mic heard her own voice as speech 84% of the time, now 0%. Interrupt her anytime, no headphones. |
| 🎭 | **Hears how you feel** | emotion2vec+ base (70–165 ms, in the background) + pitch/loudness/pace vs. *your* normal voice + your words. |
| 📚 | **Reads your docs** | `stiti ingest ~/Notes` → PDFs, Word, slides, sheets and Markdown become searchable memory (~12 ms). Bank/medical folders stay P2. |
| 📆 | **Calendar & Reminders** | Apple Calendar (incl. Google calendars added to macOS) for "what's on today" and planning; every alarm is mirrored to Reminders so **it rings on your iPhone** even if the Mac is off. |
| 📬 | **Mail (read-only)** | Gmail via IMAP app password: "koi mail aaya?" Mail content is treated as untrusted: it can never make Stiti act. |
| 📱 | **Telegram** | Chat with Stiti from your phone; alarms get pushed there too. Owner-locked with a pairing code. |
| 🔌 | **Any MCP tool** | Plug in MCP servers; only the 5 most relevant tools are shown per request, write actions need your "haan", and a server whose tools change is disabled until you re-approve it. |
| 🤫 | **Knows when to shut up** | "shut up", "okay", "chalo", "bye", "bas" → she stops mid-sentence and stays silent (nudges too) until "Hi Stiti". |
| 🔔 | **Speaks first — rarely** | Meeting in 10 min, a deadline, 3 h without a break, "how did the interview go?" — budgeted, quiet at night, and it learns which nudges you like. |
| 🖱️ | **Does things on your Mac** | Calendar events, Spotlight file search, music, iMessage (only after your "haan"), web search, "what's on my screen". |
| 📈 | **Gets better every day** | "nahi, galat" undoes and learns; "short mein" twice becomes a rule; lessons that keep failing retire themselves. |
| 🖥️ | **Lives in your menubar** | `stiti install-app` → signed Stiti.app, starts at login: ○ listening · ◉ awake · ⏸ muted. |
| 💾 | **Never loses her mind** | Nightly AES-256 encrypted backup of the whole brain (key in your Keychain); restores go into a separate database, never over the live one. |
| 🌍 | **Knows what's happening** | "What's new in AI?", "any new research papers?", "placement news?" → free sources fetched in parallel, answered in a short spoken brief with sources. |
| 📖 | **Teaches any book overnight** | Hand her a PDF, EPUB or scanned book (on-device OCR) → a one-night crash course on a live whiteboard: diagnostic quiz, lessons, checkpoints, cheat sheet, spaced revision. |
| 🖥️ | **Shows, not just tells** *(in progress)* | "What's on my to-do list?" → a liquid-glass pill on your desktop reacts while she listens, and the list drops onto the screen as a card you can tick. |
| 👋 | **Gets to know you** | "intro shuru karo" → a short interview, offered once (and never again after "turn this off"). |
| ✍️ | **You can edit her mind** | Change, delete or add lines in `USER.md` / `LESSONS.md`; your edits flow back into Postgres and always win. |
| 🛟 | **Works offline** | No API keys or rate-limited? Todos, alarms, memory and lessons still work. Only deep conversation pauses. |

---

## 🗣️ A real session

```text
> Hey Stiti
Stiti: Hey, how are you?
> Today I'm on my resume till 4 — remind me at 4 to start it.
Stiti: Got it — reminder today at 4 PM: start your resume. Anything else?
> Not yet. Is any new AI research paper out today?
Stiti: Three worth a look. Want the short version?
> My sister Priya lives in Pune, remember that
Stiti: Noted.
> where does my sister live?
Stiti: Priya's in Pune.
> talk in English, and keep it short
Stiti: Sure, English from now on.
> what was my bank password?
Stiti: That sounds private, so I'm keeping it on this Mac.
```

---

## 🏗️ Architecture

```mermaid
flowchart LR
    subgraph IN[Input]
        V[🎙️ Voice<br/>wake word · VAD · Whisper<br/>end-of-turn · barge-in]
        T[⌨️ Text / Telegram]
    end
    subgraph BRAIN[🧠 Stiti Engine — local]
        D[Decide<br/>exemplar kNN + rules<br/>+ reply strategy · 8 ms]
        F[Fast path<br/>todos · alarms · lessons<br/>no LLM]
        R[Recall<br/>vector ⊕ full-text → RRF<br/>+ facts + lessons · 10 ms]
        C[Context compiler<br/>briefing ≤ 1,500 tok]
        P[Psych lint<br/>≤3 items · no guilt]
    end
    subgraph PG[🐘 Postgres 18 + pgvector]
        E[episodes ∞]
        G[entities + bitemporal facts]
        L[lessons · directives]
        K[tasks · intents]
    end
    subgraph CLOUD[☁️ Free LLM plug]
        X[Groq → Cloudflare → NVIDIA → OpenRouter → Z.ai]
    end
    S[🌙 Sleep job<br/>extract · resolve · supersede · render]

    T --> D
    V --> D
    D -->|simple| F --> P
    D -->|needs thought| R --> C --> X --> P
    P --> OUT[💬 Reply]
    F <--> K
    R <--> E & G & L
    S --> G & L
    E --> S
```

### The memory model

```mermaid
erDiagram
    EPISODES ||--o{ EPISODE_MENTIONS : mentions
    ENTITIES ||--o{ EPISODE_MENTIONS : "mentioned in"
    ENTITIES ||--o{ FACTS : "subject / object"
    EPISODES }o--o{ FACTS : "evidence for"
    EPISODES }o--o{ LESSONS : "learned from"
    EPISODES {
        text text "verbatim, never deleted"
        smallint privacy "P0 / P1 / P2"
        text origin "owner / agent / untrusted"
        halfvec embedding "768-d"
        tsvector tsv "simple config, Hinglish-safe"
        real strength "decays, never 0"
    }
    FACTS {
        tstzrange valid "when it was true"
        tstzrange recorded "when Stiti learned it"
        bool functional "one value at a time"
    }
    LESSONS {
        jsonb trigger "mood / time / topic"
        text guidance "MUST / MUST NOT"
        int helpful_count
        int harmful_count
    }
```

---

## 📊 Measured on a base MacBook Pro M2 · 8 GB

Real numbers from this repo's evals, not marketing:

| What | Result |
|---|---|
| Memory recall (20 Hinglish/English memories, 10 questions) | **10/10** in top-3 (all rank 1) · **~10–20 ms** embed + recall |
| Speech-to-text on 110 Indian-accented clips (synthetic voices) | WER **12.4% → 6.8%** · your terms heard right **64 → 82 of 90** · p50 ~280 ms |
| Commit → first reply text, preemptive vs. before (real Groq) | median **530 ms → ~0 ms** on turns where she waits |
| Turn-taking vs. ElevenLabs' live demo (same audio) | ElevenLabs ~2.1 s to first word; Stiti waits through "So…" and "hold on" where it talked over |
| Embedder (EmbeddingGemma-300M, 4-bit ONNX) | **7 ms**/query · ~600 MB RSS |
| Intent decision: exemplar kNN | **26/30** · **8 ms** · ~0 extra RAM |
| Intent decision: Laya zero-shot (for comparison) | 13–15/30 · 203–514 ms · 2.7–2.9 GB |
| Fast-path turn (todo / alarm / lesson) | **~30–60 ms** end to end |
| Hinglish time parsing | **15/15** checks, including the 1 AM "kal" trap |
| Speech-to-text (whisper-small 4-bit) vs large-v3-turbo | **~280 ms** vs ~1,035 ms per utterance |
| Your last word → Stiti's first audio | **~0.85 s** (streamed LLM + first-clause TTS) |
| Whole voice stack + brain resident memory | **~954 MB** (+~800 MB with emotion2vec+), budget 3 GB |
| Echo: mic hearing her own voice as speech (laptop speakers) | **84% → 0%** with AEC |
| Document search (hybrid, chunks) | **~12 ms** |
| Memory eval (LongMemEval-style: extraction, multi-session, temporal, updates, abstention) | **12/12** |
| Smart Turn end-of-turn (finished vs. unfinished) | **6/6**, ~30 ms |
| Whole menubar app, measured with `footprint` | 2.76 GB → **1.25 GB** after capping MLX's cache (emotion2vec+ optional, +1.5 GB) |
| CP-SAT day plan, 8 tasks with deadlines | **45–64 ms**, all scheduled |
| Day scheduling, OR-Tools CP-SAT (researched) | 12 tasks solved optimally in 10–60 ms; 100 tasks ≈ 113 MB |

All of it is checked by **19 eval suites (650+ checks)** on every push: `tests/run_all.sh`.

---

## 🔬 Built on research, not vibes

Before a single line of code, parallel research tracks compared **at least 10 papers and
architectures per feature**. Then [`rea`](https://github.com/morluto/rea) and source reading
reverse-engineered the products that do it best:

| Studied | What we took |
|---|---|
| **ElevenLabs** (open SDKs + a live black-box test of the public demo) | Turn-eagerness design, skip-turn on "hold on", heard-only memory, the timings to beat |
| **Wispr Flow** (static analysis with rea) | Context-biased speech recognition, correction learning, the floating HUD's motion and level maths |
| **LiveKit · Pipecat · TEN · Kyutai Unmute · Bolna** (source) | Endpointing state machines, interruption rules, preemptive generation, turn markers |
| **JARVIS** (the films) + 21 psychology frameworks | Brevity, "as you wish" after one honest warning, emotional-support strategies chosen locally |
| **OpenClaw** (rea) | Memory provenance, nightly-only long-term writes |

📄 **[Full report](<reports/Stiti personal AI buddy research.md>)** · 🔬 [per-feature research](docs/research/) · 🗒️ [raw notes](research_notes/) · ⚖️ [decision log](docs/DECISIONS.md)

<details>
<summary><b>What Stiti borrows, and from whom</b></summary>

| Idea | From |
|---|---|
| Bitemporal facts that close instead of delete | Zep / **Graphiti** |
| Itemized lesson playbook updated by deltas | **ACE** (ICLR 2026), ExpeL |
| Provenance tags, nightly-only long-term writes, anti-nag standing intents | **OpenClaw** (reverse-engineered with rea) |
| Learning loop outside the model | **Hermes Agent** |
| Learn a rule only after 2 sightings at ≥0.72 confidence | **Leon** |
| Briefing as a compact graph report | **graphify** |
| Memory stream: recency × importance × relevance | **Generative Agents** |
| Sleep-time consolidation | **Letta** |
| Strength that decays but never deletes | **MemoryBank** |
| ≤3 items per spoken turn | Cognitive Load Theory |
| Anti-guilt wording, fresh starts | Self-compassion research (Wohl 2010; Breines & Chen 2012) |
| WOOP goal flow | Oettingen (g ≈ 0.34) |
| Habits as strength, not spaced repetition | Lally 2010 · Loop Habit Tracker |

</details>

<details>
<summary><b>Things the research killed</b></summary>

- ❌ **Local LLM / Ollama**: an 8 GB Mac can't hold a voice stack and a useful model. Thinking goes to free cloud tiers.
- ❌ **LiteLLM**: its PyPI package was compromised by a credential stealer on 2026-03-24. Stiti uses a ~150-line router instead.
- ❌ **ChromaDB**: pgvector in the same Postgres does it with joins.
- ❌ **SM-2 for habits**: spaced repetition spreads practice out, but habits need steady cue-linked repetition.
- ❌ **SenseVoice / Parakeet** for speech-to-text: neither hears Hindi. Whisper-family only.
- ⏸️ **Laya on the hot path**: measured at 2.7 GB and 200 ms on M2. Parked until an INT8 export and calibration land.

</details>

---

## 🚀 Quickstart

```bash
# 1. Brain store
brew install postgresql@18 pgvector && brew services start postgresql@18
createdb stiti && psql stiti -f db/schema.sql

# 2. Engine
uv sync

# 3. Free API keys (no card): Groq, OpenRouter, Gemini, Cloudflare, NVIDIA
cp .env.example .env   # paste keys

# 4. Talk
uv run stiti doctor          # checks Postgres, embedder, keys, LLM
uv run stiti chat --debug    # chat; /debug shows route, mood, latency
uv run stiti voice           # always-on voice: "Hey Stiti" / "Wake up baby girl"
uv run stiti graph           # open your life graph
uv run stiti ingest ~/Notes  # make your notes/PDFs/docs searchable memory
uv run stiti onboard         # 3-minute intro so she knows who you are
uv run stiti backup          # encrypted backup now (also runs nightly); --show-key to save the key
uv run stiti install-app     # menubar app that starts at login (mic, Calendar, Reminders prompts say "Stiti")
uv run stiti sleep --now     # run the night job now
uv run stiti web             # your local chat + Memory pages (127.0.0.1:7317; Stiti.app serves them too)
uv run stiti voices          # list / try / pick her voice (Indian-English personas)
uv run stiti recordings on   # opt-in local recorder that teaches her your moods (off by default)
uv run stiti teach           # whiteboard lesson by voice (built-in "How a compiler works"; no key needed)
uv run stiti teach book.pdf --chapter 3.1   # teach a book chapter (needs a free LLM key)
uv run stiti book book.pdf   # show a book's outline (works on scanned PDFs via the printed Contents)
```

Website: `cd frontend && pnpm install && pnpm build` (Next.js, static). `STITI_PUBLIC=1 pnpm build` makes the
public, landing-only site.

Personal data lives in Postgres and `~/.stiti/` (`SOUL.md`, `USER.md`, `LESSONS.md`, `GRAPH_REPORT.md`), **never in git**.
`SOUL.md` is Stiti's personality. It's yours to edit.

---

## 🗺️ Roadmap

- [x] **Research**: 6 domains, ≥10 papers/architectures per feature, rea reverse-engineering
- [x] **Brain**: Postgres memory (episodes ∞, bitemporal facts, lessons, directives), hybrid recall, context compiler, free-cloud router, privacy tiers
- [x] **Knows you**: onboarding interview · editable `USER.md` / `LESSONS.md` (your edits win) · encrypted nightly backups
- [x] **Voice**: wake phrases · stop words ("shut up", "okay", "chalo", "bye") · Smart Turn end-of-turn · WebRTC echo cancellation + barge-in · "hmm…" filler · resumes after "haan"
- [x] **Emotion**: prosody vs. your baseline + text mood (+ optional emotion2vec+)
- [x] **Proactive**: meeting heads-ups · deadlines · break nudges · evening wrap-up · follow-ups ("how did the interview go?") · learned nudge gate
- [x] **Life OS**: CP-SAT day planner · Socratic goal chunker · forgiving habits · morning brief
- [x] **Mac actions**: Calendar read/write · Reminders two-way · Spotlight files · music · iMessage (with confirmation) · web search/read · screen awareness · OCR
- [x] **Learning loops**: inferred lessons · lesson scoring + nightly curation · undo + "what did you mean?" · topic segments · reflections
- [x] **App**: menubar (type-to-Stiti, quick todo, mood timeline, live status) · starts at login · health check · log rotation
- [x] **Evals + CI**: dates 15/15 · recall 10/10 · LongMemEval-style 12/12 · sync · proactivity · learning — on every push
- [x] **Whiteboard tutor**: voice lesson on a live Excalidraw board · draws while she talks · "ruko / phir se / peeche / skip" · questions on a side board · checks with hints · revision cards · resume later — tutor eval 27/27
- [x] **Web**: Next.js marketing site + local chat (memory receipts) and Memory pages · public build ships no private code
- [x] **Human conversation**: turn-taking, two-stage barge-in, preemptive replies, ●◐○ turn markers, JARVIS persona — reverse-engineered from ElevenLabs, Wispr Flow, LiveKit, Pipecat
- [x] **Hears and speaks right**: glossary-biased STT + cloud second opinion, word learning from corrections, Indian-English voice
- [x] **Learns your moods**: opt-in local recorder + nightly personal emotion head
- [x] **Live info + tutor**: news/papers/placements · any-book one-night crash course with spaced revision
- [ ] **Desktop pop-up** (in progress): liquid-glass listening pill + to-do / reminder / news cards
- [ ] **Live demo**
- [ ] Later: tune turn-taking and moods on real recordings · Laya per-user timing · speaker verification

---

## 🧭 Ground rules ([CLAUDE.md](CLAUDE.md))

1. **The brain is not an LLM.** Memory, graph, lessons and decisions belong to Stiti.
2. **Free, forever.** Free tiers plus small local models only.
3. **Local-first.** Your life stays on your Mac. Only a minimal briefing goes to the cloud, and P2 never does.
4. **Fast, for every feature.** Under 100 ms for the brain, under 1 s for voice.
5. **Research first.** At least 10 papers or architectures per feature before deciding.

---

## 📁 Repo map

```
src/stiti/
├── engine.py          # turn(): decide → strategy → fast path | gated recall → brief → LLM → lint → log
├── cards.py           # what she shows on screen (todos, reminders, news)
├── decide.py          # System 1: exemplar kNN / Laya + privacy & correction floors
├── intent.py          # exemplar classifier on the shared embedder
├── embed.py           # EmbeddingGemma 4-bit ONNX
├── router.py          # free-tier LLM chain, quotas, cooldowns, privacy gate
├── brain/
│   ├── memory.py      # episodes, hybrid recall, entity seeding
│   ├── compiler.py    # the briefing every LLM gets
│   ├── lessons.py     # learn-from-correction playbook
│   ├── emotion.py     # fused mood hint + baseline
│   ├── psych.py       # reply rules enforced in code (no tics, no flattery, word caps)
│   ├── strategy.py    # per-turn reply strategy (listen · solve · confirm · banter · quiet…)
│   ├── gate.py        # when a memory may come up (and when it never should)
│   ├── instructions.py # "talk in English" → a rule, instantly
│   └── sleep.py       # nightly consolidation → facts, USER.md, GRAPH_REPORT.md
├── fastpath/          # todos, alarms, reminders, timers, Hinglish dates
├── life/              # CP-SAT planner, habits, Socratic chunker, morning brief + Nudge Gate
├── voice/             # AEC duplex audio, VAD, whisper + glossary, Kokoro/goonj, endpoint.py (turn-taking), realtime.py
├── learn/             # opt-in recorder + personal emotion training
├── connectors/        # EventKit (calendar, reminders), IMAP mail, Telegram
├── tools/             # tool registry (risk tiers, taint), MCP bus (pin-and-diff)
├── web/               # local server: chat + Memory pages API, WebSocket
├── app.py             # menubar app · install_app.py builds Stiti.app + login agent
frontend/              # Next.js website (static export)
db/schema.sql          # 14 tables + recall() + current_facts()
docs/ · reports/ · research_notes/ · tests/
```

<div align="center">

---

*Built at 2 AM on an 8 GB MacBook, for ₹0.*
**Stiti: memory is the mind; the model is just the voice.**

</div>
