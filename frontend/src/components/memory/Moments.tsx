"use client";
// Every conversation: newest first, grouped by day, debounced keyword search with highlights,
// and "Show older" paging via ?before=<oldest timestamp>.
import Link from "next/link";
import { Fragment, useEffect, useRef, useState, type ReactNode } from "react";
import type { Moment } from "@/lib/stiti";
import { api, fmtDay, fmtTime } from "@/lib/stiti";
import { Arrow, Empty, Section } from "./bits";

const PAGE = 60;                                  // mind.moments() default limit

function highlight(text: string, q: string): ReactNode {
  const words = q.split(/\s+/).filter((w) => w.length > 1).map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  if (!words.length) return text;
  const rx = new RegExp(`(${words.join("|")})`, "gi");
  return text.split(rx).map((part, i) => (i % 2 ? <mark key={i}>{part}</mark> : part));
}

export default function Moments({ total }: { total: number }) {
  const [value, setValue] = useState("");
  const [query, setQuery] = useState("");
  const [rows, setRows] = useState<Moment[]>([]);
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");
  const [more, setMore] = useState(false);
  const [paging, setPaging] = useState(false);
  const seq = useRef(0);
  const timer = useRef(0);

  function fetchPage(q: string, before: string | null) {
    const id = ++seq.current;                    // a slower, older search must never overwrite a newer one
    const p = new URLSearchParams({ q });
    if (before) p.set("before", before);
    return api<Moment[]>(`/api/moments?${p}`).then((got) => {
      if (id !== seq.current) return;
      setRows((prev) => (before ? [...prev, ...got] : got));
      setMore(got.length >= PAGE);
      setState("ready");
      setPaging(false);
    }, () => {
      if (id !== seq.current) return;
      setState("error");
      setPaging(false);
    });
  }

  useEffect(() => {
    void fetchPage("", null);
    return () => window.clearTimeout(timer.current);
  }, []);

  function onType(v: string) {
    setValue(v);
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => { setQuery(v.trim()); void fetchPage(v.trim(), null); }, 250);
  }

  function older() {
    setPaging(true);
    void fetchPage(query, rows.length ? rows[rows.length - 1].at : null);
  }

  const days = rows.map((m) => fmtDay(new Date(m.at)));
  return (
    <Section id="moments" thin="Every" bold="conversation"
      note={<>Stiti never forgets. Search anything you&apos;ve ever said to her{total ? ` — ${total} messages so far` : ""}.</>}>
      <form className="search" role="search" onSubmit={(e) => e.preventDefault()}>
        <label className="sr-only" htmlFor="search-input">Search conversations</label>
        <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <circle cx="11" cy="11" r="6.5" stroke="currentColor" strokeWidth="2" />
          <path d="M16 16l4.5 4.5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
        </svg>
        <input id="search-input" type="search" value={value} onChange={(e) => onType(e.target.value)}
          placeholder="Search — “placements”, “mom”, “interview”…" />
      </form>

      <div className="moments" aria-live="polite" aria-busy={state === "loading"}>
        {state === "loading" && <p className="moments__note label">Reading your conversations…</p>}
        {state === "error" && <p className="moments__note">Couldn&apos;t load conversations. Is Stiti running?</p>}
        {state === "ready" && rows.length === 0 && (query
          ? <div className="empty"><p className="empty__text">Nothing matches <q>{query}</q>. Try a different word — search looks at every word you and Stiti said.</p></div>
          : <Empty say={["hey Stiti, how was your day?", "remind me what I said about placements"]}>No conversations yet. Everything you say to Stiti lands here, searchable forever.</Empty>)}
        {state === "ready" && query && rows.length > 0 && (
          <p className="moments__note label">{rows.length}{more ? "+" : ""} {rows.length === 1 ? "match" : "matches"} for “{query}”</p>
        )}
        {rows.map((m, i) => {
          const d = new Date(m.at), day = days[i], head = i === 0 || day !== days[i - 1];
          return (
            <Fragment key={m.id}>
              {head && <h3 className="day label">{day}</h3>}
              <div className={`mo mo--${m.who}`}>
                <span className="mo__who">{m.who === "you" ? "You" : "Stiti"}</span>
                <span className="mo__text">{highlight(m.text, query)}
                  <span className="mo__time">{fmtTime(d)}{m.mood && m.mood !== "calm" ? ` · sounded ${m.mood}` : ""}</span>
                </span>
              </div>
            </Fragment>
          );
        })}
      </div>
      {state === "ready" && more && (
        <button className="btn-line" type="button" onClick={older} disabled={paging}>
          {paging ? "Loading…" : "Show older conversations"} {!paging && <Arrow />}
        </button>
      )}
      {state === "ready" && !more && rows.length > 0 && !query && (
        <p className="moments__end label">That&apos;s the very first thing you said. <Link href="/chat" className="link-arrow">Keep talking <Arrow /></Link></p>
      )}
    </Section>
  );
}
