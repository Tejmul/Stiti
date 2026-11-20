"""Grade a learner's answer to a check — locally (keywords + the local embedder), no LLM.

AutoTutor-style "expectation coverage" (EMT): each check lists 1–3 expectations; we decide which are
covered, then the tutor picks a move (praise / "aur?" + hint / reveal). Decisions stay in Stiti's brain
(CLAUDE.md principle 1); an LLM is never needed to say "right" or "not quite".
"""
from __future__ import annotations

import re

from .commands import is_idk
from .lesson import Check

STOP = set("""a an the is are was were be been of to in on for and or but with by at from as it its this that these
those then than so do does did not no yes you your i me my we our they them he she his her what which who why how
when where there here into out up down about over just also very more most some any can could would should will
because like kind sort thing things one two three first second third hai hota hoti hain ka ki ke ko se me mein
aur ya toh to bhi nahi kya woh yeh ye""".split())
ORD = {0: r"\b(first|pehla|pehle wala|option a|option 1)\b", 1: r"\b(second|doosra|dusra|option b|option 2)\b",
       2: r"\b(third|teesra|tisra|option c|option 3)\b", 3: r"\b(fourth|chautha|option d|option 4)\b"}
ORD_NUM = {0: r"\b(1|one|ek)\b", 1: r"\b(2|two|do)\b", 2: r"\b(3|three|teen)\b", 3: r"\b(4|four|char|chaar)\b"}
NUM_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "ek": 1, "do": 2, "teen": 3, "char": 4,
             "chaar": 4, "paanch": 5, "panch": 5}


_UNITS = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve",
          "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen"]
_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90}
# "one" stays a word ("one intermediate code", "the second one"); every other number word becomes digits
_NUM_RX = re.compile(rf"\b(?:({'|'.join(_TENS)})(?:[\s-]({'|'.join(_UNITS[1:10])}))?|"
                     rf"({'|'.join(u for u in _UNITS if u != 'one')}))\b")


def _norm(s: str) -> str:
    """Spoken and written forms meet: 'thirty' → 30, 'twenty-five' → 25, 'x^2' → 'x squared', 'a – b' → 'a minus b'."""
    s = (s or "").lower().replace("²", " squared").replace("³", " cubed")
    s = re.sub(r"\^\s*2\b", " squared", s)
    s = re.sub(r"\^\s*3\b", " cubed", s)
    s = re.sub(r"\s\+\s", " plus ", s)
    s = re.sub(r"\s[-–−]\s", " minus ", s)
    s = _NUM_RX.sub(lambda m: str(_TENS[m.group(1)] + (_UNITS.index(m.group(2)) if m.group(2) else 0))
                    if m.group(1) else str(_UNITS.index(m.group(3))), s)
    return re.sub(r"\b(\d+) point (\d+)\b", r"\1.\2", s)                # "eight point four" → 8.4


_ALT = re.compile(r"\bor\b|(?<=[a-z ])/(?=[a-z ])")    # "A or B", "lexer/scanner" — but not a fraction "1/2"


def _numbers(s: str) -> set[str]:
    return set(re.findall(r"(?<![\w.])\d+(?:\.\d+)?(?!\w|\.\d)", _norm(s)))   # "…in 1914." counts too


def _words(s: str) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9]+", _norm(s)) if w not in STOP and len(w) > 1]


def _stem(w: str) -> str:
    """Light stemming: 'saves' / 'saving' → sav(e), 'management' / 'manages' → mana."""
    if w.endswith("s") and not w.endswith("ss") and len(w) > 3:
        w = w[:-1]
    for suf in ("ing", "ion", "ment", "ed", "er", "ly"):
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            w = w[:-len(suf)]
            break
    return w[:4] if len(w) >= 5 else w


def _has(kw: str, ans: set[str]) -> bool:
    """kw said? ('sav' ↔ 'save', 'wat' ↔ 'wate'): equal, or one a prefix of the other with ≥ 3 letters."""
    return kw in ans or (len(kw) >= 3 and any(len(a) >= 3 and (a.startswith(kw) or kw.startswith(a)) for a in ans))


def _keyword_score(expectation: str, answer: str, echo: set[str] | None = None) -> float:
    """Best share of an expectation's key words (any 'or' alternative) found in the answer. Words the question
    itself says (echo) don't count — repeating the question isn't knowing the answer."""
    ans = {_stem(w) for w in _words(answer)}
    best = 0.0
    # alternatives are "A or B" / "A/B"; a comma list ("Germany, Austria-Hungary, Italy") is ONE answer, not three
    for alt in _ALT.split(expectation.lower()):
        kws = {_stem(w) for w in _words(alt)}
        if echo and kws - echo:
            kws -= echo
        if kws:
            sc = sum(_has(k, ans) for k in kws) / len(kws)
            if len(kws) >= 4:                     # a long expectation gets paraphrased: half its words is enough
                sc = min(1.0, sc * 1.2)
            best = max(best, sc if len(kws) > 1 or sc == 1 else 0)
    return best


COVER = 0.6         # share of an expectation's key words that must be said: both of two, 2 of 3, 3 of 5


def _semantic(expectation: str, answer: str) -> float:
    try:
        from .. import embed
        v = embed._embed([expectation, answer])
        return float(v[0] @ v[1])
    except Exception:
        return 0.0


def pick_option(check: Check, answer: str) -> int | None:
    """Which MCQ option did they pick? Letter/number/ordinal, or the option's words (last mentioned wins)."""
    t = answer.lower().strip()
    m = re.match(r"^\(?([a-d])\)?(?:[.,:)]|\s*$)", t)        # "b", "B.", "c) parser"
    if m:
        return "abcd".index(m.group(1))
    hits = []
    tn = _norm(t)                                        # option words are normalised the same way ("ten" → 10)
    for i, o in enumerate(check.options or []):
        kws = [_stem(w) for w in _words(o["text"])]
        pos = [m.start() for w in kws for m in re.finditer(r"\b" + re.escape(w), tn)]
        if kws and pos:
            hits.append((max(pos), i))
    if hits:
        return max(hits)[1]
    for table in (ORD, ORD_NUM):                         # "the second one": ordinal beats the bare "one"
        for i, rx in table.items():
            if i < len(check.options or []) and re.search(rx, t):
                return i
    return None


def grade(check: Check, answer: str, *, semantic: bool = True) -> dict:
    """-> {verdict: correct|partial|wrong|idk|predict, covered:[i], missing:[i], option:int|None}"""
    if check.kind == "predict":
        return {"verdict": "predict", "covered": [], "missing": [], "option": None}
    if is_idk(answer) and len(answer.split()) <= 6:
        return {"verdict": "idk", "covered": [], "missing": list(range(len(check.expectations))), "option": None}
    if check.options:
        i = pick_option(check, answer)
        if i is not None:
            ok = check.options[i]["correct"]
            return {"verdict": "correct" if ok else "wrong", "covered": [], "missing": [], "option": i}
    exps = check.expectations or []
    echo = {_stem(w) for w in _words(check.prompt or "")}
    # an expectation made only of the question's own words tests nothing ("unknown doer" for "…when the doer is
    # unknown?"): grade on the others
    real = [i for i, e in enumerate(exps) if {_stem(w) for w in _words(e)} - echo or _numbers(e)]
    if real and len(real) < len(exps):
        exps = [exps[i] for i in real]
    got_nums = _numbers(answer)
    covered, touched = [], []
    for i, e in enumerate(exps):
        kw = _keyword_score(e, answer, echo)
        sem = _semantic(e, answer) if semantic and kw < COVER else 0.0
        need = _numbers(e)
        # a number in the expected answer must be said ("thirty" counts as 30): 'ten shirts' ≠ '30 shirts'
        nums_ok = not need or any(_numbers(alt) <= got_nums for alt in _ALT.split(e.lower())
                                  if _numbers(alt))
        only_num = bool(need) and not _words(re.sub(r"\d+(?:\.\d+)?", " ", _norm(e)))   # '8.4', '5', '30%'
        if only_num and nums_ok or (kw >= COVER or sem >= 0.72) and nums_ok:
            covered.append(i)
        elif kw >= 0.25 or sem >= 0.6:
            touched.append(i)                     # on the right track, not complete
    missing = [i for i in range(len(exps)) if i not in covered]
    if exps and not missing:
        v = "correct"
    elif covered or touched:
        v = "partial"
    else:
        v = "wrong"
    return {"verdict": v, "covered": covered, "missing": missing, "option": None}


def parse_confidence(text: str) -> int | None:
    t = text.lower()
    m = re.search(r"\b([1-5])\b", t)
    if m:
        return int(m.group(1))
    for w, n in NUM_WORDS.items():
        if re.search(rf"\b{w}\b", t):
            return n
    if re.search(r"(very|bahut|totally|pakka|100|full)", t):
        return 5
    if re.search(r"(not|nahi|guess|thoda|little)", t):
        return 2
    return None
