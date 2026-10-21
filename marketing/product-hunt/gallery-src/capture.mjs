import { chromium } from "playwright";
const OUT = process.env.OUT ?? "ph/cap";
const ONLY = process.env.ONLY ?? "hero,session";
const browser = await chromium.launch({ executablePath: "/opt/pw-browsers/chromium-1194/chrome-linux/chrome" });
const HIDE = `nextjs-portal{display:none!important} *{transition:none!important;animation:none!important}`;
const clamps = {};
const cls = c => `[class*="${c}"]`;
async function mk(width, dsf) {
  const ctx = await browser.newContext({ viewport: { width, height: 1000 }, deviceScaleFactor: dsf, reducedMotion: "reduce" });
  const page = await ctx.newPage();
  page.on("pageerror", e => console.log("PAGEERR", String(e)));
  await page.goto("http://localhost:3200/", { waitUntil: "networkidle" });
  await page.addStyleTag({ content: HIDE });
  await page.waitForTimeout(1000);
  return page;
}
// Capture an element with padding; ancestors' backgrounds are cleared so only the
// element's own surface + shadow remain (alpha PNG).
async function pshot(page, loc, name, pad = 0) {
  await loc.first().scrollIntoViewIfNeeded(); await page.waitForTimeout(250);
  const b = await loc.first().evaluate(n => {
    const saved = [];
    for (let p = n.parentElement; p; p = p.parentElement) {
      saved.push([p, p.getAttribute("style")]);
      p.style.setProperty("background", "transparent", "important");
      p.style.setProperty("box-shadow", "none", "important");
      p.style.setProperty("border-color", "transparent", "important");
    }
    const hidden = [];
    for (const el of document.body.querySelectorAll("*")) {
      if (el === n || el.contains(n) || n.contains(el)) continue;
      hidden.push([el, el.style.visibility, el.style.getPropertyPriority("visibility")]);
      el.style.setProperty("visibility", "hidden", "important");
    }
    window.__hidden = hidden;
    window.__saved = saved;
    const r = n.getBoundingClientRect();
    return { x: r.left + scrollX, y: r.top + scrollY, width: r.width, height: r.height };
  });
  await page.screenshot({ path: `${OUT}/${name}.png`, clip: { x: b.x - pad, y: b.y - pad, width: b.width + 2 * pad, height: b.height + 2 * pad }, omitBackground: true, fullPage: true });
  await page.evaluate(() => { for (const [el, v] of window.__hidden) { el.style.removeProperty("visibility"); if (v) el.style.visibility = v; } for (const [p, s] of window.__saved) s === null ? p.removeAttribute("style") : p.setAttribute("style", s); });
  const dx = Math.max(0, pad - b.x), dy = Math.max(0, pad - b.y);
  if (dx || dy) clamps[name] = { left: dx, top: dy };
  console.log(name, Math.round(b.width), Math.round(b.height), dx || dy ? `CLAMPED ${dx},${dy}` : "");
}

if (ONLY.includes("hero")) {
  const page = await mk(Number(process.env.HW ?? 1440), 4);
  await page.addStyleTag({ content: `button${cls("hero-module__")}${cls("__print")}{rotate:0deg!important}` });
  const prints = page.locator("button" + cls("__print"));
  const n = await prints.count();
  for (let i = 0; i < n; i++) await pshot(page, prints.nth(i), `print-${i}`, 64);
  await pshot(page, page.locator(`a.btn`, { hasText: "Start learning free" }), "cta-start", 16);
  await pshot(page, page.locator("header img").first(), "wordmark-header", 6);
  await page.screenshot({ path: `${OUT}/hero-full.png` });
  await pshot(page, page.locator(cls("pastaPicker")), "pasta-picker", 14);
  await pshot(page, page.locator(cls("Features-module__") + cls("__avatarDisc")), "pasta-disc", 30);
  await pshot(page, page.locator(cls("Features-module__") + cls("__avatar")).first(), "pasta-avatar", 16);
  await pshot(page, page.locator("#features " + cls("__week")), "feat-week", 30);
  await pshot(page, page.locator("#features " + cls("__stats")), "feat-stats", 30);
  await pshot(page, page.locator("#features " + cls("__streak")), "feat-streak", 30);
  await pshot(page, page.locator("#features " + cls("__chat")), "feat-chat", 30);
  await pshot(page, page.locator("#features " + cls("__bubbleYou")), "feat-bubble-you", 24);
  await pshot(page, page.locator("#features " + cls("__bubbleThem")), "feat-bubble-them", 24);
  await pshot(page, page.locator("#features " + cls("__spyPhoto")), "feat-spy-photo", 24);
  await pshot(page, page.locator("#features " + cls("__voice")), "feat-voice", 30);
  await page.context().close();
}

if (ONLY.includes("session")) {
  const page = await mk(1024, 4);
  await page.evaluate(() => scrollTo(0, 0));
  await page.getByRole("button", { name: /Across the bay/ }).click({ force: true });
  await page.getByRole("heading", { name: /Found/ }).waitFor({ timeout: 8000 });
  await page.addStyleTag({ content: HIDE });
  await page.waitForTimeout(1500);
  await page.mouse.move(1, 1);
  const panel = page.locator(cls("session-module__") + cls("__panel"));
  const photo = page.locator(cls("photoFrame"));
  await pshot(page, page.locator(cls("session-module__") + cls("__layout")), "s-review-layout", 30);
  await pshot(page, photo, "s-review-photo", 56);
  await pshot(page, page.locator(cls("__found")).first(), "s-review-found", 20);
  await pshot(page, panel, "s-review-panel", 30);
  await pshot(page, page.locator(cls("langToggle")).first(), "lang-toggle", 12);
  await page.getByRole("button", { name: /Start learning/ }).click(); await page.waitForTimeout(800);
  await page.mouse.move(1, 1);
  await pshot(page, page.locator(cls("wordCard")), "s-words-card", 48);
  await pshot(page, panel, "s-words-panel", 30);
  await pshot(page, photo, "s-words-photo", 56);
  for (let i = 1; i < 5; i++) {
    await page.getByRole("button", { name: "Next word" }).click(); await page.waitForTimeout(300);
    await pshot(page, page.locator(cls("wordCard")), `s-words-card-${i}`, 48);
  }
  await page.getByRole("button", { name: "Play I-Spy" }).click(); await page.waitForTimeout(600);
  await page.getByRole("button", { name: "Show translation" }).click();
  await page.getByRole("button", { name: "el mar", exact: true }).click(); await page.waitForTimeout(800);
  await page.mouse.move(1, 1);
  await pshot(page, panel, "s-ispy-panel", 30);
  await pshot(page, page.locator(cls("__says")), "s-ispy-says", 48);
  await pshot(page, page.locator("fieldset" + cls("__choices")), "s-ispy-choices", 20);
  await pshot(page, page.locator(cls("__feedback")).first(), "s-ispy-feedback", 12);
  await pshot(page, photo, "s-ispy-photo", 56);
  await page.getByRole("button", { name: "Next task" }).click(); await page.waitForTimeout(500);
  await page.getByRole("button", { name: "coches", exact: true }).click(); await page.waitForTimeout(500);
  await pshot(page, panel, "s-blank-panel", 30);
  await page.getByRole("button", { name: "Next task" }).click(); await page.waitForTimeout(500);
  for (const t of ["El", "puente", "rojo", "está", "sobre", "el", "mar."]) await page.locator("fieldset", { has: page.getByText("Word tiles", { exact: true }) }).getByRole("button", { name: t, exact: true }).click();
  await page.getByRole("button", { name: "Check sentence" }).click(); await page.waitForTimeout(500);
  await pshot(page, panel, "s-build-panel", 30);
  await page.getByRole("button", { name: /Write today/ }).click(); await page.waitForTimeout(500);
  await pshot(page, panel, "s-journal-panel", 30);
  await page.getByRole("button", { name: /Save to journal/ }).click(); await page.waitForTimeout(1200);
  await pshot(page, panel, "s-done-panel", 30);
  await pshot(page, page.locator(cls("journalCard")), "s-done-journal", 48);
  await pshot(page, page.locator(cls("session-module__") + cls("__streak")), "s-done-streak", 24);
  await pshot(page, page.locator(cls("__xpBig")), "s-done-xp", 16);
  await page.context().close();
}
await browser.close();
import("node:fs").then(fs => fs.writeFileSync(`${OUT}/clamps.json`, JSON.stringify(clamps)));
