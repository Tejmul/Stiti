"""The owner's own words, for the ears: a glossary built by the brain, and a "snap to glossary" post-fix (D27).

Whisper writes "Tejmal" and "Newton's Club" because it has never seen those words. Names are a biasing problem, not
a model-size problem (docs/research/stt_tts_indian_english.md): a short glossary in the prompt took whisper-small
from 12.4 → 9.7% WER, and snapping near-misses to the glossary afterwards took it to 9.1% (owner terms 64 → 80/90).

Terms come from Stiti's own store, never hard-coded: the owner profile (name, call_me), USER.md (proper nouns in his
facts, by frequency), the most-connected graph entities, the titles of ingested documents, and a few fixed words
every user of Stiti says (Stiti, todos, resume…). Near-duplicates of a better-ranked term are dropped, so a misheard
fact ("Tejmal is a final year undergrad at Newton's Club…") can't teach the ears the wrong spelling.

The snap is deliberately strict (research: wider spans ate neighbouring Hindi words): a span is rewritten only when
its consonant skeleton (with simple phonetic folding) is ≥ 0.8 similar to a term, starts with the same sound, and
it is not an ordinary word (system dictionary, Stiti's Hinglish lexicon, or another glossary term). < 1 ms.
"""
from __future__ import annotations

import difflib
import re
import threading
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

REFRESH_S = 300
MAX_TERMS = 40                     # research: ~40 terms (< 150 tokens; Whisper keeps only the last 223)
TOKEN_BUDGET = 150                 # for the glossary sentence; the rest of the prompt has its own share
MIN_SKELETON = 3                   # "DSA" (skeleton "ds") is too short to snap safely
SNAP_RATIO = 0.8
# words every Stiti user says that Whisper often writes wrong ("to-dos / tattoos", "playsa mains", "curzle")
FIXED = ["cursor", "GitHub", "DSA", "resume", "placements", "todos", "Stiti"]

_STOP = {"the", "a", "an", "of", "and", "or", "in", "on", "at", "to", "for", "with", "my", "his", "her", "is", "was",
         "i", "he", "she", "they", "it", "this", "that", "from", "by", "as", "&"}
_HEADINGS_SKIP = {"how i understand you (tentative)"}


@dataclass(frozen=True)
class Term:
    text: str
    private: bool = False          # P2: stays in the local prompt, never sent to a cloud ear


# ---------------------------------------------------------------- ordinary words (never rewritten)
_dict_words: set[str] | None = None


def ordinary_words() -> set[str]:
    """System dictionary (~235k words on macOS) + Stiti's Roman Hinglish lexicon. Loaded once (~60 ms)."""
    global _dict_words
    if _dict_words is None:
        words: set[str] = set()
        for p in ("/usr/share/dict/words", "/usr/dict/words"):
            try:
                words |= {w.strip().lower() for w in Path(p).read_text(errors="ignore").split()}
                break
            except OSError:
                continue
        from . import hinglish
        words |= set(hinglish.LEX)
        words |= {"ok", "okay", "yeah", "hey", "hi", "bye", "todo", "email", "online", "app", "apps"}
        _dict_words = words
    return _dict_words


_SUFFIXES = (("ies", "y"), ("es", ""), ("s", ""), ("ed", ""), ("ed", "e"), ("ing", ""), ("ing", "e"), ("ly", ""),
             ("er", ""), ("est", ""))


def _is_ordinary(word: str) -> bool:
    """A real word (the macOS list has base forms only, so 'tattoos' / 'preparing' are checked via their stem)."""
    w = re.sub(r"[^a-z']", "", word.lower())
    w = re.sub(r"'s?$", "", w)
    if not w:
        return False
    d = ordinary_words()
    if w in d:
        return True
    for suf, rep in _SUFFIXES:
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            stem = w[:-len(suf)] + rep
            if stem in d:
                return True
            if (suf in ("ed", "ing", "er", "est") and len(stem) > 3 and stem[-1] == stem[-2]
                    and stem[-1] not in "aeiou" and stem[:-1] in d):          # "stopped" → stop
                return True
    return False


# ---------------------------------------------------------------- phonetic skeleton
_FOLD = [("sch", "sk"), ("ph", "f"), ("ck", "k"), ("q", "k"), ("x", "ks"), ("z", "s"), ("v", "w")]


def skeleton(s: str) -> str:
    """First letter + consonants, phonetically folded, repeats collapsed: Tejmal/Tajmal/Tejmul → 'tjml'."""
    s = re.sub(r"[^a-z]", "", s.lower())
    if not s:
        return ""
    for a, b in _FOLD:
        s = s.replace(a, b)
    s = re.sub(r"c(?!h)", "k", s)
    s = s[0] + re.sub(r"[aeiouy]", "", s[1:])
    return re.sub(r"(.)\1+", r"\1", s)


def _letters(s: str) -> str:
    return re.sub(r"[^a-z]", "", s.lower())


# ---------------------------------------------------------------- building the glossary
def _clean(name: str) -> str:
    return " ".join(str(name).replace("_", " ").split()).strip(" .,:;-")


def _ok(name: str) -> bool:
    return 2 <= len(name) <= 40 and bool(re.fullmatch(r"[\w .'&+-]+", name)) and len(name.split()) <= 5


_PROPER = re.compile(r"\b[a-z]?[A-Z][\w'+.-]*(?:\s+(?:of|the|de)\s+[A-Z][\w'+-]*|\s+[a-z]?[A-Z][\w'+.-]*)*")
# a name made only of ordinary words counts when it ends like an organisation or place ("Newton School of Technology")
_ORG_HEADS = {"school", "university", "college", "institute", "technology", "labs", "lab", "academy", "foundation",
              "club", "team", "company", "hospital", "bank", "park", "street", "road", "nagar", "society", "group"}
_CALENDAR = {"jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "sept", "oct", "nov", "dec", "mon", "tue", "wed",
             "thu", "fri", "sat", "sun"}


def user_md_terms(text: str) -> list[str]:
    """Proper nouns in USER.md facts, most frequent first: multi-word names ("Rishihood University") and rare
    single words (not in the dictionary: "Zonuly", "Codeforces"). Common capitalised words are left to Whisper."""
    counts: Counter[str] = Counter()
    first_seen: dict[str, int] = {}
    heading = ""
    for line in text.splitlines():
        if line.startswith("#"):
            heading = line.lstrip("# ").strip().lower()
            continue
        if not line.lstrip().startswith("- ") or heading in _HEADINGS_SKIP:
            continue
        body = re.sub(r"^\s*-\s*(\[[A-Z]\d+\]\s*)?", "", line)
        for m in _PROPER.finditer(body):
            cand = _clean(m.group().rstrip("."))
            cand = re.sub(r"'s$", "", cand)
            words = cand.split()
            if not words or not _ok(cand):
                continue
            rare = [w for w in words if w.lower() not in _STOP and w.lower().strip(".") not in _CALENDAR
                    and not _is_ordinary(w) and not (w.isupper() and len(w) <= 3)]   # YC, AWS: Whisper knows them
            org = len(words) >= 2 and words[-1].lower() in _ORG_HEADS
            if rare or org:
                counts[cand] += 1
                first_seen.setdefault(cand, len(first_seen))
    return sorted(counts, key=lambda c: (-counts[c], first_seen[c]))


def _graph_terms() -> list[Term]:
    from ..db import q
    rows = q("""SELECT e.name, max(e.privacy) AS privacy FROM entities e
                LEFT JOIN facts f ON (f.subj_id = e.id OR f.obj_id = e.id) AND upper_inf(f.recorded)
                WHERE e.merged_into IS NULL AND e.kind IN ('person','project','place','org')
                GROUP BY e.id, e.name ORDER BY count(f.id) DESC, max(e.created_at) DESC LIMIT 25""")
    return [Term(_clean(r["name"]), int(r["privacy"] or 1) >= 2) for r in rows if _ok(_clean(r["name"]))]


def _doc_terms() -> list[Term]:
    from ..db import q
    rows = q("SELECT title, privacy FROM documents ORDER BY ingested_at DESC LIMIT 15")
    out = []
    for r in rows:
        title = re.sub(r"\.(md|pdf|docx?|pptx?|xlsx?|txt|html?|epub)$", "", str(r["title"]), flags=re.I)
        for w in re.split(r"[\s_\-–—:,()]+", title):
            if len(w) >= 4 and w[0].isalpha() and not _is_ordinary(w) and not w.isdigit():
                out.append(Term(w, int(r["privacy"] or 1) >= 2))
    return out


def build() -> list[Term]:
    """All terms, least important first (Whisper weighs the end of the prompt most). Each source is optional."""
    from .. import profile
    from ..config import CFG
    ranked: list[Term] = []                          # most important first while collecting

    def add(t: Term) -> None:
        if not t.text or not _ok(t.text):
            return
        for i, have in enumerate(ranked):
            if have.text.lower() == t.text.lower():
                if t.private and not have.private:
                    ranked[i] = Term(have.text, True)
                return
            if _near(have.text, t.text):              # "Tejmal" after "Tejmul": the better-ranked spelling wins
                return
        ranked.append(t)

    for k in ("call_me", "name"):
        v = profile.get(k)
        if v:
            for part in [v] + ([w for w in v.split() if len(w) >= 3] if len(v.split()) > 1 else []):
                add(Term(_clean(part)))
    add(Term("Stiti"))
    try:
        from . import vocab                           # words he taught by correcting her: like Wispr's manual words
        for w in reversed(vocab.terms()):
            add(Term(w))
    except Exception:
        pass
    try:
        p = CFG.home / "USER.md"
        if p.exists():
            for name in user_md_terms(p.read_text(errors="ignore"))[:15]:
                add(Term(name))
    except Exception:
        pass
    for src in (_graph_terms, _doc_terms):
        try:
            for t in src():
                add(t)
        except Exception:
            pass
    for w in reversed(FIXED):
        add(Term(w))
    ranked = ranked[:MAX_TERMS]
    while ranked and _tokens(", ".join(t.text for t in ranked)) > TOKEN_BUDGET:
        ranked.pop()                                  # drop the least important until it fits
    return list(reversed(ranked))


def _near(a: str, b: str) -> bool:
    """Two spellings of the same thing (Tejmul/Tejmal, Newton School of Technology/Newton's Club of Technology)."""
    if len(a.split()) != len(b.split()):
        return False
    sa, sb = skeleton(a), skeleton(b)
    if len(sa) < MIN_SKELETON or sa[0] != sb[:1]:
        return False
    return difflib.SequenceMatcher(None, sa, sb).ratio() >= SNAP_RATIO + 0.05


def _tokens(text: str) -> int:
    """Conservative Whisper token estimate (BPE splits rare names into ~3-letter pieces)."""
    return sum(max(1, -(-len(w) // 3)) for w in re.findall(r"\w+", text)) + len(re.findall(r"[^\w\s]", text))


# ---------------------------------------------------------------- cache (refreshed in the background)
_terms: list[Term] = [Term(w) for w in FIXED]
_at = 0.0
_lock = threading.Lock()


def _refresh() -> None:
    global _terms
    try:
        _terms = build()
    except Exception:
        pass


def terms(block: bool = False) -> list[Term]:
    """Cached terms; a stale cache is refreshed in a background thread (never blocks a transcription)."""
    global _at
    if time.time() - _at > REFRESH_S:
        with _lock:
            if time.time() - _at > REFRESH_S:
                _at = time.time()
                if block:
                    _refresh()
                else:
                    threading.Thread(target=_refresh, daemon=True).start()
    return _terms


def invalidate() -> None:
    global _at
    _at = 0.0


def learn(term: str) -> None:
    """A word he just taught (vocab.py): usable on the very next turn, then kept by the next rebuild."""
    global _terms
    _terms = [t for t in _terms if t.text.lower() != term.lower()] + [Term(term)]
    invalidate()


def prompt_text(cloud: bool = False) -> str:
    """'Glossary: a, b, c.' (P2 terms are left out of anything sent to a cloud ear)."""
    ts = [t.text for t in terms() if not (cloud and t.private)]
    return ("Glossary: " + ", ".join(ts) + ".") if ts else ""


# ---------------------------------------------------------------- snap to glossary
def _variants(ts: list[str]) -> list[str]:
    """Terms + the first two words of long names ('Newton School' of 'Newton School of Technology'), longest first."""
    out = list(ts)
    for t in ts:
        w = t.split()
        if len(w) >= 3 and not ({w[0].lower(), w[1].lower()} & _STOP):
            out.append(" ".join(w[:2]))
    return sorted(dict.fromkeys(out), key=lambda t: -len(t.split()))


def _match(span_words: list[str], term: str, glossary_words: set[str]) -> bool:
    core = " ".join(re.sub(r"[^\w'\s-]", "", w) for w in span_words).strip()
    if not core or core.lower() == term.lower():
        return False
    tw = term.split()
    if len(tw) == 1:
        w = span_words[0]
        if _is_ordinary(w) or re.sub(r"[^\w]", "", w).lower() in glossary_words:
            return False
    else:
        # a multi-word name needs one anchor word heard right ("Newton's" ~ "Newton"), or no ordinary word at all
        anchor = any(re.sub(r"'s?$", "", re.sub(r"[^\w']", "", a).lower()) == b.lower()
                     for a, b in zip(span_words, tw) if b.lower() not in _STOP)
        if not anchor and any(_is_ordinary(w) for w in span_words):
            return False
    ss, ts = skeleton(core), skeleton(term)
    if len(ts) >= MIN_SKELETON:
        return bool(ss) and ss[0] == ts[0] and difflib.SequenceMatcher(None, ss, ts).ratio() >= SNAP_RATIO
    lc, lt = _letters(core), _letters(term)       # short skeleton ("Stiti" → "st"): compare letters instead
    return (len(lt) >= 5 and lc[:2] == lt[:2]
            and difflib.SequenceMatcher(None, lc, lt).ratio() >= SNAP_RATIO + 0.05)


def snap(text: str, glossary: list[str] | None = None) -> str:
    """Rewrite near-misses of glossary terms ("Tejmal" → "Tejmul"); ordinary words are never touched."""
    if not text:
        return text
    try:
        from . import vocab
        text = vocab.rewrite(text)                    # his own corrections first: "Tejmal" → "Tejmul", exactly
    except Exception:
        pass
    ts = glossary if glossary is not None else [t.text for t in terms()]
    if not ts:
        return text
    glossary_words = {w.lower() for t in ts for w in t.split()}
    words = text.split()
    for term in _variants(ts):
        n = len(term.split())
        i = 0
        while i + n <= len(words):
            span = words[i:i + n]
            if _match(span, term, glossary_words):
                lead = re.match(r"^[^\w]*", span[0]).group()
                tail = re.search(r"[^\w']*$", re.sub(r"'s$", "", span[-1])).group()
                poss = "'s" if n == 1 and re.search(r"'s[^\w]*$", span[-1]) and not term.endswith("s") else ""
                words[i:i + n] = [lead + term + poss + tail]
            i += 1
    return " ".join(words)
