// Stiti's "mind": a wavy point-cloud sphere (the owner's reference look) that shows her state.
//   idle      slow turn, gentle wobble
//   thinking  faster swirl, rougher surface (she's working on it)
//   speaking  one soft outward pulse per reply
//   offline   still and faded
// Canvas 2D, ~1400 dots, a few hundred µs per frame on an M2. Pauses when hidden; static with reduced motion.
import { reducedMotion } from "./common.js";

const STATES = {
  idle: { spin: 0.18, amp: 0.09, flow: 0.35, alpha: 1 },
  thinking: { spin: 0.65, amp: 0.17, flow: 1.25, alpha: 1 },
  offline: { spin: 0.06, amp: 0.06, flow: 0.12, alpha: 0.7 },
};

// cheap smooth 3D value noise (hash + trilinear), enough for an organic wobble
function hash(x, y, z) {
  let h = (x * 374761393 + y * 668265263 + z * 2147483647) | 0;
  h = Math.imul(h ^ (h >>> 13), 1274126177);
  return ((h ^ (h >>> 16)) >>> 0) / 4294967295;
}
function noise(x, y, z) {
  const xi = Math.floor(x), yi = Math.floor(y), zi = Math.floor(z);
  const xf = x - xi, yf = y - yi, zf = z - zi;
  const s = (t) => t * t * (3 - 2 * t), u = s(xf), v = s(yf), w = s(zf);
  const L = (a, b, t) => a + (b - a) * t;
  const c = (dx, dy, dz) => hash(xi + dx, yi + dy, zi + dz);
  return L(L(L(c(0, 0, 0), c(1, 0, 0), u), L(c(0, 1, 0), c(1, 1, 0), u), v),
           L(L(c(0, 0, 1), c(1, 0, 1), u), L(c(0, 1, 1), c(1, 1, 1), u), v), w);
}

export function createMind(canvas, { count = 1400 } = {}) {
  const g = canvas.getContext("2d");
  const pts = [];
  const golden = Math.PI * (3 - Math.sqrt(5));
  for (let i = 0; i < count; i++) {                 // Fibonacci sphere, some dots pulled inside
    const y = 1 - (i / (count - 1)) * 2, r = Math.sqrt(1 - y * y), th = golden * i;
    const depth = Math.random() < 0.78 ? 1 : 0.55 + Math.random() * 0.4;
    pts.push({ x: Math.cos(th) * r, y, z: Math.sin(th) * r, d: depth, k: Math.random() });
  }
  const cur = { ...STATES.idle };
  let target = STATES.idle, t = 0, rot = 0, pulse = 0, raf = 0, w = 0, h = 0, last = performance.now();

  function size() {
    const dpr = Math.min(devicePixelRatio || 1, 2), rect = canvas.getBoundingClientRect();
    w = rect.width; h = rect.height;
    canvas.width = Math.max(1, w * dpr); canvas.height = Math.max(1, h * dpr);
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
  }

  function draw() {
    for (const k in cur) cur[k] += (target[k] - cur[k]) * 0.05;     // ease between states
    g.clearRect(0, 0, w, h);
    const R = Math.min(w, h) * 0.36, cx = w / 2, cy = h / 2;
    const cr = Math.cos(rot), sr = Math.sin(rot), tilt = 0.32, ct = Math.cos(tilt), st = Math.sin(tilt);
    const buckets = [[], [], [], []];
    for (const p of pts) {
      const n = noise(p.x * 1.6 + 7, p.y * 1.6 + t * cur.flow, p.z * 1.6 - t * cur.flow * 0.5);
      const rr = p.d * (1 + (n - 0.5) * 2 * cur.amp + pulse * 0.12 * (0.6 + p.k * 0.4));
      let x = p.x * rr, y = p.y * rr, z = p.z * rr;
      [x, z] = [x * cr - z * sr, x * sr + z * cr];             // spin around Y
      [y, z] = [y * ct - z * st, y * st + z * ct];             // fixed tilt
      const front = (z + 1.2) / 2.4;                           // 0 back … 1 front
      const rim = 1 - Math.abs(z) / Math.max(0.2, rr);         // denser look at the silhouette
      const a = (0.12 + front * 0.55 + rim * 0.25) * cur.alpha;
      const b = Math.min(3, (a * 4) | 0);
      buckets[b].push(cx + x * R, cy + y * R, 0.55 + front * 0.95, p.k);
    }
    const alphas = [0.16, 0.32, 0.55, 0.85];
    for (let b = 0; b < 4; b++) {
      const L = buckets[b];
      for (const [col, sel] of [["#7fb2f0", (k) => k < 0.45], ["#4656d6", (k) => k >= 0.45 && k < 0.93], ["#262b57", (k) => k >= 0.93]]) {
        g.globalAlpha = alphas[b] * cur.alpha;
        g.fillStyle = col;
        g.beginPath();
        for (let i = 0; i < L.length; i += 4) {
          if (!sel(L[i + 3])) continue;
          g.moveTo(L[i] + L[i + 2], L[i + 1]);
          g.arc(L[i], L[i + 1], L[i + 2], 0, 6.2832);
        }
        g.fill();
      }
    }
    g.globalAlpha = 1;
  }

  function frame(now) {
    const dt = Math.min(0.05, (now - last) / 1000); last = now;
    t += dt; rot += dt * cur.spin; pulse *= 0.94;
    draw();
    raf = requestAnimationFrame(frame);
  }

  size();
  addEventListener("resize", () => { size(); if (reducedMotion) draw(); });
  if (reducedMotion) draw();
  else raf = requestAnimationFrame(frame);
  document.addEventListener("visibilitychange", () => {
    if (reducedMotion) return;
    cancelAnimationFrame(raf);
    if (!document.hidden) { last = performance.now(); raf = requestAnimationFrame(frame); }
  });

  return {
    set(state) { target = STATES[state] || STATES.idle; if (reducedMotion) { Object.assign(cur, target); draw(); } },
    pulse() { pulse = 1; },
  };
}
