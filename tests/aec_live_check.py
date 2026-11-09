"""Live AEC check on real hardware: Stiti talks through the laptop speakers while the mic listens.
Counts VAD 'speech' frames heard during her own playback, with AEC off vs on (lower = better).
uv run python tests/aec_live_check.py
"""
import time
import numpy as np
from stiti.voice.duplex import Duplex
from stiti.voice.tts import TTS
from stiti.voice.vad import VAD, FRAME

tts = TTS()
audio, sr = tts.synth("Hello Tejmul! This is Stiti testing echo cancellation. I am talking through the laptop "
                      "speakers right now, and the microphone should not hear me as a person speaking.")
for aec in (False, True):
    vad, buf, probs, raw_peak = VAD(), [np.zeros(0, np.float32)], [], [0.0]
    def on_mic(x):
        raw_peak[0] = max(raw_peak[0], float(np.abs(x).max()))
        buf[0] = np.concatenate([buf[0], x])
        while len(buf[0]) >= FRAME:
            f, buf[0] = buf[0][:FRAME], buf[0][FRAME:]
            probs.append(vad.prob(f))
    with Duplex(on_mic, aec=aec) as d:
        time.sleep(1.0)            # let AEC settle on silence
        probs.clear()
        d.play(audio, sr)
        while d.playing:
            time.sleep(0.05)
        time.sleep(0.3)
    p = np.array(probs)
    print(f"AEC {'ON ' if aec else 'OFF'}: {len(p)} frames during playback · speech frames (p>0.5): {(p > 0.5).sum()} "
          f"({(p > 0.5).mean() * 100:.0f}%) · mean p {p.mean():.2f} · mic peak {raw_peak[0]:.3f}")
