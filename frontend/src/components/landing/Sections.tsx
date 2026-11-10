// Landing markup: what Stiti DOES (not how she works). Pure markup — motion is wired in Landing.tsx / MacShot.tsx.
// Every example line is generic; nothing here is about a real person.
import type { CSSProperties, ReactNode } from "react";
import { GITHUB, QUOTE } from "@/lib/site";
import MacShot from "./MacShot";
import Split from "./Split";

const icon = (n: number) => ({ "--icon": `url(/icons/${n}.png)` }) as CSSProperties;

function Arrow() {
  return (
    <svg className="btn__arrow" viewBox="0 0 26 12" aria-hidden="true">
      <path d="M0 6h24M19 1l5 5-5 5" fill="none" stroke="currentColor" strokeWidth="1.4" />
    </svg>
  );
}

// The site's one action until the app ships (a live demo link comes later).
function GitHubButton({ big }: { big?: boolean }) {
  return (
    <a className={`btn btn--primary${big ? " btn--big" : ""}`} href={GITHUB} target="_blank" rel="noopener">
      <span>View on GitHub</span>
      <span className="sr-only"> (opens in a new tab)</span>
      <Arrow />
    </a>
  );
}

/** A tiny two-line exchange: what you say → what she says. */
function Say({ you, her }: { you: string; her: string }) {
  return (
    <div className="say">
      <p className="say__you"><span className="sr-only">You say: </span>{you}</p>
      <p className="say__her"><span className="sr-only">Stiti says: </span>{her}</p>
    </div>
  );
}

function H2({ id, thin, bold }: { id: string; thin: string; bold: string }) {
  return <h2 className="h2" id={id}><span className="thin"><Split t={thin} /></span> <b><Split t={bold} /></b></h2>;
}

// ------------------------------------------------------------------ hero
export function Hero() {
  return (
    <section className="hero" id="hero" aria-labelledby="hero-title">
      <div className="container hero__grid">
        <div className="hero__copy">
          <p className="label hero__label"><span className="hero__label-text">A VOICE FRIEND THAT LIVES ON YOUR MAC</span></p>
          <h1 className="hero__title" id="hero-title">
            {/* remembers everything · talks like a friend · lives on your Mac (and your data never leaves it) */}
            <span className="line"><Split t="Never " /><b><Split t="forgets." /></b></span>
            <span className="line"><Split t="Always " /><b><Split t="listens." /></b></span>
            <span className="line"><Split t="Never " /><b><Split t="leaves." /></b></span>
          </h1>
          <figure className="hero__quote">
            <blockquote><p><span className="thin">{QUOTE.lead}</span> <b>{QUOTE.punch}</b></p></blockquote>
          </figure>
          <div className="hero__ctas"><GitHubButton /></div>
          <p className="label hero__facts">Free <span aria-hidden="true">·</span> No account <span aria-hidden="true">·</span> Stays on your Mac</p>
        </div>
        <div className="hero__shot"><MacShot /></div>
      </div>
    </section>
  );
}

// ------------------------------------------------------------------ features
const FEATURES: { icon: number; title: string; text: string; you: string; her: string }[] = [
  { icon: 217, title: "Remembers your life",
    text: "Your people, your plans, what happened last week. Tell her once and she keeps it.",
    you: "What did I promise Sam last week?", her: "To send him the trip photos. Want a nudge tonight?" },
  { icon: 20, title: "Talks like a friend",
    text: "She hears when you sound tired or stressed, and changes how she talks to you.",
    you: "Ugh, long day.", her: "You sound wiped. Want tomorrow in one line, or just to talk?" },
  { icon: 180, title: "Gets things done",
    text: "Alarms, reminders and todos. Just say it, the way you’d say it to a person.",
    you: "Wake me at 7 and add groceries to my list.", her: "Alarm set for 7 AM. Groceries added." },
  { icon: 97, title: "Knows what’s happening",
    text: "News, tech and AI updates, new research papers and placement news, in a quick brief.",
    you: "Anything new on placements?", her: "Two companies opened applications today. Want the deadlines?" },
  { icon: 213, title: "Teaches anything overnight",
    text: "Hand her any book or subject and get a one-night crash course that actually sticks.",
    you: "Teach me statistics before tomorrow’s exam.", her: "Five short rounds. Round one: averages, in two minutes." },
  { icon: 296, title: "Learns how you like it",
    text: "Correct her once and it sticks. From then on, she talks your way.",
    you: "No long lists in the morning, please.", her: "Noted. Mornings stay short from now on." },
];

export function Features() {
  return (
    <section className="features" id="features" aria-labelledby="features-title">
      <div className="container">
        <div className="sec-head">
          <p className="label" data-reveal>WHAT STITI DOES</p>
          <H2 id="features-title" thin="Talk to her" bold="like a person." />
          <p className="lead sec-head__side" data-reveal>
            No commands to learn. Say it the way you’d say it to a friend. She remembers, follows up and gets it done.
          </p>
        </div>
        <ul className="feats">
          {FEATURES.map((f) => (
            <li className="feat" key={f.title} data-reveal>
              <span className="feat__icon" style={icon(f.icon)} aria-hidden="true" />
              <h3 className="feat__title">{f.title}</h3>
              <p className="feat__text">{f.text}</p>
              <Say you={f.you} her={f.her} />
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}

// ------------------------------------------------------------------ a day with Stiti (time order carries meaning)
const DAY: { time: string; iso: string; title: string; lines: { who: "you" | "her"; t: string }[] }[] = [
  { time: "7:30 AM", iso: "07:30", title: "Morning brief", lines: [
    { who: "you", t: "Morning, Stiti." },
    { who: "her", t: "Morning! Clear skies till 5, three things on your list, and it’s Maya’s birthday tomorrow." },
  ] },
  { time: "4:00 PM", iso: "16:00", title: "Right on time", lines: [
    { who: "her", t: "It’s 4. Time to start your resume." },
    { who: "you", t: "Okay, starting now." },
    { who: "her", t: "I’ll check in at 5." },
  ] },
  { time: "8:30 PM", iso: "20:30", title: "What’s new in AI", lines: [
    { who: "you", t: "Anything new in AI today?" },
    { who: "her", t: "Two new open models and a paper on memory for assistants. Two-minute version?" },
  ] },
  { time: "1:10 AM", iso: "01:10", title: "Still up?", lines: [
    { who: "you", t: "One more chapter and I’m done." },
    { who: "her", t: "You sound tired, and it’s past 1. Sleep. I’ll recap the chapter at breakfast." },
  ] },
];

export function Day() {
  return (
    <section className="day" id="day" aria-labelledby="day-title">
      <div className="container">
        <div className="sec-head">
          <p className="label" data-reveal>A DAY WITH STITI</p>
          <H2 id="day-title" thin="From morning" bold="to midnight." />
          <p className="lead sec-head__side" data-reveal>
            She’s there all day. Sometimes you call her, sometimes she speaks up at just the right moment.
          </p>
        </div>
        <ol className="day__list">
          {DAY.map((m) => (
            <li className="moment" key={m.iso} data-reveal>
              <span className="moment__dot" aria-hidden="true" />
              <time className="label moment__time" dateTime={m.iso}>{m.time}</time>
              <h3 className="moment__title">{m.title}</h3>
              <div className="moment__lines">
                {m.lines.map((l, i) => (
                  <p key={i} className={l.who === "you" ? "say__you" : "say__her"}>
                    <span className="sr-only">{l.who === "you" ? "You: " : "Stiti: "}</span>{l.t}
                  </p>
                ))}
              </div>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}

// ------------------------------------------------------------------ privacy
const PROMISES: { h: string; p: string }[] = [
  { h: "Kept only on your Mac", p: "Everything she remembers lives on your Mac. Not in the cloud, not on anyone’s server." },
  { h: "No account, no sign-up", p: "No email, no password, no profile. Open her and start talking." },
  { h: "Free", p: "No subscription, no trial, no ads. Stiti is free and open source." },
  { h: "See and edit everything", p: "What she knows about you is plain text you can read. Change a line and she follows it." },
];
const KNOWS: { t: string; tag: string }[] = [
  { t: "Likes short answers in the morning", tag: "Learned" },
  { t: "Sam — best friend, loves trip photos", tag: "Person" },
  { t: "Resume due Friday", tag: "Plan" },
  { t: "Don’t call me “sir”", tag: "Rule" },
];

export function Privacy() {
  return (
    <section className="privacy" id="privacy" aria-labelledby="privacy-title">
      <div className="container">
        <div className="sec-head">
          <p className="label" data-reveal>PRIVACY</p>
          <H2 id="privacy-title" thin="Your life stays" bold="on your Mac." />
          <p className="lead sec-head__side" data-reveal>
            What you tell Stiti is hers to remember and yours to own. It isn’t sent off to a company, and there’s nothing to sign up for.
          </p>
        </div>
        <div className="privacy__grid">
          <ul className="promises">
            {PROMISES.map((p) => (
              <li className="promise" key={p.h} data-reveal>
                <h3>{p.h}</h3>
                <p>{p.p}</p>
              </li>
            ))}
          </ul>
          <figure className="knows" data-reveal aria-labelledby="knows-cap">
            <div className="knows__bar" aria-hidden="true"><i /><i /><i /></div>
            <figcaption className="label knows__cap" id="knows-cap">What Stiti knows about you <span className="knows__eg">example</span></figcaption>
            <ul className="knows__list">
              {KNOWS.map((k) => (
                <li key={k.t}>
                  <span className="knows__t">{k.t}</span>
                  <span className="knows__tag label">{k.tag}</span>
                  <span className="knows__edit" aria-hidden="true">Edit</span>
                </li>
              ))}
            </ul>
            <p className="knows__foot">Change a line and she follows it. Delete it and it’s gone.</p>
          </figure>
        </div>
      </div>
    </section>
  );
}

// ------------------------------------------------------------------ FAQ (native <details>: keyboard + screen-reader friendly)
const FAQ: { q: string; a: ReactNode }[] = [
  { q: "Is it free?", a: "Yes. Stiti is free and open source. No subscription, no trial, no ads, and no account." },
  { q: "Does it need the internet?", a: "Not for the everyday things: alarms, reminders, todos and remembering what you told her keep working offline. She goes online for longer, thoughtful answers and for news and new papers." },
  { q: "What languages does she speak?", a: "English, for now. More languages are on the way." },
  { q: "Which Macs does it run on?", a: "Macs with Apple silicon (M1 and newer). She’s built to run comfortably on the base models too." },
  { q: "Is my data shared?", a: "No. Her memory stays on your Mac. When a question needs deeper thinking, only the few lines that answer needs are sent, and nothing is kept about you anywhere else. There’s no account to tie it to." },
  { q: "How do I try it?", a: <>Stiti is on <a href={GITHUB} target="_blank" rel="noopener">GitHub<span className="sr-only"> (opens in a new tab)</span></a> now, with everything you need to set her up on your Mac. A live demo is coming soon.</> },
];

export function Faq() {
  return (
    <section className="faq" id="faq" aria-labelledby="faq-title">
      <div className="container faq__grid">
        <div className="faq__head">
          <p className="label" data-reveal>FAQ</p>
          <H2 id="faq-title" thin="Good" bold="questions." />
        </div>
        <div className="faq__list">
          {FAQ.map((f) => (
            <details className="qa" key={f.q} data-reveal>
              <summary>
                <h3 className="qa__q">{f.q}</h3>
                <span className="qa__icon" aria-hidden="true" />
              </summary>
              <p className="qa__a">{f.a}</p>
            </details>
          ))}
        </div>
      </div>
    </section>
  );
}

// ------------------------------------------------------------------ footer
export function Footer() {
  return (
    <footer className="foot">
      <div className="container foot__cta">
        <p className="label" data-reveal>READY WHEN YOU ARE</p>
        <p className="foot__title"><span className="thin"><Split t="Say hi to" /></span> <b><Split t="Stiti." /></b></p>
        <GitHubButton big />
        <p className="label foot__soon">A live demo is coming soon.</p>
      </div>
      <div className="container foot__bar">
        <span className="foot__mark" aria-hidden="true">S</span>
        <p className="foot__quote"><span className="thin">“{QUOTE.lead}</span> <b>{QUOTE.punch}”</b></p>
        <a className="foot__gh" href={GITHUB} target="_blank" rel="noopener">GitHub<span className="sr-only"> (opens in a new tab)</span></a>
        <span className="foot__copy">© 2026 Stiti</span>
      </div>
    </footer>
  );
}
