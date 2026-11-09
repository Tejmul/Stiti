"""Encrypted backups of Stiti's whole mind (runs in the night job; `stiti backup` anytime).

What: pg_dump of the brain (episodes, facts, lessons, tasks, …) + SOUL/USER/LESSONS/GRAPH_REPORT.md,
learned exemplars, voice baseline, onboarding + MCP pins → tar.gz → AES-256 (openssl, PBKDF2 200k).
Key: random 256-bit, kept in the macOS Keychain (service "stiti-backup"); `stiti backup --show-key`
prints it so you can also save it in a password manager — without it, backups can't be opened.
Where: ~/.stiti/backups (14 newest kept) + optional mirror dir STITI_BACKUP_MIRROR (e.g. iCloud Drive).
Restore never touches the live brain: it goes into a NEW database and a separate folder.
"""
from __future__ import annotations

import os
import secrets
import shutil
import subprocess
import tarfile
import tempfile
from datetime import datetime
from pathlib import Path

from ..config import CFG

PG = Path("/opt/homebrew/opt/postgresql@18/bin")
DIR = CFG.home / "backups"
KEEP = int(os.getenv("STITI_BACKUP_KEEP", "14"))
FILES = ["SOUL.md", "USER.md", "LESSONS.md", "GRAPH_REPORT.md", "exemplars.jsonl", "voice_baseline.json",
         "onboarding.json", "mcp.json", "mcp_pins.json"]
SERVICE, ACCOUNT = "stiti-backup", "stiti"


def _bin(name: str) -> str:
    p = PG / name
    return str(p) if p.exists() else (shutil.which(name) or name)


def key(create: bool = True) -> str:
    r = subprocess.run(["security", "find-generic-password", "-s", SERVICE, "-a", ACCOUNT, "-w"],
                       capture_output=True, text=True)
    if r.returncode == 0 and r.stdout.strip():
        return r.stdout.strip()
    if not create:
        raise RuntimeError("no backup key in Keychain")
    k = secrets.token_hex(32)
    subprocess.run(["security", "add-generic-password", "-s", SERVICE, "-a", ACCOUNT, "-w", k, "-U",
                    "-l", "Stiti backup key"], check=True, capture_output=True)
    return k


def _openssl(args: list[str], k: str) -> None:
    subprocess.run(["openssl", "enc", "-aes-256-cbc", "-pbkdf2", "-iter", "200000", *args, "-pass", "env:STITI_BK"],
                   check=True, capture_output=True, env={**os.environ, "STITI_BK": k})


def backup(verbose: bool = False) -> Path:
    DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(CFG.tz).strftime("%Y%m%d-%H%M%S")
    out = DIR / f"stiti-{ts}.tar.gz.enc"
    with tempfile.TemporaryDirectory() as td:
        t = Path(td)
        subprocess.run([_bin("pg_dump"), "-Fc", "--no-owner", "-d", CFG.db_url, "-f", str(t / "brain.dump")],
                       check=True, capture_output=True)
        with tarfile.open(t / "bundle.tar.gz", "w:gz") as tar:
            tar.add(t / "brain.dump", arcname="brain.dump")
            for name in FILES:
                p = CFG.home / name
                if p.exists():
                    tar.add(p, arcname=f"files/{name}")
        _openssl(["-salt", "-in", str(t / "bundle.tar.gz"), "-out", str(out)], key())
    out.chmod(0o600)
    mirror = os.getenv("STITI_BACKUP_MIRROR")
    if mirror:
        Path(mirror).expanduser().mkdir(parents=True, exist_ok=True)
        shutil.copy2(out, Path(mirror).expanduser() / out.name)
    for old in sorted(DIR.glob("stiti-*.tar.gz.enc"))[:-KEEP]:
        old.unlink()
    if verbose:
        print(f"backup → {out} ({out.stat().st_size / 1024:.0f} KB)")
    return out


def restore(path: str, into_db: str = "stiti_restored") -> dict:
    """Decrypt + restore into a NEW database and ~/.stiti/restored-<ts>/. The live brain is untouched."""
    src = Path(path).expanduser()
    dest = CFG.home / f"restored-{datetime.now(CFG.tz):%Y%m%d-%H%M%S}"
    with tempfile.TemporaryDirectory() as td:
        t = Path(td)
        _openssl(["-d", "-in", str(src), "-out", str(t / "bundle.tar.gz")], key(create=False))
        with tarfile.open(t / "bundle.tar.gz", "r:gz") as tar:
            tar.extractall(t, filter="data")
        r = subprocess.run([_bin("createdb"), into_db], capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(f"createdb {into_db}: {r.stderr.strip()} (choose another --into name)")
        subprocess.run([_bin("pg_restore"), "--no-owner", "-d", into_db, str(t / "brain.dump")],
                       capture_output=True)
        if (t / "files").exists():
            shutil.copytree(t / "files", dest)
    return {"database": into_db, "files": str(dest)}
