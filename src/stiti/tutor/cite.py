"""Cited answers + "your file doesn't cover this" (feature 2; research/apps/notebooklm.md "Techniques for Stiti").

His study file is cut into page-tagged chunks in Postgres (doc_chunks: page label, char span, full-text + pgvector).
A doubt is answered like this, all local until the last step:
  1. answer bank: the same doubt about the same file was answered before → that answer, no LLM call
  2. one hybrid SQL (ts_rank_cd over an OR-query + cosine) ranks the file's chunks, < 100 ms
  3. score gate: the best chunk is too weak → "your notes don't cover that" BEFORE any LLM call (he can still ask
     for a general answer); a half-built index never claims that (it may just not have reached the page yet)
  4. the top passages go to the free LLM as numbered SOURCES; it must return a verbatim quote + page per claim
  5. verify_quotes keeps only quotes whose words appear, in order, in a retrieved passage (case, whitespace,
     line-break hyphenation and punctuation ignored) — a fabricated quote is never shown or said.
Privacy: the file's text stays in this Mac's Postgres; only the 3–4 passages for one doubt go to the free LLM.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

CHUNK_MIN, CHUNK_MAX = 400, 800        # chars, sentence-aligned, never across a page (one page label per chunk)
EMBED_BATCH = 16
# Calibrated on EmbeddingGemma-300M (q4) with a fake textbook + off-topic questions (tests/cite_eval.py): on-topic
# doubts score ≥ ~0.55 cosine on their passage, off-topic ones ≤ ~0.42. A keyword hit lowers the bar a little.
GATE_COS = 0.50                        # covered when a passage's cosine is at least this …
GATE_COS_KW = 0.33                     # … or at least this AND it holds most of the question's words:
GATE_COVER = 0.6                       #     share of the question's stemmed words found in the passage
LEX_W, COVER_W = 0.25, 0.15            # rank = cosine + LEX_W · ts_rank_cd (0..1) + COVER_W · cover
BANK_SIM = 0.93                        # same doubt (query-vs-query cosine) → the saved answer
MIN_QUOTE_WORDS = 4
SPOKEN_QUOTE_WORDS = 28                # longer verified quotes are shown on the card but not read out in full

_WORD = re.compile(r"\w+(?:-\s*\n\s*\w+)*(?:['’]\w+)?")
_SENT_END = re.compile(r"(?<=[.!?:;])[\"')\]]*\s+(?=[\"'(\[]?[A-Z0-9])|\n\s*\n")


def source_key(path: str | Path) -> str:
    return hashlib.sha1(str(Path(path).expanduser().resolve()).encode()).hexdigest()[:20]


def clean(text: str) -> str:
    """Display / LLM text: line-break hyphenation joined ("compi-\\nler" → "compiler"), whitespace collapsed."""
    return re.sub(r"\s+", " ", re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", text)).strip()


# ------------------------------------------------------------------------------------------------ chunking
def _spans(text: str) -> list[tuple[int, int, bool]]:
    """Sentence spans of one page: (start, end, starts_a_paragraph), char offsets into the raw page text."""
    out, start, para = [], 0, True
    for m in _SENT_END.finditer(text):
        if m.start() > start:
            out.append((start, m.start(), para))
        start, para = m.end(), "\n\n" in re.sub(r"[ \t]+", "", m.group())
    if start < len(text):
        out.append((start, len(text), para))
    fixed = []
    for a, b, pa in out:                               # a "sentence" longer than a chunk: cut at a space
        while b - a > CHUNK_MAX:
            cut = text.rfind(" ", a + CHUNK_MIN, a + CHUNK_MAX)
            cut = cut if cut > a else a + CHUNK_MAX
            fixed.append((a, cut, pa))
            a, pa = cut + 1, False
        fixed.append((a, b, pa))
    return [(a, b, pa) for a, b, pa in fixed if text[a:b].strip()]


def chunk_page(text: str) -> list[tuple[int, int]]:
    """~400–800-char chunks of whole sentences, cut at a paragraph break once a chunk has CHUNK_MIN chars (one idea
    per chunk keeps its embedding sharp) and always before a heading (a chunk never spans two units):
    [(char_start, char_end)] into the page text."""
    from .book import _is_heading
    chunks: list[tuple[int, int, bool]] = []          # (start, end, starts with a heading)
    cur: tuple[int, int, bool] | None = None
    for a, b, para in _spans(text):
        head = para and _is_heading(text[a:b])
        if cur is None:
            cur = (a, b, head)
        elif head or (para and cur[1] - cur[0] >= CHUNK_MIN) or b - cur[0] > CHUNK_MAX:
            chunks.append(cur)
            cur = (a, b, head)
        else:
            cur = (cur[0], b, cur[2])
    if cur is not None:
        if (chunks and not cur[2] and cur[1] - cur[0] < CHUNK_MIN // 2
                and cur[1] - chunks[-1][0] <= CHUNK_MAX + CHUNK_MIN // 2):
            chunks[-1] = (chunks[-1][0], cur[1], chunks[-1][2])     # a short tail joins the chunk before it
        else:
            chunks.append(cur)
    out = []
    for a, b, _ in chunks:
        while a < b and text[a].isspace():
            a += 1
        while b > a and text[b - 1].isspace():
            b -= 1
        if sum(c.isalpha() for c in text[a:b]) >= 30:
            out.append((a, b))
    return out


def _unit_starts(book) -> list[tuple[int, int, str]]:
    """(page index, char offset of its heading in that page, name) per unit — a unit can start mid-page."""
    out = []
    for s in book.chapters() or book.sections:
        page = book.pages[s.page] if s.page < len(book.pages) else ""
        off = page.lower().find(s.title.lower()) if s.title else -1
        out.append((s.page, max(0, off), s.name[:60]))
    return sorted(out)


def _unit_at(starts: list[tuple[int, int, str]], i: int, end: int) -> str:
    name = ""
    for pg, off, nm in starts:
        if (pg, off) < (i, end):
            name = nm
    return name


def _page_chunks(book, i: int, starts) -> list[dict]:
    page = book.pages[i]
    label = str(book.labels[i] if i < len(book.labels) else i + 1)
    return [{"page_index": i, "page_label": label, "unit": _unit_at(starts, i, b), "char_start": a, "char_end": b,
             "text": page[a:b]} for a, b in chunk_page(page)]


def chunk_book(book) -> list[dict]:
    """Every page → chunks with page label, page index, unit and char span (pure; no DB, no embedder)."""
    starts = _unit_starts(book)
    return [c for i in range(len(book.pages)) for c in _page_chunks(book, i, starts)]


# ------------------------------------------------------------------------------------------------ indexing
def _stat(path: Path) -> tuple[float, int]:
    st = path.stat()
    return round(st.st_mtime, 3), st.st_size


def indexed(path: str | Path) -> dict | None:
    """The doc_sources row when the file is indexed and unchanged (same mtime, size and embedder), else None."""
    from .. import embed
    from ..db import one
    p = Path(path).expanduser()
    mtime, size = _stat(p)
    row = one("SELECT * FROM doc_sources WHERE source_key=%s", (source_key(p),))
    if row and abs(row["mtime"] - mtime) < 0.01 and row["size"] == size and row["embed_model"] == embed.EMBED_MODEL:
        return row
    return None


def index_book(path: str | Path, *, priority: str | None = None, log=print, book=None,
               stop: threading.Event | None = None) -> dict:
    """Index (or re-index when the file changed) one file. Pages of the `priority` section go first, so a doubt
    about the lesson's own chapter can be cited within seconds while the rest of a big book follows.
    -> the doc_sources row. Idempotent and resumable: an unchanged, complete file costs one SELECT."""
    from .. import embed
    from ..db import conn, one, q
    from . import book as B
    p = Path(path).expanduser()
    key = source_key(p)
    mtime, size = _stat(p)
    row = one("SELECT * FROM doc_sources WHERE source_key=%s", (key,))
    fresh = (row and abs(row["mtime"] - mtime) < 0.01 and row["size"] == size
             and row["embed_model"] == embed.EMBED_MODEL)
    if fresh and (row["complete"] or row["outline"]):
        return row
    t0 = time.time()
    book = book or B.load(p)
    outline = B.is_outline(book)
    if not fresh:                                     # new or changed file: old chunks + banked answers go
        q("DELETE FROM doc_sources WHERE source_key=%s", (key,))
        q("""INSERT INTO doc_sources(source_key, path, mtime, size, pages, outline, complete, embed_model)
             VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
          (key, str(p), mtime, size, len(book.pages), outline, outline, embed.EMBED_MODEL))
    if outline:                                       # a topic list: nothing to quote (coach teaches it generally)
        q("UPDATE doc_sources SET outline=true, complete=true WHERE source_key=%s", (key,))
        return one("SELECT * FROM doc_sources WHERE source_key=%s", (key,))
    done = {r["page_index"] for r in q("SELECT DISTINCT page_index FROM doc_chunks WHERE source_key=%s", (key,))}
    order = list(range(len(book.pages)))
    sec = book.find(priority) if priority and priority != "all" else None
    if sec is not None:
        first = list(range(sec.page, min(sec.end, len(book.pages))))
        order = first + [i for i in order if i not in set(first)]
    pending: list[dict] = []
    starts = _unit_starts(book)

    def flush():
        if not pending:
            return
        vecs = embed.embed_docs([clean(c["text"])[:2000] for c in pending])
        with conn().cursor() as cur:
            cur.executemany("""INSERT INTO doc_chunks(source_key, path, page_label, page_index, unit, char_start,
                                                      char_end, text, embedding)
                               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
                            [(key, str(p), c["page_label"], c["page_index"], c["unit"], c["char_start"],
                              c["char_end"], c["text"], v) for c, v in zip(pending, vecs)])
        pending.clear()

    for i in order:
        if stop is not None and stop.is_set():
            break
        if i in done:
            continue
        B.ensure_text(book, i, i + 1)                 # scanned PDF: OCR this page on demand
        pending += _page_chunks(book, i, starts)
        if len(pending) >= EMBED_BATCH:
            flush()
    flush()
    n = one("SELECT count(*) AS n FROM doc_chunks WHERE source_key=%s", (key,))["n"]
    complete = not (stop is not None and stop.is_set())
    q("UPDATE doc_sources SET chunks=%s, complete=%s, indexed_at=now() WHERE source_key=%s", (n, complete, key))
    log(f"   [cite] indexed {p.name}: {n} chunks from {len(book.pages)} pages in {time.time() - t0:.1f}s")
    return one("SELECT * FROM doc_sources WHERE source_key=%s", (key,))


# ------------------------------------------------------------------------------------------------ retrieval
@dataclass
class Passage:
    id: int
    page: str
    unit: str
    text: str                  # clean display text of the chunk
    char_start: int
    char_end: int
    page_index: int
    cos: float
    lex: float
    cover: float
    score: float

    def ref(self) -> str:
        return f"p. {self.page}" + (f" · {self.unit}" if self.unit else "")


@dataclass
class Retrieval:
    covered: bool | None       # True / False; None = can't tell (index still being built, or no file to cite)
    passages: list[Passage] = field(default_factory=list)
    top: float = 0.0
    ms: float = 0.0


HYBRID_SQL = """
WITH q AS (SELECT %(v)s::halfvec(768) AS v,
                  NULLIF(replace(plainto_tsquery('english', %(t)s)::text, ' & ', ' | '), '')::tsquery AS t,
                  tsvector_to_array(to_tsvector('english', %(t)s)) AS words),
cand AS (
  (SELECT c.id FROM doc_chunks c WHERE c.source_key = %(k)s
   ORDER BY (c.embedding <=> (SELECT v FROM q))::float8 LIMIT 40)
  UNION
  (SELECT c.id FROM doc_chunks c, q WHERE c.source_key = %(k)s AND q.t IS NOT NULL AND c.tsv @@ q.t
   ORDER BY ts_rank_cd(c.tsv, q.t, 32) DESC LIMIT 40)
), scored AS (
  SELECT c.id, c.page_label, c.page_index, c.unit, c.char_start, c.char_end, c.text,
         1 - (c.embedding <=> q.v) AS cos,
         COALESCE(CASE WHEN q.t IS NOT NULL THEN ts_rank_cd(c.tsv, q.t, 32) END, 0) AS lex,
         COALESCE((SELECT count(*) FROM unnest(q.words) w WHERE w = ANY(tsvector_to_array(c.tsv)))::float8
                  / NULLIF(cardinality(q.words), 0), 0) AS cover
  FROM doc_chunks c JOIN cand USING (id), q
)
SELECT *, cos + %(w)s * lex + %(wc)s * cover AS score FROM scored ORDER BY score DESC LIMIT %(n)s
"""


def gate(p: Passage | None) -> bool:
    """Does this passage really speak to the question? Meaning (cosine) alone, or a weaker meaning match that also
    holds most of the question's own words ("why strip comments" → the passage that strips comments)."""
    if p is None:
        return False
    return p.cos >= GATE_COS or (p.cos >= GATE_COS_KW and p.cover >= GATE_COVER)


def retrieve(question: str, key: str, k: int = 4, *, qvec=None, complete: bool = True) -> Retrieval:
    """One hybrid SQL over this file's chunks → the top k passages + the gate's verdict."""
    from .. import embed
    from ..db import q
    t0 = time.perf_counter()
    v = qvec if qvec is not None else embed.embed_query(question)
    rows = q(HYBRID_SQL, {"v": v, "t": question[:300], "k": key, "w": LEX_W, "wc": COVER_W, "n": max(k, 1) + 2})
    ps = [Passage(r["id"], r["page_label"], r["unit"] or "", clean(r["text"]), r["char_start"], r["char_end"],
                  r["page_index"], float(r["cos"]), float(r["lex"]), float(r["cover"]), float(r["score"]))
          for r in rows]
    ok = any(gate(p) for p in ps)
    covered: bool | None = True if ok else (False if complete else None)
    keep = [p for p in ps if gate(p) or p.cos >= GATE_COS - 0.1 or p.cover >= 0.5][:k] if ok else []
    return Retrieval(covered, keep, ps[0].score if ps else 0.0, (time.perf_counter() - t0) * 1000)


# ------------------------------------------------------------------------------------------------ verification
def _tokens(text: str) -> list[tuple[str, int, int]]:
    out = []
    for m in _WORD.finditer(text):
        w = re.sub(r"-\s*\n\s*", "", m.group()).replace("’", "'").lower()
        out.append((w, m.start(), m.end()))
    return out


def _find(words: list[str], toks: list[tuple[str, int, int]], start: int = 0) -> tuple[int, int] | None:
    n = len(words)
    for i in range(start, len(toks) - n + 1):
        if all(toks[i + j][0] == words[j] for j in range(n)):
            return i, i + n
    return None


def locate(quote: str, text: str) -> tuple[int, int] | None:
    """Char span of `quote` inside `text` when its words appear there verbatim and in order (case, whitespace,
    line-break hyphenation and punctuation ignored; "…" in the quote may skip words between its parts)."""
    parts = [pt for pt in re.split(r"\s*(?:\.\.\.|…|\[\.\.\.\])\s*", quote) if pt.strip()]
    toks = _tokens(text)
    if not parts or not toks:
        return None
    pos, first, last = 0, None, None
    for pt in parts:
        words = [w for w, _, _ in _tokens(pt)]
        if not words:
            continue
        if len(parts) > 1 and len(words) < 3:
            return None                                # "the … of" is not a quote
        hit = _find(words, toks, pos)
        if hit is None:
            return None
        first = hit[0] if first is None else first
        last, pos = hit[1], hit[1]
    if first is None:
        return None
    return toks[first][1], toks[last - 1][2]


def verify_quotes(quotes: list[dict] | None, passages: list[Passage]) -> list[dict]:
    """Keep only quotes found verbatim in a retrieved passage; the page and unit come from THAT passage (never the
    LLM's word). -> [{quote, page, unit, passage, q_start, q_end, chunk_id}] (q_* = span in `passage`)."""
    out, seen = [], set()
    for qd in quotes or []:
        if not isinstance(qd, dict):
            continue
        quote = str(qd.get("quote") or "").strip().strip("\"'“”‘’ ")
        if len(_tokens(quote)) < MIN_QUOTE_WORDS:
            continue
        claimed = re.sub(r"^(p|pp|page)\.?\s*", "", str(qd.get("page") or "").strip(), flags=re.I)
        hits = [(p, sp) for p in passages if (sp := locate(quote, p.text))]
        if not hits:
            continue
        p, (a, b) = next(((p, sp) for p, sp in hits if p.page == claimed), hits[0])
        exact = p.text[a:b]
        if exact.lower() in seen:
            continue
        seen.add(exact.lower())
        out.append({"quote": exact, "page": p.page, "unit": p.unit, "passage": p.text, "q_start": a, "q_end": b,
                    "chunk_id": p.id})
    return out


def spoken(c: dict) -> str:
    """The line she says for a verified quote: 'Page 42 says: …' (long quotes: just where it is)."""
    words = c["quote"].split()
    if len(words) > SPOKEN_QUOTE_WORDS:
        return f"Your notes cover this on page {c['page']}."
    return f"Page {c['page']} says: {c['quote'].rstrip(' .;:,')}."


# ------------------------------------------------------------------------------------------------ answer bank
def bank_lookup(key: str, qvec) -> dict | None:
    from ..db import one, q
    row = one("""SELECT id, answer, 1 - (embedding <=> %s) AS sim FROM doc_answers WHERE source_key=%s
                 ORDER BY embedding <=> %s LIMIT 1""", (qvec, key, qvec))
    if not row or row["sim"] < BANK_SIM:
        return None
    q("UPDATE doc_answers SET hits = hits + 1 WHERE id=%s", (row["id"],))
    ans = row["answer"] if isinstance(row["answer"], dict) else json.loads(row["answer"])
    return {**ans, "banked": True, "bank_sim": float(row["sim"])}


def bank_save(key: str, question: str, qvec, ans: dict) -> None:
    from ..db import q
    from .lesson import Op
    ops = [asdict(o) if isinstance(o, Op) else o for o in ans.get("ops") or []]
    keep = {"say": ans.get("say") or [], "cited": ans.get("cited") or [], "ops": ops, "check": ans.get("check"),
            "intent": ans.get("intent"), "strategy": ans.get("strategy"), "error_type": ans.get("error_type"),
            "stuck_at": ans.get("stuck_at")}
    q("INSERT INTO doc_answers(source_key, question, embedding, answer) VALUES (%s,%s,%s,%s)",
      (key, question[:500], qvec, json.dumps(keep, ensure_ascii=False)))


def from_bank(ans: dict) -> dict:
    """A banked answer back into the shape player._play_answer expects (ops re-sanitised)."""
    from .lesson import sanitize_op
    out = dict(ans)
    out["ops"] = [o for o in (sanitize_op(x) for x in ans.get("ops") or [] if isinstance(x, dict)) if o]
    return out


# ------------------------------------------------------------------------------------------------ per lesson
@dataclass
class Lookup:
    status: str                # bank | covered | not_covered | unknown
    passages: list[Passage] = field(default_factory=list)
    answer: dict | None = None # a banked answer
    qvec: object = None
    ms: float = 0.0


class Citer:
    """One lesson's file: indexes it in the background at lesson start, then answers lookup() per doubt."""

    def __init__(self, path: str | Path, *, priority: str | None = None, log=print):
        self.path = Path(path).expanduser()
        self.key = source_key(self.path)
        self.priority, self.log = priority, log
        self.row: dict | None = None
        self.ready = threading.Event()
        self.stop = threading.Event()
        self.error: Exception | None = None
        self.thread = threading.Thread(target=self._index, daemon=True, name="cite-index")

    def start(self) -> "Citer":
        self.thread.start()
        return self

    def _index(self) -> None:
        try:
            self.row = index_book(self.path, priority=self.priority, log=self.log, stop=self.stop)
        except Exception as e:                       # no migration 013 / unreadable file: doubts work as before
            self.error = e
            self.log(f"   [cite] off: {type(e).__name__}: {str(e)[:120]}")
        finally:
            self.ready.set()

    @property
    def usable(self) -> bool:
        return self.error is None and not (self.row and self.row.get("outline"))

    def lookup(self, question: str, k: int = 4) -> Lookup:
        """Bank → hybrid retrieval → gate. Never raises (a broken index means 'unknown' = today's behaviour)."""
        t0 = time.perf_counter()
        if not self.usable:
            return Lookup("unknown")
        try:
            from .. import embed
            qvec = embed.embed_query(question)
            complete = bool(self.ready.is_set() and self.row and self.row.get("complete"))
            if complete:
                hit = bank_lookup(self.key, qvec)
                if hit:
                    return Lookup("bank", answer=from_bank(hit), qvec=qvec, ms=(time.perf_counter() - t0) * 1000)
            r = retrieve(question, self.key, k, qvec=qvec, complete=complete)
            st = {True: "covered", False: "not_covered", None: "unknown"}[r.covered]
            ms = (time.perf_counter() - t0) * 1000
            self.log(f"   [cite] {st} (top {r.top:.2f}, {len(r.passages)} passages, {ms:.0f} ms)")
            return Lookup(st, r.passages, qvec=qvec, ms=ms)
        except Exception as e:
            self.log(f"   [cite] lookup {type(e).__name__}: {str(e)[:120]}")
            return Lookup("unknown", ms=(time.perf_counter() - t0) * 1000)

    def attach(self, ans: dict, look: Lookup) -> dict:
        """The LLM's answer + this doubt's passages → ans["cited"] = verified quotes only (fabricated ones dropped);
        ans["uncited"] = the file was relevant but nothing it said could be quoted (she says so)."""
        if not ans or look.status != "covered":
            return ans
        raw = ans.get("quotes") or []
        ans["cited"] = verify_quotes(raw, look.passages)
        dropped = len([x for x in raw if isinstance(x, dict) and x.get("quote")]) - len(ans["cited"])
        if dropped > 0:
            self.log(f"   [cite] dropped {dropped} quote(s) not found in the passages")
        ans["uncited"] = not ans["cited"]
        return ans

    def save(self, question: str, ans: dict, look: Lookup) -> None:
        if look.qvec is None or not ans.get("cited") or ans.get("banked"):
            return
        try:
            bank_save(self.key, question, look.qvec, ans)
        except Exception as e:
            self.log(f"   [cite] bank {type(e).__name__}: {str(e)[:80]}")


def for_lesson(source: dict | None, log=print) -> Citer | None:
    """A Citer when the lesson came from his file (classic book lesson or the coach over a file), else None
    (topics without a file keep today's behaviour). STITI_CITE=off turns it off."""
    src = source or {}
    if os.getenv("STITI_CITE", "on") == "off" or src.get("kind") != "book" or not src.get("path"):
        return None
    p = Path(str(src["path"])).expanduser()
    if not p.is_file():
        return None
    return Citer(p, priority=src.get("section"), log=log).start()
