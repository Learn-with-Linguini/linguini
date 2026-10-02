// Print a blog post to public/blog/<slug>.pdf with headless Chrome.
// Usage: node scripts/export-post-pdf.mjs [slug] [base-url]
// Build and start the site first (npm run build && npm start). Build with
// NEXT_PUBLIC_SITE_URL set to the production URL so the PDF prints the public link.
// The page receives a `beforeprint` event first, so scroll-driven charts show their final state.
import { writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { openPage, sleep } from "./chrome.mjs";

const slug = process.argv[2] ?? "linguini-business-model";
const base = process.argv[3] ?? "http://localhost:3000";
const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const out = join(root, "public/blog", `${slug}.pdf`);

const page = await openPage(`${base}/blog/${slug}`);
try {
  await page.evaluate("window.dispatchEvent(new Event('beforeprint'))");
  await sleep(2500);
  const pdf = await page.send("Page.printToPDF", { printBackground: true, preferCSSPageSize: true, displayHeaderFooter: false });
  writeFileSync(out, Buffer.from(pdf.data, "base64"));
  console.log(`Wrote ${out}`);
} finally {
  page.close();
}
