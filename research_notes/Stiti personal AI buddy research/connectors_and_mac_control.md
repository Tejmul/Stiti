# Connectors and Mac Control: MCP Ecosystem, macOS Control, Phone Access, Security (as of Nov 2026)

Scope: tools/connectors layer for "Stiti" (local-first, zero-cost, Python, M2 / 8 GB). Per coordinator requirement, each feature has a comparison table of 10 or more papers or architectures, followed by a recommendation (under Inferences).

Legend for the "Fit" column: F = free, L = runs locally, Py = Python-native or uvx-installable. A "~" means partial. Rows marked † come from canonical project or arXiv URLs I know but did **not** re-fetch this session. The descriptions are standard, but versions, star counts and maintenance status were not re-verified for Nov 2026.

---

## 1. MCP state of the art and client architecture: spec, Python SDK / FastMCP, stdio vs HTTP, tool selection at scale, registries

### Takeaway
The current spec is **2026-07-28**, released July 28, 2026. It makes the protocol core stateless: no initialize handshake and no session ID. It also adds an extensions framework (Tasks, MCP Apps, enterprise auth) and deprecates Sampling, Roots, Logging and legacy HTTP+SSE. The official Python SDK **v2** (`pip install mcp` now gives 2.x) supports it and ships `ClientSessionGroup` for multi-server clients. FastMCP 3.x (PrefectHQ) is the higher-level option. With hundreds of tools, the established pattern is "tool RAG" / deferred loading: embed tool descriptions, retrieve the top 3–5 per turn, and keep a few always-on tools. That fits a local embedding model and Laya.

### Cited Findings

**Spec**
- 2026-07-28 spec released July 28, 2026. The `initialize`/`initialized` handshake and `Mcp-Session-Id` are retired (SEP-2575, SEP-2567). Each request carries protocol version, client identity and capabilities in `_meta`, and an optional `server/discover` replaces the handshake — [MCP blog](https://blog.modelcontextprotocol.io/posts/2026-07-28/)
- Multi Round-Trip Requests (SEP-2322) replace server-initiated elicitation, sampling and roots: the server returns `resultType: "input_required"` and the client retries with `inputResponses` — [MCP blog](https://blog.modelcontextprotocol.io/posts/2026-07-28/)
- Streamable HTTP requests must include `Mcp-Method` / `Mcp-Name` headers (SEP-2243). `tools/list` results are cacheable (`ttlMs`, `cacheScope`, deterministic order; SEP-2549) — [MCP blog](https://blog.modelcontextprotocol.io/posts/2026-07-28/)
- Tasks moved to the `io.modelcontextprotocol/tasks` extension. Notifications now go through a single `subscriptions/listen` stream. MCP Apps and Enterprise Managed Authorization are also extensions — [MCP blog](https://blog.modelcontextprotocol.io/posts/2026-07-28/)
- Auth changes: RFC 9207 `iss` validation; `application_type` in DCR so localhost redirects work for desktop/CLI apps; DCR deprecated in favour of Client ID Metadata Documents (CIMD) — [MCP blog](https://blog.modelcontextprotocol.io/posts/2026-07-28/)
- Roots, Sampling and Logging are deprecated, with at least 12 months of support. Legacy HTTP+SSE transport is deprecated with a one-year offramp, under a formal 12-month deprecation policy — [MCP blog](https://blog.modelcontextprotocol.io/posts/2026-07-28/)
- The previous version was 2025-11-25. Date-based versioning means "MCP 2.0" is a misnomer — [mcpservers.org blog](https://blog.mcpservers.org/posts/mcp-spec-2026-07-28); [Composio](https://composio.dev/blog/mcp-2026-07-28-update-statelessness-apps-auth)
- Tier-1 SDKs (TypeScript, Python, Go, C#) supported 2026-07-28 on release day; Rust is in beta — [MCP blog](https://blog.modelcontextprotocol.io/posts/2026-07-28/)

**Python SDK / FastMCP**
- MCP Python SDK v2 is the current stable line, and `pip install mcp` now pulls 2.x, so `<2` pins must be updated — [PyPI mcp 2.0.1](https://pypi.org/project/mcp/2.0.1/); [newreleases v2.0.0](https://newreleases.io/project/github/modelcontextprotocol/python-sdk/release/v2.0.0)
- `ClientSessionGroup` manages connections to multiple MCP servers via `connect_to_server` per server, e.g. with stdio params. v2 renamed `call_tool(args=)` to `arguments=` — [SDK v2 session groups docs](https://py.sdk.modelcontextprotocol.io/v2/client/session-groups/); [v2 migration](https://py.sdk.modelcontextprotocol.io/v2/migration/)
- FastMCP 3.0 is stable and moved from jlowin/fastmcp to PrefectHQ/fastmcp with the same PyPI name and imports. v3.3.x is current — [newreleases 3.0.0](https://newreleases.io/project/pypi/fastmcp/release/3.0.0); [v3.3.0](https://newreleases.io/project/github/PrefectHQ/fastmcp/release/v3.3.0)
- FastMCP clients can be built from a Claude-Desktop-style `mcpServers` config dict listing multiple servers. Servers can be mounted into a parent with prefixes to avoid tool-name collisions — [FastMCP v3 client docs](https://gofastmcp.com/v3/clients/client.md); [engineers-musings](https://engineers-musings.pages.dev/blog/mcp/12-fastmcp-and-beyond/)

**Tool selection at scale: comparison table**

| # | Name | Link | Year | Mechanism | Strengths | Weaknesses | Fit |
|---|---|---|---|---|---|---|---|
| 1 | RAG-MCP | [arXiv 2505.03275](https://arxiv.org/abs/2505.03275) | 2025 | Embed MCP tool/server descriptions; retrieve relevant ones before the LLM call | Cuts prompt tokens; "more than triples" selection accuracy in MCP stress test | Server-level retrieval is coarse; static pipeline | F/L/Py |
| 2 | MCP-Zero | [arXiv 2506.01056](https://arxiv.org/abs/2506.01056) | 2025 | Agent *actively requests* tools by writing a structured need; hierarchical server→tool retrieval | ~98% token reduction on APIBank at high accuracy | Needs a model that follows the request format | F/L/Py |
| 3 | ScaleMCP | [cited in LiveMCPBench](https://arxiv.org/html/2508.01780) (arXiv 2505.06416†) | 2025 | Dynamic, auto-synchronizing MCP tool index for agents | Keeps the index in sync as servers change | Abstract not retrieved; details unverified | F/L/Py |
| 4 | Semantic Tool Discovery | [arXiv 2603.20313](https://arxiv.org/abs/2603.20313) | 2026 | Dense-embedding index of MCP tools, top-K per query | 97.1% hit@3 over 121 tools / 5 servers; <100 ms retrieval | Small benchmark (140 queries) | F/L/Py |
| 5 | Dynamic ReAct | [arXiv 2509.20386](https://arxiv.org/html/2509.20386) | 2025 | Meta-tools let the agent search and load MCP tools from a vector DB; compares 5 architectures | Designed for hundreds to thousands of tools | Extra reasoning steps and latency | F/L/Py |
| 6 | Toolshed (RAG-Tool Fusion) | [aitopics/arXiv 2410.14594](https://aitopics.org/doc/arxivorg:33A2A678) | 2024 | Tool knowledge base plus pre-, intra- and post-retrieval (query rewrite, multi-query, rerank) | Recall@5 +46–56 points on ToolE/Seal-Tools; no fine-tuning | More retrieval stages mean more latency | F/L/Py |
| 7 | ToolRet benchmark | [arXiv 2503.01763](https://arxiv.org/pdf/2503.01763) | 2025 | 7.6k tasks over 43k tools; ToolRet-train with 200k+ instances | Shows generic IR embedders are poor at tool retrieval (NV-embed ~33.8 nDCG@10) | Benchmark, not a system | F |
| 8 | LiveMCPBench | [arXiv 2508.01780](https://arxiv.org/html/2508.01780) | 2025 | Benchmark for navigating a large live MCP toolset | Argues retrieval pipelines are rigid and weak at error recovery | Benchmark | F |
| 9 | Anthropic Tool Search Tool (`defer_loading`) | [Claude docs](https://platform.claude.com/docs/agents-and-tools/tool-use/tool-search-tool); [Anthropic eng](https://anthropic.com/engineering/advanced-tool-use) | 2025 | Deferred tools are not in context until found by regex/BM25 search; keep 3–5 hot tools | Production-proven pattern; per-server defer with per-tool overrides | Cloud API feature; must be reimplemented locally | ~F |
| 10 | Claude Code MCP Tool Search | [VentureBeat](https://venturebeat.com/orchestration/claude-code-just-got-updated-with-one-of-the-most-requested-user-features) | 2026 | Lazy-loads MCP tool defs when they exceed a token threshold; server `instructions` guide when to search | Shows the client-side pattern works | Proprietary client | – |
| 11 | GitHub MCP "dynamic toolsets" | [GitHub MCP config doc mirror](https://glama.ai/mcp/servers/@github/github-mcp-server/blob/bf6467855c13d3b8f5cf72f8dfd9c86f8336b20b/docs/server-configuration.md) | 2025–26 | Server exposes meta-tools so the model enables toolsets on demand (local only) | Server-side filtering; `--toolsets` allowlist | GitHub-specific | F/L |
| 12 | Gorilla † | [arXiv 2305.15334](https://arxiv.org/abs/2305.15334) | 2023 | Retriever-aware fine-tuned LLM for API calls | Early evidence that retrieval plus tuning reduces hallucinated calls | Pre-MCP; fine-tuning required | F |
| 13 | ToolLLM / ToolBench † | [arXiv 2307.16789](https://arxiv.org/abs/2307.16789) | 2023 | 16k+ RapidAPI tools, neural API retriever, DFS decision tree | Foundational large-toolset dataset | Pre-MCP; heavy | F |

- Context cost motivation: five MCP servers can use about 55k tokens of schemas before the user request is read. This is a third-party figure — [dev.to/unified.to](https://unified.to/blog/scaling_mcp_tools_with_anthropic_and_openai_defer_loading)

**Transports (stdio vs streamable HTTP)**
- Under 2026-07-28, streamable HTTP is stateless and load-balanceable with routing headers, while HTTP+SSE is deprecated — [MCP blog](https://blog.modelcontextprotocol.io/posts/2026-07-28/)
- Each stdio server is a separate process per client. That raises throttling risk for some servers (e.g. Telegram userbots spawn a new process per client) — [usecarly](https://www.usecarly.com/blog/telegram-mcp/)

**Registries**
- The official MCP Registry (registry.modelcontextprotocol.io) is still a **preview**. The REST API is v0.1 (additive-only changes) using standard `server.json` metadata, with no GA date announced. The Registry WG charter lists "API v1 GA" as "Ideating" — [qveris guide](https://qveris.ai/guides/mcp-registry/); [datallmlab](https://www.datallmlab.com/blog/mcp-registry.html); [Registry charter](https://modelcontextprotocol.io/community/working-groups/registry)
- Community directories used in this research include Glama, mcpservers.org, Smithery, mcp.so, LobeHub and PulseMCP. Many listings conflict on stars and versions (e.g. workspace-mcp at 2.8k vs 1.7k stars) — [mcpservers.org](https://mcpservers.org/servers/github-com-steipete-macos-automator-mcp); [Glama](https://glama.ai/mcp/servers/%40taylorwilsdon/google_workspace_mcp)
- Registry poisoning is real. In the Feb 2026 SmartLoader campaign a cloned Oura-ring MCP server was pushed via registry and social engineering (Straiker STAR Labs) — [UpGuard](https://www.upguard.com/blog/mcp-security-incidents)

### Inferences
- **Recommendation: client architecture.** Use the official `mcp` v2 SDK (`ClientSessionGroup`) or a FastMCP 3 `Client` built from an `mcpServers` JSON config as the "connector bus". That config file is the plug-in point, so adding a tool means adding a config entry with no core change. Use **stdio** for local servers (simplest, no network exposure, process lifetime tied to Stiti) and **streamable HTTP** only for remote/hosted servers (Notion, Google Workspace preview) or for Stiti's own memory server when several agents share it.
- **Recommendation: tool selection.** Implement "Laya tool-RAG". At startup, `tools/list` every server and cache using `ttlMs`. Embed `server.name + tool.name + description` with a small local embedder already loaded for memory (e.g. bge-small or nomic-embed; about 100 MB). Per turn, Laya picks intent, retrieves the top 5 tools (MCP-Zero-style hierarchical: server first, then tool), and adds 3–5 always-on tools (time, memory.search, notify, confirm). This follows RAG-MCP, MCP-Zero, Semantic Tool Discovery and Anthropic's `defer_loading`. It matters more on 8 GB, where a small local LLM (3–8B) has a short effective context and degrades badly with long tool lists. ToolRet suggests generic embedders are mediocre, so add a light reranker or lexical BM25 hybrid (as Anthropic offers BM25) and per-tool hand-written "when to use" examples.
- Target 2026-07-28 semantics (stateless, MRTR for elicitation/confirmations) when writing Stiti's own servers, because Sampling and Roots are deprecated.
- Expose Stiti memory with FastMCP 3 (`@mcp.tool` for `memory.search`, `memory.add`; resources for profile). Serve stdio for Claude Code (`claude mcp add stiti-memory -- uv run stiti-mem`) and optionally streamable HTTP bound to 127.0.0.1 with a bearer token.
- Do not auto-install from registries. Treat registries as discovery only and pin versions and hashes.

### Gaps
- No official confirmation of exact FastMCP 3.x multi-server config syntax under the 2026-07-28 spec, or of whether FastMCP's client already speaks stateless MRTR.
- ScaleMCP abstract and results not retrieved. Gorilla and ToolLLM details are from prior knowledge (†).
- No published benchmark of tool-RAG with **small local models** (3–8B) specifically; the evidence is mostly with frontier models.

---

## 2. Connectors: calendar, mail, files, notes, GitHub, music (best free MCP servers)

### Takeaway
For Google, the community **taylorwilsdon/google_workspace_mcp** (`uvx workspace-mcp`, Python, MIT, 120+ tools with tool tiers and service filtering) is the best free local option. Google's official Workspace MCP servers exist but are in developer preview and remote. For Apple apps, use **iMCP** (native app: Calendar, Contacts, Messages, Reminders and more) or Python **Apple-MCPs** (per-app uvx servers), or write a small pyobjc EventKit server. Filesystem, GitHub (official, with read-only and lockdown modes), Obsidian (Local REST API), Notion (official hosted) and Apple Music (AppleScript) all have solid free servers.

### Cited Findings

| # | Name | Link | Year | Mechanism / auth | Strengths | Weaknesses | Fit |
|---|---|---|---|---|---|---|---|
| 1 | google_workspace_mcp (taylorwilsdon) | [Glama](https://glama.ai/mcp/servers/%40taylorwilsdon/google_workspace_mcp); [mcpservers.org](https://mcpservers.org/fr/servers/taylorwilsdon/google_workspace_mcp) | 2025–26 | Python; OAuth 2.1 with your own GCP OAuth client; `uvx workspace-mcp --tools gmail drive calendar`; tool tiers core/extended/complete | Gmail, Calendar, Drive, Docs, Sheets, Tasks, Contacts, Chat; 120+ tools; v1.22.0 (2026-06-22) | Requires a GCP project and OAuth consent; broad scopes | F/L/Py |
| 2 | Google official Workspace MCP servers | [Workspace blog May 2026](https://workspaceupdates.googleblog.com/2026/05/agent-tools-and-security-updates-for-workspace-developers.html); [setup guide](https://developers.google.com/workspace/guides/configure-mcp-servers) | 2026 | Remote, per-product servers (e.g. drivemcp.googleapis.com); APIs enabled in GCP | First-party; Gmail drafting (no send tool, per third parties) is safer | Public developer preview; remote, not local; GA not confirmed | F~/–/– |
| 3 | iMCP (Loopwork/mattt) | [GitHub](https://github.com/mattt/iMCP); [mcpservers.org](https://mcpservers.org/servers/loopwork/iMCP) | 2025 | Native macOS app plus `imcp-server` CLI over stdio; EventKit/Contacts; Messages via `~/Library/Messages/chat.db` | Calendar, Contacts, Location, Maps, Messages, Reminders, Weather; per-service TCC prompts handled by a signed app | Swift app; macOS 15.3+; community-maintained | F/L/~ |
| 4 | apple-mcp (supermemoryai) | [docsearch](https://docsearch.algolia.com/mcp/docs/repo/supermemoryai/apple-mcp) | 2025 | Node, AppleScript/JXA | Messages, Mail, Notes, Calendar, Maps, Reminders, Contacts | Node; AppleScript speed; maintenance unclear | F/L/– |
| 5 | Apple-MCPs (JonathanRReed) | [mcpservers.org](https://mcpservers.org/servers/jonathanrreed/apple-mcps); [PyPI apple-messages-mcp](https://pypi.org/project/apple-messages-mcp/) | 2025–26 | Python, per-app uvx servers | Mail, Calendar, Reminders, Notes, Contacts, Messages, Shortcuts, Files; Messages needs Full Disk Access (read) and Automation (send) | Small project | F/L/Py |
| 6 | mcp-reminders / mcp-eventkit (pyobjc) | [mcp-reminders source](https://glama.ai/mcp/servers/@pongsapakl/mcp-reminders/blob/4208caee7acba410ee5126ad46bdd7962aba82b0/src/mcp_reminders/reminders.py); [mcp-eventkit](https://glama.ai/mcp/servers/Sub-lime-time/mcp-eventkit) | 2025–26 | pyobjc `EKReminder.reminderWithEventStore_`; `uv run --with mcp --with pyobjc-framework-EventKit` | Pure-Python template for Stiti's own EventKit server | Tiny projects | F/L/Py |
| 7 | Filesystem reference server † | [modelcontextprotocol/servers](https://github.com/modelcontextprotocol/servers) | 2024– | Official reference; allowlisted directories as args | Canonical; directory-scoped | Node; no content sandbox beyond path allowlist | F/L/~ |
| 8 | GitHub official MCP server | [config docs](https://glama.ai/mcp/servers/@github/github-mcp-server/blob/bf6467855c13d3b8f5cf72f8dfd9c86f8336b20b/docs/server-configuration.md); [GitHub changelog](https://github.blog/changelog/2025-12-10-the-github-mcp-server-adds-support-for-tool-specific-configuration-and-more) | 2025–26 | Go binary or remote; PAT/OAuth; `--toolsets`, `--read-only`, `--lockdown-mode`, per-tool `X-MCP-Tools` | Best-in-class scoping; lockdown limits public-repo content to authors with push access | Lockdown is "best-effort filter"; NeuralTrust reports a lockdown flaw fixed in 1.1.2 | F/L |
| 9 | Notion official hosted MCP | [mcp.so blog](https://mcp.so/blog/best-mcp-servers); [mcpservers.org best 2026](https://blog.mcpservers.org/posts/best-mcp-servers-2026) | 2025– | Remote `https://mcp.notion.com/mcp`, OAuth | First-party, tracks the current API | Cloud only | F/–/– |
| 10 | Obsidian via Local REST API plugin (mcp-obsidian etc.) | [enterprisedna](https://enterprisedna.co/directories/mcp/mcp-obsidian); [Glama Obsidian list](https://images.glama.ai/mcp/servers/integrations/obsidian) | 2025–26 | MCP server calls the Obsidian Local REST API plugin (API key) | Fully local, no cloud; no official server exists | Obsidian must be running; or read the vault folder directly with the filesystem server | F/L/Py |
| 11 | spotify-mcp (varunneal) | [LobeHub](https://lobehub.com/en/mcp/varunneal-spotify-mcp) | 2025 | Python; Spotify Web API with your own client ID/secret | Playback, search, queue, playlists | Playback control needs Spotify Premium (Spotify API rule, †) | F~/L/Py |
| 12 | mcp-applemusic (kennethreitz, epheterson) | [Glama](https://glama.ai/mcp/servers/kennethreitz/mcp-applemusic); [PyPI applemusic-mcp](https://pypi.org/project/applemusic-mcp/) | 2025 | FastMCP plus AppleScript to Music.app | No developer account needed; local | Library/playback only via AppleScript | F/L/Py |
| 13 | macos-automator-mcp (steipete) | [Glama README](https://glama.ai/mcp/servers/@steipete/macos-automator-mcp/blob/3e98b906909d68e466acc47e85bdc0c264017e0c/README.md) | 2025 | AppleScript/JXA runner with a script knowledge base | Covers any scriptable app (Notes, Mail, Music) | Arbitrary script execution, so high risk | F/L/– |

- Google's own guide warns about indirect prompt injection from untrusted emails and documents — reported by [eseospace](https://eseospace.com/blog/google-workspace-mcp-server/) (third-party)
- Apple has no public Messages API. Readers use `~/Library/Messages/chat.db`, which requires Full Disk Access — [iMCP via mcpservers.org](https://mcpservers.org/servers/loopwork/iMCP); [Apple-MCPs](https://mcpservers.org/servers/jonathanrreed/apple-mcps)

### Inferences
- **Recommendation (calendar, email, drive):** `workspace-mcp` via uvx, with `--tools gmail calendar drive` and the **core** tier only. Use your own GCP OAuth desktop client (free) and store the token in the macOS Keychain. Gate send/delete behind confirmation (see section 6). Switch to Google's official servers once they reach GA, if a remote dependency is acceptable.
- **Apple Calendar/Reminders:** write a ~150-line FastMCP server on pyobjc EventKit, following the mcp-reminders pattern. It stays Python-native, uses no extra RAM beyond the process, and gives full control of alarms (`EKAlarm`). Alternatively use iMCP if the user prefers an install with a signed app that already holds the TCC grants. **Notes:** AppleScript via an allowlisted Stiti tool (not the generic macos-automator) or Apple-MCPs notes. **Messages:** read-only from chat.db via iMCP or Apple-MCPs; sending only with confirmation.
- **Files:** official filesystem server restricted to `~/Documents/Stiti` plus selected folders, read-only by default.
- **GitHub:** official server with `--read-only --lockdown-mode --toolsets repos,issues,pull_requests`.
- **Notes apps:** Obsidian through a local vault (filesystem or mcp-obsidian). Notion through the official hosted server, if used.
- **Music:** Apple Music via AppleScript (free). Spotify only if the user has Premium.

### Gaps
- Exact current maintenance and last-commit dates for iMCP, apple-mcp and Apple-MCPs were not verified.
- Whether Google's official Workspace servers can run without Developer Preview Program membership in Nov 2026 is unconfirmed.
- Spotify Premium requirement for playback control is from prior knowledge.

---

## 3. macOS control and always-on daemon from Python

### Takeaway
Stiti must be a **signed .app bundle** (py2app or PyInstaller, then codesign) launched as a **user LaunchAgent** (or Login Item). It should be a menubar app (rumps, `LSUIElement`). TCC permissions (Microphone, Reminders/Calendars, Notifications, Accessibility, Automation, Screen Recording) attach to a "responsible" app bundle. A bare `python` launched by launchd often cannot get a mic grant and records silence. Use pyobjc EventKit for reminders/alarms, UNUserNotificationCenter (via desktop-notifier) for notifications, osascript/JXA for app control and volume, the `shortcuts run` CLI for user-built automations, and the Accessibility API / ScreenCaptureKit (e.g. Peekaboo) for screen context.

### Cited Findings

| # | Name | Link | Year | Mechanism | Strengths | Weaknesses | Fit |
|---|---|---|---|---|---|---|---|
| 1 | pyobjc EventKit | [Apple requestFullAccessToReminders](https://developer.apple.com/documentation/eventkit/ekeventstore/requestfullaccesstoreminders(completion:).md); [Apple creating events/reminders](https://developer.apple.com/documentation/eventkit/creating-events-and-reminders.md) | macOS 14+ API | `EKEventStore`, `requestFullAccessToRemindersWithCompletion_`, `EKReminder`, due dates via `dueDateComponents`, `EKAlarm` | Native, syncs to iPhone via iCloud, so reminders/alarms reach the phone for free | Completion handler fires on an arbitrary queue (wait on an Event); needs TCC Reminders | F/L/Py |
| 2 | UNUserNotificationCenter via desktop-notifier | [desktop-notifier docs](https://desktop-notifier.readthedocs.io/en/latest/); [macos backend](https://desktop-notifier.readthedocs.io/en/stable/autoapi/desktop_notifier/macos/index.html) | 2020s | pyobjc wrapper for UN API (Catalina+) | Actions/replies, modern API | Works only for **signed** executables; python.org Python is signed, Homebrew Python is not | F/L/Py |
| 3 | rumps (menubar) | [GitHub](https://github.com/jaredks/rumps); [PyPI](https://pypi.org/project/rumps/) | 2014– | pyobjc status-bar app; py2app packaging with `LSUIElement` | Simplest Python menubar; the bundle provides bundle ID for notifications/TCC | Older project; limited UI | F/L/Py |
| 4 | terminal-notifier / pync | [macnotifier](https://github.com/send/macnotifier); [pync](https://pypi.org/project/pync/1.6/) | legacy | Deprecated NSUserNotification | Trivial | Click actions fail on macOS 26 | F/L/~ |
| 5 | osascript / AppleScript / JXA | [macos-automator-mcp](https://glama.ai/mcp/servers/@steipete/macos-automator-mcp/blob/3e98b906909d68e466acc47e85bdc0c264017e0c/README.md) | – | `osascript -e` (open apps, `set volume output volume`, Music, Notes, Mail) | Covers most apps | Needs Automation permission per target app; UI scripting needs Accessibility | F/L/Py |
| 6 | PyXA † | [PyXA docs](https://skaplanofficial.github.io/PyXA/_modules/PyXA/apps/Reminders.html) | 2022– | Python wrapper over scripting bridge/JXA for Apple apps | Pythonic Reminders/Calendar/Music access | Single maintainer | F/L/Py |
| 7 | Shortcuts CLI (`shortcuts run "Name" -i file`) † | Apple Shortcuts user guide (not fetched) | macOS 12+ | User-built Shortcuts as tools | User can add capabilities (HomeKit, Focus, alarms via iPhone) with no code | Shortcuts has no direct Clock-app alarm on macOS; output limited | F/L/Py |
| 8 | Peekaboo (steipete) | [Peekaboo spec](https://glama.ai/mcp/servers/@steipete/Peekaboo/blob/05cbfee2c615de4a510673ebcac428a75909ab71/docs/specv3.md) | 2025–26 | CLI plus Mac app plus `@peekaboo/mcp`; screen capture plus AX element actions | Screen context and GUI actions as MCP | Needs Screen Recording and Accessibility; Node/Swift | F/L/– |
| 9 | macos-automator-mcp | [mcpservers.org](https://mcpservers.org/servers/github-com-steipete-macos-automator-mcp) | 2025 | MCP runner for AppleScript/JXA with knowledge base | Fast way to many Mac actions | Arbitrary code execution; host app needs Automation | F/L/– |
| 10 | launchd LaunchAgent | [Apple: Creating Launch Daemons and Agents](https://developer.apple.com/library/archive/documentation/MacOSX/Conceptual/BPSystemStartup/Chapters/CreatinglaunchdJobs.html); [launchy (Python)](https://pypi.org/project/launchy/) | – | `~/Library/LaunchAgents/*.plist`, `RunAtLoad` plus `KeepAlive {SuccessfulExit=false}` | Always-on, crash-restart, runs in user GUI session (can notify) | Python child processes may lose TCC responsibility | F/L/Py |
| 11 | TCC responsible-process behaviour | [Apple forum 805245](https://developer.apple.com/forums/thread/805245); [Apple forum 853725](https://developer.apple.com/forums/thread/853725); [claudeissues 86217](https://claudeissues.com/issue/86217-voice-dictation-always-fails-in-daemon-hosted-background-agent-sessions-recorder) | 2025–26 | macOS walks child→parent to find responsible code; launchd-reparented processes (PPID 1) may have no grantable responsible app, so the mic returns silence | Explains silent-mic failures | Poorly documented by Apple | – |
| 12 | Helper-agent pattern (OpenLogi) | [instagit OpenLogi](https://instagit.com/AprilNEA/OpenLogi/openlogi-macos-tcc-permission-checks-no-user-prompts/) | 2025 | Separate signed helper with own launchd label so it becomes the responsible process | Clean TCC attribution | More packaging work | F/L |
| 13 | Hammerspoon † | hammerspoon.org (not fetched) | 2014– | Lua automation with AX, hotkeys, URL events | Mature AX/window control; Stiti could call it via `hs` CLI | Lua, separate app | F/L/~ |

- Apple: a reminder needs `title` and `calendar`. Alarms can be time- or location-based — [Apple EventKit guide](https://developer.apple.com/documentation/eventkit/creating-events-and-reminders.md)
- UN notifications read bundle ID from the enclosing app bundle, so rumps users must package with py2app. Permission is per bundle ID, and changing the ID re-prompts — [RumpSharp/NuGet](https://www.nuget.org/packages/RumpSharp); [desktop-notifier PyPI](https://pypi.org/project/desktop-notifier/3.5.0)
- Sandboxed signed Python apps can fail `launchctl bootstrap` ("Bootstrap failed: 5") — [Apple forum 748205](https://developer.apple.com/forums/thread/748205)
- Security tooling flags "first time Python created a LaunchAgent" as suspicious (persistence technique), so expect AV/EDR noise — [Elastic rule](https://www.elastic.co/guide/en/security/8.19/prebuilt-rule-8-19-18-first-time-python-created-a-launchagent-or-launchdaemon.html)

### Inferences
- **Recommendation:** package Stiti as `Stiti.app` (py2app, ad-hoc or Developer ID signed, `LSUIElement=1`, `NSMicrophoneUsageDescription`, `NSRemindersFullAccessUsageDescription`, `NSCalendarsFullAccessUsageDescription`, `NSAppleEventsUsageDescription`). Start it as a Login Item, or a LaunchAgent that execs the app's main binary directly (not `/usr/bin/python3 script.py`). Use `KeepAlive {SuccessfulExit=false}`.
- Do all mic capture **in-process** in the app (sounddevice/AVAudioEngine via pyobjc), so the app is the TCC-responsible process. Spawn MCP servers as children that do **not** need the mic. Children needing Reminders, Automation or Full Disk Access inherit attribution only sometimes. Prefer doing EventKit inside Stiti's own in-process MCP server, or run those servers as signed helpers.
- "Alarms" on Mac means EventKit reminders with `EKAlarm` (syncs to iPhone and rings there) plus local UN notifications with sound. The Clock-app alarm is not scriptable on macOS.
- Volume, open apps and media: a fixed, allowlisted set of osascript snippets exposed as Stiti tools (`set_volume`, `open_app`, `now_playing`). Avoid a generic "run any AppleScript" tool. Screen context: Peekaboo MCP or ScreenCaptureKit plus local OCR or VLM only on explicit request.
- RAM: every stdio MCP server is a process. Node servers cost about 50–100 MB each (estimate), which matters on 8 GB. Prefer in-process Python tools for core Mac control and start external servers lazily.

### Gaps
- No Apple primary doc found stating the launchd/Python mic-TCC rule. The evidence is forum threads and issue reports.
- Shortcuts CLI and Hammerspoon details were not re-verified this session.
- Whether ad-hoc-signed (non-Developer-ID) py2app bundles keep TCC grants stable across rebuilds was not verified. Re-signing probably changes the code requirement and re-prompts.

---

## 4. Phone access for free (Telegram, WhatsApp, ntfy, Pushover alternatives)

### Takeaway
The best free, low-risk phone channel is a **Telegram Bot** (official Bot API, two-way chat and voice notes, the bot only acts where added) plus **ntfy** for one-way push. Apprise can fan out to both. WhatsApp via unofficial whatsmeow/Baileys bridges risks bans of a personal number, and the main project (lharries/whatsapp-mcp) appears unmaintained since July 2025. iCloud-synced Reminders are a free "push to iPhone" path with no extra service.

### Cited Findings

| # | Name | Link | Year | Mechanism | Strengths | Weaknesses | Fit |
|---|---|---|---|---|---|---|---|
| 1 | Telegram Bot API (python-telegram-bot / aiogram †) | [core.telegram.org/bots/api](https://core.telegram.org/bots/api) †; [usecarly analysis](https://www.usecarly.com/blog/telegram-mcp/) | – | Bot token, long-polling (no inbound port needed) | Free, official, two-way, voice notes, buttons for confirmations; low ban risk | Messages pass through Telegram cloud (not E2E for bots) | F/L/Py |
| 2 | Telegram userbot MCP (telegram-mcp, Telethon) | [usecarly](https://www.usecarly.com/blog/telegram-mcp/); [policylayer risk](https://policylayer.com/risk/critical/mcp-telegram-mcp-telegram) | 2025 | Logs into a personal account via MTProto | Full account access (read all chats) | Throttling and ban risk; critical-risk tools; no official server | F/L/Py |
| 3 | ntfy (ntfy.sh or self-host) | [ntfy terms](https://docs.ntfy.sh/terms/); [ntfy FAQ](https://docs.ntfy.sh/faq/) | 2021– | HTTP PUT/POST to topic; iOS/Android apps | Free without account; one `requests.post` call; open source | Topic name is the password on free tier; self-hosted iOS delivery less reliable (relays via ntfy.sh/APNs) | F/~L/Py |
| 4 | Gotify | [cloudingenium](https://kx.cloudingenium.com/en/gotify-self-hosted-push-notification-server-api/); [sumguy](https://sumguy.com/ntfy-vs-gotify-vs-apprise) | 2018– | Self-hosted WebSocket push | Fully self-hosted | No official iOS app (third-party iGotify) | F/L |
| 5 | Pushover | [selfhosting.sh](https://dev.to/selfhostingsh/pushover-nn6) | – | Hosted API, native APNs | Most reliable iOS push | Not free (~$5 one-time per platform after trial) | –/–/Py |
| 6 | Apprise | [ntfy vs gotify vs apprise](https://sumguy.com/ntfy-vs-gotify-vs-apprise); [apprise GitHub †](https://github.com/caronc/apprise) | 2017– | Python library routing to 100+ services by URL scheme | One API for ntfy, Telegram, email, Discord and more | No phone app itself | F/L/Py |
| 7 | lharries/whatsapp-mcp | [dragapp](https://www.dragapp.com/blog/whatsapp-mcp-server/); [HN](https://hn.svelte.dev/item/43532967) | 2025 | whatsmeow (multi-device web protocol) plus Python MCP; QR login | Full WhatsApp read/send | Unofficial and against Meta ToS; reported bans even at low volume; no releases since Jul 2025 | F/L/Py |
| 8 | WhatsApp Baileys/Go forks | [trykondo](https://www.trykondo.com/blog/best-whatsapp-mcp-server); [blueticks](https://blueticks.co/blog/best-whatsapp-mcp-servers) | 2025–26 | TypeScript Baileys / Go rewrites | Maintained alternatives | Same ban risk; vendor sources | F/L/– |
| 9 | WhatsApp Cloud API (official) | [dragapp](https://www.dragapp.com/blog/whatsapp-mcp-server/) | – | Meta Business account | Sanctioned | Business account plus template rules; not personal-chat access; paid conversations † | ~F |
| 10 | iMessage via iMCP / Apple-MCPs | [Apple-MCPs](https://mcpservers.org/servers/jonathanrreed/apple-mcps) | 2025 | Read chat.db; send via Messages AppleScript | Native, free, reaches iPhone contacts | Full Disk Access needed; sending to others is risky | F/L/Py |
| 11 | iCloud Reminders/Calendar push (EventKit) | [Apple EventKit](https://developer.apple.com/documentation/eventkit/creating-events-and-reminders.md) | – | Create EKReminder with alarm; iCloud syncs to iPhone | Zero extra service; uses Apple's native alarms | One-way; needs iCloud | F/L/Py |
| 12 | signal-cli † | [github.com/AsamK/signal-cli](https://github.com/AsamK/signal-cli) | 2015– | Unofficial Signal client (Java), JSON-RPC daemon | E2E encrypted two-way | Java (RAM); requires a phone number; unofficial | F/L/~ |
| 13 | Matrix (self-host or matrix.org) † | [matrix-nio](https://github.com/matrix-nio/matrix-nio) | – | Matrix bot via Python SDK | Open, E2E possible, self-hostable | Heavier setup | F/L/Py |

### Inferences
- **Recommendation:** (1) **Telegram bot** as the primary remote channel. It gives free two-way text and voice, and inline buttons work as the remote confirmation UI for risky actions. Use long-polling so Stiti opens no inbound ports, and allowlist your own chat_id only. (2) **ntfy** (self-hosted or ntfy.sh with a long random topic) for fire-and-forget alerts. (3) **EventKit reminders** for time-based alarms that must ring on the iPhone. Wrap all of these behind one `notify` tool using Apprise.
- Avoid WhatsApp automation on a personal number. If required, run it read-only and rate-limited, and accept the ban risk.
- Telegram bot traffic is not end-to-end encrypted. Do not send secrets or full memory dumps over it.

### Gaps
- Telegram Bot API pricing and rate limits were not re-verified this session (prior knowledge: free).
- No authoritative ban-rate data for WhatsApp/Telegram unofficial clients. The sources are vendor blogs.
- Exact ntfy.sh free-tier limits are not published.

---

## 5. Browser automation and free web search

### Takeaway
Use **Playwright MCP** (Microsoft) for acting (accessibility-snapshot actions, no vision model needed) and **Chrome DevTools MCP** (Google) for inspecting. Both are free and local but Node-based. For search, **self-hosted SearXNG** plus a SearXNG MCP server is the only truly free, unlimited, private option. Brave Search API dropped its free tier for new users in Feb 2026 (now a ~$5/month credit with a card required). DuckDuckGo-scraping servers are free but fragile.

### Cited Findings

| # | Name | Link | Year | Mechanism | Strengths | Weaknesses | Fit |
|---|---|---|---|---|---|---|---|
| 1 | Playwright MCP (Microsoft) | [stevekinney](https://stevekinney.com/writing/driving-vs-debugging-the-browser); [mcp.directory test](https://mcp.directory/blog/chrome-devtools-mcp-vs-playwright-mcp-2026) | 2025– | Structured accessibility snapshots plus deterministic actions | Text-only, which suits small LLMs; cross-browser | No deep devtools introspection; Node | F/L/– |
| 2 | Chrome DevTools MCP (Google) | [trackingplan](https://www.trackingplan.com/blog/chrome-devtools-mcp-vs-playwright-mcp-digital-analysts); [Addy Osmani deck](https://talks.addy.ie/openai-devtoolsmcp-2026/deck) | 2025– | Chrome DevTools Protocol: console, network, perf, Lighthouse | Can attach to the user's live Chrome; ~51k stars vs 36.8k (one directory) | Oriented to observation/debugging | F/L/– |
| 3 | browser-use † | [github.com/browser-use/browser-use](https://github.com/browser-use/browser-use) | 2024– | Python agent loop over Playwright with DOM plus vision | Python-native | Wants strong models; heavy for 8 GB local LLM | F/L/Py |
| 4 | Browser Harness / CDP self-healing | [shiporskip](https://shiporskip.io/compare/browser-harness-browser-use-self-healing-llm-automation-cdp-592-lines-2026-vs-chrome-devtools-mcp-server-ai-agent-browser-automation-2026) | 2026 | Small CDP harness | Lightweight | New; little evidence | F/L |
| 5 | Fetch reference server † | [modelcontextprotocol/servers](https://github.com/modelcontextprotocol/servers) | 2024– | HTTP GET to markdown | Cheapest "read a page" tool; Python | No JS rendering; SSRF/exfil channel risk | F/L/Py |
| 6 | SearXNG self-hosted plus MCP (ihor-sokoliuk/mcp-searxng, kevinwatt, searxng-http-mcp) | [mcpservers.org mcp-searxng](https://mcpservers.org/zh-CN/servers/ihor-sokoliuk/mcp-searxng); [@kevinwatt](https://glama.ai/mcp/servers/%40kevinwatt/mcp-server-searxng); [PyPI searxng-http-mcp](https://pypi.org/project/searxng-http-mcp/) | 2025–26 | Metasearch (Google, Bing, DDG, Brave, Wikipedia) via local JSON API | Free, unlimited, private, no keys; Python uvx option | Docker container (~100–200 MB est.); upstream engines can rate-limit/CAPTCHA | F/L/Py |
| 7 | DuckDuckGo MCP servers | [SearXNG/DDG listing](https://glama.ai/mcp/servers/vi8l485u5y) | 2025 | Scrape DDG HTML/lite | No infrastructure | Rate limits and breakage; ToS grey area | F/L/Py |
| 8 | Brave Search API | [implicator](https://www.implicator.ai/brave-drops-free-search-api-tier-puts-all-developers-on-metered-billing.md); [apiserpent](https://apiserpent.com/blog/free-brave-search-api) | 2026 | Paid API, $5 monthly credit (~1k queries) with attribution and card | Independent index, good quality | Free tier removed Feb 2026 for new users; overage with no cap reported; pricing sources conflict | ~F |
| 9 | Google Custom Search JSON API | [Brave on Google API shutdown](https://brave.com/learn/google-api-shutdown/) | – | Google API being shut down (2027 per Brave) | – | Shutting down; avoid | – |
| 10 | Tavily / Exa / Firecrawl free credits | [Firecrawl alternatives](https://www.firecrawl.dev/blog/brave-search-api-alternatives); [agentdeals](https://agentdeals.dev/alternative-to/brave-search-api) | 2025–26 | Hosted AI-search APIs with monthly free credits | Clean LLM-ready results | Cloud; quotas; vendor lock-in | ~F |

### Inferences
- **Recommendation:** run SearXNG in Docker (or via `pip`/uwsgi without Docker to save RAM) on localhost and use a Python SearXNG MCP server (`uvx searxng-http-mcp`, `SEARXNG_URL=http://127.0.0.1:8080`) as the default `web.search`. Use the fetch server or trafilatura in-process for reading pages. Start Playwright MCP **on demand only**, because Chromium takes several hundred MB (estimate) and 8 GB is tight with a local LLM loaded. Use a separate, logged-out browser profile for the agent.
- Chrome DevTools MCP attached to the user's real Chrome profile exposes all logged-in sessions to prompt injection from any page. Do not do this by default.
- Small local LLMs handle Playwright's accessibility-tree snapshots better than screenshot/vision loops.

### Gaps
- No RAM measurements found for Playwright MCP, Chrome DevTools MCP or SearXNG on Apple Silicon. The figures above are estimates.
- Maintenance status of individual SearXNG MCP servers was not verified.

---

## 6. Connector security: prompt injection, tool poisoning, sandboxing, confirmation; OpenClaw/Hermes incidents

### Takeaway
MCP's main risks are (a) **tool poisoning / rug pulls**: malicious instructions in tool descriptions, or descriptions changed after approval; (b) **indirect prompt injection** through data the tools return (emails, issues, web pages); and (c) **supply-chain malware** in skill/server registries. The "toxic flow" combination of untrusted input, private data and an outbound channel in one context is what turns injection into exfiltration. Real incidents: GitHub MCP private-repo leak (May 2025), WhatsApp MCP exfiltration (Apr 2025), ClawHavoc on ClawHub (341 of 2,857 skills malicious, AMOS stealer on macOS, Feb 2026), 30+ MCP CVEs in 60 days in early 2026, and a Microsoft June 2026 disclosure. Defenses that work are architectural: capability/flow control (CaMeL, Progent-style policies), least-privilege toolsets, pinned and hashed tool descriptions, human confirmation for side effects, and process sandboxing.

### Cited Findings

**Incidents and research: comparison table**

| # | Name | Link | Year | Mechanism / finding | Lesson for Stiti |
|---|---|---|---|---|---|
| 1 | Invariant Labs tool poisoning plus WhatsApp exfiltration | [Invariant blog](https://invariantlabs.ai/blog/whatsapp-mcp-exploited); [Docker](https://www.docker.com/blog/mcp-horror-stories-whatsapp-data-exfiltration-issue/); [Simon Willison](https://simonwillison.net/2025/Apr/9/mcp-prompt-injection/) | Apr 2025 | Malicious second server's tool description silently redirected WhatsApp sends and leaked chat history | Cross-server shadowing: one bad server compromises others in the same context |
| 2 | GitHub MCP "toxic agent flow" | [Invariant](https://invariantlabs.ai/blog/mcp-github-vulnerability); [toxic flow analysis](https://invariantlabs.ai/blog/toxic-flow-analysis) | May 2025 | Malicious public issue made the agent leak private repo data into a public PR; architectural, no CVE | Never mix untrusted input, private data and a public write channel without a gate |
| 3 | MCPoison (Cursor, CVE-2025-54136) | [Zealynx](https://www.zealynx.io/resources/ai-security-hacks-library/cursor-mcpoison-tool-descriptor-injection-cve-2025-54136) | 2025 | Approved MCP config silently swapped (rug pull) | Re-approve on any change to server command or description |
| 4 | MCPTox benchmark | [arXiv 2508.14925](https://arxiv.org/abs/2508.14925) | 2025 (v2 Sep 2026) | 45 real servers, 353 tools, 1,312 poisoned cases; o1-mini ASR 72.8%; more capable models were often *more* susceptible | Model-level refusal is not a defense |
| 5 | MCP-SafetyBench | [arXiv 2512.15163](https://arxiv.org/pdf/2512.15163) | 2025 | Multi-turn safety on real MCP servers | Test Stiti with such suites |
| 6 | MCPSecBench / MCP Security Bench (MSB) | cited in [MCP-SafetyBench](https://arxiv.org/pdf/2512.15163) | 2025 | 17 attacks across user, host, transport and server layers; poisoned descriptions, outputs, trajectories | Threat taxonomy for design review |
| 7 | CaMeL "Defeating Prompt Injections by Design" (Google DeepMind) | [arXiv 2503.18813](https://arxiv.org/abs/2503.18813) | 2025 | Privileged LLM plans code from the trusted query; quarantined LLM parses untrusted data; capabilities block exfiltration | 67% (v1) to 77% (later summary) of AgentDojo tasks with provable security; this split is the gold-standard pattern |
| 8 | Progent | arXiv 2504.11703 (unverified ID) via [danielvaughan](https://codex.danielvaughan.com/2026/07/08/out-of-band-prompt-injection-defences-camel-fides-progent-codex-cli-sandbox-approval-hooks/) | 2025 | Reference monitor enforcing tool and argument privilege policies | Deterministic policy layer, which maps onto Laya |
| 9 | ShieldNet | [arXiv 2604.04426](https://arxiv.org/pdf/2604.04426) | 2026 | Network-level guardrails against supply-chain injections | Egress filtering of MCP subprocesses |
| 10 | CSA research notes and whitepaper | [CSA crisis note](https://labs.cloudsecurityalliance.org/research/csa-research-note-mcp-security-crisis-20260504/); [CSA tool poisoning/rug pull](https://labs.cloudsecurityalliance.org/research-rb/csa-whitepaper-mcp-security-tool-poisoning-20260506-csa-styl/); [CSA description poisoning Jul 2026](https://labs.cloudsecurityalliance.org/research/csa-research-note-mcp-tool-description-poisoning-20260711-cs/) | 2026 | Systemic design flaws; Microsoft's June 2026 disclosure treats poisoned descriptions as a general exfiltration path | Industry consensus that the problem is structural |
| 11 | Early-2026 CVE wave | [dev.to state of MCP security](https://dev.to/luckypipewrench/the-state-of-mcp-security-2026-incidents-attack-patterns-and-defense-coverage-2h45); [heyuan110](https://www.heyuan110.com/posts/ai/2026-03-10-mcp-security-2026/) | 2026 | 30+ MCP server CVEs in 60 days; ~13 command injection | Prefer few, well-maintained servers; pin versions |
| 12 | SmartLoader registry poisoning | [UpGuard](https://www.upguard.com/blog/mcp-security-incidents) | Feb 2026 | Cloned Oura MCP server distributed via registry/social engineering | Install only from source repos you trust; verify the publisher |
| 13 | ClawHavoc (OpenClaw / ClawHub) | [The Hacker News](https://thehackernews.com/2026/02/researchers-find-341-malicious-clawhub.html); [eSecurity Planet](https://esecurityplanet.com/threats/hundreds-of-malicious-skills-found-in-openclaws-clawhub); [Tom's Hardware](https://www.tomshardware.com/tech-industry/cyber-security/malicious-moltbot-skill-targets-crypto-users-on-clawhub) | Jan–Feb 2026 | Koi Security: 341 of 2,857 skills malicious, 335 in one campaign; fake "prerequisite" installs AMOS stealer on macOS; reverse shells; typosquats; only gate was a 1-week-old GitHub account | Markdown skills are code. No unvetted third-party skills |
| 14 | OpenClaw response | [The Hacker News](https://thehackernews.com/2026/02/openclaw-integrates-virustotal-scanning.html) | Feb 2026 | VirusTotal scan of every upload, daily rescans, reporting; maintainers say "not a silver bullet" | Scanning helps but cannot catch prompt-injection payloads |
| 15 | Hermes Agent (Nous Research) skills plus Tirith | [Medium security review](https://medium.com/@ishayvilroel/hermes-agent-what-security-teams-should-understand-before-they-run-it-e413de65fcd4); [Adversa](https://airq.adversa.ai/agent/hermes-agent); [techjacksolutions](https://techjacksolutions.com/ai-tools/hermes/best-hermes-skills/) | 2026 | Skills as markdown in `~/.hermes/skills/` (self-written or community); Tirith Rust pre-install scanner (v0.13.0); "Skills Guard"; CVE-2026-7113 reported; bypasses claimed | Self-modifying skills persist behaviour, so review them like code (third-party claims) |
| 16 | mcp-scan (Invariant/Snyk) | [Invariant](https://invariantlabs.ai/blog/introducing-mcp-scan) | 2025 | `uvx mcp-scan@latest` checks descriptions, tool pinning and toxic flows | Default mode sends tool descriptions to invariantlabs.ai; `--local-only` needs an OpenAI key |
| 17 | GitHub MCP lockdown / read-only | [classmethod lockdown](https://dev.classmethod.jp/en/articles/github-mcp-lockdown-verification/); [NeuralTrust](https://neuraltrust.ai/blog/how-to-secure-github-mcp) | 2025–26 | Server-side read-only and public-content filtering | Least privilege at the server is effective; lockdown is best-effort |

- Lethal-trifecta / toxic-flow definition: privileged access plus untrusted input plus external communication channel — [UpGuard](https://www.upguard.com/blog/ai-github-agents-issue-leaked-private-repos); [Invariant](https://invariantlabs.ai/blog/toxic-flow-analysis)
- Rug-pull attack: tool definitions change after the user approved them — [dev.to waxell](https://dev.to/waxell/the-mcp-rug-pull-attack-the-threat-that-changes-your-tools-after-youve-approved-them-2km0)
- Separate analysis of 3,984 skills: 283 (~7.1%) expose credentials in plaintext — [eSecurity Planet](https://esecurityplanet.com/threats/hundreds-of-malicious-skills-found-in-openclaws-clawhub)
- Spec-level help: 2026-07-28 MRTR gives a standard "input_required" round-trip usable for confirmations, and cacheable deterministic `tools/list` makes hash-pinning descriptions practical — [MCP blog](https://blog.modelcontextprotocol.io/posts/2026-07-28/)

### Inferences
- **Recommendation: Stiti security architecture.**
  1. **Pin-and-diff**: hash each server's command, version and full `tools/list` JSON on approval. On any change, disable the server until the user re-approves (defends against rug pulls and MCPoison).
  2. **Risk tiers per tool** in Stiti's config, not trusted from server annotations: `read` (auto), `local-write` (auto, logged, undo where possible), `external/irreversible` (send email/message, delete, purchase, shell, git push, sharing permissions), which **always requires a spoken or Telegram-button confirmation** showing the exact arguments.
  3. **Toxic-flow guard in Laya**: after any untrusted-content tool runs (email read, web fetch, GitHub issue, Messages), mark the context "tainted". While tainted, outbound tools (send, post, http fetch to new domains) need confirmation even if normally auto. This is a lightweight approximation of CaMeL/Progent.
  4. **Quarantined summarization**: pass raw tool output through a summarizer prompt that cannot call tools before the planner sees it (CaMeL-lite). Never put tool-returned text in the system prompt.
  5. **Least privilege at the server**: GitHub `--read-only --lockdown-mode`; filesystem allowlisted dirs; Workspace `--tools` subset and core tier; Gmail drafting rather than sending.
  6. **Sandboxing**: run third-party stdio servers under a separate macOS user or with `sandbox-exec` profiles (deprecated but functional †), or in a container for Node servers. Strip env vars (pass only the needed token) and give no shell access. Network egress allowlist per server (Little Snitch/LuLu †, or a proxy as in ShieldNet).
  7. **Supply chain**: no ClawHub-style auto-install. Install only from known repos, pin commit SHA/version, and run `mcp-scan` (local-only) on install. Treat any "prerequisite: paste this into Terminal" as malware (ClawHavoc pattern).
  8. **Secrets** in macOS Keychain (`keyring` lib), never in the LLM context.
- Since MCPTox shows stronger models are often *more* obedient to poisoned descriptions, a small local model offers no safety advantage. Deterministic policy outside the model (Laya) is the key control.

### Gaps
- Primary Microsoft June 2026 disclosure not fetched (only CSA and Aviatrix summaries).
- Progent arXiv ID and MCPSecBench ID not verified.
- Hermes/Tirith details come from third-party security blogs, not Nous Research docs; CVE-2026-7113 is unverified.
- No independent evaluation of `sandbox-exec` effectiveness for MCP servers on macOS 26.

---

## 7. How other personal assistants structure tool/skill layers

### Takeaway
Two families exist. **Intent-routed code handlers** (Home Assistant intents, OVOS skills) are deterministic, fast and safe. **LLM-read instruction packages** (Anthropic Agent Skills `SKILL.md`, OpenClaw skills, Hermes skills) are flexible, but because they are prose they are a code-execution and prompt-injection surface. Stiti's Laya plus MCP design can combine them: a deterministic intent fast-path for common voice commands, then MCP tools selected by tool-RAG, plus optional SKILL.md "playbooks" with progressive disclosure.

### Cited Findings

| # | Name | Link | Mechanism | Strengths | Weaknesses | Fit |
|---|---|---|---|---|---|---|
| 1 | Anthropic Agent Skills (`SKILL.md`) | [OpenClaw docs referencing AgentSkills spec](https://docs.openclaw.ai/skills); [Anthropic tool use eng](https://anthropic.com/engineering/advanced-tool-use) | Folder with SKILL.md; only the short description is always in context, the body is loaded on demand | Progressive disclosure saves context; open format | Scripts inside skills execute code | F/L/Py |
| 2 | OpenClaw skills plus ClawHub | [OpenClaw skills docs](https://docs.openclaw.ai/skills); [morphllm](https://www.morphllm.com/openclaw-skills); [ampere](https://www.ampere.sh/blog/openclaw-skills-skillmd-loading-precedence) | AgentSkills-format; `metadata.openclaw.requires` gates load on binaries, env and OS; `always` bypasses gates; precedence workspace > user > bundled | Huge ecosystem | `requires` is a dependency check, **not** a permission; ClawHavoc | F/L |
| 3 | Hermes Agent skills | [Hermes docs](https://hermes-agent.org/docs/skills); [Medium](https://medium.com/@ishayvilroel/hermes-agent-what-security-teams-should-understand-before-they-run-it-e413de65fcd4) | Markdown skills in `~/.hermes/skills/`, self-authored by the agent ("self-improving") or community; Curator; Tirith scanner | Learns procedures over time | Persistent behaviour change; scanner bypass claims | F/L/Py |
| 4 | Home Assistant intents | [HA dev docs: intents](https://developers.home-assistant.io/docs/voice/intents/); [intent index](https://developers.home-assistant.io/docs/intent_index) | Typed intents (`HassTurnOn`, etc.) with slots; all voice paths go through one intent layer; LLM APIs expose intents as tools | Deterministic, multilingual sentence templates, safe | Limited to defined intents | F/L/Py |
| 5 | OVOS skills / intent pipeline | [OVOS intents](https://openvoiceos.github.io/ovos-technical-manual/399-intents); [pipelines](https://openvoiceos.github.io/ovos-technical-manual/pipelines_overview) | Intent = message plus handler; Adapt (keyword) and Padatious (example) at high, medium and low confidence, then common_query, then fallback | Proven voice-first pipeline; Python | Older matchers; less LLM-native | F/L/Py |
| 6 | OVOS plus HA combined | [OVOS blog](https://blog.openvoiceos.org/posts/2025-09-17-ovos_ha_dream_team) | OVOS voice front-end driving HA | Shows a layered design | – | F/L/Py |
| 7 | GitHub MCP toolsets / dynamic discovery | [config doc](https://glama.ai/mcp/servers/@github/github-mcp-server/blob/bf6467855c13d3b8f5cf72f8dfd9c86f8336b20b/docs/server-configuration.md) | Grouped toolsets enabled on demand | Server-side tool grouping | – | F/L |
| 8 | Anthropic Tool Search (`defer_loading`) | [Claude docs](https://platform.claude.com/docs/agents-and-tools/tool-use/tool-search-tool) | Deferred tool catalogue plus search tool | Scales to large catalogues | Cloud API | – |
| 9 | MCP-Zero active discovery | [arXiv 2506.01056](https://arxiv.org/abs/2506.01056) | Agent requests capabilities | Agent-driven | Needs a capable model | F/L/Py |
| 10 | Hermes/OpenClaw scanners (Tirith, VirusTotal) | [THN](https://thehackernews.com/2026/02/openclaw-integrates-virustotal-scanning.html); [techjacksolutions](https://techjacksolutions.com/ai-tools/hermes/best-hermes-skills/) | Pre-install scanning of skill packages | Catches commodity malware | Misses prompt injection | – |

### Inferences
- **Recommendation: Stiti layering.** (1) **Laya fast-path**: an OVOS/HA-style intent matcher (keyword plus embedding similarity over example sentences) for the ~20 most common voice commands (time, timer/alarm, volume, open app, play music, "what's next on my calendar"). These run without the LLM, for low latency and less RAM pressure. (2) **LLM plus tool-RAG over MCP tools** for everything else. (3) **Skills** as optional SKILL.md playbooks (multi-step procedures such as "morning brief") that reference MCP tools by name. Store them locally, write them yourself, and never install them from a hub without review. Skills cannot grant permissions; risk tiers come only from Stiti's tool policy.
- Follow HA's choice of typed intents with slots for the fast-path, so Laya's decisions are auditable and testable.

### Gaps
- Did not fetch the primary Agent Skills specification page. The "open standard" status rests on OpenClaw docs and secondary articles.
- Did not verify Home Assistant's 2026 LLM-API/MCP-server integration details (HA ships an MCP server integration per prior knowledge; not verified this session).
