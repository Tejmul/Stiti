"use client";
// Stiti's memory of him: a still map of his life, then every part of it — editable where it should be.
// Reads /api/mind (what she knows). Conversations are never shown on a page (owner's privacy rule). Same token model as the chat.
import { Fragment, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import Nav from "@/components/Nav";
import type { Mind } from "@/lib/stiti";
import { NotAllowed, api, plural } from "@/lib/stiti";
import About from "./About";
import LifeMap from "./LifeMap";
import Rail, { type RailItem } from "./Rail";
import { Files, Habits, Mood, People, Plans, Rules } from "./Sections";

type Status = "loading" | "ready" | "gate" | "down";

export default function MemoryPage() {
  const [mind, setMind] = useState<Mind | null>(null);
  const [status, setStatus] = useState<Status>("loading");

  // Promise callbacks (not effect-body setState): reload after an edit and on first visit.
  const load = useCallback(() => api<Mind>("/api/mind").then(       // no token → 403 → gate
    (d) => { setMind(d); setStatus("ready"); },
    (e) => setStatus(e instanceof NotAllowed ? "gate" : "down"),
  ), []);

  useEffect(() => { void load(); }, [load]);
  useEffect(() => { if (mind?.name) document.title = `Memory · ${mind.name} · Stiti`; }, [mind?.name]);

  const c = mind?.counts;
  const rail: RailItem[] = [
    { id: "about", label: "About you", n: c?.facts },
    { id: "people", label: "People", n: c?.people },
    { id: "rules", label: "How to talk to you", n: c?.rules },
    { id: "habits", label: "Habits", n: c?.habits },
    { id: "mood", label: "Mood" },
    { id: "files", label: "Files", n: c?.docs },
    { id: "plans", label: "Plans" },
  ];

  return (
    <div className="pg-memory">
      <Nav current="memory" />
      <main id="main">
        <header className="head container">
          <div className="head__text">
            <p className="label">Stiti&apos;s memory of you</p>
            <h1 className="head__title">
              <span className="thin">What I know</span><br />
              <span className="bold">about {mind?.name || "you"}.</span>
            </h1>
            <p className="head__lede">
              Everything here lives on this Mac, in <code>~/.stiti</code>. Change a line and Stiti changes with it — the
              next thing she says already knows.
            </p>
            <p className="head__stats label" aria-live="polite">
              {status === "loading" && "Reading your memory…"}
              {status === "down" && <>Can&apos;t reach Stiti. Is she running? (menu bar → Open Stiti){" "}
                <button type="button" className="retry" onClick={() => { setStatus("loading"); void load(); }}>Try again</button></>}
              {status === "ready" && c && <Stats c={c} />}
            </p>
          </div>
          {mind ? <LifeMap mind={mind} /> : <div className="map map--wait" aria-hidden="true" />}
        </header>

        {mind && (
          <div className="body container">
            <Rail items={rail} />
            <div className="sections">
              <About facts={mind.facts} onChanged={load} />
              <People d={mind} />
              <Rules d={mind} />
              <Habits d={mind} />
              <Mood d={mind} />
              <Files d={mind} />
              <Plans d={mind} />
            </div>
          </div>
        )}
      </main>

      {status === "gate" && (
        <div className="gate" role="dialog" aria-modal="true" aria-labelledby="gate-h">
          <div className="gate__card">
            <p className="label">Not connected</p>
            <h2 id="gate-h"><span className="thin">Open Stiti from</span> <span className="bold">the menu bar.</span></h2>
            <p>This page couldn&apos;t link to Stiti. Click Stiti in your menu bar → <b>Open Stiti (chat + memory)</b>. If
              she isn&apos;t in the menu bar, she isn&apos;t running.</p>
            <p><Link className="gate__home" href="/">← Back to home</Link></p>
          </div>
        </div>
      )}
    </div>
  );
}

function Stats({ c }: { c: Mind["counts"] }) {
  const since = c.since ? new Date(c.since).toLocaleDateString([], { day: "numeric", month: "short" }) : null;
  const parts = [plural(c.facts, "fact"), plural(c.people, "person", "people"), plural(c.docs, "file"), plural(c.rules, "rule")];
  const all = since ? [...parts, `since ${since}`] : parts;
  return (
    <>
      {all.map((p, i) => (
        <Fragment key={p}>
          <span className="stat">{i < parts.length ? <b>{p}</b> : p}{i < all.length - 1 ? " ·" : ""}</span>{" "}
        </Fragment>
      ))}
    </>
  );
}
