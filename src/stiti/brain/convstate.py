"""The conversation survives a restart (2026-11-20, docs/research/conversation_continuity.md).

His Stiti restarts often — the mic watchdog (12 restarts in 55 min on 2026-11-18), every update — and each restart
began a new session with an empty head: RECENT, the said-ledger ("what else?"), the thread ("and that one?"), the open
"haan?" for an action, her last reply… all lived only in the process. Now:

  - the session itself is picked up again when the last turn was < memory.RESUME_S ago (Postgres has every episode);
  - the engine's small in-memory state is written after every turn to ~/.stiti/conversation.json (0600, atomic) and
    read back by an Engine that resumed that same session. Local only (principle 3); nothing here is new data — every
    sentence is already an episode in the brain.
Missing / old / foreign file → nothing is restored and everything behaves as before.
"""
from __future__ import annotations

import json
import os
import time

from ..config import CFG
from . import norepeat
from .thread import Thread

FILE = "conversation.json"
VERSION = 1


def path():
    return CFG.home / FILE


def snapshot(e) -> dict:
    """Plain data from an Engine (everything JSON can hold)."""
    said = [[t, ep, s] for (t, ep, s, _w) in e.said.live()]
    pend = None
    if getattr(e, "pending", None):
        tool, args = e.pending[0], e.pending[1]
        pend = {"tool": getattr(tool, "name", None), "args": args}
    th = getattr(e, "thread", None)
    return {
        "v": VERSION, "session": e.session, "saved_at": time.time(),
        "said": said, "anchor": e.said.anchor[0] if e.said.anchor else None,
        "info_at": e.info_at, "last_reply_text": e.last_reply_text, "last_user_text": e.last_user_text,
        "last_route": e.last_route, "last_reply_ep": e.last_reply_ep, "last_user_ep": e.last_user_ep,
        "last_mood": e.last_mood, "lang_prev": e.lang_prev, "lang_pref": e.lang_pref,
        "topic_hint": list(e.topic_hint) if e.topic_hint else None,
        "thread": th.as_dict() if th is not None else None,
        "her_last": list(getattr(e, "her_last", []))[-3:], "his_last": list(getattr(e, "his_last", []))[-3:],
        "pending": pend if pend and pend["tool"] else None,
    }


def save(e) -> None:
    """After a turn (never raises: a full disk must not cost him a reply)."""
    try:
        data = json.dumps(snapshot(e), ensure_ascii=False, default=str)
        p = path()
        tmp = p.with_suffix(".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(data)
        os.replace(tmp, p)
    except Exception as ex:
        print(f"[convstate] save: {type(ex).__name__}: {ex}")


def load(session: int, max_age_s: float) -> dict | None:
    try:
        d = json.loads(path().read_text())
    except (OSError, ValueError):
        return None
    if d.get("v") != VERSION or d.get("session") != session or time.time() - float(d.get("saved_at") or 0) > max_age_s:
        return None
    return d


def restore(e, d: dict) -> None:
    """Put a saved conversation back into a fresh Engine (the session already matches)."""
    led = norepeat.Ledger(ignore=e.said.ignore)
    for t, ep, s in d.get("said") or []:
        led = led.add(s, ep, now=float(t))
    if d.get("anchor"):
        try:
            from .. import embed
            led = led.with_anchor(d["anchor"], embed.embed_query(d["anchor"]))
        except Exception:
            pass
    e.said = led
    for k in ("info_at", "last_reply_text", "last_user_text", "last_route", "last_reply_ep", "last_user_ep",
              "last_mood", "lang_prev", "lang_pref"):
        if k in d:
            setattr(e, k, d[k])
    if d.get("topic_hint"):
        e.topic_hint = tuple(d["topic_hint"])
    e.thread = Thread.from_dict(d.get("thread"))
    e.her_last = list(d.get("her_last") or [])
    e.his_last = list(d.get("his_last") or [])
    p = d.get("pending")
    if p:
        try:
            from ..tools import registry
            tool = next((t for t in registry.all_tools() if t.name == p["tool"]), None)
            if tool is not None:
                e.pending, e.pending_ctx = (tool, p.get("args") or {}), None
        except Exception:
            pass
