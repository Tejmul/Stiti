"""Pure logic of the desktop overlay (no AppKit): states, level smoothing, card layout, dismiss timing.

Everything here is plain Python so it can be unit-tested headless (tests/overlay_eval.py). The AppKit side
(pill.py, card.py, ui.py) only *draws* what these objects decide. Design: docs/research/desktop_overlay.md, D26.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

# ---------------------------------------------------------------- palette (Stiti's look)
PAPER = (0xEC, 0xEB, 0xF2)        # lavender paper #ecebf2
NAVY = (0x26, 0x2B, 0x57)         # #262b57
BLUE = (0x46, 0x56, 0xD6)         # #4656d6
MID = (0x62, 0x84, 0xE3)          # between blue and sky
SKY = (0x7F, 0xB2, 0xF0)          # #7fb2f0
AMBER = (0xB4, 0x53, 0x1F)        # offline / error dot
DOT_COLOURS = [NAVY, BLUE, MID, SKY, MID, BLUE, NAVY]

# ---------------------------------------------------------------- geometry (points)
PILL_W, PILL_H, PILL_MAX_W = 168.0, 40.0, 320.0
N_DOTS, DOT, DOT_GAP = 7, 6.0, 7.0
DOTS_W = N_DOTS * DOT + (N_DOTS - 1) * DOT_GAP           # 84 pt
TOP_GAP = 8.0                                            # under the menu bar
CARD_GAP = 8.0                                           # card drops this far below the pill
FPS = 30.0
FPS_LOW_POWER = 15.0

# ---------------------------------------------------------------- states
STATES = ("hidden", "idle", "listening", "thinking", "speaking")
DOING_LABELS = {"calendar": ("calendar", "Checking calendar"), "mail": ("envelope", "Checking mail"),
                "plan": ("list.bullet", "Planning your day"), "web": ("globe", "Looking it up"),
                "tools": ("wrench.and.screwdriver", "Working on it")}


@dataclass(frozen=True)
class Look:
    """What the pill should look like in a state (decided here, drawn by pill.py)."""
    visible: bool
    timer: bool            # needs the 30 Hz level timer (mic / voice reactive)
    source: str | None     # "mic" | "out" | None: which level drives the dots
    anim: str | None       # render-server animation: "shimmer" | "wave" | None
    click_through: bool    # True: clicks pass to the window underneath


LOOKS = {
    "hidden": Look(False, False, None, None, True),
    "idle": Look(True, False, None, "shimmer", True),
    "listening": Look(True, True, "mic", "shimmer", True),
    "thinking": Look(True, False, None, "wave", False),     # click = stop her (detail → "Checking calendar")
    "speaking": Look(True, True, "out", None, False),       # click = stop her
}


@dataclass
class Transition:
    prev: str
    new: str
    show: bool             # panel goes hidden → visible (wake bloom)
    hide: bool             # visible → hidden (fade out, close the card)
    look: Look
    detail: str | None = None


class PillState:
    """The pill's state machine. Unknown states are refused; repeated states are no-ops (cheap to call often)."""

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
    """RMS (per 40 ms block) → 0..1 dot swell. Behaviour learnt from Wispr Flow's bar (docs/research/re_wispr_flow.md §1):
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


def bulge(i: int, n: int = N_DOTS) -> float:
    """Centre-bulge weight 1 − d²/48 (Wispr's 10 bars), d stretched so our 7 dots fall off like their 10."""
    d = abs(i - (n - 1) / 2) * (4.5 / ((n - 1) / 2))
    return 1.0 - d * d / 48.0


def dot_scales(level: float, n: int = N_DOTS, gain: float = 1.2) -> list[float]:
    """Round dots swell evenly (bars would squash the caps), the middle ones most."""
    return [1.0 + level * gain * bulge(i, n) for i in range(n)]


SHIMMER_KEYS = [1.0, 1.2, 1.5, 1.1, 1.3, 1.0]                # idle shimmer, 1 s loop
SHIMMER_TIMES = [0.0, 0.2, 0.4, 0.8, 0.9, 1.0]
SHIMMER_STAGGER = 0.1                                        # s per dot, from the centre outward


def shimmer(i: int, n: int = N_DOTS) -> tuple[list[float], float]:
    """Keyframe scales for dot i (bulge-weighted) and its start delay."""
    w = bulge(i, n)
    return [1.0 + (k - 1.0) * w for k in SHIMMER_KEYS], SHIMMER_STAGGER * abs(i - (n - 1) / 2)


STATE_S, STATE_EASE = 0.1, (0.05, 0.6, 0.4, 0.95)           # state transitions (Flow's default morph)
MORPH_S, MORPH_EASE = 0.25, (0.4, 0.0, 0.2, 1.0)             # larger morphs (pill width)


def changed(a: float, b: float, eps: float = 0.01) -> bool:
    """Skip a Core Animation commit when the swell moved less than this (WindowServer cost)."""
    return abs(a - b) >= eps


# ---------------------------------------------------------------- shapes + displays (pure geometry)
def in_round_rect(x: float, y: float, w: float, h: float, r: float) -> bool:
    """Point inside a rounded rect (the pill capsule / card). Outside = transparent corner = not ours."""
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


# ---------------------------------------------------------------- pill width (doing / confirmation)
def pill_width(label_w: float, *, with_dots: bool = True, symbol: bool = True) -> float:
    """Compact pill is 168 pt; with a label it widens to fit, up to 320 pt."""
    if label_w <= 0:
        return PILL_W
    w = 18 + (DOTS_W + 14 if with_dots else 0) + (22 if symbol else 0) + label_w + 20
    return max(PILL_W, min(PILL_MAX_W, math.ceil(w)))


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
CONFIRM_KINDS = ("todo_added", "reminder_set")   # widen the pill instead
MAX_ROWS = 6
CARD_W = {"news": 380.0}
CARD_W_DEFAULT = 360.0
PAD, EYEBROW_H, TITLE_H, ROW_H, NEWS_ROW_H, MORE_H, EMPTY_H = 16.0, 16.0, 26.0, 36.0, 46.0, 24.0, 8.0
HEADER_GAP = 10.0


@dataclass
class Row:
    id: int | None
    text: str
    meta: str
    y: float               # top of the row, from the card's top (flipped coordinates)
    h: float
    tickable: bool
    done: bool = False


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

    @property
    def n(self) -> int:
        return len(self.rows)


def _count_from_title(title: str) -> int | None:
    w = title.split()
    return int(w[0]) if w and w[0].isdigit() else None


def layout(card: dict) -> CardLayout | None:
    """A card dict from cards.py → what to draw. None for kinds that don't open a card."""
    kind = card.get("kind")
    if kind not in CARD_KINDS:
        return None
    items = [i for i in (card.get("items") or []) if isinstance(i, dict) and str(i.get("text") or "").strip()]
    title = _clip(str(card.get("title") or ""), 44)
    total = max(len(items), _count_from_title(title) or 0)
    shown = items[:MAX_ROWS]
    eyebrow = {"todos": f"TO-DO · {total} OPEN" if total else "TO-DO",
               "reminders": f"REMINDERS · {total}" if total else "REMINDERS", "news": "HEADLINES"}[kind]
    if kind == "todos" and shown:
        title = "You have these to complete"         # the owner's words; the count is in the eyebrow
    w = CARD_W.get(kind, CARD_W_DEFAULT)
    rh = NEWS_ROW_H if kind == "news" else ROW_H
    y = PAD + EYEBROW_H + TITLE_H + HEADER_GAP
    rows = []
    for it in shown:
        tid = it.get("id")
        rows.append(Row(tid if isinstance(tid, int) else None, _clip(str(it["text"]), 90 if kind == "news" else 60),
                        _clip(str(it.get("meta") or ""), 26), y, rh,
                        tickable=kind == "todos" and isinstance(tid, int)))
        y += rh
    more = max(0, total - len(shown))
    more_y = y
    if more:
        y += MORE_H
    if not rows:
        y = PAD + EYEBROW_H + TITLE_H + EMPTY_H
    return CardLayout(kind, eyebrow, title, w, y + PAD, rows, more, more_y)


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
    """When a card (or the pill's confirmation) goes away. The clock starts when her SPEECH ends, not when the card
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
