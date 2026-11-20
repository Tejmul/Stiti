"""`stiti install-app`: build ~/Applications/Stiti.app (menubar, no Dock icon), ad-hoc sign it, and
start it at login via a LaunchAgent that opens the app through LaunchServices (so macOS attributes
mic / Calendar / Reminders permissions to "Stiti"). `stiti uninstall-app` removes both.

The LaunchAgent label is the same generic `com.stiti.app` for every user. An older install under another label
(any LaunchAgent that opens ~/Applications/Stiti.app) is booted out and removed on the next install / migrate-local;
the app's existing bundle identifier is kept so macOS doesn't ask for mic / Calendar / Reminders access again.
"""
from __future__ import annotations

import os
import plistlib
import shutil
import subprocess
from pathlib import Path

from .config import CFG, REPO

APP = Path.home() / "Applications" / "Stiti.app"
LABEL = "com.stiti.app"
AGENTS_DIR = Path.home() / "Library" / "LaunchAgents"
AGENT = AGENTS_DIR / f"{LABEL}.plist"

LAUNCHER = """#!/bin/bash
# Stiti launcher: runs the menubar app from the repo's venv; restarts it if it crashes.
REPO="{repo}"
LOGDIR="$HOME/.stiti/logs"
mkdir -p "$LOGDIR"
if [ ! -x "$REPO/.venv/bin/python" ]; then
  echo "[launcher] $(date): no Stiti code at $REPO (moved?) — run 'uv run stiti install-app' from the repo" >> "$LOGDIR/app.log"
  exit 1
fi
cd "$REPO" || exit 1
while true; do
  "$REPO/.venv/bin/python" -m stiti app >> "$LOGDIR/app.log" 2>&1
  [ $? -eq 0 ] && exit 0
  echo "[launcher] Stiti exited with an error, restarting in 5 s" >> "$LOGDIR/app.log"
  sleep 5
done
"""


def legacy_agents() -> list[tuple[str, Path]]:
    """LaunchAgents from an older Stiti install under another label: (label, plist path). Found by what they run
    (open -a ~/Applications/Stiti.app), not by name, so nothing user-specific lives in the code."""
    out = []
    for p in sorted(AGENTS_DIR.glob("*.plist")) if AGENTS_DIR.exists() else []:
        if p == AGENT:
            continue
        try:
            with open(p, "rb") as f:
                d = plistlib.load(f)
        except Exception:
            continue
        args = [str(a) for a in d.get("ProgramArguments") or []]
        if d.get("Label") and str(APP) in args:
            out.append((str(d["Label"]), p))
    return out


def remove_legacy_agents() -> list[str]:
    """Boot out + delete older Stiti LaunchAgents. The running app keeps running (it was only started by them)."""
    uid, gone = os.getuid(), []
    for label, p in legacy_agents():
        subprocess.run(["launchctl", "bootout", f"gui/{uid}/{label}"], capture_output=True)
        p.unlink(missing_ok=True)
        gone.append(label)
    return gone


def _bundle_id() -> str:
    """Keep an installed app's bundle id (macOS ties mic / Calendar / Reminders grants to it); new installs get LABEL."""
    try:
        with open(APP / "Contents" / "Info.plist", "rb") as f:
            return str(plistlib.load(f).get("CFBundleIdentifier") or LABEL)
    except Exception:
        return LABEL


def migrate() -> str:
    """One-time move from an older LaunchAgent label to LABEL. Idempotent; never starts a second copy of the app."""
    old = legacy_agents()
    if not old:
        return f"LaunchAgent: already {LABEL}." if AGENT.exists() else "LaunchAgent: Stiti.app not installed (nothing to move)."
    if not APP.exists():
        remove_legacy_agents()
        return f"LaunchAgent: removed {len(old)} old login item(s); Stiti.app isn't installed (run `stiti install-app`)."
    install(start_now=False)
    return f"LaunchAgent: moved {len(old)} old login item(s) to {LABEL} (the running app was left alone)."


def install(start_now: bool = True) -> str:
    bundle_id = _bundle_id()
    remove_legacy_agents()
    contents = APP / "Contents"
    (contents / "MacOS").mkdir(parents=True, exist_ok=True)
    (contents / "Resources").mkdir(exist_ok=True)
    info = {
        "CFBundleName": "Stiti", "CFBundleDisplayName": "Stiti", "CFBundleIdentifier": bundle_id,
        "CFBundleExecutable": "Stiti", "CFBundlePackageType": "APPL", "CFBundleVersion": "0.1.0",
        "CFBundleShortVersionString": "0.1.0", "LSUIElement": True, "LSMinimumSystemVersion": "13.0",
        "NSMicrophoneUsageDescription": "Stiti listens for “Hey Stiti” and to what you say to her.",
        "NSCalendarsFullAccessUsageDescription": "Stiti reads your calendar to plan your day and answer “what's on today”.",
        "NSCalendarsUsageDescription": "Stiti reads your calendar to plan your day.",
        "NSRemindersFullAccessUsageDescription": "Stiti puts your alarms and reminders in Reminders so they ring on your iPhone.",
        "NSRemindersUsageDescription": "Stiti saves your alarms and reminders to Reminders.",
    }
    with open(contents / "Info.plist", "wb") as f:
        plistlib.dump(info, f)
    exe = contents / "MacOS" / "Stiti"
    exe.write_text(LAUNCHER.format(repo=REPO))
    exe.chmod(0o755)
    subprocess.run(["codesign", "--force", "--deep", "--sign", "-", str(APP)], check=True, capture_output=True)

    AGENT.parent.mkdir(parents=True, exist_ok=True)
    with open(AGENT, "wb") as f:
        plistlib.dump({"Label": LABEL, "ProgramArguments": ["/usr/bin/open", "-a", str(APP)],
                       "RunAtLoad": True, "ProcessType": "Interactive"}, f)
    uid = os.getuid()
    subprocess.run(["launchctl", "bootout", f"gui/{uid}/{LABEL}"], capture_output=True)
    subprocess.run(["launchctl", "bootstrap", f"gui/{uid}", str(AGENT)], capture_output=True)
    if start_now:
        subprocess.run(["open", "-a", str(APP)])
    return f"Installed {APP} (starts at login). Logs: {CFG.home / 'logs' / 'app.log'}"


def uninstall() -> str:
    remove_legacy_agents()
    subprocess.run(["launchctl", "bootout", f"gui/{os.getuid()}/{LABEL}"], capture_output=True)
    subprocess.run(["pkill", "-f", "-m", "1", "python -m stiti app"], capture_output=True)
    AGENT.unlink(missing_ok=True)
    shutil.rmtree(APP, ignore_errors=True)
    return "Stiti.app and its login item removed. Your memory (Postgres + ~/.stiti) is untouched."
