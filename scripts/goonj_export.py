"""One-time export of goonj-1-82M (Apache-2.0 Kokoro fine-tune, Indian-English personas) to ONNX int8 for Stiti's
kokoro_onnx runtime (D27). There is no hosted ONNX build, so this downloads the PyTorch weights from Hugging Face,
exports with kokoro-onnx's input names (tokens / style / speed), quantizes to int8 (114 MB) and packs the persona
style vectors into an .npz voices file. Needs torch + kokoro only for this run, in a throwaway env:

  uv run --isolated --with kokoro==0.9.4 --with torch --with onnx --with onnxruntime --with huggingface_hub \
      python scripts/goonj_export.py --out ~/.stiti/models/goonj

(`stiti voices install` runs exactly this.) Outputs: goonj.int8.onnx + goonj-voices.bin.
"""
from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

REPO = "BH-Builds/goonj-1-82M"
PERSONAS = ["en_aman", "en_ananya", "en_arjun", "en_dev", "en_divya", "en_kabir", "en_nisha", "en_priya", "en_sameer",
            "en_tara", "hi_atul", "hi_meera", "hi_ravi", "hi_shivani"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(Path.home() / ".stiti" / "models" / "goonj"))
    out = Path(ap.parse_args().out).expanduser()
    out.mkdir(parents=True, exist_ok=True)

    import numpy as np
    import torch
    from huggingface_hub import hf_hub_download
    from kokoro.model import KModel, KModelForONNX
    from onnxruntime.quantization import QuantType, quantize_dynamic

    km = KModel(repo_id="hexgrad/Kokoro-82M", config=hf_hub_download(REPO, "config.json"),
                model=hf_hub_download(REPO, "kokoro_hindi_final.pth"), disable_complex=True).eval()
    m = KModelForONNX(km).eval()
    tokens = torch.randint(1, 100, (1, 48), dtype=torch.long)
    tokens[0, 0] = tokens[0, -1] = 0
    with tempfile.TemporaryDirectory() as tmp:
        fp32 = Path(tmp) / "goonj.onnx"
        torch.onnx.export(m, (tokens, torch.randn(1, 256), torch.tensor([1.0])), str(fp32),
                          input_names=["tokens", "style", "speed"], output_names=["audio"],
                          dynamic_axes={"tokens": {1: "sequence_length"}, "audio": {0: "audio_length"}},
                          opset_version=17, do_constant_folding=True, dynamo=False)
        quantize_dynamic(str(fp32), str(out / "goonj.int8.onnx"), weight_type=QuantType.QInt8)
    packs = {n: torch.load(hf_hub_download(REPO, f"voices/{n}.pt"), weights_only=True).numpy().astype(np.float32)
             for n in PERSONAS}
    with open(out / "goonj-voices.bin", "wb") as f:              # an .npz under the name kokoro_onnx expects
        np.savez(f, **packs)
    print(f"goonj ready in {out}: {(out / 'goonj.int8.onnx').stat().st_size // 1_000_000} MB model, "
          f"{len(packs)} personas")


if __name__ == "__main__":
    main()
