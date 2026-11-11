"""She replies in the language he speaks (owner, 2026-11-11): English → English; switch to Telugu → Telugu;
"Namaskar…" → Hindi; back to English → English. "Just talk in English, don't talk in any other language" locks
English until he says she can switch. "Talk in Telugu" switches. Throwaway test DB + temp STITI_HOME only.

STITI_DB=postgresql:///stiti_test STITI_HOME=<tmp> uv run python tests/lang_switch_eval.py
"""
from __future__ import annotations

import os
import re
import sys

db = os.environ.get("STITI_DB", "")
if not db.rstrip("/").split("/")[-1].startswith("stiti_test"):
    sys.exit(f"refusing to run against {db!r}: use a stiti_test* database")
os.environ.setdefault("STITI_LIVE_WARM", "0")
for k in ("STITI_VOICE", "STITI_VOICE_HI", "STITI_VOICE_TE"):
    os.environ.pop(k, None)

passed = total = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global passed, total
    total += 1
    passed += bool(cond)
    print(f"  {'✓' if cond else '✗'} {name}" + (f" — {detail}" if detail and not cond else ""))


from stiti.brain import compiler, instructions, lang, psych, strategy  # noqa: E402
from stiti.db import q                                                  # noqa: E402

TE = re.compile(r"[ఀ-౿]")
DEV = re.compile(r"[ऀ-ॿ]")

print("what he is speaking")
CASES = {
    "Can you tell me what's on my to-do list today?": "english", "Namaskar, aaj mera din bahut accha tha": "hinglish",
    "Mera to-do list kya hai aaj?": "hinglish", "नमस्कार, आज मेरा दिन बहुत अच्छा था।": "hindi",
    "నమస్కారం, ఈ రోజు నా రోజు చాలా బాగుంది.": "telugu", "ఈ రోజు నా to-do list లో ఏముంది?": "tenglish",
    "Nenu ivala chala tired ga unnanu": "tenglish", "Repu poddunna alarm pettu": "tenglish", "Ela unnav?": "tenglish",
    "Kaise ho?": "hinglish", "ok": "english", "I speak English at work": "english",
    "The placement interview went well": "english", "Main office jaa raha hoon": "hinglish",
}
for t, want in CASES.items():
    got = lang.classify(t)
    check(f"{want:9} ← {t[:46]}", got == want, got)

print("his commands")
CMDS = {"Just talk in English. Don't talk in any other language right now.": ("lock", "english"),
        "English only please": ("lock", "english"), "reply only in telugu": ("lock", "telugu"),
        "Talk in Telugu": ("switch", "telugu"), "Telugu lo matladu": ("switch", "telugu"),
        "Hindi mein bolo": ("switch", "hindi"), "Switch to Hindi": ("switch", "hindi"),
        "You can talk in any language now": ("unlock", None), "I speak English at work": None}
for t, want in CMDS.items():
    check(f"{str(want):22} ← {t[:50]}", lang.command(t) == want, str(lang.command(t)))

print("the reply language follows him")
prev, seq = None, []
for t in ["What's on my list today?", "నమస్కారం, ఈ రోజు నా రోజు చాలా బాగుంది.", "ok",
          "Namaskar, aaj mera din bahut accha tha", "Thanks", "And what about tomorrow's meetings?"]:
    prev = lang.decide(t, prev=prev)
    seq.append(prev)
check("English → Telugu → (ok keeps Telugu) → Hindi → (thanks keeps Hindi) → English",
      seq == ["english", "telugu", "telugu", "hinglish", "hinglish", "english"], str(seq))
check("lock wins over Telugu", lang.decide("నమస్కారం", lock="english") == "english")
check("'talk in Telugu' holds while he speaks English", lang.decide("what time is it?", pref="telugu") == "telugu")
check("…but he switches to Hindi → Hindi", lang.decide("Namaskar, aaj mera din bahut accha tha", pref="telugu") == "hinglish")
check("only an explicit lock is a lock (old 'Reply in English' rules are not)",
      lang.locked([lang.lock_directive("english")]) == "english"
      and lang.locked(["Reply in English (he asked for it), even if he mixes in Hindi words."]) is None)
check("strategy uses it", strategy.choose("నమస్కారం, ఈ రోజు నా రోజు చాలా బాగుంది.", domain="chat").lang == "telugu")

print("what the LLM is told")
for lg, needle in (("telugu", "Telugu script"), ("hindi", "Devanagari"), ("tenglish", "Tenglish"), ("english", "English")):
    rb = psych.rules_block(strategy.make("ACKNOWLEDGE", lg), can_do="")
    check(f"{lg}: language line says {needle!r}", needle in rb)
brief, _ = compiler.build(text="hi", now=__import__("datetime").datetime.now(), privacy=1, emotion_hint="", tone="",
                          recent=[], memories=[], facts=[], lessons=[], open_loops=None,
                          talk_directives=["Reply in English (he asked for it).", "Keep replies short."], mvd=False)
check("old language rules stay out of the MUST lines (only the language line decides)",
      "MUST: Reply in English" not in brief and "MUST: Keep replies short." in brief)

print("saved rules (test DB)")
q("DELETE FROM user_directives")
ins = instructions.parse("Just talk in English. Don't talk in any other language right now.")
instructions.apply(ins, [])
active = [r["directive"] for r in q("SELECT directive FROM user_directives WHERE status='active'")]
check("lock → one saved 'Language lock' rule", active == [lang.lock_directive("english")], str(active))
instructions.apply(instructions.parse("Talk in Telugu"), [])
check("an explicit switch ends the lock", not q("SELECT 1 FROM user_directives WHERE status='active'"))
q("INSERT INTO user_directives(directive, category, supersession_key) VALUES ('Talk in English.', 'talk_style', 'talk_style')")
instructions.apply(instructions.parse("You can talk in any language now"), [])
check("unlock also retires old-style 'Talk in English.' rules", not q("SELECT 1 FROM user_directives WHERE status='active'"))

print("voices by script")
from stiti.voice import tts                                             # noqa: E402

t = tts.TTS("af_jessica", voice_hi="hf_alpha", voice_te="hf_beta")
v, _, ph = t.pick("రేపు morning six కి alarm set చేశాను.")
check("Telugu line → Telugu voice with Telugu phonemes", v == "hf_beta" and ph and "ɹ" not in ph[:3], f"{v} {ph}")
v, _, ph = t.pick("ठीक है, अब हिंदी में बात करते हैं।")
check("Devanagari line → Hindi voice", v == "hf_alpha" and ph)
v, _, _ = t.pick("Okay.")
check("'Okay.' right after a Telugu/Hindi line keeps that voice", v == "hf_alpha")
t._native_t = 0
v, _, _ = t.pick("Your call is at four.")
check("plain English later → English voice", v == "af_jessica")
a, sr = t.synth("రేపు morning six కి alarm set చేశాను.")
check("Telugu line synthesizes", len(a) > sr * 0.8)

print("hearing Telugu (STT)")
from stiti.voice import lid, stt, stt_cloud                             # noqa: E402

check("pooling: Kannada counts as Telugu", lid.pooled({"kn": 0.5, "te": 0.1, "en": 0.2, "hi": 0.2})["te"] == 0.6)
os.environ["STITI_STT_CLOUD"] = "on"
lid_detect, cloud_enabled = lid.detect, stt_cloud.enabled
lid.detect = lambda audio, sr=16000: ("te", 0.9)
stt_cloud.enabled = lambda: True
fake = lambda audio, prompt, language="en": stt_cloud.CloudResult("రేపు పొద్దున ఆరు గంటలకి అలారం పెట్టు", 250.0, [])  # noqa: E731
import numpy as np                                                       # noqa: E402

r = stt.transcribe_ex(np.zeros(16000 * 2, dtype=np.float32), cloud_call=fake)
check("Telugu speech → transcribed AS Telugu (not translated)", TE.search(r.text) and r.lang == "telugu", f"{r}")
lid.detect, stt_cloud.enabled = lid_detect, cloud_enabled

print("waking is never routed through the language check (2026-11-11: 'Suno Stiti' heard as Telugu script)")
from stiti.voice import wake                                            # noqa: E402
calls = []
lid.detect = lambda audio, sr=16000: calls.append(1) or ("te", 0.9)
stt.transcribe_ex(np.zeros(16000 * 2, dtype=np.float32), lid=False)
check("asleep (lid=False) → no language check at all", not calls)
lid.detect = lid_detect
loop_src = open(os.path.join(os.path.dirname(__file__), "..", "src", "stiti", "voice", "loop.py")).read()
check("voice loop asks for the language check only while awake", loop_src.count('lid=getattr(self, "awake", False)') == 2)
check("short clips need a clear Telugu majority", lid.TE_SHARE_SHORT > lid.TE_SHARE >= 0.6)
check("near-miss wakes are logged ('Hey Stuthi', 'సునోస్తిరిఏ')", wake.near_miss("Hey Stuthi") and wake.near_miss("సునోస్తిరిఏ."))
check("ambient talk is never logged", not wake.near_miss("I think the train is late again today guys")
      and not wake.near_miss("Pass me the water"))

# ---- live LLM (only with a free key): his exact flow
from stiti import router                                                # noqa: E402

if any(s.get("key") for s in router.status()):
    print("live LLM — his flow")
    from stiti.engine import Engine                                     # noqa: E402
    q("DELETE FROM user_directives")
    e = Engine("text")
    steps = [("What should I focus on this evening?", "english"),
             ("ఈ రోజు సాయంత్రం నేను ఏమి చదవాలి?", "telugu"),
             ("Namaskar, mujhe DSA padhne ka bilkul mann nahi hai", "hindi"),
             ("Okay, so what should I do about that?", "english")]
    for text, want in steps:
        r = e.turn(text)
        got = e.last_strategy.lang if e.last_strategy else None
        script_ok = {"telugu": bool(TE.search(r)), "hindi": bool(DEV.search(r)) or lang.classify(r) in ("hindi", "hinglish"),
                     "english": not TE.search(r) and not DEV.search(r)}[want]
        ok_lang = got == want or (want == "hindi" and got == "hinglish")   # Roman Hindi from the STT may read as Hinglish
        check(f"live: {want:8} ← {text[:40]!r} → {r[:60]!r}", ok_lang and script_ok, f"lang={got}")
    r = e.turn("Just talk in English. Don't talk in any other language right now.")
    r2 = e.turn("ఈ రోజు సాయంత్రం నేను ఏమి చదవాలి?")
    check("live: after the lock, Telugu in → English out", e.last_strategy.lang == "english" and not TE.search(r2), r2[:80])
    e.turn("You can talk in any language now")
    r3 = e.turn("ఈ రోజు సాయంత్రం నేను ఏమి చదవాలి?")
    check("live: unlocked → Telugu again", e.last_strategy.lang == "telugu" and bool(TE.search(r3)), r3[:80])
    q("DELETE FROM user_directives")

print(f"language switch: {passed}/{total} checks passed")
sys.exit(0 if passed == total else 1)
