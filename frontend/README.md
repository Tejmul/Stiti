# Stiti web frontend

Next.js 16 (App Router, TypeScript), built as a **static export** that Stiti's Python server serves on
`127.0.0.1:7317` (inside Stiti.app). No Node process runs at runtime. Design notes: `docs/DECISIONS.md` D23.

| Page | What it is |
|---|---|
| `/` | Marketing landing: hero (quote + Stiti-on-a-Mac product shot over the particle sphere), Features, A day with Stiti, Privacy, FAQ |
| `/chat` | Chat with Stiti over the local WebSocket, with memory receipts under each reply |
| `/memory` | Everything Stiti knows about you: life map, facts (add/forget), people, rules, habits, mood, files, plans |

**Privacy:** your conversations are never shown on any page (chat starts fresh each visit; receipts show only how
many past conversations were recalled). Chat and Memory exist only on your Mac at `127.0.0.1:7317`.

```bash
pnpm install
pnpm build                                   # → out/, picked up by the Python server immediately
# dev (hot reload): two terminals
STITI_WEB_DEV=1 uv run stiti web --no-open   # API + WebSocket on :7317
pnpm dev                                     # http://localhost:3017/chat#t=$(cat ~/.stiti/web_token)
```

**Deploying the public website** (landing only — never the local build):

```bash
NEXT_PUBLIC_SITE_URL=https://your.domain STITI_PUBLIC=1 pnpm build    # /chat and /memory become a "runs on your Mac" page; their code isn't even bundled
```

SEO: canonical/OG URLs use `NEXT_PUBLIC_SITE_URL` (set it to the deployed origin when building the public site; see
`src/lib/site.ts`). The share image and apple-touch icon are static files rendered from the real page — rebuild + serve
the public site, then `node scripts/og.mjs http://127.0.0.1:7400/` to refresh them after a hero change.

`scripts/shot.mjs` takes headless screenshots (uses a cached Playwright Chromium); `scripts/chat-e2e.mjs` sends one
real chat message and screenshots the receipts — it writes to your real memory, so use it sparingly.
