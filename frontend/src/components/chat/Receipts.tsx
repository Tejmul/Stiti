"use client";
// Memory receipts: what Stiti's own brain handed the LLM for this reply (memories, facts, files, lessons).
// Native <details> so it's keyboard accessible for free; the reveal is CSS (::details-content).
import type { Used } from "@/lib/stiti";

const cut = (s: string, n = 140) => (s.length > n ? s.slice(0, n).replace(/\s+\S*$/, "") + "…" : s);

export default function Receipts({ used }: { used?: Used }) {
  if (!used) return null;
  const { facts = [], docs = [] } = used;
  const memories = typeof used.memories === "number" ? used.memories : 0;   // a count, never the words
  const lessons = (used.lessons || []).filter(Boolean);
  const n = memories + facts.length + docs.length + lessons.length;
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
        {memories > 0 && (
          <section className="receipts__group">
            <h3>Earlier conversations</h3>
            <p className="receipts__private">{memories} recalled. Kept private, so they&apos;re not shown here.</p>
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
