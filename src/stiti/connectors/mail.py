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


def snippet_of(raw: bytes, n: int = 300) -> str:
    """The first readable lines of a mail body (plain text; tags, headers of MIME parts and base64 blobs dropped).
    Best effort on a partial fetch: when it can't be read, "" — the subject alone is used. UNTRUSTED text."""
    import base64
    import quopri
    import re
    text = raw.decode("utf-8", "replace")
    part = re.search(r"content-type:\s*text/plain[^\n]*\n(?P<h>(?:[\w-]+:[^\n]*\n)*)\r?\n(?P<b>.*?)(?:\n--|\Z)", text,
                     re.I | re.S)
    head, body = (part["h"], part["b"]) if part else ("", text)
    if re.search(r"content-transfer-encoding:\s*base64", head, re.I):
        try:
            blob = re.sub(r"\s+", "", body)
            body = base64.b64decode(blob[:len(blob) // 4 * 4]).decode("utf-8", "replace")
        except Exception:
            return ""
    elif re.search(r"content-transfer-encoding:\s*quoted-printable", head, re.I) or "=\r\n" in body or "=\n" in body:
        try:
            body = quopri.decodestring(body.encode()).decode("utf-8", "replace")
        except Exception:
            pass
    if not part and re.search(r"^--[\w=.-]{8,}\s*$|content-type:", body, re.I | re.M):
        return ""                                   # a MIME tangle with no plain-text part in reach
    body = re.sub(r"(?s)<(script|style)\b.*?</\1>|<[^>]+>", " ", body)
    body = re.sub(r"(?m)^>.*$|https?://\S+", " ", body)                 # quoted replies and links say nothing new
    return re.sub(r"\s+", " ", body).strip()[:n]


def _fetch(m, ids: list[bytes], limit: int, snippet: bool = False) -> list[dict]:
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
        row = {"from": sender, "subject": _hdr(msg["Subject"]) or "(no subject)", "date": when}
        if snippet:                                 # D49: first lines only, never the whole mail
            try:
                typ, body = m.fetch(i, "(BODY.PEEK[TEXT]<0.2048>)")
                row["snippet"] = snippet_of(body[0][1]) if typ == "OK" and body and body[0] else ""
            except Exception:
                row["snippet"] = ""
        out.append(row)
    return out


def unread(limit: int = 5, snippet: bool = False) -> dict:
    if not configured():
        return {"error": "mail not configured (MAIL_ADDRESS / MAIL_APP_PASSWORD in .env)"}
    m = _conn()
    try:
        typ, data = m.search(None, "UNSEEN")
        ids = data[0].split() if typ == "OK" else []
        return {"unread": len(ids), "latest": _fetch(m, ids, limit, snippet)}
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
        return "I can't see your mail yet — it isn't set up."
    if not r["unread"]:
        return "Inbox zero — nothing unread. 🎉"
    items = "; ".join(f"{x['from']}: {x['subject']}" for x in r["latest"][:3])
    return f"{r['unread']} unread. Latest: {items}."
