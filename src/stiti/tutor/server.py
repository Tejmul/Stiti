"""Local board server: Starlette + uvicorn (already in uv.lock via mcp — no new dependency, ~38 MB).

127.0.0.1:7318 for every lesson (one tab that reconnects; a random port only if 7318 is busy or in tests).
Security (research §4): a token in the URL *fragment* (kept in ~/.stiti/board.token, owner-only)
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

WEB = Path(__file__).parent / "web"                                        # plain-JS fallback board
OUT = Path(__file__).resolve().parents[3] / "frontend" / "out"             # the Next.js board (frontend: pnpm build)
CDN = "https://esm.sh"
STATIC_PREFIXES = ("_next/", "excalidraw/")                                 # what the Next board page loads
STATIC_FILES = ("favicon.svg", "apple-touch-icon.png")


BOARD_PORT = 7318          # ONE fixed address for every lesson (he: "creating tabs on tabs"); free_port() if busy
TAB_WAIT_S = 6.0           # an open board tab reconnects within ~5 s (board.js backoff caps at 5 s)


def _port_free(port: int) -> bool:
    with socket.socket() as s:
        try:
            s.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def board_token() -> str:
    """A token kept in ~/.stiti/board.token (owner-only): the board URL stays the same across lessons, so the tab he
    already has open reconnects instead of a new tab per lesson. Still a secret in the URL fragment (never sent)."""
    try:
        from ..config import CFG
        f = CFG.home / "board.token"
        if f.exists() and len(f.read_text().strip()) >= 24:
            return f.read_text().strip()
        tok = secrets.token_urlsafe(24)
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(tok)
        f.chmod(0o600)
        return tok
    except Exception:
        return secrets.token_urlsafe(24)


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class BoardServer:
    def __init__(self, on_connect: Callable[[], list[dict]] | None = None, port: int | None = None,
                 fixed: bool | None = None):
        import os
        if fixed is None:                            # the real lessons use the fixed address; tests keep random ports
            fixed = os.getenv("STITI_BOARD_FIXED", "1") != "0" and port is None
        want = int(os.getenv("STITI_BOARD_PORT", BOARD_PORT))
        self.fixed = bool(fixed and _port_free(want))
        self.port = port or (want if self.fixed else free_port())
        self.token = board_token() if self.fixed else secrets.token_urlsafe(24)
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
    def _csp_next(self, html: str) -> str:
        """CSP for the Next.js static export: its inline bootstrap scripts are allowed by their sha256 (computed from
        this exact build at startup), everything else loads from this server — Excalidraw's fonts included."""
        hashes = " ".join(
            f"'sha256-{base64.b64encode(hashlib.sha256(body.encode()).digest()).decode()}'"
            for attrs, body in re.findall(r"<script([^>]*)>(.*?)</script>", html, re.S)
            if body and "src=" not in attrs)
        ws = " ".join(f"ws://{x}" for x in self.hosts)
        return (f"default-src 'self'; script-src 'self' {hashes}; style-src 'self' 'unsafe-inline'; "
                f"font-src 'self' data:; img-src 'self' data: blob:; connect-src 'self' {ws}; worker-src 'self' blob:; "
                f"frame-ancestors 'none'; base-uri 'none'; form-action 'none'; object-src 'none'")

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

        import mimetypes
        for ext, typ in ((".woff2", "font/woff2"), (".woff", "font/woff"), (".ttf", "font/ttf"), (".js", "text/javascript"),
                         (".css", "text/css"), (".svg", "image/svg+xml"), (".txt", "text/plain")):
            mimetypes.add_type(typ, ext)
        nextjs = (OUT / "board.html").is_file()           # built Next.js board, else the plain-JS fallback
        if nextjs:
            html = (OUT / "board.html").read_text()
            csp = self._csp_next(html)
        else:
            html = (WEB / "index.html").read_text()
            csp = self._csp(html)
        out_root = OUT.resolve()
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

        async def asset(req):                             # the Next board's files: /_next/…, /excalidraw/fonts/…
            if not host_ok(req.headers):
                return PlainTextResponse("bad host", 400)
            rel = req.path_params["path"]
            if not nextjs or not (rel.startswith(STATIC_PREFIXES) or rel in STATIC_FILES) or "\\" in rel or "\0" in rel:
                return PlainTextResponse("not found", 404)
            f = (out_root / rel).resolve()
            if (".." in rel.split("/") or not f.is_relative_to(out_root) or not f.is_file()    # no path traversal
                    or not (f.relative_to(out_root).as_posix().startswith(STATIC_PREFIXES)
                            or f.relative_to(out_root).as_posix() in STATIC_FILES)):
                return PlainTextResponse("not found", 404)
            hashed = rel.startswith("_next/static/")      # content-hashed names never change
            cache = "public, max-age=31536000, immutable" if hashed else "no-cache"
            return FileResponse(f, headers={"Cache-Control": cache, "X-Content-Type-Options": "nosniff"})

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

        return Starlette(routes=[Route("/", page), Route("/static/{name}", static), WebSocketRoute("/ws", ws_ep),
                                 Route("/{path:path}", asset)])

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

    def open_if_no_tab(self) -> bool:
        """Open the board only when no tab is already showing it: on the fixed address an open tab reconnects by
        itself within TAB_WAIT_S. -> True when a new tab was opened."""
        if self.fixed and self.connected.wait(TAB_WAIT_S):
            return False
        if self.connected.is_set():
            return False
        self.open_browser()
        return True

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
