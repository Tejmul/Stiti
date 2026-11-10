"""Cards: native AppKit rows on the same white glass, dropping 8 pt below the pill.

Data comes from the brain (cards.py → Engine.last_card), never from the LLM's words, and only card titles/items are
shown (no captions of the conversation, D24). Click a to-do row = tick it (ui.py writes the brain in a worker thread).
The card panel is key-CAPABLE (so Esc works after he clicks it) but still non-activating: his app stays frontmost.
"""
from __future__ import annotations

import AppKit
import objc
from PyObjCTools import AppHelper

from . import model as M
from .surface import Access, animate_frame, cg, fade, label, make_panel, make_surface, ns, out_ease, set_symbol, \
    set_text, symbol

RADIUS = 18.0
F_TEXT = lambda: AppKit.NSFont.systemFontOfSize_(13.5)                                              # noqa: E731
F_TITLE = lambda: AppKit.NSFont.systemFontOfSize_weight_(17, AppKit.NSFontWeightSemibold)            # noqa: E731
F_EYEBROW = lambda: AppKit.NSFont.monospacedSystemFontOfSize_weight_(10, AppKit.NSFontWeightMedium)  # noqa: E731
F_META = lambda: AppKit.NSFont.monospacedSystemFontOfSize_weight_(11, AppKit.NSFontWeightRegular)    # noqa: E731
ICON = {"todos": "circle", "reminders": "bell", "news": None}


class _CardPanel(AppKit.NSPanel):
    def canBecomeKeyWindow(self):           # only after he clicks it: then Esc works
        return True

    def canBecomeMainWindow(self):
        return False

    def cancelOperation_(self, sender):     # Esc
        cb = getattr(self, "on_esc", None)
        if cb is not None:
            cb()

    def keyDown_(self, event):
        if event.keyCode() == 53:
            self.cancelOperation_(None)
        else:
            objc.super(_CardPanel, self).keyDown_(event)


class _CardView(AppKit.NSView):
    def isFlipped(self):
        return True

    def acceptsFirstMouse_(self, event):
        return True

    def mouseEntered_(self, event):
        cb = getattr(self, "on_hover", None)
        if cb is not None:
            cb(True)

    def mouseExited_(self, event):
        cb = getattr(self, "on_hover", None)
        if cb is not None:
            cb(False)


class _RowView(AppKit.NSView):
    def isFlipped(self):
        return True

    def acceptsFirstMouse_(self, event):    # the first click on an inactive panel ticks (no "focus click")
        return True

    def hitTest_(self, point):              # labels inside must not eat the click
        return self if objc.super(_RowView, self).hitTest_(point) is not None else None

    def mouseDown_(self, event):
        cb = getattr(self, "on_click", None)
        if cb is not None:
            cb(self.idx)

    def mouseEntered_(self, event):
        if getattr(self, "hoverable", False):
            self.layer().setBackgroundColor_(cg(M.NAVY, 0.06))

    def mouseExited_(self, event):
        self.layer().setBackgroundColor_(None)


def _track(view) -> None:
    opts = (AppKit.NSTrackingMouseEnteredAndExited | AppKit.NSTrackingActiveAlways | AppKit.NSTrackingInVisibleRect)
    view.addTrackingArea_(AppKit.NSTrackingArea.alloc().initWithRect_options_owner_userInfo_(
        ((0, 0), (0, 0)), opts, view, None))


class Card:
    def __init__(self, acc: Access, on_row, on_esc, on_hover):
        self.acc, self.on_row, self.on_hover = acc, on_row, on_hover
        self.panel = make_panel(_CardPanel, M.CARD_W_DEFAULT, 200)
        self.panel.setBecomesKeyOnlyIfNeeded_(False)
        self.panel.setIgnoresMouseEvents_(False)
        self.panel.on_esc = on_esc
        self.visible = False
        self.gen = 0
        self.lay: M.CardLayout | None = None
        self.rows: list[dict] = []           # per row: view, icon, text, meta

    def frame_for(self, lay: M.CardLayout, anchor):
        x, top = anchor
        y = top - M.TOP_GAP - M.PILL_H - M.CARD_GAP - lay.height
        return ((round(x - lay.width / 2), round(y)), (lay.width, lay.height))

    def show(self, lay: M.CardLayout, anchor) -> None:
        self.gen += 1
        self.lay = lay
        self._build(lay)
        (x, y), (w, h) = self.frame_for(lay, anchor)
        if self.visible:                     # a new turn replaces the card in place (no stacking, no history)
            if self.acc.reduce_motion:
                self.panel.setFrame_display_(((x, y), (w, h)), True)
            else:
                animate_frame(self.panel, ((x, y), (w, h)), 1.0, 0.2)
            return
        self.visible = True
        if self.acc.reduce_motion:
            self.panel.setFrame_display_(((x, y), (w, h)), True)
            self.panel.orderFrontRegardless()
            fade(self.panel, 1.0, 0.2)
        else:                                # drops 10 pt out of the pill, 320 ms --out ease
            self.panel.setFrame_display_(((x, y + 10), (w, h)), True)
            self.panel.orderFrontRegardless()
            animate_frame(self.panel, ((x, y), (w, h)), 1.0, 0.32, out_ease())

    def hide(self) -> None:
        if not self.visible:
            return
        self.visible = False
        self.gen += 1
        g = self.gen
        fade(self.panel, 0.0, 0.2)
        AppHelper.callLater(0.25, self._order_out, g)

    def _order_out(self, g: int) -> None:
        if g == self.gen:
            self.panel.orderOut_(None)       # if he had clicked it (key), the keyboard goes back to his app

    def close(self) -> None:
        self.gen += 1
        self.visible = False
        self.panel.orderOut_(None)

    # ---------------------------------------------------------------- content
    def _build(self, lay: M.CardLayout) -> None:
        w, h = lay.width, lay.height
        outer, host = make_surface(w, h, RADIUS, self.acc, _CardView)
        host.on_hover = self.on_hover
        _track(host)
        eb = label(lay.eyebrow, F_EYEBROW(), ns(M.BLUE), kern=1.2)
        eb.setFrame_(((M.PAD, M.PAD - 2), (w - 2 * M.PAD, M.EYEBROW_H)))
        host.addSubview_(eb)
        tl = label(lay.title, F_TITLE(), ns(M.NAVY))
        tl.setFrame_(((M.PAD, M.PAD + M.EYEBROW_H - 2), (w - 2 * M.PAD, M.TITLE_H)))
        host.addSubview_(tl)
        self.rows = []
        for i, r in enumerate(lay.rows):
            self.rows.append(self._row(host, lay, i, r, w))
        if lay.more:
            mo = label(f"+{lay.more} more", F_META(), ns(M.NAVY, 0.5))
            mo.setFrame_(((M.PAD + 26, lay.more_y + 4), (w - 2 * M.PAD, 16)))
            host.addSubview_(mo)
        self.panel.setContentView_(outer)

    def _row(self, host, lay: M.CardLayout, i: int, r: M.Row, w: float) -> dict:
        rw = w - 16
        rv = _RowView.alloc().initWithFrame_(((8, r.y), (rw, r.h)))
        rv.setWantsLayer_(True)
        rv.layer().setCornerRadius_(9)
        rv.idx, rv.on_click, rv.hoverable = i, self.on_row, r.tickable
        _track(rv)
        rv.setAccessibilityElement_(True)
        rv.setAccessibilityRole_(AppKit.NSAccessibilityCheckBoxRole if r.tickable else AppKit.NSAccessibilityStaticTextRole)
        rv.setAccessibilityLabel_(f"{r.text} {r.meta}".strip())
        host.addSubview_(rv)
        icon_name = ICON.get(lay.kind)
        icon = symbol(icon_name, 15, ns(M.NAVY, 0.35) if lay.kind == "todos" else ns(M.BLUE, 0.85)) if icon_name else None
        x = 8.0
        if icon is not None:
            icon.setFrame_(((x, (r.h - 18) / 2), (18, 18)))
            rv.addSubview_(icon)
            x += 26
        meta = label(r.meta, F_META(), ns(M.NAVY, 0.55)) if r.meta else None
        if lay.kind == "news":               # headline over its source
            tx = label(r.text, F_TEXT(), ns(M.NAVY))
            tx.setFrame_(((x, 5), (rw - x - 8, 18)))
            rv.addSubview_(tx)
            if meta is not None:
                meta.setFrame_(((x, 25), (rw - x - 8, 15)))
                rv.addSubview_(meta)
        else:                                # text … meta (right-aligned, mono); the shorter one gives way
            tx = label(r.text, F_TEXT(), ns(M.NAVY))
            tx.sizeToFit()
            mw = 0.0
            if meta is not None:
                meta.sizeToFit()
                room = rw - x - 8 - 12
                mw = min(meta.frame().size.width, max(110.0, room - min(tx.frame().size.width, room * 0.55)))
                meta.setAlignment_(AppKit.NSTextAlignmentRight)
                meta.setFrame_(((rw - 8 - mw, (r.h - 15) / 2), (mw, 15)))
                rv.addSubview_(meta)
            tx.setFrame_(((x, (r.h - 18) / 2), (rw - x - 8 - (mw + 12 if mw else 0), 18)))
            rv.addSubview_(tx)
        row = {"view": rv, "icon": icon, "text": tx, "meta": meta}
        if r.done:
            self._paint(row, r, True, animate=False)
        return row

    def set_done(self, i: int, done: bool) -> None:
        if self.lay is None or not (0 <= i < len(self.rows)):
            return
        r = self.lay.rows[i]
        r.done = done
        self._paint(self.rows[i], r, done, animate=not self.acc.reduce_motion)

    def _paint(self, row: dict, r: M.Row, done: bool, animate: bool) -> None:
        if row["icon"] is not None:          # ○ → ✓ filled blue (SF Symbol replace + bounce)
            set_symbol(row["icon"], "checkmark.circle.fill" if done else "circle",
                       ns(M.BLUE) if done else ns(M.NAVY, 0.35), animate)
        set_text(row["text"], r.text, F_TEXT(), ns(M.NAVY, 0.45) if done else ns(M.NAVY), strike=done)
        if row["meta"] is not None:
            row["meta"].setAlphaValue_(0.45 if done else 1.0)
        row["view"].setAccessibilityValue_(1 if done else 0)
