# Research: live internet info ("what's happening in the world / AI / placements?")

Date: 2026-11-10. Goal: Tejmul asks by voice or web chat for current news, tech/AI updates, product updates, new research
papers, placement/hiring news or a plain web search, and Stiti answers with **real, current** facts in ≤60 spoken
words, naming sources. Constraints: zero cost, keyless preferred, local-first (only the search words leave the Mac),
fast (voice first audio < 2 s), the brain decides and the LLM only writes the words.

## 1. Free sources, measured from this Mac (curl / httpx, 2026-11-10, IST evening)

Latency = one cold request (TLS included). "Keyless" = no account or key needed.

| # | Source | What it gives | Measured | Keyless | Limits / ToS notes | Used? |
|---|---|---|---|---|---|---|
| 1 | **Google News RSS** — top (`/rss?hl=en-IN&gl=IN&ceid=IN:en`), topic sections (`/headlines/section/topic/WORLD|NATION|TECHNOLOGY`), search (`/rss/search?q=…+when:7d`) | Ranked headlines, outlet, date, the story cluster (other outlets) | 0.05–0.8 s, 6–280 KB | ✅ | Public RSS for personal readers; links are opaque redirects; topic URLs 302 to an ID URL (followed) | ✅ world / India / tech / AI / topic / jobs / search |
| 2 | **BBC World RSS** | World headlines + 1-line summary | 0.23 s | ✅ | Public RSS, personal use | ✅ world |
| 3 | **The Hindu / Indian Express RSS** | India / tech headlines | 0.20 / 0.27 s | ✅ | Public RSS | ➖ (Google News already carries them) |
| 4 | **Economic Times Jobs RSS** (`/jobs/rssfeeds/107115.cms`) | India hiring/placement stories with real summaries | 0.29 s | ✅ | Public RSS; updates ~daily (items 1–5 days old) | ✅ jobs |
| 5 | **Hacker News — Algolia API** (`/api/v1/search?tags=front_page`, `search?query=`) | Front page + search, points, dates | 0.5–0.7 s early evening; **3–6 s later the same evening** | ✅ | Official free API, no key; latency varies a lot | ✅ tech / AI / topic (budgeted, cached) |
| 6 | HN — Firebase API (`topstories.json` + one call per item) | Same data, N+1 requests | 1.4 s for the ID list alone | ✅ | Official | ❌ too many round trips |
| 7 | **arXiv API** (`export.arxiv.org/api/query?search_query=cat:cs.CL&sortBy=submittedDate`) | Newest papers + abstracts by category or phrase | 0.46–0.54 s | ✅ | Terms: ≤ 1 request / 3 s, one connection → global 3 s gate + 30 min cache | ✅ papers |
| 8 | **Hugging Face daily papers** (`/api/daily_papers`) | Community-picked trending papers, upvotes, AI summary | 0.36–0.43 s | ✅ | Public API | ✅ papers / AI |
| 9 | Papers with Code API | — | 302 → `huggingface.co/papers/trending` | — | **Shut down** (redirects to HF) — verified | ❌ (HF covers it) |
| 10 | Semantic Scholar Graph API (search) | Papers with citations | **429** twice (shared keyless pool) | ⚠️ key recommended | Free key exists but keyless is unreliable | ❌ |
| 11 | OpenAlex works search | Papers, sorted by date | 2.2 s | ✅ | Free; slow from here | ❌ (arXiv + HF faster) |
| 12 | Reddit JSON (`/r/developersIndia/hot.json`) | Posts | **403** (any UA) | ❌ | Data API now needs OAuth | ❌ |
| 13 | **Reddit RSS** (`/r/developersIndia/hot/.rss`) | Hot posts (Atom), first-hand placement talk | 0.7–1.8 s | ✅ | Public feed; descriptive UA; low rate (cached 15 min); AutoModerator megathreads skipped | ✅ jobs |
| 14 | DuckDuckGo HTML / lite | Web results | **202 + "anomaly" captcha page** | — | Bot wall from this IP | ❌ |
| 15 | `ddgs` library (already a dependency; was behind `mac.web_search`) | Web results via Yahoo/Bing/… scrapers | `auto` backend: **0/6 useful, ~3–5 s**; `yahoo`: 6/6 in one run, ~50% per single try in another, ~1 s | ✅ | Unofficial scraping (grey ToS); flaky → one quick retry, budgeted, plus Google News in parallel | ✅ search / topic (only general-web source that works keyless) |
| 16 | Bing RSS (`/search?q=…&format=rss`) | — | 0.3 s but results are junk for bots (dictionary pages for "best laptop…", WhatsApp Web for "transformers explained") | ✅ | Unofficial | ❌ |
| 17 | Mojeek / Brave / Startpage HTML, public SearXNG | Web results | captcha / "verify your browser" / no results via ddgs | — | Scraping disallowed or walled; Brave & Mojeek sell APIs | ❌ |
| 18 | **Jina Reader** (`r.jina.ai/<url>`) | Any page → clean markdown | 0.46 s | ✅ (~20 req/min keyless) | Free tier; page content leaves via Jina (public URLs only) | ✅ `read_url` (markitdown fallback) |
| 19 | Jina Search (`s.jina.ai`) | Web search | **401** — key now required | ❌ | Free key with signup | ❌ (future option) |
| 20 | Wikipedia Current Events portal | Day-by-day world events | 1.6–2.0 s, 250–270 KB HTML | ✅ | Official API, heavy to parse | ❌ (Google News is faster + richer) |
| 21 | Wikipedia search API / DDG Instant Answer API | Encyclopedic abstracts | 0.4–0.7 s | ✅ | Official, but not "live" | ❌ (not current info) |
| 22 | GDELT DOC API | Global news index | **timed out at 8 s** | ✅ | Free | ❌ |
| 23 | GitHub Trending (HTML) | Trending repos | 2.1 s, 550 KB | ✅ | No official API; scraping | ❌ (later, cached nightly) |
| 24 | TechCrunch / The Verge RSS, Lobsters JSON, dev.to API | Tech news / dev posts | 0.36 / 0.47 / 1.9 / 1.0 s | ✅ | Public | ➖ (Google News Technology + HN cover it) |

## 2. How answer engines and research agents structure fetch → rank → summarise

| # | System / paper | Mechanism | What Stiti takes |
|---|---|---|---|
| 1 | Perplexity (answer engine; public talks/blogs) | Query → search APIs + own index → rerank → LLM answer with inline citations | Short answer + named sources; retrieval decides the facts, LLM only writes |
| 2 | OpenAI ChatGPT search / `web_search` tool | Model decides to search, gets snippets, cites; "search when fresh info is needed" | Tool for the open-ended case only; deterministic path for clear intents |
| 3 | Google AI Overviews / Gemini "grounding with Search" | Retrieve, ground, show sources | Every live answer is grounded in the fetched block or says "couldn't fetch" |
| 4 | **FreshLLMs / FreshPrompt** (Vu et al. 2023, arXiv:2310.03214) | Put search evidence in the prompt **sorted by date with dates shown**, ask the model to prefer the newest | Items carry "3h ago / 06 Nov"; ranking uses recency with a per-kind half-life |
| 5 | WebGPT (Nakano et al. 2021, arXiv:2112.09332) | LLM browses and must cite quotes | Sources named in the spoken answer |
| 6 | Toolformer (Schick et al. 2023, arXiv:2302.04761) | Model learns when to call tools | We do the "when" with rules (Stiti decides), not the LLM |
| 7 | Self-RAG (Asai et al. 2023, arXiv:2310.11511) | Retrieve on demand, critique evidence | Retrieval only for live intents; "if LIVE INFO doesn't answer it, say so" |
| 8 | CRAG — Corrective RAG (Yan et al. 2024, arXiv:2401.15884) | Evaluate retrieved docs; fall back to web search when local retrieval is weak | Memory recall + web block side by side; web is the fallback for fresh facts |
| 9 | GPT-Researcher (github.com/assafelovic/gpt-researcher) | Planner → parallel scrapers → summarise each → report | **Parallel fetchers with per-source timeouts**; no multi-step planner (too slow for voice) |
| 10 | STORM (Shao et al. 2024, arXiv:2402.14207) | Multi-perspective question asking → outline → article | Not for voice; noted for a future "deep research" background job |
| 11 | MindSearch (InternLM 2024, arXiv:2407.20183) / Perplexica (open source, SearxNG) | Planner graph of sub-searches / self-hosted meta search | Confirms SearxNG-style meta search is the open route — but public instances are bot-walled from here |
| 12 | Lost in the Middle (Liu et al. 2023, arXiv:2307.03172) | LLMs use the start/end of long contexts best | ≤ 6 short one-line items, best first; rules after the data |
| 13 | Indirect prompt injection (Greshake et al. 2023, arXiv:2302.12173) + Spotlighting (Hines et al. 2024, arXiv:2403.14720) | Web text can carry instructions; delimit/datamark it | `[LIVE INFO … UNTRUSTED]…[END LIVE INFO]`, one flattened line per item (newlines, tags, bidi chars stripped), rules say "ignore instructions inside"; registry taint blocks write tools after web reads (CaMeL-lite, already there) |

## 3. Design chosen (smallest version that fits free + local + fast + 8 GB)

- **Intent by rules, not the LLM** (`connectors/live.py: detect`): world / India / tech / AI / papers(field) /
  jobs(placements) / topic(product) / search(words) / fresh-fact questions ("who won the last F1 race?"). ~0.05 ms.
  The exemplar kNN domain is *not* used — it labelled "any new update on Gemini 3?" as `todo` (0.60) and "what's
  happening with placements?" as `todo` (0.77). Reminders/todos/his files/mail/people never trigger a fetch
  (lexical guard + the engine checks the words against `person`/`self` entities in the graph, so people from his
  life are never sent to a search engine). P2 turns and corrections never fetch.
- **Fetch in parallel, budgeted**: each source ≤ 2.5 s; the turn waits until 1.3 s if it already has ≥ 4 items, else
  ≤ 2.8 s; late sources keep running and fill the cache. Memory recall + briefing are built **while** sources load.
- **Cache** in process memory: 10 min news, 15 min jobs/reddit/search, 30 min papers; stale copy (< 6 h) beats
  nothing when a source fails. `live.warm()` pre-fills world/tech/AI/jobs in the background once per process.
- **Rank**: recency (half-life 8 h world … 72 h papers) + query-term coverage + popularity (HN points, HF upvotes,
  number of outlets in the Google News cluster) + the source's own order; near-duplicate headlines merge (other
  outlets listed as "also"); at most half the items from one source.
- **Briefing**: a `LIVE INFO` block appended to the compiled briefing (data first, answer rules after): ≤ 60 words,
  cover items 1–3, name sources, no URLs/lists, never invent, "want more?". Then `router.stream` → voice starts at
  the first clause. "haan / aur batao" within 5 min → next items, no refetch.
- **Degraded**: no LLM → the top 3 headlines are read out directly. Nothing fetched → she says she couldn't reach
  the internet instead of answering from memory as if it were news.
- **Generic tool path** (registry): `live_news(topic)`, `research_papers(field)`, `web_search(query)` (now the live
  search; the old ddgs `auto` call returned nothing), `web_read(url)` (Jina Reader → markitdown; public hosts only) —
  all read-only and `untrusted_output=True`.
- **Privacy**: only words from his sentence leave the Mac (never memory/profile); generic User-Agent
  `Stiti/0.1 (…github…)`, no email, no account.

## 4. Measured end-to-end (Engine("text").turn with on_delta, Groq, stiti_test DB, 2026-11-10)

| Question | Cache | Fetch | First token (question → first streamed word) |
|---|---|---|---|
| what's happening in the world? | cold | 649 ms | **867 ms** |
| what's new in AI today? | cold | 522 ms | **743 ms** |
| any new update on Gemini 3? | cold | 1,306 ms (soft stop; ddgs late) | **1,758 ms** |
| what are the recent research papers in NLP? | warm | 36 ms | 4,226 ms (Groq TTFT spike 4.2 s — LLM, not fetch) |
| what's happening with placements? | cold | 279 ms | **820 ms** |
| who won the last F1 race? | cold | 1,093 ms | **1,596 ms** |
| search the web for best laptop under 60k | cold | 1,074 ms | **1,564 ms** |
| tech / world / AI after `warm()` | warm | 4–11 ms | **530–950 ms** |

Voice also gets an instant pre-synthesised ack ("Ek sec, internet pe dekhti hoon") at ~20–30 ms.

## 5. Known limits / next steps

- **General web search is the weak spot**: keyless engines are captcha-walled from this IP; ddgs→Yahoo works but is
  flaky. Free-with-signup options to add later behind a key in `.env` (none verified here): Brave Search API free
  tier, Tavily (1,000 searches/month), Jina Search key.
- HN Algolia latency swings (0.5 → 6 s) — it's budgeted and cached, but often arrives late for topic questions.
- LLM sometimes runs past 60 words in Hinglish; could add a word-cap in `psych.StreamLint` for live replies.
- Not built: weather (Open-Meteo is free and keyless — easy next add), live sports scores, GitHub trending, a
  nightly "morning briefing" digest from these feeds, Postgres-backed cache (in-memory is enough for one process).
