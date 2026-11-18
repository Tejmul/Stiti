"""Shared AppKit pieces: colours, accessibility settings, the non-activating panel recipe, the HUD surface.

Main thread only. Gotchas from the research prototypes (docs/research/desktop_overlay.md):
- setFloatingPanel_(True) resets the level to 3, so the status level is set AFTER it;
- borderless + NonactivatingPanel + orderFrontRegardless never activates Stiti or steals his keyboard;
- the surface is a solid dark navy layer (D44), not glass: see-through glass went muddy over whatever was behind it
  and the text lost contrast. Reduce Transparency makes it fully opaque, Increase Contrast brightens its border.
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
    if os.getenv("STITI_OVERLAY_DEMO_CAPTURE") != "1":   # set only by `overlay.demo --shots` (fake data)
        p.setSharingType_(AppKit.NSWindowSharingNone)   # his to-dos stay out of screen shares / recordings
    p.setAlphaValue_(0.0)
    return p


def surface_alpha(base: float, acc: Access) -> float:
    return 1.0 if acc.reduce_transparency else base


def hairline(acc: Access, alpha: float = M.HAIR_A):
    """The 1 pt SKY border of the orb and the cards (near-solid under Increase Contrast)."""
    return cg(M.SKY, 0.95 if acc.increase_contrast else alpha)


def text_alpha(base: float, acc: Access) -> float:
    """White text alphas (0.96 / 0.90 / 0.50): Increase Contrast lifts the dim ones."""
    return min(1.0, base + 0.25) if acc.increase_contrast else base


_SCALE: list[float] = []


def crisp(layer):
    """Shape / gradient layers are rasterised at contentsScale: use the sharpest display's (he may drag between)."""
    if not _SCALE:
        _SCALE.append(max([float(s.backingScaleFactor()) for s in (AppKit.NSScreen.screens() or [])] or [2.0]))
    layer.setContentsScale_(_SCALE[0])
    return layer


def still(layer, *keys):
    """No implicit animation for these properties (the layer follows its window / the level, frame by frame)."""
    layer.setActions_({k: AppKit.NSNull.null() for k in (keys or ("bounds", "position", "frame"))})
    return layer


def make_hud(w: float, h: float, radius: float, acc: Access, host_cls=None, alpha: float = M.CARD_A):
    """A card's surface: solid navy, continuous corners, SKY hairline. Returns the view to draw into (flipped or
    not is the host class's business)."""
    host = (host_cls or AppKit.NSView).alloc().initWithFrame_(((0, 0), (w, h)))
    host.setWantsLayer_(True)
    host.setAutoresizingMask_(AppKit.NSViewWidthSizable | AppKit.NSViewHeightSizable)
    lay = host.layer()
    lay.setBackgroundColor_(cg(M.CARD, surface_alpha(alpha, acc)))
    lay.setCornerRadius_(radius)
    if hasattr(lay, "setCornerCurve_"):
        lay.setCornerCurve_("continuous")
    lay.setBorderWidth_(1.0)
    lay.setBorderColor_(hairline(acc))
    lay.setMasksToBounds_(True)
    return host


def label(text: str, font, colour, *, kern: float | None = None, lines: int = 1):
    """A one-line label that truncates with an ellipsis (lines=2: wraps once, then truncates)."""
    f = AppKit.NSTextField.labelWithString_("")
    f.setSelectable_(False)
    f.setMaximumNumberOfLines_(lines)
    f.setLineBreakMode_(AppKit.NSLineBreakByWordWrapping if lines > 1 else AppKit.NSLineBreakByTruncatingTail)
    if lines > 1:
        f.cell().setWraps_(True)
        f.cell().setTruncatesLastVisibleLine_(True)
    set_text(f, text, font, colour, kern=kern, wrap=lines > 1)
    return f


def text_attrs(font, colour, *, kern: float | None = None, wrap: bool = False) -> dict:
    attrs = {AppKit.NSFontAttributeName: font, AppKit.NSForegroundColorAttributeName: colour}
    if kern:
        attrs[AppKit.NSKernAttributeName] = kern
    para = AppKit.NSMutableParagraphStyle.alloc().init()
    para.setLineBreakMode_(AppKit.NSLineBreakByWordWrapping if wrap else AppKit.NSLineBreakByTruncatingTail)
    attrs[AppKit.NSParagraphStyleAttributeName] = para
    return attrs


def set_text(f, text: str, font, colour, *, kern: float | None = None, wrap: bool = False) -> None:
    f.setAttributedStringValue_(AppKit.NSAttributedString.alloc().initWithString_attributes_(
        text, text_attrs(font, colour, kern=kern, wrap=wrap)))


def text_lines(text: str, font, width: float, most: int = 2) -> int:
    """How many lines the text needs at this width (1..most)."""
    s = AppKit.NSAttributedString.alloc().initWithString_attributes_(text, text_attrs(font, AppKit.NSColor.whiteColor(),
                                                                                     wrap=True))
    one = s.size().height or 1.0
    r = s.boundingRectWithSize_options_((width, 10000.0), AppKit.NSStringDrawingUsesLineFragmentOrigin)
    return max(1, min(most, int(r.size.height / one + 0.5)))


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


def state_ease():                                    # state cross-fades
    return ease(M.STATE_EASE)


def frame_rate(anim, fps: float) -> None:
    if hasattr(anim, "setPreferredFrameRateRange_"):
        anim.setPreferredFrameRateRange_(Quartz.CAFrameRateRangeMake(min(15.0, fps), fps, fps))


def pointer_screen():
    """The display the mouse pointer is on (or nearest to): the orb follows him across displays."""
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
    """(centre x, top y) for the orb on a screen: under the menu bar, or hugging a notch."""
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
