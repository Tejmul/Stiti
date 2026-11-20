"use client";
// Background jobs (D56): what Stiti is working on for him (today: preparing a file's concept map before a lesson).
// Live over server-sent events (/api/events: a snapshot, then one event per change), so step, %, time left and
// "will retry at" update without a refresh. Retry / Cancel go to /api/jobs/{id}/…. Still panel: no motion.
import { useCallback, useEffect, useRef, useState } from "react";
import type { Job, JobStatus } from "@/lib/stiti";
import { JOB_LIVE, api, fmtDay, fmtTime, jobEvents } from "@/lib/stiti";
import { Icon } from "./bits";

const MAX_SHOWN = 12;
const live = (s: JobStatus) => JOB_LIVE.includes(s);

function order(list: Job[]): Job[] {
  return [...list].sort((a, b) => {
    const la = live(a.status), lb = live(b.status);
    if (la !== lb) return la ? -1 : 1;
    return la ? a.created_at.localeCompare(b.created_at) : b.updated_at.localeCompare(a.updated_at);
  }).slice(0, 30);
}

/** The jobs list, kept live. `onDone(job)` fires once when a job finishes while the page is open. */
export function useJobs(onDone?: (j: Job) => void) {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [connected, setConnected] = useState(false);
  const done = useRef(onDone);
  useEffect(() => { done.current = onDone; }, [onDone]);

  useEffect(() => {
    let es: EventSource | null = null;
    let stopped = false;
    let wait = 2000;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const seen = new Map<number, JobStatus>();               // last status per job: "done" fires onDone once

    const open = async () => {
      if (stopped) return;
      try { es = await jobEvents(); } catch { return retry(); }
      if (stopped) { es.close(); return; }
      es.onopen = () => { setConnected(true); wait = 2000; };
      es.addEventListener("snapshot", (e) => {
        let list: Job[];
        try { list = (JSON.parse((e as MessageEvent).data) as { jobs: Job[] }).jobs; } catch { return; }
        list.forEach((j) => seen.set(j.id, j.status));
        setJobs(order(list));
      });
      es.addEventListener("job", (e) => {
        let j: Job;
        try { j = JSON.parse((e as MessageEvent).data) as Job; } catch { return; }
        const was = seen.get(j.id);
        seen.set(j.id, j.status);
        if (j.status === "done" && was !== "done") done.current?.(j);
        setJobs((prev) => order(prev.some((x) => x.id === j.id)
          ? prev.map((x) => (x.id === j.id ? { ...x, ...j } : x)) : [j, ...prev]));
      });
      es.onerror = () => {
        setConnected(false);
        if (es && es.readyState === EventSource.CLOSED) { es.close(); retry(); }   // e.g. a stale key: re-link
      };
    };
    const retry = () => {
      if (stopped) return;
      clearTimeout(timer);
      timer = setTimeout(() => {
        api<{ jobs: Job[] }>("/api/jobs").then((d) => setJobs(order(d.jobs))).catch(() => {}).finally(open);
      }, wait);
      wait = Math.min(wait * 2, 30000);
    };
    void open();
    return () => { stopped = true; clearTimeout(timer); es?.close(); };
  }, []);

  const patch = useCallback((j: Job) => setJobs((prev) => order(prev.some((x) => x.id === j.id)
    ? prev.map((x) => (x.id === j.id ? { ...x, ...j } : x)) : [j, ...prev])), []);

  return { jobs, connected, patch };
}

const KIND: Record<string, string> = { concept_map: "Prepare for a lesson" };
const WORD: Record<JobStatus, string> = {
  queued: "Queued", running: "Running", parked: "Waiting", done: "Done", failed: "Failed", cancelled: "Cancelled",
};

function at(iso: string): string {
  const d = new Date(iso);
  return d.toDateString() === new Date().toDateString() ? fmtTime(d) : `${fmtDay(d)} ${fmtTime(d)}`;
}

function left(s: number | null): string | null {
  if (s == null) return null;
  if (s < 60) return "under a minute left";
  const m = Math.round(s / 60);
  return m < 60 ? `about ${m} min left` : `about ${Math.round(m / 6) / 10} h left`;
}

type Props = { jobs: Job[]; connected: boolean; onChange: (j: Job) => void };

export default function Jobs({ jobs, connected, onChange }: Props) {
  const [busy, setBusy] = useState<number | null>(null);
  const [err, setErr] = useState("");
  const shown = jobs.slice(0, MAX_SHOWN);
  const running = jobs.filter((j) => live(j.status)).length;

  const act = async (j: Job, what: "retry" | "cancel") => {
    setBusy(j.id); setErr("");
    try {
      const r = await api<{ job: Job }>(`/api/jobs/${j.id}/${what}`, { method: "POST" });
      onChange(r.job);
    } catch (e) {
      setErr(e instanceof Error && e.message !== "not allowed" ? e.message
        : "This page isn't linked to Stiti. Open it from Stiti's menu bar icon, then try again.");
    } finally {
      setBusy(null);
    }
  };

  return (
    <section className="block" id="jobs" aria-labelledby="jobs-h">
      <header className="sec__head jobs__head">
        <h2 id="jobs-h"><span className="thin">Background</span> <span className="bold">jobs</span>
          {running > 0 && <span className="sec__n">{running} active</span>}</h2>
        <span className={`live${connected ? " is-on" : ""}`} role="status">
          <i aria-hidden="true" />{connected ? "Live" : "Reconnecting"}
        </span>
      </header>
      {shown.length ? (
        <ul className="panel list jobs" aria-live="polite">
          {shown.map((j) => {
            const waitingRetry = j.status === "queued" && !!j.not_before && !!j.error && new Date(j.not_before) > new Date();
            const word = waitingRetry ? "Retrying" : WORD[j.status];
            const line = j.status === "parked" || j.status === "failed" || waitingRetry ? j.error
              : j.step || (j.status === "queued" ? "Waiting for its turn" : null);
            const meta = j.status === "running" ? [`${j.percent}%`, left(j.eta_s)].filter(Boolean).join(" · ")
              : j.status === "parked" && j.not_before ? `Will retry at ${at(j.not_before)}`
              : waitingRetry && j.not_before ? `Try ${j.attempts + 1} of ${j.max_attempts ?? 3} at ${at(j.not_before)}`
              : j.status === "queued" ? (j.percent > 0 ? `${j.percent}% done before · picks up from there` : "Starts in a moment")
              : j.status === "failed" ? `Stopped${j.attempts > 1 ? ` after ${j.attempts} tries` : ""}${j.finished_at ? ` · ${at(j.finished_at)}` : ""}`
              : j.finished_at ? `${j.status === "cancelled" ? "Cancelled" : "Finished"} ${at(j.finished_at)}` : "";
            const bar = live(j.status) && (j.status === "running" || j.percent > 0);
            return (
              <li key={j.id} className={`job is-${waitingRetry ? "retrying" : j.status}`}>
                <div className="job__top">
                  <Icon name={j.status === "done" ? "check" : j.status === "failed" ? "alert" : j.status === "parked" ? "clock" : "file"}
                    className="job__ico" />
                  <span className="job__main">
                    <span className="job__name" title={j.label}>{j.label}</span>
                    <span className="job__kind">{KIND[j.kind] ?? j.kind}</span>
                  </span>
                  <span className="job__st">{word}</span>
                </div>
                {line && <p className="job__step">{line}</p>}
                {bar && (
                  <div className="bar job__bar" role="progressbar" aria-label={`${j.label}: ${j.percent}%`}
                    aria-valuemin={0} aria-valuemax={100} aria-valuenow={j.percent}>
                    <i className="bar__k" style={{ width: `${j.percent}%` }} />
                  </div>
                )}
                <div className="job__foot">
                  <span className="job__meta">{meta}</span>
                  <span className="job__acts">
                    {(j.status === "failed" || j.status === "cancelled" || j.status === "parked" || waitingRetry) && (
                      <button type="button" className="job__b" disabled={busy === j.id} onClick={() => void act(j, "retry")}>
                        {j.status === "parked" || waitingRetry ? "Retry now" : "Retry"}
                      </button>
                    )}
                    {live(j.status) && (
                      <button type="button" className="job__b job__b--quiet" disabled={busy === j.id}
                        onClick={() => void act(j, "cancel")}>Cancel</button>
                    )}
                  </span>
                </div>
              </li>
            );
          })}
        </ul>
      ) : (
        <div className="empty">
          <p className="empty__text">Nothing running. Press <b>Prepare</b> on one of your files and Stiti reads it in the
            background, so its lesson starts at once. The step, progress and time left show here, live. If the free AI runs
            out, the job waits and carries on by itself.</p>
        </div>
      )}
      {err && <p className="msg is-err" role="alert"><Icon name="alert" />{err}</p>}
    </section>
  );
}
