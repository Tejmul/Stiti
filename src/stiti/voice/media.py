"""Media pause while Stiti listens (Wispr Flow's shouldPauseAudio, D29).

When she wakes up, music that is ACTUALLY playing in Spotify / Apple Music is paused (clean audio for STT, and it
feels like Jarvis). When she goes back to sleep — or the session sits idle — exactly what she paused is resumed.
Never starts playback that wasn't playing, never touches an app that isn't running (AppleScript `is running` doesn't
launch it), and if he (or "play music") started something meanwhile she leaves it alone. Switch: owner_profile
media_pause = on/off (default on); STITI_MEDIA_PAUSE=off overrides (tests, dev).
"""
from __future__ import annotations

import os
import subprocess
from typing import Callable

APPS = ("Spotify", "Music")
RESUME_AFTER_SLEEP_S = 1.0     # let the falling chime / goodbye finish first
IDLE_RESUME_S = 20.0           # awake but nothing happening this long → give him his music back


def osascript(script: str) -> str:
    try:
        r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=3)
        return (r.stdout or "").strip()
    except Exception:
        return ""


def enabled() -> bool:
    if os.getenv("STITI_MEDIA_PAUSE", "").lower() in ("off", "0", "no"):
        return False
    try:
        from .. import profile
        return (profile.get("media_pause", "on") or "on").lower() not in ("off", "0", "no", "false")
    except Exception:
        return True


class MediaPauser:
    """update(awake, idle_s, busy) is called ~4×/s from one background thread; all AppleScript runs there."""

    def __init__(self, run: Callable[[str], str] | None = None, *, is_enabled: Callable[[], bool] | None = None,
                 log: Callable[[str], None] | None = None):
        self.run = run or osascript
        self.is_enabled = is_enabled or enabled
        self.log = log or (lambda m: None)
        self.paused: list[str] = []          # apps WE paused (only these are ever resumed)
        self.session = False                 # inside an awake session we already handled
        self.asleep_since: float | None = None

    # ---- AppleScript (never launches an app)
    def _running(self, app: str) -> bool:
        return self.run(f'application "{app}" is running').lower() == "true"

    def _state(self, app: str) -> str:
        return self.run(f'tell application "{app}" to player state as string').lower()

    def playing(self) -> list[str]:
        return [a for a in APPS if self._running(a) and self._state(a) == "playing"]

    def pause(self) -> list[str]:
        if not self.is_enabled():
            return []
        apps = self.playing()
        for a in apps:
            self.run(f'tell application "{a}" to pause')
        self.paused += [a for a in apps if a not in self.paused]
        if apps:
            self.log(f"paused {', '.join(apps)}")
        return apps

    def resume(self) -> list[str]:
        back = []
        for a in self.paused:
            if self._running(a) and self._state(a) == "paused":     # still paused by us (not stopped/quit/replaced)
                self.run(f'tell application "{a}" to play')
                back.append(a)
        self.paused = []
        if back:
            self.log(f"resumed {', '.join(back)}")
        return back

    # ---- the decision (pure apart from the calls above)
    def update(self, awake: bool, now: float, *, idle_s: float = 0.0, busy: bool = False) -> str | None:
        """Returns "pause" / "resume" when it acted, else None."""
        if awake:
            self.asleep_since = None
            if not self.session:                        # she just woke up: once per session
                self.session = True
                return "pause" if self.pause() else None
            if self.paused and idle_s >= IDLE_RESUME_S and not busy:
                return "resume" if self.resume() else None
            return None
        if not self.session:
            return None
        if self.asleep_since is None:
            self.asleep_since = now
        if now - self.asleep_since < RESUME_AFTER_SLEEP_S:
            return None
        self.session, self.asleep_since = False, None
        return "resume" if self.resume() else None
