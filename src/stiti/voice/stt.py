"""Speech-to-text with mlx-whisper (Apple GPU). Whisper-family only: SenseVoice/Parakeet can't hear Hindi.

D27 (docs/research/stt_tts_indian_english.md, re_wispr_flow.md), one transcription per turn:
1. **Prompt = his words + the conversation.** `glossary.py` builds his glossary from the brain (name, USER.md,
   graph, documents); then two example blocks (Hinglish + English) ordered by the language PRIOR (the previous
   utterance's language, Wispr-style counters in `hinglish.language`); then the previous utterance itself
   (Wispr `prev_asr_text`). Whisper weighs the end of the prompt most. Measured on 110 clips with whisper-small q4:
   today's code 12.4% WER → 7.7% local, 6.8% with the cloud second opinion (owner terms 64 → 82/90).
2. **Guards.** A transcript that copies the prompt (a prompt sentence, a glossary list, a clause ×3) is not speech.
3. **Escalate, don't drop.** Unsure local text (avg_logprob < −0.5), empty text while there was speech, Whisper's own
   no-speech filter firing on real speech ("Add buy milk to my todos" was dropped) or a prompt copy → the same audio
   goes to Groq whisper-large-v3 with the same prompt (stt_cloud.py, 700 ms cap, keep local text otherwise).
4. **Snap to glossary** ("Tejmal" → "Tejmul", "Newton's Club" → "Newton School"), < 1 ms, ordinary words untouched.
Confidence: `transcribe_ex()` returns Whisper's own no_speech_prob / avg_logprob (duration-weighted) so the loop can
refuse a phantom "Bye." and ask "Sorry, say that again?" instead of answering garbage.
"""
from __future__ import annotations

import hashlib
import os
import re
import threading
import time
from dataclasses import dataclass

import numpy as np

from . import glossary, hinglish, stt_cloud
from .models import WHISPER_MAIN

# the old one-block prompt (kept: tests and tools still use it as a plain Hinglish bias)
HINGLISH_PROMPT = ("Hey Stiti. Wake up baby girl. Haan Stiti, kal subah 6 baje alarm laga do. "
                   "Meri todos kya hain? Aaj bahut kaam tha yaar. Remind me to call mummy.")
WAKE_PROMPT = HINGLISH_PROMPT
# D27 example blocks (none of them is a test sentence: an earlier draft that reused test lines looked 2 points better
# than it was). Measured, whisper-small q4, 110 clips, + snap: English block first 7.8% WER (commands 5.3%), Hinglish
# block first 7.9% (Hinglish 15.3%); English only 21.8% (it TRANSLATES Hinglish: 63%). So both blocks are always
# there and the language prior only picks the order.
WAKE_LINE = "Hey Stiti. Wake up baby girl."
EN_LINES = "Okay, set a reminder for my class tomorrow. What's on my calendar today?"
HI_LINES = ("Haan Stiti, shaam ko 5 baje yaad dila dena. Aaj ka plan kya hai? "
            "Thoda busy hoon yaar, baad mein baat karte hain.")

# "confident" = good enough to act on a one-word stop/goodbye; "unclear" = ask him to repeat
CONF_NO_SPEECH, CONF_LOGPROB = 0.4, -0.8
UNCLEAR_NO_SPEECH = float(os.getenv("STITI_UNCLEAR_NOSPEECH", "0.5"))
UNCLEAR_LOGPROB = float(os.getenv("STITI_UNCLEAR_LOGPROB", "-1.0"))
ESCALATE_LOGPROB = float(os.getenv("STITI_STT_ESCALATE_LOGPROB", "-0.5"))   # research: 16% of turns, 6.3% WER
MIN_SPEECH_MS = 500              # Wispr: less speech than this is a blip — never escalated, never "Sorry?"
CONTEXT_TTL_S = 120              # the previous utterance is context only within one conversation
CONTEXT_MAX_WORDS = 30
SR = 16000


@dataclass
class STTResult:
    text: str
    ms: float = 0.0
    no_speech_prob: float = 0.0
    avg_logprob: float = 0.0
    source: str = "local"        # local | cloud
    escalated: str = ""          # why the cloud was asked: low_conf | empty | filtered | prompt_copy
    lang: str = "en"             # en | hinglish (what this utterance sounded like)
    speech_ms: int = -1          # voiced audio estimate (-1 = unknown)

    @property
    def confident(self) -> bool:
        return bool(self.text) and self.no_speech_prob < CONF_NO_SPEECH and self.avg_logprob > CONF_LOGPROB

    @property
    def unclear(self) -> bool:
        return bool(self.text) and (self.no_speech_prob > UNCLEAR_NO_SPEECH or self.avg_logprob < UNCLEAR_LOGPROB)


_cache_capped = False


def _cap_mlx_cache() -> None:
    """MLX keeps GPU buffers cached: 1.2 GB → 0.33 GB with a 64 MB cap (STT 283 → ~320 ms). Worth it on 8 GB."""
    global _cache_capped
    if not _cache_capped:
        import mlx.core as mx
        mx.set_cache_limit(int(os.getenv("STITI_MLX_CACHE_MB", "64")) * 1024 * 1024)
        _cache_capped = True


def score(segs: list[dict]) -> tuple[float, float]:
    """Duration-weighted (no_speech_prob, avg_logprob) over Whisper's segments."""
    if not segs:
        return 1.0, -9.0
    w = [max(0.05, float(s.get("end", 0)) - float(s.get("start", 0))) for s in segs]
    tot = sum(w)
    nsp = sum(float(s.get("no_speech_prob", 0.0)) * x for s, x in zip(segs, w)) / tot
    lp = sum(float(s.get("avg_logprob", 0.0)) * x for s, x in zip(segs, w)) / tot
    return nsp, lp


_vad = None
_vad_lock = threading.Lock()


def voiced_ms(audio: np.ndarray) -> int:
    """Speech length by Silero VAD (~3.5 ms per second of audio; only run when a decision needs it).
    Falls back to an energy estimate (frames clearly above the clip's noise floor) if the VAD can't load."""
    global _vad
    a = np.asarray(audio, dtype=np.float32)
    try:
        from .vad import FRAME, VAD
        with _vad_lock:
            if _vad is None:
                _vad = VAD()
            _vad.reset()
            n = sum(_vad.prob(a[i:i + FRAME]) >= 0.5 for i in range(0, len(a) - FRAME + 1, FRAME))
        return int(n * FRAME * 1000 // SR)
    except Exception:
        k = len(a) // 320
        if k == 0:
            return 0
        rms = np.sqrt(np.mean(a[:k * 320].reshape(k, 320) ** 2, axis=1))
        return int(np.count_nonzero(rms > max(0.004, 3 * float(np.percentile(rms, 10)))) * 20)


# ---------------------------------------------------------------- prompt
def build_prompt(lang: str = "en", prev: str = "", cloud: bool = False) -> str:
    """Glossary + the previous utterance + example blocks (ordered by the language prior)."""
    blocks = [WAKE_LINE] + ([HI_LINES, EN_LINES] if lang == "hinglish" else [EN_LINES, HI_LINES])
    parts = [glossary.prompt_text(cloud=cloud)] if os.getenv("STITI_STT_BIAS", "on") != "off" else []
    # the previous utterance goes BEFORE the examples: measured with a previous line in the other language
    # (he switches), at the end it cost 8.6 → 12.2% WER, before the examples 9.9% (same language: 8.5 vs 8.8%)
    parts += [" ".join(prev.split()[-CONTEXT_MAX_WORDS:]) if prev else ""] + blocks
    return " ".join(p for p in parts if p)


def prompt(lang: str = "en") -> str:
    """The prompt a fresh turn would get (no previous utterance)."""
    return build_prompt(lang)


def _words(s: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", (s or "").lower())


def prompt_copy(text: str, prompt_text: str, terms: list[str] | None = None) -> str | None:
    """Is this transcript a copy of the prompt rather than speech? 'repeat' (a clause ×3, seen on Groq turbo),
    'glossary' (a list of glossary terms), 'prompt' (a run of ≥ 2 prompt words, e.g. "Aaj bahut kaam tha yaar"
    from noise — but also a real "What are my todos?", so the caller double-checks instead of dropping)."""
    w = _words(text)
    if not w:
        return None
    clauses = [" ".join(_words(c)) for c in re.split(r"[.!?,;\n]+", text) if len(_words(c)) >= 2]
    if clauses and max(clauses.count(c) for c in clauses) >= 3:
        return "repeat"
    for n in range(2, 7):                                  # unpunctuated loops: "remind me remind me remind me"
        if len(w) >= 3 * n and any(w[i:i + n] == w[i + n:i + 2 * n] == w[i + 2 * n:i + 3 * n]
                                   for i in range(len(w) - 3 * n + 1)):
            return "repeat"
    if terms and len(w) >= 3:
        tw = {x for t in terms for x in _words(t)}
        if sum(x in tw for x in w) >= 0.8 * len(w) and len(re.findall(r",", text)) >= 2:
            return "glossary"
    if len(w) >= 2 and f" {' '.join(w)} " in f" {' '.join(_words(prompt_text))} ":
        return "prompt"
    return None


# ---------------------------------------------------------------- conversation context (Wispr prev_asr_text)
@dataclass
class _Heard:
    fp: str
    text: str
    lang: str
    t: float


_ctx_lock = threading.Lock()
_last: _Heard | None = None      # the utterance heard most recently (may still be growing: speculative passes)
_prev: _Heard | None = None      # the one before it


def _fingerprint(audio: np.ndarray) -> str:
    """Speculative passes of one utterance share their start (the turn-taker keeps appending frames), so the
    first 0.5 s identifies the utterance: a later pass of the same one must not see itself as 'previous'."""
    head = np.asarray(audio[:SR // 2], dtype=np.float32)
    return hashlib.blake2b(head.tobytes(), digest_size=8).hexdigest()


def context(fp: str) -> _Heard | None:
    with _ctx_lock:
        c = _last if (_last is not None and _last.fp != fp) else _prev
    return c if c is not None and c.text and time.time() - c.t < CONTEXT_TTL_S else None


def _remember(fp: str, text: str, lang: str) -> None:
    global _last, _prev
    if not text:
        return
    with _ctx_lock:
        if _last is not None and _last.fp == fp:
            _last = _Heard(fp, text, lang, time.time())
        else:
            _prev, _last = _last, _Heard(fp, text, lang, time.time())


def reset_context() -> None:
    global _last, _prev
    with _ctx_lock:
        _last = _prev = None


# ---------------------------------------------------------------- the decision (pure, tested)
@dataclass
class Local:
    text: str                    # Whisper's raw text
    no_speech_prob: float
    avg_logprob: float
    filtered: bool = False       # Whisper's own no-speech filter fired (every segment looks like silence)
    hard_silence: bool = False   # ... and it was sure (no_speech_prob > 0.6 everywhere)
    copy: str | None = None      # prompt_copy() verdict


def decide(loc: Local, speech_ms: int) -> tuple[str, str | None]:
    """(text to use if the cloud can't help, reason to ask the cloud or None)."""
    real = speech_ms >= MIN_SPEECH_MS
    raw = (loc.text or "").strip()
    if not raw:
        return "", ("empty" if real else None)
    if loc.copy in ("repeat", "glossary"):
        return "", ("prompt_copy" if real else None)
    if loc.copy == "prompt":
        # "Hey Stiti" is in the prompt AND the most common thing he says: a confident copy is just him; an unsure one
        # (noise turned into a prompt sentence) gets a second opinion and is kept only if Whisper heard speech
        if loc.no_speech_prob <= 0.3 and loc.avg_logprob >= ESCALATE_LOGPROB and not loc.filtered:
            return raw, None
        keep = raw if real and loc.no_speech_prob < UNCLEAR_NO_SPEECH and not loc.filtered else ""
        return keep, ("prompt_copy" if real else None)
    if loc.filtered:                                # was dropped before D27, even "Add buy milk to my todos"
        sure_words = real and loc.avg_logprob >= ESCALATE_LOGPROB      # confident words over "silence": keep them
        return ("" if loc.hard_silence and not sure_words else raw), ("filtered" if real else None)
    if loc.avg_logprob < ESCALATE_LOGPROB and real:
        return raw, "low_conf"
    return raw, None


def accept_cloud(cr: stt_cloud.CloudResult | None, prompt_text: str, terms: list[str]) -> bool:
    if cr is None or not cr.text.strip():
        return False
    if prompt_copy(cr.text, prompt_text, terms) in ("repeat", "glossary"):
        return False
    if cr.segments and all(float(s.get("no_speech_prob", 0)) > 0.8 for s in cr.segments):
        return False
    return True


# ---------------------------------------------------------------- transcription
def _local(audio: np.ndarray, repo: str, prompt_text: str) -> tuple[Local, float]:
    import mlx_whisper
    _cap_mlx_cache()
    t = time.perf_counter()
    r = mlx_whisper.transcribe(np.asarray(audio, dtype=np.float32), path_or_hf_repo=repo,
                               language=os.getenv("STITI_STT_LANG", "en"), initial_prompt=prompt_text,
                               condition_on_previous_text=False, temperature=0.0,
                               no_speech_threshold=0.6, verbose=None)
    ms = (time.perf_counter() - t) * 1000
    text = (r.get("text") or "").strip()
    segs = r.get("segments") or []
    nsp, lp = score(segs)
    filtered = bool(segs) and all(sg.get("no_speech_prob", 0) > 0.6 or sg.get("avg_logprob", 0) < -1.2 for sg in segs)
    hard = bool(segs) and all(sg.get("no_speech_prob", 0) > 0.6 for sg in segs)
    return Local(text, nsp, lp, filtered, hard), ms


def _finish(text: str) -> str:
    return glossary.snap(text) if text and os.getenv("STITI_STT_SNAP", "on") != "off" else text


def transcribe_ex(audio: np.ndarray, *, cloud_call=None) -> STTResult:
    t0 = time.perf_counter()
    audio = np.asarray(audio, dtype=np.float32)
    fp = _fingerprint(audio)
    ctx = context(fp)
    lang = ctx.lang if ctx else "en"
    prev = ctx.text if ctx else ""
    p = build_prompt(lang, prev)
    terms = [t.text for t in glossary.terms()]
    stt_cloud.prewarm()
    loc, _ = _local(audio, os.getenv("STITI_WHISPER", WHISPER_MAIN), p)
    loc.copy = prompt_copy(loc.text, p, terms)
    sp = -1
    text, reason = decide(loc, 10 ** 6)               # the speech length only matters if something looks wrong
    if reason or not loc.text.strip():
        sp = voiced_ms(audio)
        text, reason = decide(loc, sp)
    nsp, lp, source = loc.no_speech_prob, loc.avg_logprob, "local"
    if reason and stt_cloud.enabled():
        cp = build_prompt(lang, prev, cloud=True)
        cr = stt_cloud.transcribe(audio, cp, call=cloud_call)
        if accept_cloud(cr, cp, terms):
            text, source = cr.text, "cloud"
            if cr.segments:
                nsp, lp = score(cr.segments)
            else:
                nsp, lp = min(nsp, 0.1), max(lp, -0.3)
    text = _finish(text)
    heard_lang = hinglish.language(text) if text else lang
    _remember(fp, text, heard_lang)
    return STTResult(text, (time.perf_counter() - t0) * 1000, nsp, lp, source, reason or "", heard_lang, sp)


def transcribe(audio: np.ndarray) -> tuple[str, float]:
    r = transcribe_ex(audio)
    return r.text, r.ms


def transcribe_wake(audio: np.ndarray) -> tuple[str, float]:
    return transcribe(audio)
