"use client";
// One line of the conversation. Yours: a navy bubble on the right. Stiti's: plain text on the left
// (no avatar mark — layout and type alone tell her apart), with an action chip, a meta line and,
// on replies where the brain handed the LLM context, her "memory receipts".
import { Fragment, type ReactNode } from "react";
import { fmtTime, prefersReducedMotion, type Reply } from "@/lib/stiti";
import Receipts from "./Receipts";

export type Msg = {
  id: number;
  who: "you" | "stiti";
  text: string;
  at: Date;
  animate: boolean;                   // fresh this session (history from "hello" doesn't animate)
  reply?: Partial<Reply>;             // only Stiti's live replies
  streaming?: boolean;                // deltas still arriving
  wordFade?: boolean;                 // word-by-word reveal (only if the reply wasn't streamed)
};

// internal ids like "(task #3)" / "(#1)" / "(lesson L2)" are for the terminal, not for people
const clean = (t: string) => t.replace(/\s*\((?:task |lesson )?#?L?\d+\)/g, "");

/** While streaming, hide a "**" whose closing pair hasn't arrived yet. */
const draft = (t: string) => ((t.match(/\*\*/g) || []).length % 2 ? t.replace(/\*\*(?![\s\S]*\*\*)/, "") : t);

/** **bold** + newlines → React nodes; optional word-by-word fade, total reveal capped at ~0.7 s. */
function rich(text: string, fade: boolean): ReactNode[] {
  const segs = clean(text).split(/(\*\*.+?\*\*)/g).filter(Boolean)
    .map((s) => (s.startsWith("**") && s.endsWith("**") && s.length > 4 ? { b: true, s: s.slice(2, -2) } : { b: false, s }));
  const words = fade ? segs.reduce((n, g) => n + g.s.split(/\s+/).filter(Boolean).length, 0) : 0;
  const step = Math.min(28, 700 / Math.max(1, words));
  let i = 0, key = 0;
  const out: ReactNode[] = [];
  for (const g of segs) {
    const parts: ReactNode[] = [];
    for (const p of g.s.split(/(\n|\s+)/)) {
      if (!p) continue;
      if (p === "\n") parts.push(<br key={key++} />);
      else if (!p.trim()) parts.push(p.includes("\n") ? <br key={key++} /> : " ");
      else if (fade) parts.push(<span key={key++} className="w" style={{ animationDelay: `${Math.round(i++ * step)}ms` }}>{p}</span>);
      else parts.push(p);
    }
    out.push(g.b ? <b key={key++}>{parts}</b> : <Fragment key={key++}>{parts}</Fragment>);
  }
  return out;
}

/** What did she just do? → chip {icon, label} for fast-path actions. Icons: /icons/<n>.png pictograms. */
function chipFor(r: Partial<Reply>): { icon: number; label: string } | null {
  if (r.route !== "fast_path") return null;
  const t = (r.text || "").toLowerCase();
  if (/alarm/.test(t)) return { icon: 180, label: "Alarm" };
  if (/remind/.test(t)) return { icon: 180, label: "Reminder" };
  if (r.domain === "todo" || /todo|task/.test(t)) return { icon: 104, label: "Todos" };
  if (/calendar|meeting|event/.test(t)) return { icon: 187, label: "Calendar" };
  if (/play|music|song|spotify/.test(t)) return { icon: 146, label: "Music" };
  if (/mail|inbox/.test(t)) return { icon: 97, label: "Mail" };
  if (/whiteboard|lesson/.test(t)) return { icon: 213, label: "Tutor" };
  if (r.domain === "memory") return { icon: 217, label: "Memory" };
  if (r.domain === "time") return { icon: 187, label: "Time" };
  return { icon: 139, label: "Done on your Mac" };
}

function metaFor(r: Partial<Reply>, when: Date) {
  const bits = [fmtTime(when)];
  if (r.route === "fast_path") bits.push(`on your Mac · ${r.ms} ms`);
  else if (r.route === "llm") bits.push(`${r.provider ? "via " + r.provider : "cloud"} · ${r.ms} ms`);
  else if (r.route === "degraded") bits.push("from memory · thinking brain offline");
  return bits.join(" · ");
}

export default function Message({ m }: { m: Msg }) {
  const still = !m.animate ? { animation: "none" } : undefined;
  if (m.who === "you") {
    return (
      <div className="msg msg--you" style={still}>
        <div className="msg__body">{m.text}</div>
      </div>
    );
  }
  const r = m.reply ?? {};
  const chip = m.streaming ? null : chipFor(r);
  const fade = !!m.wordFade && !prefersReducedMotion();
  return (
    <div className={`msg msg--stiti${m.streaming ? " is-streaming" : ""}`} style={still}>
      <div className="msg__body">
        {chip && (
          <div className="chip">
            {/* eslint-disable-next-line @next/next/no-img-element -- static export, tiny local pictogram */}
            <img src={`/icons/${chip.icon}.png`} alt="" width={20} height={20} />{chip.label}
          </div>
        )}
        <div className="msg__text">{rich(m.streaming ? draft(m.text) : m.text, fade && !m.streaming)}</div>
        {!m.streaming && m.reply && <div className="msg__meta">{metaFor(r, m.at)}</div>}
        {!m.streaming && <Receipts used={r.used} />}
      </div>
    </div>
  );
}
