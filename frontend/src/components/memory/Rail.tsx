"use client";
// Sticky section rail (wrapped chips on mobile). The section in the middle band of the screen is highlighted.
import { useEffect, useState } from "react";
import { prefersReducedMotion } from "@/lib/stiti";

export type RailItem = { id: string; label: string; n?: number };

export default function Rail({ items }: { items: RailItem[] }) {
  const [here, setHere] = useState(items[0]?.id);
  const ids = items.map((i) => i.id).join(",");

  // The highlighted section is the last one whose top has passed 30% of the viewport (first one at the top,
  // last one at the very bottom). Measured on scroll, at most once per frame.
  useEffect(() => {
    const list = ids.split(",");
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

  const go = (e: React.MouseEvent, id: string) => {
    const el = document.getElementById(id);
    if (!el) return;
    e.preventDefault();
    el.scrollIntoView({ behavior: prefersReducedMotion() ? "auto" : "smooth", block: "start" });
    el.focus({ preventScroll: true });                     // keyboard users continue from the section they chose
    setHere(id);
  };

  return (
    <nav className="rail" aria-label="Memory sections">
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
