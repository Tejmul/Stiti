"""Voice end-to-end latency (no mic/speaker): speech end -> STT -> wake -> engine.turn -> first TTS sentence.
STITI_DB=postgresql:///stiti_test uv run python tests/voice_e2e_eval.py
"""
import os, resource, sys, time
import numpy as np
if "stiti_test" not in os.getenv("STITI_DB", ""):
    sys.exit("refusing: set STITI_DB=postgresql:///stiti_test")
from stiti import embed, intent
from stiti.engine import Engine
from stiti.voice import prosody, stt, wake
from stiti.voice.tts import TTS, sentences, speakable

tts = TTS(); embed.embed_query("warm"); intent._index(); stt.transcribe(np.zeros(16000, np.float32))
eng = Engine("voice")
LINES = ["Hey Stiti, add todo buy milk", "Stiti, kal subah 6 baje alarm laga do", "Hey Stiti, what are my todos",
         "Hey Stiti, itna lamba mat bolo yaar", "Wake up baby girl, meri sister Priya Pune mein rehti hai, yaad rakhna"]
for line in LINES:
    a, sr = tts.synth(line)
    a16 = np.interp(np.linspace(0, len(a), int(len(a) * 16000 / sr), endpoint=False), np.arange(len(a)), a).astype(np.float32)
    t0 = time.perf_counter()
    text, ms_stt = stt.transcribe(a16)
    woke, rest = wake.detect(text)
    lab, conf, _ = prosody.update_and_score(prosody.features(a16, 16000, len(text.split())))
    t1 = time.perf_counter()
    reply = eng.turn(rest or text, voice_emotion=(lab, conf) if lab else None)
    t2 = time.perf_counter()
    first = sentences(speakable(reply))[0]
    tts.synth(first, eng.last_mood or "calm")
    t3 = time.perf_counter()
    print(f"woke={woke} heard={rest!r}\n   Stiti: {reply}\n   stt {ms_stt:.0f} · engine {(t2-t1)*1000:.0f} · first-audio TTS {(t3-t2)*1000:.0f} "
          f"→ speech-end→first-audio {(t3-t0)*1000:.0f} ms  [{eng.last_debug['route']}]")
print(f"maxRSS {resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1e6:.0f} MB (embedder + whisper-small + kokoro + VAD + engine)")
