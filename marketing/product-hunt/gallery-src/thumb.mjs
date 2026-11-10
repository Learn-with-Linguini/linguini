import { chromium } from "playwright";
import { mkdirSync } from "node:fs";
import { fileURLToPath, pathToFileURL } from "node:url";
import { dirname, resolve } from "node:path";
const SRC = dirname(fileURLToPath(import.meta.url));
const OUT = process.env.OUTDIR ?? resolve(SRC, "../gallery");
const FRAMES = resolve(SRC, "frames");
mkdirSync(FRAMES, { recursive: true });
const launchOpts = process.env.BROWSER_PATH ? { executablePath: process.env.BROWSER_PATH } : {};
const browser = await chromium.launch(launchOpts);
const ctx = await browser.newContext({ viewport: { width: 240, height: 240 }, deviceScaleFactor: 1 });
const page = await ctx.newPage();
await page.goto(pathToFileURL(`${SRC}/thumbnail.html`).href); await page.evaluate(() => window.uiReady);
await page.screenshot({ path: `${OUT}/thumbnail.png` });
await page.goto(pathToFileURL(`${SRC}/thumbnail-anim.html`).href); await page.evaluate(() => window.uiReady);
const FPS = 25, LOOP = 2400, N = (LOOP / 1000) * FPS;
await page.evaluate(() => document.getAnimations().forEach(a => a.pause()));
for (let f = 0; f < N; f++) {
  const t = (f * 1000) / FPS;
  await page.evaluate(t => document.getAnimations().forEach(a => { a.currentTime = t; }), t);
  await page.screenshot({ path: `${FRAMES}/f${String(f).padStart(3, "0")}.png` });
}
console.log("frames", N, "->", FRAMES);
await browser.close();
