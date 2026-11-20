"""Always-on voice loop: SLEEPING ⇄ AWAKE, full-duplex with WebRTC echo cancellation.

SLEEPING  mic (AEC-cleaned) → VAD → speech segment → whisper → wake phrase?
          "Stiti" / "Hi/Hey/Hello Stiti" / "uth jao Stiti" / the owner's own phrases → rising chime → AWAKE
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
import re
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor

import numpy as np

from . import endpoint, prosody, stt, turn, wake
from .duplex import Duplex
from .realtime import Realtime
from .. import overlay, router, say
from ..learn import recorder
from ..brain.psych import StreamLint
from .speaker import ACKS, FILLER_AFTER_S, FILLERS, Speaker
from .tts import TTS, ClauseChunker, chime_audio, sentences, speakable
from .vad import FRAME, SR, VAD

AWAKE_TIMEOUT_S = float(os.getenv("STITI_AWAKE_TIMEOUT", "30"))    # of real silence (D47: was 20, counted from her last reply;
                                                                   # D48: 45 kept her answering things said to someone else)
CONVO_AWAKE_S = float(os.getenv("STITI_CONVO_AWAKE", "60"))      # 2026-11-20: once a conversation is going (2+ turns) or
                                                                   # she just asked him something, 60 s of silence
DROWSY_S = float(os.getenv("STITI_DROWSY", "90"))                 # after dozing off mid-conversation, a follow-up-shaped
                                                                   # line ("and why…", "what about…") carries on, no wake word
CAPTIONS = os.getenv("STITI_CAPTIONS", "on") != "off"             # live words next to the orb: what she hears, what she says
INTERIM_EVERY_S, INTERIM_MIN_MS, INTERIM_WINDOW_S = 1.6, 1500, 6.0   # a rough transcript while he is still talking
WORK_JOIN_S = 8.0                    # wait at most this long for the previous engine call before the next one
REPROMPT = "Mm-hm?"                  # a fragment that timed out (Unmute: prompt him to continue, never guess)
CLARIFY = say.LINES["clarify"]       # "Sorry, say that again?" and four more; say.line("clarify") rotates them


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
        self.turns_awake = 0             # turns handled since she woke (an active conversation keeps her up longer)
        self.drowsy_until = 0.0          # dozed off mid-conversation: a follow-up still counts until then
        self.duplex: Duplex | None = None
        self.paused = threading.Event()  # menubar "mute"
        self.ring_control = None         # set while an alarm rings: "band karo" / "5 minute aur" (no wake word needed)
        self.ack_control = None          # app: "ok / got it" right after a reminder stops its repeats (D39)
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
        return self._stt.submit(stt.transcribe_ex, audio, lid=getattr(self, "awake", False))

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
                if CAPTIONS:
                    self._interim()

    def _interim(self) -> None:
        """While he is still talking (≥ 1.5 s in, not in a pause): every 1.6 s a rough transcript of the last 6 s goes
        next to the orb, so he can SEE she is hearing him. Runs on the STT thread only when it is free; never while he
        pauses (that is when the real transcript is made), never asleep, never while she speaks."""
        tt, now = self.tt, time.monotonic()
        if (not getattr(self, "awake", False) or not tt.cur or tt.speech_ms < INTERIM_MIN_MS or tt.silence_ms > 150
                or now - getattr(self, "_interim_t", 0.0) < INTERIM_EVERY_S
                or (self.duplex is not None and self.duplex.playing)):
            return
        f = getattr(self, "_interim_f", None)
        if f is not None and not f.done():
            return
        self._interim_t = now
        audio = tt._audio()[-int(INTERIM_WINDOW_S * SR):]
        prefix = getattr(tt, "prefix", "") or ""

        def job():
            try:
                loc, _ = stt._local(np.asarray(audio, dtype=np.float32), os.getenv("STITI_WHISPER", stt.WHISPER_MAIN),
                                    stt.build_prompt("en", ""))
                text = (loc.text or "").strip()
                if text and loc.no_speech_prob < 0.6 and not stt.prompt_copy(text, stt.build_prompt("en", "")):
                    overlay.caption("you", f"{prefix} {text}".strip(), live=True)
            except Exception as e:
                self._dbg(f"interim caption: {type(e).__name__}: {e}")
        self._interim_f = self._stt.submit(job)

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
            # the first wording of each first (ready in ~1 s, as before), then the other variants (D50)
            self.fillers = [self.tts.synth_on_worker(t, "calm") for t in FILLERS[:3]]
            acks = {k: [self.tts.synth_on_worker(v[0], "calm")] for k, v in ACKS.items()}
            self.acks = acks
            for k, v in ACKS.items():
                for t in v[1:]:
                    acks[k].append(self.tts.synth_on_worker(t, "calm"))     # ack_text[k][i] ↔ acks[k][i]
            for t in FILLERS[3:]:
                self.fillers.append(self.tts.synth_on_worker(t, "calm"))
        except Exception:
            if not self.acks:
                self.fillers, self.acks = [], {}

    def _play(self, audio: np.ndarray, sr: int):
        self.duplex.play(audio, sr)
        while self.duplex.playing and not self._interrupted.is_set():
            time.sleep(0.02)

    def say(self, text: str, mood: str = "calm", *, nudge: bool = False):
        """Speak sentence by sentence. Nudges stay silent while he has told her to stop."""
        if self.silenced and nudge:
            return
        if getattr(self, "ring_control", None) is None and _tutor_active():
            return                                 # a lesson owns the speakers: ONE voice (D40); alarms still ring
        print(f"Stiti: {text}")
        shown = self.awake                         # on screen only while awake (asleep = nothing on screen)
        if shown:
            overlay.set_state("speaking")
        self._speak(sentences(speakable(text)), mood)
        if shown and self.awake:
            overlay.set_state("listening")

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
        overlay.set_state("hidden")
        if self.duplex is not None:
            self.duplex.stop_playback()
        self._resume = None
        self.awake, self.silenced, self.drowsy_until = False, True, 0.0
        self._chime(up=False)
        print(f"🤫 (stopped — say {wake.hint()} when you need me)")

    # ---------- behaviour ----------
    def _wait_work(self) -> None:
        """One engine call at a time: a cancelled/cut reply's thread finishes (or aborts) before the next."""
        w = self._work
        if w is not None and w.is_alive():
            w.join(WORK_JOIN_S)

    def _handle(self, text: str, audio: np.ndarray | None, c: endpoint.Commit | None = None):
        self.turns_awake = getattr(self, "turns_awake", 0) + 1
        self._wait_work()
        overlay.set_state("thinking")
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
        def first_audio(t: float) -> None:
            pend.first_audio_t = t
            overlay.set_state("speaking")

        sp = Speaker(self, mood, filler_after=FILLER_AFTER_S if finished else 1e9,   # never "hmm" on a fragment/hold
                     on_first_audio=first_audio)

        def on_ack(kind: str) -> None:                  # "Checking your calendar." + the pill says what she's doing
            sp.ack(kind)
            overlay.set_state("thinking", kind)
        # StreamLint() binds to the strategy engine.turn() picks for THIS turn (on the engine thread, at first piece)
        chunker, lint, result = ClauseChunker(), StreamLint(), {}

        def on_delta(d: str):
            if pend.cancelled:
                raise _Cancelled()                      # he went on talking: stop the LLM stream
            for piece in chunker.feed(d):
                if (piece := lint.feed(piece)) is not None:
                    sp.add(piece)

        def work():
            t_turn = time.time()
            try:
                result["reply"] = (self.rt.turn if self.rt is not None else self.engine.turn)(
                    text, voice_emotion=voice, on_delta=on_delta, on_ack=on_ack)
                if getattr(self.engine, "last_route", None) == "fast_path":
                    pend.action = getattr(self.engine, "last_action", None)
            except _Cancelled:
                result["cancelled"] = True
            except Exception as e:
                result["reply"] = "Sorry, something went wrong."
                print(f"[turn] {type(e).__name__}: {e}")
            pend.user_ep = getattr(self.engine, "cur_user_ep", None)
            try:
                if pend.cancelled or result.get("cancelled"):
                    return
                card = getattr(self.engine, "last_card", None)
                if card and card.get("ts", 0) >= t_turn:   # this turn's card (a held turn keeps the old one)
                    overlay.show_card(card)             # on screen while she starts saying it
                if getattr(self.engine, "skip_turn", False) and not (result.get("reply") or "").strip():
                    result["skip"] = True               # "ek sec" / "let me think": he's thinking, say nothing
                    return
                if self.engine.streamed:
                    for piece in chunker.flush():
                        if (piece := lint.feed(piece)) is not None:
                            sp.add(piece)
                    if not lint.said and (result.get("reply") or "").strip():
                        for piece in sentences(speakable(result["reply"])):   # every piece was cut (machine-talk…):
                            sp.add(piece)                                    # say the cleaned reply, never silence
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
        overlay.speech_ended()                          # the card's auto-dismiss clock starts now
        overlay.set_state("listening" if getattr(self, "awake", False) else "hidden")
        if pend.first_audio_t is None and self.tt.pending is pend:
            self.tt.pending = None                      # nothing was said: nothing to join to
        if pend.cancelled:
            print("Stiti: (dropped — you were still talking)")
            return
        recorder.on_turn(self.engine, text, audio, c, voice, th)      # opt-in local recorder (D28); no-op when OFF
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
        fn = getattr(self.engine, "forget_fragment", None)
        if fn is not None and pend.user_ep:
            try:
                fn(pend.user_ep)                         # the joined sentence holds the whole thought (D36)
            except Exception as e:
                print(f"[fragment] {type(e).__name__}: {e}")
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
                c.res = (c.spec or self._stt.submit(stt.transcribe_ex, c.audio,
                                                    lid=getattr(self, "awake", False))).result()
            except Exception as e:
                print(f"[stt] {type(e).__name__}: {e}")
                c.res = stt.STTResult("")
        return c.res

    def _dbg(self, msg: str) -> None:
        if self.debug:
            print(f"   ({msg})")

    def run(self, stop: threading.Event | None = None):
        stop = stop or threading.Event()
        print(f"🎙️  Listening for “Stiti” or {wake.hint()}…  (stop her anytime: “shut up”, “bye”, “chalo”)")
        print(f"   echo cancellation {'ON — interrupt her anytime' if self.aec else 'OFF — half-duplex'}")
        threading.Thread(target=self._segmenter, args=(stop,), daemon=True).start()
        overlay.set_click_handler(lambda: self._on_event(("stop",)))   # click the pill = stop her
        with Duplex(self._on_mic, aec=self.aec) as d:
            self.duplex = d
            self.tt.started_t = time.monotonic()
            while not stop.is_set():
                try:
                    c = self.segq.get(timeout=0.5)
                except queue.Empty:
                    c = None
                if self.awake and _tutor_active():      # a lesson started: she goes quiet now, not at his next word
                    self.awake = False                  # (an "Mm-hm?" reprompt or a missed-alarm line would talk over it)
                    overlay.set_state("hidden")
                if self.rt is not None:
                    self.rt.tick(c)
                if c is None and not _tutor_active() and (why := d.heal()):
                    print(f"🎙️  [mic] {why} — reopened the microphone (reopen #{d.reopens})")
                now = time.time()
                if c is None and not _tutor_active() and d.reopen_failed():
                    ok = mic_restart_ok(self.awake, now - self.last_activity, d.heard_once, _last_restart_ago(now))
                    if ok and _may_restart():
                        print("🎙️  [mic] still silent after reopening — restarting Stiti (a fresh process hears again)",
                              flush=True)
                        os._exit(75)                     # Stiti.app's launcher restarts on a non-zero exit
                    if not ok and not d.heard_once and not getattr(self, "_no_help_said", False):
                        self._no_help_said = True        # said once: the log filled with a restart every 5 min
                        print("🎙️  [mic] silent even after a fresh start (lid closed / input muted / headset away?) — "
                              "not restarting again; I keep checking and reopen when a mic comes back", flush=True)
                win = awake_window(self.turns_awake, getattr(self.engine, "last_reply_text", None))
                if self.awake and (self.tt.busy or c is not None):
                    self.last_activity = max(self.last_activity, now - win + 8)   # he is talking: stay
                # D47: only an IDLE moment can end the session. Before, the check also ran on the tick that delivered
                # his words: he spoke for 25 s, paused, and she fell asleep before reading what he had just said.
                if should_sleep(self.awake, c is not None, now - self.last_activity, d.playing, self.tt.busy,
                                timeout=win):
                    self.awake = False
                    self.drowsy_until = now + DROWSY_S if self.turns_awake >= 1 else 0.0
                    overlay.set_state("hidden")
                    self._chime(up=False)
                    print("💤 (sleeping — say “Hey Stiti” to wake me)")
                if c is None or len(c.audio) < SR * 0.3:
                    continue
                if _tutor_active():                     # a whiteboard lesson owns the mic right now
                    self.awake = False
                    overlay.set_state("hidden")
                    continue
                # one pass serves wake check + command; usually already done (started early in the pause)
                res = self._result(c)
                text = c.text or ""
                if not text:
                    continue
                if CAPTIONS and self.awake:
                    overlay.caption("you", text)         # what she heard, next to the orb
                if self.ring_control is not None and (said := self.ring_control(text)):
                    print(f"You: {text}")
                    self.duplex.stop_playback()
                    self.say(said)
                    continue
                if self.ack_control is not None and (said := _safe(self.ack_control, text)):
                    print(f"You: {text}")
                    self.say(said)
                    self.last_activity = now
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
                    if not res.unclear and carries_on(text, now, self.drowsy_until, self.silenced):
                        # she dozed off a moment ago in the middle of a conversation and he just carries on ("and
                        # why is that?", "what about Pune?"): no wake word needed, no greeting — answer it
                        self.awake, self.last_activity, self.drowsy_until = True, now, 0.0
                        overlay.set_state("listening")
                        router.warm()
                        print(f"You: {text}   (carrying on — no wake word needed right after a conversation)")
                        self._handle(text, c.audio, c)
                        continue
                    woke, rest = wake.detect(text)
                    if not woke:
                        if wake.near_miss(text):         # "Hey Stuti-ish" that didn't match: log it, nothing else
                            print(f"   (almost woke: {text!r})")
                        continue
                    self.awake, self.silenced, self.last_activity = True, False, now
                    self.turns_awake, self.drowsy_until = 0, 0.0
                    overlay.set_state("listening")      # "Hey Stiti" → the pill blooms in under the menu bar
                    router.warm()                       # reconnect to the LLM while the chime plays
                    self._chime(up=True)
                    if len(rest.split()) >= 2:   # "Hey Stiti, what are my todos" -> handle at once
                        print(f"You: {rest}")
                        self._handle(rest, c.audio, c)
                    else:
                        overlay.note(_greeting_line())   # next to the orb: "Hey <name>, what's on your mind?"
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
                        self.say(say.line("clarify"))
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


MIC_RESTARTS = 2              # at most this many mic restarts …
MIC_RESTART_WINDOW_S = 600.0  # … per 10 minutes (a really muted mic must not cause a restart loop)
CONVO_GUARD_S = 120.0         # never restart during a conversation or within 2 min of its last turn (2026-11-20)
NO_HELP_S = 30 * 60.0         # this process never heard a sound and the last restart was < 30 min ago: a fresh
                              # process doesn't help (2026-11-18: 12 restarts in 55 min, one every 5 min, mic still dead)


def mic_restart_ok(awake: bool, since_activity_s: float, heard_once: bool, last_restart_ago_s: float | None) -> bool:
    """May the mic watchdog restart the process now? Never mid-conversation (a restart used to wipe what she was
    talking about); never again when the last restart didn't bring any sound back (the mic itself is silent)."""
    if awake or since_activity_s < CONVO_GUARD_S:
        return False
    if not heard_once and last_restart_ago_s is not None and last_restart_ago_s < NO_HELP_S:
        return False
    return True


def _last_restart_ago(now: float | None = None) -> float | None:
    from ..config import CFG
    now = time.time() if now is None else now
    try:
        stamps = [float(x) for x in (CFG.home / "logs" / "mic_restarts").read_text().split()]
    except (OSError, ValueError):
        return None
    return now - max(stamps) if stamps else None


def _may_restart(now: float | None = None) -> bool:
    """Record a mic restart unless there were already MIC_RESTARTS in the window (file survives the restart)."""
    from ..config import CFG
    now = time.time() if now is None else now
    p = CFG.home / "logs" / "mic_restarts"
    try:
        stamps = [float(x) for x in p.read_text().split()] if p.exists() else []
    except ValueError:
        stamps = []
    stamps = [t for t in stamps if now - t < MIC_RESTART_WINDOW_S]
    if len(stamps) >= MIC_RESTARTS:
        return False
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(" ".join(str(t) for t in stamps + [now]))
    return True


def _safe(fn, text: str):
    """A hook must never kill the voice loop (a DB hiccup → just not an ack)."""
    try:
        return fn(text)
    except Exception as e:
        print(f"[voice] hook failed: {e}", flush=True)
        return None


def should_sleep(awake: bool, got_segment: bool, since_activity_s: float, playing: bool, busy: bool,
                 timeout: float | None = None) -> bool:
    """End the session? Only on an idle tick: never on the tick that delivers his words (got_segment), never while he
    is mid-sentence (busy) or she is speaking."""
    t = AWAKE_TIMEOUT_S if timeout is None else timeout
    return bool(awake and not got_segment and since_activity_s > t and not playing and not busy)


def awake_window(turns_awake: int, her_last: str | None) -> float:
    """Seconds of silence before she sleeps: AWAKE_TIMEOUT_S after a wake or a one-off command; CONVO_AWAKE_S once a
    conversation is going (2+ turns since the wake) or when her last reply asked him something (he is thinking about
    his answer). 2026-11-20: 9 % of his next lines came 30 s – 10 min after her reply, i.e. after she had slept."""
    if turns_awake >= 2 or (her_last or "").rstrip().endswith("?"):
        return max(AWAKE_TIMEOUT_S, CONVO_AWAKE_S)
    return AWAKE_TIMEOUT_S


def carries_on(text: str, now: float, drowsy_until: float, silenced: bool) -> bool:
    """Right after she dozed off mid-conversation (not after "bye" / "stop"): a line shaped like a follow-up ("and
    why…", "what about…", "tell me more") or one that names her anywhere continues the conversation."""
    if silenced or now >= drowsy_until or not text.strip():
        return False
    from ..brain.thread import cue
    named = any(v in wake._norm(text).split() for v in wake.NAME_VARIANTS)
    return cue(text) or named


def _greeting_line() -> str:
    try:
        from .. import profile
        from ..overlay import model as OM
        return OM.greeting(profile.call())
    except Exception:
        return "Hey, what's on your mind?"


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
