"""Telegram: talk to Stiti from your phone (free, official Bot API, long-polling → no open ports).

Setup: message @BotFather → /newbot → put TELEGRAM_BOT_TOKEN in .env. Start Stiti; it prints a
6-digit pairing code; send `/pair <code>` to your bot. Only that chat id is ever answered (owner lock).
Alarms/reminders also get pushed here. Bot traffic is not end-to-end encrypted: P2 replies are
withheld on this channel.
"""
from __future__ import annotations

import json
import os
import random
import threading
import time

import httpx

from ..config import CFG

API = "https://api.telegram.org/bot{token}/{method}"
STATE = CFG.home / "telegram.json"


def token() -> str:
    return os.getenv("TELEGRAM_BOT_TOKEN", "")


def _state() -> dict:
    return json.loads(STATE.read_text()) if STATE.exists() else {}


def _save(d: dict) -> None:
    STATE.write_text(json.dumps(d))
    STATE.chmod(0o600)


def owner() -> int | None:
    return _state().get("owner_id")


def call(method: str, **params) -> dict:
    r = httpx.post(API.format(token=token(), method=method), json=params, timeout=40)
    return r.json()


def send(text: str, chat_id: int | None = None) -> None:
    cid = chat_id or owner()
    if token() and cid:
        try:
            call("sendMessage", chat_id=cid, text=text[:4000])
        except Exception:
            pass


class TelegramBot:
    def __init__(self, engine_factory):
        self.engine_factory = engine_factory
        self.engine = None
        self.code = f"{random.randint(0, 999999):06d}"

    def run(self, stop: threading.Event) -> None:
        if not token():
            return
        if not owner():
            print(f"[telegram] send this to your bot to pair it:  /pair {self.code}")
        offset = _state().get("offset", 0)
        while not stop.is_set():
            try:
                r = call("getUpdates", offset=offset, timeout=30, allowed_updates=["message"])
            except Exception:
                time.sleep(5)
                continue
            for u in r.get("result", []):
                offset = u["update_id"] + 1
                st = _state()
                st["offset"] = offset
                _save(st)
                msg = u.get("message") or {}
                chat, text = msg.get("chat", {}).get("id"), (msg.get("text") or "").strip()
                if not chat or not text:
                    continue
                if text.startswith("/pair"):
                    if not owner() and text.split()[-1] == self.code:
                        st["owner_id"] = chat
                        _save(st)
                        send("Paired ✅ — main hoon na. Ab yahan se bhi baat kar sakte ho.", chat)
                    else:
                        send("Pairing failed.", chat)
                    continue
                if chat != owner():
                    continue                                   # owner lock: ignore everyone else
                if self.engine is None:
                    self.engine = self.engine_factory("telegram")
                try:
                    reply = self.engine.turn(text)
                    if self.engine.last_debug.get("privacy") == 2:
                        reply = "That's private, so I'll answer it on your Mac, not over Telegram. 🔒"
                except Exception as e:
                    reply = f"Oops ({type(e).__name__}). Try again?"
                send(reply, chat)
