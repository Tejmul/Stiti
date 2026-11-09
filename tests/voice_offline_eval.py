"""Offline voice-pipeline check (no mic): Kokoro speaks test lines -> 16 kHz -> VAD -> wake -> Whisper.
uv run python tests/voice_offline_eval.py
"""
import resource, time
import numpy as np
from stiti.voice import stt, wake
from stiti.voice.tts import TTS
from stiti.voice.vad import VAD, segments

LINES = [("Hey Stiti, what are my todos?", True), ("Wake up baby girl.", True), ("Stiti, set an alarm for 6 am.", True),
         ("I was talking to my friend about the city.", False), ("Remind me at 7 pm to call mummy.", None)]
t = time.perf_counter(); tts = TTS(); vad = VAD()
print(f"load tts+vad {time.perf_counter() - t:.1f}s")
for text, expect_wake in LINES:
    t = time.perf_counter(); audio, sr = tts.synth(text); t_tts = (time.perf_counter() - t) * 1000
    a16 = np.interp(np.linspace(0, len(audio), int(len(audio) * 16000 / sr), endpoint=False), np.arange(len(audio)), audio).astype(np.float32)
    a16 = np.concatenate([np.zeros(8000, np.float32), a16, np.zeros(16000, np.float32)])
    segs = segments(a16, vad)
    seg = np.concatenate(segs) if segs else a16
    wt, wms = stt.transcribe_wake(seg); woke, rest = wake.detect(wt)
    mt, mms = stt.transcribe(seg)
    flag = "" if expect_wake is None else ("OK " if woke == expect_wake else "BAD")
    print(f"{flag:3} tts {t_tts:4.0f}ms | segs {len(segs)} | wake[{wms:4.0f}ms] {wt!r} woke={woke} | stt[{mms:4.0f}ms] {mt!r}")
print(f"maxRSS {resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1e6:.0f} MB")
