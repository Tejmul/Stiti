"""Example replies in the briefing (D50): EXAMPLES.md is a readable, editable file; the compiler shows the LLM the two
pairs of this turn's strategy nearest to his sentence, as style only; they are the first thing dropped when the
briefing is over budget, and they never appear on fetch / recap / fast-path / Hinglish turns.

STITI_DB=postgresql:///stiti_test STITI_HOME=<tmp> python tests/examples_eval.py     (no LLM: the router is faked)
"""
from __future__ import annotations

import os
import sys
from datetime import datetime

db = os.environ.get("STITI_DB", "")
if not db.rstrip("/").split("/")[-1].startswith("stiti_test"):
    sys.exit(f"refusing to run against {db!r}: use a stiti_test* database")
os.environ.setdefault("STITI_LIVE_WARM", "0")
os.environ.setdefault("STITI_EVENTKIT", "off")
os.environ.pop("STITI_EXAMPLES", None)
os.environ["STITI_LANGS"] = "mirror"          # D51: the Hinglish check below needs the opt-in mirror mode

passed = total = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global passed, total
    total += 1
    passed += bool(cond)
    print(f"  {'✓' if cond else '✗'} {name}" + (f" — {detail}" if detail and not cond else ""))


from stiti import embed, router                                          # noqa: E402
from stiti.brain import compiler, examples, psych, strategy              # noqa: E402
from stiti.config import CFG                                             # noqa: E402
from stiti.engine import Engine                                          # noqa: E402

p = examples.path()
if p.exists():
    p.unlink()                                  # a fresh home: the default is written on first use
examples._index.cache_clear()

print("the file")
idx = examples.index()
check("EXAMPLES.md is written to the home on first use", p.exists() and p.read_text() == examples.DEFAULT_EXAMPLES)
check("six sections: LISTEN, ACKNOWLEDGE, BANTER, SOLVE, ANSWER, REPAIR", set(idx) == set(examples.STRATEGIES), str(set(idx)))
check("6–10 pairs in each", all(6 <= len(v[0]) <= 10 for v in idx.values()), str({k: len(v[0]) for k, v in idx.items()}))
flat = [(s, y, h) for s, (pairs, _) in idx.items() for y, h in pairs]
changed = [(s, h, psych.enforce(h, strategy.make(s), user_text=y)) for s, y, h in flat
           if psych.enforce(h, strategy.make(s), user_text=y) != h]
check("every example reply passes her own rules for its strategy, untouched (word cap, no question, no advice in "
      "LISTEN, no banned phrase, no promise)", not changed, str(changed[:2]))
check("no banned phrase, no machine-talk, no emoji, no exclamation spam", not any(
    psych.BANNED_RX.search(h) or psych.MACHINE_RX.search(h) or psych.EMOJI.search(h) or h.count("!") > 1 for _, _, h in flat))
check("short: her side is ≤ 22 words everywhere", max(len(h.split()) for _, _, h in flat) <= 22,
      str(max((len(h.split()), h) for _, _, h in flat)))
check("REPAIR lines all open with “Sorry —”", all(h.startswith("Sorry —") for s, _, h in flat if s == "REPAIR"))
check("LISTEN never advises or asks", not any(psych.ADVICE.search(h) or "?" in h for s, _, h in flat if s == "LISTEN"))
check("no pair is said twice", len({h for _, _, h in flat}) == len(flat) and len({y for _, y, _ in flat}) == len(flat))
check("the vectors are kept on disk (no re-embedding at the next start)", (CFG.home / "data" / "examples_vecs.npz").exists())

print("picking")
qv = embed.embed_query("I messed up my exam today")
got = examples.pick("LISTEN", qv, "I messed up my exam today")
check("two pairs, from this strategy, the test one among them", len(got) == 2 and all(g in idx["LISTEN"][0] for g in got)
      and any("test" in y for y, _ in got), str(got))
blk = examples.block(got)
check("the block is labelled 'style only — never reuse these words'", blk.startswith(examples.LABEL)
      and "Style only" in examples.LABEL and "never reuse these words" in examples.LABEL)
check("about 70 tokens (≤ 110)", compiler.tokens(blk) <= 110, str(compiler.tokens(blk)))
for q, st in (("should I take the job or keep studying", "SOLVE"), ("what is an operating system", "ANSWER"),
              ("we won the quiz today haha", "BANTER"), ("what? that made no sense", "REPAIR"),
              ("I bought a new keyboard", "ACKNOWLEDGE")):
    pk = examples.pick(st, embed.embed_query(q), q)
    check(f"{st}: 1–2 pairs, ≤ 110 tokens", 1 <= len(pk) <= 2 and compiler.tokens(examples.block(pk)) <= 110, str(pk))
same = examples.pick("ANSWER", embed.embed_query("What's the capital of Australia?"), "What's the capital of Australia?")
check("a pair that IS his sentence is not shown (it would answer for the LLM)", all("Australia" not in y for y, _ in same), str(same))
check("no section → nothing (DO, QUIET, NUDGE, CRISIS)", all(examples.pick(s, qv, "x") == [] for s in ("DO", "QUIET", "NUDGE", "CRISIS")))
os.environ["STITI_EXAMPLES"] = "off"
check("STITI_EXAMPLES=off → nothing", examples.pick("LISTEN", qv, "x") == [])
os.environ.pop("STITI_EXAMPLES")

print("the briefing")
NOW = datetime(2026, 11, 18, 10, 0, tzinfo=CFG.tz)


def build(ex, mems=()):
    return compiler.build(text="I messed up my exam today", now=NOW, privacy=1, emotion_hint="calm", tone="calm",
                          recent=[{"speaker": "user", "text": "hello"}, {"speaker": "stiti", "text": "Hey."}],
                          memories=list(mems), facts=[], lessons=[], open_loops=None, talk_directives=[], mvd=False,
                          strategy=strategy.make("LISTEN"), examples=ex)


b0, t0 = build(None)
b1, t1 = build(got)
check("without examples the briefing is exactly as before", examples.LABEL not in b0)
check("with examples: the block sits right before [THIS TURN]", examples.LABEL in b1
      and b1.index(examples.LABEL) < b1.index("[THIS TURN]") and b1.index(examples.LABEL) > b1.index("[RECENT CONVERSATION]"))
check("…and costs ≤ 110 tokens", 0 < t1 - t0 <= 110, f"{t1 - t0}")
big = [{"episode_id": i, "occurred_at": NOW, "text": "x" * 220} for i in range(40)]
b2, t2 = build(got, big)
check("over budget → the examples go first, memory lines are still there", examples.LABEL not in b2 and "[E0 ·" in b2
      and t2 <= CFG.briefing_token_budget + 80, f"{t2}")

print("the engine (LLM faked)")
seen = []


def fake(msgs, **kw):
    seen.append(msgs[0]["content"])
    return {"text": REPLY["text"], "provider": "fake", "model": "fake", "ms": 1}


REPLY = {"text": "That's a hard morning."}
orig = router.complete
router.complete = fake
try:
    e = Engine("text")
    r = e.turn("I messed up my exam today and I feel terrible")
    check("a chat turn: the LLM sees two LISTEN pairs", e.last_strategy.name == "LISTEN" and seen
          and examples.LABEL in seen[-1] and seen[-1].count("\nHe: ") == 2, e.last_strategy.name)
    check("…and the reply is the LLM's own", r == "That's a hard morning.", r)
    shown = e.last_strategy.shown
    REPLY["text"] = shown[0] + " Still, the week is not over."
    r = e.turn("I failed the quiz I prepared so hard for")
    check("a reply that says a shown example back word for word loses that sentence",
          e.last_strategy.shown[0] not in r or shown[0] not in r, r)
    REPLY["text"] = "Okay."
    n = len(seen)
    e.turn("yaar aaj bahut thak gaya hoon, kuch accha nahi lag raha")
    check("a Hinglish reply gets no English examples", len(seen) > n and examples.LABEL not in seen[-1])
    n = len(seen)
    e.turn("add buy milk to my list")
    check("a fast path never calls the LLM (no examples needed)", len(seen) == n)
    e.turn("My brother is visiting next week and we will go trekking")
    n = len(seen)
    e.turn("what did I tell you till now?")
    check("a recap turn: his words, no style examples", len(seen) > n and examples.LABEL not in seen[-1]
          and "WHAT HE TOLD YOU" in seen[-1])
    n = len(seen)
    e.turn("search the web for the best keyboard under 3000")
    check("a tool / web turn: no style examples", all(examples.LABEL not in s for s in seen[n:]))
    os.environ["STITI_EXAMPLES"] = "off"
    n = len(seen)
    e.turn("I cleaned my desk this morning")
    check("STITI_EXAMPLES=off: briefing without the block", len(seen) > n and examples.LABEL not in seen[-1])
    os.environ.pop("STITI_EXAMPLES")

    print("he edits the file")
    p.write_text(p.read_text() + "\n## ACKNOWLEDGE\n- You: I repaired my cycle today.\n  Stiti: Two wheels back in service.\n")
    n = len(seen)
    e.turn("My bicycle is fixed, did it myself this afternoon")
    check("a pair he added is used on the next turn (no restart)", len(seen) > n and "Two wheels back in service." in seen[-1],
          seen[-1][-900:-600] if len(seen) > n else "")
    p.write_text("# EXAMPLES\n(nothing here)\n")
    n = len(seen)
    e.turn("I watered the plants today")
    check("an emptied file → no block, the turn still works", len(seen) > n and examples.LABEL not in seen[-1])
finally:
    router.complete = orig
    p.write_text(examples.DEFAULT_EXAMPLES)
    examples._index.cache_clear()

print(f"examples: {passed}/{total} checks passed")
sys.exit(0 if passed == total else 1)
