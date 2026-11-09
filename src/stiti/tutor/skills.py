"""Whiteboard skills: semantic board ops -> laid-out Excalidraw skeletons + animation actions.

The LLM (or a hand-written lesson) only says WHAT to draw and roughly WHERE ("box right_of sun",
"graph of these nodes", "underline atp"). This module owns every pixel (research: small models place
coordinates badly — TheoremExplainAgent, ChalkTalk), so layout is deterministic, testable and free.

Skills: title · text · bullet · box (rectangle/ellipse/diamond) · arrow · graph (layered layout,
wraps long chains) · table · formula · sticky note · highlight (underline/circle/marker/color/tick/
cross/pointer) · strike · erase · focus (camera) · new_page · Q&A side boards · parking lot · goal.
Animations (done in the browser): sketch (outline drawn on, then filled), grow (arrows/lines),
type (typewriter text), fade.

Board geometry: each lesson segment gets its own page (1600×900) laid left→right; questions open an
"aside" page under the current one, so the camera pans instead of wiping the board.
"""
from __future__ import annotations

import copy
import math
import re
import textwrap
from dataclasses import dataclass, field

from .lesson import Op

PAGE_W, PAGE_H, GAP = 1600, 900, 260
REGIONS = {  # relative to the page origin: x, y, w, h
    "title": (60, 34, 1060, 80), "goal": (1160, 40, 380, 60),
    "main": (60, 150, 1040, 610), "side": (1160, 150, 380, 520),
    "parking": (1160, 700, 380, 170), "notes": (60, 790, 1040, 80),
}
PALETTE = {  # stroke, background (Excalidraw's own palette)
    "plain": ("#1e1e1e", "#f8f9fa"), "warm": ("#e8590c", "#ffec99"), "green": ("#2f9e44", "#b2f2bb"),
    "blue": ("#1971c2", "#a5d8ff"), "red": ("#e03131", "#ffc9c9"), "violet": ("#6741d9", "#d0bfff"),
    "muted": ("#868e96", "#e9ecef"),
}
ACCENT, OK_GREEN = "#e03131", "#2f9e44"
CH = 0.58          # average glyph width / font size for Excalifont (layout estimate only)
HGAP, VGAP = 96, 70


@dataclass
class El:
    id: str
    kind: str                 # box | text | arrow | table | formula | sticky | deco | title
    x: float
    y: float
    w: float
    h: float
    frame: tuple[int, int]
    shape: str = "rectangle"
    region: str = "main"
    children: list[str] = field(default_factory=list)   # extra element ids (cells, formula text, title line)
    decos: list[str] = field(default_factory=list)      # highlight elements attached to this one

    @property
    def cx(self):
        return self.x + self.w / 2

    @property
    def cy(self):
        return self.y + self.h / 2

    @property
    def right(self):
        return self.x + self.w

    @property
    def bottom(self):
        return self.y + self.h


def text_size(text: str, fs: float) -> tuple[float, float]:
    lines = text.split("\n")
    return max(len(line) for line in lines) * fs * CH, len(lines) * fs * 1.25


def wrap(text: str, width: int) -> str:
    return "\n".join(textwrap.wrap(text, width=width, break_long_words=True)) or text


def _base(**kw) -> dict:
    d = {"strokeWidth": 2, "roughness": 1, "fillStyle": "solid", "strokeColor": "#1e1e1e",
         "backgroundColor": "transparent"}
    d.update(kw)
    return d


def border_point(e: El, tx: float, ty: float, pad: float = 6) -> tuple[float, float]:
    """Where the ray from e's centre towards (tx, ty) leaves e's outline."""
    dx, dy = tx - e.cx, ty - e.cy
    if dx == 0 and dy == 0:
        return e.cx, e.cy
    a, b = e.w / 2 + pad, e.h / 2 + pad
    if e.shape == "ellipse":
        s = 1 / math.sqrt((dx / a) ** 2 + (dy / b) ** 2)
    elif e.shape == "diamond":
        s = 1 / (abs(dx) / a + abs(dy) / b)
    else:
        s = min(a / abs(dx) if dx else math.inf, b / abs(dy) if dy else math.inf)
    return e.cx + dx * s, e.cy + dy * s


def layered_layout(nodes: list[dict], edges: list[dict], sizes: dict[str, tuple[float, float]],
                   direction: str, max_w: float, max_h: float) -> tuple[dict, str]:
    """Tiny Sugiyama: longest-path ranks (cycle edges ignored), barycentre ordering, LR/TB, and a
    'wrapped LR' (rows of ranks) when a long chain fits neither way. Returns ({id: (x, y)}, mode)."""
    ids = [n["id"] for n in nodes]
    succ: dict[str, list[str]] = {i: [] for i in ids}
    seen, stack, back = set(), set(), set()

    def dfs(u):
        seen.add(u)
        stack.add(u)
        for e in edges:
            if e["from"] == u:
                v = e["to"]
                if v in stack:
                    back.add((u, v))
                elif v not in seen:
                    dfs(v)
        stack.discard(u)
    for i in ids:
        if i not in seen:
            dfs(i)
    for e in edges:
        if (e["from"], e["to"]) not in back and e["from"] != e["to"]:
            succ[e["from"]].append(e["to"])
    rank = {i: 0 for i in ids}
    for _ in ids:                                   # relax (graph ≤ 8 nodes)
        for u in ids:
            for v in succ[u]:
                rank[v] = max(rank[v], rank[u] + 1)
    parents = {v: [u for u in ids if v in succ[u]] for v in ids}
    nr = max(rank.values()) + 1
    layers = [[i for i in ids if rank[i] == r] for r in range(nr)]
    for r in range(1, nr):                          # barycentre ordering
        prev = {v: k for k, v in enumerate(layers[r - 1])}
        def bary(v):
            ps = [prev[u] for u in ids if v in succ[u] and u in prev]
            return sum(ps) / len(ps) if ps else 1e9
        layers[r].sort(key=bary)

    def place(mode: str, per_row: int = 0) -> tuple[dict, float, float]:
        pos, rgap, ngap = {}, 110, 46
        if mode == "TB":                            # children centred under their parents (trees read right)
            y, cx = 0.0, {}
            for r, L in enumerate(layers):
                lh = max(sizes[i][1] for i in L)
                want = []
                for k, i in enumerate(L):
                    ps = [cx[u] for u in parents[i] if u in cx]
                    want.append((sum(ps) / len(ps) if ps else (want[-1][0] + 1 if want else 0), k, i))
                want.sort()
                xs, prev_right = [], -math.inf
                for c, _, i in want:
                    x = max(c - sizes[i][0] / 2, prev_right + ngap)
                    xs.append((i, x))
                    prev_right = x + sizes[i][0]
                if r and want:                      # shift the layer back so it stays balanced under parents
                    shift = sum(c - (x + sizes[i][0] / 2) for (c, _, i), (_, x) in zip(want, xs)) / len(xs)
                    xs = [(i, x + shift) for i, x in xs]
                for i, x in xs:
                    pos[i] = (x, y + (lh - sizes[i][1]) / 2)
                    cx[i] = x + sizes[i][0] / 2
                y += lh + rgap * 0.75
            x0 = min(p[0] for p in pos.values())
            pos = {i: (p[0] - x0, p[1]) for i, p in pos.items()}
            W = max(pos[i][0] + sizes[i][0] for i in pos)
            return pos, W, y - rgap * 0.75
        rows = [layers[k:k + per_row] for k in range(0, nr, per_row)] if per_row else [layers]
        y0, W = 0.0, 0.0
        for row in rows:
            heights = [sum(sizes[i][1] for i in L) + ngap * (len(L) - 1) for L in row]
            H = max(heights)
            x = 0.0
            for L, lh in zip(row, heights):
                y = y0 + (H - lh) / 2
                lw = max(sizes[i][0] for i in L)
                for i in L:
                    pos[i] = (x + (lw - sizes[i][0]) / 2, y)
                    y += sizes[i][1] + ngap
                x += lw + rgap
            W = max(W, x - rgap)
            y0 += H + rgap
        return pos, W, y0 - rgap

    modes = [direction] if direction in ("LR", "TB") else ["LR", "TB"]
    for m in modes:
        pos, W, H = place(m)
        if W <= max_w and H <= max_h:
            return pos, m
    for per_row in range(nr - 1, 1, -1):            # wrap a long LR chain into rows
        pos, W, H = place("LR", per_row)
        if W <= max_w and H <= max_h:
            return pos, f"LRwrap{per_row}"
    pos, W, H = place(modes[0])
    return pos, modes[0]                            # overflow: the camera zooms out to fit


class Board:
    def __init__(self):
        self.els: dict[str, El] = {}
        self.alias: dict[str, str] = {}
        self.col = 0                     # page column (one per segment)
        self.frame: tuple[int, int] = (0, 0)
        self.asides = 0
        self.flow: dict[tuple[int, int], dict] = {}
        self.view: tuple[float, float, float, float] | None = None
        self.log: list[dict] = []        # every action so far (instant replay on reconnect / rewind)
        self.n = 0
        self.active_hl: list[str] = []

    # ---------------------------------------------------------------- state
    def snapshot(self) -> dict:
        st = {k: copy.deepcopy(v) for k, v in self.__dict__.items() if k != "log"}
        st["_log_len"] = len(self.log)
        return st

    def restore(self, st: dict) -> None:
        st = copy.deepcopy(st)
        n = st.pop("_log_len")
        self.__dict__.update(st)
        del self.log[n:]

    # ---------------------------------------------------------------- geometry helpers
    def origin(self, frame=None) -> tuple[float, float]:
        c, r = frame or self.frame
        return c * (PAGE_W + GAP), r * (PAGE_H + GAP)

    def region(self, name: str) -> tuple[float, float, float, float]:
        ox, oy = self.origin()
        x, y, w, h = REGIONS[name]
        return ox + x, oy + y, w, h

    def _fs(self) -> dict:
        return self.flow.setdefault(self.frame, {"last": None, "side_y": None, "park_y": None, "notes_x": None})

    def _new_id(self, want: str | None, prefix: str) -> str:
        self.n += 1
        base = want or f"{prefix}{self.n}"
        iid = base if base not in self.els and base not in self.alias.values() else f"{base}~{self.n}"
        self.alias[base] = iid
        return iid

    def ref(self, name: str | None) -> El | None:
        if not name:
            return None
        return self.els.get(self.alias.get(name, name)) or self.els.get(name)

    def _frame_els(self, kinds_excluded=("arrow", "deco")) -> list[El]:
        return [e for e in self.els.values() if e.frame == self.frame and e.kind not in kinds_excluded]

    def _overlaps(self, x, y, w, h, margin=18) -> El | None:
        for e in self._frame_els():
            if x < e.right + margin and e.x < x + w + margin and y < e.bottom + margin and e.y < y + h + margin:
                return e
        return None

    def _place(self, w: float, h: float, place: str | None, ref: str | None, region: str | None) -> tuple[float, float, str]:
        fs = self._fs()
        region = region or "main"
        if region in ("side", "parking"):
            rx, ry, rw, rh = self.region(region)
            key = "side_y" if region == "side" else "park_y"
            y = fs[key] if fs[key] is not None else ry
            fs[key] = y + h + 16
            return rx, y, region
        if region == "notes":
            rx, ry, rw, rh = self.region("notes")
            x = fs["notes_x"] if fs["notes_x"] is not None else rx
            fs["notes_x"] = x + w + 30
            return x, ry, region
        if region == "goal":
            rx, ry, _, _ = self.region("goal")
            return rx, ry, region
        rx, ry, rw, rh = self.region("main")
        mains = [e for e in self._frame_els() if e.region == "main"]
        bottom = max((e.bottom for e in mains), default=None)
        newrow_y = ry if bottom is None else bottom + VGAP
        r = self.ref(ref)
        last = self.els.get(fs["last"]) if fs["last"] else None
        if last is not None and last.frame != self.frame:
            last = None
        place = place or "auto"
        if r is not None and r.frame == self.frame and place in ("right_of", "left_of", "below", "above"):
            if place == "right_of":
                x, y = r.right + HGAP, r.cy - h / 2
            elif place == "left_of":
                x, y = r.x - HGAP - w, r.cy - h / 2
            elif place == "below":
                x, y = r.cx - w / 2, r.bottom + VGAP
            else:
                x, y = r.cx - w / 2, r.y - VGAP - h
        elif place == "center":
            x, y = rx + (rw - w) / 2, newrow_y
        elif place == "next_line" or last is None or last.region != "main":
            x, y = rx, newrow_y
        else:
            x, y = last.right + HGAP, last.cy - h / 2
            if x + w > rx + rw:
                x, y = rx, newrow_y
        x = max(rx, min(x, rx + rw - w)) if w <= rw else rx
        y = max(ry, y)
        for _ in range(30):                          # push down until free
            hit = self._overlaps(x, y, w, h)
            if hit is None:
                break
            y = hit.bottom + 24
        return x, y, "main"

    # ---------------------------------------------------------------- camera
    def _content_rect(self) -> tuple[float, float, float, float]:
        ox, oy = self.origin()
        x0, y0, x1, y1 = ox, oy, ox + PAGE_W, oy + PAGE_H
        for e in self.els.values():
            if e.frame == self.frame:
                x0, y0 = min(x0, e.x - 40), min(y0, e.y - 40)
                x1, y1 = max(x1, e.right + 40), max(y1, e.bottom + 40)
        return x0, y0, x1 - x0, y1 - y0

    def _camera(self, rect=None, ms: int = 700) -> list[dict]:
        rect = tuple(round(v) for v in (rect or self._content_rect()))
        if rect == self.view:
            return []
        self.view = rect
        return [{"do": "camera", "rect": list(rect), "ms": ms}]

    # ---------------------------------------------------------------- public API
    def apply(self, op: Op) -> list[dict]:
        fn = getattr(self, f"_op_{op.type}", None)
        if fn is None:
            return []
        acts = fn(op) or []
        if op.type not in ("focus", "new_page"):
            acts += self._camera()
        self.log.extend(acts)
        return acts

    def apply_all(self, ops: list[Op]) -> list[dict]:
        return [a for op in ops for a in self.apply(op)]

    def begin_aside(self, question: str) -> list[dict]:
        """Q&A side board under the current page (Stiti 'turns to the side board')."""
        self.asides += 1
        self.frame = (self.col, self.asides)
        acts = self._camera((*self.origin(), PAGE_W, PAGE_H), 600)
        acts += self._op_title(Op(type="title", text="Q: " + question[:70], style="violet"))
        self.log.extend(acts)
        return acts

    def end_aside(self) -> list[dict]:
        self.frame = (self.col, 0)
        acts = self._camera(None, 600)
        self.log.extend(acts)
        return acts

    def park(self, text: str) -> list[dict]:
        """Parking lot (top-right corner list) for tangents we'll come back to."""
        main = (self.col, 0)
        keep, self.frame = self.frame, main
        acts = []
        fs = self._fs()
        if fs["park_y"] is None:
            acts += self._op_text(Op(type="text", text="Parking lot", region="parking", style="muted"))
        acts += self._op_text(Op(type="text", text="• " + text[:40], region="parking", style="muted"))
        self.frame = keep
        self.log.extend(acts)
        return acts

    def summary(self) -> str:
        """'id | type | text' lines — what the LLM gets instead of a screenshot (ChalkTalk)."""
        out = []
        for alias, iid in self.alias.items():
            e = self.els.get(iid)
            if e and e.kind not in ("deco",) and e.frame[0] == self.col:
                out.append(f"{alias} | {e.kind} | {getattr(e, 'label', '')}")
        return "\n".join(out[-30:])

    # ---------------------------------------------------------------- skills
    def _register(self, iid, kind, x, y, w, h, region="main", shape="rectangle", label="", children=None) -> El:
        e = El(iid, kind, x, y, w, h, self.frame, shape, region, children or [])
        e.label = label  # type: ignore[attr-defined]
        self.els[iid] = e
        if region == "main" and kind not in ("deco", "arrow"):
            self._fs()["last"] = iid
        return e

    def _op_new_page(self, op: Op) -> list[dict]:
        if self.flow or self.els:
            self.col += 1
        self.frame, self.asides = (self.col, 0), 0
        acts = self._camera((*self.origin(), PAGE_W, PAGE_H), 900)
        if op.text:
            acts += self._op_title(Op(type="title", text=op.text, style=op.style))
        return acts

    def _op_title(self, op: Op) -> list[dict]:
        acts: list[dict] = []
        for e in [e for e in self.els.values() if e.frame == self.frame and e.kind == "title"]:
            acts.append({"do": "erase", "ids": [e.id, *e.children]})
            del self.els[e.id]
        iid = self._new_id(op.id, "title")
        x, y, _, _ = self.region("title")
        fs = 40
        w, h = text_size(op.text, fs)
        stroke = PALETTE.get(op.style or "plain", PALETTE["plain"])[0]
        line_id = iid + ".ul"
        self._register(iid, "title", x, y, w, h, region="title", label=op.text, children=[line_id])
        return acts + [{"do": "add", "anim": "type", "els": [_base(type="text", id=iid, x=x, y=y, text=op.text,
                                                                     fontSize=fs, strokeColor=stroke)]},
                {"do": "add", "anim": "grow", "dt": 350, "els": [_base(
                    type="line", id=line_id, x=x, y=y + h + 8, points=[[0, 0], [min(w, 900), 0]],
                    strokeColor=ACCENT, strokeWidth=3, roughness=2)]}]

    def _op_text(self, op: Op) -> list[dict]:
        region = op.region or "main"
        small = region in ("parking", "goal", "notes")
        fs = 16 if small else 20
        txt = wrap(op.text, 34 if region in ("side", "parking", "goal") else 52)
        w, h = text_size(txt, fs)
        x, y, reg = self._place(w, h, op.place, op.ref, region)
        iid = self._new_id(op.id, "t")
        stroke = PALETTE.get(op.style or "plain", PALETTE["plain"])[0]
        self._register(iid, "text", x, y, w, h, reg, label=op.text)
        return [{"do": "add", "anim": "type" if len(txt) < 80 else "fade",
                 "els": [_base(type="text", id=iid, x=x, y=y, text=txt, fontSize=fs, strokeColor=stroke)]}]

    def _op_bullet(self, op: Op) -> list[dict]:
        return self._op_text(Op(type="text", id=op.id, text="• " + op.text, region=op.region or "side",
                                place=op.place, ref=op.ref, style=op.style))

    def _box_dims(self, text: str, shape: str, fs: int = 22) -> tuple[str, float, float]:
        txt = wrap(text, 16)
        tw, th = text_size(txt, fs)
        w, h = max(150, tw + 50), max(66, th + 32)
        if shape == "ellipse":
            w, h = w * 1.28, h * 1.3
        elif shape == "diamond":
            w, h = w * 1.55, h * 1.7
        return txt, w, h

    def _op_box(self, op: Op) -> list[dict]:
        shape = op.shape or "rectangle"
        txt, w, h = self._box_dims(op.text, shape)
        x, y, reg = self._place(w, h, op.place, op.ref, op.region)
        iid = self._new_id(op.id, "b")
        stroke, bg = PALETTE.get(op.style or "plain", PALETTE["plain"])
        self._register(iid, "box", x, y, w, h, reg, shape, label=op.text)
        el = _base(type=shape, id=iid, x=x, y=y, width=w, height=h, strokeColor=stroke, backgroundColor=bg,
                   label={"text": txt, "fontSize": 22, "strokeColor": "#1e1e1e"})
        if shape == "rectangle":
            el["roundness"] = {"type": 3}
        return [{"do": "add", "anim": "sketch", "els": [el]}]

    def _arrow_el(self, a: El, b: El, iid: str, label: str | None, color="#1e1e1e") -> tuple[dict, El]:
        sx, sy = border_point(a, b.cx, b.cy)
        ex, ey = border_point(b, a.cx, a.cy)
        el = _base(type="arrow", id=iid, x=sx, y=sy, width=abs(ex - sx), height=abs(ey - sy),
                   points=[[0, 0], [ex - sx, ey - sy]], strokeColor=color, endArrowhead="arrow")
        if label:
            el["label"] = {"text": label, "fontSize": 16}
        e = El(iid, "arrow", min(sx, ex), min(sy, ey), abs(ex - sx), abs(ey - sy), self.frame)
        e.label = label or ""  # type: ignore[attr-defined]
        return el, e

    def _op_arrow(self, op: Op) -> list[dict]:
        parts = re.split(r"\s*(?:->|→|>)\s*", op.ref or "")
        if len(parts) != 2:
            return []
        a, b = self.ref(parts[0]), self.ref(parts[1])
        if a is None or b is None:
            return []
        iid = self._new_id(op.id, "a")
        color = PALETTE.get(op.style, PALETTE["plain"])[0] if op.style in PALETTE else "#1e1e1e"
        el, e = self._arrow_el(a, b, iid, op.text, color)
        self.els[iid] = e
        return [{"do": "add", "anim": "grow", "els": [el]}]

    def _op_graph(self, op: Op) -> list[dict]:
        gid = op.id or f"g{self.n + 1}"
        nodes = op.nodes or []
        sizes, dims = {}, {}
        for n in nodes:
            txt, w, h = self._box_dims(n["text"], n.get("shape") or "rectangle", 20)
            sizes[n["id"]], dims[n["id"]] = (w, h), txt
        rx, ry, rw, rh = self.region("main")
        mains = [e for e in self._frame_els() if e.region == "main"]
        top = ry if not mains else max(e.bottom for e in mains) + VGAP
        pos, mode = layered_layout(nodes, op.edges or [], sizes, op.direction or "", rw + 380 if not mains else rw,
                                   ry + rh - top if mains else rh)
        gw = max(pos[i][0] + sizes[i][0] for i in pos)
        x0 = rx + max(0, (rw - gw) / 2) if gw <= rw else rx
        acts, t = [], 0
        for n in nodes:
            nid = self._new_id(n["id"], "n")
            w, h = sizes[n["id"]]
            x, y = x0 + pos[n["id"]][0], top + pos[n["id"]][1]
            stroke, bg = PALETTE.get(n.get("style") or op.style or "blue", PALETTE["blue"])
            shape = n.get("shape") or "rectangle"
            self._register(nid, "box", x, y, w, h, "main", shape, label=n["text"])
            el = _base(type=shape, id=nid, x=x, y=y, width=w, height=h, strokeColor=stroke, backgroundColor=bg,
                       label={"text": dims[n["id"]], "fontSize": 20})
            if shape == "rectangle":
                el["roundness"] = {"type": 3}
            acts.append({"do": "add", "anim": "sketch", "dt": t, "els": [el]})
            t += 450
        for k, e in enumerate(op.edges or []):
            a, b = self.ref(e["from"]), self.ref(e["to"])
            if a and b:
                aid = self._new_id(f"{gid}.e{k}", "a")
                el, ae = self._arrow_el(a, b, aid, e.get("text"))
                self.els[aid] = ae
                acts.append({"do": "add", "anim": "grow", "dt": t, "els": [el]})
                t += 250
        self.alias[gid] = self.alias.get(nodes[0]["id"], nodes[0]["id"]) if nodes else gid
        return acts

    def _op_table(self, op: Op) -> list[dict]:
        rows = op.rows or []
        ncol = max(len(r) for r in rows)
        rows = [r + [""] * (ncol - len(r)) for r in rows]
        fs = 18
        colw = [max(110, max(len(r[c]) for r in rows) * fs * CH + 30) for c in range(ncol)]
        rowh = 50
        W, H = sum(colw), rowh * len(rows)
        x0, y0, reg = self._place(W, H, op.place, op.ref, op.region)
        tid = self._new_id(op.id, "tbl")
        acts, kids = [], []
        for i, r in enumerate(rows):
            els, x = [], x0
            for c, cell in enumerate(r):
                cid = f"{tid}.r{i}c{c}"
                kids.append(cid)
                head = i == 0
                el = _base(type="rectangle", id=cid, x=x, y=y0 + i * rowh, width=colw[c], height=rowh,
                           backgroundColor="#d0ebff" if head else "#ffffff", strokeColor="#495057")
                if cell:
                    el["label"] = {"text": cell, "fontSize": fs}
                els.append(el)
                self.alias[f"{op.id or tid}.r{i}c{c}"] = cid
                ce = El(cid, "deco", x, y0 + i * rowh, colw[c], rowh, self.frame)
                ce.label = cell  # type: ignore[attr-defined]
                self.els[cid] = ce
                x += colw[c]
            self.alias[f"{op.id or tid}.r{i}"] = f"{tid}.r{i}c0"
            acts.append({"do": "add", "anim": "fade", "dt": i * 260, "els": els})
        self._register(tid, "table", x0, y0, W, H, reg, label=" / ".join(rows[0]), children=kids)
        return acts

    def _op_formula(self, op: Op) -> list[dict]:
        fs = 28
        tw, th = text_size(op.text, fs)
        w, h = tw + 60, th + 36
        x, y, reg = self._place(w, h, op.place, op.ref, op.region)
        iid = self._new_id(op.id, "f")
        self._register(iid, "formula", x, y, w, h, reg, label=op.text, children=[iid + ".t"])
        return [{"do": "add", "anim": "fade", "els": [_base(type="rectangle", id=iid, x=x, y=y, width=w, height=h,
                                                              backgroundColor="#f1f3f5", strokeColor="#868e96",
                                                              roundness={"type": 3})]},
                {"do": "add", "anim": "type", "dt": 200, "els": [_base(type="text", id=iid + ".t", x=x + 30,
                                                                        y=y + 18, text=op.text, fontSize=fs,
                                                                        fontFamily=8)]}]

    def _op_sticky(self, op: Op) -> list[dict]:
        txt = wrap(op.text, 22)
        tw, th = text_size(txt, 18)
        w, h = max(180, tw + 40), th + 40
        x, y, reg = self._place(w, h, op.place, op.ref, op.region or "side")
        iid = self._new_id(op.id, "note")
        self._register(iid, "sticky", x, y, w, h, reg, label=op.text)
        return [{"do": "add", "anim": "fade", "els": [_base(
            type="rectangle", id=iid, x=x, y=y, width=w, height=h, backgroundColor="#fff3bf",
            strokeColor="#f08c00", angle=-0.03, label={"text": txt, "fontSize": 18})]}]

    def _op_image_hint(self, op: Op) -> list[dict]:   # placeholder sketch: dashed box with "[ picture: … ]"
        return self._op_box(Op(type="box", id=op.id, text=f"[ {op.text} ]", place=op.place, ref=op.ref,
                               region=op.region, style="muted"))

    def _deco(self, target: El, el: dict, anim: str, z: str = "front") -> list[dict]:
        target.decos.append(el["id"])
        self.els[el["id"]] = El(el["id"], "deco", target.x, target.y, target.w, target.h, target.frame)
        return [{"do": "add", "anim": anim, "z": z, "els": [el]}]

    def _op_highlight(self, op: Op) -> list[dict]:
        e = self.ref(op.ref)
        if e is None:
            return []
        kind = op.style if op.style in ("underline", "circle", "marker", "color", "tick", "cross", "pointer") \
            else "underline"
        acts = []
        if self.active_hl and kind != "color":                 # fade the previous pointer/underline
            old = [i for i in self.active_hl if i in self.els]
            if old:
                acts.append({"do": "style", "ids": old, "props": {"opacity": 25}})
            self.active_hl = []
        hid = f"hl.{e.id}.{self.n}"
        self.n += 1
        if kind == "underline":
            acts += self._deco(e, _base(type="line", id=hid, x=e.x, y=e.bottom + 6, points=[[0, 0], [e.w, 0]],
                                        strokeColor=ACCENT, strokeWidth=3, roughness=2), "grow")
        elif kind == "circle":
            acts += self._deco(e, _base(type="ellipse", id=hid, x=e.x - 22, y=e.y - 18, width=e.w + 44,
                                        height=e.h + 36, strokeColor=ACCENT, strokeWidth=3, roughness=2), "sketch")
        elif kind == "marker":
            acts += self._deco(e, _base(type="rectangle", id=hid, x=e.x - 8, y=e.y - 6, width=e.w + 16,
                                        height=e.h + 12, backgroundColor="#ffd43b", strokeColor="transparent",
                                        opacity=45), "fade", z="back")
        elif kind == "tick":
            acts += self._deco(e, _base(type="line", id=hid, x=e.right + 14, y=e.cy,
                                        points=[[0, 0], [12, 14], [40, -22]], strokeColor=OK_GREEN, strokeWidth=4),
                               "grow")
        elif kind == "cross":
            acts += self._deco(e, _base(type="line", id=hid, x=e.right + 14, y=e.cy - 16,
                                        points=[[0, 0], [30, 30]], strokeColor=ACCENT, strokeWidth=4), "grow")
            acts += self._deco(e, _base(type="line", id=hid + "b", x=e.right + 44, y=e.cy - 16,
                                        points=[[0, 0], [-30, 30]], strokeColor=ACCENT, strokeWidth=4), "grow")
        elif kind == "pointer":
            acts += self._deco(e, _base(type="arrow", id=hid, x=e.right + 120, y=e.y - 70,
                                        points=[[0, 0], [-110, 66]], strokeColor=ACCENT, strokeWidth=3,
                                        endArrowhead="arrow"), "grow")
        else:   # color
            acts.append({"do": "style", "ids": [e.id], "props": {"strokeColor": ACCENT, "strokeWidth": 4}})
            return acts
        self.active_hl += [d for d in e.decos[-2:]]
        return acts

    def _op_strike(self, op: Op) -> list[dict]:
        e = self.ref(op.ref)
        if e is None:
            return []
        return self._deco(e, _base(type="line", id=f"st.{e.id}.{self.n}", x=e.x - 8, y=e.cy,
                                   points=[[0, 0], [e.w + 16, 0]], strokeColor=ACCENT, strokeWidth=4), "grow")

    def _op_erase(self, op: Op) -> list[dict]:
        e = self.ref(op.ref)
        if e is None:
            return []
        ids = [e.id, *e.children, *e.decos]
        for i in ids:
            self.els.pop(i, None)
        if self.flow.get(e.frame, {}).get("last") == e.id:
            self.flow[e.frame]["last"] = None
        return [{"do": "erase", "ids": ids}]

    def _op_focus(self, op: Op) -> list[dict]:
        e = self.ref(op.ref)
        if e is not None:                       # never zoom on one small element (760 % bug): ≥ 900×506
            w, h = max(e.w + 200, 900), max(e.h + 160, 506)
            return self._camera((e.cx - w / 2, e.cy - h / 2, w, h), 700)
        if op.region in REGIONS:
            x, y, w, h = self.region(op.region)
            w2, h2 = max(w + 120, 900), max(h + 120, 506)
            return self._camera((x + w / 2 - w2 / 2, y + h / 2 - h2 / 2, w2, h2), 700)
        return self._camera(None, 700)
