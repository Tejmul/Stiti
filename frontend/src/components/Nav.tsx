"use client";
// The white liquid-glass pill navbar (owner rule: clear white glass, never grey/dark), shared by every page.
// Hides on scroll down, returns on scroll up; pointer sheen follows the cursor; full-screen menu on mobile.
import Link from "next/link";
import { useEffect, useRef, useState, type ReactNode } from "react";

type Page = "home" | "chat" | "memory";
// The deployed marketing site (STITI_PUBLIC=1 build) has no Chat/Memory — those exist only on the owner's Mac.
const PUBLIC = process.env.NEXT_PUBLIC_STITI_PUBLIC === "1";
const GITHUB = "https://github.com/Tejmul/Stiti";
const ALL_LINKS: { href: string; label: string; page?: Page }[] = [
  { href: "/chat", label: "Chat", page: "chat" },
  { href: "/memory", label: "Memory", page: "memory" },
  { href: "/#abilities", label: "Abilities" },
  { href: "/#privacy", label: "Privacy" },
];
const LINKS = PUBLIC ? ALL_LINKS.filter((l) => !l.page) : ALL_LINKS;

export function Logo() {
  // A plain letter mark (the old dot-in-a-tilted-ring read as an eye).
  return <span className="nav__mark" aria-hidden="true">S</span>;
}

/** `cta` replaces the right-hand button (e.g. the chat page's "Today" toggle). */
export default function Nav({ current, cta }: { current?: Page; cta?: ReactNode }) {
  const nav = useRef<HTMLElement>(null);
  const [open, setOpen] = useState(false);
  const [hidden, setHidden] = useState(false);

  useEffect(() => {
    let last = scrollY;
    const onScroll = () => {
      const y = scrollY;
      if (Math.abs(y - last) < 6) return;
      setHidden(y > last && y > 120);
      last = y;
    };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    addEventListener("scroll", onScroll, { passive: true });
    addEventListener("keydown", onKey);
    return () => { removeEventListener("scroll", onScroll); removeEventListener("keydown", onKey); };
  }, []);

  useEffect(() => { document.body.classList.toggle("menu-open", open); }, [open]);

  const sheen = (e: React.PointerEvent) => {
    const r = nav.current!.getBoundingClientRect();
    nav.current!.style.setProperty("--mx", `${e.clientX - r.left}px`);
    nav.current!.style.setProperty("--my", `${e.clientY - r.top}px`);
  };

  return (
    <>
      <a className="skip" href="#main">Skip to content</a>
      <nav ref={nav} className={`nav${hidden && !open ? " is-hidden" : ""}`} aria-label="Main" onPointerMove={sheen}>
        <Link className="nav__logo" href="/" aria-label="Stiti home"><Logo /></Link>
        <div className="nav__links">
          {LINKS.map((l) => (
            <Link key={l.href} className="nav__link" href={l.href} aria-current={l.page && l.page === current ? "page" : undefined}>
              {l.label}
            </Link>
          ))}
        </div>
        <button className="nav__menu-btn" type="button" aria-expanded={open} aria-controls="menu" onClick={() => setOpen(!open)}>
          {open ? "CLOSE" : "MENU"}
        </button>
        {cta ?? (PUBLIC
          ? <a className="nav__cta" href={GITHUB} target="_blank" rel="noopener">GitHub</a>
          : <Link className="nav__cta" href="/chat">Talk to Stiti</Link>)}
      </nav>
      <div className={`menu${open ? " is-open" : ""}`} id="menu" aria-label="Menu">
        <div className="menu__links">
          {LINKS.map((l, i) => (
            <Link key={l.href} href={l.href} onClick={() => setOpen(false)}>
              <span style={{ transitionDelay: open ? `${i * 70}ms` : "0ms" }}>{l.label}</span>
            </Link>
          ))}
        </div>
        <div className="menu__foot">Runs on your Mac · Your memory stays at ~/.stiti</div>
      </div>
    </>
  );
}
