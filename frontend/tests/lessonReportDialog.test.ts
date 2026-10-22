import assert from "node:assert/strict";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import test from "node:test";
import { JSDOM } from "jsdom";
import { rolldown } from "rolldown";

const dom = new JSDOM("<!doctype html><html><body></body></html>", { url: "http://localhost/" });
for (const key of ["window", "document", "localStorage", "HTMLElement"] as const) {
  Object.defineProperty(globalThis, key, { value: key === "window" ? dom.window : dom.window[key], configurable: true });
}
(globalThis as Record<string, unknown>).IS_REACT_ACT_ENVIRONMENT = true;
const originalFetch = globalThis.fetch;
const requests: unknown[] = [];
let reply: () => Response | Promise<Response> = () => Response.json({ id: "report" });
globalThis.fetch = async (_input, options) => {
  requests.push(JSON.parse(String(options?.body)));
  return reply();
};
const NativeMessageChannel = globalThis.MessageChannel;
const channels: MessageChannel[] = [];
globalThis.MessageChannel = class extends NativeMessageChannel {
  constructor() { super(); channels.push(this); }
};

const folder = mkdtempSync(join(tmpdir(), "lesson-report-"));
const entry = join(dirname(fileURLToPath(import.meta.url)), `.lessonReport-${crypto.randomUUID()}.ts`);
writeFileSync(entry, [
  'export { createElement as h, act } from "react";',
  'export { createRoot } from "react-dom/client";',
  'export { ReportIssueLink } from "../src/components/ReportIssueLink";',
].join("\n"));
let bundled: unknown;
try {
  const bundler = await rolldown({ input: entry, platform: "node", resolve: { extensions: [".tsx", ".ts", ".js"] },
    plugins: [{ name: "test-environment", transform: code => code.replaceAll("import.meta.env", '({ VITE_API_BASE_URL: "http://test.local" })') }, {
      name: "test-css", resolveId: id => id.endsWith(".css") ? "\0empty-css" : null,
      load: id => id === "\0empty-css" ? "export default {};" : null,
    }],
  });
  try {
    const { output } = await bundler.generate({ format: "esm" });
    const path = join(folder, "bundle.mjs");
    writeFileSync(path, output[0].code);
    bundled = await import(pathToFileURL(path).href);
  } finally { await bundler.close(); }
} finally { rmSync(entry, { force: true }); rmSync(folder, { recursive: true, force: true }); }
const { h, act, createRoot, ReportIssueLink } = bundled as {
  h: typeof import("react").createElement; act: typeof import("react").act;
  createRoot: typeof import("react-dom/client").createRoot;
  ReportIssueLink: typeof import("../src/components/ReportIssueLink.tsx").ReportIssueLink;
};
const cleanups = new Set<() => Promise<void>>();
async function mount() {
  const container = dom.window.document.createElement("div");
  dom.window.document.body.appendChild(container);
  const root = createRoot(container);
  await act(async () => root.render(h(ReportIssueLink, { reportType: "Vocabulary answer", fields: [["Task ID", "task-1"]] })));
  const cleanup = async () => { await act(async () => root.unmount()); container.remove(); cleanups.delete(cleanup); };
  cleanups.add(cleanup);
  return container;
}
function button(container: Element, label: string) {
  const found = [...container.querySelectorAll("button")].find(candidate => candidate.textContent?.trim() === label);
  assert.ok(found, `Expected button: ${label}`);
  return found;
}
async function click(element: HTMLElement) { await act(async () => element.click()); }
async function escape() {
  await act(async () => dom.window.document.dispatchEvent(new dom.window.KeyboardEvent("keydown", { key: "Escape", bubbles: true })));
}
function freshForm(container: Element) {
  assert.ok(!container.querySelector("[role=alert]"), "Old submission errors must be cleared");
  assert.ok(!container.querySelector("[role=status]"), "Old success state must be cleared");
  assert.ok([...container.querySelectorAll("[role=radio]")].every(option => option.getAttribute("aria-checked") === "false"));
  assert.equal(button(container, "Send report").disabled, true);
  assert.equal(container.querySelector("textarea")?.value, "");
}
test.beforeEach(() => { requests.length = 0; reply = () => Response.json({ id: "report" }); });
test.afterEach(async () => { for (const cleanup of [...cleanups]) await cleanup(); });
test.after(() => {
  dom.window.close();
  for (const channel of channels) { channel.port1.close(); channel.port2.close(); }
  globalThis.MessageChannel = NativeMessageChannel;
  globalThis.fetch = originalFetch;
});

test("Escape after a successful lesson report reopens a fresh form", async () => {
  const container = await mount();
  const trigger = button(container, "Report this answer");
  await click(trigger);
  await click(button(container, "The displayed solution is incorrect"));
  await click(button(container, "Send report"));
  assert.match(container.querySelector("[role=status]")?.textContent ?? "", /Report sent/);
  assert.equal(requests.length, 1);
  await escape();
  assert.ok(!container.querySelector("[role=dialog]"), "Escape should close the dialog");
  await click(trigger);
  freshForm(container);
});

test("Escape clears failed report state and returns focus to its trigger", async () => {
  reply = () => new Response("unavailable", { status: 503 });
  const container = await mount();
  const trigger = button(container, "Report this answer");
  await click(trigger);
  await click(button(container, "The wording or translation is unclear"));
  await click(button(container, "Send report"));
  assert.ok(container.querySelector("[role=alert]"));
  await escape();
  assert.ok(!container.querySelector("[role=dialog]"), "Escape should close the dialog");
  assert.ok(dom.window.document.activeElement === trigger, "Closing should return focus to the report link");
  await click(trigger);
  freshForm(container);
});

test("Escape cannot dismiss a lesson report while its submission is pending", async () => {
  let finish: ((value: Response) => void) | undefined;
  reply = () => new Promise(resolve => { finish = resolve; });
  const container = await mount();
  await click(button(container, "Report this answer"));
  await click(button(container, "Something else"));
  await click(button(container, "Send report"));
  assert.ok(finish);
  await escape();
  assert.ok(container.querySelector("[role=dialog]"));
  assert.equal(requests.length, 1);
  await act(async () => finish!(Response.json({ id: "report" })));
  assert.match(container.querySelector("[role=status]")?.textContent ?? "", /Report sent/);
});
