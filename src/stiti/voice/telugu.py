"""Telugu / Tenglish → Kokoro phonemes (D34): Telugu-script runs through espeak `te`, Latin runs through `en-us`,
joined into one phoneme string, so any Kokoro voice (the owner picked hf_alpha) reads "రేపు morning six కి alarm
set చేశాను" naturally. Measured 2026-11-11: espeak-ng has Telugu (రేపు → rˈeːpu)."""
from __future__ import annotations

import re

TE_RUN = re.compile(r"[ఀ-౿‌]+(?:[\s‌]+[ఀ-౿‌]+)*")


def has(text: str) -> bool:
    return bool(re.search(r"[ఀ-౿]", text or ""))


def phonemize(text: str, tokenizer) -> str | None:
    """Phoneme string for a line with Telugu script, or None (no Telugu in it)."""
    if not has(text):
        return None
    parts, pos = [], 0
    for m in TE_RUN.finditer(text):
        lat = text[pos:m.start()].strip(" ,")
        if re.search(r"[A-Za-z0-9]", lat):
            parts.append(tokenizer.phonemize(lat, "en-us"))
        elif lat.strip() in (".", "!", "?", ","):
            parts.append(lat.strip())
        parts.append(tokenizer.phonemize(m.group(0), "te"))
        pos = m.end()
    tail = text[pos:].strip()
    if re.search(r"[A-Za-z0-9]", tail):
        parts.append(tokenizer.phonemize(tail, "en-us"))
    elif tail in (".", "!", "?"):
        parts.append(tail)
    out = re.sub(r"\s+", " ", " ".join(p for p in parts if p)).strip()
    return out or None
