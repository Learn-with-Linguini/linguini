// Render gallery compositions: node ph/render.mjs 01-hero [02-spot ...]
// Env: SCALES=1,2  OUTDIR=...
import { chromium } from "playwright";
import { pathToFileURL } from "node:url";
const SRC = "/home/user/linguini/marketing/product-hunt/gallery-src";
const OUT = process.env.OUTDIR ?? "/home/user/linguini/marketing/product-hunt/gallery";
const scales = (process.env.SCALES ?? "1,2").split(",").map(Number);
const jobs = {
  og: { file: "og-social.html", w: 1200, h: 630, name: "og-social-1200x630" },
};
const names = process.argv.slice(2);
const browser = await chromium.launch({ executablePath: "/opt/pw-browsers/chromium-1194/chrome-linux/chrome" });
for (const n of names) {
  const job = jobs[n] ?? { file: `${n}.html`, w: 1270, h: 760, name: n };
  for (const s of scales) {
    const ctx = await browser.newContext({ viewport: { width: job.w, height: job.h }, deviceScaleFactor: s });
    const page = await ctx.newPage();
    page.on("pageerror", e => console.log("ERR", n, String(e)));
    page.on("console", m => m.type() === "error" && console.log("CONSOLE", n, m.text()));
    await page.goto(pathToFileURL(`${SRC}/${job.file}`).href, { waitUntil: "load" });
    await page.evaluate(() => window.uiReady);
    await page.waitForTimeout(200);
    // overflow report: any text element whose scrollWidth exceeds its box
    const issues = await page.evaluate(() => {
      const out = [];
      for (const el of document.querySelectorAll("h1,h2,p,span,div")) {
        if (el.scrollWidth > el.clientWidth + 1 && getComputedStyle(el).overflow !== "visible") out.push(el.className);
      }
      return out;
    });
    if (issues.length) console.log("overflow", n, issues);
    const suffix = s === 1 ? "" : `@${s}x`;
    await page.screenshot({ path: `${OUT}/${job.name}${suffix}.png` });
    await ctx.close();
  }
  console.log("rendered", n);
}
await browser.close();
