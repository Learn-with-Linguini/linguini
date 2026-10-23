import assert from "node:assert/strict";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import test from "node:test";
import { JSDOM } from "jsdom";
import { rolldown } from "rolldown";

const dom = new JSDOM('<!doctype html><html><head><title>Initial document</title></head><body><div id="root"></div></body></html>', {
  url: "https://www.learnwithlinguini.com/learn/korean",
});
for (const key of ["window", "document", "localStorage", "sessionStorage", "HTMLElement"] as const) {
  Object.defineProperty(globalThis, key, { value: key === "window" ? dom.window : dom.window[key], configurable: true });
}
(globalThis as Record<string, unknown>).IS_REACT_ACT_ENVIRONMENT = true;
dom.window.scrollTo = () => {};
Object.defineProperty(dom.window, "matchMedia", { value: () => ({ matches: true }) });
const analyticsWindow = dom.window as unknown as Window;
const calls = () => (analyticsWindow.dataLayer ?? []).map(command => Array.from(command as IArguments));
const NativeMessageChannel = globalThis.MessageChannel;
const channels: MessageChannel[] = [];
globalThis.MessageChannel = class extends NativeMessageChannel {
  constructor() { super(); channels.push(this); }
};

const folder = mkdtempSync(join(tmpdir(), "analytics-pages-"));
const here = dirname(fileURLToPath(import.meta.url));
const entry = join(here, `.analyticsPages-${crypto.randomUUID()}.ts`);
writeFileSync(entry, 'export { act } from "react"; export const boot = () => import("../src/main.tsx");');
try {
  const bundler = await rolldown({
    input: entry, platform: "node", resolve: { extensions: [".tsx", ".ts", ".js"] },
    plugins: [{
      name: "test-entry-root",
      transform(code, id) {
        if (id.endsWith("/src/main.tsx")) {
          // Expose the real entry's root only to clean up the mounted app after testing.
          code = code.replace('createRoot(document.getElementById("root")!).render(', 'export const root = createRoot(document.getElementById("root")!); root.render(');
        }
        return code.replaceAll("import.meta.env", "({})");
      },
    }, {
      name: "test-css",
      resolveId: id => id.endsWith(".css") ? "\0empty-css" : null,
      load: id => id === "\0empty-css" ? "export default {};" : null,
    }],
  });
  try { await bundler.write({ dir: folder, format: "esm", entryFileNames: "entry.mjs", chunkFileNames: "[name]-[hash].mjs" }); }
  finally { await bundler.close(); }
} finally { rmSync(entry, { force: true }); }

const source = await import(pathToFileURL(join(folder, "entry.mjs")).href) as {
  act: typeof import("react").act;
  boot: () => Promise<{ root: import("react-dom/client").Root }>;
};
const { act } = source;
let root: import("react-dom/client").Root;
const views = () => calls().filter(call => call[0] === "event" && call[1] === "page_view").map(call => call[2] as { page_title: string; page_path: string; page_location: string; send_to: string });
async function waitForHeading(text: string) {
  for (let attempt = 0; attempt < 100; attempt++) {
    if (dom.window.document.querySelector("h1")?.textContent?.includes(text)) return;
    await act(async () => { await new Promise(resolve => setTimeout(resolve, 10)); });
  }
  assert.fail(`Page did not render: ${text}`);
}
async function navigate(path: string, heading: string) {
  const link = dom.window.document.querySelector<HTMLAnchorElement>(`a[href="${path}"]`);
  assert.ok(link, `Expected real router link to ${path}`);
  await act(async () => { link.dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true, cancelable: true })); });
  await waitForHeading(heading);
}
test.before(async () => {
  await act(async () => { root = (await source.boot()).root; });
  await waitForHeading("Learn Korean");
});
test.after(async () => {
  if (root) await act(async () => root.unmount());
  dom.window.close();
  for (const channel of channels) { channel.port1.close(); channel.port2.close(); }
  globalThis.MessageChannel = NativeMessageChannel;
  rmSync(folder, { recursive: true, force: true });
});

test("initial lazy route records its real page title once under StrictMode", () => {
  assert.equal(views()[0]?.page_title, "Learn Korean with photos · Linguini");
  assert.equal(views().length, 1);
  assert.equal(views()[0].page_path, "/learn/korean");
  assert.equal(views()[0].page_location, "https://www.learnwithlinguini.com/learn/korean");
  assert.equal(calls()[0][0], "js");
  assert.equal(calls()[1][0], "config");
  assert.equal(calls()[1][1], "G-CHBF82TVG3");
  assert.equal((calls()[1][2] as Record<string, unknown>).send_page_view, false);
  assert.equal(dom.window.document.querySelectorAll('script[src="https://www.googletagmanager.com/gtag/js?id=G-CHBF82TVG3"]').length, 1);
  assert.deepEqual(analyticsWindow._uxa?.filter(command => command[0] === "trackPageview"), [["trackPageview", "/learn/korean"]]);
});

test("SPA navigation records the destination title rather than the previous page", async () => {
  const before = views().length;
  await navigate("/learn/german", "Learn German");
  const destination = views().slice(before);
  assert.equal(destination.length, 1);
  assert.equal(destination[0].page_title, "Learn German with photos · Linguini");
  assert.equal(destination[0].page_path, "/learn/german");
  assert.equal(destination[0].page_location, "https://www.learnwithlinguini.com/learn/german");
  assert.equal(destination[0].send_to, "G-CHBF82TVG3");
});

test("return navigation records another view with the restored route title", async () => {
  const before = views().length;
  await act(async () => { dom.window.history.back(); });
  await waitForHeading("Learn Korean");
  assert.equal(views().length, before + 1);
  assert.equal(views().at(-1)?.page_title, "Learn Korean with photos · Linguini");
  assert.equal(views().at(-1)?.page_path, "/learn/korean");
  assert.deepEqual(analyticsWindow._uxa?.filter(command => command[0] === "trackPageview"), [
    ["trackPageview", "/learn/korean"], ["trackPageview", "/learn/german"], ["trackPageview", "/learn/korean"],
  ]);
});
