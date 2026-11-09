"""`stiti web` — Stiti's local web app: landing page + chat, served from this Mac only.

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

STATIC = Path(__file__).parent / "static"
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


def _history(n: int = 40) -> list[dict]:
    from ..db import q
    rows = q("""SELECT speaker, text, ts FROM (
                  SELECT speaker, text, occurred_at AS ts FROM episodes
                  WHERE speaker IN ('user','stiti') AND origin IN ('owner','agent') AND privacy < 2
                  ORDER BY occurred_at DESC LIMIT %s) x ORDER BY ts""", (n,))
    return [{"who": "you" if r["speaker"] == "user" else "stiti", "text": r["text"], "ts": r["ts"].isoformat()}
            for r in rows]


class ChatSession:
    """One Engine per browser connection; turns are serialised (the Engine is not re-entrant)."""

    def __init__(self):
        from ..engine import Engine
        self.eng = Engine("text")
        self.lock = threading.Lock()

    def turn(self, text: str) -> dict:
        import time
        with self.lock:
            t = time.perf_counter()
            try:
                reply = self.eng.turn(text)
            except Exception as e:                       # one bad turn never kills the chat
                reply = f"Something broke on my side ({type(e).__name__}). Try again?"
            dbg = getattr(self.eng, "last_debug", {}) or {}
            return {"type": "reply", "text": reply, "route": dbg.get("route"), "domain": dbg.get("domain"),
                    "mood": dbg.get("mood"), "provider": dbg.get("provider"),
                    "action": self.eng.last_action if dbg.get("route") == "fast_path" else None,
                    "ms": round((time.perf_counter() - t) * 1000), "ended": self.eng.ended}


def app():
    from starlette.applications import Starlette
    from starlette.responses import FileResponse, JSONResponse, PlainTextResponse
    from starlette.routing import Mount, Route, WebSocketRoute
    from starlette.staticfiles import StaticFiles
    from starlette.websockets import WebSocketDisconnect

    token = web_token()
    hosts = {f"127.0.0.1:{PORT}", f"localhost:{PORT}"}
    origins = {f"http://{h}" for h in hosts}

    def host_ok(h) -> bool:
        return h.get("host") in hosts

    def tok_ok(req) -> bool:
        t = req.query_params.get("t") or req.headers.get("x-stiti-token", "")
        return secrets.compare_digest(t, token)

    nostore = {"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer"}

    def page(name):
        async def h(req):
            if not host_ok(req.headers):
                return PlainTextResponse("bad host", 400)
            return FileResponse(STATIC / name, headers=nostore)
        return h

    async def icon(req):
        if not host_ok(req.headers):
            return PlainTextResponse("bad host", 400)
        n = req.path_params["n"]
        f = ICONS / f"asset {n}.png"
        if not re.fullmatch(r"\d{1,3}", n) or not f.exists():
            return PlainTextResponse("not found", 404)
        return FileResponse(f, headers={"Cache-Control": "max-age=86400"})

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
                     "llm": any(s["key"] for s in router.status()), "history": await asyncio.to_thread(_history),
                     "state": await asyncio.to_thread(_state)}
            await ws.send_text(json.dumps(hello))
            while True:
                msg = json.loads(await ws.receive_text())
                if msg.get("type") == "say" and isinstance(msg.get("text"), str) and msg["text"].strip():
                    await ws.send_text(json.dumps({"type": "thinking"}))
                    out = await asyncio.to_thread(sess.turn, msg["text"].strip()[:2000])
                    await ws.send_text(json.dumps(out))
                    await ws.send_text(json.dumps({"type": "state", **await asyncio.to_thread(_state)}))
        except (WebSocketDisconnect, RuntimeError, json.JSONDecodeError):
            pass

    return Starlette(routes=[
        Route("/", page("index.html")), Route("/chat", page("chat.html")),
        Route("/icons/{n}.png", icon), Route("/api/state", state),
        Route("/api/todo/{id:int}/done", todo_done, methods=["POST"]),
        WebSocketRoute("/ws", ws_chat),
        Mount("/static", StaticFiles(directory=STATIC)),
    ])


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
