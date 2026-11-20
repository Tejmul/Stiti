"use client";
// One saved lesson note, read in a side panel (a native modal <dialog>: focus stays inside, Escape closes).
// The markdown is rendered by a tiny parser into React elements — never as raw HTML.
import { Fragment, useEffect, useRef, useState, type ReactNode } from "react";
import type { LessonNote } from "@/lib/stiti";
import { api } from "@/lib/stiti";
import { Icon, fmtWhen } from "./bits";

type Loaded = { name: string; md?: string; err?: string };

export default function NoteView({ note, onClose }: { note: LessonNote | null; onClose: () => void }) {
  const dlg = useRef<HTMLDialogElement>(null);
  const [got, setGot] = useState<Loaded | null>(null);

  useEffect(() => {
    const d = dlg.current;
    if (!d) return;
    if (note && !d.open) d.showModal();
    if (!note && d.open) d.close();
  }, [note]);

  useEffect(() => {
    if (!note) return;
    let live = true;
    api<{ markdown: string }>(`/api/lessons/notes?name=${encodeURIComponent(note.name)}`).then(
      (r) => { if (live) setGot({ name: note.name, md: r.markdown }); },
      (e) => { if (live) setGot({ name: note.name, err: e instanceof Error ? e.message : String(e) }); },
    );
    return () => { live = false; };
  }, [note]);

  const cur = note && got?.name === note.name ? got : null;

  return (
    <dialog ref={dlg} className="note" aria-labelledby="note-h" onClose={onClose}
      onClick={(e) => { if (e.target === dlg.current) dlg.current?.close(); }}>
      {note && (
        <div className="note__in">
          <header className="note__head">
            <div>
              <p className="label">Lesson notes · {fmtWhen(note.modified)}</p>
              <h2 id="note-h">{note.title}</h2>
            </div>
            <button type="button" className="note__x" aria-label="Close notes" onClick={() => dlg.current?.close()}>
              <Icon name="close" />
            </button>
          </header>
          <div className="note__body">
            {!cur && (
              <div aria-busy="true">
                <p className="sr-only" role="status">Opening the note…</p>
                {Array.from({ length: 7 }, (_, i) => <span key={i} className="sk sk--row" />)}
              </div>
            )}
            {cur?.err && <p className="msg is-err" role="alert"><Icon name="alert" />Couldn&apos;t open this note: {cur.err}</p>}
            {cur?.md != null && <Markdown text={cur.md} />}
          </div>
          <footer className="note__foot">
            <span className="label">Saved on this Mac</span>
            <code>~/.stiti/tutor/notes/{note.name}</code>
          </footer>
        </div>
      )}
    </dialog>
  );
}

// ------------------------------------------------------------------ markdown (the subset the tutor writes)
function inline(s: string): ReactNode[] {
  const parts = s.split(/(\*\*[^*]+\*\*|`[^`]+`|(?<![\w])_[^_]+_(?![\w]))/g);
  return parts.map((p, i) => {
    if (i % 2 === 0) return <Fragment key={i}>{p}</Fragment>;
    if (p.startsWith("**")) return <strong key={i}>{p.slice(2, -2)}</strong>;
    if (p.startsWith("`")) return <code key={i}>{p.slice(1, -1)}</code>;
    return <em key={i}>{p.slice(1, -1)}</em>;
  });
}

type Item = { depth: number; text: string; bullet: boolean };

function List({ items }: { items: Item[] }) {
  const out: ReactNode[] = [];
  for (let i = 0; i < items.length;) {
    const it = items[i];
    let j = i + 1;
    while (j < items.length && items[j].depth > it.depth) j++;
    const kids = items.slice(i + 1, j);
    out.push(
      <li key={i} className={it.bullet ? undefined : "md__cont"}>
        {inline(it.text)}
        {kids.length > 0 && <List items={kids} />}
      </li>,
    );
    i = j;
  }
  return <ul>{out}</ul>;
}

function Markdown({ text }: { text: string }) {
  const blocks: ReactNode[] = [];
  let list: Item[] = [];
  let para: string[] = [];
  const flush = () => {
    if (list.length) { blocks.push(<List key={`l${blocks.length}`} items={list} />); list = []; }
    if (para.length) { blocks.push(<p key={`p${blocks.length}`}>{inline(para.join(" "))}</p>); para = []; }
  };
  for (const raw of text.split("\n")) {
    const line = raw.replace(/\s+$/, "");
    const indent = line.length - line.trimStart().length;
    const t = line.trim();
    if (!t) { flush(); continue; }
    const h = /^(#{1,4})\s+(.*)$/.exec(t);
    if (h && indent === 0) {
      flush();
      if (h[1].length === 1) continue;                     // the "# Title — notes" line is the panel's own heading
      const mark = /\s+(✓|~)$/.exec(h[2]);
      const title = mark ? h[2].slice(0, mark.index) : h[2];
      const Tag = h[1].length === 2 ? "h3" : "h4";
      blocks.push(
        <Tag key={`h${blocks.length}`}>
          {inline(title)}
          {mark && <span className={`md__tag${mark[1] === "~" ? " md__tag--rev" : ""}`}>{mark[1] === "✓" ? "Solid" : "To revise"}</span>}
        </Tag>,
      );
      continue;
    }
    if (t.startsWith(">")) { flush(); blocks.push(<blockquote key={`q${blocks.length}`}>{inline(t.replace(/^>\s?/, ""))}</blockquote>); continue; }
    const b = /^[-*]\s+(.*)$/.exec(t);
    if (b || (indent >= 2 && list.length)) {
      if (para.length) { blocks.push(<p key={`p${blocks.length}`}>{inline(para.join(" "))}</p>); para = []; }
      list.push({ depth: Math.floor(indent / 2), text: b ? b[1] : t, bullet: !!b });
      continue;
    }
    if (list.length) flush();
    para.push(t);
  }
  flush();
  return <div className="md">{blocks}</div>;
}
