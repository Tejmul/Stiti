# Where Stiti is against "Jarvis" — service audit (2026-11-18)

Everything below was run for real on the M2 (main @ f745737 + D41/D42), not read from the docs.

## 1. Tools the LLM can call (`tools/registry.py`, 18 tools: 11 read, 4 low, 2 write, 1 irreversible)
| Tool | Real call | Result |
|---|---|---|
| calendar_today / calendar_upcoming | yes | answers (0.7 s); empty list from a terminal process, the app has access |
| mail_unread / mail_search | yes | **not configured** (`MAIL_ADDRESS` / `MAIL_APP_PASSWORD` missing in `.env`) |
| files_find (Spotlight) | yes | works, 1.5 s |
| web_search | yes | works, 1.3 s — but results come from news feeds (a price query returned news articles) |
| web_read | yes | works, 3.1 s |
| live_news / research_papers | yes | work, 1.3 s / 0.2 s |
| screen_now / screen_read | yes | answer in 1.3 s / 1.8 s (very little text returned; screen permission not checked) |
| mac_open_app, mac_set_volume, music_control, file_open, imessage_send, calendar_create/cancel | not run (they change things) | untested this session |
MCP: `~/.stiti/mcp.json` does not exist → **zero MCP servers**. No browser tool, no GitHub, no mail sending.
LLM keys present: Groq, Z.ai, Cloudflare, OpenRouter, NVIDIA, Gemini. Missing: Cerebras, Mistral.

## 2. Twelve whole tasks through `Engine.turn` (text channel, throwaway DB, real free LLMs)
| Task | What happened | Verdict |
|---|---|---|
| Price of MacBook Air M5 in India | live-info path, 5.7 s, sourced answer | works |
| Latest AI news | live-info path, 1.8 s, three sourced headlines | works |
| Top trending GitHub repos | judged a "to-do"; no tool; **invented** a generic answer | wrong |
| Compare iPhone 17 vs Pixel 10 cameras | judged "feedback"; no search; answered from the model's memory | unsourced |
| Read a URL and summarise | judged "memory"; **page never read; summary invented** | wrong |
| Weather in Bengaluru | answered for Kolkata (city only parsed at the end of a sentence) | bug — fixed (branch fix/weather-city-anywhere) |
| Find three internships | the only task where a tool ran; **raw tool-call markup was the reply** (Z.ai model), 9.6 s | broken |
| Research free STT models, short report | one line from the model's memory, outdated | not a research task |
| Book a flight / add to Amazon cart / open GitHub PRs / send an email | honest "I can't" | no capability |
Score: 2 of 12 done properly, 4 honest refusals, 6 wrong/unsourced/broken. Tools were called in 1 of 12.

## 3. Root causes (all in the "agent core", see agent_core.md)
1. Tools are offered to the LLM only when the intent classifier says `tool` or a keyword regex fires; the classifier
   mislabels task sentences (to-do / feedback / memory), so the LLM answers without tools and makes things up.
2. A URL or "search / find / compare / research" in the sentence does not force a fetch before the LLM speaks.
3. The tool loop falls through to providers whose tool-call format isn't parsed (raw markup spoken).
4. No multi-step task state: one turn = one LLM call (≤ 3 tool rounds), nothing runs in the background and reports back.
5. No browser, no account connectors (GitHub, mail send), no MCP servers.
