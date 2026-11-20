"""Pictures on the notes page (D53): Commons search → title filter → LLM judge → shrink → cache. Offline: HTTP and the
LLM are faked, STITI_HOME is a temp folder.

STITI_DB=postgresql:///stiti_test STITI_HOME=<tmp> python tests/tutor_pictures_eval.py
"""
from __future__ import annotations

import io
import os
import sys

db = os.environ.get("STITI_DB", "")
if not db.rstrip("/").split("/")[-1].startswith("stiti_test"):
    sys.exit(f"refusing to run against {db!r}: use a stiti_test* database")

import tempfile  # noqa: E402

# run_all.sh shares one STITI_HOME (STITI_TEST_HOME may be reused): the picture cache must start empty
_home = os.environ.get("STITI_HOME") or ""
os.environ["STITI_HOME"] = tempfile.mkdtemp(prefix="pictures_eval_", dir=_home if os.path.isdir(_home) else None)

from PIL import Image  # noqa: E402

from stiti.tutor import pictures as P  # noqa: E402

passed = total = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global passed, total
    total += 1
    passed += bool(cond)
    print(("  ✓ " if cond else "  ✗ ") + name + ("" if cond else f"  — {detail}"))


def png(w=1600, h=900) -> bytes:
    buf = io.BytesIO()
    Image.new("RGBA", (w, h), (30, 120, 200, 255)).save(buf, "PNG")
    return buf.getvalue()


def page(i, title, desc="", cats="", w=800, h=500, mime="image/png"):
    return {str(i): {"index": i, "title": f"File:{title}.png", "imageinfo": [{
        "mime": mime, "thumburl": f"https://upload.example/{i}.png", "thumbwidth": w, "thumbheight": h,
        "descriptionurl": f"https://commons.example/{i}",
        "extmetadata": {"LicenseShortName": {"value": "CC BY-SA 4.0"}, "ImageDescription": {"value": desc},
                        "Categories": {"value": cats}}}]}}


class R:
    def __init__(self, status=200, json_data=None, content=b"", ctype="application/json"):
        self.status_code, self._j, self.content, self.headers = status, json_data, content, {"content-type": ctype}

    def json(self):
        return self._j


CALLS = {"api": 0, "img": 0}


def fake_get(url, params=None, headers=None, timeout=None, follow_redirects=False):
    assert headers and "StitiTutor" in headers.get("User-Agent", "")
    if "api.php" in url:
        CALLS["api"] += 1
        q = params["gsrsearch"].lower()
        pages = {}
        if "symbol" in q:
            pages.update(page(1, "Synte 2 and symbol table (1979)", "a synthesizer", "Synthesizers"))
            pages.update(page(2, "Compiler symbol table diagram", "names, types and scopes in a compiler",
                              "Compiler construction"))
        if "photosynthesis" in q:
            pages.update(page(1, "Syntax tree - Affirmation", "linguistics"))       # title doesn't match
            pages.update(page(2, "Photosynthesis overview", "how plants make sugar", "Photosynthesis"))
            pages.update(page(3, "Photosynthesis tall", w=300, h=900))            # too tall → skipped
        return R(json_data={"query": {"pages": pages}})
    CALLS["img"] += 1
    return R(content=png(), ctype="image/png")


def fake_judge(system, user, schema, name, max_tokens, **kw):
    lines = [x for x in user.splitlines() if x[:1].isdigit()]
    for ln in lines:                                  # pick the first candidate that isn't a synthesizer
        if "synthesizer" not in ln.lower():
            return {"pick": int(ln.split(":")[0])}
    return {"pick": -1}


hits = P.search("Photosynthesis", context="Biology", get=fake_get)
check("title filter: only files ABOUT the concept, sane size (linguistics tree and a 3:1 strip dropped)",
      [h["title"] for h in hits] == ["Photosynthesis overview"], str([h["title"] for h in hits]))
check("abbreviations count: 'DFA' in a title matches 'Deterministic finite automaton (DFA)'",
      P._title_ok("DFA search mommy", "Deterministic finite automaton (DFA)")
      and not P._title_ok("Finite field", "Deterministic finite automaton (DFA)"))
hs = P.search("Symbol Tables", context="Compiler", get=fake_get)
j = P.judge("Symbol Tables", "Compiler", hs, call=fake_judge)
check("the judge rejects a title-only match (the 1979 synthesizer) and keeps the compiler diagram",
      len(hs) == 2 and [h["title"] for h in j] == ["Compiler symbol table diagram"], str([h["title"] for h in j]))
p = P.picture("Symbol Tables", context="Compiler", get=fake_get, call=fake_judge)
check("picture: shrunk to ≤ 720 px, a data URL, credited (Commons + licence)",
      p and p["size"][0] <= 720 and p["src"].startswith("data:image/") and "Wikimedia Commons" in p["caption"]
      and "CC BY-SA" in p["caption"], str(p and p["caption"]))
n = dict(CALLS)
p2 = P.picture("Symbol Tables", context="Compiler", get=fake_get, call=fake_judge)
check("cached: the same concept again makes no network call", p2 == p and CALLS == n, str(CALLS))
none = P.picture("Quantum foam", context="Physics", get=fake_get, call=fake_judge)
check("nothing good → None (and remembered, so no repeated searches)", none is None
      and P.picture("Quantum foam", context="Physics", get=fake_get, call=fake_judge) is None
      and CALLS["api"] == n["api"] + 2)        # with the subject words, then without; never again


def down(url, **kw):
    return R(status=429, json_data=None, ctype="text/html")


check("Commons rate limit / outage → None and NOT cached (tried again next time)",
      P.picture("Mitochondria", context="Biology", get=down) is None
      and not (P._cache_dir() / f"{__import__('hashlib').sha1(b'mitochondria|biology').hexdigest()[:16]}.json").exists())
op = P.picture_op("Symbol Tables", context="Compiler", get=fake_get, call=fake_judge)
check("picture_op → an image op for the figure slot with src + size", op is not None and op.type == "image"
      and op.region == "figure" and op.src and op.size, str(op))

print(f"tutor pictures: {passed}/{total} checks passed")
sys.exit(0 if passed == total else 1)
