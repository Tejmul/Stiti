"""Tools Stiti can use through the LLM: native connectors + any MCP server (report §Connectors).

- tool-RAG: only the top-5 tools most similar to the request are shown to the LLM (embedder, ~ms).
- risk tiers: read → auto · low (open app, volume) → auto + announced · write/irreversible →
  never executed without an explicit "haan/yes" from Tejmul on the next turn.
- taint: once a turn has read untrusted content (mail, web, MCP output), write tools are blocked
  for that turn (CaMeL-lite: injected text can't make Stiti act).
"""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Callable

import numpy as np

from .. import embed
from ..config import CFG


@dataclass
class Tool:
    name: str
    description: str
    params: dict
    fn: Callable[..., object]
    risk: str = "read"              # read | low | write | irreversible
    untrusted_output: bool = False  # output may carry injected instructions
    source: str = "native"
    vec: np.ndarray | None = field(default=None, repr=False)

    def schema(self) -> dict:
        return {"type": "function", "function": {"name": self.name, "description": self.description,
                                                 "parameters": self.params}}


def _obj(**props) -> dict:
    return {"type": "object", "properties": props, "required": [k for k, v in props.items() if not v.get("optional")]}


# ---------------- native tools ----------------
def _cal_today():
    from ..connectors import eventkit
    return [{"title": e["title"], "start": f"{e['start']:%a %H:%M}", "end": f"{e['end']:%H:%M}",
             "location": e["location"]} for e in eventkit.today_events()]


def _cal_upcoming(days: int = 7):
    from ..connectors import eventkit
    now = datetime.now(CFG.tz)
    return [{"title": e["title"], "start": f"{e['start']:%a %d %b %H:%M}", "calendar": e["calendar"]}
            for e in eventkit.events(now, now + timedelta(days=min(int(days), 31)))][:15]


def _mail_unread():
    from ..connectors import mail
    r = mail.unread()
    return r if "error" in r else {"unread": r["unread"], "latest": [
        {"from": x["from"], "subject": x["subject"], "date": f"{x['date']:%d %b %H:%M}" if x["date"] else ""}
        for x in r["latest"]]}


def _mail_search(query: str):
    from ..connectors import mail
    r = mail.search(query)
    return r if "error" in r else {"matches": r["matches"], "latest": [
        {"from": x["from"], "subject": x["subject"]} for x in r["latest"]]}


SAFE_APPS = {"spotify", "safari", "chrome", "google chrome", "notes", "calendar", "mail", "music", "whatsapp",
             "telegram", "visual studio code", "code", "terminal", "finder", "messages", "reminders", "slack"}


def _open_app(name: str):
    n = name.strip().lower()
    if n not in SAFE_APPS:
        return {"error": f"'{name}' isn't on Stiti's allowlist of apps"}
    subprocess.run(["open", "-a", name.title() if n != "code" else "Visual Studio Code"], check=False)
    return {"opened": name}


def _volume(level: int):
    lv = max(0, min(100, int(level)))
    subprocess.run(["osascript", "-e", f"set volume output volume {lv}"], check=False)
    return {"volume": lv}


NATIVE = [
    Tool("calendar_today", "List today's events from Tejmul's calendar (Apple/Google via macOS Calendar).",
         _obj(), lambda: _cal_today()),
    Tool("calendar_upcoming", "List upcoming calendar events for the next N days.",
         _obj(days={"type": "integer", "description": "days ahead, 1-31"}), _cal_upcoming),
    Tool("mail_unread", "Count unread emails and list the latest senders and subjects (read-only).",
         _obj(), lambda: _mail_unread(), untrusted_output=True),
    Tool("mail_search", "Search Tejmul's email by sender or subject words (read-only).",
         _obj(query={"type": "string"}), _mail_search, untrusted_output=True),
    Tool("mac_open_app", "Open an app on the Mac (allowlisted apps only).",
         _obj(name={"type": "string"}), _open_app, risk="low"),
    Tool("mac_set_volume", "Set the Mac output volume 0-100.",
         _obj(level={"type": "integer"}), _volume, risk="low"),
]


def all_tools() -> list[Tool]:
    from . import mcp_bus
    return NATIVE + mcp_bus.tools()


def select(qvec, k: int = 5, tools: list[Tool] | None = None) -> list[Tool]:
    tools = tools or all_tools()
    missing = [t for t in tools if t.vec is None]
    if missing:
        for t, v in zip(missing, embed.embed_docs([f"{t.name}: {t.description}" for t in missing])):
            t.vec = v.to_numpy().astype(np.float32)
    qv = qvec.to_numpy().astype(np.float32) if hasattr(qvec, "to_numpy") else qvec
    ranked = sorted(tools, key=lambda t: -float(t.vec @ qv))
    return ranked[:k]


def run(tool: Tool, args: dict, tainted: bool) -> tuple[str, bool]:
    """Execute with the risk gate. Returns (result_text, needs_confirmation)."""
    if tool.risk in ("write", "irreversible"):
        if tainted:
            return json.dumps({"blocked": "untrusted content was read this turn; write actions are disabled"}), False
        return json.dumps({"needs_confirmation": f"{tool.name}({json.dumps(args)})"}), True
    try:
        out = tool.fn(**args)
    except TypeError as e:
        out = {"error": f"bad arguments: {e}"}
    except Exception as e:
        out = {"error": f"{type(e).__name__}: {str(e)[:200]}"}
    text = json.dumps(out, default=str, ensure_ascii=False)
    return text[:2500], False
