"""Visual demo of Stiti's desktop overlay (no mic, no brain, no database).

    PYTHONPATH=src .venv/bin/python -m stiti.overlay.demo [--hold S] [--shots DIR] [--measure] [--all]

Cycles idle → listening (fake mic) → thinking → "Checking calendar" → speaking (fake voice) + to-do card →
speech ends → a to-do added on the card → "✓ Added" in the orb's capsule → hidden, in ~17 s. Ticking a row in the card only prints (no DB write).
--hold S      seconds per phase (default 1.6–3 s; use 6 for steadier CPU numbers)
--shots DIR   screencapture the top-centre region in each phase (overlay-<phase>.png) plus a tight crop of the
              orb, three per phase so its motion shows (orb-<phase>-<n>.png; native pixels: 2x on a Retina display)
--measure     print CPU % (this process + WindowServer) and memory (phys_footprint) per phase
--all         also show the reminders and headlines cards and a to-do card with long titles
--motion      only the card motion: a to-do added → one finished (✓, strike, folds away) → a reminder set → one
              cancelled; with --shots, a burst of frames through each animation (overlay-<phase>-<ms>.png)
--screen N    show it on display N (NSScreen.screens() index) instead of the one the pointer is on
"""
from __future__ import annotations

import argparse
import math
import os
import random
import re
import resource
import subprocess
import threading
import time

import AppKit
from PyObjCTools import AppHelper

from .. import overlay
from . import model
from .surface import pointer_screen, screen_anchor

TODOS = {"kind": "todos", "title": "5 things to do", "ts": time.time(), "items": [
    {"id": 1, "text": "Finish the resume draft", "meta": "due today, 4 PM"},
    {"id": 2, "text": "Reply to the placement cell", "meta": "due today, 6 PM"},
    {"id": 3, "text": "Revise graph algorithms", "meta": "due tomorrow, 10 AM"},
    {"id": 4, "text": "Buy a notebook", "meta": ""},
    {"id": 5, "text": "Call home", "meta": ""}]}
ADDED = {"kind": "todos", "title": "6 things to do", "ts": time.time(), "focus": {"op": "added", "ids": [6]},
         "items": TODOS["items"] + [{"id": 6, "text": "Start the resume", "meta": "due today, 4 PM"}]}
DONE = {"kind": "todos", "title": "4 things to do", "ts": time.time(), "focus": {"op": "done", "ids": [2]},
        "items": TODOS["items"]}
REMINDERS = {"kind": "reminders", "title": "Coming up", "ts": time.time(), "items": [
    {"id": 1, "text": "Alarm", "meta": "tomorrow, 7 AM · repeats"},
    {"id": 2, "text": "Stand-up call", "meta": "today, 5:30 PM"},
    {"id": 3, "text": "Drink water", "meta": "today, 6 PM · repeats"}]}
SET = dict(REMINDERS, items=REMINDERS["items"] + [{"id": 4, "text": "Call mom", "meta": "today, 8 PM"}],
           focus={"op": "set", "ids": [4]})
CANCELLED = dict(REMINDERS, focus={"op": "cancelled", "ids": [2]})
NEWS = {"kind": "news", "title": "AI updates", "ts": time.time(), "items": [
    {"id": None, "text": "A new open model tops the small-model leaderboard", "meta": "Hacker News"},
    {"id": None, "text": "Apple ships a Core ML update for on-device speech", "meta": "The Verge"},
    {"id": None, "text": "Faster retrieval for long memories", "meta": "arXiv"}]}
LONG = {"kind": "todos", "title": "9 things to do", "ts": time.time(), "items": [
    {"id": 1, "text": "Finish the resume draft and send it to the placement cell before the deadline",
     "meta": "due today, 4 PM"},
    {"id": 2, "text": "Reply to the placement cell about the interview slot", "meta": "due tomorrow, 10:30 AM"},
    {"id": 3, "text": "Revise graph algorithms", "meta": ""},
    {"id": 4, "text": "Buy a notebook", "meta": "due Sat"},
    {"id": 5, "text": "Call home", "meta": ""},
    {"id": 6, "text": "Gym", "meta": ""}]}


class FakeAudio(threading.Thread):
    """Speech-like RMS envelopes (syllables ~4–6 Hz, pauses) into overlay.level(), like Duplex._cb does."""

    def __init__(self):
        super().__init__(daemon=True)
        self.mode = None
        self.stop = threading.Event()

    def run(self):
        t0 = time.monotonic()
        while not self.stop.is_set():
            t = time.monotonic() - t0
            env = max(0.0, math.sin(t * 2 * math.pi * 4.7)) * (0.6 + 0.4 * math.sin(t * 1.3)) * 0.06
            env *= 0.0 if (t % 2.2) > 1.8 else 1.0              # breath pauses
            v = env + random.uniform(0, 0.003)
            overlay.level(v if self.mode == "mic" else 0.0, v if self.mode == "out" else 0.0)
            time.sleep(0.01)                                   # the audio callback runs every 10 ms


def _footprint(pid: int) -> float | None:
    try:
        out = subprocess.run(["footprint", "-p", str(pid)], capture_output=True, text=True, timeout=10).stdout
        m = re.search(r"phys_footprint:\s*([\d.]+)\s*([KMG]B)", out) or re.search(r"Footprint:\s*([\d.]+)\s*([KMG]B)", out)
        if not m:
            return None
        v, u = float(m.group(1)), m.group(2)
        return v / 1024 if u == "KB" else v * 1024 if u == "GB" else v
    except Exception:
        return None


def _cputime(pid: int) -> float | None:
    try:
        s = subprocess.run(["ps", "-o", "time=", "-p", str(pid)], capture_output=True, text=True, timeout=5).stdout.strip()
        parts = [float(x) for x in s.replace("-", ":").split(":")]
        sec = 0.0
        for p in parts:
            sec = sec * 60 + p
        return sec
    except Exception:
        return None


class Demo:
    def __init__(self, args):
        self.args = args
        self.audio = FakeAudio()
        self.results: list[tuple] = []
        self.pid = os.getpid()
        self.base_mb = None
        self.ws = None
        try:
            self.ws = int(subprocess.run(["pgrep", "-x", "WindowServer"], capture_output=True, text=True).stdout.split()[0])
        except Exception:
            pass
        h = args.hold
        phases = [("idle", h * 0.5 or 1.2, lambda: overlay.set_state("idle")),
                  ("listening", h or 3.0, self._listen),
                  ("thinking", h * 0.6 or 1.5, self._think),
                  ("doing", h * 0.6 or 1.5, lambda: overlay.set_state("thinking", "calendar")),
                  ("speaking-card", h or 3.0, self._speak_card),
                  ("card-after-speech", h * 0.8 or 2.5, self._speech_end),
                  ("added", h * 0.8 or 2.6, self._added),
                  ("confirm", h * 0.5 or 2.0, self._confirm)]
        if args.motion:
            show = lambda c: (lambda: (overlay.hide_card(), overlay.show_card(c, speaking=False)))  # noqa: E731
            phases = [("idle", 0.8, lambda: overlay.set_state("idle")),
                      ("added", 3.0, show(ADDED)), ("done", 3.2, show(DONE)),
                      ("reminder-set", 3.0, show(SET)), ("reminder-cancelled", 3.2, show(CANCELLED))]
        elif args.all:
            phases += [("reminders", h or 2.5, lambda: overlay.show_card(REMINDERS, speaking=False)),
                       ("news", h or 2.5, lambda: overlay.show_card(NEWS, speaking=False)),
                       ("long", h or 2.5, lambda: overlay.show_card(LONG, speaking=False))]
        phases += [("hidden", max(1.2, h * 0.5), self._sleep)]      # with --measure --hold: the machine's own baseline
        self.phases = phases

    def _listen(self):
        overlay.set_state("listening")
        self.audio.mode = "mic"

    def _think(self):
        self.audio.mode = None
        overlay.set_state("thinking")

    def _speak_card(self):
        overlay.set_state("listening")                         # a new turn: "Checking calendar" belongs to the last one
        overlay.set_state("speaking")
        self.audio.mode = "out"
        overlay.show_card(TODOS)

    def _speech_end(self):
        self.audio.mode = None
        overlay.speech_ended()
        overlay.set_state("listening")

    def _added(self):
        overlay.hide_card()
        overlay.show_card(ADDED, speaking=False)

    def _confirm(self):                                        # the one-line ✓ in the orb's capsule (no card)
        overlay.hide_card()
        overlay.show_card({"kind": "todo_added", "title": "Added", "ts": time.time(),
                           "items": [{"id": 6, "text": "Start the resume", "meta": "due today, 4 PM"}]}, speaking=False)

    def _sleep(self):
        overlay.set_state("hidden")

    def start(self):
        self.audio.start()
        self._run(0)

    def _run(self, i: int):
        if i >= len(self.phases):
            self.audio.stop.set()
            AppHelper.callLater(0.6, self._finish)
            return
        name, secs, fn = self.phases[i]
        print(f"[demo] {name}", flush=True)
        r0, w0 = self._cpu(), _cputime(self.ws) if (self.args.measure and self.ws) else None
        t0 = time.monotonic()
        fn()
        if self.args.shots and self.args.motion and name not in ("idle", "hidden"):
            for ms in (150, 450, 800, 1100, 1500, 2000, 2700):
                if ms / 1000 < secs:
                    AppHelper.callLater(ms / 1000, self._shot, f"{name}-{ms:04d}")
        elif self.args.shots:
            AppHelper.callLater(min(secs * 0.6, secs - 0.2), self._shot, name)
            if name != "hidden":
                for n, at in enumerate((0.35, 0.6, 0.85), 1):
                    AppHelper.callLater(secs * at, self._shot, f"{name}-{n}", True)
        AppHelper.callLater(secs, self._end_phase, i, name, t0, r0, w0)

    def _end_phase(self, i, name, t0, r0, w0):
        dt = time.monotonic() - t0
        if self.args.measure:
            cpu = (self._cpu() - r0) / dt * 100
            ws = ((_cputime(self.ws) - w0) / dt * 100) if (w0 is not None) else None
            threading.Thread(target=self._mem, args=(name, cpu, ws), daemon=True).start()
        self._run(i + 1)

    def _mem(self, name, cpu, ws):
        self.results.append((name, cpu, ws, _footprint(self.pid)))

    @staticmethod
    def _cpu() -> float:
        u = resource.getrusage(resource.RUSAGE_SELF)
        return u.ru_utime + u.ru_stime

    def _shot(self, name, orb=False):
        """The top-centre of the display the overlay is on (screencapture wants top-left-origin global points).
        orb=True: a tight crop of the orb / its capsule only."""
        scr = pointer_screen()
        cx, top = screen_anchor(scr)
        f = scr.frame()
        flip = AppKit.NSScreen.screens()[0].frame().size.height      # Cocoa y is up from the primary display's bottom
        if orb:                                                # the orb's own panel (disc or capsule) + a margin
            ui = overlay._ui
            pf = ui.orb.panel.frame() if ui is not None else None
            w, h = (pf.size.width if pf else model.ORB) + 24, int(model.ORB + 40)
            y = flip - top + model.TOP_GAP - 20
        else:
            w, h = 480, 520
            y = flip - (f.origin.y + f.size.height)
        path = os.path.join(self.args.shots, f"{'orb' if orb else 'overlay'}-{name}.png")
        threading.Thread(target=subprocess.run, daemon=True,
                         args=(["screencapture", "-x", f"-R{int(cx - w / 2)},{int(y)},{int(w)},{int(h)}", path],)).start()

    def _finish(self):
        if self.args.measure:
            time.sleep(1.0)
            print(f"[measure] baseline (AppKit, overlay not created): {self.base_mb} MB", flush=True)
            for name, cpu, ws, mb in self.results:
                wst = f"{ws:.1f} %" if ws is not None else "n/a"
                print(f"[measure] {name:18s} python {cpu:5.1f} %  WindowServer {wst:>7s}  footprint {mb} MB", flush=True)
        overlay.shutdown()
        AppHelper.stopEventLoop()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hold", type=float, default=0.0)
    ap.add_argument("--shots", default=None)
    ap.add_argument("--measure", action="store_true")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--motion", action="store_true")
    ap.add_argument("--screen", type=int, default=None)
    args = ap.parse_args()
    front = AppKit.NSWorkspace.sharedWorkspace().frontmostApplication()
    app = AppKit.NSApplication.sharedApplication()
    app.setActivationPolicy_(AppKit.NSApplicationActivationPolicyAccessory)   # like Stiti.app (LSUIElement)
    if args.shots:
        os.makedirs(args.shots, exist_ok=True)
        os.environ["STITI_OVERLAY_DEMO_CAPTURE"] = "1"   # demo cards hold fake data; the real app is never captured
    if args.screen is not None:                           # demo only: pin the overlay (and the shots) to one display
        from . import ui
        screens = list(AppKit.NSScreen.screens() or [])
        pick = lambda: screens[min(max(args.screen, 0), len(screens) - 1)]   # noqa: E731
        ui.pointer_screen = pick
        globals()["pointer_screen"] = pick
    demo = Demo(args)

    def go():
        if front is not None:                         # a bare python launch activates itself: give focus back
            front.activateWithOptions_(0)
        if args.measure:
            demo.base_mb = _footprint(demo.pid)
        ok = overlay.init(respect_lock=False, tick_todo=lambda tid, done: print(f"[demo] tick todo {tid} → "
                                                                                  f"{'done' if done else 'open'}") or True,
                          on_click=lambda: print("[demo] orb clicked → stop her"))
        if not ok:
            print("[demo] overlay unavailable (no display / AppKit)")
            AppHelper.stopEventLoop()
            return
        demo.start()
    AppHelper.callLater(0.3, go)
    AppHelper.runEventLoop(installInterrupt=True)


if __name__ == "__main__":
    main()
