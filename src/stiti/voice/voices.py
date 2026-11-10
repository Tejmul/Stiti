"""`stiti voices` — see, try, pick and install Stiti's voice (D27).

  stiti voices                     list personas, the current one, and whether goonj is installed
  stiti voices try <persona> [txt] speak a sample line with that persona
  stiti voices use <persona>       save it (owner_profile `voice`; STITI_VOICE still wins if set)
  stiti voices install [--from D]  get goonj: copy an existing export from D, or export it (scripts/goonj_export.py)
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from . import models

# heard in the research samples (docs/research/stt_tts_indian_english.md §C): priya + tara female, arjun male
HEARD = {"en_priya": "female, recommended", "en_tara": "female", "en_arjun": "male"}
SAMPLE = "Hey, your meeting with the placement team is at three thirty. Okay yaar, I added it to your todos."


def personas() -> list[str]:
    if not models.goonj_ready():
        return []
    import numpy as np
    v = np.load(models.GOONJ_DIR / models.GOONJ_VOICES)
    return sorted(n for n in v.files if n[:3] in ("en_", "hi_"))


def status() -> str:
    from .tts import DEFAULT_VOICE, resolve, voice_setting
    setting = voice_setting()
    engine, voice = resolve(setting)
    lines = [f"Voice setting: {setting}  →  speaking with {'goonj:' if engine == 'goonj' else 'Kokoro '}{voice}"]
    if os.getenv("STITI_VOICE"):
        lines.append("  (from STITI_VOICE; unset it to use the saved choice)")
    ps = personas()
    if not ps:
        lines.append(f"goonj not installed in {models.GOONJ_DIR} → fallback Kokoro af_heart (American).")
        lines.append("Install the Indian-English voice:  stiti voices install")
        return "\n".join(lines)
    lines.append(f"goonj installed ({models.GOONJ_DIR}). Personas (English ones speak Indian English):")
    for p in ps:
        mark = "★" if engine == "goonj" and p == voice else " "
        lines.append(f"  {mark} {p:12} {HEARD.get(p, '')}")
    lines.append(f"Default: {DEFAULT_VOICE}. Try one: stiti voices try en_tara · keep it: stiti voices use en_tara")
    return "\n".join(lines)


def try_voice(persona: str, text: str | None = None) -> str:
    import sounddevice as sd

    from .tts import TTS
    t = TTS(persona if ":" in persona or persona.startswith("af_") else f"goonj:{persona}")
    audio, sr = t.synth_on_worker(text or SAMPLE)
    sd.play(audio, sr)
    sd.wait()
    return f"(spoke with {t.name})"


def use(persona: str) -> str:
    from .. import profile
    value = persona if ":" in persona or not persona.startswith(("en_", "hi_")) else f"goonj:{persona}"
    if value.startswith("goonj:") and personas() and value.split(":", 1)[1] not in personas():
        return f"No persona {value.split(':', 1)[1]!r}. Run `stiti voices` to see them."
    profile.set("voice", value, source="voices")
    return f"Saved: Stiti will speak with {value} (restart Stiti.app to hear it)."


def install(src: str | None = None) -> str:
    out = models.GOONJ_DIR
    out.mkdir(parents=True, exist_ok=True)
    if src:
        d = Path(src).expanduser()
        for f in (models.GOONJ_MODEL, models.GOONJ_VOICES):
            if not (d / f).exists():
                return f"{d / f} not found."
            shutil.copy2(d / f, out / f)
        return f"Copied goonj into {out}."
    if models.goonj_ready():
        return f"goonj is already installed in {out}."
    script = Path(__file__).resolve().parents[3] / "scripts" / "goonj_export.py"
    cmd = ["uv", "run", "--isolated", "--with", "kokoro==0.9.4", "--with", "torch", "--with", "onnx",
           "--with", "onnxruntime", "--with", "huggingface_hub", "python", str(script), "--out", str(out)]
    print("Exporting goonj-1-82M to ONNX int8 (one time: downloads ~330 MB of PyTorch weights + torch, ~2 min)…")
    r = subprocess.run(cmd)
    return "Done." if r.returncode == 0 and models.goonj_ready() else "Export failed (see above)."


def cli(args: list[str]) -> None:
    sub = args[1] if len(args) > 1 else ""
    if sub == "try" and len(args) > 2:
        print(try_voice(args[2], " ".join(args[3:]) or None))
    elif sub == "use" and len(args) > 2:
        print(use(args[2]))
    elif sub == "install":
        print(install(args[args.index("--from") + 1] if "--from" in args and len(args) > args.index("--from") + 1
                      else None))
    elif sub in ("", "list"):
        print(status())
    else:
        print(__doc__.split("\n\n", 1)[1], file=sys.stderr)
