"""The mastery map of one source (his file or a topic) — feature 4 (docs/FEATURE_PLAN.md; iTutor techniques 5 + 6 in
docs/research/apps/itutor.md). Pure Python over what the brain already holds, no LLM:

- groups: Strong (p ≥ 0.8) · Focus (seen, below 0.8 — shaky, weak, or strong once and dropped) · Not started (never
  answered), from ~/.stiti/tutor/mastery/<key>.json over the concept map ~/.stiti/tutor/concepts/<key>.json
- heatmap: concept × day for the last 30 days, from the append-only `mastery_events` (answers per day + where p ended)
- at risk on exam day: (1 − FSRS recall at the exam date) × concept weight, for every concept below 0.9 recall; a
  concept with no review card yet counts its mastery p as its recall
The Lessons page's Map view and the board's "Map" page at the start of a coached lesson both read from here.
"""
from __future__ import annotations

import json
from datetime import date, datetime, time as dtime, timedelta, timezone

from .mastery import KNOWN, PRIOR, SHAKY

DAYS = 30
RISK_RECALL = 0.9          # below this predicted recall on exam day = at risk (srs.at_risk uses the same line)
RISK_MAX = 8
EXAM_HOUR = 9              # an exam date with no time: 9 am local


def _home():
    from ..config import CFG
    return CFG.home


def load(key: str) -> dict | None:
    """Concepts + mastery of one source key, or None when neither file exists."""
    home = _home()
    concepts: list[dict] = []
    m: dict = {}
    try:
        concepts = [c for c in json.loads((home / "tutor" / "concepts" / f"{key}.json").read_text())
                    if isinstance(c, dict) and c.get("id")]
    except (OSError, ValueError, TypeError):
        pass
    try:
        m = json.loads((home / "tutor" / "mastery" / f"{key}.json").read_text())
        if not isinstance(m, dict):
            m = {}
    except (OSError, ValueError, TypeError):
        pass
    if not concepts and not m:
        return None
    p = {str(k): float(v) for k, v in (m.get("p") or {}).items() if isinstance(v, (int, float))}
    seen = {str(k): float(v) for k, v in (m.get("seen") or {}).items() if isinstance(v, (int, float))}
    if not concepts:                                  # mastery without a cached map: the ids are all we have
        concepts = [{"id": i, "name": i, "unit": "", "weight": 2} for i in p]
    return {"source": str(m.get("source") or ""), "concepts": concepts, "p": p, "seen": seen,
            "exam": m.get("exam") if isinstance(m.get("exam"), str) else None}


def level(p: float | None, seen: bool) -> str:
    if p is not None and p >= KNOWN:
        return "strong"
    if not seen:
        return "new"
    return "shaky" if (p if p is not None else PRIOR) >= SHAKY else "weak"


def groups(concepts: list[dict], p: dict[str, float], seen: dict[str, float],
           ever_strong: set[str] | None = None) -> dict[str, list[dict]]:
    """Strong / Focus / Not started, each concept with id, name, unit, weight, p, level (strong|shaky|weak|new) and
    dropped (was strong once, now below). Book order inside each group."""
    out: dict[str, list[dict]] = {"strong": [], "focus": [], "not_started": []}
    ever = ever_strong or set()
    for c in concepts:
        cid = str(c["id"])
        was_seen = cid in seen or cid in p
        pv = p.get(cid)
        lv = level(pv, was_seen)
        item = {"id": cid, "name": str(c.get("name") or cid)[:60], "unit": str(c.get("unit") or "")[:60],
                "weight": int(c.get("weight") or 2), "p": round(pv, 2) if pv is not None else None, "level": lv,
                "dropped": lv != "strong" and cid in ever}
        out["strong" if lv == "strong" else "not_started" if lv == "new" else "focus"].append(item)
    return out


def _events(key: str, since: datetime) -> list[dict]:
    try:
        from ..db import q
        return q("""SELECT concept_id, verdict, p_after, origin, at FROM mastery_events
                    WHERE source_key=%s AND at >= %s ORDER BY at""", (key, since))
    except Exception:
        return []


def _ever_strong(key: str) -> set[str]:
    try:
        from ..db import q
        return {r["concept_id"] for r in q("""SELECT DISTINCT concept_id FROM mastery_events
                                               WHERE source_key=%s AND p_after >= %s""", (key, KNOWN))}
    except Exception:
        return set()


def heatmap(key: str, concepts: list[dict], days: int = DAYS, now: datetime | None = None) -> dict:
    """{"days": [ISO date × days, oldest first], "rows": [{id, name, cells: [[answers, p_end] | None per day]}]}.
    Days are his local calendar days; an "inferred" bump (a probe that implied an earlier concept) isn't an answer."""
    now = (now or datetime.now(timezone.utc)).astimezone()
    today = now.date()
    day_list = [today - timedelta(days=days - 1 - i) for i in range(days)]
    start = datetime.combine(day_list[0], dtime.min).astimezone()
    idx = {d: i for i, d in enumerate(day_list)}
    names = {str(c["id"]): str(c.get("name") or c["id"])[:60] for c in concepts}
    cells: dict[str, list] = {}
    for e in _events(key, start):
        cid = e["concept_id"]
        if cid not in names or e["verdict"] == "inferred":
            continue
        i = idx.get(e["at"].astimezone().date())
        if i is None:
            continue
        row = cells.setdefault(cid, [None] * days)
        n = (row[i][0] if row[i] else 0) + 1
        row[i] = [n, round(float(e["p_after"]), 2)]
    order = [str(c["id"]) for c in concepts]
    return {"days": [d.isoformat() for d in day_list],
            "rows": [{"id": cid, "name": names[cid], "cells": cells[cid]} for cid in order if cid in cells]}


def parse_exam(text) -> date | None:
    if not isinstance(text, str) or len(text) != 10:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def at_risk(key: str, concepts: list[dict], p: dict[str, float], seen: dict[str, float], exam: date,
            limit: int = RISK_MAX) -> list[dict]:
    """Concepts whose predicted recall on exam day is below 0.9, riskiest first: risk = (1 − recall) × weight."""
    when = datetime.combine(exam, dtime(EXAM_HOUR)).astimezone()
    cards: dict[str, dict] = {}
    try:
        from . import srs
        cards = {r["concept_id"]: r for r in srs.concept_cards(key)}
        recall = {cid: srs.recall_at(r, when) for cid, r in cards.items()}
    except Exception:
        recall = {}
    out = []
    for c in concepts:
        cid = str(c["id"])
        r = recall.get(cid)
        if r is None:                                  # no card yet: what he knows now is the best guess
            r = p.get(cid, 0.0) if (cid in seen or cid in p) else 0.0
        if r >= RISK_RECALL:
            continue
        w = int(c.get("weight") or 2)
        out.append({"id": cid, "name": str(c.get("name") or cid)[:60], "recall": round(r, 2), "weight": w,
                    "risk": round((1 - r) * w, 2), "card": cid in cards})
    out.sort(key=lambda x: (-x["risk"], -x["weight"], x["recall"]))
    return out[:limit]


def build(key: str, exam: date | None = None, now: datetime | None = None) -> dict | None:
    """The whole map of one source key (see the module docstring), or None if the key is unknown."""
    d = load(key)
    if d is None:
        return None
    if exam is None:
        exam = parse_exam(d["exam"])
    today = (now or datetime.now(timezone.utc)).astimezone().date()
    g = groups(d["concepts"], d["p"], d["seen"], _ever_strong(key))
    out = {"key": key, "source": d["source"], "total": len(d["concepts"]), "groups": g,
           "counts": {k: len(v) for k, v in g.items()}, "heatmap": heatmap(key, d["concepts"], now=now),
           "exam": exam.isoformat() if exam else None, "exam_days": (exam - today).days if exam else None,
           "at_risk": []}
    if exam and exam >= today:
        out["at_risk"] = at_risk(key, d["concepts"], d["p"], d["seen"], exam)
    return out


def board_ops(concepts: list, mastery, due: int = 0) -> list:
    """The board's "Map" notes page: a line per group (points), the counts as a small table (figure), and what to do
    first (remember). `concepts` are coach Concepts; `mastery` a Mastery."""
    from .lesson import Op
    rows = [{"id": c.id, "name": c.name, "unit": c.unit, "weight": c.weight} for c in concepts]
    g = groups(rows, mastery.p, mastery.seen)
    ops = [Op(type="new_page", text="Map")]
    labels = (("Strong", "strong"), ("Focus", "focus"), ("Not started", "not_started"))
    for label, k in labels:
        items = g[k]
        names = ", ".join(x["name"] for x in items[:3]) + (f" +{len(items) - 3}" if len(items) > 3 else "")
        ops.append(Op(type="text", text=f"{label} ({len(items)}): {names or 'none'}"[:80], region="points"))
    ops.append(Op(type="table", region="figure", rows=[["Group", "Topics"]] + [[lb, str(len(g[k]))] for lb, k in labels]))
    if due:
        tip = f"{due} due for review: say review any time"
    elif g["focus"]:
        tip = f"Focus first: {g['focus'][0]['name']}"
    else:
        tip = f"Strong on {len(g['strong'])} of {len(rows)}"
    ops.append(Op(type="text", text=tip[:60], region="remember"))
    return ops
