"""D27 — his words for the ears, one Indian-English voice for the mouth.

Glossary built from the brain, snap-to-glossary (never ordinary words), Hinglish detection + language prior,
prompt-copy rejection, the cloud-fallback decision (Groq mocked; one live call when a key exists), blips, the
goonj voice selection / fallback and one voice per reply. With the research clips present it also runs a quick
WER regression (STITI_STT_CLIPS=<dir with meta.json>, default: the research scratchpad).
Needs a fresh test DB (run_all.sh) — never the real brain.
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import statistics
import sys
import time
from pathlib import Path

os.environ.setdefault("HF_HUB_OFFLINE", "1")
passed = total = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global passed, total
    total += 1
    passed += bool(cond)
    print(("  ✓ " if cond else "  ✗ ") + name + (f" — {detail}" if detail and not cond else ""))


import numpy as np  # noqa: E402

from stiti import profile  # noqa: E402
from stiti.config import CFG  # noqa: E402
from stiti.db import q  # noqa: E402
from stiti.voice import endpoint, glossary, hinglish, models, stt, stt_cloud, tts  # noqa: E402

# ---------------------------------------------------------------- the brain the glossary is built from
print("glossary (built from the brain)")
profile.set("name", "Tejmul")
profile.set("call_me", "Tejmul")
(CFG.home / "USER.md").write_text("""# USER — who Tejmul is

## About me
- [F4] Tejmul is a final-year B.Tech student at Newton School of Technology, Rishihood University.
- [F9] Tejmul built Zonuly, a 40+ agent system for job referrals.
- [F10] Tejmul is a competitive programmer on Codeforces.
- [F16] Tejmal is a final year undergrad at Newton's Club of Technology.

## How to talk to me
- [D2] Reply in English.
""")
q("INSERT INTO entities(kind, name, privacy) VALUES ('person','Rahul',1), ('person','Anvika',2), ('project','Zonuly',1)")
q("INSERT INTO documents(path, title, kind, sha256) VALUES ('/x/Tejmul_Resume_Placements.pdf', "
  "'Tejmul_Resume_Placements.pdf', 'pdf', 'x')")
t0 = time.perf_counter()
terms = glossary.build()
build_ms = (time.perf_counter() - t0) * 1000
names = [t.text for t in terms]
check("owner name is the most important term (last)", names[-1] == "Tejmul", str(names))
for want in ("Stiti", "Newton School of Technology", "Rishihood University", "Zonuly", "Codeforces", "Rahul",
             "todos", "placements", "GitHub", "DSA", "resume", "cursor"):
    check(f"glossary has {want!r}", want in names, str(names))
check("misheard USER.md fact doesn't teach the wrong spelling (no Tejmal / Newton's Club)",
      not any(n in names for n in ("Tejmal", "Newton's Club of Technology", "Newton's Club")), str(names))
check("no duplicates", len({n.lower() for n in names}) == len(names), str(names))
check(f"glossary fits the prompt budget ({glossary._tokens(', '.join(names))} est. tokens)",
      glossary._tokens(", ".join(names)) <= glossary.TOKEN_BUDGET and len(names) <= glossary.MAX_TERMS)
check(f"built in < 300 ms ({build_ms:.0f} ms, incl. the dictionary load)", build_ms < 300)
glossary._terms, glossary._at = terms, time.time()
check("private (P2) person stays in the local prompt", "Anvika" in glossary.prompt_text())
check("… but never goes to the cloud prompt", "Anvika" not in glossary.prompt_text(cloud=True))
full = stt.build_prompt("en", "Remind me to call Rahul tomorrow")
check(f"whole prompt < 224 Whisper tokens ({glossary._tokens(full)} est.)", glossary._tokens(full) < 224, full)

# ---------------------------------------------------------------- snap to glossary
print("snap to glossary")
G = names
SNAP = [("My name is Tejmal.", "My name is Tejmul."),
        ("Tajmal, what's up?", "Tejmul, what's up?"),
        ("I study at Newton's Club of Technology.", "I study at Newton School of Technology."),
        ("I study at Newton's Club.", "I study at Newton School."),
        ("Add buy milk to my tadoos.", "Add buy milk to my todos."),
        ("Tejmal's resume is ready", "Tejmul's resume is ready"),
        ("Hey Stithi", "Hey Stiti")]
for heard, want in SNAP:
    got = glossary.snap(heard, G)
    check(f"{heard!r} → {want!r}", got == want, got)
KEEP = ["What are today's plans?", "The city is nice.", "Steady progress on the tattoos and orders.",
        "Kal subah 6 baje alarm laga do.", "Mera DSA ka contest kab hai?", "Currently I am preparing for placements.",
        "Newton said gravity.", "Aaj bahut kaam tha yaar, main thak gaya hoon.", "I talked to Rahul and Raju.",
        "Remind me at 4 to start my resume.", "Open my GitHub and check the pull requests."]
for s in KEEP:
    check(f"ordinary words untouched: {s!r}", glossary.snap(s, G) == s, glossary.snap(s, G))
t0 = time.perf_counter()
for _ in range(50):
    glossary.snap("Hey Stiti, add buy milk to my tadoos and remind Tejmal about Newton's Club.", G)
snap_ms = (time.perf_counter() - t0) * 1000 / 50
check(f"snap < 2 ms per turn ({snap_ms:.2f} ms)", snap_ms < 2)

# ---------------------------------------------------------------- Hinglish detection
print("Hinglish detection (language prior)")
for s, want in [("Kal subah 6 baje alarm laga do.", "hinglish"), ("Meri todos kya hain?", "hinglish"),
                ("Hey bhai, padhai kaisi chal rahi hai?", "hinglish"), ("Add buy milk to my todos.", "en"),
                ("I want to do it so fast.", "en"), ("Talk to me in English or Hindi?", "en"),
                ("आज का दिन कैसा रहा?", "hinglish")]:
    check(f"{s!r} → {want}", hinglish.language(s) == want, hinglish.language(s))
pe, ph = stt.build_prompt("en"), stt.build_prompt("hinglish")
check("English prior: English examples come first", pe.index(stt.EN_LINES) < pe.index(stt.HI_LINES))
check("Hinglish prior: Hinglish examples come first", ph.index(stt.HI_LINES) < ph.index(stt.EN_LINES))
check("both blocks always present (English-only prompts translate Hinglish: 63% WER)",
      all(x in pe and x in ph for x in (stt.EN_LINES, stt.HI_LINES)))

# ---------------------------------------------------------------- previous-utterance context
print("previous utterance (Wispr prev_asr_text)")
stt.reset_context()
a = np.random.default_rng(0).standard_normal(16000 * 2).astype(np.float32) * 0.1
b = np.random.default_rng(1).standard_normal(16000 * 2).astype(np.float32) * 0.1
fa, fb = stt._fingerprint(a), stt._fingerprint(b)
check("speculative passes of one utterance share a fingerprint", stt._fingerprint(np.concatenate([a, b])) == fa)
stt._remember(fa, "Kal subah alarm laga do yaar", "hinglish")
check("a new utterance sees the previous one", (c := stt.context(fb)) is not None and c.lang == "hinglish")
check("a later pass of the SAME utterance doesn't see itself", stt.context(fa) is None)
stt._remember(fb, "Add buy milk", "en")
stt._remember(fb, "Add buy milk to my todos", "en")              # its final pass replaces the partial
c = stt.context(stt._fingerprint(np.ones(16000, np.float32)))
check("the latest pass of the last utterance is the context", c is not None and c.text == "Add buy milk to my todos")
check("… and the same utterance's own context is the one before it", (stt.context(fb) or c).text.startswith("Kal"))
check("context goes into the prompt", "Add buy milk to my todos" in stt.build_prompt("en", c.text))
stt.reset_context()

# ---------------------------------------------------------------- prompt-copy rejection
print("prompt-copy rejection")
P = stt.build_prompt("en")
check("noise → prompt sentence ('Aaj ka plan kya hai?') is a prompt copy",
      stt.prompt_copy("Aaj ka plan kya hai?", P, G) == "prompt")
check("old turbo echo 'Aaj bahut kaam tha yaar.' vs the old prompt",
      stt.prompt_copy("Aaj bahut kaam tha yaar.", stt.HINGLISH_PROMPT, G) == "prompt")
check("Groq turbo's 'Remind me to call mummy.' ×3 is a repeat",
      stt.prompt_copy("Remind me to call mummy. Remind me to call mummy. Remind me to call mummy.", P, G) == "repeat")
check("unpunctuated loop is a repeat", stt.prompt_copy("call mummy call mummy call mummy", P, G) == "repeat")
check("a list of glossary terms is a glossary echo",
      stt.prompt_copy("Stiti, Tejmul, placements, DSA, GitHub.", P, G) == "glossary")
for s in ("Add buy milk to my todos.", "Currently I am preparing for placements.", "Mera DSA ka contest kab hai?"):
    check(f"real speech is not a copy: {s!r}", stt.prompt_copy(s, P, G) is None)

# ---------------------------------------------------------------- the cloud-fallback decision
print("cloud fallback decision (pure)")
L = stt.Local
D = [("confident local → no cloud", L("Add buy milk to my todos.", 0.05, -0.2), 1500, ("Add buy milk to my todos.", None)),
     ("unsure local (logprob < -0.5) → cloud, keep local text meanwhile", L("Add by milk to my todos.", .3, -.6), 1500,
      ("Add by milk to my todos.", "low_conf")),
     ("empty text while he spoke → cloud", L("", 1.0, -9.0), 1500, ("", "empty")),
     ("empty text on a blip → nothing", L("", 1.0, -9.0), 200, ("", None)),
     ("Whisper's filter fired on real speech → cloud (was silently dropped)",
      L("Add buy milk to my todos.", 0.7, -0.4, True, True), 1500, ("Add buy milk to my todos.", "filtered")),
     ("filter fired, unsure words, sure silence → dropped unless the cloud hears it",
      L("Thank you.", 0.9, -1.3, True, True), 1500, ("", "filtered")),
     ("filter fired on low logprob only → kept (loop asks 'Sorry?') + cloud", L("Hmm what", 0.2, -1.4, True, False),
      1500, ("Hmm what", "filtered")),
     ("confident 'Hey Stiti' (in the prompt!) is just him", L("Hey Stiti.", 0.05, -0.2, copy="prompt"), 800,
      ("Hey Stiti.", None)),
     ("unsure prompt copy → second opinion", L("Aaj ka plan kya hai?", 0.45, -0.7, copy="prompt"), 1500,
      ("Aaj ka plan kya hai?", "prompt_copy")),
     ("prompt copy from noise → dropped", L("Aaj ka plan kya hai?", 0.7, -0.7, copy="prompt"), 1500,
      ("", "prompt_copy")),
     ("repeat ×3 → dropped + cloud", L("Remind me. Remind me. Remind me.", .1, -.2, copy="repeat"), 1500,
      ("", "prompt_copy")),
     ("unsure blip (< 500 ms) → never escalated", L("Uh.", 0.3, -0.9), 300, ("Uh.", None))]
for name, loc, sp, want in D:
    got = stt.decide(loc, sp)
    check(name, got == want, f"{got} != {want}")

print("cloud fallback (Groq mocked)")
REAL_LOCAL, REAL_VOICED = stt._local, stt.voiced_ms
stt.voiced_ms = lambda a: 1500 if float(np.abs(a).max()) > 0 else 0     # the real Silero check runs in the WER part
stt_cloud.has_key = lambda: True
os.environ["STITI_STT_CLOUD"] = "on"
speech = (np.sin(np.linspace(0, 2000, 16000 * 2)) * 0.3).astype(np.float32)
calls: list[str] = []


def fake_local(text, nsp=0.1, lp=-0.2, filtered=False, hard=False):
    stt._local = lambda audio, repo, p: (stt.Local(text, nsp, lp, filtered, hard), 250.0)


def cloud(text, delay=0.05, segs=None):
    def call(audio, prompt):
        calls.append(prompt)
        time.sleep(delay)
        return stt_cloud.CloudResult(text, delay * 1000, segs or [{"start": 0, "end": 2, "no_speech_prob": .02,
                                                                    "avg_logprob": -0.15}])
    return call


stt.reset_context()
stt_cloud.reset()
fake_local("Add by milk to my todos.", 0.3, -0.7)
n = len(calls)
r = stt.transcribe_ex(speech, cloud_call=cloud("x"))
check("asleep (no conversation): unsure audio never goes to the cloud", len(calls) == n and r.source == "local")
eng_v = type("E", (), {"channel": "voice"})()
from stiti.engine import Engine as _Eng  # noqa: E402
_Eng._voice_active(eng_v)
check("a voice turn opens the cloud lane", stt.conversation_active())
stt.mark_active(600)                                              # keep it open for the slow checks below
r = stt.transcribe_ex(speech, cloud_call=cloud("Add buy milk to my todos."))
check("unsure turn → cloud text used", r.text == "Add buy milk to my todos." and r.source == "cloud"
      and r.escalated == "low_conf", str(r))
check("cloud scores replace local ones (the loop no longer asks 'Sorry?')", not r.unclear and r.confident, str(r))
check("the glossary went with it", "Tejmul" in calls[-1] and "Glossary:" in calls[-1])
check("… minus private terms", "Anvika" not in calls[-1])
fake_local("Tejmal is here", 0.3, -0.7)
r = stt.transcribe_ex(speech, cloud_call=cloud("Tejmal is here"))
check("cloud text is snapped too (Tejmal → Tejmul)", r.text == "Tejmul is here", r.text)
fake_local("Add by milk to my todos.", 0.3, -0.7)
t0 = time.perf_counter()
r = stt.transcribe_ex(speech, cloud_call=cloud("late", delay=2.0))
waited = (time.perf_counter() - t0) * 1000
check(f"slow cloud: local text kept within the 700 ms cap ({waited:.0f} ms)",
      r.text == "Add by milk to my todos." and r.source == "local" and waited < 900, f"{r} {waited:.0f}")
check("… and the lane cools down (no 700 ms on every next turn)", not stt_cloud.enabled())
stt_cloud.reset()
n = len(calls)
fake_local("Add by milk to my todos.", 0.3, -0.7)
r = stt.transcribe_ex(speech, cloud_call=cloud("Remind me to call mummy. Remind me to call mummy. "
                                               "Remind me to call mummy."))
check("cloud prompt echo (×3) rejected → local kept", r.text == "Add by milk to my todos." and r.source == "local",
      r.text)
fake_local("", 1.0, -9.0)
r = stt.transcribe_ex(speech, cloud_call=cloud("Is any new research paper published?"))
check("empty local + speech → cloud hears the command", r.text == "Is any new research paper published?", str(r))
fake_local("", 1.0, -9.0)
r = stt.transcribe_ex(speech, cloud_call=cloud("Thank you.", segs=[{"start": 0, "end": 2, "no_speech_prob": .95,
                                                                     "avg_logprob": -0.8}]))
check("… but not when the cloud also says 'no speech'", r.text == "", r.text)
n = len(calls)
fake_local("Okay, add milk.", 0.05, -0.2)
r = stt.transcribe_ex(speech, cloud_call=cloud("x"))
check("confident turn: no cloud call", len(calls) == n and r.source == "local")
fake_local("Hmm.", 0.3, -0.9)
r = stt.transcribe_ex(np.zeros(16000, np.float32), cloud_call=cloud("x"))
check("silence/blip: no cloud call", len(calls) == n, str(r))
os.environ["STITI_STT_CLOUD"] = "off"
fake_local("Add by milk to my todos.", 0.3, -0.7)
r = stt.transcribe_ex(speech, cloud_call=cloud("x"))
check("STITI_STT_CLOUD=off: audio never leaves the Mac", len(calls) == n and r.text == "Add by milk to my todos.")
del os.environ["STITI_STT_CLOUD"]
profile.set("stt_cloud", "off")
r = stt.transcribe_ex(speech, cloud_call=cloud("x"))
check("owner_profile stt_cloud=off works too", len(calls) == n and stt_cloud.setting() == "off")
os.environ["STITI_STT_CLOUD"] = "on"
check("env wins over the profile", stt_cloud.setting() == "on")
profile.set("stt_cloud", "on")

# ---------------------------------------------------------------- learning words from his corrections (Wispr §3)
print("correction learning (personal vocabulary)")
from stiti.voice import vocab  # noqa: E402

PREV = "Hey Tejmal, add Newtons Club to my todos"
LEARN = [("no, I said Tejmul", ("Tejmul", "Tejmal")), ("it's Stiti, not City", ("Stiti", "City")),
         ("Tejmul, not Tejmal", ("Tejmul", "Tejmal")), ("spell it T-E-J-M-U-L", ("Tejmul", "Tejmal")),
         ("It's spelled T E J M U L.", ("Tejmul", "Tejmal")), ("nahi, maine Tejmul bola", ("Tejmul", "Tejmal")),
         ("Not Tejmal, Tejmul.", ("Tejmul", "Tejmal")), ("My name is Tejmul, not Tejmal.", ("Tejmul", "Tejmal")),
         ("Newton School, not Newtons Club", ("Newton School", "Newtons Club")),
         ("add 'Zonuly' to your vocabulary", ("Zonuly", None)), ("Add Zonuly to your dictionary.", ("Zonuly", None)),
         ("remember the word Codeforces", ("Codeforces", None))]
for said, want in LEARN:
    lr = vocab.parse(said, PREV)
    check(f"learns from {said!r} → {want}", lr is not None and (lr.term, lr.heard) == want, str(lr))
for said in ("I said hello", "no, I said milk", "call Rahul not Raju", "I want tea not coffee", "No, it's fine",
             "no, I said add milk to my todos", "Remind me to call mummy at 7 pm."):
    check(f"not a word correction: {said!r}", vocab.parse(said, PREV) is None, str(vocab.parse(said, PREV)))
os.environ["STITI_STT_CLOUD"] = "off"
fake_local("Hey Tejmal, what's up?", 0.1, -0.2)
check("before learning: 'Tejmal' snaps only if the glossary already knows Tejmul",
      "Tejmul" in stt.transcribe_ex(speech).text)
vocab.add("Zonuly", None, "explicit")
lr = vocab.learn("no, I said Kshitij", "Call Shitij about the project")
check("a new name is learned with its mis-hearing", lr is not None and (lr.term, lr.heard) == ("Kshitij", "Shitij"),
      str(lr))
check("saved locally in ~/.stiti/vocab.json", "Kshitij" in json.loads((CFG.home / "vocab.json").read_text())["terms"])
check("next turn: it is in the Whisper glossary right away", "Kshitij" in glossary.prompt_text())
fake_local("Remind me to call Shitij tomorrow", 0.1, -0.2)
check("next turn: the heard form is rewritten", stt.transcribe_ex(speech).text == "Remind me to call Kshitij tomorrow")
fake_local("Remind me to call Ksheetij tomorrow", 0.1, -0.2)
check("… and near-misses snap to it", stt.transcribe_ex(speech).text == "Remind me to call Kshitij tomorrow")
vocab.add("Stiti", "City", "correction")
check("an ordinary heard word ('City') is NOT rewritten everywhere", vocab.rewrite("The city is big") == "The city is big")
glossary.invalidate()
check("learned words survive a glossary rebuild", any(t.text == "Kshitij" for t in glossary.terms(block=True)))
check("explicit words too", "Zonuly" in glossary.prompt_text())
stt._local = REAL_LOCAL
from stiti.engine import Engine  # noqa: E402
eng = Engine("text")
eng.last_user_text = "Message Anshal about the hackathon"
reply = eng.turn("no, I said Anshul")
check("engine: a voice correction gets a fast local reply", reply.startswith("Got it") and eng.last_route == "fast_path",
      f"{reply!r} {eng.last_route}")
check("engine: … and the word is learned", "Anshul" in vocab.terms())
reply = eng.turn("add Rishihood to your vocabulary")
check("engine: explicit 'add X to your vocabulary'", "Rishihood" in reply and "Rishihood" in vocab.terms(), reply)
os.environ["STITI_STT_CLOUD"] = "on"
stt._local, stt.voiced_ms = REAL_LOCAL, REAL_VOICED

# ---------------------------------------------------------------- blips (Wispr: < 500 ms → ignore, not "Sorry?")
print("blips")
S = stt.STTResult
unsure, sure = S("Uh?", 1, 0.6, -1.2), S("Haan.", 1, 0.05, -0.2)
check("unsure 300 ms blip → ignored", endpoint.Commit(audio=[], res=unsure, speech_ms=300).text == "")
check("sure 300 ms 'Haan.' → kept", endpoint.Commit(audio=[], res=sure, speech_ms=300).text == "Haan.")
check("unsure 900 ms turn → kept (the loop may ask)", endpoint.Commit(audio=[], res=unsure, speech_ms=900).text == "Uh?")
check("a barge-in is never a blip", endpoint.Commit(audio=[], res=unsure, speech_ms=300, barged=True).text == "Uh?")

# ---------------------------------------------------------------- voice: goonj selection, fallback, one voice
print("voice (goonj)")
check("default is goonj:en_priya (female)", tts.DEFAULT_VOICE == "goonj:en_priya")
check("goonj:en_tara → goonj persona", tts.resolve("goonj:en_tara", ready=True) == ("goonj", "en_tara"))
check("'goonj' alone → default persona", tts.resolve("goonj", ready=True) == ("goonj", "en_priya"))
check("goonj files missing → Kokoro af_heart", tts.resolve("goonj:en_tara", ready=False) == ("kokoro", "af_heart"))
check("stock voices still selectable", tts.resolve("af_heart", ready=True) == ("kokoro", "af_heart"))
os.environ.pop("STITI_VOICE", None)
profile.set("voice", "goonj:en_arjun")
check("owner_profile voice is used", tts.voice_setting() == "goonj:en_arjun")
os.environ["STITI_VOICE"] = "goonj:en_tara"
check("STITI_VOICE wins over the profile", tts.voice_setting() == "goonj:en_tara")
del os.environ["STITI_VOICE"]
q("DELETE FROM owner_profile WHERE key='voice'")
profile._all.cache_clear()

real_goonj = Path.home() / ".stiti" / "models" / "goonj"
if not models.goonj_ready() and (real_goonj / models.GOONJ_MODEL).exists():
    models.GOONJ_DIR = real_goonj                                 # run_all uses a temp STITI_HOME
real_voice = Path.home() / ".stiti" / "models" / "voice"
if not (models.DIR / "kokoro-v1.0.int8.onnx").exists() and (real_voice / "kokoro-v1.0.int8.onnx").exists():
    models.DIR = real_voice
if models.goonj_ready():
    v = tts.TTS("goonj:en_priya")
    check("goonj loads", v.engine == "goonj" and v.name == "goonj:en_priya", v.name)
    used: list[str] = []
    real_create = v.k.create

    def spy(text, voice, **kw):
        used.append(voice)
        return real_create(text, voice=voice, **kw)
    v.k.create = spy
    for line in ("Okay, I added buy milk to your todos.", "Okay yaar, aaj ka plan ready hai, chalo shuru karte hain.",
                 "Haan, note kar liya.", "Your meeting is at three thirty."):
        v.synth_on_worker(line)
    check("one voice per reply: English and Hinglish lines both use en_priya", set(used) == {"en_priya"}, str(used))
    check("never the stock Hindi voices", not ({"hf_alpha", "hf_beta", "hm_omega"} & set(used)))
    v.k.create = real_create
    v.synth_on_worker("Warm up.")
    ms = []
    for clause in ("Hey Tejmul,", "Okay yaar, I added buy milk", "Haan, note kar liya.", "Sure, setting it now.") * 3:
        t0 = time.perf_counter()
        audio, sr = v.synth_on_worker(clause)
        ms.append((time.perf_counter() - t0) * 1000)
    med = statistics.median(ms)
    check(f"goonj first clause < 450 ms after warm-up ({med:.0f} ms p50)", med < 450, str([round(x) for x in ms]))
    check("audio is real speech (not silent)", len(audio) > sr * 0.4 and float(abs(audio).max()) > 0.05)
    bad = tts.TTS("goonj:en_nobody")
    check("unknown persona → default persona, still goonj", bad.name == "goonj:en_priya", bad.name)
else:
    print("  (goonj files not installed: synthesis checks skipped — `stiti voices install`)")
saved = models.GOONJ_DIR
models.GOONJ_DIR = CFG.home / "no_such_dir"
if (models.DIR / "kokoro-v1.0.int8.onnx").exists():
    fb = tts.TTS("goonj:en_priya")
    check("missing goonj files → speaks with af_heart, not a crash", fb.name == "af_heart", fb.name)
    fb.synth_on_worker("Warm up.")                                # let the start-up warm-ups finish first
    used = []
    real_create = fb.k.create
    fb.k.create = lambda text, voice, **kw: (used.append(voice), real_create(text, voice=voice, **kw))[1]
    fb.synth_on_worker("Okay yaar, aaj ka plan ready hai.")
    check("fallback is one voice too (no hf_alpha switch)", used == ["af_heart"], str(used))
models.GOONJ_DIR = saved

# ---------------------------------------------------------------- live Groq (only when a key exists)
print("live Groq whisper-large-v3 (optional)")
_C = CFG
if _C.keys.get("groq") and os.getenv("STITI_STT_LIVE", "1") != "0" and models.goonj_ready():
    stt_cloud.has_key = lambda: bool(_C.keys.get("groq"))
    stt_cloud.reset()
    v = tts.TTS("goonj:en_priya")
    a24, sr = v.synth_on_worker("Add buy milk to my todos.")
    a16 = np.interp(np.linspace(0, len(a24), int(len(a24) * 16000 / sr), endpoint=False), np.arange(len(a24)),
                    a24).astype(np.float32)
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        cr = stt_cloud.transcribe(np.concatenate([np.zeros(4000, np.float32), a16, np.zeros(4000, np.float32)]),
                                  stt.build_prompt("en", cloud=True), cap_ms=4000)
    if cr is None:
        print("  (Groq unreachable / rate-limited: live check skipped)")
    else:
        check(f"Groq large-v3 heard the command ({cr.ms:.0f} ms): {cr.text!r}", "milk" in cr.text.lower(), cr.text)
    check("the API key is never printed", _C.keys["groq"] not in out.getvalue())
else:
    print("  (no Groq key / STITI_STT_LIVE=0: skipped)")

# ---------------------------------------------------------------- WER regression on the research clips
CLIPS = Path(os.getenv("STITI_STT_CLIPS", "/private/tmp/claude-501/-Users-tejmul-Desktop-Stiti/"
                       "0e6c0a17-f92d-4e80-a621-98bf58ea090b/scratchpad/stt/clips"))
hub = Path.home() / ".cache" / "huggingface" / "hub" / ("models--" + models.WHISPER_MAIN.replace("/", "--"))
if (CLIPS / "meta.json").exists() and hub.exists():
    print("WER regression (research clips, local only)")
    import difflib

    import soundfile as sf
    os.environ["STITI_STT_CLOUD"] = "off"

    def norm(s: str) -> list[str]:
        import re
        s = s.lower().replace("to-dos", "todos").replace("to dos", "todos").replace("a.m.", " am").replace("p.m.", " pm")
        s = re.sub(r"(\d+)\s*(am|pm)\b", r"\1 \2", s)
        return [hinglish.LEX.get(w, w) for w in re.findall(r"[a-z0-9']+", s)]

    voices = set(os.getenv("STITI_STT_CLIP_VOICES", "Rishi,go_en_priya").split(","))
    meta = [m for m in json.loads((CLIPS / "meta.json").read_text()) if m["voice"] in voices]
    stt.transcribe_ex(np.zeros(16000, np.float32))
    err = n = 0
    lat = []
    for m in meta:
        stt.reset_context()
        r = stt.transcribe_ex(sf.read(m["file"], dtype="float32")[0])
        ref, hyp = norm(m["ref"]), norm(r.text)
        sm = difflib.SequenceMatcher(None, ref, hyp)
        err += max(len(ref), len(hyp)) - sum(b.size for b in sm.get_matching_blocks())
        n += len(ref)
        lat.append(r.ms)
    w = 100 * err / n
    print(f"  {len(meta)} clips: WER ≈ {w:.1f}% (before D27 ≈ 12%), p50 {statistics.median(lat):.0f} ms")
    check(f"local WER stays under 11% ({w:.1f}%)", w < 11)
    check(f"local STT p50 < 400 ms ({statistics.median(lat):.0f} ms)", statistics.median(lat) < 400)
else:
    print("  (research clips or cached whisper-small not found: WER regression skipped)")

print(f"stt+voice: {passed}/{total} checks passed")
sys.exit(0 if passed == total else 1)
