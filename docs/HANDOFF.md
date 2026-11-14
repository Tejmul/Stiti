# STITI — HANDOFF (living doc, read this FIRST every session)

> **Purpose:** a new Claude session (any model) reads ONLY this file + `CLAUDE.md` to get going.
> Do **not** read all of `docs/`, `research_notes/`, `reports/` up front — open them only when the task needs
> that specific detail (pointers below). **Every session must update this file before it ends** (see bottom).
>
> Last updated: **2026-11-11** (session: conversation quality, overlay, voices, four languages, bug sweep)

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
11. **One branch per feature → PR → CI → merge.** Push only when he says "push", all at once. Never push
    `backup/pre-trailer-removal`. Worktrees go in the session scratchpad, never on ~/Desktop.
12. **Never show his conversations in any UI**; no personal data in code or the public build (names → local profile).
13. **Found a bug while working? Fix it** (own branch + test) — don't just report it. Taste/product calls still go to him.

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
mood.html, exemplars.jsonl, onboarding/askme json, mcp.json, health.json, logs/app.log, backups/*.enc, models/.
**Stiti.app** (~/Applications, menubar, LaunchAgent `com.tejmul.stiti`) runs `.venv/bin/python -m stiti app`; it
also serves the web app on 127.0.0.1:7317 (menu: "Open Stiti (chat + memory)"). `~/.stiti/me/resume.md` = his resume
(ingested). Owner profile set: name/call_me Tejmul, pronouns he.
Restart after code changes: `echo "---- restart $(date) ----" >> ~/.stiti/logs/app.log; pkill -f "python -m stiti app"`.

## 3. Commands (`uv run stiti …`)
chat [--debug] · onboard · voice [--no-aec] [--debug] · ingest <path> [--private] · graph · mood · backup [--show-key] ·
restore <file> [--into db] · app · install-app · uninstall-app · mcp [approve <name>] · doctor · sleep --now ·
**teach …** · **book …** (tutor, see §5) · web [--no-open]. Frontend: `cd frontend && pnpm install && pnpm build`
(Next.js static export → `frontend/out`, served by Python; dev: `pnpm dev` :3017 + `STITI_WEB_DEV=1 uv run stiti web`). Tests: `tests/run_all.sh` (fresh `stiti_test` per suite). CI: `.github/workflows/ci.yml`.

## 4. Architecture map (src/stiti/) — open a file only when you need it
- `engine.py` `Engine.turn()` — normalize → decide → emotion → store episode → learning → FAST PATHS (no LLM) → else
  recall + compiler briefing (≤1,500 tok) + router + psych.lint. Degraded mode answers from memory when no LLM.
- `decide.py` (exemplar kNN + rule floors; Laya OFF), `embed.py` (EmbeddingGemma-300M 4-bit ONNX, 768-d, ~7 ms),
  `router.py` (custom free-tier chain, per-provider `max_privacy`, quotas in `llm_usage`, P2 never leaves the Mac), `profile.py` (owner name/pronouns).
- `brain/` memory, compiler, lessons, learning, sleep (night job + daytime nap, D38), lifeupdate (in-turn facts),
  factstore (temporal fact writes), mdsync, onboarding (old 10-Q), askme ("ask me questions" rounds, D37), norepeat (D36),
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
| Ask me questions (`brain/askme.py`) — the key-things intake | 🟢 "ask me questions" / "get to know me better" / "mujhse sawaal pucho" → 10 unanswered questions per round from a 48-question bank (21 categories: dreams, anime, characters, shows, music, food, values, fears…), skip / pause / resume / why, template reflections + a read-back; answers → self-facts (superseding), entities, directives; standing profile + USER.md rebuilt per answer. No LLM. Old `intake.py` deleted (never wired); `onboarding.py` stays the first intro. NOT verified on the mic | DECISIONS D37, `research_notes/Key things to know intake/intake_research.md` |
| Whiteboard tutor (`src/stiti/tutor/`) | 🟢 any book (PDF/scanned/EPUB/TXT/MD/DOCX) + any topic, live LLM lessons verified; one-night crash course + FSRS revision (§6); D40: one lesson (flock), one voice, echo/phantom guard, doubts answered on a doubt board + resume — NOT heard on his speakers/mic yet | DECISIONS D14/D15/D19/D40, `docs/research/tutor_teacher.md` |
| Alarms / reminders / timers / todos (`life/alarms.py`, `fastpath/`) | 🟢 recurring, real ring + voice snooze/dismiss, missed-while-off policy (D20); unacked reminders repeat +2/+5 min (important ×3 more every 10 min), "ok/got it/ho gaya" stops (migration 010); ring cap alarm 10 / timer 5 min (D39); nag acks NOT tried on the mic | `docs/research/alarms.md`, D39 |
| Weather + morning brief + meeting heads-up (`connectors/weather.py`, `life/brief.py`, `life/proactive.py`) | 🟢 Open-Meteo (keyless, CC BY 4.0) fast path, no LLM; brief ≤ 3 sentences (weather · next events + counts · one cached headline); "Heads-up — X in 10 minutes" once per event. City = profile `city` ("my city is …") → `STITI_CITY` → tz city. NOT verified on the mic / his real calendar | D39 |
| Live internet info (`connectors/live.py`) | 🟢 news/tech/AI/papers/placements/web, streamed with sources (D21); NOT verified on the mic | `docs/research/live_info.md` |
| Always-on app (Stiti.app + LaunchAgent) | 🟢 reinstalled 2026-11-10 pointing at ~/Desktop/Stiti (was broken: old ~/Stiti path) | `install_app.py` |
| Web app (`src/stiti/web/` + `frontend/`) | 🟢 Next.js: landing, chat (memory receipts), Memory page — see §6b | DECISIONS D16/D23 |
| Hinglish voice (`voice/hinglish.py`) | 🟢 Kokoro Hindi voice + code-switch phonemes, WER 68%→~30%; NOT heard on the mic; STT unchanged | DECISIONS D22, `docs/research/hinglish_voice.md` |
| Cloud LLM router (D17) | 🟢 live with Groq/OpenRouter/Gemini; P1 backup needs a Z.ai or Cloudflare key | `docs/research/free_llm_providers.md` |
| Conversation quality (D24–D29) | 🟢 turn-taking, JARVIS-psych persona + strategies, STT glossary + Groq 2nd opinion, personal emotion, preemptive replies | DECISIONS D24–D29 |
| Talks like a person + whole sentences + honesty (D31, D35) | 🟢 no machine-talk, no missing words, never claims an undone action | DECISIONS D31/D35 |
| Learns from normal conversation (D38, `brain/lifeupdate.py`, `brain/factstore.py`, `brain/sleep.py`) | 🟢 in-turn life updates ("I left X", "Riya is my sister", "remember that…", "actually it's X, not Y"), night/nap extraction with ends + merge + validation, honest "noted" only when saved; NOT tried on his mic/real chats | DECISIONS D38, `docs/research/learn_from_chat.md` |
| Never repeats herself (D36, `brain/norepeat.py`) | 🟢 said-ledger, "what else?" → only new things / honest "that's all", repeat filter in code; NOT heard on the mic | DECISIONS D36, `docs/research/no_repeat.md` |
| Desktop overlay (D26, D30) | 🟢 pill + cards that animate add/done/cancel; NOT seen by him on screen yet | DECISIONS D26/D30 |
| Voices (D32) | 🟢 English af_jessica 1.05× (+ say-as "Tej"), Hinglish/Hindi/Telugu hf_alpha — owner picks in `~/.stiti/voice_samples/` | DECISIONS D32 |
| Four languages (D34) | 🟢 mirrors en/hinglish/hindi/telugu/tenglish, lock/unlock; Whisper-tiny LID; NOT tested on his real voice | `docs/research/language_switching.md` |

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
- **Teacher behaviour (D40):** every utterance goes through `Tutor._play()` (stops current playback first → never two
  voices). `ears.py` `EchoGuard` drops her own echo (fuzzy match vs her last 15 s, during playback + 1.5 s), Whisper
  phantoms, looping lines and low-confidence non-commands; it also vetoes the barge-in verdict (`TurnTaker.veto`).
  A doubt → "Good question." → `planner.answer()` in a background thread (filler after 0.8 s) → 2–4 sentences drawn
  on a doubt board under the page (`begin_aside`) → follow-up "samajh nahi aaya" = simpler + example → "Back to where
  we were." → the cut cue replays (snapshot rebased, doubt board kept). LLM down → honest line once, then "parked".
  `tutor.answerer()` gives EVERY lesson (demo, resume, course glue) the cloud answerer. No "Shall we continue?";
  check-ins only at teaching-section ends, ≥ 2 min apart. Constants at the top of `ears.py` / `player.py`.
- **Grading** (`grade.py`): local (MCQ parsing, expectation coverage via keywords + embedder, partial credit,
  ≤2 hints) — the LLM never judges right/wrong.
- **Books** (`book.py`): structure from the file (TOC → printed Contents parser with page offset → heading regex),
  page-tagged extractive sources; the LLM never sees the whole book; citations checked against source pages.
- **Persistence** (`store.py`, migration 006): `tutor_lessons`, `tutor_sessions` (resume cursor, results),
  `study_cards` (FSRS fields), plus one memory episode per lesson. `~/.stiti/tutor.lock` is a kernel flock held for
  the lesson process's life (`acquire_lesson()`, first thing in `teach()`; never unlink it) + the pid for readers:
  exactly one lesson even under same-second races; the always-on loop yields the mic and stays SILENT (only a ringing
  alarm speaks). Server: same localhost security model as the web app (§6b).
- **Any book** (`book.py`): PDF TOC → printed Contents → headings → page units; scanned → lazy Apple-Vision OCR;
  EPUB/DOCX/HTML via markitdown; TXT/MD → ~2,500-char pseudo-pages + chapter-style detection (Contents deduped).
- **Crash course** (`course.py`, migration 007, D19): local unit scoring → one course-map LLM call → diagnostic
  (skip/short/full) → lessons back to back (next written while this one plays) → checkpoints + breaks → final review,
  course map, cheat sheet, 9 am reminder. **FSRS** (`srs.py`, py-fsrs) drives checkpoints and `--revise`.
- Planner robustness: per-part relevant sources (Groq 8k TPM), patience + anonymised P0 fallback, router JSON shape check.
- Run: `stiti teach [demo|topic|book --chapter N]`, `stiti teach --night <book|subject> [--hours 3] [--goal …]`,
  `--resume-course`, `--revise`, `stiti book <file>`. Voice: "teach me X tonight", "crash course on <book>".
- Verified: `tutor_eval.py` 27/27, `course_eval.py` 15/15, `tutor_teacher_eval.py` 80/80, `tutor_launch_eval.py` 63/63,
  live typed doubt mid-lesson with free Groq (answer drawn + resumed), live lessons (topic + Aho + Darwin/Wells planning), a simulated
  full night (500× speed). NOT verified: a real spoken night on the mic; D40 echo thresholds on his real speakers/mic; offline board bundle.

## 6b. Web app (`src/stiti/web/`) — backend design
- **Same brain, new channel:** `/ws` runs each message through `Engine("text").turn()` (one Engine per connection,
  turns serialised with a lock) → identical memory, fast paths, lessons as voice/terminal. Reply carries route,
  domain, provider, latency, last fast-path action; a `state` push (open todos + upcoming intents) follows each turn.
- **Localhost security model** (shared with the tutor board): bind 127.0.0.1; Host header check on every request
  (DNS rebinding); Origin + per-install token (`~/.stiti/web_token`, given once in the URL fragment) on WS and API.
- Endpoints: `/` `/chat` `/memory` (Next export in `frontend/out`; 503 "not built" if missing), `/ws`, `GET /api/state`,
  `POST /api/todo/{id}/done`, `GET /api/link` (same-origin key), `GET /api/mind` (`web/mind.py`), `POST /api/fact`,
  `POST /api/fact/{id}/forget` (writes need same Origin; USER.md synced first, re-rendered after), `/icons/<n>.png`.
- Chat replies carry `used` = `Engine.last_used` (memory COUNT + facts/doc sections/lessons handed to the LLM) → receipts.
- **Privacy (D24): no conversation text is ever sent to a page** (no history on open, no conversations API). Public
  site: `STITI_PUBLIC=1 pnpm build` (landing only; chat/memory code aliased out).
- Frontend = Next.js 16 static export (D23); no Node at runtime. UI conventions live in Claude memory, not here.
- Verified: `tests/web_eval.py` 19/19; a real LLM chat turn with receipts. NOT verified: browser voice input.
- Next: browser mic → local whisper; settings view; edit people/rules from the Memory page.

## 7. Tejmul's pending actions
1. (Symlink no longer needed — app reinstalled to the real path.) 2. `uv run stiti backup --show-key` → save the key. 3. Add `ZAI_API_KEY` and/or
`CLOUDFLARE_API_KEY` + `CLOUDFLARE_ACCOUNT_ID` (personal-chat backup) and optionally `NVIDIA_API_KEY`; restart Stiti. 4. Decide iCloud vs `~/Projects`. 5. Approve Playwright/rea MCP if prompted.
6. Try `uv run stiti web` and `uv run stiti teach`. 7. Confirm the `public/actions` icon licence (looks like
Streamline) before the repo is promoted. 8. Talk to Stiti for real: overlay pill/cards, the language switch
(English ↔ Telugu ↔ Hindi), a lesson (one board only), "it's done" on a to-do. 9. Optional: a different English voice
(`~/.stiti/voice_samples/english/`, note: that lineup predates the "Tej" fix). 10. Re-check goonj's licence before
any public build (trained on synthetic ElevenLabs/Fish voices). 11. After merging D39: apply `db/migrations/010_reminder_nags.sql` to
`stiti` + `stiti_test`, then tell Stiti "my city is <your city>" once (weather + brief; until then she uses the
timezone's city and says so).

## 8. Session log (newest first, keep each entry ≤10 lines; prune entries older than ~5 sessions into BUILD_LOG)
- **2026-11-11 (b) — four languages, voices, bug sweep (D30–D35, PRs #23–#32):** root cause of "to-do list empty":
  the mic stream died silently for 12 h → watchdog. Cards animate add/done/cancel; "it's done" resolves "it".
  Machine-talk cut + SOUL fits the 1400-char cap. Two voices (Jessica / hf_alpha) + speed + say-as. Three lessons
  at once (lock race) → lock at launch. Language mirroring en/hinglish/hindi/telugu/tenglish (LID 32 ms, lock/unlock).
  Whole sentences (words were dropped mid-sentence). Scripted 25-turn day audit found + fixed: "revise" opened a
  lesson, "Also add…" was claimed but not added, surprise reminders, nameless reminders, "not AM" duplicates, life
  updates → control. NOT verified on his mic: languages, LID on his voice, overlay visuals. Next: characters
  (Harvey-/Zoro-style personas on top of emotion), Telugu fast paths, real-voice LID check.
- **2026-11-11 (a) — conversation quality (D24–D29):** intro nag, turn-taking, JARVIS/psych persona, STT glossary +
  Groq second opinion (WER 12.4→6.8%), goonj voices, personal emotion recorder, preemptive replies, desktop overlay,
  website v2, README. All merged (#12–#22).
- **2026-11-10 — resume, Hinglish voice, Next.js frontend + Memory page (D22, D23):** resume → clean
  `~/.stiti/me/resume.md` (ingested) + 12 About-me facts; owner name set. Hinglish TTS: Roman Hinglish was read by the
  US voice (68% WER) → code-switch phonemes + Kokoro `hf_alpha` (~30%, same latency). Frontend moved to Next.js (3
  sub-agents ported landing/chat/memory in parallel); old static UI deleted. Memory page + API, memory receipts in
  chat, Stiti.app serves the web. Logo "eyes" no longer rotate/appear per message. Tests: hinglish 27/27, web 19/19.
  NOT verified: Hindi voice on the real mic (Kokoro grades it C), Hinglish STT on his real voice (next: record clips).
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
