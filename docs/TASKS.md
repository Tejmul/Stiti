# Stiti — task list (started 2026-11-18)

One list of what is broken, in the order it gets fixed. A task is **done** only when its test passes AND Tejmul has
tried it by voice. Evidence for each: `docs/research/jarvis_gap_audit.md`.

Status: ✅ fixed + tested by code · 🎙️ needs his voice test · 🔧 being fixed · ⬜ open · 🙋 needs Tejmul

## A. She answers wrong (highest priority) — 12-task score: 2 of 12 before, 8 of 12 after D43 (the other 4 are honest "I can't yet")
| # | Problem | Status |
|---|---|---|
| A1 | Tasks that need the web are answered from the LLM's own memory or invented ("read this URL", "trending repos", "compare X and Y", "research …") | ✅ 🎙️ D43 `feat/fetch-first` |
| A2 | Raw tool-call code is spoken as the reply (Z.ai model in the tool loop) | ✅ 🎙️ D43 `feat/fetch-first` |
| A3 | After "haan" to a tool action she speaks the raw tool name + data; the rest of the plan is dropped | ✅ 🎙️ D43 `feat/fetch-first` |
| A4 | Web search returns news-feed results for ordinary questions (prices, how-to) | ✅ 🎙️ D43 `feat/fetch-first` |
| A6 | With no LLM reachable she reads raw page text aloud ("From Tomsguide: Specs Price & Release Design…") | ⬜ |
| A7 | "Research … give me a report" is still thin (one source); Hinglish task phrasing ("… compare karo") not covered | ⬜ |
| A5 | "Weather in Bengaluru, should I…" answered for the home city | ✅ 🎙️ `fix/weather-city-anywhere` |

## B. She hears wrong
| # | Problem | Status |
|---|---|---|
| B1 | 1 in 5 English turns written in Telugu script | ✅ 🎙️ D41 (Telugu check is opt-in) |
| B2 | Real accuracy on his voice has never been measured (no recordings) | 🙋 OK to turn on the local recorder? |
| B3 | Recogniser is the small local Whisper; large model only as a second opinion | ⬜ after B2 |
| B4 | Raw mic for the recogniser (today it gets echo-cancelled audio); learn words from corrections automatically | ⬜ after B2 |
| B5 | He wears AirPods: she listened on the headset mic (call-quality audio both ways) and macOS flipped the default mic back and forth → 4 reopens in a session | ✅ 🎙️ D45 `fix/mic-prefer-builtin` (listens on the Mac's own mic; headset keeps the sound) |
| B6 | Replies dropped because she answered before he finished (15 in one week) | ⬜ |
| B7 | She fell asleep while he was still talking (timer counted from her last reply; long speech was thrown away) | ✅ 🎙️ D47 |
| B8 | He could not tell whether she was hearing him | ✅ 🎙️ D47 live captions next to the orb (his words + hers) |
| B9 | "You shouldn't talk in Hindi" switched her into Hindi | ✅ 🎙️ D47 |
| B10 | A single misheard "yaar" (for "you're") flips her reply to Hinglish; the Hinglish prompt pulls English words toward Hindi | ⬜ |

## C. Whiteboard teacher
| # | Problem | Status |
|---|---|---|
| C1 | ~19 s of empty screen before a lesson starts | ✅ 🎙️ D42 (board first, plan while voice loads) |
| C2 | Three voices at once; she hears herself; doubts not answered; "Shall we continue?" spam | ✅ 🎙️ D40 |
| C3 | "end" did not end the lesson | ✅ 🎙️ D42 |
| C4 | A lesson loads a second copy of every voice model (+550 MB, ~7 s) → teach inside the app | ⬜ |
| C5 | Lesson writing waits on free-tier limits; the fastest lesson provider (Cerebras) has no key | 🙋 add `CEREBRAS_API_KEY` |
| C6 | Drawings are sparse (a title and two boxes) → arrays with pointers, trees, step traces | ⬜ |

## D. On screen
| # | Problem | Status |
|---|---|---|
| D1 | Cards are see-through grey: muddy and hard to read over any window | ✅ D44 solid dark panels — needs his eyes |
| D2 | The pill is a row of dots; the blue ring orb read as "Jarvis, not mine" | ✅ D46 his own orb (woven line + three points, indigo/amber), cards in the same colours, wake greeting — he picked it live; greeting + cards need his eyes |

## E. Memory
| # | Problem | Status |
|---|---|---|
| E1 | Junk already saved: both "Switch to Hindi" and "Switch to English" rules, "I said shut up…" as a boundary | 🙋 OK to remove? (rows shown first) |
| E2 | Learning from conversation (D38), "ask me questions" (D37), no-repeat (D36) | ✅ 🎙️ |

## F. Missing abilities (not bugs — the road to Jarvis; design in `docs/research/agent_core.md`)
| # | Ability | Status |
|---|---|---|
| F1 | Multi-step tasks that run in the background, ask before risky steps, report back | ⬜ after A |
| F2 | A browser she can drive (search, open, click, fill; stops at payment / OTP / passwords) | ⬜ after F1 |
| F3 | Accounts: GitHub, email (read + draft + send with his yes); mail is not configured at all | 🙋 keys / logins |
| F4 | One learned router instead of per-feature phrase lists | ⬜ |
| F5 | Pick free APIs from the public-apis list for the remaining gaps | ⬜ |
