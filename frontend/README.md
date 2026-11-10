# Stiti web frontend

Next.js 16 (App Router, TypeScript), built as a **static export** that Stiti's Python server serves on
`127.0.0.1:7317` (inside Stiti.app). No Node process runs at runtime. Design notes: `docs/DECISIONS.md` D23.

| Page | What it is |
|---|---|
| `/` | Landing: preloader, hero particle sphere, sections |
| `/chat` | Chat with Stiti over the local WebSocket, with memory receipts under each reply |
| `/memory` | Everything Stiti knows about you: life map, facts (add/forget), people, rules, habits, mood, conversations, files, plans |

```bash
pnpm install
pnpm build                                   # → out/, picked up by the Python server immediately
# dev (hot reload): two terminals
STITI_WEB_DEV=1 uv run stiti web --no-open   # API + WebSocket on :7317
pnpm dev                                     # http://localhost:3017/chat#t=$(cat ~/.stiti/web_token)
```

`scripts/shot.mjs` takes headless screenshots (uses a cached Playwright Chromium); `scripts/chat-e2e.mjs` sends one
real chat message and screenshots the receipts — it writes to your real memory, so use it sparingly.
