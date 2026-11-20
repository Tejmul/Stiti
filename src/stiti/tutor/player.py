"""Tutor orchestrator: plays a lesson cue by cue, keeps board + voice in sync, and handles the learner.

Design (research §5 + pedagogy §7; OpenMAIC action engine, ChalkTalk hand-raise):
- One cue = one spoken sentence + its board ops. Audio is synthesised 3 cues ahead, so each cue's
  exact length is known and its ops are scheduled at real offsets (`at` word → proportional time).
- Every cue boundary keeps a board snapshot → repeat / back / resume-after-question redraw exactly.
- Code owns time, resume and repairs; content (LLM or hand-written) only fills slots.
- Voice-first: everything works by talking (board optional, MCQ options are read out loud).
- Checks are graded locally (grade.py). A miss climbs a code-owned hint ladder (Feature 5): nudge → hint → worked
  example → the answer; the rung he needed is kept on the record → FSRS rating. Never "samjha?". Pacing (pacing.py):
  never the same question twice; the coach spaces checks one per full idea and sparser when he's fed up.
- Doubts (D40): she stops, says "Good question —", turns to a doubt board under the current page, answers in
  2–4 sentences while drawing (cloud LLM in a background thread, a filler if it takes > 0.8 s), takes a follow-up
  ("still didn't get it" → simpler + an example), then "Back to where we were —" and replays the interrupted cue
  with the doubt board kept. LLM down → one honest line + what the lesson itself said, then just "parked".
- ONE voice: every line goes through `_play()`, which stops whatever is playing first; her echo / Whisper
  phantoms are dropped by `ears.EchoGuard` before they count as the learner. No "Shall we continue?" after every
  input — check-ins only at section ends, at most every 2 minutes.
"""
from __future__ import annotations

import queue
import re
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor

from . import commands, grade
from .ears import EchoGuard
from .lesson import Check, Lesson, Op, resolve_at
from .pacing import RUNGS, Pacing, rung_rating, sentences
from .skills import Board

PRAISE = "Yes, exactly right."
ACTIONABLE = {"control", "text", "voice", "click", "hand"}

# ---- teacher pacing (seconds; all scaled by Tutor(pace=…) so tests run fast) ----
FILLER_AFTER_S = 0.8        # a doubt's answer isn't back yet → one short filler ("Let me draw it out.")
ANSWER_TIMEOUT_S = 20.0     # the cloud gets this long, then the honest local answer
RESUME_GAP_S = 1.4          # after an answer: room for a follow-up doubt before "Back to where we were —"
FOLLOWUP_S = 45.0           # "still didn't get it" this soon after an answer is about THAT answer
SEGMENT_GAP_S = 0.6         # a breath between ideas (end of a section)
CHECKIN_MIN_GAP_S = 120.0   # "any doubt so far?" only at a section end, and at most this often
CHECKIN_WAIT_S = 3.0        # … then this long for a doubt before she carries on
LONG_PAUSE_S = 90.0         # paused and silent this long → one gentle "whenever you're ready"
BREAK_NUDGE_S = 6 * 60.0    # a day-mode break (5 min): the gentle nudge only after the break is over
# ---- his whole sentence before she acts (D52). The mic cuts his speech at every breath: 2026-11-20 "Tomorrow." was
# dropped as too short, then "I meant to say, tomorrow I have exam…" came as its own turn and she answered half of it.
GATHER_IDLE_S = 2.2         # no new words from him for this long (Whisper ~0.5 s + a breath) = he has finished
GATHER_MAX_S = 30.0         # a long explanation still gets heard to the end, up to this long
FRAG_S = 6.0                # a fragment dropped as "too short to interrupt" this recently starts his next sentence
GATHER_UNFINISHED_S = 4.5   # his words end mid-thought ("…so", "…I want you to") → wait this long for the rest
UNFINISHED_RX = re.compile(r"\b(so|and|but|or|because|to|the|a|an|of|in|on|with|for|is|are|was|like|that|which|"
                           r"if|then|i|my|you|want|mean|about|um+|uh+|actually|basically)\W*$", re.I)
BLURT_MORE_S = 4.0          # Blurt: after his first burst of recall, this long of quiet means he has finished
STALE_GRACE_S = 0.3        # speech starting this little before her question still counts as its answer (clock slop)
PTT_TAIL_S = 2.5           # hold-to-talk: speech still counts this long after he lets go (Whisper finishing)
STEER_LINES = {"skip_to": "Okay, let's jump ahead.", "restart": "Okay, let's go again from the start, slowly.",
               "switch": "Okay, let's switch to that.", "crash": "Got it. Let's cover the whole thing quickly for your exam."}

ACKS = ["Good question.", "Okay, good doubt.", "Hmm, nice one."]
FILLERS = ["Let me draw it out.", "One sec, let me sketch this.", "Let me show you on the board."]
BRIDGES = ["Back to where we were.", "Okay, back to the lesson.", "Right, back to where we were."]
SIMPLER = ["Okay, let me try it another way.", "No problem, simpler this time.", "Let me put it differently."]
CHECKINS = ["Any doubt so far? Just ask, or I'll carry on.", "All clear till here? Stop me any time with a doubt."]
OFFLINE_FIRST = "I can't reach my thinking brain right now, so here's the short version from this lesson."
OFFLINE_PARK_FIRST = "I can't reach my thinking brain right now, so I've parked that, and we'll come back to it."
OFFLINE_AGAIN = "Parked that one too. We'll come back to it."
_ACK_RX = re.compile(r"^(good|great|nice|achha|accha)( question| doubt| one)?[.!,—-]*\s*", re.I)


class Tutor:
    def __init__(self, lesson: Lesson, *, audio, events: queue.Queue, server=None, planner=None,
                 persist: bool = True, start: int = 0, log=print, idle_resume_s: float = 25,
                 check_timeout_s: float = 90, pace: float = 1.0):
        self.L, self.audio, self.events, self.srv, self.planner = lesson, audio, events, server, planner
        self.persist, self.log = persist, log
        self.idle_resume_s, self.check_timeout_s = idle_resume_s, check_timeout_s
        self.pace = pace                             # < 1 = every pause/gap shorter (tests)
        self.guard: EchoGuard = getattr(audio, "guard", None) or EchoGuard()
        self.answer_pool = ThreadPoolExecutor(1, thread_name_prefix="doubt")
        self._pick_i: dict[str, int] = {}
        self._offline_said = False                   # the honest "can't reach the cloud" line: once per lesson
        self.last_doubt: dict | None = None          # {"q", "a": [lines], "t"} for follow-ups
        self.last_checkin = time.time()
        self.checkins = 0
        self.cue_open = False
        self.board = Board()
        self.snaps: dict[int, dict] = {}
        self.k = start
        self.speed = 1.0
        self.results: list[dict] = []
        self.questions: list[str] = []
        self.predict: tuple[Check, str] | None = None
        self._hook_done = False
        self.ended = False
        self.drawn_at: dict[str, int] = {}
        self.pool = ThreadPoolExecutor(1, thread_name_prefix="tts")
        self.futs: dict[tuple[int, float], object] = {}
        self._cue_vecs = None
        self.lesson_id = self.session_id = None
        self._frag: tuple[float, str] | None = None   # (when, text) of a too-short piece of his speech
        self._held: deque = deque()                     # events that arrived while she waited for his whole sentence
        self.switch: dict | None = None                 # {"mode": switch|crash, "target", "say"} → __init__ plans it
        self.on_check = None                            # D53 coach: (segment, record) after every graded check
        self.skip_to: int | None = None                 # D53 coach: jump here at the next step (he knows the rest)
        self.before_end = None                          # D53 coach: () -> True when it added more segments
        # Feature 5: how often she asks (one check per full idea, sparser when he's fed up, never the same question
        # twice). Plain lessons ask every check they have (min_gap 0); the coach sets the gap and should_check.
        self.pacing = Pacing()
        self.should_check = None                        # (segment, pacing) -> bool: ask this check now?
        self.on_blurt = None                            # (segment) -> None: a "blurt" segment's free recall
        self.on_blurt_request = None                    # () -> bool: he said "test me" / "let me blurt"
        # hold-to-talk (Wispr Flow: the user decides when he's talking). 2026-11-20 demo: people talking in his room
        # ("Where did you play yesterday?") were graded as his answers. On: only speech while the key is held (or
        # within PTT_TAIL_S after release, while Whisper finishes) counts; commands like "end" too.
        self._since_q: float | None = None              # listen(): when her question started (stale speech is older)
        self.ptt_mode = False
        self.ptt_down = False
        self.ptt_up_t = 0.0
        if start:                                    # resuming: rebuild the board silently up to `start`
            flat = lesson.cue_list()
            for kk in range(min(start, len(flat))):
                self.snaps[kk] = self.board.snapshot()
                si, ci = flat[kk]
                self._apply(lesson.segments[si].cues[ci].ops, kk)

    # ------------------------------------------------------------ plumbing
    def send(self, msg: dict) -> None:
        if self.srv is not None:
            self.srv.send(msg)

    def status(self, mode: str, text: str, caption: str | None = None) -> None:
        m = {"type": "status", "mode": mode, "text": text}
        if caption is not None:
            m["caption"] = caption
        self.send(m)

    def on_connect(self) -> list[dict]:
        """A (re)loaded page gets the whole board instantly."""
        return [{"type": "reset", "actions": list(self.board.log)}]

    def _flat(self):
        return self.L.cue_list()

    def _cue(self, k):
        si, ci = self._flat()[k]
        return self.L.segments[si], self.L.segments[si].cues[ci], si, ci

    def _next_event(self, timeout: float) -> dict | None:
        try:
            ev = self._held.popleft() if self._held else self.events.get(timeout=timeout)
        except queue.Empty:
            return None
        if ev.get("type") == "error":
            self.log(f"   [board] {ev.get('msg')}")
            return None
        if ev.get("type") == "ptt_mode":
            self.ptt_mode = bool(ev.get("on"))
            self.log(f"   [ptt] hold-to-talk {'on' if self.ptt_mode else 'off'}")
            self.status("waiting" if self.ptt_mode else "playing",
                        "hold Space to talk" if self.ptt_mode else "listening")
            return None
        if ev.get("type") == "ptt":
            self.ptt_down = bool(ev.get("down"))
            if self.ptt_down:
                self.ptt_mode = True                  # pressing the key at all means he wants this mode
                if self.audio.playing:
                    self.audio.stop()                 # he's about to talk: she stops, like a raised hand
            else:
                self.ptt_up_t = time.time()
            return None
        if (ev.get("type") == "voice" and self.ptt_mode and not self.ptt_down
                and time.time() - self.ptt_up_t > PTT_TAIL_S):
            self.log(f"   (ignored, not holding the talk key: {(ev.get('text') or '')[:60]!r})")
            return None
        if ev.get("type") not in ACTIONABLE:
            return None
        if ev.get("type") in ("text", "voice") and not ev.get("_seen"):   # re-queued events were judged already
            ev["text"] = (ev.get("text") or "").strip()
            ev["_seen"] = True
            if ev["type"] == "voice" and self._since_q is not None and self._stale(ev, self._since_q):
                self.log(f"   (dropped, said before the question: {ev['text'][:60]!r})")
                return None                           # still in flight when she asked: never his answer
            if ev["type"] == "voice" and ev["text"]:
                keep, why = self.guard.check(ev["text"], at=ev.get("at"), no_speech=float(ev.get("no_speech") or 0),
                                             logprob=float(ev.get("logprob") or 0), barged=bool(ev.get("barged")))
                if not keep:                          # her own voice / a phantom / noise: never the learner
                    if why == "too short to interrupt":
                        self._frag = (time.time(), ev["text"])     # maybe the first word of a longer sentence
                    self.log(f"   (ignored, {why}: {ev['text']!r})")
                    return None
                ev["text"] = self._whole(ev["text"])
            if ev["type"] == "text" and ev["text"]:
                self.log(f"You: {ev['text']}")
            elif ev["type"] == "voice" and ev["text"]:
                self.log(f"You (voice): {ev['text']}")
        return ev

    def _whole(self, text: str) -> str:
        """Wait for his WHOLE sentence before acting on it (D52): she stops talking, shows what she's hearing, and
        joins every piece that follows within GATHER_IDLE_S. A lesson command ("wait", "skip") or a bare "hmm" acts
        at once, as before."""
        if self._frag and time.time() - self._frag[0] < FRAG_S:
            text = f"{self._frag[1].strip().rstrip('.')} {text}"      # "Tomorrow." + "I have an exam…"
        self._frag = None
        kind = commands.classify(text)
        if kind not in ("question", "steer", "answer", "other", "confused") or (kind == "other" and len(text.split()) < 3):
            return text
        if self.audio.playing:
            self.audio.stop()                         # he is talking: she stops and listens
        self.status("waiting", "listening…", caption=f"You: {text}")
        last, hard = time.time(), time.time() + GATHER_MAX_S * self.pace

        def idle() -> float:                          # "…so I want you to" isn't finished: give him longer
            return (GATHER_UNFINISHED_S if UNFINISHED_RX.search(text) else GATHER_IDLE_S) * self.pace
        while time.time() - last < idle() and time.time() < hard:
            try:
                nx = self.events.get(timeout=0.05)
            except queue.Empty:
                continue
            piece = (nx.get("text") or "").strip()
            if nx.get("type") == "voice" and self._since_q is not None and self._stale(nx, self._since_q):
                self.log(f"   (dropped, said before the question: {piece[:60]!r})")
                continue
            if nx.get("type") == "voice" and piece:
                keep, why = self.guard.check(piece, at=nx.get("at"), no_speech=float(nx.get("no_speech") or 0),
                                             logprob=float(nx.get("logprob") or 0), barged=True)
                if not keep:
                    self.log(f"   (ignored, {why}: {piece!r})")
                    continue
                text = f"{text} {piece}"
                last = time.time()
                self.status("waiting", "listening…", caption=f"You: {text}")
                continue
            self._held.append(nx)                     # a click / typed line while he talks: right after this
        return text

    @staticmethod
    def _kind(ev: dict, answering: bool = False) -> tuple[str, str]:
        t = ev.get("type")
        if t == "control":
            return {"play": "resume"}.get(ev.get("cmd"), ev.get("cmd") or "other"), ""
        if t == "hand":
            return "hand", ""
        if t == "click":
            return "click", ev.get("id") or ""
        text = ev.get("text") or ""
        return commands.classify(text, answering=answering) if text else "other", text

    # ------------------------------------------------------------ audio
    def _synth_future(self, k: int):
        key = (k, self.speed)
        if key not in self.futs:
            _, cue, _, _ = self._cue(k)
            self.futs[key] = self.pool.submit(self.audio.synth, cue.say, self.speed)
        return self.futs[key]

    def _prefetch(self, k: int, n: int = 3) -> None:
        for kk in range(k, min(k + n, len(self._flat()))):
            self._synth_future(kk)

    def _wait_audio(self, ms: int, *, ignore_backchannel: bool = False) -> dict | None:
        """Wait for the clip to end; return an actionable learner event that should interrupt it."""
        t0 = time.time()
        while True:
            ev = self._next_event(0.03)
            if ev is not None:
                kind, _ = self._kind(ev)
                if ignore_backchannel and ev["type"] == "voice" and kind in ("resume", "other") \
                        and not getattr(self.audio, "interrupted", False):
                    continue                          # "haan", "hmm" while she talks: just listening
                self.audio.stop()
                return ev
            if getattr(self.audio, "interrupted", False):   # learner talked over her (barge-in)
                ev = self._next_event(4.0)
                return ev or {"type": "voice", "text": ""}
            if time.time() - t0 > 0.12 and not self.audio.playing:
                break
        end = time.time() + 0.15
        while time.time() < end:
            ev = self._next_event(0.03)
            if ev is not None and not (ignore_backchannel and ev["type"] == "voice"
                                       and self._kind(ev)[0] in ("resume", "other")):
                return ev
        return None

    def _play(self, audio, ms: int, text: str) -> None:
        """The ONLY way sound starts: whatever is playing stops first (never two utterances at once), and the echo
        guard learns what she is saying so her own voice coming back through the mic is never 'him'."""
        if self.audio.playing:
            self.audio.stop()
        self.guard.spoke(text, ms)
        self.audio.play(audio, ms)

    def _pick(self, kind: str, options: list[str]) -> str:
        """Rotate wordings: never the same acknowledgement / bridge twice in a row."""
        i = self._pick_i.get(kind, 0)
        self._pick_i[kind] = i + 1
        return options[i % len(options)]

    def _gap(self, seconds: float) -> dict | None:
        """A teacher's pause (scaled by pace); returns a learner event if one arrives meanwhile."""
        end = time.time() + seconds * self.pace
        while time.time() < end:
            ev = self._next_event(min(0.05, max(0.005, end - time.time())))
            if ev is not None:
                kind, _ = self._kind(ev)
                if ev["type"] == "voice" and kind in ("resume", "other"):
                    continue                          # "haan" / "hmm" in a pause: just listening
                return ev
        return None

    def say(self, text: str, *, interruptible: bool = True, actions: list[dict] | None = None) -> dict | None:
        """Speak a non-lesson line (feedback, answers, prompts). Returns an interrupting event, if any."""
        self.log(f"Stiti: {text}")
        audio, ms = self.audio.synth(text, self.speed)
        if actions:
            self.send({"type": "actions", "actions": actions})
        self.send({"type": "status", "mode": "playing", "text": "talking", "caption": text})
        self._play(audio, ms, text)
        ev = self._wait_audio(ms)
        if ev is not None and not interruptible:
            self.events.put(ev)
            return None
        return ev

    # ------------------------------------------------------------ board
    def _apply(self, ops: list[Op], k: int, say: str = "", ms: int = 0) -> list[dict]:
        before = set(self.board.els)
        acts = []
        # D53 "it should look like real time": ops without their own word cue are spread across the sentence, so she
        # writes while she talks instead of everything popping in at 0 ms (a page title still comes first)
        loose = [i for i, op in enumerate(ops) if op.type != "new_page" and (op.at in (None, "", "start"))]
        for i, op in enumerate(ops):
            at = resolve_at(op.at, say, ms) if ms else 0
            if ms and i in loose:
                j = loose.index(i)
                at = int(ms * (0.08 + 0.8 * j / max(1, len(loose))))
            for a in self.board.apply(op):
                acts.append({**a, "at_ms": at + a.get("dt", 0)})
        for iid in set(self.board.els) - before:
            self.drawn_at.setdefault(iid, k)
        return acts

    # ------------------------------------------------------------ main loop
    def lesson_words(self) -> list[str]:
        """Short labels she will draw and say (segment titles, box / formula labels): what he'll say back to her."""
        words = [self.L.title] + [s.title for s in self.L.segments]
        for s in self.L.segments:
            for c in s.cues:
                for op in c.ops:
                    if op.type in ("box", "formula", "text", "bullet") and op.text and len(op.text.split()) <= 3:
                        words.append(op.text)
        return [w for w in words if w and not w.lower().startswith(("warm", "summary", "recap"))]

    @staticmethod
    def _stale(e: dict, since: float | None) -> bool:
        """Speech that STARTED before the question began (its `at` is the mic's monotonic start time). Speech that
        began while she was still asking — he answers over the end of her question — is his answer, not stale."""
        if e.get("type") not in ("voice", "text"):
            return False
        at = e.get("at")
        if since is not None and e.get("type") == "voice" and at is not None:
            try:
                return float(at) < since - STALE_GRACE_S
            except (TypeError, ValueError):
                return True
        return True                                    # typed / no start time: queued before the question

    def _drop_stale_speech(self, since: float | None = None) -> None:
        """2026-11-20: a garbled reply to the goal question was still queued and got graded as the answer to probe 1
        before he even heard it ('asking me the same questions again and again'). Voice/typed lines already waiting
        when a new question starts are dropped (controls — end, pause… — are kept), except speech that started at or
        after `since` (the question's start): that one is his answer and dropping it made her ask again."""
        keep = []
        while True:
            try:
                e = self.events.get_nowait()
            except queue.Empty:
                break
            if self._stale(e, since):
                self.log(f"   (dropped, said before the question: {(e.get('text') or '')[:60]!r})")
                continue
            keep.append(e)
        self._held = deque(e for e in self._held if not self._stale(e, since))
        for e in keep:
            self.events.put(e)

    def ears_on(self, words: list[str] | None = None) -> None:
        """D52: the big cloud ear + his lesson's words for Whisper. Called before ANY listening — the coach's opening
        questions too (2026-11-20: his goal answer was heard as 'Ipul yoru, abstracti…' by the local ear alone)."""
        try:
            from ..voice import glossary, stt
            glossary.set_session((words or []) + self.lesson_words())
            stt.prefer_cloud(hasattr(self.audio, "vl"))   # voice lessons only
        except Exception:
            pass

    def run(self) -> dict:
        self._persist_start()
        self.ears_on(getattr(self, "extra_words", None))
        try:
            while not self.ended:
                flat = self._flat()
                if self.k >= len(flat):
                    if not getattr(self.L, "complete", True) and self._wait_for_more():
                        continue
                    if (getattr(self.L, "complete", True) and self.before_end is not None and not self.ended
                            and self.before_end()):
                        continue                    # D53 coach: come back to what's still wrong, then the recap
                    break
                seg, cue, si, ci = self._cue(self.k)
                if seg.type == "summary" and ci == 0 and self.predict and not self._hook_done:
                    self._revisit_hook()
                ev = self._play_cue(self.k)
                if seg.type == "break" and not self.ended:  # day mode: a real break — wait for him to come back
                    if ev is None:
                        self._pause("Say continue when you're back.", brk=True)
                    elif self._kind(ev)[0] in ("resume", "next", "back"):
                        ev = None                     # "no, carry on" said over her: skip the break, don't replay it
                self.cue_open = ev is not None        # she was cut mid-sentence: a doubt now resumes THIS cue
                if ev is not None:
                    self._handle(ev)
                    continue
                if seg.type != "break":               # a whole sentence of teaching heard: pacing counts it
                    self.pacing.taught(sentences(cue.say))
                if ci == len(seg.cues) - 1 and seg.type == "blurt" and self.on_blurt is not None and not self.ended:
                    try:
                        self.on_blurt(seg)            # Feature 5: "tell me everything you remember" (the coach)
                    except Exception as e:
                        self.log(f"   [blurt] {type(e).__name__}: {e}")
                    self.pacing.asked()
                if ci == len(seg.cues) - 1 and seg.check is not None and self._ask_check(seg):
                    r = self._run_check(seg)
                    if r in ("moved", "end"):
                        continue
                self.k += 1
                if self.skip_to is not None:            # the coach saw he knows this concept: skip its other steps
                    self.k, self.skip_to = max(self.k, self.skip_to), None
                self._save_cursor()
                if ci == len(seg.cues) - 1 and not self.ended:      # end of a section: breathe, maybe check in
                    ev = self._section_end(seg)
                    if ev is not None:
                        self._handle(ev, mid_cue=False)
        except KeyboardInterrupt:
            self.ended = True
        finally:
            try:
                from ..voice import glossary, stt
                glossary.set_session(None)
                stt.prefer_cloud(False)
            except Exception:
                pass
        return self._finish()

    def _play_cue(self, k: int) -> dict | None:
        seg, cue, si, ci = self._cue(k)
        if k in self.snaps:                           # replay (repeat / back / after a question)
            self.board.restore(self.snaps[k])
            self.send({"type": "reset", "actions": list(self.board.log)})
        else:
            self.snaps[k] = self.board.snapshot()
        audio, ms = self._synth_future(k).result()
        acts = self._apply(cue.ops, k, cue.say, ms)
        self.send({"type": "cue", "seq": k, "cue_id": cue.id, "say": cue.say, "audio_ms": ms, "actions": acts,
                   "progress": f"{seg.title} · part {si + 1} of {len(self.L.segments)}", "lesson": self.L.title})
        self.status("playing", "teaching")
        self.log(f"Stiti: {cue.say}")
        self._prefetch(k + 1)
        self._play(audio, ms, cue.say)
        return self._wait_audio(ms, ignore_backchannel=True)     # "haan", "hmm" while she teaches = listening

    def _section_end(self, seg) -> dict | None:
        """A short pause between ideas; after a teaching section with no check of its own, at most every
        CHECKIN_MIN_GAP_S, one check-in ("Any doubt so far?") — never after every input."""
        ev = self._gap(SEGMENT_GAP_S)
        if ev is not None:
            return ev
        if (seg.check is None and seg.type in ("teach", "worked_example", "contrast", "apply")
                and time.time() - self.last_checkin >= CHECKIN_MIN_GAP_S * self.pace
                and self.k < len(self._flat())):
            self.last_checkin = time.time()
            self.checkins += 1
            ev = self.say(self._pick("checkin", CHECKINS))
            return ev or self._gap(CHECKIN_WAIT_S)
        return None

    def _handle(self, ev: dict, mid_cue: bool = True) -> None:
        kind, text = self._kind(ev)
        if kind in ("pause", "hand"):
            self._pause("Go ahead, I'm listening." if kind == "hand" else "Okay, paused. Say continue when you're ready.")
        elif kind in ("resume", "repeat", "other"):
            pass                                       # replay the current cue from its start
        elif kind == "back":
            self.k = max(0, self.k - 1)
        elif kind == "next":
            self._skip_segment()
        elif kind in ("slower", "faster"):
            self.speed = round(min(1.3, max(0.75, self.speed + (-0.1 if kind == "slower" else 0.1))), 2)
            self.futs.clear()
            self.send({"type": "speed", "value": self.speed})      # the dock shows "0.9×"
            self.say("Okay, slower." if kind == "slower" else "Okay, a bit faster.")
        elif kind == "end":
            self.ended = True
        elif kind == "confused":
            self._explain_again(mid_cue)
        elif kind in ("hindi", "english"):
            self.say("I'll keep it in English." if kind == "hindi" else "Okay, English it is.")
        elif kind == "fewer":                          # "skip the questions" / "just teach": sparser checks
            self.fewer_questions("asked")
        elif kind == "blurt":                          # "test me" / "let me blurt": free recall now
            if self.on_blurt_request is None or not self.on_blurt_request():
                self.say("Let's get a bit further first, then I'll test you.")
        elif kind == "click":
            self._explain_element(text)
        elif kind == "question":
            self._answer(text, resume_cue=mid_cue)
        elif kind == "steer":
            self._steer(text, mid_cue=mid_cue)
        elif kind == "correct":
            self._corrected(text, mid_cue)

    def listen(self, prompt: str | None = None, *, check_box: dict | None = None, timeout: float = 60.0,
               nudge: bool = True) -> str | None:
        """Ask him something outside the lesson script and wait for his whole answer (D53 coach opening).
        -> his text, "" when he stayed silent, None when he ended the lesson."""
        since = time.monotonic()                      # the question starts now (the mic stamps speech the same way)
        self._drop_stale_speech(since)                # words from before this question are not its answer
        self._since_q = since                         # … nor speech still in flight (_next_event / _whole drop it)
        try:
            ev = self.say(prompt) if prompt else None
        except BaseException:
            self._since_q = None
            raise
        if check_box:
            self.send({"type": "check", **check_box})
        self.status("waiting", "your turn — say or type your answer")
        t0, nudged = time.time(), not nudge
        try:
            while not self.ended:
                ev = ev or self._next_event(0.3)
                if ev is None:
                    waited = time.time() - t0
                    if waited > timeout * self.pace:
                        return ""
                    if not nudged and waited > timeout * self.pace / 2:
                        nudged = True
                        ev = self.say("Take your time. Or say I don't know.")
                    continue
                kind, text = self._kind(ev, answering=True)
                ev = None
                if kind == "end":
                    self.ended = True
                    return None
                if kind == "repeat" and prompt:
                    ev = self.say(prompt)
                    continue
                if text:
                    return text
        finally:
            self._since_q = None
            if check_box:
                self.send({"type": "check_done"})
        return None

    def more_words(self, idle_s: float = BLURT_MORE_S) -> str:
        """Free recall (Blurt) comes in bursts with thinking pauses: after his first burst, keep listening until he's
        quiet for idle_s. -> the extra words ("" when none). A control ("end", "pause"…) goes back to the queue."""
        out: list[str] = []
        last = time.time()
        while not self.ended and time.time() - last < idle_s * self.pace:
            ev = self._next_event(0.05)
            if ev is None:
                continue
            kind, text = self._kind(ev, answering=True)
            if ev.get("type") in ("voice", "text") and text and kind in ("answer", "other", "question", "confused"):
                out.append(text)
                last = time.time()
                continue
            self.events.put(ev)
            break
        return " ".join(out)

    def _corrected(self, text: str, mid_cue: bool = True) -> None:
        """'No, I said lexer': she heard him wrong. Drop what she was doing with the wrong words and take the right
        ones — and teach the ear the word (vocab.learn), so the next time it hears 'lexer' (D53)."""
        rest = commands.correction(text) or text
        prev = self.questions[-1] if self.questions else None
        self.log(f"   [heard wrong] now: {rest!r} (before: {prev!r})")
        try:
            from ..voice import vocab
            vocab.learn(text, prev)
        except Exception:
            pass
        self.audio.stop()
        kind = commands.classify(rest)
        if kind == "steer":
            self._steer(rest, mid_cue=mid_cue)
        else:
            self.say("Ah, sorry. Got it.", interruptible=False)
            self._answer(rest if kind == "question" or len(rest.split()) > 2 else f"What about {rest}?",
                         resume_cue=mid_cue)

    # ------------------------------------------------------------ he changes the plan (D52)
    def _units(self) -> tuple[str, list[str]]:
        """(file title, unit names) when the lesson comes from his book / notebook, else ("", [])."""
        src = self.L.source or {}
        if src.get("kind") != "book" or not src.get("path"):
            return "", []
        if not hasattr(self, "_units_cache"):
            try:
                from . import book
                b = book.load(src["path"])
                self._units_cache = (b.title, [s.name for s in (b.chapters() or b.sections)][:40])
            except Exception:
                self._units_cache = ("", [])
        return self._units_cache

    def _seg_start(self, si: int) -> int:
        return next((i for i, (s, _) in enumerate(self._flat()) if s == si), self.k)

    def _steer(self, text: str, mid_cue: bool = True) -> str:
        """He wants something else than the plan: "I know this", "start from unit 3", "exam tomorrow, cover it all".
        A teacher changes course — never "let's park this". -> answered | moved | switch | stay."""
        self.audio.stop()
        self.send({"type": "pause"})
        self.status("thinking", "thinking…", caption=f"You: {text}")
        si = self._flat()[min(self.k, len(self._flat()) - 1)][0]
        title, units = self._units()
        ctx = {"lesson": self.L.title, "segment": self.L.segments[si].title, "pos": si + 1,
               "parts": [s.title for s in self.L.segments], "book": title, "units": units}
        d = None
        if self.planner is not None and hasattr(self.planner, "steer"):
            fut = self.answer_pool.submit(self.planner.steer, text, ctx)
            try:
                d = fut.result(timeout=FILLER_AFTER_S * self.pace)
            except Exception:
                if not fut.done():
                    self.say("Okay, let me think about that.", interruptible=False)
                try:
                    d = fut.result(timeout=ANSWER_TIMEOUT_S * self.pace)
                except Exception as e:
                    self.log(f"   [planner] steer {type(e).__name__}: {str(e)[:120]}")
        if d is None:                                 # no cloud: the clear cases still work locally
            exam = re.search(r"\b(exams?|tests?|viva)\b", text, re.I)
            d = {"action": "crash" if exam else "answer", "part": None, "target": None, "say": ""}
        act = d["action"]
        self.log(f"   [steer] {act} part={d.get('part')} target={d.get('target')!r}")
        if act in ("skip_to", "restart"):
            p = 1 if act == "restart" else int(d.get("part") or 0)
            if 1 <= p <= len(self.L.segments):
                self.say(d.get("say") or STEER_LINES[act], interruptible=False)
                self.k = self._seg_start(p - 1)
                self.cue_open = False
                return "moved"
            act = "answer"
        if act in ("switch", "crash"):
            self.switch = {"mode": act, "target": d.get("target"), "say": d.get("say") or STEER_LINES[act],
                           "request": text}
            self.say(self.switch["say"], interruptible=False)
            self.ended = True
            return "switch"
        self._answer(text, resume_cue=mid_cue)
        return "answered"

    def _skip_segment(self) -> None:
        flat = self._flat()
        si = flat[min(self.k, len(flat) - 1)][0]
        nxt = next((i for i, (s, _) in enumerate(flat) if s > si), len(flat))
        self.k = nxt

    def _pause(self, line: str, *, brk: bool = False) -> None:
        """Wait for "continue". brk=True (a day-mode break): no nudge before the break is over, and "back" /
        "I'm back" / "next" end the break instead of replaying the previous step."""
        self.audio.stop()
        self.send({"type": "pause"})
        self.status("paused", "paused")
        ev = self.say(line, interruptible=True)
        self.status("paused", "paused — say continue")
        since, nudged = time.time(), False
        while not self.ended:
            ev = ev or self._next_event(0.5 if self.pace >= 1 else 0.05)
            if ev is None:
                if not nudged and time.time() - since > (BREAK_NUDGE_S if brk else LONG_PAUSE_S) * self.pace:
                    nudged = True
                    ev = self.say("Break's over whenever you're ready. Say continue." if brk
                                  else "Whenever you're ready, say continue. Or ask me anything.")
                continue
            kind, text = self._kind(ev)
            ev = None
            if kind in ("resume", "repeat") or (brk and kind in ("back", "next")):
                return
            if kind in ("pause", "hand", "other"):
                continue
            self._handle({"type": "text", "text": text} if text else {"type": "control", "cmd": kind})
            return

    def _wait_for_more(self) -> bool:
        """Lazy (LLM) lessons: the next segment is still being written."""
        self.say("One second, I'm preparing the next part.")
        n = len(self._flat())
        for i in range(1600):                         # ≤4 min: free-tier rate limits can make the writer wait
            if len(self._flat()) > n or getattr(self.L, "complete", True):
                return len(self._flat()) > n
            if i and i % 300 == 0:
                self.say(["Almost ready.", "Just a moment more, writing the next part.", "Nearly there."][i // 300 % 3])
            ev = self._next_event(0.15)
            if ev is not None and self._kind(ev)[0] == "end":
                self.ended = True
                return False
        return False

    # ------------------------------------------------------------ questions
    def _context(self) -> dict:
        seg, cue, si, ci = self._cue(min(self.k, len(self._flat()) - 1))
        flat = self._flat()
        said = [self._cue(kk)[1].say for kk in range(max(0, self.k - 3), self.k + 1)]
        return {"lesson": self.L.title, "topic": self.L.topic, "segment": seg.title, "last_said": said,
                "board": self.board.summary(), "source": self.L.source, "position": f"{self.k + 1}/{len(flat)}"}

    def _local_lookup(self, question: str, k: int = 2) -> list[str]:
        """No cloud brain? Find what the lesson itself said that matches (local embedder, ~10 ms)."""
        try:
            from .. import embed
            says = [c.say for s in self.L.segments for c in s.cues]
            if self._cue_vecs is None:
                self._cue_vecs = embed._embed(says)
            qv = embed._embed([question])[0]
            sims = self._cue_vecs @ qv
            order = sims.argsort()[::-1][:k]
            return [says[i] for i in order if sims[i] >= 0.45]
        except Exception:
            return []

    def _answer(self, question: str, *, resume_cue: bool = True, simpler: bool = False,
                title: str | None = None, answering: bool = False) -> None:
        """A doubt, like a teacher: stop → "Good question —" → answer on a doubt board while drawing → follow-ups →
        "Back to where we were —" → the interrupted cue replays (resume_cue) with the doubt board kept."""
        resume_cue = resume_cue and self.cue_open     # a doubt during a check / pause doesn't replay a finished cue
        self.audio.stop()
        self.send({"type": "pause"})
        if resume_cue and self.k in self.snaps:       # the cue's drawing redraws on replay; the doubt board stays
            self.board.restore(self.snaps[self.k])
        self.status("thinking", "thinking…")
        self.send({"type": "actions", "actions": [{**a, "at_ms": 0} for a in self.board.begin_aside(title or question)]})
        first = True
        while not self.ended:
            self.questions.append(question)
            lead = self._pick("simpler", SIMPLER) if simpler else (self._pick("ack", ACKS) if first else None)
            if simpler and not first:
                self.send({"type": "actions", "actions": self._apply([Op(type="text", text="Simpler:", style="violet")],
                                                                     self.k)})
            ans = self._fetch_answer(question, lead, simpler)
            if self.ended:
                break
            lines = self._play_answer(ans) if ans and ans.get("say") else self._offline_answer(question)
            self.last_doubt = {"q": question, "a": lines, "t": time.time()}
            if ans and ans.get("stuck_at"):
                self.log(f"   [doubt] stuck at: {ans['stuck_at']} ({ans.get('error_type')})")
            first = False
            if ans and not answering and not self.ended:
                self._doubt_check(ans.get("check"))
            nxt = self._await_followup(question, answering)
            if nxt is None:
                break
            question, simpler = nxt
        self.send({"type": "actions", "actions": [{**a, "at_ms": 0} for a in self.board.end_aside()]
                   + [{**a, "at_ms": 300} for a in self.board.note_doubt(title or question)]})
        if resume_cue:
            self.snaps[self.k] = self.board.snapshot()   # replay restores THIS (lesson board + doubt board below)
        if not self.ended:
            ev = self.say(self._pick("bridge", BRIDGES)) if resume_cue else None
            if ev is not None:
                self.events.put(ev)

    def _fetch_answer(self, question: str, lead: str | None, simpler: bool) -> dict | None:
        """Ask the cloud in the background while she acknowledges; a filler only if it's slow; "ruko"/"bas karo"
        still work while she waits. -> the answer dict, or None (no LLM / down / too slow)."""
        fut = None
        if self.planner is not None:
            ctx = self._context()
            if self.last_doubt and time.time() - self.last_doubt["t"] < FOLLOWUP_S:
                ctx["previous"] = {"q": self.last_doubt["q"], "a": self.last_doubt["a"]}
            ctx["simpler"] = simpler
            fut = self.answer_pool.submit(self.planner.answer, question, ctx)
        t0 = time.time()
        if lead:
            a, ms = self.audio.synth(lead, self.speed)
            self.log(f"Stiti: {lead}")
            self.send({"type": "status", "mode": "playing", "text": "thinking", "caption": lead})
            self._play(a, ms, lead)
        if fut is None:
            while self.audio.playing:
                time.sleep(0.02)
            return None
        filler, stash = False, []
        while not fut.done() and time.time() - t0 < ANSWER_TIMEOUT_S:
            ev = self._next_event(0.03)
            if ev is not None:
                kind, _ = self._kind(ev)
                if kind == "end":
                    self.ended = True
                    return None
                if kind in ("pause", "hand"):
                    self.audio.stop()
                    continue                          # he wants quiet: no filler, the answer still comes
                if kind not in ("resume", "other"):
                    stash.append(ev)                  # a second doubt while she thinks: after this one
                continue
            if not filler and not self.audio.playing and time.time() - t0 >= FILLER_AFTER_S * self.pace:
                filler = True
                line = self._pick("filler", FILLERS)
                a, ms = self.audio.synth(line, self.speed)
                self.log(f"Stiti: {line}")
                self._play(a, ms, line)
        while self.audio.playing:                     # let the acknowledgement / filler finish its sentence
            ev = self._next_event(0.03)
            if ev is not None and self._kind(ev)[0] == "end":
                self.ended = True
                return None
            if ev is not None and self._kind(ev)[0] not in ("resume", "other", "pause", "hand"):
                stash.append(ev)
        for ev in stash:
            self.events.put(ev)
        try:
            return fut.result(timeout=0) if fut.done() else None
        except Exception as e:                        # NoProvider / rate limit / bad JSON → honest local answer
            self.log(f"   [planner] {type(e).__name__}: {str(e)[:120]}")
            return None

    def _offline_answer(self, question: str) -> list[str]:
        """No cloud answer: be honest ONCE, give what the lesson itself said about it, park the doubt."""
        hits = self._local_lookup(question)
        self.send({"type": "actions", "actions": [{**a, "at_ms": 0} for a in self.board.park(question)]})
        said: list[str] = []
        if hits:
            ops = [Op(type="text", text=h[:120], style="violet") for h in hits[:2]]
            lead = OFFLINE_FIRST if not self._offline_said else "From this lesson:"
            self.say(lead, actions=self._apply(ops, self.k))
            said.append(lead)
            for h in hits[:2]:
                self.say(h)
                said.append(h)
        else:
            line = OFFLINE_PARK_FIRST if not self._offline_said else OFFLINE_AGAIN
            self.say(line)
            said.append(line)
        self._offline_said = True
        return said

    def _await_followup(self, question: str, answering: bool = False) -> tuple[str, bool] | None:
        """Right after an answer: a follow-up doubt or "still didn't get it" → (question, simpler); else None.
        In a check (`answering`), a plain sentence is his answer to the check, not another doubt."""
        end = time.time() + RESUME_GAP_S * self.pace
        while not self.ended and time.time() < end:
            ev = self._next_event(0.03)
            if ev is None:
                continue
            kind, text = self._kind(ev, answering=answering)
            if kind == "question":
                return text, False
            if kind == "correct":                     # "no, I asked about X": answer X instead
                self.log(f"   [heard wrong] now: {commands.correction(text)!r}")
                return commands.correction(text) or text, False
            if kind == "confused":
                return f"I still didn't get this: {question}", True
            if kind == "answer":
                self.events.put(ev)                   # the check loop grades it
                return None
            if kind == "end":
                self.ended = True
                return None
            if kind in ("pause", "hand"):
                self._pause("Okay. Say continue when you're ready.")
                return None
            if kind in ("resume", "other"):
                return None                           # "okay", "got it": straight back to the lesson
            self.events.put(ev)                       # back / skip / slower …: the lesson loop handles it
            return None
        return None

    def _doubt_check(self, chk: dict | None) -> None:
        """D53: after a doubt, one short question shows whether the gap is really closed (not 'did you get it?')."""
        if not chk or not chk.get("prompt") or self.pacing.repeat(chk["prompt"]):   # never the same question twice
            return
        self.pacing.answered(chk["prompt"], False)
        reply = self.listen(chk["prompt"], timeout=25)
        if not reply:
            return
        if commands.classify(reply, answering=True) in ("question", "steer", "confused"):
            self.events.put({"type": "text", "text": reply, "_seen": True})   # another doubt: the follow-up takes it
            return
        g = grade.grade(Check(kind="recall", prompt=chk["prompt"], expectations=[chk.get("expected") or ""]), reply,
                        llm=grade.llm_for(self.planner))
        self._log_grade(g)
        if g["verdict"] == "correct":
            self.say("Yes, exactly.", interruptible=False)
        elif g["verdict"] == "partial":
            self.say(f"Nearly. The key part: {chk.get('expected')}.", interruptible=False)
        else:
            self.say(f"Not quite. It's {chk.get('expected')}.", interruptible=False)

    def _play_answer(self, ans: dict) -> list[str]:
        """Say the answer sentence by sentence; each sentence draws its own ops while it is said."""
        lines = [s for s in ans.get("say") or [] if s][:4]
        if lines:
            lines[0] = _ACK_RX.sub("", lines[0]).strip() or lines[0]   # she already said "Good question"
            lines[0] = lines[0][:1].upper() + lines[0][1:]
        ops = ans.get("ops") or []
        buckets: list[list[Op]] = [[] for _ in lines]
        for op in ops:
            i = next((j for j, s in enumerate(lines) if op.at and op.at.lower() in s.lower()), 0)
            buckets[i].append(op)
        said = []
        for line, b in zip(lines, buckets):
            audio, ms = self.audio.synth(line, self.speed)
            acts = self._apply(b, self.k, line, ms)
            self.log(f"Stiti: {line}")
            self.send({"type": "actions", "actions": acts})
            self.send({"type": "status", "mode": "playing", "text": "answering", "caption": line})
            self._play(audio, ms, line)
            said.append(line)
            ev = self._wait_audio(ms, ignore_backchannel=True)
            if ev is not None:
                kind, _ = self._kind(ev)
                if kind in ("pause", "hand"):
                    self._pause("Okay, paused. Say continue when you're ready.")
                    continue
                self.events.put(ev)                   # a follow-up / control: handled right after
                break
        return said

    def _explain_element(self, iid: str) -> None:
        e = self.board.els.get(iid)
        label = getattr(e, "label", "") if e else ""
        if self.planner is not None and label:
            return self._answer(f"Explain '{label}' again, more simply.", title=label)
        k = self.drawn_at.get(iid)
        if k is None:
            return
        self.say(f"Sure. Let me go over {label or 'that'} again." if label else "Sure, let me go over that again.")
        self.k = k

    def _explain_again(self, mid_cue: bool = True) -> None:
        """'samajh nahi aaya': about her last doubt answer if that was just now, else about what she just said."""
        if self.last_doubt and time.time() - self.last_doubt["t"] < FOLLOWUP_S and self.planner is not None:
            return self._answer(f"I still didn't get this: {self.last_doubt['q']}", resume_cue=mid_cue, simpler=True,
                                title="Simpler: " + self.last_doubt["q"])
        _, cue, _, _ = self._cue(min(self.k, len(self._flat()) - 1))
        if self.planner is not None:
            return self._answer(f"I didn't understand this: '{cue.say}'. Explain it differently, with a simpler "
                                "example.", resume_cue=mid_cue, simpler=True, title="Another way")
        self.speed = max(0.8, round(self.speed - 0.1, 2))
        self.futs.clear()
        self.say("No problem. Let me say that again, a little slower.")
        self.k = max(0, self.k - 1)

    # ------------------------------------------------------------ checks
    def _check_prompt(self, c: Check) -> str:
        if c.options:
            opts = "; ".join(f"{'ABCD'[i]}, {o['text']}" for i, o in enumerate(c.options))
            return f"{c.prompt} Is it {opts}?"
        return c.prompt

    def _ask_check(self, seg) -> bool:
        """Feature 5: ask this check now? Never a question already asked this session (or answered right in the last
        few days); the coach's should_check decides the spacing (one check per full idea, sparser when he's fed up)."""
        c = seg.check
        if self.pacing.repeat(c.prompt):
            self.log(f"   [pacing] skipped a repeated question: {c.prompt[:60]!r}")
            return False
        if self.should_check is not None and not self.should_check(seg, self.pacing):
            self.log(f"   [pacing] no check yet ({self.pacing.since} sentences since the last one, gap "
                     f"{self.pacing.gap}): {c.prompt[:50]!r}")
            return False
        return True

    def fewer_questions(self, why: str) -> None:
        """'skip the questions' / curt answers: checks get sparser for the rest of the session — said ONCE."""
        if self.pacing.go_sparse(why):
            self.log(f"   [pacing] fewer questions from now on ({why})")
            self.say("Okay, fewer questions.", interruptible=False)

    # ---- the hint ladder (iTutor; code-owned, LLM-free): nudge → hint → worked example → answer
    def _rung_available(self, rung: int, c: Check) -> bool:
        if rung == 2:
            return bool(c.hints)
        if rung == 3:
            return bool(c.example or (c.options and len(c.options) > 2) or (c.reveal or "").split())
        return True

    def _next_rung(self, rung: int, verdict: str, c: Check) -> int:
        nxt = rung + 1
        if rung == 0 and verdict == "idk":
            nxt = 2                                    # "What else?" after "I don't know" is a pump into nothing
        while nxt in (2, 3) and not self._rung_available(nxt, c):
            nxt += 1
        if self.pacing.sparse and rung >= 1:
            nxt = 4                                    # he wants fewer questions: one help, then the answer
        return min(nxt, 4)

    @staticmethod
    def _nudge(c: Check, g: dict, verdict: str) -> str:
        """Rung 1: a pump, pointed at what's missing (fair grading's missing_text) without giving it away."""
        if c.options:
            return "Not that one. Have another look at the options."
        if verdict == "partial":
            exps = c.expectations or []
            missing = g.get("missing_text") or []
            got = [e for i, e in enumerate(exps) if i not in (g.get("missing") or [])]
            line = "Good start, you've got part of it."
            if got and len(exps) > 1:
                line += f" Yes, {got[0].split(' or ')[0]}."
            if any(re.search(r"\d", m) for m in missing):
                line += " There's a number still missing."
            elif len(missing) > 1:
                line += f" {len(missing)} more pieces."
            return line + " What else?"
        if verdict == "idk":
            return "No worries. Take a guess, what comes to mind first?"
        return "Not quite. Think about what I just showed you. Try once more?"

    @staticmethod
    def _worked_step(c: Check) -> str:
        """Rung 3: ONE short worked step, no LLM — the step's example line, an MCQ elimination, or the start of the
        answer."""
        if c.example:
            return f"Let me show you one step: {c.example[0].rstrip('.')}. Now you try."
        if c.options and len(c.options) > 2:
            wrong = next(o["text"] for o in c.options if not o.get("correct"))
            return f"Here's a step: it's not {wrong}. So which one is it?"
        words = (c.reveal or "").rstrip(".").split()
        if len(words) >= 4:
            return f"Here's how it starts: {' '.join(words[:len(words) // 2])}… Finish it."
        return f"Here's a start: it begins with '{words[0][0]}'. What is it?" if words else "Have one more go."

    def _run_check(self, seg) -> str:
        c = seg.check
        label = {"predict": "Quick guess", "mcq": "Pick one", "recall": "From memory", "explain_why": "Explain why",
                 "apply": "Apply it", "discriminate": "Which one?", "explain_back": "Teach it back"}.get(c.kind, "Your turn")
        self.send({"type": "check", "kind_label": label, "prompt": c.prompt,
                   "options": [o["text"] for o in c.options] if c.options else []})
        rec = {"segment": seg.id, "kind": c.kind, "verdict": None, "attempts": 0, "hints": 0, "confidence": None,
               "answers": [], "rung": 0, "ladder": []}
        self.pacing.asked(c.prompt)
        ev = self.say(self._check_prompt(c))
        self.status("waiting", "your turn — say or type your answer")
        nudged = False
        t0 = time.time()
        outcome = "done"
        tipped = False                                 # his answers just showed he's fed up with questions
        while not self.ended:
            if ev is None:
                ev = self._next_event(0.3)
            if ev is None:
                waited = time.time() - t0
                if waited > 30 and not nudged:
                    nudged = True
                    ev = self.say("Take your time. Or say 'I don't know', and I'll give you a hint.")
                    t0 = time.time() - 30
                elif waited > self.check_timeout_s:
                    ev = {"type": "text", "text": "pata nahi", "_timeout": True}
                continue
            emotion, silent = ev.get("emotion"), bool(ev.get("_timeout"))
            kind, text = self._kind(ev, answering=True)
            ev = None
            if kind == "other" and not text:
                continue
            if kind == "repeat":
                ev = self.say(self._check_prompt(c))
                continue
            if kind == "hand":
                continue                              # he's about to type his answer: that IS the turn he's taking
            if kind == "pause":
                self._pause("Sure, take a moment. Say continue when you want me to ask again.")
                ev = self.say(self._check_prompt(c))
                continue
            if kind == "end":
                self.ended, outcome = True, "end"
                break
            if kind == "back":
                self.k = max(0, self.k - 1)
                outcome = "moved"
                break
            if kind == "next":
                rec["verdict"] = "skipped"
                if c.reveal and c.kind != "predict":
                    self.say("Okay. Quickly, the answer: " + c.reveal)
                break
            if kind in ("slower", "faster"):
                self._handle({"type": "control", "cmd": kind})
                continue
            if kind == "correct":                     # "no, I said FIRST sets": grade what he really said
                text = commands.correction(text) or text
                self.log(f"   [heard wrong] his answer: {text!r}")
                kind = "answer"
            if kind == "steer":                       # "I don't need the basics" is a request, not his guess (D52)
                r = self._steer(text, mid_cue=False)
                if r in ("moved", "switch"):
                    rec["verdict"] = "skipped"
                    outcome = "end" if r == "switch" else "moved"
                    break
                ev = self.say(self._check_prompt(c))
                continue
            if kind in ("question", "click"):
                self._answer(text, resume_cue=False, answering=True) if kind == "question" \
                    else self._explain_element(text)
                ev = self.say(self._check_prompt(c))
                continue
            if kind == "fewer":                       # "skip the questions": the answer, and fewer from now on
                rec["verdict"] = "skipped"
                self.fewer_questions("asked")
                if c.reveal and c.kind != "predict":
                    self.say("The answer: " + c.reveal)
                break
            if kind == "blurt":                       # "test me" in the middle of a check: the check comes first
                ev = self.say("Sure, right after this one. " + self._check_prompt(c))
                continue
            if kind == "confused":
                text = "pata nahi"
            # ---- it's an answer
            rec["attempts"] += 1
            rec["answers"].append(text[:200])
            g = grade.grade(c, text, llm=grade.llm_for(self.planner))   # wrong/partial → free-LLM second opinion
            self._log_grade(g)
            v = g["verdict"]
            if (v != "predict" and not silent and self.pacing.note(text, v, emotion)
                    and self.pacing.go_sparse("curt answers")):
                tipped = True                          # the ladder shortens right away; she says so after this check
                self.log("   [pacing] fewer questions from now on (curt answers)")
            if v == "predict":
                self.predict = (c, text)
                rec["verdict"] = "predict"
                self.say(c.reveal or "Hold that thought. We'll come back to your guess at the end.")
                break
            if v == "correct":
                rec["verdict"] = "correct"
                self.say(c.on_correct or PRAISE)
                break
            nxt = self._next_rung(rec["rung"], v, c)
            rec["rung"] = nxt
            rec["ladder"].append(RUNGS[nxt])
            if nxt == 1:
                ev = self.say(self._nudge(c, g, v))
            elif nxt == 2:
                opener = {"partial": "Close.", "wrong": "Not quite.", "idk": "No worries."}[v]
                ev = self.say(f"{opener} Hint: {c.hints[0]}")
            elif nxt == 3:
                ev = self.say(self._worked_step(c))
            if nxt < 4:
                rec["hints"] += 1                      # help given (srs: any help → Hard)
                t0 = time.time()                       # his turn again: the wait (and its nudge) starts over
                self.status("waiting", "your turn — say or type your answer")
                continue
            rec["verdict"] = "partial" if v == "partial" else "wrong"
            self.say(("Close. " if v == "partial" else "Here's the answer. ") + (c.reveal or "Let's look at it together."))
            break
        if c.confidence and rec["verdict"] in ("correct", "partial", "wrong") and not self.ended:
            ev = self.say("Quick one: how sure were you, from 1 to 5?")
            for _ in range(int(20 / 0.3)):
                ev = ev or self._next_event(0.3)
                if ev is not None and ev.get("text"):
                    rec["confidence"] = grade.parse_confidence(ev["text"])
                    break
                ev = None
            if rec["confidence"] and rec["confidence"] >= 4 and rec["verdict"] != "correct":
                self.say("A confident miss. Those are the best ones to learn from, so this card goes to the top of your revision.")
        if rec["verdict"] in ("correct", "partial", "wrong"):
            rec["rating"] = rung_rating(rec["verdict"], rec["rung"], rec["confidence"])
            self.pacing.answered(c.prompt, rec["verdict"] == "correct" and rec["rung"] == 0)
            self.log(f"   [ladder] {rec['verdict']} at rung {RUNGS[rec['rung']]} → {rec['rating']}")
        if tipped and not self.ended:
            self.say("Okay, fewer questions.", interruptible=False)
        self.results.append(rec)
        self.send({"type": "check_done"})
        if self.on_check is not None:
            try:
                self.on_check(seg, rec)
            except Exception as e:
                self.log(f"   [coach] on_check {type(e).__name__}: {e}")
        return outcome

    def _log_grade(self, g: dict) -> None:
        if g.get("llm_error"):
            self.log(f"   [grade] second opinion failed ({g['llm_error']}): keeping local {g['verdict']}")
        elif g.get("source") == "llm":
            self.log(f"   [grade] second opinion: {g['local_verdict']} → {g['verdict']} ({g['llm_ms']:.0f} ms) {g['reason']}")

    def _revisit_hook(self) -> None:
        self._hook_done = True
        c, ans = self.predict
        truth = c.expectations[0] if c.expectations else ""
        if not truth:
            return
        g = grade.grade(Check(kind="recall", prompt=c.prompt, expectations=[truth]), ans)
        self.say(f"Remember your guess at the start? You said: {ans}. "
                 + ("You were right!" if g["verdict"] == "correct" else f"Turns out, it {truth}."))

    # ------------------------------------------------------------ persistence
    def _persist_start(self) -> None:
        if not self.persist:
            return
        try:
            from . import store
            self.lesson_id = store.save_lesson(self.L)
            self.session_id = store.start_session(self.lesson_id, self.k)
        except Exception as e:
            self.log(f"   [store] not saving this lesson: {type(e).__name__}: {e}")
            self.persist = False

    def _save_cursor(self) -> None:
        if self.persist and self.session_id:
            try:
                from . import store
                store.update_session(self.session_id, cursor=self.k, results=self.results, questions=self.questions)
            except Exception:
                pass

    def _finish(self) -> dict:
        finished = self.k >= len(self._flat())
        self.audio.stop()
        self.send({"type": "end"})
        self.status("done", "lesson finished" if finished else "stopped — resume any time")
        if not finished:
            self.say("Okay, we'll stop here. Next time, say: continue my lesson, and I'll pick up right here.",
                     interruptible=False)
        cards = 0
        if self.persist and self.session_id:
            try:
                from . import store
                store.update_session(self.session_id, cursor=self.k, results=self.results,
                                     questions=self.questions, finished=finished, ended=True)
                if finished:
                    cards = store.save_cards(self.lesson_id, self.L.cards)
                if self.L.source.get("kind") != "course":      # course glue (map, quiz, break) isn't a memory
                    store.remember(self.L, self.results, self.questions, finished)
            except Exception as e:
                self.log(f"   [store] {type(e).__name__}: {e}")
        self.pool.shutdown(wait=False, cancel_futures=True)
        self.answer_pool.shutdown(wait=False, cancel_futures=True)
        right = sum(r["verdict"] == "correct" for r in self.results)
        graded = sum(r["verdict"] not in ("predict", None) for r in self.results)
        return {"finished": finished, "cursor": self.k, "checks_right": right, "checks_graded": graded,
                "questions": len(self.questions), "cards_saved": cards, "results": self.results}
