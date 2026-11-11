"""Cards: native AppKit rows on the same white glass, dropping 8 pt below the pill.

Data comes from the brain (cards.py → Engine.last_card), never from the LLM's words, and only card titles/items are
shown (no captions of the conversation, D24). Click a to-do row = tick it (ui.py writes the brain in a worker thread).
The card panel is key-CAPABLE (so Esc works after he clicks it) but still non-activating: his app stays frontmost.

Motion (model.choreography decides the timeline, this file only plays it): rows rise in one after another; a row he
just added / a reminder he just set arrives tinted and its icon bounces, then settles; a to-do he finished gets ✓ and a
strike line drawn left → right, holds a moment, then folds away while the rows below close up and the card shortens
(the eyebrow counts down). Removed / cancelled rows do the same with ✕ / a slashed bell. Reduce Motion: no slides.
"""
from __future__ import annotations

import AppKit
import objc
import Quartz
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
ENTER_DY = 8.0                               # rows rise this far as they fade in
STRUCK = {"done": ("checkmark.circle.fill", M.BLUE, 1.0), "removed": ("xmark.circle.fill", M.NAVY, 0.4),
          "cancelled": ("bell.slash", M.NAVY, 0.45)}


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

    def hitTest_(self, point):              # the rounded card only, not its transparent corners
        hit = objc.super(_CardView, self).hitTest_(point)
        if hit is None:
            return None
        p = self.convertPoint_fromView_(point, self.superview())
        b = self.bounds().size
        return hit if M.in_round_rect(p.x, p.y, b.width, b.height, RADIUS) else None

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
        self.anchor = None
        self.rows: list[dict] = []           # per row: view, icon, text, meta, line, glow
        self.gone: set[int] = set()          # rows that have folded away (indices into lay.rows stay stable)
        self.head: dict = {}                 # eyebrow / title / "+N more" labels

    def frame_for(self, lay: M.CardLayout, anchor):
        x, top = anchor
        y = top - M.TOP_GAP - M.PILL_H - M.CARD_GAP - lay.height
        return ((round(x - lay.width / 2), round(y)), (lay.width, lay.height))

    def show(self, lay: M.CardLayout, anchor) -> None:
        self.gen += 1
        self.lay, self.anchor, self.gone = lay, anchor, set()
        self._build(lay)
        self._play(lay)
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

    def move(self, anchor) -> None:
        """Follow the pill to another display (fade, jump, fade in)."""
        if not self.visible or self.lay is None or anchor == self.anchor:
            return
        self.anchor = anchor
        self.gen += 1
        g = self.gen
        fade(self.panel, 0.0, M.STATE_S)

        def land():
            if g == self.gen and self.visible:
                self.panel.setFrame_display_(self.frame_for(self.lay, anchor), True)
                fade(self.panel, 1.0, 0.2)
        AppHelper.callLater(M.STATE_S + 0.02, land)

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
        self.head = {"eyebrow": eb, "title": tl, "more": None}
        self.rows = []
        hidden = not self.acc.reduce_motion        # rows wait for their "enter" step
        for i, r in enumerate(lay.rows):
            row = self._row(host, lay, i, r, w)
            if hidden:
                row["view"].setAlphaValue_(0.0)
                row["view"].setFrameOrigin_((8, r.y + ENTER_DY))
            self.rows.append(row)
        if lay.more:
            mo = label(f"+{lay.more} more", F_META(), ns(M.NAVY, 0.5))
            mo.setFrame_(((M.PAD + 26, lay.more_y + 4), (w - 2 * M.PAD, 16)))
            host.addSubview_(mo)
            self.head["more"] = mo
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
        row = {"view": rv, "icon": icon, "text": tx, "meta": meta, "line": None, "glow": None, "kind": lay.kind}
        if r.done:
            self._paint(row, r, True, animate=False)
        return row

    def set_done(self, i: int, done: bool) -> None:
        if self.lay is None or not (0 <= i < len(self.rows)):
            return
        r = self.lay.rows[i]
        r.done = done
        self._paint(self.rows[i], r, done, animate=not self.acc.reduce_motion)

    def _paint(self, row: dict, r: M.Row, done: bool, animate: bool, op: str = "done") -> None:
        """○ → ✓ (or ✕ / slashed bell) + the text dims and a strike line is drawn across it; reversible (a click)."""
        if row["icon"] is not None:          # SF Symbol replace + bounce
            name, colour, a = STRUCK.get(op, STRUCK["done"]) if done else (ICON.get(row["kind"]) or "circle", M.NAVY, 0.35)
            set_symbol(row["icon"], name, ns(colour, a), animate)
        self._strike(row, done, animate)
        if row["meta"] is not None:
            row["meta"].setAlphaValue_(0.45 if done else 1.0)
        row["view"].setAccessibilityValue_(1 if done else 0)

    def _strike(self, row: dict, on: bool, animate: bool) -> None:
        tx = row["text"]
        if not on:
            if row["line"] is not None:
                row["line"].removeFromSuperlayer()
                row["line"] = None
            tx.setAlphaValue_(1.0)
            return
        if row["line"] is not None:
            return
        f = tx.frame()
        w = max(8.0, min(tx.attributedStringValue().size().width, f.size.width))
        line = Quartz.CALayer.layer()
        line.setBackgroundColor_(cg(M.NAVY, 0.6))
        line.setCornerRadius_(0.75)
        line.setAnchorPoint_((0.0, 0.5))
        line.setBounds_(((0, 0), (w + 2, 1.5)))
        line.setPosition_((f.origin.x - 1, f.origin.y + f.size.height / 2 + 0.5))
        row["view"].layer().addSublayer_(line)
        row["line"] = line
        if animate:                          # drawn left → right
            a = Quartz.CABasicAnimation.animationWithKeyPath_("transform.scale.x")
            a.setFromValue_(0.0)
            a.setToValue_(1.0)
            a.setDuration_(M.STRIKE_S)
            a.setTimingFunction_(out_ease())
            line.addAnimation_forKey_(a, "draw")
            AppKit.NSAnimationContext.beginGrouping()
            AppKit.NSAnimationContext.currentContext().setDuration_(M.STRIKE_S)
            tx.animator().setAlphaValue_(0.5)
            AppKit.NSAnimationContext.endGrouping()
        else:
            tx.setAlphaValue_(0.5)

    # ---------------------------------------------------------------- choreography
    def _play(self, lay: M.CardLayout) -> None:
        g = self.gen
        groups: dict[tuple[float, str], list[int]] = {}
        for t, step, i in M.choreography(lay, self.acc.reduce_motion):
            groups.setdefault((round(t, 3), step), []).append(i)
        for (t, step), idx in groups.items():
            if t <= 0:
                self._step(g, step, idx)
            else:
                AppHelper.callLater(t, self._step, g, step, idx)

    def _step(self, g: int, step: str, idx: list[int]) -> None:
        if g != self.gen or self.lay is None:
            return                           # a newer card replaced this one
        try:
            getattr(self, f"_do_{step}")(idx)
        except Exception as e:
            print(f"[overlay] card {step}: {type(e).__name__}: {e}")

    def _anim(self, secs: float, fn) -> None:
        AppKit.NSAnimationContext.beginGrouping()
        ctx = AppKit.NSAnimationContext.currentContext()
        ctx.setDuration_(secs)
        ctx.setTimingFunction_(out_ease())
        fn()
        AppKit.NSAnimationContext.endGrouping()

    def _hide_gone(self, g: int) -> None:
        if g == self.gen:                    # alpha 0 still takes clicks in AppKit; hidden doesn't
            for i in self.gone:
                self.rows[i]["view"].setHidden_(True)

    def _do_enter(self, idx: list[int]) -> None:
        def go():
            for i in idx:
                rv = self.rows[i]["view"]
                rv.animator().setAlphaValue_(1.0)
                rv.animator().setFrameOrigin_((8, self.lay.rows[i].y))
        self._anim(M.ENTER_S, go)

    def _do_arrive(self, idx: list[int]) -> None:
        for i in idx:
            row = self.rows[i]
            if row["glow"] is None:          # soft blue wash behind the new row
                glow = Quartz.CALayer.layer()
                glow.setBackgroundColor_(cg(M.BLUE, 0.10))
                glow.setCornerRadius_(9)
                glow.setFrame_(row["view"].layer().bounds())
                glow.setOpacity_(0.0)
                row["view"].layer().insertSublayer_atIndex_(glow, 0)
                row["glow"] = glow
            Quartz.CATransaction.begin()
            Quartz.CATransaction.setAnimationDuration_(0.0 if self.acc.reduce_motion else 0.25)
            row["glow"].setOpacity_(1.0)
            Quartz.CATransaction.commit()
            if row["icon"] is not None:
                name = "bell.fill" if row["kind"] == "reminders" else "circle"
                set_symbol(row["icon"], name, ns(M.BLUE), not self.acc.reduce_motion)

    def _do_settle(self, idx: list[int]) -> None:
        for i in idx:
            row = self.rows[i]
            if row["glow"] is not None:
                Quartz.CATransaction.begin()
                Quartz.CATransaction.setAnimationDuration_(0.6)
                row["glow"].setOpacity_(0.0)
                Quartz.CATransaction.commit()
            if row["icon"] is not None and row["kind"] in ("todos", "reminders"):
                set_symbol(row["icon"], ICON[row["kind"]],
                           ns(M.NAVY, 0.35) if row["kind"] == "todos" else ns(M.BLUE, 0.85), False)

    def _do_strike(self, idx: list[int]) -> None:
        for i in idx:
            r = self.lay.rows[i]
            r.done = r.op == "done"
            self._paint(self.rows[i], r, True, animate=not self.acc.reduce_motion, op=r.op or "done")

    def _do_collapse(self, idx: list[int]) -> None:
        self.gone |= set(idx)
        new = M.collapse(self.lay, self.gone)
        self.lay = new
        secs = 0.0 if self.acc.reduce_motion else M.COLLAPSE_S

        def go():
            for i, (row, r) in enumerate(zip(self.rows, new.rows)):
                rv = row["view"]
                if i in self.gone:
                    rv.animator().setAlphaValue_(0.0)
                    if not self.acc.reduce_motion:
                        rv.animator().setFrameOrigin_((8, r.y - 6))
                else:
                    rv.animator().setFrameOrigin_((8, r.y))
            if self.head.get("more") is not None:
                self.head["more"].animator().setFrameOrigin_((M.PAD + 26, new.more_y + 4))
        if secs:
            self._anim(secs, go)
        else:
            go()
        for i in self.gone:
            self.rows[i]["view"].setAccessibilityElement_(False)
        g = self.gen
        AppHelper.callLater(secs + 0.05, self._hide_gone, g)
        set_text(self.head["eyebrow"], new.eyebrow, F_EYEBROW(), ns(M.BLUE), kern=1.2)
        if new.title != self.head["title"].stringValue():
            set_text(self.head["title"], new.title, F_TITLE(), ns(M.NAVY))
        if self.visible and self.anchor is not None:      # the card shortens from the bottom; its top stays put
            frame = self.frame_for(new, self.anchor)
            if secs:
                animate_frame(self.panel, frame, None, secs, out_ease())
            else:
                self.panel.setFrame_display_(frame, True)
