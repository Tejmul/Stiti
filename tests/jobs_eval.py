"""Background jobs + live progress (D56): idempotent enqueue, SKIP LOCKED claims with two workers, progress + NOTIFY,
park on a free-tier limit and run after not_before, retry backoff, cancel, requeue + resume after a restart, the
concept-map job (checkpoint resume after a 429), and the web API: /api/jobs list / retry / cancel, Prepare, and the
/api/events server-sent-events stream (a real uvicorn on a spare port).

Offline: no LLM (the concept-map calls are stubbed), temp STITI_HOME, a stiti_test* database only.

STITI_DB=postgresql:///stiti_test STITI_HOME=<tmp> python tests/jobs_eval.py
"""
from __future__ import annotations

import os
import socket
import sys

db = os.environ.get("STITI_DB", "")
if not db.rstrip("/").split("/")[-1].startswith("stiti_test"):
    sys.exit(f"refusing to run against {db!r}: use a stiti_test* database")
if not os.environ.get("STITI_HOME"):
    sys.exit("set STITI_HOME to a throwaway folder")
with socket.socket() as _s:                                   # the SSE test runs a real server on a spare port
    _s.bind(("127.0.0.1", 0))
    os.environ["STITI_WEB_PORT"] = str(_s.getsockname()[1])
os.environ.setdefault("STITI_LIVE_WARM", "0")

import json  # noqa: E402
import tempfile  # noqa: E402
import threading  # noqa: E402
import time  # noqa: E402
from datetime import datetime, timedelta, timezone  # noqa: E402
from pathlib import Path  # noqa: E402

import psycopg  # noqa: E402

import stiti.tutor as T  # noqa: E402
from stiti import jobs, router  # noqa: E402
from stiti.config import CFG  # noqa: E402
from stiti.db import one, q  # noqa: E402

if CFG.home.resolve() == (Path.home() / ".stiti").resolve():
    sys.exit("refusing to write into the real ~/.stiti: use a throwaway STITI_HOME")

passed = total = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global passed, total
    total += 1
    passed += bool(cond)
    print(f"  {'✓' if cond else '✗'} {name}" + (f" — {detail}" if detail and not cond else ""))


def row(jid: int) -> dict:
    return one("SELECT * FROM stiti_job WHERE id=%s", (jid,)) or {}


def reset() -> None:
    q("DELETE FROM stiti_job")
    q("DELETE FROM llm_usage")


def now() -> datetime:
    return datetime.now(timezone.utc)


class Listener:
    """Collects NOTIFY stiti_jobs payloads on its own connection."""

    def __init__(self):
        self.c = psycopg.connect(CFG.db_url, autocommit=True)
        self.c.execute(f"LISTEN {jobs.CHANNEL}")

    def drain(self, wait: float = 0.5) -> list[dict]:
        return [json.loads(n.payload) for n in self.c.notifies(timeout=wait)]


# ------------------------------------------------------------------ handlers used by the tests
gate = threading.Event()
log: list = []


@jobs.handler("t_quick")
def _quick(job):
    job.progress("Step one", 40)
    log.append(("quick", job.id))
    return {"step": "All done", "n": 1}


@jobs.handler("t_wait")
def _wait(job):
    gate.wait(5)
    return {}


@jobs.handler("t_paced")
def _paced(job):
    job.progress("Warming up", 10)
    time.sleep(1.2)
    job.progress("Half way", 55)
    return {}


limit_left = {"n": 0}


@jobs.handler("t_limited")
def _limited(job):
    if limit_left["n"] > 0:
        limit_left["n"] -= 1
        raise router.NoProvider("groq/llama: 429; cerebras/qwen: gated")
    return {"step": "Made it"}


class RateLimit(Exception):
    status_code = 429


@jobs.handler("t_429")
def _r429(job):
    raise RateLimit("Too Many Requests")


@jobs.handler("t_flaky")
def _flaky(job):
    raise ValueError("bad json from the model")


@jobs.handler("t_fatal")
def _fatal(job):
    raise jobs.Fail("The file isn't there any more.")


class Crash(BaseException):
    """Stands in for the app being killed mid-job (not caught by the worker)."""


crash_at = {"i": None}


@jobs.handler("t_steps")
def _steps(job):
    start = int(job.checkpoint.get("i", 0))
    for i in range(start, 4):
        if crash_at["i"] == i:
            crash_at["i"] = None
            raise Crash()
        log.append(("step", i))
        job.save(i=i + 1)
        job.progress(f"Step {i + 1} of 4", (i + 1) * 25)
    return {"step": "4 steps"}


@jobs.handler("t_long")
def _long(job):
    for i in range(100):
        job.progress(f"tick {i}", i)
        time.sleep(0.05)
    return {}


T_KINDS = ["t_quick", "t_wait", "t_paced", "t_limited", "t_429", "t_flaky", "t_fatal", "t_steps", "t_long"]


def worker(*kinds, **kw) -> jobs.Worker:
    return jobs.Worker(list(kinds) or T_KINDS, **kw)


# ------------------------------------------------------------------ 1. enqueue is idempotent
print("enqueue")
reset()
a = jobs.enqueue("t_quick", {"path": "/x/a.pdf", "n": 1}, label="a.pdf")
b = jobs.enqueue("t_quick", {"n": 1, "path": "/x/a.pdf"}, label="a.pdf")
c = jobs.enqueue("t_quick", {"path": "/x/b.pdf"}, label="b.pdf")
d = jobs.enqueue("t_wait", {"path": "/x/a.pdf", "n": 1})
check("same kind + recipe (any key order) → the same job", a["id"] == b["id"] and a["new"] and not b["new"])
check("another recipe or another kind → a new job", len({a["id"], c["id"], d["id"]}) == 3)
check("a new job starts queued at 0 %", a["status"] == "queued" and a["percent"] == 0 and a["label"] == "a.pdf")
check("one live row per recipe in the table", one("SELECT count(*) AS n FROM stiti_job WHERE recipe_hash=%s",
                                                  (jobs.recipe_hash("t_quick", {"path": "/x/a.pdf", "n": 1}),))["n"] == 1)
hits = []
ths = [threading.Thread(target=lambda: hits.append(jobs.enqueue("t_quick", {"race": 1})["id"])) for _ in range(6)]
[t.start() for t in ths]
[t.join() for t in ths]
check("six enqueues at the same moment → one job", len(set(hits)) == 1 and len(hits) == 6, str(hits))
w = worker("t_quick")
while w.run_once():
    pass
check("after it finished, the same recipe can run again", jobs.enqueue("t_quick", {"race": 1})["new"])
w.stop()

# ------------------------------------------------------------------ 2. claims: SKIP LOCKED, two workers
print("claims")
reset()
j1 = jobs.enqueue("t_wait", {"k": 1})["id"]
j2 = jobs.enqueue("t_wait", {"k": 2})["id"]
wa, wb = worker(), worker()
got = {}
ths = [threading.Thread(target=lambda n=n, ww=ww: got.__setitem__(n, ww.claim())) for n, ww in (("a", wa), ("b", wb))]
[t.start() for t in ths]
[t.join() for t in ths]
ids = sorted(j.id for j in got.values() if j)
check("two workers at once take two different jobs", ids == sorted([j1, j2]), str(ids))
check("both rows say running, each by its own worker",
      {row(j1)["claimed_by"], row(j2)["claimed_by"]} == {wa.id, wb.id} and row(j1)["status"] == "running")
check("a third claim finds nothing", worker().claim() is None)
reset()
j1 = jobs.enqueue("t_wait", {"k": 1})["id"]
j2 = jobs.enqueue("t_wait", {"k": 2})["id"]
lock = psycopg.connect(CFG.db_url)                            # someone holds j1's row lock in an open transaction
lock.execute("SELECT id FROM stiti_job WHERE id=%s FOR UPDATE", (j1,))
t0 = time.perf_counter()
jb = worker().claim()
ms = (time.perf_counter() - t0) * 1000
lock.rollback()
lock.close()
check("a locked row is skipped, not waited on", jb is not None and jb.id == j2 and ms < 1000, f"{jb and jb.id} {ms:.0f} ms")
check("claim only takes kinds it has handlers for", worker("t_quick").claim() is None)
for ww in (wa, wb):
    ww.stop()

# ------------------------------------------------------------------ 3. progress + NOTIFY
print("progress + notify")
reset()
L = Listener()
jid = jobs.enqueue("t_quick", {"n": 3}, label="Notes.pdf")["id"]
w = worker()
check("run_once runs a ready job", w.run_once())
r = row(jid)
check("done: 100 %, the handler's step, result saved", r["status"] == "done" and r["percent"] == 100
      and r["step"] == "All done" and r["result"].get("n") == 1 and r["finished_at"] is not None, str(r.get("status")))
ev = [e for e in L.drain() if e["id"] == jid]
sts = [e["status"] for e in ev]
check("NOTIFY on every change: queued → running → progress → done", sts[:1] == ["queued"] and "running" in sts
      and sts[-1] == "done", str(sts))
mid = [e for e in ev if e.get("step") == "Step one"]
check("the progress event carries step + percent + label", bool(mid) and mid[0]["percent"] == 40
      and mid[0]["label"] == "Notes.pdf", str(mid))
check("events are small JSON (no recipe paths)", all("recipe" not in e for e in ev))
jid = jobs.enqueue("t_paced", {"n": 1})["id"]
w.run_once()
pe = [e for e in L.drain() if e["id"] == jid and e.get("step") == "Half way"]
check("ETA from the pace when the handler gives none", bool(pe) and pe[0]["eta_s"] is not None and 0 < pe[0]["eta_s"] < 5,
      str(pe))
q("UPDATE stiti_job SET heartbeat_at=now() WHERE id=%s", (jid,))
check("a heartbeat alone sends no event", not [e for e in L.drain(0.3) if e["id"] == jid])
w.stop()

# ------------------------------------------------------------------ 4. park on a free-tier limit
print("park on the free tier")
reset()
limit_left["n"] = 1
jid = jobs.enqueue("t_limited", {"n": 1}, label="Big.pdf")["id"]
w = worker()
w.run_once()
r = row(jid)
left = (r["not_before"] - now()).total_seconds() if r.get("not_before") else -1
check("router.NoProvider → parked, not failed", r["status"] == "parked" and r["attempts"] == 0 and r["parks"] == 1,
      str(r.get("status")))
check("parked with a not_before about a minute ahead", 40 < left < 70, f"{left:.0f}s")
check("the reason is shown, in plain words", "free AI" in (r["error"] or ""), r.get("error") or "")
check("not claimed before not_before", not w.run_once() and row(jid)["status"] == "parked")
q("UPDATE stiti_job SET not_before = now() - interval '1 second' WHERE id=%s", (jid,))
check("after not_before it runs and finishes", w.run_once() and row(jid)["status"] == "done"
      and row(jid)["step"] == "Made it")
limit_left["n"] = 2
q("""INSERT INTO llm_usage(provider, model, day, cooldown_until) VALUES ('groq','m',current_date, now() + interval '20 min')
     ON CONFLICT (provider, model, day) DO UPDATE SET cooldown_until = EXCLUDED.cooldown_until""")
jid = jobs.enqueue("t_limited", {"n": 2})["id"]
w.run_once()
left = (row(jid)["not_before"] - now()).total_seconds()
check("waits for the provider's 429 cooldown when that's later than the backoff", 19 * 60 < left < 21 * 60, f"{left:.0f}s")
q("DELETE FROM llm_usage")
q("UPDATE stiti_job SET not_before = now() - interval '1 second' WHERE id=%s", (jid,))
w.run_once()
left = (row(jid)["not_before"] - now()).total_seconds()
check("parked again → the backoff doubles (2 min)", row(jid)["parks"] == 2 and 100 < left < 130, f"{left:.0f}s")
jid = jobs.enqueue("t_429", {"n": 1})["id"]
w.run_once()
check("an HTTP 429 error from a handler → parked", row(jid)["status"] == "parked")
w.stop()

# ------------------------------------------------------------------ 5. errors: retry with backoff, then failed
print("errors")
reset()
jid = jobs.enqueue("t_flaky", {"n": 1})["id"]
w = worker()
w.run_once()
r = row(jid)
left = (r["not_before"] - now()).total_seconds() if r.get("not_before") else -1
check("an error → back in the queue with a backoff (30 s), attempts 1", r["status"] == "queued" and r["attempts"] == 1
      and 20 < left < 40 and "ValueError" in (r["error"] or ""), f"{r.get('status')} {left:.0f}")
for _ in range(2):
    q("UPDATE stiti_job SET not_before = now() - interval '1 second' WHERE id=%s", (jid,))
    w.run_once()
r = row(jid)
check("after max_attempts (3) → failed, the error kept", r["status"] == "failed" and r["attempts"] == 3
      and r["error"] and r["finished_at"] is not None, f"{r.get('status')} {r.get('attempts')}")
jid2 = jobs.enqueue("t_fatal", {"n": 1})["id"]
w.run_once()
check("Fail() → failed at once with its message", row(jid2)["status"] == "failed"
      and row(jid2)["error"] == "The file isn't there any more.")
jid3 = jobs.enqueue("t_unknown", {"n": 1})["id"]
check("a kind with no handler is never claimed", jobs.Worker().claim() is None and row(jid3)["status"] == "queued")
w.stop()

# ------------------------------------------------------------------ 6. retry / cancel
print("retry + cancel")
r = jobs.retry(jid)
check("retry a failed job → queued, attempts reset, error cleared", r["status"] == "queued" and r["attempts"] == 0
      and r["error"] is None)
try:
    jobs.retry(jid)
    ok = True
except jobs.NotPossible:
    ok = False
check("retry a queued job → stays queued (try now)", ok and row(jid)["status"] == "queued")
q("UPDATE stiti_job SET status='done' WHERE id=%s", (jid,))
try:
    jobs.retry(jid)
    msg = ""
except jobs.NotPossible as e:
    msg = str(e)
check("retry a done job → refused, in words", msg == "It already finished.", msg)
dup_old = jobs.enqueue("t_fatal", {"dup": 1})["id"]
q("UPDATE stiti_job SET status='failed' WHERE id=%s", (dup_old,))
jobs.enqueue("t_fatal", {"dup": 1})
try:
    jobs.retry(dup_old)
    msg = ""
except jobs.NotPossible as e:
    msg = str(e)
check("retry while the same recipe is already live → refused", "already in the queue" in msg, msg)
cq = jobs.enqueue("t_quick", {"cancel": 1})["id"]
jobs.cancel(cq)
check("cancel a queued job → cancelled, never claimed", row(cq)["status"] == "cancelled"
      and worker("t_quick").claim() is None)
try:
    jobs.cancel(cq)
    msg = ""
except jobs.NotPossible as e:
    msg = str(e)
check("cancel twice → refused", msg == "It already finished.", msg)
reset()
lj = jobs.enqueue("t_long", {"n": 1})["id"]
w = worker("t_long")
th = threading.Thread(target=w.run_once)
th.start()
time.sleep(0.4)
jobs.cancel(lj)
th.join(5)
r = row(lj)
check("cancel a running job → it stops at its next progress report", not th.is_alive() and r["status"] == "cancelled"
      and r["percent"] < 90, f"{r.get('status')} {r.get('percent')}")
check("a cancelled run never writes done over it", r["result"] is None)
w.stop()

# ------------------------------------------------------------------ 7. restart: requeue stale, resume from checkpoint
print("restart + resume")
reset()
host = socket.gethostname()
dead = jobs.enqueue("t_quick", {"dead": 1})["id"]
q("""UPDATE stiti_job SET status='running', claimed_by=%s, heartbeat_at=now(), step='Reading unit 2', percent=30,
     checkpoint='{"units": 1}' WHERE id=%s""", (f"{host}:999999:1", dead))
old = jobs.enqueue("t_quick", {"old": 1})["id"]
q("UPDATE stiti_job SET status='running', claimed_by='other-mac:1:1', heartbeat_at=now() - interval '5 min' WHERE id=%s",
  (old,))
alive = jobs.enqueue("t_quick", {"alive": 1})["id"]
q("UPDATE stiti_job SET status='running', claimed_by='other-mac:1:2', heartbeat_at=now() WHERE id=%s", (alive,))
back = jobs.requeue_stale()
check("a job claimed by a dead process on this Mac → back in the queue", dead in back and row(dead)["status"] == "queued")
check("a job whose heartbeat stopped → back in the queue", old in back and row(old)["status"] == "queued")
check("a job with a live heartbeat (another worker) is left alone", alive not in back and row(alive)["status"] == "running")
r = row(dead)
check("requeued keeps step, percent and checkpoint", r["step"] == "Reading unit 2" and r["percent"] == 30
      and r["checkpoint"] == {"units": 1} and r["claimed_by"] is None)
reset()
log.clear()
crash_at["i"] = 2
sj = jobs.enqueue("t_steps", {"n": 1}, label="Steps")["id"]
w1 = worker("t_steps")
try:
    w1.run_once()
except Crash:
    pass
r = row(sj)
check("killed mid-job: the row still says running at its last step", r["status"] == "running" and r["percent"] == 50
      and r["checkpoint"] == {"i": 2}, f"{r.get('status')} {r.get('percent')} {r.get('checkpoint')}")
w1._x("SELECT 1")
q("UPDATE stiti_job SET claimed_by=%s WHERE id=%s", (f"{host}:999998:1", sj))   # that process is gone now
w1.stop()
w2 = worker("t_steps", poll_s=0.1).start()                   # the app starts again → its worker reconciles
deadline = time.time() + 5
while time.time() < deadline and row(sj)["status"] != "done":
    time.sleep(0.05)
w2.stop()
check("after the restart it finishes", row(sj)["status"] == "done", row(sj).get("status", ""))
steps = [i for k, i in log if k == "step"]
check("…resuming from its last step (0 1 | 2 3), nothing redone", steps == [0, 1, 2, 3], str(steps))
check("the worker thread stops cleanly", not (w2.thread and w2.thread.is_alive()))

# ------------------------------------------------------------------ 8. the concept-map job (Prepare a file)
print("prepare a file (concept map)")
reset()
from stiti.tutor import planner as P  # noqa: E402
from stiti.tutor import prepare as PR  # noqa: E402

books = Path(tempfile.mkdtemp(prefix="stiti-jobs-books-"))
book = books / "Compiler Notes.md"
body = "\n\n".join(f"Chapter {n} {t}\n\n" + (f"{t} explained. " * 400) for n, t in
                   [(1, "Tokens"), (2, "Parsing"), (3, "Types"), (4, "Code generation")])
book.write_text("Compiler Notes\n\n" + body)
T.BOOK_DIRS = (str(books),)
calls_made: list[str] = []
fail_units = {"Parsing"}
real_call = P._call


def fake_call(system, user, schema, name, max_tokens, **kw):
    unit = next((ln[6:] for ln in user.splitlines() if ln.startswith("UNIT: ")), "?")
    calls_made.append(unit)
    if any(u in unit for u in fail_units):
        raise router.NoProvider("groq/llama: 429")
    return {"concepts": [{"name": f"{unit[:20]} idea {i}", "points": ["a fact"], "weight": 2} for i in range(2)]}


P._call = fake_call
check("a file isn't prepared before", not PR.prepared(str(book)))
pj = PR.enqueue(str(book))
check("Prepare queues one concept_map job labelled with the file name", pj["kind"] == "concept_map"
      and pj["label"] == "Compiler Notes.md" and pj["new"])
check("…with a source hash of the file", bool(row(pj["id"])["source_hash"]))
L = Listener()
w = jobs.Worker(["concept_map"])
w.run_once()
r = row(pj["id"])
n_first = len(calls_made)
check("a 429 on one unit → parked, the other units kept in the checkpoint", r["status"] == "parked"
      and len(r["checkpoint"].get("calls", {})) == n_first - 1 and n_first >= 3, f"{r.get('status')} {n_first}")
check("…and the half-built map is not cached (no filler for the missing unit)", not PR.cache_file(str(book)).exists()
      and not PR.prepared(str(book)))
check("the park reason says how far it got", "units" in (r["error"] or ""), r.get("error") or "")
steps = [e.get("step") or "" for e in L.drain() if e["id"] == pj["id"]]
check("live steps name the units as they finish", any(" of " in s and "units read" in s for s in steps), str(steps))
fail_units.clear()
calls_made.clear()
q("UPDATE stiti_job SET not_before = now() - interval '1 second' WHERE id=%s", (pj["id"],))
w.run_once()
r = row(pj["id"])
check("after the limit: done, only the missing unit was asked again", r["status"] == "done" and len(calls_made) == 1
      and "Parsing" in calls_made[0], f"{r.get('status')} {calls_made}")
check("the result counts topics and units", r["result"].get("concepts", 0) >= 6 and r["result"].get("units", 0) >= 3,
      str(r.get("result")))
check("now the file is prepared (cache newer than the file)", PR.prepared(str(book)))
from stiti.tutor import coach as C  # noqa: E402
cm = C.concept_map(str(book), book_path=str(book), call=lambda *a, **k: (_ for _ in ()).throw(AssertionError("LLM")))
check("a lesson on it now reads the map with no LLM call", len(cm) >= 6)
calls_made.clear()
pj2 = PR.enqueue(str(book))
w.run_once()
check("preparing again → 'Already prepared', no LLM call", row(pj2["id"])["status"] == "done" and not calls_made
      and row(pj2["id"])["result"].get("cached") is True)
future = time.time() + 5
os.utime(book, (future, future))
check("the file changed after the map → not prepared any more (stale)", not PR.prepared(str(book)))
gone = jobs.enqueue("concept_map", {"path": str(books / "missing.pdf")}, label="missing.pdf")
w.run_once()
check("a file that's gone → failed with a plain reason", row(gone["id"])["status"] == "failed"
      and "isn't there" in (row(gone["id"])["error"] or ""))
w.stop()
P._call = real_call

# ------------------------------------------------------------------ 9. web API: /api/jobs, retry / cancel, Prepare
print("web API")
reset()
from starlette.testclient import TestClient  # noqa: E402

from stiti.web import server  # noqa: E402

base = f"http://127.0.0.1:{server.PORT}"
hosth = {"host": f"127.0.0.1:{server.PORT}"}
tok = server.web_token()
auth = {"x-stiti-token": tok, **hosth}
write = {**auth, "origin": base}
T.tutor_active = lambda: False
cl = TestClient(server.app(), base_url=base)
fj = jobs.enqueue("t_fatal", {"api": 1}, label="api.pdf")["id"]
jobs.Worker(["t_fatal"]).run_once()
check("/api/jobs needs the token", cl.get("/api/jobs", headers=hosth).status_code == 403)
check("/api/jobs checks the Host header", cl.get("/api/jobs", headers={**auth, "host": "evil.example"}).status_code == 403)
rr = cl.get("/api/jobs", headers=auth)
jl = rr.json().get("jobs", []) if rr.status_code == 200 else []
check("/api/jobs lists recent jobs with status / step / % / ETA / error", rr.status_code == 200 and jl
      and jl[0]["id"] == fj and set(jl[0]) >= {"status", "step", "percent", "eta_s", "error", "not_before", "label"},
      str(rr.status_code))
check("…and never sends the recipe (file paths) to the page", all("recipe" not in j for j in jl))
check("retry needs the Origin (cross-site writes blocked)",
      cl.post(f"/api/jobs/{fj}/retry", headers=auth).status_code == 403)
rr = cl.post(f"/api/jobs/{fj}/retry", headers=write)
check("POST /api/jobs/{id}/retry → queued", rr.status_code == 200 and rr.json()["job"]["status"] == "queued")
rr = cl.post(f"/api/jobs/{fj}/cancel", headers=write)
check("POST /api/jobs/{id}/cancel → cancelled", rr.status_code == 200 and rr.json()["job"]["status"] == "cancelled")
rr = cl.post(f"/api/jobs/{fj}/cancel", headers=write)
check("cancel again → 409 with a message", rr.status_code == 409 and rr.json().get("error") == "It already finished.")
check("retry an unknown job → 409", cl.post("/api/jobs/999999/retry", headers=write).status_code == 409)
book2 = books / "Operating Systems.md"
book2.write_text("Operating Systems\n\n" + ("Processes and threads. " * 4000))
rr = cl.post("/api/lessons/prepare", headers=auth, json={"target": str(book2)})
check("Prepare needs the Origin", rr.status_code == 403)
rr = cl.post("/api/lessons/prepare", headers=write, json={"target": "/etc/passwd"})
check("Prepare refuses a path that isn't one of his listed files", rr.status_code == 400 and rr.json().get("error"))
rr = cl.post("/api/lessons/prepare", headers=write, data="{nope")
check("Prepare with a broken body → 400", rr.status_code == 400)
rr = cl.post("/api/lessons/prepare", headers=write, json={"target": str(book2)})
pjob = rr.json().get("job") or {}
check("Prepare a listed file → a queued concept_map job", rr.status_code == 200 and pjob.get("status") == "queued"
      and pjob.get("kind") == "concept_map" and "background" in rr.json().get("message", ""), rr.text[:200])
rr2 = cl.post("/api/lessons/prepare", headers=write, json={"target": str(book2)})
check("Prepare twice → the same job", (rr2.json().get("job") or {}).get("id") == pjob.get("id")
      and "already being prepared" in rr2.json().get("message", ""))
P._call = fake_call
jobs.Worker(["concept_map"]).run_once()
P._call = real_call
files = {f["name"]: f for f in cl.get("/api/lessons", headers=auth).json()["files"]}
check("/api/lessons marks a prepared file", files["Operating Systems.md"]["prepared"] is True)
rr = cl.post("/api/lessons/prepare", headers=write, json={"target": str(book2)})
check("Prepare a prepared file → 'already prepared', no job", rr.json().get("prepared") is True and rr.json()["job"] is None)

# ------------------------------------------------------------------ 10. /api/events: server-sent events, live
print("live events (server-sent events)")
import httpx  # noqa: E402
import uvicorn  # noqa: E402

srv = uvicorn.Server(uvicorn.Config(server.app(), host="127.0.0.1", port=server.PORT, log_level="warning",
                                    timeout_graceful_shutdown=1))
st = threading.Thread(target=srv.run, daemon=True)
st.start()
for _ in range(100):
    if srv.started:
        break
    time.sleep(0.05)
check("the web server streams on a spare port", srv.started)
hc = httpx.Client(base_url=base, timeout=5)
check("/api/events needs the token", hc.get("/api/events", headers=hosth).status_code == 403)
check("/api/events checks the Host header",
      hc.get(f"/api/events?t={tok}", headers={"host": "evil.example"}).status_code == 403)
seen: dict = {"snapshot": None, "job": [], "new_id": None, "lat": None}


def listen_once() -> None:
    t0 = time.perf_counter()
    with hc.stream("GET", f"/api/events?t={tok}", headers=hosth) as resp:
        check("SSE answers 200 text/event-stream, no caching", resp.status_code == 200
              and resp.headers.get("content-type", "").startswith("text/event-stream")
              and "no-store" in resp.headers.get("cache-control", ""))
        ev = None
        for line in resp.iter_lines():
            if line.startswith("event: "):
                ev = line[7:]
            elif line.startswith("data: ") and ev == "snapshot":
                seen["snapshot"] = json.loads(line[6:])
                jobs.HUB.listening.wait(3)                    # the shared LISTEN is up → enqueue now
                t0 = time.perf_counter()
                seen["new_id"] = jobs.enqueue("t_quick", {"sse": 1}, label="Live.pdf")["id"]
            elif line.startswith("data: ") and ev == "job":
                d = json.loads(line[6:])
                seen["job"].append(d)
                if d["id"] == seen["new_id"]:
                    seen["lat"] = (time.perf_counter() - t0) * 1000
                    return
            if time.perf_counter() - t0 > 4:
                return


try:
    listen_once()
except httpx.HTTPError as e:
    print(f"  (stream error: {type(e).__name__})")
new_id, lat = seen["new_id"], seen["lat"]
snap = seen["snapshot"] or {}
check("first event: a snapshot of recent jobs", isinstance(snap.get("jobs"), list) and len(snap["jobs"]) >= 1)
mine = [d for d in seen["job"] if d["id"] == new_id]
check("a new job reaches the open stream as a `job` event", bool(mine) and mine[0]["status"] == "queued"
      and mine[0]["label"] == "Live.pdf", str(seen["job"])[:200])
check("…within half a second", lat is not None and lat < 500, f"{lat}")
time.sleep(0.3)
check("closing the page unsubscribes it", not jobs.HUB._subs)
srv.should_exit = True
st.join(5)
hc.close()

print(f"\n{passed}/{total} passed")
sys.exit(0 if passed == total else 1)
