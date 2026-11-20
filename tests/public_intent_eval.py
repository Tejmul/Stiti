"""A real yardstick for the intent router (D50): 529 held-out English lines from the TEST splits of Amazon MASSIVE
(en-US), CLINC150 (incl. out-of-scope) and Google PRESTO (en-US: plain, disfluent, "no wait, I mean …"), each mapped
to one of Stiti's domains, plus 28 PRESTO "no, I meant …" follow-ups and our own life-update statements that must
never become a command. The lines live in tests/fixtures/public_intent.jsonl (CC BY — docs/THIRD_PARTY_DATA.md), so
this runs offline. None of them is ever used as a router example (scripts/build_exemplars.py drops them).

It reports accuracy per domain and per source, the share of decisions under 0.7 confidence, and what the mistakes
were. It passes on the built-in examples alone (a fresh clone, CI) and asks for more when the public example file
($STITI_HOME/data/public_exemplars.npz) is loaded.

uv run python tests/public_intent_eval.py [--misses]      STITI_PUBLIC_EX=off → measure without the public examples
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

from stiti import embed, intent
from stiti.brain.learning import UNDO_RX
from stiti.decide import decide

FIXTURE = Path(__file__).parent / "fixtures" / "public_intent.jsonl"
LOW = 0.7
# Plain statements about his life (ours, not from a dataset): people + days + clock words, even "alarm" and "list".
# Chat (or a memory look-up) — never a reminder, a to-do, a tool or a control word.
LIFE_UPDATES = [
    "My sister is flying in from Pune on Thursday", "Papa has an eye check-up tomorrow morning",
    "We have guests coming over for dinner tonight", "My flatmate is moving out next week",
    "The college fest starts on Friday", "I have a presentation at ten tomorrow", "My mom called me this morning",
    "Grandpa turns eighty next month", "I finished the assignment last night",
    "My manager moved the review to Monday", "I'm going home for Diwali next week",
    "My best friend is getting married in December", "The exam got postponed to next Wednesday",
    "I woke up at five today", "My cousin's flight lands at six in the evening",
    "Dad is coming back from Hyderabad on Sunday", "My brother starts his new job tomorrow",
    "I had a meeting with my professor this afternoon", "We are planning a trip to Manali in January",
    "My roommate forgot his keys again today", "I slept only four hours last night",
    "My parents are visiting me this weekend", "I got my results this morning",
    "The interview is scheduled for next Tuesday", "My friend is throwing a party on Saturday night",
    "I missed my alarm today and reached class late", "My landlord wants the rent by the fifth",
    "Mummy made biryani for lunch today", "My team won the match last evening",
    "I am meeting Arjun for coffee at four", "My aunt arrives from Chennai tomorrow evening",
    "The semester ends in two weeks", "I was on a call with my mentor for an hour",
    "My sister's baby is due in March", "I'm taking the night bus to Bangalore on Friday",
    "We had a power cut for three hours today", "My internship starts on the first of June",
    "I made a list of colleges with my dad yesterday", "My alarm clock broke this morning",
    "Mummy is coming to stay with us next week", "It's my parents' anniversary tomorrow",
    "My uncle reminded me of my grandfather today",
]
NOT_A_COMMAND = ("chat", "memory")
# Public request examples vote only on requests / questions; a plain statement keeps his own examples (intent.py).
STATEMENTS = ["Rahul got placed at Amazon today", "Mummy is coming home tomorrow", "Dad's train reaches at nine tonight",
              "My mom called me this morning", "I woke up at five today", "Priya wants a new phone",
              "The exam got postponed to next Wednesday", "Okay, it has been done", "So, my cousin is visiting next week"]
REQUESTS = ["Play songs by Arijit", "Show reminders for today", "Cancel alarms for tomorrow", "Add eggs to my list",
            "Set reminders for the trip", "Check emails from Amazon", "List todos", "Remind me at 4 to call mom",
            "What's on my calendar today?", "Who is Rahul?", "I want an alarm for 6 am", "I need to add flour to my list",
            "Please set a timer", "Tell me a joke", "Delete tasks from yesterday", "Read emails from mom", "Stop",
            "Set an alarm for 6 am", "Can you call mom"]
FRAMED = {"Also add call the placement cell": "todo", "add email the professor to my list": "todo",
          "mark play football as done": "todo", "remind me to email Sam at 5": "time",
          "set an alarm to call the bank at 9 am": "time", "add a meeting with John to my calendar on friday": None,
          "play some music": None, "call mom": None}
# Floors. Measured 2026-11-18: built-in examples only 386/529 (73.0%), 24% under 0.7, life updates 38/42;
# with the public examples 511/529 (96.6%), 4% under 0.7, life updates 42/42.
FLOOR = {"builtin": {"acc": 0.70, "life": 36}, "public": {"acc": 0.92, "low": 0.10, "life": 40}}


def _norm(t: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", t.lower())).strip()


def leaked(rows: list[dict]) -> int:
    """Yardstick lines that also sit in the public example file (must be 0: build_exemplars.py drops them)."""
    import numpy as np

    from stiti.config import CFG
    p = CFG.home / "data" / intent.PUBLIC_FILE
    if not p.exists():
        return 0
    with np.load(p, allow_pickle=False) as z:
        have = {_norm(str(t)) for t in z["texts"]}
    return sum(_norm(r["text"]) in have for r in rows) + sum(_norm(t) in have for t in LIFE_UPDATES)


def main() -> int:
    rows = [json.loads(l) for l in FIXTURE.read_text(encoding="utf-8").splitlines() if l.strip()]
    n_public = intent.public_count() if hasattr(intent, "public_count") else 0
    by_gold, by_src, wrong = defaultdict(list), defaultdict(list), []
    low = total = 0
    rev_hit = rev_n = false_corr = 0
    for r in rows:
        d = decide(r["text"], embed.embed_query(r["text"]))
        noticed = d.is_("is_correction", 0.6) or bool(UNDO_RX.match(r["text"]))
        if r.get("revision"):
            rev_n += 1
            rev_hit += noticed
            continue
        got, conf = d.get("domain"), d.conf.get("domain", 0.0)
        ok = got == r["gold"] or got in r.get("also", ())
        total += 1
        low += conf < LOW
        false_corr += d.is_("is_correction", 0.6)
        by_gold[r["gold"]].append(ok)
        by_src[r["src"].split(":")[0]].append(ok)
        if not ok:
            wrong.append((r["gold"], got, conf, r["text"]))
    life_bad = []
    for t in LIFE_UPDATES:
        d = decide(t, embed.embed_query(t))
        if d.get("domain") not in NOT_A_COMMAND:
            life_bad.append((d.get("domain"), d.conf.get("domain", 0.0), t))
    right = sum(sum(v) for v in by_gold.values())
    acc, low_share = right / total, low / total
    print(f"public yardstick — {'built-in examples only' if not n_public else f'{n_public} public examples loaded'}")
    print("  by domain: " + " · ".join(f"{g} {sum(v)}/{len(v)} ({100 * sum(v) / len(v):.0f}%)"
                                      for g, v in sorted(by_gold.items(), key=lambda kv: -len(kv[1]))))
    print("  by source: " + " · ".join(f"{s} {sum(v)}/{len(v)} ({100 * sum(v) / len(v):.0f}%)" for s, v in sorted(by_src.items())))
    print("  mistakes:  " + ", ".join(f"{g}→{p} {n}" for (g, p), n in Counter((g, p) for g, p, _, _ in wrong).most_common(10)))
    print(f"  under {LOW} confidence: {low}/{total} ({100 * low_share:.0f}%)")
    print(f"  “no, I meant …” follow-ups noticed as a correction: {rev_hit}/{rev_n} · plain requests wrongly taken "
          f"as a correction: {false_corr}/{total}")
    print(f"  life updates kept out of the command paths: {len(LIFE_UPDATES) - len(life_bad)}/{len(LIFE_UPDATES)}")
    for g, c, t in life_bad:
        print(f"    ✗ {g} ({c:.2f}) {t}")
    if "--misses" in sys.argv:
        for g, p, c, t in sorted(wrong):
            print(f"    {g:8}→ {p:8} {c:.2f}  {t}")
    f = FLOOR["public" if n_public else "builtin"]
    fails = []
    shape = [t for t in STATEMENTS if not intent.is_statement(t)] + [t for t in REQUESTS if intent.is_statement(t)]
    frames = [t for t, want in FRAMED.items() if intent.frame(t) != want]
    print(f"  statement / request told apart: {len(STATEMENTS) + len(REQUESTS) - len(shape)}/{len(STATEMENTS) + len(REQUESTS)}"
          f" · to-do / reminder frames: {len(FRAMED) - len(frames)}/{len(FRAMED)}")
    if shape or frames:
        fails.append(f"statement/request or frame rule: {shape + frames}")
    if n_public:
        wrong_frame = [(t, decide(t, embed.embed_query(t)).get("domain")) for t, want in FRAMED.items()
                       if want and decide(t, embed.embed_query(t)).get("domain") != want]
        if wrong_frame:
            fails.append(f"a framed to-do / reminder left its domain: {wrong_frame}")
    if n_public and (n := leaked(rows)):
        fails.append(f"{n} yardstick lines are also router examples")
    if acc < f["acc"]:
        fails.append(f"accuracy {acc:.3f} < {f['acc']}")
    if low_share > f.get("low", 1.0):
        fails.append(f"low-confidence share {low_share:.3f} > {f['low']}")
    if len(LIFE_UPDATES) - len(life_bad) < f["life"]:
        fails.append(f"life updates {len(LIFE_UPDATES) - len(life_bad)} < {f['life']}")
    if any(g in ("time", "todo") for g, _, _ in life_bad) and n_public:
        fails.append("a life update became a reminder / to-do")
    for x in fails:
        print(f"  ✗ {x}")
    print(f"public intent: {right}/{total} right ({100 * acc:.1f}%) · {100 * low_share:.0f}% under {LOW} · life updates "
          f"{len(LIFE_UPDATES) - len(life_bad)}/{len(LIFE_UPDATES)} · {'public examples on' if n_public else 'built-in only'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
