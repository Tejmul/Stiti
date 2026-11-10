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
from datetime import datetime, timedelta

import rumps

from .config import CFG

LOG = CFG.home / "logs"


class StitiApp(rumps.App):
    def __init__(self):
        super().__init__("Stiti", title="…", quit_button=None)
        self.status_item = rumps.MenuItem("Starting up…")
        self._ring_lock = threading.Lock()
        self.ringer = None
        self.listen_item = rumps.MenuItem("Listening", callback=self.toggle_listen)
        self.listen_item.state = 1
        self.thinking_item = rumps.MenuItem("—")
        self.emotion_item = rumps.MenuItem("Deep voice emotion", callback=self.toggle_emotion)
        self.emotion_item.state = int(os.getenv("STITI_VOICE_EMOTION", "off") != "off")
        self.menu = [self.status_item, self.thinking_item, None,
                     rumps.MenuItem("⏰ Stop alarm", callback=self.stop_alarm),
                     rumps.MenuItem("Type to Stiti…", callback=self.type_to_stiti),
                     rumps.MenuItem("Quick add todo…", callback=self.quick_todo), None,
                     self.listen_item, self.emotion_item,
                     rumps.MenuItem("Open mood timeline", callback=lambda _: self._bg(self._mood)),
                     rumps.MenuItem("Open life graph", callback=lambda _: self._bg(self._graph)),
                     rumps.MenuItem("Run sleep job now", callback=lambda _: self._bg(self._sleep)),
                     rumps.MenuItem("Open USER.md", callback=lambda _: subprocess.run(["open", str(CFG.home / "USER.md")])),
                     rumps.MenuItem("Open LESSONS.md", callback=lambda _: subprocess.run(["open", str(CFG.home / "LESSONS.md")])),
                     rumps.MenuItem("Open SOUL.md (her personality)", callback=lambda _: subprocess.run(["open", str(CFG.home / "SOUL.md")])),
                     rumps.MenuItem("Open logs", callback=lambda _: subprocess.run(["open", str(LOG)])),
                     None, rumps.MenuItem("Quit Stiti", callback=self.quit)]
        self.stop = threading.Event()
        self.loop = None
        self._voice_alive = False
        self.healthy = True
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
        if os.getenv("STITI_VOICE_EMOTION", "off") != "off":
            from .voice import emotion_model
            emotion_model.preload_async()
        self._permissions_check()
        threading.Thread(target=self._scheduler, daemon=True).start()
        from .connectors import telegram
        if telegram.token():
            threading.Thread(target=telegram.TelegramBot(Engine).run, args=(self.stop,), daemon=True).start()
        self.loop = VoiceLoop(Engine("voice"), aec=os.getenv("STITI_AEC", "on") != "off")
        self._set_status("Say “Hey Stiti” or “Wake up baby girl”")
        self._voice_alive = True
        try:
            self.loop.run(self.stop)
        except Exception as e:
            self._set_status(f"Voice stopped: {type(e).__name__}")
            print(f"[app] voice loop error: {e}", flush=True)
        finally:
            self._voice_alive = False

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
            if self.loop.silenced:            # he told her to stop: notification only until he wakes her
                return "notification"
            threading.Thread(target=self.loop.say, args=(text,), kwargs={"nudge": True}, daemon=True).start()
            return "voice"
        if telegram.token() and telegram.owner() and kind in ("meeting_soon", "deadline", "followup"):
            telegram.send(text)
            return "telegram"
        return "notification" if present else None

    def _sync_reminders(self):
        """Ticked off in Reminders (iPhone/Watch/Mac) → done in Stiti too."""
        from .connectors import eventkit
        from .db import q
        rows = q("SELECT id, ek_identifier FROM intents WHERE ek_identifier IS NOT NULL AND state IN ('pending','armed','fired')")
        done = set(eventkit.completed_ids([r["ek_identifier"] for r in rows]))
        for r in rows:
            if r["ek_identifier"] in done:
                q("UPDATE intents SET state='done' WHERE id=%s", (r["id"],))

    def _ring(self, row: dict):
        """Alarm / timer: ring (tone + voice, louder each round) until 'band karo' / '5 minute aur' / timeout."""
        from .life.alarms import Ringer
        with self._ring_lock:                         # two alarms at once ring one after the other
            r = Ringer(row, loop=self.loop, log=lambda m: print(m, flush=True))
            self.ringer = r
            if self.loop is not None:
                self.loop.ring_control = r.control
            subprocess.Popen(["osascript", "-e", f'display notification {json.dumps(row["payload"].get("say", "Alarm"))} '
                                                 'with title "Stiti ⏰" sound name "Glass"'])
            try:
                r.run()
            finally:
                if self.loop is not None:
                    self.loop.ring_control = None
                self.ringer = None

    def stop_alarm(self, _=None):
        if getattr(self, "ringer", None) is not None:
            self.ringer.stop()

    def _fire(self, present: bool):
        from .connectors import telegram
        from .life import alarms
        deliver, missed = alarms.due()
        for r in deliver:
            k = r["payload"].get("kind") or r["kind"]
            msg = r["payload"].get("say", "Reminder")
            print(f"⏰ [{k}] {msg}", flush=True)
            late = timedelta(minutes=r.get("late_min", 0))
            if k in ("alarm", "timer") and late <= alarms.RING_IF_LATE_UNDER:
                threading.Thread(target=self._ring, args=(r,), daemon=True).start()
            elif k in ("alarm", "timer"):                       # 10–30 min late: say it, don't blast a ring
                self._deliver(alarms.late_note(r), "alarm", present)
                q_done(r)
            elif k == "reminder":
                text = alarms.late_note(r) if late > timedelta(minutes=15) else f"Reminder: {msg}"
                where = self._deliver(text, "reminder", present and not alarms.quiet_now())
                if where != "voice" and telegram.token() and telegram.owner():
                    telegram.send(f"⏰ {msg}")
                q_done(r)
            else:                                     # check-ins / nudges
                self._deliver(msg, k, present)
                q_done(r)
        if missed:
            m = alarms.missed_summary(mark=False)
            if m:
                subprocess.Popen(["osascript", "-e", f'display notification {json.dumps(m)} with title "Stiti"'])
                self._missed_pending = True

    def _scheduler(self):
        from .life import alarms, proactive
        tracker, last_pro = proactive.PresenceTracker(), 0.0
        present = True
        if (m := alarms.missed_summary(mark=False)):     # e.g. the Mac was off this morning
            print(f"[alarms] {m}", flush=True)
            self._missed_pending = True
        while not self.stop.is_set():
            try:
                self._fire(present)
                if getattr(self, "_missed_pending", False) and self.loop is not None and self.loop.awake:
                    self._missed_pending = False          # tell him once, the next time he talks to her
                    if (m := alarms.missed_summary()):
                        threading.Thread(target=self.loop.say, args=(m,), daemon=True).start()
                if time.time() - last_pro >= 60:
                    last_pro = time.time()
                    self._health()
                    self._sync_reminders()
                    rotate_logs()
                    pres = tracker.sample()
                    present = bool(getattr(pres, "present", True))
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

    def _ask(self, title: str, prompt: str) -> str | None:
        w = rumps.Window(message=prompt, title=title, default_text="", ok="Send", cancel="Cancel",
                         dimensions=(320, 60))
        r = w.run()
        return r.text.strip() if r.clicked and r.text.strip() else None

    def type_to_stiti(self, _):
        text = self._ask("Stiti", "Type to Stiti (same brain as voice):")
        if text and self.loop is not None:
            reply = self.loop.engine.turn(text)
            rumps.alert(title="Stiti", message=reply)

    def quick_todo(self, _):
        text = self._ask("Quick add todo", "What do you need to do? (you can add a time: “kal 5 baje”)")
        if text:
            from .fastpath.handlers import todo
            rumps.notification("Stiti", "", todo(f"add todo {text}") or "Couldn't add that.")

    def toggle_emotion(self, item):
        item.state = 0 if item.state else 1
        os.environ["STITI_VOICE_EMOTION"] = "emotion2vec" if item.state else "off"

    def _mood(self):
        from .brain.moodview import render
        render(open_browser=True)

    def _health(self):
        """Heartbeat for `stiti doctor` + a ⚠ in the menubar when something is wrong."""
        h = {"ts": datetime.now(CFG.tz).isoformat(timespec="seconds"), "pid": os.getpid()}
        try:
            from .db import one
            one("SELECT 1 AS ok")
            h["db"] = "ok"
        except Exception as e:
            h["db"] = f"DOWN: {str(e)[:80]}"
        h["voice"] = "listening" if self.loop is not None and self._voice_alive else "down"
        h["awake"] = bool(self.loop and self.loop.awake)
        h["silenced"] = bool(self.loop and self.loop.silenced)
        self.healthy = h["db"] == "ok" and h["voice"] == "listening"
        (CFG.home / "health.json").write_text(json.dumps(h))

    def toggle_listen(self, item):
        if self.loop is None:
            return
        item.state = 0 if item.state else 1
        (self.loop.paused.clear if item.state else self.loop.paused.set)()

    def _set_status(self, text: str):
        self.status_item.title = text

    def _tick(self, _):
        if self.loop is not None and getattr(self.loop.engine, "last_debug", None):
            d = self.loop.engine.last_debug
            self.thinking_item.title = f"Last: {d.get('route')} · mood {d.get('mood')} · {d.get('latency_ms', {}).get('total', '?')} ms"
        if not self.healthy:
            self.title = "⚠"
        elif self.loop is None:
            self.title = "…"
        elif self.loop.paused.is_set():
            self.title = "⏸"
        elif self.loop.silenced:
            self.title = "🤫"
        else:
            self.title = "◉" if self.loop.awake else "○"

    def quit(self, _):
        self.stop.set()
        time.sleep(0.3)
        rumps.quit_application()


def q_done(row: dict) -> None:
    from .db import q
    if not row.get("rrule"):
        q("UPDATE intents SET state='done' WHERE id=%s AND state='fired'", (row["id"],))


def rotate_logs(max_mb: int = 10, keep: int = 3) -> None:
    """Copy app.log aside and truncate it in place (the launcher appends with >>, so writing continues)."""
    import shutil
    log = LOG / "app.log"
    if not log.exists() or log.stat().st_size < max_mb * 1024 * 1024:
        return
    for i in range(keep - 1, 0, -1):
        older = LOG / f"app.log.{i}"
        if older.exists():
            older.replace(LOG / f"app.log.{i + 1}")
    shutil.copyfile(log, LOG / "app.log.1")
    os.truncate(log, 0)


def run():
    import sys
    sys.stdout.reconfigure(line_buffering=True)   # log lines appear immediately (stdout is a file here)
    sys.stderr.reconfigure(line_buffering=True)
    LOG.mkdir(parents=True, exist_ok=True)
    rotate_logs()
    StitiApp().run()
