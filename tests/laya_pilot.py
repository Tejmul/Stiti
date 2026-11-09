"""Laya pilot (build step 4): accuracy / latency / RSS of the 11-question pass.
Usage: uv run python tests/laya_pilot.py english|multilingual
NOTE: synthetic sentences written by Claude; replace with 30 of Tejmul's real ones.
"""
import json, resource, sys, time
sys.path.insert(0, __import__('os').path.dirname(__file__))
from stiti.decide import LayaDecider, rule_floor

from gold_turns import GOLD  # noqa: E402

ckpt = sys.argv[1]
t = time.perf_counter(); L = LayaDecider(ckpt); load_s = time.perf_counter() - t
L.ask("warm up")
hits = {"domain": 0, "is_correction": 0, "privacy": 0, "privacy+floor": 0, "emotion": 0}
lat, rows = [], []
for text, dom, corr, priv, emo in GOLD:
    d = L.ask(text); lat.append(d.latency_ms)
    f = rule_floor(text)
    pc = d.answers["privacy_level"]
    pf = "P2" if f.privacy() == 2 else pc
    c_laya = d.conf.get("is_correction.p_yes", 0) >= 0.6
    hits["domain"] += d.answers["domain"] == dom
    hits["is_correction"] += (c_laya or f.answers.get("is_correction") == "yes") == bool(corr)
    hits["privacy"] += pc == priv
    hits["privacy+floor"] += pf == priv
    hits["emotion"] += d.answers["text_emotion"] == emo
    rows.append((text, dom, d.answers["domain"], round(d.conf["domain"], 2), d.answers["text_emotion"]))
n = len(GOLD); lat.sort()
out = {"checkpoint": ckpt, "version": L.version, "load_s": round(load_s, 1),
       "acc": {k: f"{v}/{n}" for k, v in hits.items()},
       "latency_ms_p50": round(lat[n // 2]), "latency_ms_p90": round(lat[int(n * .9)]),
       "max_rss_mb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e6)}
print(json.dumps(out))
for r in rows:
    if r[1] != r[2]: print("  domain miss:", r)
