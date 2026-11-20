"""Tutor answer grading: local grader + the free-LLM second opinion (offline — a fake LLM, no cloud).

His complaint (2026-11-20): a right SPOKEN answer, paraphrased or slightly mis-heard by speech-to-text ("the FA" for
DFA, "tokens" for "a list of tokens"), was marked wrong. The local grader stays first; a wrong/partial verdict on an
answer of ≥ 3 words gets one tiny LLM judgement under a hard deadline, falling back to the local verdict.
STITI_DB=postgresql:///stiti_test STITI_HOME=<tmp with models> PYTHONPATH=src python tests/tutor_grade_eval.py
Live accuracy with the real free models: tests/tutor_grade_live.py (not run here).
"""
from __future__ import annotations

import json
import os
import queue
import sys
import threading
import time
from pathlib import Path

db = os.environ.get("STITI_DB", "")
if not db.rstrip("/").split("/")[-1].startswith("stiti_test"):
    sys.exit(f"refusing to run against {db!r}: use a stiti_test* database")
os.environ.setdefault("STITI_LIVE_WARM", "0")
os.environ.setdefault("STITI_EVENTKIT", "off")
os.environ.pop("STITI_TUTOR_LLM_GRADE", None)

from stiti import router                                                 # noqa: E402
from stiti.tutor import grade, lesson as LS                              # noqa: E402
from stiti.tutor import planner as PM                                    # noqa: E402
from stiti.tutor.audio import SilentAudio                                # noqa: E402
from stiti.tutor.lesson import Check                                     # noqa: E402
from stiti.tutor.player import Tutor                                     # noqa: E402

passed = total = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global passed, total
    total += 1
    passed += bool(cond)
    print(f"  {'✓' if cond else '✗'} {name}" + (f" — {detail}" if detail and not cond else ""))


class FakeLLM:
    """planner._call's signature. Replies with `reply` (or raises / sleeps) and records every call."""

    def __init__(self, reply=None, delay=0.0, exc=None):
        self.reply, self.delay, self.exc, self.calls = reply, delay, exc, []

    def __call__(self, system, user, schema, name, max_tokens, **kw):
        self.calls.append({"system": system, "user": user, "schema": schema, "name": name, **kw})
        time.sleep(self.delay)
        if self.exc:
            raise self.exc
        return self.reply


FIX = json.loads((Path(__file__).parent / "fixtures" / "tutor_grade_cases.json").read_text())


def chk(key: str) -> Check:
    k = FIX["checks"][key]
    return Check(kind=k["kind"], prompt=k["prompt"], expectations=list(k["expectations"]), options=k.get("options"))


# ------------------------------------------------------------------ 1. local only
print("local grader on the labelled spoken-answer set (no LLM)")
never = FakeLLM({"verdict": "correct", "missing": [], "reason": "x"})
right = n = 0
by_tag: dict[str, list[bool]] = {}
for c in FIX["cases"]:
    g = grade.grade(chk(c["check"]), c["answer"], call=never)          # llm defaults to False
    right += g["verdict"] == c["truth"]
    n += 1
    by_tag.setdefault(c["tag"], []).append(g["verdict"] == c["truth"])
check(f"the set is big and varied ({n} cases, {len(FIX['checks'])} questions)", n >= 40 and len(FIX["checks"]) >= 20)
check(f"local accuracy holds its baseline ({right}/{n} = {right / n:.0%} ≥ 70%)", right / n >= 0.70)
check("idk variants and MCQ picks are always right locally", all(by_tag["idk"]) and all(by_tag["mcq"]),
      str({t: sum(v) for t, v in by_tag.items()}))
check("with llm=False the LLM is never asked", never.calls == [])
for a, v in (("tokens", "correct"), ("it produces a parse tree", "wrong"), ("I don't know", "idk"),
             ("I think it's the lexer", "wrong")):
    key = "parse" if "lexer" in a else "lexer"
    check(f"local: {a!r} → {v}", grade.grade(chk(key), a)["verdict"] == v, grade.grade(chk(key), a)["verdict"])
check("'the one that builds the tree' describes an option, it doesn't pick option A",
      grade.pick_option(chk("parse"), "the one that checks the grammar and builds the tree") is None)
g = grade.grade(chk("lexer"), "tokens")
check("backward compatible: the old keys are all still there (+ source/local_verdict/missing_text/llm_ms)",
      {"verdict", "covered", "missing", "option"} <= set(g) and g["source"] == "local" and g["llm_ms"] is None
      and g["missing_text"] == [], str(g))

# ------------------------------------------------------------------ 2. the LLM upgrades a mis-heard / paraphrased answer
print("second opinion: a right answer the local grader missed")
n2, ans = chk("newton2"), "f equals m a"
local = grade.grade(n2, ans)["verdict"]
fake = FakeLLM({"verdict": "correct", "missing": [], "reason": "F = ma said as letters"})
g = grade.grade(n2, ans, llm=True, call=fake)
check(f"local said {local!r}; the LLM says correct and wins", local in ("wrong", "partial") and g["verdict"] == "correct"
      and g["source"] == "llm" and g["local_verdict"] == local, str(g))
check("exactly one small call: route tutor_answer, reasoning low, temperature 0, schema 'grade'",
      len(fake.calls) == 1 and fake.calls[0]["route"] == "tutor_answer" and fake.calls[0]["reasoning"] == "low"
      and fake.calls[0]["temperature"] == 0 and fake.calls[0]["name"] == "grade", str(fake.calls[:1]))
u = fake.calls[0]["user"]
check("the prompt says it came through speech recognition and lists the expectations + his words",
      "speech" in fake.calls[0]["system"].lower() and "1. force equals mass times acceleration" in u and ans in u, u[:200])
check("the schema is tiny and strict-mode safe (3 required fields, enum verdict)",
      fake.calls[0]["schema"]["required"] == ["verdict", "missing", "reason"]
      and fake.calls[0]["schema"]["properties"]["verdict"]["enum"] == ["correct", "partial", "wrong"])
check("…and fits the 5,000-char schema limit", len(json.dumps(fake.calls[0]["schema"])) < 5000)

ir = chk("ir")
fake = FakeLLM({"verdict": "partial", "missing": [2], "reason": "no optimisation point"})
g = grade.grade(ir, "so the front end can be reused for many machines", llm=True, call=fake)
check("partial: the LLM names WHICH expectation is missing (so the hint can target it)",
      g["verdict"] == "partial" and g["missing"] == [1] and g["covered"] == [0]
      and g["missing_text"] == ["optimizations are easier on the IR"], str(g))
g = grade.grade(ir, "because it makes the code run in the browser", llm=True,
                call=FakeLLM({"verdict": "wrong", "missing": [], "reason": "wrong idea"}))
check("wrong without a missing list → every expectation is missing", g["verdict"] == "wrong" and g["missing"] == [0, 1])
g = grade.grade(chk("parse"), "I'd say the passer", llm=True,
                call=FakeLLM({"verdict": "correct", "missing": [], "reason": "parser"}))
check("MCQ said in words the picker can't match ('the passer') → correct, option = the right one",
      g["verdict"] == "correct" and g["option"] == 1, str(g))
fake = FakeLLM({"verdict": "correct", "missing": [], "reason": ""})
grade.grade(chk("parse"), "I'd say the passer", llm=True, call=fake)
check("…the LLM is shown the options with the correct one marked", "B) Parser *" in fake.calls[0]["user"])
g = grade.grade(ir, "so the front end can be reused for many machines", llm=True,
                call=FakeLLM({"verdict": "partial", "missing": [], "reason": ""}))
check("'partial' without saying what's missing keeps the local missing list", g["verdict"] == "partial"
      and g["missing"] == grade.grade(ir, "so the front end can be reused for many machines")["missing"], str(g))

print("the LLM is NOT asked when the local verdict is final")
fake = FakeLLM({"verdict": "wrong", "missing": [], "reason": ""})
for c_, a in ((chk("lexer"), "tokens"),                              # local correct
              (chk("ir"), "I don't know"),                           # idk
              (chk("parse"), "B"), (chk("parse"), "I think it's the lexer"),   # MCQ pick (right / wrong)
              (Check(kind="predict", prompt="guess?", expectations=["x"]), "maybe it is fast"),
              (chk("potus"), "Abraham Lincoln"),                     # < 3 words
              (Check(kind="recall", prompt="q", expectations=[""]), "something about the parser")):  # nothing to judge
    grade.grade(c_, a, llm=True, call=fake)
check("local correct / idk / MCQ pick / predict / < 3 words / no expectations → no call", fake.calls == [],
      str([x["user"][-60:] for x in fake.calls]))

# ------------------------------------------------------------------ 3. down / slow / garbage → local verdict
print("fallback: a slow, down or confused LLM never changes or blocks the grade")
slow = FakeLLM({"verdict": "correct", "missing": [], "reason": ""}, delay=1.5)
t0 = time.perf_counter()
g = grade.grade(n2, ans, llm=True, call=slow, timeout_s=0.3)
dt = time.perf_counter() - t0
check(f"timeout: back in {dt * 1000:.0f} ms (deadline 300 ms) with the local verdict",
      dt < 0.6 and g["verdict"] == local and g["source"] == "local" and g["llm_error"] == "timeout", str(g))
old = grade.LLM_TIMEOUT_S
grade.LLM_TIMEOUT_S = 0.2
t0 = time.perf_counter()
grade.grade(n2, ans, llm=True, call=slow)
check("the default deadline is grade.LLM_TIMEOUT_S (read at call time)", time.perf_counter() - t0 < 0.5)
grade.LLM_TIMEOUT_S = old
check("the default deadline is ≈ 2 s", 1.0 <= grade.LLM_TIMEOUT_S <= 2.5)
g = grade.grade(n2, ans, llm=True, call=FakeLLM(exc=router.NoProvider("groq: 429; cerebras: timeout")))
check("all providers down → local verdict", g["verdict"] == local and "NoProvider" in g.get("llm_error", ""), str(g))
for bad in (None, {"verdict": "maybe"}, {"verdict": "correct"}, "correct", {"verdict": "partial", "missing": ["x", 9]}):
    g = grade.grade(n2, ans, llm=True, call=FakeLLM(bad))
    okv = g["verdict"] == local if not (isinstance(bad, dict) and bad.get("verdict") in ("correct", "partial")) \
        else g["verdict"] == bad["verdict"]
    check(f"odd reply {bad!r} handled", okv and set(g["missing"]) <= {0}, str(g))

# ------------------------------------------------------------------ 4. the switch
print("STITI_TUTOR_LLM_GRADE=off")
fake = FakeLLM({"verdict": "correct", "missing": [], "reason": ""})
os.environ["STITI_TUTOR_LLM_GRADE"] = "off"
g = grade.grade(n2, ans, llm=True, call=fake)
check("off → never asked, local verdict", fake.calls == [] and g["verdict"] == local and g["source"] == "local")
os.environ["STITI_TUTOR_LLM_GRADE"] = "on"
grade.grade(n2, ans, llm=True, call=fake)
check("on again → asked", len(fake.calls) == 1)
os.environ.pop("STITI_TUTOR_LLM_GRADE")

# ------------------------------------------------------------------ 5. wiring: the player's check + doubt check
print("player: a real Planner → the check's answer gets the second opinion; a fake planner / none → local only")
check("llm_for: only a real cloud Planner", grade.llm_for(PM.Planner(None)) and not grade.llm_for(None)
      and not grade.llm_for(object()))


class FakeSrv:
    def __init__(self):
        self.sent: list[dict] = []

    def send(self, m):
        self.sent.append(m)


def play(answer: str, planner, llm_reply=None, delay=0.0):
    les = LS.from_dict({"title": "Newton", "topic": "newton", "segments": [
        {"id": "t1", "type": "teach", "title": "Second law", "cues": [
            {"say": "Push a heavy cart and a light cart equally hard: the light one speeds up more.", "ops": []}],
         "check": {"kind": "recall", "prompt": "What is Newton's second law?",
                   "expectations": ["force equals mass times acceleration"],
                   "hints": ["It links force, mass and acceleration."],
                   "reveal": "F equals m times a.", "on_correct": "Yes! Force is mass times acceleration."}}]})
    ev, logs = queue.Queue(), []
    fake = FakeLLM(llm_reply, delay=delay)
    real = PM._call
    PM._call = fake                                     # second_opinion() uses planner._call when no call= is given

    def log(line):
        logs.append(line)
        if line.startswith("Stiti: What is Newton"):
            threading.Timer(0.1, lambda: ev.put({"type": "text", "text": answer})).start()
        elif line.startswith("Stiti: Not quite") or line.startswith("Stiti: Good start"):
            threading.Timer(0.1, lambda: ev.put({"type": "text", "text": "skip"})).start()
    t = Tutor(les, audio=SilentAudio(scale=0.01), events=ev, server=FakeSrv(), planner=planner, persist=False, log=log,
              pace=0.02, idle_resume_s=0.2, check_timeout_s=3)
    out = {}
    th = threading.Thread(target=lambda: out.setdefault("res", t.run()), daemon=True)
    th.start()
    th.join(20)
    t.ended = True
    PM._call = real
    return out.get("res") or {}, logs, fake


res, logs, fake = play(ans, PM.Planner(None), {"verdict": "correct", "missing": [], "reason": "F = ma"})
check("with a real Planner, 'f equals m a' is praised, not hinted",
      any("Yes! Force is mass" in x for x in logs) and res.get("checks_right") == 1 and len(fake.calls) == 1,
      str([x for x in logs if x.startswith(("Stiti", "   [grade"))][-4:]))
check("…and the log shows the second opinion", any("[grade] second opinion:" in x for x in logs))
res, logs, fake = play(ans, PM.Planner(None), {"verdict": "correct", "missing": [], "reason": ""}, delay=5)
check("LLM slow → the hint ladder runs on the local verdict, the lesson isn't stuck",
      any("Hint:" in x for x in logs) and res.get("finished") is not None and len(fake.calls) == 1,
      str([x for x in logs if x.startswith(("Stiti", "   [grade"))][-4:]))
res, logs, fake = play(ans, None, {"verdict": "correct", "missing": [], "reason": ""})
check("no planner (offline lesson) → local only, no call", fake.calls == [] and any("Hint:" in x for x in logs))

print("player: the one-question check after a doubt gets the second opinion too")


class DoubtPlanner(PM.Planner):
    """A real Planner (so llm_for is True) whose doubt answer is canned — only the grading goes to the fake LLM."""

    def answer(self, question, ctx):
        return {"intent": "clarify", "strategy": "direct_explain", "stuck_at": "force vs mass",
                "say": ["Same push, less mass, so more acceleration.", "That is Newton's second law."], "ops": [],
                "check": {"prompt": "So what does the second law say?", "expected": "force equals mass times acceleration"}}


def doubt(reply: str, llm_reply) -> tuple[list[str], FakeLLM]:
    les = LS.from_dict({"title": "Newton", "topic": "newton", "segments": [
        {"id": "t1", "type": "teach", "title": "Second law", "cues": [
            {"say": "Push a heavy cart and a light cart equally hard: the light one speeds up more.", "ops": []},
            {"say": "That is the whole idea for today.", "ops": []}]}]})
    ev, logs = queue.Queue(), []
    fake, real = FakeLLM(llm_reply), PM._call
    PM._call = fake

    def log(line):
        logs.append(line)
        if line.startswith("Stiti: Push a heavy cart") and not any("why does" in x for x in logs):
            logs.append("(asked: why does the light cart speed up more?)")
            threading.Timer(0.1, lambda: ev.put({"type": "text", "text": "why does the light cart speed up more?"})).start()
        elif line.startswith("Stiti: So what does the second law say"):
            threading.Timer(0.1, lambda: ev.put({"type": "text", "text": reply})).start()
    t = Tutor(les, audio=SilentAudio(scale=0.01), events=ev, server=FakeSrv(), planner=DoubtPlanner(None),
              persist=False, log=log, pace=0.02, idle_resume_s=0.2, check_timeout_s=3)
    th = threading.Thread(target=t.run, daemon=True)
    th.start()
    deadline = time.time() + 20
    while time.time() < deadline and not any(x.startswith(("Stiti: Yes, exactly", "Stiti: Nearly", "Stiti: Not quite"))
                                             for x in logs):
        time.sleep(0.05)
    t.ended = True
    th.join(5)
    PM._call = real
    return logs, fake


logs, fake = doubt("f equals m a", {"verdict": "correct", "missing": [], "reason": "F = ma"})
check("doubt check: 'f equals m a' → 'Yes, exactly.' after the second opinion",
      any(x.startswith("Stiti: Yes, exactly") for x in logs) and len(fake.calls) == 1,
      str([x for x in logs if x.startswith(("Stiti", "   [grade"))][-4:]))
logs, fake = doubt("f equals m a", None)
check("doubt check: LLM gives nothing usable → the local verdict ('Nearly…')",
      any(x.startswith("Stiti: Nearly") for x in logs), str([x for x in logs if x.startswith("Stiti")][-3:]))

print("coach: the opening probes use the second opinion through the coach's own LLM call")
from stiti.tutor import coach as CO                                       # noqa: E402

GRADE_CALLS: list[str] = []
TOPIC = [{"unit": "Lexing", "name": n, "points": [f"{n} fact one", f"{n} fact two"], "weight": w}
         for n, w in (("Tokens", 3), ("Regular expressions", 2), ("DFA", 3), ("Longest match", 2))]


def coach_call(system, user, schema, name, max_tokens, **kw):
    if name == "concepts":
        return {"concepts": TOPIC}
    if name == "probes":
        return {"probes": [{"concept_id": "c0", "question": "What does a lexer produce?", "expected": ["tokens"]},
                           {"concept_id": "c2", "question": "What is a DFA made of?", "expected": ["states"]},
                           {"concept_id": "c3", "question": "Which match does a scanner take?",
                            "expected": ["longest"]}]}
    if name == "grade":
        GRADE_CALLS.append(user)
        return ({"verdict": "correct", "missing": [], "reason": "circles = states"} if "circles" in user
                else {"verdict": "wrong", "missing": [1], "reason": "no"})
    raise router.NoProvider("not needed in this test")


csrv, cev = FakeSrv(), queue.Queue()
ANS = ["I have my exam tomorrow", "tokens", "a few circles joined by arrows", "the shortest one I think"]


def cfeed(stop):
    seen = 0
    while not stop.is_set():
        waits = [m for m in list(csrv.sent) if m.get("type") == "status" and m.get("mode") == "waiting"]
        if len(waits) > seen and ANS:
            seen = len(waits)
            time.sleep(0.05)
            cev.put({"type": "text", "text": ANS.pop(0)})
        time.sleep(0.02)


co = CO.Coach("lexing basics for an exam (grading test)",   # own topic: its cache/mastery never touch other evals
              audio=SilentAudio(scale=0.01), events=cev, server=csrv, log=lambda *_: None,
              call=coach_call, persist=False, planner=None, pace=0.02, idle_resume_s=0.2, check_timeout_s=2)
stop = threading.Event()
threading.Thread(target=cfeed, args=(stop,), daemon=True).start()
threading.Thread(target=co.run, daemon=True).start()
deadline = time.time() + 30
while time.time() < deadline and not co.after_probes:
    time.sleep(0.05)
co.t.ended = True
stop.set()
check("'a few circles joined by arrows' (DFA = states) → the LLM says correct → DFA counted as known",
      co.after_probes.get("c2", 0) >= 0.8, str(co.after_probes))
check("…'the shortest one I think' stays wrong (LLM agrees), 'tokens' never asked (local correct)",
      co.after_probes.get("c3", 1) < 0.5 and len(GRADE_CALLS) == 2 and not any('"tokens"' in u for u in GRADE_CALLS),
      f"{co.after_probes} · {len(GRADE_CALLS)} calls")

print(f"\n{passed}/{total} passed")
sys.exit(0 if passed == total else 1)
