"""Tutor grading accuracy on the labelled spoken-answer set — local grader vs local + free-LLM second opinion.

NOT part of run_all (it calls the real free cloud models). Usage:
  STITI_HOME=<tmp with models symlink> PYTHONPATH=src python tests/tutor_grade_live.py [--local] [--runs N] [--gap S]
Prints a confusion matrix (rows = true verdict, columns = graded verdict), accuracy, the misses, and latency.
"""
from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path

from stiti import router
from stiti.tutor import grade
from stiti.tutor.lesson import Check

FIX = Path(__file__).parent / "fixtures" / "tutor_grade_cases.json"
LABELS = ["correct", "partial", "wrong", "idk"]
MODELS: list[str] = []
_complete = router.complete


def _spy(*a, **k):                     # which free model answered (never logs keys or prompts)
    r = _complete(*a, **k)
    MODELS.append(f"{r['provider']}/{r['model']}")
    return r


router.complete = _spy


def load() -> list[tuple[Check, dict]]:
    d = json.loads(FIX.read_text())
    out = []
    for c in d["cases"]:
        k = d["checks"][c["check"]]
        out.append((Check(kind=k["kind"], prompt=k["prompt"], expectations=list(k["expectations"]),
                          options=k.get("options")), c))
    return out


def run(use_llm: bool, gap_s: float = 0) -> dict:
    cases = load()
    grade.grade(cases[0][0], "warm up the embedder")           # first embed loads the model: not a grading cost
    conf = {t: {p: 0 for p in LABELS} for t in LABELS}
    ms, llm_ms, misses, asked, changed = [], [], [], 0, 0
    MODELS.clear()
    for chk, c in cases:
        t = time.perf_counter()
        g = grade.grade(chk, c["answer"], **({"llm": True} if use_llm else {}))
        ms.append((time.perf_counter() - t) * 1000)
        v = g["verdict"]
        conf[c["truth"]][v] += 1
        if g.get("llm_ms") is not None:
            asked += 1
            llm_ms.append(g["llm_ms"])
            time.sleep(gap_s)                                    # --gap: space calls like a real lesson
            if g.get("llm_error"):
                misses.append(f"  (LLM {g['llm_error']} after {g['llm_ms']:.0f} ms on {c['answer']!r})")
        if g.get("source") == "llm" and g.get("local_verdict") != v:
            changed += 1
        if v != c["truth"]:
            misses.append(f"  [{c['tag']}] {c['check']}: {c['answer']!r} → {v} (truth {c['truth']}"
                          f"{', local ' + g['local_verdict'] if g.get('local_verdict') not in (None, v) else ''})")
    n = len(cases)
    right = sum(conf[t][t] for t in LABELS)
    return {"n": n, "acc": right / n, "conf": conf, "misses": misses, "ms": ms, "llm_ms": llm_ms,
            "asked": asked, "changed": changed}


def show(r: dict, title: str) -> None:
    print(f"\n== {title}: {r['acc']:.1%} ({sum(r['conf'][t][t] for t in LABELS)}/{r['n']})")
    print("true\\graded " + " ".join(f"{p:>8}" for p in LABELS))
    for t in LABELS:
        print(f"{t:>11} " + " ".join(f"{r['conf'][t][p]:>8}" for p in LABELS))
    fp = sum(r["conf"][t]["correct"] for t in LABELS if t != "correct")
    fn = sum(r["conf"]["correct"][p] for p in LABELS if p != "correct")
    print(f"right answers marked not-correct: {fn} · not-right answers marked correct: {fp}")
    ms = sorted(r["ms"])
    print(f"latency per answer: median {statistics.median(ms):.0f} ms, p90 {ms[int(len(ms) * .9)]:.0f} ms, "
          f"max {ms[-1]:.0f} ms")
    if MODELS:
        print("answered by: " + ", ".join(f"{m} ×{MODELS.count(m)}" for m in sorted(set(MODELS))))
        MODELS.clear()
    if r["llm_ms"]:
        lm = sorted(r["llm_ms"])
        print(f"LLM asked on {r['asked']}/{r['n']} answers, changed {r['changed']}; LLM latency median "
              f"{statistics.median(lm):.0f} ms, p90 {lm[int(len(lm) * .9)]:.0f} ms, max {lm[-1]:.0f} ms")
    print("misses:\n" + "\n".join(r["misses"]) if r["misses"] else "misses: none")


if __name__ == "__main__":
    runs = int(sys.argv[sys.argv.index("--runs") + 1]) if "--runs" in sys.argv else 1
    gap = float(sys.argv[sys.argv.index("--gap") + 1]) if "--gap" in sys.argv else 0
    show(run(False), "local only")
    if "--local" not in sys.argv:
        for i in range(runs):
            show(run(True, gap), f"local + LLM second opinion (run {i + 1}{f', {gap:g} s apart' if gap else ''})")
