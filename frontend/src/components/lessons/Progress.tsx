"use client";
// Your progress: per file / topic, how many of its topics are known, shaky or still new (the tutor's mastery files).
import type { LessonProgress } from "@/lib/stiti";
import { plural } from "@/lib/stiti";
import { Arrow, Icon, fmtWhen } from "./bits";

export default function Progress({ rows, onContinue }: { rows: LessonProgress[]; onContinue: (r: LessonProgress) => (() => void) | null }) {
  return (
    <section className="block" id="progress" aria-labelledby="progress-h">
      <header className="sec__head">
        <h2 id="progress-h"><span className="thin">Your</span> <span className="bold">progress</span></h2>
      </header>
      {rows.length ? (
        <div className="progs">
          {rows.map((r) => {
            const go = onContinue(r);
            const pct = (n: number) => `${r.total ? (n / r.total) * 100 : 0}%`;
            return (
              <article className="prog" key={r.key}>
                <div className="prog__top">
                  <Icon name={r.kind === "file" ? "file" : "topic"} className="prog__ico" />
                  <h3 className="prog__name" title={r.source}>{r.source}</h3>
                </div>
                <div className="bar" role="img"
                  aria-label={`${r.known} known, ${r.shaky} shaky, ${r.new} new, of ${plural(r.total, "topic")}`}>
                  <i className="bar__k" style={{ width: pct(r.known) }} />
                  <i className="bar__s" style={{ width: pct(r.shaky) }} />
                </div>
                <p className="legend">
                  <span><i className="dot dot--k" />{r.known} known</span>
                  <span><i className="dot dot--s" />{r.shaky} shaky</span>
                  <span><i className="dot dot--n" />{r.new} new</span>
                </p>
                {r.revise.length > 0 && <p className="prog__rev">To revise: {r.revise.join(", ")}</p>}
                <div className="prog__foot">
                  <span className="prog__meta">{plural(r.total, "topic")}{r.last_seen ? ` · last lesson ${fmtWhen(r.last_seen)}` : ""}</span>
                  {go && <button type="button" className="link-arrow" onClick={go}>Continue <Arrow /></button>}
                </div>
              </article>
            );
          })}
        </div>
      ) : (
        <div className="empty">
          <p className="empty__text">Nothing yet. After your first lesson, each file or topic shows here with how much of it you
            know, what&apos;s shaky, and what&apos;s still new. Next time she starts from the shaky parts.</p>
        </div>
      )}
    </section>
  );
}
