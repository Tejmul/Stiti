"""Shared AppKit pieces: colours, accessibility settings, the non-activating panel recipe, the glass surface.

Main thread only. Gotchas from the research prototypes (docs/research/desktop_overlay.md):
- setFloatingPanel_(True) resets the level to 3, so the status level is set AFTER it;
- borderless + NonactivatingPanel + orderFrontRegardless never activates Stiti or steals his keyboard;
- glass is a real NSGlassEffectView (macOS 26), NSVisualEffectView before that, solid paper under Reduce Transparency.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

import AppKit
import Quartz
from Foundation import NSProcessInfo

from . import model as M


def cg(c: tuple[int, int, int], a: float = 1.0):
    return Quartz.CGColorCreateGenericRGB(c[0] / 255, c[1] / 255, c[2] / 255, a)


def ns(c: tuple[int, int, int], a: float = 1.0):
    return AppKit.NSColor.colorWithSRGBRed_green_blue_alpha_(c[0] / 255, c[1] / 255, c[2] / 255, a)


@dataclass
class Access:
    reduce_motion: bool = False
    reduce_transparency: bool = False
    increase_contrast: bool = False
    low_power: bool = False

    @classmethod
    def read(cls) -> "Access":
        ws = AppKit.NSWorkspace.sharedWorkspace()
        pi = NSProcessInfo.processInfo()
        return cls(bool(ws.accessibilityDisplayShouldReduceMotion()),
                   bool(ws.accessibilityDisplayShouldReduceTransparency()),
                   bool(ws.accessibilityDisplayShouldIncreaseContrast()),
                   bool(pi.isLowPowerModeEnabled()) if hasattr(pi, "isLowPowerModeEnabled") else False)


def panel_level() -> int:
    """Status-bar level (25) by default. STITI_OVERLAY_LEVEL=screensaver uses 1000, Wispr Flow's choice, in case
    status level ends up under full-screen video (untested with a display on, see D26)."""
    if os.getenv("STITI_OVERLAY_LEVEL", "status") == "screensaver":
        return AppKit.NSScreenSaverWindowLevel
    return AppKit.NSStatusWindowLevel


def make_panel(cls, w: float, h: float):
    """A borderless, non-activating panel at status-bar level that floats over every Space and full-screen app."""
    p = cls.alloc().initWithContentRect_styleMask_backing_defer_(
        ((0, 0), (w, h)), AppKit.NSWindowStyleMaskBorderless | AppKit.NSWindowStyleMaskNonactivatingPanel,
        AppKit.NSBackingStoreBuffered, False)
    p.setFloatingPanel_(True)                        # resets the level to 3 (floating) …
    p.setLevel_(panel_level())                       # … so our level goes AFTER it
    p.setCollectionBehavior_(AppKit.NSWindowCollectionBehaviorCanJoinAllSpaces
                             | AppKit.NSWindowCollectionBehaviorFullScreenAuxiliary
                             | AppKit.NSWindowCollectionBehaviorStationary
                             | AppKit.NSWindowCollectionBehaviorIgnoresCycle)
    p.setOpaque_(False)
    p.setBackgroundColor_(AppKit.NSColor.clearColor())
    p.setHasShadow_(True)
    p.setHidesOnDeactivate_(False)
    p.setReleasedWhenClosed_(False)
    p.setMovable_(False)
    p.setSharingType_(AppKit.NSWindowSharingNone)   # his to-dos stay out of screen shares / recordings
    p.setAlphaValue_(0.0)
    return p


def make_surface(w: float, h: float, radius: float, acc: Access, host_cls=None):
    """(outer view for the panel, host view to draw into). White liquid glass, or the fallbacks."""
    host_cls = host_cls or AppKit.NSView
    frame = ((0, 0), (w, h))
    flex = AppKit.NSViewWidthSizable | AppKit.NSViewHeightSizable
    host = host_cls.alloc().initWithFrame_(frame)
    host.setWantsLayer_(True)
    host.setAutoresizingMask_(flex)
    if acc.reduce_transparency:
        outer = AppKit.NSView.alloc().initWithFrame_(frame)
        outer.setWantsLayer_(True)
        outer.layer().setBackgroundColor_(cg(M.PAPER, 0.98))
        outer.layer().setCornerRadius_(radius)
        outer.addSubview_(host)
    elif hasattr(AppKit, "NSGlassEffectView"):      # macOS 26 Liquid Glass
        outer = AppKit.NSGlassEffectView.alloc().initWithFrame_(frame)
        outer.setCornerRadius_(radius)
        outer.setTintColor_(AppKit.NSColor.colorWithWhite_alpha_(1.0, 0.55))
        outer.setContentView_(host)
    else:                                            # macOS < 26
        outer = AppKit.NSVisualEffectView.alloc().initWithFrame_(frame)
        outer.setMaterial_(AppKit.NSVisualEffectMaterialPopover)
        outer.setBlendingMode_(AppKit.NSVisualEffectBlendingModeBehindWindow)
        outer.setState_(AppKit.NSVisualEffectStateActive)
        outer.setWantsLayer_(True)
        outer.layer().setCornerRadius_(radius)
        outer.layer().setMasksToBounds_(True)
        outer.addSubview_(host)
    outer.setAutoresizingMask_(flex)
    if acc.increase_contrast:
        host.layer().setBorderWidth_(1.0)
        host.layer().setBorderColor_(cg(M.NAVY, 0.9))
        host.layer().setCornerRadius_(radius)
    return outer, host


def label(text: str, font, colour, *, kern: float | None = None, strike: bool = False):
    f = AppKit.NSTextField.labelWithString_("")
    set_text(f, text, font, colour, kern=kern, strike=strike)
    f.setLineBreakMode_(AppKit.NSLineBreakByTruncatingTail)
    f.setMaximumNumberOfLines_(1)
    f.setSelectable_(False)
    return f


def set_text(f, text: str, font, colour, *, kern: float | None = None, strike: bool = False) -> None:
    attrs = {AppKit.NSFontAttributeName: font, AppKit.NSForegroundColorAttributeName: colour}
    if kern:
        attrs[AppKit.NSKernAttributeName] = kern
    if strike:
        attrs[AppKit.NSStrikethroughStyleAttributeName] = AppKit.NSUnderlineStyleSingle
    para = AppKit.NSMutableParagraphStyle.alloc().init()
    para.setLineBreakMode_(AppKit.NSLineBreakByTruncatingTail)
    attrs[AppKit.NSParagraphStyleAttributeName] = para
    f.setAttributedStringValue_(AppKit.NSAttributedString.alloc().initWithString_attributes_(text, attrs))


def symbol(name: str, size: float, colour, weight=None):
    img = AppKit.NSImage.imageWithSystemSymbolName_accessibilityDescription_(name, None)
    if img is None:
        return None
    cfg = AppKit.NSImageSymbolConfiguration.configurationWithPointSize_weight_(
        size, weight if weight is not None else AppKit.NSFontWeightMedium)
    img = img.imageWithSymbolConfiguration_(cfg) or img
    iv = AppKit.NSImageView.imageViewWithImage_(img)
    iv.setContentTintColor_(colour)
    return iv


def set_symbol(iv, name: str, colour, animate: bool) -> None:
    img = AppKit.NSImage.imageWithSystemSymbolName_accessibilityDescription_(name, None)
    if img is None or iv is None:
        return
    cur = iv.image()
    if cur is not None and cur.symbolConfiguration() is not None:
        img = img.imageWithSymbolConfiguration_(cur.symbolConfiguration()) or img
    iv.setContentTintColor_(colour)
    if animate and hasattr(iv, "setSymbolImage_withContentTransition_"):
        iv.setSymbolImage_withContentTransition_(img, AppKit.NSSymbolReplaceContentTransition.transition())
    else:
        iv.setImage_(img)
    if animate and hasattr(iv, "addSymbolEffect_"):
        try:
            iv.addSymbolEffect_(AppKit.NSSymbolBounceEffect.effect())
        except Exception:
            pass


def fade(window, alpha: float, secs: float, timing=None) -> None:
    AppKit.NSAnimationContext.beginGrouping()
    ctx = AppKit.NSAnimationContext.currentContext()
    ctx.setDuration_(secs)
    ctx.setTimingFunction_(timing or Quartz.CAMediaTimingFunction.functionWithName_(Quartz.kCAMediaTimingFunctionEaseOut))
    window.animator().setAlphaValue_(alpha)
    AppKit.NSAnimationContext.endGrouping()


def animate_frame(window, frame, alpha: float | None, secs: float, timing=None) -> None:
    AppKit.NSAnimationContext.beginGrouping()
    ctx = AppKit.NSAnimationContext.currentContext()
    ctx.setDuration_(secs)
    ctx.setTimingFunction_(timing or Quartz.CAMediaTimingFunction.functionWithName_(Quartz.kCAMediaTimingFunctionEaseOut))
    window.animator().setFrame_display_(frame, True)
    if alpha is not None:
        window.animator().setAlphaValue_(alpha)
    AppKit.NSAnimationContext.endGrouping()


OUT_EASE = (0.16, 1.0, 0.3, 1.0)                     # the web's --out token


def ease(points=OUT_EASE):
    return Quartz.CAMediaTimingFunction.functionWithControlPoints____(*points)


def out_ease():
    return ease(OUT_EASE)


def state_ease():                                    # 100 ms state transitions
    return ease(M.STATE_EASE)


def frame_rate(anim, fps: float) -> None:
    if hasattr(anim, "setPreferredFrameRateRange_"):
        anim.setPreferredFrameRateRange_(Quartz.CAFrameRateRangeMake(min(15.0, fps), fps, fps))


def pointer_screen():
    """The display the mouse pointer is on (or nearest to): the pill follows him across displays."""
    screens = list(AppKit.NSScreen.screens() or [])
    if not screens:
        return AppKit.NSScreen.mainScreen()
    p = AppKit.NSEvent.mouseLocation()
    frames = [(f.origin.x, f.origin.y, f.size.width, f.size.height) for f in (s.frame() for s in screens)]
    return screens[M.screen_index(frames, (p.x, p.y))]


def screen_key(s) -> tuple:
    f = s.frame()
    return (f.origin.x, f.origin.y, f.size.width, f.size.height)


def screen_anchor(s=None) -> tuple[float, float]:
    """(centre x, top y) for the pill on a screen: under the menu bar, or hugging a notch."""
    s = s or pointer_screen()
    f, vf = s.frame(), s.visibleFrame()
    inset = s.safeAreaInsets().top if hasattr(s, "safeAreaInsets") else 0
    if inset and inset > 0:
        top = f.origin.y + f.size.height - inset
    else:
        top = vf.origin.y + vf.size.height
    return f.origin.x + f.size.width / 2, top


def screen_locked() -> bool:
    try:
        d = Quartz.CGSessionCopyCurrentDictionary()
        return bool(d and d.get("CGSSessionScreenIsLocked"))
    except Exception:
        return False
