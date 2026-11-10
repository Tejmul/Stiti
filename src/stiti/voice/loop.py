"""Always-on voice loop: SLEEPING ⇄ AWAKE, full-duplex with WebRTC echo cancellation.

SLEEPING  mic (AEC-cleaned) → VAD → speech segment → whisper → wake phrase?
          "Stiti" / "Hi/Hey/Hello Stiti" / "Wake up baby girl" / "uth jao Stiti" → rising chime → AWAKE
AWAKE     segment → whisper → engine.turn() → Kokoro, sentence-streamed through the duplex stream.
STOP      "shut up" / "chup" / "bas" / "stop" (alone) → she stops at once, falling chime, NO talking — and stays
          silent (her voice nudges too) until a wake phrase. "bye" / "chalo bye" / "good night" → she says a
          warm goodbye first (farewell.py), then sleeps.
Turn-end  Smart Turn v3.2 on a 300 ms pause: finished → answer now; unfinished → wait (≤2 s silence).
Barge-in  he talks over her ≥450 ms → she stops. If it was only "haan"/"hmm" she resumes her sentence.
Speed     LLM reply is streamed; she starts at the first clause, next sentence is synthesised while the
          current one plays (speaker.py). Slow actions get an instant "ek sec, calendar dekhti hoon";
          anything else silent for >0.9 s gets a "hmm". Connections to the LLM are pre-warmed on wake.
"""
from __future__ import annotations

import os
import queue
import random
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor

import numpy as np

from . import prosody, stt, turn, wake
from .duplex import Duplex
from .. import router
from ..brain.psych import StreamLint
from .speaker import ACKS, FILLERS, Speaker
from .tts import TTS, ClauseChunker, chime_audio, sentences, speakable
from .vad import FRAME, SR, VAD

AWAKE_TIMEOUT_S = float(os.getenv("STITI_AWAKE_TIMEOUT", "20"))
BARGE_MS = 450
PAUSE_CHECKS_MS = (300, 600, 1000)   # ask Smart Turn at each of these pauses (a "matlab…" pause gets re-checked)
FALLBACK_SILENCE_MS = 1500           # end the turn anyway after this much silence
SPEC_STT_MS = 160                    # start transcribing this early in a pause (thrown away if he goes on)


class VoiceLoop:
    def __init__(self, engine, aec: bool = True, debug: bool = False):
        self.engine = engine
        self.aec = aec
        self.debug = debug
        self.vad = VAD()
        self.tts = TTS()
        self.micq: queue.Queue[np.ndarray] = queue.Queue()
        self.segq: queue.Queue[tuple[np.ndarray, Future | None]] = queue.Queue()
        self._stt = ThreadPoolExecutor(max_workers=1, thread_name_prefix="whisper")   # one long-lived STT thread
        self.awake = False
        self.silenced = False            # True after a stop word: no voice at all until a wake phrase
        self.last_activity = 0.0
        self.duplex: Duplex | None = None
        self.paused = threading.Event()  # menubar "mute"
        self._interrupted = threading.Event()
        self._resume: tuple[list[str], str] | None = None
        self.fillers: list[tuple[np.ndarray, int]] = []
        self.acks: dict[str, tuple[np.ndarray, int]] = {}
        self.ack_text = ACKS
        threading.Thread(target=self._prepare_fillers, daemon=True).start()
        router.warm()

    # ---------- audio in: callback only queues; segmentation runs in its own thread ----------
    def _on_mic(self, x16: np.ndarray):
        if not self.paused.is_set():
            self.micq.put(x16)

    def _segmenter(self, stop: threading.Event):
        buf = np.zeros(0, dtype=np.float32)
        cur: list[np.ndarray] = []
        ring: list[np.ndarray] = []
        silence = speech_ms = 0
        checks = 0                                    # how many of PAUSE_CHECKS_MS were asked this pause
        spec: Future | None = None                    # transcription started early in this pause
        while not stop.is_set():
            try:
                buf = np.concatenate([buf, self.micq.get(timeout=0.5)])
            except queue.Empty:
                continue
            while len(buf) >= FRAME:
                f, buf = buf[:FRAME], buf[FRAME:]
                p = self.vad.prob(f)
                if self.duplex is not None and self.duplex.playing:
                    speech_ms = speech_ms + 32 if p > 0.6 else 0
                    if not self.aec:
                        cur, silence = [], 0          # half-duplex without AEC
                        continue
                    if speech_ms >= BARGE_MS:         # barge-in
                        self.duplex.stop_playback()
                        self._interrupted.set()
                        self.engine.last_interrupted = True   # feedback: her reply may have been too long
                if cur:
                    cur.append(f)
                    if p >= 0.5:
                        silence, checks, spec = 0, 0, None   # he kept talking: the early transcript is stale
                        continue
                    silence += 32
                    if spec is None and silence >= SPEC_STT_MS:
                        spec = self._stt.submit(stt.transcribe, np.concatenate(cur))
                    end = False
                    if checks < len(PAUSE_CHECKS_MS) and silence >= PAUSE_CHECKS_MS[checks]:
                        checks += 1
                        try:                          # bar lowers as the pause grows
                            end = turn.complete_prob(np.concatenate(cur)) >= (0.5, 0.4, 0.3)[checks - 1]
                        except Exception:
                            end = silence >= 800
                    if end or silence >= FALLBACK_SILENCE_MS or len(cur) * 32 > 30000:
                        self.segq.put((np.concatenate(cur), spec))
                        cur, silence, checks, spec = [], 0, 0, None
                elif p >= 0.5:
                    cur = ring[-10:] + [f]               # ~320 ms pre-roll
                ring = (ring + [f])[-10:]

    # ---------- speaking ----------
    def _prepare_fillers(self):
        """Pre-synthesise fillers + acknowledgements (and warm Kokoro) so they play with ~0 ms delay.
        Also load Smart Turn + whisper now: lazily loaded, the first turn-end check stalled ~2.5 s."""
        try:
            turn.complete_prob(np.zeros(SR, dtype=np.float32))
            self._stt.submit(stt.transcribe, np.zeros(SR, dtype=np.float32)).result()
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
    def _handle(self, text: str, audio: np.ndarray | None):
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
        sp, chunker, lint, result = Speaker(self, mood), ClauseChunker(), StreamLint(), {}

        def on_delta(d: str):
            for piece in chunker.feed(d):
                if (piece := lint.feed(piece)) is not None:
                    sp.add(piece)

        def work():
            try:
                result["reply"] = self.engine.turn(text, voice_emotion=voice, on_delta=on_delta, on_ack=sp.ack)
            except Exception as e:
                result["reply"] = "Sorry, kuch gadbad ho gayi."
                print(f"[turn] {type(e).__name__}: {e}")
            try:
                if self.engine.streamed:
                    for piece in chunker.flush():
                        if (piece := lint.feed(piece)) is not None:
                            sp.add(piece)
                else:                                   # fast path / tools / offline: whole reply at once
                    for piece in sentences(speakable(result["reply"])):
                        sp.add(piece)
            finally:
                sp.close()

        threading.Thread(target=work, daemon=True).start()
        left = sp.run()
        if left:
            self._resume = (left, mood)
        self.last_activity = time.time()
        print(f"Stiti: {result.get('reply', '…')}")
        if self.debug:
            ms = lambda x: f"{x:.0f} ms" if x is not None else "—"  # noqa: E731
            print(f"   ↳ first text {ms(sp.first_text_ms)} → first audio {ms(sp.first_audio_ms)} after turn start"
                  f" · {self.engine.last_debug}")

    def run(self, stop: threading.Event | None = None):
        stop = stop or threading.Event()
        print("🎙️  Listening for “Stiti”, “Hi Stiti” or “Wake up baby girl”…  (stop her anytime: “shut up”, “bye”, “chalo”)")
        print(f"   echo cancellation {'ON — interrupt her anytime' if self.aec else 'OFF — half-duplex'}")
        threading.Thread(target=self._segmenter, args=(stop,), daemon=True).start()
        with Duplex(self._on_mic, aec=self.aec) as d:
            self.duplex = d
            while not stop.is_set():
                try:
                    seg, spec = self.segq.get(timeout=0.5)
                except queue.Empty:
                    seg, spec = None, None
                now = time.time()
                if self.awake and now - self.last_activity > AWAKE_TIMEOUT_S and not d.playing:
                    self.awake = False
                    self._chime(up=False)
                    print("💤 (sleeping — say “Hey Stiti” to wake me)")
                if seg is None or len(seg) < SR * 0.3:
                    continue
                if _tutor_active():                     # a whiteboard lesson owns the mic right now
                    self.awake = False
                    continue
                # one pass serves wake check + command; usually already done (started early in the pause)
                text, ms = (spec or self._stt.submit(stt.transcribe, seg)).result()
                if not text:
                    continue
                engaged = self.awake or now - self.last_activity < 10      # awake, or she just spoke (a nudge)
                if engaged and (wake.is_stop(text) or wake.is_sleep(text)):
                    print(f"You: {text}")
                    if wake.is_goodbye(text) and not self.silenced:
                        from ..farewell import farewell
                        self.say(farewell(text, self.engine.last_mood))
                    self.deactivate()
                    continue
                if self.awake and self._resume and wake.is_backchannel(text):
                    parts, mood = self._resume       # he only said "haan" — carry on
                    self._speak(parts, mood)
                    continue
                self._resume = None
                if not self.awake:
                    if self.debug:
                        print(f"   (heard while asleep: {text!r}, {ms:.0f} ms)")
                    woke, rest = wake.detect(text)
                    if not woke:
                        continue
                    self.awake, self.silenced, self.last_activity = True, False, now
                    router.warm()                       # reconnect to the LLM while the chime plays
                    self._chime(up=True)
                    if len(rest.split()) >= 2:   # "Hey Stiti, what are my todos" -> handle at once
                        print(f"You: {rest}")
                        self._handle(rest, seg)
                    else:
                        self.say(self.engine.greet())
                    continue
                print(f"You: {text}" + (f"   ({ms:.0f} ms STT)" if self.debug else ""))
                self.last_activity = now
                self._handle(text, seg)


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
