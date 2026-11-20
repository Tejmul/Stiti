/* eslint-disable @typescript-eslint/no-explicit-any */
// Stiti whiteboard runtime: a renderer driven by cue messages from Python (D14/D15). Python owns the lesson, layout
// and audio; this only draws, animates (pen-like, live), moves the camera and reports errors. Excalidraw 0.18.1 (MIT).
// Ported from the plain-JS board (src/stiti/tutor/web/board.js), same action protocol:
//   {do: "add", anim: none|fade|grow|type|sketch, els: [skeleton…], z?: "back", files?: [{id, dataURL, mimeType}]}
//   {do: "style", ids, props} · {do: "erase", ids} · {do: "camera", rect: [x, y, w, h], ms}

type Lib = typeof import("@excalidraw/excalidraw");
type Api = any;
type El = any;
export type Action = { do: string; [k: string]: any };

const PAGE_W = 1600, PAGE_H = 900, MARGIN = 0.06, ZMAX = 1.15;
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
const ease = (t: number) => 1 - Math.pow(1 - t, 3);
const clamp = (v: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, v));
const pathLen = (P: number[][]) => P.reduce((s, p, i) => (i ? s + Math.hypot(p[0] - P[i - 1][0], p[1] - P[i - 1][1]) : 0), 0);

export interface RuntimeOpts {
  api: Api;
  lib: Lib;
  board: () => HTMLElement | null;          // the canvas container
  check: () => HTMLElement | null;          // the check card (camera leaves room for it)
  pen: () => HTMLElement | null;            // the pen dot
  toolbarShown: () => boolean;              // Excalidraw's own toolbar visible (D)
  reduced: () => boolean;                   // prefers-reduced-motion
  send: (m: object) => void;
}

export function createRuntime(o: RuntimeOpts) {
  const { api, lib } = o;
  const NEVER = lib.CaptureUpdateAction.NEVER;
  const scene = (): El[] => api.getSceneElements();
  const put = (els: El[]) => api.updateScene({ elements: els, captureUpdate: NEVER });
  const convert = (skels: any[]): El[] => lib.convertToExcalidrawElements(skels, { regenerateIds: false }) as El[];
  const anims = new Set<() => void>();
  let pending: ReturnType<typeof setTimeout>[] = [];
  let lastRect: number[] | null = null;

  function tween(ms: number, step: (t: number) => void): Promise<void> {
    return new Promise((res) => {
      const t0 = performance.now();
      let done = false;
      const finish = () => { if (done) return; done = true; anims.delete(finish); step(1); res(); };
      anims.add(finish);
      const tick = () => {
        if (done) return;
        const t = Math.min(1, (performance.now() - t0) / ms);
        step(t);
        if (t < 1) setTimeout(tick, 16); else finish();     // setTimeout (not rAF): keeps going in background tabs
      };
      tick();
    });
  }
  function mutate(ids: Set<string>, fn: (e: El) => object) {
    put(scene().map((e) => (ids.has(e.id) || (e.containerId && ids.has(e.containerId)) ? lib.newElementWith(e, fn(e) as any) : e)));
  }
  const insert = (els: El[], z?: string) => put(z === "back" ? [...els, ...scene()] : [...scene(), ...els]);
  function fresh(skels: any[]) {
    const have = new Set(scene().map((e) => e.id));
    return convert(skels).filter((e) => !have.has(e.id));      // idempotent: replayed cues never duplicate
  }

  // Fonts land late sometimes: re-measure free text so nothing stays clipped.
  function remeasure() {
    put(scene().map((e) => {
      if (e.type !== "text" || e.containerId) return e;
      const [m] = convert([{ type: "text", id: e.id, x: e.x, y: e.y, text: e.originalText ?? e.text, fontSize: e.fontSize,
                             fontFamily: e.fontFamily, strokeColor: e.strokeColor }]);
      return lib.newElementWith(e, { width: m.width, height: m.height } as any);
    }));
  }

  function perimeter(e: El): number[][] {   // outline points (relative) for the "sketch" draw-on animation
    const w = e.width, h = e.height, P: number[][] = [];
    if (e.type === "ellipse") {
      for (let i = 0; i <= 48; i++) { const a = -Math.PI / 2 + (i / 48) * 2 * Math.PI; P.push([w / 2 + (w / 2) * Math.cos(a), h / 2 + (h / 2) * Math.sin(a)]); }
    } else {
      const c = e.type === "diamond" ? [[w / 2, 0], [w, h / 2], [w / 2, h], [0, h / 2], [w / 2, 0]] : [[0, 0], [w, 0], [w, h], [0, h], [0, 0]];
      for (let k = 0; k < 4; k++) for (let i = 0; i < 12; i++) {
        const t = i / 12; P.push([c[k][0] + (c[k + 1][0] - c[k][0]) * t, c[k][1] + (c[k + 1][1] - c[k][1]) * t]);
      }
      P.push(c[4]);
    }
    return P;
  }
  function growPoints(pts: number[][], k: number): number[][] {   // reveal a polyline progressively along its length
    if (pts.length === 2) return [pts[0], [pts[1][0] * k, pts[1][1] * k]];
    const segs = pts.length - 1, upto = k * segs, i = Math.floor(upto), f = upto - i;
    const out = pts.slice(0, Math.min(pts.length, i + 1));
    if (i < segs) out.push([pts[i][0] + (pts[i + 1][0] - pts[i][0]) * f, pts[i][1] + (pts[i + 1][1] - pts[i][1]) * f]);
    return out.length >= 2 ? out : [pts[0], pts[0]];
  }

  // The pen: a small indigo dot riding the point being drawn, so the board looks hand-written live.
  let penHide: ReturnType<typeof setTimeout> | undefined;
  function penAt(x: number, y: number) {
    const pen = o.pen(), b = o.board();
    if (!pen || !b) return;
    const s = api.getAppState(), r = b.getBoundingClientRect(), z = s.zoom.value;
    pen.style.transform = `translate(${r.left + (x + s.scrollX) * z}px, ${r.top + (y + s.scrollY) * z}px)`;
    pen.dataset.on = "1";
    clearTimeout(penHide);
    penHide = setTimeout(() => { delete pen.dataset.on; }, 260);
  }

  async function add(a: Action, instant: boolean) {
    if (a.files?.length) {        // pictures (the "image" op): register the bitmap before the element that shows it
      try { api.addFiles(a.files.map((f: any) => ({ mimeType: "image/png", ...f, created: Date.now() }))); }
      catch (err) { o.send({ type: "error", msg: String(err).slice(0, 300), action: "addFiles" }); }
    }
    const els = fresh(a.els);
    if (!els.length) return;
    const target = new Map(els.map((e) => [e.id, e.opacity ?? 100]));
    const ids = new Set(els.map((e) => e.id));
    if (instant || !a.anim || a.anim === "none" || o.reduced()) return insert(els, a.z);
    if (a.anim === "fade") {
      insert(els.map((e) => ({ ...e, opacity: 1 })), a.z);
      return tween(360, (t) => mutate(ids, (e) => ({ opacity: Math.max(1, Math.round(target.get(e.id) * ease(t))) })));
    }
    if (a.anim === "grow") {      // arrows / lines grow from their first point (pen at the tip); labels fade in after
      const lin = els.filter((e) => e.points), rest = els.filter((e) => !e.points);
      const full = new Map(lin.map((e) => [e.id, e.points as number[][]]));
      insert([...lin.map((e) => ({ ...e, points: growPoints(e.points, 0.02) })), ...rest.map((e) => ({ ...e, opacity: 1 }))], a.z);
      const linIds = new Set(lin.map((e) => e.id));
      const ms = clamp(Math.max(0, ...lin.map((e) => pathLen(e.points))) * 2.2, 420, 900);
      const lead = lin[0];
      await tween(ms, (t) => {
        const k = Math.max(0.02, t < 1 ? t * (2 - t) : 1);
        put(scene().map((e) => (linIds.has(e.id) ? lib.newElementWith(e, { points: growPoints(full.get(e.id)!, k) } as any) : e)));
        if (lead && t < 1) { const g = growPoints(full.get(lead.id)!, k), p = g[g.length - 1]; penAt(lead.x + p[0], lead.y + p[1]); }
      });
      const restIds = new Set(rest.map((e) => e.id));
      if (restIds.size) await tween(220, (t) => mutate(restIds, () => ({ opacity: Math.max(1, Math.round(100 * t)) })));
      return;
    }
    if (a.anim === "type" && a.els.length === 1 && a.els[0].type === "text") {
      // written out at a speaking-ish pace (~34 chars/s, capped at ~2.6 s for long lines), the pen at the caret
      const sk = a.els[0], txt: string = sk.text, per = 1000 / 34;
      const step = Math.max(1, Math.ceil(txt.length / (2600 / per)));
      let done = false;
      const finish = () => { done = true; };
      anims.add(finish);
      for (let i = step; i < txt.length && !done; i += step) {
        const part = txt.slice(0, i);
        const [el] = convert([{ ...sk, text: part }]);
        put([...scene().filter((e) => e.id !== sk.id), el]);
        const lines = part.split("\n"), last = lines[lines.length - 1], longest = Math.max(...lines.map((l) => l.length), 1);
        penAt(el.x + (el.width * last.length) / longest, el.y + el.height - (sk.fontSize || 20) * 0.45);
        await sleep(per * step);
      }
      anims.delete(finish);
      put([...scene().filter((e) => e.id !== sk.id), ...convert([sk])]);
      return;
    }
    if (a.anim === "sketch") {    // draw the outline like a pen, then drop in the real shape + label
      const shape = els.find((e) => !e.containerId) || els[0];
      const P = perimeter(shape), skId = shape.id + ".sk";
      const [line] = convert([{ type: "line", id: skId, x: shape.x, y: shape.y, width: 1, height: 1,
        strokeColor: shape.strokeColor, strokeWidth: shape.strokeWidth, roughness: 1 }]);
      insert([lib.newElementWith(line, { points: P.slice(0, 2) } as any)], a.z);
      await tween(clamp(pathLen(P) * 1.3, 650, 1000), (t) => {
        const n = Math.max(2, Math.round(P.length * t));
        put(scene().map((e) => (e.id === skId ? lib.newElementWith(e, { points: P.slice(0, n) } as any) : e)));
        if (t < 1) penAt(shape.x + P[n - 1][0], shape.y + P[n - 1][1]);
      });
      put(scene().filter((e) => e.id !== skId));
      if (scene().some((e) => ids.has(e.id))) return;
      insert(els.map((e) => ({ ...e, opacity: 1 })), a.z);
      return tween(260, (t) => mutate(ids, (e) => ({ opacity: Math.max(1, Math.round(target.get(e.id) * t)) })));
    }
    insert(els, a.z);
  }

  // ---------------------------------------------------------------- camera
  const top = () => (o.toolbarShown() ? 64 : 16);     // keep drawings clear of Excalidraw's toolbar when it shows
  const viewport = (): [number, number] => { const b = o.board(); return b ? [b.clientWidth, b.clientHeight] : [1, 1]; };
  // The free part of the board: below the toolbar and clear of the check card. A card on the right leaves the strip
  // to its left; a card across the bottom (phone) leaves the space above it.
  function safeArea() {
    const [vw, vh] = viewport();
    const x0 = 0, y0 = top();
    let x1 = vw, y1 = vh;
    const c = o.check(), b = o.board();
    if (c && b && !c.hidden) {
      const br = b.getBoundingClientRect(), r = c.getBoundingClientRect();
      const L = r.left - br.left, T = r.top - br.top;
      if (L > vw * 0.4) x1 = Math.min(x1, L - 8); else y1 = Math.min(y1, T - 8);
    }
    return { x0, y0, w: Math.max(120, x1 - x0), h: Math.max(120, y1 - y0) };
  }
  function camState(rect: number[]) {
    const s = safeArea(), [x, y, w, h] = rect, [vw, vh] = viewport();
    // fit with a margin, but never blow a small drawing up past ~1.15× of "the whole 1600×900 page fits the board"
    const fit = Math.min(s.w / w, s.h / h) * (1 - 2 * MARGIN);
    const cap = ZMAX * Math.min(vw / PAGE_W, (vh - top()) / PAGE_H);
    return { z: Math.max(0.05, Math.min(fit, cap)), cx: x + w / 2, cy: y + h / 2 };
  }
  const anchor = () => { const s = safeArea(); return [s.x0 + s.w / 2, s.y0 + s.h / 2]; };
  function applyCam({ z, cx, cy }: { z: number; cx: number; cy: number }) {
    const [px, py] = anchor();
    api.updateScene({ appState: { zoom: { value: z }, scrollX: px / z - cx, scrollY: py / z - cy }, captureUpdate: NEVER });
  }
  async function camera(a: Action, instant = false) {
    lastRect = a.rect;
    const to = camState(a.rect);
    if (instant) return applyCam(to);
    const s = api.getAppState(), [px, py] = anchor(), z0 = s.zoom.value;
    const from = { z: z0, cx: px / z0 - s.scrollX, cy: py / z0 - s.scrollY };
    return tween(a.ms || 700, (t) => {
      const k = ease(t);
      applyCam({ z: Math.exp(Math.log(from.z) + (Math.log(to.z) - Math.log(from.z)) * k),
                 cx: from.cx + (to.cx - from.cx) * k, cy: from.cy + (to.cy - from.cy) * k });
    });
  }

  function run(a: Action, instant = false) {
    try {
      if (a.do === "add") return add(a, instant);
      if (a.do === "style") return mutate(new Set(a.ids), () => a.props);
      if (a.do === "erase") { const ids = new Set(a.ids); return put(scene().filter((e) => !ids.has(e.id) && !ids.has(e.containerId))); }
      if (a.do === "camera") return camera(a, instant);
    } catch (err) { o.send({ type: "error", msg: String(err).slice(0, 300), action: a.do }); }
  }

  return {
    run,
    schedule(actions: Action[]) { for (const a of actions || []) pending.push(setTimeout(() => run(a), a.at_ms || 0)); },
    async replay(actions: Action[]) { for (const a of actions || []) await run(a, true); },
    clearPending() { pending.forEach(clearTimeout); pending = []; },
    finishAll() { [...anims].forEach((f) => f()); },
    reset() { put([]); },
    refit(ms = 450) { if (lastRect) camera({ do: "camera", rect: lastRect, ms }); },
    reframe() { if (lastRect && !anims.size) applyCam(camState(lastRect)); },
    reframeNow() { if (lastRect) applyCam(camState(lastRect)); },
    remeasure,
    viewport,
    scene,
    busy: () => anims.size > 0,
  };
}
export type Runtime = ReturnType<typeof createRuntime>;
