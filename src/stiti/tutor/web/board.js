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
  Promise.all(["20px Excalifont", '20px "Comic Shanns"', "20px Assistant"].map((f) => document.fonts.load(f, "Aa1→✓").catch(() => null))),
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
    for (let i = 0; i <= 36; i++) { const a = -Math.PI / 2 + (i / 36) * 2 * Math.PI; P.push([w / 2 + (w / 2) * Math.cos(a), h / 2 + (h / 2) * Math.sin(a)]); }
  } else if (e.type === "diamond") {
    [[w / 2, 0], [w, h / 2], [w / 2, h], [0, h / 2], [w / 2, 0]].forEach((p) => P.push(p));
  } else {
    const c = [[0, 0], [w, 0], [w, h], [0, h], [0, 0]];
    for (let k = 0; k < 4; k++) for (let i = 0; i < 6; i++) {
      const t = i / 6; P.push([c[k][0] + (c[k + 1][0] - c[k][0]) * t, c[k][1] + (c[k + 1][1] - c[k][1]) * t]);
    }
    P.push([0, 0]);
  }
  return P;
}

async function add(a, instant) {
  const els = fresh(a.els);
  if (!els.length) return;
  const target = new Map(els.map((e) => [e.id, e.opacity ?? 100]));
  const ids = new Set(els.map((e) => e.id));
  if (instant || !a.anim || a.anim === "none") return insert(els, a.z);
  if (a.anim === "fade") {
    insert(els.map((e) => ({ ...e, opacity: 1 })), a.z);
    return tween(320, (t) => mutate(ids, (e) => ({ opacity: Math.max(1, Math.round(target.get(e.id) * ease(t))) })));
  }
  if (a.anim === "grow") {       // arrows / lines grow from their first point; labels fade in after
    const lin = els.filter((e) => e.points), rest = els.filter((e) => !e.points);
    const full = new Map(lin.map((e) => [e.id, e.points]));
    insert([...lin.map((e) => ({ ...e, points: e.points.map((p) => [p[0] * 0.02, p[1] * 0.02]) })),
            ...rest.map((e) => ({ ...e, opacity: 1 }))], a.z);
    const linIds = new Set(lin.map((e) => e.id));
    await tween(420, (t) => {
      const k = Math.max(0.02, ease(t));
      put(scene().map((e) => linIds.has(e.id) ? X.newElementWith(e, { points: growPoints(full.get(e.id), k) }) : e));
    });
    const restIds = new Set(rest.map((e) => e.id));
    if (restIds.size) await tween(200, (t) => mutate(restIds, () => ({ opacity: Math.max(1, Math.round(100 * t)) })));
    return;
  }
  if (a.anim === "type" && a.els.length === 1 && a.els[0].type === "text") {
    const sk = a.els[0], txt = sk.text, step = Math.max(1, Math.round(txt.length / 18));
    let done = false;
    const finish = () => { done = true; };
    anims.add(finish);
    for (let i = step; i < txt.length && !done; i += step) {
      const [el] = convert([{ ...sk, text: txt.slice(0, i) }]);
      put([...scene().filter((e) => e.id !== sk.id), el]);
      await sleep(28);
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
    await tween(380, (t) => {
      const n = Math.max(2, Math.round(P.length * t));
      put(scene().map((e) => e.id === skId ? X.newElementWith(e, { points: P.slice(0, n) }) : e));
    });
    put(scene().filter((e) => e.id !== skId));
    if (scene().some((e) => ids.has(e.id))) return;
    insert(els.map((e) => ({ ...e, opacity: 1 })), a.z);
    return tween(220, (t) => mutate(ids, (e) => ({ opacity: Math.max(1, Math.round(target.get(e.id) * t)) })));
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

const top = () => (document.body.classList.contains("presenting") ? 12 : 64);   // clear of the toolbar
function viewport() { const b = $("board"); return [b.clientWidth, b.clientHeight]; }
function camState(rect) {
  const [vw, vh] = viewport(), [x, y, w, h] = rect;
  const z = Math.min(vw / w, (vh - top()) / h) * 0.97;
  return { z, cx: x + w / 2, cy: y + h / 2 };
}
function applyCam({ z, cx, cy }) {
  const [vw, vh] = viewport();
  api.updateScene({ appState: { zoom: { value: z }, scrollX: vw / (2 * z) - cx, scrollY: (vh + top()) / (2 * z) - cy }, captureUpdate: NEVER });
}
let lastRect = null;
async function camera(a, instant) {
  lastRect = a.rect;
  const to = camState(a.rect);
  if (instant) return applyCam(to);
  const s = api.getAppState(), [vw, vh] = viewport(), z0 = s.zoom.value;
  const from = { z: z0, cx: vw / (2 * z0) - s.scrollX, cy: (vh + top()) / (2 * z0) - s.scrollY };
  return tween(a.ms || 700, (t) => {
    const k = ease(t);
    applyCam({ z: Math.exp(Math.log(from.z) + (Math.log(to.z) - Math.log(from.z)) * k),
               cx: from.cx + (to.cx - from.cx) * k, cy: from.cy + (to.cy - from.cy) * k });
  });
}
addEventListener("resize", () => lastRect && applyCam(camState(lastRect)));

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
  const s = $("status"); s.className = "pill " + (mode || ""); s.textContent = text || mode || "";
  $("pp").textContent = mode === "paused" ? "▶" : "⏸";
  $("pp").dataset.cmd = mode === "paused" ? "play" : "pause";
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
  $("q").placeholder = m.options?.length ? "Pick an option, or type / say your answer…" : "Type your answer (or just say it)…";
  $("q").focus();
}
function hideCheck() { $("check").hidden = true; $("q").placeholder = "✋ Ask a question or type your answer…  (H)"; }
function onSelection(st) {
  const ids = Object.keys(st.selectedElementIds || {}).filter((k) => st.selectedElementIds[k]);
  const id = ids.length === 1 ? ids[0] : null;
  if (id === selectedId) return;
  selectedId = id;
  const chip = $("ask-chip");
  const el = id && scene().find((e) => e.id === id);
  const label = el && (el.text || scene().find((t) => t.containerId === id)?.text);
  chip.hidden = !label;
  if (label) chip.textContent = `✋ Explain “${label.replace(/\s+/g, " ").slice(0, 28)}”`;
}
$("ask-chip").onclick = () => selectedId && send({ type: "click", id: selectedId });
document.querySelectorAll("#controls > button").forEach((b) => b.onclick = () => send({ type: "control", cmd: b.dataset.cmd }));
$("ask").onsubmit = (e) => {
  e.preventDefault();
  const t = $("q").value.trim();
  if (t) send({ type: "text", text: t });
  $("q").value = "";
};
$("q").addEventListener("focus", () => send({ type: "hand" }));
addEventListener("keydown", (e) => {
  if (e.target.tagName === "INPUT" || e.target.closest?.(".excalidraw textarea")) return;
  const map = { " ": $("pp").dataset.cmd, ArrowLeft: "back", ArrowRight: "next", r: "repeat", R: "repeat" };
  if (map[e.key]) { e.preventDefault(); send({ type: "control", cmd: map[e.key] }); }
  if (e.key === "h" || e.key === "H") { e.preventDefault(); $("q").focus(); }
  if (e.key === "f" || e.key === "F") { e.preventDefault(); present(); }
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
    if (m.progress) $("progress").textContent = m.progress;
    for (const a of m.actions || []) pending.push(setTimeout(() => run(a), a.at_ms || 0));
  } else if (m.type === "reset") {
    clearPending(); finishAll(); put([]);
    for (const a of m.actions || []) await run(a, true);
  } else if (m.type === "actions") {             // live answers / parking lot: run now, in order
    for (const a of m.actions || []) pending.push(setTimeout(() => run(a), a.at_ms || 0));
  } else if (m.type === "pause") { clearPending(); finishAll(); }
  else if (m.type === "status") { setStatus(m.mode, m.text); if (m.caption !== undefined) $("caption").textContent = m.caption; }
  else if (m.type === "check") showCheck(m);
  else if (m.type === "check_done") hideCheck();
  else if (m.type === "end") { setStatus("done", "lesson finished"); hideCheck(); }
}
function connect() {
  ws = new WebSocket(`ws://${location.host}/ws?t=${encodeURIComponent(TOKEN || "")}`);
  ws.onopen = () => { retry = 300; setStatus("ready", "connected"); send({ type: "ready", w: viewport()[0], h: viewport()[1] }); };
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
