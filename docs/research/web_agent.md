# Research: web agent — flight prices by voice, booking up to payment, crawling later

Date: 2026-11-18. Research only, nothing built. Every fact below was checked today by web search + page fetch
unless marked **(not verified)**. "Measured" = run from this Mac today with `curl` (no browser, no account).
Rules that shape every choice: free only, no local LLM, personal data stays on the Mac, ≤ ~3 GB local RAM, tools via MCP.

## 1. The three jobs and what "done" means

| Job | He says | Done when |
|---|---|---|
| 1. Price lookup | "Flight prices Delhi to Mumbai on 10 Dec?" | Stiti says the 2–3 best options (price, airline, time) in ≤ 8 s, and says where the price came from. |
| 2. Open and hand over | "Open it." | The search / booking page opens in his own browser, already filled with route and date. He does the rest. |
| 3. Fill up to payment | "Book the 7:10 Akasa one." | Stiti selects the flight, fills passenger details, reads everything back, gets his "haan", stops **on** the payment page. He pays. |
| Later | "Watch this page / collect these pages." | Pages fetched and cleaned into text, politely, in the background. |

## 2. Comparison tables

### A. Price data sources (free, from India)

| # | Option | How it works | Free? limits | Fit / time | ToS / risk | Verdict |
|---|---|---|---|---|---|---|
| 1 | **Kiwi.com MCP** `https://mcp.kiwi.com` ([page](https://www.kiwi.com/ag/pages/mcp/), [write-up 27 Aug 2025](https://dev.to/alpic/behind-the-kiwicom-mcp-server-building-an-agentic-flight-booking-service-2pdd)) | Official remote MCP server. One read-only tool `search-flight` → price, times, airline, `bookingUrl` | Free, no key, no account. Rate limit not published | **Measured: DEL→BOM, INR, 15 results in 5.2 s**, ~9k tokens raw. Akasa, SpiceJet, IndiGo shown; Air India missing in this sample | Made for AI agents, so allowed. Price is Kiwi's own, not the airline's | **Use first** |
| 2 | Google Flights link `google.com/travel/flights?q=…` | Plain page fetch; prices are inside the HTML | Free, no key | **Measured: 200 OK, 1.5 s, 3.7 MB**, 19 ₹ prices, 4 Indian airlines | [Google terms](https://policies.google.com/terms) (India, 30 Jul 2026) ban automated access that breaks robots.txt; robots.txt blocks `/travel/flights/search` and `/booking`, not this path. Grey, unofficial | Use as the **link to open** (job 2); fetch only as a rare cross-check |
| 3 | [fast-flights](https://github.com/AWeirdDev/flights) (MIT, v3.0, 2.1k stars) | Builds Google's `tfs` protobuf URL and parses the page | Free | Not run here (no installs allowed) | Same grey area as #2; can break any day | Backup parser only |
| 4 | [SerpApi](https://serpapi.com/pricing) Google Flights | Paid scraper with a free plan | **250 searches/month, 50/hour** | Clean JSON; needs signup + key | Risk sits with SerpApi | Good cross-check if he wants a key |
| 5 | Travelpayouts / Aviasales Data API ([docs](https://travelpayouts-data-api.readthedocs.io/)) | Cached cheapest fares per route / month | Free token after affiliate signup; limits **(not verified, page blocked)** | Prices are cached (days old), default currency RUB | Meant for affiliate sites | Only for "cheapest day this month" |
| 6 | Amadeus Self-Service | Official GDS API | **Shut down 17 Jul 2026**; signups paused ([PhocusWire](https://www.phocuswire.com/amadeus-shut-down-self-service-apis-portal-developers), [AirLabs](https://airlabs.co/amadeus-self-service-api-shutdown); Amadeus' own page not readable) | — | — | Dead |
| 7 | Kiwi Tequila API | Old partner API | Invite-only since [30 May 2024](https://media.kiwi.com/articles-and-interviews/better-for-business-kiwi-com-takes-a-new-approach-to-partnerships/) | — | — | Closed |
| 8 | [Duffel](https://duffel.com/pricing) | Booking API for travel sellers | $3 per order; test mode is free but has [fake prices](https://duffel.com/docs/api/overview/test-mode) | — | For businesses | No |
| 9 | Skyscanner API | Partner API | Partners only (~100k monthly visitors, secondary source) | — | — | No |
| 10 | MakeMyTrip, ixigo, Cleartrip, EaseMyTrip | No public API or official MCP found. Feb 2026 OpenAI deals are for their own chatbots ([Skift](https://skift.com/2026/02/18/indian-otas-strike-deals-with-openai/)) | — | — | [ixigo terms](https://www.ixigo.com/about/terms-of-use/): no access "through a bot, script, or otherwise", no "spider, robot… scraper". MMT / Cleartrip / EaseMyTrip text **(not verified)** — assume the same | No scraping; open links only |
| 11 | Trains: IRCTC, ConfirmTkt, RailYatri | No free official API found; marketplace "IRCTC APIs" are unofficial | — | — | Railways deactivated ~3 crore suspect IDs and made Aadhaar OTP compulsory for Tatkal (Jul 2025, news reports); Delhi HC called RailYatri's unlicensed model "unauthorized" ([2019](https://inc42.com/buzz/delhi-high-court-rules-railyatri-operations-as-unauthorised-after-irctc-complaint)) | **Never automate.** Open the site/app only |
| 12 | Buses: redBus, AbhiBus | Partner-only APIs (secondary sources) | — | — | — | Open link only |

### B. Browser agents

| # | Option | How it works | Free? licence | Free cloud LLMs? | Evidence | Login / hand-off | Verdict |
|---|---|---|---|---|---|---|---|
| 1 | [Playwright MCP](https://github.com/microsoft/playwright-mcp) | Text accessibility snapshot, no vision; saved profile by default; `--extension` joins his running Chrome | Apache-2.0 | Any tool-calling model, but a snapshot is often 10–30k tokens and a task ~114k (blog reports) — Groq free is 8k tokens/min | README: "not a security boundary" | He logs in by hand in the saved profile | Good driver; snapshots must be trimmed |
| 2 | [Chrome DevTools MCP](https://developer.chrome.com/blog/chrome-devtools-mcp-debug-your-browser-session) | `--autoConnect` to his live Chrome (144+); Chrome asks permission each session and shows a banner | Apache-2.0 | Same | Exposes **all** tabs to the client | Uses his logins | Too much access |
| 3 | [browser-use](https://github.com/browser-use/browser-use) | Python agent loop: DOM + screenshot | MIT | Gemini, Groq by model string | Own claim 89.1% WebVoyager with GPT-4o ([Dec 2024](https://browser-use.com/posts/sota-technical-report); Google Flights 95%, ~36 steps). Independent: **30%** on Online-Mind2Web; **29% with Gemini 2.0 Flash**, best 40% ([HAL](https://hal.cs.princeton.edu/online_mind2web)) | `Browser('chrome')` uses his Chrome; secrets by placeholder; approval step is enterprise-only | Borrow ideas, not the loop |
| 4 | [Stagehand](https://github.com/browserbase/stagehand) | `act / observe / extract / agent`; code-first, LLM per step, self-heals | MIT; local Chrome OK | Gemini, Groq, Cerebras listed | ~7k input tokens per call (blog benchmark) | None built in | **Best pattern for step 3** |
| 5 | [Skyvern](https://github.com/Skyvern-AI/skyvern) | Vision LLM + planner + validator | AGPL-3.0; CAPTCHA/anti-bot cloud-only | Gemini, OpenRouter | Own claim 85.85% WebVoyager (GPT-4o, their cloud) | TOTP, password managers | Too heavy |
| 6 | [Nanobrowser](https://github.com/nanobrowser/nanobrowser) | Chrome extension in his logged-in Chrome | Apache-2.0 | Gemini, OpenRouter, OpenAI-compatible | No benchmark | Asks before submit; hands payments, passwords, codes to the user | Good manual fallback; not voice-driven |
| 7 | [Magentic-UI](https://github.com/microsoft/magentic-ui) ([paper](https://arxiv.org/abs/2507.22358)) | Co-planning, co-tasking, action guards; VM sandbox | MIT | Built around its own models (MagenticBrain, Fara) | No numbers on its page | Approve / take over any time | Ideas only |
| 8 | OpenAI Operator / CUA | Screenshot agent | Paid | — | Own 87% WebVoyager; **61.3%** Online-Mind2Web | "Takeover mode" for login, payment, CAPTCHA; asks before ordering | Ideas only |
| 9 | Anthropic computer use / [Claude for Chrome](https://claude.com/blog/claude-for-chrome) | Same | Paid | — | 56.3% Online-Mind2Web | Confirms purchases; blocks financial sites | Ideas only |
| 10 | [Agent-E](https://arxiv.org/abs/2407.13032) | Planner + browser agent, DOM distillation | Open source (licence not checked) | Not tested with free models | 73.2% WebVoyager, but **Google Flights 35.7%, Booking.com 27.3%, ~244 s, ~54 LLM calls** | — | Shows the real cost |
| 11 | [AgentQL](https://www.agentql.com/pricing) | Cloud finds elements from a query | 50 calls/month free | — | — | Page content leaves the Mac | No |
| 12 | [LaVague](https://github.com/lavague-ai/LaVague) | World model → Selenium/Playwright code | Apache-2.0; GPT-4o default; telemetry on | Unclear | Activity **(not verified)** | — | No |
| 13 | Research: [WebVoyager](https://arxiv.org/abs/2401.13919) 59.1% (2024) → [Online-Mind2Web](https://arxiv.org/abs/2504.01382) (2025) | 300 live tasks, human-judged | — | — | "Close to 90%" claims drop to ~30%; failed runs take ~2× the steps | — | Trust this, not vendor numbers |

### C. Which browser

- **His main Chrome profile:** Chrome 136+ ignores `--remote-debugging-port` on the default profile, to stop cookie theft
  ([Chrome blog, 17 Mar 2025](https://developer.chrome.com/blog/remote-debugging-port)). Chrome 144+ allows it with a permission
  dialog. It works, but the agent can then reach mail and bank tabs. No.
- **A separate saved profile** (`~/.stiti/browser/`, real Chrome, visible window): he logs in to the travel site once; cookies
  stay; nothing else is logged in. **Recommended.**
- **Fresh headless:** no session, login + OTP every time, most likely to be flagged. No.
- **Safari via AppleScript:** needs "Allow JavaScript from Apple Events" **(not verified today)**; no snapshot tools. No.
- RAM: browsers open on this Mac during research used ~1 GB (`ps`, rough). One extra Chrome tab: ~300–600 MB (estimate, not measured).

### D. Safety evidence

- Brave on Perplexity Comet ([20 Aug 2025](https://brave.com/blog/comet-prompt-injection/)): hidden text in a Reddit comment made the
  agent read an OTP from Gmail and post it.
- Guardio "Scamlexity" ([Aug 2025](https://guard.io/labs/scamlexity-we-put-agentic-ai-browsers-to-the-test-they-clicked-they-paid-they-failed)):
  an agent bought from a fake shop and auto-filled payment.
- Anthropic: 23.6% attack success, 11.2% after defences (123 cases). WASP ([arXiv:2504.18575](https://arxiv.org/abs/2504.18575)):
  attacks partly succeed in up to 86% of cases. EIA ([arXiv:2409.11295](https://arxiv.org/abs/2409.11295)): up to 70% success
  stealing personal details from form-filling agents. OpenAI (Dec 2025): prompt injection is "unlikely to ever be fully solved"
  ([TechCrunch](https://techcrunch.com/2025/12/22/openai-says-ai-browsers-may-always-be-vulnerable-to-prompt-injection-attacks/)).
- Amazon v. Perplexity: a March 2026 court order stopped Comet shopping inside Amazon accounts — the user's permission is
  not the site's permission ([The Decoder](https://the-decoder.com/amazon-gets-court-order-blocking-perplexitys-ai-shopping-agent/)).

### E. Crawling for later (brief)

| Tool | Licence | Notes | Verdict |
|---|---|---|---|
| [trafilatura](https://github.com/adbar/trafilatura) | Apache-2.0 (v1.8+) | HTML → clean text, no browser | **Default** |
| [Jina Reader](https://jina.ai/reader/) | hosted | 20 requests/min without a key; already in `live.read_url` | Keep as fallback (public URLs only) |
| [Crawl4AI](https://github.com/unclecode/crawl4ai) | Apache-2.0, v0.9.5 (14 Oct 2026) | Playwright Chromium, no LLM needed, memory-adaptive | On demand for JavaScript pages |
| Scrapy | BSD **(not re-checked)** | Many-page crawls, no browser | Only for big crawls |
| [Firecrawl](https://github.com/firecrawl/firecrawl) | AGPL-3.0 | Self-host is a multi-service Docker stack | Too heavy for 8 GB |

## 3. Recommended design, smallest first

**Step 1 — price lookup by voice (build now).**
- Parts: a small connector (suggested `connectors/travel.py`, same shape as `live.py`): rule-based intent → cities and date from
  `fastpath/dates` → one HTTPS call to Kiwi MCP. Registry tool `flight_prices`, `risk="read"`, `untrusted_output=True`.
  `mcp_bus.py` is stdio-only today, so call the endpoint directly (it answered plain JSON-RPC POSTs) or add HTTP transport.
- Flow: instant ack → ~5 s → template answer, no LLM: *"Delhi to Mumbai, 10 December. Cheapest around ₹7,100 on Akasa at 7:10 am.
  SpiceJet ₹7,350 at 5:40. Both non-stop, Kiwi's price. Open it?"* Cache 10 minutes.
- Privacy: only cities, date, passenger count leave the Mac. RAM: none.
- Fails when: speech-to-text mishears a city (so the route is said back first); Kiwi down or rate-limited (fallback: say so,
  open the Google Flights link); Kiwi's price differs from the airline's (same route today: Kiwi from ₹7,137, Google page showed
  strings from ₹6,551 — not parsed carefully, so always say "around").
- Reliability (my estimate): 90%+ correct answers. No LLM in the path.

**Step 2 — open pre-filled and hand over (build next; best value).**
- Parts: code builds the URL (Google Flights `?q=` link, Kiwi `bookingUrl`, later one deep link per site he uses, found by
  reverse-engineering). Tool `travel_open`, `risk="low"`, host allowlist; the URL is never taken from LLM or page text. Opens his
  normal browser with `open`.
- < 1 s, no extra RAM, no automation of any site → no ToS problem, no bot detection, his own logins.
- Fails when a site changes its URL format. Reliability ~99% for Google Flights / Kiwi.

**Step 3 — fill up to payment (pilot on one site, only after his answers).**
- Parts: Playwright (Python) driving real Chrome with the separate saved profile, visible window, started on demand as a
  background task that speaks progress and exits when done.
- Script first, LLM second (Stagehand's pattern): a recorded flow per site. The LLM is asked only when a selector fails, and only
  "which of these numbered elements is the Continue button?" on a trimmed snapshot (≤ 3k tokens, fits Groq's limit).
- Passenger details are typed by code from a local encrypted profile. The LLM sees placeholders, never names or phone numbers.
- Control (extends the registry's taint rule): he approves the plan **before** any page is read (route, date, flight, passenger,
  price cap). Page text can never add steps or new websites.
- **Hard stops in code, not in the prompt:** card / CVV / UPI / password / OTP fields, CAPTCHA, payment-gateway hosts, any
  host off the allowlist → freeze, speak, hand over.
- **Read-back before the last click:** name as on ID, route, date, time, airline, total, every paid add-on — read from the
  page by code and compared with the approved plan. Higher price or a new add-on → stop. Needs a fresh spoken "haan".
- Audit: a step log and screenshots in `~/.stiti/agent_runs/` (never of the payment page). No card data stored, ever.
- Time 1–3 minutes and RAM ~0.3–0.6 GB while running (both estimates, not measured).
- **Honest reliability:** a free-model general agent finishing an Indian booking flow — I estimate **10–25%**, 3–8 minutes
  (independent test: 29% with Gemini 2.0 Flash on mixed web tasks). Script-first on one site — maybe **70–85%** while the
  script is fresh; it breaks when the site changes. Login, OTP and CAPTCHA always need him.

## 4. What NOT to build

- **A general "do anything" browser agent on free models** — ~30% success in independent tests, and a reported 100k+ tokens per task against Groq's free 8k per minute.
- **Any IRCTC automation** — active bans and ID deactivation.
- **Scraping MakeMyTrip / ixigo / Cleartrip for prices** — terms forbid it; Kiwi is the allowed road.
- **CAPTCHA solvers, stealth plugins, proxies** — that is bypassing protections; it risks his accounts.
- **Driving his main Chrome profile** — one injected page could reach mail and bank.
- **Reading OTPs, storing cards / UPI PIN, clicking Pay** — never, even if asked later by a web page or a tool.
- **Amadeus, Tequila, Skyscanner, Duffel** — closed or business-only. **Skyvern, Magentic-UI, Firecrawl self-host** — too heavy
  for 8 GB. **Operator, Claude computer use, AgentQL beyond 50 calls** — paid.

## 5. Questions only Tejmul can answer

1. Which sites do you really book on — flights (airline site, MakeMyTrip, ixigo, Cleartrip?), trains, buses? Step 3 starts with one.
2. Is step 2 (page opens filled, you finish) enough for now, or do you want step 3 knowing it may break and may be against the site's terms?
3. OK to keep a **separate** Stiti Chrome profile that you log in to once? (Recommended over your main Chrome.)
4. Whose passenger details may Stiti store locally (you, family, friends)? Name as on ID, age, phone, email — anything else?
5. Is Kiwi's price good enough for "tell me the price", or do you want a second source (a free SerpApi key, 250 searches a month)?
6. Price rule: stop if the total is more than what Stiti quoted? Any absolute cap per booking?
7. Paid add-ons (seat, meal, insurance, "free cancellation"): always refuse, or ask each time?
8. Should Stiti stay silent while filling, or speak each step?
