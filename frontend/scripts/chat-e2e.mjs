// Real chat exchange for checking the chat page end to end (stored in Stiti's real memory: use sparingly).
//   node scripts/chat-e2e.mjs <url-with-#t=> <out-prefix> "<message>" [width=1440] [height=900]
// Writes <out-prefix>-thinking.png (just after sending) and <out-prefix>-receipts.png (reply with receipts open).
import { chromium } from "playwright-core";
import { readdirSync } from "node:fs";
import { homedir } from "node:os";
const cache = `${homedir()}/Library/Caches/ms-playwright`;
const dir = readdirSync(cache).filter((d) => d.startsWith("chromium-")).sort().pop();
const exe = `${cache}/${dir}/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing`;
const [url, out, msg, w = 1440, h = 900] = process.argv.slice(2);
const b = await chromium.launch({ executablePath: exe });
const p = await b.newPage({ viewport: { width: +w, height: +h } });
const errs = [];
p.on("console", (m) => m.type() === "error" && errs.push(m.text()));
p.on("pageerror", (e) => errs.push(String(e)));
await p.goto(url);
await p.waitForSelector(".pg-chat .composer textarea");
await p.waitForFunction(() => document.querySelector(".pg-chat .brain__dot") && !/Connecting/.test(document.querySelector(".pg-chat .brain").textContent));
const before = await p.locator(".pg-chat .msg--stiti .msg__meta").count();
await p.fill(".pg-chat .composer textarea", msg);
await p.keyboard.press("Enter");
await p.waitForTimeout(700);
await p.screenshot({ path: `${out}-thinking.png` });
await p.waitForFunction((n) => document.querySelectorAll(".pg-chat .msg--stiti .msg__meta").length > n, before, { timeout: 60000 });
await p.waitForTimeout(800);
const rec = p.locator(".pg-chat .receipts summary").last();
if (await rec.count()) {
  console.log("receipts:", await rec.textContent());
  await rec.focus();
  await p.keyboard.press("Enter");                     // keyboard opens it
  await p.waitForTimeout(900);
} else console.log("no receipts on this reply");
console.log("meta:", await p.locator(".pg-chat .msg--stiti .msg__meta").last().textContent());
await p.screenshot({ path: `${out}-receipts.png` });
if (errs.length) console.log("console errors:\n" + errs.join("\n"));
await b.close();
