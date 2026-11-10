"use client";
// Stiti landing — motion ported from the original static/js/landing.js: Lenis smooth scroll + GSAP/ScrollTrigger,
// preloader (counter → logo dot collapses → sphere blooms), hero timeline, hero-only particles, scroll reveals,
// marquees, smooth anchors. Everything below the hero is still and clean (owner rule); reduced motion = no motion.
// No redirect to /chat anywhere here (the original had none either): the landing always stays the landing.
import { useEffect, useRef } from "react";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import Lenis from "lenis";
import Nav from "@/components/Nav";
import { prefersReducedMotion } from "@/lib/stiti";
import { createField } from "./particles";
import { EXPO, OUT } from "./ease";
import Preloader from "./Preloader";
import Cursor from "./Cursor";
import { Hero, Body, Footer } from "./Sections";

export default function Landing() {
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const root = rootRef.current!;
    const html = document.documentElement, body = document.body;
    const reduced = prefersReducedMotion();
    const MOBILE = matchMedia("(max-width: 760px)").matches;
    const $ = <T extends Element = HTMLElement>(s: string, r: ParentNode = root) => r.querySelector<T>(s)!;
    const $$ = <T extends Element = HTMLElement>(s: string, r: ParentNode = root) => [...r.querySelectorAll<T>(s)];
    gsap.registerPlugin(ScrollTrigger);

    const offs: (() => void)[] = [];
    const on = <E extends Event>(t: EventTarget, type: string, fn: (e: E) => void, opts?: AddEventListenerOptions) => {
      t.addEventListener(type, fn as EventListener, opts);
      offs.push(() => t.removeEventListener(type, fn as EventListener, opts));
    };

    // ---------------------------------------------------------------- boot
    const prevRestoration = history.scrollRestoration;
    history.scrollRestoration = "manual";
    html.classList.add("landing-page");
    const canvas = $<HTMLCanvasElement>("canvas.field");
    const field = createField(canvas);
    let loading = !reduced;

    let lenis: Lenis | null = null;
    const lenisTick = (t: number) => lenis?.raf(t * 1000);
    if (!reduced) {
      lenis = new Lenis({ lerp: .1 });
      lenis.on("scroll", ScrollTrigger.update);
      gsap.ticker.add(lenisTick);
      gsap.ticker.lagSmoothing(0);
    }

    // mobile menu (owned by <Nav>, which toggles body.menu-open): dim the sphere and pause smooth scroll
    const mo = new MutationObserver(() => {
      const open = body.classList.contains("menu-open");
      field.dim(open ? .15 : 1);
      if (open) lenis?.stop(); else if (!loading) lenis?.start();
    });
    mo.observe(body, { attributes: true, attributeFilter: ["class"] });

    // ---------------------------------------------------------------- anchors (smooth via Lenis)
    const scrollToEl = (el: HTMLElement, instant = false) => {
      if (lenis) lenis.scrollTo(el, { offset: 0, duration: instant ? 0 : 1.4, immediate: instant, easing: EXPO });
      else el.scrollIntoView({ behavior: reduced || instant ? "auto" : "smooth" });
      if (!el.hasAttribute("tabindex")) el.setAttribute("tabindex", "-1");
      el.focus({ preventScroll: true });
    };
    const byHash = (h: string) => (/^#[\w-]+$/.test(h) ? document.getElementById(h.slice(1)) : null);
    // capture phase on window, so it runs before next/link's handler (the nav's "/#abilities" links)
    on<MouseEvent>(window, "click", (e) => {
      if (e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
      const a = (e.target as Element | null)?.closest?.('a[href^="#"], a[href^="/#"]');
      if (!a) return;
      const el = byHash(a.getAttribute("href")!.replace(/^\//, ""));
      if (!el) return;
      e.preventDefault();
      e.stopPropagation();
      if (body.classList.contains("menu-open")) dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));  // Nav closes on Esc
      scrollToEl(el);
    }, { capture: true });

    let alive = true;
    const ctx = gsap.context(() => {
      // -------------------------------------------------------------- hero timeline
      const tl = gsap.timeline({ paused: true, defaults: { ease: OUT } });
      if (!reduced) {
        const label = $(".hero__label-text");
        const lines = $$(".hero__title .line").map((l) => $$(".w", l));
        const strip = $(".hero__strip"), desc = $(".hero__desc"), stack = $$(".hero__stack li");
        const ctas = $$(".hero__ctas .btn"), cue = $(".hero__cue");
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
      }

      // -------------------------------------------------------------- particles: hero only
      // as the hero scrolls out the sphere rises a little and fades to nothing; the loop sleeps at 0
      const hero = $("#hero"), cta = $(".hero__ctas .btn--primary");
      ScrollTrigger.create({
        trigger: hero, start: "top top", end: "bottom 30%",
        onUpdate: (s) => { field.cur.lift = s.progress * innerHeight * .3; field.setFade(1 - s.progress); },
        onLeave: () => field.setFade(0),
      });
      // a ripple through the dots from the hero CTA and from clicks inside the hero
      on(cta, "mouseenter", () => { const r = cta.getBoundingClientRect(); field.ripple(r.left + r.width / 2, r.top + r.height / 2); });
      on<PointerEvent>(hero, "pointerdown", (e) => field.ripple(e.clientX, e.clientY));

      if (!reduced) {
        // ------------------------------------------------------------ scroll reveals
        const st = (trigger: Element | string, start = "top 86%") => ({ trigger, start, once: true });

        $$("[data-reveal]").forEach((el) =>
          gsap.from(el, { opacity: 0, y: 30, duration: .9, ease: OUT, scrollTrigger: st(el) }));

        // section headings with a thin/bold mix get the masked word rise
        $$(".abilities .h2, .privacy .h2, .sayings .h2").forEach((h) =>
          gsap.from($$(".w", h), { yPercent: 110, duration: .9, stagger: .06, ease: OUT, scrollTrigger: st(h) }));

        // quote: each word's opacity scrubbed .15 → 1, caption after the last word
        const q = $(".quote__text p"), cap = $(".quote__cap");
        gsap.fromTo($$(".w", q), { opacity: .15 }, {
          opacity: 1, stagger: .1, ease: "none",
          scrollTrigger: { trigger: q, start: "top 75%", end: "bottom 40%", scrub: true },
        });
        gsap.fromTo(cap, { opacity: 0, y: 20 }, {
          opacity: 1, y: 0, duration: .8, ease: OUT,
          scrollTrigger: { trigger: q, start: "bottom 40%", toggleActions: "play none none reverse" },
        });
        gsap.from($(".quote__glyph"), { opacity: 0, y: 40, duration: 1.2, ease: OUT, scrollTrigger: st($(".quote"), "top 80%") });

        // abilities rows: border draws left → right, then icon / title / text rise
        $$(".row").forEach((row) => {
          const line = $(".row__line", row), kids = $$(".row__icon, .row__title, .row__text", row);
          gsap.set(line, { scaleX: 0 });
          gsap.set(kids, { opacity: 0, y: MOBILE ? 16 : 30 });
          ScrollTrigger.create({
            trigger: row, start: "top 88%", once: true,
            onEnter: () => { gsap.timeline()
              .to(line, { scaleX: 1, duration: .8, ease: EXPO })
              .to(kids, { opacity: 1, y: 0, duration: .8, stagger: .1, ease: OUT, clearProps: "transform" }, .3); },
          });
        });

        // privacy stats: each figure fades + rises into place once, always showing its final text
        gsap.from($$(".stat"), { opacity: 0, y: 30, duration: .9, stagger: .15, ease: OUT, scrollTrigger: st($(".stats"), "top 82%") });
        gsap.from($$(".point"), { opacity: 0, y: 30, duration: .8, stagger: .1, ease: OUT, clearProps: "transform,opacity", scrollTrigger: st($(".points")) });
        gsap.from($(".sayings__viewport"), { opacity: 0, y: 30, duration: 1, ease: OUT, scrollTrigger: st($(".sayings__viewport")) });

        // CTA: "Say hi to Stiti." words rise like the hero
        const ct = $(".cta__title");
        gsap.from($$(".w", ct), { yPercent: 110, duration: 1, stagger: .08, ease: OUT, scrollTrigger: st(ct, "top 85%") });

        // ------------------------------------------------------------ marquees
        const ticker = $(".ticker");
        const tk = gsap.to($(".ticker__track"), { xPercent: -50, duration: 28, ease: "none", repeat: -1 });
        on(ticker, "mouseenter", () => gsap.to(tk, { timeScale: .25, duration: .6, ease: "power2.out", overwrite: true }));
        on(ticker, "mouseleave", () => gsap.to(tk, { timeScale: 1, duration: .6, ease: "power2.out", overwrite: true }));

        const vp = $(".sayings__viewport");
        const sy = gsap.to($(".sayings__track"), { xPercent: -100 / 3, duration: 70, ease: "none", repeat: -1 });
        on(vp, "mouseenter", () => gsap.to(sy, { timeScale: 0, duration: .5, ease: "power2.out", overwrite: true }));
        on(vp, "mouseleave", () => gsap.to(sy, { timeScale: 1, duration: .5, ease: "power2.in", overwrite: true }));
      }

      // -------------------------------------------------------------- preloader (0 → 2.4 s), then the hero plays
      const afterLoad = () => {
        tl.play();
        const el = byHash(location.hash);
        if (el) scrollToEl(el, true);
      };
      const loader = $(".loader");
      if (reduced) {
        loader.style.display = "none";
        canvas.style.opacity = "1";
        afterLoad();
        return;
      }
      scrollTo(0, 0);
      html.classList.add("landing-loading");
      lenis?.stop();
      const num = $(".loader__num"), line = $(".loader__line"), logo = $(".loader__logo");
      const o = { v: 0 };
      gsap.timeline()
        .fromTo(logo, { opacity: 0, scale: .8 }, { opacity: 1, scale: 1, duration: 1.2, ease: OUT }, 0)
        .to(o, { v: 100, duration: 1.8, ease: "power2.inOut", onUpdate: () => { num.textContent = String(Math.round(o.v)).padStart(3, "0") + "%"; } }, 0)
        .fromTo(line, { scaleX: 0 }, { scaleX: 1, duration: 1.8, ease: "power2.inOut" }, 0)
        .to([num, line], { opacity: 0, y: -40, duration: .4, ease: OUT }, 1.8)
        // handoff: the logo's dot collapses and the sphere blooms out of that exact point
        .to(logo, { scale: .25, opacity: 0, duration: .35, ease: EXPO }, 1.72)
        .add(() => field.intro(innerWidth / 2, innerHeight / 2), 2.15)
        .to(canvas, { opacity: 1, duration: 1, ease: "power1.out" }, 1.75)
        .to(loader, { yPercent: -100, duration: .9, ease: EXPO }, 2.0)
        .add(() => { html.classList.remove("landing-loading"); loading = false; lenis?.start(); afterLoad(); }, 2.4)
        .add(() => { loader.style.display = "none"; }, 2.95);
    }, root);

    document.fonts?.ready.then(() => { if (alive) ScrollTrigger.refresh(); });

    return () => {
      alive = false;
      ctx.revert();
      offs.forEach((off) => off());
      mo.disconnect();
      field.destroy();
      if (lenis) {
        gsap.ticker.remove(lenisTick);
        lenis.destroy();
        // Lenis 1.3.4 leaves a pending 400 ms velocity-reset timer that re-adds "lenis" classes to <html> after
        // destroy (seen when navigating to /chat right after a scroll) — clear it.
        const t = (lenis as unknown as { _resetVelocityTimeout?: ReturnType<typeof setTimeout> | null })._resetVelocityTimeout;
        if (t) clearTimeout(t);
        gsap.ticker.lagSmoothing(500, 33);
      }
      html.classList.remove("landing-loading", "landing-page");
      history.scrollRestoration = prevRestoration;
      const loader = $(".loader"), num = $(".loader__num");
      loader.style.display = "";
      num.textContent = "000%";
      canvas.style.opacity = "";
    };
  }, []);

  return (
    <div className="pg-landing" ref={rootRef}>
      <Preloader />
      <canvas className="field" aria-hidden="true" />
      <Cursor />
      <Nav current="home" />
      <main id="main" tabIndex={-1}>
        <Hero />
        <Body />
      </main>
      <Footer />
    </div>
  );
}
