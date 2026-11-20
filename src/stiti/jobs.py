"""Background jobs with live progress (D56): long tasks (concept maps today; notes, recaps, transcription next) run in
a worker thread inside Stiti.app, survive a restart, wait out free-tier limits, and report step / % / ETA live.

Research: docs/research/teaching_apps.md — Turbo's per-upload progress rows + a startup reconciler, NotebookLM's
"generate later" when the quota is out, iTutor's job queue. Postgres is the only moving part (no Redis, no new server):

- `enqueue(kind, recipe)` is idempotent: one live job (queued / running / parked) per kind + recipe hash.
- A `Worker` claims one ready row at a time with `FOR UPDATE SKIP LOCKED` (many workers never take the same job),
  runs the handler registered for its kind, and heartbeats while it runs.
- The handler reports `job.progress(step, percent)` (ETA is estimated from the pace when it doesn't give one) and
  saves what it already finished with `job.save(...)`; a restarted job reads `job.checkpoint` and resumes there.
- Free tier out (`router.NoProvider`, HTTP 429, or `raise Park`) → status `parked` with `not_before`; any other error
  → retried with backoff, then `failed` (Retry on the page); `raise Fail(msg)` fails at once.
- On start (and every half minute) running rows whose worker died — heartbeat stopped, or a dead pid on this Mac —
  go back to the queue with their step, percent and checkpoint kept.
- Every visible change fires `NOTIFY stiti_jobs` (a trigger, db/migrations/012_jobs.sql); `HUB` fans it out to the
  web app's `/api/events` server-sent-events streams.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import socket
import threading
import time
from collections.abc import Callable
from datetime import datetime, timedelta, timezone

import psycopg
from psycopg.rows import dict_row

from .config import CFG

CHANNEL = "stiti_jobs"
LIVE = ("queued", "running", "parked")
STALE_S = 60                 # a running job whose heartbeat is older than this lost its worker
HEARTBEAT_S = 10
POLL_S = 3.0                 # idle worker: look for ready jobs this often (an enqueue in this process wakes it)
RECONCILE_S = 30
RETRY_BASE_S, RETRY_MAX_S = 30, 15 * 60
PARK_BASE_S, PARK_MAX_S = 60, 30 * 60
_COLS = ("id, kind, recipe, label, status, step, percent, eta_s, error, attempts, max_attempts, parks, not_before, "
         "source_hash, result, created_at, updated_at, started_at, finished_at")


class Park(Exception):
    """Raise from a handler to wait (free tier out): the job is parked until `until` (default: backoff)."""

    def __init__(self, reason: str = "The free AI is out of quota for now.", until: datetime | None = None):
        super().__init__(reason)
        self.until = until


class Fail(Exception):
    """Raise from a handler for an error retrying won't fix (file gone, bad input): fails at once."""


class Cancelled(Exception):
    """He cancelled the job (or another worker took it over): stop quietly, write nothing."""


HANDLERS: dict[str, Callable[["Job"], dict | None]] = {}
_HANDLER_MODULES = ("stiti.tutor.prepare",)       # imported by the worker so their @handler()s register


def handler(kind: str):
    def deco(fn):
        HANDLERS[kind] = fn
        return fn
    return deco


def load_handlers() -> None:
    import importlib
    for m in _HANDLER_MODULES:
        try:
            importlib.import_module(m)
        except Exception as e:                                 # one broken handler never stops the others
            print(f"[jobs] handler {m}: {type(e).__name__}: {e}", flush=True)


# ------------------------------------------------------------------------------------------------ helpers
def _now() -> datetime:
    return datetime.now(timezone.utc)


def recipe_hash(kind: str, recipe: dict) -> str:
    return hashlib.sha256((kind + "\n" + json.dumps(recipe, sort_keys=True, separators=(",", ":"))).encode()).hexdigest()


def _connect() -> psycopg.Connection:
    return psycopg.connect(CFG.db_url, autocommit=True, row_factory=dict_row)


def public(row: dict | None) -> dict | None:
    """A job row as the page sees it (JSON-safe; recipe paths and results stay on the server)."""
    if not row:
        return None
    iso = lambda d: d.isoformat() if isinstance(d, datetime) else d  # noqa: E731
    return {"id": row["id"], "kind": row["kind"], "label": row.get("label") or row["kind"], "status": row["status"],
            "step": row.get("step"), "percent": row.get("percent") or 0, "eta_s": row.get("eta_s"),
            "error": row.get("error"), "attempts": row.get("attempts") or 0, "max_attempts": row.get("max_attempts"),
            "not_before": iso(row.get("not_before")), "created_at": iso(row.get("created_at")),
            "updated_at": iso(row.get("updated_at")), "finished_at": iso(row.get("finished_at"))}


_wake = threading.Event()        # set by enqueue/retry in this process → the worker looks right away


# ------------------------------------------------------------------------------------------------ the queue (API)
def enqueue(kind: str, recipe: dict, *, label: str | None = None, source_hash: str | None = None,
            max_attempts: int = 3) -> dict:
    """Add a job, or return the live one with the same kind + recipe (a second click never makes a second job).
    The row comes back with `new` = True when this call created it."""
    from .db import q, unheld
    h = recipe_hash(kind, recipe)
    with unheld():                                             # never inside a speculative voice turn
        for _ in range(3):
            rows = q(f"""INSERT INTO stiti_job (kind, recipe, recipe_hash, source_hash, label, max_attempts)
                         VALUES (%s, %s, %s, %s, %s, %s)
                         ON CONFLICT (recipe_hash) WHERE status IN ('queued','running','parked') DO NOTHING
                         RETURNING {_COLS}""",
                     (kind, json.dumps(recipe), h, source_hash, (label or kind)[:200], max_attempts))
            if rows:
                _wake.set()
                return {**rows[0], "new": True}
            rows = q(f"SELECT {_COLS} FROM stiti_job WHERE recipe_hash=%s AND status IN ('queued','running','parked')",
                     (h,))
            if rows:                                           # (it may have finished between the two statements)
                return {**rows[0], "new": False}
    raise RuntimeError("could not enqueue the job")


def get(job_id: int) -> dict | None:
    from .db import one
    return one(f"SELECT {_COLS} FROM stiti_job WHERE id=%s", (job_id,))


def recent(limit: int = 20) -> list[dict]:
    """Live jobs first (oldest first), then what finished in the last 3 days (newest first)."""
    from .db import q
    rows = q(f"""SELECT {_COLS} FROM stiti_job
                 WHERE status IN ('queued','running','parked') OR updated_at > now() - interval '3 days'
                 ORDER BY (status IN ('queued','running','parked')) DESC,
                          CASE WHEN status IN ('queued','running','parked') THEN extract(epoch FROM created_at)
                               ELSE -extract(epoch FROM updated_at) END
                 LIMIT %s""", (limit,))
    return [public(r) for r in rows]


def latest_for(kind: str, recipe: dict) -> dict | None:
    from .db import one
    return one(f"SELECT {_COLS} FROM stiti_job WHERE recipe_hash=%s ORDER BY id DESC LIMIT 1",
               (recipe_hash(kind, recipe),))


class NotPossible(ValueError):
    """Retry / cancel that doesn't apply to the job's state; the message is safe to show him."""


def retry(job_id: int) -> dict:
    """Failed / cancelled → back in the queue (fresh attempts); parked or waiting to retry → try now."""
    from .db import q
    try:
        rows = q(f"""UPDATE stiti_job SET status='queued', not_before=NULL, error=NULL, eta_s=NULL, finished_at=NULL,
                            attempts = CASE WHEN status IN ('failed','cancelled') THEN 0 ELSE attempts END,
                            updated_at=now()
                     WHERE id=%s AND status IN ('failed','cancelled','parked','queued') RETURNING {_COLS}""",
                 (job_id,))
    except psycopg.errors.UniqueViolation:
        raise NotPossible("The same job is already in the queue.") from None
    if not rows:
        row = get(job_id)
        raise NotPossible("No such job." if not row else
                          "It's running right now." if row["status"] == "running" else "It already finished.")
    _wake.set()
    return rows[0]


def cancel(job_id: int) -> dict:
    """Queued / parked → cancelled now; running → cancelled, and the handler stops at its next progress report."""
    from .db import q
    rows = q(f"""UPDATE stiti_job SET status='cancelled', finished_at=now(), not_before=NULL, eta_s=NULL,
                        updated_at=now()
                 WHERE id=%s AND status IN ('queued','running','parked') RETURNING {_COLS}""", (job_id,))
    if not rows:
        raise NotPossible("No such job." if not get(job_id) else "It already finished.")
    return rows[0]


def _backoff(n: int, base: float, cap: float) -> float:
    return min(cap, base * 2 ** max(0, n - 1))


def park_until(c: psycopg.Connection, parks: int) -> datetime:
    """Backoff (1, 2, 4… min, at most 30), or later if every provider's 429 cooldown ends later than that."""
    t = _now() + timedelta(seconds=_backoff(parks, PARK_BASE_S, PARK_MAX_S))
    try:
        row = c.execute("SELECT min(cooldown_until) AS m FROM llm_usage WHERE day=current_date "
                        "AND cooldown_until > now()").fetchone()
        if row and row["m"] and row["m"] > t:
            t = row["m"]
    except psycopg.Error:
        pass
    return t


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def requeue_stale(c: psycopg.Connection | None = None, stale_s: float = STALE_S, *, me: str = "") -> list[int]:
    """Running jobs whose worker died go back to the queue, keeping step / percent / checkpoint (they resume).
    Dead = heartbeat older than stale_s, or claimed by a process on this Mac that no longer exists."""
    own = c is None
    c = c or _connect()
    try:
        host = socket.gethostname()
        rows = c.execute("""SELECT id, claimed_by, heartbeat_at < now() - make_interval(secs => %s) AS old,
                                   heartbeat_at IS NULL AS never
                            FROM stiti_job WHERE status='running'""", (stale_s,)).fetchall()
        dead = []
        for r in rows:
            who = (r["claimed_by"] or "").split(":")
            gone = (len(who) >= 2 and who[0] == host and who[1].isdigit() and int(who[1]) != os.getpid()
                    and not _pid_alive(int(who[1])))
            if r["claimed_by"] == me and me:
                continue
            if r["old"] or r["never"] or gone:
                dead.append(r["id"])
        if dead:
            c.execute("""UPDATE stiti_job SET status='queued', claimed_by=NULL, heartbeat_at=NULL, eta_s=NULL,
                                updated_at=now()
                         WHERE id = ANY(%s) AND status='running'""", (dead,))
        return dead
    finally:
        if own:
            c.close()


# ------------------------------------------------------------------------------------------------ a running job
class Job:
    """What a handler gets: its recipe, its checkpoint, and progress/save that write through the worker."""

    def __init__(self, row: dict, worker: "Worker"):
        self.id: int = row["id"]
        self.kind: str = row["kind"]
        self.recipe: dict = row["recipe"] or {}
        self.label: str = row.get("label") or self.kind
        self.source_hash: str | None = row.get("source_hash")
        self.checkpoint: dict = dict(row.get("checkpoint") or {})
        self.attempts: int = row.get("attempts") or 0
        self.parks: int = row.get("parks") or 0
        self.cancelled = False
        self._w = worker
        self._t0 = time.monotonic()
        self._p0 = int(row.get("percent") or 0)                 # resumed jobs start part-way
        self._last: tuple | None = None

    def progress(self, step: str | None = None, percent: float | None = None, eta_s: float | None = None) -> None:
        """Report where it is. Raises Cancelled if he cancelled it. ETA: from the pace so far when not given."""
        p = None if percent is None else max(0, min(100, int(percent)))
        if eta_s is None and p is not None and p > self._p0 and p < 100:
            el = time.monotonic() - self._t0
            if el > 1:
                eta_s = el * (100 - p) / (p - self._p0)
        eta = None if eta_s is None else max(0, int(round(eta_s)))
        key = (step, p, eta)
        if key == self._last:
            return
        self._last = key
        rows = self._w._x("""UPDATE stiti_job SET step=COALESCE(%s, step), percent=COALESCE(%s, percent), eta_s=%s,
                                    heartbeat_at=now(), updated_at=now()
                             WHERE id=%s AND status='running' AND claimed_by=%s RETURNING id""",
                          (None if step is None else str(step)[:200], p, eta, self.id, self._w.id))
        if not rows:
            self.cancelled = True
            raise Cancelled()

    def save(self, **parts) -> None:
        """Merge top-level keys into the checkpoint (what's done so far); a resumed run sees them in .checkpoint."""
        self.checkpoint.update(parts)
        self._w._x("UPDATE stiti_job SET checkpoint = checkpoint || %s::jsonb, heartbeat_at=now() "
                   "WHERE id=%s AND status='running' AND claimed_by=%s", (json.dumps(parts), self.id, self._w.id))


# ------------------------------------------------------------------------------------------------ the worker
_n = 0


class Worker:
    """Claims and runs one job at a time in its own thread (a background job never blocks voice or the web app)."""

    def __init__(self, kinds: list[str] | None = None, *, poll_s: float = POLL_S, stale_s: float = STALE_S,
                 heartbeat_s: float = HEARTBEAT_S):
        global _n
        _n += 1
        self.id = f"{socket.gethostname()}:{os.getpid()}:{_n}"
        self.kinds = kinds
        self.poll_s, self.stale_s, self.heartbeat_s = poll_s, stale_s, heartbeat_s
        self.stop_evt = threading.Event()
        self.thread: threading.Thread | None = None
        self.current: Job | None = None
        self._c: psycopg.Connection | None = None
        self._lock = threading.Lock()
        self._last_reconcile = 0.0
        self.ran = 0

    # one connection per worker; the handler's own threads (concept_map reads two units at a time) share it
    def _x(self, sql: str, params=None) -> list[dict]:
        with self._lock:
            if self._c is None or self._c.closed:
                self._c = _connect()
            cur = self._c.execute(sql, params)
            return cur.fetchall() if cur.description else []

    def _kinds(self) -> list[str]:
        return list(self.kinds) if self.kinds is not None else list(HANDLERS)

    def claim(self) -> Job | None:
        kinds = self._kinds()
        if not kinds:
            return None
        rows = self._x(f"""UPDATE stiti_job SET status='running', claimed_by=%s, heartbeat_at=now(), started_at=now(),
                                  not_before=NULL, error=NULL, eta_s=NULL, finished_at=NULL, updated_at=now()
                           WHERE id = (SELECT id FROM stiti_job
                                       WHERE status IN ('queued','parked') AND kind = ANY(%s)
                                         AND (not_before IS NULL OR not_before <= now())
                                       ORDER BY created_at, id
                                       FOR UPDATE SKIP LOCKED LIMIT 1)
                           RETURNING {_COLS}, checkpoint""", (self.id, kinds))
        return Job(rows[0], self) if rows else None

    def run_once(self) -> bool:
        """Claim one ready job and run it to an end state. False when nothing was ready."""
        if time.monotonic() - self._last_reconcile > RECONCILE_S:
            self._last_reconcile = time.monotonic()
            with self._lock:
                if self._c is None or self._c.closed:
                    self._c = _connect()
                requeue_stale(self._c, self.stale_s, me=self.id)
        job = self.claim()
        if not job:
            return False
        self.current = job
        beat = threading.Event()
        hb = threading.Thread(target=self._heartbeat, args=(job, beat), name="stiti-job-beat", daemon=True)
        hb.start()
        try:
            self._run(job)
        finally:
            beat.set()
            self.current = None
            self.ran += 1
        return True

    def _heartbeat(self, job: Job, done: threading.Event) -> None:
        while not done.wait(self.heartbeat_s):
            try:
                rows = self._x("UPDATE stiti_job SET heartbeat_at=now() WHERE id=%s AND status='running' "
                               "AND claimed_by=%s RETURNING id", (job.id, self.id))
                if not rows:
                    job.cancelled = True
            except psycopg.Error:
                pass

    def _run(self, job: Job) -> None:
        from . import router
        fn = HANDLERS.get(job.kind)
        try:
            if fn is None:
                raise Fail(f"Stiti doesn't know how to do '{job.kind}' jobs.")
            result = fn(job)
            if job.cancelled:
                raise Cancelled()
            self._finish(job, result)
        except Cancelled:
            pass                                               # the row already says cancelled; write nothing
        except Park as e:
            self._park(job, str(e), e.until)
        except router.NoProvider as e:
            if "P2" in str(e):                                 # private content never leaves the Mac: no retry helps
                self._fail(job, "This needs the cloud AI, but the content is private.", permanent=True)
            elif "no API keys" in str(e):
                self._park(job, "No free AI key yet. Add one (e.g. GROQ_API_KEY) to .env.", None)
            else:
                self._park(job, "The free AI is busy or out of quota for now.", None)
        except Fail as e:
            self._fail(job, str(e) or "It can't be done.", permanent=True)
        except Exception as e:                                 # noqa: BLE001 — any other error: retry with backoff
            if getattr(e, "status_code", None) == 429:
                self._park(job, "The free AI is busy or out of quota for now.", None)
            else:
                print(f"[jobs] {job.kind} #{job.id}: {type(e).__name__}: {e}", flush=True)
                self._fail(job, f"{type(e).__name__}: {str(e)[:200]}", permanent=False)

    def _finish(self, job: Job, result: dict | None) -> None:
        self._x("""UPDATE stiti_job SET status='done', percent=100, eta_s=0, step=COALESCE(%s, 'Done'),
                          result=%s, finished_at=now(), heartbeat_at=NULL, claimed_by=NULL, updated_at=now()
                   WHERE id=%s AND status='running' AND claimed_by=%s""",
                ((result or {}).get("step") if isinstance(result, dict) else None,
                 json.dumps(result or {}, default=str), job.id, self.id))

    def _park(self, job: Job, reason: str, until: datetime | None) -> None:
        with self._lock:
            if self._c is None or self._c.closed:
                self._c = _connect()
            t = until or park_until(self._c, job.parks + 1)
        self._x("""UPDATE stiti_job SET status='parked', parks=parks+1, not_before=%s, error=%s, eta_s=NULL,
                          heartbeat_at=NULL, claimed_by=NULL, updated_at=now()
                   WHERE id=%s AND status='running' AND claimed_by=%s""", (t, reason[:300], job.id, self.id))

    def _fail(self, job: Job, err: str, *, permanent: bool) -> None:
        n = job.attempts + 1
        rows = self._x("SELECT max_attempts FROM stiti_job WHERE id=%s", (job.id,))
        final = permanent or not rows or n >= rows[0]["max_attempts"]
        t = None if final else _now() + timedelta(seconds=_backoff(n, RETRY_BASE_S, RETRY_MAX_S))
        self._x("""UPDATE stiti_job SET status=%s, attempts=%s, error=%s, not_before=%s, eta_s=NULL,
                          finished_at=CASE WHEN %s THEN now() END, heartbeat_at=NULL, claimed_by=NULL, updated_at=now()
                   WHERE id=%s AND status='running' AND claimed_by=%s""",
                ("failed" if final else "queued", n, err[:300], t, final, job.id, self.id))

    # ---- thread
    def start(self) -> "Worker":
        if self.kinds is None:
            load_handlers()
        self.thread = threading.Thread(target=self._loop, name="stiti-jobs", daemon=True)
        self.thread.start()
        return self

    def stop(self, timeout: float = 5.0) -> None:
        self.stop_evt.set()
        _wake.set()
        if self.thread and self.thread is not threading.current_thread():
            self.thread.join(timeout)
        with self._lock:
            if self._c is not None and not self._c.closed:
                self._c.close()

    def _loop(self) -> None:
        try:
            with self._lock:
                self._c = _connect()
                back = requeue_stale(self._c, self.stale_s, me=self.id)
            self._last_reconcile = time.monotonic()
            if back:
                print(f"[jobs] resuming {len(back)} job(s) left running before the restart", flush=True)
        except psycopg.errors.UndefinedTable:
            print("[jobs] off — apply db/migrations/012_jobs.sql", flush=True)
            return
        except psycopg.Error as e:
            print(f"[jobs] {type(e).__name__}: {e}", flush=True)
        while not self.stop_evt.is_set():
            try:
                ran = self.run_once()
            except psycopg.errors.UndefinedTable:
                print("[jobs] off — apply db/migrations/012_jobs.sql", flush=True)
                return
            except psycopg.Error as e:                         # database restarting: wait, reconnect
                print(f"[jobs] {type(e).__name__}: {str(e)[:160]}", flush=True)
                with self._lock:
                    if self._c is not None:
                        try:
                            self._c.close()
                        except psycopg.Error:
                            pass
                        self._c = None
                self.stop_evt.wait(5)
                continue
            if not ran:
                _wake.wait(self.poll_s)
                _wake.clear()


_worker: Worker | None = None


def start_worker() -> Worker:
    """The always-on app's worker (Stiti.app / `stiti web`). Safe to call twice."""
    global _worker
    if _worker is None or not (_worker.thread and _worker.thread.is_alive()):
        _worker = Worker().start()
    return _worker


def stop_worker(timeout: float = 5.0) -> None:
    global _worker
    if _worker is not None:
        _worker.stop(timeout)
        _worker = None


# ------------------------------------------------------------------------------------------------ live events
class Hub:
    """One LISTEN connection for the whole process, fanned out to every open /api/events stream. The listening
    thread starts with the first subscriber and stops a few seconds after the last one leaves."""

    def __init__(self):
        self._subs: set[tuple[asyncio.AbstractEventLoop, asyncio.Queue]] = set()
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self.listening = threading.Event()

    def subscribe(self, loop: asyncio.AbstractEventLoop) -> asyncio.Queue:
        qu: asyncio.Queue = asyncio.Queue(maxsize=500)
        with self._lock:
            self._subs.add((loop, qu))
            if self._thread is None or not self._thread.is_alive():
                self.listening.clear()
                self._thread = threading.Thread(target=self._run, name="stiti-jobs-listen", daemon=True)
                self._thread.start()
        return qu

    def unsubscribe(self, qu: asyncio.Queue) -> None:
        with self._lock:
            self._subs = {s for s in self._subs if s[1] is not qu}

    def _fan(self, payload: str) -> None:
        def put(qu, p=payload):
            try:
                qu.put_nowait(p)
            except asyncio.QueueFull:                          # a stuck tab misses events, never blocks others
                pass
        with self._lock:
            subs = list(self._subs)
        for loop, qu in subs:
            try:
                loop.call_soon_threadsafe(put, qu)
            except RuntimeError:                               # its event loop is gone
                self.unsubscribe(qu)

    def _run(self) -> None:
        idle_since = None
        while True:
            try:
                with _connect() as c:
                    c.execute(f"LISTEN {CHANNEL}")
                    self.listening.set()
                    while True:
                        for n in c.notifies(timeout=2.0):
                            self._fan(n.payload)
                        with self._lock:
                            if self._subs:
                                idle_since = None
                            else:
                                idle_since = idle_since or time.monotonic()
                                if time.monotonic() - idle_since > 5:
                                    self._thread = None
                                    self.listening.clear()
                                    return
            except psycopg.Error as e:
                self.listening.clear()
                print(f"[jobs] listen: {type(e).__name__}: {str(e)[:120]}", flush=True)
                time.sleep(2)
                with self._lock:
                    if not self._subs:
                        self._thread = None
                        return


HUB = Hub()
