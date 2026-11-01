import assert from "node:assert/strict";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import test from "node:test";
import { JSDOM } from "jsdom";
import { rolldown } from "rolldown";
import type { Lang, Scene } from "../src/marketing/data/types.ts";

const dom = new JSDOM("<!doctype html><html><body></body></html>", { url: "http://localhost/" });
for (const key of ["window", "document", "localStorage", "HTMLElement"] as const) {
  Object.defineProperty(globalThis, key, { value: key === "window" ? dom.window : dom.window[key], configurable: true });
}
(globalThis as Record<string, unknown>).IS_REACT_ACT_ENVIRONMENT = true;
Object.defineProperty(dom.window, "matchMedia", { value: () => ({ matches: true }) });
dom.window.scrollTo = () => {};
globalThis.requestAnimationFrame = callback => setTimeout(() => callback(0), 0) as unknown as number;
globalThis.cancelAnimationFrame = handle => clearTimeout(handle);
const NativeMessageChannel = globalThis.MessageChannel;
const channels: MessageChannel[] = [];
globalThis.MessageChannel = class extends NativeMessageChannel {
  constructor() { super(); channels.push(this); }
};
const folder = mkdtempSync(join(tmpdir(), "demo-vocabulary-"));
const entry = join(dirname(fileURLToPath(import.meta.url)), `.demoVocabulary-${crypto.randomUUID()}.ts`);
writeFileSync(entry, [
  'export { createElement as h, act } from "react";',
  'export { createRoot } from "react-dom/client";',
  'export { Session } from "../src/marketing/components/try/Session";',
  'export { scenes } from "../src/marketing/data/scenes";',
].join("\n"));
let bundled: unknown;
try {
  const bundler = await rolldown({ input: entry, platform: "node", resolve: { extensions: [".tsx", ".ts", ".js"] },
    plugins: [{ name: "test-css", resolveId: id => id.endsWith(".css") ? "\0empty-css" : null,
      load: id => id === "\0empty-css" ? "export default {};" : null }],
  });
  try {
    const { output } = await bundler.generate({ format: "esm" });
    const path = join(folder, "bundle.mjs");
    writeFileSync(path, `import.meta.env = {};\n${output[0].code}`);
    bundled = await import(pathToFileURL(path).href);
  } finally { await bundler.close(); }
} finally { rmSync(entry, { force: true }); rmSync(folder, { recursive: true, force: true }); }
const { h, act, createRoot, Session, scenes } = bundled as {
  h: typeof import("react").createElement; act: typeof import("react").act;
  createRoot: typeof import("react-dom/client").createRoot;
  Session: typeof import("../src/marketing/components/try/Session.tsx").Session;
  scenes: Scene[];
};
const cleanups = new Set<() => Promise<void>>();
async function mount(scene: Scene) {
  const container = dom.window.document.createElement("div");
  dom.window.document.body.appendChild(container);
  const root = createRoot(container);
  const render = (lang: Lang) => root.render(h(Session, { scene, lang, onLangChange: render, onExit: () => {} }));
  await act(async () => render("ko"));
  const cleanup = async () => { await act(async () => root.unmount()); container.remove(); cleanups.delete(cleanup); };
  cleanups.add(cleanup);
  return container;
}
function button(container: Element, label: string) {
  const element = [...container.querySelectorAll("button")].find(candidate => candidate.textContent?.trim() === label);
  assert.ok(element, `Expected button: ${label}`);
  return element;
}
function selection(container: Element, word: string) {
  const element = [...container.querySelectorAll("li button")].find(candidate => candidate.querySelector("[lang]")?.textContent === word);
  assert.ok(element, `Expected word selection: ${word}`);
  return element;
}
async function click(element: HTMLElement) {
  await act(async () => element.click());
}
test.afterEach(async () => { for (const cleanup of [...cleanups]) await cleanup(); });
test.after(() => {
  dom.window.close();
  for (const channel of channels) { channel.port1.close(); channel.port2.close(); }
  globalThis.MessageChannel = NativeMessageChannel;
});

for (const id of ["desk-flatlay", "alpine-castle"]) {
  test(`${id} teaches its required gap word before asking it, including after language changes`, async () => {
    const scene = scenes.find(item => item.id === id);
    assert.ok(scene);
    const target = scene.words.find(word => word.id === scene.blankWordId);
    assert.ok(target, "The fixed gap question needs a word card before it is assessed");
    const ispyTarget = scene.words.find(word => word.ko.word === scene.ispy.ko.answer);
    assert.ok(ispyTarget);
    const optional = scene.words.find(word => word.id !== target.id && word.id !== ispyTarget.id);
    assert.ok(optional);
    const container = await mount(scene);
    assert.ok(button(container, `Start learning ${scene.words.length} words`));
    for (const word of [target, ispyTarget]) {
      const required = selection(container, word.ko.word);
      assert.equal(required.disabled, true);
      assert.match(required.textContent ?? "", /Used in this lesson/);
      await click(required);
      assert.equal(required.getAttribute("aria-pressed"), "true");
    }
    await click(selection(container, optional.ko.word));
    assert.equal(selection(container, optional.ko.word).getAttribute("aria-pressed"), "false");
    const french = container.querySelector<HTMLInputElement>('input[value="fr"]');
    assert.ok(french);
    await click(french);
    assert.equal(selection(container, target.fr.word).disabled, true);
    assert.equal(selection(container, optional.fr.word).getAttribute("aria-pressed"), "false");
    const korean = container.querySelector<HTMLInputElement>('input[value="ko"]');
    assert.ok(korean);
    await click(korean);
    await click(button(container, `Start learning ${scene.words.length - 1} words`));
    const learned = [];
    for (let index = 0; index < scene.words.length - 1; index++) {
      learned.push(container.querySelector('p[lang="ko"]')?.textContent);
      await click(button(container, index === scene.words.length - 2 ? "Play I-Spy" : "Next word"));
    }
    assert.ok(learned.includes(target.ko.word), "Gap noun must be taught before assessment");
    await click(button(container, scene.ispy.ko.answer));
    await click(button(container, "Next task"));
    assert.equal(container.querySelector("h2")?.textContent, "Describe the scene");
    await click(button(container, scene.blank.ko.answer));
    assert.equal(button(container, "Next task").disabled, false);
  });
}
