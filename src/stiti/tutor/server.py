"""Local board server: Starlette + uvicorn (already in uv.lock via mcp — no new dependency, ~38 MB).

127.0.0.1 on a random free port. Security (research §4): per-session token in the URL *fragment*
(never sent in HTTP requests or logs), Host check on every request (DNS rebinding), Host + Origin +
token check on the WebSocket handshake (cross-site WebSocket hijacking), strict CSP.

Runs in a background thread with its own event loop; the tutor (sync code) calls `send()` from any
thread and reads browser events from `events` (a plain queue).
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import queue
import re
import secrets
import socket
import threading
import time
from pathlib import Path
from typing import Callable

WEB = Path(__file__).parent / "web"
CDN = "https://esm.sh"


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class BoardServer:
    def __init__(self, on_connect: Callable[[], list[dict]] | None = None, port: int | None = None):
        self.port = port or free_port()
        self.token = secrets.token_urlsafe(24)
        self.hosts = {f"127.0.0.1:{self.port}", f"localhost:{self.port}"}
        self.origins = {f"http://{h}" for h in self.hosts}
        self.events: queue.Queue[dict] = queue.Queue()
        self.on_connect = on_connect or (lambda: [])
        self.clients: set = set()
        self.loop: asyncio.AbstractEventLoop | None = None
        self.server = None
        self._ready = threading.Event()
        self.connected = threading.Event()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}/#t={self.token}"

    # ------------------------------------------------------------ app
    def _csp(self, html: str) -> str:
        m = re.search(r'<script type="importmap">(.*?)</script>', html, re.S)
        h = base64.b64encode(hashlib.sha256(m.group(1).encode()).digest()).decode() if m else ""
        ws = " ".join(f"ws://{x}" for x in self.hosts)
        return (f"default-src 'self'; script-src 'self' {CDN} 'sha256-{h}'; style-src 'self' 'unsafe-inline' {CDN}; "
                f"font-src 'self' data: {CDN}; img-src 'self' data: blob: {CDN}; connect-src 'self' {ws} {CDN}; "
                f"worker-src 'self' blob: {CDN}; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")

    def app(self):
        from starlette.applications import Starlette
        from starlette.responses import FileResponse, HTMLResponse, PlainTextResponse
        from starlette.routing import Route, WebSocketRoute
        from starlette.websockets import WebSocketDisconnect

        html = (WEB / "index.html").read_text()
        csp = self._csp(html)
        nostore = {"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"}

        def host_ok(headers) -> bool:
            return headers.get("host") in self.hosts

        async def page(req):
            if not host_ok(req.headers):
                return PlainTextResponse("bad host", 400)
            return HTMLResponse(html, headers={**nostore, "Content-Security-Policy": csp,
                                               "Referrer-Policy": "no-referrer"})

        async def static(req):
            if not host_ok(req.headers):
                return PlainTextResponse("bad host", 400)
            name = req.path_params["name"]
            if name not in ("board.js", "board.css"):
                return PlainTextResponse("not found", 404)
            return FileResponse(WEB / name, headers=nostore)

        async def ws_ep(ws):
            ok = (host_ok(ws.headers) and ws.headers.get("origin") in self.origins
                  and secrets.compare_digest(ws.query_params.get("t", ""), self.token))
            if not ok:
                await ws.close(code=4403)
                return
            await ws.accept()
            self.clients.add(ws)
            try:
                for m in self.on_connect():
                    await ws.send_text(json.dumps(m))
                while True:
                    msg = json.loads(await ws.receive_text())
                    if isinstance(msg, dict) and isinstance(msg.get("type"), str):
                        if msg["type"] == "ready":
                            self.connected.set()
                        self.events.put(msg)
            except (WebSocketDisconnect, RuntimeError, json.JSONDecodeError):
                pass
            finally:
                self.clients.discard(ws)

        return Starlette(routes=[Route("/", page), Route("/static/{name}", static), WebSocketRoute("/ws", ws_ep)])

    # ------------------------------------------------------------ lifecycle
    def start(self) -> "BoardServer":
        import uvicorn

        cfg = uvicorn.Config(self.app(), host="127.0.0.1", port=self.port, log_level="warning",
                             ws_max_size=1 << 20, lifespan="off")
        self.server = uvicorn.Server(cfg)

        def run():
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            self._ready.set()
            self.loop.run_until_complete(self.server.serve())

        threading.Thread(target=run, daemon=True, name="board-server").start()
        self._ready.wait(5)
        for _ in range(100):
            if self.server.started:
                break
            time.sleep(0.02)
        return self

    def stop(self) -> None:
        if self.server:
            self.server.should_exit = True

    def open_browser(self) -> None:
        import webbrowser
        webbrowser.open(self.url)

    # ------------------------------------------------------------ messaging
    def send(self, msg: dict) -> None:
        if not self.loop or not self.clients:
            return
        data = json.dumps(msg)

        async def go():
            for ws in list(self.clients):
                try:
                    await ws.send_text(data)
                except Exception:
                    self.clients.discard(ws)
        asyncio.run_coroutine_threadsafe(go(), self.loop)
