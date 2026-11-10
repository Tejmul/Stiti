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
    scanned: bool = False         # no text layer: pages are OCR'd on demand (ensure_text)

    def chapters(self) -> list[Section]:
        return [s for s in self.sections if s.level == 1]

    def find(self, query: str) -> Section | None:
        """'3', '3.4', 'chapter 3', or words from a title."""
        q = query.lower().replace("chapter", "").strip()
        for s in self.sections:
            if s.num == q or (s.level == 1 and s.num and _numkey(s.num) == _numkey(q.upper())):
                return s
        hits = [s for s in self.sections if q and q in s.title.lower()]
        # "lexical analysis" → Chapter 3 "Lexical Analysis", not §1.2.1: exact title first, then the biggest unit
        hits.sort(key=lambda s: (s.title.lower().strip() != q, s.level, s.page))
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
    if sum(len(t.strip()) < 80 for t in pages) > 0.6 * len(pages):     # scanned book: no text layer
        book.scanned = True
        ensure_text(book, 0, min(30, len(pages)))                      # front matter → its Contents page
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
        book.sections = detect_headings(book.pages, labels)
    if not book.sections:
        book.sections = _even_units(book)
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


TEXT_PAGE_CHARS = 2500       # non-PDF books are cut into ~1-page chunks so sections and citations still work
_ROMAN = r"[IVXLCDM]{1,7}"
_WORDNUM = r"(?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|" \
           r"sixteen|seventeen|eighteen|nineteen|twenty|first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth)"
# "Chapter 4", "CHAPTER IV. TITLE", "Part Two: …", "Lesson 3 - …"  (keyword case-insensitive)
KW_HEAD = re.compile(rf"^(?:#{{1,3}}\s+)?(?i:chapter|book|part|lesson|unit|lecture)\s+(?i:\d{{1,3}}|{_ROMAN}|{_WORDNUM})"
                     rf"\b[.:]?(?:\s*[-—:.]?\s*(?P<t>[^\n]{{0,80}}))?\s*$")
# "XII. PRIMITIVE THOUGHT" — Roman numeral + an ALL-CAPS title (uppercase only, so words like "did" never match)
RN_HEAD = re.compile(rf"^(?:#{{1,3}}\s+)?(?P<rn>{_ROMAN})\.?\s+(?P<t>[A-Z][A-Z ,;'’&-]{{3,80}}?)\.?(?:\s+\d{{1,4}})?\s*$")
RN_ALONE = re.compile(rf"^(?P<rn>{_ROMAN})\.?\s*$")         # "I" alone, title on the next line
GB_START = re.compile(r"START OF (?:THE|THIS) PROJECT GUTENBERG[^\n]*", re.I)
GB_END = re.compile(r"[*\\ ]*END OF (?:THE|THIS) PROJECT GUTENBERG", re.I)


def _roman_int(r: str) -> int:
    v = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}
    n = 0
    for a, b in zip(r, r[1:] + " "):
        n += -v[a] if b in v and v[b] > v[a] else v[a]
    return n


def _numkey(num: str) -> str:
    return str(_roman_int(num.upper())) if re.fullmatch(_ROMAN, num.upper() or "-") else num


def _core(title: str) -> str:
    """Comparable title: no 'Chapter IV —', numbering, punctuation or page numbers."""
    t = re.sub(rf"^(?i:chapter|book|part|lesson|unit|lecture)\s+\S+\s*[-—:.]?\s*", "", title.strip())
    t = re.sub(rf"^({_ROMAN}|\d+)\.?\s+", "", t)
    return re.sub(r"[^a-z ]", "", t.lower()).strip()


def _text_pages(text: str) -> tuple[list[str], list[int]]:
    """Cut at paragraph breaks into ~TEXT_PAGE_CHARS pages; returns (pages, char offset where each page starts)."""
    pages, starts, buf, start, pos = [], [], [], 0, 0
    for para in re.split(r"(\n\s*\n)", text):
        if buf and sum(map(len, buf)) + len(para) > TEXT_PAGE_CHARS and para.strip():
            pages.append("".join(buf)); starts.append(start)
            buf, start = [], pos
        buf.append(para)
        pos += len(para)
    if buf:
        pages.append("".join(buf)); starts.append(start)
    return pages, starts


def load_text(path: Path) -> Book:
    """Any text-like book (txt, md, epub, docx, html, pptx…): pseudo-pages + headings in many styles."""
    from bisect import bisect_right

    from ..brain.ingest import to_markdown
    text = to_markdown(path).replace("\r", "")
    if (m := GB_START.search(text)):                         # drop Project Gutenberg licence header/footer
        text = text[m.end():]
    if (m := GB_END.search(text)):
        text = text[:m.start()]
    pages, starts = _text_pages(text)
    book = Book(path=path, title=path.stem, pages=pages, labels=[str(i + 1) for i in range(len(pages))])
    lines = [(m.start(), m.group().strip()) for m in re.finditer(r"^[^\n]*$", text, re.M)]
    found: list[tuple[int, str]] = []
    for k, (off, line) in enumerate(lines):
        if not line or len(line) > 100:
            continue
        nxt = next((ln for _, ln in lines[k + 1:k + 4] if ln), "").strip(" #*_.")
        if (h := KW_HEAD.match(line)):
            t = (h.group("t") or "").strip(" .:-—#")
            title = f"{line.strip('# ').rstrip('.')} — {nxt}" if not t and 3 <= len(nxt) <= 80 else line.strip("# ")
        elif (h := RN_HEAD.match(line)):
            title = f"{h.group('rn')}. {h.group('t').strip()}"
        elif RN_ALONE.match(line) and nxt.isupper() and 3 <= len(nxt) <= 80:
            title = f"{line.rstrip('.')}. {nxt}"
        else:
            continue
        found.append((off, title[:80]))
    md_heads = [(m.start(), m.group(2).strip()[:80]) for m in re.finditer(r"^#{1,2}\s+(.+)$", text, re.M)
                for _ in [0]] if False else [(m.start(), m.group(1).strip()[:80])
                                             for m in re.finditer(r"^#{1,2}\s+(.+)$", text, re.M)]
    heads = found if len(found) >= 3 else md_heads           # chapter-style lines beat generic markdown headings
    numof = lambda t: (m.group(1) if (m := re.match(rf"^(?i:chapter\s+)?({_ROMAN}|\d+)\b", t)) else "")  # noqa
    last: dict[str, int] = {}
    for k, (_, title) in enumerate(heads):                   # a CONTENTS list repeats every chapter: keep the last
        last[_core(title)] = k
        if numof(title):
            last["#" + _numkey(numof(title))] = k
    for k, (off, title) in enumerate(heads):
        core, num = _core(title), numof(title)
        if num and last.get("#" + _numkey(num)) != k:
            continue
        if last[core] != k or not core or re.fullmatch(r"(contents|table of contents|index|illustrations|list of .*|"
                                                       r"preface|footnotes|transcribers note.*)", core):
            continue
        pg = max(0, bisect_right(starts, off) - 1)
        clean = re.sub(rf"^(?i:chapter\s+)?({_ROMAN}|\d+)\b\s*[.:—-]*\s*", "", title).strip() or title
        book.sections.append(Section(num, clean.title() if clean.isupper() else clean, 1, pg, book.labels[pg]))
    if not book.sections:
        book.sections = _even_units(book)
    _close(book)
    return book


def _even_units(book: Book, size: int = 12) -> list[Section]:
    """Last resort for books with no detectable structure: ~size-page units named by their first real line."""
    out = []
    for i in range(0, len(book.pages), size):
        first = next((ln.strip() for ln in book.pages[i].splitlines() if len(ln.strip()) > 12), "")
        end = book.labels[min(i + size, len(book.pages)) - 1]
        out.append(Section("", f"Part {len(out) + 1}: {first[:50]}" if first else f"Pages {book.labels[i]}–{end}",
                           1, i, book.labels[i]))
    return out


def _ocr_page(path: Path, i: int, scale: float = 2.0) -> str:
    """On-device OCR (Apple Vision) of one PDF page — for scanned books with no text layer."""
    import Quartz
    from Foundation import NSURL

    from ..connectors.ocr import _recognize
    doc = Quartz.CGPDFDocumentCreateWithURL(NSURL.fileURLWithPath_(str(path)))
    page = Quartz.CGPDFDocumentGetPage(doc, i + 1)
    box = Quartz.CGPDFPageGetBoxRect(page, Quartz.kCGPDFMediaBox)
    w, h = int(box.size.width * scale), int(box.size.height * scale)
    ctx = Quartz.CGBitmapContextCreate(None, w, h, 8, 0, Quartz.CGColorSpaceCreateDeviceRGB(),
                                       Quartz.kCGImageAlphaPremultipliedLast)
    Quartz.CGContextSetRGBFillColor(ctx, 1, 1, 1, 1)
    Quartz.CGContextFillRect(ctx, Quartz.CGRectMake(0, 0, w, h))
    Quartz.CGContextScaleCTM(ctx, scale, scale)
    Quartz.CGContextDrawPDFPage(ctx, page)
    return _recognize(Quartz.CGBitmapContextCreateImage(ctx))


def ensure_text(book: Book, start: int, end: int) -> None:
    """Scanned PDF: OCR the pages of [start, end) that have no text yet (lazy, cached in book.pages)."""
    if not book.scanned:
        return
    for i in range(start, min(end, len(book.pages))):
        if len(book.pages[i].strip()) < 80:
            try:
                book.pages[i] = _ocr_page(book.path, i)
            except Exception:
                pass


def load(path: str | Path) -> Book:
    p = Path(path).expanduser()
    return load_pdf(p) if p.suffix.lower() == ".pdf" else load_text(p)


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
    ensure_text(book, sec.page, min(sec.end, sec.page + max_pages))
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
