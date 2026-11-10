"use client";
// "Start talking to Stiti" → a small panel that says how: Stiti lives on your Mac, so you get her from GitHub,
// set her up, and start building your own buddy. Native <dialog>: Esc closes, focus is trapped, the page stays put.
import { useRef } from "react";
import { GITHUB } from "@/lib/site";

function Arrow() {
  return (
    <svg className="btn__arrow" viewBox="0 0 26 12" aria-hidden="true">
      <path d="M0 6h24M19 1l5 5-5 5" fill="none" stroke="currentColor" strokeWidth="1.4" />
    </svg>
  );
}

const STEPS = [
  { t: "Get Stiti from GitHub", d: "Free and open source. No account, no app store." },
  { t: "Set her up on your Mac", d: "A few minutes. Everything she learns stays on your Mac." },
  { t: "Say “Hey Stiti”", d: "Talk like you would to a friend. She learns you from day one." },
];

export default function StartButton({ big }: { big?: boolean }) {
  const dlg = useRef<HTMLDialogElement>(null);
  const close = () => dlg.current?.close();
  return (
    <>
      <button type="button" className={`btn btn--primary${big ? " btn--big" : ""}`} aria-haspopup="dialog"
              onClick={() => dlg.current?.showModal()}>
        <span>Start talking to Stiti</span>
        <Arrow />
      </button>
      <dialog ref={dlg} className="start-dlg" aria-labelledby="start-dlg-title"
              onClick={(e) => { if (e.target === dlg.current) close(); }}>
        <div className="start-dlg__card">
          <button type="button" className="start-dlg__x" onClick={close} aria-label="Close">
            <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M3 3l10 10M13 3L3 13" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" /></svg>
          </button>
          <p className="label">Stiti lives on your Mac</p>
          <h2 id="start-dlg-title" className="start-dlg__title"><span className="thin">Start talking</span> <b>in a few minutes.</b></h2>
          <p className="start-dlg__lede">
            Stiti isn&apos;t a website you chat with. She&apos;s your own buddy that runs on your Mac. Get her from GitHub,
            set her up, and start building her into the friend you want.
          </p>
          <ol className="start-dlg__steps">
            {STEPS.map((s) => (
              <li key={s.t}><b>{s.t}</b><span>{s.d}</span></li>
            ))}
          </ol>
          <div className="start-dlg__actions">
            <a className="btn btn--primary" href={GITHUB} target="_blank" rel="noopener" onClick={close}>
              <span>Get Stiti on GitHub</span><span className="sr-only"> (opens in a new tab)</span><Arrow />
            </a>
            <button type="button" className="start-dlg__later" onClick={close}>Not now</button>
          </div>
          <p className="label start-dlg__foot">Free · Open source · macOS · Live demo coming soon</p>
        </div>
      </dialog>
    </>
  );
}
