"""Opt-in LOCAL conversation recorder (D28). Default OFF.

When Tejmul turns it on (menubar "Record our chats (local)", or `stiti recordings on`), every committed voice turn
is kept so Stiti can learn HIS voice:
  ~/.stiti/recordings/YYYY-MM-DD/HHMMSS-<id>.flac   16 kHz mono, ~20 KB per second of speech
  voice_turns row: transcript, timings (speech, pause before commit, turn state), STT confidence, prosody, the voice /
                   text / fused mood Stiti used, and the emotion2vec embedding when the live model ran.
Privacy: never uploaded, never shown on any web/UI page, not in the encrypted backup, crisis (P2) turns are never
kept, folder is 0700. Retention: 30 days / 2 GB (owner_profile `recorder_days`, `recorder_max_gb`); expired audio is
deleted but its compact features + labels stay so the personal model never forgets. `stiti recordings delete`
removes the audio, the rows and the personal models learned from them.
"""
from __future__ import annotations

import os
import shutil
import threading
import time
from datetime import date, datetime
from pathlib import Path

import numpy as np

from .. import profile
from ..config import CFG
from ..db import one, q

SR = 16000
DEFAULT_DAYS, DEFAULT_MAX_GB = 30, 2.0
_writes = 0


def root() -> Path:
    d = CFG.home / "recordings"
    d.mkdir(parents=True, exist_ok=True)
    try:
        d.chmod(0o700)
    except OSError:
        pass
    return d


def enabled() -> bool:
    env = os.getenv("STITI_RECORDER")
    if env in ("on", "off"):
        return env == "on"
    return (profile.get("recorder", "off") or "off") == "on"


def set_enabled(on: bool) -> None:
    profile.set("recorder", "on" if on else "off", source="owner")


def limits() -> tuple[int, int]:
    def num(key: str, env: str, default: float) -> float:
        try:
            return float(os.getenv(env) or profile.get(key) or default)
        except ValueError:
            return default
    days = int(num("recorder_days", "STITI_RECORDER_DAYS", DEFAULT_DAYS))
    max_bytes = int(num("recorder_max_gb", "STITI_RECORDER_MAX_GB", DEFAULT_MAX_GB) * 1e9)
    return days, max_bytes


def _write_audio(path: Path, audio: np.ndarray, sr: int) -> tuple[int, Path]:
    a = np.clip(np.asarray(audio, dtype=np.float32).reshape(-1), -1.0, 1.0)
    try:
        import soundfile as sf
        sf.write(str(path), a, sr, format="FLAC", subtype="PCM_16")
    except Exception:                            # no libsndfile: plain 16-bit wav
        import wave
        path = path.with_suffix(".wav")
        with wave.open(str(path), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(sr)
            w.writeframes((a * 32767).astype("<i2").tobytes())
    path.chmod(0o600)
    return path.stat().st_size, path


def record_turn(audio, transcript: str, *, sr: int = SR, meta: dict | None = None,
                when: datetime | None = None, force: bool = False) -> int | None:
    """Store one turn (audio + metadata row). Returns the voice_turns id, or None when the recorder is OFF."""
    global _writes
    if not (force or enabled()):
        return None
    m = dict(meta or {})
    when = when or datetime.now(CFG.tz)
    a = np.asarray(audio, dtype=np.float32).reshape(-1)
    emb = m.pop("embedding", None)
    import json
    row = one("""INSERT INTO voice_turns(recorded_at, session_id, episode_id, duration_ms, transcript, speech_ms, pause_ms,
                     turn_state, timed_out, overlap, barged, stt_ms, no_speech_prob, avg_logprob, prosody, prosody_label,
                     voice_label, voice_conf, voice_src, text_label, text_conf, fused_label, e2v_label, e2v_conf,
                     e2v_scores, embedding)
                 VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
              (when, m.get("session_id"), m.get("episode_id"), int(len(a) * 1000 / sr), transcript,
               m.get("speech_ms"), m.get("pause_ms"), m.get("turn_state"), m.get("timed_out"), m.get("overlap"),
               m.get("barged"), m.get("stt_ms"), m.get("no_speech_prob"), m.get("avg_logprob"),
               json.dumps(m["prosody"]) if m.get("prosody") else None, m.get("prosody_label"),
               m.get("voice_label"), m.get("voice_conf"), m.get("voice_src"), m.get("text_label"),
               m.get("text_conf"), m.get("fused_label"), m.get("e2v_label"), m.get("e2v_conf"),
               json.dumps(m["e2v_scores"]) if m.get("e2v_scores") else None,
               np.asarray(emb, dtype=np.float32).reshape(-1) if emb is not None else None))
    rid = row["id"]
    if len(a):
        day = root() / f"{when.astimezone(CFG.tz):%Y-%m-%d}"
        day.mkdir(exist_ok=True)
        try:
            size, path = _write_audio(day / f"{when.astimezone(CFG.tz):%H%M%S}-{rid}.flac", a, sr)
            q("UPDATE voice_turns SET path=%s, bytes=%s WHERE id=%s", (str(path.relative_to(root())), size, rid))
        except Exception as e:                   # disk full etc.: the features row is still useful
            print(f"[recorder] audio not saved: {e}")
    _writes += 1
    if _writes % 25 == 0:
        enforce_retention()
    return rid


def on_turn(engine, text: str, audio, c=None, voice: tuple | None = None, work: threading.Thread | None = None,
            *, wait: bool = False) -> None:
    """The voice loop's one hook after a committed turn. A no-op (no thread, no I/O) while the recorder is OFF."""
    if audio is None or not enabled():
        return

    def go():
        try:
            if work is not None:
                work.join(10)                    # the engine stores the episode (mood, privacy) first
            _record_from_loop(engine, text, audio, c, voice)
        except Exception as e:
            print(f"[recorder] {type(e).__name__}: {e}")
    if wait:
        go()
    else:
        threading.Thread(target=go, daemon=True, name="recorder").start()


def _record_from_loop(engine, text, audio, c, voice) -> int | None:
    from ..voice import emotion_model, prosody
    from . import personal
    a = np.asarray(getattr(audio, "audio", audio), dtype=np.float32).reshape(-1)
    ep_id = None if getattr(engine, "skip_turn", False) else getattr(engine, "last_user_ep", None)
    ep = one("SELECT id, session_id, privacy, emotion FROM episodes WHERE id=%s", (ep_id,)) if ep_id else None
    if ep and ep["privacy"] >= 2:
        return None                               # crisis / private turns are never kept
    emo = (ep or {}).get("emotion") or {}
    res = getattr(c, "res", None)
    feat = prosody.features(a, SR, len(text.split()))
    m = {"session_id": (ep or {}).get("session_id") or getattr(engine, "session", None),
         "episode_id": ep_id if ep else None, "prosody": feat, "prosody_label": prosody.generic_label(feat),
         "speech_ms": getattr(c, "speech_ms", None), "turn_state": getattr(c, "state", None),
         "timed_out": getattr(c, "timed_out", None), "overlap": getattr(c, "overlap", None),
         "barged": getattr(c, "barged", None),
         "stt_ms": getattr(res, "ms", None), "no_speech_prob": getattr(res, "no_speech_prob", None),
         "avg_logprob": getattr(res, "avg_logprob", None),
         "text_label": emo.get("text"), "text_conf": emo.get("text_conf"), "fused_label": emo.get("label")}
    if c is not None and getattr(c, "commit_t", 0) and getattr(c, "end_t", 0):
        m["pause_ms"] = int(round(max(0.0, c.commit_t - c.end_t) * 1000))
    if voice:
        m["voice_label"], m["voice_conf"] = voice[0], float(voice[1])
        m["voice_src"] = personal.provenance(voice[0], voice[1]) or "generic"
    if os.getenv("STITI_VOICE_EMOTION", "off") != "off":   # the live emotion2vec pass runs in parallel
        deadline = time.time() + 2.0
        r = emotion_model.recent(audio)
        while r is None and time.time() < deadline:
            time.sleep(0.05)
            r = emotion_model.recent(audio)
        if r is not None:
            g = emotion_model.generic_label(r["scores"])
            m.update(embedding=r.get("emb"), e2v_scores=r["scores"],
                     e2v_label=g[0] if g else None, e2v_conf=g[1] if g else None)
    return record_turn(a, text, meta=m)


def _drop_audio(rows: list[dict]) -> int:
    n = 0
    for r in rows:
        if r.get("path"):
            try:
                (root() / r["path"]).unlink(missing_ok=True)
            except OSError:
                pass
        q("UPDATE voice_turns SET path=NULL, bytes=0 WHERE id=%s", (r["id"],))
        n += 1
    _prune_dirs()
    return n


def _prune_dirs() -> None:
    for d in root().iterdir():
        if d.is_dir() and not any(d.iterdir()):
            d.rmdir()


def enforce_retention() -> dict:
    """Delete audio older than the day cap, then the oldest audio until under the size cap. Features stay."""
    days, cap = limits()
    old = q("""SELECT id, path FROM voice_turns WHERE path IS NOT NULL
               AND recorded_at < now() - make_interval(days => %s) ORDER BY recorded_at""", (days,))
    out = {"expired": _drop_audio(old), "over_cap": 0}
    total = int(one("SELECT COALESCE(sum(bytes),0) t FROM voice_turns WHERE path IS NOT NULL")["t"])
    if total > cap:
        drop = []
        for r in q("SELECT id, path, bytes FROM voice_turns WHERE path IS NOT NULL ORDER BY recorded_at, id"):
            if total <= cap:
                break
            drop.append(r)
            total -= r["bytes"]
        out["over_cap"] = _drop_audio(drop)
    return out


def delete(before: date | None = None) -> dict:
    """`stiti recordings delete`: audio + rows (+ labels). With no date, also every personal model learned from them."""
    if before is None:
        n = one("SELECT count(*) n FROM voice_turns")["n"]
        q("DELETE FROM voice_turns")
        shutil.rmtree(root(), ignore_errors=True)
        root()
        from . import personal
        shutil.rmtree(personal.model_dir(), ignore_errors=True)
        return {"deleted_turns": n, "models_deleted": True}
    rows = q("SELECT id, path FROM voice_turns WHERE (recorded_at AT TIME ZONE %s)::date < %s", (CFG.tz.key, before))
    for r in rows:
        if r["path"]:
            (root() / r["path"]).unlink(missing_ok=True)
    q("DELETE FROM voice_turns WHERE id = ANY(%s)", ([r["id"] for r in rows],))
    _prune_dirs()
    return {"deleted_turns": len(rows), "models_deleted": False}


def status() -> dict:
    r = one("""SELECT count(*) n, count(path) with_audio, COALESCE(sum(bytes),0) bytes, min(recorded_at) first,
                      count(embedding) embedded FROM voice_turns""")
    lab = one("SELECT count(DISTINCT voice_turn_id) n FROM emotion_labels")["n"]
    days, cap = limits()
    from . import personal
    return {"recorder": "on" if enabled() else "off", "turns": r["n"], "with_audio": r["with_audio"],
            "mb": round(r["bytes"] / 1e6, 1), "embedded": r["embedded"], "labelled": lab,
            "since": r["first"].astimezone(CFG.tz).strftime("%Y-%m-%d") if r["first"] else None,
            "retention": f"{days} days / {cap / 1e9:g} GB", "active_models": personal.active_versions()}


def cli(args: list[str]) -> None:
    """stiti recordings [status|on|off|delete [--before YYYY-MM-DD] [--yes]|train]"""
    sub = args[0] if args else "status"
    if sub == "on":
        set_enabled(True)
        print("🎙️  Recording our chats locally (~/.stiti/recordings, 30 days / 2 GB, never uploaded). "
              "Stop: `stiti recordings off`. Restart Stiti.app if it's running.")
    elif sub == "off":
        set_enabled(False)
        print("Recorder OFF. Nothing new will be kept (existing recordings stay until `stiti recordings delete`).")
    elif sub == "delete":
        before = None
        if "--before" in args:
            before = date.fromisoformat(args[args.index("--before") + 1])
        what = f"recordings before {before}" if before else "ALL recordings, their labels and the personal emotion models"
        if "--yes" not in args and input(f"Delete {what}? [y/N] ").strip().lower() not in ("y", "yes"):
            print("Nothing deleted.")
            return
        print(delete(before))
    elif sub == "train":
        from .emotion_train import nightly
        import json
        print(json.dumps(nightly(verbose=True), indent=2, default=str))
    else:
        for k, v in status().items():
            print(f"{k:>14}: {v}")
