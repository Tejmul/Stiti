// Renders the static share/icon images from the real landing page (its fonts, product shot and particle sphere),
// so they always match the site and work with the static export (plain files, no image route at runtime):
//   src/app/opengraph-image.png + src/app/twitter-image.png   1200×630
//   public/apple-touch-icon.png                                 180×180
// Usage: build + serve the public site first, then
//   node scripts/og.mjs [url=http://127.0.0.1:7400/]
import { chromium } from "playwright-core";
import { copyFileSync, readdirSync } from "node:fs";
import { homedir } from "node:os";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("..", import.meta.url));
const cache = `${homedir()}/Library/Caches/ms-playwright`;
const dir = readdirSync(cache).filter((d) => d.startsWith("chromium-")).sort().pop();
const exe = `${cache}/${dir}/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing`;
const url = process.argv[2] || "http://127.0.0.1:7400/";

const b = await chromium.launch({ executablePath: exe });

// ---- 1200×630 share image: the hero, re-laid for a card (reduced motion = the full conversation, still sphere)
const p = await b.newPage({ viewport: { width: 1200, height: 630 }, deviceScaleFactor: 1, reducedMotion: "reduce" });
await p.goto(url);
await p.evaluate(() => document.fonts.ready);
await p.addStyleTag({ content: `
  .nav, .skip, .cursor, .hero__ctas, .hero__label { display: none !important; }
  .pg-landing .hero { min-height: 630px; height: 630px; padding: 0; }
  .pg-landing .hero__grid { grid-template-columns: minmax(0, .9fr) minmax(0, 1.1fr); column-gap: 40px; }
  .pg-landing .container { padding: 0 56px; }
  .pg-landing .hero__title { font-size: 76px; }
  .pg-landing .hero__quote p { font-size: 22px; }
  .pg-landing .hero__facts { margin-top: 26px; font-size: 12px; }
  .og-brand { display: flex; align-items: center; gap: 14px; margin: 0 0 34px; font: 600 26px/1 var(--display); letter-spacing: -.02em; color: var(--ink); }
  .og-brand i { display: grid; place-items: center; width: 46px; height: 46px; border-radius: 50%; background: var(--ink);
    color: #fff; font: 600 23px/1 var(--display); font-style: normal; letter-spacing: -.04em; }
` });
await p.evaluate(() => {
  const brand = document.createElement("div");
  brand.className = "og-brand";
  brand.innerHTML = "<i>S</i>Stiti";
  document.querySelector(".hero__copy").prepend(brand);
  dispatchEvent(new Event("resize"));      // re-anchor the sphere behind the shot at its new place
});
await p.waitForTimeout(3500);              // field re-layout (150 ms debounce) + settle
const og = `${root}src/app/opengraph-image.png`;
await p.screenshot({ path: og });
copyFileSync(og, `${root}src/app/twitter-image.png`);

// ---- apple-touch-icon: the plain "S" mark, full-bleed (iOS rounds the corners itself)
const q = await b.newPage({ viewport: { width: 180, height: 180 }, deviceScaleFactor: 1 });
await q.goto(url);
await q.evaluate(() => document.fonts.ready);
await q.evaluate(() => {
  document.body.innerHTML = '<div style="position:fixed;inset:0;display:grid;place-items:center;background:#262b57;color:#fff;' +
    'font:600 112px/1 var(--display);letter-spacing:-.04em;z-index:99999"><span style="transform:translateY(-4px)">S</span></div>';
});
await q.waitForTimeout(300);
await q.screenshot({ path: `${root}public/apple-touch-icon.png` });

await b.close();
console.log("wrote opengraph-image.png, twitter-image.png, apple-touch-icon.png");
