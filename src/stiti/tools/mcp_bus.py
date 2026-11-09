"""MCP bus: plug any MCP server into Stiti without touching the core.

Config: ~/.stiti/mcp.json → {"servers": {"github": {"command": "...", "args": [...], "env": {...}}}}
Security (report §Security — tool poisoning, rug pulls):
  * pin-and-diff: each server's tool list (names, descriptions, schemas) is hashed. A server is only
    used after `stiti mcp approve <name>`; if its tools ever change, it is disabled until re-approved.
  * every MCP result is treated as untrusted output (taints the turn).
  * tools whose names look like actions (create/send/delete/update/write…) need spoken confirmation.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import re
import threading
from contextlib import AsyncExitStack

from ..config import CFG

CONF = CFG.home / "mcp.json"
PINS = CFG.home / "mcp_pins.json"
READ_VERBS = re.compile(r"^(get|list|search|read|find|query|fetch|show|describe|lookup|view)", re.I)

_loop: asyncio.AbstractEventLoop | None = None
_sessions: dict = {}
_tools: list = []
_status: dict[str, str] = {}
_started = threading.Event()


def _config() -> dict:
    return json.loads(CONF.read_text()).get("servers", {}) if CONF.exists() else {}


def _pins() -> dict:
    return json.loads(PINS.read_text()) if PINS.exists() else {}


def _hash(tools) -> str:
    blob = json.dumps(sorted([(t.name, t.description or "", json.dumps(t.inputSchema, sort_keys=True))
                              for t in tools]), sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()


async def _connect_all(stack: AsyncExitStack, approve: str | None = None):
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    from .registry import Tool
    pins = _pins()
    for name, spec in _config().items():
        try:
            params = StdioServerParameters(command=spec["command"], args=spec.get("args", []),
                                           env=spec.get("env") or None)
            read, write = await stack.enter_async_context(stdio_client(params))
            sess = await stack.enter_async_context(ClientSession(read, write))
            try:
                await sess.initialize()
            except Exception:
                pass
            listed = (await sess.list_tools()).tools
            h = _hash(listed)
            if approve == name:
                pins[name] = h
                PINS.write_text(json.dumps(pins, indent=2))
            if pins.get(name) != h:
                _status[name] = "NOT APPROVED" if name not in pins else "TOOLS CHANGED — disabled, re-approve"
                continue
            _sessions[name] = sess
            for t in listed:
                risk = "read" if READ_VERBS.match(t.name) else "write"
                _tools.append(Tool(f"{name}__{t.name}"[:64], (t.description or "")[:400],
                                   t.inputSchema or {"type": "object", "properties": {}},
                                   _caller(name, t.name), risk=risk, untrusted_output=True, source=f"mcp:{name}"))
            _status[name] = f"ok ({len(listed)} tools)"
        except Exception as e:
            _status[name] = f"error: {type(e).__name__}: {str(e)[:120]}"


def _caller(server: str, tool: str):
    def call(**args):
        fut = asyncio.run_coroutine_threadsafe(_sessions[server].call_tool(tool, args), _loop)
        res = fut.result(timeout=60)
        parts = [getattr(c, "text", None) or str(c) for c in (res.content or [])]
        return {"result": "\n".join(parts)[:2400], "is_error": bool(getattr(res, "isError", False))}
    return call


def start(approve: str | None = None) -> None:
    """Start servers in a background event-loop thread (once)."""
    global _loop
    if _started.is_set() or not _config():
        _started.set()
        return
    ready = threading.Event()

    def runner():
        global _loop
        _loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_loop)
        stack = AsyncExitStack()
        _loop.run_until_complete(stack.__aenter__())
        _loop.run_until_complete(_connect_all(stack, approve))
        ready.set()
        _loop.run_forever()
    threading.Thread(target=runner, daemon=True).start()
    ready.wait(60)
    _started.set()


def tools() -> list:
    if not _started.is_set():
        start()
    return list(_tools)


def status() -> dict[str, str]:
    if not _started.is_set():
        start()
    return dict(_status)
