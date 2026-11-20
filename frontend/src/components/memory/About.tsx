"use client";
// About you: tell Stiti a fact (validated, with clear feedback), and every fact grouped by part of life in its own
// card, each with an inline two-step Forget ("Forget" → "Forget it?"). Forgetting retracts; history keeps it.
import gsap from "gsap";
import { useEffect, useRef, useState } from "react";
import type { Fact } from "@/lib/stiti";
import { api, fmtDay, prefersReducedMotion } from "@/lib/stiti";
import { Empty, FACT_GROUPS, Hi, Icon, Section, has, jump } from "./bits";

type Msg = { kind: "" | "ok" | "err"; text: string };

export default function About({ facts, q, onChanged }: { facts: Fact[]; q: string; onChanged: () => Promise<void> }) {
  const [text, setText] = useState("");
  const [msg, setMsg] = useState<Msg>({ kind: "", text: "" });
  const [saving, setSaving] = useState(false);
  const [confirm, setConfirm] = useState<number | null>(null);
  const [busy, setBusy] = useState<number | null>(null);
  const input = useRef<HTMLInputElement>(null);
  const timer = useRef(0);
  const pending = useRef<string | null>(null);

  // After a save, once the new row is on the page, take him to it.
  useEffect(() => {
    if (pending.current && document.querySelector(pending.current)) { jump(pending.current); pending.current = null; }
  }, [facts]);
  useEffect(() => () => window.clearTimeout(timer.current), []);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const t = text.trim();
    if (t.length < 3) {
      setMsg({ kind: "err", text: t ? "That's a bit short. Write at least a few words." : "Write something first — one line about you." });
      input.current?.focus();
      return;
    }
    setSaving(true);
    setMsg({ kind: "", text: "Saving…" });
    try {
      const out = await api<Fact>("/api/fact", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ text: t }) });
      setText("");
      setMsg({ kind: "ok", text: "Saved. Stiti will remember that from her next reply." });
      pending.current = `#fact-${out.id}`;
      await onChanged();
    } catch (err) {
      setMsg({ kind: "err", text: `${err instanceof Error ? err.message : "Couldn't save."} Try again.` });
    } finally {
      setSaving(false);
    }
  }

  async function forget(id: number, e: React.MouseEvent<HTMLButtonElement>) {
    window.clearTimeout(timer.current);
    if (confirm !== id) {                                  // destructive: ask once, inline
      setConfirm(id);
      timer.current = window.setTimeout(() => setConfirm(null), 3500);
      return;
    }
    setConfirm(null);
    setBusy(id);
    const row = e.currentTarget.closest("li");
    try {
      await api(`/api/fact/${id}/forget`, { method: "POST" });
      if (row && !prefersReducedMotion()) await gsap.to(row, { opacity: 0, duration: 0.25, ease: "power2.in" });
      setMsg({ kind: "ok", text: "Forgotten. It stays in history, but Stiti won't use it any more." });
      await onChanged();
    } catch (err) {
      if (row) gsap.set(row, { clearProps: "opacity" });
      setMsg({ kind: "err", text: `Couldn't forget that (${err instanceof Error ? err.message : "error"}). Try again.` });
    } finally {
      setBusy(null);
    }
  }

  const shown = facts.filter((f) => has(q, f.text, f.group));
  const groups = FACT_GROUPS.filter((g) => shown.some((f) => f.group === g));
  if (q && !shown.length) return null;

  return (
    <Section id="about" thin="About" bold="you" n={q ? shown.length : facts.length}
      note={<>Facts Stiti keeps in mind when she talks to you. Also in <code>USER.md</code>.</>}>
      {!q && (
        <form className="teach" onSubmit={submit} autoComplete="off" noValidate>
          <label className="sr-only" htmlFor="teach-input">Tell Stiti something about you</label>
          <div className="teach__row">
            <input ref={input} id="teach-input" type="text" maxLength={400} value={text}
              onChange={(e) => { setText(e.target.value); if (msg.kind === "err") setMsg({ kind: "", text: "" }); }}
              placeholder="Tell Stiti something about you…"
              aria-describedby="teach-msg" aria-invalid={msg.kind === "err" || undefined} />
            <button className="btn-ink" type="submit" disabled={saving}>{saving ? "Saving…" : "Remember this"}</button>
          </div>
          <p className={`teach__msg${msg.kind ? ` is-${msg.kind}` : ""}`} id="teach-msg" role="status">
            {msg.kind === "ok" && <Icon name="check" />}
            {msg.kind === "err" && <Icon name="alert" />}
            {msg.text}
          </p>
        </form>
      )}

      {facts.length === 0 ? (
        <Empty say={["key things", "I'm in my final year of B.Tech", "I play football every Sunday"]}>
          Stiti doesn&apos;t know anything about you yet. Write one line above, or say <q>key things</q> in chat for a five-minute intro.
        </Empty>
      ) : (
        <div className="groups">
          {groups.map((g) => {
            const list = shown.filter((f) => f.group === g);
            return (
              <div className="panel group" key={g}>
                <h3 className="panel__h"><span className="label">{g}</span><span className="panel__n">{list.length}</span></h3>
                <ul className="list">
                  {list.map((f) => (
                    <li className="row" id={`fact-${f.id}`} key={f.id}>
                      <span className="row__text"><Hi text={f.text} q={q} />
                        <span className="row__meta">{f.mine ? "you told her" : "learned in conversation"}{f.since ? ` · ${fmtDay(new Date(f.since))}` : ""}</span>
                      </span>
                      <button className={`row__act${confirm === f.id ? " is-confirm" : ""}`} type="button" disabled={busy === f.id}
                        onClick={(e) => forget(f.id, e)} aria-label={confirm === f.id ? `Confirm: forget “${f.text}”` : `Forget “${f.text}”`}>
                        {busy === f.id ? "Forgetting…" : confirm === f.id ? "Forget it?" : "Forget"}
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            );
          })}
        </div>
      )}
    </Section>
  );
}
