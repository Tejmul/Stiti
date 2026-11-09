# Stiti — Build Log

The record of how Stiti was researched and built, so work never depends on a chat history.
Motive and rules: [../CLAUDE.md](../CLAUDE.md) · Plan: [PLAN.md](PLAN.md) · Decisions: [DECISIONS.md](DECISIONS.md)
· Research: [../reports/](../reports/), [../research_notes/](../research_notes/)

Project location: `~/Desktop/Stiti` (moved from `~/Stiti` on 2026-11-10; `~/Stiti` should be a symlink to it
so the installed Stiti.app launcher and older paths keep working:
`rm ~/Stiti/.placeholder && rmdir ~/Stiti && ln -s ~/Desktop/Stiti ~/Stiti`).
Note: the Desktop is iCloud-synced — keep `.venv` (1.8 GB) out of iCloud or move the project to `~/Projects`.

---

## 2026-11-10 — research night + build night

### Research (rule: ≥10 papers/architectures per feature before deciding)
- 6 parallel research tracks → `research_notes/Stiti personal AI buddy research/` (assistants, memory/KG in
  Postgres, voice+emotion, productivity+psychology, LLM routing+documents, MCP/Mac control) → synthesized in
  `reports/Stiti personal AI buddy research.md` (~14k words).
- rea used to reverse-engineer OpenClaw's memory pipeline (dreaming, candidate-truth confidence).
- Owner decisions: **Postgres** (not SQLite), **no local LLM / no Ollama**, free tiers only, brain ≠ LLM.

### Built (all tested; see `tests/run_all.sh`, CI on every push)
| Area | What | Proof |
|---|---|---|
| Brain | Postgres 18 + pgvector: episodes ∞, bitemporal facts, lessons, directives, hybrid RRF recall, context compiler, router (Groq→Cerebras→OpenRouter→Mistral, Gemini P0 only), privacy P0/P1/P2 | recall 10/10 ~10 ms; LongMemEval-style 12/12 |
| Decisions | exemplar kNN on the embedder + rule floors (Laya parked: 13–15/30, 2.7 GB) | 26/30, 8 ms |
| Fast paths | todos, alarms, reminders, timers, Hinglish dates, plans, habits, chunker, WOOP — no LLM | dates 15/15 |
| Knows you | onboarding (10 Q), two-way USER.md/LESSONS.md, encrypted nightly backups (Keychain key) | sync 10/10, restore round-trip |
| Voice | wake ("Stiti", "Hi/Hey Stiti", "Wake up baby girl"), stop words ("shut up", "okay", "chalo", "bye", "bas") → silent until woken, Smart Turn v3.2, WebRTC AEC3 barge-in, filler, resume after "haan" | AEC self-hearing 84%→0%; Smart Turn 6/6 |
| Emotion | prosody vs personal baseline + text mood; emotion2vec+ optional (+1.5 GB) | |
| Proactive | presence, meeting heads-ups, deadlines, breaks, wrap-up, follow-ups, Thompson-sampled nudge gate | proactive eval 10/10 |
| Mac | EventKit calendar r/w + Reminders two-way (rings on iPhone), Spotlight, music, iMessage (confirm), web search/read, screen + Vision OCR | |
| Learning | inferred lessons (2 sightings ≥0.72), lesson scoring + curation, undo + clarify + exemplar learning, segments, reflections | learning eval 9/9 |
| App | menubar Stiti.app at login, type-to-Stiti, quick todo, mood timeline, health, log rotation | footprint 2.76 GB → 1.25 GB |
| Open source | owner profile (name/pronouns), nothing hard-coded to one person; key-things capture from talk | |

### Not yet verified
- Anything needing a cloud LLM (conversation, tool calling, night fact extraction, reflections) — no API key yet.
- Real-voice quality (Hinglish STT, false wakes) — first real use: "Bye." correctly silenced her.

---

## In progress (2026-11-10, late)

### A. "Key Things to Know" intake (5–6 min, any owner)
- Built: interview engine `brain/intake.py` (sections, progress, skip/pause/resume, "why?", spoken 1–5 scale
  parser), owner profile (`profile.py`, migration 005), tentative traits in USER.md (editable, owner wins),
  passive key-things capture (`brain/keythings.py`).
- ✅ Research done → `research_notes/Key things to know intake/intake_research.md` (decision D13): 20-turn intake
  (~6 min est.) from licence-safe instruments only (IPIP/Mini-IPIP, TIPI/TIVI; Stiti-original wording for the rest),
  31-row psychology guide, ethics rules (consent ×2, P2 for stress answers, no sensitive inferences).
- Next (with the research in hand): `brain/guide.py` (questions + `label_for` + `CHOICE_VALUES` + rules), `brain/understanding.py`
  (`guide_lines()` used by the compiler; adaptations: chronotype → quiet hours, social energy → nudge budget,
  support style → stress replies), trigger phrase "key things", full scripted test, push.

### B. Whiteboard tutor ("teach me this book in 30 minutes")
- Idea: Stiti opens a local whiteboard (Excalidraw-like) in the browser, draws diagrams while she talks,
  checks understanding, and the learner can interrupt with questions; book → outline via RAG over ingested
  chunks (cites pages).
- ✅ Research done (decision D14) → `research_notes/Whiteboard tutor/whiteboard_tech.md` (Excalidraw 0.18.1 + esm.sh,
  Starlette WebSocket, sentence-level cues, dagre layout, book→outline pipeline; tested on this Mac) and
  `tutoring_pedagogy.md` (26+4 min session template, tutor rules, 8 interruption types, lesson JSON schema,
  ~330-word system prompt).
- Next: `tutor/` package — board server + Excalidraw page, cue player synced to Kokoro, lesson planner (cloud LLM,
  strict JSON), book outline from ingested chunks, voice commands ("ruko", "phir se", question), FSRS cards.
- Constraint: lesson generation needs the cloud LLM (free key). Board, drawing engine, voice sync,
  interruptions and book ingestion can be built and tested without it.

---

## 2026-11-10 (night 2) — whiteboard tutor + web app

### Whiteboard tutor (`src/stiti/tutor/`, D15) — paused here by Tejmul to focus on chat; resume tomorrow
| Piece | What | Proof |
|---|---|---|
| Board | Excalidraw 0.18.1 page + runtime (sketch/grow/type/fade, camera, reset/replay), Starlette WS server (token + Host/Origin + CSP), presenter mode (F) for a big monitor | Playwright screenshots; WS security checks |
| Skills | semantic ops → layout in Python (pages, regions, relative placement, graphs/trees, tables, formulas, stickies, highlights, Q&A side boards, parking lot) | demo layout 0 overlaps; tree centred |
| Player | cue per sentence synced to Kokoro audio (prefetch 3), pause/continue/repeat/back/skip/slower/faster by voice or button, barge-in, questions answered on a side board, checks with hint ladder + confidence, hook revisited, resume cursor | scripted 24-cue lesson at 200× speed |
| Content | hand-written demo "How a compiler works" (8 parts, 5 checks, 5 cards); LLM planner (outline + 1 call per idea, strict JSON) | planner unverified (no key) |
| Books | printed-Contents parser + page offsets + heading fallback + extractive page-tagged sources | Aho: 654 headings, 2.7 s |
| Memory | migration 006 (lessons, sessions, study_cards) + one episode per lesson; app voice loop quiet during lessons | tutor eval 27/27 |

### Web app (`src/stiti/web/`, D16)
- `uv run stiti web` → landing page + `/chat`. Chat = same Engine (fast paths ran in 80–560 ms on the test DB),
  side panel with todos (tick to finish) + alarms/reminders, Stiti's breathing particle "mind", action chips with
  the owner's pictograms. Web eval 12/12 (security + a real turn).
- Landing page built in parallel by a sub-agent from the owner's motion spec; particles only in the hero (owner rule).

### Not verified
- Any LLM path (planner, live Q&A answers, chat replies via cloud). Real voice in a lesson (mic + AEC with the
  board on a monitor). Excalidraw needs internet for the CDN (offline bundle is the next step).
