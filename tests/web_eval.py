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

built = (server.OUT / "chat.html").exists()          # Next.js export (cd frontend && pnpm build)
pages = {p: c.get(p) for p in ("/", "/chat", "/memory")}
check("landing, chat and memory pages served (or a clear 'not built' message)",
      all(r.status_code == 200 and "<html" in r.text for r in pages.values()) if built
      else all(r.status_code == 503 and "pnpm build" in r.text for r in pages.values()))
check("Host check blocks DNS rebinding", c.get("/chat", headers={"host": "evil.example"}).status_code == 400)
if built:
    check("Next.js assets served", c.get("/favicon.svg").status_code == 200 and c.get(
        next(a for a in __import__("re").findall(r'/_next/static/[^"]+\.js', pages["/chat"].text))).status_code == 200)
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
          and "water the plants" in r["text"] and "used" in r, str(r)[:200])
    titles = [t["title"] for t in st["todos"]]
    check("state push shows the new todo", st["type"] == "state" and "water the plants" in titles, str(titles))
    tid = next(t["id"] for t in st["todos"] if t["title"] == "water the plants")

check("todo done needs same-origin + token",
      c.post(f"/api/todo/{tid}/done", headers={"x-stiti-token": tok}).status_code == 403)
after = c.post(f"/api/todo/{tid}/done", headers={"x-stiti-token": tok, **origin}).json()
check("todo done from the side panel", all(t["id"] != tid for t in after["todos"]))

# ---- auto-link: Stiti's own pages get the key; other sites can't
same = {"sec-fetch-site": "same-origin", **host}
check("own page gets the key without the terminal link", c.get("/api/link", headers=same).json().get("t") == tok)
check("other websites and non-browser calls can't get the key",
      c.get("/api/link", headers={"sec-fetch-site": "cross-site", **host}).status_code == 403
      and c.get("/api/link", headers=host).status_code == 403
      and c.get("/api/link", headers={"sec-fetch-site": "same-origin", "host": "evil.example"}).status_code in (400, 403))

# ---- Memory page API (D23)
check("memory API needs the token", c.get("/api/mind").status_code == 403)
mind = c.get("/api/mind", headers={"x-stiti-token": tok}).json()
check("memory overview has every section", all(k in mind for k in (
    "facts", "people", "directives", "lessons", "habits", "mood", "docs", "todos", "alarms", "counts")) and len(mind["mood"]) == 14)
check("adding a fact needs same-origin + token",
      c.post("/api/fact", json={"text": "I love filter coffee"}, headers={"x-stiti-token": tok}).status_code == 403)
check("too-short fact refused", c.post("/api/fact", json={"text": "a"}, headers={"x-stiti-token": tok, **origin}).status_code == 400)
new = c.post("/api/fact", json={"text": "I love filter coffee"}, headers={"x-stiti-token": tok, **origin}).json()
mind = c.get("/api/mind", headers={"x-stiti-token": tok}).json()
from stiti.config import CFG  # noqa: E402
check("added fact shows up (and in USER.md)", any(f["id"] == new["id"] for f in mind["facts"])
      and "I love filter coffee" in (CFG.home / "USER.md").read_text())
c.post(f"/api/fact/{new['id']}/forget", headers={"x-stiti-token": tok, **origin})
mind = c.get("/api/mind", headers={"x-stiti-token": tok}).json()
check("forgotten fact is gone (kept in history)", all(f["id"] != new["id"] for f in mind["facts"])
      and "filter coffee" not in (CFG.home / "USER.md").read_text())
hits = c.get("/api/moments?q=plants", headers={"x-stiti-token": tok}).json()
check("conversation search finds earlier messages", any("plants" in m["text"] for m in hits), str(hits)[:200])

print(f"web: {ok}/{ok + fail} checks passed")
raise SystemExit(1 if fail else 0)
