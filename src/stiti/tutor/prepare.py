"""Prepare a file before a lesson (D56): build the coach's concept map in the background, so the lesson on that file
starts at once (the map is the slow part: one free-LLM call per unit).

The job wraps `coach.concept_map` with its own `call`:
- every finished unit is saved in the job's checkpoint, so a restart (or a free-tier pause) resumes with the units
  still missing — nothing already read is asked again;
- each finished unit moves the progress (step "4 of 9 units read · Unit 4: Parsing", %, ETA from the pace);
- if the free tier ran out on any unit, the half-built map is thrown away (the coach would otherwise cache filler
  for those units) and the job is parked until the limit resets.
A map is stale when the file changed after it was built (newer mtime): Prepare builds it again.
"""
from __future__ import annotations

import hashlib
import re
import threading
from pathlib import Path

from .. import jobs

KIND = "concept_map"


def source_hash(path: str) -> str | None:
    try:
        st = Path(path).stat()
    except OSError:
        return None
    return hashlib.sha256(f"{path}|{st.st_size}|{st.st_mtime_ns}".encode()).hexdigest()[:32]


def cache_file(path: str) -> Path:
    from .coach import _cache_path
    return _cache_path(path)


def prepared(path: str) -> bool:
    """A concept map for this file exists and was built after the file last changed."""
    c = cache_file(path)
    try:
        return c.stat().st_mtime >= Path(path).stat().st_mtime and c.stat().st_size > 2
    except OSError:
        return False


def enqueue(path: str, label: str | None = None) -> dict:
    return jobs.enqueue(KIND, {"path": path}, label=label or Path(path).name, source_hash=source_hash(path))


@jobs.handler(KIND)
def run(job: jobs.Job) -> dict:
    from .. import router
    from . import book as B
    from . import coach as C
    from . import planner as P
    path = str(job.recipe.get("path") or "")
    p = Path(path)
    if not path or not p.is_file():
        raise jobs.Fail("The file isn't there any more (moved or deleted).")
    if p.suffix.lower() not in _book_exts():
        raise jobs.Fail("Stiti can only prepare study files (PDF, EPUB, Word, slides, text).")
    if prepared(path):
        job.progress("Already prepared", 100)
        return {"step": "Ready for a lesson", "cached": True}
    cache = cache_file(path)
    cache.unlink(missing_ok=True)                              # older than the file: rebuild

    job.progress("Opening the file", 3)
    b = B.load(path)
    total = max(1, len((b.chapters() or b.sections)[:12]))
    del b
    calls: dict[str, dict] = dict(job.checkpoint.get("calls") or {})
    lock = threading.Lock()
    limited: list[str] = []
    done_before = len(calls)
    job.progress(f"Reading {total} unit{'s' if total != 1 else ''}" + (f" · {done_before} already read" if done_before
                                                                        else ""), 5 + 90 * min(done_before, total) / total)

    def call(system, user, schema, name, max_tokens, **kw):
        key = hashlib.sha256(user.encode()).hexdigest()[:24]
        with lock:
            if key in calls:
                return calls[key]
        if job.cancelled:
            raise jobs.Cancelled()
        try:
            d = P._call(system, user, schema, name, max_tokens, **kw)
        except router.NoProvider as e:
            limited.append(str(e))
            raise
        except Exception as e:
            if getattr(e, "status_code", None) == 429:
                limited.append(str(e))
            raise
        m = re.search(r"^UNIT: (.+)$", user, re.M)
        with lock:
            calls[key] = d
            n = len(calls)
            snapshot = dict(calls)
        try:
            job.save(calls=snapshot)
            job.progress(f"{min(n, total)} of {total} units read" + (f" · {m.group(1)[:60]}" if m else ""),
                         5 + 90 * min(n, total) / total)
        except jobs.Cancelled:
            pass
        return d

    concepts = C.concept_map(path, book_path=path, call=call)
    if job.cancelled:
        cache.unlink(missing_ok=True)
        raise jobs.Cancelled()
    if limited:
        cache.unlink(missing_ok=True)                          # filler for the units it couldn't read: not kept
        raise jobs.Park(f"The free AI ran out after {len(calls)} of {total} units. It picks up from there.")
    if not concepts:
        raise RuntimeError("no concepts came back")
    units = len({c.unit for c in concepts})
    return {"step": f"Ready · {len(concepts)} topics in {units} unit{'s' if units != 1 else ''}",
            "concepts": len(concepts), "units": units}


def _book_exts() -> tuple[str, ...]:
    from . import BOOK_EXTS
    return tuple(BOOK_EXTS)
