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


def chat(debug: bool = False):
    from .engine import Engine
    print("Stiti is waking up… (loading memory + embedder)")
    from . import embed, intent
    embed.embed_query("warm up")
    intent._index()
    eng = Engine("text")
    stop = threading.Event()
    threading.Thread(target=_scheduler, args=(stop,), daemon=True).start()
    print("Stiti: Haan, bolo! (type 'exit' to quit, '/debug' to toggle details)\n")
    try:
        while True:
            try:
                text = input("> ").strip()
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
    finally:
        stop.set()
        print("Stiti: Theek hai, baad mein baat karte hain. 👋")


def voice(headphones: bool = False, debug: bool = False):
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
    stop = threading.Event()
    threading.Thread(target=_scheduler, args=(stop,), daemon=True).start()
    try:
        VoiceLoop(Engine("voice"), headphones=headphones, debug=debug).run()
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        print("\nStiti: Bye! 👋")


def doctor():
    from . import embed, router
    from .db import one
    ok = lambda b: "✅" if b else "❌"  # noqa: E731
    try:
        n = one("SELECT count(*) n FROM episodes")["n"]
        print(f"{ok(True)} Postgres: connected, {n} episodes stored")
    except Exception as e:
        print(f"{ok(False)} Postgres: {e}")
    t = time.perf_counter()
    embed.embed_query("hello")
    print(f"{ok(True)} Embedder: {embed.EMBED_MODEL} ({(time.perf_counter() - t) * 1000:.0f} ms incl. load)")
    for s in router.status():
        print(f"{ok(s['key'])} {s['provider']:10} API key {'set' if s['key'] else 'missing'}")
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
    elif cmd == "voice":
        voice(headphones="--headphones" in args, debug="--debug" in args)
    elif cmd == "doctor":
        doctor()
    elif cmd == "sleep":
        from .brain.sleep import run
        run(verbose=True)
    else:
        print("usage: stiti [chat [--debug] | voice [--headphones] [--debug] | doctor | sleep --now]")
