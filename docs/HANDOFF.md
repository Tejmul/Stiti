# STITI — HANDOFF (living doc, read this FIRST every session)

> **Purpose:** a new Claude session (any model) reads ONLY this file + `CLAUDE.md` to get going.
> Do **not** read all of `docs/`, `research_notes/`, `reports/` up front — open them only when the task needs
> that specific detail (pointers below). **Every session must update this file before it ends** (see bottom).
>
> Last updated: **2026-11-10** (session: whiteboard tutor build)

---

## 0. Hard rules from Tejmul (never break)
1. **Brain ≠ LLM.** Identity/memory/decisions live in Stiti's local Postgres brain; the LLM is a swappable cloud
   "mouth" fed a compiled briefing. No LLM fine-tuning (small local decision models like Laya may be tuned).
2. **No local LLM, no Ollama — ever.** LLM = free cloud tiers only (D17: Groq, Z.ai GLM, Cloudflare, OpenRouter :free,
   Mistral; NVIDIA + Gemini for public questions only).
3. **Free only.** Zero cost.
4. **Postgres** is the store (not SQLite, not ChromaDB).
5. **Research before building:** ≥10 papers/architectures per feature, comparison table, then decide
   (`research_notes/<topic>/`, decision in `docs/DECISIONS.md`).
6. **Git: NO `Co-Authored-By: Claude`, no "Generated with Claude Code"** — commits authored by Tejmul only.
   Small meaningful commits. He likes a "crazy" README. Building first; commits are secondary.
7. Hardware: **Apple M2, 8 GB RAM**; local stuff ≤ ~3 GB. Measure RAM with `footprint -p <pid>`.
8. Tejmul writes casual Hinglish/English — take intent over exact words. Short status updates, build fast & fully.
9. Pronouns for Tejmul not stated → use "they" or the name. Stiti is "she" (wake phrase "wake up baby girl").
10. README tagline: "Your girlfriend may not understand you, but Stiti will."

## 1. Machine / environment
- Repo **/Users/tejmul/Desktop/Stiti** (GitHub Tejmul/Stiti, public, `main`). Python 3.12 via **uv**; Node 26; gh CLI as `Tejmul`.
- Postgres 18 (brew `postgresql@18`) + pgvector. DBs: `stiti` (REAL brain — never put test data here), `stiti_test`.
  Schema `db/schema.sql` + `db/migrations/*.sql` (apply new migrations to BOTH DBs).
- `~/Stiti` must become a symlink to `~/Desktop/Stiti` (Stiti.app launcher hard-codes it). Tejmul runs:
  `rm -r ~/Stiti/research_notes ~/Stiti/.placeholder && rmdir ~/Stiti && ln -s ~/Desktop/Stiti ~/Stiti`
- Desktop is iCloud-synced (1.8 GB `.venv`) — undecided: move to `~/Projects` or `.venv.nosync`.
- Untracked `actions/` (PNG assets) is Tejmul's — don't commit or delete.
- `.env` exists (Groq, OpenRouter, Gemini keys set 2026-11-10; Z.ai/Cloudflare/NVIDIA slots empty). Real LLM calls
  verified via the router (voice chain, P0 fallback, tutor strict JSON).
- Claude Code MCP (`.mcp.json`): playwright, rea (reverse-engineering).
- Gotchas: zsh doesn't word-split `$VAR` commands; force-push / deleting the working dir are blocked (ask Tejmul);
  CI uses `macos-latest`; `uv run stiti` with no args waits on stdin — always pass a subcommand.

## 2. Runtime layout
`~/.stiti/` (STITI_HOME): SOUL.md, USER.md & LESSONS.md (two-way synced with Postgres), GRAPH_REPORT.md, graph.html,
mood.html, exemplars.jsonl, onboarding/intake json, mcp.json, health.json, logs/app.log, backups/*.enc, models/.
**Stiti.app** (~/Applications, menubar, LaunchAgent `com.tejmul.stiti`) runs `.venv/bin/python -m stiti app`.
Restart after code changes: `echo "---- restart $(date) ----" >> ~/.stiti/logs/app.log; pkill -f "python -m stiti app"`.

## 3. Commands (`uv run stiti …`)
chat [--debug] · onboard · voice [--no-aec] [--debug] · ingest <path> [--private] · graph · mood · backup [--show-key] ·
restore <file> [--into db] · app · install-app · uninstall-app · mcp [approve <name>] · doctor · sleep --now ·
**teach …** · **book …** (tutor, see §5). Tests: `tests/run_all.sh` (fresh `stiti_test` per suite). CI: `.github/workflows/ci.yml`.

## 4. Architecture map (src/stiti/) — open a file only when you need it
- `engine.py` `Engine.turn()` — normalize → decide → emotion → store episode → learning → FAST PATHS (no LLM) → else
  recall + compiler briefing (≤1,500 tok) + router + psych.lint. Degraded mode answers from memory when no LLM.
- `decide.py` (exemplar kNN + rule floors; Laya OFF), `embed.py` (EmbeddingGemma-300M 4-bit ONNX, 768-d, ~7 ms),
  `router.py` (custom free-tier chain, per-provider `max_privacy`, quotas in `llm_usage`, P2 never leaves the Mac), `profile.py` (owner name/pronouns).
- `brain/` memory, compiler, lessons, learning, sleep (night job), mdsync, onboarding (old 10-Q), intake (new engine),
  keythings, emotion, psych, ingest (documents/chunks), graphview, moodview, backup.
- `fastpath/` Hinglish dates + handlers · `life/` planner (CP-SAT), habits, chunker, brief, proactive.
- `voice/` duplex (AEC3), vad, stt (mlx-whisper small q4), tts (Kokoro int8 + ClauseChunker), turn (Smart Turn), wake,
  prosody, speaker (gapless streamed speech, acks, fillers), loop. Speed design: D18. `farewell.py` goodbyes.
- `connectors/` eventkit, mail (IMAP read-only), telegram, mac (Spotlight/music/iMessage/web/screen), ocr,
  live (free news/papers/jobs/web fetch → untrusted LIVE INFO block in the briefing, D21).
- `tools/` registry (risk tiers, confirm), mcp_bus · `app.py` menubar.
- **`tutor/`** whiteboard tutor (see §5).

## 5. Feature status
| Feature | Status | Where to read more |
|---|---|---|
| Memory/brain, fast paths, voice, proactive, Mac connectors, backups, app | ✅ built + tested (see `docs/BUILD_LOG.md`) | BUILD_LOG |
| Key-things intake v2 (`brain/guide.py`, `brain/understanding.py`) | 🟡 engine built; question set + adaptations TODO | `research_notes/Key things to know intake/intake_research.md`, DECISIONS D13 |
| Whiteboard tutor (`src/stiti/tutor/`) | 🟢 any book (PDF/scanned/EPUB/TXT/MD/DOCX) + any topic, live LLM lessons verified; one-night crash course + FSRS revision (§6) | DECISIONS D14/D15/D19 |
| Alarms / reminders / timers / todos (`life/alarms.py`, `fastpath/`) | 🟢 recurring, real ring + voice snooze/dismiss, missed-while-off policy (D20) | `docs/research/alarms.md` |
| Live internet info (`connectors/live.py`) | 🟢 news/tech/AI/papers/placements/web, streamed with sources (D21); NOT verified on the mic | `docs/research/live_info.md` |
| Always-on app (Stiti.app + LaunchAgent) | 🟢 reinstalled 2026-11-10 pointing at ~/Desktop/Stiti (was broken: old ~/Stiti path) | `install_app.py` |
| Web app (`src/stiti/web/`) | 🟢 `stiti web`: chat + landing — see §6b | DECISIONS D16 |
| Cloud LLM router (D17) | 🟢 live with Groq/OpenRouter/Gemini; P1 backup needs a Z.ai or Cloudflare key | `docs/research/free_llm_providers.md` |

## 6. Whiteboard tutor (`src/stiti/tutor/`) — backend design
- **Pattern: the brain decides, the LLM fills slots.** Code owns lesson shape (warm-up → hook → map → teach ×3 →
  quiz → wrap), timing, resume and grading; the LLM only writes teaching segments as strict JSON
  (`router.complete(schema=…)`, constrained decoding on Groq/Cerebras, `tutor_plan` chain) in a background thread.
- **Lesson format** (`lesson.py`): segment → cues (one spoken sentence + flat, all-nullable board ops) + optional
  check. Same format for hand-written demos and LLM output; `sanitize_*` is the trust boundary.
- **Layout in code** (`skills.py` Board): semantic ops (region / right_of / below / graph nodes+edges) → coordinates;
  deterministic, unit-tested; `snapshot()/restore()` per cue gives exact repeat/back/resume.
- **Sync:** audio synthesised 3 cues ahead; each cue's ops scheduled at real offsets (`resolve_at`: word bookmark →
  proportional time, since Kokoro int8 has no word timings).
- **Event loop** (`player.py`): one queue merges browser controls, typed text and voice transcripts; `commands.py`
  classifies Hinglish controls locally before anything else; questions → LLM answer or local lookup (embedder).
- **Grading** (`grade.py`): local (MCQ parsing, expectation coverage via keywords + embedder, partial credit,
  ≤2 hints) — the LLM never judges right/wrong.
- **Books** (`book.py`): structure from the file (TOC → printed Contents parser with page offset → heading regex),
  page-tagged extractive sources; the LLM never sees the whole book; citations checked against source pages.
- **Persistence** (`store.py`, migration 006): `tutor_lessons`, `tutor_sessions` (resume cursor, results),
  `study_cards` (FSRS fields), plus one memory episode per lesson. `~/.stiti/tutor.lock` makes the always-on
  voice loop yield the mic. Server: same localhost security model as the web app (§6b).
- **Any book** (`book.py`): PDF TOC → printed Contents → headings → page units; scanned → lazy Apple-Vision OCR;
  EPUB/DOCX/HTML via markitdown; TXT/MD → ~2,500-char pseudo-pages + chapter-style detection (Contents deduped).
- **Crash course** (`course.py`, migration 007, D19): local unit scoring → one course-map LLM call → diagnostic
  (skip/short/full) → lessons back to back (next written while this one plays) → checkpoints + breaks → final review,
  course map, cheat sheet, 9 am reminder. **FSRS** (`srs.py`, py-fsrs) drives checkpoints and `--revise`.
- Planner robustness: per-part relevant sources (Groq 8k TPM), patience + anonymised P0 fallback, router JSON shape check.
- Run: `stiti teach [demo|topic|book --chapter N]`, `stiti teach --night <book|subject> [--hours 3] [--goal …]`,
  `--resume-course`, `--revise`, `stiti book <file>`. Voice: "teach me X tonight", "crash course on <book>".
- Verified: `tutor_eval.py` 27/27, `course_eval.py` 16/16, live lessons (topic + Aho + Darwin/Wells planning), a simulated
  full night (500× speed). NOT verified: a real spoken night on the mic; offline board bundle.

## 6b. Web app (`src/stiti/web/`) — backend design
- **Same brain, new channel:** `/ws` runs each message through `Engine("text").turn()` (one Engine per connection,
  turns serialised with a lock) → identical memory, fast paths, lessons as voice/terminal. Reply carries route,
  domain, provider, latency, last fast-path action; a `state` push (open todos + upcoming intents) follows each turn.
- **Localhost security model** (shared with the tutor board): bind 127.0.0.1; Host header check on every request
  (DNS rebinding); Origin + per-install token (`~/.stiti/web_token`, given once in the URL fragment) on WS and API.
- Endpoints: `/` `/chat` (static), `/ws`, `GET /api/state`, `POST /api/todo/{id}/done`, `/icons/<n>.png`.
- Static frontend, no build step (ES modules + pinned CDNs). UI conventions live in Claude memory, not here.
- Verified: `tests/web_eval.py` 12/12. NOT verified: LLM replies in chat (no key); browser voice input.
- Next: browser mic → local whisper; streaming replies; memory search / mood / settings views.

## 7. Tejmul's pending actions
1. (Symlink no longer needed — app reinstalled to the real path.) 2. `uv run stiti backup --show-key` → save the key. 3. Add `ZAI_API_KEY` and/or
`CLOUDFLARE_API_KEY` + `CLOUDFLARE_ACCOUNT_ID` (personal-chat backup) and optionally `NVIDIA_API_KEY`; restart Stiti. 4. Decide iCloud vs `~/Projects`. 5. Approve Playwright/rea MCP if prompted.
6. Try `uv run stiti web` and `uv run stiti teach`. 7. Confirm the `public/actions` icon licence (looks like
Streamline) before the repo is promoted.

## 8. Session log (newest first, keep each entry ≤10 lines; prune entries older than ~5 sessions into BUILD_LOG)
- **2026-11-10 — always-on fix, any book, crash course, alarms (D19, D20):** Stiti.app launcher pointed at the old
  ~/Stiti → reinstalled; it runs now. Tutor: 4 bugs fixed, any-book loader, one-night crash course + FSRS. Alarms
  rebuilt (recurrence, ring/snooze by voice, missed policy, AM/PM + saade/sawa/paune), todos remove/clear/restore.
  Live web/news tools built by a sub-agent (see its research doc `docs/research/live_info.md`). Tests: course 16/16,
  alarms 23/23. NOT verified on the real mic: a crash-course night, an alarm ring + "band karo".
- **2026-11-10 — conversation speed + goodbyes (D18):** streamed LLM → first-clause TTS, gapless speaker, persistent
  Kokoro/whisper threads (Kokoro's 700 ms new-thread cost), early STT in the pause, Smart Turn re-checks, warm-up on
  start/wake, instant acks + fillers, warm goodbyes. Web chat streams too. Simulated: ~0.85–1.0 s voice→first audio
  (was ~2.3 s). `tests/speed_eval.py` 24/24. NOT verified: a real mic session (echo cancellation + barge-in mid-stream).
- **2026-11-10 — free LLM providers (D17):** Tejmul added Groq/OpenRouter/Gemini keys. Researched 17 free providers,
  measured latency live (Groq Qwen3.8-27B ~190 ms first token). Router: per-provider `max_privacy`, Z.ai/Cloudflare/
  NVIDIA added, Gemini `models/` ID bug + dead OpenRouter model fixed, OpenRouter `data_collection: deny` on P1.
  NOT verified: Z.ai/Cloudflare/NVIDIA (no keys yet); full chat turn through Engine with the LLM.
- **2026-11-10 — whiteboard tutor + web app:** created this HANDOFF + session protocol in CLAUDE.md. Built the
  tutor (§6, D15) then Tejmul switched priority to "normal chat features" → built `stiti web` (§6b, D16) with a
  sub-agent doing the landing page. New: migration 006 (applied to stiti + stiti_test), router `schema=` strict
  JSON + `tutor_plan` chain, engine fast path for tutor phrases, voice loop quiet during lessons, tests
  `tutor_eval.py` 27/27 + `web_eval.py` 12/12; full suite 8/8 green.
  Test tip: isolate with `STITI_DB=postgresql:///stiti_test STITI_HOME=<tmp>` + symlink `<tmp>/models → ~/.stiti/models`.
  Gotcha: the Playwright MCP browser is shared with sub-agents (one "current tab") — don't drive it in parallel.

---

## END-OF-SESSION PROTOCOL (mandatory, every session, every model)
When Tejmul says "push" / "I'm ending" / "wrap up" (or the session's work is clearly done):
1. Update this file: "Last updated", §5 status table, §6 (or the relevant feature section), §7 pending actions,
   and add a ≤10-line entry to §8 (what was built, what's verified vs NOT verified, exact next steps).
2. Update `docs/BUILD_LOG.md` / `docs/PLAN.md` / `docs/DECISIONS.md` only for things that changed.
3. Run `tests/run_all.sh`; report failures honestly.
4. Commit in small meaningful commits (NO Claude trailers / attribution), then `git push`.
Keep this file under ~250 lines: replace stale text instead of appending forever.
