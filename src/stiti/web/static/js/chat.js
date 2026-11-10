// Stiti chat client. One WebSocket to the local server; every message goes through the same Engine
// as voice/terminal, so this is the same Stiti with the same memory.
import { reducedMotion, token, wireNav } from "./common.js";
import { createMind } from "./mind.js";

const $ = (id) => document.getElementById(id);
const log = $("log"), input = $("composer-input"), send = $("send"), form = $("composer");
const mind = createMind($("mind"));
const TOKEN = token();
let ws = null, retry = 400, busy = false, lastDay = null, thinkingEl = null, streamEl = null;

const MARK = `<svg viewBox="0 0 32 32" fill="none" aria-hidden="true"><circle cx="16" cy="16" r="6.5" fill="currentColor"/><ellipse cx="16" cy="16" rx="14" ry="5.2" stroke="currentColor" stroke-width="2.4" transform="rotate(-24 16 16)"/></svg>`;
const TICK = `<svg viewBox="0 0 16 16" fill="none" aria-hidden="true"><path d="M3.5 8.5l3 3 6-7" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
const SUGGEST = ["What's on my todo list?", "Remind me to drink water in 1 hour", "What did we talk about yesterday?",
                 "Add call mom to my todos", "Set an alarm for 7 am tomorrow"];

// ------------------------------------------------------------------ helpers
const esc = (s) => s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmtTime = (d) => d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
function dayLabel(d) {
  const today = new Date(); const y = new Date(); y.setDate(today.getDate() - 1);
  if (d.toDateString() === today.toDateString()) return "Today";
  if (d.toDateString() === y.toDateString()) return "Yesterday";
  return d.toLocaleDateString([], { weekday: "short", day: "numeric", month: "short" });
}
// internal ids like "(task #3)" / "(#1)" / "(lesson L2)" are for the terminal, not for people
const clean = (t) => t.replace(/\s*\((?:task |lesson )?#?L?\d+\)/g, "");
function rich(text, animate) {
  let h = esc(clean(text)).replace(/\*\*(.+?)\*\*/g, "<b>$1</b>").replace(/\n/g, "<br>");
  if (!animate || reducedMotion) return h;
  // word-by-word fade (tags kept intact); total reveal capped at ~0.7 s
  const parts = h.split(/(<[^>]+>|\s+)/);
  const words = parts.filter((p) => p && !p.startsWith("<") && p.trim()).length;
  const step = Math.min(28, 700 / Math.max(1, words));
  let i = 0;
  return parts.map((p) => (!p || p.startsWith("<") || !p.trim()) ? p
    : `<span class="w" style="animation-delay:${Math.round(i++ * step)}ms">${p}</span>`).join("");
}
function scrollDown() { log.scrollTop = log.scrollHeight; }

/** What did she just do? -> chip {icon, label} for fast-path actions. Icons: /icons/<n>.png pictograms. */
function chipFor(r) {
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

function metaFor(r, when) {
  const bits = [fmtTime(when)];
  if (r.route === "fast_path") bits.push(`on your Mac · ${r.ms} ms`);
  else if (r.route === "llm") bits.push(`${r.provider ? "via " + r.provider : "cloud"} · ${r.ms} ms`);
  else if (r.route === "degraded") bits.push("from memory · thinking brain offline");
  return bits.join(" · ");
}

// ------------------------------------------------------------------ rendering
function addDay(d) {
  const label = dayLabel(d);
  if (label === lastDay) return;
  lastDay = label;
  const el = document.createElement("div");
  el.className = "day label"; el.textContent = label;
  log.appendChild(el);
}
function addYou(text, when = new Date(), animate = true) {
  addDay(when);
  const el = document.createElement("div");
  el.className = "msg msg--you";
  if (!animate) el.style.animation = "none";
  el.innerHTML = `<div class="msg__body"></div>`;
  el.firstChild.textContent = text;
  log.appendChild(el);
  scrollDown();
}
function addStiti(r, when = new Date(), animate = true) {
  addDay(when);
  const chip = chipFor(r);
  const el = document.createElement("div");
  el.className = "msg msg--stiti";
  if (!animate) el.style.animation = "none";
  el.innerHTML = `<div class="msg__avatar">${MARK}</div><div class="msg__body">
      ${chip ? `<div class="chip"><img src="/icons/${chip.icon}.png" alt="" width="20" height="20">${esc(chip.label)}</div>` : ""}
      <div class="msg__text">${rich(r.text || "", animate)}</div>
      ${r.route || animate ? `<div class="msg__meta">${esc(metaFor(r, when))}</div>` : ""}</div>`;
  log.appendChild(el);
  scrollDown();
}
function welcome(name) {
  const el = document.createElement("div");
  el.className = "welcome";
  el.innerHTML = `<p class="label">Your local AI buddy</p>
    <h2><span class="thin">Hey${name ? " " + esc(name) : ""}.</span><br><span class="bold">What's on your mind?</span></h2>
    <p>Ask about anything you've told her before, or let her handle todos, alarms and reminders. Everything you say stays on this Mac.</p>`;
  log.appendChild(el);
}
function showThinking(on) {
  if (on && !thinkingEl) {
    thinkingEl = document.createElement("div");
    thinkingEl.className = "thinking";
    thinkingEl.innerHTML = `<span><i></i> <i></i> <i></i></span> thinking`;
    log.appendChild(thinkingEl); scrollDown();
  } else if (!on && thinkingEl) { thinkingEl.remove(); thinkingEl = null; }
}
function setMindState(state, text) {
  mind.set(state);
  $("mind-state").textContent = text;
}

function renderSuggest(show) {
  const box = $("suggest");
  box.innerHTML = "";
  if (!show) return;
  SUGGEST.slice(0, 4).forEach((s) => {
    const b = document.createElement("button");
    b.type = "button"; b.textContent = s;
    b.onclick = () => say(s);
    box.appendChild(b);
  });
}

function renderState(st) {
  const todos = $("todos"), alarms = $("alarms");
  todos.innerHTML = ""; alarms.innerHTML = "";
  (st.todos || []).forEach((t) => {
    const li = document.createElement("li");
    li.className = "todo";
    const due = t.due ? new Date(t.due) : null;
    li.innerHTML = `<button class="todo__check" type="button" aria-label="Mark “${esc(t.title)}” done">${TICK}</button>
      <span><span class="todo__title"></span>${due ? `<span class="todo__due">due ${esc(dayLabel(due))} ${esc(fmtTime(due))}</span>` : ""}</span>`;
    li.querySelector(".todo__title").textContent = t.title;
    li.querySelector("button").onclick = () => done(t.id, li);
    todos.appendChild(li);
  });
  (st.alarms || []).forEach((a) => {
    const li = document.createElement("li");
    li.className = "alarm";
    const at = new Date(a.at);
    li.innerHTML = `<img src="/icons/180.png" alt="" width="20" height="20"><span><span class="alarm__text"></span>
      <span class="alarm__at">${esc(a.kind)} · ${esc(dayLabel(at))} ${esc(fmtTime(at))}</span></span>`;
    li.querySelector(".alarm__text").textContent =
      a.kind === "alarm" ? "Alarm" : (a.text || "Reminder");
    alarms.appendChild(li);
  });
  const n = (st.todos || []).length;
  $("todos-empty").hidden = n > 0;
  $("alarms-empty").hidden = (st.alarms || []).length > 0;
  $("todos-n").textContent = n ? String(n) : "";
  const c = $("today-count");
  c.hidden = !n; c.textContent = String(n);
}

async function done(id, li) {
  li.classList.add("is-done");
  try {
    const r = await fetch(`/api/todo/${id}/done`, { method: "POST", headers: { "x-stiti-token": TOKEN } });
    if (r.ok) setTimeout(async () => renderState(await r.json()), 500);
    else li.classList.remove("is-done");
  } catch { li.classList.remove("is-done"); }
}

// ------------------------------------------------------------------ talking
function say(text) {
  text = text.trim();
  if (!text || busy || ws?.readyState !== 1) return;
  log.querySelector(".welcome")?.remove();
  renderSuggest(false);
  addYou(text);
  ws.send(JSON.stringify({ type: "say", text }));
  busy = true; send.disabled = true;
  input.value = ""; autosize();
}

function handle(m) {
  if (m.type === "hello") {
    log.innerHTML = ""; lastDay = null;
    const name = m.name;
    $("hello").innerHTML = `<span class="thin">Hi</span> <span class="bold">${esc(name || "there")}.</span>`;
    const brain = $("brain");
    brain.classList.toggle("is-on", m.llm); brain.classList.toggle("is-off", !m.llm);
    $("brain-text").textContent = m.llm ? "Thinking brain connected (free cloud model)"
      : "Thinking brain offline — todos, alarms and memory still work";
    (m.history || []).forEach((h) => h.who === "you"
      ? addYou(h.text, new Date(h.ts), false) : addStiti({ text: h.text }, new Date(h.ts), false));
    if (!(m.history || []).length) welcome(name);
    renderSuggest(true);
    renderState(m.state || {});
    setMindState(m.llm ? "idle" : "offline", m.llm ? "Here for you" : "Here · offline brain");
    scrollDown();
  } else if (m.type === "thinking") {
    showThinking(true);
    setMindState("thinking", "Thinking");
  } else if (m.type === "delta") {                 // reply streaming in while she writes it
    if (!streamEl) {
      showThinking(false);
      addDay(new Date());
      streamEl = document.createElement("div");
      streamEl.className = "msg msg--stiti";
      streamEl.innerHTML = `<div class="msg__avatar">${MARK}</div><div class="msg__body"><div class="msg__text"></div></div>`;
      log.appendChild(streamEl);
      setMindState("thinking", "Talking");
    }
    streamEl.querySelector(".msg__text").textContent += m.text;
    scrollDown();
  } else if (m.type === "reply") {
    showThinking(false);
    const streamed = !!streamEl;
    if (streamEl) { streamEl.remove(); streamEl = null; }
    addStiti(m, new Date(), !streamed);
    mind.pulse();
    busy = false; send.disabled = !input.value.trim();
    setMindState("idle", m.route === "fast_path" ? "Done" : "Here for you");
    setTimeout(() => $("mind-state").textContent === "Done" && ($("mind-state").textContent = "Here for you"), 2500);
    input.focus();
  } else if (m.type === "state") {
    renderState(m);
  }
}

function connect() {
  if (!TOKEN) { $("gate").hidden = false; setMindState("offline", "Not connected"); return; }
  ws = new WebSocket(`ws://${location.host}/ws?t=${encodeURIComponent(TOKEN)}`);
  ws.onopen = () => { retry = 400; $("gate").hidden = true; };
  ws.onmessage = (e) => handle(JSON.parse(e.data));
  ws.onclose = (e) => {
    showThinking(false); busy = false;
    if (e.code === 4403) { $("gate").hidden = false; setMindState("offline", "Not connected"); return; }
    setMindState("offline", "Reconnecting…");
    $("brain-text").textContent = "Lost the connection to Stiti. Is uv run stiti web still running?";
    $("brain").classList.remove("is-on"); $("brain").classList.add("is-off");
    setTimeout(connect, (retry = Math.min(retry * 2, 6000)));
  };
}

// ------------------------------------------------------------------ composer + layout
function autosize() { input.style.height = "auto"; input.style.height = Math.min(input.scrollHeight, 180) + "px"; }
input.addEventListener("input", () => { autosize(); send.disabled = busy || !input.value.trim(); });
input.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); say(input.value); }
});
form.addEventListener("submit", (e) => { e.preventDefault(); say(input.value); });

const side = $("side"), todayBtn = $("today-btn");
const toggleSide = (open) => { side.classList.toggle("is-open", open); todayBtn.setAttribute("aria-expanded", String(open)); };
todayBtn.addEventListener("click", () => toggleSide(!side.classList.contains("is-open")));
$("side-close").addEventListener("click", () => toggleSide(false));
addEventListener("keydown", (e) => e.key === "Escape" && toggleSide(false));

wireNav();
connect();
input.focus();
