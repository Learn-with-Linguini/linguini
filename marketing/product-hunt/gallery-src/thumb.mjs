import { chromium } from "playwright";
const SRC = "file:///home/user/linguini/marketing/product-hunt/gallery-src";
const OUT = "/home/user/linguini/marketing/product-hunt/gallery";
const browser = await chromium.launch({ executablePath: "/opt/pw-browsers/chromium-1194/chrome-linux/chrome" });
const ctx = await browser.newContext({ viewport: { width: 240, height: 240 }, deviceScaleFactor: 1 });
const page = await ctx.newPage();
await page.goto(`${SRC}/thumbnail.html`); await page.evaluate(() => window.uiReady);
await page.screenshot({ path: `${OUT}/thumbnail.png` });
await page.goto(`${SRC}/thumbnail-anim.html`); await page.evaluate(() => window.uiReady);
const FPS = 25, LOOP = 2400, N = (LOOP / 1000) * FPS;
await page.evaluate(() => document.getAnimations().forEach(a => a.pause()));
for (let f = 0; f < N; f++) {
  const t = (f * 1000) / FPS;
  await page.evaluate(t => document.getAnimations().forEach(a => { a.currentTime = t; }), t);
  await page.screenshot({ path: `ph/frames/f${String(f).padStart(3, "0")}.png` });
}
console.log("frames", N);
await browser.close();
