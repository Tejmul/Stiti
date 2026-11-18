"""Cards: quiet, sharp HUD panels that drop out from under the orb (D44).

A solid navy panel (what is behind it never shows through, so every word stays readable over any window), a SKY
hairline border and a short bright beam on its top edge, under the orb. Mono eyebrow, a title, then rows: a ring
checkbox for to-dos, a bell for reminders, 01 / 02 / 03 for headlines; due times in mono on the right.

Data comes from the brain (cards.py → Engine.last_card), never from the LLM's words, and only card titles/items are
shown (no captions of the conversation, D24). Click a to-do row = tick it (ui.py writes the brain in a worker thread).
The card panel is key-CAPABLE (so Esc works after he clicks it) but still non-activating: his app stays frontmost.

Motion (model.choreography decides the timeline, this file only plays it): rows rise in one after another; a row he
just added / a reminder he just set arrives on a blue wash and its icon bounces, then settles; a to-do he finished
gets a filled ✓ and a strike line drawn left → right, holds a moment, then folds away while the rows below close up
and the card shortens (the eyebrow counts down). Removed / cancelled rows do the same with ✕ / a slashed bell.
Reduce Motion: no slides.
"""
from __future__ import annotations

import AppKit
import objc
import Quartz
from PyObjCTools import AppHelper

from . import model as M
from .surface import Access, animate_frame, cg, crisp, fade, label, make_hud, make_panel, ns, out_ease, set_symbol, \
    set_text, symbol, text_alpha, text_lines

F_TEXT = lambda: AppKit.NSFont.systemFontOfSize_(15)                                                 # noqa: E731
F_TITLE = lambda: AppKit.NSFont.systemFontOfSize_weight_(17, AppKit.NSFontWeightSemibold)             # noqa: E731
F_EYEBROW = lambda: AppKit.NSFont.monospacedSystemFontOfSize_weight_(10.5, AppKit.NSFontWeightMedium)  # noqa: E731
F_META = lambda: AppKit.NSFont.monospacedSystemFontOfSize_weight_(11, AppKit.NSFontWeightRegular)     # noqa: E731
F_SOURCE = lambda: AppKit.NSFont.monospacedSystemFontOfSize_weight_(10, AppKit.NSFontWeightMedium)    # noqa: E731
EYEBROW_KERN, SOURCE_KERN = 1.6, 0.9
TEXT_X = M.ROW_PAD + M.LEAD_W                # where a row's text starts, inside the row
TEXT_H, META_H, BOX = 19.0, 15.0, 16.0       # line boxes; the checkbox's diameter
ENTER_DY = 8.0                               # rows rise this far as they fade in
STRUCK_A = 0.42                              # a struck row's text
CHECK = ((4.3, 8.3), (6.9, 10.9), (11.7, 5.5))                           # ✓ inside the 16 pt ring (y down)
CROSS = (((5.4, 5.4), (10.6, 10.6)), ((10.6, 5.4), (5.4, 10.6)))         # ✕


def headline_lines(text: str, card_w: float = M.CARD_W["news"]) -> int:
    """1 or 2: the lines a headline really needs on the news card (model.layout asks, so rows get the right height)."""
    return text_lines(text, F_TEXT(), card_w - 2 * M.ROW_INSET - TEXT_X - M.ROW_PAD)


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
        return hit if M.in_round_rect(p.x, p.y, b.width, b.height, M.CARD_RADIUS) else None

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
            self.layer().setBackgroundColor_(cg(M.WHITE, M.HOVER_A))

    def mouseExited_(self, event):
        self.layer().setBackgroundColor_(None)


def _track(view) -> None:
    opts = (AppKit.NSTrackingMouseEnteredAndExited | AppKit.NSTrackingActiveAlways | AppKit.NSTrackingInVisibleRect)
    view.addTrackingArea_(AppKit.NSTrackingArea.alloc().initWithRect_options_owner_userInfo_(
        ((0, 0), (0, 0)), opts, view, None))


def _lines(segments) -> object:
    p = Quartz.CGPathCreateMutable()
    for seg in segments:
        Quartz.CGPathMoveToPoint(p, None, *seg[0])
        for pt in seg[1:]:
            Quartz.CGPathAddLineToPoint(p, None, *pt)
    return p


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
        self.rows: list[dict] = []           # per row: view, icon | box, text, meta, line, glow
        self.gone: set[int] = set()          # rows that have folded away (indices into lay.rows stay stable)
        self.head: dict = {}                 # eyebrow / title / "+N more" labels

    def white(self, alpha: float):
        return ns(M.WHITE, text_alpha(alpha, self.acc))

    def frame_for(self, lay: M.CardLayout, anchor):
        x, top = anchor
        y = top - M.TOP_GAP - M.ORB - M.CARD_GAP - lay.height
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
        else:                                # drops 10 pt out from under the orb, 320 ms --out ease
            self.panel.setFrame_display_(((x, y + 10), (w, h)), True)
            self.panel.orderFrontRegardless()
            animate_frame(self.panel, ((x, y), (w, h)), 1.0, M.LAND_S, out_ease())

    def move(self, anchor) -> None:
        """Follow the orb to another display (fade, jump, fade in)."""
        if not self.visible or self.lay is None or anchor == self.anchor:
            return
        self.anchor = anchor
        self.gen += 1
        g = self.gen
        fade(self.panel, 0.0, 0.1)

        def land():
            if g == self.gen and self.visible:
                self.panel.setFrame_display_(self.frame_for(self.lay, anchor), True)
                fade(self.panel, 1.0, 0.2)
        AppHelper.callLater(0.12, land)

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
        host = make_hud(w, h, M.CARD_RADIUS, self.acc, _CardView)
        host.on_hover = self.on_hover
        _track(host)
        self._beam(host.layer(), w)
        eb = label(lay.eyebrow, F_EYEBROW(), ns(M.ACCENT), kern=EYEBROW_KERN)
        eb.setFrame_(((M.PAD, M.PAD - 2), (w - 2 * M.PAD, M.EYEBROW_H)))
        host.addSubview_(eb)
        tl = label(lay.title, F_TITLE(), self.white(M.TEXT_A))
        tl.setFrame_(((M.PAD, M.PAD + M.EYEBROW_H), (w - 2 * M.PAD, M.TITLE_H)))
        host.addSubview_(tl)
        self.head = {"eyebrow": eb, "title": tl, "more": None}
        self.rows = []
        hidden = not self.acc.reduce_motion        # rows wait for their "enter" step
        for i, r in enumerate(lay.rows):
            row = self._row(host, lay, i, r, w)
            if hidden:
                row["view"].setAlphaValue_(0.0)
                row["view"].setFrameOrigin_((M.ROW_INSET, r.y + ENTER_DY))
            self.rows.append(row)
        if lay.more:
            mo = label(f"+{lay.more} more", F_META(), self.white(M.META_A))
            mo.setFrame_(((M.ROW_INSET + TEXT_X, lay.more_y + 5), (w - 2 * M.PAD, 16)))
            host.addSubview_(mo)
            self.head["more"] = mo
        self.panel.setContentView_(host)

    def _beam(self, base, w: float) -> None:
        """A short bright hairline centred on the top edge, with a faint glow under it: the light of the orb above."""
        glow = crisp(Quartz.CAGradientLayer.layer())
        glow.setFrame_(((w / 2 - 120, -26), (240, 52)))
        glow.setType_("radial")
        glow.setStartPoint_((0.5, 0.5))
        glow.setEndPoint_((1.0, 1.0))
        glow.setColors_([cg(M.ACCENT, 0.16), cg(M.ACCENT, 0.0)])
        base.addSublayer_(glow)
        beam = crisp(Quartz.CAGradientLayer.layer())
        beam.setFrame_(((w / 2 - 72, 0), (144, 1.5)))
        beam.setStartPoint_((0.0, 0.5))
        beam.setEndPoint_((1.0, 0.5))
        beam.setColors_([cg(M.ACCENT, 0.0), cg(M.WHITE, M.BEAM_A), cg(M.ACCENT, 0.0)])
        base.addSublayer_(beam)

    def _row(self, host, lay: M.CardLayout, i: int, r: M.Row, w: float) -> dict:
        rw = w - 2 * M.ROW_INSET
        rv = _RowView.alloc().initWithFrame_(((M.ROW_INSET, r.y), (rw, r.h)))
        rv.setWantsLayer_(True)
        rv.layer().setCornerRadius_(8)
        rv.idx, rv.on_click, rv.hoverable = i, self.on_row, r.tickable
        _track(rv)
        rv.setAccessibilityElement_(True)
        rv.setAccessibilityRole_(AppKit.NSAccessibilityCheckBoxRole if r.tickable else AppKit.NSAccessibilityStaticTextRole)
        rv.setAccessibilityLabel_(f"{r.text} {r.meta}".strip())
        host.addSubview_(rv)
        sep = Quartz.CALayer.layer()                 # hairline above every row (the first one closes the header)
        sep.setFrame_(((M.ROW_PAD, 0), (rw - 2 * M.ROW_PAD, 1)))
        sep.setBackgroundColor_(cg(M.WHITE, 0.2 if self.acc.increase_contrast else M.SEP_A))
        rv.layer().addSublayer_(sep)
        row = {"view": rv, "icon": None, "box": None, "text": None, "meta": None, "line": None, "glow": None,
               "kind": lay.kind}
        if lay.kind == "todos":
            row["box"] = self._checkbox(rv.layer(), r.h)
        elif lay.kind == "reminders":
            row["icon"] = symbol("bell", 13, ns(M.ACCENT, 0.85))
            if row["icon"] is not None:
                row["icon"].setFrame_(((M.ROW_PAD - 1, (r.h - 18) / 2), (18, 18)))
                rv.addSubview_(row["icon"])
        else:                                        # headlines are numbered
            num = label(f"{i + 1:02d}", F_SOURCE(), ns(M.ACCENT, 0.6), kern=0.4)
            num.setFrame_(((M.ROW_PAD, 9), (M.LEAD_W, 14)))
            rv.addSubview_(num)
        x = TEXT_X
        room = rw - x - M.ROW_PAD
        if lay.kind == "news":                       # headline (up to two lines) over its source
            tx = label(r.text, F_TEXT(), self.white(M.ROW_A), lines=2)
            tx.setFrame_(((x, 6), (room, r.lines * M.NEWS_LINE_H)))
            rv.addSubview_(tx)
            if r.meta:
                meta = label(r.meta.upper(), F_SOURCE(), ns(M.ACCENT, text_alpha(0.7, self.acc)), kern=SOURCE_KERN)
                meta.setFrame_(((x, 6 + r.lines * M.NEWS_LINE_H + 3), (room, 14)))
                rv.addSubview_(meta)
                row["meta"] = meta
        else:                                        # text … meta (right-aligned, mono); text truncates, meta doesn't
            tx = label(r.text, F_TEXT(), self.white(M.ROW_A))
            tx.sizeToFit()
            mw = 0.0
            if r.meta:
                meta = label(r.meta, F_META(), self.white(M.META_A))
                meta.sizeToFit()
                mw = min(meta.frame().size.width + 1, room * 0.55)
                meta.setAlignment_(AppKit.NSTextAlignmentRight)
                meta.setFrame_(((rw - M.ROW_PAD - mw, (r.h - META_H) / 2 + 0.5), (mw, META_H)))
                rv.addSubview_(meta)
                row["meta"] = meta
            tx.setFrame_(((x, (r.h - TEXT_H) / 2), (room - (mw + 10 if mw else 0), TEXT_H)))
            rv.addSubview_(tx)
        row["text"] = tx
        if r.done:
            self._paint(row, r, True, animate=False)
        return row

    def _checkbox(self, base, row_h: float) -> dict:
        """16 pt ring, 1.5 pt SKY. Done = filled SKY with a navy ✓; removed = dim ring with a ✕."""
        box = Quartz.CALayer.layer()
        box.setFrame_(((M.ROW_PAD, (row_h - BOX) / 2), (BOX, BOX)))
        ring, mark = crisp(Quartz.CAShapeLayer.layer()), crisp(Quartz.CAShapeLayer.layer())
        ring.setPath_(Quartz.CGPathCreateWithEllipseInRect(((0.75, 0.75), (BOX - 1.5, BOX - 1.5)), None))
        ring.setLineWidth_(1.5)
        ring.setStrokeColor_(cg(M.ACCENT))
        ring.setFillColor_(cg(M.ACCENT, 0.0))
        mark.setFillColor_(None)
        mark.setLineWidth_(1.8)
        mark.setLineCap_(Quartz.kCALineCapRound)
        mark.setLineJoin_(Quartz.kCALineJoinRound)
        mark.setStrokeEnd_(0.0)
        for lay in (ring, mark):
            lay.setFrame_(((0, 0), (BOX, BOX)))
            box.addSublayer_(lay)
        base.addSublayer_(box)
        return {"box": box, "ring": ring, "mark": mark}

    def _tick_box(self, b: dict, state: str, animate: bool) -> None:
        """open | done | removed."""
        Quartz.CATransaction.begin()
        Quartz.CATransaction.setDisableActions_(not animate)
        Quartz.CATransaction.setAnimationDuration_(0.18)
        if state == "done":
            b["ring"].setStrokeColor_(cg(M.ACCENT))
            b["ring"].setFillColor_(cg(M.ACCENT, 1.0))
            b["mark"].setPath_(_lines([CHECK]))
            b["mark"].setStrokeColor_(cg(M.CARD))
        elif state == "removed":
            b["ring"].setStrokeColor_(cg(M.WHITE, 0.32))
            b["ring"].setFillColor_(cg(M.ACCENT, 0.0))
            b["mark"].setPath_(_lines(CROSS))
            b["mark"].setStrokeColor_(cg(M.WHITE, 0.55))
        else:
            b["ring"].setStrokeColor_(cg(M.ACCENT))
            b["ring"].setFillColor_(cg(M.ACCENT, 0.0))
        Quartz.CATransaction.commit()
        Quartz.CATransaction.begin()                 # the mark is drawn (or wiped) as a stroke
        Quartz.CATransaction.setDisableActions_(not animate)
        Quartz.CATransaction.setAnimationDuration_(0.22)
        b["mark"].setStrokeEnd_(0.0 if state == "open" else 1.0)
        Quartz.CATransaction.commit()
        if animate and state != "open":
            self._bounce(b["box"])

    def _bounce(self, layer) -> None:
        a = Quartz.CAKeyframeAnimation.animationWithKeyPath_("transform.scale")
        a.setValues_([1.0, 1.22, 0.96, 1.0])
        a.setKeyTimes_([0.0, 0.35, 0.75, 1.0])
        a.setDuration_(0.36)
        a.setTimingFunction_(out_ease())
        layer.addAnimation_forKey_(a, "bounce")

    def set_done(self, i: int, done: bool) -> None:
        if self.lay is None or not (0 <= i < len(self.rows)):
            return
        r = self.lay.rows[i]
        r.done = done
        self._paint(self.rows[i], r, done, animate=not self.acc.reduce_motion)

    def _paint(self, row: dict, r: M.Row, done: bool, animate: bool, op: str = "done") -> None:
        """○ → filled ✓ (or ✕ / slashed bell) + the text dims and a strike line is drawn across it; reversible."""
        if row["box"] is not None:
            self._tick_box(row["box"], ("removed" if op == "removed" else "done") if done else "open", animate)
        if row["icon"] is not None:          # SF Symbol replace + bounce
            name, colour, a = ("bell.slash", M.WHITE, 0.45) if done else ("bell", M.ACCENT, 0.85)
            set_symbol(row["icon"], name, ns(colour, a), animate)
        self._strike(row, done, animate, bright=op == "done")
        if row["meta"] is not None:
            row["meta"].setAlphaValue_(0.5 if done else 1.0)
        row["view"].setAccessibilityValue_(1 if done else 0)

    def _strike(self, row: dict, on: bool, animate: bool, bright: bool = True) -> None:
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
        line.setBackgroundColor_(cg(M.ACCENT, 0.95) if bright else cg(M.WHITE, 0.5))
        line.setCornerRadius_(0.75)
        line.setAnchorPoint_((0.0, 0.5))
        line.setBounds_(((0, 0), (w + 4, 1.5)))
        line.setPosition_((f.origin.x - 2, f.origin.y + f.size.height / 2 + 0.5))
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
            tx.animator().setAlphaValue_(STRUCK_A)
            AppKit.NSAnimationContext.endGrouping()
        else:
            tx.setAlphaValue_(STRUCK_A)

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
                rv.animator().setFrameOrigin_((M.ROW_INSET, self.lay.rows[i].y))
        self._anim(M.ENTER_S, go)

    def _do_arrive(self, idx: list[int]) -> None:
        for i in idx:
            row = self.rows[i]
            if row["glow"] is None:          # blue wash behind the new row
                glow = Quartz.CALayer.layer()
                glow.setBackgroundColor_(cg(M.ACCENT_DEEP, 0.34))
                glow.setCornerRadius_(8)
                glow.setFrame_(row["view"].layer().bounds())
                glow.setOpacity_(0.0)
                row["view"].layer().insertSublayer_atIndex_(glow, 0)
                row["glow"] = glow
            Quartz.CATransaction.begin()
            Quartz.CATransaction.setAnimationDuration_(0.0 if self.acc.reduce_motion else 0.25)
            row["glow"].setOpacity_(1.0)
            Quartz.CATransaction.commit()
            if row["icon"] is not None:
                set_symbol(row["icon"], "bell.fill", ns(M.ACCENT), not self.acc.reduce_motion)
            if row["box"] is not None and not self.acc.reduce_motion:
                self._bounce(row["box"]["box"])

    def _do_settle(self, idx: list[int]) -> None:
        for i in idx:
            row = self.rows[i]
            if row["glow"] is not None:
                Quartz.CATransaction.begin()
                Quartz.CATransaction.setAnimationDuration_(0.6)
                row["glow"].setOpacity_(0.0)
                Quartz.CATransaction.commit()
            if row["icon"] is not None:
                set_symbol(row["icon"], "bell", ns(M.ACCENT, 0.85), False)

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
                        rv.animator().setFrameOrigin_((M.ROW_INSET, r.y - 6))
                else:
                    rv.animator().setFrameOrigin_((M.ROW_INSET, r.y))
            if self.head.get("more") is not None:
                self.head["more"].animator().setFrameOrigin_((M.ROW_INSET + TEXT_X, new.more_y + 5))
        if secs:
            self._anim(secs, go)
        else:
            go()
        for i in self.gone:
            self.rows[i]["view"].setAccessibilityElement_(False)
        g = self.gen
        AppHelper.callLater(secs + 0.05, self._hide_gone, g)
        set_text(self.head["eyebrow"], new.eyebrow, F_EYEBROW(), ns(M.ACCENT), kern=EYEBROW_KERN)
        if new.title != self.head["title"].stringValue():
            set_text(self.head["title"], new.title, F_TITLE(), self.white(M.TEXT_A))
        if self.visible and self.anchor is not None:      # the card shortens from the bottom; its top stays put
            frame = self.frame_for(new, self.anchor)
            if secs:
                animate_frame(self.panel, frame, None, secs, out_ease())
            else:
                self.panel.setFrame_display_(frame, True)
