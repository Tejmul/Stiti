# Desktop presence overlay + on-screen cards (research, 2026-11-11)

**Question:** When Tejmul says "Hey Stiti", what should appear on his desktop so he can *see* that she is hearing,
thinking, doing and speaking, and how should she show answers like his to-do list? It has to look premium and calm,
match Stiti's look (paper `#ecebf2`, navy `#262b57`, blue `#4656d6`, sky `#7fb2f0`, dot particles, white liquid-glass
pill), never take focus away from what he's doing, and stay cheap on an **M2 with 8 GB**. Everything stays on the Mac.
Proposed decision: **D26** (not recorded in `DECISIONS.md` yet; add it after Tejmul approves).

**Short answer:** a **native Core Animation pill** inside the rumps process: a borderless, non-activating `NSPanel` at
status-bar level, using macOS 26 `NSGlassEffectView` for the glass. It sits top-centre, just under the menu bar (or
hugging the notch on Macs that have one). Seven brand-coloured dots react to the mic level while he talks and to the
TTS level while she talks, and ripple while she thinks. It fades out when she goes back to sleep. Answers appear as
**cards** that drop out of the pill: a list on the same glass, where clicking an item ticks it off, Esc or a click
elsewhere closes it, and it closes by itself a few seconds after she finishes speaking. The card data is the typed
`Engine.last_card` that `cards.py` already builds. Measured cost: about 1 MB of RAM and about 1 % CPU in Stiti's
process, with no extra processes. A WKWebView version costs 40–53 MB, three extra WebKit processes and roughly 3× the
CPU while animating.

## Live measurements (this Mac, 2026-11-11 00:15–00:27 IST)
MacBook Pro 13" M2, 8 GB, macOS 26.3, one built-in display 1440×900 pt, **no notch**, PyObjC 13.0.
The prototypes are in the session scratchpad (`ca_pill.py`, `wk_pill.py`, `card_test.py`, `click_test.py`,
`orb_test.py`, `overlay_sketch.py`). Each phase ran 5–6 s. CPU is % of **one core**. Memory is `phys_footprint` (what
Activity Monitor calls "Memory"), read with `footprint`. A bare Python + AppKit process uses 33–35 MB. Stiti already
pays that inside rumps, so only the **delta** counts.

| Renderer (pill 168×40 pt) | Extra memory | Our process CPU: shown idle / listening (30 Hz RMS) / thinking | WebKit helper CPU (listening / thinking) | WindowServer CPU (listening / thinking) |
|---|---|---|---|---|
| **Core Animation + Liquid Glass, 60 fps** (2 runs) | **≈ +1 MB** (35 → 36), 0 helpers | 0.1–0.4 % / 0.8–1.4 % / 0.2–0.9 % | — | 24–26 % / 27–29 % |
| **Core Animation + Liquid Glass, capped at 30 fps** (2 runs) | ≈ +1 MB | 0.1 % / 0.5–1.1 % / 0.2–0.5 % | — | **14–17 % / 15–18 %** |
| Core Animation, plain white layer (no glass), 60 fps | ≈ +0 MB | 0.1 % / 0.8 % / 0.4 % | — | 20 % / 24 % |
| WKWebView canvas dot-sphere + Liquid Glass (rAF 60 fps, `evaluateJavaScript` at 30 Hz) | **+11 MB in-process + 29–42 MB in 3 helpers** (GPU, Networking, WebContent) | 0.1 % / 5.8 % / 1.9 % | 18.2 % / 7.1 % | 31.5 % / 23.9 % |
| WKWebView canvas, plain background | +9 MB + 29–42 MB | 0.2 % / 2.5 % / 2.0 % | 7.3 % / 7.3 % | 23.1 % / 23.5 % |
| Native 3D dot-sphere: 240 `CALayer`s in a `CATransformLayer`, 64 pt | ≈ +0 MB | 0.1 % spinning / 0.5 % + level | — | **38–40 %** at 60 fps, 22 % at 30 fps (too heavy) |

| Card test (5-item to-do list, WKWebView on glass, 360 pt wide) | Result |
|---|---|
| Cold start (create WKWebView → page "ready") | **771 / 906 / 982 / 2,257 ms**, plus one run that went over 2 s (process spawn) |
| `render(card)` → laid out | 69–132 ms first time, **22–32 ms** warm |
| Memory | +20–21 MB in-process, +32–33 MB helpers (≈ 53 MB total) |
| Real HID click on item 3 (key-capable panel) | `tick id=13` reached Python **on the main thread**; VS Code stayed frontmost |
| Esc after that click | card closed. After closing, Stiti was not active and had no key window, so focus went back to his app |
| Same click with `canBecomeKeyWindow = False` | tick received, panel never became key, Stiti never active, Esc impossible |

When nothing is visible the cost is zero. A hidden WKWebView whose page still asks for frames is throttled to
0.2–0.4 % helper CPU, but its ~30–40 MB stay resident.

**Caveat on the WindowServer numbers.** WindowServer serves the whole screen, so they are noisy: idle baselines were
0.4–6 % and one run had to be thrown out. The display then slept and locked at **00:27:55**, so three later checks are
**not valid** and are listed under "to verify":
1. the 30 fps plain-layer run (its idle-shown phase already read 14 %),
2. a one-layer **sprite-sheet orb** (96 pre-rendered frames animated with `contentsRect`), which read 0.2–5 % WindowServer,
3. a transform-only dot run, whose click test also failed.
Python CPU and memory don't depend on the display, so those numbers stand. While the display sleeps, Core Animation
animations and `animator()` fades do not advance (the sketch's alpha stayed at 0.0).

### Things the prototypes proved (or disproved)
1. **`setFloatingPanel_(True)` resets the window level to 3 (floating).** Set `setLevel_(NSStatusWindowLevel)` **after**
   it. Our first run was silently at level 3.
2. **Click-through works.** With `setIgnoresMouseEvents_(True)`, a real HID click landed on the window underneath.
   With `False`, the pill's own view got the click. In both cases the app stayed inactive and VS Code stayed frontmost
   (borderless + `NSWindowStyleMaskNonactivatingPanel`, verified 4×).
3. A bare `python` launch makes itself the active app at start-up. `Stiti.app` is `LSUIElement` (`install_app.py`), so
   this matters only for tests from the terminal: give focus back to the previous app first.
4. **WKWebView swallows the first click** in a window that isn't key (no tick event). A subclass whose
   `acceptsFirstMouse_` returns `True` fixes it (verified).
5. A non-activating panel that **can** become key becomes key only when clicked. From then on `NSApp.isActive()` reads
   `True`, but the frontmost app and the menu bar stay his. Esc works, and closing the panel gives the keyboard back.
6. **Thread marshalling works.** `PyObjCTools.AppHelper.callAfter` from a worker thread ran on the main thread 8/8
   times (`NSThread.isMainThread()`), including WKScriptMessageHandler callbacks. rumps runs `NSApp.run()`, so the same
   mechanism works inside Stiti.
7. **Scaling round dots into bars with a transform squashes the caps into ellipses** (seen in the rendered snapshot).
   Either keep **round dots that swell evenly**, which suits the particle look anyway, or change `bounds`, which costs a
   re-raster.
8. **Animating with `transform`/`opacity`/`contentsRect` keeps Python out of the frame loop.** Thinking as a
   `CABasicAnimation` uses 0.2 % Python CPU. Capping animations at 30 fps with `preferredFrameRateRange`, and drawing
   listening frames as discrete 30 Hz updates (`setDisableActions_`), cut WindowServer from about 25 % to about 15 %.
9. **CSS glass can't do this job.** `backdrop-filter` in a WKWebView only blurs page content, not the desktop behind
   the window, so real glass has to be a native `NSGlassEffectView` (PyObjC 13 exposes `NSGlassEffectView` and
   `NSGlassEffectContainerView`). A web page can only *sit on top of* native glass.
10. Settings read fine without any permission: Reduce Motion `False`, Reduce Transparency `False`.
    `NSScreen.safeAreaInsets().top` is `0` (no notch), and the menu bar is 30 pt (`visibleFrame` top 870 of 900).

## Design references (16 products/architectures)
"src" means the detail is from the sources below. "PK" means product knowledge that wasn't re-checked for this doc.

| # | Reference | Placement / size | States & how it shows sound | Captions | Appear / disappear | Focus & clicks | Lesson for Stiti |
|---|---|---|---|---|---|---|---|
| 1 | **macOS Siri** (Sequoia 15.1 → Tahoe) | Floating Siri window, top-right by default, can be moved (src) | Glowing edge while listening (src). Results replace the glow with a snippet card | "Type to Siri"; shows the answer, not a transcript, by default (PK) | Fast spring in; fades after the answer (PK) | Doesn't take over the screen; work continues (src) | Glow = "I'm listening", card = "here is the answer". **Two layers** |
| 2 | **macOS Tahoe 26.2 Edge Light** | Light border around the whole screen (src) | Static | — | **Fades when the cursor approaches the edge** (src) | Sits above windows | Get out of the way of the pointer: dim the pill on hover |
| 3 | **iPhone Apple Intelligence edge glow** + *EdgeGlow* (open-source Mac recreation) | Whole screen edge | Iridescent glow while Siri thinks (src) | — | Glow ripples in from the edges | Click-through | Full-screen glow is dramatic. Too loud for "calm" and costly on WindowServer. **Not used** |
| 4 | **Dynamic Island / Live Activities** (HIG) | Top-centre around the camera. Compact (leading + trailing), minimal (fits a 28 pt circle), expanded (src) | Live data in a small glyph | — | Morphs; "expanded should grow predictably from compact" (src) | Tap → app, long-press → expanded | **Pill = compact; card = expanded; same shape language** |
| 5 | **ChatGPT macOS voice** | Started as a floating window with an animated **orb** (Oct 2024); later voice moved inside the chat (src) | Orb moves with her voice (PK) | Transcript in the chat (src) | Window | It's a real window that takes focus | An orb is iconic, but a window is too heavy for "just show me you hear me" |
| 6 | **Gemini overlay / Live (Android)** | Bottom floating panel → full-width pill; 2026 "neural" design with **coloured dots** (src) | Glow; **waveform when voice is active** (src) | Text field + reply sheet | Glow sweeps in | Overlay over the current app (src) | Dots + waveform ≈ Stiti's particle identity |
| 7 | **Copilot Voice ("Hey Copilot")** | **Small floating mic UI near the bottom** (src) | Mic animation; **chime** on wake (src) | Short reply text | Ends on **X** or **after a few seconds of silence** (src) | Doesn't steal the app | Chime + small pill + auto-end on silence is exactly Stiti's loop |
| 8 | **Raycast AI / Notes** | Floating window above apps; "Always on Top"; changelog fixes for showing over **full-screen apps** and staying across **Spaces** (src) | — | Full chat | Hotkey; "Escape loses focus" setting (src) | Floats over the app without switching | Full-screen and Spaces behaviour is where floaters break: test it |
| 9 | **Superwhisper** recording window | **Mini window** by default (src) | **Waveform** while recording; **stop button appears on hover** (src) | Transcript pasted afterwards | Shows on hotkey, closes after processing | Doesn't take focus (pastes into the current app) | Hover shows the control, otherwise just the waveform |
| 10 | **Wispr Flow "Flow Bar"** | **Bottom-centre narrow pill**; dock to bottom/left/right, **top not supported** (src) | **White animated bars on a dark capsule** + a start ping (src) | None live | Pill grows on dictation | Cancel / Stop buttons during recording (src) | A narrow, always-there pill; users wanted to move it (PillFloat) |
| 11 | **Amazon Echo light ring** | Device ring | **Blue ring with a cyan arc pointing toward the speaker** = listening; spinning = thinking; **red = mic off**; yellow = notification (src) | — | — | — | One colour per state: **mic off/muted must look clearly different** |
| 12 | **Google Assistant / Nest** | Four dots (PK) | Dots bounce when idle-listening, **turn into a waveform with his voice**, spin while thinking (PK) | Live transcript on phones (PK) | Dots morph between states | — | Same dots, different motion per state: the closest match to our dots |
| 13 | **Rabbit R1 / Humane Ai Pin** | Small screen / laser projection | R1: **push-to-talk** + animated rabbit character; reviewers praised the animation's personality (src) | — | — | — | Personality lives in the idle motion; Humane's projector failed outdoors (src) |
| 14 | **Iron Man JARVIS HUD** (Cantina Creative / Jayse Hansen) | Full-view HUD | "Every HUD tells a story"; neutral ↔ battle mode as a choreographed spin (src) | Data callouts | Choreographed transitions | — | Borrow the **choreography**, not the clutter. Calm by default |
| 15 | **boring.notch** (open source, SwiftUI) | Notch | — | — | — | `NSPanel`: `isFloatingPanel`, clear background, level **`.mainMenu + 3`**, behaviour **`[.fullScreenAuxiliary, .stationary, .canJoinAllSpaces, .ignoresCycle]`**, `canBecomeKey = false` (source read) | Same recipe as ours |
| 16 | **DynamicNotchKit** (open source) | Notch, or a **floating style on screens without a notch** (`screen.hasNotch ? .notch : .floating`) | — | — | **Fade in 0.15 s ease-out** (source read) | `[.borderless, .nonactivatingPanel]`, `orderFrontRegardless` | Auto notch/floating fallback: this Mac has **no notch**, a future one might |

**Card references**, for the owner's to-do/reminder ask:
- **Dynamic Island expanded:** grows out of the compact pill and keeps its shape.
- **Siri result snippets:** a card with a short title and a few rows, plus the spoken answer.
- **Spotlight / Raycast results:** rows with a secondary column, keyboard-closable.
- **Google Assistant cards:** list or timeline cards with chips (PK).
Common rules across them: ≤ 5–6 rows, one title line, a muted "meta" column, the card grows out of the presence
indicator, and it goes away on Esc, on click-away or after a timeout.

## Rendering options
| Option | Mechanism | RAM (measured) | CPU while animating | Start-up | Effort / fit |
|---|---|---|---|---|---|
| **A. Core Animation layers in the rumps process** | `CALayer` dots; render-server animations; a 30 Hz `NSTimer` sets transforms | **+1 MB, 0 processes** | ~1 % ours + 15–18 % WindowServer @30 fps | instant | ✅ Best fit. Pure PyObjC, which Stiti already uses (rumps, Quartz, EventKit) |
| B. WKWebView in the panel (HTML/canvas, reuse the `particles.ts` look) | 3 WebKit XPC processes; `evaluateJavaScript` per level update | +40–53 MB | 6 % ours + 7–18 % helpers + 24–32 % WindowServer | **0.8–2.3 s cold** | 🟡 Great typography and fast iteration, but too heavy for an always-ready pill. OK for **rich cards** if pre-warmed at wake |
| C. SwiftUI helper app (like boring.notch) | Separate signed Swift process, IPC from Python | ~15–30 MB (estimate, not built) | low | process launch | 🟡 Best native polish (`glassEffect`, morphing), but adds a Swift toolchain, a second binary to sign/notarise, and IPC. Not v1 |
| Glass: `NSGlassEffectView` (macOS 26) | Real Liquid Glass composited by WindowServer | — | glass vs plain ≈ +4–5 % WindowServer | — | ✅ Use it; fall back to `NSVisualEffectView` (`.popover`) on macOS < 26 and to solid paper under Reduce Transparency |
| Glass: CSS `backdrop-filter` | Blurs page content only | — | — | — | ⛔ Can't blur the desktop |

## macOS technique checklist (PyObjC, verified unless marked)
- **Window:** create a `NSPanel` with style mask `Borderless | NonactivatingPanel`. Call `setFloatingPanel_(True)`
  first, then `setLevel_(NSStatusWindowLevel)` (25). `setOpaque_(False)`, `setBackgroundColor_(clearColor)`,
  `setHidesOnDeactivate_(False)`, and override `canBecomeKeyWindow` → `False` for the pill. Show it with
  `orderFrontRegardless()`, never `makeKeyAndOrderFront`.
- **Spaces / full screen:** `collectionBehavior = CanJoinAllSpaces | FullScreenAuxiliary | Stationary | IgnoresCycle`,
  the boring.notch recipe. Showing over a full-screen video was *not tested*. Apple forum reports say levels below
  `.screenSaver` can end up under full-screen content, so test that before choosing a higher level.
- **Click-through:** `setIgnoresMouseEvents_(True)` while idle-listening. Switch to `False` while a card is open, or
  while the pill offers stop/mute.
- **Click-away to close a card:** `NSEvent.addGlobalMonitorForEventsMatchingMask_handler_` for mouse-down. Mouse
  monitors need **no** permission. Global **key** monitors need Accessibility trust, which is why Esc instead works
  through a key-capable card (see the cards section).
- **Placement:**
  - Use `NSScreen.mainScreen()`, the screen with his key window, at wake time. Don't move the pill while it's visible.
  - y = `visibleFrame` top − 8 pt − height, i.e. under the menu bar. In a full-screen Space the menu bar is hidden,
    so this is the screen top.
  - If `safeAreaInsets().top > 0` (notch), hang the pill from the notch instead.
  - Centre it horizontally on `frame().midX`.
- **Threading:** the voice code never touches AppKit. Public methods wrap `AppHelper.callAfter(fn, *args)`, which is
  `performSelectorOnMainThread` underneath. Audio levels are two floats that the 30 Hz main-thread timer reads, with no
  per-frame queueing.
- **Privacy:**
  - `setSharingType_(NSWindowSharingNone)` keeps the pill and cards (his to-dos) out of screen shares and recordings
    (the call runs; whether shares actually skip it isn't verified).
  - Don't show anything while the session is locked (`CGSessionCopyCurrentDictionary()["CGSSessionScreenIsLocked"]`).
- **Accessibility:**
  - `NSWorkspace.accessibilityDisplayShouldReduceMotion` → no wave or swell, only opacity cross-fades and a brightness
    change for level.
  - `…ShouldReduceTransparency` → solid `#ecebf2` at 0.98 alpha instead of glass.
  - `…ShouldIncreaseContrast` → a 1 pt navy border.
  - Re-read them on `NSWorkspaceAccessibilityDisplayOptionsDidChangeNotification`.
- **Battery:**
  - Animate only `transform`/`opacity`/`contentsRect` and cap at 30 fps (`CAFrameRateRangeMake(15, 30, 30)`).
  - Run the timer only while listening or speaking. Order the panel out when idle.
  - If `NSProcessInfo.processInfo().isLowPowerModeEnabled()`, use 15 fps or the static style.
  - While asleep (wake-word listening) **nothing is on screen**, like Siri, Copilot and Alexa.

## Recommended design (D26 proposal)
**Placement and size:** top-centre, 8 pt under the menu bar.
- **Compact pill:** 168×40 pt, radius 20, white Liquid Glass with a 0.55 tint, soft shadow.
- **Wide pill** when she's doing something: up to 260×40 with an SF Symbol and a 2–3 word label, e.g.
  `calendar` "Checking calendar". The label is plain text with no text effects (UI rule).
- **Card:** 360 pt wide, drops 8 pt below the pill.

Seven 6 pt dots, coloured navy · blue · mid · sky · mid · blue · navy, are the "voice" of the pill. No orb in v1: the
240-layer orb was too heavy. A sprite-sheet orb can come back once its WindowServer cost is re-measured.

| State | Trigger in code | Visual | Motion / timing |
|---|---|---|---|
| asleep | wake-word listening (`awake == False`) | nothing on screen | — |
| **wake** | wake phrase detected (`run()`: `self.awake, self.silenced… = True`) | Dots bloom from the centre point outward (same idea as `particles.ts` `intro()`); rising chime plays | Panel fade + scale 0.92 → 1 in **180 ms ease-out** (DynamicNotchKit uses 150 ms); dots stagger 30 ms each |
| **listening** (awake, he's quiet) | after wake / after her reply, until `AWAKE_TIMEOUT_S` (20 s) | Dots breathe, alpha 0.6 → 1 | 0.4 Hz, ±10 % scale |
| **hearing** (he's talking) | `tt.busy` / VAD speech | Middle dots swell with **mic RMS** (navy → blue) | 30 Hz discrete updates; attack 0.35, release 0.12 smoothing |
| **thinking** | `_handle()` start → until first audio | Travelling ripple left → right, tinted sky | Render-server keyframes, 0.6 s autoreverse, 90 ms stagger, 30 fps |
| **doing** | `on_ack(kind)` (calendar, mail, web, plan, tools) | Pill widens 168 → 240 pt in 250 ms; symbol + label ("Checking calendar"); ripple continues | 250 ms ease-out width morph |
| **speaking** | Speaker `on_first_audio` → until playback drains | Dots swell with **TTS output RMS** (blue → sky), mirrored | 30 Hz |
| **card** | `engine.last_card` is not `None` | Card drops out of the pill (see below) | 320 ms `cubic-bezier(.16,1,.3,1)` (the web `--out` token) |
| **done → sleep** | `AWAKE_TIMEOUT_S` expiry (`💤` branch) | Dots collapse to the centre; pill fades | 350 ms fade + 4 pt rise; then `orderOut` |
| **stopped** | `deactivate()` (stop words) | Dots drop and fade with the falling chime | 250 ms |
| **muted** | menubar "Listening" off (`paused`) | Grey dots + a mic-slash glyph shown once for 1.2 s, then hidden (Alexa "red = mic off") | — |
| **offline / error** | `[turn]` exception, or every LLM provider down | One amber dot (`#b4531f`) for 1.5 s while she says the fallback | — |
| **alarm ringing** | `ring_control` set | Card with **Stop** / **+5 min** buttons | stays until handled |

- **Captions: off by default.** Tejmul's rule is never to show his conversations in the UI. An opt-in one-line caption
  of *her* sentence (14 pt, under the pill, never stored, kept out of screen sharing) can be a setting later. Cards show
  **data from the brain** (lists), not chat.
- **Focus:** the pill never becomes key. It is click-through while hearing, so it can't eat a click aimed at the menu
  bar. Hovering over it fades it to 35 % (Edge Light behaviour; a global mouse-moved monitor needs no permission).
- **Click to stop / mute:** while she speaks or thinks, clicking the pill does what the turn-taker's `stop` event does
  (`_interrupted.set()` + `duplex.stop_playback()`); hovering shows a small ✕ (Superwhisper pattern). Option-click
  toggles mute (`loop.paused`). While awake the pill accepts clicks; it's only 168×40 pt.
- **Multi-display:** show on `NSScreen.mainScreen()` at wake and stay there for the session.

## On-screen cards (owner's extra ask: "show my to-do list while she says it")
**Data flow (on-device only, no network, no server):**
```
engine.turn() ──► cards.for_turn(...) ──► Engine.last_card  (already built: kind/title/items[id,text,meta]/ts)
      │                                       │
voice thread: _handle().work() after turn() ──► ui.card(card)      # AppHelper.callAfter → main thread
      │                                                             # card shows while she starts saying it
overlay click "tick id=13" ──► ui.on_action("todos", 13, "done") ──► worker thread ──► brain write (tasks.status='done')
                                                                   └► optimistic ✓ in the card; revert if the write fails
```
The card is built from the brain (Postgres), never from the LLM's words: the D8 principle that `cards.py` already
follows. The overlay only receives a plain dict. Proposed additions to the schema:
- `"actions": ["tick"|"open"|"cancel"]`
- per-item `"done"` (bool) and `"url"` (news only; opened in the browser when clicked; the overlay itself never fetches)
- `"progress"` (crash course)
- two new kinds: `calendar` and `course`.

| Kind (`cards.py`) | Trigger | Layout | Size | Interaction | Auto-close |
|---|---|---|---|---|---|
| `todos` | "what's on my to-do list" | Mono label "TODAY · 5 TO DO", title "You have these to finish", ≤ 6 rows of ○ text · due chip, then "+3 more" | 360 × ~287 pt for 5 rows (measured) | **Click row = tick**: ✓ fills blue `#4656d6`, strike-through, optimistic | speech end + 4 s + 1.2 s × rows, ≤ 15 s; paused while hovered |
| `todo_added` / `reminder_set` | "add …" / "remind me at 4 to start resume" | **No card.** The pill widens into a confirmation, like a Dynamic Island compact view: `✓ Start resume · 4:00 PM` | 300×44 pt | Click = undo (2 s window) | 2.5 s after speech |
| `reminders` | "what's coming up" | Rows of time (mono, left column) · text · "repeats" | 360 pt | Hover ✕ = cancel (asks "cancel it?" by voice) | as `todos` |
| `calendar` *(new)* | "what's on my calendar today" (`eventkit.today_events`) | Timeline rows: time · coloured calendar dot · title · location | 360 pt, ≤ 6 rows | Click = open in Calendar.app | as `todos` |
| `news` | live headlines (`connectors/live.py`) | Headline (2-line clamp) · source in mono | 380 pt, 4 rows | Click = open the link in the browser | speech end + 8 s |
| `course` *(new)* | crash-course progress | Progress ring + "Lesson 3 of 8 · 40 %" + "Next: …" | 360×120 pt | Click "Continue" = start the lesson by voice | speech end + 6 s |

**Closing a card:**
- Esc. The card panel is *key-capable*, so the first click on it makes it key (verified: his app stays frontmost, and
  focus returns when the card closes).
- Clicking anywhere else (global mouse-down monitor).
- Saying "okay" / "theek hai" / "close it".
- The timer, which **starts when her speech ends**, not when the card appears.
- A new turn replaces the card in place: no stacking, no history (UI rule).

**Renderer for cards:** native AppKit rows on the same glass in v1: `NSTextField` labels plus a `CALayer` checkbox,
with SF Pro / SF Mono, because the web fonts aren't bundled locally. That means no cold start and no helper processes.
If richer cards later justify WKWebView (images, charts), **pre-warm it on wake**: wake + chime + his question take
> 1.5 s, which covers the 0.8–2.3 s cold start. Release it about 60 s after she sleeps, so the ~53 MB is only paid while
awake. Use the `acceptsFirstMouse_` subclass and `loadHTMLString_baseURL_(html, None)` with no remote URLs. A
`WKContentRuleList` that blocks `http(s)` makes "no network" enforced, not just promised.

## Hooking into the voice loop (no code changed in this research)
| Where | Call |
|---|---|
| `Duplex._cb` (`voice/duplex.py`) | `self.mic_rms = float(np.sqrt(np.mean(mic*mic)))` and `self.out_rms = …(out)`: two floats per 10 ms block (microseconds of work) |
| `VoiceLoop.__init__` | `self.ui = None` (set by `StitiApp._boot` once the overlay exists; `None` in terminal mode) |
| `run()`: wake branch, before `_chime(up=True)` | `ui.state("wake")` |
| `run()`: `💤` timeout branch | `ui.state("hidden")` |
| `deactivate()` | `ui.state("stopped")` |
| `_handle()` start | `ui.state("thinking")` |
| `Speaker(..., on_first_audio=…)` | also call `ui.state("speaking")` |
| `sp.ack` (on_ack) | `ui.state("doing", kind)` |
| `_handle().work()`, right after `engine.turn()` returns | `if self.engine.last_card: ui.card(self.engine.last_card)` |
| end of `_handle()` | `ui.state("listening")`; `ui.speech_ended()` starts card auto-close |
| `StitiApp.toggle_listen` / `_ring` | `ui.state("muted")` / `ui.card(alarm_card)` |
| hearing vs listening | derived in the 30 Hz tick from `loop.tt.busy` + `duplex.mic_rms`, so no extra hook |

## Minimal working sketch (PyObjC). Ran on this Mac
The panel settings below are the same ones verified on screen (level 25, alpha 1, on screen; click-through ON lets a
real click pass, OFF lets the pill take it; app never activated) in `ca_pill.py` and `click_test.py` while the display
was on. The sketch file itself ran cleanly at 00:31: window at level 25, `ignoresMouseEvents == True`, state machine
on the main thread. The display had slept by then, so its fade-in wasn't checked by eye.
```python
import AppKit, objc, Quartz
from Foundation import NSObject, NSTimer
from PyObjCTools import AppHelper

W, H, N, DOT, GAP = 168, 40, 7, 6, 7
COLS = [(0x26,0x2B,0x57),(0x46,0x56,0xD6),(0x62,0x84,0xE3),(0x7F,0xB2,0xF0),(0x62,0x84,0xE3),(0x46,0x56,0xD6),(0x26,0x2B,0x57)]

class _Panel(AppKit.NSPanel):
    def canBecomeKeyWindow(self): return False          # the pill never takes the keyboard
    def canBecomeMainWindow(self): return False

class Pill(NSObject):
    def initWithLevels_(self, levels):                   # levels() -> (mic_rms, tts_rms)
        self = objc.super(Pill, self).init()
        self.levels, self.mode, self.timer = levels, "hidden", None
        p = _Panel.alloc().initWithContentRect_styleMask_backing_defer_(((0, 0), (W, H)),
            AppKit.NSWindowStyleMaskBorderless | AppKit.NSWindowStyleMaskNonactivatingPanel, AppKit.NSBackingStoreBuffered, False)
        p.setFloatingPanel_(True)                        # resets level to 3 …
        p.setLevel_(AppKit.NSStatusWindowLevel)          # … so set 25 AFTER it
        p.setCollectionBehavior_(AppKit.NSWindowCollectionBehaviorCanJoinAllSpaces | AppKit.NSWindowCollectionBehaviorFullScreenAuxiliary
                                 | AppKit.NSWindowCollectionBehaviorStationary | AppKit.NSWindowCollectionBehaviorIgnoresCycle)
        p.setOpaque_(False); p.setBackgroundColor_(AppKit.NSColor.clearColor()); p.setHasShadow_(True)
        p.setIgnoresMouseEvents_(True)                   # click-through
        p.setHidesOnDeactivate_(False); p.setSharingType_(AppKit.NSWindowSharingNone); p.setAlphaValue_(0.0)
        glass = AppKit.NSGlassEffectView.alloc().initWithFrame_(((0, 0), (W, H)))   # macOS 26; else NSVisualEffectView
        glass.setCornerRadius_(H / 2); glass.setTintColor_(AppKit.NSColor.colorWithWhite_alpha_(1.0, 0.55))
        host = AppKit.NSView.alloc().initWithFrame_(((0, 0), (W, H))); host.setWantsLayer_(True)
        glass.setContentView_(host); p.setContentView_(glass)
        x0, self.dots = (W - (N * DOT + (N - 1) * GAP)) / 2, []
        for i, c in enumerate(COLS):
            d = Quartz.CALayer.layer(); d.setBounds_(((0, 0), (DOT, DOT))); d.setCornerRadius_(DOT / 2)
            d.setPosition_((x0 + i * (DOT + GAP) + DOT / 2, H / 2))
            d.setBackgroundColor_(Quartz.CGColorCreateGenericRGB(c[0]/255, c[1]/255, c[2]/255, 1))
            host.layer().addSublayer_(d); self.dots.append(d)
        self.panel = p
        return self

    @objc.python_method
    def state(self, mode):                               # safe from ANY thread (voice loop)
        AppHelper.callAfter(self._apply, mode)

    @objc.python_method
    def _apply(self, mode):                              # main thread only
        prev, self.mode = self.mode, mode
        if self.timer: self.timer.invalidate(); self.timer = None
        for d in self.dots: d.removeAllAnimations(); d.setTransform_(Quartz.CATransform3DIdentity)
        if mode == "hidden":
            self._fade(0.0, 0.35); AppHelper.callLater(0.4, lambda: self.mode == "hidden" and self.panel.orderOut_(None)); return
        if prev == "hidden":
            s = AppKit.NSScreen.mainScreen(); f, vf = s.frame(), s.visibleFrame()
            top = vf.origin.y + vf.size.height if s.safeAreaInsets().top == 0 else f.origin.y + f.size.height - s.safeAreaInsets().top
            self.panel.setFrameOrigin_((f.origin.x + (f.size.width - W) / 2, top - 8 - H))
            self.panel.orderFrontRegardless(); self._fade(1.0, 0.18)       # shows WITHOUT activating Stiti
        if mode in ("listening", "speaking"):
            self.timer = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(1/30, self, "tick:", None, True)
        elif mode == "thinking":                         # render-server animation: no Python per frame
            t0 = Quartz.CACurrentMediaTime()
            for i, d in enumerate(self.dots):
                a = Quartz.CABasicAnimation.animationWithKeyPath_("transform.translation.y")
                a.setFromValue_(-3.0); a.setToValue_(3.0); a.setDuration_(0.6); a.setAutoreverses_(True)
                a.setRepeatCount_(1e9); a.setBeginTime_(t0 + i * 0.09)
                a.setPreferredFrameRateRange_(Quartz.CAFrameRateRangeMake(15, 30, 30))
                d.addAnimation_forKey_(a, "wave")

    @objc.python_method
    def _fade(self, alpha, secs):
        AppKit.NSAnimationContext.beginGrouping(); AppKit.NSAnimationContext.currentContext().setDuration_(secs)
        self.panel.animator().setAlphaValue_(alpha); AppKit.NSAnimationContext.endGrouping()

    def tick_(self, _):                                  # 30 Hz, transform-only, discrete (no 60 fps tweening)
        mic, tts = self.levels()
        lv = min(1.0, (mic if self.mode == "listening" else tts) * 8)
        Quartz.CATransaction.begin(); Quartz.CATransaction.setDisableActions_(True)
        for i, d in enumerate(self.dots):
            k = 1 + lv * 1.2 * (1 - abs(i - (N - 1) / 2) / N)
            d.setTransform_(Quartz.CATransform3DMakeScale(k, k, 1))   # round dots swell (bars would squash)
        Quartz.CATransaction.commit()

# in StitiApp._boot (rumps already runs NSApp on the main thread):
#   pill = Pill.alloc().initWithLevels_(lambda: (d.mic_rms, d.out_rms));  loop.ui = pill
```
**Card panel differences (verified in `card_test.py`):**
- `canBecomeKeyWindow` → `True` with `setBecomesKeyOnlyIfNeeded_(False)`, so the first click makes it key and Esc works.
- `setIgnoresMouseEvents_(False)`.
- If WKWebView is used, subclass it to return `True` from `acceptsFirstMouse_`.
- `WKScriptMessageHandler` sends `{type: "tick", id}` back, and it arrives on the main thread. Hand the DB write to a
  worker thread.

## To verify before building (honest gaps)
1. The WindowServer cost of the 30 fps plain-layer pill, the **sprite-sheet orb** and transform-only dots, re-measured
   with the display awake (the earlier runs were invalidated when the display slept). Run each 3×.
2. Showing over a **full-screen video**/Keynote with level 25 + `FullScreenAuxiliary` (Apple forum reports suggest
   that may need `NSScreenSaverWindowLevel`), across Spaces, and on a second monitor.
3. A notch Mac: the pill hanging from the notch (the `safeAreaInsets`/`auxiliaryTopLeftArea` maths).
4. `NSGlassEffectContainerView` *morph* between pill and card, so the two glass shapes merge like liquid. That would be
   the premium Dynamic-Island moment; untested.
5. Whether `setSharingType_(NSWindowSharingNone)` still hides the window from ScreenCaptureKit captures (Zoom/Meet)
   on macOS 26.
6. Caption policy: confirm with Tejmul that an opt-in caption of *her* line doesn't break the "no conversations in UI"
   rule.

## Sources
- Apple, Live Activities HIG (compact/minimal/expanded, 28 pt): https://developer.apple.com/design/human-interface-guidelines/live-activities
- macOS Sequoia 15.1 Siri redesign (glow; movable window): https://www.macrumors.com/2024/10/28/new-features-macos-sequoia-next-week/ ·
  https://appleinsider.com/articles/24/10/28/apple-intelligence-arrives-on-the-mac-with-macos-sequoia-update
- macOS Tahoe 26.2 Edge Light (fades near the cursor): https://www.macrumors.com/2025/11/12/apple-macos-tahoe-26-2-edge-light/ ·
  https://support.apple.com/en-la/125934
- EdgeGlow (Apple Intelligence glow recreated on Mac): https://dev.to/vector4wang/i-recreated-iphones-apple-intelligence-edge-glow-effect-on-mac-57f5
- ChatGPT desktop voice (orb, later moved into chat): https://help.openai.com/en/articles/9703738-macos-app-release-notes ·
  https://www.macrumors.com/2025/11/26/chatgpt-voice-mode-update-seamless-chat/ ·
  https://testingcatalog.com/chatgpt-desktop-adds-advanced-voice-mode-prepares-to-launch-voice-clips
- Gemini overlay glow / waveform / "neural" dots: https://9to5google.com/2024/08/17/gemini-glow-floating-overlay/ ·
  https://9to5google.com/2025/01/20/gemini-overlay-redesign-beta/ · https://androidauthority.com/gemini-overlay-live-neural-design-apk-teardown-3690991/
- Copilot Voice "Hey Copilot" (floating mic UI, chime, X / silence ends): https://blogs.windows.com/windows-insider/2025/05/14/copilot-on-windows-hey-copilot-begins-rolling-out-to-windows-insiders/ ·
  https://pureinfotech.com/enable-disable-hey-copilot-windows-11/
- Raycast changelog (floating over full-screen apps, Spaces, Always on Top): https://www.raycast.com/changelog/macos/0-53 ·
  https://www.raycast.com/changelog/macos/0-71 · https://www.raycast.com/core-features/ai
- Superwhisper recording window (mini mode, waveform, hover stop): https://superwhisper.com/docs/get-started/interface-rec-window ·
  https://superwhisper.com/changelog
- Wispr Flow bar (bottom pill, docking, no top): https://docs.wisprflow.ai/articles/1790396454-move-and-dock-the-flow-bar-on-desktop ·
  https://cdn.jsdelivr.net/npm/@agent-native/core@0.124.6/corpus/templates/clips/desktop/design-refs/wispr-ux.md · https://github.com/orangeaka/pillfloat
- Echo light ring meanings: https://www.androidauthority.com/alexa-ring-color-meanings-1085725/ · https://gizmodo.com/amazon-echo-colors-meaning-1848775533
- Rabbit R1 / Humane: https://www.engadget.com/rabbit-r1-hands-on-already-more-fun-and-accessible-than-the-humane-ai-pin-163622560.html ·
  https://spectrum.ieee.org/ai-gadgets-2024
- Iron Man HUD (Cantina Creative, Jayse Hansen): https://www.provideocoalition.com/marvels_the_avengers_taking_the_hud_to_new_heights/ ·
  https://www.creativebloq.com/3d/cinema-4d-secrets-iron-mans-interface-61515419
- boring.notch window source (read): https://github.com/TheBoredTeam/boring.notch/blob/main/boringNotch/components/Notch/BoringNotchWindow.swift
- DynamicNotchKit source (read: nonactivating panel, notch/floating, 0.15 s fade): https://github.com/MrKai77/DynamicNotchKit
- Floating-panel / full-screen level reports: https://developer.apple.com/forums/thread/826308 · https://cindori.com/developer/floating-panel ·
  https://github.com/mitchchn/FunWithPanels
- Global event monitors (key events need Accessibility; mouse don't): https://developer.apple.com/library/mac/documentation/cocoa/conceptual/eventoverview/MonitoringEvents/MonitoringEvents.html ·
  https://kaweah.freedombox.rocks/kiwix/content/stackoverflow.com_en_all_2023-11/a/49718389
- First-mouse / click-through for inactive windows: https://christiantietze.de/posts/2024/04/enable-swiftui-button-click-through-inactive-windows ·
  https://webkit.googlesource.com/WebKit/+/bba8387a032405c9c4086ae920136c1f2a7fad08/Source/WebKit/UIProcess/API/mac/WKWebViewMac.mm
- `NSGlassEffectView` usage (style, tint, cornerRadius, contentView): https://docs.rs/crate/rio-window/0.5.14/source/src/platform_impl/macos/glass.rs
