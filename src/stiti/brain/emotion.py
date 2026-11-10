"""Emotion state: a soft, personally calibrated, fused HINT — never a verdict (report §Emotion).

Sources now: text mood (exemplar kNN) + wording intensity. Voice (emotion2vec+ base + prosody)
plugs into `voice` when the voice pipeline lands. Personal baseline = his usual mood over 30 days.
Denials ("I'm not angry") are stored as labels for calibration.
D28: when the voice read comes from his PERSONAL head (learn/personal.py — trained nightly on his own labelled
turns, switched on only when it beat the generic model), its calibrated probability is trusted (bar 0.55, not 0.75).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..db import q

INTENSIFIERS = re.compile(r"(!{2,}|\b(so|very|bahut|bohot|really|itna|ekdum|totally)\b|[A-Z]{4,})")
PERSONAL_BAR = 0.55                 # a calibrated personal voice read needs this much to change the mood
DENIAL = re.compile(r"\b(i'?m not|main .* nahi hoon|not (angry|stressed|sad|upset)|gussa nahi)\b", re.I)


@dataclass
class EmotionState:
    label: str = "calm"
    conf: float = 0.0
    text_label: str | None = None
    text_conf: float = 0.0
    voice_label: str | None = None
    voice_conf: float = 0.0
    arousal: float = 0.3
    baseline: str | None = None
    denial: bool = False
    extras: dict = field(default_factory=dict)

    def as_json(self) -> dict:
        return {"label": self.label, "conf": round(self.conf, 2), "text": self.text_label,
                "text_conf": round(self.text_conf, 2), "voice": self.voice_label,
                "voice_conf": round(self.voice_conf, 2), "arousal": round(self.arousal, 2),
                "baseline": self.baseline, "denial": self.denial,
                "voice_src": self.extras.get("voice_src")}

    def hint(self) -> str:
        """Line for the briefing's [RIGHT NOW] section."""
        parts = [f"words: {self.text_label} {self.text_conf:.2f}"] if self.text_label else []
        if self.voice_label:
            parts.append(f"voice: {self.voice_label} {self.voice_conf:.2f}")
        if self.baseline:
            parts.append(f"usual mood: {self.baseline}")
        if self.denial:
            parts.append("they say they are NOT feeling that — believe them")
        return " · ".join(parts) + " (a hint: adapt how you talk; don't announce it or ask about feelings)"


def baseline() -> str | None:
    row = q("""SELECT emotion->>'label' AS l, count(*) n FROM episodes
               WHERE speaker='user' AND emotion IS NOT NULL AND occurred_at > now() - interval '30 days'
               GROUP BY 1 ORDER BY n DESC LIMIT 1""")
    return row[0]["l"] if row else None


def fuse(text: str, text_label: str | None, text_conf: float,
         voice_label: str | None = None, voice_conf: float = 0.0) -> EmotionState:
    s = EmotionState(text_label=text_label, text_conf=text_conf, voice_label=voice_label, voice_conf=voice_conf)
    s.baseline = baseline()
    s.denial = bool(DENIAL.search(text))
    s.arousal = min(1.0, 0.3 + 0.2 * len(INTENSIFIERS.findall(text)))
    from ..learn import personal
    src = personal.provenance(voice_label, voice_conf) if voice_label else None
    s.extras["voice_src"] = src
    bar = 0.75
    if voice_label and src == "personal":
        # D28: his personal head beat the generic model on his held-out turns and is temperature-calibrated,
        # so its probability IS the confidence; the text only nudges it (text mood is ~50% reliable).
        s.label, s.conf, bar = voice_label, voice_conf, PERSONAL_BAR
        if text_label == voice_label:
            s.conf = min(0.95, voice_conf + 0.1 * text_conf)
        elif text_label and text_label != "calm" and text_conf >= 0.75:     # his words say a different mood
            if text_conf > voice_conf:
                s.label, s.conf = text_label, text_conf * 0.8
            else:
                s.conf = voice_conf * 0.8
    else:
        # weighted vote: voice (when present) counts more for arousal-type moods; text for content moods
        votes: dict[str, float] = {}
        if text_label:
            votes[text_label] = votes.get(text_label, 0) + text_conf
        if voice_label:
            w = 1.2 if voice_label in ("angry", "stressed", "happy") else 0.8
            votes[voice_label] = votes.get(voice_label, 0) + w * voice_conf
        if votes:
            s.label, top = max(votes.items(), key=lambda kv: kv[1])
            total = sum(votes.values()) or 1
            s.conf = min(0.95, top / total * max(text_conf, voice_conf))
    if s.denial:  # believe him over the classifier
        s.label, s.conf = "calm", 0.5
    if s.label != "calm" and s.conf < bar:  # weak signal -> neutral (text mood is only ~50% reliable)
        s.label = "calm"
    return s
