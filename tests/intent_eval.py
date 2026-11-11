"""Domain classifier on held-out lines (none of these are exemplars): life updates must be chat, not tool / time /
memory / control (2026-11-11: "Repu maa ammamma vastundi" → control 0.93, "Mummy is coming home tomorrow" → time).

uv run python tests/intent_eval.py   (offline, embedder only)
"""
from __future__ import annotations

import sys

from stiti import embed
from stiti.decide import decide

CASES = [
    ("My cousin is visiting next weekend", "chat"), ("My friend's birthday is on Saturday", "chat"),
    ("We're going to Goa next month", "chat"), ("Mummy is coming home tomorrow", "chat"),
    ("I have my DBMS exam on Monday", "chat"), ("Kal mera interview hai, thoda nervous hoon", "chat"),
    ("Rahul got placed at Amazon today", "chat"), ("The placement interview went well", "chat"),
    ("ఈ రోజు చాలా అలసిపోయాను", "chat"), ("Nenu ivala chala tired ga unnanu", "chat"),
    ("Repu maa ammamma vastundi", "chat"), ("నాకు రేపు ఎగ్జామ్ ఉంది", "chat"), ("I'm so done with this code", "chat"),
    ("Naa to-do list lo emundi?", "todo"), ("నా పనుల జాబితాలో ఏముంది?", "todo"),
    ("Repu podduna 6 ki alarm pettu", "time"), ("రేపు ఉదయం ఆరు గంటలకు అలారం పెట్టు", "time"),
    ("What's on my calendar today?", "tool"), ("Check my email", "tool"), ("Play some music", "tool"),
    ("Add buy milk to my todos", "todo"), ("Remind me at 4 to call mom", "time"), ("Okay, it has been done", "todo"),
    ("What did I tell you about my sister?", "memory"), ("Who is Rahul?", "memory"), ("Don't call me sir", "feedback"),
    ("I had a long day at college today", "chat"), ("Tell me a joke", "chat"), ("Set an alarm for 6 am", "time"),
    ("What's the weather today?", "tool"), ("stop", "control"), ("repeat that", "control"),
    ("mark laundry as done", "todo"), ("when is papa's birthday", "memory"),
]
bad = []
for text, want in CASES:
    got = decide(text, embed.embed_query(text)).get("domain")
    print(f"  {'✓' if got == want else '✗'} {got:8} (want {want:8}) {text}")
    if got != want:
        bad.append(text)
print(f"intent: {len(CASES) - len(bad)}/{len(CASES)} checks passed")
sys.exit(0 if not bad else 1)
