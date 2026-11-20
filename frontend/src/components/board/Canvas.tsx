"use client";
// The Excalidraw canvas, loaded only in the browser (next/dynamic ssr:false from BoardApp). Its hand-drawn fonts
// come from /excalidraw/fonts on this Mac (copied by scripts/excalidraw-assets.mjs), never from a CDN.
import "@excalidraw/excalidraw/index.css";
import * as lib from "@excalidraw/excalidraw";

type Lib = typeof lib;

export default function Canvas({ onReady, onChange }: {
  onReady: (api: unknown, l: Lib) => void;
  onChange: (appState: { selectedElementIds?: Record<string, boolean> }) => void;
}) {
  return (
    <lib.Excalidraw
      excalidrawAPI={(api) => onReady(api, lib)}
      zenModeEnabled
      theme="light"
      initialData={{ appState: { viewBackgroundColor: "#fffdf7", currentItemFontFamily: 5 } }}
      UIOptions={{ canvasActions: { loadScene: false, saveToActiveFile: false, toggleTheme: false } }}
      onChange={(_els, st) => onChange(st as { selectedElementIds?: Record<string, boolean> })}
    />
  );
}
