"""Personal emotion learning + opt-in recorder (D28). Headless, no mic, no emotion2vec load, ~seconds.
STITI_DB=postgresql:///stiti_test STITI_HOME=<tmp> uv run python tests/emotion_learning_eval.py
"""
import os
from pathlib import Path
import sys
import tempfile

if "test" not in os.getenv("STITI_DB", ""):
    sys.exit("refusing: set STITI_DB to a *test* database")
os.environ["STITI_PERSONAL_EMOTION_DIR"] = tempfile.mkdtemp(prefix="stiti-pe-")   # never the real ~/.stiti/models
os.environ["STITI_E2V_NIGHTLY"] = "off"
os.environ.pop("STITI_RECORDER", None)
os.environ["STITI_VOICE_EMOTION"] = "off"

import json, resource, time                                                    # noqa: E401,E402
from datetime import datetime, timedelta                                      # noqa: E402
from types import SimpleNamespace                                             # noqa: E402

import numpy as np                                                            # noqa: E402

from stiti.config import CFG                                                  # noqa: E402
from stiti.db import one, q                                                   # noqa: E402
from stiti.learn import emotion_train, labels, personal, recorder             # noqa: E402

# never run against the owner's real brain folder: a temp dir, or CI's own throwaway home
assert CFG.home.resolve() != (Path.home() / ".stiti").resolve() and (
    str(CFG.home).startswith(("/var/", "/tmp", "/private")) or os.environ.get("CI") or CFG.home.name.endswith("-ci")
), f"STITI_HOME must be a temp/CI dir, got {CFG.home}"
q("TRUNCATE voice_turns, emotion_labels RESTART IDENTITY CASCADE")
q("DELETE FROM owner_profile WHERE key LIKE 'recorder%%'")
from stiti import profile                                                     # noqa: E402
profile._all.cache_clear()
checks: dict[str, bool] = {}
rng = np.random.default_rng(7)
SR = 16000


def tone(sec=1.0, f=140.0, amp=0.2):
    t = np.arange(int(SR * sec)) / SR
    return (amp * np.sin(2 * np.pi * f * t) * (1 + 0.3 * np.sin(2 * np.pi * 3 * t))).astype(np.float32)


def episode(text, privacy=1, emo=None):
    return one("""INSERT INTO episodes(speaker, text, privacy, emotion) VALUES ('user', %s, %s, %s) RETURNING id""",
               (text, privacy, json.dumps(emo or {"label": "calm", "text": "calm", "text_conf": 0.6})))["id"]


def files():
    d = CFG.home / "recordings"
    return sorted(p for p in d.rglob("*") if p.is_file()) if d.exists() else []


# ---------- 1. recorder: OFF by default writes nothing ----------
eng = SimpleNamespace(last_user_ep=episode("I'm so tired today"), skip_turn=False, session=None)
commit = SimpleNamespace(res=SimpleNamespace(ms=180.0, no_speech_prob=0.05, avg_logprob=-0.3), speech_ms=900,
                         state="finished", timed_out=False, overlap=False, barged=False, start_t=10.0, end_t=11.0,
                         commit_t=11.45)
recorder.on_turn(eng, "I'm so tired today", tone(), commit, ("tired", 0.45), None, wait=True)
checks["recorder OFF by default"] = not recorder.enabled()
checks["OFF writes nothing (no rows, no files)"] = one("SELECT count(*) n FROM voice_turns")["n"] == 0 and not files()

# ---------- 2. recorder ON: audio + metadata ----------
recorder.set_enabled(True)
recorder.on_turn(eng, "I'm so tired today", tone(), commit, ("tired", 0.45), None, wait=True)
row = one("SELECT * FROM voice_turns ORDER BY id DESC LIMIT 1")
f = files()
checks["ON writes one FLAC under recordings/YYYY-MM-DD/"] = (len(f) == 1 and f[0].suffix == ".flac"
                                                            and f[0].parent.name == datetime.now(CFG.tz).strftime("%Y-%m-%d"))
checks["row has transcript, timings, STT conf, prosody, moods"] = bool(
    row and row["transcript"] == "I'm so tired today" and row["pause_ms"] == 450 and row["speech_ms"] == 900
    and row["turn_state"] == "finished" and abs(row["no_speech_prob"] - 0.05) < 1e-6 and row["prosody"]
    and row["voice_label"] == "tired" and row["text_label"] == "calm" and row["episode_id"] == eng.last_user_ep
    and row["duration_ms"] == 1000)
checks["folder is private (0700) + file 0600"] = (oct((CFG.home / "recordings").stat().st_mode)[-3:] == "700"
                                                  and oct(f[0].stat().st_mode)[-3:] == "600") if f else False
eng2 = SimpleNamespace(last_user_ep=episode("crisis words", privacy=2), skip_turn=False, session=None)
recorder.on_turn(eng2, "crisis words", tone(), commit, None, None, wait=True)
checks["P2 (crisis) turns are never recorded"] = one("SELECT count(*) n FROM voice_turns")["n"] == 1

# ---------- 3. retention ----------
old_id = recorder.record_turn(tone(0.5), "old turn", when=datetime.now(CFG.tz) - timedelta(days=40))
old_file = recorder.root() / one("SELECT path FROM voice_turns WHERE id=%s", (old_id,))["path"]
ret = recorder.enforce_retention()
checks["audio older than 30 days deleted, features kept"] = (ret["expired"] == 1 and not old_file.exists()
    and one("SELECT path FROM voice_turns WHERE id=%s", (old_id,))["path"] is None)
recorder.record_turn(tone(0.5), "another turn")
os.environ["STITI_RECORDER_MAX_GB"] = str(row["bytes"] * 1.5 / 1e9)
ret = recorder.enforce_retention()
os.environ.pop("STITI_RECORDER_MAX_GB")
checks["size cap drops the oldest audio first"] = (ret["over_cap"] == 1 and len(files()) == 1
    and one("SELECT path FROM voice_turns WHERE transcript='another turn'")["path"] is not None)

# ---------- 4. labels from his words (EN + Hinglish) ----------
cases = {
    "I'm so tired today": [("tired", 1)], "thak gaya hoon yaar": [("tired", 1)], "tension ho rahi hai": [("stressed", 1)],
    "mujhe gussa aa raha hai": [("angry", 1)], "aaj bahut khush hoon": [("happy", 1)], "feeling low": [("sad", 1)],
    "main theek hoon": [("calm", 1)], "I'm not angry, just tired": [("angry", -1), ("tired", 1)],
    "main udaas nahi hoon": [("sad", -1)], "why do you think I'm sad": [("sad", -1)],
    "kisne kaha main gussa hoon": [("angry", -1)],
    "my mom is tired": [], "are you tired?": [], "you're angry": [], "tum gussa ho": [],
    "okay set an alarm for 6": [], "the movie was so sad": [], "if I'm tired I'll sleep": [],
}
bad = {t: labels.extract(t) for t, want in cases.items()
       if sorted((m, p) for m, p, _ in labels.extract(t)) != sorted(want)}
checks[f"self-report/correction extraction ({len(cases)} EN+Hinglish cases)"] = not bad
q("TRUNCATE voice_turns, emotion_labels RESTART IDENTITY CASCADE")
t0 = datetime.now(CFG.tz) - timedelta(hours=1)
seq = [("what's on my calendar", "stressed"), ("I'm so stressed about the exam", None), ("ok next one", None),
       ("you sound angry", None), ("set a timer", "angry"), ("I'm not angry", "angry"), ("main udaas nahi hoon", "calm")]
ids = [recorder.record_turn(np.zeros(0), t, when=t0 + timedelta(seconds=20 * i), force=True,
                            meta={"session_id": 1, "fused_label": fl, "text_label": None}) for i, (t, fl) in enumerate(seq)]
st = labels.rebuild()
lab = {(r["voice_turn_id"], r["label"], r["polarity"], r["source"]) for r in q("SELECT * FROM emotion_labels")}
checks["self-report labels its turn (+1.0)"] = (ids[1], "stressed", 1, "self_report") in lab
checks["neighbours get the self-report (+0.5)"] = {(ids[0], "stressed", 1, "neighbour"), (ids[2], "stressed", 1, "neighbour")} <= lab
checks["correction → NOT-label on this + previous turn"] = {(ids[5], "angry", -1, "correction"), (ids[4], "angry", -1, "correction")} <= lab
checks["Hinglish denial → NOT sad"] = (ids[6], "sad", -1, "self_report") in lab
q("TRUNCATE voice_turns, emotion_labels RESTART IDENTITY CASCADE")
recorder.record_turn(np.zeros(0), "kaam ho gaya", force=True,
                     meta={"text_label": "happy", "text_conf": 0.9, "e2v_label": "happy", "e2v_conf": 0.6})
recorder.record_turn(np.zeros(0), "kal dekhte", force=True,
                     meta={"text_label": "happy", "text_conf": 0.9, "e2v_label": "calm", "e2v_conf": 0.6})
labels.rebuild()
checks["text+voice agreement → pseudo-label (0.3), disagreement → none"] = [
    (r["label"], r["source"], round(r["weight"], 2)) for r in q("SELECT * FROM emotion_labels")] == [("happy", "pseudo", 0.3)]

# ---------- 5. training + gating on synthetic embeddings ----------
SAY = {"calm": "main theek hoon", "tired": "I'm so tired", "stressed": "tension ho rahi hai", "happy": "I'm really happy"}
SPEAKER = rng.normal(0, 1, 768).astype(np.float32) * 2.0         # "his voice": a big constant offset
CENT = {m: rng.normal(0, 1, 768).astype(np.float32) for m in SAY}
PROS = {"calm": (-27, 130, 18, 2.5), "tired": (-35, 112, 10, 1.6), "stressed": (-20, 165, 32, 3.6), "happy": (-22, 150, 35, 3.0)}


def synth(days: int, per_day: int, signal: float, generic_acc: float, pros_acc: float = 0.35):
    q("TRUNCATE voice_turns, emotion_labels RESTART IDENTITY CASCADE")
    base = datetime.now(CFG.tz) - timedelta(days=days)
    sid = 0
    for d in range(days):
        for m in SAY:
            for k in range(per_day):
                sid += 1
                emb = SPEAKER + signal * CENT[m] + rng.normal(0, 1, 768).astype(np.float32)
                g = m if rng.random() < generic_acc else rng.choice([x for x in personal.MOODS if x != m])
                gp = m if rng.random() < pros_acc else rng.choice(["calm", "stressed", "tired"])
                db, pitch, sd, rate = PROS[m]
                pr = {"db": db + rng.normal(0, 2), "pitch": pitch + rng.normal(0, 8), "pitch_sd": sd + rng.normal(0, 4),
                      "rate": rate + rng.normal(0, 0.3)}
                recorder.record_turn(np.zeros(0), SAY[m], force=True, when=base + timedelta(days=d, minutes=10 * k + sid),
                                     meta={"session_id": sid, "embedding": emb, "e2v_label": g, "e2v_conf": 0.5,
                                           "prosody": pr, "prosody_label": gp})
    # a few unlabeled chats too (normalization uses them)
    for i in range(20):
        recorder.record_turn(np.zeros(0), "what time is it", force=True, meta={
            "session_id": 10_000 + i, "embedding": SPEAKER + rng.normal(0, 1, 768).astype(np.float32), "e2v_label": "calm",
            "prosody": {"db": -27.0, "pitch": 130.0, "pitch_sd": 18.0, "rate": 2.5}, "prosody_label": "calm"})
    labels.rebuild()


ru0 = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
synth(days=6, per_day=2, signal=0.6, generic_acc=0.35)
t = time.perf_counter()
A = emotion_train.train("e2v")
P = emotion_train.train("prosody")
train_s = time.perf_counter() - t
ru1 = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
print(f"  A e2v: personal {A.get('personal_f1')} vs generic {A.get('generic_f1')} Δ{A.get('delta')} "
      f"folds {A.get('fold_wins')}-{A.get('fold_losses')} T={A.get('T')} cov={A.get('coverage')} → {A['status']}")
print(f"  A prosody: personal {P.get('personal_f1')} vs generic {P.get('generic_f1')} → {P['status']}")
print(f"  train both heads: {train_s * 1000:.0f} ms on {A['rows']} rows; peak RSS +{(ru1 - ru0) / 1e6:.1f} MB")
checks["personal e2v head ACTIVATES when it beats generic"] = A["active"] and A["delta"] >= emotion_train.MARGIN
checks["personal prosody head ACTIVATES when it beats the rule"] = P["active"]
checks["model + metrics versioned on disk"] = all((personal.model_dir() / n).exists() for n in
                                                  ("e2v-v1.npz", "e2v-v1.json", "metrics.jsonl", "active.json"))
checks["training is fast (< 5 s for both heads)"] = train_s < 5

# ---------- 6. live use of the active head ----------
x_tired = SPEAKER + 0.6 * CENT["tired"] + rng.normal(0, 0.5, 768).astype(np.float32)
pred = personal.predict("e2v", x_tired)
checks["active e2v head predicts his 'tired' voice"] = bool(pred and pred[0] == "tired")
from stiti.voice import emotion_model, prosody                                # noqa: E402
dec = emotion_model.decide({"emb": x_tired, "scores": {"neutral": 0.9, "sad": 0.1}})
checks["emotion2vec path uses the personal head over the generic map"] = bool(dec and dec[0] == "tired")
checks["provenance marks it personal"] = personal.provenance(*dec) == "personal" if dec else False
pp = prosody.update_and_score({"db": -35.5, "pitch": 111.0, "pitch_sd": 9.0, "rate": 1.5})
checks["prosody path uses the personal head"] = pp[0] == "tired"
from stiti.brain.emotion import fuse                                          # noqa: E402
s1 = fuse("hmm okay", "calm", 0.6, dec[0], dec[1])
personal.note("tired", 0.61, "generic")
s2 = fuse("hmm okay", "calm", 0.6, "tired", 0.61)
checks["fuse() trusts the calibrated personal read"] = s1.label == "tired" and s1.as_json()["voice_src"] == "personal"
checks["fuse() keeps the old bar for a generic read"] = s2.label == "calm"
s3 = fuse("I'm not tired", "calm", 0.6, dec[0], dec[1])
checks["his denial still wins over the personal head"] = s3.label == "calm"

# ---------- 7. gating: no personal signal → stays generic; too few days → stays generic ----------
synth(days=6, per_day=2, signal=0.0, generic_acc=0.75)
B = emotion_train.train("e2v")
print(f"  B (no signal): personal {B.get('personal_f1')} vs generic {B.get('generic_f1')} → {B['status']} ({B.get('why')})")
checks["NO activation when generic is better (and the old head is switched off)"] = (
    not B["active"] and personal.active_versions().get("e2v") is None and personal.predict("e2v", x_tired) is None)
synth(days=2, per_day=4, signal=0.6, generic_acc=0.35)
C = emotion_train.train("e2v")
print(f"  C (2 days): {C['status']} ({C.get('why')})")
checks["NO activation with < 3 days of data"] = not C["active"]
synth(days=4, per_day=1, signal=0.6, generic_acc=0.35)
q("DELETE FROM emotion_labels WHERE voice_turn_id IN (SELECT id FROM voice_turns WHERE transcript <> 'I''m so tired')")
D = emotion_train.train("e2v")
checks["one mood only → not_enough_labels, nothing activated"] = D["status"] == "not_enough_labels" and not D["active"]

# ---------- 8. nightly job + delete ----------
synth(days=6, per_day=2, signal=0.6, generic_acc=0.35)
N = emotion_train.nightly()
run = one("SELECT status, stats FROM consolidation_runs WHERE job='emotion_train' ORDER BY id DESC LIMIT 1")
checks["nightly(): labels → train → gate, logged in consolidation_runs"] = (
    run and run["status"] == "ok" and N["e2v"]["active"] and N["labels"]["self_report"] > 0)
recorder.record_turn(tone(0.3), "keep me until delete")
res = recorder.delete()
checks["`stiti recordings delete` removes audio, rows, labels and models"] = (
    not files() and one("SELECT count(*) n FROM voice_turns")["n"] == 0
    and one("SELECT count(*) n FROM emotion_labels")["n"] == 0 and not personal.active_versions()
    and personal.predict("e2v", x_tired) is None and res["models_deleted"])
recorder.set_enabled(False)
checks["recorder can be switched off again"] = not recorder.enabled()

for t_, got in bad.items():
    print(f"  extract mismatch: {t_!r} → {got}")
for k, v in checks.items():
    print(("OK  " if v else "FAIL"), k)
ok = sum(checks.values())
print(f"{ok}/{len(checks)} personal emotion + recorder checks")
sys.exit(0 if ok == len(checks) else 1)
