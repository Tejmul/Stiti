"""Mac actions: files (Spotlight), music, iMessage, web search/read, what's on screen.

Risk tiers live in tools/registry.py: reading is automatic; sending a message is never done
without his spoken "haan". Web pages, search results and screen text are UNTRUSTED (they can
contain injected instructions), so a turn that read them can't trigger write actions.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path

from ..config import CFG

HOME = Path.home()


def _osa(script: str) -> str:
    r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=15)
    return (r.stdout or r.stderr).strip()


# ---------------- files ----------------
def find_files(query: str, recent_days: int | None = None, limit: int = 8) -> list[dict]:
    q = query.replace('"', "").strip()
    args = ["mdfind", "-onlyin", str(HOME)]
    args += [f'kMDItemDisplayName == "*{q}*"cd || kMDItemTextContent == "{q}"cd'] if q else ["kMDItemContentType == *"]
    out = subprocess.run(args, capture_output=True, text=True, timeout=20).stdout.splitlines()
    files = []
    for p in out:
        if "/Library/" in p or "/." in p:
            continue
        try:
            st = os.stat(p)
        except OSError:
            continue
        files.append({"path": p, "name": os.path.basename(p), "modified": datetime.fromtimestamp(st.st_mtime, CFG.tz)})
    if recent_days:
        cutoff = datetime.now(CFG.tz).timestamp() - recent_days * 86400
        files = [f for f in files if f["modified"].timestamp() >= cutoff]
    files.sort(key=lambda f: f["modified"], reverse=True)
    return [{**f, "modified": f"{f['modified']:%d %b %H:%M}"} for f in files[:limit]]


def open_path(path: str) -> dict:
    p = Path(path).expanduser().resolve()
    if not str(p).startswith(str(HOME)) or not p.exists():
        return {"error": "only existing files inside your home folder can be opened"}
    subprocess.run(["open", str(p)])
    return {"opened": str(p)}


# ---------------- music ----------------
def music(action: str, app: str = "auto") -> dict:
    action = action.lower().strip()
    verbs = {"play": "play", "pause": "pause", "toggle": "playpause", "next": "next track",
             "previous": "previous track", "back": "previous track"}
    if action not in verbs:
        return {"error": f"unknown action {action}"}
    if app == "auto":
        running = _osa('tell application "System Events" to get name of every process')
        app = "Spotify" if "Spotify" in running else "Music"
    _osa(f'tell application "{app}" to {verbs[action]}')
    now = _osa(f'tell application "{app}" to if player state is playing then return (name of current track) & " — " & (artist of current track)')
    return {"app": app, "action": action, "now_playing": now if "—" in now else None}


MUSIC_RX = re.compile(r"\b(pause|resume|play|next|skip|previous|pichla|agla|band karo|chalao|rok do)\b.*\b(music|song|gaana|gana|track|spotify)\b|"
                      r"\b(music|song|gaana|gana|spotify)\b.*\b(pause|resume|play|next|skip|previous|band|chalao|rok)\b", re.I)


def music_fastpath(text: str) -> str | None:
    if not MUSIC_RX.search(text):
        return None
    t = text.lower()
    action = ("next" if re.search(r"\b(next|skip|agla)\b", t) else "previous" if re.search(r"\b(previous|pichla|back)\b", t)
              else "pause" if re.search(r"\b(pause|band|rok|stop)\b", t) else "play")
    r = music(action)
    if "error" in r:
        return "Couldn't control the music."
    return f"{r['app']}: {action}" + (f" — now playing {r['now_playing']}." if r.get("now_playing") else ".")


# ---------------- messages ----------------
def send_imessage(to: str, text: str) -> dict:
    """WRITE action — only ever called after his explicit 'haan' (registry risk tier)."""
    script = f'''tell application "Messages"
        set svc to 1st account whose service type = iMessage
        send {json.dumps(text)} to participant {json.dumps(to)} of svc
    end tell'''
    out = _osa(script)
    return {"sent_to": to} if not out else {"error": out[:200]}


# ---------------- web ----------------
def web_search(query: str, limit: int = 5) -> list[dict]:
    from ddgs import DDGS
    try:
        res = DDGS().text(query, max_results=limit, backend="auto")
    except Exception as e:
        return [{"error": f"search failed: {str(e)[:80]}"}]
    return [{"title": r.get("title", ""), "url": r.get("href", ""), "snippet": (r.get("body") or "")[:240]} for r in res]


def web_read(url: str, max_chars: int = 3000) -> dict:
    if not re.match(r"^https?://", url):
        return {"error": "only http(s) URLs"}
    import httpx
    from markitdown import MarkItDown
    r = httpx.get(url, timeout=15, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0 (Stiti personal assistant)"})
    with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as f:
        f.write(r.content)
        tmp = f.name
    try:
        text = MarkItDown(enable_plugins=False).convert(tmp).text_content or ""
    finally:
        os.unlink(tmp)
    return {"url": str(r.url), "text": re.sub(r"\n{3,}", "\n\n", text)[:max_chars]}


# ---------------- screen ----------------
def screen_now() -> dict:
    from ..life.proactive import frontmost_app
    app = frontmost_app()
    title = _osa('tell application "System Events" to tell (first process whose frontmost is true) to '
                 'get name of front window')
    return {"app": app, "window": title if title and "error" not in title.lower() and "not allowed" not in title.lower() else None}


def screen_read() -> dict:
    """Screenshot → on-device Vision OCR (macOS asks once for Screen Recording permission). Nothing is stored."""
    with tempfile.TemporaryDirectory() as td:
        png = Path(td) / "s.png"
        subprocess.run(["screencapture", "-x", "-C", str(png)], capture_output=True, timeout=15)
        if not png.exists() or png.stat().st_size < 1000:
            return {"error": "no screen access — allow Stiti in System Settings → Privacy → Screen Recording"}
        from .ocr import ocr_image
        return {**screen_now(), "text": ocr_image(png)[:3000]}
