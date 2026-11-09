"""Gmail (or any IMAP) — READ-ONLY, stdlib imaplib, free. Needs a Google *app password*:
myaccount.google.com → Security → 2-Step Verification → App passwords. In .env:
  MAIL_ADDRESS=you@gmail.com   MAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx   (MAIL_IMAP_HOST=imap.gmail.com)

Only headers (from, subject, date) are read by default; email content is UNTRUSTED (prompt-injection
risk), tagged origin='untrusted', and a turn that read mail can't trigger write tools (CaMeL-lite).
Sending mail is deliberately not implemented.
"""
from __future__ import annotations

import email
import imaplib
import os
from email.header import decode_header, make_header
from email.utils import parsedate_to_datetime

from ..config import CFG


def configured() -> bool:
    return bool(os.getenv("MAIL_ADDRESS") and os.getenv("MAIL_APP_PASSWORD"))


def _conn() -> imaplib.IMAP4_SSL:
    m = imaplib.IMAP4_SSL(os.getenv("MAIL_IMAP_HOST", "imap.gmail.com"))
    m.login(os.environ["MAIL_ADDRESS"], os.environ["MAIL_APP_PASSWORD"].replace(" ", ""))
    m.select("INBOX", readonly=True)
    return m


def _hdr(v) -> str:
    return str(make_header(decode_header(v or ""))).strip()


def _fetch(m, ids: list[bytes], limit: int) -> list[dict]:
    out = []
    for i in reversed(ids[-limit:]):
        typ, data = m.fetch(i, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])")
        if typ != "OK" or not data or not data[0]:
            continue
        msg = email.message_from_bytes(data[0][1])
        try:
            when = parsedate_to_datetime(msg["Date"]).astimezone(CFG.tz)
        except Exception:
            when = None
        sender = _hdr(msg["From"]).split("<")[0].strip(' "') or _hdr(msg["From"])
        out.append({"from": sender, "subject": _hdr(msg["Subject"]) or "(no subject)", "date": when})
    return out


def unread(limit: int = 5) -> dict:
    if not configured():
        return {"error": "mail not configured (MAIL_ADDRESS / MAIL_APP_PASSWORD in .env)"}
    m = _conn()
    try:
        typ, data = m.search(None, "UNSEEN")
        ids = data[0].split() if typ == "OK" else []
        return {"unread": len(ids), "latest": _fetch(m, ids, limit)}
    finally:
        m.logout()


def search(text: str, limit: int = 5) -> dict:
    if not configured():
        return {"error": "mail not configured"}
    m = _conn()
    try:
        safe = text.replace('"', "")
        typ, data = m.search(None, f'(OR SUBJECT "{safe}" FROM "{safe}")')
        ids = data[0].split() if typ == "OK" else []
        return {"matches": len(ids), "latest": _fetch(m, ids, limit)}
    finally:
        m.logout()


def speak_unread(r: dict) -> str:
    if "error" in r:
        return "Mail isn't connected yet — add a Gmail app password to .env."
    if not r["unread"]:
        return "Inbox zero — nothing unread. 🎉"
    items = "; ".join(f"{x['from']}: {x['subject']}" for x in r["latest"][:3])
    return f"{r['unread']} unread. Latest: {items}."
