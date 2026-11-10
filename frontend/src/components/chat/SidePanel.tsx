"use client";
// Left pane (bottom sheet on mobile): her mind sphere + state, hello, brain status, what she knows,
// todos (check to finish) and upcoming alarms/reminders.
import Link from "next/link";
import { useState, type Ref } from "react";
import { fmtDay, fmtTime, plural, type DayState, type Mind } from "@/lib/stiti";
import MindCanvas, { type MindHandle, type MindState } from "./MindCanvas";

export type Brain = "connecting" | "on" | "off" | "lost";
const BRAIN_TEXT: Record<Brain, string> = {
  connecting: "Connecting to Stiti…",
  on: "Thinking brain connected (free cloud model)",
  off: "Thinking brain offline — todos, alarms and memory still work",
  lost: "Lost the connection to Stiti. Is uv run stiti web still running?",
};

type Props = {
  name: string | null;
  brain: Brain;
  mindState: MindState;
  mindLabel: string;
  mindRef: Ref<MindHandle>;
  day: DayState;
  knows: Mind | null;
  open: boolean;
  onClose: () => void;
  onDone: (id: number) => Promise<boolean>;
};

function Todo({ t, onDone }: { t: DayState["todos"][number]; onDone: Props["onDone"] }) {
  const [done, setDone] = useState(false);
  const [leaving, setLeaving] = useState(false);
  const due = t.due ? new Date(t.due) : null;
  const click = async () => {
    if (done) return;
    setDone(true);                                         // box fills + tick draws
    const fold = setTimeout(() => setLeaving(true), 520);  // then the row folds away
    if (!(await onDone(t.id))) { clearTimeout(fold); setDone(false); setLeaving(false); }
  };
  return (
    <li className={`todo${done ? " is-done" : ""}${leaving ? " is-leaving" : ""}`}>
      <div className="todo__in">
        <button className="todo__check" type="button" aria-pressed={done} aria-label={`Mark “${t.title}” done`} onClick={click}>
          <svg viewBox="0 0 16 16" fill="none" aria-hidden="true">
            <path d="M3.5 8.5l3 3 6-7" pathLength={1} stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>
        <span>
          <span className="todo__title">{t.title}</span>
          {due && <span className="todo__due">due {fmtDay(due)} {fmtTime(due)}</span>}
        </span>
      </div>
    </li>
  );
}

function Knows({ knows }: { knows: Mind | null }) {
  if (!knows) return null;
  const c = knows.counts;
  const bits = [
    c.facts && plural(c.facts, "fact"),
    c.people && plural(c.people, "person", "people"),
    c.moments && plural(c.moments, "message"),
    c.docs && plural(c.docs, "file"),
  ].filter(Boolean);
  const facts = knows.facts.slice(0, 3);
  return (
    <section className="today knows" aria-labelledby="knows-h">
      <div className="today__head"><h2 className="label" id="knows-h">Stiti knows</h2></div>
      {bits.length > 0 && <p className="knows__counts">{bits.join(" · ")}</p>}
      {facts.length > 0 ? (
        <>
          <ul className="knows__facts">{facts.map((f) => <li key={f.id}>{f.text}</li>)}</ul>
          <Link className="knows__link" href="/memory">See everything she knows <span aria-hidden="true">→</span></Link>
        </>
      ) : (
        <Link className="knows__link knows__link--empty" href="/memory">
          Tell her about yourself in Memory <span aria-hidden="true">→</span>
        </Link>
      )}
    </section>
  );
}

export default function SidePanel({ name, brain, mindState, mindLabel, mindRef, day, knows, open, onClose, onDone }: Props) {
  const nTodos = day.todos.length;
  return (
    <aside className={`side${open ? " is-open" : ""}`} id="side" aria-label="Stiti and today">
      <div className="mind">
        <MindCanvas ref={mindRef} state={mindState} />
        <p className="mind__state label" aria-live="polite">{mindLabel}</p>
      </div>
      <h1 className="hello"><span className="thin">Hi</span> <span className="bold">{name || "there"}.</span></h1>
      <p className={`brain${brain === "on" ? " is-on" : brain === "connecting" ? "" : " is-off"}`}>
        <span className="brain__dot" aria-hidden="true" /><span>{BRAIN_TEXT[brain]}</span>
      </p>

      <Knows knows={knows} />

      <section className="today" aria-labelledby="todos-h">
        <div className="today__head"><h2 className="label" id="todos-h">Todos</h2><span className="label">{nTodos || ""}</span></div>
        <ul className="todos">{day.todos.map((t) => <Todo key={t.id} t={t} onDone={onDone} />)}</ul>
        {!nTodos && <p className="empty">Nothing open. Say “add call mom to my todos”.</p>}
      </section>
      <section className="today" aria-labelledby="alarms-h">
        <div className="today__head"><h2 className="label" id="alarms-h">Alarms &amp; reminders</h2></div>
        <ul className="alarms">
          {day.alarms.map((a) => {
            const at = new Date(a.at);
            return (
              <li className="alarm" key={a.id}>
                {/* eslint-disable-next-line @next/next/no-img-element -- static export, tiny local pictogram */}
                <img src="/icons/180.png" alt="" width={20} height={20} />
                <span>
                  <span className="alarm__text">{a.kind === "alarm" ? "Alarm" : a.text || "Reminder"}</span>
                  <span className="alarm__at">{a.kind} · {fmtDay(at)} {fmtTime(at)}</span>
                </span>
              </li>
            );
          })}
        </ul>
        {!day.alarms.length && <p className="empty">None set. Try “remind me to stretch in 1 hour”.</p>}
      </section>
      <button className="side__close" type="button" onClick={onClose}>Back to chat</button>
    </aside>
  );
}
