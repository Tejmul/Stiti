"""Document ingestion: `stiti ingest <file|folder>` (report §Documents).

Route by type → Markdown (MarkItDown, MIT: pdf/docx/pptx/xlsx/html; md/txt read directly) →
structure-aware chunks of ~300–512 tokens under heading paths → contextual header
(title · section · date) → local embeddings → Postgres (`documents`, `chunks`).
Unchanged files (same sha256) are skipped. Sensitive folders/filenames are P2 (never sent to cloud).
"""
from __future__ import annotations

import hashlib
import re
from datetime import datetime
from pathlib import Path

from .. import embed
from ..config import CFG
from ..db import one, q

EXTS = {".md": "md", ".txt": "txt", ".pdf": "pdf", ".docx": "docx", ".pptx": "pptx", ".xlsx": "xlsx",
        ".html": "html", ".htm": "html", ".csv": "csv"}
P2_PATH = re.compile(r"(bank|tax|salary|medical|health|passport|aadhaar|aadhar|pan|insurance|password|statement)",
                     re.I)
MAX_TOK, MIN_TOK = 450, 60


def _tok(s: str) -> int:
    return len(s) // 4 + 1


def to_markdown(path: Path) -> str:
    if path.suffix.lower() in (".md", ".txt", ".csv"):
        return path.read_text(errors="ignore")
    from markitdown import MarkItDown
    return MarkItDown(enable_plugins=False).convert(str(path)).text_content or ""


def chunk(md: str) -> list[tuple[str, str]]:
    """Split under headings; pack paragraphs to ≤MAX_TOK; returns [(section_path, text)]."""
    out, path, buf = [], [], []

    def flush():
        txt = "\n\n".join(buf).strip()
        if txt:
            out.append((" > ".join(path) or "", txt))
        buf.clear()

    for block in re.split(r"\n\s*\n", md):
        b = block.strip()
        if not b:
            continue
        m = re.match(r"^(#{1,6})\s+(.+)$", b.splitlines()[0])
        if m:
            flush()
            level = len(m.group(1))
            path = path[:level - 1] + [m.group(2).strip()[:60]]
            rest = "\n".join(b.splitlines()[1:]).strip()
            if rest:
                buf.append(rest)
            continue
        if _tok("\n\n".join(buf + [b])) > MAX_TOK and _tok("\n\n".join(buf)) >= MIN_TOK:
            flush()
        while _tok(b) > MAX_TOK:                       # very long paragraph: hard split on sentences
            cut = b[:MAX_TOK * 4].rfind(". ")
            cut = cut + 1 if cut > MAX_TOK else MAX_TOK * 4
            buf.append(b[:cut])
            flush()
            b = b[cut:].strip()
        buf.append(b)
    flush()
    return out


def ingest_file(path: Path, privacy: int | None = None) -> str:
    kind = EXTS.get(path.suffix.lower())
    if not kind:
        return "skip (type)"
    raw = path.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    prev = one("SELECT id, sha256 FROM documents WHERE path=%s", (str(path),))
    if prev and prev["sha256"] == sha:
        return "unchanged"
    md = to_markdown(path)
    if len(md.strip()) < 20 and kind == "pdf":          # scanned PDF → on-device Vision OCR
        from ..connectors.ocr import ocr_pdf
        md = ocr_pdf(path)
    if len(md.strip()) < 20:
        return "skip (no text found, even with OCR)"
    priv = privacy if privacy is not None else (2 if P2_PATH.search(str(path)) else 1)
    mtime = datetime.fromtimestamp(path.stat().st_mtime, CFG.tz)
    title = path.stem.replace("_", " ").replace("-", " ")
    if prev:
        q("DELETE FROM chunks WHERE document_id=%s", (prev["id"],))
        q("UPDATE documents SET sha256=%s, kind=%s, privacy=%s, ingested_at=now(), modified_at=%s WHERE id=%s",
          (sha, kind, priv, mtime, prev["id"]))
        doc_id = prev["id"]
    else:
        doc_id = one("""INSERT INTO documents(path, title, kind, sha256, privacy, modified_at)
                        VALUES (%s,%s,%s,%s,%s,%s) RETURNING id""", (str(path), title, kind, sha, priv, mtime))["id"]
    parts = chunk(md)
    for i in range(0, len(parts), 16):
        batch = parts[i:i + 16]
        headers = [f"{title} · {sec or 'main'} · {mtime:%Y-%m-%d}" for sec, _ in batch]
        vecs = embed.embed_docs([f"{h}\n{t}" for h, (_, t) in zip(headers, batch)])
        for j, ((sec, txt), h, v) in enumerate(zip(batch, headers, vecs)):
            q("""INSERT INTO chunks(document_id, ord, section, header, text, privacy, embedding, embed_model)
                 VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""", (doc_id, i + j, sec, h, txt, priv, v, embed.EMBED_MODEL))
    return f"{'updated' if prev else 'added'}: {len(parts)} chunks (P{priv})"


def ingest(target: str, privacy: int | None = None, verbose: bool = True) -> dict:
    root = Path(target).expanduser().resolve()
    files = [root] if root.is_file() else sorted(p for p in root.rglob("*")
                                                  if p.is_file() and p.suffix.lower() in EXTS
                                                  and not any(part.startswith(".") for part in p.parts))
    stats: dict[str, int] = {}
    for f in files:
        try:
            r = ingest_file(f, privacy)
        except Exception as e:
            r = f"error: {type(e).__name__}: {str(e)[:80]}"
        key = r.split(":")[0]
        stats[key] = stats.get(key, 0) + 1
        if verbose:
            print(f"  {r:40} {f}")
    return stats


def recall(text: str, qvec, max_privacy: int = 1, k: int = 4) -> list[dict]:
    from .memory import tsquery_text
    return [r for r in q("SELECT * FROM recall_chunks(to_tsquery('simple', %s), %s, %s::smallint, %s)",
                         (tsquery_text(text), qvec, max_privacy, k)) if r["sim"] >= 0.3]
