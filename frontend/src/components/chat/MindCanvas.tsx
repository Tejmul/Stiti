"use client";
// Stiti's "mind": a wavy point-cloud sphere that shows her state (port of static/js/mind.js).
//   idle      slow turn, gentle wobble
//   thinking  faster swirl, rougher surface (she's working on it)
//   talking   steady swirl; every streamed word gives it a small nudge
//   offline   still and faded
// One soft outward pulse when a reply lands. Canvas 2D, ~1400 dots, a few hundred µs per frame on an M2.
// Pauses when the tab is hidden or the canvas is off-screen (mobile sheet closed); static with reduced motion.
import { useEffect, useImperativeHandle, useRef, type Ref } from "react";
import { prefersReducedMotion } from "@/lib/stiti";

export type MindState = "idle" | "thinking" | "talking" | "offline";
export type MindHandle = { pulse: (amount?: number) => void };

type Params = { spin: number; amp: number; flow: number; alpha: number };
const STATES: Record<MindState, Params> = {
  idle: { spin: 0.18, amp: 0.09, flow: 0.35, alpha: 1 },
  thinking: { spin: 0.65, amp: 0.17, flow: 1.25, alpha: 1 },
  talking: { spin: 0.42, amp: 0.12, flow: 0.8, alpha: 1 },
  offline: { spin: 0.06, amp: 0.06, flow: 0.12, alpha: 0.7 },
};
const COLORS: [string, number, number][] = [["#7fb2f0", 0, 0.45], ["#4656d6", 0.45, 0.93], ["#262b57", 0.93, 1.01]];
const ALPHAS = [0.16, 0.32, 0.55, 0.85];

// cheap smooth 3D value noise (hash + trilinear), enough for an organic wobble
function hash(x: number, y: number, z: number) {
  let h = (x * 374761393 + y * 668265263 + z * 2147483647) | 0;
  h = Math.imul(h ^ (h >>> 13), 1274126177);
  return ((h ^ (h >>> 16)) >>> 0) / 4294967295;
}
function noise(x: number, y: number, z: number) {
  const xi = Math.floor(x), yi = Math.floor(y), zi = Math.floor(z);
  const s = (t: number) => t * t * (3 - 2 * t), u = s(x - xi), v = s(y - yi), w = s(z - zi);
  const L = (a: number, b: number, t: number) => a + (b - a) * t;
  const c = (dx: number, dy: number, dz: number) => hash(xi + dx, yi + dy, zi + dz);
  return L(L(L(c(0, 0, 0), c(1, 0, 0), u), L(c(0, 1, 0), c(1, 1, 0), u), v),
           L(L(c(0, 0, 1), c(1, 0, 1), u), L(c(0, 1, 1), c(1, 1, 1), u), v), w);
}

export default function MindCanvas({ state, ref, count = 1400 }: { state: MindState; ref?: Ref<MindHandle>; count?: number }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const target = useRef<Params>(STATES.idle);
  const pulse = useRef(0);
  const redraw = useRef<() => void>(() => {});

  useImperativeHandle(ref, () => ({ pulse: (amount = 1) => { pulse.current = Math.max(pulse.current, amount); } }), []);

  useEffect(() => {
    target.current = STATES[state] ?? STATES.idle;
    redraw.current();
  }, [state]);

  useEffect(() => {
    const cv = canvas.current!;
    const g = cv.getContext("2d")!;
    const reduced = prefersReducedMotion();
    const pts: { x: number; y: number; z: number; d: number; k: number }[] = [];
    const golden = Math.PI * (3 - Math.sqrt(5));
    for (let i = 0; i < count; i++) {                 // Fibonacci sphere, some dots pulled inside
      const y = 1 - (i / (count - 1)) * 2, r = Math.sqrt(1 - y * y), th = golden * i;
      const depth = Math.random() < 0.78 ? 1 : 0.55 + Math.random() * 0.4;
      pts.push({ x: Math.cos(th) * r, y, z: Math.sin(th) * r, d: depth, k: Math.random() });
    }
    const cur: Params = { ...target.current };
    const buckets: number[][] = [[], [], [], []];
    let t = 0, rot = 0, raf = 0, w = 0, h = 0, last = performance.now(), onScreen = true;

    function size() {
      const dpr = Math.min(devicePixelRatio || 1, 2), rect = cv.getBoundingClientRect();
      w = rect.width; h = rect.height;
      cv.width = Math.max(1, w * dpr); cv.height = Math.max(1, h * dpr);
      g.setTransform(dpr, 0, 0, dpr, 0, 0);
    }

    function draw() {
      const tg = target.current;
      if (reduced) Object.assign(cur, tg);
      else for (const k of ["spin", "amp", "flow", "alpha"] as const) cur[k] += (tg[k] - cur[k]) * 0.05;  // ease between states
      g.clearRect(0, 0, w, h);
      const R = Math.min(w, h) * 0.36, cx = w / 2, cy = h / 2, pz = pulse.current;
      const cr = Math.cos(rot), sr = Math.sin(rot), tilt = 0.32, ct = Math.cos(tilt), st = Math.sin(tilt);
      for (const b of buckets) b.length = 0;
      for (const p of pts) {
        const n = noise(p.x * 1.6 + 7, p.y * 1.6 + t * cur.flow, p.z * 1.6 - t * cur.flow * 0.5);
        const rr = p.d * (1 + (n - 0.5) * 2 * cur.amp + pz * 0.12 * (0.6 + p.k * 0.4));
        let x = p.x * rr, y = p.y * rr, z = p.z * rr;
        [x, z] = [x * cr - z * sr, x * sr + z * cr];             // spin around Y
        [y, z] = [y * ct - z * st, y * st + z * ct];             // fixed tilt
        const front = (z + 1.2) / 2.4;                           // 0 back … 1 front
        const rim = 1 - Math.abs(z) / Math.max(0.2, rr);         // denser look at the silhouette
        const a = (0.12 + front * 0.55 + rim * 0.25) * cur.alpha;
        buckets[Math.min(3, (a * 4) | 0)].push(cx + x * R, cy + y * R, 0.55 + front * 0.95, p.k);
      }
      for (let b = 0; b < 4; b++) {
        const L = buckets[b];
        for (const [col, lo, hi] of COLORS) {
          g.globalAlpha = ALPHAS[b] * cur.alpha;
          g.fillStyle = col;
          g.beginPath();
          for (let i = 0; i < L.length; i += 4) {
            const k = L[i + 3];
            if (k < lo || k >= hi) continue;
            g.moveTo(L[i] + L[i + 2], L[i + 1]);
            g.arc(L[i], L[i + 1], L[i + 2], 0, 6.2832);
          }
          g.fill();
        }
      }
      g.globalAlpha = 1;
    }

    function frame(now: number) {
      const dt = Math.min(0.05, (now - last) / 1000); last = now;
      t += dt; rot += dt * cur.spin; pulse.current *= 0.94;
      draw();
      raf = requestAnimationFrame(frame);
    }
    const stop = () => { cancelAnimationFrame(raf); raf = 0; };
    const start = () => {
      if (reduced || raf || document.hidden || !onScreen) return;
      last = performance.now(); raf = requestAnimationFrame(frame);
    };

    size();
    draw();
    redraw.current = () => { if (reduced) draw(); };
    start();
    const ro = new ResizeObserver(() => { size(); draw(); });
    ro.observe(cv);
    const io = new IntersectionObserver(([e]) => { onScreen = e.isIntersecting; if (onScreen) start(); else stop(); });
    io.observe(cv);
    const onVis = () => (document.hidden ? stop() : start());
    document.addEventListener("visibilitychange", onVis);
    return () => {
      stop(); ro.disconnect(); io.disconnect();
      document.removeEventListener("visibilitychange", onVis);
      redraw.current = () => {};
    };
  }, [count]);

  return <canvas ref={canvas} className="mind__canvas" aria-hidden="true" />;
}
