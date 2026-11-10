"use client";
// The hero's product shot: Stiti on a Mac desktop, drawn in pure CSS/SVG (no screenshots). A floating pill at the
// top centre shows her state (idle → listening → thinking → speaking) and a short conversation plays as caption
// bubbles, one at a time (fade + rise only), then rests and restarts. Reduced motion: the whole conversation, still.
// All content is generic example dialogue.
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { prefersReducedMotion } from "@/lib/stiti";

type State = "idle" | "listening" | "thinking" | "speaking";
type Line = { who: "you" | "stiti"; text: string; tag?: { icon: "bell" | "paper"; text: string } };

const LINES: Line[] = [
  { who: "you", text: "Hey Stiti" },
  { who: "stiti", text: "Hey! How are you?" },
  { who: "you", text: "Today I’m on my resume till 4 — remind me at 4 to start it." },
  { who: "stiti", text: "Got it, reminder at 4 PM. Anything else?", tag: { icon: "bell", text: "Today · 4:00 PM · Start resume" } },
  { who: "you", text: "Is any new AI research paper out today?" },
  { who: "stiti", text: "Yes — three worth a look. Want the short version?", tag: { icon: "paper", text: "3 new papers · AI" } },
];

// [pill state, how many lines are visible from this step on (-1 = unchanged), how long the step lasts in ms]
const STEPS: [State, number, number][] = [
  ["idle", 0, 1300],
  ["listening", 1, 900],      // "Hey Stiti" wakes her
  ["speaking", 2, 2100],
  ["listening", -1, 1700],
  ["listening", 3, 600],
  ["thinking", -1, 900],
  ["speaking", 4, 2500],
  ["listening", -1, 1700],
  ["listening", 5, 600],
  ["thinking", -1, 1400],
  ["speaking", 6, 2800],
  ["idle", -1, 3800],         // rest on the finished conversation, then start again
];
const LABEL: Record<State, string> = { idle: "Say “Hey Stiti”", listening: "Listening…", thinking: "Thinking…", speaking: "Speaking" };

function Bell() {
  return (
    <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M8 2.2a3.6 3.6 0 0 0-3.6 3.6v2.6L3.2 10.6h9.6l-1.2-2.2V5.8A3.6 3.6 0 0 0 8 2.2ZM6.4 12.4a1.6 1.6 0 0 0 3.2 0" fill="none" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round" /></svg>
  );
}
function Paper() {
  return (
    <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M4 1.8h5.4L12.2 4.6v9.6H4ZM9.2 1.8v3h3M6 8h4.2M6 10.6h4.2" fill="none" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round" /></svg>
  );
}

/** `once`: play the conversation one time when it scrolls into view, then stay on the finished exchange
 *  (below the hero the page is still — owner rule). */
export default function MacShot({ once = false }: { once?: boolean }) {
  const [state, setState] = useState<State>("idle");
  const [shown, setShown] = useState(0);
  const [resetting, setResetting] = useState(false);
  const [still, setStill] = useState(false);
  const rootRef = useRef<HTMLElement>(null);
  const vpRef = useRef<HTMLDivElement>(null);
  const trackRef = useRef<HTMLOListElement>(null);

  // the conversation loop (paused while the shot is off screen or the tab is hidden)
  useEffect(() => {
    if (prefersReducedMotion()) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- one-time switch to the static version
      setStill(true); setShown(LINES.length); setState("speaking");
      return;
    }
    let alive = true, onScreen = true, timer = 0;
    const io = new IntersectionObserver(([e]) => { onScreen = e.isIntersecting; }, { threshold: .15 });
    io.observe(rootRef.current!);
    const wait = (ms: number) => new Promise<void>((res) => {
      let left = ms, lastT = performance.now();
      const tick = () => {
        if (!alive) return;
        const now = performance.now();
        if (onScreen && !document.hidden) left -= now - lastT;
        lastT = now;
        if (left <= 0) res(); else timer = window.setTimeout(tick, Math.min(left, 200));
      };
      timer = window.setTimeout(tick, Math.min(left, 200));
    });
    (async () => {
      while (alive) {
        for (const [st, n, ms] of STEPS) {
          if (!alive) return;
          setState(st);
          if (n >= 0) setShown(n);
          await wait(ms);
        }
        if (once) return;                   // stays on the last exchange
        setResetting(true);                 // the finished conversation fades out together
        await wait(700);
        if (!alive) return;
        setShown(0); setResetting(false);
      }
    })();
    return () => { alive = false; clearTimeout(timer); io.disconnect(); };
  }, [once]);

  // keep the newest visible bubble at the bottom of the caption area; older ones slide up under the top fade
  useLayoutEffect(() => {
    const vp = vpRef.current, track = trackRef.current;
    if (!vp || !track) return;
    const place = () => {
      const items = track.children;
      const last = items[Math.max(0, shown - 1)] as HTMLElement | undefined;
      const bottom = shown && last ? last.offsetTop + last.offsetHeight : 0;
      track.style.transform = `translateY(${Math.min(0, vp.clientHeight - bottom)}px)`;
    };
    place();
    const ro = new ResizeObserver(place);
    ro.observe(vp);
    return () => ro.disconnect();
  }, [shown]);

  return (
    <figure className={`shot${still ? " is-still" : ""}`} ref={rootRef}
            aria-label="Stiti on a Mac: a small pill at the top of the screen shows when she is listening, thinking or speaking, and the conversation appears as captions.">
      <div className="shot__lid">
        <div className="shot__screen">
          <div className="shot__wall" aria-hidden="true" />
          <div className="shot__menubar" aria-hidden="true">
            <span className="shot__menu"><b>Stiti</b><span>File</span><span>Edit</span><span>View</span><span>Window</span></span>
            <span className="shot__status">
              <svg viewBox="0 0 18 12"><path d="M1.5 4.2a10.6 10.6 0 0 1 15 0M4.1 6.9a7 7 0 0 1 9.8 0M6.7 9.4a3.2 3.2 0 0 1 4.6 0" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" /></svg>
              <svg viewBox="0 0 26 12"><rect x=".75" y=".75" width="21.5" height="10.5" rx="3" fill="none" stroke="currentColor" strokeWidth="1.2" /><rect x="2.6" y="2.6" width="15" height="6.8" rx="1.6" fill="currentColor" /><path d="M24 4.2v3.6" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" /></svg>
              <span>Wed 9:41</span>
            </span>
          </div>

          {/* what you're working on, behind the conversation */}
          <div className="shot__doc" aria-hidden="true">
            <div className="shot__doc-bar"><i /><i /><i /><span>Resume — draft</span></div>
            <div className="shot__doc-body">
              <span className="w70 h" /><span className="w40" /><span className="w90" /><span className="w80" /><span className="w60" />
              <span className="w50 h" /><span className="w90" /><span className="w75" /><span className="w85" />
            </div>
          </div>

          <div className={`pill pill--${state}`} aria-hidden="true">
            <span className="pill__orb" />
            <span className="pill__wave"><i /><i /><i /><i /><i /></span>
            <span className="pill__labels">
              {(Object.keys(LABEL) as State[]).map((k) => (
                <span key={k} className={k === state ? "is-on" : undefined}>{LABEL[k]}</span>
              ))}
            </span>
          </div>

          <div className="shot__captions" ref={vpRef}>
            <ol className={`shot__track${resetting ? " is-resetting" : ""}`} ref={trackRef} aria-label="Example conversation">
              {LINES.map((l, i) => (
                <li key={i} className={`bub bub--${l.who}${i < shown ? " is-in" : ""}`}>
                  <span className="sr-only">{l.who === "you" ? "You: " : "Stiti: "}</span>
                  <span className="bub__text">{l.text}</span>
                  {l.tag && (
                    <span className="bub__tag">{l.tag.icon === "bell" ? <Bell /> : <Paper />}{l.tag.text}</span>
                  )}
                </li>
              ))}
            </ol>
          </div>

          <div className="shot__dock" aria-hidden="true">
            <i /><i /><i /><i /><i /><span className="shot__dock-s">S</span>
          </div>
        </div>
      </div>
      <div className="shot__base" aria-hidden="true" />
    </figure>
  );
}
