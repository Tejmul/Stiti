"""Grade a learner's answer to a check — locally (keywords + the local embedder), with an optional LLM second opinion.

AutoTutor-style "expectation coverage" (EMT): each check lists 1–3 expectations; we decide which are
covered, then the tutor picks a move (praise / "aur?" + hint / reveal). Decisions stay in Stiti's brain
(CLAUDE.md principle 1): the local grader always answers first, and "correct" / "I don't know" / an MCQ pick
never leave the Mac.

Second opinion (docs/research/tutor_grading.md): spoken answers come through speech-to-text, so a right answer
is often paraphrased or mis-heard ("the FA" for DFA, "see oh two" for CO2) and the local grader says "not quite".
When the local verdict is wrong/partial and the answer has ≥ 3 words, one tiny strict-JSON call to a free model
judges it against the expectations, under a hard ~2 s deadline (a daemon thread + future, so a slow provider
never stalls the lesson). Down / slow / garbage → the local verdict stands. STITI_TUTOR_LLM_GRADE=off disables it.
"""
from __future__ import annotations

import os
import re
import threading
import time
from concurrent.futures import Future

from .commands import is_idk
from .lesson import Check

LLM_TIMEOUT_S = 2.0
LLM_MIN_WORDS = 3

JUDGE_SYSTEM = """You grade a learner's SPOKEN answer to a tutor's question. The answer came through speech
recognition, so words may be mis-heard: sound-alikes, split or merged words, letters spelled out, numbers and
symbols said as words (e.g. "the FA" = "DFA", "see oh two" = "CO2", "f equals m a" = "F = ma"). Judge what the
learner most likely SAID and MEANT against the expectations. Be fair, not lenient: a wrong idea is wrong even if it
shares words with an expectation, and a vague answer does not cover an expectation it doesn't actually state."""

JUDGE_PROMPT = """QUESTION: {prompt}
{options}EXPECTATIONS (what a good answer covers):
{exps}
LEARNER'S ANSWER (speech-to-text): "{answer}"
Return JSON: verdict = "correct" (every expectation is stated, in any words) / "partial" (at least one expectation
is stated, but not all) / "wrong" (no expectation is stated, or the answer gives a different or incorrect idea);
missing = the numbers of the expectations the answer does NOT state ([] when correct); reason = at most 12 words."""

JUDGE_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["verdict", "missing", "reason"],
    "properties": {
        "verdict": {"type": "string", "enum": ["correct", "partial", "wrong"]},
        "missing": {"type": "array", "items": {"type": "integer"}},
        "reason": {"type": "string"},
    },
}

STOP = set("""a an the is are was were be been of to in on for and or but with by at from as it its this that these
those then than so do does did not no yes you your i me my we our they them he she his her what which who why how
when where there here into out up down about over just also very more most some any can could would should will
because like kind sort thing things one two three first second third hai hota hoti hain ka ki ke ko se me mein
aur ya toh to bhi nahi kya woh yeh ye""".split())
ORD = {0: r"\b(first|pehla|pehle wala|option a|option 1)\b", 1: r"\b(second|doosra|dusra|option b|option 2)\b",
       2: r"\b(third|teesra|tisra|option c|option 3)\b", 3: r"\b(fourth|chautha|option d|option 4)\b"}
# "the one that builds the tree" describes an option, it doesn't pick option 1 (2026-11-20 grading eval)
ORD_NUM = {0: r"\b(1|one(?!\s+(?:that|which|who|where|with|about|for)\b)|ek)\b", 1: r"\b(2|two|do)\b",
           2: r"\b(3|three|teen)\b", 3: r"\b(4|four|char|chaar)\b"}
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


def llm_enabled() -> bool:
    return os.environ.get("STITI_TUTOR_LLM_GRADE", "on").strip().lower() not in ("off", "0", "false", "no")


def llm_for(planner) -> bool:
    """Ask the LLM only when the lesson has a real cloud planner (answerer() makes one only when a free key exists)."""
    try:
        from .planner import Planner
        return isinstance(planner, Planner)
    except Exception:
        return False


def _judge_prompt(check: Check, answer: str, exps: list[str]) -> str:
    opts = ""
    if check.options:
        opts = "OPTIONS (* = the correct one):\n" + "\n".join(
            f"{'ABCD'[i]}) {o['text']}{' *' if o.get('correct') else ''}" for i, o in enumerate(check.options[:4])) + "\n"
    return JUDGE_PROMPT.format(prompt=check.prompt[:300], options=opts,
                               exps="\n".join(f"{i + 1}. {e[:200]}" for i, e in enumerate(exps)),
                               answer=answer[:400].replace('"', "'"))


def _deadline(call, system: str, user: str, schema: dict, name: str, max_tokens: int, timeout_s: float):
    """One strict-JSON free-LLM call on a daemon thread under a hard deadline -> (reply, ms, error | None)."""
    if call is None:
        from .planner import _call as call
    fut: Future = Future()

    def work():
        try:
            fut.set_result(call(system, user, schema, name, max_tokens, route="tutor_answer", reasoning="low",
                                temperature=0))
        except BaseException as e:            # noqa: BLE001 — any failure means "no second opinion"
            fut.set_exception(e)
    t = time.perf_counter()
    threading.Thread(target=work, daemon=True, name="grade-llm").start()
    try:
        d = fut.result(timeout=timeout_s)
    except Exception as e:
        return None, (time.perf_counter() - t) * 1000, ("timeout" if not fut.done()
                                                       else f"{type(e).__name__}: {str(e)[:80]}")
    return d, (time.perf_counter() - t) * 1000, None


def second_opinion(check: Check, answer: str, *, call=None, timeout_s: float | None = None) -> dict:
    """One free-LLM judgement under a hard deadline -> {verdict, missing:[i], reason, ms} or {error, ms}.
    `call` has planner._call's signature (tests pass a fake). The worker is a daemon thread: if the provider is
    slow we stop waiting, and its late answer is simply dropped."""
    exps = [e for e in check.expectations or [] if e and e.strip()]
    d, ms, err = _deadline(call, JUDGE_SYSTEM, _judge_prompt(check, answer, exps), JUDGE_SCHEMA, "grade", 300,
                           LLM_TIMEOUT_S if timeout_s is None else timeout_s)
    if err:
        return {"error": err, "ms": ms}
    if not isinstance(d, dict) or d.get("verdict") not in ("correct", "partial", "wrong"):
        return {"error": "bad reply", "ms": ms}
    idx = [i for i, e in enumerate(check.expectations or []) if e and e.strip()]   # prompt number n → index
    raw = d.get("missing") if isinstance(d.get("missing"), list) else []
    missing = sorted({idx[int(n) - 1] for n in raw if isinstance(n, (int, float)) and 1 <= int(n) <= len(idx)})
    v = d["verdict"]
    if v == "correct":
        missing = []
    elif v == "wrong" and not missing:
        missing = idx
    elif not missing:
        missing = None                          # "partial" without saying what's missing: keep the local guess
    return {"verdict": v, "missing": missing, "reason": str(d.get("reason") or "")[:120], "ms": ms}


def grade(check: Check, answer: str, *, semantic: bool = True, llm: bool = False, call=None,
          timeout_s: float | None = None) -> dict:
    """-> {verdict: correct|partial|wrong|idk|predict, covered:[i], missing:[i], option:int|None,
           source: local|llm, local_verdict, missing_text:[str], llm_ms: float|None, reason: str}
    With llm=True (and STITI_TUTOR_LLM_GRADE not off), a local wrong/partial on an answer of ≥ 3 words gets a
    free-LLM second opinion (see second_opinion); the LLM's verdict wins when it answers in time. Never asked for:
    local correct, idk, predict, an MCQ option he picked, or a check with no expectations."""
    g = _local(check, answer, semantic=semantic)
    g.update(source="local", local_verdict=g["verdict"], llm_ms=None, reason="")
    exps = check.expectations or []
    if (llm and g["verdict"] in ("wrong", "partial") and g["option"] is None   # an MCQ pick he said is final
            and len(answer.split()) >= LLM_MIN_WORDS
            and any(e and e.strip() for e in exps) and llm_enabled()):
        j = second_opinion(check, answer, call=call, timeout_s=timeout_s)
        g["llm_ms"] = j["ms"]
        if "error" in j:
            g["llm_error"] = j["error"]
        else:
            missing = g["missing"] if j["missing"] is None else j["missing"]
            covered = [i for i in range(len(exps)) if i not in missing]
            g.update(verdict=j["verdict"], covered=covered, missing=missing, source="llm", reason=j["reason"])
            if check.options and j["verdict"] == "correct":
                g["option"] = next((i for i, o in enumerate(check.options) if o.get("correct")), None)
    g["missing_text"] = [exps[i] for i in g["missing"] if i < len(exps)]
    return g


def _local(check: Check, answer: str, *, semantic: bool = True) -> dict:
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
    # (indices stay those of check.expectations, so missing / missing_text point at the right expectation)
    real = [i for i, e in enumerate(exps) if {_stem(w) for w in _words(e)} - echo or _numbers(e)]
    idx = real if real else list(range(len(exps)))
    got_nums = _numbers(answer)
    covered, touched = [], []
    for i in idx:
        e = exps[i]
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
    missing = [i for i in idx if i not in covered]
    if idx and not missing:
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


# ------------------------------------------------------------------------------------------------ Blurt (free recall)
# Coconote's Blurt (docs/research/apps/coconote.md T4): "tell me everything you remember about X", graded per key
# point as recalled / partial / missed — here locally (keywords + the local embedder, the best piece of his answer per
# point), with one free-LLM second opinion only when a point is partial (a paraphrase the keywords half-caught).
BLURT_RECALLED_SEM = 0.72
BLURT_PARTIAL_KW, BLURT_PARTIAL_SEM = 0.3, 0.62
BLURT_TIMEOUT_S = 3.0
BLURT_PROMPT = """TOPIC: {topic}
KEY POINTS the learner should remember:
{points}
LEARNER'S FREE RECALL (speech-to-text, everything they remembered): "{answer}"
For EACH key point return status = "recalled" (the recall states it, in any words), "partial" (touches it but
misses its key part) or "missed" (not stated, or stated wrongly). Return JSON: points = items of n (the point's
number) and status; reason = at most 12 words."""
BLURT_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["points", "reason"], "properties": {
    "points": {"type": "array", "items": {"type": "object", "additionalProperties": False, "required": ["n", "status"],
                                          "properties": {"n": {"type": "integer"},
                                                         "status": {"type": "string",
                                                                    "enum": ["recalled", "partial", "missed"]}}}},
    "reason": {"type": "string"}}}
_CHUNK_RX = re.compile(r"(?<=[.!?;])\s+|,\s+|\s+(?:and then|and also|also|then|plus|and)\s+")


def _chunks(answer: str) -> list[str]:
    """His recall in idea-sized pieces, so one point's similarity isn't diluted by everything else he said."""
    parts = [p.strip() for p in _CHUNK_RX.split(answer or "") if p and len(p.split()) >= 2]
    return parts[:24] or ([answer.strip()] if (answer or "").strip() else [])


def blurt_grade(points: list[str], answer: str, *, topic: str = "", semantic: bool = True, llm: bool = False,
                call=None, timeout_s: float | None = None) -> dict:
    """-> {points: [{point, status: recalled|partial|missed, kw, sem}], recalled, partial, missed, score (0–1),
           source: local|llm, llm_ms, reason}. Words of the topic's own name don't count ("photosynthesis is…"
    alone recalls nothing), and a number in a point must be said."""
    pts = [str(p) for p in (points or []) if p and str(p).strip()]
    answer = answer or ""
    echo = {_stem(w) for w in _words(topic)}
    idk = is_idk(answer) and len(answer.split()) <= 6
    chunks = [] if idk else _chunks(answer)
    sims: list[list[float]] = [[0.0] for _ in pts]
    if semantic and chunks and pts:
        try:
            from .. import embed
            v = embed._embed(pts + chunks)
            pv, cv = v[:len(pts)], v[len(pts):]
            sims = [[float(pv[i] @ cv[j]) for j in range(len(chunks))] for i in range(len(pts))]
        except Exception:
            pass
    got_nums = _numbers(answer)
    rows = []
    for i, p in enumerate(pts):
        kw = 0.0 if idk else _keyword_score(p, answer, echo)
        sem = max(sims[i]) if sims[i] else 0.0
        need = _numbers(p)
        nums_ok = not need or bool(need & got_nums)
        if (kw >= COVER or sem >= BLURT_RECALLED_SEM) and nums_ok:
            st = "recalled"
        elif kw >= BLURT_PARTIAL_KW or sem >= BLURT_PARTIAL_SEM:
            st = "partial"
        else:
            st = "missed"
        rows.append({"point": p, "status": st, "kw": round(kw, 2), "sem": round(sem, 2)})
    out: dict = {"points": rows, "source": "local", "llm_ms": None, "reason": ""}
    if (llm and llm_enabled() and any(r["status"] == "partial" for r in rows)
            and len(answer.split()) >= LLM_MIN_WORDS):
        prompt = BLURT_PROMPT.format(topic=topic[:120] or "this topic",
                                     points="\n".join(f"{i + 1}. {p[:160]}" for i, p in enumerate(pts)),
                                     answer=answer[:1200].replace('"', "'"))
        d, ms, err = _deadline(call, JUDGE_SYSTEM, prompt, BLURT_SCHEMA, "blurt", 400,
                               BLURT_TIMEOUT_S if timeout_s is None else timeout_s)
        out["llm_ms"] = ms
        if err or not isinstance(d, dict):
            out["llm_error"] = err or "bad reply"
        else:
            for it in d.get("points") or []:
                try:
                    k = int(it.get("n")) - 1
                except (TypeError, ValueError):
                    continue
                if 0 <= k < len(rows) and it.get("status") in ("recalled", "partial", "missed"):
                    rows[k]["status"] = it["status"]
            out.update(source="llm", reason=str(d.get("reason") or "")[:120])
    n = len(rows) or 1
    for st in ("recalled", "partial", "missed"):
        out[st] = sum(r["status"] == st for r in rows)
    out["score"] = round((out["recalled"] + 0.5 * out["partial"]) / n, 2)
    return out
