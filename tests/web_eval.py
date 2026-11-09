"""Web app eval: security checks + a real chat turn through the Engine (no browser, no port).

STITI_DB=postgresql:///stiti_test STITI_HOME=<tmp> uv run python tests/web_eval.py
"""
from __future__ import annotations

from starlette.testclient import TestClient

from stiti.web import server

ok = fail = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global ok, fail
    ok += cond
    fail += not cond
    print(f"{'✅' if cond else '❌'} {name}" + (f" — {detail}" if detail and not cond else ""))


base = f"http://127.0.0.1:{server.PORT}"
host = {"host": f"127.0.0.1:{server.PORT}"}
origin = {"origin": base, **host}
tok = server.web_token()
c = TestClient(server.app(), base_url=base)

check("landing + chat pages served", c.get("/chat").status_code == 200 and "Message Stiti" in c.get("/chat").text)
check("Host check blocks DNS rebinding", c.get("/chat", headers={"host": "evil.example"}).status_code == 400)
check("static assets served", c.get("/static/css/base.css").status_code == 200)
check("pictogram icons: numbers only", c.get("/icons/180.png").status_code in (200, 404)
      and c.get("/icons/..%2F..%2Fsecret.png").status_code == 404)
check("API needs the token", c.get("/api/state").status_code == 403 and c.get(f"/api/state?t={tok}").status_code == 200)

refused = False
try:
    with c.websocket_connect(f"/ws?t={tok}", headers={"origin": "http://evil.example", **host}) as ws:
        ws.receive_json()
except Exception:
    refused = True
check("WebSocket refuses a foreign Origin", refused)
refused = False
try:
    with c.websocket_connect("/ws?t=wrong", headers=origin) as ws:
        ws.receive_json()
except Exception:
    refused = True
check("WebSocket refuses a wrong token", refused)

with c.websocket_connect(f"/ws?t={tok}", headers=origin) as ws:
    hello = ws.receive_json()
    check("hello carries history, state and brain status", hello["type"] == "hello" and "history" in hello
          and "todos" in hello["state"] and isinstance(hello["llm"], bool))
    ws.send_json({"type": "say", "text": "add water the plants to my todos"})
    assert ws.receive_json()["type"] == "thinking"
    r = ws.receive_json()
    st = ws.receive_json()
    check("chat turn runs through the Engine fast path", r["type"] == "reply" and r["route"] == "fast_path"
          and "water the plants" in r["text"], str(r)[:200])
    titles = [t["title"] for t in st["todos"]]
    check("state push shows the new todo", st["type"] == "state" and "water the plants" in titles, str(titles))
    tid = next(t["id"] for t in st["todos"] if t["title"] == "water the plants")

check("todo done needs same-origin + token",
      c.post(f"/api/todo/{tid}/done", headers={"x-stiti-token": tok}).status_code == 403)
after = c.post(f"/api/todo/{tid}/done", headers={"x-stiti-token": tok, **origin}).json()
check("todo done from the side panel", all(t["id"] != tid for t in after["todos"]))

print(f"web: {ok}/{ok + fail} checks passed")
raise SystemExit(1 if fail else 0)
