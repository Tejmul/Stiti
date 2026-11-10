"""Always-on voice loop: SLEEPING ⇄ AWAKE, full-duplex with WebRTC echo cancellation.

SLEEPING  mic (AEC-cleaned) → VAD → speech segment → whisper → wake phrase?
          "Stiti" / "Hi/Hey/Hello Stiti" / "Wake up baby girl" / "uth jao Stiti" → rising chime → AWAKE
AWAKE     segment → whisper → engine.turn() → Kokoro, sentence-streamed through the duplex stream.
STOP      "shut up" / "chup" / "bas" / "stop" (alone) → she stops at once, falling chime, NO talking — and stays
          silent (her voice nudges too) until a wake phrase. "bye" / "chalo bye" / "good night" → she says a
          warm goodbye first (farewell.py), then sleeps.
Turn-end  endpoint.py: Smart Turn once at 300 ms (bar 0.5) + a text check on the early transcript
          (finished / unfinished / wait) → answer at ~450 ms, or wait his learned pause (0.6 s+), 3 s for
          "So…"/"remind me at 4 to", 8 s for "hold on"/"ek sec" (then silence). A fragment that times out gets
          a soft "Mm-hm?" and is joined with whatever he says next.
Grace     if he goes on talking right after she was handed the turn (before her first audio, or within 0.9 s
          of it), the reply is cancelled and both parts are answered as one.
Barge-in  he talks over her: 250 ms → she ducks, 900 ms → she pauses; his words decide: "stop"/"wait" or ≥2
          words → she stops and listens; "haan"/"okay"/one word/1.5 s quiet → she carries on.
Bye gate  "bye"/"stop" only counts if it was ≥300 ms, confidently heard and not the echo tail of her reply.
Speed     LLM reply is streamed; she starts at the first clause, next sentence is synthesised while the
          current one plays (speaker.py). Slow actions get an instant "Checking your calendar.";
          anything else silent for >1.5 s gets a "hmm". Connections to the LLM are pre-warmed on wake.
"""
from __future__ import annotations

import os
import queue
import random
import re
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor

import numpy as np

from . import endpoint, prosody, stt, turn, wake
from .duplex import Duplex
from .realtime import Realtime
from .. import router
from ..brain.psych import StreamLint
from .speaker import ACKS, FILLER_AFTER_S, FILLERS, Speaker
from .tts import TTS, ClauseChunker, chime_audio, sentences, speakable
from .vad import FRAME, SR, VAD

AWAKE_TIMEOUT_S = float(os.getenv("STITI_AWAKE_TIMEOUT", "20"))
WORK_JOIN_S = 8.0                    # wait at most this long for the previous engine call before the next one
REPROMPT = "Mm-hm?"                  # a fragment that timed out (Unmute: prompt him to continue, never guess)
CLARIFY = ["Sorry, say that again?", "Sorry, I didn't catch that.", "Hmm, say that once more?"]


class _Cancelled(Exception):
    """Raised inside on_delta to abort the LLM stream of a reply he talked over."""


class VoiceLoop:
    rt: Realtime | None = None           # preemptive reply, pre-warm, ● ◐ ○, media pause (realtime.py, D29)

    def __init__(self, engine, aec: bool = True, debug: bool = False):
        self.engine = engine
        self.aec = aec
        self.debug = debug
        self.vad = VAD()
        self.tts = TTS()
        self.micq: queue.Queue[np.ndarray] = queue.Queue()
        self.segq: queue.Queue[endpoint.Commit] = queue.Queue()
        self._stt = ThreadPoolExecutor(max_workers=1, thread_name_prefix="whisper")   # one long-lived STT thread
        self.stats = endpoint.TurnStats()                # his learned pace (~/.stiti/turn_stats.json)
        self.tt = endpoint.TurnTaker(self.stats, self._submit_stt, turn.complete_prob, aec=aec,
                                     start_t=time.monotonic(),
                                     log=(lambda m: print(f"   [turn] {m}")) if debug else None)
        self._work: threading.Thread | None = None      # the last engine call (one at a time)
        self._clarified = False
        self.awake = False
        self.silenced = False            # True after a stop word: no voice at all until a wake phrase
        self.last_activity = 0.0
        self.duplex: Duplex | None = None
        self.paused = threading.Event()  # menubar "mute"
        self.ring_control = None         # set while an alarm rings: "band karo" / "5 minute aur" (no wake word needed)
        self._interrupted = threading.Event()
        self._resume: tuple[list[str], str] | None = None
        self.fillers: list[tuple[np.ndarray, int]] = []
        self.acks: dict[str, tuple[np.ndarray, int]] = {}
        self.ack_text = ACKS
        threading.Thread(target=self._prepare_fillers, daemon=True).start()
        router.warm()
        self.rt = Realtime(self)

    # ---------- audio in: callback only queues; segmentation runs in its own thread ----------
    def _on_mic(self, x16: np.ndarray):
        if not self.paused.is_set():
            self.micq.put(x16)

    def _submit_stt(self, audio: np.ndarray) -> Future:
        return self._stt.submit(stt.transcribe_ex, audio)

    def _segmenter(self, stop: threading.Event):
        """VAD every 32 ms frame → endpoint.TurnTaker decides (end of turn, barge-in, continuation)."""
        buf = np.zeros(0, dtype=np.float32)
        self.tt.started_t = time.monotonic()             # AEC warm-up counts from here
        while not stop.is_set():
            try:
                buf = np.concatenate([buf, self.micq.get(timeout=0.5)])
            except queue.Empty:
                continue
            while len(buf) >= FRAME:
                f, buf = buf[:FRAME], buf[FRAME:]
                p = self.vad.prob(f)
                d = self.duplex
                playing = d is not None and d.playing
                for ev in self.tt.feed(f, p, time.monotonic(), playing, getattr(d, "started_at", None)):
                    self._on_event(ev)

    def _on_event(self, ev: tuple) -> None:
        if self.rt is not None and self.rt.on_event(ev):
            return
        kind, d = ev[0], self.duplex
        if kind == "commit":
            self.segq.put(ev[1])
        elif d is None:
            return
        elif kind == "duck" and hasattr(d, "duck"):
            d.duck()
        elif kind == "pause" and hasattr(d, "pause"):
            d.pause()
        elif kind == "resume" and hasattr(d, "resume"):
            d.resume()
        elif kind == "stop":                             # his words stopped her: a real interruption
            self._interrupted.set()
            d.stop_playback()
            self.engine.last_interrupted = True          # feedback: her reply may have been too long
        elif kind == "cancel":                           # he wasn't done: drop the reply, his parts get joined
            self._interrupted.set()
            d.stop_playback()

    # ---------- speaking ----------
    def _prepare_fillers(self):
        """Pre-synthesise fillers + acknowledgements (and warm Kokoro) so they play with ~0 ms delay.
        Also load Smart Turn + whisper now: lazily loaded, the first turn-end check stalled ~2.5 s."""
        try:
            turn.complete_prob(np.zeros(SR, dtype=np.float32))
            self._stt.submit(stt.transcribe_ex, np.zeros(SR, dtype=np.float32)).result()
        except Exception as e:
            print(f"[voice warm-up] {e}")
        try:
            self.fillers = [self.tts.synth_on_worker(t, "calm") for t in FILLERS]
            self.acks = {k: self.tts.synth_on_worker(t, "calm") for k, t in ACKS.items()}
        except Exception:
            self.fillers, self.acks = [], {}

    def _play(self, audio: np.ndarray, sr: int):
        self.duplex.play(audio, sr)
        while self.duplex.playing and not self._interrupted.is_set():
            time.sleep(0.02)

    def say(self, text: str, mood: str = "calm", *, nudge: bool = False):
        """Speak sentence by sentence. Nudges stay silent while he has told her to stop."""
        if (self.silenced or _tutor_active()) and nudge:
            return
        print(f"Stiti: {text}")
        self._speak(sentences(speakable(text)), mood)

    def _speak(self, parts: list[str], mood: str):
        """Gapless: the next sentence is synthesised while the current one plays."""
        self._interrupted.clear()
        self._resume = None
        sp = Speaker(self, mood, filler_after=1e9)
        for s in parts:
            sp.add(s)
        sp.close()
        left = sp.run()
        if left:
            self._resume = (left, mood)            # re-say the cut sentence if he only said "haan"
        self.last_activity = time.time()

    def _chime(self, up: bool):
        a, sr = chime_audio(up)
        self._interrupted.clear()
        self._play(a, sr)

    def deactivate(self):
        """Stop word: stop now, no words, stay silent until a wake phrase."""
        if self.duplex is not None:
            self.duplex.stop_playback()
        self._resume = None
        self.awake, self.silenced = False, True
        self._chime(up=False)
        print("🤫 (stopped — say “Hi Stiti” or “Wake up baby girl” when you need me)")

    # ---------- behaviour ----------
    def _wait_work(self) -> None:
        """One engine call at a time: a cancelled/cut reply's thread finishes (or aborts) before the next."""
        w = self._work
        if w is not None and w.is_alive():
            w.join(WORK_JOIN_S)

    def _handle(self, text: str, audio: np.ndarray | None, c: endpoint.Commit | None = None):
        self._wait_work()
        voice = None
        if audio is not None:
            label, conf, _ = prosody.update_and_score(prosody.features(audio, SR, len(text.split())))
            deep = _deep_last
            if deep and deep[1] > conf:
                label, conf = deep
            voice = (label, conf) if label else None
            _deep_emotion_async(audio)
        self._interrupted.clear()
        self._resume = None
        mood = (voice[0] if voice and voice[0] else None) or self.engine.last_mood or "calm"
        now = time.monotonic()
        pend = endpoint.Pending(text, committed_t=c.commit_t if c is not None else now,
                               speech_end_t=c.end_t if c is not None else now)
        finished = (c is None or c.state in (None, "finished")) and endpoint.text_state(text) != "wait"
        sp = Speaker(self, mood, filler_after=FILLER_AFTER_S if finished else 1e9,   # never "hmm" on a fragment/hold
                     on_first_audio=lambda t: setattr(pend, "first_audio_t", t))
        # StreamLint() binds to the strategy engine.turn() picks for THIS turn (on the engine thread, at first piece)
        chunker, lint, result = ClauseChunker(), StreamLint(), {}

        def on_delta(d: str):
            if pend.cancelled:
                raise _Cancelled()                      # he went on talking: stop the LLM stream
            for piece in chunker.feed(d):
                if (piece := lint.feed(piece)) is not None:
                    sp.add(piece)

        def work():
            try:
                result["reply"] = (self.rt.turn if self.rt is not None else self.engine.turn)(
                    text, voice_emotion=voice, on_delta=on_delta, on_ack=sp.ack)
                if getattr(self.engine, "last_route", None) == "fast_path":
                    pend.action = getattr(self.engine, "last_action", None)
            except _Cancelled:
                result["cancelled"] = True
            except Exception as e:
                result["reply"] = "Sorry, something went wrong."
                print(f"[turn] {type(e).__name__}: {e}")
            try:
                if pend.cancelled or result.get("cancelled"):
                    return
                if getattr(self.engine, "skip_turn", False) and not (result.get("reply") or "").strip():
                    result["skip"] = True               # "ek sec" / "let me think": he's thinking, say nothing
                    return
                if self.engine.streamed:
                    for piece in chunker.flush():
                        if (piece := lint.feed(piece)) is not None:
                            sp.add(piece)
                else:                                   # fast path / tools / offline: whole reply at once
                    for piece in sentences(speakable(result["reply"])):
                        sp.add(piece)
            finally:
                sp.close()

        th = threading.Thread(target=work, daemon=True)
        pend.work = self._work = th
        self.tt.pending = pend
        th.start()
        left = sp.run()
        self.last_activity = time.time()
        if pend.first_audio_t is None and self.tt.pending is pend:
            self.tt.pending = None                      # nothing was said: nothing to join to
        if pend.cancelled:
            print("Stiti: (dropped — you were still talking)")
            return
        if left:
            self._resume = (left, mood)
        if sp.interrupted:
            self._truncate(sp.heard, th)
            print(f"Stiti: {' '.join(sp.heard)} —(cut off)")
        elif result.get("skip"):
            print("Stiti: (quiet — you're thinking)")
        else:
            print(f"Stiti: {result.get('reply', '…')}")
        if self.debug:
            ms = lambda x: f"{x:.0f} ms" if x is not None else "—"  # noqa: E731
            print(f"   ↳ first text {ms(sp.first_text_ms)} → first audio {ms(sp.first_audio_ms)} after turn start"
                  f" · {self.engine.last_debug}")

    def _truncate(self, heard: list[str], th: threading.Thread) -> None:
        """He cut her off: memory keeps only what he actually heard (OpenAI item.truncate / ElevenLabs
        agent_response_correction). The engine method is optional (another module owns it)."""
        fn = getattr(self.engine, "truncate_last_reply", None)
        if fn is None:
            return

        def go():
            th.join(WORK_JOIN_S)                         # the reply must be stored before it can be cut
            try:
                fn(" ".join(heard).strip())
            except Exception as e:
                print(f"[truncate] {type(e).__name__}: {e}")
        t = threading.Thread(target=go, daemon=True)
        self._work = t                                   # the next turn waits for this too
        t.start()

    def _undo_replaced(self, pend: endpoint.Pending) -> None:
        """A cancelled fragment may already have done a fast-path write ("Remind me at 4." + "…to call mom"):
        undo it, the joined sentence does it properly."""
        if pend.work is not None and pend.work.is_alive():
            pend.work.join(WORK_JOIN_S)
        if pend.action:
            try:
                from ..brain import learning
                learning.undo_last(pend.action)
                if getattr(self.engine, "last_action", None) == pend.action:
                    self.engine.last_action = None
            except Exception as e:
                print(f"[undo] {type(e).__name__}: {e}")

    def _result(self, c: endpoint.Commit) -> stt.STTResult:
        if c.res is None:
            try:
                c.res = (c.spec or self._stt.submit(stt.transcribe_ex, c.audio)).result()
            except Exception as e:
                print(f"[stt] {type(e).__name__}: {e}")
                c.res = stt.STTResult("")
        return c.res

    def _dbg(self, msg: str) -> None:
        if self.debug:
            print(f"   ({msg})")

    def run(self, stop: threading.Event | None = None):
        stop = stop or threading.Event()
        print("🎙️  Listening for “Stiti”, “Hi Stiti” or “Wake up baby girl”…  (stop her anytime: “shut up”, “bye”, “chalo”)")
        print(f"   echo cancellation {'ON — interrupt her anytime' if self.aec else 'OFF — half-duplex'}")
        threading.Thread(target=self._segmenter, args=(stop,), daemon=True).start()
        with Duplex(self._on_mic, aec=self.aec) as d:
            self.duplex = d
            self.tt.started_t = time.monotonic()
            while not stop.is_set():
                try:
                    c = self.segq.get(timeout=0.5)
                except queue.Empty:
                    c = None
                if self.rt is not None:
                    self.rt.tick(c)
                now = time.time()
                if (self.awake and now - self.last_activity > AWAKE_TIMEOUT_S and not d.playing
                        and not self.tt.busy):           # never fall asleep while he's mid-sentence
                    self.awake = False
                    self._chime(up=False)
                    print("💤 (sleeping — say “Hey Stiti” to wake me)")
                if c is None or len(c.audio) < SR * 0.3:
                    continue
                if _tutor_active():                     # a whiteboard lesson owns the mic right now
                    self.awake = False
                    continue
                # one pass serves wake check + command; usually already done (started early in the pause)
                res = self._result(c)
                text = c.text or ""
                if not text:
                    continue
                if self.ring_control is not None and (said := self.ring_control(text)):
                    print(f"You: {text}")
                    self.duplex.stop_playback()
                    self.say(said)
                    continue
                engaged = self.awake or now - self.last_activity < 10      # awake, or she just spoke (a nudge)
                # after her "…Anything else?", "that's it / okay / bas / not yet" is an answer, not a goodbye:
                # the engine says "Okay, I'm here." and the session stays open (only a real bye or the timeout ends it)
                answer = self.awake and _after_offer(self.engine) and len(text.split()) <= 4 and not _explicit_bye(text)
                if engaged and not answer and (wake.is_stop(text) or wake.is_sleep(text)):
                    if not endpoint.goodbye_counts(c, res, d.ended_at):
                        self._dbg(f"ignored {text!r}: {c.speech_ms} ms, no_speech {res.no_speech_prob:.2f}, "
                                  f"logprob {res.avg_logprob:.2f} — too short / unsure / her echo")
                        self.tt.clear_prefix()
                        continue
                    print(f"You: {text}")
                    if wake.is_goodbye(text) and not self.silenced:
                        from ..farewell import farewell
                        self.say(farewell(text, self.engine.last_mood))
                    self.deactivate()
                    continue
                if (c.overlap and not c.barged and not answer
                        and all(w in endpoint.BACKCHANNEL_WORDS for w in endpoint.words(text))):
                    self._dbg(f"backchannel while she spoke: {text!r}")
                    continue
                if self.awake and self._resume and wake.is_backchannel(text):
                    parts, mood = self._resume       # he only said "haan" — carry on
                    self._speak(parts, mood)
                    continue
                self._resume = None
                if not self.awake:
                    self.tt.clear_prefix()
                    if self.debug:
                        print(f"   (heard while asleep: {text!r}, {res.ms:.0f} ms)")
                    woke, rest = wake.detect(text)
                    if not woke:
                        continue
                    self.awake, self.silenced, self.last_activity = True, False, now
                    router.warm()                       # reconnect to the LLM while the chime plays
                    self._chime(up=True)
                    if len(rest.split()) >= 2:   # "Hey Stiti, what are my todos" -> handle at once
                        print(f"You: {rest}")
                        self._handle(rest, c.audio, c)
                    else:
                        self.say(self.engine.greet())
                    continue
                if c.timed_out and c.state == "wait":   # "hold on" / "ek sec": he's thinking — say nothing
                    print(f"You: {text}   (waiting)")
                    self.tt.clear_prefix()
                    self.last_activity = time.time()
                    continue
                if c.timed_out and c.state == "unfinished" and not c.reprompted:
                    print(f"You: {text}   (unfinished)")  # the fragment is kept and joined to what comes next
                    self.say(REPROMPT)
                    continue
                if res.unclear and not c.prefix:
                    if endpoint.in_echo_tail(c, d.ended_at):
                        self._dbg(f"ignored unsure {text!r} right after her audio (echo/noise)")
                        continue
                    if not self._clarified:
                        self._clarified = True
                        print(f"You: {text}   (unclear: no_speech {res.no_speech_prob:.2f}, "
                              f"logprob {res.avg_logprob:.2f})")
                        self.say(random.choice(CLARIFY))
                        continue
                self._clarified = False
                if c.replaces is not None:
                    self._undo_replaced(c.replaces)
                print(f"You: {text}" + (f"   ({res.ms:.0f} ms STT)" if self.debug else ""))
                self.last_activity = now
                self._handle(text, c.audio, c)
            if self.rt is not None:
                self.rt.close()                         # give him back any music she paused


def _after_offer(engine) -> bool:
    """Her last reply closed with "Anything else?" (the engine's confirm-and-close)."""
    return bool(re.search(r"anything else\?\s*$", getattr(engine, "last_reply_text", None) or "", re.I))


def _explicit_bye(text: str) -> bool:
    try:
        from ..farewell import is_bye                   # the persona engine's goodbye detector, when present
        if is_bye(text):
            return True
    except ImportError:
        pass
    return bool(_BYE_RX.search(text))


_BYE_RX = re.compile(r"\b(bye+|good ?night|gn|so jao|go to sleep|sleep now|see you|kal milte|shubh ratri)\b", re.I)


def _tutor_active() -> bool:
    try:
        from ..tutor import tutor_active
        return tutor_active()
    except Exception:
        return False


# ---------- deep voice emotion (emotion2vec+ base), background only, never on the critical path ----------
_deep_last: tuple[str, float] | None = None


def _deep_emotion_async(audio: np.ndarray):
    if os.getenv("STITI_VOICE_EMOTION", "off") == "off":
        return

    def work():
        global _deep_last
        try:
            from .emotion_model import classify
            _deep_last = classify(audio)
        except Exception as e:  # model missing / OOM: prosody alone still works
            if os.getenv("STITI_DEBUG"):
                print(f"[emotion2vec] {e}")
    threading.Thread(target=work, daemon=True).start()
