"""Real pictures on the notes page — the best free picture of a concept from Wikimedia Commons (D53).

He: "using the whiteboard it should use the browser, show us the best pictures and start teaching us."
- Search Commons (free, no key; only the concept's name leaves the Mac — never anything about him), keep a file only
  when its title carries ALL the content words of the concept ("Abstract syntax tree for Euclidean algorithm.svg"
  for "Abstract Syntax Trees"; linguistics "Syntax tree - …" files are rejected), largest sensible aspect first.
- The 800 px thumbnail (SVGs come rendered as PNG) is shrunk to ≤ 720 px and ≤ ~220 KB, cached in
  ~/.stiti/tutor/pictures/, and returned as a data: URL (the board's CSP allows data: images).
- Credited on the board: "Wikimedia Commons · <licence>".
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import re
from pathlib import Path

API = "https://commons.wikimedia.org/w/api.php"
UA = "StitiTutor/0.1 (local study assistant)"      # Wikimedia asks for a descriptive agent; nothing personal
MAX_W, MAX_BYTES = 720, 220_000
_STOP = {"a", "an", "the", "of", "and", "in", "on", "for", "to", "with", "by", "vs", "its", "how", "what", "basics",
         "introduction", "phase", "rules", "construction", "operation", "properties", "fundamentals"}


def _words(t: str) -> set[str]:
    def stem(w):
        return w[:-1] if len(w) > 3 and w.endswith("s") else w
    return {stem(w) for w in re.findall(r"[a-z0-9]+", (t or "").lower()) if w not in _STOP and len(w) > 1}


def _cache_dir() -> Path:
    from ..config import CFG
    return CFG.home / "tutor" / "pictures"


def _title_ok(title: str, query: str) -> bool:
    """The file title must be ABOUT the concept: every content word, or ≥ 2/3 of them (≥ 2), or its abbreviation
    ('DFA' for 'Deterministic finite automaton (DFA)')."""
    want, have = _words(re.sub(r"\(.*?\)", "", query)), _words(title)
    abbr = {w.lower() for w in re.findall(r"\(([A-Za-z0-9]{2,8})\)", query)}
    if abbr & have:
        return True
    if not want:
        return False
    hit = len(want & have)
    return hit == len(want) or (len(want) >= 3 and hit >= 2 and hit / len(want) >= 0.67)


def search(query: str, *, context: str = "", limit: int = 12, get=None) -> list[dict]:
    """Commons files about `query` (searched with the subject's words, whatever the subject is), best first."""
    import httpx
    get = get or httpx.get
    if not _words(query):
        return []
    q = re.sub(r"[()]", " ", f"{query} {context}").strip()
    r = get(API, params={"action": "query", "format": "json", "generator": "search", "gsrsearch": q,
                         "gsrnamespace": 6, "gsrlimit": limit, "prop": "imageinfo",
                         "iiprop": "url|mime|size|extmetadata", "iiurlwidth": 800},
            headers={"User-Agent": UA}, timeout=8)
    if r.status_code != 200 or "json" not in r.headers.get("content-type", ""):
        raise RuntimeError(f"commons said {r.status_code}")   # rate limit / outage: not cached, tried next time
    pages = (r.json().get("query") or {}).get("pages") or {}
    out = []
    for p in sorted(pages.values(), key=lambda p: p.get("index", 99)):
        ii = (p.get("imageinfo") or [{}])[0]
        if ii.get("mime") not in ("image/png", "image/jpeg", "image/svg+xml", "image/gif"):
            continue
        title = re.sub(r"^File:|\.[a-z0-9]+$", "", p.get("title", ""), flags=re.I)
        if not _title_ok(title, query):
            continue
        w, h = ii.get("thumbwidth") or 0, ii.get("thumbheight") or 0
        if not ii.get("thumburl") or w < 200 or h < 120 or h > 2.2 * w:
            continue
        meta = ii.get("extmetadata") or {}
        lic = (meta.get("LicenseShortName") or {}).get("value") or "free licence"
        desc = re.sub(r"<[^>]+>", " ", (meta.get("ImageDescription") or {}).get("value") or "")
        cats = (meta.get("Categories") or {}).get("value") or ""
        out.append({"title": title, "thumb": ii["thumburl"], "page": ii.get("descriptionurl", ""), "w": w, "h": h,
                    "licence": re.sub(r"<[^>]+>", "", lic)[:30], "about": " ".join(f"{desc} | {cats}".split())[:240]})
    return out


JUDGE_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["pick"],
                "properties": {"pick": {"type": "integer"}}}


def judge(query: str, context: str, hits: list[dict], call=None) -> list[dict]:
    """One quick free-LLM look: which candidate is really a teaching picture of the concept? (a title match alone
    picked a 1979 synthesizer photo for 'Symbol Tables'). No LLM → keep the word-matched order."""
    if not hits:
        return hits
    try:
        from . import planner as P
        call = call or P._call
        lines = "\n".join(f"{i}: {h['title']} — {h['about'][:160]}" for i, h in enumerate(hits[:5]))
        d = call("You pick pictures for a lesson. Answer with JSON only.",
                 f"CONCEPT: {query}\nSUBJECT: {context or 'general'}\nCANDIDATE PICTURES (number: title — description "
                 f"| categories):\n{lines}\nReturn pick = the number of the picture that clearly shows or explains "
                 "this concept in this subject (a diagram, chart or labelled photo a teacher would use), or -1 if "
                 "none does.", JUDGE_SCHEMA, "pick", 60, route="tutor_answer", reasoning="low")
        k = int(d.get("pick", -1))
        return [hits[k]] if 0 <= k < len(hits[:5]) else []
    except Exception:
        return hits


def _shrink(raw: bytes) -> tuple[bytes, str, tuple[int, int]]:
    from PIL import Image
    im = Image.open(io.BytesIO(raw))
    im = im.convert("RGBA") if im.mode in ("P", "LA", "RGBA") else im.convert("RGB")
    if im.width > MAX_W:
        im = im.resize((MAX_W, round(im.height * MAX_W / im.width)), Image.LANCZOS)
    if im.mode == "RGBA":                                # flatten on the board's paper colour
        bg = Image.new("RGB", im.size, (255, 253, 247))
        bg.paste(im, mask=im.split()[3])
        im = bg
    for fmt, kw in (("PNG", {"optimize": True}), ("JPEG", {"quality": 82}), ("JPEG", {"quality": 65})):
        buf = io.BytesIO()
        im.save(buf, fmt, **kw)
        if buf.tell() <= MAX_BYTES or fmt == "JPEG" and kw["quality"] == 65:
            return buf.getvalue(), "image/png" if fmt == "PNG" else "image/jpeg", im.size


def picture(query: str, *, context: str = "", get=None, call=None) -> dict | None:
    """-> {src: data URL, size: (w, h), caption, page} for the best Commons picture of `query`, or None."""
    key = hashlib.sha1(f"{query.strip().lower()}|{context.strip().lower()}".encode()).hexdigest()[:16]
    cache = _cache_dir() / f"{key}.json"
    try:
        d = json.loads(cache.read_text())
        return d or None                                 # {} = looked before, nothing good
    except Exception:
        pass
    found = None
    try:
        import httpx
        hits = search(query, context=context, get=get) or (search(query, get=get) if context else [])
        hits = judge(query, context, hits, call=call)
        for hit in hits[:3]:
            r = (get or httpx.get)(hit["thumb"], headers={"User-Agent": UA}, timeout=10, follow_redirects=True)
            if r.status_code != 200 or len(r.content) < 2000:
                continue
            data, mime, size = _shrink(r.content)
            found = {"src": f"data:{mime};base64," + base64.b64encode(data).decode(), "size": list(size),
                     "caption": f"{hit['title'][:44]} · Wikimedia Commons · {hit['licence']}", "page": hit["page"]}
            break
    except Exception as e:
        print(f"   [pictures] {query!r}: {type(e).__name__}: {str(e)[:100]}")
        return None                                      # network trouble: don't cache, try again next time
    try:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(found or {}))
    except Exception:
        pass
    return found


def picture_op(query: str, *, context: str = "", get=None, call=None):
    """An image Op for the figure slot, or None."""
    from .lesson import Op
    p = picture(query, context=context, get=get, call=call)
    if not p:
        return None
    return Op(type="image", region="figure", text=p["caption"][:80], src=p["src"], size=tuple(p["size"]), at="start")
