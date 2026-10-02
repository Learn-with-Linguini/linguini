// Render overlay.html to transparent PNG frames with Playwright.
// Usage: node overlay.mjs <base-url> <out-dir> [--from s] [--to s] [--fps n] [--only t1,t2]
import { chromium } from "playwright";
import { mkdirSync, readFileSync } from "node:fs";

const [base, outDir] = process.argv.slice(2);
const arg = (k, d) => {
  const i = process.argv.indexOf(k);
  return i > 0 ? process.argv[i + 1] : d;
};
const T = JSON.parse(readFileSync(new URL("./timeline.json", import.meta.url)));
const fps = Number(arg("--fps", 30));
const from = Number(arg("--from", 0));
const to = Number(arg("--to", T.end));
const only = arg("--only", null);
mkdirSync(outDir, { recursive: true });

const browser = await chromium.launch({
  executablePath: process.env.CHROMIUM || undefined,
  args: ["--font-render-hinting=none", "--disable-lcd-text"],
});
const page = await browser.newPage({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 1 });
await page.goto(`${base}/overlay.html`);
await page.evaluate(() => window.ready);
const stage = page.locator("#stage");

const frames = only
  ? only.split(",").map((t) => Math.round(Number(t) * fps))
  : Array.from({ length: Math.round((to - from) * fps) }, (_, k) => Math.round(from * fps) + k);
for (const f of frames) {
  await page.evaluate((t) => window.seek(t), f / fps);
  await stage.screenshot({ path: `${outDir}/${String(f).padStart(5, "0")}.png`, omitBackground: true });
  if (f % 60 === 0) process.stdout.write(`${f} `);
}
await browser.close();
console.log("done", frames.length);
