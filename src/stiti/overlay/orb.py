"""The orb: Stiti's arc-reactor circle, top-centre under the menu bar (D44).

A solid navy disc with a SKY hairline rim and a BLUE glow. Inside, centre outward: a glowing core, an inner ring of
three arcs (turns clockwise), a dashed mid ring (turns the other way, slower), a ring of 36 ticks that works as a
circular equaliser, and an outer arc a comet chases around while she thinks. For "Checking calendar" / "✓ Added …"
the disc grows to the right into a capsule; the orb stays as its round left end.

Main thread only (ui.py marshals every call). Motion is transform/opacity only. Everything that loops (rotation,
breathing, the comet, the thinking wave) is a render-server animation: no Python per frame. The 30 Hz tick only
pushes the level (tick lengths + core size) as plain transform updates with implicit animations off, and only when
something visible moved (gliding between pushes made Core Animation build 36 animations per frame: ~10 % of a core
on the M2, measured). Reduce Motion: nothing rotates or travels; the level shows as brightness.
"""
from __future__ import annotations

import math
import time

import AppKit
import objc
import Quartz
from PyObjCTools import AppHelper

from . import model as M
from .surface import Access, animate_frame, cg, crisp, ease, fade, frame_rate, hairline, label, make_panel, ns, \
    out_ease, set_symbol, set_text, state_ease, still, surface_alpha, symbol, text_alpha

C = M.ORB / 2                                   # the reactor's centre, in its own 64 × 64 box
F_LABEL = lambda: AppKit.NSFont.systemFontOfSize_weight_(14, AppKit.NSFontWeightMedium)   # noqa: E731
CORE_BOX = 20.0                                 # the core's gradient box: a 14 pt dot + 3 pt of soft edge
BREATHE = (0.86, 1.14)                          # core scale while it breathes
COMET = ((104.0, 0.10), (82.0, 0.14), (62.0, 0.20), (44.0, 0.28), (28.0, 0.40), (13.0, 0.60), (4.0, 1.0))  # tail → head: (°, alpha)


class _OrbPanel(AppKit.NSPanel):
    def canBecomeKeyWindow(self):           # the orb never takes his keyboard
        return False

    def canBecomeMainWindow(self):
        return False


class _OrbView(AppKit.NSView):
    def acceptsFirstMouse_(self, event):    # a click works without first focusing the (inactive) panel
        return True

    def hitTest_(self, point):
        """Only the disc (or its capsule) is ours: the glow around it is not (native shape hit-testing, no polling)."""
        if objc.super(_OrbView, self).hitTest_(point) is None:
            return None
        p = self.convertPoint_fromView_(point, self.superview())
        return self if M.in_orb(p.x - M.HALO, p.y - M.HALO, self.bounds().size.width - 2 * M.HALO) else None

    def mouseDown_(self, event):
        cb = getattr(self, "on_click", None)
        if cb is not None:
            cb()


def _layer(cls=None, frame=None):
    lay = (cls or Quartz.CALayer).layer()
    if frame is not None:
        lay.setFrame_(frame)
    return crisp(lay)


def _arc(path, r: float, start_deg: float, sweep_deg: float) -> None:
    """Counter-clockwise arc (y up) of `sweep_deg` from `start_deg`, around the reactor's centre."""
    a0, a1 = math.radians(start_deg), math.radians(start_deg + sweep_deg)
    Quartz.CGPathMoveToPoint(path, None, C + r * math.cos(a0), C + r * math.sin(a0))
    Quartz.CGPathAddArc(path, None, C, C, r, a0, a1, False)


def _stroke(path, colour, width: float, cap=Quartz.kCALineCapRound):
    s = _layer(Quartz.CAShapeLayer, ((0, 0), (M.ORB, M.ORB)))
    s.setPath_(path)
    s.setFillColor_(None)
    s.setStrokeColor_(colour)
    s.setLineWidth_(width)
    s.setLineCap_(cap)
    return s


def _radial(size: float, stops: list[tuple[float, tuple, float]]):
    """A round gradient box centred on the reactor: (location 0..1 of the radius, colour, alpha)."""
    g = _layer(Quartz.CAGradientLayer)
    g.setBounds_(((0, 0), (size, size)))
    g.setPosition_((C, C))
    g.setType_("radial")
    g.setStartPoint_((0.5, 0.5))
    g.setEndPoint_((1.0, 1.0))
    g.setColors_([cg(c, a) for _, c, a in stops])
    g.setLocations_([loc for loc, _, _ in stops])
    return g


class Orb:
    def __init__(self, acc: Access, on_click=None):
        self.acc = acc
        self.w = M.ORB
        self.visible = False
        self.expanded = False
        self.gen = 0
        self.anchor: tuple[float, float] | None = None
        self.scales = [1.0] * M.N_TICKS
        self.cs = 1.0
        self.bright = 1.0
        self.dim = False
        self.waving = False
        self.clickable = False                       # True once someone handles "click = stop her"
        self.look: M.Look = M.LOOKS["hidden"]
        self.fps = M.FPS_LOW_POWER if acc.low_power else M.FPS
        pw, ph = M.ORB + 2 * M.HALO, M.ORB + 2 * M.HALO
        self.panel = make_panel(_OrbPanel, pw, ph)
        self.panel.setHasShadow_(False)              # the glow and the soft shadow are our own layers
        self.panel.setIgnoresMouseEvents_(True)
        flex = AppKit.NSViewWidthSizable | AppKit.NSViewHeightSizable
        root = _OrbView.alloc().initWithFrame_(((0, 0), (pw, ph)))
        root.setWantsLayer_(True)
        root.setAutoresizingMask_(flex)
        root.on_click = on_click
        canvas = AppKit.NSView.alloc().initWithFrame_(((0, 0), (pw, ph)))
        canvas.setWantsLayer_(True)
        canvas.setAutoresizingMask_(flex)
        root.addSubview_(canvas)
        self.style = M.apply_theme()
        self._build_disc(canvas.layer())
        self._build_reactor(canvas.layer())
        if self.style == "knot":
            self._build_knot(canvas.layer())
        clip = AppKit.NSView.alloc().initWithFrame_(((M.HALO, M.HALO), (M.ORB, M.ORB)))   # the label never spills
        clip.setWantsLayer_(True)                                                         # out of the capsule
        clip.layer().setCornerRadius_(C)
        clip.layer().setMasksToBounds_(True)
        clip.setAutoresizingMask_(AppKit.NSViewWidthSizable)
        root.addSubview_(clip)
        self.sym = symbol("checkmark.circle.fill", 15, ns(M.ACCENT))
        self.text = label("", F_LABEL(), ns(M.WHITE, text_alpha(M.TEXT_A, acc)))
        for v in (self.sym, self.text):
            if v is not None:
                v.setAlphaValue_(0.0)
                clip.addSubview_(v)
        self.panel.setContentView_(root)
        self.host = root

    # ---------------------------------------------------------------- layers
    def _build_disc(self, base) -> None:
        """Three layers that stretch with the panel (disc ↔ capsule): soft shadow, the glowing disc, the rim."""
        frame = ((M.HALO, M.HALO), (M.ORB, M.ORB))
        fill = cg(M.DISC, surface_alpha(M.DISC_A, self.acc))
        self.shade, self.glow, self.rim = _layer(frame=frame), _layer(frame=frame), _layer(frame=frame)
        for lay in (self.shade, self.glow, self.rim):
            lay.setCornerRadius_(C)
            lay.setAutoresizingMask_(Quartz.kCALayerWidthSizable)
            still(lay)
            base.addSublayer_(lay)
        for lay, colour, radius, opacity, dy in ((self.shade, cg((0, 0, 0)), 5.0, 0.45, -2.0),
                                                 (self.glow, cg(M.BLUE), 7.0, 0.0, 0.0)):
            lay.setBackgroundColor_(fill)
            lay.setShadowColor_(colour)
            lay.setShadowRadius_(radius)
            lay.setShadowOpacity_(opacity)
            lay.setShadowOffset_((0.0, dy))
        self.rim.setBorderWidth_(1.0)
        self.rim.setBorderColor_(hairline(self.acc, M.LOOKS["idle"].rim))

    def _build_reactor(self, base) -> None:
        r = self.reactor = _layer()
        r.setBounds_(((0, 0), (M.ORB, M.ORB)))
        r.setPosition_((M.HALO + C, M.HALO + C))
        base.addSublayer_(r)
        self.aura = _radial(M.ORB, [(0.0, M.BLUE, 0.42), (0.5, M.BLUE, 0.14), (1.0, M.BLUE, 0.0)])
        r.addSublayer_(self.aura)
        # 5. outer arc (its gap points down at the card) + the comet that chases around it while she thinks
        p = Quartz.CGPathCreateMutable()
        _arc(p, M.R_OUTER, -90.0 + (360.0 - M.OUTER_ARC_DEG) / 2, M.OUTER_ARC_DEG)
        self.track = _stroke(p, cg(M.SKY, 0.30), 1.5)
        r.addSublayer_(self.track)
        self.comet = _layer(frame=((0, 0), (M.ORB, M.ORB)))
        for deg, a in COMET:                         # stacked arcs, all ending at the head: a tail that fades
            p = Quartz.CGPathCreateMutable()
            _arc(p, M.R_OUTER, 90.0, deg)
            self.comet.addSublayer_(_stroke(p, cg(M.WHITE if a >= 1.0 else M.SKY, a), 2.0 if a >= 1.0 else 1.5))
        self.comet.setOpacity_(0.0)
        r.addSublayer_(self.comet)
        # 4. tick ring: 36 radial ticks, each stretched outward by the level (a circular equaliser)
        self.tickring = _layer(frame=((0, 0), (M.ORB, M.ORB)))
        self.ticks = []
        for i in range(M.N_TICKS):
            th = M.tick_angle(i)
            spoke = _layer()                         # stands on the circle, pointing outward
            spoke.setBounds_(((0, 0), (0, 0)))
            spoke.setPosition_((C + M.R_TICK * math.sin(th), C + M.R_TICK * math.cos(th)))
            spoke.setTransform_(Quartz.CATransform3DMakeRotation(-th, 0, 0, 1))
            tk = _layer()                            # the level stretches it from its inner end
            tk.setAnchorPoint_((0.5, 0.0))
            tk.setBounds_(((0, 0), (M.TICK_W, M.TICK_LEN)))
            tk.setPosition_((0, 0))
            tk.setCornerRadius_(M.TICK_W / 2)
            tk.setBackgroundColor_(cg(M.WHITE, 0.95) if i % (M.N_TICKS // 4) == 0 else cg(M.SKY))
            spoke.addSublayer_(tk)
            self.tickring.addSublayer_(spoke)
            self.ticks.append(tk)
        r.addSublayer_(self.tickring)
        # 3. mid ring: thin, dashed, turns counter-clockwise
        p = Quartz.CGPathCreateMutable()
        Quartz.CGPathAddEllipseInRect(p, None, ((C - M.R_MID, C - M.R_MID), (2 * M.R_MID, 2 * M.R_MID)))
        self.mid = _stroke(p, cg(M.BLUE, 0.85 if self.acc.increase_contrast else 0.6), 1.0, Quartz.kCALineCapButt)
        self.mid.setLineDashPattern_(list(M.dash_pattern(M.R_MID)))
        r.addSublayer_(self.mid)
        # 2. inner ring: three arcs, turns clockwise
        p = Quartz.CGPathCreateMutable()
        for k in range(M.INNER_ARCS):
            _arc(p, M.R_INNER, 90.0 - M.INNER_ARC_DEG / 2 + k * 360.0 / M.INNER_ARCS, M.INNER_ARC_DEG)
        self.inner = _stroke(p, cg(M.SKY), 2.0)
        r.addSublayer_(self.inner)
        # 1. core: a glowing dot that swells with the level (holder) and breathes (core), plus its bloom
        self.bloom = _radial(2 * M.R_MID, [(0.0, M.SKY, 0.40), (0.45, M.BLUE, 0.26), (1.0, M.BLUE, 0.0)])
        self.bloom.setOpacity_(0.0)
        r.addSublayer_(self.bloom)
        self.hold = _layer()
        self.hold.setBounds_(((0, 0), (CORE_BOX, CORE_BOX)))
        self.hold.setPosition_((C, C))
        edge = M.R_CORE / (CORE_BOX / 2)
        self.core = _radial(CORE_BOX, [(0.0, M.WHITE, 1.0), (edge * 0.28, M.WHITE, 0.96), (edge * 0.64, M.SKY, 1.0),
                                       (edge, M.BLUE, 0.9), (1.0, M.BLUE, 0.0)])
        self.core.setPosition_((CORE_BOX / 2, CORE_BOX / 2))
        self.hold.addSublayer_(self.core)
        r.addSublayer_(self.hold)

    # ---------------------------------------------------------------- the knot (preview style, STITI_ORB=knot)
    def _knot_path(self, pts, closed: bool):
        p = Quartz.CGPathCreateMutable()
        for i, (x, y) in enumerate(pts):
            (Quartz.CGPathMoveToPoint if i == 0 else Quartz.CGPathAddLineToPoint)(p, None, C + M.R_KNOT * x, C + M.R_KNOT * y)
        if closed:
            Quartz.CGPathCloseSubpath(p)
        return p

    def _build_knot(self, base) -> None:
        """One closed line woven over and under itself on an indigo disc, three points travelling along it, a dashed
        ring around. The reactor's rings stay built but hidden, so the two styles share every other code path."""
        for lay in (self.aura, self.track, self.comet, self.tickring, self.mid, self.inner, self.bloom, self.hold):
            lay.setHidden_(True)
        fill = cg(M.INDIGO, surface_alpha(M.DISC_A, self.acc))
        self.shade.setBackgroundColor_(fill)
        self.glow.setBackgroundColor_(fill)
        self.glow.setShadowColor_(cg(M.AMBER))
        k = self.kbox = _layer()
        k.setBounds_(((0, 0), (M.ORB, M.ORB)))
        k.setPosition_((M.HALO + C, M.HALO + C))
        base.addSublayer_(k)
        self.kaura = _radial(M.ORB, [(0.0, M.AMBER, 0.34), (0.55, M.AMBER, 0.10), (1.0, M.AMBER, 0.0)])
        k.addSublayer_(self.kaura)
        p = Quartz.CGPathCreateMutable()
        Quartz.CGPathAddEllipseInRect(p, None, ((C - M.R_KNOT_RING, C - M.R_KNOT_RING), (2 * M.R_KNOT_RING, 2 * M.R_KNOT_RING)))
        self.kring = _stroke(p, cg(M.AMBER, 0.75), 1.0)
        self.kring.setLineDashPattern_([0.6, 3.4])
        k.addSublayer_(self.kring)
        self.knot = _layer(frame=((0, 0), (M.ORB, M.ORB)))           # turns slowly, swells with the level
        k.addSublayer_(self.knot)
        pts = M.knot_points()
        self.kpath = self._knot_path(pts, True)
        self.kline = _stroke(self.kpath, cg(M.RICE), 2.0)
        self.kline.setLineJoin_(Quartz.kCALineJoinRound)
        self.knot.addSublayer_(self.kline)
        self.kover = _layer(frame=((0, 0), (M.ORB, M.ORB)))          # the three stretches that pass OVER
        n = len(pts)
        for a, b in M.knot_overs(pts):
            seg = [pts[i % n] for i in range(a, b + 1)]
            gap = [pts[i % n] for i in range(a + 3, b - 2)]          # the cut in the line underneath
            self.kover.addSublayer_(_stroke(self._knot_path(gap, False), fill, 5.4, Quartz.kCALineCapButt))
            self.kover.addSublayer_(_stroke(self._knot_path(seg, False), cg(M.RICE), 2.0, Quartz.kCALineCapButt))
        self.knot.addSublayer_(self.kover)
        self.beads = []
        for j, col in enumerate((M.CORAL, M.AMBER, M.AMBER)):
            holder = _layer()                                        # rides the line
            holder.setBounds_(((0, 0), (0, 0)))
            x, y = pts[(j * n) // 3]
            holder.setPosition_((C + M.R_KNOT * x, C + M.R_KNOT * y))
            dot = _layer()                                           # swells with the level
            dot.setBounds_(((0, 0), (2 * M.BEAD_R, 2 * M.BEAD_R)))
            dot.setCornerRadius_(M.BEAD_R)
            dot.setBackgroundColor_(cg(col))
            dot.setShadowColor_(cg(col))
            dot.setShadowRadius_(2.5)
            dot.setShadowOpacity_(0.9)
            dot.setShadowOffset_((0.0, 0.0))
            holder.addSublayer_(dot)
            self.knot.addSublayer_(holder)
            self.beads.append((holder, dot))
        self.kphase, self.klap, self.kt = 0.0, 0.0, Quartz.CACurrentMediaTime()
        self.ks = 1.0

    def _knot_look(self, look: M.Look) -> None:
        e = look.glow
        Quartz.CATransaction.begin()
        Quartz.CATransaction.setAnimationDuration_(M.STATE_S)
        Quartz.CATransaction.setAnimationTimingFunction_(state_ease())
        self.glow.setShadowOpacity_(look.glow)
        self.rim.setBorderColor_(cg(M.RICE, 0.95 if self.acc.increase_contrast else look.rim))
        self.kaura.setOpacity_(0.3 + 0.7 * e)
        self.kring.setOpacity_(0.45 + 0.55 * e)
        self.kline.setOpacity_(0.7 + 0.3 * e)
        self.kover.setOpacity_(0.0 if look.comet else 1.0)           # while the line draws itself it lies flat
        Quartz.CATransaction.commit()
        still_now = self.acc.reduce_motion
        self._spin(self.knot, 0.0 if still_now else look.counter * 4, clockwise=False)
        self._spin(self.kring, 0.0 if still_now else look.counter * 2, clockwise=True)
        now = Quartz.CACurrentMediaTime()                            # carry the points on from where they are
        if self.klap > 0:
            self.kphase = (self.kphase + (now - self.kt) / self.klap) % 1.0
        self.kt, self.klap = now, (0.0 if still_now or look.spin <= 0 else look.spin * M.KNOT_LAP)
        for j, (holder, _) in enumerate(self.beads):
            holder.removeAnimationForKey_("ride")
            if self.klap <= 0:
                continue
            a = Quartz.CAKeyframeAnimation.animationWithKeyPath_("position")
            a.setPath_(self.kpath)
            a.setCalculationMode_(Quartz.kCAAnimationPaced)
            a.setDuration_(self.klap)
            a.setRepeatCount_(1e9)
            a.setBeginTime_(now - ((self.kphase + j / 3.0) % 1.0) * self.klap)
            frame_rate(a, self.fps)
            holder.addAnimation_forKey_(a, "ride")
        self.kline.removeAnimationForKey_("draw")
        if look.comet and not still_now:                             # thinking: the line keeps drawing itself
            a = Quartz.CAKeyframeAnimation.animationWithKeyPath_("strokeEnd")
            a.setValues_([0.0, 1.0, 1.0])
            a.setKeyTimes_([0.0, 0.78, 1.0])
            a.setDuration_(look.comet * 2.4)
            a.setRepeatCount_(1e9)
            frame_rate(a, self.fps)
            self.kline.addAnimation_forKey_(a, "draw")
        self.kbox.removeAnimationForKey_("pulse")
        if look.pulse:
            a = Quartz.CABasicAnimation.animationWithKeyPath_("opacity")
            a.setFromValue_(0.5)
            a.setToValue_(1.0)
            a.setDuration_(look.pulse / 2)
            a.setAutoreverses_(True)
            a.setRepeatCount_(1e9)
            frame_rate(a, M.FPS_LOW_POWER)
            self.kbox.addAnimation_forKey_(a, "pulse")

    def _knot_level(self, v: float, force: bool, secs: float) -> None:
        a = min(1.0, max(0.0, v * self.look.gain))
        ks = 1.0 + (0.0 if self.acc.reduce_motion else M.KNOT_SWELL * a)
        if not force and not M.changed(a, self.cs):
            return
        Quartz.CATransaction.begin()
        if secs > 0:
            Quartz.CATransaction.setAnimationDuration_(secs)
            Quartz.CATransaction.setAnimationTimingFunction_(state_ease())
        else:
            Quartz.CATransaction.setDisableActions_(True)
        self.kbox.setAffineTransform_((ks, 0.0, 0.0, ks, 0.0, 0.0))
        bs = 1.0 + M.BEAD_SWELL * a
        for _, dot in self.beads:
            dot.setAffineTransform_((bs, 0.0, 0.0, bs, 0.0, 0.0))
        self.kaura.setOpacity_((0.3 + 0.7 * self.look.glow) * (0.55 + 0.45 * a) if self.look.source else 0.3 + 0.7 * self.look.glow)
        Quartz.CATransaction.commit()
        self.cs = a

    # ---------------------------------------------------------------- show / hide / move
    def frame_for(self, w: float, anchor=None):
        x, top = anchor or self.anchor
        return ((round(x - w / 2 - M.HALO), round(top - M.TOP_GAP - M.ORB - M.HALO)), (w + 2 * M.HALO, M.ORB + 2 * M.HALO))

    def show(self, anchor: tuple[float, float]) -> None:
        self.gen += 1
        self.anchor = anchor
        self.reactor.removeAnimationForKey_("collapse")
        self.panel.setFrame_display_(self.frame_for(self.w), False)
        self.panel.orderFrontRegardless()            # shows WITHOUT activating Stiti
        self.visible, self.dim = True, False
        fade(self.panel, 1.0, M.STATE_S, state_ease())
        if not self.acc.reduce_motion:               # the reactor blooms open from its centre
            a = Quartz.CABasicAnimation.animationWithKeyPath_("transform.scale")
            a.setFromValue_(0.55)
            a.setToValue_(1.0)
            a.setDuration_(0.32)
            a.setTimingFunction_(out_ease())
            frame_rate(a, self.fps)
            self.reactor.addAnimation_forKey_(a, "bloom")

    def move(self, anchor: tuple[float, float]) -> None:
        """He moved to another display: fade out, jump, fade back in (never slide across screens)."""
        if anchor == self.anchor or not self.visible:
            self.anchor = anchor
            return
        self.anchor = anchor
        self.gen += 1
        g = self.gen
        fade(self.panel, 0.0, 0.1, state_ease())

        def land():
            if g != self.gen or not self.visible:
                return
            self.panel.setFrame_display_(self.frame_for(self.w), False)
            fade(self.panel, 0.35 if self.dim else 1.0, 0.2)
        AppHelper.callLater(0.12, land)

    def hide(self) -> None:
        if not self.visible:
            return
        self.visible = False
        self.gen += 1
        g = self.gen
        fade(self.panel, 0.0, 0.35)
        if not self.acc.reduce_motion:               # the reactor closes toward its centre as it fades
            a = Quartz.CABasicAnimation.animationWithKeyPath_("transform.scale")
            a.setToValue_(0.6)
            a.setDuration_(0.35)
            a.setFillMode_(Quartz.kCAFillModeForwards)
            a.setRemovedOnCompletion_(False)
            frame_rate(a, self.fps)
            self.reactor.addAnimation_forKey_(a, "collapse")
        AppHelper.callLater(0.4, self._order_out, g)

    def _order_out(self, g: int) -> None:
        if g != self.gen:
            return                                   # shown again meanwhile
        self.panel.orderOut_(None)
        self._still()                                # hidden = nothing left running on the render server
        if self.expanded:
            self.collapse(animate=False)

    def _still(self) -> None:
        for lay in (self.reactor, self.inner, self.mid, self.comet, self.core, self.aura, *self.ticks):
            lay.removeAllAnimations()
        self.waving = False
        if self.style == "knot":
            for lay in (self.kbox, self.knot, self.kring, self.kline, *[h for h, _ in self.beads]):
                lay.removeAllAnimations()
            self.klap = 0.0

    # ---------------------------------------------------------------- state look
    def set_look(self, look: M.Look) -> None:
        """Cross-fade to a state's look (≈200 ms, ease-out): brightness now, the loops re-timed from where they are."""
        self.look = look
        self.panel.setIgnoresMouseEvents_(look.click_through or not self.clickable)
        if look.source is None:
            self.set_level(0.0, force=True, secs=M.STATE_S)
        if self.dim and not look.click_through:
            self.set_dim(False)
        if self.style == "knot":
            return self._knot_look(look)
        e = look.glow                                # how "awake" she looks, 0..1
        Quartz.CATransaction.begin()
        Quartz.CATransaction.setAnimationDuration_(M.STATE_S)
        Quartz.CATransaction.setAnimationTimingFunction_(state_ease())
        self.glow.setShadowOpacity_(look.glow)
        self.rim.setBorderColor_(hairline(self.acc, look.rim))
        self.aura.setOpacity_(0.35 + 0.65 * e)
        self.tickring.setOpacity_(look.ticks)
        self.track.setOpacity_(0.55 + 0.45 * e)
        self.mid.setOpacity_(0.55 + 0.45 * e)
        self.inner.setOpacity_(0.55 + 0.45 * e)
        self.hold.setOpacity_(0.72 + 0.28 * e)
        self.comet.setOpacity_(1.0 if look.comet else 0.0)
        Quartz.CATransaction.commit()
        self._spin(self.inner, look.spin, clockwise=True)
        self._spin(self.mid, look.counter, clockwise=False)
        if look.comet:
            self._spin(self.comet, look.comet, clockwise=True)
        else:                                        # let it fade out first, then stop it
            AppHelper.callLater(M.STATE_S + 0.1, self._stop_comet, look)
        self._breathe(look.breathe)
        self._wave(look.wave)
        self.reactor.removeAnimationForKey_("pulse")
        if look.pulse:                               # Reduce Motion while thinking: a calm fade, nothing travels
            a = Quartz.CABasicAnimation.animationWithKeyPath_("opacity")
            a.setFromValue_(0.5)
            a.setToValue_(1.0)
            a.setDuration_(look.pulse / 2)
            a.setAutoreverses_(True)
            a.setRepeatCount_(1e9)
            frame_rate(a, M.FPS_LOW_POWER)
            self.reactor.addAnimation_forKey_(a, "pulse")

    def _stop_comet(self, look: M.Look) -> None:
        if self.look is look:
            self.comet.removeAnimationForKey_("spin")

    def _now(self, layer, key: str, default: float) -> float:
        """What a looping property shows right now (so a new loop starts there: nothing snaps)."""
        p = layer.presentationLayer() if layer.animationKeys() else None
        v = (p or layer).valueForKeyPath_(key)
        return float(v) if v is not None else default

    def _spin(self, layer, period: float, clockwise: bool) -> None:
        cur = self._now(layer, "transform.rotation.z", 0.0) % (2 * math.pi)
        layer.removeAnimationForKey_("spin")
        Quartz.CATransaction.begin()
        Quartz.CATransaction.setDisableActions_(True)
        layer.setValue_forKeyPath_(cur, "transform.rotation.z")      # where it stands if nothing turns it
        Quartz.CATransaction.commit()
        if period <= 0:
            return
        a = Quartz.CABasicAnimation.animationWithKeyPath_("transform.rotation.z")
        a.setFromValue_(cur)
        a.setToValue_(cur + (-2 * math.pi if clockwise else 2 * math.pi))        # y is up: negative = clockwise
        a.setDuration_(period)
        a.setRepeatCount_(1e9)
        frame_rate(a, self.fps if period < 10 else M.FPS_LOW_POWER)              # a slow turn needs few frames
        layer.addAnimation_forKey_(a, "spin")

    def _breathe(self, period: float) -> None:
        lo, hi = BREATHE
        cur = self._now(self.core, "transform.scale.x", 1.0)
        self.core.removeAnimationForKey_("breathe")
        self.aura.removeAnimationForKey_("breathe")
        if period <= 0:
            if M.changed(cur, 1.0):                  # settle back to rest
                a = Quartz.CABasicAnimation.animationWithKeyPath_("transform.scale")
                a.setFromValue_(cur)
                a.setToValue_(1.0)
                a.setDuration_(M.STATE_S)
                a.setTimingFunction_(state_ease())
                self.core.addAnimation_forKey_(a, "breathe")
            return
        t0 = Quartz.CACurrentMediaTime() - M.sine_phase(cur, lo, hi) * period    # carry on from where it was
        for layer, key, values in ((self.core, "transform.scale", M.sine_values(lo, hi)),
                                   (self.aura, "transform.scale", M.sine_values(0.94, 1.06))):
            a = Quartz.CAKeyframeAnimation.animationWithKeyPath_(key)
            a.setValues_(values)
            a.setDuration_(period)
            a.setRepeatCount_(1e9)
            a.setBeginTime_(t0)
            frame_rate(a, self.fps if period < 2 else M.FPS_LOW_POWER)           # a slow breath needs few frames
            layer.addAnimation_forKey_(a, "breathe")

    def _wave(self, period: float) -> None:
        """Thinking: the same swell on every tick, each started a little later, so a wave runs round the ring."""
        if period > 0:
            t0 = Quartz.CACurrentMediaTime() - period
            values = M.sine_values(1.0, 1.0 + 0.8 * (M.TICK_MAX / M.TICK_LEN - 1.0), 12)
            for i, tk in enumerate(self.ticks):
                a = Quartz.CAKeyframeAnimation.animationWithKeyPath_("transform.scale.y")
                a.setValues_(values)
                a.setDuration_(period)
                a.setRepeatCount_(1e9)
                a.setBeginTime_(t0 + M.tick_delay(i, period))
                frame_rate(a, self.fps)
                tk.addAnimation_forKey_(a, "wave")
            self.waving = True
        elif self.waving:                            # each tick eases down from wherever the wave left it
            self.waving = False
            for tk in self.ticks:
                off = self._now(tk, "transform.scale.y", 1.0) - 1.0
                a = Quartz.CABasicAnimation.animationWithKeyPath_("transform.scale.y")
                a.setAdditive_(True)
                a.setFromValue_(off)
                a.setToValue_(0.0)
                a.setDuration_(M.STATE_S)
                a.setTimingFunction_(state_ease())
                tk.addAnimation_forKey_(a, "wave")

    def set_level(self, v: float, now: float | None = None, force: bool = False, secs: float = 0.0) -> None:
        """0..1 level → tick lengths (a wave travelling round the ring) + core size and bloom.
        Reduce Motion: brightness instead of size. secs > 0 = a state cross-fade."""
        look = self.look
        if self.style == "knot":
            return self._knot_level(v, force, secs)
        a = min(1.0, max(0.0, v * look.gain))
        if self.acc.reduce_motion:
            b = 0.45 + 0.55 * a if look.source else 1.0
            if force or M.changed(b, self.bright):
                Quartz.CATransaction.begin()
                Quartz.CATransaction.setDisableActions_(True)
                self.tickring.setOpacity_(look.ticks * b)
                self.bloom.setOpacity_(a)
                Quartz.CATransaction.commit()
                self.bright = b
            return
        scales = M.tick_scales(v, time.monotonic() if now is None else now, look.gain)
        cs = M.core_scale(v, look.gain)
        if not force and not M.changed(cs, self.cs) and not M.changed_any(scales, self.scales):
            return                                   # nothing visible changed: no commit, no WindowServer work
        Quartz.CATransaction.begin()
        if secs > 0:
            Quartz.CATransaction.setAnimationDuration_(secs)
            Quartz.CATransaction.setAnimationTimingFunction_(state_ease())
        else:                                        # a plain step: no implicit animation objects per frame
            Quartz.CATransaction.setDisableActions_(True)
        for tk, s, old in zip(self.ticks, scales, self.scales):
            if s != old or force:
                tk.setAffineTransform_((1.0, 0.0, 0.0, s, 0.0, 0.0))     # a tick only ever stretches along its length
        if cs != self.cs or force:
            self.hold.setAffineTransform_((cs, 0.0, 0.0, cs, 0.0, 0.0))
            self.bloom.setOpacity_(a)
        Quartz.CATransaction.commit()
        self.scales, self.cs = scales, cs

    def set_dim(self, on: bool) -> None:
        """Pointer over the click-through orb → fade to 35 % so it never hides what's under it."""
        if on == self.dim or not self.visible:
            return
        self.dim = on
        fade(self.panel, 0.35 if on else 1.0, 0.2)

    def contains_pointer(self) -> bool:
        if not self.visible:
            return False
        p, f = AppKit.NSEvent.mouseLocation(), self.panel.frame()
        return M.in_orb(p.x - f.origin.x - M.HALO, p.y - f.origin.y - M.HALO, f.size.width - 2 * M.HALO)

    # ---------------------------------------------------------------- capsule: "Checking calendar" / "✓ Start resume · 4 PM"
    def expand(self, sym_name: str, text: str, tint=None) -> None:
        """The disc grows to the right into a capsule; the orb stays as its round left end."""
        set_text(self.text, text, F_LABEL(), ns(M.WHITE, text_alpha(M.TEXT_A, self.acc)))
        self.text.sizeToFit()
        tw, th = self.text.frame().size.width, self.text.frame().size.height
        w = M.capsule_width(tw, symbol=self.sym is not None)
        x = M.ORB + M.CAP_GAP
        if self.sym is not None:
            set_symbol(self.sym, sym_name, ns(tint or M.ACCENT), animate=not self.acc.reduce_motion and self.visible)
            self.sym.setFrame_(((x, (M.ORB - 20) / 2), (20, 20)))
            x += M.CAP_SYM
        self.text.setFrame_(((x, (M.ORB - th) / 2), (max(10.0, w - x - M.CAP_PAD + 2), th)))
        self.expanded = True
        self._resize(w)
        self._fade_views(1.0, True)

    def collapse(self, animate: bool = True) -> None:
        if not self.expanded:
            return
        self.expanded = False
        self._fade_views(0.0, animate)
        self._resize(M.ORB, animate)

    def _fade_views(self, alpha: float, animate: bool) -> None:
        AppKit.NSAnimationContext.beginGrouping()
        ctx = AppKit.NSAnimationContext.currentContext()
        ctx.setDuration_((M.MORPH_S if alpha else M.LABEL_S) if animate else 0.0)   # in with the capsule, out fast
        ctx.setTimingFunction_(state_ease())
        for v in (self.sym, self.text):
            if v is not None:
                (v.animator() if animate else v).setAlphaValue_(alpha)
        AppKit.NSAnimationContext.endGrouping()

    def _resize(self, w: float, animate: bool = True) -> None:
        if w == self.w:
            return
        self.w = w
        if self.anchor is None:
            return
        if self.visible and animate and not self.acc.reduce_motion:
            animate_frame(self.panel, self.frame_for(w), None, M.MORPH_S, ease(M.MORPH_EASE))
        else:
            self.panel.setFrame_display_(self.frame_for(w), self.visible)

    def close(self) -> None:
        self.gen += 1
        self._still()
        self.panel.orderOut_(None)
