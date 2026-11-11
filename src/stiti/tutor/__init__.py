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
import queue
import sys
import threading
from pathlib import Path

from ..config import CFG

LOCK = CFG.home / "tutor.lock"
BOOK_EXTS = {".pdf", ".epub", ".md", ".txt", ".docx", ".html", ".htm", ".pptx", ".rtf"}


def tutor_active() -> bool:
    """True while a lesson runs (Stiti's always-on voice loop stays out of the way)."""
    try:
        pid = int(LOCK.read_text().strip())
        os.kill(pid, 0)
        return True
    except (FileNotFoundError, ValueError, ProcessLookupError, PermissionError):
        return False


def _other_lesson() -> bool:
    """Another live lesson holds the lock (launch() writes OUR pid before we start, so that one is us)."""
    try:
        pid = int(LOCK.read_text().strip())
        if pid == os.getpid():
            return False
        os.kill(pid, 0)
        return True
    except (FileNotFoundError, ValueError, ProcessLookupError, PermissionError):
        return False


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
    try:
        sys.stdout.reconfigure(line_buffering=True)        # logs show up live even when launched by the app
    except Exception:
        pass
    from . import audio as au
    from .player import Tutor
    from .server import BoardServer
    target = next((a for i, a in enumerate(args) if not a.startswith("--")
                   and (i == 0 or args[i - 1] not in ("--chapter", "--minutes", "--hours", "--goal"))), None)
    mode = "silent" if "--silent" in args else "type" if "--type" in args else "voice"
    board = "--no-board" not in args
    holder: dict = {}
    srv = BoardServer(on_connect=lambda: holder["t"].on_connect() if "t" in holder else []) if board else None
    events = srv.events if srv else queue.Queue()
    if _other_lesson():
        print("A lesson is already running; not starting a second one.")
        return {"finished": False}
    print("Stiti is getting ready… (voice, whiteboard)" if mode == "voice" else "Stiti is getting ready…")
    audio = au.make(mode, events, debug="--debug" in args)
    if "--night" in args or "--resume-course" in args or "--revise" in args:
        return _course_session(args, target, audio, events, srv, stop_args=args)
    try:
        lesson, planner, start = make_lesson(target, args)
    except SystemExit as e:
        audio.close()
        print(e)
        return {"finished": False}
    except Exception as e:                          # LLM down / rate limited / bad output
        audio.close()
        print(f"Couldn't plan that lesson right now ({type(e).__name__}: {str(e)[:160]}).\n"
              "Try again in a minute, or run the built-in lesson: uv run stiti teach")
        return {"finished": False}
    tutor = Tutor(lesson, audio=audio, events=events, server=srv, planner=planner, start=start)
    holder["t"] = tutor
    stop = threading.Event()
    if srv:
        srv.start()
        print(f"\n🧑‍🏫  Whiteboard: {srv.url}\n    (opening it now — drag it to your big screen, press F for full screen)\n")
        if "--no-open" not in args:
            srv.open_browser()
        srv.connected.wait(15)
    if mode != "silent" and sys.stdin.isatty():
        threading.Thread(target=_stdin_reader, args=(events, stop), daemon=True).start()
    print("Talk any time: ruko / continue / phir se / peeche / skip / dheere / tez / bas karo — or just ask.\n"
          if mode == "voice" else "Type answers or questions here or on the board. Commands: pause, continue, "
                                  "repeat, back, skip, slower, faster, end.\n")
    LOCK.write_text(str(os.getpid()))
    try:
        result = tutor.run()
    finally:
        stop.set()
        LOCK.unlink(missing_ok=True)
        audio.close()
        if srv:
            srv.stop()
    right, graded = result["checks_right"], result["checks_graded"]
    print(f"\n✅ {'Finished' if result['finished'] else 'Stopped'} '{lesson.title}': checks {right}/{graded}, "
          f"{result['questions']} question(s), {result['cards_saved']} revision card(s) saved.")
    return result


def _open_board(srv, args) -> None:
    if srv:
        srv.start()
        print(f"\n🧑‍🏫  Whiteboard: {srv.url}\n    (opening it now — drag it to your big screen, press F for full screen)\n")
        if "--no-open" not in args:
            srv.open_browser()
        srv.connected.wait(15)


def _course_session(args: list[str], target: str | None, audio, events, srv, stop_args=None) -> dict:
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
            LOCK.write_text(str(os.getpid()))
            t = Tutor(lesson, audio=audio, events=events, server=srv)
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
        LOCK.write_text(str(os.getpid()))
        res = course.Night(cid, audio=audio, events=events, server=srv).run()
        print(f"\n✅ {'Finished' if res['finished'] else 'Paused'} the course: {res['lessons_done']}/{res['lessons']} "
              f"lessons." + ("" if res["finished"] else " Resume: uv run stiti teach --resume-course"))
        return res
    except Exception as e:
        print(f"Couldn't run the crash course ({type(e).__name__}: {str(e)[:200]}).")
        return {"finished": False}
    finally:
        LOCK.unlink(missing_ok=True)
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
    if COURSE_RESUME_RX.search(t):
        return None, True, "night"
    if REVISE_RX.search(t) and re.search(r"\b(stiti|karna|karao|let'?s|start|my|time)\b", t, re.I):
        return None, False, "revise"
    if RESUME_RX.search(t):
        return None, True
    if (m := re.search(r"\bcrash ?course (?:on|of|for|from) (.+)", t, re.I)):
        return m.group(1).strip(" ,.") or None, False, "night"
    if not TEACH_RX.search(t):
        return None
    topic = re.sub(r"^(?:(?:hey |hi )?stiti,? )?(?:can you |please |pls )?", "", t, flags=re.I)
    topic = re.sub(r"^(teach me|tutor me)( about)?|^mujhe|(padhao|padha do|sikhao|sikha do|samjhao)$|"
                   r"(on|pe) (the )?(white ?board|board)$|^(explain|samjhao)|^(start|open) (the )?(white ?board|tutor)",
                   "", topic, flags=re.I).strip(" ,.")
    if NIGHT_RX.search(t):
        topic = NIGHT_RX.sub("", topic or "").strip(" ,.")
        topic = re.sub(r"\b(in|me|mein|mai|tak|a|the)$", "", topic, flags=re.I).strip(" ,.")
        return (topic or None), False, "night"
    return (topic or None), False


ASK_TOPIC = "Sure! What should I teach you?"


def _spawn(args: list[str]) -> None:
    """Start the lesson process and take the lock NOW (its pid), not seconds later when the lesson has loaded:
    2026-11-11 a request said in three breaths ("can you teach me… lexical analysis… using whiteboard?") started
    three lessons that talked over each other and heard each other as the learner."""
    import subprocess
    log = open(CFG.home / "logs" / "tutor.log", "a")
    p = subprocess.Popen([sys.executable, "-m", "stiti", "teach", *args], stdout=log, stderr=log,
                         stdin=subprocess.DEVNULL, start_new_session=True)
    LOCK.write_text(str(p.pid))


def launch(topic: str | None, resume: bool = False, mode: str | None = None) -> str:
    """Start a lesson / crash course / revision as its own process (voice + board), from the always-on assistant."""
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
    if topic and topic not in demos():
        from .. import router
        if not any(s["key"] for s in router.status()):
            if "compil" in topic.lower():
                args = ["compiler"]
            else:
                return "Right now I can only teach my compilers lesson. Say: teach me compilers."
    _spawn(args)
    return "Opening the whiteboard. Give me a few seconds." if not resume else "Opening your lesson where we stopped."


def book_cmd(args: list[str]) -> None:
    from . import book
    if len(args) < 2:
        print("usage: stiti book <file.pdf|.epub|.md> [--level 2]")
        return
    b = book.load(args[1])
    print(book.outline_text(b, int(_arg(args, "--level", "2"))))
