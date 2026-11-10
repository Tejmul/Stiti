"use client";
// Custom cursor: small navy dot + a trailing ring lerped at .15. Owner rule: it never grows, changes shape,
// shows a label or turns blue. Only on fine pointers, never with reduced motion.
import { useEffect, useRef } from "react";
import gsap from "gsap";
import { prefersReducedMotion } from "@/lib/stiti";

export default function Cursor() {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const c = ref.current!;
    if (prefersReducedMotion() || !matchMedia("(hover: hover) and (pointer: fine)").matches) return;
    const html = document.documentElement;
    const dot = c.querySelector<HTMLElement>(".cursor__dot")!, ring = c.querySelector<HTMLElement>(".cursor__ring")!;
    c.hidden = false;
    html.classList.add("landing-has-cursor");
    let x = -100, y = -100, rx = x, ry = y, shown = false;
    const onMove = (e: PointerEvent) => {
      if (e.pointerType !== "mouse") return;
      x = e.clientX; y = e.clientY;
      if (!shown) { rx = x; ry = y; shown = true; c.classList.add("is-on"); }
    };
    const onLeave = () => { shown = false; c.classList.remove("is-on"); };
    const tick = () => {
      rx += (x - rx) * .15; ry += (y - ry) * .15;
      dot.style.transform = `translate3d(${x}px, ${y}px, 0) translate(-50%, -50%)`;
      ring.style.transform = `translate3d(${rx}px, ${ry}px, 0) translate(-50%, -50%)`;
    };
    addEventListener("pointermove", onMove, { passive: true });
    html.addEventListener("mouseleave", onLeave);
    gsap.ticker.add(tick);
    return () => {
      removeEventListener("pointermove", onMove);
      html.removeEventListener("mouseleave", onLeave);
      gsap.ticker.remove(tick);
      html.classList.remove("landing-has-cursor");
      c.classList.remove("is-on");
      c.hidden = true;
    };
  }, []);

  return (
    <div ref={ref} className="cursor" aria-hidden="true" hidden>
      <div className="cursor__ring" />
      <div className="cursor__dot" />
    </div>
  );
}
