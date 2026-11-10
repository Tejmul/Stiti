"use client";
// Memory receipts: what Stiti's own brain handed the LLM for this reply (memories, facts, files, lessons).
// Native <details> so it's keyboard accessible for free; the reveal is CSS (::details-content).
import type { Used } from "@/lib/stiti";

const cut = (s: string, n = 140) => (s.length > n ? s.slice(0, n).replace(/\s+\S*$/, "") + "…" : s);

function relDay(iso: string): string {
  const d = new Date(iso);
  if (isNaN(+d)) return "";
  const a = new Date(); a.setHours(0, 0, 0, 0);
  const b = new Date(d); b.setHours(0, 0, 0, 0);
  const days = Math.round((+a - +b) / 864e5);
  if (days <= 0) return "today";
  if (days === 1) return "yesterday";
  if (days < 7) return `${days} days ago`;
  if (days < 35) return `${Math.round(days / 7)} wk ago`;
  return d.toLocaleDateString([], { month: "short", year: d.getFullYear() === a.getFullYear() ? undefined : "numeric", day: "numeric" });
}

export default function Receipts({ used }: { used?: Used }) {
  if (!used) return null;
  const { memories = [], facts = [], docs = [] } = used;
  const lessons = (used.lessons || []).filter(Boolean);
  const n = memories.length + facts.length + docs.length + lessons.length;
  if (!n) return null;
  const onToggle = (e: React.SyntheticEvent<HTMLDetailsElement>) => {
    const el = e.currentTarget;
    if (el.open) setTimeout(() => el.scrollIntoView({ block: "nearest", behavior: "smooth" }), 260);
  };
  return (
    <details className="receipts" onToggle={onToggle}>
      <summary>
        <svg className="receipts__chev" viewBox="0 0 12 12" fill="none" aria-hidden="true">
          <path d="M4.5 2.5 8 6l-3.5 3.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
        Remembered {n} {n === 1 ? "thing" : "things"}
      </summary>
      <div className="receipts__body">
        {memories.length > 0 && (
          <section className="receipts__group">
            <h3>Earlier conversations</h3>
            <ul>
              {memories.map((m, i) => (
                <li key={i}><span>{cut(m.text)}</span> <time dateTime={m.at}>{relDay(m.at)}</time></li>
              ))}
            </ul>
          </section>
        )}
        {facts.length > 0 && (
          <section className="receipts__group">
            <h3>About you</h3>
            <ul>{facts.map((f, i) => <li key={i}>{cut(f)}</li>)}</ul>
          </section>
        )}
        {docs.length > 0 && (
          <section className="receipts__group">
            <h3>From your files</h3>
            <ul>{docs.map((d, i) => <li key={i}>{cut(d)}</li>)}</ul>
          </section>
        )}
        {lessons.length > 0 && (
          <section className="receipts__group">
            <h3>Rules she followed</h3>
            <ul>{lessons.map((l, i) => <li key={i}>{cut(l)}</li>)}</ul>
          </section>
        )}
      </div>
    </details>
  );
}
