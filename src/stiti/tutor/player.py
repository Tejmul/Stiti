"""Tutor orchestrator: plays a lesson cue by cue, keeps board + voice in sync, and handles the learner.

Design (research §5 + pedagogy §7; OpenMAIC action engine, ChalkTalk hand-raise):
- One cue = one spoken sentence + its board ops. Audio is synthesised 3 cues ahead, so each cue's
  exact length is known and its ops are scheduled at real offsets (`at` word → proportional time).
- Every cue boundary keeps a board snapshot → repeat / back / resume-after-question redraw exactly.
- Code owns time, resume and repairs; content (LLM or hand-written) only fills slots.
- Voice-first: everything works by talking (board optional, MCQ options are read out loud).
- Checks are graded locally (grade.py). Hints ≤ 2, then a kind reveal. Never "samjha?".
- Questions: answered on a side board (cloud LLM if a free key exists, else from the lesson itself),
  then "shall we continue?" and a bridge back to where we were.
"""
from __future__ import annotations

import queue
import time
from concurrent.futures import ThreadPoolExecutor

from . import commands, grade
from .lesson import Check, Lesson, Op, resolve_at
from .skills import Board

PRAISE = "Yes, exactly right."
ACTIONABLE = {"control", "text", "voice", "click", "hand"}


class Tutor:
    def __init__(self, lesson: Lesson, *, audio, events: queue.Queue, server=None, planner=None,
                 persist: bool = True, start: int = 0, log=print, idle_resume_s: float = 25,
                 check_timeout_s: float = 90):
        self.L, self.audio, self.events, self.srv, self.planner = lesson, audio, events, server, planner
        self.persist, self.log = persist, log
        self.idle_resume_s, self.check_timeout_s = idle_resume_s, check_timeout_s
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
            ev = self.events.get(timeout=timeout)
        except queue.Empty:
            return None
        if ev.get("type") == "error":
            self.log(f"   [board] {ev.get('msg')}")
            return None
        if ev.get("type") not in ACTIONABLE:
            return None
        if ev.get("type") in ("text", "voice"):
            ev["text"] = (ev.get("text") or "").strip()
            if ev["type"] == "text" and ev["text"]:
                self.log(f"You: {ev['text']}")
            elif ev["type"] == "voice" and ev["text"]:
                self.log(f"You (voice): {ev['text']}")
        return ev

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

    def say(self, text: str, *, interruptible: bool = True, actions: list[dict] | None = None) -> dict | None:
        """Speak a non-lesson line (feedback, answers, prompts). Returns an interrupting event, if any."""
        self.log(f"Stiti: {text}")
        audio, ms = self.audio.synth(text, self.speed)
        if actions:
            self.send({"type": "actions", "actions": actions})
        self.send({"type": "status", "mode": "playing", "text": "talking", "caption": text})
        self.audio.play(audio, ms)
        ev = self._wait_audio(ms)
        if ev is not None and not interruptible:
            self.events.put(ev)
            return None
        return ev

    # ------------------------------------------------------------ board
    def _apply(self, ops: list[Op], k: int, say: str = "", ms: int = 0) -> list[dict]:
        before = set(self.board.els)
        acts = []
        for op in ops:
            at = resolve_at(op.at, say, ms) if ms else 0
            for a in self.board.apply(op):
                acts.append({**a, "at_ms": at + a.get("dt", 0)})
        for iid in set(self.board.els) - before:
            self.drawn_at.setdefault(iid, k)
        return acts

    # ------------------------------------------------------------ main loop
    def run(self) -> dict:
        self._persist_start()
        try:
            while not self.ended:
                flat = self._flat()
                if self.k >= len(flat):
                    if getattr(self.L, "complete", True) or not self._wait_for_more():
                        break
                    continue
                seg, cue, si, ci = self._cue(self.k)
                if seg.type == "summary" and ci == 0 and self.predict and not self._hook_done:
                    self._revisit_hook()
                ev = self._play_cue(self.k)
                if ev is not None:
                    self._handle(ev)
                    continue
                if ci == len(seg.cues) - 1 and seg.check is not None:
                    r = self._run_check(seg)
                    if r in ("moved", "end"):
                        continue
                self.k += 1
                self._save_cursor()
        except KeyboardInterrupt:
            self.ended = True
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
                   "progress": f"{seg.title} · part {si + 1} of {len(self.L.segments)}"})
        self.status("playing", "teaching")
        self.log(f"Stiti: {cue.say}")
        self._prefetch(k + 1)
        self.audio.play(audio, ms)
        return self._wait_audio(ms, ignore_backchannel=True)     # "haan", "hmm" while she teaches = listening

    def _handle(self, ev: dict) -> None:
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
            self.say("Okay, slower." if kind == "slower" else "Okay, a bit faster.")
        elif kind == "end":
            self.ended = True
        elif kind == "confused":
            self._explain_again()
        elif kind in ("hindi", "english"):
            self.say("Okay. The prepared lesson is in English, but ask me anything in Hinglish, and I'll answer that way."
                     if kind == "hindi" else "Okay, English it is.")
        elif kind == "click":
            self._explain_element(text)
        elif kind == "question":
            self._answer(text)

    def _skip_segment(self) -> None:
        flat = self._flat()
        si = flat[min(self.k, len(flat) - 1)][0]
        nxt = next((i for i, (s, _) in enumerate(flat) if s > si), len(flat))
        self.k = nxt

    def _pause(self, line: str) -> None:
        self.audio.stop()
        self.send({"type": "pause"})
        self.status("paused", "paused")
        ev = self.say(line, interruptible=True)
        self.status("paused", "paused — say continue")
        while not self.ended:
            ev = ev or self._next_event(0.5)
            if ev is None:
                continue
            kind, text = self._kind(ev)
            ev = None
            if kind in ("resume", "repeat"):
                return
            if kind in ("pause", "hand", "other"):
                continue
            self._handle({"type": "text", "text": text} if text else {"type": "control", "cmd": kind})
            return

    def _wait_resume(self) -> None:
        """After an answer: wait for 'continue' (or a follow-up question). Auto-continue after a while."""
        self.status("waiting", "say continue — or ask another question")
        deadline = time.time() + self.idle_resume_s
        while not self.ended and time.time() < deadline:
            ev = self._next_event(0.3)
            if ev is None:
                continue
            kind, text = self._kind(ev)
            if kind in ("resume", "repeat"):
                return
            if kind == "other":
                continue
            if kind in ("question", "click", "confused"):
                self._handle(ev)
                return
            self._handle(ev)
            return
        if not self.ended:
            self.say("Chalo, let's keep going.")

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

    def _answer(self, question: str) -> None:
        self.questions.append(question)
        self.audio.stop()
        self.send({"type": "pause"})
        self.status("thinking", "thinking…")
        self.send({"type": "actions", "actions": [{**a, "at_ms": 0} for a in self.board.begin_aside(question)]})
        ans = None
        if self.planner is not None:
            fa, fms = self.audio.synth("Good question. Let me think.", self.speed)
            self.audio.play(fa, fms)                  # talks while the cloud LLM works (no dead air)
            try:
                ans = self.planner.answer(question, self._context())
            except Exception as e:                    # NoProvider / rate limit / bad JSON → local answer
                self.log(f"   [planner] {type(e).__name__}: {str(e)[:120]}")
            while self.audio.playing:
                time.sleep(0.03)
        if ans and ans.get("say"):
            self._play_answer(ans)
        else:
            hits = self._local_lookup(question)
            if hits:
                ops = [Op(type="text", text=h[:120], style="violet") for h in hits]
                self.say("My cloud brain isn't connected right now, so here's what I said about that earlier.",
                         actions=self._apply(ops, self.k))
                for h in hits:
                    self.say(h)
            else:
                self.send({"type": "actions", "actions": [{**a, "at_ms": 0} for a in self.board.park(question)]})
                self.say("I can't answer that one properly without my cloud brain. I've parked it in the corner, "
                         "and we'll come back to it.")
        self.send({"type": "actions", "actions": [{**a, "at_ms": 0} for a in self.board.end_aside()]})
        ev = self.say("Shall we continue?")
        if ev is None:
            self._wait_resume()
        else:
            self.events.put(ev)
            self._wait_resume()
        if not self.ended:
            seg, _, _, _ = self._cue(min(self.k, len(self._flat()) - 1))
            self.say(f"Achha, wapas. We were at: {seg.title}.")

    def _play_answer(self, ans: dict) -> None:
        lines = [s for s in ans.get("say") or [] if s][:4]
        ops = ans.get("ops") or []
        buckets: list[list[Op]] = [[] for _ in lines]
        for op in ops:
            i = next((j for j, s in enumerate(lines) if op.at and op.at.lower() in s.lower()), 0)
            buckets[i].append(op)
        for line, b in zip(lines, buckets):
            audio, ms = self.audio.synth(line, self.speed)
            acts = self._apply(b, self.k, line, ms)
            self.log(f"Stiti: {line}")
            self.send({"type": "actions", "actions": acts})
            self.send({"type": "status", "mode": "playing", "text": "answering", "caption": line})
            self.audio.play(audio, ms)
            ev = self._wait_audio(ms, ignore_backchannel=True)
            if ev is not None:
                self.events.put(ev)
                return

    def _explain_element(self, iid: str) -> None:
        e = self.board.els.get(iid)
        label = getattr(e, "label", "") if e else ""
        if self.planner is not None and label:
            return self._answer(f"Explain '{label}' again, more simply.")
        k = self.drawn_at.get(iid)
        if k is None:
            return
        self.say(f"Sure. Let me go over {label or 'that'} again." if label else "Sure, let me go over that again.")
        self.k = k

    def _explain_again(self) -> None:
        _, cue, _, _ = self._cue(min(self.k, len(self._flat()) - 1))
        if self.planner is not None:
            return self._answer(f"I didn't understand this: '{cue.say}'. Explain it differently, with a simpler example.")
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

    def _run_check(self, seg) -> str:
        c = seg.check
        label = {"predict": "Quick guess", "mcq": "Pick one", "recall": "From memory", "explain_why": "Explain why",
                 "apply": "Apply it", "discriminate": "Which one?", "explain_back": "Teach it back"}.get(c.kind, "Your turn")
        self.send({"type": "check", "kind_label": label, "prompt": c.prompt,
                   "options": [o["text"] for o in c.options] if c.options else []})
        rec = {"segment": seg.id, "kind": c.kind, "verdict": None, "attempts": 0, "hints": 0, "confidence": None,
               "answers": []}
        ev = self.say(self._check_prompt(c))
        self.status("waiting", "your turn — say or type your answer")
        nudged = False
        t0 = time.time()
        outcome = "done"
        while not self.ended:
            if ev is None:
                ev = self._next_event(0.3)
            if ev is None:
                waited = time.time() - t0
                if waited > 30 and not nudged:
                    nudged = True
                    ev = self.say("Take your time. Or say 'pata nahi', and I'll give you a hint.")
                    t0 = time.time() - 30
                elif waited > self.check_timeout_s:
                    ev = {"type": "text", "text": "pata nahi"}
                continue
            kind, text = self._kind(ev, answering=True)
            ev = None
            if kind == "other" and not text:
                continue
            if kind == "repeat":
                ev = self.say(self._check_prompt(c))
                continue
            if kind in ("pause", "hand"):
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
            if kind in ("question", "click"):
                self._answer(text) if kind == "question" else self._explain_element(text)
                ev = self.say(self._check_prompt(c))
                continue
            if kind == "confused":
                text = "pata nahi"
            # ---- it's an answer
            rec["attempts"] += 1
            rec["answers"].append(text[:200])
            g = grade.grade(c, text)
            v = g["verdict"]
            if v == "predict":
                self.predict = (c, text)
                rec["verdict"] = "predict"
                self.say(c.reveal or "Hold that thought. We'll come back to your guess at the end.")
                break
            if v == "correct":
                rec["verdict"] = "correct"
                self.say(c.on_correct or PRAISE)
                break
            if rec["hints"] < len(c.hints) and rec["attempts"] < 3:
                opener = {"partial": "Good start, you've got part of it. Aur?", "wrong": "Not quite.",
                          "idk": "No worries."}[v]
                ev = self.say(f"{opener} Hint: {c.hints[rec['hints']]}")
                rec["hints"] += 1
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
        self.results.append(rec)
        self.send({"type": "check_done"})
        return outcome

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
        right = sum(r["verdict"] == "correct" for r in self.results)
        graded = sum(r["verdict"] not in ("predict", None) for r in self.results)
        return {"finished": finished, "cursor": self.k, "checks_right": right, "checks_graded": graded,
                "questions": len(self.questions), "cards_saved": cards, "results": self.results}
