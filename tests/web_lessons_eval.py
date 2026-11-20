"""Web Lessons page backend: list his files / notes / progress, read a note (path-safe), start a lesson with strict
validation, and the goal chosen on the page reaching the coach (so she skips "is this for an exam?").

Offline: no LLM, no sound, no board, no real lesson — the spawn is stubbed. Temp STITI_HOME + temp study folders.

STITI_DB=postgresql:///stiti_test STITI_HOME=<tmp> python tests/web_lessons_eval.py
"""
from __future__ import annotations

import os
os.environ.setdefault("STITI_BOARD_FIXED", "0")     # tests: random ports, no waiting for a board tab
import json
import queue
import sys
import tempfile
import threading
import time
from pathlib import Path

db = os.environ.get("STITI_DB", "")
if not db.rstrip("/").split("/")[-1].startswith("stiti_test"):
    sys.exit(f"refusing to run against {db!r}: use a stiti_test* database")
os.environ.setdefault("STITI_LIVE_WARM", "0")
os.environ["STITI_TUTOR_PICTURES"] = "off"          # offline: no picture search
if not os.environ.get("STITI_HOME"):
    sys.exit("set STITI_HOME to a throwaway folder")

from starlette.testclient import TestClient  # noqa: E402

import stiti.tutor as T  # noqa: E402
from stiti import router  # noqa: E402
from stiti.config import CFG  # noqa: E402
from stiti.tutor import coach as C  # noqa: E402
from stiti.tutor.mastery import key_for  # noqa: E402
from stiti.web import lessons, server  # noqa: E402

passed = total = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global passed, total
    total += 1
    passed += bool(cond)
    print(f"  {'✓' if cond else '✗'} {name}" + (f" — {detail}" if detail and not cond else ""))


home = CFG.home
if home.resolve() == (Path.home() / ".stiti").resolve():
    sys.exit("refusing to write sample notes into the real ~/.stiti: use a throwaway STITI_HOME")

# ------------------------------------------------------------------ sample data (temp only)
books = Path(tempfile.mkdtemp(prefix="stiti-books-"))
dl, docs = books / "Downloads", books / "Documents"
for d in (dl, docs, dl / "sub"):
    d.mkdir(parents=True, exist_ok=True)
big = dl / "Compiler Notebook.pdf"
big.write_bytes(b"%PDF" + b"x" * 80_000)
older = docs / "Operating Systems.epub"
older.write_bytes(b"y" * 60_000)
os.utime(older, (time.time() - 86400 * 3, time.time() - 86400 * 3))
small = dl / "tiny.pdf"
small.write_bytes(b"z" * 1_000)                      # under 50 KB: not a study file
(dl / ".hidden.pdf").write_bytes(b"h" * 70_000)       # hidden: skipped
(dl / "movie.mp4").write_bytes(b"m" * 90_000)         # not a book extension
(dl / "sub" / "deep.pdf").write_bytes(b"d" * 90_000)  # not top level
T.BOOK_DIRS = (str(dl), str(docs), str(books / "missing"))

notes_dir = home / "tutor" / "notes"
notes_dir.mkdir(parents=True, exist_ok=True)
(notes_dir / "Compiler-Notebook.md").write_text(
    "# Compiler Notebook — notes\n_20 Nov 2026 · mode: day_\n\n## Tokens ✓\n- A lexer groups characters into tokens\n"
    "  - e.g. x = 42 → ID EQ NUM\n> **Remember:** characters in, tokens out\n")
(home / "secret.md").write_text("outside the notes folder")
try:
    (notes_dir / "link.md").symlink_to(home / "secret.md")
except OSError:
    pass

src = str(big)
(home / "tutor" / "mastery").mkdir(parents=True, exist_ok=True)
(home / "tutor" / "concepts").mkdir(parents=True, exist_ok=True)
(home / "tutor" / "mastery" / f"{key_for(src)}.json").write_text(json.dumps(
    {"source": src, "p": {"c0": 0.9, "c1": 0.5, "c2": 0.1}, "seen": {"c0": time.time() - 60, "c1": time.time()}}))
(home / "tutor" / "concepts" / f"{key_for(src)}.json").write_text(json.dumps(
    [{"id": f"c{i}", "name": n, "unit": "Lexing", "points": [], "weight": 2, "unit_idx": 0}
     for i, n in enumerate(["Tokens", "Regular expressions", "DFA", "Longest match"])]))
(home / "tutor" / "mastery" / f"{key_for('how DNS works')}.json").write_text(json.dumps(
    {"source": "how DNS works", "p": {"c0": 0.3}, "seen": {"c0": time.time() - 9000}}))
(home / "tutor" / "mastery" / "broken.json").write_text("{not json")

# ------------------------------------------------------------------ stubs: never really launch, never call an LLM
spawned: list[list[str]] = []
state = {"active": False}
T._spawn = lambda args: spawned.append(list(args))
T.tutor_active = lambda: state["active"]
keys = {"on": True}
router.status = lambda: [{"name": "fake", "key": keys["on"]}]

base = f"http://127.0.0.1:{server.PORT}"
host = {"host": f"127.0.0.1:{server.PORT}"}
tok = server.web_token()
auth = {"x-stiti-token": tok, **host}
write = {**auth, "origin": base}
c = TestClient(server.app(), base_url=base)

# ------------------------------------------------------------------ GET /api/lessons
print("the overview")
check("needs the token", c.get("/api/lessons", headers=host).status_code == 403)
check("Host check blocks DNS rebinding", c.get("/api/lessons", headers={**auth, "host": "evil.example"}).status_code == 403)
r = c.get("/api/lessons", headers=auth)
o = r.json() if r.status_code == 200 else {}
check("answers with active / board_url / files / notes / progress", r.status_code == 200
      and set(o) >= {"active", "board_url", "files", "notes", "progress"}, str(r.status_code))
names = [f["name"] for f in o.get("files", [])]
check("files: top-level book files over 50 KB only, newest first",
      names == ["Compiler Notebook.pdf", "Operating Systems.epub"], str(names))
f0 = (o.get("files") or [{}])[0]
check("each file has path, name, ext, size, modified", f0.get("path") == str(big) and f0.get("ext") == "pdf"
      and f0.get("size") == big.stat().st_size and "T" in (f0.get("modified") or ""), str(f0))
nt = o.get("notes", [])
check("notes listed with their title (from the '# … — notes' line)",
      any(n["name"] == "Compiler-Notebook.md" and n["title"] == "Compiler Notebook" for n in nt), str(nt))
pr = {p["source"]: p for p in reversed(o.get("progress", []))}       # same name twice: the newest wins
cn = pr.get("Compiler Notebook.pdf", {})
check("progress per file: known / shaky / new over every concept of its map",
      (cn.get("known"), cn.get("shaky"), cn.get("new"), cn.get("total"), cn.get("kind")) == (1, 1, 2, 4, "file"), str(cn))
check("…what's shaky is named, last lesson time given", cn.get("revise") == ["Regular expressions"]
      and cn.get("last_seen"), str(cn))
check("progress for a topic too; a broken file is skipped; one row per source (unique key)",
      pr.get("how DNS works", {}).get("kind") == "topic" and all(p.get("source") for p in o["progress"])
      and len(o["progress"]) == len(list((home / "tutor" / "mastery").glob("*.json"))) - 1
      and len({p["key"] for p in o["progress"]}) == len(o["progress"]), str([p["source"] for p in o["progress"]]))
check("newest lesson first", o["progress"][0]["key"] == key_for(src), str(o["progress"][:1]))
check("board link is the fixed local board with its token",
      o.get("board_url", "").startswith("http://127.0.0.1:7318/#t=") and len(o["board_url"]) > 40)
check("not active when no lesson runs", o.get("active") is False)

# ------------------------------------------------------------------ notes, path-safe
print("\nreading a note (only inside ~/.stiti/tutor/notes)")
r = c.get("/api/lessons/notes", params={"name": "Compiler-Notebook.md"}, headers=auth)
check("a listed note → its markdown", r.status_code == 200 and "## Tokens" in r.json().get("markdown", ""), r.text[:120])
check("needs the token", c.get("/api/lessons/notes", params={"name": "Compiler-Notebook.md"}, headers=host).status_code == 403)
bad = ["../secret.md", "..%2Fsecret.md", "../../web_token", "/etc/passwd", "sub/../../secret.md", "..", "",
       "Compiler-Notebook.md/../../secret.md", "link.md", "missing.md", "Compiler-Notebook.txt", "\x00.md"]
codes = {b: c.get("/api/lessons/notes", params={"name": b}, headers=auth).status_code for b in bad}
check("../, absolute paths, symlinks out, other extensions → refused (404)", all(v == 404 for v in codes.values()), str(codes))
check("note_text() itself refuses traversal", lessons.note_text("../secret.md") is None
      and lessons.note_text("..") is None and lessons.note_text(None) is None)  # type: ignore[arg-type]

# ------------------------------------------------------------------ POST /api/lessons/start
print("\nstarting a lesson (spawn stubbed)")


def start(body, headers=write):
    spawned.clear()
    return c.post("/api/lessons/start", content=json.dumps(body) if not isinstance(body, str) else body,
                  headers={**headers, "content-type": "application/json"})


r = start({"target": str(big), "mode": "day", "hours": 6}, headers=auth)
check("needs same-origin (Origin header) as well as the token", r.status_code == 403 and not spawned)
r = start({"target": str(big), "mode": "day", "hours": 6})
check("a listed file, whole syllabus today, 6 h → one spawn with the goal flags",
      r.status_code == 200 and r.json().get("ok") and spawned == [[str(big), "--goal-mode", "day", "--hours", "6"]],
      f"{r.status_code} {r.text[:120]} {spawned}")
day_args = spawned[0] if spawned else []
r = start({"target": "how DNS works", "mode": "learn"})
check("a plain topic, learn", r.status_code == 200 and spawned == [["how DNS works", "--goal-mode", "learn"]], str(spawned))
r = start({"target": str(older), "mode": "exam", "days": 3, "focus": "page tables and  TLB", "ptt": True})
exam_args = spawned[0] if spawned else []
check("exam in 3 days + focus + hold-to-talk",
      exam_args == [str(older), "--goal-mode", "exam", "--days", "3", "--focus", "page tables and TLB", "--ptt"], str(exam_args))
r = start({"target": "TCP/IP basics", "mode": "learn"})
check("a topic with a slash that isn't a path is fine", r.status_code == 200 and spawned[0][0] == "TCP/IP basics", r.text)

rejects = {
    "unlisted absolute path": {"target": "/etc/passwd"},
    "home path": {"target": "~/secret.pdf"},
    "small file in a listed folder": {"target": str(small)},
    "hidden file": {"target": str(dl / ".hidden.pdf")},
    "a file in a subfolder": {"target": str(dl / "sub" / "deep.pdf")},
    "a flag as target": {"target": "--resume"},
    "a book filename as topic": {"target": "secret.pdf"},
    "relative traversal": {"target": "../../etc/passwd"},
    "too long": {"target": "a" * 121},
    "empty": {"target": "   "},
    "not a string": {"target": ["x"]},
    "shell string": {"target": "dns; rm -rf ~"},
    "newline": {"target": "dns\n--resume"},
    "bad mode": {"target": "dns", "mode": "night"},
    "hours too many": {"target": "dns", "mode": "day", "hours": 13},
    "hours not a number": {"target": "dns", "mode": "day", "hours": "6; rm"},
    "days not an int": {"target": "dns", "mode": "exam", "days": "1"},
    "days negative": {"target": "dns", "mode": "exam", "days": -1},
    "focus as a flag": {"target": "dns", "focus": "--classic"},
    "focus too long": {"target": "dns", "focus": "b" * 121},
    "ptt not a bool": {"target": "dns", "ptt": "yes"},
}
res = {k: start(v) for k, v in rejects.items()}
check("every bad request → 400 with a message, nothing spawned",
      all(x.status_code == 400 and x.json().get("error") for x in res.values()) and not spawned,
      str({k: x.status_code for k, x in res.items() if x.status_code != 400}))
check("invalid JSON → 400", start("{nope").status_code == 400 and not spawned)

state["active"] = True
r = start({"target": "how DNS works"})
check("a lesson already running → 409, no second lesson", r.status_code == 409 and not spawned and r.json().get("active"))
check("overview says active", c.get("/api/lessons", headers=auth).json().get("active") is True)
state["active"] = False
keys["on"] = False
r = start({"target": "how DNS works"})
check("no cloud key → a clear 503, no spawn", r.status_code == 503 and not spawned and "key" in r.json()["error"])
r = start({"target": "compiler"})
check("…but the built-in demo still starts without a key", r.status_code == 200 and spawned == [["compiler", "--goal-mode", "learn"]])
keys["on"] = True

# ------------------------------------------------------------------ the goal reaches the coach
print("\nthe goal chosen on the page reaches the coach")
check("flags → the same goal dict as the spoken answer",
      C.goal_from_flags(day_args) == {"mode": "day", "days": 0, "hours": 6.0, "hours_said": True}
      and C.goal_from_flags(exam_args) == {"mode": "exam", "days": 3}
      and C.goal_from_flags(["x", "--goal-mode", "learn"]) == {"mode": "learn", "days": None}
      and C.goal_from_flags(["x"]) is None and C.goal_from_flags(["x", "--goal-mode", "night"]) is None)
check("…a day goal with no --hours: the plan won't claim 'your 6 hours' he never said",
      C.goal_from_flags(["x", "--goal-mode", "day"]) == {"mode": "day", "days": 0, "hours": C.DAY_DEFAULT_H,
                                                          "hours_said": False})
check("the lesson's topic is never mistaken for a flag value", "--goal-mode" in T.VALUE_FLAGS and "--days" in T.VALUE_FLAGS)

from stiti.tutor import audio as AU  # noqa: E402


class _A:
    def close(self):
        pass


got: list[dict] = []
real = (AU.make, C.concept_map, C.Coach.run)
AU.make = lambda mode, events, debug=False, scale=1.0: _A()
C.concept_map = lambda *a, **k: []
C.Coach.run = lambda self: (got.append({"goal": dict(self.goal or {}), "focus": self.focus, "ptt": self.t.ptt_mode,
                                        "source": self.source, "book": self.book_path}),
                            {"finished": True, "checks_right": 0, "checks_graded": 0, "questions": 0})[1]
try:
    T._teach(day_args + ["--silent", "--no-board"])        # the exact argv the page spawned
    T._teach(exam_args + ["--silent", "--no-board"])
finally:
    AU.make, C.concept_map, C.Coach.run = real
check("`stiti teach <file> --goal-mode day --hours 6` → Coach(goal=day, 6 h) on his file",
      len(got) >= 1 and got[0]["goal"] == {"mode": "day", "days": 0, "hours": 6.0, "hours_said": True} and got[0]["book"] == str(big), str(got[:1]))
check("exam args → Coach(goal=exam, 3 days), focus split, hold-to-talk on",
      len(got) == 2 and got[1]["goal"] == {"mode": "exam", "days": 3} and got[1]["focus"] == ["page tables", "TLB"]
      and got[1]["ptt"] is True, str(got[1:]))

# a real (silent, typed) session with the goal preset: she never asks the goal question
from stiti.tutor.audio import SilentAudio  # noqa: E402

TOPIC = [{"unit": "Lexing", "name": n, "points": [f"{n} fact one", f"{n} fact two"], "weight": 2}
         for n in ("Tokens", "Regular expressions", "DFA")]


def fake_call(system, user, schema, name, max_tokens, **kw):
    if name == "concepts":
        return {"concepts": TOPIC}
    if name == "probes":
        return {"probes": [{"concept_id": "c0", "question": "What does a lexer produce?", "expected": ["tokens"]}]}
    if name == "concept":
        return {"steps": [{"say": ["A lexer reads characters.", "It groups them into tokens."],
                           "board": [{"slot": "point", "kind": "text", "text": "Lexer groups chars", "nodes": None,
                                      "edges": None, "rows": None}],
                           "check": {"kind": "recall", "prompt": "What does the lexer output?", "options": None,
                                     "expectations": ["tokens"], "hints": ["Words."], "reveal": "Tokens."}}],
                "remember": "Characters in, tokens out"}
    raise AssertionError(name)


class FakeSrv:
    def __init__(self):
        self.sent = []

    def send(self, m):
        self.sent.append(m)


ev: queue.Queue = queue.Queue()
sv = FakeSrv()
logs: list[str] = []
stop = threading.Event()


def feed():
    seen = 0
    while not stop.is_set():
        waits = [m for m in list(sv.sent) if m.get("type") == "status" and m.get("mode") == "waiting"]
        if len(waits) > seen:
            seen = len(waits)
            time.sleep(0.05)
            ev.put({"type": "text", "text": "tokens"})
        time.sleep(0.02)


co = C.Coach("lexing from the web page", audio=SilentAudio(scale=0.01), events=ev, server=sv, log=logs.append,
             call=fake_call, persist=False, planner=None, pace=0.02, idle_resume_s=0.2, check_timeout_s=2,
             goal=C.goal_from_flags(["x", "--goal-mode", "day", "--hours", "2"]))
threading.Thread(target=feed, daemon=True).start()
out: dict = {}
th = threading.Thread(target=lambda: out.setdefault("r", co.run()), daemon=True)
th.start()
th.join(90)
stop.set()
said = [x[len("Stiti: "):] for x in logs if x.startswith("Stiti: ")]
check("goal preset → she never asks 'what do you need / is this for an exam?'",
      said and not any("what do you need" in s.lower() for s in said), str(said[:3]))
check("…and plans the whole syllabus in the hours given", co.goal.get("mode") == "day" and co.goal.get("hours") == 2.0
      and any("Here's the plan" in s and "hours" in s for s in said), str([s for s in said if "plan" in s][:1]))
check("the session ran to the end", out.get("r") is not None and not th.is_alive(), str(out)[:200])

import shutil  # noqa: E402

shutil.rmtree(books, ignore_errors=True)
print(f"\n{passed}/{total} web lessons checks passed")
sys.exit(0 if passed == total else 1)
