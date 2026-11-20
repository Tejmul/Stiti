"use client";
// The in-app navbar for Stiti's own pages on this Mac (Chat, Memory). Same white liquid-glass pill as the site
// nav (owner rule: clear white glass, never grey/dark) — but app tabs instead of the landing's Features/FAQ links.
// Always visible (an app bar, not a marketing bar); pointer sheen follows the cursor. Never in the public build:
// only ChatApp / MemoryPage import it, and those are swapped out by private-pages.public.tsx.
import Link from "next/link";
import { useRef, type ReactNode } from "react";
import { Logo } from "@/components/Nav";
import "./app.css";

type Tab = "chat" | "memory";

function ChatIcon() {
  return (
    <svg viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <path d="M4 5.5A2.5 2.5 0 0 1 6.5 3h7A2.5 2.5 0 0 1 16 5.5v5a2.5 2.5 0 0 1-2.5 2.5H9l-3.5 3v-3A2.5 2.5 0 0 1 4 10.5v-5Z"
        stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
    </svg>
  );
}

function MemoryIcon() {
  return (
    <svg viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <circle cx="10" cy="10" r="2.2" stroke="currentColor" strokeWidth="1.5" />
      <circle cx="4.5" cy="5" r="1.6" stroke="currentColor" strokeWidth="1.5" />
      <circle cx="15.5" cy="5.5" r="1.6" stroke="currentColor" strokeWidth="1.5" />
      <circle cx="14.5" cy="15.5" r="1.6" stroke="currentColor" strokeWidth="1.5" />
      <path d="M5.7 6.1 8.3 8.6M14.3 6.6l-2.6 2M13.4 14.3l-2-2.4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  );
}

const TABS: { id: Tab; href: string; label: string; icon: ReactNode }[] = [
  { id: "chat", href: "/chat", label: "Chat", icon: <ChatIcon /> },
  { id: "memory", href: "/memory", label: "Memory", icon: <MemoryIcon /> },
];

/** `end` goes after the "On this Mac" chip (e.g. the chat page's "Today" toggle on small screens). */
export default function AppNav({ current, end }: { current: Tab; end?: ReactNode }) {
  const nav = useRef<HTMLElement>(null);
  const sheen = (e: React.PointerEvent) => {
    const r = nav.current!.getBoundingClientRect();
    nav.current!.style.setProperty("--mx", `${e.clientX - r.left}px`);
    nav.current!.style.setProperty("--my", `${e.clientY - r.top}px`);
  };

  return (
    <>
      <a className="skip" href="#main">Skip to content</a>
      <nav ref={nav} className="nav appnav" aria-label="Stiti" onPointerMove={sheen}>
        <Link className="nav__logo" href="/" aria-label="Stiti home"><Logo /></Link>
        <div className="appnav__tabs">
          {TABS.map((t) => (
            <Link key={t.id} href={t.href} className="appnav__tab" aria-current={t.id === current ? "page" : undefined}>
              {t.icon}<span>{t.label}</span>
            </Link>
          ))}
        </div>
        <span className="appnav__local" title="Everything on these pages is stored on this Mac, in ~/.stiti">
          <span className="appnav__dot" aria-hidden="true" />On this Mac
        </span>
        {end}
      </nav>
    </>
  );
}
