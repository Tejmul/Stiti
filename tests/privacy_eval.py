"""Fork-safety (offline): nothing personal in the code, everything personal in the user's own local profile.

1. A fresh install (empty home + empty brain) knows nobody: she says "you", asks the name, wakes on the default
   phrases only, primes Whisper with generic words only, and every file she writes is free of names.
2. scripts/privacy_check.py, run on a FAKE profile (a made-up person) against a FAKE repo: finds what leaked, prints
   only file:line + category (never the value), honours the allowed places, scans staged files, skips cleanly with
   no profile / in CI, and installs an opt-in pre-commit hook that blocks a leaking commit.
3. The LaunchAgent move from an older label to com.stiti.app (launchctl / codesign faked, temp folders only).

STITI_DB=postgresql:///stiti_test STITI_HOME=<tmp> python tests/privacy_eval.py
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import plistlib
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

db = os.environ.get("STITI_DB", "")
if not db.rstrip("/").split("/")[-1].startswith("stiti_test"):
    sys.exit(f"refusing to run against {db!r}: use a stiti_test* database")
os.environ.setdefault("STITI_LIVE_WARM", "0")
os.environ.setdefault("STITI_EVENTKIT", "off")
os.environ.pop("CI", None)        # GitHub sets CI=true; the checks below need the scanner ON (one check sets CI itself)
ROOT = Path(__file__).resolve().parent.parent

# a brand-new home: only the shared models folder is linked in (models are not personal)
FRESH = Path(tempfile.mkdtemp(prefix="stiti-fresh-"))
_models = Path(os.environ.get("STITI_HOME", "")).expanduser() / "models"
if _models.exists():
    (FRESH / "models").symlink_to(_models.resolve())
os.environ["STITI_HOME"] = str(FRESH)

passed = total = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global passed, total
    total += 1
    passed += bool(cond)
    print(f"  {'✓' if cond else '✗'} {name}" + (f" — {detail}" if detail and not cond else ""))


sys.path.insert(0, str(ROOT / "scripts"))
import privacy_check as pc                                               # noqa: E402

from stiti import profile                                                # noqa: E402
from stiti.db import q                                                   # noqa: E402

q("TRUNCATE facts, entities, episode_mentions, user_directives, lessons RESTART IDENTITY CASCADE")
q("DELETE FROM owner_profile")
profile._all.cache_clear()

# ---------------------------------------------------------------- 1. a fresh install knows nobody
print("fresh install: no trace of anyone")
from stiti.voice import glossary, stt, wake                              # noqa: E402

check("she doesn't know a name: says 'you', writes 'the owner', uses they/them",
      profile.call() == "you" and profile.name() == "the owner" and profile.p() == "they" and not profile.known())
check("wakes only on the default phrases", wake.phrases() == wake.DEFAULT_PHRASES and wake.extra_phrases() == [])
check("…'Hey Stiti' works, a personal phrase doesn't", wake.detect("Hey Stiti, what's up")[0]
      and not wake.detect("Wake up sunshine")[0])
check("Whisper's wake line is generic", stt.wake_line() == "Hey Stiti.", stt.wake_line())
check("status hint is generic", wake.hint() == "“Hey Stiti”", wake.hint())
terms = [t.text for t in glossary.build()]
check("the ears' glossary holds only the words every user says", set(terms) <= set(glossary.FIXED), str(terms))

from stiti.engine import Engine                                          # noqa: E402


from stiti.brain import compiler, examples, mdsync                       # noqa: E402

mdsync.render_all()
compiler._file("SOUL.md", compiler.DEFAULT_SOUL)
examples.text()
written = {p.name: p.read_text(errors="ignore") for p in FRESH.rglob("*")
           if p.is_file() and not p.is_symlink() and "models" not in p.parts and p.stat().st_size < 2_000_000}
check("she wrote her files (SOUL.md, USER.md, LESSONS.md)", {"SOUL.md", "USER.md", "LESSONS.md"} <= set(written),
      str(sorted(written)))
names = set()
for text in written.values():
    names |= {t.lower() for t in pc.proper_terms(text)}
shipped = set()                    # words in the code's own templates (the code itself is guarded by privacy_check)
for f in (ROOT / "src" / "stiti").rglob("*.py"):
    shipped |= {t.lower() for t in pc.proper_terms(f.read_text(errors="ignore"))}
check("nothing she wrote names anyone: every name-like word comes from the shipped templates", names <= shipped,
      str(sorted(names - shipped)))
check("the SOUL template names nobody", "the owner" in written["SOUL.md"] and "{name}" not in written["SOUL.md"])
check("USER.md is an empty template", "(nothing yet)" in written["USER.md"] and "- [F" not in written["USER.md"])

eng = Engine("text")
hello = eng.greet()
check("first wake offers the intro", "intro" in hello.lower(), hello)
first = eng.turn("intro shuru karo")
check("the intro starts by asking what to call them", "call you" in first.lower(), first)
reply = eng.turn("Call me Meera")
profile._all.cache_clear()
check("the answer is saved in the LOCAL profile", profile.get("name") == "Meera" and profile.call() == "Meera",
      str(profile._all()))
check("…and the next question follows", "live" in reply.lower(), reply)
eng.turn("bas")
q("DELETE FROM owner_profile")
q("TRUNCATE facts, entities, episode_mentions, user_directives, lessons RESTART IDENTITY CASCADE")
profile._all.cache_clear()

# ---------------------------------------------------------------- 2. the privacy check, on a fake profile
print("privacy check: a made-up person, a fake repo")
HOME = Path(tempfile.mkdtemp(prefix="stiti-privhome-"))
REPO = Path(tempfile.mkdtemp(prefix="stiti-privrepo-"))
(HOME / "USER.md").write_text("""# USER — who Ravi is

## About me
- [F1] Ravi Kumar is a final-year student at Lakeview College of Engineering.
- [F2] Ravi built Tilecraft, a puzzle app, and plays chess on weekends.
""")
(HOME / "vocab.json").write_text(json.dumps({"terms": {"Parkly": {"heard": ["Park Lee"], "source": "explicit"}}}))
(HOME / "privacy_terms.txt").write_text("# my own extra words\n42 Banyan Lane\n")
q("""INSERT INTO owner_profile(key, value, source) VALUES ('name','Ravi','test'), ('call_me','Ravi','test'),
     ('say_as', '{"Ravi": "Rahvee"}', 'test'), ('wake_phrases', '["wake up sunshine", "hey stiti"]', 'test')""")
q("INSERT INTO entities(kind, name, privacy) VALUES ('person','Anvika',1), ('org','Orbitly Labs',1), "
  "('self','Ravi',1), ('thing','startup',1)")
q("""INSERT INTO facts(subj_id, predicate, obj_literal, fact_text, origin)
     SELECT id, 'interned_at', 'Orbitly Labs', 'Ravi interned at Orbitly Labs in Bengaluru', 'test' FROM entities
     WHERE kind='self'""")
DSN = os.environ["STITI_DB"]

files = {
    "src/app.py": "# talks to the owner\nNAME = 'Ravi'  # leaked\nprint('hello')\n",
    "src/ok.py": "# Ravioli and orbit math are fine\nx = 'ravishing'\nwake = 'hey stiti'\n",
    "docs/notes.md": "He studies at Lakeview College of Engineering.\nNothing here.\nHe built tilecraft.\n",
    "docs/wake.md": "Say “Wake up sunshine” to wake her.\n",
    "docs/home.md": "Lives at 42 Banyan Lane.\n",
    "docs/vocab.md": "Add Parkly to the dictionary.\n",
    "docs/friend.md": "Anvika called, and Orbitly Labs too.\n",
    "LICENSE": "Copyright (c) 2026 Ravi Kumar\n",
    "README.md": "Clone https://github.com/Ravi/Stiti and run it.\n",
    "docs/cities.md": "It's 24 and clear in Bengaluru.\n",
    "assets/blob.bin": None,
    "docs/Ravi_resume.md": "nothing personal inside\n",
}
for f, body in files.items():
    p = REPO / f
    p.parent.mkdir(parents=True, exist_ok=True)
    if body is None:
        p.write_bytes(b"\x00\x01Ravi\x00" * 10)
    else:
        p.write_text(body)
(REPO / "untracked.md").write_text("Ravi\n")
G = ["git", "-C", str(REPO), "-c", "user.name=t", "-c", "user.email=t@example.invalid", "-c", "commit.gpgsign=false"]
subprocess.run(G[:3] + ["init", "-q"], check=True)
subprocess.run(G + ["add", *files], check=True)
subprocess.run(G + ["commit", "-q", "-m", "fake"], check=True)

loaded = pc.load_terms(HOME, DSN)
cats = set(loaded.values())
check("terms come from every local source", {"owner name", "wake phrase", "person", "org", "profile fact",
                                             "vocab word", "private term"} <= cats, str(sorted(cats)))
check("ordinary words / default wake phrases / generic entities are not terms",
      not ({"hey stiti", "startup", "chess", "weekends", "bengaluru"} & {t.lower() for t in loaded}), str(sorted(loaded)))


def run(*argv: str, env: dict | None = None) -> tuple[int, str]:
    out = io.StringIO()
    old = {k: os.environ.get(k) for k in (env or {})}
    os.environ.update(env or {})
    try:
        with contextlib.redirect_stdout(out):
            code = pc.main(list(argv))
    finally:
        for k, v in old.items():
            os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
    return code, out.getvalue()


code, out = run("--home", str(HOME), "--db", DSN, "--repo", str(REPO))
hits = {ln.split()[0] for ln in out.splitlines() if ":" in ln.split()[0] and not ln.startswith("privacy check")}
want = {"src/app.py:2", "docs/notes.md:1", "docs/notes.md:3", "docs/wake.md:1", "docs/home.md:1", "docs/vocab.md:1",
        "docs/friend.md:1"}
check("exit 1 on leaks", code == 1, out)
check("finds every leaked line (name, college, project, wake phrase, address, vocab word, friend, employer)",
      want <= hits, str(sorted(hits)))
check("no false alarms: 'Ravioli', 'ravishing', 'hey stiti', a big city, the copyright line, a public repo URL",
      not ({"src/ok.py:1", "src/ok.py:2", "src/ok.py:3", "docs/cities.md:1", "LICENSE:1", "README.md:1"} & hits),
      str(sorted(hits)))
check("a file NAMED after them is caught", "docs/Ravi_resume.md" in out and "(file name)" in out)
check("binary and untracked files are skipped", "blob.bin" not in out and "untracked.md" not in out)
secret_values = ["Ravi", "Kumar", "Lakeview", "Tilecraft", "sunshine", "Banyan", "Parkly", "Anvika", "Orbitly",
                 "Rahvee"]
check("the output never contains a value — only file:line + category",
      not [v for v in secret_values if v.lower() in out.lower().replace("ravi_resume", "")], out)
cats_out = {ln.split("  ", 1)[1].replace(" (file name)", "") for ln in out.splitlines()
            if "  " in ln and not ln.startswith("privacy check")}
check("each hit has a category", cats_out <= {"owner name", "wake phrase", "person", "org", "profile fact",
                                               "vocab word", "private term", "project", "place"}, str(cats_out))

(REPO / "privacy_allow.txt").write_text("")
(HOME / "privacy_allow.txt").write_text("tilecraft\n")
code, out = run("--home", str(HOME), "--db", DSN, "--repo", str(REPO))
check("a word in the LOCAL allow list is no longer flagged", "docs/notes.md:3" not in out and "docs/notes.md:1" in out,
      out)

(REPO / "src" / "new.py").write_text("who = 'Anvika'  # Lakeview College of Engineering\n")
(REPO / "src" / "clean.py").write_text("x = 1\n")
subprocess.run(G + ["add", "src/new.py", "src/clean.py"], check=True)
code, out = run("--home", str(HOME), "--db", DSN, "--repo", str(REPO), "--staged")
check("--staged scans only what is staged", code == 1 and "src/new.py:1" in out and "docs/" not in out, out)

EMPTY = Path(tempfile.mkdtemp(prefix="stiti-nohome-"))
code, out = run("--home", str(EMPTY), "--db", "none", "--repo", str(REPO))
check("no local profile (fresh clone) → skips cleanly, exit 0", code == 0 and "nothing to check" in out, out)
code, out = run("--home", str(HOME), "--db", DSN, "--repo", str(REPO), env={"CI": "true"})
check("in CI → skips cleanly, exit 0", code == 0 and "nothing to check" in out, out)
code, out = run("--home", str(HOME), "--db", "none", "--repo", str(REPO))
check("works from the home files alone (no database)", code == 1 and "docs/notes.md:1" in out, out)

print("pre-commit hook (opt-in)")
code, out = run("--repo", str(REPO), "--install-hook")
hook = REPO / ".git" / "hooks" / "pre-commit"
check("--install-hook writes an executable hook", hook.exists() and os.access(hook, os.X_OK) and pc.HOOK_MARK in
      hook.read_text(), out)
(REPO / "scripts").mkdir(exist_ok=True)
shutil.copy(ROOT / "scripts" / "privacy_check.py", REPO / "scripts" / "privacy_check.py")
henv = {**os.environ, "STITI_HOME": str(HOME), "STITI_DB": "none"}
henv.pop("CI", None)
r = subprocess.run(G + ["commit", "-q", "-m", "leak"], env=henv, capture_output=True, text=True)
check("the hook blocks a commit that leaks", r.returncode != 0 and "src/new.py:1" in r.stdout + r.stderr,
      r.stdout + r.stderr)
check("…and still prints no value", "Anvika" not in r.stdout + r.stderr)
subprocess.run(G + ["rm", "-q", "--cached", "src/new.py"], check=True)
subprocess.run(G + ["add", "scripts/privacy_check.py"], check=True)
r = subprocess.run(G + ["commit", "-q", "-m", "clean"], env=henv, capture_output=True, text=True)
check("a clean commit goes through", r.returncode == 0, r.stdout + r.stderr)
hook.write_text("#!/bin/sh\necho mine\n")
code, out = run("--repo", str(REPO), "--install-hook")
check("someone else's hook is never overwritten", "left alone" in out and "echo mine" in hook.read_text(), out)
hook.unlink()
run("--repo", str(REPO), "--install-hook")
code, out = run("--repo", str(REPO), "--uninstall-hook")
check("--uninstall-hook removes ours", not hook.exists(), out)

# ---------------------------------------------------------------- 3. LaunchAgent: older label → com.stiti.app
print("LaunchAgent move (faked launchctl)")
from stiti import install_app as ia                                      # noqa: E402

T = Path(tempfile.mkdtemp(prefix="stiti-la-"))
ia.APP = T / "Applications" / "Stiti.app"
ia.AGENTS_DIR = T / "LaunchAgents"
ia.AGENT = ia.AGENTS_DIR / f"{ia.LABEL}.plist"
ia.AGENTS_DIR.mkdir(parents=True)
(ia.APP / "Contents").mkdir(parents=True)
with open(ia.APP / "Contents" / "Info.plist", "wb") as f:
    plistlib.dump({"CFBundleIdentifier": "org.example.older"}, f)
with open(ia.AGENTS_DIR / "org.example.older.plist", "wb") as f:
    plistlib.dump({"Label": "org.example.older", "ProgramArguments": ["/usr/bin/open", "-a", str(ia.APP)]}, f)
with open(ia.AGENTS_DIR / "com.other.tool.plist", "wb") as f:
    plistlib.dump({"Label": "com.other.tool", "ProgramArguments": ["/usr/bin/true"]}, f)
calls: list[list[str]] = []
_real_run = subprocess.run
subprocess.run = lambda cmd, *a, **k: calls.append(list(cmd)) or subprocess.CompletedProcess(cmd, 0, b"", b"")
check("the label is the same generic one for everyone", ia.LABEL == "com.stiti.app")
check("an older Stiti agent is found by what it runs", [x[0] for x in ia.legacy_agents()] == ["org.example.older"])
msg = ia.migrate()
check("migrate: old agent booted out and removed", not (ia.AGENTS_DIR / "org.example.older.plist").exists()
      and any(c[:2] == ["launchctl", "bootout"] and c[2].endswith("/org.example.older") for c in calls), msg)
check("…new com.stiti.app agent installed and loaded", ia.AGENT.exists()
      and any(c[:2] == ["launchctl", "bootstrap"] for c in calls), msg)
check("…other agents untouched", (ia.AGENTS_DIR / "com.other.tool.plist").exists())
with open(ia.APP / "Contents" / "Info.plist", "rb") as f:
    bid = plistlib.load(f)["CFBundleIdentifier"]
check("…the app keeps its bundle id (macOS keeps mic / Calendar / Reminders grants)", bid == "org.example.older", bid)
check("…and the running app is neither rebuilt nor started again", not any(c[:1] in (["open"], ["codesign"])
      for c in calls), str(calls))
n = len(calls)
check("migrate is idempotent", "already" in ia.migrate() and len(calls) == n)
ia.install(start_now=False)
with open(ia.APP / "Contents" / "Info.plist", "rb") as f:
    bid = plistlib.load(f)["CFBundleIdentifier"]
check("a later install-app keeps the existing bundle id too", bid == "org.example.older", bid)
shutil.rmtree(ia.APP)
ia.install(start_now=False)
with open(ia.APP / "Contents" / "Info.plist", "rb") as f:
    bid = plistlib.load(f)["CFBundleIdentifier"]
check("a brand-new install gets the generic id", bid == "com.stiti.app", bid)
subprocess.run = _real_run
from stiti import migrate_local                                          # noqa: E402

lines = migrate_local.run(["--wake", "Wake up sunshine", "--wake", "Hey Stiti"])
profile._all.cache_clear()
check("migrate-local --wake saves the owner's phrase locally", "wake up sunshine" in wake.extra_phrases()
      and wake.extra_phrases().count("wake up sunshine") == 1, str(lines))
lines2 = migrate_local.run(["--wake", "Wake up sunshine"])
check("…and a second run changes nothing", wake.extra_phrases() == ["wake up sunshine"], str(lines2))

for d in (FRESH, HOME, REPO, EMPTY, T):
    shutil.rmtree(d, ignore_errors=True)
print(f"\nprivacy: {passed}/{total} checks passed")
sys.exit(0 if passed == total else 1)
