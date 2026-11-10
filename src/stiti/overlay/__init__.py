"""Stiti on screen: a calm liquid-glass pill that shows she is listening / thinking / speaking, and cards that drop
out of it (to-dos, reminders, headlines). Design + measurements: docs/research/desktop_overlay.md, DECISIONS D26.

Thread-safe API. Any thread may call these; every AppKit call is marshalled to the main thread. Until `init()` has
run on the main thread of an AppKit app (Stiti.app), every function is a cheap no-op, so the voice loop in a terminal
(`stiti voice`), the tests and machines without a display work unchanged.

    overlay.set_state("listening" | "thinking" | "speaking" | "idle" | "hidden", detail=None)
    overlay.level(mic_rms, out_rms)        # from the audio callback: stores two floats, nothing else
    overlay.show_card(card)                # cards.py dict; todos/reminders/news open a card, *_added/_set widen the pill
    overlay.hide_card()
    overlay.speech_ended()                 # starts the card's auto-dismiss clock
"""
from __future__ import annotations

import os

from .model import LOOKS

_ui = None                    # the main-thread Overlay (ui.py) once init() succeeded
_enabled = True
_lv = [0.0, 0.0]              # [mic_rms, out_rms]; read by the 30 Hz main-thread tick


def init(*, respect_lock: bool = True, tick_todo=None, on_click=None) -> bool:
    """Create the overlay. Must run on the main thread of a running (or about to run) NSApplication.
    Returns False (and stays a no-op) without AppKit, without a screen, off the main thread, or STITI_OVERLAY=off."""
    global _ui
    if _ui is not None:
        return True
    if os.getenv("STITI_OVERLAY", "on") == "off":
        return False
    try:
        import AppKit
        from Foundation import NSThread
        if not NSThread.isMainThread() or AppKit.NSScreen.mainScreen() is None:
            return False
        from .ui import Overlay
        _ui = Overlay(_lv, respect_lock=respect_lock, tick_todo=tick_todo, on_click=on_click)
        return True
    except Exception as e:
        print(f"[overlay] not available: {type(e).__name__}: {e}")
        _ui = None
        return False


def active() -> bool:
    return _ui is not None and _enabled


def _call(name: str, *args) -> None:
    ui = _ui
    if ui is None or not _enabled:
        return
    from PyObjCTools import AppHelper
    AppHelper.callAfter(ui.call, name, *args)


def set_state(state: str, detail: str | None = None) -> None:
    """detail: an on_ack kind ("calendar", "mail", "web", "plan", "tools") while thinking → "Checking calendar"."""
    if state in LOOKS:
        _call("apply_state", state, detail)


def level(mic: float, out: float) -> None:
    """Audio-callback safe: two float stores, no locks, no allocation, no AppKit."""
    _lv[0] = mic
    _lv[1] = out


def show_card(card: dict | None, speaking: bool = True) -> None:
    if card:
        _call("show_card", card, speaking)


def hide_card() -> None:
    _call("hide_card")


def speech_ended() -> None:
    _call("speech_ended")


def set_click_handler(fn) -> None:
    """fn() runs on the main thread when he clicks the pill while she thinks / speaks (= stop her)."""
    _call("set_click_handler", fn)


def set_enabled(on: bool) -> None:
    """Menu toggle "Show Stiti on screen". Off hides everything and makes the API a no-op again."""
    global _enabled
    ui = _ui
    if ui is not None:
        from PyObjCTools import AppHelper
        AppHelper.callAfter(ui.call, "set_enabled", bool(on))
    _enabled = bool(on)


def shutdown() -> None:
    global _ui
    ui, _ui = _ui, None
    if ui is not None:
        try:
            ui.shutdown()
        except Exception:
            pass
