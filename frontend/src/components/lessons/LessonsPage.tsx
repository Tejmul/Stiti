"use client";
// Lessons: start a whiteboard lesson from his own files or any topic (no terminal), see what he knows per file, and
// read the notes each lesson saved. Reads /api/lessons; starts via POST /api/lessons/start. Same token model as the
// other app pages. Still page: no entrance motion; hovers are a subtle navy shift + arrow nudge.
// Background jobs (D56): "Prepare" on a file queues its concept map; the Jobs panel follows it live (/api/events).
import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import AppNav from "@/components/app/AppNav";
import type { Job, LessonNote, LessonProgress, Lessons } from "@/lib/stiti";
import { NotAllowed, api } from "@/lib/stiti";
import Jobs, { useJobs } from "./Jobs";
import MapView from "./MapView";
import NoteView from "./NoteView";
import Progress from "./Progress";
import Review from "./Review";
import StartCard, { type Pick } from "./StartCard";
import { Arrow, Icon, fmtSize, fmtWhen } from "./bits";

type Status = "loading" | "ready" | "gate" | "down" | "slow";
const TIMEOUT = 12000;
const POLL_MS = 4000;         // while a lesson runs (or was just started): banner + notes stay current

export default function LessonsPage() {
  const [data, setData] = useState<Lessons | null>(null);
  const [status, setStatus] = useState<Status>("loading");
  const [err, setErr] = useState("");
  const [lag, setLag] = useState(false);
  const [pick, setPick] = useState<Pick>({ kind: "file", path: "", topic: "" });
  const [note, setNote] = useState<LessonNote | null>(null);
  const [map, setMap] = useState<LessonProgress | null>(null);
  const [watch, setWatch] = useState(0);                 // > now: keep polling (a lesson was just started)
  const got = useRef(false);
  const kindSet = useRef(false);
  const reload = useRef<() => void>(() => {});
  // background jobs, live; a finished "Prepare" refreshes the files so that file shows Ready
  const { jobs, connected, patch } = useJobs(useCallback((j: Job) => { if (j.kind === "concept_map") reload.current(); }, []));

  const load = useCallback((): Promise<void> => {
    const ctl = new AbortController();
    const timer = setTimeout(() => ctl.abort(), TIMEOUT);
    return api<Lessons>("/api/lessons", { signal: ctl.signal }).then(
      (d) => {
        got.current = true;
        setData(d);
        setStatus("ready");
        if (!kindSet.current) {                          // no files at all → start on "A topic"
          kindSet.current = true;
          if (!d.files.length) setPick((p) => ({ ...p, kind: "topic" }));
        }
      },
      (e) => {
        if (got.current) return;                         // a failed refresh keeps what's on screen
        setErr(e instanceof Error ? e.message : String(e));
        setStatus(e instanceof NotAllowed ? "gate" : ctl.signal.aborted ? "slow" : "down");
      },
    ).finally(() => clearTimeout(timer));
  }, []);

  useEffect(() => { reload.current = () => { void load(); }; }, [load]);

  const retry = () => { setStatus("loading"); setLag(false); void load(); };

  useEffect(() => { void load(); }, [load]);
  useEffect(() => {
    if (status !== "loading") return;
    const t = setTimeout(() => setLag(true), 2500);
    return () => clearTimeout(t);
  }, [status]);

  // Poll while a lesson runs or was just started; otherwise refresh when he comes back to the tab.
  const polling = !!data?.active || watch > 0;
  useEffect(() => {
    if (!polling) return;
    const t = setInterval(() => {
      void load();
      if (watch && Date.now() > watch) setWatch(0);
    }, POLL_MS);
    return () => clearInterval(t);
  }, [polling, watch, load]);
  useEffect(() => {
    const onVis = () => { if (document.visibilityState === "visible") void load(); };
    document.addEventListener("visibilitychange", onVis);
    return () => document.removeEventListener("visibilitychange", onVis);
  }, [load]);

  const started = () => { setWatch(Date.now() + 60_000); void load(); };

  // "Continue" on a progress card: pick that file (if it's still in his folders) or that topic, then go to Start.
  const continueFrom = (r: LessonProgress): (() => void) | null => {
    const toStart = () => document.getElementById("start")?.scrollIntoView({ block: "start" });
    if (r.kind === "topic") return () => { setPick((p) => ({ ...p, kind: "topic", topic: r.source.slice(0, 120) })); toStart(); };
    const name = r.source.split(" · ")[0];
    const f = data?.files.find((x) => x.name === name);
    return f ? () => { setPick((p) => ({ ...p, kind: "file", path: f.path })); toStart(); } : null;
  };

  return (
    <div className="pg-lessons">
      <AppNav current="lessons" />
      <main id="main" className="container">
        <header className="head">
          <div className="head__text">
            <p className="label">Lessons · on the whiteboard</p>
            <h1 className="head__title"><span className="thin">Learn anything,</span> <span className="bold">your way.</span></h1>
            <p className="head__lede">
              Pick one of your files or type a topic. Stiti checks what you already know, teaches the rest by voice on the
              whiteboard, and saves your notes here.
            </p>
          </div>
        </header>

        {data?.active && (
          <div className="running" role="status">
            <span className="running__dot" aria-hidden="true" />
            <div className="running__text">
              <p className="running__t">A lesson is running on the whiteboard</p>
              <p className="running__l">To finish it, say or type <q>end</q> on the board. Your notes appear here when it ends.</p>
            </div>
            <a className="btn-glass" href={data.board_url} target="_blank" rel="noopener noreferrer">Open board <Icon name="open" /></a>
          </div>
        )}

        {status === "loading" && <Loading lag={lag} />}
        {(status === "down" || status === "slow" || status === "gate") && <Problem status={status} err={err} onRetry={retry} />}

        {data && status === "ready" && (
          <div className="lay">
            <StartCard files={data.files} active={data.active} boardUrl={data.board_url} pick={pick} setPick={setPick}
              onStarted={started} jobs={jobs} onJob={patch} />
            <div className="side">
              <Jobs jobs={jobs} connected={connected} onChange={patch} />
              <Review total={data.review?.total ?? 0} rows={data.progress} active={data.active} boardUrl={data.board_url}
                onStarted={started} />
              <Progress rows={data.progress} onContinue={continueFrom} onMap={setMap} />
              <Notes notes={data.notes} onOpen={setNote} />
            </div>
          </div>
        )}
      </main>
      <NoteView note={note} onClose={() => setNote(null)} />
      <MapView row={map} active={!!data?.active} boardUrl={data?.board_url ?? ""} onClose={() => setMap(null)} onStarted={started} />
    </div>
  );
}

function Notes({ notes, onOpen }: { notes: LessonNote[]; onOpen: (n: LessonNote) => void }) {
  return (
    <section className="block" id="notes" aria-labelledby="notes-h">
      <header className="sec__head">
        <h2 id="notes-h"><span className="thin">Your</span> <span className="bold">notes</span>
          {notes.length > 0 && <span className="sec__n">{notes.length}</span>}</h2>
      </header>
      {notes.length ? (
        <ul className="panel list">
          {notes.map((n) => (
            <li key={n.name}>
              <button type="button" className="nrow" onClick={() => onOpen(n)}>
                <Icon name="note" className="nrow__ico" />
                <span className="nrow__main">
                  <span className="nrow__t">{n.title}</span>
                  <span className="nrow__m">{fmtWhen(n.modified)} · {fmtSize(n.size)}</span>
                </span>
                <Arrow />
              </button>
            </li>
          ))}
        </ul>
      ) : (
        <div className="empty">
          <p className="empty__text">No notes yet. At the end of every lesson she writes the key points, examples and the
            “Remember” lines into a note you can read here (plain markdown in <code>~/.stiti/tutor/notes</code>).</p>
        </div>
      )}
    </section>
  );
}

function Loading({ lag }: { lag: boolean }) {
  return (
    <div className="loading" aria-busy="true">
      <p className="label loading__msg" role="status">
        {lag ? "Still looking… the first load after Stiti starts can take a few seconds." : "Looking for your files and notes…"}
      </p>
      <div className="lay" aria-hidden="true">
        <div className="start">
          <span className="sk sk--h" />
          {[0, 1, 2].map((s) => (
            <div key={s} className="step">
              <span className="sk sk--line" style={{ width: 220 }} />
              <span className="sk sk--box" />
            </div>
          ))}
        </div>
        <div className="side">
          {[0, 1].map((s) => (
            <div key={s} className="block">
              <span className="sk sk--h" />
              <div className="panel">{Array.from({ length: 3 }, (_, i) => <span key={i} className="sk sk--row" />)}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

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
            <li>Click Stiti in your menu bar → <b>Open Stiti (chat + memory)</b>, then open <b>Lessons</b>.</li>
            <li>If Stiti isn&apos;t in the menu bar, she isn&apos;t running — start the Stiti app first.</li>
          </ol>
        ) : (
          <ol className="problem__steps">
            <li>Check that Stiti is running — look for her icon in the menu bar.</li>
            <li>If she isn&apos;t, open the Stiti app, or run <code>uv run stiti web</code> in the Stiti folder.</li>
            <li>{status === "slow" ? "She may still be starting up. Give it a moment, then try again." : "Then try again."}</li>
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
