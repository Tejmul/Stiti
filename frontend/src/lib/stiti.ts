// Shared client helpers: per-install token, API calls, WebSocket URL, reduced-motion, small formatters.
// The Python server (127.0.0.1:7317) is the only backend; this app is a static export it serves.

export const DEV = process.env.NODE_ENV === "development";
const BACKEND = "127.0.0.1:7317";

let memToken = "";                      // fallback when localStorage is blocked

/** Per-install token: arrives once in the URL fragment (#t=…), then lives in localStorage. */
export function getToken(): string {
  if (typeof window === "undefined") return "";
  const h = new URLSearchParams(location.hash.slice(1)).get("t");
  try {
    if (h) {
      localStorage.setItem("stiti_t", h);
      history.replaceState(null, "", location.pathname + location.search);
    }
    return h || localStorage.getItem("stiti_t") || memToken;
  } catch {
    return h || memToken;
  }
}

export class NotAllowed extends Error {}

/** The key, fetching it from Stiti's own server if this browser has never been linked (same-origin only). */
let linking: Promise<string> | null = null;
export function forgetToken() {
  memToken = "";
  try { localStorage.removeItem("stiti_t"); } catch { /* ignore */ }
}
export function ensureToken(): Promise<string> {
  const t = getToken();
  if (t) return Promise.resolve(t);
  linking ??= fetch("/api/link", { cache: "no-store" })
    .then((r) => (r.ok ? r.json() : { t: "" }))
    .then(({ t }: { t: string }) => {
      if (t) try { localStorage.setItem("stiti_t", t); } catch { /* private mode: keep in memory */ }
      memToken = t || "";
      return memToken;
    })
    .catch(() => "")
    .finally(() => { linking = null; });
  return linking;
}

export async function api<T = unknown>(path: string, init: RequestInit = {}): Promise<T> {
  let key = await ensureToken();
  let r = await fetch(path, { ...init, headers: { "x-stiti-token": key, ...(init.headers || {}) } });
  if (r.status === 403 && key) {                       // stale saved key (e.g. reinstalled) → re-link once
    forgetToken();
    key = await ensureToken();
    if (key) r = await fetch(path, { ...init, headers: { "x-stiti-token": key, ...(init.headers || {}) } });
  }
  if (r.status === 403) throw new NotAllowed("not allowed");
  const body = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error((body as { error?: string }).error || `HTTP ${r.status}`);
  return body as T;
}

export function wsUrl(): string {
  const host = DEV ? BACKEND : location.host;
  return `ws://${host}/ws?t=${encodeURIComponent(getToken())}`;
}

export function prefersReducedMotion(): boolean {
  return typeof window !== "undefined" && matchMedia("(prefers-reduced-motion: reduce)").matches;
}

export const plural = (n: number, w: string, many?: string) => `${n} ${n === 1 ? w : many ?? w + "s"}`;
export const fmtTime = (d: Date) => d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
export function fmtDay(d: Date): string {
  const t = new Date(), y = new Date(), tm = new Date();
  y.setDate(t.getDate() - 1);
  tm.setDate(t.getDate() + 1);
  if (d.toDateString() === t.toDateString()) return "Today";
  if (d.toDateString() === y.toDateString()) return "Yesterday";
  if (d.toDateString() === tm.toDateString()) return "Tomorrow";
  return d.toLocaleDateString([], { weekday: "short", day: "numeric", month: "short",
    year: d.getFullYear() === t.getFullYear() ? undefined : "numeric" });
}

// ---- types of the Python API (src/stiti/web/server.py + mind.py)
export type Fact = { id: number; text: string; group: string; mine: boolean; since: string | null };
export type Mind = {
  name: string | null;
  counts: { facts: number; people: number; rules: number; habits: number; docs: number; moments: number; conversations: number; since: string | null };
  facts: Fact[];
  people: { id: number; kind: string; name: string; summary: string | null; facts: string[] }[];
  directives: { id: number; category: string; text: string }[];
  lessons: { id: number; when: string; text: string; dont: boolean; confidence: number; seen: number }[];
  traits: { key: string; label: string; confidence: number }[];
  reflections: { text: string; at: string }[];
  habits: { name: string; cue: string | null; target: number | null; strength: number; status: string; days: (boolean | null)[] }[];
  mood: { day: string; label: string | null; n: number; mix: Record<string, number> }[];
  docs: { title: string; kind: string; chunks: number; at: string }[];
  todos: { id: number; title: string; due: string | null }[];
  alarms: { id: number; kind: string; at: string; repeats: boolean; text: string }[];
  courses: { title: string; status: string; at: string }[];
};
export type Moment = { id: number; who: "you" | "stiti"; text: string; at: string; mood: string | null };
export type Used = { memories: { text: string; at: string }[]; facts: string[]; docs: string[]; lessons: string[] } | null;
export type Reply = {
  type: "reply"; text: string; route?: string; domain?: string; mood?: string; provider?: string;
  action?: { type: string; id: number } | null; ms?: number; ended?: boolean; used?: Used;
};
export type DayState = { todos: { id: number; title: string; due: string | null }[]; alarms: { id: number; kind: string; at: string; text: string }[] };
