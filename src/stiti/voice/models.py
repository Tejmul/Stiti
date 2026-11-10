"""Small local voice models, fetched once into ~/.stiti/models (real files, no symlinks)."""
from __future__ import annotations

import urllib.request
from pathlib import Path

from ..config import CFG

DIR = CFG.home / "models" / "voice"
FILES = {
    "silero_vad.onnx": "https://github.com/snakers4/silero-vad/raw/master/src/silero_vad/data/silero_vad.onnx",
    "kokoro-v1.0.int8.onnx": "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.int8.onnx",
    "voices-v1.0.bin": "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin",
}
WHISPER_MAIN = "mlx-community/whisper-small-mlx-q4"   # commands: 283 ms vs turbo 1,064 ms on M2, ~same Hinglish
# accuracy in tests/voice_offline_eval.py; set STITI_WHISPER=mlx-community/whisper-large-v3-turbo-q4 for max accuracy
WHISPER_WAKE = "mlx-community/whisper-base-mlx-q4"         # cheap wake-phrase spotting

# goonj-1-82M (Apache-2.0, Kokoro fine-tuned on Indian-English + Hindi personas), exported to ONNX int8 by
# scripts/goonj_export.py (`stiti voices install`). There is no hosted ONNX, so it is never auto-downloaded here.
GOONJ_DIR = CFG.home / "models" / "goonj"
GOONJ_MODEL, GOONJ_VOICES = "goonj.int8.onnx", "goonj-voices.bin"


def goonj_ready() -> bool:
    return (GOONJ_DIR / GOONJ_MODEL).exists() and (GOONJ_DIR / GOONJ_VOICES).exists()


def path(name: str) -> Path:
    DIR.mkdir(parents=True, exist_ok=True)
    p = DIR / name
    if not p.exists():
        print(f"[stiti] downloading {name} …")
        tmp = p.with_suffix(p.suffix + ".part")
        urllib.request.urlretrieve(FILES[name], tmp)
        tmp.rename(p)
    return p
