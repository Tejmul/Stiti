"use client";
// Small shared pieces of the Memory page: section shell, empty state, search highlight, icons, jump + flash.
import Link from "next/link";
import { Fragment, type ReactNode } from "react";
import { prefersReducedMotion } from "@/lib/stiti";

/** Fact groups, in the order the page shows them (same names as mind.py GROUPS + "Other"). */
export const FACT_GROUPS = ["Work", "Study", "Projects", "Skills", "Ventures", "Life", "Other"];

/** Does `text` contain the search query? An empty query matches everything. */
export function has(q: string, ...texts: (string | null | undefined)[]) {
  if (!q) return true;
  const n = q.toLowerCase();
  return texts.some((t) => t && t.toLowerCase().includes(n));
}

/** Text with the search query marked (case-insensitive, plain <mark>, no effects). */
export function Hi({ text, q }: { text: string; q: string }) {
  if (!q) return <>{text}</>;
  const esc = q.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const parts = text.split(new RegExp(`(${esc})`, "ig"));
  return <>{parts.map((p, i) => (i % 2 ? <mark key={i}>{p}</mark> : <Fragment key={i}>{p}</Fragment>))}</>;
}

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
  if (target.matches(".row, .card")) {
    target.classList.remove("is-flash");
    void target.offsetWidth;                 // restart the flash if it was already running
    target.classList.add("is-flash");
    window.setTimeout(() => target.classList.remove("is-flash"), 2200);
  }
}

/** A page section: heading with thin + bold words, a count, a one-line note. Still — no entrance motion. */
export function Section({ id, thin, bold, n, note, aside, children }: {
  id: string; thin: string; bold: string; n?: number; note?: ReactNode; aside?: ReactNode; children: ReactNode;
}) {
  return (
    <section className="sec" id={id} aria-labelledby={`${id}-h`} tabIndex={-1}>
      <header className="sec__head">
        <div>
          <h2 id={`${id}-h`}>
            <span className="thin">{thin}</span> <span className="bold">{bold}</span>
            {n != null && n > 0 && <span className="sec__n">{n}</span>}
          </h2>
          {note && <p className="sec__note">{note}</p>}
        </div>
        {aside}
      </header>
      {children}
    </section>
  );
}

/** Empty state that looks deliberate: what's missing, why it matters, and exact phrases to say. */
export function Empty({ children, say, cta = true, small }: { children: ReactNode; say?: string[]; cta?: boolean; small?: boolean }) {
  return (
    <div className={`empty${small ? " empty--small" : ""}`}>
      <p className="empty__text">{children}</p>
      {say && say.length > 0 && (
        <ul className="empty__phrases" aria-label="Try saying">
          {say.map((s) => <li key={s}><q>{s}</q></li>)}
        </ul>
      )}
      {cta && say && say.length > 0 && (
        <Link className="link-arrow" href="/chat">Say it in Chat <Arrow /></Link>
      )}
    </div>
  );
}

// ---- icons (SVG only, 20×20, stroke = currentColor)
const S = { stroke: "currentColor", strokeWidth: 1.5, strokeLinecap: "round" as const, strokeLinejoin: "round" as const };
const ICONS: Record<string, ReactNode> = {
  person: <><circle cx="10" cy="7" r="3" {...S} /><path d="M4 16.5c.8-3 3.2-4.5 6-4.5s5.2 1.5 6 4.5" {...S} /></>,
  org: <><path d="M4 16.5V5l6-2v13.5M10 7h6v9.5M3 16.5h14" {...S} /><path d="M6.5 7.5h1M6.5 10.5h1M12.5 10h1M12.5 13h1" {...S} /></>,
  project: <><path d="M3.5 6.5h5l1.5 2h6.5v7a1 1 0 0 1-1 1H4.5a1 1 0 0 1-1-1v-9Z" {...S} /><path d="M3.5 6.5v-2a1 1 0 0 1 1-1h3.5l1.5 2" {...S} /></>,
  place: <><path d="M10 17s5-4.6 5-8.5a5 5 0 0 0-10 0C5 12.4 10 17 10 17Z" {...S} /><circle cx="10" cy="8.5" r="1.8" {...S} /></>,
  thing: <><path d="m10 3 6.5 3.5v7L10 17l-6.5-3.5v-7L10 3Z" {...S} /><path d="M3.5 6.5 10 10l6.5-3.5M10 10v7" {...S} /></>,
  search: <><circle cx="9" cy="9" r="5.5" {...S} /><path d="m13.2 13.2 3.3 3.3" {...S} /></>,
  close: <path d="M5.5 5.5l9 9M14.5 5.5l-9 9" {...S} />,
  check: <path d="m4.5 10.5 3.5 3.5 7.5-8" {...S} />,
  bell: <><path d="M5.5 13.5V9a4.5 4.5 0 0 1 9 0v4.5l1.5 1.5H4l1.5-1.5Z" {...S} /><path d="M8.5 17h3" {...S} /></>,
  book: <><path d="M4 4.5h4.5A1.5 1.5 0 0 1 10 6v10a1.5 1.5 0 0 0-1.5-1.5H4v-10ZM16 4.5h-4.5A1.5 1.5 0 0 0 10 6v10a1.5 1.5 0 0 1 1.5-1.5H16v-10Z" {...S} /></>,
  file: <><path d="M5.5 3h6l3.5 3.5V16a1 1 0 0 1-1 1h-8.5a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1Z" {...S} /><path d="M11.5 3v3.5H15M7.5 10.5h5M7.5 13.5h5" {...S} /></>,
  alert: <><circle cx="10" cy="10" r="7" {...S} /><path d="M10 6.5v4.2M10 13.4v.1" {...S} /></>,
  plug: <><path d="M7 3v3.5M13 3v3.5M5.5 6.5h9V9a4.5 4.5 0 0 1-9 0V6.5ZM10 13.5V17" {...S} /></>,
};
export function Icon({ name, className }: { name: string; className?: string }) {
  return <svg className={`ico${className ? " " + className : ""}`} viewBox="0 0 20 20" fill="none" aria-hidden="true">{ICONS[name] ?? ICONS.thing}</svg>;
}
