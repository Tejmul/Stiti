"""Pure logic of the desktop overlay (no AppKit): states, looks, level smoothing, orb geometry, card layout,
dismiss timing.

Everything here is plain Python so it can be unit-tested headless (tests/overlay_eval.py). The AppKit side
(orb.py, card.py, ui.py) only *draws* what these objects decide. Design: docs/research/desktop_overlay.md, D26, D44.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, replace

# ---------------------------------------------------------------- palette (always dark: it sits over any window)
DISC = (0x0A, 0x0F, 0x24)         # the orb's disc, navy #0a0f24
CARD = (0x0B, 0x10, 0x26)         # card panel, navy #0b1026
BLUE = (0x46, 0x56, 0xD6)         # #4656d6
MID = (0x62, 0x84, 0xE3)          # between blue and sky
SKY = (0x7F, 0xB2, 0xF0)          # #7fb2f0
WHITE = (0xFF, 0xFF, 0xFF)
AMBER = (0xB4, 0x53, 0x1F)        # offline / error only
DISC_A, CARD_A = 0.94, 1.0        # solid: at 96 % a page of white text behind a card was still readable through it
TEXT_A, ROW_A, META_A = 0.96, 0.90, 0.50      # white: titles / rows / meta
HAIR_A, BEAM_A = 0.30, 0.95       # SKY hairline border; the bright beam on a card's top edge
SEP_A, HOVER_A = 0.07, 0.06       # white: row separators, hover wash

# ---------------------------------------------------------------- geometry (points)
ORB = 64.0                        # the disc's diameter
HALO = 8.0                        # room around the disc inside its panel for the glow
ORB_MAX_W = 340.0                 # widest capsule ("Checking calendar" / "✓ Start resume · today, 4 PM")
R_CORE, R_INNER, R_MID, R_TICK, R_OUTER = 7.0, 13.0, 18.0, 21.5, 28.5    # radii, centre outward
INNER_ARCS, INNER_ARC_DEG = 3, 80.0                      # inner ring: three arc segments
MID_DASHES = 24                                          # mid ring: dashes around the circle
N_TICKS, TICK_W, TICK_LEN, TICK_MAX = 36, 1.4, 2.4, 4.6  # tick ring: a circular equaliser (rest → loudest length)
OUTER_ARC_DEG = 300.0                                    # outer arc, its gap points down at the card
TOP_GAP = 8.0                                            # under the menu bar
CARD_GAP = 10.0                                          # card drops this far below the orb
FPS = 30.0
FPS_LOW_POWER = 15.0

# ---------------------------------------------------------------- states
STATES = ("hidden", "idle", "listening", "thinking", "speaking")
DOING_LABELS = {"calendar": ("calendar", "Checking calendar"), "mail": ("envelope", "Checking mail"),
                "plan": ("list.bullet", "Planning your day"), "web": ("globe", "Looking it up"),
                "tools": ("wrench.and.screwdriver", "Working on it")}


@dataclass(frozen=True)
class Look:
    """What the orb should look like in a state (decided here, drawn by orb.py). Periods are seconds, 0 = off."""
    visible: bool
    timer: bool            # needs the 30 Hz level timer (mic / voice reactive)
    source: str | None     # "mic" | "out" | None: which level drives the ticks + core
    click_through: bool    # True: clicks pass to the window underneath
    glow: float = 0.0      # outer glow strength 0..1
    rim: float = 0.0       # alpha of the SKY hairline rim
    ticks: float = 0.0     # opacity of the tick ring
    spin: float = 0.0      # inner ring: one clockwise turn takes this long
    counter: float = 0.0   # mid ring: one counter-clockwise turn
    breathe: float = 0.0   # core breathing period
    comet: float = 0.0     # the comet's lap around the outer arc
    wave: float = 0.0      # travelling wave on the ticks (render server, per-tick delays)
    gain: float = 0.0      # level → tick length / core size
    pulse: float = 0.0     # Reduce Motion only: a calm opacity pulse instead of the comet


LOOKS = {
    "hidden": Look(False, False, None, True),
    "idle": Look(True, False, None, True, glow=0.30, rim=0.28, ticks=0.32, spin=14.0, counter=30.0, breathe=3.0),
    "listening": Look(True, True, "mic", True, glow=0.55, rim=0.40, ticks=0.80, spin=6.0, counter=16.0, breathe=2.4,
                      gain=1.0),
    "thinking": Look(True, False, None, False, glow=0.70, rim=0.46, ticks=0.85, spin=1.6, counter=5.0,   # click = stop her
                     breathe=0.8, comet=0.9, wave=0.9),
    "speaking": Look(True, True, "out", False, glow=0.95, rim=0.55, ticks=1.0, spin=3.5, counter=9.0,    # click = stop her
                     gain=1.3),
}


def look_for(state: str, reduce_motion: bool = False) -> Look:
    """The look to draw. Reduce Motion: nothing rotates or travels: static rings, level + opacity only."""
    look = LOOKS[state]
    if not reduce_motion:
        return look
    return replace(look, spin=0.0, counter=0.0, breathe=0.0, comet=0.0, wave=0.0, pulse=1.8 if look.comet else 0.0)


@dataclass
class Transition:
    prev: str
    new: str
    show: bool             # panel goes hidden → visible (wake bloom)
    hide: bool             # visible → hidden (fade out, close the card)
    look: Look
    detail: str | None = None


class OrbState:
    """The orb's state machine. Unknown states are refused; repeated states are no-ops (cheap to call often)."""

    def __init__(self):
        self.state = "hidden"
        self.detail: str | None = None

    def apply(self, new: str, detail: str | None = None) -> Transition | None:
        if new not in LOOKS:
            raise ValueError(f"unknown overlay state {new!r}")
        prev = self.state
        if new == "thinking":
            d = detail
        elif new == "speaking":            # "Checking calendar" stays while she says it and the answer (same turn)
            d = detail or (self.detail if prev in ("thinking", "speaking") else None)
        else:
            d = None
        if new == prev and d == self.detail:
            return None
        self.state, self.detail = new, d
        was, now = LOOKS[prev].visible, LOOKS[new].visible
        return Transition(prev, new, show=now and not was, hide=was and not now, look=LOOKS[new], detail=self.detail)


def doing_label(kind: str | None) -> tuple[str, str] | None:
    """SF Symbol + 2–3 word label while she does something slow (on_ack kinds)."""
    return DOING_LABELS.get(kind or "")


# ---------------------------------------------------------------- level meter (Wispr Flow's level path, our numbers)
class LevelMeter:
    """RMS (per 40 ms block) → 0..1 level (tick length, core size). Behaviour learnt from Wispr Flow's bar (docs/research/re_wispr_flow.md §1):
    dBFS → adaptive floor (starts −60 dB, follows the quietest level heard, creeps up slowly) with a 20 dB range →
    150 ms average → frame-rate-independent smoothing 0.85^(dt/16.7 ms) → slew limit 1.6/s → 0.01 steps.
    Floats + a tiny window only; called from the 30 Hz main-thread tick, never from the audio callback."""

    RANGE_DB, AVG_S, POLE, POLE_DT, SLEW, RISE_DB_S = 20.0, 0.15, 0.85, 1 / 60, 1.6, 0.5

    def __init__(self, floor_min: float = -75.0, floor_max: float = -35.0, floor0: float = -60.0):
        self.floor_min, self.floor_max, self.floor0 = floor_min, floor_max, floor0
        self.reset()

    def reset(self) -> None:
        self.floor = min(self.floor_max, max(self.floor_min, self.floor0))
        self.value = 0.0
        self._win: list[tuple[float, float]] = []
        self._t: float | None = None

    @staticmethod
    def db(rms: float) -> float:
        return 20.0 * math.log10(rms + 1e-10) if rms > 0 else -200.0      # NaN / negative → silence

    def target(self, rms: float) -> float:
        return min(1.0, max(0.0, (self.db(rms) - self.floor) / self.RANGE_DB))

    def step(self, rms: float, now: float) -> float:
        dt = 1 / 30 if self._t is None else min(0.25, max(0.0, now - self._t))
        self._t = now
        d = self.db(rms)
        if d < self.floor:                                   # the quietest level heard is the floor …
            self.floor = max(self.floor_min, d)
        else:                                                # … which creeps up slowly in a noisier room
            self.floor = min(self.floor_max, self.floor + self.RISE_DB_S * dt, d)
        self._win.append((now, self.target(rms)))
        while self._win and self._win[0][0] < now - self.AVG_S:
            self._win.pop(0)
        tgt = sum(v for _, v in self._win) / len(self._win)
        a = self.POLE ** (dt / self.POLE_DT)
        v = self.value * a + tgt * (1 - a)
        lim = self.SLEW * dt
        v = self.value + max(-lim, min(lim, v - self.value))
        v = tgt if abs(v - tgt) < 0.01 else round(v, 2)      # 0.01 steps, and it really reaches 0 (timer can idle)
        self.value = v
        return v


METER = {"mic": dict(floor_min=-75.0, floor_max=-35.0),      # his AEC-cleaned mic: room noise is the floor
         "out": dict(floor_min=-40.0, floor_max=-25.0)}      # her TTS is digital silence between words


# ---------------------------------------------------------------- the orb's moving parts (pure maths)
WAVES = 3                    # crests around the tick ring
WAVE_HZ = 1.1                # a tick swells and falls this often while a level drives it
CORE_SWELL = 0.6             # the core grows 1.0 → 1.6 with the level


def tick_angle(i: int, n: int = N_TICKS) -> float:
    """Radians clockwise from 12 o'clock."""
    return 2 * math.pi * i / n


def tick_phase(i: int, n: int = N_TICKS, waves: int = WAVES) -> float:
    """Where tick i is in the wave's cycle (0..1). It rises with i, so the crests travel clockwise."""
    return (waves * i / n) % 1.0


def tick_scales(level: float, t: float, gain: float = 1.0, n: int = N_TICKS) -> list[float]:
    """Length of each tick (× its rest length) at time t: the level sets how far, the per-tick phase makes a wave
    travel around the circle. Silence = every tick at rest, exactly 1.0 (nothing to commit)."""
    a = min(1.0, max(0.0, level * gain))
    if a <= 0.0:
        return [1.0] * n
    top = TICK_MAX / TICK_LEN - 1.0
    return [round(1.0 + a * top * (0.3 + 0.7 * (0.5 + 0.5 * math.sin(2 * math.pi * (WAVE_HZ * t - tick_phase(i, n))))), 2)
            for i in range(n)]


def tick_delay(i: int, period: float, n: int = N_TICKS, waves: int = WAVES) -> float:
    """Thinking: every tick plays the same render-server loop, started this much later than tick 0."""
    return period * tick_phase(i, n, waves)


def core_scale(level: float, gain: float = 1.0) -> float:
    return round(1.0 + CORE_SWELL * min(1.0, max(0.0, level * gain)), 2)


def sine_values(lo: float, hi: float, n: int = 24) -> list[float]:
    """One smooth lo → hi → lo cycle as n+1 keyframes (linear between them is smooth enough at this size)."""
    return [lo + (hi - lo) * (0.5 - 0.5 * math.cos(2 * math.pi * k / n)) for k in range(n + 1)]


def sine_phase(value: float, lo: float, hi: float) -> float:
    """Where in that cycle (0..0.5, rising half) the value sits: a new loop starts from where the old one was."""
    if hi <= lo:
        return 0.0
    x = min(1.0, max(0.0, (value - lo) / (hi - lo)))
    return math.acos(1.0 - 2.0 * x) / (2 * math.pi)


def dash_pattern(r: float, n: int = MID_DASHES, duty: float = 0.4) -> tuple[float, float]:
    """(dash, gap) so exactly n dashes fit the circle of radius r (no seam where the ring closes)."""
    period = 2 * math.pi * r / n
    return period * duty, period * (1 - duty)


STATE_S, STATE_EASE = 0.2, (0.16, 1.0, 0.3, 1.0)            # a state cross-fades in 200 ms, ease-out
LABEL_S = 0.12                                               # the capsule's label fades this fast
MORPH_S, MORPH_EASE = 0.25, (0.4, 0.0, 0.2, 1.0)             # disc ↔ capsule


def changed(a: float, b: float, eps: float = 0.01) -> bool:
    """Skip a Core Animation commit when the value moved less than this (WindowServer cost)."""
    return abs(a - b) >= eps


def changed_any(a: list[float], b: list[float], eps: float = 0.01) -> bool:
    return len(a) != len(b) or any(abs(x - y) >= eps for x, y in zip(a, b))


# ---------------------------------------------------------------- shapes + displays (pure geometry)
def in_round_rect(x: float, y: float, w: float, h: float, r: float) -> bool:
    """Point inside a rounded rect (the orb's capsule / a card). Outside = transparent corner = not ours."""
    if not (0 <= x <= w and 0 <= y <= h):
        return False
    r = min(r, w / 2, h / 2)
    cx, cy = min(max(x, r), w - r), min(max(y, r), h - r)
    return (x - cx) ** 2 + (y - cy) ** 2 <= r * r + 1e-6


def screen_index(frames: list[tuple[float, float, float, float]], p: tuple[float, float]) -> int:
    """The display under the pointer, else the nearest one (frames as x, y, w, h)."""
    best, bd = 0, float("inf")
    for i, (x, y, w, h) in enumerate(frames):
        dx = max(x - p[0], 0.0, p[0] - (x + w))
        dy = max(y - p[1], 0.0, p[1] - (y + h))
        d = dx * dx + dy * dy
        if d < bd:
            best, bd = i, d
    return best


FOLLOW_S = 0.4                                               # re-check the pointer's display while visible


def in_orb(x: float, y: float, w: float = ORB) -> bool:
    """Point inside the orb: a circle of diameter ORB, or the capsule of width w it morphs into (x, y from the
    shape's own corner, not the panel's: the glow around it is not clickable)."""
    return in_round_rect(x, y, max(w, ORB), ORB, ORB / 2)


# ---------------------------------------------------------------- capsule width (doing / confirmation)
CAP_GAP, CAP_SYM, CAP_PAD = 6.0, 24.0, 24.0                  # orb | gap | icon | label | right padding


def capsule_width(label_w: float, *, symbol: bool = True) -> float:
    """The disc alone is ORB wide; with a label it grows to the right to fit it, up to ORB_MAX_W."""
    if label_w <= 0:
        return ORB
    return max(ORB, min(ORB_MAX_W, math.ceil(ORB + CAP_GAP + (CAP_SYM if symbol else 0) + label_w + CAP_PAD)))


def confirm_text(card: dict, max_chars: int = 38) -> str:
    """todo_added / reminder_set → "Start resume · today, 4 PM" (one line, from the brain's card data)."""
    it = (card.get("items") or [{}])[0]
    text = _clip(str(it.get("text") or card.get("title") or "Done"), max_chars)
    meta = str(it.get("meta") or "")
    if meta.startswith("due "):
        meta = meta[4:]
    return f"{text} · {meta}" if meta else text


def _clip(s: str, n: int) -> str:
    s = " ".join(s.split())
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


# ---------------------------------------------------------------- card layout
CARD_KINDS = ("todos", "reminders", "news")      # open a card
CONFIRM_KINDS = ("todo_added", "reminder_set")   # the orb widens into a one-line ✓ instead
MAX_ROWS = 6
CARD_W = {"news": 380.0}
CARD_W_DEFAULT = 380.0                           # every card is the same width: one column under the orb
CARD_RADIUS = 20.0
PAD, PAD_BOTTOM, EYEBROW_H, TITLE_H, ROW_H, MORE_H, EMPTY_H = 18.0, 12.0, 16.0, 26.0, 34.0, 24.0, 6.0
NEWS_ROW_H, NEWS_LINE_H = 48.0, 19.0             # a headline over its source; a second headline line adds NEWS_LINE_H
NEWS_LINE_CHARS = 42                             # headless guess of what fits on one line (card.py measures for real)
HEADER_GAP = 8.0
ROW_INSET, ROW_PAD, LEAD_W = 10.0, 8.0, 24.0     # row inside the card; content inside the row; checkbox / bell / 01 column


@dataclass
class Row:
    id: int | None
    text: str
    meta: str
    y: float               # top of the row, from the card's top (flipped coordinates)
    h: float
    tickable: bool
    done: bool = False
    op: str | None = None  # what this turn did to it: added | done | removed | set | cancelled | moved
    lines: int = 1         # news: a long headline wraps onto a second line


@dataclass
class CardLayout:
    kind: str
    eyebrow: str
    title: str
    width: float
    height: float
    rows: list[Row] = field(default_factory=list)
    more: int = 0          # "+N more" below the rows
    more_y: float = 0.0
    total: int = 0         # the count in the eyebrow

    @property
    def n(self) -> int:
        return len(self.rows)


def _count_from_title(title: str) -> int | None:
    w = title.split()
    return int(w[0]) if w and w[0].isdigit() else None


def headline_lines(text: str) -> int:
    return 1 if len(text) <= NEWS_LINE_CHARS else 2


def row_meta(kind: str, meta: str) -> str:
    """The eyebrow already says TO-DO, so "due today, 4 PM" is shown as "today, 4 PM" (shorter, never clipped)."""
    meta = " ".join(meta.split())
    return meta[4:] if kind == "todos" and meta.startswith("due ") else meta


def layout(card: dict, measure=None) -> CardLayout | None:
    """A card dict from cards.py → what to draw. None for kinds that don't open a card.
    measure(text) → 1 or 2: how many lines a headline really needs (card.py asks AppKit; headless we guess)."""
    kind = card.get("kind")
    if kind not in CARD_KINDS:
        return None
    items = [i for i in (card.get("items") or []) if isinstance(i, dict) and str(i.get("text") or "").strip()]
    title = _clip(str(card.get("title") or ""), 44)
    focus = card.get("focus") if isinstance(card.get("focus"), dict) else {}
    fop, fids = focus.get("op"), {i for i in (focus.get("ids") or []) if isinstance(i, int)}
    shown = items[:MAX_ROWS]
    leaving = sum(1 for it in items if fop in LEAVING and it.get("id") in fids)
    counted = _count_from_title(title)
    if counted is None and kind != "news" and items and not title.lower().startswith("nothing"):
        counted = len(items) - leaving
    # a row on its way out still counts until it leaves (the eyebrow ticks down as it collapses)
    total = (counted or 0) + leaving if counted is not None else len(items)
    eyebrow = eyebrow_text(kind, total)
    if kind == "todos" and shown:
        title = "You have these to complete"         # the owner's words; the count is in the eyebrow
    w = CARD_W.get(kind, CARD_W_DEFAULT)
    y = PAD + EYEBROW_H + TITLE_H + HEADER_GAP
    rows = []
    for it in shown:
        tid = it.get("id")
        text = _clip(str(it["text"]), 90 if kind == "news" else 60)
        lines = min(2, max(1, int((measure or headline_lines)(text)))) if kind == "news" else 1
        rh = NEWS_ROW_H + (lines - 1) * NEWS_LINE_H if kind == "news" else ROW_H
        rows.append(Row(tid if isinstance(tid, int) else None, text,
                        _clip(row_meta(kind, str(it.get("meta") or "")), 26), y, rh,
                        tickable=kind == "todos" and isinstance(tid, int),
                        op=fop if (fop and tid in fids) else None, lines=lines))
        y += rh
    more = max(0, total - len(shown))
    more_y = y
    if more:
        y += MORE_H
    return CardLayout(kind, eyebrow, title, w, _card_height(y, bool(rows)), rows, more, more_y, total)


def _card_height(y: float, has_rows: bool) -> float:
    """Rows carry their own air, so the card ends PAD_BOTTOM under the last one; a header-only card ends PAD under it."""
    return y + PAD_BOTTOM if has_rows else PAD + EYEBROW_H + TITLE_H + EMPTY_H + PAD


def eyebrow_text(kind: str, total: int) -> str:
    return {"todos": f"TO-DO · {total} OPEN" if total else "TO-DO",
            "reminders": f"REMINDERS · {total}" if total else "REMINDERS", "news": "HEADLINES"}.get(kind, "")


# ---------------------------------------------------------------- choreography (what the card plays)
LEAVING = ("done", "removed", "cancelled")       # struck through, then leave the list
ARRIVING = ("added", "set", "moved")             # slide in highlighted, then settle
ENTER_S, ENTER_STAGGER_S, ENTER_MAX_S = 0.26, 0.045, 0.25   # rows rise in one after another (≤ 250 ms of stagger)
LAND_S = 0.32                                    # the card's own drop (card.show)
STRIKE_AT_S, STRIKE_S, STRIKE_STAGGER_S = 0.55, 0.30, 0.14  # ✓ + the line drawn left → right
COLLAPSE_HOLD_S, COLLAPSE_S = 0.75, 0.30         # he sees it struck, then the row folds away and the rest close up
HIGHLIGHT_S = 1.6                                # an arriving row stays tinted this long


def choreography(lay: CardLayout, reduce_motion: bool = False) -> list[tuple[float, str, int]]:
    """(seconds after the card is shown, step, row index), sorted. Steps: enter | arrive | settle | strike | collapse.
    Reduce Motion: no slides — rows are just there; the strike and the removal still happen (they carry meaning)."""
    steps: list[tuple[float, str, int]] = []
    n = lay.n
    stagger = min(ENTER_STAGGER_S, ENTER_MAX_S / max(n - 1, 1))
    for i, r in enumerate(lay.rows):
        t = 0.0 if reduce_motion else LAND_S * 0.4 + i * stagger
        if not reduce_motion:
            steps.append((t, "enter", i))
        if r.op in ARRIVING:
            steps.append((t + (0.0 if reduce_motion else ENTER_S * 0.6), "arrive", i))
            steps.append((t + HIGHLIGHT_S, "settle", i))
    leaving = [i for i, r in enumerate(lay.rows) if r.op in LEAVING]
    for k, i in enumerate(leaving):
        steps.append((STRIKE_AT_S + k * STRIKE_STAGGER_S, "strike", i))
    if leaving:                                  # all of them fold together, after the last one is struck
        t = STRIKE_AT_S + (len(leaving) - 1) * STRIKE_STAGGER_S + STRIKE_S + COLLAPSE_HOLD_S
        steps += [(t, "collapse", i) for i in leaving]
    return sorted(steps, key=lambda s: (s[0], s[2]))


def collapse(lay: CardLayout, gone: set[int]) -> CardLayout:
    """The card after rows `gone` (indices into lay.rows) folded away: rows below move up, the card gets shorter,
    the eyebrow counts down. lay.rows keeps every row (indices stay stable); gone rows keep their old y."""
    y = PAD + EYEBROW_H + TITLE_H + HEADER_GAP
    rows = []
    for i, r in enumerate(lay.rows):
        if i in gone:
            rows.append(replace(r, h=0.0))
            continue
        rows.append(replace(r, y=y))
        y += r.h
    more_y = y
    if lay.more:
        y += MORE_H
    left = sum(1 for i in range(lay.n) if i not in gone)
    title = lay.title
    if not left and not lay.more:
        title = "All clear" if lay.kind == "todos" else "Nothing coming up"
    total = max(0, lay.total - sum(1 for i in gone if lay.rows[i].op in LEAVING))
    return CardLayout(lay.kind, eyebrow_text(lay.kind, total), title, lay.width, _card_height(y, bool(left or lay.more)),
                      rows, lay.more, more_y, total)


def row_at(lay: CardLayout, y: float) -> int | None:
    """Index of the row under a point (flipped y from the card top), for clicks."""
    for i, r in enumerate(lay.rows):
        if r.y <= y < r.y + r.h:
            return i
    return None


# ---------------------------------------------------------------- dismiss timing
MAX_CARD_S = 15.0          # after her speech ends, never longer than this
MAX_LIFETIME_S = 60.0      # failsafe if "speech ended" never arrives
HOVER_GRACE_S = 1.5        # after the pointer leaves, at least this long


def dismiss_after(kind: str, n_items: int) -> float:
    """Seconds after her speech ends: lists 4 s + 1.2 s per row (≤ 15 s), news 8 s, a confirmation 2.5 s."""
    if kind in CONFIRM_KINDS:
        return 2.5
    if kind == "news":
        return 8.0
    return min(MAX_CARD_S, 4.0 + 1.2 * n_items)


class DismissTimer:
    """When a card (or the orb's confirmation) goes away. The clock starts when her SPEECH ends, not when the card
    appears; hovering pauses it. `now` is passed in (monotonic seconds) so tests need no sleeping."""

    def __init__(self, kind: str, n_items: int, now: float, speaking: bool = True):
        self.secs = dismiss_after(kind, n_items)
        self.shown = now
        self.deadline: float | None = None
        self.hovering = False
        self._left: float | None = None
        if not speaking:
            self.speech_ended(now)

    def speech_ended(self, now: float) -> None:
        if self.deadline is None and self._left is None:
            if self.hovering:
                self._left = self.secs
            else:
                self.deadline = now + self.secs

    def hover(self, on: bool, now: float) -> None:
        if on == self.hovering:
            return
        self.hovering = on
        if on and self.deadline is not None:
            self._left, self.deadline = max(0.0, self.deadline - now), None
        elif not on and self._left is not None:
            self.deadline, self._left = now + max(self._left, HOVER_GRACE_S), None

    def due(self, now: float) -> bool:
        if self.hovering:
            return False
        if self.deadline is not None:
            return now >= self.deadline
        return now - self.shown >= MAX_LIFETIME_S

    def remaining(self, now: float) -> float | None:
        return None if self.deadline is None else max(0.0, self.deadline - now)
