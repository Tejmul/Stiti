#!/usr/bin/env python3
"""Privacy guard: is anything from YOUR local profile written into the repo?

Stiti is open source and forkable: the code is the same for everyone, and everything personal stays on your Mac
(Postgres `stiti` + ~/.stiti). This script reads your LOCAL profile — owner_profile, graph entities, facts,
~/.stiti/USER.md, ~/.stiti/vocab.json — and scans the files git tracks for those names and words.

It prints only `path:line  category`, never the matched value, so its output is safe to paste anywhere.
Exit code 1 when anything is found, 0 when clean or when there is no local profile (CI, a fresh clone).

  python scripts/privacy_check.py                  scan every tracked file
  python scripts/privacy_check.py --staged         scan what is staged (what the pre-commit hook runs)
  python scripts/privacy_check.py --install-hook   opt in: run --staged before every commit
  python scripts/privacy_check.py --uninstall-hook

Local tuning (never committed): ~/.stiti/privacy_terms.txt adds words to guard (one per line: a surname, an email,
a street), ~/.stiti/privacy_allow.txt lists words that are fine to appear (public names, common tech words).
Options for tests: --home DIR (default $STITI_HOME or ~/.stiti), --db DSN|none (default $STITI_DB or
postgresql:///stiti), --repo DIR (default: this repo).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

HOOK_MARK = "# stiti-privacy-check"
# the owner's name may appear as the copyright holder / package author / project owner — nowhere else
NAME_OK_PATHS = {"LICENSE", "pyproject.toml", "CLAUDE.md"}
# public tech / platform words that show up in anyone's résumé facts; flagging them would only be noise
COMMON = {
    "stiti", "ai", "ml", "aiml", "llm", "llms", "nlp", "api", "apis", "sdk", "ui", "ux", "cs", "it", "ngo", "llc",
    "inc", "ltd", "pvt", "usa", "uk", "us", "eu", "yc", "gtm", "mrr", "arr", "cgpa", "gpa", "sse", "rag", "lora",
    "qlora", "aws", "gcp", "azure", "sql", "nosql", "postgres", "postgresql", "pgvector", "mysql", "sqlite", "redis",
    "docker", "kubernetes", "k8s", "fastapi", "flask", "django", "next", "next.js", "nextjs", "react", "node",
    "node.js", "typescript", "javascript", "python", "java", "golang", "rust", "swift", "kotlin", "langchain",
    "langgraph", "llamaindex", "openai", "anthropic", "claude", "gemini", "groq", "mistral", "llama", "whisper",
    "huggingface", "pytorch", "tensorflow", "yolo", "yolov8", "yolov11", "lambda", "github", "gitlab", "leetcode",
    "codeforces", "codechef", "hackerrank", "kaggle", "instagram", "linkedin", "youtube", "twitter", "telegram",
    "whatsapp", "google", "apple", "mac", "macos", "iphone", "ios", "android", "windows", "linux", "microsoft",
    "b.tech", "btech", "m.tech", "mtech", "bsc", "msc", "mba", "phd", "ci", "cd", "ci/cd", "devops", "mlops",
    "saas", "b2b", "b2c", "mvp", "okr", "kpi", "seo", "crm", "erp", "json", "html", "css", "http", "https", "rest",
    "graphql", "grpc", "webrtc", "mcp", "agentic", "chatgpt", "copilot", "cursor", "vscode", "notion", "slack",
    "figma", "jira", "excel", "pdf", "u-14", "india", "indian", "english", "hindi", "hinglish", "telugu",
}
# big cities are public and low-signal (a résumé line "… Intern, <city>" must not flag every weather example)
COMMON |= {"london", "paris", "berlin", "tokyo", "singapore", "dubai", "new york", "san francisco", "seattle",
           "toronto", "sydney", "delhi", "new delhi", "mumbai", "bangalore", "bengaluru", "hyderabad", "chennai",
           "kolkata", "pune", "jaipur", "ahmedabad", "goa", "noida", "gurgaon", "gurugram", "lucknow", "chandigarh"}
_ORG_HEADS = {"school", "university", "college", "institute", "technology", "labs", "lab", "academy", "foundation",
              "club", "team", "company", "hospital", "bank", "park", "street", "road", "nagar", "society", "group",
              "llc", "inc", "ltd", "secure", "tech"}
_CALENDAR = {"jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "sept", "oct", "nov", "dec", "january",
             "february", "march", "april", "june", "july", "august", "september", "october", "november", "december",
             "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"}
_GLUE = {"of", "the", "de", "and", "&"}
_PROPER = re.compile(r"\b[a-z]?[A-Z][\w'+.&-]*(?:\s+(?:of|the|de|and)\s+[A-Z][\w'+&-]*|\s+[a-z]?[A-Z][\w'+.&-]*)*")
_URL = re.compile(r"(?:https?://|www\.)\S+|\bgithub\.com/\S+|[\w.+-]+@[\w-]+\.[\w.]+")


# ---------------------------------------------------------------- words
_dict: set[str] | None = None


def ordinary() -> set[str]:
    global _dict
    if _dict is None:
        _dict = set()
        for p in ("/usr/share/dict/words", "/usr/dict/words"):
            try:
                _dict = {w.strip().lower() for w in Path(p).read_text(errors="ignore").split()}
                break
            except OSError:
                continue
    return _dict


def _base(w: str) -> str:
    return re.sub(r"'s?$", "", w.lower().strip(" .,;:!?\"()[]"))


_SUFFIXES = (("ies", "y"), ("es", ""), ("s", ""), ("ed", ""), ("ed", "e"), ("ing", ""), ("ing", "e"))


def _plain(w: str) -> bool:
    """An ordinary English word (or a plural / -ed / -ing of one), a calendar word, a common tech word, or a
    number — never personal by itself."""
    b = _base(w)
    if "'" in b:                                  # "you're", "I've", "we'll"
        b = b.split("'", 1)[0]
    if not b or len(b) <= 2 or b in COMMON or b in _CALENDAR or re.fullmatch(r"[\d.,+%$k×x-]+", b):
        return True
    d = ordinary()
    if b in d:
        return True
    return any(b.endswith(s) and len(b) - len(s) >= 3 and b[:-len(s)] + r in d for s, r in _SUFFIXES)


def proper_terms(text: str) -> set[str]:
    """Names in free text: multi-word names with a rare word or an organisation ending ("… University"), and rare
    single words (not in the dictionary, not common tech words). Sentence-initial ordinary words never count."""
    out: set[str] = set()
    for m in _PROPER.finditer(text):
        cand = m.group(0).strip(" .,'-")
        words = cand.split()
        rare = [w for w in words if not _plain(w) and w.lower() not in _GLUE]
        for w in rare:                            # "Built Tilecraft" → "tilecraft" (rare words match anywhere)
            out.add(_base(w) if not w.isupper() else w.strip(" .,'"))
        # an organisation made of ordinary words ("Kepler School of Technology"), but not "School of Technology"
        if (len(words) >= 2 and not rare and words[-1].lower() in _ORG_HEADS
                and any(_base(w) not in _ORG_HEADS | _GLUE | COMMON for w in words)):
            out.add(cand)
    return {t for t in out if len(t) >= 3}


# ---------------------------------------------------------------- the local profile
def _db_rows(dsn: str) -> dict[str, list] | None:
    if not dsn or dsn == "none":
        return None
    try:
        import psycopg
    except ImportError:
        return None
    try:
        with psycopg.connect(dsn, connect_timeout=3) as c:
            def rows(sql: str) -> list:
                try:
                    return c.execute(sql).fetchall()
                except Exception:
                    c.rollback()
                    return []
            return {"profile": rows("SELECT key, value FROM owner_profile"),
                    "entities": rows("SELECT kind, name, coalesce(aliases, '{}') FROM entities WHERE merged_into IS NULL"),
                    "facts": rows("SELECT fact_text FROM facts")}
    except Exception:
        return None


def load_terms(home: Path, dsn: str) -> dict[str, str]:
    """{term: category} from the local profile. Empty when there is no local profile."""
    terms: dict[str, str] = {}
    seen: set[str] = set()

    def add(t: str, cat: str, force: bool = False) -> None:
        t = " ".join(str(t).split()).strip(" .,'\"")
        if len(t) < 3 or t.lower() in COMMON or t.lower() in seen:
            return
        if not force and all(_plain(w) for w in t.split()) and not (len(t.split()) >= 2 and
                                                                       t.split()[-1].lower() in _ORG_HEADS):
            return
        seen.add(t.lower())
        terms[t] = cat

    rows = _db_rows(dsn) or {}
    for key, value in rows.get("profile", []):
        if key in ("name", "call_me"):
            for w in str(value).split():
                add(w, "owner name", force=True)
        elif key == "say_as":
            try:
                for k, v in json.loads(value).items():
                    add(k, "owner name", force=True)
                    add(v, "owner name")
            except Exception:
                pass
        elif key == "wake_phrases":
            try:
                for ph in json.loads(value):
                    if not str(ph).lower().endswith("stiti"):
                        add(ph, "wake phrase", force=True)
            except Exception:
                pass
    cats = {"self": "owner name", "person": "person", "org": "org", "project": "project", "place": "place"}
    for kind, name, aliases in rows.get("entities", []):
        if kind not in cats:
            continue                           # "thing", "event", "feeling": ordinary words, not identities
        cat = cats[kind]
        for n in [name] + ([] if kind == "self" else list(aliases or [])):   # self aliases: "me", "main", "mujhe"
            if re.search(r"'s\s", n):          # "<owner>'s sister" placeholders: the parts are caught elsewhere
                continue
            add(n, cat, force=kind == "self")
            for w in n.split():
                if not _plain(w):
                    add(_base(w) if not w.isupper() else w, cat)
    for (text,) in rows.get("facts", []):
        for t in proper_terms(str(text or "")):
            add(t, "profile fact")
    user = home / "USER.md"
    if user.exists():
        for line in user.read_text(errors="ignore").splitlines():
            if line.lstrip().startswith("- "):
                for t in proper_terms(re.sub(r"^\s*-\s*(\[[A-Z]\d+\]\s*)?", "", line)):
                    add(t, "profile fact")
    vocab = home / "vocab.json"
    if vocab.exists():
        try:
            data = json.loads(vocab.read_text())
            items = data.get("terms", data) if isinstance(data, dict) else data
            for it in list(items) if isinstance(items, (list, dict)) else []:
                t = it.get("term") if isinstance(it, dict) else it
                if t:
                    add(t, "vocab word", force=not str(t).islower())    # words the owner taught her
        except Exception:
            pass
    extra = home / "privacy_terms.txt"
    if extra.exists():
        for line in extra.read_text(errors="ignore").splitlines():
            if line.strip() and not line.startswith("#"):
                add(line.strip(), "private term", force=True)
    allow = home / "privacy_allow.txt"
    if allow.exists():
        ok = {ln.strip().lower() for ln in allow.read_text(errors="ignore").splitlines() if ln.strip()}
        terms = {t: c for t, c in terms.items() if t.lower() not in ok}
    return terms


def has_profile(home: Path, dsn: str) -> bool:
    rows = _db_rows(dsn) or {}
    return bool(rows.get("profile") or rows.get("facts") or (home / "USER.md").exists()
                or (home / "privacy_terms.txt").exists())


# ---------------------------------------------------------------- scanning
def _matcher(terms: dict[str, str]) -> list[tuple[re.Pattern, str]]:
    out = []
    for t, cat in sorted(terms.items(), key=lambda kv: -len(kv[0])):
        flags = 0 if (cat != "owner name" and t.isupper()) else re.I
        out.append((re.compile(rf"(?<![\w]){re.escape(t)}(?![\w])", flags), cat))
    return out


def scan_text(path: str, text: str, matchers: list[tuple[re.Pattern, str]]) -> list[tuple[str, int, str]]:
    hits = []
    attribution = path in NAME_OK_PATHS
    for i, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        bare = _URL.sub(" ", line)                        # public URLs (github.com/<user>/Stiti) are fine
        if attribution and any(rx.search(bare) for rx, cat in matchers if cat == "owner name"):
            continue                                      # "Copyright (c) <owner>", authors = [...]
        for rx, cat in matchers:
            if rx.search(bare):
                hits.append((path, i, cat))
                break
    spaced = re.sub(r"[_\-./]+", " ", path)              # a file NAMED after something private
    for rx, cat in matchers:
        if rx.search(spaced):
            hits.append((path, 0, cat + " (file name)"))
            break
    return hits


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True).stdout


def scan_repo(repo: Path, terms: dict[str, str], staged: bool = False) -> list[tuple[str, int, str]]:
    matchers = _matcher(terms)
    if staged:
        files = [f for f in _git(repo, "diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z").split("\0") if f]
    else:
        files = [f for f in _git(repo, "ls-files", "-z").split("\0") if f]
    hits: list[tuple[str, int, str]] = []
    for f in files:
        try:
            if staged:
                raw = subprocess.run(["git", "-C", str(repo), "show", f":{f}"], capture_output=True, check=True).stdout
            else:
                p = repo / f
                if not p.is_file() or p.stat().st_size > 5_000_000:
                    continue
                raw = p.read_bytes()
        except Exception:
            continue
        if b"\0" in raw[:8192]:
            continue                                      # binary
        hits += scan_text(f, raw.decode("utf-8", errors="ignore"), matchers)
    return hits


# ---------------------------------------------------------------- hook
def _hook_path(repo: Path) -> Path:
    p = Path(_git(repo, "rev-parse", "--git-path", "hooks").strip())
    return (p if p.is_absolute() else repo / p) / "pre-commit"


HOOK = f"""#!/bin/sh
{HOOK_MARK}: block commits that contain anything from your local Stiti profile (prints file:line only)
ROOT="$(git rev-parse --show-toplevel)"
PY="$ROOT/.venv/bin/python"; [ -x "$PY" ] || PY=python3
exec "$PY" "$ROOT/scripts/privacy_check.py" --staged
"""


def install_hook(repo: Path, force: bool = False) -> str:
    hp = _hook_path(repo)
    if hp.exists() and HOOK_MARK not in hp.read_text(errors="ignore") and not force:
        return f"{hp} already exists (not ours) — left alone. Re-run with --force to replace it."
    hp.parent.mkdir(parents=True, exist_ok=True)
    hp.write_text(HOOK)
    hp.chmod(0o755)
    return f"Installed the privacy pre-commit hook: {hp}  (skip once: git commit --no-verify)"


def uninstall_hook(repo: Path) -> str:
    hp = _hook_path(repo)
    if hp.exists() and HOOK_MARK in hp.read_text(errors="ignore"):
        hp.unlink()
        return f"Removed {hp}."
    return "No privacy hook installed."


# ---------------------------------------------------------------- main
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--staged", action="store_true")
    ap.add_argument("--install-hook", action="store_true")
    ap.add_argument("--uninstall-hook", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--home", default=os.getenv("STITI_HOME") or str(Path.home() / ".stiti"))
    ap.add_argument("--db", default=os.getenv("STITI_DB") or "postgresql:///stiti")
    ap.add_argument("--repo", default=str(Path(__file__).resolve().parent.parent))
    a = ap.parse_args(argv)
    repo = Path(a.repo).resolve()
    if a.install_hook:
        print(install_hook(repo, a.force))
        return 0
    if a.uninstall_hook:
        print(uninstall_hook(repo))
        return 0
    home = Path(a.home).expanduser()
    if os.getenv("CI") or not has_profile(home, a.db):
        print("privacy check: no local profile here (CI or a fresh clone) — nothing to check.")
        return 0
    terms = load_terms(home, a.db)
    hits = scan_repo(repo, terms, staged=a.staged)
    for path, line, cat in hits:
        print(f"{path}:{line}  {cat}" if line else f"{path}  {cat}")
    files = len({h[0] for h in hits})
    if hits:
        print(f"privacy check: {len(hits)} line(s) in {files} file(s) contain something from your local profile "
              f"({len(terms)} terms checked). Values are not printed. Move them to your local profile, or list a "
              f"public word in {home / 'privacy_allow.txt'}.")
        return 1
    print(f"privacy check: clean ({len(terms)} terms from your local profile, "
          f"{'staged files' if a.staged else 'all tracked files'}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
