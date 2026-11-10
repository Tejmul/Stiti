"""Nightly personal emotion training + gating (D28). numpy only; seconds; no GPU, no new model download.

nightly():  retention → embed backlog (emotion2vec in a SUBPROCESS, so its 1.5 GB is returned) → labels.rebuild()
            → train + evaluate both heads → activate a head ONLY if it beats the generic predictor on his
            held-out turns. Model files + metrics are versioned in ~/.stiti/models/personal_emotion/.

Head = multinomial logistic regression (L2, class-balanced sample weights) + a complementary-label term for his
"I'm not X" corrections (Ishida et al. 2017). Features are normalized on HIS data (per-speaker normalization):
  e2v      embedding − his mean → PCA (≤32 dims, whitened)
  prosody  [db, pitch, pitch_sd, rate] z-scored
Evaluation: k-fold grouped by DAY (neighbouring turns share labels → no leakage), truth = human-sourced labels only
(pseudo-labels agree with the generic model by construction, so they never count as truth), macro-F1.
Gate: Δ macro-F1 ≥ MARGIN over generic AND over chance (1/K), more folds won than lost, ≥ MIN_EVAL turns,
≥ MIN_DAYS days.
Calibration: one temperature fitted on out-of-fold logits; the live head abstains below `threshold`.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime

import numpy as np

from ..config import CFG
from ..db import one, q
from . import labels as L
from .personal import MOODS, PROSODY_KEYS, model_dir

MARGIN, MIN_EVAL, MIN_DAYS, MIN_CLASS_N, MAX_FOLDS, KEEP_VERSIONS = 0.05, 12, 3, 5, 5, 10
PCA_DIMS = int(os.getenv("STITI_PE_PCA", "32"))


# ---------------- data ----------------
def _vec(v) -> np.ndarray:
    return np.asarray(v.to_numpy() if hasattr(v, "to_numpy") else v, dtype=np.float32)


def load(kind: str) -> dict:
    col = "embedding" if kind == "e2v" else "prosody"
    rows = q(f"""SELECT id, recorded_at, {col} AS f, e2v_label, prosody_label FROM voice_turns
                 WHERE {col} IS NOT NULL ORDER BY recorded_at, id""")
    if kind == "e2v":
        X = np.array([_vec(r["f"]) for r in rows], dtype=np.float32).reshape(len(rows), -1)
        generic = [r["e2v_label"] or "calm" for r in rows]
    else:
        X = np.array([[float(r["f"].get(k, 0.0) or 0.0) for k in PROSODY_KEYS] for r in rows],
                     dtype=np.float32).reshape(len(rows), len(PROSODY_KEYS))
        generic = [r["prosody_label"] or "calm" for r in rows]
    idx = {r["id"]: i for i, r in enumerate(rows)}
    pos: dict[int, dict[str, tuple[float, bool]]] = {}
    neg: dict[int, dict[str, float]] = {}
    for lab in q("SELECT voice_turn_id v, label, polarity, weight, source FROM emotion_labels"):
        i = idx.get(lab["v"])
        if i is None or lab["label"] not in MOODS:
            continue
        if lab["polarity"] > 0:
            w, h = pos.setdefault(i, {}).get(lab["label"], (0.0, False))
            pos[i][lab["label"]] = (max(w, lab["weight"]), h or lab["source"] in L.HUMAN_SOURCES)
        else:
            neg.setdefault(i, {})[lab["label"]] = max(neg.get(i, {}).get(lab["label"], 0.0), lab["weight"])
    y, w, human = [None] * len(rows), np.zeros(len(rows)), np.zeros(len(rows), dtype=bool)
    for i, d in pos.items():
        lab, (wt, h) = max(d.items(), key=lambda kv: kv[1][0])
        if neg.get(i, {}).get(lab, 0.0) >= wt:   # he both said it and denied it: skip
            continue
        y[i], w[i], human[i] = lab, wt, h
    negs = [(i, lab, wt) for i, d in neg.items() for lab, wt in d.items()]
    days = [r["recorded_at"].astimezone(CFG.tz).date().isoformat() for r in rows]
    return {"X": X, "y": y, "w": w, "human": human, "negs": negs, "days": days, "generic": generic,
            "ids": [r["id"] for r in rows]}


def fit_norm(kind: str, X: np.ndarray) -> dict:
    """Per-speaker normalization fitted on ALL his rows (labelled or not)."""
    if kind == "e2v":
        mu = X.mean(0, dtype=np.float64)
        k = max(1, min(PCA_DIMS, X.shape[0] - 1, X.shape[1]))
        cov = np.zeros((X.shape[1], X.shape[1]))
        for i in range(0, len(X), 512):                  # 768×768 covariance in chunks: a few MB, any n
            c = X[i:i + 512] - mu
            cov += c.T @ c
        vals, vecs = np.linalg.eigh(cov / max(1, len(X) - 1))
        top = np.argsort(vals)[::-1][:k]
        return {"mu": mu.astype(np.float32), "comps": vecs[:, top].T.astype(np.float32),
                "scale": (np.sqrt(np.clip(vals[top], 0, None)) + 1e-6).astype(np.float32)}
    X = X.copy()
    pitch = PROSODY_KEYS.index("pitch")
    voiced = X[:, pitch] > 0
    pm = X[voiced, pitch].mean() if voiced.any() else 0.0
    X[~voiced, pitch] = pm
    return {"mean": X.mean(0).astype(np.float32), "std": (X.std(0) + 1e-6).astype(np.float32)}


def transform(kind: str, X: np.ndarray, norm: dict) -> np.ndarray:
    if kind == "e2v":
        return ((X - norm["mu"]) @ norm["comps"].T) / norm["scale"]
    X = X.copy()
    pitch = PROSODY_KEYS.index("pitch")
    X[X[:, pitch] == 0, pitch] = norm["mean"][pitch]
    return (X - norm["mean"]) / norm["std"]


# ---------------- model ----------------
def _softmax(Z: np.ndarray) -> np.ndarray:
    Z = Z - Z.max(1, keepdims=True)
    E = np.exp(Z)
    return E / E.sum(1, keepdims=True)


def fit(X: np.ndarray, yi: np.ndarray, w: np.ndarray, negs: list[tuple[int, int, float]], K: int,
        l2: float = 0.05, iters: int = 300, lr: float = 0.05) -> tuple[np.ndarray, np.ndarray]:
    """Softmax regression: Σ w·CE on positives + Σ w·(−log(1−p_k)) on "not k" + L2. Full-batch Adam, deterministic."""
    n, d = X.shape
    has = yi >= 0
    counts = np.bincount(yi[has], minlength=K).astype(float)
    cw = np.where(counts > 0, has.sum() / (K * np.maximum(counts, 1)), 0.0)        # class-balanced
    sw = np.where(has, w * cw[np.clip(yi, 0, K - 1)], 0.0)
    Y = np.zeros((n, K))
    Y[has, yi[has]] = 1
    ni = np.array([a for a, _, _ in negs], dtype=int)
    nk = np.array([b for _, b, _ in negs], dtype=int)
    nw = np.array([c for _, _, c in negs], dtype=float)
    norm = sw.sum() + nw.sum() + 1e-9
    W, b = np.zeros((d, K)), np.log((counts + 1) / (counts + 1).sum())
    mW, vW, mb, vb = np.zeros_like(W), np.zeros_like(W), np.zeros_like(b), np.zeros_like(b)
    for t in range(1, iters + 1):
        P = _softmax(X @ W + b)
        G = (P - Y) * sw[:, None]
        if len(ni):
            pk = np.clip(P[ni, nk], 1e-6, 1 - 1e-6)
            Gn = -P[ni] * (pk / (1 - pk))[:, None]
            Gn[np.arange(len(ni)), nk] += pk / (1 - pk)
            np.add.at(G, ni, Gn * nw[:, None])
        gW = X.T @ G / norm + l2 * W
        gb = G.sum(0) / norm
        for p, g, m, v in ((W, gW, mW, vW), (b, gb, mb, vb)):
            m *= 0.9
            m += 0.1 * g
            v *= 0.999
            v += 0.001 * g * g
            p -= lr * (m / (1 - 0.9 ** t)) / (np.sqrt(v / (1 - 0.999 ** t)) + 1e-8)
    return W.astype(np.float32), b.astype(np.float32)


def macro_f1(truth: list[str], pred: list[str]) -> float:
    labs = sorted(set(truth))
    if not labs:
        return 0.0
    f = []
    for c in labs:
        tp = sum(1 for t, p in zip(truth, pred) if t == c and p == c)
        fp = sum(1 for t, p in zip(truth, pred) if t != c and p == c)
        fn = sum(1 for t, p in zip(truth, pred) if t == c and p != c)
        f.append(2 * tp / (2 * tp + fp + fn) if tp else 0.0)
    return float(np.mean(f))


def _temperature(logits: np.ndarray, yi: np.ndarray) -> float:
    best, bt = 1e18, 1.0
    for T in np.linspace(0.25, 5.0, 96):
        P = _softmax(logits / T)
        nll = -np.log(np.clip(P[np.arange(len(yi)), yi], 1e-9, 1)).mean()
        if nll < best:
            best, bt = nll, float(T)
    return bt


# ---------------- train + gate ----------------
def train(kind: str, *, save: bool = True) -> dict:
    t0 = time.perf_counter()
    D = load(kind)
    n = len(D["ids"])
    counts = {}
    for lab in D["y"]:
        if lab:
            counts[lab] = counts.get(lab, 0) + 1
    classes = [m for m in MOODS if counts.get(m, 0) >= MIN_CLASS_N]
    out: dict = {"kind": kind, "rows": n, "labelled": sum(1 for v in D["y"] if v), "per_class": counts,
                 "classes": classes, "active": False}
    if len(classes) < 2:
        out["status"] = "not_enough_labels"
        return _finish(kind, out, None, save, t0)
    ci = {c: k for k, c in enumerate(classes)}
    norm = fit_norm(kind, D["X"])
    X = transform(kind, D["X"], norm).astype(np.float64)
    yi = np.array([ci.get(v, -1) if v else -1 for v in D["y"]])
    negs = [(i, ci[lab], wt) for i, lab, wt in D["negs"] if lab in ci]
    days = np.array(D["days"])
    eval_mask = (yi >= 0) & D["human"]
    eval_days = sorted(set(days[eval_mask]))
    out.update(n_eval=int(eval_mask.sum()), n_days=len(eval_days))
    K = len(classes)
    oof_logits, oof_idx, folds = [], [], []
    if len(eval_days) >= 2:
        rng = np.random.default_rng(0)
        order = list(rng.permutation(eval_days))
        k = min(MAX_FOLDS, len(order))
        for f in range(k):
            test_days = set(order[f::k])
            te = np.where(eval_mask & np.isin(days, list(test_days)))[0]
            tr = ~np.isin(days, list(test_days))
            tr_idx = np.where(tr)[0]
            if not len(te) or len(set(yi[tr_idx][yi[tr_idx] >= 0])) < 2:
                continue
            remap = {g: j for j, g in enumerate(tr_idx)}
            W, b = fit(X[tr_idx], yi[tr_idx], D["w"][tr_idx],
                       [(remap[i], c, wt) for i, c, wt in negs if i in remap], K)
            lg = X[te] @ W + b
            truth = [classes[i] for i in yi[te]]
            pp = [classes[i] for i in lg.argmax(1)]
            gp = [D["generic"][i] for i in te]
            folds.append({"n": int(len(te)), "personal": round(macro_f1(truth, pp), 3),
                          "generic": round(macro_f1(truth, gp), 3)})
            oof_logits.append(lg)
            oof_idx.extend(te.tolist())
    if oof_idx:
        lg = np.vstack(oof_logits)
        oi = np.array(oof_idx)
        truth = [classes[i] for i in yi[oi]]
        pp = [classes[i] for i in lg.argmax(1)]
        gp = [D["generic"][i] for i in oi]
        T = _temperature(lg, yi[oi])
        P = _softmax(lg / T)
        thr = max(0.5, 1.0 / K + 0.2)
        keep = P.max(1) >= thr
        out.update(personal_f1=round(macro_f1(truth, pp), 3), generic_f1=round(macro_f1(truth, gp), 3),
                   personal_acc=round(float(np.mean([a == b for a, b in zip(truth, pp)])), 3),
                   generic_acc=round(float(np.mean([a == b for a, b in zip(truth, gp)])), 3),
                   T=round(T, 2), threshold=round(thr, 2), coverage=round(float(keep.mean()), 3),
                   selective_acc=round(float(np.mean([a == b for a, b, k_ in zip(truth, pp, keep) if k_]))
                                       if keep.any() else 0.0, 3), folds=folds)
        out["delta"] = round(out["personal_f1"] - out["generic_f1"], 3)
        wins = sum(f["personal"] > f["generic"] for f in folds)
        losses = sum(f["personal"] < f["generic"] for f in folds)
        out["fold_wins"], out["fold_losses"] = wins, losses
        reasons = []
        if out["n_eval"] < MIN_EVAL:
            reasons.append(f"only {out['n_eval']} labelled turns (need {MIN_EVAL})")
        if out["n_days"] < MIN_DAYS:
            reasons.append(f"only {out['n_days']} days (need {MIN_DAYS})")
        if out["delta"] < MARGIN:
            reasons.append(f"Δ macro-F1 {out['delta']:+.3f} < {MARGIN}")
        chance = 1.0 / len(set(truth))                   # a uniform guess; beating a weak generic isn't enough
        if out["personal_f1"] < chance + MARGIN:
            reasons.append(f"macro-F1 {out['personal_f1']:.3f} not above chance {chance:.3f} + {MARGIN}")
        if wins <= losses:
            reasons.append(f"won {wins} / lost {losses} folds")
        out["active"] = not reasons
        out["status"] = "activated" if out["active"] else "kept_generic"
        out["why"] = "; ".join(reasons) or "beats generic on his held-out turns"
    else:
        T, thr = 1.0, 0.6
        out["status"], out["why"] = "kept_generic", "not enough days to hold any out"
    W, b = fit(X, yi, D["w"], negs, K)
    model = {"classes": np.array(classes), "W": W, "b": b, "T": np.float32(T), "threshold": np.float32(thr), **norm}
    return _finish(kind, out, model, save, t0)


def _finish(kind: str, out: dict, model: dict | None, save: bool, t0: float) -> dict:
    out["train_ms"] = round((time.perf_counter() - t0) * 1000, 1)
    if not save:
        return out
    d = model_dir(create=True)
    active = _read_active()
    if model is not None:
        v = 1 + max([int(p.stem.split("-v")[1]) for p in d.glob(f"{kind}-v*.npz")] or [0])
        np.savez(d / f"{kind}-v{v}.npz", **model)
        (d / f"{kind}-v{v}.json").write_text(json.dumps(out, indent=1, default=str))
        out["version"] = v
        for old in sorted(d.glob(f"{kind}-v*.npz"), key=lambda p: int(p.stem.split("-v")[1]))[:-KEEP_VERSIONS]:
            if active.get(kind) != int(old.stem.split("-v")[1]):
                old.unlink(missing_ok=True)
                old.with_suffix(".json").unlink(missing_ok=True)
    # only tonight's gate decides: a head that no longer beats generic is switched off
    active[kind] = out.get("version") if out.get("active") else None
    tmp = d / "active.json.tmp"
    tmp.write_text(json.dumps(active))
    os.replace(tmp, d / "active.json")
    with open(d / "metrics.jsonl", "a") as f:
        f.write(json.dumps({"ts": datetime.now(CFG.tz).isoformat(timespec="seconds"),
                            **{k: v for k, v in out.items() if k != "folds"}}, default=str) + "\n")
    return out


def _read_active() -> dict:
    try:
        return json.loads((model_dir() / "active.json").read_text())
    except (OSError, ValueError):
        return {}


# ---------------- emotion2vec backlog (subprocess) ----------------
def embed_backlog(limit: int = 2000) -> int:
    """Rows with audio but no embedding: one subprocess loads emotion2vec once, embeds them, exits (RAM returned)."""
    mode = os.getenv("STITI_E2V_NIGHTLY", "auto")
    if mode == "off":
        return 0
    need = one("SELECT count(*) n FROM voice_turns WHERE path IS NOT NULL AND embedding IS NULL")["n"]
    if not need:
        return 0
    import importlib.util
    if importlib.util.find_spec("funasr") is None:
        return 0
    try:
        r = subprocess.run([sys.executable, "-m", "stiti.learn.emotion_train", "embed", str(limit)],
                           capture_output=True, text=True, timeout=1800, env=os.environ.copy())
        return int((r.stdout.strip().splitlines() or ["0"])[-1])
    except Exception as e:
        print(f"[emotion_train] embed backlog failed: {e}")
        return 0


def _embed_main(limit: int) -> int:
    import soundfile as sf
    from ..voice import emotion_model
    from .recorder import root
    n = 0
    for r in q("""SELECT id, path FROM voice_turns WHERE path IS NOT NULL AND embedding IS NULL
                  ORDER BY id LIMIT %s""", (limit,)):
        try:
            a, sr = sf.read(str(root() / r["path"]), dtype="float32")
            if sr != 16000 or len(a) < 1600:
                continue
            res = emotion_model.analyze(a)
            g = emotion_model.generic_label(res["scores"])
            q("""UPDATE voice_turns SET embedding=%s, e2v_scores=%s, e2v_label=%s, e2v_conf=%s WHERE id=%s""",
              (res["emb"], json.dumps(res["scores"]), g[0] if g else None, g[1] if g else None, r["id"]))
            n += 1
        except Exception as e:
            print(f"[embed] {r['id']}: {e}", file=sys.stderr)
    return n


# ---------------- the night job ----------------
def nightly(verbose: bool = False) -> dict:
    try:
        n = one("SELECT count(*) n FROM voice_turns")["n"]
    except Exception:
        return {"skipped": "no voice_turns table (apply migration 009)"}
    if not n:
        return {"skipped": "no recordings"}
    rid = one("INSERT INTO consolidation_runs(job) VALUES ('emotion_train') RETURNING id")["id"]
    out: dict = {}
    try:
        from .recorder import enforce_retention
        out["retention"] = enforce_retention()
        out["embedded"] = embed_backlog()
        out["labels"] = L.rebuild()
        for kind in ("e2v", "prosody"):
            out[kind] = train(kind)
            if verbose:
                r = out[kind]
                print(f"[{kind}] {r.get('status')}: personal {r.get('personal_f1')} vs generic {r.get('generic_f1')}"
                      f" ({r.get('why', '')})")
        slim = {k: ({kk: vv for kk, vv in v.items() if kk != "folds"} if isinstance(v, dict) else v)
                for k, v in out.items()}
        q("UPDATE consolidation_runs SET finished_at=now(), status='ok', stats=%s WHERE id=%s",
          (json.dumps(slim, default=str), rid))
    except Exception as e:
        q("UPDATE consolidation_runs SET finished_at=now(), status='failed', error=%s WHERE id=%s", (str(e), rid))
        out["error"] = f"{type(e).__name__}: {e}"
    return out


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "embed":
        print(_embed_main(int(sys.argv[2]) if len(sys.argv) > 2 else 2000))
    else:
        print(json.dumps(nightly(verbose=True), indent=2, default=str))
