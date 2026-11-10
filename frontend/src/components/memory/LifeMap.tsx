"use client";
// The signature: a still map of his life. Him at the centre, a hub per part of life on a spoke, one dot per
// thing Stiti knows, and the landing sphere's blue "dust" held still behind it. Draws itself in once, then
// never moves on its own. Hover/focus a dot to read it; click to jump to its line below.
import gsap from "gsap";
import { useLayoutEffect, useMemo, useRef, useState } from "react";
import type { Mind } from "@/lib/stiti";
import { plural, prefersReducedMotion } from "@/lib/stiti";
import { FACT_GROUPS, jump } from "./bits";

type Item = { key: string; text: string; href: string; mine?: boolean };
type Group = { name: string; href: string; items: Item[]; hint?: string };

const C = 320;                                            // viewBox centre (640 × 640)
const f1 = (n: number) => +n.toFixed(1);

/** Seeded PRNG (Park–Miller) so the dust is identical on every render and every visit. */
function rng(seed: number) { return () => ((seed = (seed * 16807) % 2147483647) - 1) / 2147483646; }
const DUST = (() => {
  const rand = rng(7), out: { x: number; y: number; r: number; o: number; deep: boolean }[] = [];
  for (let i = 0; i < 340; i++) {
    const a = rand() * Math.PI * 2, r = 300 * Math.sqrt(rand());
    out.push({ x: f1(C + Math.cos(a) * r), y: f1(C + Math.sin(a) * r), r: +(0.7 + rand() * 1.1).toFixed(2),
      o: +(0.16 + 0.5 * (1 - r / 300) * rand()).toFixed(2), deep: rand() < 0.22 });
  }
  return out;
})();

function groupsOf(d: Mind): Group[] {
  const g: Group[] = [];
  for (const name of FACT_GROUPS) {
    const items = d.facts.filter((f) => f.group === name)
      .map((f) => ({ key: `f${f.id}`, text: f.text, href: `#fact-${f.id}`, mine: f.mine }));
    if (items.length) g.push({ name, items, href: "#about" });
  }
  // People, Rules and Habits always get a hub: when empty it's a dashed "not yet" hub that says how to fill it.
  g.push({ name: "People", href: "#people", hint: "Mention someone — “my sister Ayesha lives in Pune”.",
    items: d.people.map((p) => ({ key: `p${p.id}`, text: `${p.name}${p.summary ? " — " + p.summary : ""}`, href: `#person-${p.id}` })) });
  g.push({ name: "Rules", href: "#rules", hint: "Correct Stiti once — “don't call me bro” — and it becomes a rule.",
    items: [...d.directives.map((x) => ({ key: `d${x.id}`, text: x.text, href: `#directive-${x.id}` })),
            ...d.lessons.map((x) => ({ key: `l${x.id}`, text: `${x.dont ? "Don't: " : ""}${x.text}`, href: `#lesson-${x.id}` }))] });
  g.push({ name: "Habits", href: "#habits", hint: "Say “I want to go to the gym 4 times a week”.",
    items: d.habits.map((h, i) => ({ key: `h${i}`, text: h.name, href: `#habit-${i}` })) });
  if (d.docs.length) g.push({ name: "Files", href: "#files",
    items: d.docs.map((x, i) => ({ key: `doc${i}`, text: `${x.title} — ${plural(x.chunks, "passage")}`, href: `#doc-${i}` })) });
  return g;
}

function layout(groups: Group[]) {
  const n = groups.length, R = n <= 2 ? 150 : n <= 5 ? 175 : 188;
  const wedge = (2 * Math.PI) / n;                        // each hub gets its own slice, so fans never collide
  return groups.map((g, gi) => {
    const ang = -Math.PI / 2 + gi * wedge;
    const hx = C + Math.cos(ang) * R, hy = C + Math.sin(ang) * R;
    const m = g.items.length, spread = Math.min(m > 1 ? wedge * 1.25 : 0, 2.4);
    const items = g.items.map((it, k) => {
      const off = m > 1 ? (k / (m - 1) - 0.5) * spread : 0;
      const rr = 62 + (k % 2) * 22 + (m > 8 ? (k % 3) * 7 : 0);
      return { ...it, x: f1(hx + Math.cos(ang + off) * rr), y: f1(hy + Math.sin(ang + off) * rr) };
    });
    return { ...g, ang, hx: f1(hx), hy: f1(hy), len: f1(Math.hypot(hx - C, hy - C) - 46), items };
  });
}

export default function LifeMap({ mind }: { mind: Mind }) {
  const svg = useRef<SVGSVGElement>(null);
  const seen = useRef<Set<string> | null>(null);
  const [cap, setCap] = useState<{ head: string; text: string } | null>(null);
  const hubs = useMemo(() => layout(groupsOf(mind)), [mind]);
  const keys = hubs.flatMap((h) => h.items.map((i) => i.key)).join(",");
  const known = hubs.some((h) => h.items.length);

  // One-time entrance: dust, then him, spokes draw out, hubs, twigs, dots (≈25 ms apart). Nothing loops.
  useLayoutEffect(() => {
    if (prefersReducedMotion()) return;
    const ctx = gsap.context((self) => {
      const q = (s: string) => (self.selector ? self.selector(s) : []) as Element[];
      const draw = (el: Element) => +((el as SVGElement).dataset.len || 0);
      const tl = gsap.timeline({ defaults: { ease: "power3.out" } });
      tl.from(q(".m-dust"), { opacity: 0, duration: 1.4, ease: "power1.out" }, 0)
        .from(q(".m-me"), { opacity: 0, scale: 0.6, transformOrigin: "50% 50%", duration: 0.8 }, 0.05);
      const spokes = q(".m-spoke:not(.is-ghost)"), ghosts = q(".m-spoke.is-ghost"), twigs = q(".m-twig"), nodes = q(".m-node");
      if (spokes.length) tl.from(spokes, { strokeDashoffset: (_: number, el: Element) => draw(el), duration: 0.7, stagger: 0.05, ease: "power2.inOut" }, 0.25);
      if (ghosts.length) tl.from(ghosts, { opacity: 0, duration: 0.6, stagger: 0.05 }, 0.4);
      tl.from(q(".m-hub"), { opacity: 0, scale: 0.4, transformOrigin: "50% 50%", duration: 0.65, stagger: 0.05, ease: "back.out(1.7)" }, 0.6);
      if (twigs.length) tl.from(twigs, { strokeDashoffset: (_: number, el: Element) => draw(el), duration: 0.45, stagger: 0.025 }, 0.9);
      if (nodes.length) tl.from(nodes, { opacity: 0, scale: 0, transformOrigin: "50% 50%", duration: 0.5, stagger: 0.025, ease: "back.out(2.2)" }, 1.0);
    }, svg);
    return () => ctx.revert();
  }, []);

  // A dot that appears later (he just told Stiti something) pops in once; the rest stay still.
  useLayoutEffect(() => {
    const all = new Set(keys.split(",").filter(Boolean));
    if (seen.current && !prefersReducedMotion()) {
      const fresh = [...all].filter((k) => !seen.current!.has(k));
      const els = fresh.map((k) => svg.current!.querySelector(`[data-key="${k}"]`)).filter(Boolean) as Element[];
      if (els.length) gsap.from(els, { opacity: 0, scale: 0, transformOrigin: "50% 50%", duration: 0.6, ease: "back.out(2.4)" });
    }
    seen.current = all;
  }, [keys]);

  const name = mind.name || "You";
  const go = (e: React.MouseEvent, href: string) => { e.preventDefault(); jump(href); };

  return (
    <figure className="map" aria-labelledby="map-cap-h">
      <svg ref={svg} className="map__svg" viewBox="0 0 640 640" role="group"
        aria-label={`Map of what Stiti knows about ${name}, grouped by part of life. Each dot opens its line below.`}>
        <g className="m-dust" aria-hidden="true">
          {DUST.map((p, i) => <circle key={i} cx={p.x} cy={p.y} r={p.r} opacity={p.o} className={p.deep ? "is-deep" : undefined} />)}
        </g>
        <g aria-hidden="true">
          {hubs.map((h) => {
            const sx = f1(C + Math.cos(h.ang) * 46), sy = f1(C + Math.sin(h.ang) * 46);
            const ghost = !h.items.length;
            return <line key={h.name} className={`m-spoke${ghost ? " is-ghost" : ""}`} x1={sx} y1={sy} x2={h.hx} y2={h.hy}
              data-len={h.len} strokeDasharray={ghost ? "2 5" : h.len} />;
          })}
          {hubs.flatMap((h) => h.items.map((it) => {
            const len = f1(Math.hypot(it.x - h.hx, it.y - h.hy));
            return <line key={it.key} className="m-twig" x1={h.hx} y1={h.hy} x2={it.x} y2={it.y} data-len={len} strokeDasharray={len} />;
          }))}
        </g>
        <g>
          {hubs.map((h) => {
            const ghost = !h.items.length;
            const label = ghost ? `${h.name}: nothing yet. ${h.hint}` : `${h.name}: ${plural(h.items.length, "thing")}`;
            const show = () => setCap(ghost ? { head: `${h.name} · nothing yet`, text: h.hint! }
              : { head: h.name, text: `${plural(h.items.length, "thing")} — open the list below.` });
            return (
              <g key={h.name}>
                <a className={`m-hub${ghost ? " is-ghost" : ""}`} href={h.href} aria-label={label}
                  onClick={(e) => go(e, h.href)} onPointerEnter={show} onFocus={show}>
                  <circle cx={h.hx} cy={h.hy} r={ghost ? 30 : 34} />
                  <text x={h.hx} y={h.hy - (ghost ? -4 : 1)} textAnchor="middle">{h.name}</text>
                  {!ghost && <text className="m-count" x={h.hx} y={h.hy + 13} textAnchor="middle">{h.items.length}</text>}
                </a>
                {h.items.map((it) => {
                  const on = () => setCap({ head: h.name, text: it.text });
                  return (
                    <a key={it.key} data-key={it.key} className={`m-node${it.mine ? " is-mine" : ""}`} href={it.href}
                      aria-label={`${h.name}: ${it.text}`} onClick={(e) => go(e, it.href)} onPointerEnter={on} onFocus={on}>
                      <circle className="hit" cx={it.x} cy={it.y} r={15} />
                      <circle className="halo" cx={it.x} cy={it.y} r={13} />
                      <circle className="ring" cx={it.x} cy={it.y} r={9.5} />
                      <circle className="dot" cx={it.x} cy={it.y} r={4.5} />
                    </a>
                  );
                })}
              </g>
            );
          })}
        </g>
        <g className="m-me" aria-hidden="true">
          <circle cx={C} cy={C} r={46} />
          <text x={C} y={C + 5} textAnchor="middle">{name}</text>
        </g>
      </svg>
      <figcaption className="map__cap" id="map-cap-h">
        <span className="label">{cap ? cap.head : "Your life, as Stiti sees it"}</span>
        <span className="map__detail">
          {cap ? cap.text : known ? "Point at a dot to read it. Click to open it below." : "Nothing yet. Tell Stiti something about you below and it appears here."}
        </span>
      </figcaption>
    </figure>
  );
}
