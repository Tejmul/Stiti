"""Two voices + speed + say-as (owner, 2026-11-11: "there should be two voices: one for Hinglish and another for
English"; picked the American af_jessica for English, which said his name "Tej" as "Tedge").

English line → `voice`; Hinglish line (2+ Hindi words, hinglish.phonemize) → `voice_hi`; respellings from the local
owner_profile `say_as` (never in code) only for stock Kokoro voices; base speed 0.8–1.3. Throwaway test DB only.

STITI_DB=postgresql:///stiti_test STITI_HOME=<tmp> uv run python tests/voice_pick_eval.py
"""
from __future__ import annotations

import os
import sys

db = os.environ.get("STITI_DB", "")
if not db.rstrip("/").split("/")[-1].startswith("stiti_test"):
    sys.exit(f"refusing to run against {db!r}: use a stiti_test* database")
for k in ("STITI_VOICE", "STITI_VOICE_HI", "STITI_VOICE_SPEED"):
    os.environ.pop(k, None)

passed = total = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global passed, total
    total += 1
    passed += bool(cond)
    print(f"  {'✓' if cond else '✗'} {name}" + (f" — {detail}" if detail and not cond else ""))


from stiti import profile                                              # noqa: E402
from stiti.voice import tts, voices                                    # noqa: E402

print("say-as")
T = {"Tej": "Tayj", "Tejmul": "Tayjmul"}
check("name respelled", tts.apply_say_as("Hey Tej, good to hear you.", T) == "Hey Tayj, good to hear you.")
check("longer name first", tts.apply_say_as("Tejmul here", T) == "Tayjmul here")
check("possessive too", tts.apply_say_as("Tej's list", T) == "Tayj's list")
check("case-insensitive", tts.apply_say_as("hey tej", T) == "hey Tayj")
check("not inside other words", tts.apply_say_as("Tejas and Tejasvi", T) == "Tejas and Tejasvi")

print("settings (owner_profile)")
profile.set("voice_speed", "1.05", source="test")
check("speed read", tts.speed_setting() == 1.05)
profile.set("voice_speed", "9", source="test")
check("speed clamped to 1.3", tts.speed_setting() == 1.3)
profile.set("voice_speed", "fast", source="test")
check("bad speed → 1.0", tts.speed_setting() == 1.0)
print(voices.speed("1.05"))
print(voices.say_as("Tej", "Tayj"))
check("say-as saved locally", tts.say_as_setting() == {"Tej": "Tayj"})
print(voices.say_as("Tej", "off"))
check("say-as removed", tts.say_as_setting() == {})
check("goonj names vs stock Kokoro names", voices._setting("en_tara") == "goonj:en_tara"
      and voices._setting("hf_beta") == "hf_beta" and voices._setting("af_jessica") == "af_jessica")
print(voices.use("af_jessica"))
print(voices.use("hf_beta", key="voice_hi"))
check("use / use-hi saved", tts.voice_setting() == "af_jessica" and tts.hindi_voice_setting() == "hf_beta")
check("unknown voice refused", voices.use("zz_nobody").startswith("No voice"))
print(voices.use("off", key="voice_hi"))
check("use-hi off → one voice", tts.hindi_voice_setting() is None)

print("routing (real Kokoro, stock voices)")
t = tts.TTS("af_jessica", voice_hi="hf_beta")
t.say_as = {"Tej": "Tayj"}
v, k, ph = t.pick("Your call with the placement team is at four.")
check("English line → English voice, plain text path", v == "af_jessica" and ph is None)
v, k, ph = t.pick("Haan, ho gaya! Kal subah chhe baje ka alarm laga diya hai.")
check("Hinglish line → Hinglish voice with Hindi phonemes", v == "hf_beta" and ph)
check("both voices share one model file (no extra RAM)", t.hi[2] is t.k)
a, sr = t.synth("Hey Tej, good to hear you.")
b, _ = t.synth("Haan, ho gaya! Kal subah chhe baje ka alarm laga diya hai.")
check("both synthesize", len(a) > sr * 0.5 and len(b) > sr * 0.5)
check("'Tej' reaches the voice as /teɪdʒ/ ('Tay-j'), not /tɛdʒ/ ('Tedge')",
      "teɪdʒ" in t.k.tokenizer.phonemize(tts.apply_say_as("Tej", t.say_as), "en-us").replace("ˈ", ""))
one = tts.TTS("af_jessica")
check("explicit single voice (stiti voices try) ignores voice_hi", one.hi is None)
slow = tts.TTS("af_jessica")
slow.base_speed = 1.0
fast = tts.TTS("af_jessica")
fast.base_speed = 1.2
la = len(slow.synth("Your call with the placement team is at four.")[0])
lb = len(fast.synth("Your call with the placement team is at four.")[0])
check("base speed makes her quicker", lb < la * 0.92, f"{la} vs {lb}")

for key in ("voice", "voice_hi", "voice_speed", "say_as"):
    profile.set(key, "", source="test")
print(f"voice pick: {passed}/{total} checks passed")
sys.exit(0 if passed == total else 1)
