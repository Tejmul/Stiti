// Stiti particle engine — hero only (ported 1:1 from the original static/js/particles.js).
// A wrinkled, slowly turning point-cloud planet ("a busy mind") that the cursor irons smooth. It fades out as the
// hero scrolls away and the rAF loop stops at zero, so the rest of the page stays flat paper. Around the cursor,
// nearby dots link up into a nerve-like web. One fixed canvas, typed arrays, colour × alpha batched fills.
// Built as a factory (not module state) so React can mount/unmount it cleanly (StrictMode mounts twice in dev).

const TAU = Math.PI * 2;
const COLORS = ["#262b57", "#4656d6", "#6284e3", "#7fb2f0"]; // navy, royal, mid, sky
const LEVELS = [0.22, 0.45, 0.68, 0.94];                     // the 4 alpha buckets
const LINK_AREA = 230;                                       // the nerve web lights up within this many px of the cursor

// ------------------------------------------------------------------ 3D simplex noise (Gustavson), seeded
const G3 = new Float32Array([1,1,0,-1,1,0,1,-1,0,-1,-1,0,1,0,1,-1,0,1,1,0,-1,-1,0,-1,0,1,1,0,-1,1,0,1,-1,0,-1,-1]);
const perm = new Uint8Array(512), pm12 = new Uint8Array(512);
(() => {
  const p = new Uint8Array(256); for (let i = 0; i < 256; i++) p[i] = i;
  let s = 1337;
  for (let i = 255; i > 0; i--) { s = (s * 16807) % 2147483647; const j = s % (i + 1); [p[i], p[j]] = [p[j], p[i]]; }
  for (let i = 0; i < 512; i++) { perm[i] = p[i & 255]; pm12[i] = perm[i] % 12; }
})();
function noise3(x: number, y: number, z: number): number {
  const F = 1 / 3, G = 1 / 6;
  const s = (x + y + z) * F, i = Math.floor(x + s), j = Math.floor(y + s), k = Math.floor(z + s);
  const t = (i + j + k) * G, x0 = x - i + t, y0 = y - j + t, z0 = z - k + t;
  let i1, j1, k1, i2, j2, k2;
  if (x0 >= y0) {
    if (y0 >= z0) { i1 = 1; j1 = 0; k1 = 0; i2 = 1; j2 = 1; k2 = 0; }
    else if (x0 >= z0) { i1 = 1; j1 = 0; k1 = 0; i2 = 1; j2 = 0; k2 = 1; }
    else { i1 = 0; j1 = 0; k1 = 1; i2 = 1; j2 = 0; k2 = 1; }
  } else {
    if (y0 < z0) { i1 = 0; j1 = 0; k1 = 1; i2 = 0; j2 = 1; k2 = 1; }
    else if (x0 < z0) { i1 = 0; j1 = 1; k1 = 0; i2 = 0; j2 = 1; k2 = 1; }
    else { i1 = 0; j1 = 1; k1 = 0; i2 = 1; j2 = 1; k2 = 0; }
  }
  const x1 = x0 - i1 + G, y1 = y0 - j1 + G, z1 = z0 - k1 + G;
  const x2 = x0 - i2 + 2 * G, y2 = y0 - j2 + 2 * G, z2 = z0 - k2 + 2 * G;
  const x3 = x0 - 1 + 3 * G, y3 = y0 - 1 + 3 * G, z3 = z0 - 1 + 3 * G;
  const ii = i & 255, jj = j & 255, kk = k & 255;
  let n = 0, c, g;
  c = .6 - x0 * x0 - y0 * y0 - z0 * z0;
  if (c > 0) { g = pm12[ii + perm[jj + perm[kk]]] * 3; c *= c; n += c * c * (G3[g] * x0 + G3[g + 1] * y0 + G3[g + 2] * z0); }
  c = .6 - x1 * x1 - y1 * y1 - z1 * z1;
  if (c > 0) { g = pm12[ii + i1 + perm[jj + j1 + perm[kk + k1]]] * 3; c *= c; n += c * c * (G3[g] * x1 + G3[g + 1] * y1 + G3[g + 2] * z1); }
  c = .6 - x2 * x2 - y2 * y2 - z2 * z2;
  if (c > 0) { g = pm12[ii + i2 + perm[jj + j2 + perm[kk + k2]]] * 3; c *= c; n += c * c * (G3[g] * x2 + G3[g + 1] * y2 + G3[g + 2] * z2); }
  c = .6 - x3 * x3 - y3 * y3 - z3 * z3;
  if (c > 0) { g = pm12[ii + 1 + perm[jj + 1 + perm[kk + 1]]] * 3; c *= c; n += c * c * (G3[g] * x3 + G3[g + 1] * y3 + G3[g + 2] * z3); }
  return 32 * n;
}

export type Field = {
  /** Live state: lift = px the sphere rises while the hero scrolls away; fade 1..0; wr = wrinkle; iron = cursor strength. */
  cur: { lift: number; fade: number; wr: number; iron: number };
  /** Preloader handoff: collapse every dot into (x, y) and let them bloom out to the sphere, staggered. */
  intro(x: number, y: number): void;
  /** Hero visibility 0..1 (scroll-driven). Wakes the loop when the hero comes back. */
  setFade(v: number): void;
  /** Expanding ring (600 px/s) that kicks the dots outward as it passes. Hero only. */
  ripple(x: number, y: number): void;
  /** Centre the sphere on (x, y) with radius r (viewport px), e.g. behind the hero's product shot; the dots spring
   *  there, so moving it while scrolling trails softly. Without a call the sphere keeps its original placement. */
  anchor(x: number, y: number, r: number): void;
  /** Global dim (e.g. .15 while the menu is open); eased inside the loop. */
  dim(alpha: number): void;
  perf(): { fps: number; ms: number; total: number; drawn: number; mobile: boolean; running: boolean };
  destroy(): void;
};

export function createField(cv: HTMLCanvasElement): Field {
  const REDUCE = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const FINE = matchMedia("(hover: hover) and (pointer: fine)").matches;
  const ctx = cv.getContext("2d")!;
  const cur = { lift: 0, fade: 1, wr: 1, iron: 1 };

  let W = 0, H = 0, dpr = 1, mobile = false, N = 0;
  let px = new Float32Array(0), py = px, vx = px, vy = px, ux = px, uy = px, uz = px, rr = px, rnd = px, size = px, zz = px;
  let edges = new Int32Array(0);
  let bucket: Int32Array[] = [];
  const bcount = new Int32Array(16);
  let frames = 0, t = 0, last = 0, raf = 0, liftS = 0, dimT = 1, dimV = 1, fadeV = 1, introT = 0, introX = 0, introY = 0;
  let bcx = 0, bcy = 0, R = 0, SZ = 1;
  let dead = false;
  let anc: { x: number; y: number; r: number } | null = null;
  const mouse = { x: -1e4, y: -1e4, vx: 0, vy: 0, on: false };
  const rings: { x: number; y: number; t0: number }[] = [];
  const stat = { fps: 60, ms: 0, drawn: 0 };

  function layout() {
    W = innerWidth; H = innerHeight;
    dpr = Math.min(devicePixelRatio || 1, 2);
    mobile = W < 760 || !FINE;
    cv.width = Math.round(W * dpr); cv.height = Math.round(H * dpr);
    if (mobile) { bcx = W * .5; bcy = Math.min(H * .25, W * .52); R = Math.min(W * .3, H * .19); }
    else { bcx = W * .715; bcy = H * .53; R = Math.min(W * .2, H * .3); }   // level with the headline, clear of the nav
    if (anc) { bcx = anc.x; bcy = anc.y; R = anc.r; }
    SZ = mobile ? .72 : 1;
    return mobile ? 2200 : 6000;
  }

  function alloc(n: number) {
    N = n;
    const F = () => new Float32Array(n);
    px = F(); py = F(); vx = F(); vy = F(); ux = F(); uy = F(); uz = F(); rr = F(); rnd = F(); size = F(); zz = F();
    bucket = Array.from({ length: 16 }, () => new Int32Array(n));
    const ga = Math.PI * (3 - Math.sqrt(5));
    for (let i = 0; i < n; i++) {
      // Fibonacci sphere with angular jitter so no spiral shows
      const y = 1 - 2 * (i + .5) / n, r = Math.sqrt(1 - y * y), th = i * ga + (Math.random() - .5) * .9;
      ux[i] = Math.cos(th) * r; uy[i] = y; uz[i] = Math.sin(th) * r;
      rr[i] = .96 + Math.random() * .08;
      rnd[i] = Math.random();
      px[i] = bcx + ux[i] * R; py[i] = bcy + uy[i] * R;
    }
    wire();
  }

  // Fixed "neural" wiring: ~1 in 9 dots is a neuron, permanently linked to its 3 nearest neurons along the sphere
  // surface. Computed once, so the web never flickers; the cursor only lights it up. Long links are dropped so it
  // reads as a fine mesh, like nerves, not random scribbles.
  function wire() {
    const ids: number[] = [];
    for (let i = 0; i < N; i++) if (rnd[i] > .89) ids.push(i);
    const m = ids.length, spacing = Math.sqrt(4 * Math.PI / Math.max(1, m)), maxD2 = (spacing * 1.8) ** 2;
    const seen = new Set<number>(), out: number[] = [];
    for (let a = 0; a < m; a++) {
      const i = ids[a], best: [number, number][] = [[9, -1], [9, -1], [9, -1]];
      for (let b = 0; b < m; b++) {
        if (a === b) continue;
        const j = ids[b], dx = ux[i] - ux[j], dy = uy[i] - uy[j], dz = uz[i] - uz[j], d2 = dx * dx + dy * dy + dz * dz;
        if (d2 < best[2][0]) { best[2] = [d2, j]; best.sort((p, q) => p[0] - q[0]); }
      }
      for (const [d2, j] of best) {
        if (j < 0 || d2 > maxD2) continue;
        const key = i < j ? i * 65536 + j : j * 65536 + i;
        if (!seen.has(key)) { seen.add(key); out.push(i, j); }
      }
    }
    edges = Int32Array.from(out);
  }

  function resize() { const n = layout(); if (n !== N) alloc(n); }

  // ------------------------------------------------------------------ frame
  function frame(now: number) {
    raf = requestAnimationFrame(frame);
    const t0 = performance.now();
    let dt = last ? (now - last) / 16.667 : 1; last = now;
    if (dt > 3) dt = 3; if (dt <= 0) dt = 1;
    stat.fps += (60 / dt - stat.fps) * .05;
    if (!REDUCE) t += dt / 60;

    dimV += (dimT - dimV) * Math.min(1, .08 * dt);
    fadeV += (cur.fade - fadeV) * Math.min(1, .2 * dt);
    liftS += (cur.lift - liftS) * Math.min(1, .2 * dt);
    if (cur.fade <= 0 && fadeV < .01) {           // hero is gone: clear once and sleep
      ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.clearRect(0, 0, cv.width, cv.height);
      fadeV = 0; stop(); return;
    }
    mouse.vx *= .85; mouse.vy *= .85;
    if (REDUCE && ++frames > 150) stop();         // reduced motion: settle once, then hold a still frame

    const ay = t * .14, tb = .38 + Math.sin(t * .1) * .08;  // yaw + gentle tilt
    const ca = Math.cos(ay), sa = Math.sin(ay), cb = Math.cos(tb), sb = Math.sin(tb);
    const wr = cur.wr, amp = .2 * wr;
    const cx0 = bcx, cy0 = bcy - liftS;
    const ironK = (mouse.on && !REDUCE) ? cur.iron : 0;
    const mx = mouse.x, my = mouse.y, mvx = mouse.vx, mvy = mouse.vy;
    const damp = Math.pow(.86, dt), spring = .06 * dt;
    const tn = performance.now(), maxR = Math.hypot(W, H);
    const ringR = rings.map((r) => Math.max(0, (tn - r.t0) * .6));
    const since = tn - introT;
    if (introT && since > 2500) introT = 0;
    bcount.fill(0);

    for (let i = 0; i < N; i++) {
      const x0 = ux[i], y0 = uy[i], z0 = uz[i];
      const x1 = x0 * ca + z0 * sa, z1 = -x0 * sa + z0 * ca;
      const y2 = y0 * cb - z1 * sb, z2 = y0 * sb + z1 * cb;
      // wrinkles: soft swell + ridged creases + latitude waves, all drifting in object space
      const n1 = noise3(x0 * 1.2 + t * .07, y0 * 1.2 - t * .05, z0 * 1.2 + t * .04);
      const n2 = 1 - Math.abs(noise3(x0 * 2.6 - t * .06, y0 * 2.6, z0 * 2.6 + t * .08));
      const wave = Math.sin(y0 * 9 + n1 * 3.2 + t * .5);
      const disp = 1 + amp * (n1 * .85 + (n2 - .6) * .45 + wave * .14);
      const ridge = n2 * .6 + (wave * .5 + .5) * .4;
      const p = 1 / (1 - z2 * .2), k = R * rr[i] * p;
      let tx = cx0 + x1 * k * disp, ty = cy0 + y2 * k * disp;
      const ssx = cx0 + x1 * k, ssy = cy0 + y2 * k;

      // depth shading: rim and ridges read darker (royal), the facing centre lighter (sky)
      zz[i] = z2;
      const rim = 1 - Math.abs(z2);
      let ci, a, s;
      if (z2 >= 0) {
        const sh = rim * .6 + ridge * .6;
        ci = sh > .8 ? 1 : sh > .48 ? 2 : 3;
        a = .34 + .6 * Math.min(1, sh); s = .8 + .5 * ridge + .15 * (1 - rim);
      } else {
        ci = rim > .5 ? 2 : 3;
        a = .1 + .32 * rim; s = .75;
      }
      if (rnd[i] < .04 && z2 > -.1) ci = 0;

      // cursor "iron": flattens wrinkles toward the smooth sphere + a nudge along cursor velocity
      const x = px[i], y = py[i];
      if (introT) {                                   // preloader handoff: dots wait at the logo, then spring out
        const held = since < rnd[i] * 900;
        if (held) { a *= .5; s *= .7; tx = introX; ty = introY; }
      }
      if (ironK) {
        const dx = x - mx, dy = y - my;
        if (dx < 180 && dx > -180 && dy < 180 && dy > -180) {
          const d = Math.sqrt(dx * dx + dy * dy);
          if (d < 180) {
            const f = 1 - d / 180;
            tx += (ssx - tx) * f * ironK; ty += (ssy - ty) * f * ironK;
            vx[i] += mvx * .045 * f; vy[i] += mvy * .045 * f;
          }
        }
      }
      for (let q = 0; q < rings.length; q++) {
        const rg = rings[q], dx = x - rg.x, dy = y - rg.y, d = Math.sqrt(dx * dx + dy * dy) || 1;
        const off = Math.abs(d - ringR[q]);
        if (off < 30) { const f = 3 * (1 - off / 30) * (1 - ringR[q] / maxR) * .35 * dt; vx[i] += dx / d * f; vy[i] += dy / d * f; }
      }
      vx[i] = (vx[i] + (tx - x) * spring) * damp;
      vy[i] = (vy[i] + (ty - y) * spring) * damp;
      px[i] = x + vx[i] * dt; py[i] = y + vy[i] * dt;

      if (a < .06) continue;
      const b = a < .3 ? 0 : a < .54 ? 1 : a < .78 ? 2 : 3;
      const qb = ci * 4 + b;
      bucket[qb][bcount[qb]++] = i;
      size[i] = s * SZ;
    }
    for (let q = rings.length - 1; q >= 0; q--) if (ringR[q] > maxR) { rings.splice(q, 1); ringR.splice(q, 1); }
    draw();
    stat.ms += (performance.now() - t0 - stat.ms) * .05;
  }

  function draw() {
    const G = dimV * fadeV;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, W, H);
    if (mouse.on && !REDUCE && edges.length) drawLinks(G);
    let drawn = 0;
    for (let q = 0; q < 16; q++) {
      const c = bcount[q]; if (!c) continue;
      drawn += c;
      const list = bucket[q];
      ctx.globalAlpha = LEVELS[q & 3] * G;
      ctx.fillStyle = COLORS[q >> 2];
      ctx.beginPath();
      for (let k = 0; k < c; k++) {
        const i = list[k], x = px[i], y = py[i], r = size[i];
        ctx.moveTo(x + r, y); ctx.arc(x, y, r, 0, TAU);
      }
      ctx.fill();
    }
    stat.drawn = drawn;
    ctx.globalAlpha = 1;
  }

  // Neural "nerves": draw the fixed wiring (front side only) where it is near the cursor, fading with distance.
  const lineB: number[][] = [[], [], []];
  function drawLinks(G: number) {
    lineB[0].length = lineB[1].length = lineB[2].length = 0;
    const A = LINK_AREA, mx = mouse.x, my = mouse.y;
    for (let k = 0; k < edges.length; k += 2) {
      const i = edges[k], j = edges[k + 1];
      if (zz[i] < 0 || zz[j] < 0) continue;                       // back of the sphere: hidden
      const dx = (px[i] + px[j]) / 2 - mx, dy = (py[i] + py[j]) / 2 - my;
      const d = Math.sqrt(dx * dx + dy * dy);
      if (d > A) continue;
      const w = (1 - d / A) * Math.min(1, (zz[i] + zz[j]) * 1.5);  // fade toward the cursor's edge and the rim
      lineB[w > .55 ? 2 : w > .28 ? 1 : 0].push(i, j);
    }
    ctx.strokeStyle = COLORS[1]; ctx.lineWidth = .7; ctx.lineCap = "round";
    const AL = [.14, .28, .46];
    for (let b = 0; b < 3; b++) {
      const L = lineB[b]; if (!L.length) continue;
      ctx.globalAlpha = AL[b] * G;
      ctx.beginPath();
      for (let k = 0; k < L.length; k += 2) { ctx.moveTo(px[L[k]], py[L[k]]); ctx.lineTo(px[L[k + 1]], py[L[k + 1]]); }
      ctx.stroke();
    }
    ctx.globalAlpha = 1;
  }

  // ------------------------------------------------------------------ loop control + listeners
  function start() { if (!dead && !raf && !document.hidden) { last = 0; frames = 0; raf = requestAnimationFrame(frame); } }
  function stop() { cancelAnimationFrame(raf); raf = 0; }

  let rt = 0;
  const onResize = () => {
    clearTimeout(rt);
    rt = window.setTimeout(() => {
      // mobile URL bars change the height constantly: only re-layout on real changes
      if (!mobile || Math.abs(innerWidth - W) > 2 || Math.abs(innerHeight - H) > 120) { resize(); if (!raf) start(); }
    }, 150);
  };
  const onMove = (e: PointerEvent) => {
    if (e.pointerType !== "mouse") return;
    if (mouse.on) { mouse.vx = mouse.vx * .5 + (e.clientX - mouse.x) * .5; mouse.vy = mouse.vy * .5 + (e.clientY - mouse.y) * .5; }
    mouse.x = e.clientX; mouse.y = e.clientY; mouse.on = true;
  };
  const onLeave = () => { mouse.on = false; };
  const onVis = () => (document.hidden ? stop() : start());

  resize();
  addEventListener("resize", onResize);
  if (FINE && !REDUCE) {
    addEventListener("pointermove", onMove, { passive: true });
    document.documentElement.addEventListener("mouseleave", onLeave);
  }
  document.addEventListener("visibilitychange", onVis);
  start();

  return {
    cur,
    intro(x, y) {
      if (REDUCE || !N) return;
      introT = performance.now(); introX = x; introY = y;
      for (let i = 0; i < N; i++) {
        const a = Math.random() * TAU, r = Math.random() * 3;
        px[i] = x + Math.cos(a) * r; py[i] = y + Math.sin(a) * r; vx[i] = 0; vy[i] = 0;
      }
    },
    setFade(v) { cur.fade = v; if (v > 0) start(); },
    ripple(x, y) {
      if (REDUCE || !raf) return;
      rings.push({ x, y, t0: performance.now() });
      if (rings.length > 6) rings.shift();
    },
    anchor(x, y, r) {
      anc = { x, y, r }; bcx = x; bcy = y; R = r;
      if (REDUCE && !raf) start();                    // reduced motion: re-settle once at the new place
    },
    dim(alpha) { dimT = alpha; },
    perf: () => ({ fps: Math.round(stat.fps), ms: +stat.ms.toFixed(2), total: N, drawn: stat.drawn, mobile, running: !!raf }),
    destroy() {
      dead = true; stop(); clearTimeout(rt);
      removeEventListener("resize", onResize);
      removeEventListener("pointermove", onMove);
      document.documentElement.removeEventListener("mouseleave", onLeave);
      document.removeEventListener("visibilitychange", onVis);
    },
  };
}
