"use client";
// Sticky section rail (a sticky, sideways-scrolling strip on small screens). The section in the upper band of the
// screen is highlighted; on the strip, the highlighted chip is kept in view.
import { useEffect, useRef, useState } from "react";
import { prefersReducedMotion } from "@/lib/stiti";

export type RailItem = { id: string; label: string; n?: number };

export default function Rail({ items }: { items: RailItem[] }) {
  const [here, setHere] = useState(items[0]?.id);
  const ref = useRef<HTMLElement>(null);
  const ids = items.map((i) => i.id).join(",");

  // The highlighted section is the last one whose top has passed 30% of the viewport (first one at the top,
  // last one at the very bottom). Measured on scroll, at most once per frame.
  useEffect(() => {
    const list = ids.split(",").filter(Boolean);
    let raf = 0;
    const measure = () => {
      raf = 0;
      const line = innerHeight * 0.3;
      let cur = list[0];
      for (const id of list) {
        const el = document.getElementById(id);
        if (el && el.getBoundingClientRect().top <= line) cur = id;
      }
      if (innerHeight + scrollY >= document.documentElement.scrollHeight - 4) cur = list[list.length - 1];
      setHere(cur);
    };
    const onScroll = () => { if (!raf) raf = requestAnimationFrame(measure); };
    addEventListener("scroll", onScroll, { passive: true });
    addEventListener("resize", onScroll);
    onScroll();
    return () => { removeEventListener("scroll", onScroll); removeEventListener("resize", onScroll); cancelAnimationFrame(raf); };
  }, [ids]);

  // On the horizontal strip, keep the current chip visible (scrolls the strip only, never the page).
  useEffect(() => {
    const strip = ref.current;
    const a = strip?.querySelector<HTMLElement>(".is-here");
    if (!strip || !a || strip.scrollWidth <= strip.clientWidth) return;
    const left = a.offsetLeft - 16, right = a.offsetLeft + a.offsetWidth + 16;
    if (left < strip.scrollLeft) strip.scrollTo({ left, behavior: "smooth" });
    else if (right > strip.scrollLeft + strip.clientWidth) strip.scrollTo({ left: right - strip.clientWidth, behavior: "smooth" });
  }, [here]);

  const go = (e: React.MouseEvent, id: string) => {
    const el = document.getElementById(id);
    if (!el) return;
    e.preventDefault();
    el.scrollIntoView({ behavior: prefersReducedMotion() ? "auto" : "smooth", block: "start" });
    el.focus({ preventScroll: true });                     // keyboard users continue from the section they chose
    setHere(id);
  };

  return (
    <nav ref={ref} className="rail" aria-label="Memory sections">
      <p className="label rail__h">On this page</p>
      {items.map((it) => (
        <a key={it.id} href={`#${it.id}`} className={here === it.id ? "is-here" : undefined}
          aria-current={here === it.id ? "location" : undefined} onClick={(e) => go(e, it.id)}>
          <span>{it.label}</span>
          {it.n ? <span className="rail__n">{it.n}</span> : null}
        </a>
      ))}
    </nav>
  );
}
