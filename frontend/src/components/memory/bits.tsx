"use client";
// Small shared pieces of the Memory page: section shell (one-time reveal), empty state, arrow, jump + flash.
import Link from "next/link";
import { useEffect, useRef, type ReactNode } from "react";
import { prefersReducedMotion } from "@/lib/stiti";

/** Fact groups, in the order the page and the map show them (same names as mind.py GROUPS + "Other"). */
export const FACT_GROUPS = ["Work", "Study", "Projects", "Skills", "Ventures", "Life", "Other"];

export function Arrow() {
  return (
    <svg className="arrow" viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <path d="M3 8h9M8.5 4.5 12 8l-3.5 3.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

/** Scroll a row/card/section into view and give it one soft highlight so the eye lands on it. */
export function jump(href: string) {
  const target = document.querySelector<HTMLElement>(href);
  if (!target) return;
  target.scrollIntoView({ behavior: prefersReducedMotion() ? "auto" : "smooth", block: "center" });
  if (target.matches(".row, .card, .habit")) {
    target.classList.remove("is-flash");
    void target.offsetWidth;                 // restart the flash if it was already running
    target.classList.add("is-flash");
    window.setTimeout(() => target.classList.remove("is-flash"), 2200);
  }
}

/** A page section: heading with thin + bold words, a note, and a one-time rise-in when it first scrolls into view. */
export function Section({ id, thin, bold, note, children }: {
  id: string; thin: string; bold: string; note: ReactNode; children: ReactNode;
}) {
  const ref = useRef<HTMLElement>(null);
  useEffect(() => {
    const el = ref.current!;
    const io = new IntersectionObserver((ents) => {
      if (ents.some((e) => e.isIntersecting)) { el.classList.add("is-in"); io.disconnect(); }
    }, { rootMargin: "0px 0px -8% 0px" });
    io.observe(el);
    return () => io.disconnect();
  }, []);
  return (
    <section ref={ref} className="sec" id={id} aria-labelledby={`${id}-h`} tabIndex={-1}>
      <div className="sec__head">
        <h2 id={`${id}-h`}><span className="thin">{thin}</span> <span className="bold">{bold}</span></h2>
        <p className="sec__note">{note}</p>
      </div>
      {children}
    </section>
  );
}

/** Empty state that looks deliberate: what's missing, why it matters, and exact phrases to say. */
export function Empty({ children, say, cta = true }: { children: ReactNode; say?: string[]; cta?: boolean }) {
  return (
    <div className="empty">
      <p className="empty__text">{children}</p>
      {say && say.length > 0 && (
        <div className="empty__try">
          <span className="label">Try saying</span>
          <ul className="empty__phrases">
            {say.map((s) => <li key={s}><q>{s}</q></li>)}
          </ul>
        </div>
      )}
      {cta && say && say.length > 0 && (
        <Link className="link-arrow" href="/chat">Say it in Chat <Arrow /></Link>
      )}
    </div>
  );
}
