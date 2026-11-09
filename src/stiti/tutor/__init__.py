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
BOOK_EXTS = {".pdf", ".epub", ".md", ".txt", ".docx", ".html"}


def tutor_active() -> bool:
    """True while a lesson runs (Stiti's always-on voice loop stays out of the way)."""
    try:
        pid = int(LOCK.read_text().strip())
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
                   and (i == 0 or args[i - 1] not in ("--chapter", "--minutes"))), None)
    mode = "silent" if "--silent" in args else "type" if "--type" in args else "voice"
    board = "--no-board" not in args
    holder: dict = {}
    srv = BoardServer(on_connect=lambda: holder["t"].on_connect() if "t" in holder else []) if board else None
    events = srv.events if srv else queue.Queue()
    print("Stiti is getting ready… (voice, whiteboard)" if mode == "voice" else "Stiti is getting ready…")
    audio = au.make(mode, events, debug="--debug" in args)
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


TEACH_RX = __import__("re").compile(
    r"^(?:(?:hey |hi )?stiti,? )?(?:can you |please |pls )?(?:teach me|tutor me|padhao|padha do|sikhao|sikha do|"
    r"mujhe .+ (?:padhao|sikhao|samjhao)|.+ (?:padhao|sikhao|padha do|sikha do)|"
    r"(?:explain|samjhao) .+ (?:on|pe) (?:the )?(?:white ?board|board)|(?:start|open) (?:the )?(?:white ?board|tutor))",
    __import__("re").I)
RESUME_RX = __import__("re").compile(r"\b(continue|resume) (my |the )?(lesson|class|tutor)|lesson (continue|resume) karo",
                                     __import__("re").I)


def voice_request(text: str) -> tuple[str | None, bool] | None:
    """'teach me how DNS works' -> ('how DNS works', False); 'continue my lesson' -> (None, True)."""
    import re
    t = text.strip().rstrip(".!?")
    if RESUME_RX.search(t):
        return None, True
    if not TEACH_RX.search(t):
        return None
    topic = re.sub(r"^(?:(?:hey |hi )?stiti,? )?(?:can you |please |pls )?", "", t, flags=re.I)
    topic = re.sub(r"^(teach me|tutor me)( about)?|^mujhe|(padhao|padha do|sikhao|sikha do|samjhao)$|"
                   r"(on|pe) (the )?(white ?board|board)$|^(explain|samjhao)|^(start|open) (the )?(white ?board|tutor)",
                   "", topic, flags=re.I).strip(" ,.")
    return (topic or None), False


def launch(topic: str | None, resume: bool = False) -> str:
    """Start a lesson as its own process (voice + board), from the always-on assistant."""
    import subprocess
    if tutor_active():
        return "A lesson is already running on the whiteboard."
    from .lesson import demos
    args = ["--resume"] if resume else ([topic] if topic else [])
    if topic and topic not in demos():
        from .. import router
        if not any(s["key"] for s in router.status()):
            if "compil" in topic.lower():
                args = ["compiler"]
            else:
                return ("I can only teach my built-in lesson until I have a free LLM key. Add GROQ_API_KEY to .env, "
                        "or say: teach me compilers.")
    log = open(CFG.home / "logs" / "tutor.log", "a")
    subprocess.Popen([sys.executable, "-m", "stiti", "teach", *args], stdout=log, stderr=log,
                     stdin=subprocess.DEVNULL, start_new_session=True)
    return "Opening the whiteboard. Give me a few seconds." if not resume else "Opening your lesson where we stopped."


def book_cmd(args: list[str]) -> None:
    from . import book
    if len(args) < 2:
        print("usage: stiti book <file.pdf|.epub|.md> [--level 2]")
        return
    b = book.load(args[1])
    print(book.outline_text(b, int(_arg(args, "--level", "2"))))
