# AI Whiteboard Tutor: Technology Research for Stiti

Research date: 2026-11-10. Target: Stiti teaches a topic or a book in about 30 minutes. It speaks with local Kokoro TTS while drawing text, boxes, arrows and highlights on a whiteboard in the owner's browser. The owner can interrupt by voice. LLM content comes from free cloud tiers (Groq, Cerebras, OpenRouter). Everything else runs on the Mac (M2, 8 GB, zero cost, open source).

How the claims were checked:
- **[tested]** means I ran it on this Mac on 2026-11-10: headless Chrome 2026, Stiti's `.venv`, and Node from Homebrew. The test files are in the session scratchpad, not in the repo.
- **[repo]** means I read it from the project's source or LICENSE on GitHub, or from npm/PyPI metadata, on 2026-11-10.
- **[docs]** means official documentation.
- **[secondary]** means a blog, review or aggregator.
- **[unverified]** means from memory or a single weak source. Check it before relying on it.

Free-tier limits are taken from the sibling note `../Stiti personal AI buddy research/llm_routing_and_documents.md`, fetched 2026-11-10:
- **Groq** `openai/gpt-oss-20b`, `openai/gpt-oss-120b` and `qwen/qwen3.8-27b`: 30 RPM, 1K RPD, **8K TPM**, **200K TPD**.
- **Cerebras** free tier: 5 RPM, 30K uncached TPM, **1M TPD**.

---

## 0. Decisions at a glance

| Decision | Choice | Why (short) |
|---|---|---|
| Whiteboard | **Excalidraw `@excalidraw/excalidraw@0.18.1` (MIT)** as a live React component, with **React 19.2.0** through an import map | MIT. A full programmatic API (`updateScene`, `convertToExcalidrawElements`, `scrollToContent`, `newElementWith`, `exportToSvg`). Hand-drawn look. Loads from a pinned CDN with no build step **[tested]** and can be vendored to run fully offline **[tested]**. |
| Not chosen | tldraw | Under the tldraw license (**not open source**) it may run only in "Development Environments" and needs a license key in production **[repo]** |
| LLM output format | **Semantic lesson JSON** (no pixel coordinates) enforced with **Groq/Cerebras strict `json_schema`**. Graphs are sent as `nodes`/`edges` and laid out in code with **dagre**. Mermaid is an optional input converted with `@excalidraw/mermaid-to-excalidraw`. | Constrained decoding guarantees the JSON parses for gpt-oss-20b/120b and qwen3.8-27b **[docs]**. Small models place coordinates badly (TheoremExplainAgent, ChalkTalk), so layout belongs in code. |
| Server | **Starlette WebSocket on uvicorn**, bound to `127.0.0.1` on a random port, with a per-session token plus Host and Origin checks | Starlette 1.10.0, uvicorn 0.54.0 and websockets 17.4 are **already in `uv.lock`** (pulled in by `mcp`), so no new dependency. Measured ≈ **38 MB RSS** **[tested]**. |
| Audio | Python plays the audio (the existing Kokoro and sounddevice stack). The browser is a renderer driven by cue messages. | Barge-in, VAD and STT already live in Python. Localhost WebSocket latency is negligible. |
| Sync | **One cue per spoken sentence.** Each cue carries board ops with `at` offsets measured against the sentence's real audio length. | Kokoro gives the exact sentence duration. Stiti's current `kokoro-v1.0.int8.onnx` has **no duration output**, so it has no word timestamps **[tested]**. |
| Book → outline | **pypdfium2** (TOC and page labels) or **MarkItDown EPUB** (structure), then font-size or numbered-heading fallback, then local extractive compression, then LLM map over chapters, reduce into a lesson plan, and generate segment scripts lazily | All of these libraries are already installed and permissively licensed. A whole textbook (≈538K tokens) does not fit Groq's 200K TPD, so the free LLM must never see the whole book. |

---

## 1. Embeddable whiteboard libraries with a programmatic API

### Takeaway
**Excalidraw is the only option that is MIT-licensed, looks like a real whiteboard, has an imperative API for adding, updating and highlighting elements and moving the camera, and runs from a single HTML page without a bundler.** tldraw is technically excellent but its license forbids production use without a key. draw.io gives precise diagrams but is an iframe editor driven by XML, and its docs say embed mode is supported only on embed.diagrams.net. Konva and Fabric are general canvas engines, so the whiteboard itself would have to be built from scratch. Mermaid, Kroki and PlantUML are renderers, not boards.

### Cited findings
- **Excalidraw versions [repo, npm]:** `latest` is **0.18.1** (2026-04-20). 0.18.0 came out on 2025-03-10. The `next` tag gets snapshot builds such as `0.18.0-3c916c5` (2026-11-04). License **MIT**. Peer dependencies: `react`/`react-dom` `^17.0.2 || ^18.2.0 || ^19.0.0`. The package is ESM-only with `main: ./dist/prod/index.js` and `./index.css`. Unpacked size is 46.8 MB; `dist/prod` is 17 MB, of which fonts are 13 MB.
- **Official no-bundler browser recipe [docs]:** use an import map for `react`, `react/jsx-runtime` and `react-dom` from esm.sh, then `import * as ExcalidrawLib from 'https://esm.sh/@excalidraw/excalidraw@0.18.0/dist/dev/index.js?external=react,react-dom'`, and set `window.EXCALIDRAW_ASSET_PATH` for fonts. Source: [integration.mdx](https://github.com/excalidraw/excalidraw/blob/master/dev-docs/docs/@excalidraw/excalidraw/integration.mdx). Docs moved to plus.excalidraw.com: [integration](https://plus.excalidraw.com/docs/sdk/excalidraw/integration). Fonts default to `https://esm.run/@excalidraw/excalidraw/dist/prod` unless `EXCALIDRAW_ASSET_PATH` is set: [installation](https://plus.excalidraw.com/docs/sdk/excalidraw/installation).
- **Imperative API [docs](https://plus.excalidraw.com/docs/sdk/excalidraw/api/props/excalidraw-api):**
  - `updateScene({elements, appState, collaborators, captureUpdate})`, where `captureUpdate` is one of `CaptureUpdateAction.IMMEDIATELY | EVENTUALLY | NEVER` and controls undo capture.
  - `scrollToContent(target?, {fitToContent | fitToViewport, viewportZoomFactor=0.7, animate=false, duration=500})`.
  - Also: `getSceneElements()`, `getAppState()`, `addFiles()`, `resetScene()`, `history.clear()`, `setActiveTool({type})`, `setToast()`, `setCursor()`, and the events `onChange`, `onPointerDown`, `onPointerUp`.
  - Tested in 0.18.1: the API object also has `onScrollChange`, `onUserFollow`, `registerAction` and `updateFrameRendering` **[tested]**.
- **Element skeleton API [docs](https://plus.excalidraw.com/docs/sdk/excalidraw/api/excalidraw-element-skeleton):** `convertToExcalidrawElements(skeletons, {regenerateIds})` turns minimal objects into full elements.
  - `regenerateIds` defaults to `true`; pass `false` to keep your own ids.
  - Containers take a `label: {text}`, and the size is computed if you omit it.
  - Arrows bind with `start: {id}` / `end: {id}` (or `{type}`).
  - Frames take `children: [ids]`.
- **ToolType [repo, `dist/types/excalidraw/types.d.ts`]** includes `"laser"`. `setActiveTool({type:"laser"})` works in edit mode but **does not apply when `viewModeEnabled: true`**: activeTool stayed `selection` **[tested]**. The laser is a pointer trail that the user draws, so the tutor's own "pointing" should be a drawn highlight element. It should not use the laser.
- **tldraw license [repo LICENSE.md](https://github.com/tldraw/tldraw/blob/main/LICENSE.md):** you are allowed to "Use the Software in Development Environments" and you must agree "Not to use the Software in Production Environments" without a trial or commercial key.
  - The license defines a production environment as any deployment "where the software is used to provide functionality to end users".
  - The SDK treats `localhost` and HTTP as development, and in production it "stops rendering the editor" after 5 s without a key ([license-key docs](https://tldraw.dev/sdk-features/license-key)).
  - Hobby licenses are discretionary, for non-commercial projects, and keep a "made with tldraw" watermark ([tldraw.dev/community/license](https://tldraw.dev/community/license)).
  - npm `tldraw@5.6.0` (2026-10-28) has `license: SEE LICENSE IN LICENSE.md`.
  - **Verdict: not acceptable for an open-source zero-cost Stiti.** Anyone who forks Stiti would need their own key.
- **draw.io embed [docs](https://www.drawio.com/doc/faq/embed-mode):**
  - Turn it on with `embed=1&proto=json` and drive it with postMessage.
  - Actions: `load`, `merge` (merges XML, which allows incremental cells), `patch`, `export`, `layout`, `fit`, `viewport`, `status`, `spinner`, and others.
  - Events: `init`, `save`, `autosave`, `exit`.
  - The docs say embed mode "is only supported on https://embed.diagrams.net". Self-hosting `jgraph/drawio` (Apache-2.0) is possible, but I have not checked whether embed mode works when self-hosted **[unverified]**.
- **Mermaid 12.3.0 (MIT, 2026-11-03), Konva 10.9.1 (MIT, 2026-10-31), Fabric 7.4.0 (MIT, 2026-05-18), Rough.js 4.6.6 (MIT, last release 2023-11-20), KaTeX 0.19.1 (MIT), JSXGraph 1.14.3 (MIT or LGPL-3.0), morphdom 2.7.8 (MIT)** [npm]. Pinned CDN URLs return HTTP 200 **[tested]**. GSAP 3.15.1 uses the "Standard 'no charge' license", which is free but **not OSI** [npm].

### Comparison table

| Name | Link | Year / version | License | How it works | Programmatic API | Strengths | Weaknesses | Fit for Stiti |
|---|---|---|---|---|---|---|---|---|
| **Excalidraw** | [repo](https://github.com/excalidraw/excalidraw) (135K★) | 2020– / 0.18.1 (2026-04) | **MIT** | React component that draws hand-drawn-style elements (via Rough.js) on canvas; scene is a JSON element array | `updateScene`, `convertToExcalidrawElements` (skeletons, labels, bound arrows, frames), `newElementWith`, `scrollToContent(animate)`, `exportToSvg`, `getSceneElements`, `onChange`/`onPointerDown` | Whiteboard look; JSON scene easy for code; CDN with no build **[tested]**; user can draw too; the official MCP app already uses it for AI drawing | Needs React (about 0.5 MB JS + fonts); no built-in "draw-on" stroke animation (you write it yourself, see §1 recommendation); laser is user-only; 0.18.x release cadence is slow (13 months between 0.18.0 and 0.18.1) | **Chosen** |
| tldraw | [repo](https://github.com/tldraw/tldraw) | 2021– / 5.6.0 (2026-10) | **tldraw license (source-available, not OSI)** | React infinite-canvas SDK with a rich shape and editor API | `editor.createShapes`, `updateShapes`, `zoomToBounds`, agent starter kit | Best editor API; official agent starter kit | Production use needs a license key; hobby license keeps the watermark and is discretionary; forks need their own key | **Rejected (license)** |
| draw.io / diagrams.net embed | [docs](https://www.drawio.com/doc/faq/embed-mode), [repo](https://github.com/jgraph/drawio) | 2005– / active | **Apache-2.0** | Full editor in an iframe; JSON postMessage protocol; mxGraph XML | `load`, `merge`, `patch`, `layout`, `export`, `fit`, `viewport` | Precise technical diagrams; built-in layouts; official MCP | Embed documented as only on embed.diagrams.net (cloud); heavy UI; XML is verbose for LLMs; not a whiteboard look (a sketch theme exists) | Fallback for precise diagrams; not for the live board |
| Konva | [repo](https://github.com/konvajs/konva) | 2015– / 10.9.1 | MIT | 2D canvas scene graph with built-in Tweens | `new Konva.Rect(...)`, `layer.add`, `node.to({duration})`, `Konva.Tween` | Excellent animation; small; one `<script>` from unpkg works | No whiteboard UX, arrows-with-binding or text containers; everything is DIY | Only if you build a custom board |
| Fabric.js | [repo](https://github.com/fabricjs/fabric.js) | 2010– / 7.4.0 | MIT | Interactive canvas object model with SVG import/export | `canvas.add(new Rect())`, `obj.animate()`, `loadSVGFromString` | Mature; free-drawing brush; SVG import | Same DIY cost as Konva; heavier | Custom board alternative |
| Rough.js (+ rough-notation) | [rough](https://github.com/rough-stuff/rough), [rough-notation](https://github.com/rough-stuff/rough-notation) | 2018– / 4.6.6 (2023); r-n 0.5.1 (2020) | MIT | Sketchy primitives on canvas/SVG; rough-notation draws animated underline, circle, highlight and box on **DOM** elements | `rc.rectangle()`, `rc.line()`; `annotate(el,{type:'highlight'}).show()` | Tiny; hand-drawn look; rough-notation's animated highlight is exactly the "teacher underlines" effect | No scene model; rough-notation targets DOM, not Excalidraw's canvas; both are dormant | Inspiration for the highlight style; use for HTML text panels |
| Mermaid | [repo](https://github.com/mermaid-js/mermaid) | 2014– / 12.3.0 | MIT | Text DSL rendered to SVG | `mermaid.render(id, text)` | LLMs know it well; many diagram types | Static SVG, no incremental reveal; syntax errors (see §2) | Input format for some diagrams, through mermaid-to-excalidraw |
| Kroki | [repo](https://github.com/yuzutech/kroki) | 2019– / active | MIT | HTTP server that renders 20+ DSLs (PlantUML, D2, Graphviz…) to SVG | `GET /{type}/svg/{encoded}` | One API for many DSLs | Needs a self-hosted Java server plus companion containers (heavy on 8 GB) or the public cloud instance (not local) **[unverified RAM]** | No |
| PlantUML | [repo](https://github.com/plantuml/plantuml) | 2009– / active | GitHub reports LGPL-3.0; the project ships multi-license jars (GPL/LGPL/Apache/EPL/MIT) **[unverified per jar]** | Java DSL renderer | CLI/jar, server | Rich UML | JVM RAM; static output | No |
| Miro | [miro.com](https://miro.com) | 2011– | Proprietary SaaS | Cloud board with REST and Web SDK | REST `POST /boards/{id}/shapes` | Polished | Cloud, account required, not local, paid tiers | No (violates local-first) |
| FigJam | [figma.com/figjam](https://www.figma.com/figjam/) | 2021– | Proprietary SaaS | Cloud board; plugin API | Figma Plugin API | Polished | Cloud only; account | No |
| Penpot | [repo](https://github.com/penpot/penpot) (62K★) | 2020– / active | MPL-2.0 | Open-source design tool; self-hosted with Docker (Postgres, Redis, backend, exporter) | Plugin API (`@penpot/plugin-types` 1.4.2) | Open source; SVG-native | Design tool, not a teaching board; self-host is far too heavy for 8 GB | No |
| JSXGraph | [jsxgraph.org](https://jsxgraph.org) | 2008– / 1.14.3 | MIT or LGPL-3.0 | Interactive geometry and plotting in SVG | `board.create('point',…)`, animations | Real math plots (functions, geometry) | Not a whiteboard | Optional add-on for math lessons |
| Plain SVG + Vivus / GSAP DrawSVG | [vivus](https://github.com/maxwellito/vivus) | 2014– / 0.4.6 (2021) | Vivus MIT; GSAP "standard no-charge" (not OSI) | Animate `stroke-dashoffset` to "draw" SVG paths | `new Vivus(svg,{duration})` | True draw-on animation | You own layout and all shapes | Technique used for SVG-mode playback (excalidraw-mcp does this with CSS) |

### Recommendation and verified snippet
Use **Excalidraw 0.18.1** as a live component.
- Use `zenModeEnabled: true` and keep `viewModeEnabled: false` so the laser and user drawing still work.
- The tutor draws through the API. The owner may also scribble.
- Pin every URL. Phase 1 loads from esm.sh. Phase 2 vendors the bundle locally (below).

**Pinned CDN page. Tested in headless Chrome on 2026-11-10: all exports resolved, the scene rendered, and binding, label, highlight, camera, laser and SVG export all worked:**

```html
<!doctype html>
<html><head><meta charset="utf-8"><title>Stiti board</title>
<link rel="stylesheet" href="https://esm.sh/@excalidraw/excalidraw@0.18.1/dist/prod/index.css">
<script>window.EXCALIDRAW_ASSET_PATH = "https://esm.sh/@excalidraw/excalidraw@0.18.1/dist/prod/";</script>
<script type="importmap">
{ "imports": {
  "react": "https://esm.sh/react@19.2.0",
  "react/jsx-runtime": "https://esm.sh/react@19.2.0/jsx-runtime",
  "react-dom": "https://esm.sh/react-dom@19.2.0",
  "react-dom/client": "https://esm.sh/react-dom@19.2.0/client"
} }
</script>
<style>html,body,#app{margin:0;height:100%;width:100%}</style>
</head><body><div id="app"></div>
<script type="module">
import React from "react";
import { createRoot } from "react-dom/client";
import * as X from "https://esm.sh/@excalidraw/excalidraw@0.18.1/dist/prod/index.js?external=react,react-dom";

const api = await new Promise(res => createRoot(document.getElementById("app")).render(
  React.createElement(X.Excalidraw, { excalidrawAPI: res, zenModeEnabled: true, theme: "light" })));
// GOTCHA [tested]: an updateScene sent right after mount can be wiped by Excalidraw's initial load.
// Wait until appState.isLoading is false (or pass initialData).
while (api.getAppState().isLoading) await new Promise(r => setTimeout(r, 50));
window.board = makeBoard(api, X);   // see runtime below
</script></body></html>
```

**Minimal board runtime.** These are the calls that were tested. Ids are kept with `regenerateIds:false`. Bound labels get random ids and carry `containerId`.

```js
function makeBoard(api, X) {
  const NEVER = X.CaptureUpdateAction.NEVER;              // don't pollute the user's undo stack
  const scene = () => api.getSceneElements();
  const put = (els) => api.updateScene({ elements: els, captureUpdate: NEVER });
  const sleep = (ms) => new Promise(r => setTimeout(r, ms));
  const withChildren = (els, id) => els.filter(e => e.id === id || e.containerId === id);

  return {
    // add: skeletons -> elements, revealed one group at a time with an opacity fade
    async add(skeletons, { fadeMs = 250 } = {}) {
      const els = X.convertToExcalidrawElements(skeletons, { regenerateIds: false });
      const existing = new Set(scene().map(e => e.id));
      const fresh = els.filter(e => !existing.has(e.id));       // idempotent: replaying a cue is a no-op
      put([...scene(), ...fresh.map(e => ({ ...e, opacity: 1 }))]);   // 1, not 0: Excalidraw treats 0 as "unset"
      for (const o of [35, 70, 100]) {
        await sleep(fadeMs / 3);
        put(scene().map(e => fresh.some(f => f.id === e.id) ? X.newElementWith(e, { opacity: o }) : e));
      }
    },
    // draw-on for arrows/lines: grow the last point over N frames [tested: 20 steps OK]
    async growArrow(id, ms = 400, steps = 15) {
      const a = scene().find(e => e.id === id); const end = a.points.at(-1);
      for (let i = 1; i <= steps; i++) {
        put(scene().map(e => e.id === id ? X.newElementWith(e, { points: [[0, 0], [end[0] * i / steps, end[1] * i / steps]] }) : e));
        await sleep(ms / steps);
      }
    },
    // typewriter text: re-convert the same id with a longer string (width recomputed) [tested]
    async write(id, x, y, text, { fontSize = 24, cps = 40 } = {}) {
      for (let i = 1; i <= text.length; i += 3) {
        const [el] = X.convertToExcalidrawElements([{ type: "text", id, x, y, text: text.slice(0, i), fontSize }], { regenerateIds: false });
        put([...scene().filter(e => e.id !== id), el]); await sleep(3000 / cps);
      }
    },
    // highlight = recolour the target, plus an optional translucent marker rectangle behind it
    highlight(id, color = "#e03131") {
      put(scene().map(e => withChildren([e], id).length ? X.newElementWith(e, { strokeColor: color, strokeWidth: 4 }) : e));
    },
    erase(ids) { put(scene().map(e => ids.includes(e.id) || ids.includes(e.containerId) ? X.newElementWith(e, { isDeleted: true }) : e)); },
    // camera: pass the elements of the current SECTION, not one small element
    focus(ids, ms = 500) {
      api.scrollToContent(scene().filter(e => ids.includes(e.id) || ids.includes(e.containerId)),
        { fitToViewport: true, viewportZoomFactor: 0.8, animate: true, duration: ms });
    },
    setCamera(scrollX, scrollY, zoom) {   // exact camera; applied on the next render [tested]
      api.updateScene({ appState: { scrollX, scrollY, zoom: { value: zoom } }, captureUpdate: NEVER });
    },
    snapshot() { return JSON.parse(JSON.stringify(scene())); },   // for rewind
    restore(els) { put(els); },
  };
}
```

Gotchas found in testing:
1. Calling `scrollToContent([oneSmallElement], {fitToViewport:true})` zoomed to **760 %** **[tested]**. Always focus a section, or compute a camera rectangle in Python and use `setCamera`. The excalidraw-mcp `cameraUpdate` pseudo-element does the same thing.
2. `setActiveTool({type:"laser"})` is ignored in view mode **[tested]**.
3. Opacity `0` means "unset" in Excalidraw, so start fades at `1`. Source: comment in [excalidraw-mcp `mcp-app.tsx`](https://github.com/excalidraw/excalidraw-mcp).
4. Arrows whose first point is not `(0,0)` were moved by the converter in ChalkTalk. Express points relative to the first point ([ChalkTalk post](https://dev.to/danial_mo/chalktalk-a-whiteboard-tutor-that-draws-like-a-teacher-and-lets-you-raise-your-hand-4jmd)).

**Fully offline variant [tested]:**
- A one-time dev command needs Node, which is already installed: `npm i --ignore-scripts @excalidraw/excalidraw@0.18.1 react@19.2.0 react-dom@19.2.0 esbuild`. Then bundle an `entry.js` that re-exports `@excalidraw/excalidraw`, `React` and `createRoot`, using `esbuild entry.js --bundle --format=esm --minify --define:process.env.NODE_ENV='"production"' --define:process.env.IS_PREACT='"false"'`.
- The result is one **8.1 MB** `excalidraw-bundle.mjs`. Add `dist/prod/index.css` and copy `dist/prod/fonts` (13 MB) to `/assets/`, then set `EXCALIDRAW_ASSET_PATH="/assets/"`.
- The page loaded with **zero external requests** (`performance.getEntriesByType("resource")` showed nothing off-origin).
- This is a one-off vendoring step, not a runtime build. Commit the outputs, or fetch them on first run. Adding `--splitting` would let locales load lazily.

**Browser RAM [tested, rough]:** in a fresh headless Chrome, the renderer processes measured 75–125 MB each with Excalidraw loaded. The whole headless browser, including GPU and utility processes, was about 840 MB. In the owner's already-running browser, expect about **100–150 MB for the tab**.

---

## 2. LLM → diagram generation: representation, reliability, layout

### Takeaway
**Do not ask a free or small LLM for pixel coordinates.** The ones that work all follow the same pattern: the model emits semantic structure, and code does the layout.
- Excalidraw's own text-to-diagram goes through Mermaid.
- tldraw's agent kit uses a simplified shape format plus a sanitizer.
- ChalkTalk uses regions and relative placement.
- SketchAgent uses a grid.

For Stiti:
- The lesson is **strict JSON**, enforced by Groq/Cerebras `json_schema` with `strict: true`. Constrained decoding guarantees the JSON parses for gpt-oss-20b, gpt-oss-120b and qwen3.8-27b.
- Graph-shaped diagrams are `nodes`/`edges`, laid out by dagre.
- Mermaid is accepted only as an optional field. It gets validated in the browser and repaired once, or Stiti falls back to the JSON graph.

### Cited findings
- **Groq structured outputs [docs](https://console.groq.com/docs/structured-outputs):** strict mode (`strict: true`) on `openai/gpt-oss-20b`, `openai/gpt-oss-120b`, `qwen/qwen3.8-27b` (and `meta-models/muse-spark-open`) "uses constrained decoding to guarantee that the output will always match your schema exactly".
  - Requirements: all properties must be `required`; model optional values as `null` unions; set `additionalProperties:false`.
  - Supported keywords: string, number, boolean, integer, object, array, enum, `anyOf`.
  - **"Streaming and tool use are not currently supported with Structured Outputs."**
  - The page contradicts itself: one table says strict mode is limited to the GPT-OSS models.
- **Cerebras structured outputs [docs](https://inference-docs.cerebras.ai/capabilities/structured-outputs):** strict constrained decoding on `qwen-3.8-27b` and `gpt-oss-120b` (shared inference).
  - Not supported: `oneOf`, `allOf`, `not`, `if/then/else`, `pattern`, `format`, `minItems/maxItems`, recursive schemas.
  - Limits: max depth 10, 500 properties, 500 enum values, and a schema of at most 5,000 characters.
  - A single flat schema with nullable fields works on both providers.
- **Format restrictions vs reasoning:** "Let Me Speak Freely?" (Tam et al., EMNLP 2024 Industry, [arXiv 2408.02442](https://arxiv.org/abs/2408.02442)) found strict JSON can hurt reasoning tasks, while looser formats help. It suggests a two-step NL→format approach. For Stiti, think in prose first (the outline and the segment plan), then format each segment as JSON.
- **Mermaid reliability:**
  - A practitioner saw 23 of 872 LLM-generated Mermaid blocks (2.6 %) fail to render because of delimiter conflicts ([CodeWiki #141](https://github.com/FSoft-AI4Code/CodeWiki/issues/141)) [secondary].
  - OmniDiagram ([arXiv 2604.05514](https://arxiv.org/abs/2604.05514)) reports that PlantUML and Mermaid syntax errors stay "largely stagnant regardless of model scale" [secondary summary].
  - MermaidSeqBench ([arXiv 2511.14967](https://arxiv.org/abs/2511.14967)) covers sequence diagrams only, judged by an LLM.
  - **No study compares JSON, Mermaid and DSL head-to-head for small models** [search, 2026-11-10]. Build a 20-prompt local eval when keys are set (none are configured in `.env` today).
- **Layout is the weak point:** TheoremExplainAgent ([arXiv 2502.19400](https://arxiv.org/abs/2502.19400), ACL 2025) reports "most of the videos produced exhibit minor issues with visual element layout", and these get worse at medium and hard difficulty. Code2Video ([arXiv 2510.01174](https://arxiv.org/abs/2510.01174), ICML 2026) adds a separate **Critic** agent with "visual anchor" prompts just to fix spatial layout.
- **`@excalidraw/mermaid-to-excalidraw` [repo](https://github.com/excalidraw/mermaid-to-excalidraw), MIT:**
  - `latest` is **3.6.0** (2026-11-04). The **3.x line (since 2026-10-27) dropped the `mermaid` dependency for `pele` 1.13.0**, Obsidian's MIT Mermaid parser and layout engine ("No Mermaid runtime"). 2.3.0 (2026-10-21) still depends on `mermaid ^11.12.1` [npm].
  - API: `parseMermaidToExcalidraw(def, {elbow?})` returns `{elements, files?}`, then `convertToExcalidrawElements`, then `updateScene`. It throws on invalid syntax.
  - 3.x README: flowchart, sequence, class, ER, state, Gantt, quadrant and timeline become native elements; other types fall back to an image.
  - **Tested:** both 2.3.0 and 3.6.0 converted a 4-node flowchart from esm.sh into 7 skeletons → 13 elements (rectangle, diamond, arrow, text).
- **dagre / ELK [tested in Node]:** `@dagrejs/dagre@3.1.3` (MIT, 2026-10-24) keeps the classic API (`new dagre.graphlib.Graph()`, `setGraph({rankdir})`, `setNode(id,{width,height})`, `setEdge`, `dagre.layout(g)`, `g.node(id).x/.y` = **centre**). `elkjs@0.12.1` (EPL-2.0 OR GPL-3.0-or-later, 2026-10-28) `elk.layout(graph)` returns `x/y` = **top-left**. Both are on esm.sh (HTTP 200).

### Comparison table: projects and papers

| Name | Link | Year | License | How it works | Programmatic API | Strengths | Weaknesses | Fit |
|---|---|---|---|---|---|---|---|---|
| **@excalidraw/mermaid-to-excalidraw** | [repo](https://github.com/excalidraw/mermaid-to-excalidraw) | 2023– / 3.6.0 | MIT | Parses Mermaid (3.x with `pele`), lays it out, emits Excalidraw skeletons | `parseMermaidToExcalidraw(text)` | Native editable elements; works from CDN **[tested]** | 3.x is two weeks old with a fast release cadence; unsupported types become images; Mermaid syntax errors | **Optional input path**; pin 2.3.0 now, move to 3.x after a few stable weeks |
| Excalidraw "Text to diagram" | excalidraw.com AI menu | 2023– | MIT client; the AI backend is Excalidraw's service | Prompt → LLM → Mermaid → mermaid-to-excalidraw [secondary](https://medium.com/@venn5708/excalidraw-open-sources-its-text-to-diagram-feature-3810169df601) | UI only | Shows that the Mermaid-intermediate approach works | Cloud backend; no word on how failures are handled | Pattern only |
| **excalidraw-mcp (official MCP app)** | [repo](https://github.com/excalidraw/excalidraw-mcp) (5.6K★) | 2026 | MIT per README (GitHub API shows none) | LLM streams an **Excalidraw skeleton JSON array**. The client parses partial JSON, converts, `exportToSvg`, **morphdom**-diffs, and CSS `stroke-dashoffset` draw-on. Pseudo-elements `cameraUpdate`, `delete`, `restoreCheckpoint`. | MCP tool `create_view` plus a cheat sheet in `src/server.ts` | Excellent prompt cheat sheet (drawing order "background → shape → its label → its arrows", min font 16, camera first); real streaming draw-on | The LLM still writes coordinates (big models only); needs an MCP Apps host | **Borrow the cheat sheet, the camera pseudo-op and the CSS draw-on idea** |
| yctimlin/mcp_excalidraw | [repo](https://github.com/yctimlin/mcp_excalidraw) (2.6K★) | 2025– | MIT | MCP server plus a canvas server; elements pushed live over WebSocket | MCP tools (create, update, batch, export) | Same architecture as Stiti's plan (Python ↔ WS ↔ canvas) | Node canvas server; coordinates from the LLM | Reference |
| jgraph/drawio-mcp | [repo](https://github.com/jgraph/drawio-mcp) (5.8K★) | 2025– | Apache-2.0 | Tools `open_drawio_xml`, `open_drawio_csv`, `open_drawio_mermaid` | MCP | Official; Mermaid → draw.io | Opens the draw.io editor; CSV needs draw.io's server | No |
| tldraw "make real" | [repo](https://github.com/tldraw/make-real) | 2023 | Repo license not stated; the SDK is tldraw-licensed | Vision LLM turns a sketched UI into HTML | — | Famous demo | Drawing → code (opposite direction); license | No |
| tldraw agent starter kit | [docs](https://tldraw.dev/starter-kits/agent) | 2025 | tldraw license | Screenshot plus simplified "SimpleShape" data → model actions → **sanitizer fixes bad ids and out-of-range coords** [secondary] | Action utils | Shows that a sanitizer and short ids are needed | License | Pattern: short ids, sanitizer |
| Eraser DiagramGPT | [eraser.io](https://www.eraser.io/diagramgpt-new) | 2023– | Proprietary | LLM → Eraser's diagram-as-code DSL → render [secondary] | Web app | DSL is short and easy to edit | Closed SaaS | Pattern: compact DSL |
| Napkin AI | [napkin.ai](https://napkin.ai) | 2024– | Proprietary | Text → suggested visual templates [secondary](https://techcrunch.com/2024/08/07/napkin-turns-text-into-visuals-with-a-bit-of-generative-ai) | Web app | Choosing a template beats free-form drawing | Closed; internals unknown | Pattern: a small template library |
| Whimsical AI | [help](https://help.whimsical.com/article/725-getting-started-with-whimsical-ai) | 2023– | Proprietary | Pick a type (flowchart, mind map, sequence) + prompt → editable canvas | Web app | Typed generation | Closed | Pattern: ask for a diagram *type* first |
| DiagramAgent / DiagramGenBenchmark | [arXiv 2411.11916](https://arxiv.org/abs/2411.11916) | 2024 (CVPR 2025) | paper | Plan, Code, Check and Diagram-to-Code agents; 8 diagram types | — | Check agent improves pass@1 (58.15) | Big models; code-based (LaTeX/TikZ style) | A check-and-repair loop is worth it |
| MermaidSeqBench | [arXiv 2511.14967](https://arxiv.org/abs/2511.14967) | 2025 | paper | LLM-judge scoring of NL → Mermaid sequence diagrams | — | Includes small models (Qwen2.5-7B, Llama-3.1-8B) | Sequence diagrams only | Evidence that Mermaid quality varies |
| OmniDiagram | [arXiv 2604.05514](https://arxiv.org/abs/2604.05514) | 2026 | paper | Unified diagram-code generation with a visual-interrogation reward | — | Finds syntax errors don't shrink with model scale | Training method | Supports "validate + repair" |
| SketchAgent | [arXiv 2411.17673](https://arxiv.org/abs/2411.17673), [repo](https://github.com/yael-vinker/SketchAgent) | 2024 (CVPR 2025) | MIT | MLLM draws **stroke by stroke** on a numbered grid canvas using a string action language | — | Real sequential drawing; grid coordinates instead of pixels | Sketches, not diagrams; needs a big MLLM | A grid or region is the right abstraction |
| Let Me Speak Freely? | [arXiv 2408.02442](https://arxiv.org/abs/2408.02442) | 2024 | paper | Measures JSON-mode or format constraints vs free text | — | Strict formats help classification and hurt reasoning | Older models | Generate the plan in prose, then format |

### Comparison table: representations for the LLM

| Representation | Parse guarantee on free tier | Layout burden on the LLM | Diagram coverage | Verdict |
|---|---|---|---|---|
| Raw Excalidraw JSON (full elements) | Strict schema possible but huge (≈30 fields) | Pixel coordinates | Everything | No |
| Excalidraw skeleton JSON with x/y (excalidraw-mcp style) | Strict schema feasible | Pixel coordinates; overlaps are common for small models | Everything | Only behind a code-side layout fixer |
| **Semantic lesson JSON (ids, regions, relative placement, nodes/edges)** | **Strict schema → guaranteed** | **None; code lays out** | Text, lists, boxes, flows, trees, tables, highlights | **Chosen** |
| Mermaid | None (2–3 % render failures [secondary]); validated in the browser | None (auto layout) | Flowchart, sequence, class, state, ER, timeline | Optional field |
| PlantUML | None; needs a JVM | None | UML | No |
| Graphviz DOT | None; needs a WASM or native renderer | None | Graphs | No (dagre covers it) |
| draw.io XML | None; verbose | Coordinates | Everything | No |
| D2 / Eraser DSL | None; D2 needs its own renderer | None | Graphs and architecture | No |
| TikZ / Manim code | None; must execute | Coordinates | Math | No (video, not live) |
| ChalkTalk-style NDJSON steps (`say`, `gist`, `actions`) | Per-line JSON; Gemma emitted stray brackets → custom parser | Regions only | Text, tables, bars, lists, links | Close to the chosen format; strict schema removes the bracket bugs |

### Layout libraries (≥10 considered)

| Name | Link | License | Use |
|---|---|---|---|
| **@dagrejs/dagre 3.1.3** | [repo](https://github.com/dagrejs/dagre) | MIT | **Chosen** for flow and tree layout in the browser **[tested]** |
| elkjs 0.12.1 | [repo](https://github.com/kieler/elkjs) | EPL-2.0 OR GPL-3.0 | Better orthogonal and compound layouts; larger (≈1.4 MB bundled) **[unverified size]** |
| Mermaid / pele built-in layouts | see above | MIT | Used implicitly through mermaid-to-excalidraw |
| d3-hierarchy (d3 7.9.2) | [d3](https://github.com/d3/d3) | ISC | Tree and mind-map layouts |
| d3-force | same | ISC | Concept maps |
| Cytoscape.js (+ cola/klay) | [js.cytoscape.org](https://js.cytoscape.org) | MIT | Graph layouts **[unverified version]** |
| Graphviz (viz.js WASM) | [viz-js](https://github.com/mdaines/viz-js) | MIT (wrapper); EPL (Graphviz) **[unverified]** | Classic DOT |
| WebCola | [ialab.it.monash.edu/webcola](https://ialab.it.monash.edu/webcola/) | MIT **[unverified]** | Constraint layout |
| networkx (Python) | [networkx.org](https://networkx.org) | BSD-3 | Server-side tree positions if needed |
| Own "region grid" layout (Python) | — | — | Title, bullet column, side panel, and wrap to a second column (ChalkTalk's approach) |
| draw.io built-in layouts | draw.io `layout` action | Apache-2.0 | Not used |

### Recommendation
1. **Two LLM calls per segment** to follow the "speak freely" finding.
   - (a) The plan call is free text or simple JSON: key points and the diagram idea.
   - (b) The script call uses a **strict `json_schema`** (§5 schema), non-streaming because Groq strict mode cannot stream. Prefetch the next segment while the current one plays.
2. Diagram ops carry **semantics only**: `region`, `below/right_of/<id>`, or `graph: {nodes, edges, direction}`.
3. **Python** resolves regions and relative positions into a grid.
4. The **browser** runs dagre for `graph` ops and converts the result to skeletons with coordinates, then to Excalidraw.
5. If an op has `mermaid` text, try `parseMermaidToExcalidraw` in the browser. On a throw, send the error back to Python for **one** repair call. If that fails, drop the diagram and keep the narration (ChalkTalk: "a bad action no longer discards its entire step").
6. Keep **short ids** (`b1`, `a3`), as tldraw's kit, ChalkTalk and excalidraw-mcp all do. **Sanitize** before drawing: unknown ids, duplicates, overly long labels, and too many ops per cue.
7. Put excalidraw-mcp's style rules into the system prompt as constants that Python enforces, not as LLM instructions: minimum font 16, minimum labeled box 120×60, and short labels on arrows.

---

## 3. Existing "AI teacher draws while talking" projects

### Takeaway
The pattern has converged.
- **Flat, ordered action lists**: speech actions block until the audio ends, visual "effects" fire and forget, and board actions run for fixed animation times (OpenMAIC).
- **Per-step objects** of `{say, actions[]}`, synced to the *real* clip duration rather than estimates, with TTS generated about 3 steps ahead (ChalkTalk).
- **Bookmarks inside the narration text** to trigger visuals mid-sentence (manim-voiceover).

ChalkTalk (Excalidraw + Kokoro + open model + "raise hand") is nearly Stiti's exact design and confirms it. OpenMAIC (MIT, 43K★) is the most complete open system to study for resume and navigation.

### Comparison table

| Name | Link | Year | License | How it works | Narration ↔ drawing sync | Strengths | Weaknesses | Fit / what to borrow |
|---|---|---|---|---|---|---|---|---|
| **OpenMAIC** (Tsinghua) | [repo](https://github.com/THU-MAIC/OpenMAIC) (43K★), paper *JCST* 2026 doi:10.1007/s11390-025-6000-0 | 2025– | MIT (some packages LGPL) | Multi-agent classroom: slides, quizzes, simulations, and an SVG whiteboard (`wb_draw_text/shape/chart/latex/table/line`, `wb_delete`, `wb_clear`), plus `spotlight`, `laser`, `speech` | `lib/action/engine.ts`: **"Fire-and-forget: spotlight, laser"** vs **"Synchronous: speech, whiteboard, discussion — await completion"**; timing constants `WB_DRAW_MS` etc.; `lib/playback/action-resume.ts` stores `{actionIndex, actionId, actionType}` per scene **[repo]** | Complete, open, many LLM providers including Ollama and OpenRouter; resume cursor; layout eval harness (`eval/whiteboard-layout`) | Next.js 16 + Postgres stack, heavy for 8 GB; TTS mostly cloud | **Borrow the action taxonomy, the sync vs fire-and-forget split, and the resume cursor** |
| **ChalkTalk** | [post](https://dev.to/danial_mo/chalktalk-a-whiteboard-tutor-that-draws-like-a-teacher-and-lets-you-raise-your-hand-4jmd), [repo](https://github.com/Danialmoa/chalktalk) | 2026-10 | Repo license not stated | Gemma 4 26B-A4B through OpenRouter → **NDJSON steps `{say, gist, actions≤3}`**; actions `write, mark, link, table, bars, list, strike` with `id.part` targets; Excalidraw; Kokoro-82M in a browser Web Worker | Draw timing follows the **actual clip duration**; voice generated **3 steps ahead**; a backup timer covers a missed `ended` event | Raise hand (✋/H): finish the step, pause, send `{title, said-so-far, board summary "id | type | text", question}`, answer into a side area, then Continue. No pixel coordinates from the LLM. | Fade-ins only (no stroke animation yet); small-model JSON bugs (fixed with a bracket-tracking parser); zero stars | **Closest match. Borrow the step shape, the board-summary format and the hand-raise flow.** |
| Clarly | [repo (description only)](https://github.com/satya-lakshya/clarly) | 2026 | Source private | Excalidraw; Kokoro plus provider TTS; FastAPI | "board is drawn in step with the voice" (no details) | Hold-space barge-in; quick-check answers by tap, number or voice | Closed source | UX reference only |
| AI_TUTOR | [repo](https://github.com/muhammadammark326-dot/AI_TUTOR) | 2026-09 | MIT | Excalidraw tutor; Edge (cloud) TTS | Step-by-step [secondary] | MIT | Tiny, unreviewed | Low |
| whiteboard-tutor (harjothkhara) | [repo](https://github.com/harjothkhara/whiteboard-tutor) | 2026-09 | NOASSERTION | tldraw; Claude; OpenAI TTS; "watch the explanation drawn step by step" | Step-based | No screenshots in the prompt (cheap) | tldraw license; paid APIs | Low |
| ai-live-tutor | [repo](https://github.com/SohailElskhawy/ai-live-tutor) | 2026-10 | NOASSERTION | Gemini Live voice calls tldraw-agent drawing tools | Tool calls during a realtime voice session | Natural barge-in through Gemini Live | Cloud realtime API; tldraw | Low |
| Khanmigo interactive diagrams | [Khan blog](https://blog.khanacademy.org/?p=22106) | 2026 | Proprietary | Gemini generates charts and geometry when helpful | Chat-turn based | Pedagogy-driven ("when a visual helps") | Closed; not a talking whiteboard | Pedagogy reference |
| NotebookLM Video Overviews | [Google blog](https://blog.google/innovation-and-ai/models-and-research/google-labs/notebooklm-video-overviews-studio-upgrades/) | 2025-07; styles 2025-10 incl. **Whiteboard** ([blog](https://blog.google/innovation-and-ai/models-and-research/google-labs/video-overviews-nano-banana/)) | Proprietary | Sources → narrated slides; image model renders the frames | Pre-rendered video (no live interrupt) | Shows that "teach my document in N minutes" is a product | Not interactive | Product reference |
| TheoremExplainAgent | [arXiv 2502.19400](https://arxiv.org/abs/2502.19400), [repo](https://github.com/TIGER-AI-Lab/TheoremExplainAgent) | 2025 (ACL) | MIT | Planner + coder agents write Manim; 5+ min videos | Rendered offline, scene by scene with voiceover | 240-theorem benchmark | Layout errors are common; offline render | Evidence: keep layout out of the LLM |
| Code2Video | [arXiv 2510.01174](https://arxiv.org/abs/2510.01174), [repo](https://github.com/showlab/Code2Video) | 2025 (ICML 2026) | MIT | Planner → Coder (Manim) → Critic with visual anchors; TeachQuiz metric | Offline storyboard | +40 % over direct code generation [secondary] | Offline; GPU or time heavy | The TeachQuiz idea suits Stiti's end-of-lesson quiz |
| Math-To-Manim | [repo](https://github.com/HarleyCoops/Math-To-Manim) (2.8K★) | 2025– | MIT | LLM → Manim animations plus study notes | Offline | Pretty output | Offline render; heavy | No |
| manim-voiceover | [repo](https://github.com/ManimCommunity/manim-voiceover), [example](https://github.com/ManimCommunity/manim-voiceover/blob/main/examples/bookmark-example.py) | 2022– | MIT | `with self.voiceover(text="…<bookmark mark='A'/>…") as tracker:` then `self.wait_until_bookmark("A")`, `tracker.time_until_bookmark("B")`; word timing via Whisper or Azure | **In-text bookmarks** | Elegant mid-sentence sync | Offline video | **Borrow the bookmark syntax** for `at` anchors (§5) |
| excalidraw-mcp | above | 2026 | MIT | Element-ordered streaming with camera pseudo-ops | Visual order = stream order (no audio) | Draw-on CSS; camera easing | No narration | Borrow camera ops |
| SketchAgent | above | 2024 | MIT | Stroke-by-stroke sketch actions | Sequential | Natural drawing | No speech | Idea for future "hand-drawn" icons |
| Photomath animated steps | [photomath.com](https://photomath.com) | 2014– | Proprietary | Step-by-step math solution animations **[unverified details]** | Step-based | Math clarity | Closed | Pedagogy only |

---

## 4. Local web app architecture (Python ↔ browser)

### Takeaway
Use **Starlette's WebSocket on uvicorn**. Both are already in Stiti's lockfile: starlette 1.10.0, uvicorn 0.54.0, websockets 17.4, sse-starlette 3.7.0, all pulled in by `mcp`. Run it inside Stiti's asyncio process.
- Bind to **127.0.0.1** on a random free port.
- Serve one HTML page plus the vendored assets.
- Open it with `webbrowser.open`, or later with pywebview for a native window.
- Authenticate with a **per-session token in the URL fragment**, and check **Host** and **Origin** on every request and on the WS handshake.

A WebSocket is needed because traffic goes both ways: cue acks, pause, typed questions, clicks on elements, and "done animating" events. SSE + POST would also work (FastAPI ≥ 0.135 has native `EventSourceResponse` ([docs](https://fastapi.tiangolo.com/tutorial/server-sent-events/))), but that means two channels for no gain.

### Cited findings
- **Measured:** a minimal Starlette + uvicorn app with a WS route on Stiti's venv peaked at **≈ 38 MB RSS** **[tested]**.
- **CSWSH:** browsers let any website open a WebSocket to `ws://127.0.0.1:port`. The defense is **server-side Origin validation** plus a token ([Christian Schneider](https://christian-schneider.net/CrossSiteWebSocketHijacking.html), [Include Security 2025](https://blog.includesecurity.com/2025/04/cross-site-websocket-hijacking-exploitation-in-2025/)).
- **DNS rebinding:** a plain-HTTP local server must validate the **Host** header. Vite's CVE-2025-24010 is the model case ([advisory](https://www.miggo.io/vulnerability-database/cve/CVE-2025-24010)). Origin checks that ignore scheme or port were a 2026 Julia advisory ([JLSEC-2026-614](https://security.julialang.org/advisories/JLSEC-2026-614/)).

### Comparison table

| Name | Link | Version / license | How it works | Python → browser push | Browser → Python | Strengths | Weaknesses | Fit |
|---|---|---|---|---|---|---|---|---|
| **Starlette WebSocketRoute + uvicorn** | [starlette.io](https://www.starlette.io/websockets/) | 1.10.0 BSD-3 / uvicorn 0.54 BSD-3 | ASGI app in Stiti's event loop | `await ws.send_json(op)` | `await ws.receive_json()` | **No new dependency**; ≈38 MB; full control | You write the routing (trivial) | **Chosen** |
| FastAPI WebSocket | [docs](https://fastapi.tiangolo.com/advanced/websockets/) | 0.162.2 MIT | Starlette plus DI and pydantic | same | same | Nicer validation | Adds a dependency (pydantic is already present) | Fine if Stiti adopts FastAPI elsewhere |
| FastAPI SSE (`fastapi.sse.EventSourceResponse`) + POST | [docs](https://fastapi.tiangolo.com/tutorial/server-sent-events/) | ≥0.135 MIT | `yield` events; 15 s keep-alive; `Last-Event-ID` resume | SSE stream | separate `fetch POST` | Auto-reconnect and resume | Two channels | Alternative |
| sse-starlette | [repo](https://github.com/sysid/sse-starlette) | 3.7.0 BSD-3 (in lock) | SSE for Starlette | SSE | POST | Already installed | Same two-channel issue | Alternative |
| Flask + Flask-SocketIO | [docs](https://flask-socketio.readthedocs.io) | 5.7.2 MIT | WSGI + Socket.IO protocol | `emit` | events | Simple | Different concurrency model from Stiti's asyncio; Socket.IO client needed | No |
| aiohttp | [docs](https://docs.aiohttp.org) | 3.14.5 Apache/MIT | asyncio HTTP + WS server | `ws.send_json` | `async for msg in ws` | Mature, one package | New dependency; same as Starlette | No |
| `websockets` library + `http.server` | [docs](https://websockets.readthedocs.io) | 17.4 BSD-3 (in lock) | Bare WS server; static files elsewhere | `send` | `recv` | Minimal | Two servers or ports; you handle Host checks yourself | No |
| NiceGUI | [nicegui.io](https://nicegui.io) | 4.0.0 MIT | Python-defined UI over a FastAPI/Socket.IO backend | `ui.run_javascript` | Python callbacks | Very fast to prototype | Heavy dependency tree; owns the event loop | No |
| Gradio | [gradio.app](https://gradio.app) | 6.31.0 Apache-2.0 | Component UI | limited | callbacks | — | Not built for a custom canvas; heavy | No |
| Streamlit | [streamlit.io](https://streamlit.io) | Apache-2.0 | Rerun-script model | poor | rerun | — | Rerun model doesn't fit real time | No |
| Reflex | [reflex.dev](https://reflex.dev) | 0.10.1 Apache-2.0 | Python → React compiler | state sync | events | — | Build step; heavy | No |
| Eel | [repo](https://github.com/python-eel/Eel) | 0.18.2 | Bottle + gevent WS; `eel.expose` | `eel.fn()` | `eel.py_fn()` | Easy | gevent clashes with asyncio; little maintenance **[unverified]** | No |
| **pywebview** | [pywebview.flowrl.com](https://pywebview.flowrl.com) | 6.2.1 BSD-3 | Native WKWebView window on macOS; `evaluate_js`, `js_api` bridge | `window.evaluate_js` | `pywebview.api.*` | No browser tab; feels like an app; WebKit may use less RAM than Chrome **[unverified]** | Main-thread GUI loop (conflicts with rumps' menu-bar loop **[unverified]**); WebKit quirks | **Phase 2 option**: point it at the same local URL |
| LiveKit data channel | [docs](https://docs.livekit.io) | `livekit` already in deps, Apache-2.0 | WebRTC data plus audio | data packets | data packets | Could carry audio and ops together | Needs a LiveKit server/room; overkill locally | No |

### Recommended server skeleton (Starlette)
This is a sketch. It uses the same APIs as the tested RSS probe.

```python
import secrets, socket, webbrowser, uvicorn
from starlette.applications import Starlette
from starlette.routing import Route, WebSocketRoute, Mount
from starlette.responses import FileResponse, PlainTextResponse
from starlette.staticfiles import StaticFiles

def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0)); return s.getsockname()[1]

PORT, TOKEN = free_port(), secrets.token_urlsafe(32)
ALLOWED_HOSTS = {f"127.0.0.1:{PORT}", f"localhost:{PORT}"}
ALLOWED_ORIGINS = {f"http://127.0.0.1:{PORT}", f"http://localhost:{PORT}"}

async def page(req):
    if req.headers.get("host") not in ALLOWED_HOSTS:          # DNS-rebinding guard
        return PlainTextResponse("bad host", 400)
    return FileResponse("board/index.html", headers={"Cache-Control": "no-store",
        "Content-Security-Policy": f"default-src 'self'; connect-src ws://127.0.0.1:{PORT}; "
                                   "img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; font-src 'self'"})

async def board_ws(ws):
    ok = (ws.headers.get("host") in ALLOWED_HOSTS and ws.headers.get("origin") in ALLOWED_ORIGINS
          and secrets.compare_digest(ws.query_params.get("t", ""), TOKEN))
    if not ok:
        await ws.close(code=4403); return
    await ws.accept()
    await lesson_session(ws)          # send cue/pause/seek messages; receive acks/questions/clicks

app = Starlette(routes=[Route("/", page), WebSocketRoute("/ws", board_ws),
                        Mount("/assets", StaticFiles(directory="board/assets"))])
# inside Stiti's asyncio loop:
server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=PORT, log_level="warning", ws_max_size=1 << 20))
# asyncio.create_task(server.serve()); then:
webbrowser.open(f"http://127.0.0.1:{PORT}/#t={TOKEN}")   # fragment is never sent to the server or written to logs
```

Browser side: `const t = new URLSearchParams(location.hash.slice(1)).get("t"); history.replaceState(null, "", "/"); const ws = new WebSocket(\`ws://${location.host}/ws?t=${t}\`);`

The CSP above assumes the **vendored** bundle. During CDN prototyping, add `https://esm.sh` to `script-src`, `style-src`, `font-src` and `connect-src`.

**RAM budget:** server ≈ 38 MB + browser tab ≈ 100–150 MB + Kokoro (already loaded). That fits the 8 GB budget. Close the tab, or call `resetScene`, after the lesson.

---

## 5. Syncing TTS narration with board actions; barge-in, pause, resume, rewind

### Takeaway
**A cue is one spoken sentence (or clause) plus its board ops.**
- Python synthesizes each cue with Kokoro, **2–3 cues ahead** as ChalkTalk does, so the exact audio length is known before playback.
- When playback starts, Python sends the cue's ops with `at` offsets, expressed as a fraction of the sentence or as a bookmark. The browser schedules them on its own clock.
- All ops are **idempotent by id**, so replaying a cue never duplicates elements.
- Pause stops audio and timers.
- Resume restarts from the beginning of the interrupted sentence.
- Rewind restores a board snapshot taken at the cue boundary.

Stiti's installed Kokoro model gives no word timings, so sentence-level sync with proportional anchors is the baseline. Word-level bookmarks need a model exported with a duration output.

### Cited findings
- **kokoro-onnx 0.6.1** (2026-08-19, MIT, in `uv.lock`) adds `Kokoro.create_timed(text, voice, …) -> (audio, sr, timings)`, with one timing per phoneme (`.phoneme`, `.start`, `.end`). It also has a `has_timings` flag. Per the docstring: "The timings are empty unless the model exposes a duration output". Its example uses `kokoro-v1.1-zh.onnx` or a model re-exported with `scripts/export.py` **[repo]**.
- **Stiti's model** `~/.stiti/models/voice/kokoro-v1.0.int8.onnx` has outputs `['audio']` only, with **no `duration`**, so it has **no timestamps** **[tested]**. Re-exporting an English model with durations through `scripts/export.py` is possible in principle **[unverified for int8/English]**.
- hexgrad `kokoro` (PyTorch, Apache-2.0) `KPipeline.join_timestamps(tokens, pred_dur)` gives word `start_ts`/`end_ts` **[repo]**, but PyTorch is too heavy for the RAM budget.
- HeadTTS and Kokoros (Rust) use `onnx-community/Kokoro-82M-v1.0-ONNX-timestamped` for phoneme or word timings [secondary].
- ChalkTalk: timing draws from text-length estimates left about **2 s silences** per line. Switching to real clip duration fixed it.

### Comparison table

| Name | Link | Year | License | Mechanism | Granularity | Strengths | Weaknesses | Fit |
|---|---|---|---|---|---|---|---|---|
| **Per-sentence cue + real clip duration** (ChalkTalk) | [post](https://dev.to/danial_mo/chalktalk-a-whiteboard-tutor-that-draws-like-a-teacher-and-lets-you-raise-your-hand-4jmd) | 2026 | — | Synthesize ahead; ops scheduled across the known duration | Sentence (fractions within) | Works with any TTS; robust | No exact word hits | **Baseline** |
| **OpenMAIC action engine** | [engine.ts](https://github.com/THU-MAIC/OpenMAIC/blob/main/lib/action/engine.ts) | 2025– | MIT | Sequential list; `speech` awaits audio end; `wb_*` await fixed ms; spotlight and laser fire and forget | Action | Simple and deterministic; resume by action index | Draws happen between speech, not during | Borrow the sync vs async split and the resume index |
| manim-voiceover bookmarks | [example](https://github.com/ManimCommunity/manim-voiceover/blob/main/examples/bookmark-example.py) | 2022– | MIT | `<bookmark mark='A'/>` in text; `wait_until_bookmark`; Whisper or Azure word times | Word | Author-friendly | Needs word timings | **Bookmark syntax for `at`** |
| SSML `<mark>` | [W3C SSML 1.1](https://www.w3.org/TR/speech-synthesis11/#S3.3.2) | 2010 | W3C | TTS engine emits a mark event when it reaches the tag | Word | Standard | Kokoro has no SSML | Concept only |
| Web Speech API `boundary` / `mark` events | [MDN](https://developer.mozilla.org/en-US/docs/Web/API/SpeechSynthesisUtterance/boundary_event) | 2012– | Web standard | Browser TTS fires word boundaries | Word | Free, in-browser | System voices, not Kokoro; macOS voices vary | Fallback only |
| EPUB 3 Media Overlays (SMIL) | [W3C](https://www.w3.org/TR/epub-33/#sec-media-overlays) | 2011– | W3C | `<par>` pairs a text fragment with an audio clip start/end | Phrase | Proven book-audio sync model | Authoring format | Mirrors our cue = text + clip + actions |
| WebVTT + `TextTrack.cuechange` | [MDN](https://developer.mozilla.org/en-US/docs/Web/API/TextTrack/cuechange_event) | 2010– | Web standard | Timed cues on a media element fire events | Any | Native browser timing | Needs audio in the browser | Option if audio moves to the browser |
| Motion Canvas time events | [docs](https://motioncanvas.io/docs/time-events) | 2022– | MIT | `yield* waitUntil('event')`, drag events to match the voiceover; `useDuration` | Any | Great authoring | Offline video | Concept |
| GSAP timeline labels / `addPause` | [gsap.com](https://gsap.com/docs/v3/GSAP/Timeline/) | 2006– | Standard no-charge (not OSI) | Timeline with labels, pause, seek, reverse | Any | Seek and rewind for free | License not OSI | No (own scheduler is enough) |
| kokoro-onnx `create_timed` | [repo](https://github.com/thewh1teagle/kokoro-onnx) | 2026 | MIT | Phoneme timings when the model has a duration output | Phoneme → word | Local and free; exact | Current Stiti model lacks durations **[tested]** | **Upgrade path for word bookmarks** |
| Kokoro KPipeline timestamps | [repo](https://github.com/hexgrad/kokoro) | 2025 | Apache-2.0 | `pred_dur` → word `start_ts`/`end_ts` | Word | Official | PyTorch RAM | No |
| Forced alignment after TTS (Whisper word timestamps via mlx-whisper, already installed) | [mlx-examples](https://github.com/ml-explore/mlx-examples) | 2023– | MIT | Transcribe your own TTS output with word timestamps | Word | Works with any TTS | Adds about 100s of ms and RAM per sentence; overkill | Not needed |
| excalidraw-mcp stream order | above | 2026 | MIT | Visual order = token order; camera first | Element | Natural "teacher drawing" order | No audio | Order rules only |

### Cue / timeline JSON schema proposal
Design rules:
- A flat op object with a `type` enum and **nullable** fields. All keys are required, and `additionalProperties:false`. This satisfies Groq strict *and* Cerebras strict, which supports no `oneOf`, no `minItems` and no `pattern`.
- Keep the schema under Cerebras's 5,000-character limit.
- The LLM writes `segment`. Python adds runtime fields (`audio_ms`, `seq`, `t0`).

**What the LLM emits per segment (strict `json_schema`):**

```json
{
  "segment_id": "s3",
  "title": "Light reactions",
  "cues": [
    {
      "id": "s3c1",
      "say": "Sunlight hits the leaf, and the chloroplast captures that energy.",
      "ops": [
        {"type": "focus_region", "id": null, "text": null, "region": "main", "place": null, "ref": null,
         "shape": null, "nodes": null, "edges": null, "mermaid": null, "style": null, "at": "start"},
        {"type": "box", "id": "sun", "text": "Sunlight", "region": "main", "place": "left", "ref": null,
         "shape": "ellipse", "nodes": null, "edges": null, "mermaid": null, "style": "warm", "at": "Sunlight"},
        {"type": "box", "id": "chl", "text": "Chloroplast", "region": "main", "place": "right_of", "ref": "sun",
         "shape": "rectangle", "nodes": null, "edges": null, "mermaid": null, "style": "green", "at": "chloroplast"},
        {"type": "arrow", "id": "a1", "text": "light", "region": null, "place": null, "ref": "sun>chl",
         "shape": null, "nodes": null, "edges": null, "mermaid": null, "style": null, "at": "0.6"}
      ]
    },
    {
      "id": "s3c2",
      "say": "Inside, water is split, releasing oxygen and making ATP.",
      "ops": [
        {"type": "graph", "id": "g1", "text": null, "region": "main", "place": "below", "ref": "chl",
         "shape": null, "nodes": [{"id": "h2o", "text": "Water"}, {"id": "o2", "text": "O2"}, {"id": "atp", "text": "ATP"}],
         "edges": [{"from": "h2o", "to": "o2", "text": null}, {"from": "h2o", "to": "atp", "text": "energy"}],
         "mermaid": null, "style": null, "at": "start"},
        {"type": "highlight", "id": null, "text": null, "region": null, "place": null, "ref": "atp",
         "shape": null, "nodes": null, "edges": null, "mermaid": null, "style": "underline", "at": "ATP"}
      ]
    }
  ],
  "check_question": "Where does the oxygen we breathe come from in this process?"
}
```

- `type` enum: `title`, `text`, `bullet`, `box`, `arrow`, `graph`, `mermaid`, `table_row`, `formula`, `highlight`, `strike`, `erase`, `focus_region`, `clear_board`, `pause_for_answer`.
- `region` enum: `title`, `main`, `side`, `notes`, `aside_qa`.
- `place` enum: `left`, `right_of`, `below`, `above`, `next_line`, `center`.
- `style` enum: `plain`, `warm`, `green`, `blue`, `underline`, `circle`, `box`, `marker`.
- `at` is `"start"`, `"end"`, a fraction `"0.0"`–`"1.0"` of the sentence audio, or **a word copied from `say`** (bookmark). With word timings, a word resolves exactly. Without them, it resolves proportionally by character offset of the word in `say`. This keeps the output schema the same regardless of TTS ability.
- `ref` is either an element id or `"from>to"` for arrows. Python's sanitizer rejects unknown refs.
- Caps enforced in code: ops per cue ≤ 4, label ≤ 28 characters, graph ≤ 8 nodes.

**What Python sends to the browser (runtime, already laid out):**

```json
{"type": "cue", "seq": 41, "cue_id": "s3c1", "audio_ms": 4120, "replay": false,
 "ops": [{"op": "camera", "at_ms": 0, "rect": [0, 0, 1200, 800]},
         {"op": "add", "at_ms": 310, "anim": "fade", "elements": [{"type": "ellipse", "id": "sun", "x": 80, "y": 200,
           "width": 160, "height": 80, "backgroundColor": "#ffec99", "fillStyle": "solid", "label": {"text": "Sunlight", "fontSize": 20}}]},
         {"op": "add", "at_ms": 2350, "anim": "grow", "elements": [{"type": "arrow", "id": "a1", "x": 240, "y": 240,
           "start": {"id": "sun"}, "end": {"id": "chl"}, "label": {"text": "light"}}]}]}
```

Other messages:
- Server → browser: `{"type":"pause"}`, `{"type":"resume"}`, `{"type":"seek","cue_id":"s3c1","snapshot":[…]}`, `{"type":"aside","ops":[…]}` (Q&A drawings).
- Browser → server: `{"type":"ready"}`, `{"type":"cue_done","seq":41}`, `{"type":"click","element_id":"atp"}` ("explain this"), `{"type":"user_text","text":"…"}`, `{"type":"hand"}` (raise-hand button), `{"type":"error","seq":41,"msg":"mermaid parse …"}`.

### Playback, barge-in, resume, rewind

1. **Prefetch.** Generate segment N+1 with an LLM call while segment N plays. Synthesize Kokoro audio for cues k+1..k+3 while cue k plays.
2. **Play cue k.**
   - Python starts audio through sounddevice and sends the `cue` message at the same moment. On localhost the WS latency is in milliseconds.
   - The browser schedules `at_ms` timers.
   - At the end of the audio, add a ≥150 ms gap, then move to the next cue. Do not wait for `cue_done`; treat it as telemetry. Add a backup timer in case an audio callback never fires (ChalkTalk lesson).
3. **Barge-in.**
   - On VAD speech-start, duck TTS to about 30 % immediately.
   - If STT confirms real speech (≥ 2 words or ≥ 400 ms), stop audio, send `pause` (the browser clears pending timers and jumps running animations to their end state), and record `{segment, cue_id, offset_ms}`.
   - Before any LLM call, route the utterance with Laya's fast path: `pause`/`wait` → stay paused; `continue`/`go on` → resume; `repeat`/`say that again` → replay the cue; `go back` → rewind one cue or segment; `slower`/`faster` → change Kokoro speed; `skip` → next segment.
   - Otherwise it is a **question**. Send the LLM `{lesson title, segment title, last 3 "say" lines, board summary "id | type | text" (ChalkTalk), question}` and stream the answer into `region: aside_qa`, using the same cue format.
   - Then ask "Shall I continue?".
4. **Resume:** replay the interrupted cue **from its start** with `replay: true`, optionally prefixed by "As I was saying…". Its ops are idempotent by id, so the board does not duplicate anything.
5. **Rewind:** after each cue the browser stores `board.snapshot()`, or Python stores the laid-out op log. Seeking to cue j sends `seek` with the snapshot at the end of cue j−1, then plays cue j. Snapshots for a 30-minute lesson are small, at hundreds of elements.
6. **Pacing:**
   - About 150 spoken words per minute means a 30-minute lesson is about 4,500 words. Split it into 6–8 segments of 12–25 cues each.
   - Insert `pause_for_answer` (a check question) at segment ends. Retrieval practice belongs here; see the sibling note `tutoring_pedagogy.md`.
   - Clear or scroll the board between segments using a frame per segment, so the camera can pan to a fresh area instead of wiping the board.

---

## 6. Book (PDF/EPUB) → teachable outline, locally

### Takeaway
**Structure comes from the file, not the LLM. The free LLM only sees compressed chapter extracts.**
- For PDFs use **pypdfium2**: Apache-2.0/BSD-3, already installed via pdfplumber, with `get_toc()` and `get_page_label()` for printed page numbers. When there is no outline, fall back to **font-size and numbered-heading detection** with pdfplumber, then to an LLM parse of the printed "Contents" pages.
- For EPUB, use **MarkItDown's built-in `EpubConverter`**, which is MIT, needs no extra dependency and reads in spine order. Parse `nav.xhtml`/`toc.ncx` for the TOC.
- **EbookLib** is avoided because it is **AGPL-3.0**. **PyMuPDF** is also AGPL-3.0: it is the fastest and best, but keep it optional and note the license.
- Then compress each chapter locally (extractive, with embeddings) to about 2–3K tokens with page tags. Run one LLM **map** call per chapter, then one **reduce** call into a 30-minute lesson plan. Generate segment scripts **lazily** during playback.
- Citations are **chunk ids → page labels**, validated in code.

### Cited findings (measured on this Mac)
- **"Aho – Compilers: Principles, Techniques, and Tools 2e" PDF (1,038 pages) with pypdfium2 [tested]:**
  - Open plus `get_toc()` took 3 ms, but the book has **0 outline entries**. This is common for scanned or older PDFs, so the fallback is needed.
  - Full text extraction took **2.0 s total (1.9 ms/page)** for 2,153,634 characters, about **538K tokens**. Peak RSS was 153 MB.
- **pdfplumber heading detection [tested]:** about 45 ms/page (40 pages in 1.79 s, so roughly 45 s for the whole book). Body font was size 10. It found "Chapter / 1 / Introduction" at sizes 20–25 and "1.1 Language Processors" at size 14. Figures produce large-font noise, so combine the font size with the regex `^(Chapter\s+\d+|\d+(\.\d+)*)\s+[A-Z]` and a minimum line length.
- **Token budget vs free tiers:**
  - 538K tokens is more than Groq's **200K TPD per model**. At 8K TPM, even one pass would take 67+ minutes.
  - Cerebras's 1M TPD could do one pass (≥18 min at 30K TPM), but that would spend most of the day's quota.
  - So **never send the whole book.** Twenty chapters × about 3K-token extracts is about 60K tokens for the map step, which is feasible.
  - Estimated cost per 30-minute lesson: outline about 10K + 8 segments × about 4.5K (in+out) + Q&A, roughly 50–60K tokens. That is about 3 lessons per day per Groq model, plus Cerebras **[estimate]**.
- **MarkItDown 0.1.9 [repo]:** `_epub_converter.py` uses `zipfile` + `defusedxml` and subclasses `HtmlConverter`, so it is MIT with no extra dependencies. The PDF converter uses pdfminer + pdfplumber and does **not** emit page markers, which is why page citations need pypdfium2 or pdfplumber page by page.
- **Summarization research:**
  - BooookScore ([arXiv 2310.00785](https://arxiv.org/abs/2310.00785), ICLR 2024): **hierarchical merging** gives more coherent but less detailed summaries than **incremental updating**. Larger chunks did not help hierarchical merging.
  - Context-Aware Hierarchical Merging ([arXiv 2502.00977](https://arxiv.org/abs/2502.00977), ACL Findings 2025): plain hierarchical merging **amplifies hallucinations**. Feeding source context (extractive selection or retrieval) at each merge helps. "Generating accurate citations is challenging", so cite **ids** and verify them in code.

### Comparison table: extraction tools

| Name | Link | Version / year | License | How it works | API for structure | Strengths | Weaknesses | Fit |
|---|---|---|---|---|---|---|---|---|
| **pypdfium2** | [repo](https://github.com/pypdfium2-team/pypdfium2) | 5.15.2 (in lock) | **Apache-2.0 / BSD-3** | PDFium bindings | `PdfDocument.get_toc()`, `get_page_label(i)`, `page.get_textpage().get_text_range()` | Fast (1.9 ms/page **[tested]**); permissive; already installed | No font sizes in the high-level API (raw `FPDFText_GetFontSize` exists) | **Primary PDF** |
| **pdfplumber** | [repo](https://github.com/jsvine/pdfplumber) | 0.11.10 (in lock) | MIT | pdfminer layout | `extract_words(extra_attrs=["size","fontname"])` | Font-size headings **[tested]** | About 45 ms/page | **Heading fallback** |
| PyMuPDF (fitz) | [repo](https://github.com/pymupdf/PyMuPDF) | 2.1 | **AGPL-3.0** (or commercial) | MuPDF | `doc.get_toc()`, `page.get_text("dict")` with span sizes | Fastest and richest | AGPL: fine only if Stiti ships under an AGPL-compatible license | Optional |
| pymupdf4llm | [docs](https://pymupdf.readthedocs.io/en/latest/pymupdf4llm/) | — | AGPL-3.0 | PyMuPDF → Markdown with headers by font size | `to_markdown(page_chunks=True)` | Markdown with page chunks | AGPL | Optional |
| **MarkItDown** | [repo](https://github.com/microsoft/markitdown) | 0.1.9 (in deps) | MIT | Converters to Markdown (EPUB, PDF, DOCX…) | Markdown headings | Already used by Stiti; EPUB in spine order | PDF output has no page markers; EPUB TOC not exposed **[repo]** | **Primary EPUB** |
| EbookLib | [repo](https://github.com/aerkalov/ebooklib) | active | **AGPL-3.0** | EPUB read/write | `book.toc`, `get_items_of_type` | Full EPUB model | AGPL | Avoid; parse `nav.xhtml`/`toc.ncx` with `zipfile`+`lxml` (both present) |
| pypdf | [repo](https://github.com/py-pdf/pypdf) | — | BSD-3 | Pure-Python PDF | `reader.outline`, `page_labels` | Pure Python | Slower text extraction **[unverified speed]** | Backup |
| Docling | [repo](https://github.com/docling-project/docling) | active | MIT | Layout models → DoclingDocument with section tree | `doc.iterate_items()` with levels | Best structure on hard PDFs | About 2.5 GB peak (sibling note); slow | Only for books with no TOC and noisy fonts, overnight |
| Marker | [repo](https://github.com/datalab-to/marker) | active | GitHub shows Apache-2.0 (model weights may carry separate terms **[unverified]**) | Deep-learning PDF → Markdown | Headings in Markdown | High accuracy | GPU/RAM heavy | No |
| GROBID | [repo](https://github.com/kermitt2/grobid) | active | Apache-2.0 | Java ML for scholarly PDFs → TEI | TEI sections | Papers | JVM; papers, not books | No |
| unstructured | [repo](https://github.com/Unstructured-IO/unstructured) | active | Apache-2.0 | Partitioning to typed elements (`Title`, `NarrativeText`) | element categories | Generic | Heavy dependencies | No |

### Comparison table: outline and summarization strategies

| Strategy | Source | Year | How it works | Strengths | Weaknesses | Fit under 8K TPM / 200K TPD |
|---|---|---|---|---|---|---|
| **TOC-first, no LLM** | (engineering) | — | Use the PDF outline or EPUB nav as the lesson skeleton | Free, exact pages | Some books have no outline | **Step 1** |
| Recursive book summarization | Wu et al., [arXiv 2109.10862](https://arxiv.org/abs/2109.10862) | 2021 | Summarize chunks, then summaries, recursively | Classic | Many calls; hallucination compounds | Too many tokens |
| Hierarchical merging | BooookScore | 2024 | Chunk summaries merged pairwise | Coherent | Less detail; hallucination amplifies (CAHM) | Use with context (below) |
| Incremental updating | BooookScore | 2024 | Running summary updated per chunk | More detail | Order-dependent; long prompts | Not on 8K TPM |
| **Context-aware hierarchical merging** | [CAHM](https://arxiv.org/abs/2502.00977) | 2025 | Merge steps get extractive or retrieved source passages | Fewer hallucinations | More input tokens | **Reduce step uses chapter extracts + page ids** |
| RAPTOR | [arXiv 2401.18059](https://arxiv.org/abs/2401.18059) | 2024 | Cluster chunks → summarize → tree for retrieval | Great for Q&A at any level | Many summary calls | Use lazily for Q&A only **[unverified details]** |
| Chain of Agents | [arXiv 2406.02818](https://arxiv.org/abs/2406.02818) | 2024 | Sequential worker agents pass notes; a manager answers | Long context with small windows | Sequential latency | Not needed **[unverified]** |
| LangChain map-reduce / refine | [docs](https://python.langchain.com) | 2023– | Map summaries → reduce, or refine iteratively | Familiar | Framework weight; same token cost | Pattern only |
| LlamaIndex tree_summarize | [docs](https://docs.llamaindex.ai) | 2023– | Bottom-up tree of summaries | Built-in | Framework weight | Pattern only |
| **Local extractive pre-compression** (embedding centrality / TextRank with Stiti's local embedder) | (classic; e.g. TextRank 2004) | — | Pick the top sentences per section locally, tagged `[p.N]` | Zero LLM tokens; keeps exact quotes for citations | Less fluent (the LLM fixes that) | **Step 2: makes the free tier feasible** |

### Recommended book → lesson pipeline

```
ingest (local, background, AC power ok)
  PDF : pypdfium2 get_toc() + get_page_label() ; per-page text (1.9 ms/page)
        no TOC -> pdfplumber font-size + numbered-heading regex -> heading list
        still messy -> LLM parses the printed "Contents" pages (1 call, ~3K tokens) -> map printed page -> index via labels
  EPUB: zipfile + lxml read nav.xhtml / toc.ncx ; MarkItDown EpubConverter for chapter Markdown
  -> sections[] = {sec_id, title, level, page_start_label, page_end_label, text}
  -> chunks (300–500 tokens) with ids "c0412" and page labels, stored in Postgres/pgvector (reuses Stiti's doc pipeline)

compress (local, no LLM)
  per chapter: embed chunks; take top-k by centrality + first/last paragraphs -> ~2–3K tokens, each line tagged [c0412|p.37]

map (LLM, 1 call per chapter, Groq gpt-oss-20b or Cerebras; ~3.5K in / ~400 out)
  -> {chapter_id, big_idea, 3–5 key_points[{text, cites:[chunk ids]}], prerequisite_terms, one_diagram_idea}

reduce (LLM, 1 call; strict JSON)
  input: all chapter cards (~20 x 400 tokens) + owner's goal ("overview" vs "chapter 4 deep dive") + minutes=30
  -> lesson_plan{segments[6–8]{title, minutes, key_points, cites, diagram_idea, check_question}}

script (LLM, lazily during playback; strict JSON §5; context = segment plan + the cited chunk texts only)
validate (code): every cite id exists; quote spans found in chunk text; drop/flag claims with no cite
display: page citations shown small on the board ("p. 37") and spoken only on request
```

- Scope choice matters most. A **whole-book overview in 30 minutes** gives 6–8 big ideas, one per segment. A **chapter deep dive** spends the same tokens on one chapter's chunks.
- Ask the owner which one they want; this fits the intake style.
- Cache map cards per book so later lessons and Q&A cost nothing.

---

## 7. Unverified / open items
- Whether **draw.io embed mode works when self-hosted**. The docs say embed.diagrams.net only.
- The **mermaid-to-excalidraw 2.x list of native diagram types**. I verified only the 3.x README and a flowchart test on both versions.
- **pywebview + rumps** coexisting in one process (both want the macOS main thread). This may need a separate process.
- Whether **kokoro-onnx `scripts/export.py`** can produce an English model with a duration output at int8 and comparable quality.
- No **head-to-head JSON vs Mermaid reliability** numbers exist for gpt-oss-20b or qwen3.8-27b. Run a 20-prompt eval once API keys are set (`.env` has none today): measure the parse rate, the sanitizer rejection rate and overlap count after layout.
- The Groq structured-outputs page contradicts itself on whether strict mode covers qwen3.8-27b. The model list says yes; a comparison table says GPT-OSS only. Test it.
- Browser RAM was measured once, in a fresh headless Chrome. Measure again in the owner's real browser.
- Photomath, Napkin, Whimsical and Eraser internals come from secondary sources.
