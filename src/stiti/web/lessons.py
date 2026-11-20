"""The web Lessons page's backend: his study files, the tutor's saved notes, per-file mastery, and starting a lesson.

Read-only except `start()`, which goes through the tutor's own argv spawn (never a shell string) under the same
one-lesson lock as voice launches. A start target is either one of the files this module lists (exact path match)
or a plain topic — never an arbitrary path, so the page can't make the tutor read a file he didn't pick.
Notes are only read from ~/.stiti/tutor/notes (path-safe). `prepare()` (D56) queues a background job that builds the
concept map of one listed file before a lesson — same exact-path rule; the only database write here.
"""
from __future__ import annotations

import json
import re
import time
from datetime import datetime
from pathlib import Path

from ..config import CFG

MIN_BYTES = 50_000          # same floor as find_book(): skips tiny stray files
MAX_FILES = 50
MAX_TOPIC = 120
MODES = ("learn", "exam", "day")
HOURS_MIN, HOURS_MAX = 1.0, 12.0
# a topic is plain words: letters/digits/space and everyday punctuation; never a flag ("-…") or a path
TOPIC_RX = re.compile(r"[\w .,:;'’\"()&+/?!#-]{1,%d}" % MAX_TOPIC)


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts).astimezone().isoformat(timespec="seconds")


def _tutor():
    from .. import tutor
    return tutor


def notes_dir() -> Path:
    return CFG.home / "tutor" / "notes"


# ------------------------------------------------------------------------------------------------ reads
def files() -> list[dict]:
    """His study files: top level of the tutor's BOOK_DIRS, book extensions, > 50 KB, newest first, at most 50."""
    t = _tutor()
    found: dict[str, tuple[Path, float, int]] = {}
    for d in t.BOOK_DIRS:
        root = Path(d).expanduser()
        if not root.is_dir():
            continue
        try:
            entries = list(root.iterdir())
        except OSError:
            continue
        for f in entries:
            if f.name.startswith(".") or f.suffix.lower() not in t.BOOK_EXTS:
                continue
            try:
                if not f.is_file():
                    continue
                st = f.stat()
            except OSError:
                continue
            if st.st_size > MIN_BYTES:
                found[str(f)] = (f, st.st_mtime, st.st_size)
    rows = sorted(found.values(), key=lambda x: -x[1])[:MAX_FILES]
    from ..tutor.prepare import prepared
    return [{"path": str(f), "name": f.name, "ext": f.suffix.lower().lstrip("."), "size": size, "modified": _iso(mt),
             "prepared": prepared(str(f))}
            for f, mt, size in rows]


def _note_title(p: Path) -> str:
    try:
        with p.open(encoding="utf-8", errors="replace") as fh:
            first = fh.readline().strip()
    except OSError:
        first = ""
    if first.startswith("# "):
        return re.sub(r"\s+—\s+notes$", "", first[2:].strip())[:120] or p.stem
    return p.stem.replace("-", " ")


def notes() -> list[dict]:
    d = notes_dir()
    if not d.is_dir():
        return []
    out = []
    for p in d.glob("*.md"):
        try:
            if not p.is_file():
                continue
            st = p.stat()
        except OSError:
            continue
        out.append({"name": p.name, "title": _note_title(p), "path": str(p), "modified": _iso(st.st_mtime),
                    "size": st.st_size, "_mt": st.st_mtime})
    out.sort(key=lambda n: -n.pop("_mt"))
    return out


def note_text(name: str) -> str | None:
    """The markdown of one saved note, or None. Only a plain `<name>.md` directly inside the notes folder."""
    if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._ -]{0,120}\.md", name) or ".." in name:
        return None
    root = notes_dir().resolve()
    p = (root / name).resolve()
    if p.parent != root or not p.is_file():
        return None
    try:
        return p.read_text(encoding="utf-8", errors="replace")[:400_000]
    except OSError:
        return None


def _source_label(source: str) -> tuple[str, str]:
    """('compilers.pdf · Unit 3', 'file') for a file source; ('how DNS works', 'topic') for a topic."""
    t = _tutor()
    base, _, unit = source.partition("#")
    p = Path(base)
    if p.suffix.lower() in t.BOOK_EXTS and ("/" in base or "\\" in base):
        return (p.name + (f" · {unit}" if unit else ""))[:140], "file"
    return source[:140], "topic"


def progress() -> list[dict]:
    """Per lesson source (his file or a topic): how many concepts are known / shaky / new, from the tutor's mastery
    files (~/.stiti/tutor/mastery) and, for the total, the cached concept map of the same source."""
    from ..tutor.mastery import KNOWN, PRIOR, SHAKY
    mdir = CFG.home / "tutor" / "mastery"
    cdir = CFG.home / "tutor" / "concepts"
    if not mdir.is_dir():
        return []
    out = []
    for f in mdir.glob("*.json"):
        try:
            d = json.loads(f.read_text())
            p = {str(k): float(v) for k, v in (d.get("p") or {}).items()}
            seen = [float(v) for v in (d.get("seen") or {}).values()]
            source = str(d.get("source") or "").strip()
        except (OSError, ValueError, TypeError, AttributeError):
            continue
        if not source:
            continue
        names: dict[str, str] = {}
        try:
            names = {str(c["id"]): str(c.get("name") or "") for c in json.loads((cdir / f.name).read_text())
                     if isinstance(c, dict) and c.get("id")}
        except (OSError, ValueError, TypeError):
            pass
        ids = list(names) or list(p)
        lv = {i: ("known" if p.get(i, PRIOR) >= KNOWN else "shaky" if p.get(i, PRIOR) >= SHAKY else "new") for i in ids}
        label, kind = _source_label(source)
        out.append({"key": f.stem, "source": label, "kind": kind, "total": len(ids),
                    "known": sum(v == "known" for v in lv.values()), "shaky": sum(v == "shaky" for v in lv.values()),
                    "new": sum(v == "new" for v in lv.values()),
                    "revise": [names[i] for i in ids if lv[i] == "shaky" and names.get(i)][:4],
                    "last_seen": _iso(max(seen)) if seen else None, "_t": max(seen) if seen else 0.0})
    out.sort(key=lambda r: -r.pop("_t"))
    return out


def board_url() -> str:
    from ..tutor.server import BOARD_PORT, board_token
    return f"http://127.0.0.1:{BOARD_PORT}/#t={board_token()}"


def overview() -> dict:
    t = _tutor()
    return {"active": bool(t.tutor_active()), "board_url": board_url(), "files": files(), "notes": notes(),
            "progress": progress()}


# ------------------------------------------------------------------------------------------------ start
class Invalid(ValueError):
    """A start request the page shouldn't have sent; the message is safe to show him."""


def plain_topic(text) -> str:
    """A topic he typed, or Invalid. Never a flag, never something the tutor would open as a file."""
    t = _tutor()
    if not isinstance(text, str):
        raise Invalid("Type a topic, or pick one of your files.")
    if any(ord(ch) < 32 for ch in text):
        raise Invalid("Use plain words for the topic (letters, numbers, simple punctuation).")
    s = " ".join(text.split())
    if not s:
        raise Invalid("Type a topic, or pick one of your files.")
    if len(s) > MAX_TOPIC:
        raise Invalid(f"Keep the topic under {MAX_TOPIC} characters.")
    if not TOPIC_RX.fullmatch(s) or s.startswith(("-", "/", "~", ".")):
        raise Invalid("Use plain words for the topic (letters, numbers, simple punctuation).")
    if Path(s).suffix.lower() in t.BOOK_EXTS or Path(s).expanduser().exists():
        raise Invalid("To learn from a file, pick it from Your files.")
    return s


def build_args(body: dict) -> tuple[list[str], str]:
    """Validated request → (argv for `stiti teach`, a short label). Raises Invalid."""
    if not isinstance(body, dict):
        raise Invalid("Bad request.")
    target = body.get("target")
    listed = {f["path"]: f for f in files()}
    if isinstance(target, str) and target in listed:
        arg, label = target, listed[target]["name"]
    else:
        arg = label = plain_topic(target)
    mode = body.get("mode", "learn")
    if mode not in MODES:
        raise Invalid("Pick Learn, Exam or Whole syllabus today.")
    args = [arg, "--goal-mode", mode]
    if mode == "day":
        try:
            hours = float(body.get("hours", 6))
        except (TypeError, ValueError):
            raise Invalid("Hours must be a number.") from None
        if not HOURS_MIN <= hours <= HOURS_MAX:
            raise Invalid(f"Pick between {HOURS_MIN:g} and {HOURS_MAX:g} hours.")
        args += ["--hours", f"{round(hours * 2) / 2:g}"]
    if mode == "exam":
        days = body.get("days", 1)
        if not isinstance(days, int) or isinstance(days, bool) or not (0 <= days <= 60):
            raise Invalid("Pick when the exam is.")
        args += ["--days", str(days)]
    focus = body.get("focus")
    if focus not in (None, ""):
        if not isinstance(focus, str):
            raise Invalid("Focus must be text.")
        if any(ord(ch) < 32 for ch in focus):
            raise Invalid("Use plain words in “focus on” (e.g. SDD and parse trees).")
        f = " ".join(focus.split())
        if f:
            if len(f) > MAX_TOPIC or not TOPIC_RX.fullmatch(f) or f.startswith("-"):
                raise Invalid("Use plain words in “focus on” (e.g. SDD and parse trees).")
            args += ["--focus", f]
    ptt = body.get("ptt", False)
    if not isinstance(ptt, bool):
        raise Invalid("Bad hold-to-talk value.")
    if ptt:
        args.append("--ptt")
    return args, label


def start(body: dict) -> dict:
    """Start a lesson from the page. One lesson at a time (the tutor's launch lock + lesson lock)."""
    t = _tutor()
    try:
        args, label = build_args(body)
    except Invalid as e:
        return {"ok": False, "message": str(e), "status": 400}
    from .. import router
    from ..tutor.lesson import demos
    if args[0] not in demos() and not any(s["key"] for s in router.status()):
        return {"ok": False, "status": 503, "message": "Stiti needs a free cloud key to plan a new lesson. Add one "
                "(e.g. GROQ_API_KEY) to .env, or try the built-in lesson: type “compiler”."}
    if not t.start_lesson(args):
        return {"ok": False, "active": True, "status": 409,
                "message": "A lesson is already open on the whiteboard. Finish it first (say “end” on the board)."}
    return {"ok": True, "active": True, "message": f"Opening the whiteboard with {label[:60]}.",
            "started_at": time.time()}


# ------------------------------------------------------------------------------------------------ prepare (D56)
def prepare(body: dict) -> dict:
    """Queue "build the concept map" for one of his listed files, so a lesson on it starts at once. Idempotent: a
    second click returns the same live job. Needs a free cloud key (the map is written by the free LLM)."""
    if not isinstance(body, dict):
        return {"ok": False, "status": 400, "message": "Bad request."}
    target = body.get("target")
    listed = {f["path"]: f for f in files()}
    if not isinstance(target, str) or target not in listed:
        return {"ok": False, "status": 400, "message": "Pick one of your files to prepare."}
    from .. import jobs
    from ..tutor import prepare as PR
    if listed[target]["prepared"]:
        return {"ok": True, "status": 200, "prepared": True, "job": None,
                "message": f"{listed[target]['name']} is already prepared."}
    row = PR.enqueue(target, listed[target]["name"])
    return {"ok": True, "status": 200, "prepared": False, "job": jobs.public(row),
            "message": (f"Preparing {listed[target]['name']} in the background." if row.get("new")
                        else f"{listed[target]['name']} is already being prepared.")}
