"""Whiteboard tutor — Stiti teaches a topic or a book chapter by voice while drawing on a live board.

    uv run stiti teach                     # built-in demo (no API key needed)
    uv run stiti teach "how DNS works"     # any topic (needs a free LLM key in .env)
    uv run stiti teach book.pdf --chapter 3.1
    uv run stiti teach --resume            # continue the last unfinished lesson
    uv run stiti book book.pdf             # just show the book's outline
Flags: --type (speakers + keyboard, no mic) · --silent (no sound) · --no-board (voice only, no screen)
       --minutes N · --debug
"""
from __future__ import annotations

import os
import re
import queue
import sys
import threading
from pathlib import Path

from ..config import CFG

LOCK = CFG.home / "tutor.lock"
BOOK_EXTS = {".pdf", ".epub", ".md", ".txt", ".docx", ".html", ".htm", ".pptx", ".rtf"}


LOCK_WAIT_S = 1.5        # a lesson waits this long for the lock (readers hold it for microseconds), then gives up
_held_fd: int | None = None
_launch_lock = threading.Lock()


def _pid_in_lock() -> int | None:
    try:
        return int(LOCK.read_text().strip())
    except (FileNotFoundError, ValueError, OSError):
        return None


def _alive(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError, OSError):
        return False


def _flock_held() -> bool:
    """Some process holds the lesson lock (kernel flock: released by the kernel when that process dies)."""
    import fcntl
    try:
        fd = os.open(LOCK, os.O_RDONLY)
    except OSError:
        return False
    try:
        fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
        fcntl.flock(fd, fcntl.LOCK_UN)
        return False
    except OSError:
        return True
    finally:
        os.close(fd)


def tutor_active() -> bool:
    """True while a lesson runs or is loading (Stiti's always-on voice loop stays out of the way)."""
    return _flock_held() or _alive(_pid_in_lock())


def _other_lesson() -> bool:
    """Another live lesson holds the lock (a lesson that holds it itself, or whose own pid is written, is us)."""
    if _held_fd is not None:
        return False
    if _flock_held():
        return True
    pid = _pid_in_lock()
    return pid != os.getpid() and _alive(pid)


def acquire_lesson(wait_s: float = LOCK_WAIT_S) -> bool:
    """Take the one-lesson lock for this process's whole life, or return False (another lesson has it).
    D33 used a pid file: check-then-write, so two launches in the same second, or a voice launch while a terminal
    `stiti teach` was still loading, could both start (three voices, 2026-11-11). A kernel flock is atomic; the
    pid is still written for readers. The file is never unlinked (that would break flock exclusivity)."""
    import fcntl
    import time
    global _held_fd
    if _held_fd is not None:
        return True
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(LOCK, os.O_RDWR | os.O_CREAT, 0o600)
    deadline = time.monotonic() + wait_s
    while True:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            break
        except OSError:
            if time.monotonic() >= deadline:
                os.close(fd)
                return False
            time.sleep(0.02)
    os.ftruncate(fd, 0)
    os.pwrite(fd, str(os.getpid()).encode(), 0)
    _held_fd = fd
    return True


def release_lesson() -> None:
    import fcntl
    global _held_fd
    fd, _held_fd = _held_fd, None
    if fd is None:
        return
    try:
        os.ftruncate(fd, 0)
        fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


def _arg(args: list[str], flag: str, default=None):
    return args[args.index(flag) + 1] if flag in args and args.index(flag) + 1 < len(args) else default


def _stdin_reader(events: queue.Queue, stop: threading.Event) -> None:
    while not stop.is_set():
        try:
            line = input()
        except (EOFError, KeyboardInterrupt):
            return
        if line.strip():
            events.put({"type": "text", "text": line.strip()})


def make_lesson(target: str | None, args: list[str], say=print):
    """-> (lesson, planner|None, start_cursor). Raises SystemExit with a friendly message when it can't."""
    from . import lesson as L
    minutes = int(_arg(args, "--minutes", "15"))
    if "--resume" in args:
        from . import store
        row = store.last_unfinished()
        if not row:
            raise SystemExit("No unfinished lesson to resume. Try: uv run stiti teach")
        say(f"Resuming '{row['title']}' where we stopped.")
        return L.from_dict(row["plan"]), None, row["cursor"]
    demos = L.demos()
    if not target or target in demos:
        return L.load(demos[target or "compiler"]), None, 0
    from .. import router
    if not any(s["key"] for s in router.status()):
        raise SystemExit("I need a free LLM key to write new lessons (the brain stays local; only the lesson "
                         "text is written in the cloud).\n  → get one free at https://console.groq.com/keys and add "
                         "GROQ_API_KEY=… to .env\nMeanwhile, try the built-in lesson: uv run stiti teach")
    from . import planner
    p = Path(target).expanduser()
    if p.suffix.lower() in BOOK_EXTS and p.exists():
        from . import book
        b = book.load(p)
        want = _arg(args, "--chapter")
        sec = b.find(want) if want else (b.chapters() or b.sections or [None])[0]
        if sec is None:
            print(book.outline_text(b, 1))
            raise SystemExit("Couldn't find that part of the book. Pick one above, e.g. --chapter 3.1")
        say(f"Reading {sec.name} from {b.title} (pages {sec.label} onwards)…")
        sources = book.sources_for(b, sec)
        topic = f"{sec.name} — from the book '{b.title}'"
        lesson, plan = planner.build(topic, minutes=minutes, sources=sources,
                                     source={"kind": "book", "path": str(p), "section": sec.name, "page": sec.label})
        return lesson, plan, 0
    say("Give me a few seconds, I'm planning your lesson.")
    lesson, plan = planner.build(target, minutes=minutes)
    return lesson, plan, 0


def teach(args: list[str]) -> dict:
    """One lesson process. The lock is taken FIRST (before any model loads or any sound), held for the whole life."""
    try:
        sys.stdout.reconfigure(line_buffering=True)        # logs show up live even when launched by the app
    except Exception:
        pass
    if not acquire_lesson():
        print("A lesson is already running; not starting a second one.")
        return {"finished": False}
    try:
        return _teach(args)
    finally:
        release_lesson()


def answerer(planner=None, lesson=None):
    """Every lesson can answer doubts with the cloud LLM when a free key exists — the built-in demo and resumed
    lessons too. 2026-11-11: the demo had planner=None, so every doubt got 'I can't answer that one properly
    without my cloud brain' although Groq was up."""
    if planner is not None:
        return planner
    try:
        from .. import router
        if not any(s["key"] for s in router.status()):
            return None
        from .planner import Planner
        return Planner(None)
    except Exception:
        return None


def _teach(args: list[str]) -> dict:
    from . import audio as au
    from .player import Tutor
    from .server import BoardServer
    target = next((a for i, a in enumerate(args) if not a.startswith("--")
                   and (i == 0 or args[i - 1] not in ("--chapter", "--minutes", "--hours", "--goal", "--focus"))), None)
    mode = "silent" if "--silent" in args else "type" if "--type" in args else "voice"
    board = "--no-board" not in args
    holder: dict = {}
    course = "--night" in args or "--resume-course" in args or "--revise" in args
    waiting = [{"type": "status", "mode": "playing", "text": "getting ready",
                "caption": f"Getting your lesson{' on ' + target if target and '/' not in target else ''} ready…"}]
    srv = BoardServer(on_connect=lambda: holder["t"].on_connect() if "t" in holder else waiting) if board else None
    events = srv.events if srv else queue.Queue()
    print("Stiti is getting ready… (voice, whiteboard)" if mode == "voice" else "Stiti is getting ready…")
    if course:
        audio = au.make(mode, events, debug="--debug" in args)
        return _course_session(args, target, audio, events, srv, stop_args=args)
    if _coach_target(target, args):
        return _coach_session(target, args, mode, srv, events, holder)
    # D42: the board opens FIRST and the lesson is planned WHILE her voice loads. Before, he said "teach me X" and
    # looked at nothing for ~19 s: voice models (13 s), then the plan (5 s), and only then the board — in a row.
    if srv:
        srv.start()
        print(f"\n🧑‍🏫  Whiteboard: {srv.url}\n    (opening it now — drag it to your big screen, press F for full screen)\n")
        if "--no-open" not in args:
            srv.open_browser()
    planned: dict = {}

    def plan():
        try:
            planned["ok"] = make_lesson(target, args)
        except BaseException as e:                  # SystemExit (friendly message) or LLM down / bad output
            planned["err"] = e
    pt = threading.Thread(target=plan, daemon=True, name="lesson-plan")
    pt.start()
    try:
        audio = au.make(mode, events, debug="--debug" in args)
    except BaseException:
        if srv:
            srv.stop()
        raise
    pt.join()
    if "err" in planned:
        audio.close()
        if srv:
            srv.stop()
        e = planned["err"]
        print(e if isinstance(e, SystemExit) else
              f"Couldn't plan that lesson right now ({type(e).__name__}: {str(e)[:160]}).\n"
              "Try again in a minute, or run the built-in lesson: uv run stiti teach")
        return {"finished": False}
    lesson, planner, start = planned["ok"]
    tutor = Tutor(lesson, audio=audio, events=events, server=srv, planner=answerer(planner, lesson), start=start)
    holder["t"] = tutor
    stop = threading.Event()
    if srv:
        srv.connected.wait(15)
        for m in tutor.on_connect():                # the page connected while we were loading: give it the board now
            srv.send(m)
    if mode != "voice" or sys.stdin.isatty():     # --silent / --type read typed lines (piped too); the app gives DEVNULL
        threading.Thread(target=_stdin_reader, args=(events, stop), daemon=True).start()
    print("Talk any time: wait / continue / repeat / go back / skip / slower / faster / end — or just ask.\n"
          if mode == "voice" else "Type answers or questions here or on the board. Commands: pause, continue, "
                                  "repeat, back, skip, slower, faster, end.\n")
    course_res = None
    try:
        result = tutor.run()
        while tutor.switch:                         # D52: he asked for another unit / an exam crash course
            sw = tutor.switch
            if sw["mode"] == "crash":
                course_res = _course_session(["--night", _switch_target(sw, target, lesson), "--goal", sw["request"][:120]],
                                             _switch_target(sw, target, lesson), audio, events, srv, close=False)
                break
            nxt = _switch_lesson(sw, target, lesson, args, srv)
            if nxt is None:
                break
            lesson, planner, start = nxt
            tutor = Tutor(lesson, audio=audio, events=events, server=srv, planner=answerer(planner, lesson), start=start)
            holder["t"] = tutor
            if srv:
                for m in tutor.on_connect():
                    srv.send(m)
            result = tutor.run()
    finally:
        stop.set()
        audio.close()
        if srv:
            srv.stop()
    if course_res is not None:
        return course_res
    right, graded = result["checks_right"], result["checks_graded"]
    print(f"\n✅ {'Finished' if result['finished'] else 'Stopped'} '{lesson.title}': checks {right}/{graded}, "
          f"{result['questions']} question(s), {result['cards_saved']} revision card(s) saved.")
    return result


def _coach_target(target: str | None, args: list[str]) -> bool:
    """D53: his file or a topic → the coach (goal + quick probes + mastery). `--classic` keeps the old lesson; the
    built-in demo, --resume and course modes stay as they were."""
    from . import lesson as L
    if not target or "--classic" in args or "--resume" in args or target in L.demos():
        return False
    from .. import router
    return any(s["key"] for s in router.status())


def _coach_session(target: str, args: list[str], mode: str, srv, events, holder: dict) -> dict:
    """One coached session on the same board and voice; 'switch to unit 3' / 'exam tomorrow' re-plan in place."""
    from . import audio as au
    from .coach import Coach
    p = Path(target).expanduser()
    book_path = str(p) if p.suffix.lower() in BOOK_EXTS and p.exists() else None
    unit = _arg(args, "--chapter")
    goal = None
    if srv:
        srv.start()
        print(f"\n🧑‍🏫  Whiteboard: {srv.url}\n    (opening it now — drag it to your big screen, press F for full screen)\n")
        if "--no-open" not in args:
            srv.open_browser()
    from concurrent.futures import ThreadPoolExecutor

    from .coach import concept_map, focus_split
    pool = ThreadPoolExecutor(1, thread_name_prefix="coach-map")
    # D42: her voice (~13 s) and reading his file run at the same time, after the board is already on screen
    fut = pool.submit(concept_map, book_path or target, book_path=book_path, unit=unit)
    try:
        audio = au.make(mode, events, debug="--debug" in args)
    except BaseException:
        if srv:
            srv.stop()
        raise
    stop = threading.Event()
    if mode != "voice" or sys.stdin.isatty():
        threading.Thread(target=_stdin_reader, args=(events, stop), daemon=True).start()
    print("Talk any time: wait / continue / repeat / go back / skip / slower / faster / end — or just ask.\n")
    res: dict = {"finished": False}
    try:
        for _ in range(4):                           # at most a few re-plans in one sitting
            coach = Coach(book_path or target, audio=audio, events=events, server=srv, book_path=book_path,
                          unit=unit, goal=goal, concepts_future=fut, focus=focus_split(_arg(args, "--focus")))
            fut = None                               # a re-plan (other unit) maps again
            holder["t"] = coach.t
            coach.t.ptt_mode = "--ptt" in args          # hold-to-talk from the start (noisy room)
            if srv:
                srv.connected.wait(15)
                for m in coach.t.on_connect():
                    srv.send(m)
            res = coach.run()
            sw = coach.t.switch
            if not sw:
                break
            if sw["mode"] == "crash":                # "exam tomorrow, cover everything": the whole file, exam mode
                unit, goal = None, {"mode": "exam", "days": 1}
            else:
                unit = sw.get("target") or unit
                goal = coach.goal
    finally:
        stop.set()
        audio.close()
        if srv:
            srv.stop()
    print(f"\n✅ {'Finished' if res.get('finished') else 'Stopped'}: checks {res.get('checks_right', 0)}/"
          f"{res.get('checks_graded', 0)}, {res.get('questions', 0)} question(s).")
    return res


def _switch_target(sw: dict, target: str | None, lesson) -> str:
    """His file when the lesson came from one (a crash course over the WHOLE notebook), else the topic he named."""
    src = getattr(lesson, "source", None) or {}
    if src.get("kind") == "book" and src.get("path"):
        return src["path"]
    return sw.get("target") or target or lesson.topic


def _switch_lesson(sw: dict, target: str | None, lesson, args: list[str], srv):
    """Plan the unit / topic he asked for, on the same board and voice. -> (lesson, planner, start) or None."""
    src = getattr(lesson, "source", None) or {}
    want = (sw.get("target") or "").strip()
    if not want:
        return None
    if srv:
        srv.send({"type": "status", "mode": "thinking", "text": "planning", "caption": f"Planning: {want}…"})
    book = src.get("path") if src.get("kind") == "book" else None
    try:
        return make_lesson(book, [book, "--chapter", want]) if book else make_lesson(want, [want])
    except BaseException as e:                     # not in the book / LLM down: say so on the board, end cleanly
        msg = str(e) if isinstance(e, SystemExit) else f"{type(e).__name__}: {str(e)[:120]}"
        print(f"Couldn't plan {want!r}: {msg}")
        if srv:
            srv.send({"type": "status", "mode": "offline", "text": "couldn't plan that",
                      "caption": f"I couldn't find {want} — ask me again with the unit name."})
        return None


def _open_board(srv, args) -> None:
    if srv and srv.server is not None:              # already open (a crash course he asked for mid-lesson, D52)
        srv.send({"type": "reset", "actions": []})
        return
    if srv:
        srv.start()
        print(f"\n🧑‍🏫  Whiteboard: {srv.url}\n    (opening it now — drag it to your big screen, press F for full screen)\n")
        if "--no-open" not in args:
            srv.open_browser()
        srv.connected.wait(15)


def _course_session(args: list[str], target: str | None, audio, events, srv, stop_args=None,
                    close: bool = True) -> dict:
    """`teach --night <book|subject> [--hours 3] [--goal …]` · `teach --resume-course` · `teach --revise`."""
    from . import course
    from .player import Tutor
    try:
        if "--revise" in args:
            lesson, cards = course.revise_lesson()
            if lesson is None:
                print("Nothing due for revision right now. 🎉")
                return {"finished": True}
            _open_board(srv, args)
            t = Tutor(lesson, audio=audio, events=events, server=srv, planner=answerer())
            res = t.run()
            from . import srs
            for r in res.get("results") or []:
                if r.get("segment", "").startswith("c"):
                    srs.review(int(r["segment"][1:]), srs.rating_for(r.get("verdict"), r.get("hints", 0),
                                                                        r.get("confidence")))
            print(f"\n✅ Revision: {res['checks_right']}/{res['checks_graded']} right. Next reviews scheduled.")
            return res
        if "--resume-course" in args:
            row = course.load()
            if not row:
                print("No unfinished crash course. Try: uv run stiti teach --night <book or subject>")
                return {"finished": False}
            cid = row["id"]
            print(f"Resuming '{row['title']}' at lesson {row['cursor'] + 1}.")
        else:
            if not target:
                print("usage: uv run stiti teach --night <book.pdf|.epub|.txt | \"a subject\"> [--hours 3] [--goal \"…\"]")
                return {"finished": False}
            hours = max(1.0, min(4.0, float(_arg(args, "--hours", "3"))))
            print(f"Planning a one-night crash course on {target!r} ({hours:g} h)…")
            cid = course.create(target, hours, _arg(args, "--goal"))
        plan = course.load(cid)["plan"]
        for k, x in enumerate(plan["lessons"]):
            print(f"   {k + 1:2}. {x['title']}" + (f"   (p.{x['unit']['label']}+)" if x.get("unit") else ""))
        _open_board(srv, args)
        res = course.Night(cid, audio=audio, events=events, server=srv).run()
        print(f"\n✅ {'Finished' if res['finished'] else 'Paused'} the course: {res['lessons_done']}/{res['lessons']} "
              f"lessons." + ("" if res["finished"] else " Resume: uv run stiti teach --resume-course"))
        return res
    except Exception as e:
        print(f"Couldn't run the crash course ({type(e).__name__}: {str(e)[:200]}).")
        return {"finished": False}
    finally:
        if close:                                   # mid-lesson switch: the caller owns the voice and the board
            audio.close()
            if srv:
                srv.stop()


TEACH_RX = __import__("re").compile(
    r"^(?:(?:hey |hi )?stiti,? )?(?:can you |please |pls )?(?:teach me|tutor me|padhao|padha do|sikhao|sikha do|"
    r"mujhe .+ (?:padhao|sikhao|samjhao)|.+ (?:padhao|sikhao|padha do|sikha do)|"
    r"(?:explain|samjhao) .+ (?:on|pe) (?:the )?(?:white ?board|board)|(?:start|open) (?:the )?(?:white ?board|tutor))",
    __import__("re").I)
RESUME_RX = __import__("re").compile(r"\b(continue|resume) (my |the )?(lesson|class|tutor)|lesson (continue|resume) karo",
                                     __import__("re").I)


NIGHT_RX = __import__("re").compile(
    r"\b(tonight|in one night|one night|overnight|crash ?course|ek raat (me|mein|mai)|aaj raat (me|mein|mai|tak)|"
    r"raat bhar (me|mein)?|in (\d|two|three|four) hours?|cram)\b", __import__("re").I)
REVISE_RX = __import__("re").compile(r"\b(revise|revision|revise karna|revision karna|revise karao|flashcards?)\b",
                                     __import__("re").I)
COURSE_RESUME_RX = __import__("re").compile(r"\b(continue|resume) (my |the )?(crash ?course|course|night)\b|"
                                            r"course (continue|resume) karo", __import__("re").I)
# a revision SESSION: "let's revise", "revision time", "revise karna hai", "start my revision", "flashcards"
REVISE_START_RX = __import__("re").compile(
    r"^(?:(?:hey |hi )?stiti,? )?(?:let'?s |start (?:my |the )?|time (?:to|for) |can we |chalo )?(?:revise|revision)"
    r"(?: (?:time|karna( hai)?|karao|karte hain|session|now|please))?$|\brevision (?:time|karna|karao|session)\b|"
    r"\brevise karna hai\b|\b(?:my |the )?flashcards?\b", __import__("re").I)
# to-dos, reminders and alarms are never lessons, even when they say "revise" / "study" / "teach"
NOT_A_LESSON_RX = __import__("re").compile(
    r"\b(add|put|daal|note (it )?down)\b.*\b(to-?do|todos?|tasks?|list)\b|\b(remind me|reminder|alarm)\b",
    __import__("re").I)
BOOK_DIRS = ("~/Downloads", "~/Documents", "~/Desktop", "~/Books")


def find_book(name: str) -> str | None:
    """'the Aho compilers book' → ~/Downloads/Aho - Compilers - ….pdf (filename word overlap, local folders only)."""
    import re
    if re.fullmatch(r"(this|that|the|my|new|latest)( new| latest)? (book|pdf|file|ebook|notes)", name.strip().lower()):
        files = [f for d in BOOK_DIRS if Path(d).expanduser().is_dir() for f in Path(d).expanduser().iterdir()
                 if f.is_file() and f.suffix.lower() in BOOK_EXTS and f.stat().st_size > 50_000]
        return str(max(files, key=lambda f: f.stat().st_mtime)) if files else None   # the one he just downloaded
    words = {w for w in re.findall(r"[a-z0-9]{3,}", name.lower()) if w not in {"the", "book", "pdf", "from", "this",
                                                                                 "wala", "vali", "wali", "tonight"}}
    if not words:
        return None
    best, score = None, 0.0
    for d in BOOK_DIRS:
        root = Path(d).expanduser()
        if not root.is_dir():
            continue
        for f in root.iterdir():
            if f.suffix.lower() in BOOK_EXTS and f.is_file():
                fw = set(re.findall(r"[a-z0-9]{3,}", f.stem.lower()))
                s = len(words & fw) / len(words)
                if s > score:
                    best, score = str(f), s
    return best if score >= 0.6 else None


def voice_request(text: str) -> tuple | None:
    """'teach me how DNS works' -> ('how DNS works', False); 'continue my lesson' -> (None, True);
    'teach me operating systems tonight' -> ('operating systems', False, 'night'); 'revise karna hai' -> revise."""
    import re
    t = text.strip().rstrip(".!?")
    if NOT_A_LESSON_RX.search(t):
        return None          # "add revise DBMS notes to my to-do list" is a to-do, not a revision session (2026-11-11)
    if COURSE_RESUME_RX.search(t):
        return None, True, "night"
    if REVISE_START_RX.search(t):
        return None, False, "revise"
    if RESUME_RX.search(t):
        return None, True
    if (m := re.search(r"\bcrash ?course (?:on|of|for|from) (.+)", t, re.I)):
        return m.group(1).strip(" ,.") or None, False, "night"
    if not TEACH_RX.search(t):
        return board_request(text)
    topic = re.sub(r"^(?:(?:hey |hi )?stiti,? )?(?:can you |please |pls )?", "", t, flags=re.I)
    topic = re.sub(r"^(teach me|tutor me)( about)?|^mujhe|(padhao|padha do|sikhao|sikha do|samjhao)$|"
                   r"(on|pe) (the )?(white ?board|board)$|^(explain|samjhao)( me| us)?( about)?|"
                   r"^(start|open) (the )?(white ?board|tutor)", "", topic, flags=re.I).strip(" ,.")
    topic = BOARD_TAIL_RX.sub("", topic).strip(" ,.")     # "teach me X using whiteboard" → X
    if _NOT_TOPIC.match(topic):
        topic = ""                                        # "explain it on the whiteboard" → ask / use context
    if NIGHT_RX.search(t):
        topic = NIGHT_RX.sub("", topic or "").strip(" ,.")
        topic = re.sub(r"\b(in|me|mein|mai|tak|a|the)$", "", topic, flags=re.I).strip(" ,.")
        return (topic or None), False, "night"
    return (topic or None), False


ASK_TOPIC = "Sure! What should I teach you?"

# 2026-11-11: none of his real asks matched TEACH_RX (it only knew sentence STARTS like "teach me …"):
#   "So, I want you to explain me lexical analysis using a whiteboard." · "open the whiteboard and explain me X"
#   "No, you have the access to open whiteboard." · "I ask you open whiteboard. That's it."
# so the LLM answered instead and claimed "Opened the whiteboard app" three times. Now ANY sentence that names the
# whiteboard and asks for it (open / explain / teach / show / use …), anywhere in the line, is a lesson request.
_BOARD = r"(?:white ?-?board|black ?board)"
BOARD_RX = re.compile(rf"\b{_BOARD}\b|\bboard (?:pe|par|mein)\b|\b(?:on|using) (?:the |a )?board\b", re.I)
BOARD_ASK_RX = re.compile(r"\b(?:open|start|launch|use|using|bring|show|draw|explain|teach|tutor|on|pe|par|kholo|"
                          r"khol do|samjhao|samjha do|padhao|sikhao|access)\b", re.I)
BOARD_NO_RX = re.compile(rf"\b(?:close|don'?t|do not|dont|no need (?:for|of)?|without|stop|bina)\b(?:\W+\w+){{0,3}}?"
                         rf"\W+(?:the |a |that )?(?:{_BOARD}|board)\b|\b{_BOARD}\b.{{0,20}}\b(?:band karo|mat kholo|"
                         rf"close karo|nahi chahiye)\b", re.I)
BOARD_TAIL_RX = re.compile(rf"\s*\b(?:using|on|with|in|via|through|pe|par|mein)\s+(?:the |a |my )?(?:{_BOARD}|board)\b.*$",
                           re.I)
TOPIC_RX = re.compile(r"\b(?:explain|teach|tutor|show|draw|walk me through|tell me about)\s+(?:me\s+|us\s+)?"
                      r"(?:about\s+|on\s+)?(?P<a>.+)$|"
                      r"^(?P<b>.+?)\s+(?:samjhao|samjha do|padhao|padha do|sikhao|sikha do)\b", re.I)
_NOT_TOPIC = re.compile(r"^(?:it|this|that|them|me|everything|something|anything|now|please|again|there|here|"
                        r"properly|to me|that'?s it|the whiteboard|whiteboard|board|it to me|that again)$", re.I)


def _topic_in(sentence: str) -> str | None:
    """'open the whiteboard and explain me lexical analysis' / 'explain me X using a whiteboard' → 'lexical analysis'."""
    s = re.sub(rf"^.*?\b(?:open|start|launch|use|bring up|kholo)\s+(?:the |a |my |that )?(?:{_BOARD}|board)\s*"
               r"(?:and|aur|then|,)?\s*", "", sentence, flags=re.I)
    s = BOARD_TAIL_RX.sub("", s).strip(" ,.?!")
    s = re.sub(rf"^(?:{_BOARD}|board)\s+(?:pe|par|mein|on)\s+", "", s, flags=re.I)   # "whiteboard pe X samjhao"
    m = TOPIC_RX.search(s)
    if not m:
        return None
    topic = (m.group("a") or m.group("b") or "").strip(" ,.?!")
    topic = re.sub(r"^(?:so|okay|ok|then|bro|please|also|now|the concept of)\s+", "", topic, flags=re.I)
    topic = re.sub(r"\s+(?:please|pls|now|to me|properly|again|yaar|bro)$", "", topic, flags=re.I).strip(" ,.?!")
    return None if not topic or _NOT_TOPIC.match(topic) or len(topic.split()) > 8 else topic


_PERSONAL_RX = re.compile(r"\b(?:my|your|our)\s+\w+|\b(?:reminders?|alarms?|to-?dos?|tasks?|calendar|e?mails?|schedule|"
                          r"weather|news|time is it)\b", re.I)


def topic_hint(text: str) -> str | None:
    """What he asked her to explain, even without the whiteboard ('explain me lexical analysis', 'what is a lexer?'):
    remembered for a few minutes so a bare 'open the whiteboard' that follows teaches THAT."""
    if NOT_A_LESSON_RX.search(text) or _PERSONAL_RX.search(text):
        return None
    for x in reversed([x for x in re.split(r"(?<=[.?!])\s+", text) if x.strip()]):
        if (topic := _topic_in(x)):
            return topic
        m = re.search(r"\bwhat (?:is|are|does) (?:a |an |the )?(.{3,60}?)(?: mean)?\s*[?.!]*$", x, re.I)
        if m and len(m.group(1).split()) <= 5 and not _NOT_TOPIC.match(m.group(1).strip()):
            return m.group(1).strip(" ,.?!")
    return None


def board_request(text: str) -> tuple | None:
    """A line that asks for the whiteboard → (topic or None, False); None if it doesn't, or says NOT to open it."""
    sentences = [x for x in re.split(r"(?<=[.?!])\s+|\bi mean\b", text, flags=re.I) if x.strip()]
    asks = [x for x in sentences if BOARD_RX.search(x) and BOARD_ASK_RX.search(x)]
    if not asks or BOARD_NO_RX.search(asks[-1]):      # the LAST thing he said about the board wins ("… I mean open it")
        return None
    for x in [asks[-1], *reversed(sentences)]:        # the topic may sit in another sentence of the same line
        if (topic := _topic_in(x)):
            return topic, False
    return None, False


def _spawn(args: list[str]) -> None:
    """Start the lesson process and take the lock NOW (its pid), not seconds later when the lesson has loaded:
    2026-11-11 a request said in three breaths ("can you teach me… lexical analysis… using whiteboard?") started
    three lessons that talked over each other and heard each other as the learner."""
    import subprocess
    (CFG.home / "logs").mkdir(parents=True, exist_ok=True)     # a fresh install has no logs/ yet (CI caught it)
    log = open(CFG.home / "logs" / "tutor.log", "a")
    p = subprocess.Popen([sys.executable, "-m", "stiti", "teach", *args], stdout=log, stderr=log,
                         stdin=subprocess.DEVNULL, start_new_session=True)
    LOCK.write_text(str(p.pid))


def launch(topic: str | None, resume: bool = False, mode: str | None = None) -> str:
    """Start a lesson / crash course / revision as its own process (voice + board), from the always-on assistant.
    Serialised: two requests in the same second (two threads) can't both pass the check and spawn."""
    with _launch_lock:
        return _launch(topic, resume, mode)


def _launch(topic: str | None, resume: bool, mode: str | None) -> str:
    if tutor_active():
        return "Your lesson's already open on the whiteboard."
    if not topic and not resume and mode is None:
        return ASK_TOPIC                        # "can you teach me?" alone: ask, don't start a random lesson
    if mode in ("night", "revise"):
        if mode == "revise":
            args, msg = ["--revise"], "Revision time! Opening the board."
        elif resume:
            args, msg = ["--resume-course"], "Opening your crash course where we stopped."
        elif not topic:
            return "Sure! Which book or subject? Say: teach me operating systems tonight."
        else:
            book = find_book(topic)
            args = ["--night", book or topic]
            msg = (f"Crash course from {Path(book).stem[:40]}! Give me a minute to plan the night."
                   if book else f"Crash course on {topic} tonight! Give me a minute to plan it.")
        _spawn(args)
        return msg
    from .lesson import demos
    args = ["--resume"] if resume else ([topic] if topic else [])
    book = find_book(topic) if topic and not resume and topic not in demos() else None
    if book:                                        # "teach me the compiler notebook" → HIS file, not the topic (D53)
        args = [book]
    if topic and topic not in demos() and not book:
        from .. import router
        if not any(s["key"] for s in router.status()):
            if "compil" in topic.lower():
                args = ["compiler"]
            else:
                return "Right now I can only teach my compilers lesson. Say: teach me compilers."
    _spawn(args)
    if book:
        return f"Opening the whiteboard with {Path(book).stem[:40]}. First, a couple of quick questions."
    return "Opening the whiteboard. Give me a few seconds." if not resume else "Opening your lesson where we stopped."


def book_cmd(args: list[str]) -> None:
    from . import book
    if len(args) < 2:
        print("usage: stiti book <file.pdf|.epub|.md> [--level 2]")
        return
    b = book.load(args[1])
    print(book.outline_text(b, int(_arg(args, "--level", "2"))))
