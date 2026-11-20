"use client";
// Stiti's memory of him, as an app page: a compact header with search and an at-a-glance strip, then every part of
// what she knows in scannable sections (editable where the API allows: add/forget a fact, tick a todo).
// Reads /api/mind. Conversations are never shown on a page (owner's privacy rule). Same token model as the chat.
import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import AppNav from "@/components/app/AppNav";
import type { Mind } from "@/lib/stiti";
import { NotAllowed, api, plural } from "@/lib/stiti";
import About from "./About";
import Rail, { type RailItem } from "./Rail";
import { Files, Habits, Mood, Notes, People, Plans, Rules } from "./Sections";
import { Arrow, Icon, has, jump } from "./bits";

type Status = "loading" | "ready" | "gate" | "down" | "slow";
const TIMEOUT = 12000;

export default function MemoryPage() {
  const [mind, setMind] = useState<Mind | null>(null);
  const [status, setStatus] = useState<Status>("loading");
  const [err, setErr] = useState("");
  const [lag, setLag] = useState(false);
  const [q, setQ] = useState("");
  const search = useRef<HTMLInputElement>(null);
  const got = useRef(false);

  // First visit: loading → ready / gate / down / slow. After an edit it just refreshes in place (a failed refresh
  // keeps what's on screen; the edit itself reports its own error).
  // Promise callbacks (not effect-body setState), so the effect below only starts the request.
  const load = useCallback((): Promise<void> => {
    const ctl = new AbortController();
    const timer = setTimeout(() => ctl.abort(), TIMEOUT);
    return api<Mind>("/api/mind", { signal: ctl.signal }).then(
      (d) => { got.current = true; setMind(d); setStatus("ready"); },
      (e) => {
        if (got.current) return;
        setErr(e instanceof Error ? e.message : String(e));
        setStatus(e instanceof NotAllowed ? "gate" : ctl.signal.aborted ? "slow" : "down");
      },
    ).finally(() => clearTimeout(timer));
  }, []);

  const retry = () => { setStatus("loading"); setLag(false); void load(); };

  useEffect(() => { void load(); }, [load]);
  useEffect(() => {                                        // a slow first answer gets a word of explanation
    if (status !== "loading") return;
    const t = setTimeout(() => setLag(true), 2500);
    return () => clearTimeout(t);
  }, [status]);
  useEffect(() => { if (mind?.name) document.title = `Memory · ${mind.name} · Stiti`; }, [mind?.name]);

  // "/" focuses search, Escape clears it.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const typing = e.target instanceof HTMLElement && e.target.closest("input, textarea, [contenteditable]");
      if (e.key === "/" && !typing && !e.metaKey && !e.ctrlKey) { e.preventDefault(); search.current?.focus(); }
    };
    addEventListener("keydown", onKey);
    return () => removeEventListener("keydown", onKey);
  }, []);

  const query = q.trim();
  const n = mind ? countAll(mind, query) : null;
  const rail: RailItem[] = n ? [
    { id: "about", label: "About you", n: n.about },
    { id: "rules", label: "How to talk to you", n: n.rules },
    { id: "people", label: "People & places", n: n.people },
    { id: "notes", label: "Recent notes", n: n.notes },
    { id: "plans", label: "Plans & reminders", n: n.plans },
    { id: "habits", label: "Habits", n: n.habits },
    ...(query ? [] : [{ id: "mood", label: "Mood" }]),
    { id: "files", label: "Files", n: n.files },
  ].filter((r) => !query || (r.n ?? 0) > 0) : [];
  const total = n ? n.about + n.rules + n.people + n.notes + n.plans + n.habits + n.files : 0;

  return (
    <div className="pg-memory">
      <AppNav current="memory" />
      <main id="main" className="container">
        <header className="head">
          <div className="head__text">
            <p className="label">Memory · stored on this Mac</p>
            <h1 className="head__title">
              <span className="thin">What Stiti knows</span> <span className="bold">about {mind?.name || "you"}.</span>
            </h1>
            <p className="head__lede">
              Everything here lives in <code>~/.stiti</code> on this Mac. Change a line and her next reply already knows.
            </p>
          </div>
          <div className="search" role="search">
            <Icon name="search" className="search__ico" />
            <label className="sr-only" htmlFor="mem-search">Search Stiti&apos;s memory</label>
            <input ref={search} id="mem-search" type="search" value={q} placeholder="Search memory" autoComplete="off"
              disabled={status !== "ready"} onChange={(e) => setQ(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Escape") setQ(""); }} />
            {q ? (
              <button type="button" className="search__clear" aria-label="Clear search" onClick={() => { setQ(""); search.current?.focus(); }}>
                <Icon name="close" />
              </button>
            ) : <kbd className="search__kbd" aria-hidden="true">/</kbd>}
          </div>
        </header>

        {status === "loading" && <Loading lag={lag} />}
        {(status === "down" || status === "slow" || status === "gate") && <Problem status={status} err={err} onRetry={retry} />}

        {mind && status === "ready" && (
          <>
            {!query && <Glance mind={mind} />}
            {query && (
              <p className="found" role="status">
                <span>{total ? <><b>{plural(total, "match", "matches")}</b> for “{query}”</> : <>Nothing in Stiti&apos;s memory matches “{query}”.</>}</span>
                <button type="button" className="found__clear" onClick={() => setQ("")}>Clear search</button>
              </p>
            )}
            <div className="body">
              {rail.length > 0 && <Rail items={rail} />}
              <div className="sections">
                <About facts={mind.facts} q={query} onChanged={load} />
                <Rules d={mind} q={query} />
                <People d={mind} q={query} />
                <Notes d={mind} q={query} />
                <Plans d={mind} q={query} onChanged={load} />
                <Habits d={mind} q={query} />
                <Mood d={mind} q={query} />
                <Files d={mind} q={query} />
              </div>
            </div>
          </>
        )}
      </main>
    </div>
  );
}

/** How many things each section shows for the current query (the rail's counts and the "N matches" line). */
function countAll(d: Mind, q: string) {
  return {
    about: d.facts.filter((f) => has(q, f.text, f.group)).length,
    rules: d.directives.filter((x) => has(q, x.text)).length + d.lessons.filter((l) => has(q, l.text, l.when)).length
      + d.traits.filter((t) => has(q, t.label)).length,
    people: d.people.filter((p) => has(q, p.name, p.summary, p.kind, ...p.facts)).length,
    notes: d.reflections.filter((r) => has(q, r.text)).length,
    plans: d.todos.filter((t) => has(q, t.title)).length + d.alarms.filter((a) => has(q, a.text, a.kind)).length
      + d.courses.filter((c) => has(q, c.title)).length,
    habits: d.habits.filter((h) => has(q, h.name, h.cue)).length,
    files: d.docs.filter((x) => has(q, x.title, x.kind)).length,
  };
}

/** At a glance: one tile per part of memory; each takes you to its section. */
function Glance({ mind }: { mind: Mind }) {
  const c = mind.counts;
  const since = c.since ? new Date(c.since).toLocaleDateString([], { day: "numeric", month: "short", year: "numeric" }) : null;
  const tiles = [
    { href: "#about", n: c.facts, w: "fact", ws: "facts" },
    { href: "#rules", n: c.rules, w: "rule", ws: "rules" },
    { href: "#people", n: c.people, w: "person", ws: "people" },
    { href: "#notes", n: mind.reflections.length, w: "note", ws: "notes" },
    { href: "#plans", n: mind.todos.length + mind.alarms.length, w: "plan", ws: "plans" },
    { href: "#files", n: c.docs, w: "file", ws: "files" },
  ];
  return (
    <nav className="glance" aria-label="At a glance">
      {tiles.map((t) => (
        <a key={t.href} className="glance__tile" href={t.href} onClick={(e) => { e.preventDefault(); jump(t.href); }}>
          <span className="glance__n">{t.n}</span>
          <span className="glance__w">{t.n === 1 ? t.w : t.ws}</span>
          <Arrow />
        </a>
      ))}
      {since && <p className="glance__since label">Talking since {since}</p>}
    </nav>
  );
}

/** Skeleton of the page while /api/mind answers (normally well under a second). */
function Loading({ lag }: { lag: boolean }) {
  return (
    <div className="loading" aria-busy="true">
      <p className="label loading__msg" role="status">
        {lag ? "Still reading her memory… the first load after Stiti starts can take a few seconds." : "Reading her memory…"}
      </p>
      <div className="glance glance--skel" aria-hidden="true">{Array.from({ length: 6 }, (_, i) => <span key={i} className="glance__tile sk" />)}</div>
      <div className="body" aria-hidden="true">
        <div className="rail rail--skel">{Array.from({ length: 7 }, (_, i) => <span key={i} className="sk sk--line" />)}</div>
        <div className="sections">
          {[0, 1].map((s) => (
            <div key={s} className="sec">
              <span className="sk sk--h" />
              <div className="groups">
                {[0, 1].map((g) => (
                  <div key={g} className="panel">{Array.from({ length: 3 + g }, (_, i) => <span key={i} className="sk sk--row" />)}</div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

/** Couldn't load: say what happened and exactly what to do. */
function Problem({ status, err, onRetry }: { status: "down" | "slow" | "gate"; err: string; onRetry: () => void }) {
  const head = status === "gate" ? ["This page isn't", "linked to Stiti."]
    : status === "slow" ? ["Stiti is taking", "too long to answer."] : ["Can't reach", "Stiti right now."];
  return (
    <section className="problem" role="alert" aria-labelledby="problem-h">
      <Icon name={status === "gate" ? "plug" : "alert"} className="problem__ico" />
      <div>
        <h2 id="problem-h"><span className="thin">{head[0]}</span> <span className="bold">{head[1]}</span></h2>
        {status === "gate" ? (
          <ol className="problem__steps">
            <li>Click Stiti in your menu bar → <b>Open Stiti (chat + memory)</b>. That opens this page already linked.</li>
            <li>If Stiti isn&apos;t in the menu bar, she isn&apos;t running — start the Stiti app first.</li>
          </ol>
        ) : (
          <ol className="problem__steps">
            <li>Check that Stiti is running — look for her icon in the menu bar.</li>
            <li>If she isn&apos;t, open the Stiti app, or run <code>uv run stiti web</code> in the Stiti folder.</li>
            <li>{status === "slow" ? "Her database may still be starting up. Give it a moment, then try again." : "Then try again."}</li>
          </ol>
        )}
        <div className="problem__acts">
          {status !== "gate" && <button type="button" className="btn-ink" onClick={onRetry}>Try again</button>}
          <Link className="link-arrow" href="/chat">Open Chat <Arrow /></Link>
        </div>
        {status === "down" && err && <p className="problem__err label">Error: {err}</p>}
      </div>
    </section>
  );
}
