"use client";
// Stiti landing — Lenis smooth scroll + GSAP/ScrollTrigger: sphere bloom intro, hero timeline, hero-only particles
// (an ambient halo behind the product shot), one-time scroll reveals, smooth anchors. Everything below the hero is
// still and clean (owner rule); reduced motion = no motion.
// No redirect to /chat anywhere here (the original had none either): the landing always stays the landing.
import { useEffect, useRef } from "react";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import Lenis from "lenis";
import Nav from "@/components/Nav";
import { prefersReducedMotion } from "@/lib/stiti";
import { createField } from "./particles";
import { EXPO, OUT } from "./ease";
import Cursor from "./Cursor";
import { Hero, SeeHer, Features, Day, Privacy, Faq, Footer } from "./Sections";

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
    // capture phase on window, so it runs before next/link's handler (the nav's "/#features" links)
    on<MouseEvent>(window, "click", (e) => {
      if (e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
      const a = (e.target as Element | null)?.closest?.('a[href^="#"], a[href^="/#"]');
      if (!a) return;
      const el = byHash(a.getAttribute("href")!.replace(/^\//, ""));
      if (!el) return;
      e.preventDefault();
      e.stopPropagation();
      if (body.classList.contains("menu-open")) {
        dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));  // Nav closes on Esc
        lenis?.start();                                                    // (it was stopped while the menu was open)
      }
      scrollToEl(el);
    }, { capture: true });

    // the neural sphere sits in its own place on the hero's right (owner liked it there); the Mac shot lives
    // further down in "See her at work", without particles

    let alive = true;
    const ctx = gsap.context(() => {
      // -------------------------------------------------------------- hero timeline (fade/rise only)
      const tl = gsap.timeline({ paused: true, defaults: { ease: OUT } });
      if (!reduced) {
        const label = $(".hero__label-text");
        const lines = $$(".hero__title .line").map((l) => $$(".w", l));
        const rest = [$(".hero__quote"), $(".hero__ctas"), $(".hero__facts")];
        gsap.set(label, { opacity: 0, y: 20 });
        lines.forEach((ws) => gsap.set(ws, { yPercent: 110 }));
        gsap.set(rest, { opacity: 0, y: 24 });

        tl.to(label, { opacity: 1, y: 0, duration: .6 }, 0);
        lines.forEach((ws, i) => tl.to(ws, { yPercent: 0, duration: .9, stagger: .08, ease: OUT }, .1 + i * .18));
        tl.to(rest, { opacity: 1, y: 0, duration: .9, stagger: .12, clearProps: "transform" }, .8);
      }

      // -------------------------------------------------------------- particles: hero only
      // as the hero scrolls out the sphere rises and fades to nothing; the loop sleeps at 0
      const hero = $("#hero"), cta = $(".hero__ctas .btn--primary");
      ScrollTrigger.create({
        trigger: hero, start: "top top", end: "bottom 30%",
        onUpdate: (s) => field.setFade(1 - s.progress),
        onLeave: () => field.setFade(0),
      });
      // a ripple through the dots from the hero CTA and from clicks inside the hero
      on(cta, "mouseenter", () => { const r = cta.getBoundingClientRect(); field.ripple(r.left + r.width / 2, r.top + r.height / 2); });
      on<PointerEvent>(hero, "pointerdown", (e) => field.ripple(e.clientX, e.clientY));

      if (!reduced) {
        // ------------------------------------------------------------ scroll reveals (one time, still afterwards)
        const st = (trigger: Element | string, start = "top 88%") => ({ trigger, start, once: true });
        $$("[data-reveal]").forEach((el) =>
          gsap.from(el, { opacity: 0, y: MOBILE ? 18 : 28, duration: .9, ease: OUT, clearProps: "transform", scrollTrigger: st(el) }));
        // headings with a thin/bold mix get the masked word rise
        $$("main .h2, .foot__title").forEach((h) =>
          gsap.from($$(".w", h), { yPercent: 110, duration: .9, stagger: .06, ease: OUT, scrollTrigger: st(h) }));
      }

      // -------------------------------------------------------------- intro: the sphere blooms out of Stiti's orb
      // (no preloader screen — owner: "the 100% loading animation is the worst")
      const afterLoad = () => {
        tl.play();
        const el = byHash(location.hash);
        if (el) scrollToEl(el, true);
      };
      loading = false;
      if (reduced) {
        canvas.style.opacity = "1";
      } else {
        const orb = $(".pill__orb").getBoundingClientRect();
        field.intro(orb.left + orb.width / 2, orb.top + orb.height / 2);
        gsap.to(canvas, { opacity: 1, duration: 1, ease: "power1.out" });
      }
      afterLoad();
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
      html.classList.remove("landing-page");
      history.scrollRestoration = prevRestoration;
      canvas.style.opacity = "";
    };
  }, []);

  return (
    <div className="pg-landing" ref={rootRef}>
      <canvas className="field" aria-hidden="true" />
      <Cursor />
      <Nav current="home" />
      <main id="main" tabIndex={-1}>
        <Hero />
        <SeeHer />
        <Features />
        <Day />
        <Privacy />
        <Faq />
      </main>
      <Footer />
    </div>
  );
}
