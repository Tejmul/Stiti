// Headless screenshot for checking pages without the shared browser:
//   node scripts/shot.mjs <url> <out.png> [width=1440] [height=900] [waitMs=2500] [fullPage=0]
import { chromium } from "playwright-core";
import { readdirSync } from "node:fs";
import { homedir } from "node:os";
const cache = `${homedir()}/Library/Caches/ms-playwright`;
const dir = readdirSync(cache).filter((d) => d.startsWith("chromium-")).sort().pop();
const exe = `${cache}/${dir}/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing`;
const [url, out, w = 1440, h = 900, wait = 2500, full = 0] = process.argv.slice(2);
const b = await chromium.launch({ executablePath: exe });
const p = await b.newPage({ viewport: { width: +w, height: +h } });
const errs = [];
p.on("console", (m) => m.type() === "error" && errs.push(m.text()));
p.on("pageerror", (e) => errs.push(String(e)));
await p.goto(url);
await p.waitForTimeout(+wait);
await p.screenshot({ path: out, fullPage: !!+full });
if (errs.length) console.log("console errors:\n" + errs.join("\n"));
await b.close();
