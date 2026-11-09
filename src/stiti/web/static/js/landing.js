// Stiti — landing page motion: Lenis + GSAP, preloader, hero timeline (+ hero-only particles), reveals, marquees, cursor.
import { wireNav, reducedMotion } from "/static/js/common.js";
import * as P from "/static/js/particles.js";

const { gsap, ScrollTrigger } = window;
const html = document.documentElement;
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const MOBILE = matchMedia("(max-width: 760px)").matches;

/** cubic-bezier → easing function (so GSAP uses the exact site curves without CustomEase). */
function bezier(x1, y1, x2, y2) {
  const cx = 3 * x1, bx = 3 * (x2 - x1) - cx, ax = 1 - cx - bx;
  const cy = 3 * y1, by = 3 * (y2 - y1) - cy, ay = 1 - cy - by;
  const X = (t) => ((ax * t + bx) * t + cx) * t, Y = (t) => ((ay * t + by) * t + cy) * t;
  const dX = (t) => (3 * ax * t + 2 * bx) * t + cx;
  return (x) => {
    if (x <= 0) return 0; if (x >= 1) return 1;
    let t = x;
    for (let i = 0; i < 8; i++) { const e = X(t) - x; if (Math.abs(e) < 1e-5) return Y(t); const d = dX(t); if (Math.abs(d) < 1e-6) break; t -= e / d; }
    let lo = 0, hi = 1; t = x;
    for (let i = 0; i < 24; i++) { if (X(t) < x) lo = t; else hi = t; t = (lo + hi) / 2; }
    return Y(t);
  };
}
const EXPO = bezier(.76, 0, .24, 1), OUT = bezier(.16, 1, .3, 1);

/** Wrap every word in <span class="wm"><span class="w"> (keeps <b> etc.). mask=false skips the overflow mask. */
function splitWords(root, mask = true) {
  const words = [];
  const walk = (node) => [...node.childNodes].forEach((ch) => {
    if (ch.nodeType === 1) return walk(ch);
    if (ch.nodeType !== 3) return;
    const frag = document.createDocumentFragment();
    ch.textContent.split(/(\s+)/).forEach((tok) => {
      if (!tok) return;
      if (/^\s+$/.test(tok)) return frag.append(" ");
      const w = document.createElement("span"); w.className = "w"; w.textContent = tok;
      if (mask) { const m = document.createElement("span"); m.className = "wm"; m.append(w); frag.append(m); }
      else frag.append(w);
      words.push(w);
    });
    ch.replaceWith(frag);
  });
  walk(root);
  return words;
}

// ------------------------------------------------------------------ boot
if ("scrollRestoration" in history) history.scrollRestoration = "manual";
const canvas = $(".field");
P.init(canvas);

let lenis = null;
if (!reducedMotion && window.Lenis) {
  lenis = new window.Lenis({ lerp: .1 });
  lenis.on("scroll", ScrollTrigger.update);
  gsap.ticker.add((t) => lenis.raf(t * 1000));
  gsap.ticker.lagSmoothing(0);
}
gsap.registerPlugin(ScrollTrigger);
gsap.defaults({ ease: OUT });

wireNav({ onMenu: (open) => { P.dim(open ? .15 : 1); open ? lenis?.stop() : lenis?.start(); } });
setupAnchors();
setupCursor();
setupSayingsClones();

const hero = setupHero();
setupHeroField();
setupReveals();
setupMarquees();
document.fonts?.ready.then(() => ScrollTrigger.refresh());

preloader().then(() => {
  hero.play();
  if (location.hash) { const el = document.querySelector(location.hash); el && scrollToEl(el, true); }
});

// ------------------------------------------------------------------ preloader (0 → 2.4 s)
function preloader() {
  const loader = $(".loader");
  if (reducedMotion) { loader?.remove(); canvas.style.opacity = 1; return Promise.resolve(); }
  scrollTo(0, 0);
  html.classList.add("is-loading");
  lenis?.stop();
  const num = $(".loader__num"), line = $(".loader__line"), logo = $(".loader__logo");
  const o = { v: 0 };
  return new Promise((done) => {
    gsap.timeline()
      .fromTo(logo, { opacity: 0, scale: .8, rotate: -30 }, { opacity: 1, scale: 1, rotate: 0, duration: 1.2, ease: OUT }, 0)
      .to(o, { v: 100, duration: 1.8, ease: "power2.inOut", onUpdate: () => { num.textContent = String(Math.round(o.v)).padStart(3, "0") + "%"; } }, 0)
      .fromTo(line, { scaleX: 0 }, { scaleX: 1, duration: 1.8, ease: "power2.inOut" }, 0)
      .to([num, line], { opacity: 0, y: -40, duration: .4, ease: OUT }, 1.8)
      // handoff: the logo's dot collapses and the sphere blooms out of that exact point
      .to(logo, { scale: .25, opacity: 0, duration: .35, ease: EXPO }, 1.72)
      .add(() => P.intro(innerWidth / 2, innerHeight / 2), 2.15)
      .to(canvas, { opacity: 1, duration: 1, ease: "power1.out" }, 1.75)
      .to(loader, { yPercent: -100, duration: .9, ease: EXPO }, 2.0)
      .add(() => { html.classList.remove("is-loading"); lenis?.start(); done(); }, 2.4)
      .add(() => loader.remove(), 2.95);
  });
}

// ------------------------------------------------------------------ hero timeline
function setupHero() {
  const label = $(".hero__label-text");
  const lines = $$(".hero__title .line").map((l) => splitWords(l));
  const strip = $(".hero__strip"), desc = $(".hero__desc"), stack = $$(".hero__stack li");
  const ctas = $$(".hero__ctas .btn"), cue = $(".hero__cue");
  const tl = gsap.timeline({ paused: true });
  if (reducedMotion) return tl;

  gsap.set(label, { opacity: 0, y: 20 });
  lines.forEach((ws) => gsap.set(ws, { yPercent: 110 }));
  gsap.set([strip, desc], { opacity: 0, y: 20 });
  gsap.set(stack, { opacity: 0 });
  gsap.set(ctas, { opacity: 0, y: 30 });
  gsap.set(cue, { autoAlpha: 0 });

  tl.to(label, { opacity: 1, y: 0, duration: .6 }, 0);
  lines.forEach((ws, i) => tl.to(ws, { yPercent: 0, duration: .9, stagger: .08, ease: OUT }, .1 + i * .2));
  tl.to(strip, { opacity: 1, y: 0, duration: .8 }, .9)
    .to(desc, { opacity: 1, y: 0, duration: .8 }, 1.1)
    .to(stack, { opacity: 1, duration: .6, stagger: .1, ease: "power1.out" }, 1.3)
    .to(ctas, { opacity: 1, y: 0, duration: .9, stagger: .12, clearProps: "transform" }, 1.5)
    .to(cue, { autoAlpha: 1, duration: .6 }, 1.9);
  return tl;
}

// ------------------------------------------------------------------ particles: hero only
function setupHeroField() {
  // as the hero scrolls out the sphere rises a little and fades to nothing; the loop sleeps at 0
  ScrollTrigger.create({
    trigger: "#hero", start: "top top", end: "bottom 30%",
    onUpdate: (s) => { P.cur.lift = s.progress * innerHeight * .3; P.setFade(1 - s.progress); },
    onLeave: () => P.setFade(0),
  });
  // a ripple through the dots from the hero CTA and from clicks inside the hero
  const hero = $("#hero"), cta = $(".hero__ctas .btn--primary");
  cta.addEventListener("mouseenter", () => { const r = cta.getBoundingClientRect(); P.ripple(r.left + r.width / 2, r.top + r.height / 2); });
  hero.addEventListener("pointerdown", (e) => P.ripple(e.clientX, e.clientY));
}

// ------------------------------------------------------------------ scroll reveals
function setupReveals() {
  if (reducedMotion) return;
  const st = (trigger, start = "top 86%") => ({ trigger, start, once: true });

  $$("[data-reveal]").forEach((el) =>
    gsap.from(el, { opacity: 0, y: 30, duration: .9, ease: OUT, scrollTrigger: st(el) }));

  // section headings with a thin/bold mix get the masked word rise
  $$(".abilities .h2, .privacy .h2, .sayings .h2").forEach((h) => {
    h.removeAttribute("data-reveal");
    gsap.killTweensOf(h); gsap.set(h, { clearProps: "all" });
    const ws = splitWords(h);
    gsap.from(ws, { yPercent: 110, duration: .9, stagger: .06, ease: OUT, scrollTrigger: st(h) });
  });

  // quote: each word's opacity scrubbed .15 → 1, caption after the last word
  const q = $(".quote__text p"), qw = splitWords(q, false), cap = $(".quote__cap");
  gsap.fromTo(qw, { opacity: .15 }, {
    opacity: 1, stagger: .1, ease: "none",
    scrollTrigger: { trigger: q, start: "top 75%", end: "bottom 40%", scrub: true },
  });
  gsap.fromTo(cap, { opacity: 0, y: 20 }, {
    opacity: 1, y: 0, duration: .8,
    scrollTrigger: { trigger: q, start: "bottom 40%", toggleActions: "play none none reverse" },
  });
  gsap.from(".quote__glyph", { opacity: 0, y: 40, duration: 1.2, scrollTrigger: st(".quote", "top 80%") });

  // abilities rows: border draws left → right, then icon / title / text rise
  $$(".row").forEach((row) => {
    const line = $(".row__line", row), kids = $$(".row__icon, .row__title, .row__text", row);
    gsap.set(line, { scaleX: 0 });
    gsap.set(kids, { opacity: 0, y: MOBILE ? 16 : 30 });
    ScrollTrigger.create({
      trigger: row, start: "top 88%", once: true,
      onEnter: () => gsap.timeline()
        .to(line, { scaleX: 1, duration: .8, ease: EXPO })
        .to(kids, { opacity: 1, y: 0, duration: .8, stagger: .1, ease: OUT, clearProps: "transform" }, .3),
    });
  });

  // privacy stats: each figure fades + rises into place once, always showing its final text
  gsap.from(".stat", { opacity: 0, y: 30, duration: .9, stagger: .15, ease: OUT, scrollTrigger: st(".stats", "top 82%") });

  gsap.from(".point", { opacity: 0, y: 30, duration: .8, stagger: .1, ease: OUT, clearProps: "transform,opacity", scrollTrigger: st(".points") });
  gsap.from(".sayings__viewport", { opacity: 0, y: 30, duration: 1, scrollTrigger: st(".sayings__viewport") });

  // CTA: "Say hi to Stiti." words rise like the hero
  const cw = splitWords($(".cta__title"));
  gsap.from(cw, { yPercent: 110, duration: 1, stagger: .08, ease: OUT, scrollTrigger: st(".cta__title", "top 85%") });
}

// ------------------------------------------------------------------ marquees
function setupSayingsClones() {
  const track = $(".sayings__track"), set = $(".sayings__set");
  if (reducedMotion) return;
  for (let k = 0; k < 2; k++) {
    const c = set.cloneNode(true);
    c.setAttribute("aria-hidden", "true"); c.removeAttribute("aria-label");
    track.append(c);
  }
}

function setupMarquees() {
  if (reducedMotion) return;
  const ticker = $(".ticker");
  const tk = gsap.to(".ticker__track", { xPercent: -50, duration: 28, ease: "none", repeat: -1 });
  ticker.addEventListener("mouseenter", () => gsap.to(tk, { timeScale: .25, duration: .6, ease: "power2.out", overwrite: true }));
  ticker.addEventListener("mouseleave", () => gsap.to(tk, { timeScale: 1, duration: .6, ease: "power2.out", overwrite: true }));

  const vp = $(".sayings__viewport");
  const sy = gsap.to(".sayings__track", { xPercent: -100 / 3, duration: 70, ease: "none", repeat: -1 });
  vp.addEventListener("mouseenter", () => gsap.to(sy, { timeScale: 0, duration: .5, ease: "power2.out", overwrite: true }));
  vp.addEventListener("mouseleave", () => gsap.to(sy, { timeScale: 1, duration: .5, ease: "power2.in", overwrite: true }));
}

// ------------------------------------------------------------------ anchors (smooth via Lenis)
function scrollToEl(el, instant = false) {
  if (lenis) lenis.scrollTo(el, { offset: 0, duration: instant ? 0 : 1.4, immediate: instant, easing: EXPO });
  else el.scrollIntoView({ behavior: reducedMotion || instant ? "auto" : "smooth" });
  if (!el.hasAttribute("tabindex")) el.setAttribute("tabindex", "-1");
  el.focus({ preventScroll: true });
}
function setupAnchors() {
  document.addEventListener("click", (e) => {
    const a = e.target.closest('a[href^="#"], a[href^="/#"]');
    if (!a) return;
    const id = a.getAttribute("href").replace(/^\//, "");
    const el = id.length > 1 && document.querySelector(id);
    if (!el) return;
    e.preventDefault();
    scrollToEl(el);
  });
}

// ------------------------------------------------------------------ cursor: navy dot + ring lerped at .15 (no hover morphs)
function setupCursor() {
  if (reducedMotion || !matchMedia("(hover: hover) and (pointer: fine)").matches) return;
  const c = $(".cursor"), dot = $(".cursor__dot", c), ring = $(".cursor__ring", c);
  c.hidden = false;
  html.classList.add("has-cursor");
  let x = -100, y = -100, rx = x, ry = y, shown = false;
  addEventListener("pointermove", (e) => {
    if (e.pointerType !== "mouse") return;
    x = e.clientX; y = e.clientY;
    if (!shown) { rx = x; ry = y; shown = true; c.classList.add("is-on"); }
  }, { passive: true });
  html.addEventListener("mouseleave", () => { shown = false; c.classList.remove("is-on"); });
  gsap.ticker.add(() => {
    rx += (x - rx) * .15; ry += (y - ry) * .15;
    dot.style.transform = `translate3d(${x}px, ${y}px, 0) translate(-50%, -50%)`;
    ring.style.transform = `translate3d(${rx}px, ${ry}px, 0) translate(-50%, -50%)`;
  });
}
