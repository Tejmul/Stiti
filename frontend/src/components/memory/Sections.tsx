"use client";
// The read-only parts of Stiti's memory: people, how to talk to him, habits, mood, files, plans.
import type { Mind } from "@/lib/stiti";
import { fmtDay, fmtTime, plural } from "@/lib/stiti";
import { Empty, Section } from "./bits";

const CAT: Record<string, string> = {
  talk_style: "How to talk to me", boundary: "Never do", routine: "My routine", preference: "Preferences", goal: "Goals",
};
const pct = (x: number) => `${Math.round(x * 100)}%`;
const when = (iso: string) => { const d = new Date(iso); return `${fmtDay(d)} ${fmtTime(d)}`; };

export function People({ d }: { d: Mind }) {
  return (
    <Section id="people" thin="People" bold="& places" note="Everyone and everything you've mentioned, linked to what you said about them.">
      {d.people.length ? (
        <div className="cards">
          {d.people.map((p) => (
            <article className="card" id={`person-${p.id}`} key={p.id}>
              <p className="label">{p.kind}</p>
              <h3>{p.name}</h3>
              <p>{p.summary || p.facts.join(" · ") || "Mentioned in conversation."}</p>
            </article>
          ))}
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

export function Rules({ d }: { d: Mind }) {
  const cats = [...Object.keys(CAT), ...new Set(d.directives.map((x) => x.category).filter((c) => !(c in CAT)))]
    .filter((c) => d.directives.some((x) => x.category === c));
  const any = cats.length || d.lessons.length || d.traits.length || d.reflections.length;
  return (
    <Section id="rules" thin="How to talk" bold="to you" note="Your instructions and the lessons Stiti learned from your corrections. These are rules, not suggestions.">
      {!any && (
        <Empty say={["don't call me bro", "keep replies short when I'm stressed", "talk to me in Hinglish"]}>
          No rules yet. Correct Stiti once and it becomes a permanent rule here — she checks these before every reply.
          You can also write them in <code>LESSONS.md</code>.
        </Empty>
      )}
      {cats.map((c) => (
        <div className="group" key={c}>
          <h3 className="label group__h">{CAT[c] ?? c.replace(/_/g, " ")}</h3>
          <ul className="list">
            {d.directives.filter((x) => x.category === c).map((x) => (
              <li className="row" id={`directive-${x.id}`} key={x.id}><span className="row__text">{x.text}</span></li>
            ))}
          </ul>
        </div>
      ))}
      {d.lessons.length > 0 && (
        <div className="group">
          <h3 className="label group__h">Lessons from your corrections</h3>
          <ul className="list">
            {d.lessons.map((l) => (
              <li className="row" id={`lesson-${l.id}`} key={l.id}>
                <span className={`tag${l.dont ? " tag--dont" : ""}`}>{l.dont ? "Don't" : "Do"}</span>
                <span className="row__text">{l.text}
                  <span className="row__meta">when {l.when} · seen {l.seen}× · {pct(l.confidence)} sure</span>
                </span>
                <span className="conf" aria-hidden="true"><i style={{ width: pct(l.confidence) }} /></span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {d.traits.length > 0 && (
        <div className="group">
          <h3 className="label group__h">How Stiti reads you (tentative)</h3>
          <ul className="list">
            {d.traits.map((t) => (
              <li className="row" key={t.key}>
                <span className="row__text">{t.label}
                  <span className="row__meta">{pct(t.confidence)} sure · rewrite it in USER.md if it&apos;s wrong</span>
                </span>
                <span className="conf" aria-hidden="true"><i style={{ width: pct(t.confidence) }} /></span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {d.reflections.length > 0 && (
        <div className="group">
          <h3 className="label group__h">What she noticed overnight</h3>
          <ul className="list">
            {d.reflections.map((r, i) => (
              <li className="row" key={i}>
                <span className="row__text">{r.text}<span className="row__meta">{fmtDay(new Date(r.at))}</span></span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </Section>
  );
}

export function Habits({ d }: { d: Mind }) {
  return (
    <Section id="habits" thin="Habits" bold="this fortnight" note="Last 14 days. Filled = done, ring = missed, blank = no check-in.">
      {d.habits.length ? (
        <div className="list">
          {d.habits.map((h, i) => {
            const done = h.days.filter((x) => x === true).length, missed = h.days.filter((x) => x === false).length;
            return (
              <div className="habit" id={`habit-${i}`} key={i}>
                <div>
                  <span className="habit__name">{h.name}</span>
                  <span className="row__meta">
                    {h.target ? `goal ${h.target}× a week · ` : ""}{done} of 14 days · strength {pct(h.strength)}{h.status !== "active" ? ` · ${h.status}` : ""}
                  </span>
                </div>
                <div className="days" role="img" aria-label={`${h.name}: done ${done}, missed ${missed}, no check-in ${14 - done - missed} of the last 14 days`}>
                  {h.days.map((x, k) => <i key={k} className={x === true ? "y" : x === false ? "n" : undefined} />)}
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <Empty say={["I want to go to the gym 4 times a week", "help me read 20 pages every night"]}>
          No habits tracked yet. Tell Stiti what you want to keep doing; she&apos;ll check in at the right moments and
          the last two weeks show up here as a dot strip.
        </Empty>
      )}
    </Section>
  );
}

export function Mood({ d }: { d: Mind }) {
  const max = Math.max(1, ...d.mood.map((m) => m.n));
  const heard = d.mood.filter((m) => m.label).length;
  return (
    <Section id="mood" thin="Mood" bold="from your voice & words"
      note={<>The mood Stiti heard most each day; bar height = how much you talked.{heard < 3 ? " It fills in as you talk more." : ""}</>}>
      <ol className="mood" aria-label={heard ? "Mood per day for the last 14 days" : "No mood heard in the last 14 days"}>
        {d.mood.map((m, i) => {
          const day = new Date(m.day + "T12:00:00");
          const h = m.n ? Math.round(16 + 96 * (m.n / max)) : 6;
          const mix = Object.entries(m.mix).map(([k, v]) => `${k} ${v}`).join(", ");
          const lab = (m.label || "none").toLowerCase().replace(/[^a-z]/g, "");
          return (
            <li key={m.day} className={`mood__day mood--${lab}`} style={{ "--i": i } as React.CSSProperties} title={`${fmtDay(day)}: ${mix || "no talk"}`}>
              <span className="sr-only">{fmtDay(day)}: {m.label ? `${m.label}, ${plural(m.n, "message")}` : "no talk"}</span>
              <span className="mood__lab" aria-hidden="true">{m.label || "—"}</span>
              <span className="mood__bar" aria-hidden="true" style={{ height: h }} />
              <span className="mood__d" aria-hidden="true">{day.toLocaleDateString([], { day: "numeric" })}</span>
            </li>
          );
        })}
      </ol>
    </Section>
  );
}

export function Files({ d }: { d: Mind }) {
  return (
    <Section id="files" thin="Files" bold="she has read" note={<>Documents Stiti can quote from. Add one with <code>uv run stiti ingest &lt;file&gt;</code>.</>}>
      {d.docs.length ? (
        <ul className="list">
          {d.docs.map((x, i) => (
            <li className="row" id={`doc-${i}`} key={i}>
              <span className="tag">{x.kind}</span>
              <span className="row__text">{x.title}
                <span className="row__meta">{plural(x.chunks, "passage")} · read {fmtDay(new Date(x.at))}</span>
              </span>
            </li>
          ))}
        </ul>
      ) : (
        <Empty cta={false}>No files yet. Give Stiti a PDF, your notes or a resume: <code>uv run stiti ingest ~/Documents/notes</code>.</Empty>
      )}
    </Section>
  );
}

export function Plans({ d }: { d: Mind }) {
  return (
    <Section id="plans" thin="Plans" bold="& reminders" note="Open todos, alarms and study courses. Change them by telling Stiti.">
      <div className="plans">
        <div>
          <h3 className="label group__h">Todos</h3>
          {d.todos.length ? (
            <ul className="list">
              {d.todos.map((t) => (
                <li className="row" key={t.id}><span className="row__text">{t.title}
                  {t.due && <span className="row__meta">due {when(t.due)}</span>}</span></li>
              ))}
            </ul>
          ) : <Empty say={["add call mom to my todos"]}>Nothing open.</Empty>}
        </div>
        <div>
          <h3 className="label group__h">Alarms &amp; reminders</h3>
          {d.alarms.length ? (
            <ul className="list">
              {d.alarms.map((a) => (
                <li className="row" key={a.id}>
                  <span className="tag">{a.kind}</span>
                  <span className="row__text">{a.kind === "alarm" ? a.text || "Alarm" : a.text || "Reminder"}
                    <span className="row__meta">{when(a.at)}{a.repeats ? " · repeats" : ""}</span></span>
                </li>
              ))}
            </ul>
          ) : <Empty say={["wake me up at 7"]}>None set.</Empty>}
        </div>
        <div>
          <h3 className="label group__h">Study</h3>
          {d.courses.length ? (
            <ul className="list">
              {d.courses.map((c, i) => (
                <li className="row" key={i}><span className="row__text">{c.title}
                  <span className="row__meta">{c.status} · {fmtDay(new Date(c.at))}</span></span></li>
              ))}
            </ul>
          ) : <Empty say={["teach me operating systems tonight"]}>No courses.</Empty>}
        </div>
      </div>
    </Section>
  );
}
