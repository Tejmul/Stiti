"""Always-on voice loop: SLEEPING ⇄ AWAKE, full-duplex with WebRTC echo cancellation.

SLEEPING  mic (AEC-cleaned) → VAD → speech segment → whisper → wake phrase?
          "Stiti" / "Hi/Hey/Hello Stiti" / "Wake up baby girl" / "uth jao Stiti" → rising chime → AWAKE
AWAKE     segment → whisper → engine.turn() → Kokoro, sentence-streamed through the duplex stream.
STOP      "shut up" / "chup" / "okay" / "chalo" / "bye" / "bas" / "stop" (alone) → she stops at once,
          falling chime, NO talking — and stays silent (her voice nudges too) until a wake phrase.
Turn-end  Smart Turn v3.2 on a 300 ms pause: finished → answer now; unfinished → wait (≤2 s silence).
Barge-in  he talks over her ≥450 ms → she stops. If it was only "haan"/"hmm" she resumes her sentence.
Filler    if a reply takes >0.8 s she says "hmm…" so the silence never feels dead.
"""
from __future__ import annotations

import os
import queue
import random
import threading
import time

import numpy as np

from . import prosody, stt, turn, wake
from .duplex import Duplex
from .tts import TTS, chime_audio, sentences, speakable
from .vad import FRAME, SR, VAD

AWAKE_TIMEOUT_S = float(os.getenv("STITI_AWAKE_TIMEOUT", "20"))
BARGE_MS = 450
PAUSE_CHECK_MS = 300          # ask Smart Turn after this much silence
FALLBACK_SILENCE_MS = 2000    # end the turn anyway after this much silence
FILLERS = ["Hmm.", "Ek sec.", "Haan, dekhti hoon."]


class VoiceLoop:
    def __init__(self, engine, aec: bool = True, debug: bool = False):
        self.engine = engine
        self.aec = aec
        self.debug = debug
        self.vad = VAD()
        self.tts = TTS()
        self.micq: queue.Queue[np.ndarray] = queue.Queue()
        self.segq: queue.Queue[np.ndarray] = queue.Queue()
        self.awake = False
        self.silenced = False            # True after a stop word: no voice at all until a wake phrase
        self.last_activity = 0.0
        self.duplex: Duplex | None = None
        self.paused = threading.Event()  # menubar "mute"
        self._interrupted = threading.Event()
        self._resume: tuple[list[str], str] | None = None
        self._fillers: list[tuple[np.ndarray, int]] = []
        threading.Thread(target=self._prepare_fillers, daemon=True).start()

    # ---------- audio in: callback only queues; segmentation runs in its own thread ----------
    def _on_mic(self, x16: np.ndarray):
        if not self.paused.is_set():
            self.micq.put(x16)

    def _segmenter(self, stop: threading.Event):
        buf = np.zeros(0, dtype=np.float32)
        cur: list[np.ndarray] = []
        ring: list[np.ndarray] = []
        silence = speech_ms = 0
        checked = False
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
                        silence, checked = 0, False
                        continue
                    silence += 32
                    end = False
                    if silence >= PAUSE_CHECK_MS and not checked:
                        checked = True
                        try:
                            end = turn.complete_prob(np.concatenate(cur)) >= 0.5
                        except Exception:
                            end = silence >= 800
                    if end or silence >= FALLBACK_SILENCE_MS or len(cur) * 32 > 30000:
                        self.segq.put(np.concatenate(cur))
                        cur, silence, checked = [], 0, False
                elif p >= 0.5:
                    cur = ring[-10:] + [f]               # ~320 ms pre-roll
                ring = (ring + [f])[-10:]

    # ---------- speaking ----------
    def _prepare_fillers(self):
        try:
            self._fillers = [self.tts.synth(t, "calm") for t in FILLERS]
        except Exception:
            self._fillers = []

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
        self._interrupted.clear()
        self._resume = None
        for i, s in enumerate(parts):
            if self._interrupted.is_set():
                self._resume = (parts[i - 1:] if i else parts, mood)   # re-say the cut sentence if he only said "haan"
                break
            audio, sr = self.tts.synth(s, mood)
            self._play(audio, sr)
            if self._interrupted.is_set():
                self._resume = (parts[i:], mood)
                break
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
        result: dict = {}
        th = threading.Thread(target=lambda: result.update(reply=self.engine.turn(text, voice_emotion=voice)))
        th.start()
        th.join(0.8)
        if th.is_alive() and self._fillers:          # thinking out loud instead of dead air
            self._interrupted.clear()
            self._play(*random.choice(self._fillers))
        th.join()
        if self.debug:
            print(f"   ↳ {self.engine.last_debug}")
        self.say(result.get("reply", "Sorry, kuch gadbad ho gayi."), self.engine.last_mood or "calm")

    def run(self, stop: threading.Event | None = None):
        stop = stop or threading.Event()
        print("🎙️  Listening for “Stiti”, “Hi Stiti” or “Wake up baby girl”…  (stop her anytime: “shut up”, “bye”, “chalo”)")
        print(f"   echo cancellation {'ON — interrupt her anytime' if self.aec else 'OFF — half-duplex'}")
        threading.Thread(target=self._segmenter, args=(stop,), daemon=True).start()
        with Duplex(self._on_mic, aec=self.aec) as d:
            self.duplex = d
            while not stop.is_set():
                try:
                    seg = self.segq.get(timeout=0.5)
                except queue.Empty:
                    seg = None
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
                text, ms = stt.transcribe(seg)          # one pass serves wake check + command
                if not text:
                    continue
                engaged = self.awake or now - self.last_activity < 10      # awake, or she just spoke (a nudge)
                if engaged and (wake.is_stop(text) or wake.is_sleep(text)):
                    print(f"You: {text}")
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
