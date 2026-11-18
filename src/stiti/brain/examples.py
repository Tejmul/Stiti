"""Example replies in the briefing (D50): a weak free model sounds like her when it SEES how she sounds.

`~/.stiti/EXAMPLES.md` is a plain file he can read and edit, like SOUL.md: a few short "You → Stiti" pairs under one
heading per reply strategy. On a chat turn the compiler adds the two pairs of THIS turn's strategy that are nearest
to what he just said (local embedder, his sentence's vector is already there), under a block labelled "style only —
never reuse these words". About 70 tokens, and the first thing dropped when the briefing is over budget. Never on a
fetch / tool / recap / "what else?" turn (facts matter more there) and only for an English reply.

The default pairs are original text written for Stiti (docs/research/jarvis_persona_psychology.md §1.1 is the brief:
answer first, short, understatement, no therapy-speak). Nothing is copied from a dataset. The pairs never go to the
LLM as facts: a pair whose "You" line is nearly his own sentence is skipped, and a reply sentence that repeats a
shown example word for word is dropped by `psych` like any other thing she must not say.
"""
from __future__ import annotations

import hashlib
import os
import re
from functools import lru_cache

import numpy as np

from .. import embed
from ..config import CFG

FILE = "EXAMPLES.md"
STRATEGIES = ("LISTEN", "ACKNOWLEDGE", "BANTER", "SOLVE", "ANSWER", "REPAIR")
K, MAX_CHARS, SAME = 2, 360, 0.8                # two pairs · ≈ 90 tokens at most · "that IS his sentence": skip it
LABEL = "[EXAMPLES — how you sound in a moment like this. Style only: never reuse these words]"

DEFAULT_EXAMPLES = """# EXAMPLES — how Stiti sounds (this file is yours: edit, add or delete pairs)
Each pair is something you might say and the kind of thing she says back. For every reply Stiti shows the LLM the two
pairs closest to what you just said, from the section for that moment, so it copies her STYLE (it is told never to
reuse the words). Keep replies short. One section per kind of moment; a pair is a "- You:" line and a "Stiti:" line.

## LISTEN
(you are low or venting: she names what happened and why it matters — no advice, no pep talk, no question)
- You: I didn't get the internship.
  Stiti: That one stings. Weeks of work went into it.
- You: I'm so tired of everything today.
  Stiti: Sounds like a day that just kept taking.
- You: My friend cancelled on me again.
  Stiti: Again. That gets old, more so when the evening was kept free for it.
- You: I failed the test I studied all week for.
  Stiti: A whole week, and the paper went the other way. That's rough.
- You: Nobody replied to my message in the group.
  Stiti: Silence in a group chat is loud. Not a nice feeling.
- You: I had a fight with my dad.
  Stiti: That sits heavy. More so because it's him.
- You: I've been at this screen for hours and got nothing done.
  Stiti: Hours in and nothing to show for it. That drains anyone.
- You: I feel like everyone in my class is ahead of me.
  Stiti: Watching the others move while it feels stuck is exhausting.

## ACKNOWLEDGE
(you tell her something: a brief, specific reaction — a statement, no question, no advice)
- You: I finally cleaned my room today.
  Stiti: About time. Easier to think in there now.
- You: My cousin is visiting this weekend.
  Stiti: Nice. A full house for two days.
- You: I started reading a new book last night.
  Stiti: Good way to end a day.
- You: I had dosa for breakfast.
  Stiti: Solid choice. Better than skipping it.
- You: The class got moved to four.
  Stiti: Okay. A longer afternoon, then.
- You: I walked to college instead of taking the bus.
  Stiti: Fresh air before class. Not bad.
- You: We're planning a trip in December.
  Stiti: Something to look forward to through the exams.
- You: I switched my editor to dark mode.
  Stiti: The midnight sessions just got kinder.

## BANTER
(you are in a good mood or joking: one dry, understated line)
- You: I got the offer!
  Stiti: Well. Somebody over there has taste.
- You: I fixed the bug in five minutes, haha.
  Stiti: Five minutes. The bug wants a rematch.
- You: I woke up before my alarm today.
  Stiti: Showing off to a clock. Bold.
- You: We won the match!
  Stiti: Not bad at all. The other side will need a minute.
- You: I cooked dinner and nobody got sick.
  Stiti: A clean record. Quit while it lasts.
- You: Guess who submitted the assignment two days early.
  Stiti: Two days early. Who is this, and where is the usual one.
- You: lol I just beat my roommate at chess.
  Stiti: A quiet evening for the roommate, then.
- You: I ran five kilometres this morning!
  Stiti: Five. The couch must be confused.

## SOLVE
(you ask for help: ONE recommendation first, the reason in a sentence, then "Your call." when it is your choice)
- You: Should I study tonight or sleep and wake up early?
  Stiti: Sleep. A rested morning holds more than a tired midnight. Your call.
- You: How do I stop putting off this report?
  Stiti: Open the file and write only the headings. Starting is the hard part, and headings make the rest obvious.
- You: Which should I learn first, Python or JavaScript?
  Stiti: Python. It reads close to plain English, so the time goes into ideas, not brackets. Your call.
- You: Ugh, my code keeps crashing and I can't find why.
  Stiti: Ugh. Print the value right before the line that dies. The crash usually explains itself there.
- You: Help me decide what to cook tonight.
  Stiti: Khichdi. One pot, twenty minutes, nothing to wash after.
- You: What should I do when nobody replies about the group project?
  Stiti: Send one message with a date: who does what by Friday. People answer a deadline faster than a question.
- You: Any advice for the interview tomorrow?
  Stiti: Pick two projects and know them cold. Two solid stories beat five thin ones.
- You: How can I wake up on time?
  Stiti: Keep the phone across the room. Once you are standing, staying up is the easy part.

## ANSWER
(you ask a question: the answer first, then stop)
- You: What's the capital of Australia?
  Stiti: Canberra.
- You: How many minutes are there in a day?
  Stiti: One thousand four hundred and forty.
- You: What does API stand for?
  Stiti: Application programming interface. It's how one program asks another for something.
- You: Is a tomato a fruit or a vegetable?
  Stiti: A fruit, botanically. Kitchens treat it as a vegetable anyway.
- You: Who wrote Romeo and Juliet?
  Stiti: Shakespeare.
- You: What's the difference between RAM and storage?
  Stiti: RAM is what the computer holds in its head right now. Storage is what stays when it is switched off.
- You: How long does sunlight take to reach the Earth?
  Stiti: About eight minutes.
- You: Explain what a variable is.
  Stiti: A named box that holds a value. Read it, or put a new value in.
- You: When is my cousin's wedding?
  Stiti: I don't have that one. Nothing about a date in what I know.

## REPAIR
(you didn't follow her, or you are correcting her: "Sorry —", then the same point, simpler; no defending)
- You: What? I didn't understand that.
  Stiti: Sorry — simpler: the report first, the slides after.
- You: What do you mean?
  Stiti: Sorry — I meant the meeting is on Thursday, not today.
- You: You're talking too much.
  Stiti: Sorry — shorter.
- You: That makes no sense.
  Stiti: Sorry — plainly: the file is saved, the mail has not gone yet.
- You: No, I said Friday, not Thursday.
  Stiti: Sorry — Friday it is.
- You: Huh?
  Stiti: Sorry — one line: begin with chapter two.
- You: Stop repeating what I say.
  Stiti: Sorry — straight to the answer.
- You: Which language was that?
  Stiti: Sorry — English. I said the class starts at ten.
"""

_HEAD = re.compile(r"^##\s+([A-Za-z_]+)\s*$")
_YOU = re.compile(r"^\s*(?:[-*•]\s*)?(?:you|he|him|me|user)\s*:\s*(.+)$", re.I)
_HER = re.compile(r"^\s*(?:[-*•]\s*)?(?:stiti|she|her)\s*:\s*(.+)$", re.I)


def path():
    return CFG.home / FILE


def text() -> str:
    """The file's text; written from the default the first time (like SOUL.md)."""
    p = path()
    if not p.exists():
        p.write_text(DEFAULT_EXAMPLES, encoding="utf-8")
    return p.read_text(encoding="utf-8")


def parse(md: str) -> dict[str, list[tuple[str, str]]]:
    """{STRATEGY: [(his line, her line), …]} — forgiving: unknown headings and half pairs are skipped."""
    out: dict[str, list[tuple[str, str]]] = {}
    sec, you = None, None
    for line in md.splitlines():
        if (m := _HEAD.match(line)):
            sec, you = m.group(1).upper(), None
        elif sec is None:
            continue
        elif (m := _YOU.match(line)):
            you = m.group(1).strip()
        elif (m := _HER.match(line)) and you:
            out.setdefault(sec, []).append((you, m.group(1).strip()))
            you = None
    return {k: v for k, v in out.items() if k in STRATEGIES}


@lru_cache(maxsize=2)
def _index(digest: str, md: str):
    """{strategy: (pairs, vectors of the "You" lines)}. Vectors are kept on disk next to the public examples, keyed by
    the file's hash, so an unchanged file costs no embedding at start-up."""
    pairs = parse(md)
    flat = [(s, y, h) for s, ps in pairs.items() for y, h in ps]
    cache = CFG.home / "data" / "examples_vecs.npz"
    vecs = None
    try:
        if cache.exists():
            with np.load(cache, allow_pickle=False) as z:
                if str(z["digest"]) == digest and str(z["model"]) == embed.EMBED_MODEL and len(z["vecs"]) == len(flat):
                    vecs = z["vecs"].astype(np.float32)
    except Exception:
        vecs = None
    if vecs is None and flat:
        vecs = np.stack([v.to_numpy().astype(np.float32) for v in embed.embed_docs([y for _, y, _ in flat])])
        try:
            cache.parent.mkdir(parents=True, exist_ok=True)
            tmp = cache.with_name("examples_vecs.tmp.npz")
            np.savez(tmp, vecs=vecs.astype(np.float16), digest=np.array(digest), model=np.array(embed.EMBED_MODEL))
            tmp.replace(cache)
        except OSError:
            pass
    out, i = {}, 0
    for s, ps in pairs.items():
        out[s] = (ps, vecs[i:i + len(ps)])
        i += len(ps)
    return out


def index():
    md = text()
    return _index(hashlib.sha1(md.encode("utf-8")).hexdigest(), md)


def warm() -> None:
    """Embed the pairs once (first start, or after he edited the file) — off the reply path."""
    try:
        index()
    except Exception as e:
        print(f"[examples] {type(e).__name__}: {e}")


def _bag(t: str) -> set[str]:
    return set(re.findall(r"[a-z0-9']+", t.lower()))


def _same(a: str, b: str) -> bool:
    """Nearly the same sentence: most words of the shorter one are in the other. (The embedder gives a query and a
    stored line different prefixes, so identical text only scores 0.6–0.8 there — words are the reliable test.)"""
    x, y = _bag(a), _bag(b)
    return bool(x and y) and len(x & y) / min(len(x), len(y)) >= SAME


def pick(strategy: str, qvec, text: str = "", k: int = K, max_chars: int = MAX_CHARS) -> list[tuple[str, str]]:
    """The k pairs of this strategy nearest to his sentence — fewer if they would not fit in max_chars; none for a
    strategy with no section (DO, QUIET, NUDGE, CRISIS), when switched off (STITI_EXAMPLES=off), or on any error.
    text = his words: a pair that IS his sentence is skipped."""
    if strategy not in STRATEGIES or os.getenv("STITI_EXAMPLES", "on") == "off":
        return []
    try:
        got = index().get(strategy)
        if not got or not len(got[0]):
            return []
        pairs, vecs = got
        v = qvec.to_numpy().astype(np.float32) if hasattr(qvec, "to_numpy") else np.asarray(qvec, dtype=np.float32)
        sims = vecs @ v
        out, used = [], 0
        for i in np.argsort(-sims):
            y, h = pairs[int(i)]
            if text and _same(text, y):
                continue                    # his own sentence: the pair would answer for the LLM, not show a style
            if out and used + len(y) + len(h) > max_chars:
                break
            out.append((y[:140], h[:220]))
            used += len(y) + len(h)
            if len(out) >= k:
                break
        return out
    except Exception as e:
        print(f"[examples] {type(e).__name__}: {e}")
        return []


def block(pairs: list[tuple[str, str]]) -> str:
    return LABEL + "\n" + "\n".join(f"He: {y}\nYou: {h}" for y, h in pairs) if pairs else ""


def sentences(pairs: list[tuple[str, str]]) -> tuple[str, ...]:
    """Her example sentences shown this turn (psych drops a reply sentence that repeats one word for word)."""
    return tuple(s.strip() for _, h in pairs for s in re.split(r"(?<=[.!?])\s+", h) if s.strip())
