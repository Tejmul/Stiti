"""`stiti web` — Stiti's local web app (landing, chat, memory), served from this Mac only.

The UI is a Next.js static export in frontend/out (D23); this server adds the API + WebSocket.

Same safety model as the tutor board (D14 §4): bound to 127.0.0.1, Host header checked on every request
(DNS rebinding), Origin + per-install token checked on the WebSocket and API (cross-site hijacking).
The token is created once (~/.stiti/web_token), handed to the browser in the URL fragment, and kept in
localStorage. Chat goes through the normal Engine, so the web chat is the same Stiti — same memory,
same fast paths, same lessons — as voice and terminal.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import secrets
import threading
from datetime import datetime
from pathlib import Path

from ..config import CFG, REPO

OUT = REPO / "frontend" / "out"          # Next.js static export (`cd frontend && pnpm build`)
ICONS = REPO / "public" / "actions"
PORT = int(os.getenv("STITI_WEB_PORT", "7317"))


def web_token() -> str:
    p = CFG.home / "web_token"
    if not p.exists():
        p.write_text(secrets.token_urlsafe(24))
        p.chmod(0o600)
    return p.read_text().strip()


def _state() -> dict:
    """Open todos + upcoming alarms/reminders, for the chat side panel."""
    from ..db import q
    todos = q("""SELECT id, title, due FROM tasks WHERE status='open' AND parent_id IS NULL
                 ORDER BY due NULLS LAST, created_at DESC LIMIT 12""")
    alarms = q("""SELECT id, kind, fire_at, COALESCE(payload->>'say', payload->>'text') AS text FROM intents
                  WHERE state IN ('pending','armed') AND kind IN ('alarm','reminder') AND fire_at IS NOT NULL
                  ORDER BY fire_at LIMIT 8""")
    iso = lambda d: d.isoformat() if isinstance(d, datetime) else None  # noqa: E731
    return {"todos": [{"id": t["id"], "title": t["title"], "due": iso(t["due"])} for t in todos],
            "alarms": [{"id": a["id"], "kind": a["kind"], "at": iso(a["fire_at"]), "text": a["text"] or ""}
                       for a in alarms]}


class ChatSession:
    """One Engine per browser connection; turns are serialised (the Engine is not re-entrant)."""

    def __init__(self):
        from .. import router
        from ..engine import Engine
        self.eng = Engine("text")
        router.warm()                                     # first reply shouldn't pay the TLS handshake
        self.lock = threading.Lock()

    def turn(self, text: str, on_delta=None) -> dict:
        import time
        with self.lock:
            t = time.perf_counter()
            try:
                reply = self.eng.turn(text, on_delta=on_delta)
            except Exception as e:                       # one bad turn never kills the chat
                reply = f"Something broke on my side ({type(e).__name__}). Try again?"
            dbg = getattr(self.eng, "last_debug", {}) or {}
            return {"type": "reply", "text": reply, "route": dbg.get("route"), "domain": dbg.get("domain"),
                    "mood": dbg.get("mood"), "provider": dbg.get("provider"),
                    "action": self.eng.last_action if dbg.get("route") == "fast_path" else None,
                    "ms": round((time.perf_counter() - t) * 1000), "ended": self.eng.ended,
                    "used": getattr(self.eng, "last_used", None)}


def app():
    from starlette.applications import Starlette
    from starlette.responses import FileResponse, JSONResponse, PlainTextResponse
    from starlette.routing import Mount, Route, WebSocketRoute
    from starlette.staticfiles import StaticFiles
    from starlette.websockets import WebSocketDisconnect

    token = web_token()
    hosts = {f"127.0.0.1:{PORT}", f"localhost:{PORT}"}
    origins = {f"http://{h}" for h in hosts}
    if os.getenv("STITI_WEB_DEV") == "1":            # `pnpm dev` on :3017 talks to this server (dev only)
        origins |= {"http://localhost:3017", "http://127.0.0.1:3017"}

    def host_ok(h) -> bool:
        return h.get("host") in hosts

    def tok_ok(req) -> bool:
        t = req.query_params.get("t") or req.headers.get("x-stiti-token", "")
        return secrets.compare_digest(t, token)

    files = {}

    async def built_files(scope, receive, send):
        """The Next export's assets — or a plain 404 while it isn't built (a fresh clone, CI), never a crash.
        Checked per request, so building the frontend while Stiti runs just works."""
        if not OUT.is_dir():
            return await PlainTextResponse("not found", 404)(scope, receive, send)
        if "app" not in files:
            files["app"] = StaticFiles(directory=OUT)
        return await files["app"](scope, receive, send)

    nostore = {"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer"}

    def page(name):
        async def h(req):
            if not host_ok(req.headers):
                return PlainTextResponse("bad host", 400)
            f = OUT / name
            if not f.exists():
                return PlainTextResponse("Stiti's web app isn't built yet: cd frontend && pnpm install && pnpm build", 503)
            return FileResponse(f, headers=nostore)
        return h

    async def icon(req):
        if not host_ok(req.headers):
            return PlainTextResponse("bad host", 400)
        n = req.path_params["n"]
        f = ICONS / f"asset {n}.png"
        if not re.fullmatch(r"\d{1,3}", n) or not f.exists():
            return PlainTextResponse("not found", 404)
        return FileResponse(f, headers={"Cache-Control": "max-age=86400"})

    async def link(req):
        """Hand the per-install key to Stiti's OWN pages, so any page opened on 127.0.0.1:7317 just works (no
        'open from the terminal' gate). Safe because: the Host check blocks DNS rebinding; browsers stamp every
        fetch with Sec-Fetch-Site, which page JS can't forge, so another website's request says 'cross-site'; and
        without CORS headers no other origin can read the response anyway. (Local apps could already read
        ~/.stiti/web_token.)"""
        if not host_ok(req.headers) or req.headers.get("sec-fetch-site") != "same-origin":
            return JSONResponse({"error": "not allowed"}, 403)
        return JSONResponse({"t": token}, headers={"Cache-Control": "no-store"})

    async def state(req):
        if not (host_ok(req.headers) and tok_ok(req)):
            return JSONResponse({"error": "not allowed"}, 403)
        return JSONResponse(await asyncio.to_thread(_state))

    async def todo_done(req):
        if not (host_ok(req.headers) and tok_ok(req)) or req.headers.get("origin") not in origins:
            return JSONResponse({"error": "not allowed"}, 403)
        from ..db import q
        tid = int(req.path_params["id"])
        await asyncio.to_thread(q, "UPDATE tasks SET status='done' WHERE id=%s AND status='open'", (tid,))
        return JSONResponse(await asyncio.to_thread(_state))

    def guard(req, write=False) -> bool:
        ok = host_ok(req.headers) and tok_ok(req)
        return ok and (not write or req.headers.get("origin") in origins)

    async def mind_api(req):
        if not guard(req):
            return JSONResponse({"error": "not allowed"}, 403)
        from . import mind
        return JSONResponse(await asyncio.to_thread(mind.overview))

    async def fact_add(req):
        if not guard(req, write=True):
            return JSONResponse({"error": "not allowed"}, 403)
        from . import mind
        body = await req.json()
        try:
            return JSONResponse(await asyncio.to_thread(mind.add_fact, str(body.get("text", ""))))
        except ValueError:
            return JSONResponse({"error": "Write at least a few words."}, 400)

    async def fact_forget(req):
        if not guard(req, write=True):
            return JSONResponse({"error": "not allowed"}, 403)
        from . import mind
        return JSONResponse({"ok": await asyncio.to_thread(mind.forget_fact, int(req.path_params["id"]))})

    async def ws_chat(ws):
        if not (host_ok(ws.headers) and ws.headers.get("origin") in origins
                and secrets.compare_digest(ws.query_params.get("t", ""), token)):
            await ws.close(code=4403)
            return
        await ws.accept()
        sess = await asyncio.to_thread(ChatSession)
        try:
            from .. import profile, router
            hello = {"type": "hello", "name": profile.call() if profile.known() else None,
                     "llm": any(s["key"] for s in router.status()),
                     "state": await asyncio.to_thread(_state)}
            await ws.send_text(json.dumps(hello))
            while True:
                msg = json.loads(await ws.receive_text())
                if msg.get("type") == "say" and isinstance(msg.get("text"), str) and msg["text"].strip():
                    await ws.send_text(json.dumps({"type": "thinking"}))
                    loop, pieces = asyncio.get_running_loop(), asyncio.Queue()

                    async def pump():                    # stream the reply word by word, in order
                        while (d := await pieces.get()) is not None:
                            await ws.send_text(json.dumps({"type": "delta", "text": d}))

                    pumping = asyncio.create_task(pump())
                    on_delta = lambda d: loop.call_soon_threadsafe(pieces.put_nowait, d)  # noqa: E731
                    try:
                        out = await asyncio.to_thread(sess.turn, msg["text"].strip()[:2000], on_delta)
                    finally:
                        pieces.put_nowait(None)
                        await pumping
                    await ws.send_text(json.dumps(out))
                    await ws.send_text(json.dumps({"type": "state", **await asyncio.to_thread(_state)}))
        except (WebSocketDisconnect, RuntimeError, json.JSONDecodeError):
            pass

    return Starlette(routes=[
        Route("/", page("index.html")), Route("/chat", page("chat.html")), Route("/memory", page("memory.html")),
        Route("/api/link", link), Route("/api/mind", mind_api),
        Route("/api/fact", fact_add, methods=["POST"]),
        Route("/api/fact/{id:int}/forget", fact_forget, methods=["POST"]),
        Route("/icons/{n}.png", icon), Route("/api/state", state),
        Route("/api/todo/{id:int}/done", todo_done, methods=["POST"]),
        WebSocketRoute("/ws", ws_chat),
        Mount("/", built_files),                                     # /_next/*, favicon, fonts
    ])


def url() -> str:
    return f"http://127.0.0.1:{PORT}/chat#t={web_token()}"


def serve_in_thread() -> threading.Thread | None:
    """Stiti.app runs the web app inside its own process (embedder already loaded), so the page is always on
    while Stiti is. Returns None if the port is taken (e.g. `stiti web` already running)."""
    import socket

    import uvicorn
    with socket.socket() as s:
        if s.connect_ex(("127.0.0.1", PORT)) == 0:
            return None
    server = uvicorn.Server(uvicorn.Config(app(), host="127.0.0.1", port=PORT, log_level="warning",
                                           ws_max_size=1 << 20))
    th = threading.Thread(target=server.run, name="stiti-web", daemon=True)
    th.start()
    return th


def run(open_browser: bool = True) -> None:
    import webbrowser

    import uvicorn
    from .. import embed, intent
    print("Stiti web is waking up… (memory + embedder)")
    embed.embed_query("warm up")
    intent._index()
    url = f"http://127.0.0.1:{PORT}/#t={web_token()}"
    print(f"\n✨  Stiti is at {url}\n    (bookmark http://127.0.0.1:{PORT}/chat after the first visit)\n")
    if open_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    uvicorn.run(app(), host="127.0.0.1", port=PORT, log_level="warning", ws_max_size=1 << 20)
