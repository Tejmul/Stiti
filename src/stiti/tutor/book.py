"""Book → teachable outline + compact page-cited sources, all local (research §6, D14).

Structure comes from the FILE, never the LLM, and the free LLM never sees the whole book
(Aho's Compilers ≈ 538K tokens > Groq's 200K/day):
  PDF : pypdfium2 (Apache/BSD) — TOC if present; page labels, else the printed page number from the
        running head ("8 CHAPTER 1. INTRODUCTION"); no TOC → numbered-heading detection ("1.2.2 Syntax
        Analysis", "Chapter 3"), kept in increasing order so the book's own contents pages don't fool it.
  EPUB/DOCX/MD: MarkItDown (MIT) → Markdown headings.
  Sources for one chapter/section: local extractive compression with Stiti's embedder (centrality) →
  ~45 sentences (~3K tokens), each tagged with its printed page, so citations can be checked in code.
AGPL libraries (PyMuPDF, EbookLib) are deliberately not used.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

NUM_HEAD = re.compile(r"^(\d{1,2}(?:\.\d{1,2}){0,2})\.?\s+([A-Z][^\n]{2,70}?)\s*$")
CHAP_HEAD = re.compile(r"^Chapter\s+(\d{1,2})\s*$", re.I)
LEADER = re.compile(r"(\.\s?){3,}|\s\d+\s*$")


@dataclass
class Section:
    num: str
    title: str
    level: int
    page: int                  # 0-based page index
    label: str                 # printed page number
    end: int = 0               # exclusive page index

    @property
    def name(self) -> str:
        return f"{self.num} {self.title}".strip()


@dataclass
class Book:
    path: Path
    title: str
    pages: list[str] = field(default_factory=list)
    labels: list[str] = field(default_factory=list)
    sections: list[Section] = field(default_factory=list)

    def chapters(self) -> list[Section]:
        return [s for s in self.sections if s.level == 1]

    def find(self, query: str) -> Section | None:
        """'3', '3.4', 'chapter 3', or words from a title."""
        q = query.lower().replace("chapter", "").strip()
        for s in self.sections:
            if s.num == q:
                return s
        hits = [s for s in self.sections if q and q in s.title.lower()]
        return hits[0] if hits else None


def _printed_label(text: str, i: int) -> str:
    first = text.strip().split("\n", 1)[0].strip() if text.strip() else ""
    m = re.match(r"^(\d{1,4})\s+\S", first) or re.search(r"\S\s+(\d{1,4})$", first)
    return m.group(1) if m else str(i + 1)


def _num_key(num: str) -> tuple[int, ...]:
    return tuple(int(x) for x in num.split("."))


def load_pdf(path: Path) -> Book:
    import pypdfium2 as pdfium
    pdf = pdfium.PdfDocument(str(path))
    pages = [pdf[i].get_textpage().get_text_bounded().replace("\r", "").replace("\x02", "") for i in range(len(pdf))]
    labels = []
    for i in range(len(pdf)):
        try:
            lab = pdf.get_page_label(i)
        except Exception:
            lab = ""
        labels.append(lab or _printed_label(pages[i], i))
    if not any(lab and not lab.isdigit() for lab in labels[:5]):      # no real page labels in the file:
        off = _page_offset(labels)                                     # printed number = index − offset
        labels = [str(i - off) if i - off >= 1 else f"front {i + 1}" for i in range(len(pages))]
    book = Book(path=path, title=path.stem, pages=pages, labels=labels)
    toc = []
    try:
        toc = list(pdf.get_toc())
    except Exception:
        pass
    if not toc:
        book.sections = parse_contents(pages, labels)
    if toc:
        for it in toc:
            pi = getattr(it, "page_index", None)
            if pi is None:
                continue
            title = getattr(it, "title", None) or it.get_title()
            m = re.match(r"^(\d+(?:\.\d+)*)\s+(.*)", title)
            book.sections.append(Section(m.group(1) if m else "", m.group(2) if m else title,
                                         getattr(it, "level", 0) + 1, pi, labels[pi]))
    if not book.sections:
        book.sections = detect_headings(pages, labels)
    _close(book)
    return book


CONTENTS_LINE = re.compile(r"^(\d{1,2}(?:\.\d{1,2}){0,2}|[A-Z](?:\.[0-9l]{1,2}){0,2})\s+(.+?)\s+(\d{1,4})$")


def _page_offset(labels: list[str]) -> int:
    """PDF index − printed page number, from pages whose running head shows a number (median)."""
    diffs = sorted(i - int(lab) for i, lab in enumerate(labels) if lab.isdigit() and 0 < int(lab) < len(labels))
    return diffs[len(diffs) // 2] if diffs else 0


def parse_contents(pages: list[str], labels: list[str], scan: int = 40) -> list[Section]:
    """Use the book's own printed Contents ('3.1 The Role of the Lexical Analyzer ..... 109')."""
    off = _page_offset(labels)
    out: list[Section] = []
    last_page = 0
    for text in pages[:scan]:
        for ln in text.split("\n"):
            ln = ln.strip()
            m = CONTENTS_LINE.match(ln)
            if not m:
                continue
            num, title, pg = m.group(1).replace("l", "1"), m.group(2), int(m.group(3))
            title = re.sub(r"\s*(\.\s?){2,}\s*", " ", title).strip(" .")
            if not title or sum(c.isalpha() for c in title) < 3 or pg < last_page or pg > len(pages):
                continue
            idx = pg + off
            if not 0 <= idx < len(pages):
                continue
            last_page = pg
            level = 1 if "." not in num else num.count(".") + 1
            if level == 1 and re.match(r"^[lI1]?\s?\d", title):
                continue                                              # OCR glitch: "11 l 1.3 Vector…"
            out.append(Section(num, title[:70], level, idx, labels[idx]))
    return out if len(out) >= 8 else []


def detect_headings(pages: list[str], labels: list[str]) -> list[Section]:
    out: list[Section] = []
    last: dict[int, tuple[int, ...]] = {}
    chap_seen: set[str] = set()
    for i, text in enumerate(pages):
        lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
        for j, ln in enumerate(lines[:60]):
            if j == 0 and not CHAP_HEAD.match(ln) and (_printed_label(text, i) in ln.split()):
                continue                                      # running head
            m = CHAP_HEAD.match(ln)
            if m and j + 1 < len(lines) and m.group(1) not in chap_seen:
                num = m.group(1)
                if not out or _num_key(num) > last.get(1, (0,)):
                    chap_seen.add(num)
                    last = {1: _num_key(num)}
                    out.append(Section(num, lines[j + 1][:70], 1, i, labels[i]))
                continue
            m = NUM_HEAD.match(ln)
            if not m or LEADER.search(ln) or ln.isupper() or len(ln) > 80:
                continue
            num, title = m.group(1), m.group(2).strip()
            if title.endswith((".", ",", ";", ":")) or sum(c.isalpha() for c in title) < 3:
                continue
            key = _num_key(num)
            level = len(key)
            if level == 1:
                continue                                       # "3 Something" is usually a list item
            parent = last.get(level - 1)
            if parent is None or key[:-1] != parent:
                continue                                       # must sit inside the current chapter/section
            if key <= last.get(level, (0,) * level):
                continue                                       # keep the book's order (skips its contents pages)
            last[level] = key
            for deeper in [k for k in last if k > level]:
                del last[deeper]
            out.append(Section(num, title, level, i, labels[i]))
    return out


def _close(book: Book) -> None:
    secs = book.sections
    for k, s in enumerate(secs):
        nxt = next((t.page for t in secs[k + 1:] if t.level <= s.level), len(book.pages))
        s.end = max(s.page + 1, nxt)


def load_markdown(path: Path) -> Book:
    from ..brain.ingest import to_markdown
    md = to_markdown(path)
    book = Book(path=path, title=path.stem, pages=[md], labels=["1"])
    for m in re.finditer(r"^(#{1,3})\s+(.+)$", md, re.M):
        book.sections.append(Section("", m.group(2).strip()[:70], len(m.group(1)), 0, "1"))
    _close(book)
    return book


def load(path: str | Path) -> Book:
    p = Path(path).expanduser()
    return load_pdf(p) if p.suffix.lower() == ".pdf" else load_markdown(p)


def outline_text(book: Book, max_level: int = 2) -> str:
    lines = [f"{book.title} — {len(book.pages)} pages, {len(book.sections)} headings found"]
    for s in book.sections:
        if s.level <= max_level:
            lines.append(f"{'  ' * (s.level - 1)}{s.name}  (p. {s.label}–{book.labels[min(s.end, len(book.labels)) - 1]})")
    return "\n".join(lines)


_SENT = re.compile(r"(?<=[.!?])\s+(?=[A-Z(])")


def sources_for(book: Book, sec: Section, n: int = 45, max_pages: int = 60) -> list[dict]:
    """Extractive compression: the ~n most central sentences of a section, in book order, page-tagged."""
    import numpy as np

    from .. import embed
    sents: list[tuple[int, str]] = []
    for i in range(sec.page, min(sec.end, sec.page + max_pages)):
        body = book.pages[i].split("\n", 1)[1] if "\n" in book.pages[i] else book.pages[i]
        body = re.sub(r"-\n(?=[a-z])", "", body).replace("\n", " ")
        for s in _SENT.split(body):
            s = re.sub(r"\s+", " ", s).strip()
            if 40 <= len(s) <= 320 and sum(c.isalpha() for c in s) > len(s) * 0.6:
                sents.append((i, s))
    if not sents:
        return []
    if len(sents) > 400:                                     # bound embedding time (~1–2 s)
        step = len(sents) / 400
        sents = [sents[int(k * step)] for k in range(400)]
    vecs = np.concatenate([embed._embed([s for _, s in sents[b:b + 32]]) for b in range(0, len(sents), 32)])
    centre = vecs.mean(axis=0)
    score = vecs @ centre
    score[: min(3, len(score))] += 1.0                       # a section's opening lines define it
    keep = sorted(np.argsort(score)[::-1][:n])
    return [{"page": book.labels[sents[k][0]], "text": sents[k][1]} for k in keep]
