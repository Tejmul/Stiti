"""Stiti menubar app (rumps): always-on voice + alarms + Telegram + nightly sleep, started at login.

Runs inside ~/Applications/Stiti.app (installed by `stiti install-app`) so macOS permission prompts
say "Stiti" and the mic/Calendar/Reminders permissions survive reboots (report: bare python under
launchd can get silent mic + silent EventKit denial).

Menubar icon: ◉ awake · ○ listening for the wake phrase · ⏸ muted · … starting
"""
from __future__ import annotations

import json
import os
import subprocess
import threading
import time
from datetime import datetime

import rumps

from .config import CFG

LOG = CFG.home / "logs"


class StitiApp(rumps.App):
    def __init__(self):
        super().__init__("Stiti", title="…", quit_button=None)
        self.status_item = rumps.MenuItem("Starting up…")
        self.listen_item = rumps.MenuItem("Listening", callback=self.toggle_listen)
        self.listen_item.state = 1
        self.menu = [self.status_item, None, self.listen_item,
                     rumps.MenuItem("Open life graph", callback=lambda _: self._bg(self._graph)),
                     rumps.MenuItem("Run sleep job now", callback=lambda _: self._bg(self._sleep)),
                     rumps.MenuItem("Open USER.md", callback=lambda _: subprocess.run(["open", str(CFG.home / "USER.md")])),
                     rumps.MenuItem("Open LESSONS.md", callback=lambda _: subprocess.run(["open", str(CFG.home / "LESSONS.md")])),
                     rumps.MenuItem("Open SOUL.md (her personality)", callback=lambda _: subprocess.run(["open", str(CFG.home / "SOUL.md")])),
                     rumps.MenuItem("Open logs", callback=lambda _: subprocess.run(["open", str(LOG)])),
                     None, rumps.MenuItem("Quit Stiti", callback=self.quit)]
        self.stop = threading.Event()
        self.loop = None
        self.last_sleep_day = None
        threading.Thread(target=self._boot, daemon=True).start()
        rumps.Timer(self._tick, 2).start()

    # ---------- background boot ----------
    def _boot(self):
        import numpy as np

        from . import embed, intent
        from .engine import Engine
        from .voice import stt
        from .voice.loop import VoiceLoop
        self._set_status("Loading memory…")
        embed.embed_query("warm up")
        intent._index()
        self._set_status("Loading ears & voice…")
        stt.transcribe(np.zeros(16000, dtype=np.float32))
        if os.getenv("STITI_VOICE_EMOTION", "emotion2vec") != "off":
            from .voice import emotion_model
            emotion_model.preload_async()
        self._permissions_check()
        threading.Thread(target=self._scheduler, daemon=True).start()
        from .connectors import telegram
        if telegram.token():
            threading.Thread(target=telegram.TelegramBot(Engine).run, args=(self.stop,), daemon=True).start()
        self.loop = VoiceLoop(Engine("voice"), aec=os.getenv("STITI_AEC", "on") != "off")
        self._set_status("Say “Hey Stiti” or “Wake up baby girl”")
        try:
            self.loop.run(self.stop)
        except Exception as e:
            self._set_status(f"Voice stopped: {type(e).__name__}")
            print(f"[app] voice loop error: {e}", flush=True)

    def _permissions_check(self):
        """Inside Stiti.app the Calendar/Reminders prompts can appear (they can't from a terminal)."""
        try:
            from .connectors import eventkit
            ev, rem = eventkit._request("events"), eventkit._request("reminders")
            n = len(eventkit.today_events()) if ev else 0
            print(f"[app] calendar access={ev} ({n} events today) reminders access={rem}", flush=True)
        except Exception as e:
            print(f"[app] eventkit check failed: {e}", flush=True)

    def _deliver(self, text: str, kind: str, present: bool) -> str | None:
        """Where a proactive nudge goes: voice if he's here, Telegram if away (important ones), else nowhere."""
        from .connectors import telegram
        subprocess.Popen(["osascript", "-e", f'display notification {json.dumps(text)} with title "Stiti"'])
        if present and self.loop is not None and not self.loop.paused.is_set():
            threading.Thread(target=self.loop.say, args=(text,), daemon=True).start()
            return "voice"
        if telegram.token() and telegram.owner() and kind in ("meeting_soon", "deadline", "followup"):
            telegram.send(text)
            return "telegram"
        return "notification" if present else None

    def _scheduler(self):
        from .connectors import telegram
        from .fastpath.handlers import fire_due
        from .life import proactive
        tracker, last_pro = proactive.PresenceTracker(), 0.0

        def notify(msg: str):
            print(msg, flush=True)
            telegram.send(msg)
            if self.loop is not None:
                threading.Thread(target=self.loop.say, args=(msg.replace("⏰", "").strip(),), daemon=True).start()
        while not self.stop.is_set():
            try:
                fire_due(notify=notify)
                if time.time() - last_pro >= 60:
                    last_pro = time.time()
                    pres = tracker.sample()
                    busy = self.loop is not None and (self.loop.awake or (self.loop.duplex and self.loop.duplex.playing))
                    for nid, kind, text in proactive.tick(pres, self._deliver, busy=bool(busy)):
                        print(f"[proactive] {kind}: {text}", flush=True)
                        if self.loop is not None:
                            self.loop.engine.last_nudge = (nid, time.time())
                now = datetime.now(CFG.tz)
                if now.hour == 3 and self.last_sleep_day != now.date():   # nightly consolidation at 03:00
                    self.last_sleep_day = now.date()
                    self._sleep()
            except Exception as e:
                print(f"[scheduler] {e}", flush=True)
            self.stop.wait(5)

    # ---------- menu actions ----------
    def _bg(self, fn):
        threading.Thread(target=fn, daemon=True).start()

    def _graph(self):
        from .brain.graphview import render
        render(open_browser=True)

    def _sleep(self):
        from .brain.sleep import run
        print(f"[sleep] {run(verbose=False).get('extract')}", flush=True)

    def toggle_listen(self, item):
        if self.loop is None:
            return
        item.state = 0 if item.state else 1
        (self.loop.paused.clear if item.state else self.loop.paused.set)()

    def _set_status(self, text: str):
        self.status_item.title = text

    def _tick(self, _):
        if self.loop is None:
            self.title = "…"
        elif self.loop.paused.is_set():
            self.title = "⏸"
        else:
            self.title = "◉" if self.loop.awake else "○"

    def quit(self, _):
        self.stop.set()
        time.sleep(0.3)
        rumps.quit_application()


def run():
    LOG.mkdir(parents=True, exist_ok=True)
    StitiApp().run()
