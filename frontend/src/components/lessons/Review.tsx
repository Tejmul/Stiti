"use client";
// "Review · N due": the concept cards that are due (FSRS) — every concept she teaches leaves one. Start review runs a
// short spoken quiz on the whiteboard (POST /api/lessons/start {mode: "review", key?}); per file too.
import { useState } from "react";
import type { LessonProgress, ReviewStart } from "@/lib/stiti";
import { api, plural } from "@/lib/stiti";
import { Arrow, Icon } from "./bits";

type Props = { total: number; rows: LessonProgress[]; active: boolean; boardUrl: string; onStarted: () => void };

export default function Review({ total, rows, active, boardUrl, onStarted }: Props) {
  const [busy, setBusy] = useState<string | null>(null);        // "all" or a key while starting
  const [err, setErr] = useState("");
  const [started, setStarted] = useState("");
  const per = rows.filter((r) => (r.due ?? 0) > 0);

  const start = async (key?: string) => {
    if (busy || active) return;
    setBusy(key ?? "all"); setErr(""); setStarted("");
    const body: ReviewStart = key ? { mode: "review", key } : { mode: "review" };
    try {
      const r = await api<{ ok: boolean; message: string }>("/api/lessons/start", {
        method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body),
      });
      setStarted(r.message || "Opening the whiteboard.");
    } catch (e) {
      setErr(e instanceof Error && e.message !== "not allowed" ? e.message
        : "This page isn't linked to Stiti. Open it from Stiti's menu bar icon, then try again.");
    } finally {
      setBusy(null);
      onStarted();
    }
  };

  return (
    <section className="block" id="review" aria-labelledby="review-h">
      <header className="sec__head">
        <h2 id="review-h"><span className="thin">Review</span> <span className="bold">· {total} due</span></h2>
      </header>
      <div className={`rev${total ? " rev--due" : ""}`}>
        <div className="rev__top">
          <Icon name="cards" className="rev__ico" />
          <p className="rev__line">
            {total ? <>A five-minute spoken quiz of what you&apos;re about to forget: {plural(total, "card")}, one question each.</>
              : <>Nothing due right now. Every topic she teaches becomes a card that comes back just before you&apos;d forget it.</>}
          </p>
        </div>
        {per.length > 0 && (
          <ul className="rev__list">
            {per.map((r) => (
              <li key={r.key} className="rev__row">
                <Icon name={r.kind === "file" ? "file" : "topic"} className="rev__rico" />
                <span className="rev__name" title={r.source}>{r.source}</span>
                <span className="rev__n">{r.due} due</span>
                <button type="button" className="link-arrow" disabled={!!busy || active} onClick={() => void start(r.key)}
                  aria-label={`Review ${r.source}`}>
                  {busy === r.key ? "Starting…" : "Review"} {busy !== r.key && <Arrow />}
                </button>
              </li>
            ))}
          </ul>
        )}
        {total > 0 && (
          <div className="rev__go">
            <button type="button" className="btn-ink" disabled={!!busy || active} onClick={() => void start()}>
              {busy === "all" ? "Starting…" : "Start review"} {busy !== "all" && <Arrow />}
            </button>
            <span className="rev__hint">{active ? "A lesson is running. Finish it first." : "Or say “review” to Stiti."}</span>
          </div>
        )}
        {err && <p className="msg is-err" role="alert"><Icon name="alert" />{err}</p>}
        {started && !err && (
          <div className="done" role="status">
            <Icon name="check" className="done__ico" />
            <div>
              <p className="done__t">Review open on the whiteboard</p>
              <p className="done__l">{started}</p>
            </div>
            <a className="btn-glass" href={boardUrl} target="_blank" rel="noopener noreferrer">Open board <Icon name="open" /></a>
          </div>
        )}
      </div>
    </section>
  );
}
