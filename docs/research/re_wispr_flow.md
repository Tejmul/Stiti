# Reverse-engineering Wispr Flow (research, 2026-11-11)

**Question:** How does Wispr Flow (the best-known Mac dictation product) build its floating "Flow bar", its audio
pipeline, and its accuracy tricks, and what should Stiti copy for its own pill (`src/stiti/overlay/`, branch
`feat/desktop-overlay`), its STT biasing (`src/stiti/voice/stt.py`) and its voice loop (`src/stiti/voice/loop.py`)?
Feeds **D26** (overlay) and the STT/biasing decisions.

**Target:** `/Applications/Wispr Flow.app`, v**1.6.1400** (`Info.plist` `CFBundleShortVersionString`), installed by
Tejmul. Static analysis only: no network interception, the app was not modified or run, app storage and user data were
not opened, and no secrets were recorded. We learn the design here; no code is copied into Stiti.

## Method (rea + static reading)
| Step | Tool | Result |
|---|---|---|
| App inventory | `rea inspect_desktop_application` | Electron app, `Contents/Resources/app.asar` (139 MB), webpack bundles, native helper `swift-helper-app-dist/`, `fasttext/lid.176.ftz`, `migrations/` (SQLite via Sequelize), `assets/sounds/` |
| Fuses | `rea inspect_electron_fuses` | RunAsNode, NODE_OPTIONS and `--inspect` are **off**. Embedded ASAR integrity is **on**, so the bundle can be read but not changed |
| JS graph | `rea analyze_javascript_application` (`.webpack/renderer/overlay/index.js`) | 20 modules, 0 parse failures. rea also flagged 3 integrity mismatches on native `.node` files (`node_sqlite3.node`, `panel_activation.node`, the Jabra connector) |
| Source reading | `npx @electron/asar extract` into the scratchpad, then searches by symbol | Main: `.webpack/main/index.js` (10.6 MB). Bar UI: `.webpack/renderer/status/index.js`. Mic capture: `.webpack/renderer/hub/index.js`. Worklet: `.webpack/renderer/dist/recorderWorklet.js` |

Minified symbols are cited as `module-id → symbol`. They change between builds; the string literals stay the same.

## 1. The Flow bar (HUD)
**Window.** The bar is a **real Electron `BrowserWindow`, not a native NSPanel.** It is created in `main/index.js`
module `72413`, function `V` (title `"Flow Status Indicator"`):
`type:"panel"` (macOS), `transparent:true`, `backgroundColor:"#00000000"`, `frame:false`, `hasShadow:false`,
`roundedCorners:false`, `focusable:false` (unless the debug flag `allowBubbleFocus` is set), `skipTaskbar:true`,
`resizable/movable/minimizable/maximizable/closable/fullscreenable:false`, `alwaysOnTop:true`, `hiddenInMissionControl:true`,
and `backgroundThrottling:false`, so animations keep running while the window is in the background. After creation:
- `setAlwaysOnTop(true,"screen-saver")`. The level is set again on every show (`ee()`).
- `setVisibleOnAllWorkspaces(true,{visibleOnFullScreen:true, skipTransformProcessType:true})` (module `16815`, const `p`).
- The window appears with **`showInactive()`**, so it never takes focus. On the macOS 27 path, a native addon
  `panel_activation.node` → `preventActivation(handle)` makes the panel non-activating (feature flag
  `Macos27PanelNonactivation`).
- `setContentProtection(true)` is applied only when the user hides the meeting recorder from screen shares.
- Self-healing: when the window is `unresponsive`, auto-start is cancelled. On `render-process-gone`, it falls back to
  click-through. A post-wake refresh calls `webContents.invalidate()` and does a 1-px content-bounds "pulse"
  (`pe()`, 150 ms) to force a repaint.

**Size and position** (module `58601`). The window is a large, mostly transparent box, and the bar is drawn inside it:
- Bottom dock (default `statusDockEdge:"bottom"`): the window is **440 × 320**, centred horizontally on the work area,
  and its bottom edge sits on the work area's bottom, so the bar floats just above the Dock. Left/right docks use
  490 × 440, centred vertically. Top dock is not supported.
- The bar sits about 14 px above the window's bottom edge: `.hoverArea` has `margin:-6px 9px 8px` and `.hotArea` has
  `padding:6px 10px`.
- **Multi-display:** the bar follows the **display nearest the cursor**. `je = setInterval(Ue, 400)` re-reads
  `screen.getDisplayNearestPoint(getCursorScreenPoint())` every **400 ms**. If the window moved less than 100 px, the
  move is animated (`setContentBounds(s, animate)`). Across displays, the window drops to opacity 0, waits ≤ 600 ms
  (≤ 2 s per burst), and then fades back in (`Le`/`Pe`). Dock and menu-bar insets are computed from
  `bounds - workArea` (`c()`, `l()`).

**Click-through ("alpha hit-testing").** This is the cleverest part of the bar (module `16815`, function `C`, alias
`Bi`). The window normally uses `setIgnoreMouseEvents(true,{forward:true})`. Every **400 ms**, and on forwarded
`mouseMove` events (throttled to 50 ms), it runs `webContents.capturePage({x,y,1,1})` under the cursor. If the pixel's
alpha is `≤ threshold`, clicks pass through. Otherwise the window accepts the mouse. The threshold is 0, or 127 when
explicit "catch rects" exist. On Windows, `setShape(rects)` is used instead (class `s0`, at most 128 rects).
→ Only the visible pixels of the bar are clickable, while the window itself stays large enough for animations.

**States** (renderer `status`, module `54103` enum `fw`) and the **CSS geometry** of the bottom dock (CSS module
`31201`, `.thoughtBubble.*`):

| State | Size (w×h px) | Look |
|---|---|---|
| `resting` (idle) | **40 × 8** | `rgba(0,0,0,.5)`, 1 px `hsla(0,0%,100%,.5)` border, radius 6. Waveform hidden (opacity 0) |
| `ready` (hover) | 50 × 30 | `#30302f` (`--vast-900`), border `#5b5b59`, mic icon |
| `active_ptt` (holding key) | 73 × 30 | black capsule (`--shade-black #000`), 1 px `#30302f` border, radius **22.5** |
| `active_popo` (hands-free) | 102.5 × 30 | same, plus 18 × 18 round **cancel / stop** buttons (`.flowBarButton`) |
| `processing` | 98 × 30 | waveform + label. "Rainbow" variant: a `conic-gradient` ring that spins once every 6 s |
| `error` | 91 × 30 | 1.5 px `#ee6a6a` border |
| command / instruct mode | — | border/bars `#ffa946` (command) or `#ffbcf2` (instruct) |

The default morph between states is **`transition: all .1s cubic-bezier(0.05,0.6,0.4,0.95)`**, so it is fast with a
strong ease-out. Larger morphs use 250–400 ms `cubic-bezier(0.4,0,0.2,1)`, and the post-instruct pop is
280 ms `cubic-bezier(0.2,0.7,0.3,1)` from `scale(.9)`. Fades use 100–300 ms ease-out. `prefers-reduced-motion`
turns the bar animation off.

**Audio-level visualisation** is done with DOM and CSS transforms, not canvas or SVG (status bundle `Yi`, `dr`, CSS
module `60666`):
- **10 bars** (`barCount=10`), 2 px wide, `min-height:2px`, radius .5. Bar colour is `hsla(0,0%,100%,.4)`, and
  `#fff` once the mic delivers real audio (`micActive`).
- Static centre bulge per bar: `1 − d²·(1/48)`, where *d* is the distance from the centre.
- Idle shimmer: CSS keyframes, **1 s infinite ease-in-out**, scale ×1 → 1.2 (20 %) → 1.5 (40 %) → 1.1 (80 %) → 1.3 (90 %)
  → 1. Each bar is delayed by **0.1 s × signed index**, so a wave travels out from the centre.
- Final transform: `scaleY(--audio-scale × --bar-height-scale × keyframe)`, with
  `--audio-scale = max(1, gain·level)` and **gain 5** while dictating (2 in meetings).
- Level path (end to end):
  1. The worklet makes 40 ms blocks, and each block's RMS is converted to dBFS:
     `20·log10(rms+1e-10)` (`59719 → v`).
  2. In main, an **adaptive-floor scaler** (`59719 → E`, default floor −60 dB, range 20 dB): the floor tracks the
     quietest level heard, and `level = clamp((dB − floor)/20, 0, 1)`.
  3. Main averages the levels over a **150 ms** window, then sends them over IPC as `status:audioLevel`.
  4. In the renderer, smoothing is frame-rate independent: `a = 0.85^(dt/16.67 ms)`, `v = v·a + target·(1−a)`, with a
     **slew limit of 1.6 units/s**, rounded to 0.01. The loop stops when both values reach 0.
  5. The meeting-mode ticker runs at **20 fps** (`Ti=20`). The dictation path uses rAF only while there is a non-zero
     level.

## 2. Audio pipeline
- **Capture** (`hub` bundle, class `Pj`): `getUserMedia({audio:{echoCancellation:false, noiseSuppression:false,
  autoGainControl:false, sampleRate:16000, channelCount:1}})`. **All browser DSP is off**, so their ASR gets the raw
  voice. The `AudioContext` uses `{sampleRate:16000, latencyHint:"interactive"}`.
- **AudioWorklet** `dist/recorderWorklet.js` (`recorder-processor`) has `chunkSize=640` samples, i.e.
  **40 ms at 16 kHz** (`CHUNK_DURATION_MS=40`). Each chunk goes to main over IPC as `AudioChunk{packet, volume(dB)}`.
  WebCodecs also encodes the audio as **Opus 64 kbps** (`{codec:"opus",sampleRate:16000,numberOfChannels:1,bitrate:64e3}`).
  If no Opus data has arrived after 2 s, the app falls back to WAV.
- Hardening:
  - The worklet load is retried up to 3×.
  - `getUserMedia` gets a 3 s abort, and "Long getUserMedia wait" is logged after 100 ms. After 8 s the user gets the
    `MicAccessTimeout` notice.
  - The `AudioContext` is reloaded on stop when the start took more than 1 s.
- **Digital-silence watchdog (not a VAD).** A chunk counts as silent only when every sample is exactly 0, which means the
  mic is broken. 125 such chunks (**5 s**) trigger `NoAudioDuringDictation`, and 375 (**15 s**) escalate the notice.
  The warning clears as soon as real audio returns.
- **No client-side VAD and no auto-stop on silence.** The user ends dictation. Afterwards, `xn()` trims the
  speech region using chunks ≥ (adaptive floor + 3 dB), padded by 2 chunks on each side, which gives the "speech duration".
- **Push-to-talk vs hands-free** (module `59725`):
  - `DICTATION_DEBOUNCE_DELAY = 500 ms`. A press shorter than 500 ms is **not sent at all**, and the user sees a
    `Debounce` tip: "Hold down {shortcut} while speaking, release to see text."
  - The same 500 ms is the double-tap window. A double-tap gives hands-free "POPO" (press-on/press-off), with the
    `popo-lock.wav` sound.
  - Hold threshold for the scratchpad and extension keybinds: `SCRATCHPAD_PTT_DELAY_MS = 350`. Maximum dictation is
    **20 min**, with a warning at 19 min.
- **Transport:** gRPC streaming, then WebSocket (`wss://api.wisprflow.ai/`), then an HTTP fallback for audio ≤ 30 s.
  Audio is cut into 28 s chunks for their **Baseten**-hosted ASR.
  - Keepalive pings every 4 s, with a 2 s ping timeout and a 4 s response timeout before falling back.
  - **`GET /warmup` is fired on the first audio chunk**, which pre-warms the backend while the user is still speaking.
  - Every request records `e2eLatency` and per-component server timings.

## 3. Accuracy tricks
- **Each request carries rich context** (`serializeFlowRequest`, `main/index.js` ~offset 3.92 MB):
  - `context.app{name,bundle_id,type,url}`
  - `ax_context` (words parsed from the focused window's accessibility tree, collected by the Swift helper)
  - `ocr_context` (optional screen OCR)
  - `variable_names` and `file_names` (from the IDE)
  - `dictionary_context` (starred first, then personal, then team, capped at `48116 → D`)
  - `user_first_name` / `user_last_name`
  - `textbox_contents` (text before/after the cursor and the selection)
  - `content_text` (nearest on-screen text)
  - `personalization_style_settings`, `language[]`, and **`prev_asr_text` / `prev_llm_text` /
    `prev_detected_language`** (continuity with the previous utterance).
  - Context capture starts when the key goes down and runs **in parallel with recording**. If it isn't finished at
    release, the raw context is sent instead (`RawContext` / `NoContext` status). It never blocks.
- **Ranking the dictionary for the prompt** (`dictionary_stopwords.json` module):
  - Order: manual entries first, then recency buckets (≤ 1 day / ≤ 14 days / older), then the source rank
    (manual 0 < user-edits/meeting 1 < meeting summary 2 < app-context 3 < bulk import 4 < contacts 5), then usage
    frequency.
  - Usage counts are bumped whenever a phrase appears in output.
  - A remote stopword list blocks common words from being learned.
- **Learning from corrections:**
  1. After the paste, the native helper watches the text box until it sees an end signal (keystroke idle or focus
     change, `contentObservationEndReason`).
  2. The pasted text and the edited text are word-aligned (`parseAlignmentSteps(…,4)`). Substitution, insert and
     delete runs of ≤ 4 words become candidates (`k()`).
  3. Stopwords, already-known phrases, contractions and unsegmented CJK are dropped. Capitalised candidates are sorted
     first, and at most **4** go to a small LLM judge (`/llm/extract_edited_words`), which only accepts or rejects.
  4. Accepted words are saved with their **`observedSource`** (what the ASR heard) and `source: USER_EDITS`, and the
     app plays `achievement.wav`.
  - Words from the AX context that the user then typed are also learned (`APP_CONTEXT`).
  - The behaviour can be switched off (`shouldAutoLearnWords`, default on).
- **Post-processing runs server-side.** `/llm/formatting` uses a fine-tuned small model, chosen per app type
  (`openpipe:llama3-1-8b-…`, plus a separate email fine-tune). Other endpoints: `/llm/format_non_english`,
  `/llm/check_sensibility`, `/llm/command_mode`, `/llm/polish_text`.
  - The cleanup-level UI offers None / Light ("Removes filler words, cleans up grammar") / Medium (+ clarity) / High.
    Style is per app category: Formal / Casual / Very casual / Excited (for example, "line break after greeting").
  - **No formatting prompts ship in the bundle.** They live on the server, so there is nothing to summarise.
  - A rule classifier separates *dictation* rules (punctuation, filler words, verbatim) from *generation* rules
    (tone, length).
- **Language:**
  - A **local fastText `lid.176.ftz`** (WASM, SHA-pinned) labels text in 50-word batches. Non-English counts only at
    p ≥ 0.8. The app also counts non-Latin-script words and **romanized-Hindi lexicon hits** (`hindi_hits`), then
    sends this as `native_language_evidence` / `text_language_evidence`.
  - **Hinglish is a first-class language** (enum `HINGLISH=21`). The UI says "Want Hindi in English letters? →
    Switch to Hinglish", and the server can romanize transcripts. A `WrongLanguageSetting` nudge fires on mismatch.

## 4. Other things worth copying
- **Sound cues** (`assets/sounds/`, with several versions in `v1…v12`): `dictation-start.wav` **180 ms**,
  `dictation-stop.wav` **219 ms**, `popo-lock.wav` 165 ms, `paste.wav` 619 ms, `achievement.wav` 1.4 s. All are short
  and can be turned off (`enableSounds`). The app logs `start_sound_ms` against `recording_started_ms`.
- **Media ducking:** while dictating, the app mutes (`shouldMuteAudio`) or pauses (`shouldPauseAudio`) system media,
  with a 5 s grace period in meetings.
- **The error catalogue is a product feature.** Specific, actionable states, each with `maxTimesToShow` and
  `maxFrequencySeconds` rate limits:
  - `MicNotFound`, `MicDisconnected`, `NewMicDetected`, `MicSwitched`
  - `NoClamshellBuiltInMic` (lid closed but the built-in mic is selected)
  - `SuggestWiredMic` / `AudioQualityIssue`, `TranscriptionEmpty`, `NoInternet`
  - `SecureInputBlockingShortcuts`, `SuggestPasteLastText` (the paste failed, so the text is kept for re-paste)
  - `LowConfidenceStopPrompt`
- **Mic-permission onboarding:**
  - Permission status is polled every **1 s** while the permissions page is open. On grant, the app refocuses the hub
    and moves to the next step.
  - The flow only counts as complete when every permission is granted.
  - The 3 s probe `getUserMedia` opens the device and stops it straight away, which warms the device.
- **Telemetry for latency:** time to first audio chunk, warm-up chunks, speech start (ms), e2e latency and network
  overhead per request. Stiti's latency doc should log the same set.

## What Stiti should copy (mapped to our code)
| # | Copy this | Where in Stiti | Why |
|---|---|---|---|
| 1 | **Context-rich STT prompt:** owner name + top KG names (already done) **+ previous utterance (`prev_asr_text`) + frontmost app name + on-screen words via AX**, ranked manual > recent > learned > app-context, stopwords removed, capped | `voice/stt.py` `_bias_names()` / `_refresh_bias()`, prompt builder | Whisper's `initial_prompt` is our `dictionary_context`. Continuity with the last turn fixes split sentences |
| 2 | **Learn words from corrections:** when Tejmul repeats or corrects a name ("no, *Stiti*"), align the old and new text, take ≤ 4 substitutions, check them locally (Laya, not an LLM), and store `phrase + observedSource` in the KG/`LESSONS.md` as a bias term. Optionally add a `replacement` map for post-STT fixes | `voice/stt.py` + brain lessons / KG | This is the "corrections become permanent rules" principle, applied to the ears |
| 3 | **Local language-evidence counters:** romanized-Hindi lexicon hits + non-Latin-script count per turn, to choose the Hinglish prompt vs plain `en` (no fastText model needed; 0 MB) | `voice/hinglish.py`, `stt.py` | Same problem as Flow's `HINGLISH` mode, solved without a server |
| 4 | **Mic capture with OS DSP off** for STT (raw 16 kHz mono). Keep AEC only on the barge-in path | `voice/loop.py` / `duplex.py` capture | Their ASR works best on raw voice. Test it on our Whisper |
| 5 | **Digital-silence watchdog:** all-zero frames for 5 s → "your mic isn't sending sound", 15 s → escalate. Separate from the VAD | `voice/loop.py` | Catches a dead or muted device, which is a frequent silent failure |
| 6 | **Pre-warm on first speech:** start the LLM router's TLS connection/warm request when VAD fires, not after endpointing | `voice/loop.py` → router | Same trick as `GET /warmup`. Saves a cold-connection hop from the < 1 s budget |
| 7 | **Ignore < 500 ms blips:** don't send turns with less than 500 ms of speech. Show a gentle tip instead of "Sorry?" | `voice/endpoint.py` / `loop.py` (`REPROMPT`/`CLARIFY`) | Cuts false wakes and clarify loops |
| 8 | **Level pipeline for the pill:** dBFS → **adaptive floor** (start −60, range 20 dB) → 0..1 → frame-rate-independent EMA `0.85^(dt/16.7ms)` + slew limit, then **average over 150 ms** before crossing threads | overlay `model.py` `LevelSmoother` (today fixed `floor=0.004`, gain 9) | An adaptive floor makes the dots react the same way in a quiet room and a noisy one |
| 9 | **Pill motion recipe:** fast 100 ms state morphs with `cubic-bezier(0.05,0.6,0.4,0.95)`. Idle "breathing" = 1 s keyframes ×1→1.2→1.5→1.1→1.3→1, delayed 0.1 s per dot from the centre outwards. Static centre bulge `1 − d²/48`. `--audio-scale = max(1, 5·level)` | overlay `pill.py` `set_level`, `dot_scales()` | These are tested constants for a small bar that feels alive |
| 10 | **Tiny resting state:** collapse to a 40 × 8 translucent sliver when idle, and grow to full size on hover or wake | overlay `pill.py` (`show`/`collapse`) | Always present without being in the way |
| 11 | **Pixel-accurate click-through:** a large transparent panel with clicks enabled only over drawn pixels. Native version: override `hitTest_` to return `None` outside the pill path. No polling needed in AppKit | overlay `pill.py` `_PillView.hitTest_` | Room for card and expand animations without blocking clicks around the pill |
| 12 | **Follow the cursor's display** (poll ~400 ms). Fade out and in when changing displays. Re-assert the window level on every show. `showInactive` (= `orderFrontRegardless`). `canJoinAllSpaces` + full-screen auxiliary | overlay `surface.py` / `pill.py` `show()` | Flow uses the `screen-saver` level, so test it over full-screen video (our open item in `desktop_overlay.md`) |
| 13 | **Short sound cues** (~180 ms start / ~220 ms stop / ~165 ms lock). Log `start_sound_ms` vs mic-open | `voice/loop.py` wake chime | Under 250 ms, the cue doesn't delay speech |
| 14 | **Duck system media while listening** (pause Music/Spotify via MediaRemote or AppleScript), restore after | `voice/loop.py` | Clean STT input. Feels like Jarvis |
| 15 | **Rate-limited, specific error nudges** (`maxTimesToShow`, `maxFrequencySeconds`) | brain notifications / pill error state (red 1.5 px ring) | Users trust specific errors and get annoyed by repeated ones |

**Not to copy:** sending screen text, OCR or contacts to a cloud (Stiti keeps the AX/OCR words local and only puts names
into the local Whisper prompt). Electron/WebView for the pill: our measurements in `desktop_overlay.md` already show
Core Animation is far cheaper, and Flow needs a 400 ms alpha-capture poll precisely because it is a web view.
