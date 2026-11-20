"use client";
// Small shared pieces of the Lessons page: icons (SVG only, 20×20, stroke = currentColor), formatters.
import type { ReactNode } from "react";
import { fmtDay, fmtTime } from "@/lib/stiti";

const S = { stroke: "currentColor", strokeWidth: 1.5, strokeLinecap: "round" as const, strokeLinejoin: "round" as const };
const ICONS: Record<string, ReactNode> = {
  board: <><rect x="3" y="3.5" width="14" height="9.5" rx="1.5" {...S} /><path d="M6 10l2.3-2.4 2 1.6L14 6M7.5 13l-1.5 3.5M12.5 13l1.5 3.5" {...S} /></>,
  file: <><path d="M5.5 3h6l3.5 3.5V16a1 1 0 0 1-1 1h-8.5a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1Z" {...S} /><path d="M11.5 3v3.5H15M7.5 10.5h5M7.5 13.5h5" {...S} /></>,
  topic: <><path d="M7.5 14.5h5M8 17h4M10 3a5 5 0 0 0-3 9c.6.5 1 1.2 1 2h4c0-.8.4-1.5 1-2a5 5 0 0 0-3-9Z" {...S} /></>,
  note: <><path d="M5 3.5h10a1 1 0 0 1 1 1v11a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1v-11a1 1 0 0 1 1-1Z" {...S} /><path d="M7 7.5h6M7 10.5h6M7 13.5h3.5" {...S} /></>,
  check: <path d="m4.5 10.5 3.5 3.5 7.5-8" {...S} />,
  close: <path d="M5.5 5.5l9 9M14.5 5.5l-9 9" {...S} />,
  search: <><circle cx="9" cy="9" r="5.5" {...S} /><path d="m13.2 13.2 3.3 3.3" {...S} /></>,
  alert: <><circle cx="10" cy="10" r="7" {...S} /><path d="M10 6.5v4.2M10 13.4v.1" {...S} /></>,
  plug: <><path d="M7 3v3.5M13 3v3.5M5.5 6.5h9V9a4.5 4.5 0 0 1-9 0V6.5ZM10 13.5V17" {...S} /></>,
  mic: <><rect x="7.5" y="2.5" width="5" height="9" rx="2.5" {...S} /><path d="M4.5 9.5a5.5 5.5 0 0 0 11 0M10 15v2.5" {...S} /></>,
  clock: <><circle cx="10" cy="10" r="7" {...S} /><path d="M10 6v4.2l2.8 1.8" {...S} /></>,
  target: <><circle cx="10" cy="10" r="7" {...S} /><circle cx="10" cy="10" r="3.5" {...S} /><path d="M10 10h.01" {...S} /></>,
  cards: <><rect x="3" y="6" width="11" height="10" rx="1.5" {...S} /><path d="M6 6V4.5a1 1 0 0 1 1-1h9a1 1 0 0 1 1 1V12a1 1 0 0 1-1 1h-2M6.5 11h4" {...S} /></>,
  map: <><path d="M3 5.5 7.5 3.5l5 2 4.5-2v11l-4.5 2-5-2L3 16.5v-11Z" {...S} /><path d="M7.5 3.5v11M12.5 5.5v11" {...S} /></>,
  play: <path d="M6.5 4.5v11l9-5.5-9-5.5Z" {...S} />,
  open: <><path d="M11 3.5h5.5V9M16.5 3.5 9.5 10.5" {...S} /><path d="M14.5 12v3.5a1 1 0 0 1-1 1h-9a1 1 0 0 1-1-1v-9a1 1 0 0 1 1-1H8" {...S} /></>,
};

export function Icon({ name, className }: { name: string; className?: string }) {
  return <svg className={`ico${className ? " " + className : ""}`} viewBox="0 0 20 20" fill="none" aria-hidden="true">{ICONS[name] ?? ICONS.file}</svg>;
}

export function Arrow() {
  return (
    <svg className="arrow" viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <path d="M3 8h9M8.5 4.5 12 8l-3.5 3.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function fmtSize(b: number): string {
  if (b >= 1e9) return `${(b / 1e9).toFixed(1)} GB`;
  if (b >= 1e6) return `${(b / 1e6).toFixed(b >= 1e7 ? 0 : 1)} MB`;
  return `${Math.max(1, Math.round(b / 1e3))} KB`;
}

export const fmtWhen = (iso: string) => { const d = new Date(iso); return `${fmtDay(d)} · ${fmtTime(d)}`; };
export const fmtDate = (iso: string) => fmtDay(new Date(iso));
