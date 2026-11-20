"use client";
// The map of one file or topic, in a side panel (native modal <dialog>, like NoteView): Strong / Focus / Not started
// chips coloured by level, a concept × day heatmap of the last 30 days, and what's at risk on exam day.
// Pick a chip → "Teach me this" starts a focused lesson (--focus). Reads GET /api/lessons/map?key=…[&exam=…].
import { useCallback, useEffect, useId, useRef, useState } from "react";
import type { LessonMap, LessonProgress, LessonStart, MapConcept } from "@/lib/stiti";
import { api, plural } from "@/lib/stiti";
import { Arrow, Icon, fmtDate } from "./bits";

type Props = { row: LessonProgress | null; active: boolean; boardUrl: string; onClose: () => void; onStarted: () => void };
type Loaded = { key: string; map?: LessonMap; err?: string };

const GROUPS: { id: keyof LessonMap["groups"]; title: string; line: string }[] = [
  { id: "strong", title: "Strong", line: "Known well. One quick check next time." },
  { id: "focus", title: "Focus", line: "Seen, not solid yet. These come first." },
  { id: "not_started", title: "Not started", line: "Not answered on yet." },
];
const LEVEL: Record<string, string> = { strong: "strong", shaky: "shaky", weak: "weak", new: "not started" };
const pct = (n: number) => `${Math.round(n * 100)}%`;
const shortDay = (iso: string) => new Date(`${iso}T12:00:00`).toLocaleDateString(undefined, { day: "numeric", month: "short" });

export default function MapView({ row, active, boardUrl, onClose, onStarted }: Props) {
  const dlg = useRef<HTMLDialogElement>(null);
  const id = useId();
  const [got, setGot] = useState<Loaded | null>(null);
  const [exam, setExam] = useState("");
  const [pick, setPick] = useState<MapConcept | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  useEffect(() => {
    const d = dlg.current;
    if (!d) return;
    if (row && !d.open) d.showModal();
    if (!row && d.open) d.close();
    setPick(null); setMsg(null); setExam("");
  }, [row]);

  const load = useCallback((key: string, ex: string) => {
    let live = true;
    const qs = `key=${encodeURIComponent(key)}${ex ? `&exam=${encodeURIComponent(ex)}` : ""}`;
    api<LessonMap>(`/api/lessons/map?${qs}`).then(
      (m) => { if (live) { setGot({ key, map: m }); if (!ex && m.exam) setExam(m.exam); } },
      (e) => { if (live) setGot({ key, err: e instanceof Error ? e.message : String(e) }); },
    );
    return () => { live = false; };
  }, []);

  useEffect(() => { if (row) return load(row.key, ""); }, [row, load]);

  const cur = row && got?.key === row.key ? got : null;
  const m = cur?.map;

  const setExamDate = (v: string) => {
    setExam(v);
    if (row && (/^\d{4}-\d{2}-\d{2}$/.test(v) || v === "")) load(row.key, v);
  };

  const teach = async () => {
    if (!m?.target || !pick || busy || active) return;
    setBusy(true); setMsg(null);
    const soon = m.exam_days != null && m.exam_days >= 0 && m.exam_days <= 60;
    const body: LessonStart = soon ? { target: m.target, mode: "exam", days: m.exam_days!, focus: pick.focus }
      : { target: m.target, mode: "learn", focus: pick.focus };
    try {
      const r = await api<{ ok: boolean; message: string }>("/api/lessons/start", {
        method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body),
      });
      setMsg({ ok: true, text: r.message || "Opening the whiteboard." });
    } catch (e) {
      setMsg({ ok: false, text: e instanceof Error && e.message !== "not allowed" ? e.message
        : "This page isn't linked to Stiti. Open it from Stiti's menu bar icon, then try again." });
    } finally {
      setBusy(false);
      onStarted();
    }
  };

  return (
    <dialog ref={dlg} className="note map" aria-labelledby="map-h" onClose={onClose}
      onClick={(e) => { if (e.target === dlg.current) dlg.current?.close(); }}>
      {row && (
        <div className="note__in">
          <header className="note__head">
            <div>
              <p className="label">Map · {row.kind === "file" ? "your file" : "topic"}</p>
              <h2 id="map-h">{row.source}</h2>
            </div>
            <button type="button" className="note__x" aria-label="Close map" onClick={() => dlg.current?.close()}>
              <Icon name="close" />
            </button>
          </header>

          <div className="note__body map__body">
            {!cur && (
              <div aria-busy="true">
                <p className="sr-only" role="status">Opening the map…</p>
                {Array.from({ length: 6 }, (_, i) => <span key={i} className="sk sk--row" />)}
              </div>
            )}
            {cur?.err && <p className="msg is-err" role="alert"><Icon name="alert" />Couldn&apos;t open this map: {cur.err}</p>}
            {m && (
              <>
                <p className="map__sum">
                  {plural(m.total, "topic")} · <b>{m.counts.strong}</b> strong · <b>{m.counts.focus}</b> to focus on ·{" "}
                  <b>{m.counts.not_started}</b> not started{m.due ? <> · <b>{m.due}</b> due for review</> : null}
                </p>

                {/* three columns of concept chips */}
                <div className="cols" role="group" aria-label="Topics by how well you know them">
                  {GROUPS.map((g) => (
                    <section key={g.id} className={`col col--${g.id}`} aria-labelledby={`${id}-${g.id}`}>
                      <h3 id={`${id}-${g.id}`} className="col__h">{g.title}<span className="col__n">{m.groups[g.id].length}</span></h3>
                      <p className="col__l">{g.line}</p>
                      {m.groups[g.id].length ? (
                        <ul className="mchips">
                          {m.groups[g.id].map((c) => (
                            <li key={c.id}>
                              <button type="button" className={`mchip mchip--${c.level}`} aria-pressed={pick?.id === c.id}
                                title={`${c.name} · ${LEVEL[c.level]}${c.p != null ? ` · ${pct(c.p)}` : ""}${c.dropped ? " · was strong, slipped" : ""}`}
                                onClick={() => { setPick(pick?.id === c.id ? null : c); setMsg(null); }}>
                                {c.name}
                                {c.dropped && <svg className="mchip__drop" viewBox="0 0 12 12" aria-label="slipped"><path d="M6 2.5v7M3 6.5l3 3 3-3" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" /></svg>}
                              </button>
                            </li>
                          ))}
                        </ul>
                      ) : <p className="col__none">None yet.</p>}
                    </section>
                  ))}
                </div>
                <p className="legend map__legend">
                  <span><i className="dot dot--k" />strong</span><span><i className="dot dot--s" />shaky</span>
                  <span><i className="dot dot--w" />weak</span><span><i className="dot dot--n" />not started</span>
                </p>

                {/* heatmap */}
                <section className="mapsec" aria-labelledby={`${id}-hm`}>
                  <h3 id={`${id}-hm`} className="mapsec__h">Last 30 days</h3>
                  {m.heatmap.rows.length ? (
                    <div className="hm" style={{ ["--days" as string]: m.heatmap.days.length }}>
                      <div className="hm__row hm__row--days" aria-hidden="true">
                        <span />
                        {m.heatmap.days.map((d, i) => (i % 7 === 0 && i <= m.heatmap.days.length - 6 ? (
                          <span key={d} className="hm__day" style={{ gridColumn: `${i + 2} / span 4` }}>{shortDay(d)}</span>
                        ) : null))}
                        <span className="hm__day hm__day--end" style={{ gridColumn: `${m.heatmap.days.length - 1} / span 3` }}>Today</span>
                      </div>
                      {m.heatmap.rows.map((r) => {
                        const hit = r.cells.filter(Boolean) as [number, number][];
                        const n = hit.reduce((s, c) => s + c[0], 0);
                        return (
                          <div key={r.id} className="hm__row" role="img"
                            aria-label={`${r.name}: ${plural(n, "answer")} on ${plural(hit.length, "day")}`}>
                            <span className="hm__name" title={r.name}>{r.name}</span>
                            {r.cells.map((c, i) => (
                              <i key={i} className={`hm__c${c ? ` hm__c--${c[1] >= 0.8 ? "k" : c[1] >= 0.4 ? "s" : "w"}` : ""}`}
                                title={c ? `${shortDay(m.heatmap.days[i])}: ${plural(c[0], "answer")}, ended at ${pct(c[1])}` : undefined} />
                            ))}
                          </div>
                        );
                      })}
                    </div>
                  ) : (
                    <p className="mapsec__none">No answers in the last 30 days. Each lesson and review fills a square per topic per day.</p>
                  )}
                </section>

                {/* at risk on exam day */}
                <section className="mapsec" aria-labelledby={`${id}-risk`}>
                  <div className="mapsec__top">
                    <h3 id={`${id}-risk`} className="mapsec__h">At risk on exam day</h3>
                    <label className="exam">
                      <span className="exam__lab">Exam</span>
                      <input type="date" value={exam} onChange={(e) => setExamDate(e.target.value)} aria-label="Exam date" />
                    </label>
                  </div>
                  {!m.exam ? (
                    <p className="mapsec__none">Set your exam date to see which topics you&apos;d likely forget by then.</p>
                  ) : m.exam_days != null && m.exam_days < 0 ? (
                    <p className="mapsec__none">That date has passed. Pick the next exam.</p>
                  ) : m.at_risk.length ? (
                    <>
                      <p className="mapsec__l">Predicted recall on {fmtDate(`${m.exam}T09:00:00`)} ({m.exam_days === 0 ? "today" : `in ${plural(m.exam_days ?? 0, "day")}`}), riskiest first.</p>
                      <ol className="risk">
                        {m.at_risk.map((r) => (
                          <li key={r.id} className="risk__row">
                            <span className="risk__name">{r.name}</span>
                            <span className="risk__bar" aria-hidden="true"><i style={{ width: pct(r.recall) }} /></span>
                            <span className="risk__m">{pct(r.recall)} recall · weight {r.weight}</span>
                          </li>
                        ))}
                      </ol>
                    </>
                  ) : (
                    <p className="mapsec__none">Nothing at risk: you should still remember every topic on that day.</p>
                  )}
                </section>
              </>
            )}
          </div>

          <footer className="note__foot map__foot">
            {msg ? (
              <div className={msg.ok ? "done map__done" : "msg is-err"} role={msg.ok ? "status" : "alert"}>
                <Icon name={msg.ok ? "check" : "alert"} className={msg.ok ? "done__ico" : undefined} />
                <span className="map__msg">{msg.text}</span>
                {msg.ok && <a className="btn-glass" href={boardUrl} target="_blank" rel="noopener noreferrer">Open board <Icon name="open" /></a>}
              </div>
            ) : (
              <>
                <p className="map__pick">
                  {pick ? <>A focused lesson on <b>{pick.name}</b>{m?.exam_days != null && m.exam_days >= 0 && m.exam_days <= 60 ? ", exam order" : ""}.</>
                    : m && !m.target ? "This file isn't in your folders any more, so lessons can't start from here."
                    : "Pick a topic above to learn just that."}
                </p>
                <button type="button" className="btn-ink" disabled={!pick || !m?.target || busy || active} onClick={() => void teach()}>
                  {busy ? "Starting…" : active ? "A lesson is running" : "Teach me this"} {!busy && !active && <Arrow />}
                </button>
              </>
            )}
          </footer>
        </div>
      )}
    </dialog>
  );
}
