"""Decision layer: Stiti decides, not the LLM.

One Laya forward pass answers every typed question about the moment (report §Laya question set).
Deterministic rules run alongside as floors/overrides:
  - privacy: regex floor; Laya can raise it, never lower it
  - correction: Hinglish/English lexicon OR Laya
  - action within a domain: parsed by fast-path regexes
If Laya is unavailable, rules alone answer (degraded but working).
"""
from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass, field

QUESTIONS: dict[str, dict] = {
    "domain": {"type": "choice", "instructions": "What is the user asking the assistant to do?",
               "criteria": {
                   "todo": "add, list, finish or plan tasks / todos / to-do list",
                   "time": "set an alarm, reminder or timer for a time",
                   "memory": "asks about something from his past, his people or personal facts",
                   "chat": "casual talk, feelings, opinions or a general question",
                   "tool": "needs calendar, email, files, web search or the computer",
                   "feedback": "corrects or criticizes how the assistant talks or behaves",
                   "control": "stop, repeat, louder, quieter or cancel"}},
    "needs_llm": {"type": "noul", "instructions":
                  "Does replying need open-ended thinking or conversation, not just a simple command?"},
    "is_correction": {"type": "noul", "instructions":
                      "Is the user correcting or complaining about how the assistant replied or behaved?"},
    "text_emotion": {"type": "choice", "instructions": "How does the user feel right now?",
                     "criteria": {"calm": "neutral, fine, relaxed", "happy": "happy, excited, grateful",
                                  "stressed": "stressed, anxious, overwhelmed, rushed",
                                  "angry": "angry, irritated, frustrated", "sad": "sad, low, lonely, hurt",
                                  "tired": "tired, sleepy, exhausted"}},
    "tone_to_use": {"type": "choice", "instructions": "How should the assistant reply?",
                    "criteria": {"brief": "short and to the point", "warm": "friendly and caring",
                                 "playful": "light and fun", "serious": "focused and serious",
                                 "supportive": "calm, gentle and supportive"}},
    "urgency": {"type": "score", "instructions": "How urgent is this for the user?",
                "criteria": ["not urgent", "sometime soon", "today", "right now"]},
    "memory_needed": {"type": "choice", "instructions": "What past information is needed to reply well?",
                      "criteria": {"none": "nothing from the past", "recent": "what was just said",
                                   "people": "facts about people in his life",
                                   "project": "his work, projects or goals",
                                   "past_event": "something that happened before"}},
    "has_time_reference": {"type": "noul", "instructions":
                           "Does the message mention a date or time like today, tomorrow, kal, 6 baje or next week?"},
    "tool_category": {"type": "choice", "instructions": "Which tool would help?",
                      "criteria": {"calendar": "calendar or schedule", "mail": "email",
                                   "files": "files or notes", "mac": "the computer, apps, volume",
                                   "web": "web search or a website", "none": "no tool needed"}},
    "privacy_level": {"type": "choice", "instructions": "How private is this message?",
                      "criteria": {"P0": "general knowledge, nothing personal",
                                   "P1": "personal life, plans, people or feelings",
                                   "P2": "sensitive: health, money, bank, passwords, OTP, ID numbers"}},
    "worth_remembering": {"type": "score", "instructions": "How important is this to remember long-term?",
                          "criteria": ["trivial", "minor", "useful", "important", "life event"]},
}

# ---------- deterministic rules ----------
P2_RX = re.compile(
    r"\b(password|passcode|pin\b|otp|cvv|bank|account (no|number)|ifsc|upi|aadhaar|aadhar|pan card|"
    r"salary|loan|emi|credit card|debit card|diagnos|prescription|medicine|dawai|doctor|hospital|"
    r"therap|depress|bp\b|blood pressure|sugar level)", re.I)
CORRECTION_RX = re.compile(
    r"(\bdon'?t\b|\bdo not\b|\bstop (saying|doing|being)|\bnever (say|do)|too long|too much|"
    r"\bmat (bolo|karo|bol|kar)\b|aise mat|band karo|itna lamba|pehle bhi bola|kitni baar bola|"
    r"\bwrong\b.*\b(you|tum)|that'?s not how)", re.I)
TIME_RX = re.compile(
    r"\b(today|tomorrow|tonight|yesterday|kal|aaj|parso|subah|shaam|raat|dopahar|morning|evening|"
    r"night|baje|\d{1,2}(:\d{2})?\s*(am|pm)|monday|tuesday|wednesday|thursday|friday|saturday|sunday|"
    r"next week|minute|minutes|hour|hours|ghante)\b", re.I)


@dataclass
class Decisions:
    answers: dict[str, str] = field(default_factory=dict)      # question -> label / value
    conf: dict[str, float] = field(default_factory=dict)       # question -> confidence
    source: str = "rules"
    latency_ms: float = 0.0

    def get(self, q: str, default=None):
        return self.answers.get(q, default)

    def is_(self, q: str, threshold: float = 0.5) -> bool:
        """For yes/no questions stored as 'yes'/'no' with P(yes) in conf."""
        return self.answers.get(q) == "yes" and self.conf.get(q, 0.0) >= threshold

    def privacy(self) -> int:
        return int(str(self.answers.get("privacy_level", "P1"))[1])


def rule_floor(text: str) -> Decisions:
    d = Decisions()
    d.answers["privacy_level"] = "P2" if P2_RX.search(text) else "P1"
    d.conf["privacy_level"] = 1.0
    if CORRECTION_RX.search(text):
        d.answers["is_correction"], d.conf["is_correction"] = "yes", 0.9
    if TIME_RX.search(text):
        d.answers["has_time_reference"], d.conf["has_time_reference"] = "yes", 0.9
    return d


class LayaDecider:
    def __init__(self, checkpoint: str | None = None):
        import laya
        self.checkpoint = checkpoint or "multilingual"
        sub = None if self.checkpoint == "english" else self.checkpoint
        self.agent = laya.load("convaiinnovations/laya", subfolder=sub)
        self.version = f"laya-{laya.__version__}-{self.checkpoint}"

    def ask(self, state: str, questions: dict | None = None) -> Decisions:
        t = time.perf_counter()
        res = self.agent.predict(state, questions or QUESTIONS)
        d = Decisions(source=self.version, latency_ms=(time.perf_counter() - t) * 1000)
        for name, a in res["answers"].items():
            if "choice" in a:
                d.answers[name] = a["choice"]
                d.conf[name] = float(a.get("answer_confidence", a.get("confidence", 0.0)) or 0.0)
            elif "noul" in a:
                p = float(a["noul"])
                d.answers[name] = "yes" if p >= 0.5 else "no"
                d.conf[name] = p if p >= 0.5 else 1 - p
                d.conf[name + ".p_yes"] = p
            elif "score" in a:
                d.answers[name] = str(a["score"])
                d.conf[name] = float(a.get("answer_confidence", 0.0) or 0.0)
        return d


_laya: LayaDecider | None = None
_laya_failed = False


def decide(text: str, qvec=None, context: str = "") -> Decisions:
    """System-1 pass: exemplar kNN (hot path) or Laya (if enabled), merged with rule floors.
    Never raises. qvec = the query embedding already computed for recall (reused, no extra cost)."""
    global _laya, _laya_failed
    floor = rule_floor(text)
    d = Decisions()
    if not _laya_failed and os.getenv("STITI_LAYA", "off") != "off":
        try:
            _laya = _laya or LayaDecider(os.environ["STITI_LAYA"])
            state = f"{context}\nUser: {text}" if context else text
            d = _laya.ask(state)
        except Exception as e:  # missing weights, OOM...: degrade
            _laya_failed = True
            print(f"[stiti] Laya unavailable, using exemplars + rules: {e}")
    if "domain" not in d.answers and qvec is not None:
        from . import intent
        t = time.perf_counter()
        v = qvec.to_numpy().astype("float32") if hasattr(qvec, "to_numpy") else qvec
        d.answers["domain"], d.conf["domain"], _ = intent.classify(v, "domain")
        d.answers["text_emotion"], d.conf["text_emotion"], _ = intent.classify(v, "mood")
        d.source, d.latency_ms = "exemplar-knn", (time.perf_counter() - t) * 1000
    # privacy: floor wins if stricter
    if "privacy_level" not in d.answers or floor.privacy() > d.privacy():
        d.answers["privacy_level"], d.conf["privacy_level"] = floor.answers["privacy_level"], 1.0
    for q in ("is_correction", "has_time_reference"):
        if floor.answers.get(q) == "yes":
            d.answers[q], d.conf[q] = "yes", max(d.conf.get(q, 0), floor.conf[q])
    if d.is_("is_correction", 0.6):
        d.answers["domain"], d.conf["domain"] = "feedback", max(d.conf.get("domain", 0), 0.9)
    return d
