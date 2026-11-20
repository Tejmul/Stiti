"""`stiti migrate-local`: move per-user settings that older versions kept in the code into YOUR local setup.

Stiti's code is the same for everyone who forks it; everything personal lives on your Mac (Postgres `stiti` +
~/.stiti). Older versions hard-coded a few owner-specific things. This one-time, idempotent step moves them:

  - the login item: an older LaunchAgent label → the generic `com.stiti.app` (the running app is left alone, and
    the app keeps its bundle id so macOS doesn't ask for mic / Calendar / Reminders again)
  - your own wake phrases: pass them with `--wake "<phrase>"` (repeatable). They're saved in owner_profile
    (`wake_phrases`) and are never written to the repo. Later: `stiti wake add|remove "<phrase>"`.

Run it as often as you like: a second run changes nothing.

  uv run stiti migrate-local [--wake "<phrase>" ...] [--dry-run]
"""
from __future__ import annotations


def _wake_args(args: list[str]) -> list[str]:
    out, i = [], 0
    while i < len(args):
        if args[i] == "--wake" and i + 1 < len(args):
            out.append(args[i + 1])
            i += 2
            continue
        if args[i].startswith("--wake="):
            out.append(args[i].split("=", 1)[1])
        i += 1
    return [w for w in out if w.strip()]


def run(args: list[str]) -> list[str]:
    dry = "--dry-run" in args
    lines: list[str] = []
    from . import install_app
    old = install_app.legacy_agents()
    if dry:
        lines.append(f"LaunchAgent: would move {len(old)} old login item(s) to {install_app.LABEL}." if old
                     else "LaunchAgent: nothing to move.")
    else:
        lines.append(install_app.migrate())
    from .voice import wake
    for phrase in _wake_args(args):
        lines.append("Wake phrase: would add one of your own phrases." if dry else "Wake phrase: " + wake.add_phrase(phrase))
    have = wake.extra_phrases()
    lines.append(f"Your own wake phrases: {len(have)} saved locally" + ("" if have else
                 " (add yours: stiti migrate-local --wake \"<phrase>\")") + ".")
    return lines


def cli(args: list[str]) -> None:
    for line in run(args[1:]):
        print(line)
