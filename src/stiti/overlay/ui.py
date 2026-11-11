"""The overlay controller (main thread only): pill + card + timers + click-away + accessibility.

The public, thread-safe API is in __init__.py; it marshals every call here with AppHelper.callAfter. Python runs
per frame only while the dots follow a level (listening / speaking), at ≤ 30 fps, and the timer is stopped in every
other state. A 4 Hz timer runs only while a card or a pill confirmation is up (auto-dismiss).
"""
from __future__ import annotations

import threading
import time
import traceback

import AppKit
import objc
from Foundation import NSObject, NSRunLoop, NSRunLoopCommonModes, NSTimer
from PyObjCTools import AppHelper

from . import model as M
from .card import Card
from .pill import Pill
from .surface import Access, pointer_screen, screen_anchor, screen_key, screen_locked


class _Target(NSObject):
    """Bridges NSTimer / NSNotification callbacks to a Python function."""

    def initWithFn_(self, fn):
        self = objc.super(_Target, self).init()
        if self is None:
            return None
        self.fn = fn
        return self

    def fire_(self, sender):
        try:
            self.fn()
        except Exception:
            traceback.print_exc()


def _db_tick(task_id: int, done: bool) -> bool:
    """Tick / un-tick a to-do in the brain (same write as the web app's /api/todo/{id}/done)."""
    from ..db import q
    new, old = ("done", "open") if done else ("open", "done")
    q("UPDATE tasks SET status=%s WHERE id=%s AND status=%s", (new, task_id, old))
    return True


class Overlay:
    def __init__(self, levels: list, *, respect_lock: bool = True, tick_todo=None, on_click=None):
        self.lv = levels                       # [mic_rms, out_rms], written by the audio callback
        self.respect_lock = respect_lock
        self.tick_todo = tick_todo or _db_tick
        self.on_click = on_click               # pill click while she thinks / speaks = stop her
        self.acc = Access.read()
        self.state = M.PillState()
        self.meters = {k: M.LevelMeter(**v) for k, v in M.METER.items()}
        self.src: str | None = None
        self.timer = None
        self.slow = None
        self.follow = None                     # 400 ms: is the pointer on another display?
        self.screen = None
        self.monitor = None
        self.dismiss: M.DismissTimer | None = None
        self.confirm: M.DismissTimer | None = None
        self.confirm_hides = False
        self.enabled = True
        self.ticks = 0                         # frames drawn (measurement)
        self._t_tick = _Target.alloc().initWithFn_(self._tick)
        self._t_slow = _Target.alloc().initWithFn_(self._slow)
        self._t_follow = _Target.alloc().initWithFn_(self._follow)
        self._t_a11y = _Target.alloc().initWithFn_(self._a11y_changed)
        AppKit.NSWorkspace.sharedWorkspace().notificationCenter().addObserver_selector_name_object_(
            self._t_a11y, "fire:", AppKit.NSWorkspaceAccessibilityDisplayOptionsDidChangeNotification, None)
        self._build()

    def _build(self) -> None:
        self.pill = Pill(self.acc, self._pill_clicked)
        self.pill.clickable = self.on_click is not None
        self.card = Card(self.acc, self._row_clicked, self.hide_card, self._card_hover)

    # ---------------------------------------------------------------- safe entry (called via callAfter)
    def call(self, name: str, *args) -> None:
        try:
            getattr(self, name)(*args)
        except Exception:
            traceback.print_exc()

    # ---------------------------------------------------------------- state
    def apply_state(self, state: str, detail: str | None = None) -> None:
        if not self.enabled and state != "hidden":
            return
        tr = self.state.apply(state, detail)
        if tr is None:
            return
        if tr.hide:
            self._stop_timer()
            self._stop_follow()
            self.pill.hide()
            self.hide_card()
            self._end_confirm(collapse=False)
            return
        if tr.show:
            if self.respect_lock and screen_locked():
                self.state.state = "hidden"    # nothing on screen while the Mac is locked; retried next state
                return
            scr = pointer_screen()             # the display he is using right now
            self.screen = screen_key(scr)
            self.pill.show(screen_anchor(scr))
            self._start_follow()
        self.pill.set_look(tr.look)
        if self.confirm is None:               # a ✓ confirmation owns the wide pill until it times out
            lbl = M.doing_label(tr.detail)
            if lbl:
                self.pill.expand(lbl[0], lbl[1], with_dots=True, tint=M.BLUE)
            elif self.pill.expanded:
                self.pill.collapse()
        if tr.look.source != self.src:
            self.src = tr.look.source
            if self.src in self.meters:
                self.meters[self.src].reset()
        if tr.look.timer:
            self._start_timer()
        else:
            self._stop_timer()

    def _start_timer(self) -> None:
        if self.timer is not None:
            return
        fps = M.FPS_LOW_POWER if self.acc.low_power else M.FPS
        t = NSTimer.timerWithTimeInterval_target_selector_userInfo_repeats_(1.0 / fps, self._t_tick, "fire:", None, True)
        t.setTolerance_(0.25 / fps)
        NSRunLoop.currentRunLoop().addTimer_forMode_(t, NSRunLoopCommonModes)   # keeps going while a menu is open
        self.timer = t

    def _stop_timer(self) -> None:
        if self.timer is not None:
            self.timer.invalidate()
            self.timer = None

    def _tick(self) -> None:
        self.ticks += 1
        m = self.meters.get(self.src)
        if m is not None:
            self.pill.set_level(m.step(self.lv[0] if self.src == "mic" else self.lv[1], time.monotonic()))
        if self.state.state == "listening":    # pointer over the click-through pill → it fades out of the way
            self.pill.set_dim(self.pill.contains_pointer())

    # ---------------------------------------------------------------- cards
    def show_card(self, card: dict, speaking: bool = True) -> None:
        if not self.enabled or not isinstance(card, dict):
            return
        now = time.monotonic()
        kind = card.get("kind")
        if kind in M.CONFIRM_KINDS:            # "Added" / "Reminder set": the pill widens into a one-line ✓
            if self.state.state == "hidden":
                self.apply_state("idle")
                self.confirm_hides = self.state.state != "hidden"
            if self.state.state == "hidden":
                return
            self.pill.expand("checkmark.circle.fill", M.confirm_text(card), with_dots=False, tint=M.BLUE)
            self.confirm = M.DismissTimer(kind, 1, now, speaking)
            self._start_slow()
            return
        lay = M.layout(card)
        if lay is None:
            return
        if self.respect_lock and screen_locked():
            return
        anchor = self.pill.anchor if self.pill.visible and self.pill.anchor else screen_anchor(pointer_screen())
        self.card.show(lay, anchor)
        self.dismiss = M.DismissTimer(kind, lay.n, now, speaking)
        if self.monitor is None:               # click anywhere else closes it (mouse monitors need no permission)
            mask = AppKit.NSEventMaskLeftMouseDown | AppKit.NSEventMaskRightMouseDown
            self.monitor = AppKit.NSEvent.addGlobalMonitorForEventsMatchingMask_handler_(mask, self._click_away)
        self._start_slow()

    def _click_away(self, event) -> None:
        try:
            self.hide_card()
        except Exception:
            traceback.print_exc()

    def hide_card(self) -> None:
        self.card.hide()
        self.dismiss = None
        if self.monitor is not None:
            AppKit.NSEvent.removeMonitor_(self.monitor)
            self.monitor = None
        self._maybe_stop_slow()

    def speech_ended(self) -> None:
        now = time.monotonic()
        for t in (self.dismiss, self.confirm):
            if t is not None:
                t.speech_ended(now)

    def _card_hover(self, on: bool) -> None:
        if self.dismiss is not None:
            self.dismiss.hover(on, time.monotonic())

    def _row_clicked(self, i: int) -> None:
        lay = self.card.lay
        if lay is None or not (0 <= i < lay.n) or not lay.rows[i].tickable or i in self.card.gone:
            return
        row = lay.rows[i]
        done = not row.done
        self.card.set_done(i, done)            # optimistic ✓; reverted if the brain write fails
        tid, gen = row.id, self.card.gen

        def write():
            ok = False
            try:
                ok = bool(self.tick_todo(tid, done))
            except Exception as e:
                print(f"[overlay] tick failed: {type(e).__name__}: {e}")
            if not ok:
                AppHelper.callAfter(self._revert, i, not done, gen)
        threading.Thread(target=write, daemon=True, name="overlay-tick").start()

    def _revert(self, i: int, done: bool, gen: int) -> None:
        if self.card.gen == gen:
            self.card.set_done(i, done)

    def _end_confirm(self, collapse: bool = True) -> None:
        self.confirm = None
        if collapse:
            self.pill.collapse()
            lbl = M.doing_label(self.state.detail)
            if lbl:
                self.pill.expand(lbl[0], lbl[1], with_dots=True)
        if self.confirm_hides:
            self.confirm_hides = False
            if self.state.state == "idle":
                self.apply_state("hidden")
        self._maybe_stop_slow()

    def _start_slow(self) -> None:
        if self.slow is None:
            t = NSTimer.timerWithTimeInterval_target_selector_userInfo_repeats_(0.25, self._t_slow, "fire:", None, True)
            t.setTolerance_(0.1)
            NSRunLoop.currentRunLoop().addTimer_forMode_(t, NSRunLoopCommonModes)
            self.slow = t

    def _maybe_stop_slow(self) -> None:
        if self.slow is not None and self.dismiss is None and self.confirm is None:
            self.slow.invalidate()
            self.slow = None

    def _slow(self) -> None:
        now = time.monotonic()
        if self.dismiss is not None and self.dismiss.due(now):
            self.hide_card()
        if self.confirm is not None and self.confirm.due(now):
            self._end_confirm()
        self._maybe_stop_slow()

    # ---------------------------------------------------------------- follow the pointer's display
    def _start_follow(self) -> None:
        if self.follow is None and len(AppKit.NSScreen.screens() or []) > 1:   # one display: nothing to follow
            t = NSTimer.timerWithTimeInterval_target_selector_userInfo_repeats_(M.FOLLOW_S, self._t_follow, "fire:",
                                                                                 None, True)
            t.setTolerance_(0.1)
            NSRunLoop.currentRunLoop().addTimer_forMode_(t, NSRunLoopCommonModes)
            self.follow = t

    def _stop_follow(self) -> None:
        if self.follow is not None:
            self.follow.invalidate()
            self.follow = None

    def _follow(self) -> None:
        if not self.pill.visible:
            self._stop_follow()
            return
        scr = pointer_screen()
        key = screen_key(scr)
        if key != self.screen:                 # he moved to another display: fade over there
            self.screen = key
            anchor = screen_anchor(scr)
            self.pill.move(anchor)
            self.card.move(anchor)

    # ---------------------------------------------------------------- pill click, settings, lifecycle
    def _pill_clicked(self) -> None:
        if self.state.state in ("thinking", "speaking") and self.on_click is not None:
            self.on_click()

    def set_click_handler(self, fn) -> None:
        self.on_click = fn
        self.pill.clickable = fn is not None
        self.pill.set_look(self.pill.look)

    def set_enabled(self, on: bool) -> None:
        if not on:
            self.apply_state("hidden")
        self.enabled = bool(on)

    def _a11y_changed(self) -> None:
        """Reduce Motion / Transparency / Increase Contrast changed: rebuild the views with the new look."""
        state, detail = self.state.state, self.state.detail
        self.apply_state("hidden")
        self.pill.close()
        self.card.close()
        self.acc = Access.read()
        self._build()
        if state != "hidden":
            self.apply_state(state, detail)

    def shutdown(self) -> None:
        self._stop_timer()
        self._stop_follow()
        self.hide_card()
        self.confirm = None
        self._maybe_stop_slow()
        if self.slow is not None:
            self.slow.invalidate()
            self.slow = None
        AppKit.NSWorkspace.sharedWorkspace().notificationCenter().removeObserver_(self._t_a11y)
        self.pill.close()
        self.card.close()
