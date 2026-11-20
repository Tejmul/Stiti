"use client";
// "Start a lesson": what (one of his files, or a topic) → goal (learn / exam / the whole syllabus today) → optional
// focus + hold-to-talk → Start. POST /api/lessons/start; the coach then skips its spoken goal question.
import { useId, useState } from "react";
import type { LessonMode, LessonStart, StudyFile } from "@/lib/stiti";
import { api } from "@/lib/stiti";
import { Arrow, Icon, fmtDate, fmtSize } from "./bits";

export type Pick = { kind: "file" | "topic"; path: string; topic: string };

const MODES: { id: LessonMode; title: string; line: string }[] = [
  { id: "learn", title: "Learn", line: "Understand it properly. Skips what you already know." },
  { id: "exam", title: "Exam", line: "What exams ask most, first. Quick checks on the rest." },
  { id: "day", title: "Whole syllabus today", line: "All of it, in the hours you have, with short breaks." },
];
const WHEN = [{ d: 0, t: "Today" }, { d: 1, t: "Tomorrow" }, { d: 3, t: "In a few days" }, { d: 7, t: "A week or more" }];
const MAX_TOPIC = 120;

type Props = {
  files: StudyFile[];
  active: boolean;
  boardUrl: string;
  pick: Pick;
  setPick: (p: Pick) => void;
  onStarted: () => void;
};

export default function StartCard({ files, active, boardUrl, pick, setPick, onStarted }: Props) {
  const [mode, setMode] = useState<LessonMode>("learn");
  const [days, setDays] = useState(1);
  const [hours, setHours] = useState(6);
  const [focus, setFocus] = useState("");
  const [ptt, setPtt] = useState(false);
  const [blurt, setBlurt] = useState(false);
  const [fq, setFq] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [started, setStarted] = useState("");
  const id = useId();

  const file = files.find((f) => f.path === pick.path);
  const topic = pick.topic.trim();
  const ready = pick.kind === "file" ? !!file : topic.length > 0 && topic.length <= MAX_TOPIC;
  const shown = fq.trim() ? files.filter((f) => f.name.toLowerCase().includes(fq.trim().toLowerCase())) : files;

  const start = async () => {
    if (!ready || busy || active) return;
    setBusy(true); setErr(""); setStarted("");
    const body: LessonStart = { target: pick.kind === "file" ? pick.path : topic, mode, ptt };
    if (blurt) body.blurt = true;
    if (mode === "day") body.hours = hours;
    if (mode === "exam") body.days = days;
    if (focus.trim()) body.focus = focus.trim();
    try {
      const r = await api<{ ok: boolean; message: string }>("/api/lessons/start", {
        method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body),
      });
      setStarted(r.message || "Opening the whiteboard.");
      onStarted();
    } catch (e) {
      setErr(e instanceof Error && e.message !== "not allowed" ? e.message
        : "This page isn't linked to Stiti. Open it from Stiti's menu bar icon, then try again.");
      onStarted();                                          // refresh: maybe a lesson is already running
    } finally {
      setBusy(false);
    }
  };

  const summary = [
    pick.kind === "file" ? file?.name : topic || null,
    MODES.find((m) => m.id === mode)!.title + (mode === "day" ? ` · ${hours} h` : mode === "exam" ? ` · ${WHEN.find((w) => w.d === days)!.t.toLowerCase()}` : ""),
    focus.trim() ? `focus: ${focus.trim()}` : null,
    ptt ? "hold to talk" : null,
    blurt ? "Blurt test" : null,
  ].filter(Boolean).join(" · ");

  return (
    <section className="start" id="start" aria-labelledby="start-h">
      <header className="sec__head">
        <h2 id="start-h"><span className="thin">Start a</span> <span className="bold">lesson</span></h2>
        <p className="sec__note">She teaches by voice on the whiteboard, asks you short questions as she goes, and saves notes here.</p>
      </header>

      {/* 1 · what */}
      <fieldset className="step">
        <legend className="step__h"><span className="step__n">1</span>What do you want to learn?</legend>
        <div className="seg" role="group" aria-label="Learn from">
          <button type="button" className="seg__b" aria-pressed={pick.kind === "file"} onClick={() => setPick({ ...pick, kind: "file" })}>
            <Icon name="file" />One of your files
          </button>
          <button type="button" className="seg__b" aria-pressed={pick.kind === "topic"} onClick={() => setPick({ ...pick, kind: "topic" })}>
            <Icon name="topic" />A topic
          </button>
        </div>

        {pick.kind === "file" ? (
          files.length ? (
            <div className="files">
              {files.length > 6 && (
                <div className="filter">
                  <Icon name="search" className="filter__ico" />
                  <label className="sr-only" htmlFor={`${id}-fq`}>Filter your files</label>
                  <input id={`${id}-fq`} type="search" value={fq} placeholder={`Filter ${files.length} files`} autoComplete="off"
                    onChange={(e) => setFq(e.target.value)} onKeyDown={(e) => { if (e.key === "Escape") setFq(""); }} />
                </div>
              )}
              <div className="files__list" role="radiogroup" aria-label="Your files">
                {shown.map((f) => (
                  <label key={f.path} className={`file${f.path === pick.path ? " is-on" : ""}`} title={f.path}>
                    <input type="radio" name={`${id}-file`} className="sr-only" checked={f.path === pick.path}
                      onChange={() => setPick({ ...pick, kind: "file", path: f.path })} />
                    <span className="file__ext">{f.ext}</span>
                    <span className="file__main">
                      <span className="file__name">{f.name}</span>
                      <span className="file__meta">{fmtSize(f.size)} · {fmtDate(f.modified)}</span>
                    </span>
                    <span className="file__tick" aria-hidden="true"><Icon name="check" /></span>
                  </label>
                ))}
                {!shown.length && <p className="files__none">No file matches “{fq.trim()}”.</p>}
              </div>
              <p className="hint">From Downloads, Documents, Desktop and Books (PDF, EPUB, Word, slides, text). Newest first.</p>
            </div>
          ) : (
            <div className="empty empty--small">
              <p className="empty__text">No study files found. Put a PDF, EPUB, Word file or slides in Downloads, Documents, Desktop or
                a <code>~/Books</code> folder and it shows up here. Or switch to <b>A topic</b>.</p>
            </div>
          )
        ) : (
          <div className="field">
            <label className="sr-only" htmlFor={`${id}-topic`}>Topic</label>
            <input id={`${id}-topic`} type="text" value={pick.topic} maxLength={MAX_TOPIC} autoComplete="off"
              placeholder="e.g. how DNS works, photosynthesis, binary search"
              onChange={(e) => setPick({ ...pick, kind: "topic", topic: e.target.value })}
              onKeyDown={(e) => { if (e.key === "Enter") void start(); }} />
            {pick.topic.length > MAX_TOPIC - 20 && <span className="field__count">{pick.topic.length}/{MAX_TOPIC}</span>}
          </div>
        )}
      </fieldset>

      {/* 2 · goal */}
      <fieldset className="step">
        <legend className="step__h"><span className="step__n">2</span>What&apos;s it for?</legend>
        <div className="modes" role="radiogroup" aria-label="Goal">
          {MODES.map((m) => (
            <label key={m.id} className={`mode${mode === m.id ? " is-on" : ""}`}>
              <input type="radio" name={`${id}-mode`} className="sr-only" checked={mode === m.id} onChange={() => setMode(m.id)} />
              <span className="mode__t">{m.title}</span>
              <span className="mode__l">{m.line}</span>
            </label>
          ))}
        </div>
        {mode === "exam" && (
          <div className="sub">
            <p className="sub__h" id={`${id}-when`}>When is the exam?</p>
            <div className="chips" role="group" aria-labelledby={`${id}-when`}>
              {WHEN.map((w) => (
                <button key={w.d} type="button" className="chip" aria-pressed={days === w.d} onClick={() => setDays(w.d)}>{w.t}</button>
              ))}
            </div>
            <p className="hint">{days <= 1 ? "Exam soon: a longer session, the most-asked parts first." : "A normal-length session, exam-first order."}</p>
          </div>
        )}
        {mode === "day" && (
          <div className="sub">
            <label className="sub__h" htmlFor={`${id}-hours`}>Hours you have today</label>
            <div className="hours">
              <input id={`${id}-hours`} type="range" min={1} max={12} step={0.5} value={hours}
                onChange={(e) => setHours(Number(e.target.value))} aria-valuetext={`${hours} hours`}
                style={{ ["--fill" as string]: `${((hours - 1) / 11) * 100}%` }} />
              <output className="hours__v" htmlFor={`${id}-hours`}>{hours}<span> h</span></output>
            </div>
            <p className="hint">She plans to fit, most important first, with a 5-minute break about every 45 minutes.</p>
          </div>
        )}
      </fieldset>

      {/* 3 · options */}
      <fieldset className="step">
        <legend className="step__h"><span className="step__n">3</span>Options</legend>
        <div className="field">
          <label className="field__lab" htmlFor={`${id}-focus`}>Focus on <span>optional</span></label>
          <input id={`${id}-focus`} type="text" value={focus} maxLength={MAX_TOPIC} autoComplete="off"
            placeholder="Only these parts, e.g. SDD and parse trees" onChange={(e) => setFocus(e.target.value)} />
        </div>
        <div className="toggle">
          <button type="button" role="switch" aria-checked={ptt} className="switch" id={`${id}-ptt`} onClick={() => setPtt(!ptt)}>
            <span className="switch__knob" />
          </button>
          <label htmlFor={`${id}-ptt`} className="toggle__text">
            <span className="toggle__t"><Icon name="mic" />Hold to talk</span>
            <span className="toggle__l">For a noisy room: she only listens while you hold Space on the board.</span>
          </label>
        </div>
        <div className="toggle">
          <button type="button" role="switch" aria-checked={blurt} className="switch" id={`${id}-blurt`} onClick={() => setBlurt(!blurt)}>
            <span className="switch__knob" />
          </button>
          <label htmlFor={`${id}-blurt`} className="toggle__text">
            <span className="toggle__t"><Icon name="check" />Blurt</span>
            <span className="toggle__l">Test me at the end of each topic: say everything you remember, and she marks each key point.</span>
          </label>
        </div>
      </fieldset>

      <div className="go">
        <button type="button" className="btn-ink" disabled={!ready || busy || active} onClick={() => void start()}>
          {busy ? "Starting…" : "Start lesson"} {!busy && <Arrow />}
        </button>
        <p className="go__sum" aria-live="polite">
          {active ? "A lesson is already running. Finish it first."
            : ready ? summary : pick.kind === "file" ? "Pick one of your files." : "Type a topic."}
        </p>
      </div>
      <p className="hint go__hint">She won&apos;t ask what it&apos;s for, you&apos;ve said it here. The whiteboard opens in a new tab by itself.</p>

      {err && <p className="msg is-err" role="alert"><Icon name="alert" />{err}</p>}
      {started && !err && (
        <div className="done" role="status">
          <Icon name="check" className="done__ico" />
          <div>
            <p className="done__t">Lesson open on the whiteboard</p>
            <p className="done__l">{started} The board opens in a new tab in a few seconds; if it doesn&apos;t, open it here.</p>
          </div>
          <a className="btn-glass" href={boardUrl} target="_blank" rel="noopener noreferrer">Open board <Icon name="open" /></a>
        </div>
      )}
    </section>
  );
}
