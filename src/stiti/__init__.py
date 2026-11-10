"""Stiti — Tejmul's local-first buddy. The brain is the memory engine; the LLM is a plug."""
import os
import sys
import threading
import time
import warnings

warnings.filterwarnings("ignore")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")


def _scheduler(stop: threading.Event):
    from .fastpath.handlers import fire_due
    while not stop.is_set():
        try:
            fire_due(notify=lambda m: print(f"\n{m}\n> ", end="", flush=True))
        except Exception as e:  # never kill the chat over an alarm glitch
            print(f"\n[scheduler] {e}")
        stop.wait(5)


def chat(debug: bool = False, first: str | None = None):
    from .engine import Engine
    print("Stiti is waking up… (loading memory + embedder)")
    from . import embed, intent
    embed.embed_query("warm up")
    intent._index()
    eng = Engine("text")
    stop = threading.Event()
    threading.Thread(target=_scheduler, args=(stop,), daemon=True).start()
    print(f"Stiti: {eng.greet()} (type 'exit' to quit, '/debug' to toggle details)\n")
    pending_first = first
    try:
        while True:
            try:
                text, pending_first = (pending_first, None) if pending_first else (input("> ").strip(), None)
            except EOFError:
                break
            if not text:
                continue
            if text in ("exit", "quit", "/q"):
                break
            if text == "/debug":
                debug = not debug
                print(f"debug {'on' if debug else 'off'}")
                continue
            try:
                reply = eng.turn(text)
            except Exception as e:  # one bad turn must never kill Stiti
                import traceback
                traceback.print_exc() if debug else None
                reply = f"Oops, something broke on my side ({type(e).__name__}). Try again?"
            print(f"Stiti: {reply}")
            if debug:
                print(f"   ↳ {eng.last_debug}")
            if eng.ended:
                return
    finally:
        stop.set()
        if not eng.ended:
            print("Stiti: Theek hai, baad mein baat karte hain. 👋")


def voice(aec: bool = True, debug: bool = False):
    from . import embed, intent
    from .engine import Engine
    from .voice import stt
    from .voice.loop import VoiceLoop
    print("Stiti is waking up… (loading memory, embedder, whisper, voice)")
    embed.embed_query("warm up")
    intent._index()
    import numpy as np
    stt.transcribe_wake(np.zeros(16000, dtype=np.float32))   # load wake model
    stt.transcribe(np.zeros(16000, dtype=np.float32))        # load main model
    if os.getenv("STITI_VOICE_EMOTION", "off") != "off":
        from .voice import emotion_model
        emotion_model.preload_async()                         # background; prosody covers until ready
    stop = threading.Event()
    threading.Thread(target=_scheduler, args=(stop,), daemon=True).start()
    try:
        VoiceLoop(Engine("voice"), aec=aec, debug=debug).run()
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        print("\nStiti: Bye! 👋")


def doctor():
    import json as _json
    from datetime import datetime as _dt

    from . import embed, router
    from .config import CFG
    from .db import one
    ok = lambda b: "✅" if b else "❌"  # noqa: E731
    hp = CFG.home / "health.json"
    if hp.exists():
        h = _json.loads(hp.read_text())
        age = (_dt.now().astimezone() - _dt.fromisoformat(h["ts"])).total_seconds()
        fresh = age < 180
        print(f"{ok(fresh and h.get('db') == 'ok' and h.get('voice') == 'listening')} Stiti.app: "
              f"{'running' if fresh else f'no heartbeat for {int(age // 60)} min'} · db {h.get('db')} · voice {h.get('voice')}"
              f"{' · silenced' if h.get('silenced') else ''}")
    else:
        print("➖ Stiti.app: not installed or never ran (uv run stiti install-app)")
    bk = sorted((CFG.home / "backups").glob("stiti-*.enc")) if (CFG.home / "backups").exists() else []
    print(f"{ok(bool(bk))} Backups: {len(bk)} kept" + (f", newest {bk[-1].name}" if bk else " — run `uv run stiti backup`"))
    try:
        n = one("SELECT count(*) n FROM episodes")["n"]
        print(f"{ok(True)} Postgres: connected, {n} episodes stored")
    except Exception as e:
        print(f"{ok(False)} Postgres: {e}")
    t = time.perf_counter()
    embed.embed_query("hello")
    print(f"{ok(True)} Embedder: {embed.EMBED_MODEL} ({(time.perf_counter() - t) * 1000:.0f} ms incl. load)")
    for s in router.status():
        scope = "personal + public" if s["personal"] else "public questions only"
        print(f"{ok(s['key'])} {s['provider']:10} API key {'set' if s['key'] else 'missing'}  ({scope})")
    if any(s["key"] for s in router.status()):
        try:
            r = router.complete([{"role": "user", "content": "Reply with just: ok"}], max_tokens=20)
            print(f"{ok(True)} LLM: {r['provider']}/{r['model']} answered in {r['ms']:.0f} ms → {r['text']!r}")
        except Exception as e:
            print(f"{ok(False)} LLM: {e}")


def main() -> None:
    args = sys.argv[1:]
    cmd = args[0] if args else "chat"
    if cmd == "chat":
        chat(debug="--debug" in args)
    elif cmd == "onboard":
        chat(first="intro shuru karo")
    elif cmd == "voice":
        voice(aec="--no-aec" not in args, debug="--debug" in args)
    elif cmd == "backup":
        from .brain import backup
        if "--show-key" in args:
            print(f"Backup key (save it in a password manager; without it backups can't be opened):\n{backup.key()}")
        else:
            backup.backup(verbose=True)
    elif cmd == "restore":
        from .brain import backup
        if len(args) < 2:
            print("usage: stiti restore <backup.tar.gz.enc> [--into <new_db_name>]")
        else:
            into = args[args.index("--into") + 1] if "--into" in args else "stiti_restored"
            print(backup.restore(args[1], into))
    elif cmd == "app":
        from .app import run
        run()
    elif cmd == "install-app":
        from .install_app import install
        print(install(start_now="--no-start" not in args))
    elif cmd == "uninstall-app":
        from .install_app import uninstall
        print(uninstall())
    elif cmd == "mcp":
        from .tools import mcp_bus
        if len(args) >= 3 and args[1] == "approve":
            mcp_bus.start(approve=args[2])
        print(mcp_bus.status() or "No MCP servers configured (~/.stiti/mcp.json).")
    elif cmd == "ingest":
        from .brain.ingest import ingest
        if len(args) < 2:
            print("usage: stiti ingest <file-or-folder> [--private]")
        else:
            print(ingest(args[1], privacy=2 if "--private" in args else None))
    elif cmd == "mood":
        from .brain.moodview import render as render_mood
        print(f"Mood timeline → {render_mood(open_browser='--no-open' not in args)}")
    elif cmd == "graph":
        from .brain.graphview import render
        print(f"Life graph → {render(open_browser='--no-open' not in args)}")
    elif cmd == "web":
        from .web.server import run as run_web
        run_web(open_browser="--no-open" not in args)
    elif cmd == "teach":
        from .tutor import teach
        teach(args[1:])
    elif cmd == "book":
        from .tutor import book_cmd
        book_cmd(args)
    elif cmd == "doctor":
        doctor()
    elif cmd == "sleep":
        from .brain.sleep import run
        run(verbose=True)
    else:
        print("usage: stiti [chat [--debug] | onboard | voice [--no-aec] [--debug] | backup [--show-key] | restore <file> [--into db] | ingest <path> | graph | mood | app | install-app | uninstall-app | mcp [approve <name>] | doctor | sleep --now | teach [topic|book.pdf --chapter N|--resume] [--type|--silent|--no-board] | book <file> | web [--no-open]]")
