"use client";
/* eslint-disable @typescript-eslint/no-explicit-any */
// Stiti's whiteboard tutor page (/board), served by the tutor's board server (127.0.0.1:7318) — never by the public
// site. Python owns the lesson, layout and audio; this page draws (live, pen-like), moves the camera, shows her
// captions + status, and sends back controls, typed answers, "explain this" clicks and hold-to-talk.
// WebSocket protocol (same as the plain-JS fallback board):
//   in:  cue · reset · actions · status · check · check_done · speed · end · pause
//   out: ready{w,h} · control{cmd} · text{text} · hand · click{id} · ptt{down} · ptt_mode{on} · error
import dynamic from "next/dynamic";
import { useCallback, useEffect, useRef, useState } from "react";
import Icon from "./icons";
import "./board.css";                   // here, not in the route: the public build never ships the board's styles
import { createRuntime, type Action, type Runtime } from "./runtime";

declare global { interface Window { EXCALIDRAW_ASSET_PATH?: string | string[]; stitiBoard?: unknown } }
if (typeof window !== "undefined") {
  window.EXCALIDRAW_ASSET_PATH = "/excalidraw/";
  // Excalidraw always appends an esm.sh copy to each font's src list. The CSP blocks it anyway (fonts load from this
  // Mac), but every blocked URL logs an error, ~230 per load — so drop the CDN entry before Excalidraw builds its fonts.
  const Orig = window.FontFace;
  if (Orig && !(Orig as any).__stiti) {
    const Patched = function (family: string, source: string | BufferSource, desc?: FontFaceDescriptors) {
      if (typeof source === "string" && source.includes("https://esm.sh/")) {
        source = source.split(/,\s*(?=url\()/).filter((s) => !s.includes("https://esm.sh/")).join(", ") || source;
      }
      return new Orig(family, source, desc);
    } as unknown as typeof FontFace;
    Patched.prototype = Orig.prototype;
    (Patched as any).__stiti = true;
    window.FontFace = Patched;
  }
}

const Canvas = dynamic(() => import("./Canvas"), { ssr: false });

const HOLD_MS = 250;              // Space / mic held this long = hold-to-talk; shorter = tap
const PH_IDLE = "Type a doubt or an answer";
type Status = { mode: string; text: string };
type Check = { kind: string; prompt: string; options: string[] };
type Progress = { lesson: string; segment: string; part: string; pct: number | null };

function readToken(): string {
  let t = new URLSearchParams(location.hash.slice(1)).get("t");
  try { if (t) sessionStorage.setItem("stiti_t", t); else t = sessionStorage.getItem("stiti_t"); } catch {}
  history.replaceState(null, "", location.pathname);          // the secret never stays in the address bar
  return t || "";
}

export default function BoardApp() {
  const [loading, setLoading] = useState(true);
  const [status, setStatusState] = useState<Status>({ mode: "", text: "connecting" });
  const [caption, setCaption] = useState("");
  const [speed, setSpeed] = useState("1.0×");
  const [prog, setProg] = useState<Progress>({ lesson: "", segment: "", part: "", pct: null });
  const [check, setCheck] = useState<Check | null>(null);
  const [chip, setChip] = useState<string | null>(null);
  const [clean, setClean] = useState(true);             // Excalidraw's own toolbar hidden (D shows it)
  const [presenting, setPresenting] = useState(false);
  const [pttMode, setPttModeState] = useState(false);
  const [talking, setTalking] = useState(false);
  const [placeholder, setPlaceholder] = useState(PH_IDLE);

  const rootRef = useRef<HTMLDivElement>(null);
  const boardRef = useRef<HTMLDivElement>(null);
  const dockRef = useRef<HTMLDivElement>(null);
  const checkRef = useRef<HTMLDivElement>(null);
  const penRef = useRef<HTMLDivElement>(null);
  const qRef = useRef<HTMLInputElement>(null);
  const rt = useRef<Runtime | null>(null);
  const ws = useRef<WebSocket | null>(null);
  const queue = useRef<any[]>([]);                      // messages that arrive before the canvas is ready
  const st = useRef({ clean: true, presenting: false, pttMode: false, talking: false, paused: false, selected: null as string | null,
                      autoFocus: false, beforeTalk: null as Status | null, status: { mode: "", text: "connecting" } as Status });

  const send = useCallback((m: object) => { if (ws.current?.readyState === 1) ws.current.send(JSON.stringify(m)); }, []);

  const setStatus = useCallback((mode: string, text: string) => {
    const s = { mode: mode || "", text: text || mode || "" };
    st.current.status = s;
    st.current.paused = s.mode === "paused";
    setStatusState(s);
  }, []);

  // "Lexer basics · part 3 of 9" → header title + progress bar
  const setProgress = useCallback((p?: string, lesson?: string) => {
    const m = /^(.*?)\s*·\s*part\s+(\d+)\s+of\s+(\d+)\s*$/i.exec(p || "");
    setProg((old) => {
      const next = { ...old, lesson: lesson || old.lesson };
      if (!m) return p ? { ...next, segment: p } : next;
      const [, seg, n, of] = m;
      document.title = `${seg} · Stiti`;
      return { ...next, segment: seg, part: `part ${n} of ${of}`, pct: Math.round((100 * +n) / Math.max(1, +of)) };
    });
  }, []);

  // ---------------------------------------------------------------- incoming messages
  const handle = useCallback(async (m: any) => {
    const r = rt.current;
    if (!r) { queue.current.push(m); return; }
    if (m.type === "cue") {
      r.clearPending(); r.finishAll();
      setCaption(m.say || "");
      if (m.progress || m.lesson) setProgress(m.progress, m.lesson);
      r.schedule(m.actions as Action[]);
    } else if (m.type === "reset") {
      r.clearPending(); r.finishAll(); r.reset();
      await r.replay(m.actions as Action[]);
    } else if (m.type === "actions") {                  // live answers / parking lot: run now, in order
      r.schedule(m.actions as Action[]);
    } else if (m.type === "pause") { r.clearPending(); r.finishAll(); }
    else if (m.type === "status") { setStatus(m.mode, m.text); if (m.caption !== undefined) setCaption(m.caption); }
    else if (m.type === "speed") setSpeed(`${Number(m.value).toFixed(1)}×`);
    else if (m.type === "check") {
      setCheck({ kind: m.kind_label || "Your turn", prompt: m.prompt, options: m.options || [] });
      setPlaceholder(m.options?.length ? "Pick an option, or type it…" : "Type your answer, or say it…");
    } else if (m.type === "check_done") { setCheck(null); setPlaceholder(PH_IDLE); }
    else if (m.type === "end") { setStatus("done", "lesson finished"); setCheck(null); setPlaceholder(PH_IDLE); }
  }, [setProgress, setStatus]);

  // ---------------------------------------------------------------- socket
  useEffect(() => {
    const token = readToken();
    let retry = 300, alive = true, timer: ReturnType<typeof setTimeout> | undefined;
    const connect = () => {
      const sock = new WebSocket(`ws://${location.host}/ws?t=${encodeURIComponent(token)}`);
      ws.current = sock;
      sock.onopen = () => {
        retry = 300;
        setStatus("ready", "connected");
        const b = boardRef.current;
        send({ type: "ready", w: b?.clientWidth || innerWidth, h: b?.clientHeight || innerHeight });
        if (st.current.pttMode) send({ type: "ptt_mode", on: true });   // a reconnect keeps his hold-to-talk choice
      };
      sock.onmessage = (ev) => { try { handle(JSON.parse(ev.data)); } catch {} };
      sock.onclose = (ev) => {
        if (!alive) return;
        if (ev.code === 4403) return setStatus("offline", "not allowed (open the link Stiti gave you)");
        setStatus("offline", "reconnecting…");
        timer = setTimeout(connect, (retry = Math.min(retry * 2, 5000)));
      };
    };
    connect();
    return () => { alive = false; clearTimeout(timer); ws.current?.close(); };
  }, [handle, send, setStatus]);

  // ---------------------------------------------------------------- canvas ready
  const onReady = useCallback(async (api: any, lib: any) => {
    if (rt.current) return;
    while (api.getAppState().isLoading) await new Promise((r) => setTimeout(r, 50));
    // Fonts: text measured with a fallback font gets clipped once the real font arrives, so load them first.
    await Promise.race([
      Promise.all(["20px Excalifont", '20px "Comic Shanns"', "20px Assistant", "20px Nunito"]
        .map((f) => document.fonts.load(f, "Aa1→✓").catch(() => null))),
      new Promise((r) => setTimeout(r, 4000)),
    ]);
    const reduced = matchMedia("(prefers-reduced-motion: reduce)");
    const r = createRuntime({
      api, lib, send,
      board: () => boardRef.current, check: () => checkRef.current, pen: () => penRef.current,
      toolbarShown: () => !st.current.clean && !st.current.presenting,
      reduced: () => reduced.matches,
    });
    rt.current = r;
    window.stitiBoard = { api, lib, run: r.run, scene: r.scene };   // for tests / debugging
    document.fonts.addEventListener?.("loadingdone", () => setTimeout(() => r.remeasure(), 50));
    setLoading(false);
    const q = queue.current; queue.current = [];
    for (const m of q) await handle(m);
  }, [handle, send]);

  const onChange = useCallback((appState: { selectedElementIds?: Record<string, boolean> }) => {
    const r = rt.current;
    if (!r) return;
    const sel = appState.selectedElementIds || {};
    const ids = Object.keys(sel).filter((k) => sel[k]);
    const id = ids.length === 1 ? ids[0] : null;
    if (id === st.current.selected) return;
    st.current.selected = id;
    const els = r.scene();
    const el = id && els.find((e: any) => e.id === id);
    const label = el && (el.text || els.find((t: any) => t.containerId === id)?.text);
    setChip(label ? `Explain “${String(label).replace(/\s+/g, " ").slice(0, 28)}”` : null);
  }, []);

  // ---------------------------------------------------------------- layout observers
  useEffect(() => {
    const dock = dockRef.current, board = boardRef.current, root = rootRef.current;
    if (!dock || !board || !root) return;
    // floating cards sit just above the dock, whatever its height (caption lines, phone wrap, presenter mode)
    const ro1 = new ResizeObserver(([e]) => root.style.setProperty("--dock-h", `${Math.round(e.borderBoxSize?.[0]?.blockSize ?? dock.offsetHeight)}px`));
    ro1.observe(dock);
    let h = 0;                    // the board grows / shrinks with the dock: keep the drawing framed
    const ro2 = new ResizeObserver(() => { if (board.clientHeight !== h) { h = board.clientHeight; rt.current?.reframe(); } });
    ro2.observe(board);
    const onResize = () => rt.current?.reframeNow();
    addEventListener("resize", onResize);
    return () => { ro1.disconnect(); ro2.disconnect(); removeEventListener("resize", onResize); };
  }, []);

  // the check card: focus the answer box (not a raised hand) and slide the drawing into the space beside the card
  const hadCheck = useRef(false);
  useEffect(() => {
    if (check) {
      st.current.autoFocus = true; qRef.current?.focus(); st.current.autoFocus = false;
      rt.current?.refit();
    } else if (hadCheck.current) rt.current?.refit();
    hadCheck.current = !!check;
  }, [check]);

  // ---------------------------------------------------------------- controls
  const control = useCallback((cmd: string) => send({ type: "control", cmd }), [send]);
  const toggleDraw = useCallback(() => {
    st.current.clean = !st.current.clean;
    setClean(st.current.clean);
    setTimeout(() => rt.current?.reframeNow(), 50);
  }, []);
  const present = useCallback(() => {
    const on = !st.current.presenting;
    st.current.presenting = on;
    setPresenting(on);
    try { if (on) document.documentElement.requestFullscreen?.()?.catch(() => {}); else if (document.fullscreenElement) document.exitFullscreen?.(); } catch {}
    setTimeout(() => rt.current?.reframeNow(), 300);
  }, []);
  useEffect(() => {
    const onFs = () => {
      if (!document.fullscreenElement && st.current.presenting) { st.current.presenting = false; setPresenting(false); }
      setTimeout(() => rt.current?.reframeNow(), 300);
    };
    document.addEventListener("fullscreenchange", onFs);
    return () => document.removeEventListener("fullscreenchange", onFs);
  }, []);

  // Hold-to-talk (so voices in his room aren't taken as his answers): hold Space ≥ 250 ms, or press and hold the
  // mic, and only that speech counts. A quick Space tap stays pause / play; a click on the mic toggles the mode.
  const ptt = useCallback((down: boolean) => {
    if (down === st.current.talking) return;
    st.current.talking = down;
    setTalking(down);
    send({ type: "ptt", down });
    if (down) { st.current.beforeTalk = st.current.status; setStatus("talking", "listening — release to send"); }
    else if (st.current.status.mode === "talking" && st.current.beforeTalk) {
      setStatus(st.current.beforeTalk.mode, st.current.beforeTalk.text);       // unless the engine said something new
    }
  }, [send, setStatus]);
  const setPttMode = useCallback((on: boolean) => {
    st.current.pttMode = on;
    setPttModeState(on);
    send({ type: "ptt_mode", on });
  }, [send]);

  useEffect(() => {
    let spaceTimer: ReturnType<typeof setTimeout> | 0 = 0, spaceDown = false;
    const typing = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement;
      return t?.tagName === "INPUT" || t?.tagName === "TEXTAREA" || !!t?.closest?.(".excalidraw textarea");
    };
    const down = (e: KeyboardEvent) => {
      if (typing(e)) return;
      if (e.key === " ") {
        e.preventDefault();
        if (e.repeat || spaceDown) return;        // key repeat: still the same hold
        spaceDown = true;
        spaceTimer = setTimeout(() => { spaceTimer = 0; ptt(true); }, HOLD_MS);
        return;
      }
      const map: Record<string, string> = { ArrowLeft: "back", ArrowRight: "next", r: "repeat", R: "repeat" };
      if (map[e.key]) { e.preventDefault(); control(map[e.key]); }
      if (e.key === "h" || e.key === "H") { e.preventDefault(); qRef.current?.focus(); }
      if (e.key === "f" || e.key === "F") { e.preventDefault(); present(); }
      if ((e.key === "d" || e.key === "D") && !e.metaKey && !e.ctrlKey) { e.preventDefault(); toggleDraw(); }
    };
    const up = (e: KeyboardEvent) => {
      if (e.key !== " " || !spaceDown) return;
      e.preventDefault();
      spaceDown = false;
      if (spaceTimer) { clearTimeout(spaceTimer); spaceTimer = 0; control(st.current.paused ? "play" : "pause"); }
      else ptt(false);
    };
    const blur = () => { if (spaceTimer) clearTimeout(spaceTimer); spaceTimer = 0; spaceDown = false; ptt(false); };
    addEventListener("keydown", down);
    addEventListener("keyup", up);
    addEventListener("blur", blur);
    return () => { removeEventListener("keydown", down); removeEventListener("keyup", up); removeEventListener("blur", blur); };
  }, [control, present, ptt, toggleDraw]);

  const mic = useRef({ timer: 0 as ReturnType<typeof setTimeout> | 0, held: false, eatClick: false });
  const micDown = (e: React.PointerEvent<HTMLButtonElement>) => {
    if (e.button !== 0) return;
    e.currentTarget.setPointerCapture?.(e.pointerId);
    mic.current.held = true;
    mic.current.timer = setTimeout(() => { mic.current.timer = 0; ptt(true); }, HOLD_MS);
  };
  const micUp = () => {
    const m = mic.current;
    if (!m.held) return;
    m.held = false;
    if (m.timer) { clearTimeout(m.timer); m.timer = 0; return; }   // a short press: the click toggles the mode
    m.eatClick = true;                                             // a hold: the click that follows is not a toggle
    ptt(false);
  };
  const micClick = () => { if (mic.current.eatClick) { mic.current.eatClick = false; return; } setPttMode(!st.current.pttMode); };

  const onAsk = (e: React.FormEvent) => {
    e.preventDefault();
    const t = qRef.current?.value.trim();
    if (t) send({ type: "text", text: t });
    if (qRef.current) qRef.current.value = "";
  };

  const paused = status.mode === "paused";
  const rootCls = ["sb", clean ? "clean" : "", presenting ? "presenting" : ""].filter(Boolean).join(" ");
  return (
    <div className={rootCls} ref={rootRef}>
      <header id="head">
        <div id="brand"><span id="mark" aria-hidden="true" />Stiti</div>
        <div id="where">
          <div id="lesson">{prog.lesson}</div>
          <div id="segment">{prog.segment}</div>
        </div>
        <div id="meter" aria-live="off" hidden={prog.pct === null}>
          <span id="part">{prog.part}</span>
          <div id="track"><div id="fill" style={{ width: `${prog.pct ?? 0}%` }} /></div>
        </div>
      </header>

      <div id="board" ref={boardRef}>
        {loading && <div id="loading">Stiti is getting the whiteboard ready…</div>}
        <Canvas onReady={onReady} onChange={onChange} />
      </div>

      <div id="check" ref={checkRef} hidden={!check}>
        <div id="check-kind">{check?.kind}</div>
        <div id="check-prompt">{check?.prompt}</div>
        <div id="check-options">
          {check?.options.map((o, i) => (
            <button key={i} type="button" onClick={() => send({ type: "text", text: "ABCD"[i] })}>{`${"ABCD"[i]}. ${o}`}</button>
          ))}
        </div>
      </div>
      <button id="ask-chip" type="button" hidden={!chip}
        onClick={() => st.current.selected && send({ type: "click", id: st.current.selected })}>{chip}</button>

      <div id="pen" ref={penRef} aria-hidden="true" />

      <div id="dock" ref={dockRef}>
        <div id="say">
          <span id="status" className={`pill ${status.mode}`} title={status.text}>
            <i className="dot" aria-hidden="true" /><span id="status-text">{status.text}</span>
          </span>
          <div id="caption" aria-live="polite">{caption}</div>
        </div>
        <div id="controls">
          <div className="group transport" role="group" aria-label="Lesson">
            <button type="button" onClick={() => control("back")} title="Go back (←)" aria-label="Go back"><Icon name="back" /></button>
            <button type="button" id="pp" className="main" onClick={() => control(paused ? "play" : "pause")}
              title="Pause / play (space)" aria-label={paused ? "Play" : "Pause"}><Icon name={paused ? "play" : "pause"} /></button>
            <button type="button" onClick={() => control("next")} title="Skip to next part (→)" aria-label="Skip to next part"><Icon name="next" /></button>
            <button type="button" onClick={() => control("repeat")} title="Say that again (R)" aria-label="Say that again"><Icon name="repeat" /></button>
          </div>
          <div className="group talk" role="group" aria-label="Talk">
            <button type="button" id="mic" className={talking ? "talking" : ""} aria-pressed={pttMode} aria-label="Hold-to-talk mode"
              title={pttMode ? "Hold-to-talk is on: hold this (or Space) while you speak · click to turn off"
                             : "Hold to talk (or hold Space) · click: only listen while held"}
              onPointerDown={micDown} onPointerUp={micUp} onPointerCancel={micUp} onClick={micClick}
              onContextMenu={(e) => e.preventDefault()}><Icon name="mic" /></button>
          </div>
          <form id="ask" onSubmit={onAsk}>
            <input id="q" ref={qRef} autoComplete="off" placeholder={placeholder} aria-label="Ask a doubt or type your answer"
              onFocus={() => { if (!st.current.autoFocus) send({ type: "hand" }); }} />
            <kbd aria-hidden="true">H</kbd>
            <button type="submit" aria-label="Send"><Icon name="send" /></button>
          </form>
          <div className="group speed" role="group" aria-label="Talking speed">
            <button type="button" onClick={() => control("slower")} title="Talk slower" aria-label="Talk slower"><Icon name="slow" /></button>
            <span className="lbl" id="speed" title="Her talking speed" aria-live="polite">{speed}</span>
            <button type="button" onClick={() => control("faster")} title="Talk faster" aria-label="Talk faster"><Icon name="fast" /></button>
          </div>
          <div className="group view" role="group" aria-label="View">
            <button type="button" id="draw" onClick={toggleDraw} aria-pressed={!clean} aria-label="Show drawing tools"
              title={clean ? "Show drawing tools (D)" : "Hide drawing tools (D)"}><Icon name="pen" /></button>
            <button type="button" id="fs" onClick={(e) => { e.stopPropagation(); present(); }}
              title="Presenter mode for a big screen (F)" aria-label="Presenter mode"><Icon name="full" /></button>
          </div>
        </div>
      </div>
    </div>
  );
}
