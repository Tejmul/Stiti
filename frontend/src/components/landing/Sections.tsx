// Landing markup (ported from the original static/index.html). Pure markup — all motion is wired in Landing.tsx.
import { Fragment, type CSSProperties } from "react";
import Split from "./Split";

const icon = (n: number) => ({ "--icon": `url(/icons/${n}.png)` }) as CSSProperties;

function Arrow() {
  return (
    <svg className="btn__arrow" viewBox="0 0 26 12" aria-hidden="true">
      <path d="M0 6h24M19 1l5 5-5 5" fill="none" stroke="currentColor" strokeWidth="1.4" />
    </svg>
  );
}

export const GITHUB = "https://github.com/Tejmul/Stiti";

// The marketing site's one action until the app ships (a live demo link comes later).
function GitHubButton({ big, reveal }: { big?: boolean; reveal?: boolean }) {
  return (
    <a className={`btn btn--primary${big ? " btn--big" : ""}`} href={GITHUB} target="_blank" rel="noopener"
       data-reveal={reveal || undefined}>
      <span>View on GitHub</span>
      <Arrow />
    </a>
  );
}

const STRIP = "NO CLOUD MEMORY. NO MONTHLY BILL.";
const TICKER = ["Recall in ~10 ms", "First word in under a second", "₹0 a month", "Speaks Hinglish", "1.25 GB of RAM, total"];
const ROWS = [
  { icon: 217, title: "Remembers", text: "Every conversation is kept on your Mac and found again in milliseconds. Ask what happened last Tuesday, or what you promised your sister." },
  { icon: 20, title: "Listens", text: "Talk over her, say “ruko”, switch to Hinglish mid-sentence. She hears when you sound tired or stressed and changes how she answers." },
  { icon: 180, title: "Gets things done", text: "Todos, alarms, reminders, your calendar and mail. The everyday stuff happens instantly, without waiting on the cloud." },
  { icon: 296, title: "Learns you", text: "Correct her once and it becomes a rule. “Don't talk to me like that” is remembered, not forgotten when the chat ends." },
];
const STATS = [
  { num: "~10 ms", cap: "to find a memory" },
  { num: "₹0", cap: "to run, every month" },
  { num: "100%", cap: "of your memory stays on your Mac" },
];
const POINTS = [
  { h: "Swap the model, keep the person", p: "Any free LLM can be her voice; her identity and memory don't change." },
  { h: "Private stays private", p: "Anything marked sensitive is never sent to the cloud, not even for a reply." },
  { h: "Works when the internet doesn't", p: "Todos, alarms and recall keep working offline." },
  { h: "Memory you can read", p: "USER.md and LESSONS.md are plain text. Edit a line and she follows it." },
];
const SAYINGS = [
  { q: "“Kal subah 7 baje alarm laga do.”", icon: 180, tag: "Alarm" },
  { q: "“What did I tell you about the interview last week?”", icon: 217, tag: "Memory" },
  { q: "“Add buy milk to my todos.”", icon: 104, tag: "Todo" },
  { q: "“Play something calm.”", icon: 146, tag: "Music" },
  { q: "“Any new mail from college?”", icon: 97, tag: "Mail" },
  { q: "“Teach me compilers on the whiteboard.”", icon: 213, tag: "Tutor" },
];

function TickerGroup({ dup }: { dup?: boolean }) {
  return (
    <div className="ticker__group" aria-hidden={dup || undefined}>
      {TICKER.map((t) => (
        <Fragment key={t}>
          <span className="ticker__item">{t}</span>
          <span className="ticker__sep" aria-hidden="true">→</span>
        </Fragment>
      ))}
    </div>
  );
}

function SayingsSet({ dup }: { dup?: boolean }) {
  return (
    <ul className={`sayings__set${dup ? " sayings__set--dup" : ""}`} aria-label={dup ? undefined : "Things you can say"} aria-hidden={dup || undefined}>
      {SAYINGS.map((s) => (
        <li className="card" key={s.tag}>
          <p className="card__q">{s.q}</p>
          <p className="card__meta">
            <span className="card__icon" style={icon(s.icon)} aria-hidden="true" />
            <span className="label">{s.tag}</span>
          </p>
        </li>
      ))}
    </ul>
  );
}

export function Hero() {
  return (
    <section className="hero" id="hero">
      <div className="container hero__grid">
        <p className="label hero__label"><span className="hero__label-text">YOUR LOCAL AI BUDDY / RUNS ON → YOUR MAC</span></p>
        <h1 className="hero__title">
          {/* remembers everything · talks like a friend · lives on your Mac (and your data never leaves it) */}
          <span className="line"><Split t="Never " /><b><Split t="forgets." /></b></span>
          <span className="line"><Split t="Always " /><b><Split t="listens." /></b></span>
          <span className="line"><Split t="Never " /><b><Split t="leaves." /></b></span>
        </h1>
        <div className="hero__ctas hero__ctas--under"><GitHubButton /></div>
        <div className="hero__foot">
          <div className="hero__intro">
            <div className="hero__strip label">
              <div className="hero__strip-track">
                <span>{STRIP}</span>
                <span className="hero__strip-dup" aria-hidden="true">{STRIP}</span>
                <span className="hero__strip-dup" aria-hidden="true">{STRIP}</span>
                <span className="hero__strip-dup" aria-hidden="true">{STRIP}</span>
              </div>
            </div>
            <p className="hero__desc">Stiti is a voice buddy that keeps her memory on your Mac — your people, your plans, and how you like to be talked to. She sets alarms, keeps your todos, notices when you sound tired, and never forgets a conversation.</p>
          </div>
          <div className="hero__act">
            <ul className="hero__stack label" aria-label="What she runs on">
              <li>VOICE: WHISPER</li><li className="sep" aria-hidden="true">⋅</li>
              <li>KOKORO</li><li className="sep" aria-hidden="true">⋅</li>
              <li>MEMORY: POSTGRES</li><li className="sep" aria-hidden="true">⋅</li>
              <li>THINKING: ANY FREE LLM</li>
            </ul>

          </div>
        </div>
      </div>
      <div className="hero__cue label" aria-hidden="true">SCROLL</div>
    </section>
  );
}

export function Body() {
  return (
    <>
      <section className="ticker" aria-label="Quick facts">
        <div className="ticker__track">
          <TickerGroup />
          <TickerGroup dup />
        </div>
      </section>

      <section className="quote" id="memory" aria-label="Memory">
        <div className="container quote__inner">
          <span className="quote__glyph" aria-hidden="true">“</span>
          <blockquote className="quote__text">
            <p><Split mask={false} t="Your girlfriend may not understand you, " /><b><Split mask={false} t="but Stiti will." /></b></p>
          </blockquote>
          <p className="label quote__cap">STITI — NOTHING YOU SAY GETS LOST</p>
        </div>
      </section>

      <section className="abilities" id="abilities">
        <div className="container">
          <div className="sec-head">
            <p className="label" data-reveal>WHAT SHE DOES</p>
            <h2 className="h2"><span className="thin"><Split t="Four things." /></span> <b><Split t="One friend." /></b></h2>
            <div className="sec-head__side" data-reveal>
              <p className="lead">Simple things happen instantly on your Mac. Deep thinking borrows a free cloud model — but who she is, and what she remembers, never leaves home.</p>
              <ul className="tags" aria-label="Areas">
                <li>Voice</li><li>Memory</li><li>Todos &amp; alarms</li><li>Whiteboard tutor</li>
              </ul>
            </div>
          </div>
          <ul className="rows">
            {ROWS.map((r) => (
              <li className="row" key={r.title}>
                <span className="row__line" aria-hidden="true" />
                <span className="row__icon" style={icon(r.icon)} aria-hidden="true" />
                <h3 className="row__title">{r.title}</h3>
                <p className="row__text">{r.text}</p>
              </li>
            ))}
          </ul>
        </div>
      </section>

      <section className="privacy" id="privacy">
        <div className="container">
          <div className="sec-head">
            <p className="label" data-reveal>WHY IT&apos;S DIFFERENT</p>
            <h2 className="h2"><span className="thin"><Split t="Your memory" /></span> <b><Split t="lives at home." /></b></h2>
            <div className="sec-head__side" data-reveal>
              <p className="lead">Stiti&apos;s brain is a database on your Mac, plus three plain files you can open and edit: who she is, who you are, and what she has learned. Swap the AI model tomorrow and she is still the same Stiti.</p>
            </div>
          </div>
          <div className="stats">
            {STATS.map((s) => (
              <div className="stat" key={s.cap}>
                <p className="stat__num">{s.num}</p>
                <p className="label stat__cap">{s.cap}</p>
              </div>
            ))}
          </div>
          <ul className="points">
            {POINTS.map((p) => (
              <li className="point" key={p.h}>
                <h3>{p.h}</h3>
                <p>{p.p}</p>
              </li>
            ))}
          </ul>
          <div className="privacy__cta" data-reveal>
            <GitHubButton />
          </div>
        </div>
      </section>

      <section className="sayings" id="sayings">
        <div className="container">
          <p className="label" data-reveal>TRY SAYING</p>
          <h2 className="h2"><span className="thin"><Split t="Just talk" /></span> <b><Split t="to her." /></b></h2>
        </div>
        <div className="sayings__viewport">
          <div className="sayings__track">
            <SayingsSet />
            {/* two decorative copies for the seamless loop (hidden with reduced motion) */}
            <SayingsSet dup />
            <SayingsSet dup />
          </div>
        </div>
      </section>

      <section className="cta" id="cta">
        <div className="container cta__inner">
          <p className="label" data-reveal>READY WHEN YOU ARE</p>
          <h2 className="cta__title"><span className="thin"><Split t="Say hi to" /></span> <b><Split t="Stiti." /></b></h2>
          <GitHubButton big reveal />
          <p className="label cta__run" data-reveal>Or run <code>uv run stiti voice</code> and just talk.</p>
        </div>
      </section>
    </>
  );
}

export function Footer() {
  return (
    <footer className="foot">
      <div className="container foot__inner">
        <a className="foot__gh" href={GITHUB} target="_blank" rel="noopener"><span>GitHub</span></a>
        <span>© 2026 Stiti · open source</span>
        <span>Runs on your Mac · ~/.stiti</span>
      </div>
    </footer>
  );
}
