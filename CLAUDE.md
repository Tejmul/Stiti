# Stiti — Project Motive & Ground Rules

> This file is loaded automatically in every Claude session. It holds the
> **motive** of the project so the owner (Tejmul) never has to repeat it.
> Full plan: [docs/PLAN.md](docs/PLAN.md) · Research: [docs/RESEARCH.md](docs/RESEARCH.md)

## What Stiti is

Stiti is Tejmul's personal **Jarvis-like buddy** that runs **locally** on his Mac.
He talks to it by voice, like talking to a real person. Stiti:

- **Knows him completely** — who he is, his people, projects, habits, likes/dislikes,
  and *how people should talk to him*.
- **Has "infinite" memory** — never forgets a conversation; can recall what happened
  last week or last year.
- **Learns from situations** — "in that situation it was done like this, so don't talk
  like that again." Corrections become permanent rules, not forgotten chat.
- **Has a knowledge graph** of his life (people, projects, places, events, feelings)
  that can be viewed and linked, similar to how **graphify** gives an AI context.
- **Understands emotions from his voice** (angry, stressed, happy, tired…) and adapts
  how it responds.
- **Manages his todos**, sets **alarms / reminders**, and does real tasks.
- **Connects to tools** (calendar, mail, files, GitHub, phone chat, etc.) through
  pluggable connectors.
- **Thinks in real time** and talks naturally: fast replies, can be interrupted,
  says "hmm, let me check" while working, keeps thinking in the background.

## Non-negotiable principles

1. **The brain is NOT an LLM. The brain is Stiti's own memory engine (RAG + knowledge
   graph + rules).** Identity, memory, lessons, user model and the knowledge graph live
   in Stiti's own local store. The **Context Compiler** decides what is relevant and
   builds a short "briefing" (like graphify's GRAPH_REPORT.md) for each turn. Any LLM
   (Groq, Cerebras, OpenRouter, Mistral, Gemini… free cloud tiers) is only a **plug-in "mouth"** that
   turns that briefing into words. Rules that follow from this:
   - Swap the LLM and Stiti must still be the same person with the same memory.
   - Stiti must work even with a small/weak free model, so the brain does the heavy
     lifting (retrieval, ranking, emotion, rule matching) *before* the LLM is called.
   - **Decisions are made by Stiti, not the LLM.** A local **Decision layer (Laya)**
     answers many typed questions about each moment in one fast pass (intent, which
     tool, tone to use, is this a correction, how important, does this need the LLM…).
     Simple actions (add todo, set alarm, list todos) run from these decisions without
     calling an LLM at all.
   - **No LLM fine-tuning.** Learning = writing to memory/graph/lessons. The only
     exception: Stiti's own small local decision model (Laya) may be calibrated or
     fine-tuned on Stiti's own logged decisions, locally and free, because it is part
     of the brain, not the LLM.
   - Never store Stiti's knowledge only inside an LLM provider's chat history/memory.
2. **Free of cost.** No paid services. Use free tiers (OpenRouter `:free`, Groq,
   Gemini AI Studio) and local open-source models. Always have a fallback chain so a
   rate-limit never kills Stiti.
3. **Local-first.** All memory and personal data stay on this Mac (`~/.stiti/`).
   Only the minimal compiled context for a turn goes to a cloud LLM.
4. **Fast, for every feature.** Voice-to-first-audio target < 1 s. Memory retrieval
   < 100 ms. Stream everything. If a feature makes Stiti slow, it runs in the background.
5. **Hardware reality: Apple M2, 8 GB RAM.** Local models must be small (total
   ~3 GB budget). **No local LLM, no Ollama** (Tejmul's rule: it overloads the Mac).
   All LLM work goes to free cloud tiers. Small local models are OK only for VAD,
   speech-to-text, text-to-speech, emotion, embeddings and Laya. If every cloud
   provider is down, Stiti still runs fast-path actions (todos, alarms, recall) and
   says it can't think deeply right now.
6. **Connectors, not hard-coding.** Tools plug in via **MCP** (Model Context Protocol)
   so any new tool can be added without changing the core.
7. **Human-readable memory.** Core identity lives in plain markdown (`SOUL.md`,
   `USER.md`, `LESSONS.md`) that Tejmul can read and edit. Database is the index,
   markdown is the truth he can see.

## How we build every feature (the loop)

For **each** feature, follow this order. Do not skip to coding.

1. **Research deeply** — for **every feature, at least 10 research papers and/or
   architectures** (arXiv papers, GitHub projects, models, builder write-ups) before any
   decision. Put them in a comparison table (mechanism, strengths, weaknesses, fits
   free + 8 GB M2?) in `docs/research/<feature>.md`. No decision from 2–3 search hits.
2. **Reverse-engineer** — study how the top 1–3 are built. Read source for open-source
   projects; use **rea** (`npx rea-agents setup`, https://github.com/morluto/rea) to
   inspect JS/Electron apps, websites, binaries, model files. Only analyze software we
   are allowed to (open source, or our own installed apps for learning/interoperability).
   Don't copy proprietary code — learn the design.
3. **Design** — pick the smallest version that fits the principles above (free, local,
   fast, 8 GB). Record the choice + why in `docs/DECISIONS.md`.
4. **Build** — small, testable pieces. Measure latency and RAM.
5. **Update docs** — tick off the roadmap in `docs/PLAN.md`.

## Tech defaults (change only with a recorded decision)

- Language: **Python 3.12**, managed with **uv**. Voice pipeline: **Pipecat**.
- Storage: **PostgreSQL** (local, Homebrew) as the single brain store: `pgvector` for
  embeddings, Postgres full-text search for keywords, graph as nodes/edges tables
  with temporal validity (recursive CTEs; Apache AGE only if needed). No separate
  vector DB (no ChromaDB). Markdown identity files live in `~/.stiti/`.
- Decision layer: **Laya** (`pip install laya`, https://github.com/NandhaKishorM/laya),
  batch all questions about a moment into one call; gate on calibrated confidence.
- LLM access: OpenAI-compatible router over free cloud providers only (no Ollama / no local LLM).
- Secrets in `.env` (never committed).

## Session start / end protocol (every session, every model)

- **Start:** read [docs/HANDOFF.md](docs/HANDOFF.md) first. It is the compact, always-current handover
  (rules, environment, architecture map, feature status, next steps). Don't read all of `docs/`,
  `research_notes/` or `reports/` up front — open only what the current task needs (HANDOFF points to it).
- **End:** when Tejmul says "push" / "I'm ending" / "wrap up", follow the END-OF-SESSION PROTOCOL at the
  bottom of `docs/HANDOFF.md`: update HANDOFF (status, next steps, session-log entry), update other docs only
  where things changed, run tests, commit (no Claude trailers), push.

## Working style with Tejmul

- He explains ideas in casual English; take the intent, not the exact words.
- He wants it to "become crazy" — ambitious, but shipped in small working steps.
- Prefer showing a working demo over long theory.
