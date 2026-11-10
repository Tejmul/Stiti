"use client";
// Stiti chat client. One WebSocket to the local server; every message goes through the same Engine
// as voice/terminal, so this is the same Stiti with the same memory.
// Protocol (src/stiti/web/server.py): ← hello{name,llm,history,state} · → say{text} · ← thinking · ← delta{text}… ·
// ← reply{text,route,domain,provider,ms,used} · ← state{todos,alarms}
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import Nav from "@/components/Nav";
import { api, fmtDay, getToken, NotAllowed, wsUrl, type DayState, type Mind, type Reply } from "@/lib/stiti";
import Message, { type Msg } from "./Message";
import SidePanel, { type Brain } from "./SidePanel";
import type { MindHandle, MindState } from "./MindCanvas";

const SUGGEST = ["What's on my todo list?", "Remind me to drink water in 1 hour", "What did we talk about yesterday?",
                 "Add call mom to my todos"];
const EMPTY: DayState = { todos: [], alarms: [] };

type Hello = { type: "hello"; name: string | null; llm: boolean; history?: { who: "you" | "stiti"; text: string; ts: string }[]; state?: DayState };
type Incoming = Hello | { type: "thinking" } | { type: "delta"; text: string } | Reply | ({ type: "state" } & DayState);

export default function ChatApp() {
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [helloed, setHelloed] = useState(false);
  const [name, setName] = useState<string | null>(null);
  const [brain, setBrain] = useState<Brain>("connecting");
  const [mind, setMind] = useState<{ state: MindState; label: string }>({ state: "idle", label: "Waking up" });
  const [thinking, setThinking] = useState(false);
  const [busy, setBusy] = useState(false);
  const [suggest, setSuggest] = useState(false);
  const [gate, setGate] = useState(false);
  const [day, setDay] = useState<DayState>(EMPTY);
  const [knows, setKnows] = useState<Mind | null>(null);
  const [sideOpen, setSideOpen] = useState(false);
  const [text, setText] = useState("");

  const ws = useRef<WebSocket | null>(null);
  const log = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLTextAreaElement>(null);
  const mindRef = useRef<MindHandle>(null);
  const nextId = useRef(1);
  const streamId = useRef<number | null>(null);
  const jump = useRef(true);                         // next scroll is instant (history load)
  const knowsTimer = useRef<ReturnType<typeof setTimeout>>(undefined);
  const doneTimer = useRef<ReturnType<typeof setTimeout>>(undefined);

  // ------------------------------------------------------------------ what she knows (side card)
  const loadKnows = useCallback((delay = 0) => {
    clearTimeout(knowsTimer.current);
    knowsTimer.current = setTimeout(() => { api<Mind>("/api/mind").then(setKnows).catch(() => {}); }, delay);
  }, []);

  // ------------------------------------------------------------------ socket
  useEffect(() => {
    let alive = true, retry = 400, timer: ReturnType<typeof setTimeout> | undefined;

    const handle = (m: Incoming) => {
      if (m.type === "hello") {
        streamId.current = null;
        jump.current = true;
        setName(m.name);
        setBrain(m.llm ? "on" : "off");
        setMsgs((m.history || []).map((h) => ({ id: nextId.current++, who: h.who, text: h.text, at: new Date(h.ts), animate: false })));
        setHelloed(true);
        setSuggest(true);
        setThinking(false);
        setBusy(false);
        setDay(m.state || EMPTY);
        setMind(m.llm ? { state: "idle", label: "Here for you" } : { state: "offline", label: "Here · offline brain" });
      } else if (m.type === "thinking") {
        setThinking(true);
        setMind({ state: "thinking", label: "Thinking" });
      } else if (m.type === "delta") {                 // reply streaming in while she writes it
        mindRef.current?.pulse(0.3);
        if (streamId.current == null) {
          const id = (streamId.current = nextId.current++);
          setThinking(false);
          setMind({ state: "talking", label: "Talking" });
          setMsgs((l) => [...l, { id, who: "stiti", text: m.text, at: new Date(), animate: true, streaming: true }]);
        } else {
          const id = streamId.current;
          setMsgs((l) => l.map((x) => (x.id === id ? { ...x, text: x.text + m.text } : x)));
        }
      } else if (m.type === "reply") {
        const sid = streamId.current;
        streamId.current = null;
        const fin: Omit<Msg, "id"> = { who: "stiti", text: m.text || "", at: new Date(), animate: true, reply: m, wordFade: sid == null };
        // a streamed reply keeps its element (no second entrance), the final text just replaces the draft
        setMsgs((l) => (sid != null ? l.map((x) => (x.id === sid ? { ...fin, id: sid } : x)) : [...l, { ...fin, id: nextId.current++ }]));
        setThinking(false);
        setBusy(false);
        mindRef.current?.pulse(1);
        const fast = m.route === "fast_path";
        setMind({ state: "idle", label: fast ? "Done" : "Here for you" });
        clearTimeout(doneTimer.current);
        if (fast) doneTimer.current = setTimeout(() => setMind((s) => (s.label === "Done" ? { ...s, label: "Here for you" } : s)), 2500);
        loadKnows(1500);
        input.current?.focus();
      } else if (m.type === "state") {
        setDay({ todos: m.todos || [], alarms: m.alarms || [] });
      }
    };

    const connect = () => {
      if (!alive) return;
      if (!getToken()) {
        setGate(true);
        setMind({ state: "offline", label: "Not connected" });
        return;
      }
      const s = (ws.current = new WebSocket(wsUrl()));
      let opened = false;
      s.onopen = () => { opened = true; retry = 400; setGate(false); };
      s.onmessage = (e) => { try { handle(JSON.parse(e.data)); } catch { /* ignore a bad frame */ } };
      s.onclose = (e) => {
        if (!alive) return;
        streamId.current = null;
        setThinking(false);
        setBusy(false);
        const notLinked = () => { setGate(true); setMind({ state: "offline", label: "Not connected" }); };
        if (e.code === 4403) return notLinked();
        setMind({ state: "offline", label: "Reconnecting…" });
        setBrain("lost");
        const again = () => { if (alive) timer = setTimeout(connect, (retry = Math.min(retry * 2, 6000))); };
        // a refused handshake (wrong/old key) arrives as 1006, not 4403: ask the API before retrying forever
        if (opened) again();
        else api("/api/state").then(again, (err) => (err instanceof NotAllowed ? alive && notLinked() : again()));
      };
    };

    timer = setTimeout(connect, 0);
    loadKnows();
    return () => {
      alive = false;
      clearTimeout(timer);
      clearTimeout(knowsTimer.current);
      clearTimeout(doneTimer.current);
      const s = ws.current;
      ws.current = null;
      if (s) { s.onclose = null; s.onmessage = null; s.close(); }
    };
  }, [loadKnows]);

  // ------------------------------------------------------------------ scroll to the newest line
  useLayoutEffect(() => {
    const el = log.current;
    if (!el) return;
    el.scrollTo({ top: el.scrollHeight, behavior: jump.current ? "instant" : "smooth" });
    if (helloed) jump.current = false;
  }, [msgs, thinking, helloed]);

  // ------------------------------------------------------------------ mobile sheet
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setSideOpen(false);
    addEventListener("keydown", onKey);
    return () => removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => { input.current?.focus(); }, []);

  // ------------------------------------------------------------------ talking
  const autosize = () => {
    const el = input.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 180) + "px";
  };

  const say = (raw: string) => {
    const t = raw.trim();
    if (!t || busy || ws.current?.readyState !== WebSocket.OPEN) return;
    setSuggest(false);
    setMsgs((l) => [...l, { id: nextId.current++, who: "you", text: t, at: new Date(), animate: true }]);
    ws.current.send(JSON.stringify({ type: "say", text: t }));
    setBusy(true);
    setText("");
    requestAnimationFrame(autosize);
  };

  const done = async (id: number) => {
    const t0 = performance.now();
    try {
      const st = await api<DayState>(`/api/todo/${id}/done`, { method: "POST" });
      // let the tick draw and the row fold before the list re-renders
      setTimeout(() => setDay(st), Math.max(0, 860 - (performance.now() - t0)));
      return true;
    } catch {
      return false;
    }
  };

  // ------------------------------------------------------------------ render
  const nTodos = day.todos.length;
  const todayBtn = (
    <button className="nav__cta today-btn" type="button" aria-controls="side" aria-expanded={sideOpen}
      onClick={() => setSideOpen((o) => !o)}>
      Today{nTodos > 0 && <span className="nav__count">{nTodos}</span>}
    </button>
  );

  const days = msgs.map((m) => fmtDay(m.at));
  return (
    <div className="pg-chat">
      <Nav current="chat" cta={todayBtn} />
      <main className="chat" id="main">
        <SidePanel name={name} brain={brain} mindState={mind.state} mindLabel={mind.label} mindRef={mindRef}
          day={day} knows={knows} open={sideOpen} onClose={() => setSideOpen(false)} onDone={done} />

        <section className="thread" aria-label="Conversation">
          <div className="log" ref={log} role="log" aria-live="polite" aria-relevant="additions">
            <div className="log__in">
            {helloed && msgs.length === 0 && (
              <div className="welcome">
                <p className="label">Your local AI buddy</p>
                <h2><span className="thin">Hey{name ? " " + name : ""}.</span><br /><span className="bold">What&apos;s on your mind?</span></h2>
                <p>Ask about anything you&apos;ve told her before, or let her handle todos, alarms and reminders. Everything you say stays on this Mac.</p>
              </div>
            )}
            {msgs.map((m, i) => (
              <div key={m.id} className="turn">
                {days[i] !== days[i - 1] && <div className="day label">{days[i]}</div>}
                <Message m={m} />
              </div>
            ))}
            {thinking && (
              <div className="thinking" role="status">
                <span aria-hidden="true"><i /> <i /> <i /></span> thinking
              </div>
            )}
            </div>
          </div>

          <div className="composer-wrap">
            {suggest && (
              <div className="suggest" aria-label="Things to try">
                {SUGGEST.map((s, i) => (
                  <button key={s} type="button" style={{ animationDelay: `${i * 60}ms` }} onClick={() => say(s)}>{s}</button>
                ))}
              </div>
            )}
            <form className="composer" autoComplete="off" onSubmit={(e) => { e.preventDefault(); say(text); }}>
              <label className="sr-only" htmlFor="composer-input">Message Stiti</label>
              <textarea id="composer-input" ref={input} rows={1} value={text} enterKeyHint="send"
                placeholder="Message Stiti… English, Hindi, Hinglish"
                onChange={(e) => { setText(e.target.value); autosize(); }}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); say(text); }
                }} />
              <button className="send" type="submit" aria-label="Send" disabled={busy || !text.trim()}>
                <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
                  <path d="M5 12h13M13 6l6 6-6 6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </button>
            </form>
            <p className="composer-hint label">Enter to send · Shift+Enter for a new line · voice: <code>uv run stiti voice</code></p>
          </div>
        </section>
      </main>

      {gate && (
        <div className="gate" role="dialog" aria-modal="true" aria-labelledby="gate-h">
          <div className="gate__card">
            <p className="label">Not connected</p>
            <h2 id="gate-h"><span className="thin">Open Stiti from</span> <span className="bold">your terminal.</span></h2>
            <p>This browser hasn&apos;t been linked yet. Run <code>uv run stiti web</code> and open the link it prints — it contains a one-time key so only you can talk to her.</p>
          </div>
        </div>
      )}
    </div>
  );
}
