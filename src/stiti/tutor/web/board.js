// Stiti whiteboard runtime: a renderer driven by cue messages from Python (D14/D15).
// Python owns the lesson, layout and audio; this page only draws, animates, moves the camera and
// sends back controls / typed questions / "explain this" clicks. Excalidraw 0.18.1 (MIT).
const hash = new URLSearchParams(location.hash.slice(1));
let TOKEN = hash.get("t");
try { if (TOKEN) sessionStorage.setItem("stiti_t", TOKEN); else TOKEN = sessionStorage.getItem("stiti_t"); } catch {}
history.replaceState(null, "", "/");

const EXC = "https://esm.sh/@excalidraw/excalidraw@0.18.1/dist/prod/";
window.EXCALIDRAW_ASSET_PATH = EXC;
const React = (await import("react")).default;
const { createRoot } = await import("react-dom/client");
const X = await import(EXC + "index.js?external=react,react-dom");

const $ = (id) => document.getElementById(id);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let selectedId = null;
const api = await new Promise((res) => createRoot($("board")).render(
  React.createElement(X.Excalidraw, {
    excalidrawAPI: res, zenModeEnabled: true, theme: "light",
    initialData: { appState: { viewBackgroundColor: "#fffdf7", currentItemFontFamily: 5 } },
    UIOptions: { canvasActions: { loadScene: false, saveToActiveFile: false, toggleTheme: false } },
    onChange: (els, st) => onSelection(st),
  })));
while (api.getAppState().isLoading) await sleep(50);

const NEVER = X.CaptureUpdateAction.NEVER;
const scene = () => api.getSceneElements();
const put = (els) => api.updateScene({ elements: els, captureUpdate: NEVER });
const convert = (skels) => X.convertToExcalidrawElements(skels, { regenerateIds: false });

// Fonts: text measured with a fallback font gets clipped once the real font arrives, so make
// Excalidraw load its hand-drawn (5) and code (8) fonts before the first real draw…
// (document.fonts.check() is useless here: it says true for faces that aren't loaded yet.)
await Promise.race([
  Promise.all(["20px Excalifont", '20px "Comic Shanns"', "20px Assistant", "20px Nunito"].map((f) => document.fonts.load(f, "Aa1→✓").catch(() => null))),
  sleep(4000),
]);
// …and if a font still lands late, re-measure free text so nothing stays clipped.
function remeasure() {
  const out = scene().map((e) => {
    if (e.type !== "text" || e.containerId) return e;
    const [m] = convert([{ type: "text", id: e.id, x: e.x, y: e.y, text: e.originalText ?? e.text, fontSize: e.fontSize,
                           fontFamily: e.fontFamily, strokeColor: e.strokeColor }]);
    return X.newElementWith(e, { width: m.width, height: m.height });
  });
  put(out);
}
document.fonts.addEventListener?.("loadingdone", () => setTimeout(remeasure, 50));
$("loading")?.remove();
const anims = new Set();       // finish() callbacks of running animations
let pending = [];              // setTimeout ids of scheduled actions

function tween(ms, step) {
  return new Promise((res) => {
    const t0 = performance.now(); let done = false;
    const finish = () => { if (done) return; done = true; anims.delete(finish); step(1); res(); };
    anims.add(finish);
    const tick = () => {
      if (done) return;
      const t = Math.min(1, (performance.now() - t0) / ms);
      step(t); t < 1 ? setTimeout(tick, 16) : finish();      // setTimeout (not rAF): keeps going in background tabs
    };
    tick();
  });
}
const ease = (t) => 1 - Math.pow(1 - t, 3);
function mutate(ids, fn) {
  put(scene().map((e) => (ids.has(e.id) || (e.containerId && ids.has(e.containerId)) ? X.newElementWith(e, fn(e)) : e)));
}
function insert(els, z) { put(z === "back" ? [...els, ...scene()] : [...scene(), ...els]); }

function fresh(skels) {
  const have = new Set(scene().map((e) => e.id));
  return convert(skels).filter((e) => !have.has(e.id));       // idempotent: replayed cues never duplicate
}

function perimeter(e) {        // outline points (relative) for the "sketch" draw-on animation
  const w = e.width, h = e.height, P = [];
  if (e.type === "ellipse") {
    for (let i = 0; i <= 48; i++) { const a = -Math.PI / 2 + (i / 48) * 2 * Math.PI; P.push([w / 2 + (w / 2) * Math.cos(a), h / 2 + (h / 2) * Math.sin(a)]); }
  } else {
    const c = e.type === "diamond" ? [[w / 2, 0], [w, h / 2], [w / 2, h], [0, h / 2], [w / 2, 0]]
                                   : [[0, 0], [w, 0], [w, h], [0, h], [0, 0]];
    for (let k = 0; k < 4; k++) for (let i = 0; i < 12; i++) {
      const t = i / 12; P.push([c[k][0] + (c[k + 1][0] - c[k][0]) * t, c[k][1] + (c[k + 1][1] - c[k][1]) * t]);
    }
    P.push(c[4]);
  }
  return P;
}
const pathLen = (P) => P.reduce((s, p, i) => i ? s + Math.hypot(p[0] - P[i - 1][0], p[1] - P[i - 1][1]) : 0, 0);
const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));

// Reduced motion: things appear at once (no pen, no typing). Checked per action, so a live change applies.
const REDUCED = matchMedia("(prefers-reduced-motion: reduce)");

// The pen: a small indigo dot that rides the point being drawn, so the board looks hand-written live.
const pen = document.createElement("div");
pen.id = "pen"; pen.setAttribute("aria-hidden", "true");
document.body.appendChild(pen);
let penHide = 0;
function penAt(x, y) {          // scene coordinates → screen
  const s = api.getAppState(), r = $("board").getBoundingClientRect(), z = s.zoom.value;
  pen.style.transform = `translate(${r.left + (x + s.scrollX) * z}px, ${r.top + (y + s.scrollY) * z}px)`;
  pen.classList.add("on");
  clearTimeout(penHide);
  penHide = setTimeout(() => pen.classList.remove("on"), 260);
}

async function add(a, instant) {
  if (a.files?.length) {         // pictures (the "image" op): register the bitmap before the element that shows it
    try { api.addFiles(a.files.map((f) => ({ mimeType: "image/png", ...f, created: Date.now() }))); } catch (err) {
      send({ type: "error", msg: String(err).slice(0, 300), action: "addFiles" });
    }
  }
  const els = fresh(a.els);
  if (!els.length) return;
  const target = new Map(els.map((e) => [e.id, e.opacity ?? 100]));
  const ids = new Set(els.map((e) => e.id));
  if (instant || !a.anim || a.anim === "none" || REDUCED.matches) return insert(els, a.z);
  if (a.anim === "fade") {
    insert(els.map((e) => ({ ...e, opacity: 1 })), a.z);
    return tween(360, (t) => mutate(ids, (e) => ({ opacity: Math.max(1, Math.round(target.get(e.id) * ease(t))) })));
  }
  if (a.anim === "grow") {       // arrows / lines grow from their first point (pen at the tip); labels fade in after
    const lin = els.filter((e) => e.points), rest = els.filter((e) => !e.points);
    const full = new Map(lin.map((e) => [e.id, e.points]));
    insert([...lin.map((e) => ({ ...e, points: growPoints(e.points, 0.02) })),
            ...rest.map((e) => ({ ...e, opacity: 1 }))], a.z);
    const linIds = new Set(lin.map((e) => e.id));
    const ms = clamp(Math.max(0, ...lin.map((e) => pathLen(e.points))) * 2.2, 420, 900);
    const lead = lin[0];
    await tween(ms, (t) => {
      const k = Math.max(0.02, t < 1 ? t * (2 - t) : 1);          // ease-out, but no long crawl at the end
      put(scene().map((e) => linIds.has(e.id) ? X.newElementWith(e, { points: growPoints(full.get(e.id), k) }) : e));
      if (lead && t < 1) { const g = growPoints(full.get(lead.id), k), p = g[g.length - 1]; penAt(lead.x + p[0], lead.y + p[1]); }
    });
    const restIds = new Set(rest.map((e) => e.id));
    if (restIds.size) await tween(220, (t) => mutate(restIds, () => ({ opacity: Math.max(1, Math.round(100 * t)) })));
    return;
  }
  if (a.anim === "type" && a.els.length === 1 && a.els[0].type === "text") {
    // written out at a speaking-ish pace (~34 chars/s, capped at ~2.6 s for long lines), the pen at the caret
    const sk = a.els[0], txt = sk.text, per = 1000 / 34;
    const step = Math.max(1, Math.ceil(txt.length / (2600 / per)));
    let done = false;
    const finish = () => { done = true; };
    anims.add(finish);
    for (let i = step; i < txt.length && !done; i += step) {
      const part = txt.slice(0, i);
      const [el] = convert([{ ...sk, text: part }]);
      put([...scene().filter((e) => e.id !== sk.id), el]);
      const lines = part.split("\n"), last = lines[lines.length - 1], longest = Math.max(...lines.map((l) => l.length), 1);
      penAt(el.x + (el.width * last.length) / longest, el.y + el.height - (sk.fontSize || 20) * 0.45);
      await sleep(per * step);
    }
    anims.delete(finish);
    put([...scene().filter((e) => e.id !== sk.id), ...convert([sk])]);
    return;
  }
  if (a.anim === "sketch") {     // draw the outline like a pen, then drop in the real shape + label
    const shape = els.find((e) => !e.containerId) || els[0];
    const P = perimeter(shape), skId = shape.id + ".sk";
    const [line] = convert([{ type: "line", id: skId, x: shape.x, y: shape.y, width: 1, height: 1,
      strokeColor: shape.strokeColor, strokeWidth: shape.strokeWidth, roughness: 1 }]);
    insert([X.newElementWith(line, { points: P.slice(0, 2) })], a.z);
    await tween(clamp(pathLen(P) * 1.3, 650, 1000), (t) => {
      const n = Math.max(2, Math.round(P.length * t));
      put(scene().map((e) => e.id === skId ? X.newElementWith(e, { points: P.slice(0, n) }) : e));
      if (t < 1) penAt(shape.x + P[n - 1][0], shape.y + P[n - 1][1]);
    });
    put(scene().filter((e) => e.id !== skId));
    if (scene().some((e) => ids.has(e.id))) return;
    insert(els.map((e) => ({ ...e, opacity: 1 })), a.z);
    return tween(260, (t) => mutate(ids, (e) => ({ opacity: Math.max(1, Math.round(target.get(e.id) * t)) })));
  }
  insert(els, a.z);
}

function growPoints(pts, k) {     // reveal a polyline progressively along its length
  if (pts.length === 2) return [pts[0], [pts[1][0] * k, pts[1][1] * k]];
  const segs = pts.length - 1, upto = k * segs, i = Math.floor(upto), f = upto - i;
  const out = pts.slice(0, Math.min(pts.length, i + 1));
  if (i < segs) out.push([pts[i][0] + (pts[i + 1][0] - pts[i][0]) * f, pts[i][1] + (pts[i + 1][1] - pts[i][1]) * f]);
  return out.length >= 2 ? out : [pts[0], pts[0]];
}

const top = () => {             // keep drawings clear of Excalidraw's toolbar, only when it is showing
  const cls = document.body.classList;
  return cls.contains("presenting") || cls.contains("clean") ? 16 : 64;
};
function viewport() { const b = $("board"); return [b.clientWidth, b.clientHeight]; }
// The free part of the board: below the toolbar (when shown) and clear of the check card. A card on the right
// leaves the strip to its left; a card across the bottom (phone) leaves the space above it.
function safeArea() {
  const [vw, vh] = viewport();
  let x0 = 0, y0 = top(), x1 = vw, y1 = vh;
  const c = $("check");
  if (c && !c.hidden) {
    const b = $("board").getBoundingClientRect(), r = c.getBoundingClientRect();
    const L = r.left - b.left, T = r.top - b.top;
    if (L > vw * 0.4) x1 = Math.min(x1, L - 8);
    else y1 = Math.min(y1, T - 8);
  }
  return { x0, y0, w: Math.max(120, x1 - x0), h: Math.max(120, y1 - y0) };
}
const PAGE_W = 1600, PAGE_H = 900, MARGIN = 0.06, ZMAX = 1.15;
function camState(rect) {
  const s = safeArea(), [x, y, w, h] = rect, [vw, vh] = viewport();
  // fit with a margin, but never blow a small drawing up past ~1.15× of "the whole 1600×900 page fits the board"
  const fit = Math.min(s.w / w, s.h / h) * (1 - 2 * MARGIN);
  const cap = ZMAX * Math.min(vw / PAGE_W, (vh - top()) / PAGE_H);
  return { z: Math.max(0.05, Math.min(fit, cap)), cx: x + w / 2, cy: y + h / 2 };
}
// screen point (px, py) inside the board where the camera centre lands: the middle of the safe area
const anchor = () => { const s = safeArea(); return [s.x0 + s.w / 2, s.y0 + s.h / 2]; };
function applyCam({ z, cx, cy }) {
  const [px, py] = anchor();
  api.updateScene({ appState: { zoom: { value: z }, scrollX: px / z - cx, scrollY: py / z - cy }, captureUpdate: NEVER });
}
const refit = (ms = 450) => lastRect && camera({ rect: lastRect, ms });
let lastRect = null;
async function camera(a, instant) {
  lastRect = a.rect;
  const to = camState(a.rect);
  if (instant) return applyCam(to);
  const s = api.getAppState(), [px, py] = anchor(), z0 = s.zoom.value;
  const from = { z: z0, cx: px / z0 - s.scrollX, cy: py / z0 - s.scrollY };
  return tween(a.ms || 700, (t) => {
    const k = ease(t);
    applyCam({ z: Math.exp(Math.log(from.z) + (Math.log(to.z) - Math.log(from.z)) * k),
               cx: from.cx + (to.cx - from.cx) * k, cy: from.cy + (to.cy - from.cy) * k });
  });
}
addEventListener("resize", () => lastRect && applyCam(camState(lastRect)));
// floating cards sit just above the dock, whatever its height (caption lines, phone wrap, presenter mode)
new ResizeObserver(([e]) => document.documentElement.style.setProperty("--dock-h", `${Math.round(e.borderBoxSize?.[0]?.blockSize ?? e.target.offsetHeight)}px`))
  .observe($("dock"));
let boardH = 0;                 // the board grows / shrinks with the dock: keep the drawing framed
new ResizeObserver(() => { const h = $("board").clientHeight; if (h !== boardH) { boardH = h; lastRect && !anims.size && applyCam(camState(lastRect)); } })
  .observe($("board"));

function run(a, instant = false) {
  try {
    if (a.do === "add") return add(a, instant);
    if (a.do === "style") return mutate(new Set(a.ids), () => a.props);
    if (a.do === "erase") { const ids = new Set(a.ids); return put(scene().filter((e) => !ids.has(e.id) && !ids.has(e.containerId))); }
    if (a.do === "camera") return camera(a, instant);
  } catch (err) { send({ type: "error", msg: String(err).slice(0, 300), action: a.do }); }
}
function clearPending() { pending.forEach(clearTimeout); pending = []; }
function finishAll() { [...anims].forEach((f) => f()); }

// ---------------------------------------------------------------- UI
function setStatus(mode, text) {
  $("status").className = "pill " + (mode || "");
  $("status-text").textContent = text || mode || "";
  $("status").title = text || mode || "";
  const paused = mode === "paused";
  $("pp").dataset.cmd = paused ? "play" : "pause";
  $("pp").setAttribute("aria-label", paused ? "Play" : "Pause");
  $("pp").querySelector("use").setAttribute("href", paused ? "#i-play" : "#i-pause");
}
// "Lexer basics · part 3 of 9" → header title + progress bar
function setProgress(p, lesson) {
  if (lesson) $("lesson").textContent = lesson;
  const m = /^(.*?)\s*·\s*part\s+(\d+)\s+of\s+(\d+)\s*$/i.exec(p || "");
  if (!m) { if (p) $("segment").textContent = p; return; }
  const [, seg, n, of] = m;
  $("segment").textContent = seg;
  $("part").textContent = `part ${n} of ${of}`;
  $("fill").style.width = `${Math.round((100 * +n) / Math.max(1, +of))}%`;
  document.title = `${seg} · Stiti`;
}
function toggleDraw() {
  const on = document.body.classList.toggle("clean") === false;
  $("draw").setAttribute("aria-pressed", String(on));
  $("draw").title = on ? "Hide drawing tools (D)" : "Show drawing tools (D)";
  setTimeout(() => lastRect && applyCam(camState(lastRect)), 50);
}
function showCheck(m) {
  $("check").hidden = false;
  $("check-kind").textContent = m.kind_label || "Your turn";
  $("check-prompt").textContent = m.prompt;
  const box = $("check-options"); box.innerHTML = "";
  (m.options || []).forEach((o, i) => {
    const b = document.createElement("button");
    b.textContent = `${"ABCD"[i]}. ${o}`;
    b.onclick = () => send({ type: "text", text: "ABCD"[i] });
    box.appendChild(b);
  });
  $("q").placeholder = m.options?.length ? "Pick an option, or type it…" : "Type your answer, or say it…";
  autoFocus = true;           // focusing the box for his answer is not a raised hand (it paused every check, D40)
  $("q").focus();
  autoFocus = false;
  refit();                    // make room for the card: the drawing slides into the space beside it
}
function hideCheck() {
  const was = !$("check").hidden;
  $("check").hidden = true; $("q").placeholder = "Type a doubt or an answer";
  if (was) refit();
}
function onSelection(st) {
  const ids = Object.keys(st.selectedElementIds || {}).filter((k) => st.selectedElementIds[k]);
  const id = ids.length === 1 ? ids[0] : null;
  if (id === selectedId) return;
  selectedId = id;
  const chip = $("ask-chip");
  const el = id && scene().find((e) => e.id === id);
  const label = el && (el.text || scene().find((t) => t.containerId === id)?.text);
  chip.hidden = !label;
  if (label) chip.textContent = `Explain “${label.replace(/\s+/g, " ").slice(0, 28)}”`;
}
$("ask-chip").onclick = () => selectedId && send({ type: "click", id: selectedId });
document.querySelectorAll("#controls [data-cmd]").forEach((b) => b.onclick = () => send({ type: "control", cmd: b.dataset.cmd }));
$("draw").onclick = toggleDraw;
$("ask").onsubmit = (e) => {
  e.preventDefault();
  const t = $("q").value.trim();
  if (t) send({ type: "text", text: t });
  $("q").value = "";
};
let autoFocus = false;
$("q").addEventListener("focus", () => { if (!autoFocus) send({ type: "hand" }); });
// Hold-to-talk (so voices in his room aren't taken as his answers): hold Space ≥ 250 ms, or press and hold the mic,
// and only that speech counts. A quick Space tap stays pause / play; a click on the mic toggles the mode.
const HOLD_MS = 250;
let pttMode = false, talking = false, spaceTimer = 0, spaceDown = false;
function ptt(down) {
  if (down === talking) return;
  talking = down;
  $("mic").classList.toggle("talking", down);
  send({ type: "ptt", down });
  const st = $("status");
  if (down) { beforeTalk = [st.className.replace(/^pill\s*/, ""), $("status-text").textContent]; setStatus("talking", "listening — release to send"); }
  else if (st.classList.contains("talking") && beforeTalk) setStatus(...beforeTalk);   // unless the engine said something new
}
let beforeTalk = null;
function setPttMode(on) {
  pttMode = on;
  $("mic").setAttribute("aria-pressed", String(on));
  $("mic").title = on ? "Hold-to-talk is on: hold this (or Space) while you speak · click to turn off"
                      : "Hold to talk (or hold Space) · click: only listen while held";
  send({ type: "ptt_mode", on });
}
const typing = (e) => e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA" || e.target.closest?.(".excalidraw textarea");
addEventListener("keydown", (e) => {
  if (e.key !== " " || typing(e)) return;
  e.preventDefault();
  if (e.repeat || spaceDown) return;              // key repeat: still the same hold
  spaceDown = true;
  spaceTimer = setTimeout(() => { spaceTimer = 0; ptt(true); }, HOLD_MS);
});
addEventListener("keyup", (e) => {
  if (e.key !== " " || !spaceDown) return;
  e.preventDefault();
  spaceDown = false;
  if (spaceTimer) { clearTimeout(spaceTimer); spaceTimer = 0; send({ type: "control", cmd: $("pp").dataset.cmd }); }
  else ptt(false);
});
let micTimer = 0, micHeld = false, eatClick = false;
$("mic").addEventListener("pointerdown", (e) => {
  if (e.button !== 0) return;
  $("mic").setPointerCapture?.(e.pointerId);
  micHeld = true;
  micTimer = setTimeout(() => { micTimer = 0; ptt(true); }, HOLD_MS);
});
const micUp = () => {
  if (!micHeld) return;
  micHeld = false;
  if (micTimer) { clearTimeout(micTimer); micTimer = 0; return; }   // a short press: the click toggles the mode
  eatClick = true;                                                   // a hold: the click that follows is not a toggle
  ptt(false);
};
$("mic").addEventListener("pointerup", micUp);
$("mic").addEventListener("pointercancel", micUp);
$("mic").addEventListener("contextmenu", (e) => e.preventDefault());   // long-press on a phone is a hold, not a menu
$("mic").addEventListener("click", () => { if (eatClick) { eatClick = false; return; } setPttMode(!pttMode); });
addEventListener("blur", () => {                  // switching windows mid-hold must not leave the mic open
  clearTimeout(spaceTimer); clearTimeout(micTimer); spaceTimer = micTimer = 0; spaceDown = micHeld = false; ptt(false);
});
addEventListener("keydown", (e) => {
  if (typing(e)) return;
  const map = { ArrowLeft: "back", ArrowRight: "next", r: "repeat", R: "repeat" };
  if (map[e.key]) { e.preventDefault(); send({ type: "control", cmd: map[e.key] }); }
  if (e.key === "h" || e.key === "H") { e.preventDefault(); $("q").focus(); }
  if (e.key === "f" || e.key === "F") { e.preventDefault(); present(); }
  if ((e.key === "d" || e.key === "D") && !e.metaKey && !e.ctrlKey) { e.preventDefault(); toggleDraw(); }
});
// Presenter mode for a big monitor: full screen, drawing toolbars hidden, large captions.
function present() {
  const on = document.body.classList.toggle("presenting");
  try { on ? document.documentElement.requestFullscreen?.() : document.exitFullscreen?.(); } catch {}
  setTimeout(() => lastRect && applyCam(camState(lastRect)), 300);
}
document.addEventListener("fullscreenchange", () => {
  if (!document.fullscreenElement) document.body.classList.remove("presenting");
  setTimeout(() => lastRect && applyCam(camState(lastRect)), 300);
});

// ---------------------------------------------------------------- socket
let ws = null, retry = 300;
function send(m) { if (ws?.readyState === 1) ws.send(JSON.stringify(m)); }
async function handle(m) {
  if (m.type === "cue") {
    clearPending(); finishAll();
    $("caption").textContent = m.say || "";
    if (m.progress || m.lesson) setProgress(m.progress, m.lesson);
    for (const a of m.actions || []) pending.push(setTimeout(() => run(a), a.at_ms || 0));
  } else if (m.type === "reset") {
    clearPending(); finishAll(); put([]);
    for (const a of m.actions || []) await run(a, true);
  } else if (m.type === "actions") {             // live answers / parking lot: run now, in order
    for (const a of m.actions || []) pending.push(setTimeout(() => run(a), a.at_ms || 0));
  } else if (m.type === "pause") { clearPending(); finishAll(); }
  else if (m.type === "status") { setStatus(m.mode, m.text); if (m.caption !== undefined) $("caption").textContent = m.caption; }
  else if (m.type === "speed") $("speed").textContent = `${Number(m.value).toFixed(1)}×`;
  else if (m.type === "check") showCheck(m);
  else if (m.type === "check_done") hideCheck();
  else if (m.type === "end") { setStatus("done", "lesson finished"); hideCheck(); }
}
function connect() {
  ws = new WebSocket(`ws://${location.host}/ws?t=${encodeURIComponent(TOKEN || "")}`);
  ws.onopen = () => {
    retry = 300; setStatus("ready", "connected"); send({ type: "ready", w: viewport()[0], h: viewport()[1] });
    if (pttMode) send({ type: "ptt_mode", on: true });          // a reconnect keeps his hold-to-talk choice
  };
  ws.onmessage = (ev) => handle(JSON.parse(ev.data));
  ws.onclose = (ev) => {
    if (ev.code === 4403) return setStatus("offline", "not allowed (open the link Stiti gave you)");
    setStatus("offline", "reconnecting…");
    setTimeout(connect, (retry = Math.min(retry * 2, 5000)));
  };
}
window.stitiBoard = { api, X, run, scene };      // for tests / debugging
connect();
$("fs").onclick = (e) => { e.stopPropagation(); present(); };
