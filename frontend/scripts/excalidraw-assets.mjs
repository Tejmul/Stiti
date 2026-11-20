// Copies Excalidraw's hand-drawn fonts into public/excalidraw/ so the whiteboard (/board) loads them from this Mac
// (no CDN at runtime). Skips the 12 MB CJK font. The PUBLIC site build (STITI_PUBLIC=1) does not ship the board,
// so there the folder is removed instead.
import { cpSync, existsSync, readdirSync, rmSync } from "node:fs";
import { join } from "node:path";

const out = join("public", "excalidraw");
if (process.env.STITI_PUBLIC === "1") {
  rmSync(out, { recursive: true, force: true });
  process.exit(0);
}
const src = join("node_modules", "@excalidraw", "excalidraw", "dist", "prod", "fonts");
if (!existsSync(src)) process.exit(0);
for (const f of readdirSync(src)) {
  if (f === "Xiaolai") continue;
  cpSync(join(src, f), join(out, "fonts", f), { recursive: true });
}
