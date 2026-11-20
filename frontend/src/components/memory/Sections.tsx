"use client";
// The other parts of Stiti's memory: people, how to talk to him, recent notes, plans, habits, mood, files.
// Each takes the search query `q`; while searching, a section with nothing matching renders nothing.
import { useState } from "react";
import type { Mind } from "@/lib/stiti";
import { api, fmtDay, fmtTime, plural } from "@/lib/stiti";
import { Empty, Hi, Icon, Section, has } from "./bits";

type P = { d: Mind; q: string };

const CAT: Record<string, string> = {
  talk_style: "How to talk to me", boundary: "Never do", routine: "My routine", preference: "Likes & preferences", goal: "Goals",
};
const KIND: Record<string, string> = { person: "People", org: "Organisations", project: "Projects", place: "Places", thing: "Things" };
const KIND_ONE: Record<string, string> = { person: "Person", org: "Organisation", project: "Project", place: "Place", thing: "Thing" };
const pct = (x: number) => `${Math.round(x * 100)}%`;
const when = (iso: string) => { const d = new Date(iso); return `${fmtDay(d)} · ${fmtTime(d)}`; };

// ------------------------------------------------------------------ people & places
export function People({ d, q }: P) {
  const [kind, setKind] = useState("all");
  const kinds = [...new Set(d.people.map((p) => p.kind))];
  const matches = d.people.filter((p) => has(q, p.name, p.summary, p.kind, ...p.facts));
  const shown = q ? matches : matches.filter((p) => kind === "all" || p.kind === kind);
  if (q && !matches.length) return null;

  const chips = !q && kinds.length > 1 && (
    <div className="chips" role="group" aria-label="Show">
      {["all", ...kinds].map((k) => (
        <button key={k} type="button" className="chip" aria-pressed={kind === k} onClick={() => setKind(k)}>
          {k === "all" ? "All" : KIND[k] ?? k}
          <span className="chip__n">{k === "all" ? d.people.length : d.people.filter((p) => p.kind === k).length}</span>
        </button>
      ))}
    </div>
  );

  return (
    <Section id="people" thin="People" bold="& places" n={q ? matches.length : d.people.length}
      note="Everyone and everything you've mentioned, linked to what you said about them." aside={chips}>
      {d.people.length ? (
        <div className="cards">
          {shown.map((p) => {
            const lines = p.summary ? [p.summary] : [...new Set(p.facts)];
            return (
              <article className="card" id={`person-${p.id}`} key={p.id}>
                <p className="card__kind"><Icon name={KIND_ONE[p.kind] ? p.kind : "thing"} />{KIND_ONE[p.kind] ?? p.kind}</p>
                <h3><Hi text={p.name} q={q} /></h3>
                {lines.length ? (
                  <ul className="card__lines">{lines.map((l, i) => <li key={i}><Hi text={l} q={q} /></li>)}</ul>
                ) : <p className="card__none">Mentioned in conversation. No details yet.</p>}
              </article>
            );
          })}
        </div>
      ) : (
        <Empty say={["my sister Ayesha lives in Pune", "Rohan is my teammate at work", "I grew up in Guwahati"]}>
          No one yet. Mention people and places the way you&apos;d tell a friend, and Stiti links them to everything you
          say about them. The nightly sleep job files them here.
        </Empty>
      )}
    </Section>
  );
}

// ------------------------------------------------------------------ how to talk to you
export function Rules({ d, q }: P) {
  const dirs = d.directives.filter((x) => has(q, x.text));
  const lessons = d.lessons.filter((l) => has(q, l.text, l.when));
  const traits = d.traits.filter((t) => has(q, t.label));
  const cats = [...Object.keys(CAT), ...new Set(dirs.map((x) => x.category).filter((c) => !(c in CAT)))]
    .filter((c) => dirs.some((x) => x.category === c));
  const n = dirs.length + lessons.length + traits.length;
  if (q && !n) return null;

  return (
    <Section id="rules" thin="How to talk" bold="to you" n={n}
      note="Your instructions and the lessons Stiti learned from your corrections. She checks these before every reply.">
      {!n && (
        <Empty say={["don't call me bro", "keep replies short when I'm stressed", "talk to me in Hinglish"]}>
          No rules yet. Correct Stiti once and it becomes a permanent rule here. You can also write them in <code>LESSONS.md</code>.
        </Empty>
      )}
      {n > 0 && (
        <div className="groups">
          {cats.map((c) => (
            <div className="panel group" key={c}>
              <h3 className="panel__h"><span className="label">{CAT[c] ?? c.replace(/_/g, " ")}</span>
                <span className="panel__n">{dirs.filter((x) => x.category === c).length}</span></h3>
              <ul className="list">
                {dirs.filter((x) => x.category === c).map((x) => (
                  <li className="row" id={`directive-${x.id}`} key={x.id}>
                    {c === "boundary" && <span className="tag tag--dont">Never</span>}
                    <span className="row__text"><Hi text={x.text} q={q} /></span>
                  </li>
                ))}
              </ul>
            </div>
          ))}
          {lessons.length > 0 && (
            <div className="panel group">
              <h3 className="panel__h"><span className="label">Lessons from your corrections</span><span className="panel__n">{lessons.length}</span></h3>
              <ul className="list">
                {lessons.map((l) => (
                  <li className="row" id={`lesson-${l.id}`} key={l.id}>
                    <span className={`tag${l.dont ? " tag--dont" : ""}`}>{l.dont ? "Don't" : "Do"}</span>
                    <span className="row__text"><Hi text={l.text} q={q} />
                      <span className="row__meta">when <Hi text={l.when} q={q} /> · seen {l.seen}× · {pct(l.confidence)} sure</span>
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}
          {traits.length > 0 && (
            <div className="panel group">
              <h3 className="panel__h"><span className="label">How Stiti reads you · tentative</span><span className="panel__n">{traits.length}</span></h3>
              <ul className="list">
                {traits.map((t) => (
                  <li className="row" key={t.key}>
                    <span className="row__text"><Hi text={t.label} q={q} />
                      <span className="row__meta">{pct(t.confidence)} sure · rewrite it in USER.md if it&apos;s wrong</span>
                    </span>
                    <span className="conf" aria-hidden="true"><i style={{ width: pct(t.confidence) }} /></span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </Section>
  );
}

// ------------------------------------------------------------------ recent notes (what she noticed overnight)
export function Notes({ d, q }: P) {
  const list = d.reflections.filter((r) => has(q, r.text));
  if (q && !list.length) return null;
  return (
    <Section id="notes" thin="Recent" bold="notes" n={list.length}
      note="What Stiti noticed about your life lately, written by her nightly sleep job. Her notes, not your words.">
      {list.length ? (
        <ol className="panel timeline">
          {list.map((r, i) => {
            const at = new Date(r.at);
            return (
              <li className="row" key={i}>
                <time className="timeline__when" dateTime={r.at}>{fmtDay(at)}</time>
                <span className="row__text"><Hi text={r.text} q={q} /></span>
              </li>
            );
          })}
        </ol>
      ) : (
        <Empty cta={false}>Nothing yet. Each night Stiti looks back over the day and writes down what she noticed — it shows up here.</Empty>
      )}
    </Section>
  );
}

// ------------------------------------------------------------------ plans: todos (tick to finish), alarms, study
function Todo({ t, q, onDone }: { t: Mind["todos"][number]; q: string; onDone: (id: number) => Promise<boolean> }) {
  const [state, setState] = useState<"" | "busy" | "err">("");
  const click = async () => {
    if (state === "busy") return;
    setState("busy");
    if (!(await onDone(t.id))) setState("err");
  };
  return (
    <li className={`row todo${state === "busy" ? " is-done" : ""}`}>
      <button className="todo__check" type="button" aria-pressed={state === "busy"} aria-label={`Mark “${t.title}” done`} onClick={click}>
        <Icon name="check" />
      </button>
      <span className="row__text"><Hi text={t.title} q={q} />
        {t.due && <span className="row__meta">due {when(t.due)}</span>}
        {state === "err" && <span className="row__meta is-err">Couldn&apos;t mark it done. Try again.</span>}
      </span>
    </li>
  );
}

export function Plans({ d, q, onChanged }: P & { onChanged: () => Promise<void> }) {
  const todos = d.todos.filter((t) => has(q, t.title));
  const alarms = d.alarms.filter((a) => has(q, a.text, a.kind));
  const courses = d.courses.filter((c) => has(q, c.title));
  const n = todos.length + alarms.length + courses.length;
  if (q && !n) return null;
  const done = async (id: number) => {
    try { await api(`/api/todo/${id}/done`, { method: "POST" }); await onChanged(); return true; } catch { return false; }
  };
  return (
    <Section id="plans" thin="Plans" bold="& reminders" n={n} note="Open todos, alarms and study courses. Tick a todo to finish it; tell Stiti to change the rest.">
      <div className="plans">
        {(!q || todos.length > 0) && (
          <div className="panel">
            <h3 className="panel__h"><span className="label">Todos</span><span className="panel__n">{todos.length || ""}</span></h3>
            {todos.length ? <ul className="list">{todos.map((t) => <Todo key={t.id} t={t} q={q} onDone={done} />)}</ul>
              : <Empty small say={["add call mom to my todos"]}>Nothing open.</Empty>}
          </div>
        )}
        {(!q || alarms.length > 0) && (
          <div className="panel">
            <h3 className="panel__h"><span className="label">Alarms &amp; reminders</span><span className="panel__n">{alarms.length || ""}</span></h3>
            {alarms.length ? (
              <ul className="list">
                {alarms.map((a) => (
                  <li className="row" key={a.id}>
                    <Icon name="bell" className="row__ico" />
                    <span className="row__text"><Hi text={a.text || (a.kind === "alarm" ? "Alarm" : "Reminder")} q={q} />
                      <span className="row__meta">{a.kind} · {when(a.at)}{a.repeats ? " · repeats" : ""}</span></span>
                  </li>
                ))}
              </ul>
            ) : <Empty small say={["wake me up at 7"]}>None set.</Empty>}
          </div>
        )}
        {(!q || courses.length > 0) && (
          <div className="panel">
            <h3 className="panel__h"><span className="label">Study</span><span className="panel__n">{courses.length || ""}</span></h3>
            {courses.length ? (
              <ul className="list">
                {courses.map((c, i) => (
                  <li className="row" key={i}>
                    <Icon name="book" className="row__ico" />
                    <span className="row__text"><Hi text={c.title} q={q} /><span className="row__meta">{c.status} · {fmtDay(new Date(c.at))}</span></span>
                  </li>
                ))}
              </ul>
            ) : <Empty small say={["teach me operating systems tonight"]}>No courses.</Empty>}
          </div>
        )}
      </div>
    </Section>
  );
}

// ------------------------------------------------------------------ habits
export function Habits({ d, q }: P) {
  const list = d.habits.filter((h) => has(q, h.name, h.cue));
  if (q && !list.length) return null;
  return (
    <Section id="habits" thin="Habits" bold="this fortnight" n={list.length} note="Last 14 days. Filled = done, ring = missed, blank = no check-in.">
      {list.length ? (
        <div className="panel">
          <ul className="list">
            {list.map((h, i) => {
              const yes = h.days.filter((x) => x === true).length, no = h.days.filter((x) => x === false).length;
              return (
                <li className="row habit" key={i}>
                  <span className="row__text"><Hi text={h.name} q={q} />
                    <span className="row__meta">
                      {h.target ? `goal ${h.target}× a week · ` : ""}{yes} of 14 days · strength {pct(h.strength)}{h.status !== "active" ? ` · ${h.status}` : ""}
                    </span>
                  </span>
                  <span className="days" role="img" aria-label={`${h.name}: done ${yes}, missed ${no}, no check-in ${14 - yes - no} of the last 14 days`}>
                    {h.days.map((x, k) => <i key={k} className={x === true ? "y" : x === false ? "n" : undefined} />)}
                  </span>
                </li>
              );
            })}
          </ul>
        </div>
      ) : (
        <Empty say={["I want to go to the gym 4 times a week", "help me read 20 pages every night"]}>
          No habits tracked yet. Tell Stiti what you want to keep doing; she&apos;ll check in at the right moments and
          the last two weeks show up here.
        </Empty>
      )}
    </Section>
  );
}

// ------------------------------------------------------------------ mood (hidden while searching)
export function Mood({ d, q }: P) {
  if (q) return null;
  const max = Math.max(1, ...d.mood.map((m) => m.n));
  const heard = d.mood.filter((m) => m.label).length;
  return (
    <Section id="mood" thin="Mood" bold="from your voice & words"
      note={<>The mood Stiti heard most each day; bar height = how much you talked.{heard < 3 ? " It fills in as you talk more." : ""}</>}>
      <ol className="panel mood" aria-label={heard ? "Mood per day for the last 14 days" : "No mood heard in the last 14 days"}>
        {d.mood.map((m) => {
          const day = new Date(m.day + "T12:00:00");
          const h = m.n ? Math.round(14 + 82 * (m.n / max)) : 4;
          const mix = Object.entries(m.mix).map(([k, v]) => `${k} ${v}`).join(", ");
          const lab = (m.label || "none").toLowerCase().replace(/[^a-z]/g, "");
          return (
            <li key={m.day} className={`mood__day mood--${lab}`} title={`${fmtDay(day)}: ${mix || "no talk"}`}>
              <span className="sr-only">{fmtDay(day)}: {m.label ? `${m.label}, ${plural(m.n, "message")}` : "no talk"}</span>
              <span className="mood__lab" aria-hidden="true">{m.label || ""}</span>
              <span className="mood__bar" aria-hidden="true" style={{ height: h }} />
              <span className="mood__d" aria-hidden="true">{day.toLocaleDateString([], { day: "numeric" })}</span>
            </li>
          );
        })}
      </ol>
    </Section>
  );
}

// ------------------------------------------------------------------ files
export function Files({ d, q }: P) {
  const list = d.docs.map((x, i) => ({ ...x, i })).filter((x) => has(q, x.title, x.kind));
  if (q && !list.length) return null;
  return (
    <Section id="files" thin="Files" bold="she has read" n={list.length}
      note={<>Documents Stiti can quote from. Add one with <code>uv run stiti ingest &lt;file&gt;</code>.</>}>
      {list.length ? (
        <div className="panel">
          <ul className="list">
            {list.map((x) => (
              <li className="row" id={`doc-${x.i}`} key={x.i}>
                <Icon name="file" className="row__ico" />
                <span className="row__text"><Hi text={x.title} q={q} />
                  <span className="row__meta">{x.kind} · {plural(x.chunks, "passage")} · read {fmtDay(new Date(x.at))}</span>
                </span>
              </li>
            ))}
          </ul>
        </div>
      ) : (
        <Empty cta={false}>No files yet. Give Stiti a PDF, your notes or a resume: <code>uv run stiti ingest ~/Documents/notes</code>.</Empty>
      )}
    </Section>
  );
}
