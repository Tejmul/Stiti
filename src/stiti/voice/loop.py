"""Always-on voice loop: SLEEPING ⇄ AWAKE.

SLEEPING: mic → VAD → (speech segment) → whisper-base wake check → "Stiti"/"Hey Stiti"/
          "Wake up baby girl" → rising chime → AWAKE (any words after the phrase are handled at once)
AWAKE:    segment → whisper-turbo → prosody hint → engine.turn() → Kokoro (sentence streaming)
          stays awake until ~20 s of quiet or "so jao" / "go to sleep" → falling chime → SLEEPING
Barge-in (stop talking when he speaks) is on only with --headphones: laptop speakers would
trigger it with Stiti's own voice (research: AEC needed). Otherwise half-duplex.
"""
from __future__ import annotations

import os
import queue
import time

import numpy as np
import sounddevice as sd

from . import prosody, stt, wake
from .tts import TTS, chime
from .vad import FRAME, SR, VAD

AWAKE_TIMEOUT_S = float(os.getenv("STITI_AWAKE_TIMEOUT", "20"))


class VoiceLoop:
    def __init__(self, engine, headphones: bool = False, debug: bool = False):
        self.engine = engine
        self.headphones = headphones
        self.debug = debug
        self.vad = VAD()
        self.tts = TTS()
        self.frames: queue.Queue[np.ndarray] = queue.Queue()
        self.awake = False
        self.last_activity = 0.0
        self.end_silence_ms = int(os.getenv("STITI_END_SILENCE_MS", "800"))

    # ---------- audio in ----------
    def _cb(self, indata, frames, t, status):
        self.frames.put(indata[:, 0].copy())

    def _segments(self):
        """Yield speech segments from the live mic (VAD + pre-roll + end-of-turn silence)."""
        buf = np.zeros(0, dtype=np.float32)
        cur, silence, ring, speech_ms = [], 0, [], 0
        while True:
            try:
                chunk = self.frames.get(timeout=0.5)
            except queue.Empty:
                yield None  # heartbeat for timeouts
                continue
            buf = np.concatenate([buf, chunk])
            while len(buf) >= FRAME:
                f, buf = buf[:FRAME], buf[FRAME:]
                if self.tts.speaking and not self.headphones:
                    cur, silence, ring = [], 0, []   # half-duplex: ignore our own voice
                    continue
                p = self.vad.prob(f)
                if self.tts.speaking and self.headphones and p > 0.7:
                    speech_ms += 32
                    if speech_ms >= 300:
                        self.tts.stop()              # barge-in
                else:
                    speech_ms = 0
                if cur:
                    cur.append(f)
                    silence = 0 if p >= 0.5 else silence + 32
                    end = self.end_silence_ms if len(cur) * 32 > 1500 else self.end_silence_ms + 400
                    if silence >= end or len(cur) * 32 > 30000:
                        yield np.concatenate(cur)
                        cur, silence = [], 0
                elif p >= 0.5:
                    cur = ring[-10:] + [f]           # ~320 ms pre-roll
                ring = (ring + [f])[-10:]

    # ---------- behaviour ----------
    def _say(self, text: str, mood: str = "calm"):
        print(f"Stiti: {text}")
        self.tts.say(text, mood)
        self.last_activity = time.time()

    def _handle(self, text: str, audio: np.ndarray | None):
        if wake.is_sleep(text):
            self._say("Theek hai, jab zarurat ho bula lena.")
            chime(up=False)
            self.awake = False
            return
        voice = None
        if audio is not None:
            label, conf, _ = prosody.update_and_score(prosody.features(audio, SR, len(text.split())))
            voice = (label, conf) if label else None
        reply = self.engine.turn(text, voice_emotion=voice)
        if self.debug:
            print(f"   ↳ {self.engine.last_debug}")
        self._say(reply, self.engine.last_mood or "calm")

    def run(self):
        print("🎙️  Stiti is listening for “Stiti”, “Hey Stiti” or “Wake up baby girl”… (Ctrl+C to quit)")
        if not self.headphones:
            print("   (laptop speakers: barge-in off. Use --headphones to interrupt her mid-sentence.)")
        with sd.InputStream(samplerate=SR, channels=1, dtype="float32", blocksize=FRAME, callback=self._cb):
            for seg in self._segments():
                now = time.time()
                if self.awake and now - self.last_activity > AWAKE_TIMEOUT_S and not self.tts.speaking:
                    self.awake = False
                    chime(up=False)
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
                    chime(up=True)
                    if len(rest.split()) >= 2:   # "Hey Stiti, what are my todos" -> handle at once
                        print(f"You: {rest}")
                        self._handle(rest, seg)
                    else:
                        self._say(self.engine.greet())
                    continue
                print(f"You: {text}" + (f"   ({ms:.0f} ms STT)" if self.debug else ""))
                self.last_activity = now
                self._handle(text, seg)
