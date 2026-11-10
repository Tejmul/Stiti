"""Hinglish TTS (D22): word tagging, pure English → old path, Hindi phonemes, first-clause latency, and a round-trip
intelligibility check (TTS → local Whisper → word error rate) when a Whisper model is already cached.
Offline, no DB, no speaker.  uv run python tests/hinglish_eval.py
"""
from __future__ import annotations

import difflib
import os
import re
import statistics
import sys
import time
from pathlib import Path

os.environ.setdefault("HF_HUB_OFFLINE", "1")                     # never download a model during tests
passed = total = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global passed, total
    total += 1
    passed += bool(cond)
    print(("  ✓ " if cond else "  ✗ ") + name + (f" — {detail}" if detail and not cond else ""))


from stiti.voice import hinglish                                  # noqa: E402


def hindi_words(text: str) -> list[str]:
    return [t.lower() for t, lang in hinglish.tag(text) if lang == "hi"]


# --- tagging ---
TAGS = [
    ("Haan, note kar liya. Aaj ka interview kaisa raha?",
     {"haan", "kar", "liya", "aaj", "ka", "kaisa", "raha"}, {"note", "interview"}),
    ("Main to ghar ja raha hoon.", {"main", "to", "ghar", "ja", "raha", "hoon"}, set()),
    ("Meri todo list me kya hai?", {"meri", "me", "kya", "hai"}, {"todo", "list"}),
    ("Hi Stiti, kya haal hai?", {"kya", "haal", "hai"}, {"hi", "stiti"}),
    ("Remind me to call mummy.", set(), {"remind", "me", "to", "call"}),
    ("I want to do it so fast.", set(), {"to", "do", "so"}),
    ("Kal subah 6 baje ka alarm laga do.", {"kal", "subah", "6", "baje", "ka", "laga", "do"}, {"alarm"}),
    ("Are yaar, ye kya hai!", {"are", "yaar", "ye", "kya", "hai"}, set()),
]
for text, want_hi, want_en in TAGS:
    hi = set(hindi_words(text))
    check(f"tag {text!r}", want_hi <= hi and not (want_en & hi),
          f"hindi={sorted(hi)} missing={sorted(want_hi - hi)} wrongly-hindi={sorted(want_en & hi)}")

# main → मैं (I) at clause start, में (in) after a noun
tagged = hinglish.tag("Main kal aaunga, phone ghar main hai.")
devs = [hinglish._dev(tagged, i) for i, (t, _) in enumerate(tagged) if t.lower() == "main"]
check("main → मैं at the start, में after a noun", devs == ["मैं", "में"], str(devs))

# --- pure English keeps the old path ---
for text in ["Okay, let me plan your day.", "Hmm, let me think.", "Remind me to call mummy at 7 pm.",
             "I am so tired today.", "Do it now.", "The meeting is at 3, so go to the main hall."]:
    check(f"pure English → None: {text!r}", hinglish.phonemize(text) is None, str(hinglish.phonemize(text)))

# --- Hindi phonemes ---
ph = hinglish.phonemize("Aaj ka interview kaisa raha?") or ""
check("'kaisa raha' gets Hindi phonemes (ɾ flap, long aː)", "ɾ" in ph and "aː" in ph and "ɹ" not in ph.split("ˈɪntɚ")[-1],
      ph)
check("English word inside stays English ('interview' → ɚ)", "ɚ" in ph, ph)
ph = hinglish.phonemize("Thoda stressed lag rahe ho, break le lo yaar.") or ""
check("aspirated tʰ + long oː for 'thoda' (not English th/ɑ)", ph.startswith("tʰˈoː"), ph)
ph2 = hinglish.phonemize("Chhota sa kaam hai.") or ""
check("retroflex ʈ for 'chhota'", "ʈ" in ph2 and "cʰ" in ph2, ph2)
check("punctuation kept (comma pause + full stop)", "," in ph and ph.rstrip().endswith("."), ph)
check("Devanagari input works too", "ɾ" in (hinglish.phonemize("आज का दिन कैसा रहा?") or ""))
check("ends with ? for a question", (hinglish.phonemize("Aaj kya plan hai?") or "").endswith("?"))

# --- synthesis latency + round trip (needs the local Kokoro files) ---
MODELS = Path(os.getenv("STITI_HOME", Path.home() / ".stiti")) / "models" / "voice"
REAL_MODELS = Path.home() / ".stiti" / "models" / "voice"
mdir = MODELS if (MODELS / "kokoro-v1.0.int8.onnx").exists() else REAL_MODELS
if (mdir / "kokoro-v1.0.int8.onnx").exists() and (mdir / "voices-v1.0.bin").exists():
    from stiti.voice import models
    models.DIR = mdir                                                 # run_all uses a temp STITI_HOME
    real_goonj = Path.home() / ".stiti" / "models" / "goonj"          # …so point at his installed goonj voice too,
    if not models.GOONJ_DIR.exists() and real_goonj.exists():        # or the test grades the af_heart fallback
        models.GOONJ_DIR = real_goonj
    from stiti.voice.tts import TTS
    tts = TTS()
    tts.synth_on_worker("Warm up.")
    clause = "Haan, note kar liya."
    ms = []
    for _ in range(5):
        t = time.perf_counter()
        audio, sr = tts.synth_on_worker(clause)
        ms.append((time.perf_counter() - t) * 1000)
    med = statistics.median(ms)
    check(f"first-clause Hinglish synth < 450 ms after warm-up ({med:.0f} ms)", med < 450, f"{ms}")
    check("audio is non-empty and not silent", len(audio) > sr * 0.4 and float(abs(audio).max()) > 0.05)
    a_en, _ = tts.synth_on_worker("Okay, let me plan your day.")
    check("pure English still synthesises (old path)", len(a_en) > sr * 0.5)

    hub = Path.home() / ".cache" / "huggingface" / "hub"
    judge = next((r for r in ["mlx-community/whisper-large-v3-turbo-q4", "mlx-community/whisper-small-mlx-q4"]
                  if (hub / ("models--" + r.replace("/", "--"))).exists()), None)
    if judge:
        import mlx_whisper
        import numpy as np
        from stiti.voice.stt import HINGLISH_PROMPT
        LINES = ["Haan, note kar liya. Aaj ka interview kaisa raha?", "Kal subah chhe baje ka alarm laga diya hai.",
                 "Tumhari teen todos baaki hain, pehle GitHub wala kaam karo.",
                 "Thoda stressed lag rahe ho, break le lo yaar."]

        def norm(s: str) -> list[str]:
            return re.sub(r"[^a-z0-9 ]", "", s.lower()).split()

        def wer(ref: str, hyp: str) -> float:
            r, h = norm(ref), norm(hyp)
            return 1 - sum(b.size for b in difflib.SequenceMatcher(None, r, h).get_matching_blocks()) / len(r)

        def heard(a, sr) -> str:
            a16 = np.interp(np.linspace(0, len(a), int(len(a) * 16000 / sr), endpoint=False), np.arange(len(a)), a)
            return mlx_whisper.transcribe(a16.astype(np.float32), path_or_hf_repo=judge, language="en",
                                          initial_prompt=HINGLISH_PROMPT, condition_on_previous_text=False,
                                          temperature=0.0, verbose=None)["text"]

        new = statistics.mean(wer(s, heard(*tts.synth_on_worker(s))) for s in LINES)
        old = statistics.mean(wer(s, heard(*tts.k.create(s, voice=tts.voice, lang=tts.lang))) for s in LINES)
        print(f"  round trip ({judge.split('/')[1]}): English voice {old:.0%} WER → Hinglish path {new:.0%}")
        check("Hinglish path is clearer than the old English path", new < old, f"{new:.0%} vs {old:.0%}")
        check("Hinglish round-trip WER ≤ 40%", new <= 0.40, f"{new:.0%}")
    else:
        print("  (no cached Whisper model: round-trip check skipped)")
else:
    print("  (Kokoro model files not found: latency + round-trip checks skipped)")

print(f"hinglish: {passed}/{total} checks passed")
sys.exit(0 if passed == total else 1)
