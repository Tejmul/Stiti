"""Always-on voice loop: SLEEPING ⇄ AWAKE, full-duplex with WebRTC echo cancellation.

SLEEPING: mic (AEC-cleaned) → VAD → speech segment → whisper → wake phrase?
          "Stiti" / "Hey Stiti" / "Wake up baby girl" → rising chime → AWAKE
AWAKE:    segment → whisper → prosody hint (+ emotion2vec+ in background) → engine.turn() →
          Kokoro, sentence-streamed through the duplex stream (so AEC knows what she says).
          He talks over her for ≥300 ms → she stops (barge-in; measured 0% self-trigger with AEC).
          ~20 s quiet or "so jao" / "go to sleep" → falling chime → SLEEPING.
"""
from __future__ import annotations

import os
import queue
import threading
import time

import numpy as np

from . import prosody, stt, wake
from .duplex import Duplex
from .tts import TTS, chime_audio, sentences, speakable
from .vad import FRAME, SR, VAD

AWAKE_TIMEOUT_S = float(os.getenv("STITI_AWAKE_TIMEOUT", "20"))
BARGE_MS = 300


class VoiceLoop:
    def __init__(self, engine, aec: bool = True, debug: bool = False):
        self.engine = engine
        self.aec = aec
        self.debug = debug
        self.vad = VAD()
        self.tts = TTS()
        self.segq: queue.Queue[np.ndarray] = queue.Queue()
        self.awake = False
        self.last_activity = 0.0
        self.end_silence_ms = int(os.getenv("STITI_END_SILENCE_MS", "800"))
        self.duplex: Duplex | None = None
        self.paused = threading.Event()          # menubar "mute" toggle
        self._interrupted = threading.Event()
        self._buf = np.zeros(0, dtype=np.float32)
        self._cur: list[np.ndarray] = []
        self._ring: list[np.ndarray] = []
        self._silence = 0
        self._speech_ms = 0

    # ---------- audio in (callback thread; VAD <1 ms per 32 ms frame) ----------
    def _on_mic(self, x16: np.ndarray):
        if self.paused.is_set():
            return
        self._buf = np.concatenate([self._buf, x16])
        while len(self._buf) >= FRAME:
            f, self._buf = self._buf[:FRAME], self._buf[FRAME:]
            p = self.vad.prob(f)
            if self.duplex is not None and self.duplex.playing:
                self._speech_ms = self._speech_ms + 32 if p > 0.6 else 0
                if not self.aec:
                    self._cur, self._silence = [], 0              # half-duplex without AEC
                    continue
                if self._speech_ms >= BARGE_MS:                   # barge-in
                    self.duplex.stop_playback()
                    self._interrupted.set()
            if self._cur:
                self._cur.append(f)
                self._silence = 0 if p >= 0.5 else self._silence + 32
                end = self.end_silence_ms if len(self._cur) * 32 > 1500 else self.end_silence_ms + 400
                if self._silence >= end or len(self._cur) * 32 > 30000:
                    self.segq.put(np.concatenate(self._cur))
                    self._cur, self._silence = [], 0
            elif p >= 0.5:
                self._cur = self._ring[-10:] + [f]               # ~320 ms pre-roll
            self._ring = (self._ring + [f])[-10:]

    # ---------- speaking ----------
    def _play(self, audio: np.ndarray, sr: int):
        self.duplex.play(audio, sr)
        while self.duplex.playing and not self._interrupted.is_set():
            time.sleep(0.02)

    def say(self, text: str, mood: str = "calm"):
        print(f"Stiti: {text}")
        self._interrupted.clear()
        for s in sentences(speakable(text)):
            if self._interrupted.is_set():
                print("   (interrupted)")
                break
            audio, sr = self.tts.synth(s, mood)
            self._play(audio, sr)
        self.last_activity = time.time()

    def _chime(self, up: bool):
        a, sr = chime_audio(up)
        self._play(a, sr)

    # ---------- behaviour ----------
    def _handle(self, text: str, audio: np.ndarray | None):
        if wake.is_sleep(text):
            self.say("Theek hai, jab zarurat ho bula lena.")
            self._chime(up=False)
            self.awake = False
            return
        voice = None
        if audio is not None:
            label, conf, _ = prosody.update_and_score(prosody.features(audio, SR, len(text.split())))
            deep = _deep_last
            if deep and deep[1] > conf:
                label, conf = deep
            voice = (label, conf) if label else None
            _deep_emotion_async(audio)
        reply = self.engine.turn(text, voice_emotion=voice)
        if self.debug:
            print(f"   ↳ {self.engine.last_debug}")
        self.say(reply, self.engine.last_mood or "calm")

    def run(self, stop: threading.Event | None = None):
        print("🎙️  Listening for “Stiti”, “Hey Stiti” or “Wake up baby girl”…")
        print(f"   echo cancellation {'ON — interrupt her anytime' if self.aec else 'OFF — half-duplex'}")
        with Duplex(self._on_mic, aec=self.aec) as d:
            self.duplex = d
            while not (stop and stop.is_set()):
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
                text, ms = stt.transcribe(seg)          # one pass serves wake check + command
                if not text:
                    continue
                if not self.awake:
                    if self.debug:
                        print(f"   (heard while asleep: {text!r}, {ms:.0f} ms)")
                    woke, rest = wake.detect(text)
                    if not woke:
                        continue
                    self.awake, self.last_activity = True, now
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


# ---------- deep voice emotion (emotion2vec+ base), background only, never on the critical path ----------
_deep_last: tuple[str, float] | None = None


def _deep_emotion_async(audio: np.ndarray):
    if os.getenv("STITI_VOICE_EMOTION", "emotion2vec") == "off":
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
