"""`stiti install-app`: build ~/Applications/Stiti.app (menubar, no Dock icon), ad-hoc sign it, and
start it at login via a LaunchAgent that opens the app through LaunchServices (so macOS attributes
mic / Calendar / Reminders permissions to "Stiti"). `stiti uninstall-app` removes both.
"""
from __future__ import annotations

import os
import plistlib
import shutil
import subprocess
from pathlib import Path

from .config import CFG, REPO

APP = Path.home() / "Applications" / "Stiti.app"
AGENT = Path.home() / "Library" / "LaunchAgents" / "com.tejmul.stiti.plist"
LABEL = "com.tejmul.stiti"

LAUNCHER = """#!/bin/bash
# Stiti launcher: runs the menubar app from the repo's venv; restarts it if it crashes.
REPO="{repo}"
LOGDIR="$HOME/.stiti/logs"
mkdir -p "$LOGDIR"
cd "$REPO" || exit 1
while true; do
  "$REPO/.venv/bin/python" -m stiti app >> "$LOGDIR/app.log" 2>&1
  [ $? -eq 0 ] && exit 0
  echo "[launcher] Stiti exited with an error, restarting in 5 s" >> "$LOGDIR/app.log"
  sleep 5
done
"""


def install(start_now: bool = True) -> str:
    contents = APP / "Contents"
    (contents / "MacOS").mkdir(parents=True, exist_ok=True)
    (contents / "Resources").mkdir(exist_ok=True)
    info = {
        "CFBundleName": "Stiti", "CFBundleDisplayName": "Stiti", "CFBundleIdentifier": LABEL,
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
    subprocess.run(["launchctl", "bootout", f"gui/{os.getuid()}/{LABEL}"], capture_output=True)
    subprocess.run(["pkill", "-f", "-m", "1", "python -m stiti app"], capture_output=True)
    AGENT.unlink(missing_ok=True)
    shutil.rmtree(APP, ignore_errors=True)
    return "Stiti.app and its login item removed. Your memory (Postgres + ~/.stiti) is untouched."
