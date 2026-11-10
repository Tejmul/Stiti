"""Conversation-speed pieces: clause chunking, streaming lint, goodbye vs hush, zero-cost guard, streamed
web chat. No mic, no speaker. The streamed-chat check runs only when an LLM key is configured."""
from __future__ import annotations

import os
import sys
import tempfile

passed = total = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global passed, total
    total += 1
    passed += bool(cond)
    print(("  ✓ " if cond else "  ✗ ") + name + (f" — {detail}" if detail and not cond else ""))


from stiti import router                                          # noqa: E402
from stiti.brain.psych import StreamLint                          # noqa: E402
from stiti.farewell import farewell                               # noqa: E402
from stiti.voice.tts import ClauseChunker                         # noqa: E402
from stiti.voice.wake import is_goodbye, is_stop                  # noqa: E402


def chunk(text: str, step: int = 3) -> list[str]:
    c, out = ClauseChunker(), []
    for i in range(0, len(text), step):
        out += c.feed(text[i:i + step])
    return out + c.flush()


p = chunk("Honestly? Just lie down and do nothing. No screens, no planning tonight.")
check("first piece is short (starts talking early)", p[0] == "Honestly?", str(p))
check("later pieces are whole sentences", p[1:] == ["Just lie down and do nothing.", "No screens, no planning tonight."], str(p))
p = chunk("\n\n**Tip:** close the laptop and go for a short walk tonight because fresh air helps a lot.")
check("leading newline/markdown doesn't use up the short first piece", len(p[0].split()) <= 8, str(p))
p = chunk("That sounds really draining so please give yourself permission to rest tonight")
check("no punctuation: first piece cut at ~7 words", len(p[0].split()) <= 7 and " ".join(p).endswith("tonight"), str(p))

lint = StreamLint()
said = [lint.feed(x) for x in ["You should have slept.", "Want tea?", "Or music?", "- a", "- b", "- c", "- d"]]
check("stream lint: guilt words softened", "should have" not in said[0], said[0])
check("stream lint: only one question", said[1].endswith("?") and said[2].endswith("."), str(said[1:3]))
check("stream lint: max 3 list items spoken", said[3:6] == ["- a", "- b", "- c"] and said[6] is None, str(said[3:]))

for t in ["bye", "bye stiti", "chalo bye", "good night", "okay bye", "Bye, Stiti."]:
    check(f"goodbye → she says bye back: {t!r}", is_goodbye(t) and is_stop(t))
for t in ["shut up", "stop", "chup", "bas karo"]:
    check(f"hush → silent stop: {t!r}", is_stop(t) and not is_goodbye(t))
f1, f2 = farewell("chalo bye"), farewell("chalo bye")
check("farewell is Hinglish when he spoke Hinglish, and not repeated back to back",
      f1 != f2 and any(w in (f1 + f2).lower() for w in ("chalo", "milte", "bula", "baad")), f"{f1} | {f2}")

check("zero-cost guard: OpenRouter non-:free blocked", not router.is_free("openrouter", "openai/gpt-5"))
check("zero-cost guard: paid Z.ai model blocked", not router.is_free("zai", "glm-5.3-flash"))
check("zero-cost guard: every chain entry is free",
      all(router.is_free(p, m) for ch in router.CHAINS.values() for p, m in ch + router.P0_EXTRA))
check("personal turns never reach public-only providers",
      all(router.PROVIDERS[p].max_privacy >= 1 for p, m in router.CHAINS["voice_fast"]
          if p not in ("nvidia", "gemini")))

if any(s["key"] for s in router.status()):
    os.environ.setdefault("STITI_HOME", tempfile.mkdtemp())
    from starlette.testclient import TestClient
    from stiti.web import server
    base = "http://127.0.0.1:7317"
    c = TestClient(server.app(), base_url=base)
    with c.websocket_connect(f"/ws?t={server.web_token()}", headers={"origin": base, "host": "127.0.0.1:7317"}) as ws:
        ws.receive_json()                                          # hello
        ws.send_json({"type": "say", "text": "Tell me in two sentences why tea is relaxing."})
        kinds, deltas = [], []
        while True:
            m = ws.receive_json()
            kinds.append(m["type"])
            if m["type"] == "delta":
                deltas.append(m["text"])
            if m["type"] == "reply":
                break
        final = m
    check("web chat streams the reply (delta messages before the final reply)", len(deltas) >= 2, str(kinds[:6]))
    check("streamed text matches the final reply", "".join(deltas).strip()[:40] == final["text"].strip()[:40] or
          final["route"] != "llm", f"{''.join(deltas)[:60]!r} vs {final['text'][:60]!r}")
else:
    print("  (no LLM key: streamed-chat check skipped)")

print(f"speed: {passed}/{total} checks passed")
sys.exit(0 if passed == total else 1)
