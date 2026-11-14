"""One lesson at a time (2026-11-11: "can you teach me… lexical analysis… using whiteboard?" said in three breaths
started THREE lessons — three voices talking over each other and hearing each other as the learner).

The lesson process is faked with `sleep` (no board, no mic). Throwaway test DB + temp STITI_HOME only.

STITI_DB=postgresql:///stiti_test STITI_HOME=<tmp> uv run python tests/tutor_launch_eval.py
"""
from __future__ import annotations

import os
import subprocess
import sys

db = os.environ.get("STITI_DB", "")
if not db.rstrip("/").split("/")[-1].startswith("stiti_test"):
    sys.exit(f"refusing to run against {db!r}: use a stiti_test* database")
os.environ.setdefault("STITI_LIVE_WARM", "0")

passed = total = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global passed, total
    total += 1
    passed += bool(cond)
    print(f"  {'✓' if cond else '✗'} {name}" + (f" — {detail}" if detail and not cond else ""))


from stiti import tutor                                                # noqa: E402
_REAL_LAUNCH = tutor.launch

spawned: list[list[str]] = []
procs: list[subprocess.Popen] = []
_real_popen = subprocess.Popen


def fake_popen(cmd, **kw):
    spawned.append(list(cmd))
    p = _real_popen(["sleep", "30"])                    # stands in for the lesson process (a live pid)
    procs.append(p)
    return p


subprocess.Popen = fake_popen
tutor.LOCK.unlink(missing_ok=True)

print("one lesson, however many times it's asked")
r1 = tutor.launch("compilers")                     # a compiler topic opens with or without an LLM key (CI has none)
r2 = tutor.launch("compilers, lexical analysis")
r3 = tutor.launch("compilers using whiteboard")
check("three quick requests → ONE lesson process", len(spawned) == 1, f"{len(spawned)} spawned")
check("the lock is taken at launch (lesson still loading)", tutor.tutor_active())
check("2nd and 3rd say it's already open", r2 == r3 == "Your lesson's already open on the whiteboard.", f"{r2!r}")
check("first one opens the board", r1.startswith("Opening the whiteboard"), r1)

print("the lesson process itself")
check("our own pid in the lock is not 'another lesson'", (tutor.LOCK.write_text(str(os.getpid())), tutor._other_lesson())[1] is False)
tutor.LOCK.write_text(str(procs[0].pid))
check("a live different pid is another lesson", tutor._other_lesson() is True)
for p in procs:
    p.kill()
    p.wait()
check("a dead pid is not a lesson", tutor._other_lesson() is False and not tutor.tutor_active())
tutor.LOCK.unlink(missing_ok=True)

print("no topic → ask, don't start a random lesson")
spawned.clear()
check("'can you teach me?' → asks for the topic", tutor.launch(None) == tutor.ASK_TOPIC and not spawned)
check("'continue my lesson' still resumes", tutor.launch(None, True).startswith("Opening your lesson") and len(spawned) == 1)
for p in procs:
    p.kill()
tutor.LOCK.unlink(missing_ok=True)

print("through the engine")
from stiti.engine import Engine                                        # noqa: E402

calls: list[tuple] = []
tutor.launch = lambda *a: calls.append(a) or ("Opening the whiteboard. Give me a few seconds."
                                              if a and a[0] else tutor.ASK_TOPIC)
e = Engine("text")
r = e.turn("Can you teach me?")
check("engine: asks what to teach", r.startswith("Sure! What should I teach you?"), r)
r = e.turn("Lexical analysis in compiler design")
check("engine: his next short line is the topic", calls[-1][0] == "Lexical analysis in compiler design", str(calls))
check("engine: then it's back to normal", e.teach_ask_at == 0.0)
e.turn("Can you teach me?")
r = e.turn("never mind")
check("engine: 'never mind' cancels", r.startswith("Okay, another time"), r)

e.turn("Can you teach me?")
calls.clear()
r = e.turn("Also add call the placement cell")
check("engine: a to-do while she waits for a topic is a to-do, not a lesson", not calls and e.teach_ask_at == 0.0
      or not calls, f"{r} | {calls}")

print("to-dos are never lessons (audit 2026-11-11)")
from stiti.tutor import voice_request as vr                            # noqa: E402
for t in ("Add revise DBMS notes to my to-do list", "remind me to revise DBMS at 9", "I need to revise graphs today"):
    check(f"not a lesson: {t!r}", vr(t) is None, str(vr(t)))
for t in ("Let's revise", "revision time", "revise karna hai", "Stiti, start my revision"):
    check(f"revision session: {t!r}", vr(t) == (None, False, "revise"), str(vr(t)))

print("she talks like a person in lessons too")
here = os.path.dirname(__file__)
player = open(os.path.join(here, "..", "src", "stiti", "tutor", "player.py")).read()
check("no 'cloud brain' in what the tutor says", "cloud brain" not in player.split('"""', 2)[-1].replace("No cloud brain?", ""))
audio = open(os.path.join(here, "..", "src", "stiti", "tutor", "audio.py")).read()
check("lesson ears use the single whisper thread (MLX streams are per thread)",
      "self.vl._stt.submit(stt.transcribe_ex, seg)" in audio and "stt.transcribe(np.zeros" not in audio.replace(
          "self.vl._stt.submit(stt.transcribe, np.zeros", ""))

print("lesson ears ignore noise")
from stiti.tutor.audio import keep_heard                               # noqa: E402
check("unclear noise is ignored ('Nim nil to nara')", not keep_heard("Nim nil to nara.", True))
check("unclear but a command still counts ('ruko')", keep_heard("ruko", True) and keep_heard("phir se", True))
check("a clear question always counts", keep_heard("What is a token in lexical analysis?", False))

print("his real whiteboard asks (2026-11-11 23:45: none of these opened it)")
REAL = {
    "So, I want you to explain me lexical analysis using a whiteboard.": "lexical analysis",
    "Okay then, open the whiteboard and explain me lexical analysis.": "lexical analysis",
    "Can you teach me lexical analysis using whiteboard?": "lexical analysis",
    "Can you explain me deadlocks on the board?": "deadlocks",
    "use the whiteboard to explain how DNS works": "how DNS works",
    "whiteboard pe recursion samjhao": "recursion",
    "No, you have the access to open whiteboard.": None,
    "Can you hear my command? I ask you open whiteboard. That's it.": None,
    "Bro, leave that open whiteboard and explain. I ask you to leave whiteboard and explain. I mean open whiteboard "
    "and explain.": None,
    "explain it on the whiteboard": None,
}
for t, want in REAL.items():
    check(f"opens the board: {t[:60]!r} → {want!r}", vr(t) == (want, False), str(vr(t)))
for t in ("close the whiteboard", "don't open the whiteboard, just explain it", "explain lexical analysis",
          "what is a whiteboard", "I bought a whiteboard today", "remind me to clean the whiteboard",
          "add buy whiteboard markers to my to-do list", "set an alarm for 6"):
    check(f"not a board request: {t!r}", vr(t) is None, str(vr(t)))

print("'open the whiteboard' after 'explain X' teaches X")
from stiti.tutor import topic_hint                                     # noqa: E402
check("hint from 'explain me lexical analysis'", topic_hint("So, I want you to explain me lexical analysis.")
      == "lexical analysis")
check("hint from 'what is a lexer?'", topic_hint("what is a lexer?") == "lexer")
for t in ("Can you tell me about the reminders I have today?", "what are my reminders", "explain my code", "How are you?"):
    check(f"no lesson hint from {t!r}", topic_hint(t) is None, str(topic_hint(t)))
for p in procs:
    p.kill()
tutor.LOCK.unlink(missing_ok=True)
calls.clear()                                          # tutor.launch is the recording fake from "through the engine"
from stiti import router as _router                                    # noqa: E402
_orig = _router.complete
_router.complete = lambda msgs, **kw: {"text": "Lexical analysis splits code into tokens.", "provider": "fake",
                                       "model": "fake", "ms": 1}
e2 = Engine("text")
e2.turn("explain me lexical analysis")
r = e2.turn("No, you have the access to open whiteboard.")
_router.complete = _orig
check("engine: bare 'open whiteboard' after 'explain me lexical analysis' launches THAT lesson",
      calls == [("lexical analysis", False)] and r.startswith("Opening the whiteboard"), f"{r} | {calls}")
for p in procs:
    p.kill()
tutor.LOCK.unlink(missing_ok=True)

print("the lock under races (D40: a kernel flock, not check-then-write)")
import threading as _th                                                # noqa: E402
import time as _time                                                   # noqa: E402
subprocess.Popen = _real_popen
tutor.LOCK.unlink(missing_ok=True)
HOLDER = ("import sys,time; from stiti import tutor; t0=float(sys.argv[1]); time.sleep(max(0,t0-time.time())); "
          "ok=tutor.acquire_lesson(); print('GOT' if ok else 'NO', flush=True); time.sleep(float(sys.argv[2]))")
env = {**os.environ, "PYTHONPATH": os.path.join(os.path.dirname(__file__), "..", "src")}
go = _time.time() + 2.5                                     # both start the SAME instant (same second, same ms)
racers = [_real_popen([sys.executable, "-c", HOLDER, str(go), "20"], stdout=subprocess.PIPE, text=True, env=env)
          for _ in range(3)]
outs = [r.stdout.readline().strip() for r in racers]
check("three lesson processes starting in the same instant → exactly ONE gets the lock", outs.count("GOT") == 1,
      str(outs))
check("while it runs, tutor_active() is True", tutor.tutor_active())
tutor.LOCK.write_text("999999")                             # a voice launch overwrote the pid with a child that died
check("…even if the pid in the file is dead (the flock still says a lesson runs)", tutor.tutor_active())
spawned.clear()
subprocess.Popen = fake_popen
tutor.launch = _REAL_LAUNCH                                 # (the engine section above swapped in a recorder)
r = tutor.launch("compilers")
check("a voice launch while a terminal lesson runs → 'already open', nothing spawned", not spawned
      and r == "Your lesson's already open on the whiteboard.", f"{r} {spawned}")
subprocess.Popen = _real_popen
res = tutor.teach(["compiler", "--silent", "--no-board"])
check("a second `stiti teach` refuses before loading anything", res == {"finished": False})
holder = next(r for r, o in zip(racers, outs) if o == "GOT")
for r in racers:
    r.kill()
    r.wait()
_time.sleep(0.1)
tutor.LOCK.write_text("")
check("the holder dies (even kill -9) → the lock is free, no stale lock", not tutor.tutor_active())
check("and the next lesson can take it", tutor.acquire_lesson() and tutor.tutor_active())
tutor.release_lesson()
check("released at the end of a lesson", not tutor.tutor_active() and tutor.LOCK.exists())

spawned.clear()
subprocess.Popen = fake_popen
tutor.LOCK.unlink(missing_ok=True)
bar = _th.Barrier(6)
replies: list[str] = []


def _fire():
    bar.wait()
    replies.append(tutor.launch("compilers"))


ths = [_th.Thread(target=_fire) for _ in range(6)]
for t_ in ths:
    t_.start()
for t_ in ths:
    t_.join()
check("six voice requests in the same instant (threads) → ONE lesson spawned", len(spawned) == 1,
      f"{len(spawned)} spawned, {replies}")
for p_ in procs:
    p_.kill()
tutor.LOCK.unlink(missing_ok=True)
subprocess.Popen = _real_popen

print("the always-on voice stays silent during a lesson")
from types import SimpleNamespace                                      # noqa: E402
from stiti.voice import loop as vloop                                  # noqa: E402
heard: list = []
fake = SimpleNamespace(silenced=False, ring_control=None, awake=False, _speak=lambda parts, mood: heard.append(parts))
assert tutor.acquire_lesson()
vloop.VoiceLoop.say(fake, "You have a meeting in 10 minutes.")
vloop.VoiceLoop.say(fake, "Mm-hm?")
check("no nudge / reprompt / missed-alarm line while a lesson runs", heard == [], str(heard))
fake.ring_control = object()
vloop.VoiceLoop.say(fake, "Wake up! Your 7 am alarm.")
check("an alarm that is ringing still speaks", len(heard) == 1)
tutor.release_lesson()
fake.ring_control = None
vloop.VoiceLoop.say(fake, "Hi again.")
check("after the lesson she talks again", len(heard) == 2)

subprocess.Popen = _real_popen
print(f"tutor launch: {passed}/{total} checks passed")
sys.exit(0 if passed == total else 1)
