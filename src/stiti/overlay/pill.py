"""The pill: a white liquid-glass capsule, top-centre under the menu bar, with Stiti's 7 dots.

Main thread only (ui.py marshals every call). Motion is transform/opacity only, so Core Animation's render server
does the frames: breathing and the thinking ripple are render-server animations (no Python per frame), and the
mic / voice swell is a discrete 30 Hz transform update that is skipped when the swell didn't move.
"""
from __future__ import annotations

import AppKit
import objc
import Quartz
from PyObjCTools import AppHelper

from . import model as M
from .surface import Access, animate_frame, cg, fade, frame_rate, label, make_panel, make_surface, ns, out_ease, \
    set_symbol, set_text, symbol


class _PillPanel(AppKit.NSPanel):
    def canBecomeKeyWindow(self):           # the pill never takes his keyboard
        return False

    def canBecomeMainWindow(self):
        return False


class _PillView(AppKit.NSView):
    def acceptsFirstMouse_(self, event):    # a click works without first focusing the (inactive) panel
        return True

    def hitTest_(self, point):
        return self if objc.super(_PillView, self).hitTest_(point) is not None else None

    def mouseDown_(self, event):
        cb = getattr(self, "on_click", None)
        if cb is not None:
            cb()


class Pill:
    def __init__(self, acc: Access, on_click=None):
        self.acc = acc
        self.w = M.PILL_W
        self.visible = False
        self.expanded = False
        self.gen = 0
        self.anchor: tuple[float, float] | None = None
        self.scales = [1.0] * M.N_DOTS
        self.bright = 1.0
        self.dim = False
        self.look: M.Look = M.LOOKS["hidden"]
        self.panel = make_panel(_PillPanel, self.w, M.PILL_H)
        self.panel.setIgnoresMouseEvents_(True)
        outer, host = make_surface(self.w, M.PILL_H, M.PILL_H / 2, acc, _PillView)
        host.on_click = on_click
        self.clickable = False                       # True once someone handles "click = stop her"
        self.panel.setContentView_(outer)
        self.host = host
        self.box = Quartz.CALayer.layer()
        self.box.setBounds_(((0, 0), (M.DOTS_W, M.PILL_H)))
        self.box.setPosition_((self.w / 2, M.PILL_H / 2))
        host.layer().addSublayer_(self.box)
        self.dots = []
        for i, c in enumerate(M.DOT_COLOURS):
            d = Quartz.CALayer.layer()
            d.setBounds_(((0, 0), (M.DOT, M.DOT)))
            d.setCornerRadius_(M.DOT / 2)
            d.setPosition_((M.DOT / 2 + i * (M.DOT + M.DOT_GAP), M.PILL_H / 2))
            d.setBackgroundColor_(cg(c))
            self.box.addSublayer_(d)
            self.dots.append(d)
        self.sym = symbol("checkmark.circle.fill", 14, ns(M.BLUE))
        self.text = label("", AppKit.NSFont.systemFontOfSize_weight_(13, AppKit.NSFontWeightMedium), ns(M.NAVY))
        for v in (self.sym, self.text):
            if v is not None:
                v.setAlphaValue_(0.0)
                host.addSubview_(v)

    # ---------------------------------------------------------------- show / hide
    def frame_for(self, w: float):
        x, top = self.anchor
        return ((round(x - w / 2), round(top - M.TOP_GAP - M.PILL_H)), (w, M.PILL_H))

    def show(self, anchor: tuple[float, float]) -> None:
        self.gen += 1
        self.anchor = anchor
        self.panel.setFrame_display_(self.frame_for(self.w), False)
        self.panel.orderFrontRegardless()            # shows WITHOUT activating Stiti
        self.visible, self.dim = True, False
        fade(self.panel, 1.0, 0.18)
        if not self.acc.reduce_motion:               # dots bloom out from the centre, 30 ms stagger
            t0 = Quartz.CACurrentMediaTime()
            mid = (M.N_DOTS - 1) / 2
            for i, d in enumerate(self.dots):
                a = Quartz.CABasicAnimation.animationWithKeyPath_("transform.scale")
                a.setFromValue_(0.0)
                a.setToValue_(1.0)
                a.setDuration_(0.28)
                a.setBeginTime_(t0 + 0.03 * abs(i - mid))
                a.setFillMode_(Quartz.kCAFillModeBackwards)
                a.setTimingFunction_(out_ease())
                frame_rate(a, M.FPS)
                d.addAnimation_forKey_(a, "bloom")

    def hide(self) -> None:
        if not self.visible:
            return
        self.visible = False
        self.gen += 1
        g = self.gen
        fade(self.panel, 0.0, 0.35)
        if not self.acc.reduce_motion:               # dots collapse toward the centre as it fades
            a = Quartz.CABasicAnimation.animationWithKeyPath_("transform.scale")
            a.setToValue_(0.4)
            a.setDuration_(0.35)
            a.setFillMode_(Quartz.kCAFillModeForwards)
            a.setRemovedOnCompletion_(False)
            frame_rate(a, M.FPS)
            self.box.addAnimation_forKey_(a, "collapse")
        AppHelper.callLater(0.4, self._order_out, g)

    def _order_out(self, g: int) -> None:
        if g != self.gen:
            return                                   # shown again meanwhile
        self.panel.orderOut_(None)
        self.box.removeAllAnimations()
        for d in self.dots:
            d.removeAllAnimations()
        if self.expanded:
            self.collapse(animate=False)

    # ---------------------------------------------------------------- state look
    def set_look(self, look: M.Look) -> None:
        self.look = look
        self.panel.setIgnoresMouseEvents_(look.click_through or not self.clickable)
        self.box.removeAnimationForKey_("breathe")
        self.box.removeAnimationForKey_("pulse")
        for d in self.dots:
            d.removeAnimationForKey_("wave")
        if look.source is None:
            self.set_level(0.0, force=True)
        if self.dim and not look.click_through:
            self.set_dim(False)
        rm = self.acc.reduce_motion
        if look.anim == "breathe" and not rm:        # 0.4 Hz breathing, render server, 15 fps is plenty
            a = Quartz.CABasicAnimation.animationWithKeyPath_("opacity")
            a.setFromValue_(0.62)
            a.setToValue_(1.0)
            a.setDuration_(1.25)
            a.setAutoreverses_(True)
            a.setRepeatCount_(1e9)
            a.setTimingFunction_(Quartz.CAMediaTimingFunction.functionWithName_(
                Quartz.kCAMediaTimingFunctionEaseInEaseOut))
            frame_rate(a, 15.0)
            self.box.addAnimation_forKey_(a, "breathe")
        elif look.anim == "wave" and rm:             # Reduce Motion: a calm fade instead of a ripple
            a = Quartz.CABasicAnimation.animationWithKeyPath_("opacity")
            a.setFromValue_(0.45)
            a.setToValue_(1.0)
            a.setDuration_(0.9)
            a.setAutoreverses_(True)
            a.setRepeatCount_(1e9)
            frame_rate(a, 15.0)
            self.box.addAnimation_forKey_(a, "pulse")
        elif look.anim == "wave":                    # travelling ripple left → right
            t0 = Quartz.CACurrentMediaTime()
            for i, d in enumerate(self.dots):
                a = Quartz.CABasicAnimation.animationWithKeyPath_("transform.translation.y")
                a.setFromValue_(-3.0)
                a.setToValue_(3.0)
                a.setDuration_(0.6)
                a.setAutoreverses_(True)
                a.setRepeatCount_(1e9)
                a.setBeginTime_(t0 + i * 0.09)
                a.setTimingFunction_(Quartz.CAMediaTimingFunction.functionWithName_(
                    Quartz.kCAMediaTimingFunctionEaseInEaseOut))
                frame_rate(a, M.FPS)
                d.addAnimation_forKey_(a, "wave")

    def set_level(self, v: float, force: bool = False) -> None:
        """0..1 swell. Reduce Motion: brightness instead of size."""
        if self.acc.reduce_motion:
            b = 0.55 + 0.45 * v if self.look.source else 1.0
            if force or M.changed(b, self.bright):
                Quartz.CATransaction.begin()
                Quartz.CATransaction.setDisableActions_(True)
                self.box.setOpacity_(b)
                Quartz.CATransaction.commit()
                self.bright = b
            return
        scales = M.dot_scales(v)
        if not force and not M.changed(scales[M.N_DOTS // 2], self.scales[M.N_DOTS // 2]):
            return                                   # nothing visible changed: no commit, no WindowServer work
        Quartz.CATransaction.begin()
        Quartz.CATransaction.setDisableActions_(True)
        for d, k in zip(self.dots, scales):
            d.setTransform_(Quartz.CATransform3DMakeScale(k, k, 1.0))
        Quartz.CATransaction.commit()
        self.scales = scales

    def set_dim(self, on: bool) -> None:
        """Pointer over the click-through pill → fade to 35 % so it never hides what's under it."""
        if on == self.dim or not self.visible:
            return
        self.dim = on
        fade(self.panel, 0.35 if on else 1.0, 0.2)

    def contains_pointer(self) -> bool:
        if not self.visible:
            return False
        p, f = AppKit.NSEvent.mouseLocation(), self.panel.frame()
        return f.origin.x <= p.x <= f.origin.x + f.size.width and f.origin.y <= p.y <= f.origin.y + f.size.height

    # ---------------------------------------------------------------- widen: "Checking calendar" / "✓ Start resume · 4 PM"
    def expand(self, sym_name: str, text: str, *, with_dots: bool, tint=M.BLUE) -> None:
        set_text(self.text, text, AppKit.NSFont.systemFontOfSize_weight_(13, AppKit.NSFontWeightMedium), ns(M.NAVY))
        self.text.sizeToFit()
        tw, th = self.text.frame().size.width, self.text.frame().size.height
        w = M.pill_width(tw, with_dots=with_dots, symbol=self.sym is not None)
        x = 18.0
        Quartz.CATransaction.begin()
        Quartz.CATransaction.setAnimationDuration_(0.25)
        if with_dots:
            self.box.setPosition_((x + M.DOTS_W / 2, M.PILL_H / 2))
            self.box.setHidden_(False)
            x += M.DOTS_W + 14
        else:
            self.box.setHidden_(True)
        Quartz.CATransaction.commit()
        if self.sym is not None:
            set_symbol(self.sym, sym_name, ns(tint), animate=not self.acc.reduce_motion and self.visible)
            self.sym.setFrame_(((x, (M.PILL_H - 18) / 2), (18, 18)))
            x += 22
        self.text.setFrame_(((x, (M.PILL_H - th) / 2), (max(10.0, w - x - 18), th)))
        self.expanded = True
        self._resize(w)
        for v in (self.sym, self.text):
            if v is not None:
                v.animator().setAlphaValue_(1.0)

    def collapse(self, animate: bool = True) -> None:
        if not self.expanded:
            return
        self.expanded = False
        for v in (self.sym, self.text):
            if v is not None:
                (v.animator() if animate else v).setAlphaValue_(0.0)
        Quartz.CATransaction.begin()
        Quartz.CATransaction.setDisableActions_(not animate)
        self.box.setHidden_(False)
        self.box.setPosition_((M.PILL_W / 2, M.PILL_H / 2))
        Quartz.CATransaction.commit()
        self._resize(M.PILL_W, animate)

    def _resize(self, w: float, animate: bool = True) -> None:
        if w == self.w:
            return
        self.w = w
        if self.anchor is None:
            return
        if self.visible and animate and not self.acc.reduce_motion:
            animate_frame(self.panel, self.frame_for(w), None, 0.25)
        else:
            self.panel.setFrame_display_(self.frame_for(w), self.visible)
        if not self.expanded:
            self.box.setPosition_((w / 2, M.PILL_H / 2))

    def close(self) -> None:
        self.gen += 1
        self.panel.orderOut_(None)
