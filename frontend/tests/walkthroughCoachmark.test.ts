import assert from "node:assert/strict";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import test from "node:test";
import { JSDOM } from "jsdom";
import { rolldown } from "rolldown";

const dom = new JSDOM("<!doctype html><html><body></body></html>", { pretendToBeVisual: true });
for (const key of ["window", "document", "HTMLElement"] as const) {
  Object.defineProperty(globalThis, key, { value: key === "window" ? dom.window : dom.window[key], configurable: true });
}
Object.defineProperty(globalThis, "getComputedStyle", { value: dom.window.getComputedStyle.bind(dom.window), configurable: true });
(globalThis as Record<string, unknown>).IS_REACT_ACT_ENVIRONMENT = true;
Object.defineProperty(dom.window.document.documentElement, "clientWidth", { value: 1000, configurable: true });

const frames = new Map<number, FrameRequestCallback>();
let nextFrame = 0;
globalThis.requestAnimationFrame = callback => { frames.set(++nextFrame, callback); return nextFrame; };
globalThis.cancelAnimationFrame = id => { frames.delete(id); };
const viewport = new dom.window.EventTarget();
Object.defineProperty(dom.window, "visualViewport", { value: viewport, configurable: true });
const observers: MockResizeObserver[] = [];
class MockResizeObserver {
  callback: ResizeObserverCallback;
  targets = new Set<Element>();
  disconnected = false;
  constructor(callback: ResizeObserverCallback) { this.callback = callback; observers.push(this); }
  observe(target: Element) { this.targets.add(target); }
  unobserve(target: Element) { this.targets.delete(target); }
  disconnect() { this.disconnected = true; this.targets.clear(); }
  resize() { this.callback([], this as unknown as ResizeObserver); }
}
Object.defineProperty(globalThis, "ResizeObserver", { value: MockResizeObserver, configurable: true });
const focusCalls: { element: HTMLElement; options?: FocusOptions }[] = [];
const nativeFocus = dom.window.HTMLElement.prototype.focus;
dom.window.HTMLElement.prototype.focus = function (options?: FocusOptions) {
  focusCalls.push({ element: this, options }); nativeFocus.call(this, options);
};
const NativeMessageChannel = globalThis.MessageChannel;
const channels: MessageChannel[] = [];
globalThis.MessageChannel = class extends NativeMessageChannel {
  constructor() { super(); channels.push(this); }
};

const folder = mkdtempSync(join(tmpdir(), "walkthrough-test-"));
const entry = join(dirname(fileURLToPath(import.meta.url)), `.walkthrough-${crypto.randomUUID()}.ts`);
writeFileSync(entry, [
  'export { createElement as h, act } from "react";',
  'export { createRoot } from "react-dom/client";',
  'export { WalkthroughCoachmark } from "../src/components/WalkthroughCoachmark";',
].join("\n"));
let surface;
try {
  const bundle = await rolldown({ input: entry, platform: "node", resolve: { extensions: [".tsx", ".ts", ".js"] },
    plugins: [{ name: "empty-css", resolveId: id => id.endsWith(".css") ? "\0css" : null, load: id => id === "\0css" ? "export default {};" : null }],
  });
  try {
    const { output } = await bundle.generate({ format: "esm" });
    const path = join(folder, "bundle.mjs"); writeFileSync(path, output[0].code);
    surface = await import(pathToFileURL(path).href);
  } finally { await bundle.close(); }
} finally { rmSync(entry, { force: true }); rmSync(folder, { recursive: true, force: true }); }
const { h, act, createRoot, WalkthroughCoachmark } = surface;

const cleanups = new Set<() => Promise<void>>();
async function flushFrames() {
  const scheduled = [...frames.entries()];
  await act(async () => { for (const [id, callback] of scheduled) { frames.delete(id); callback(0); } });
}
async function mount() {
  const page = dom.window.document.createElement("main");
  const launcher = dom.window.document.createElement("button"); launcher.textContent = "Start practice";
  const targets = [dom.window.document.createElement("section"), dom.window.document.createElement("section")];
  const bounds = [{ top: 600, left: 30, width: 300, height: 80 }, { top: 900, left: 40, width: 320, height: 140 }];
  const scrolls: { target: Element; options: ScrollIntoViewOptions }[] = [];
  targets.forEach((target, index) => {
    target.getBoundingClientRect = () => new dom.window.DOMRect(bounds[index].left, bounds[index].top, bounds[index].width, bounds[index].height);
    target.scrollIntoView = options => { scrolls.push({ target, options: options as ScrollIntoViewOptions }); bounds[index].top = 150; };
  });
  const container = dom.window.document.createElement("div");
  page.append(launcher, ...targets, container); dom.window.document.body.append(page); launcher.focus();
  const root = createRoot(container);
  const calls = { next: 0, back: 0, skip: 0 };
  const props = { targetRef: { current: targets[0] }, step: 1, totalSteps: 3, title: "First feature", description: "A short guide.", nextLabel: "Next",
    saving: false, onNext: () => calls.next++, onBack: () => calls.back++, onSkip: () => calls.skip++ };
  const render = () => act(async () => root.render(h(WalkthroughCoachmark, props)));
  await render();
  let closed = false;
  const close = async () => { if (closed) return; closed = true; await act(async () => root.unmount()); page.remove(); cleanups.delete(close); };
  cleanups.add(close);
  return { page, launcher, targets, bounds, scrolls, props, calls, render, close };
}
const dialog = () => dom.window.document.querySelector<HTMLElement>('[role="dialog"]')!;
const ring = () => dom.window.document.querySelector<HTMLElement>(".walkthrough-ring")!;
test.beforeEach(() => {
  frames.clear(); focusCalls.length = 0; observers.length = 0;
  dom.window.document.body.style.cssText = ""; dom.window.document.documentElement.style.cssText = "";
});
test.afterEach(async () => { for (const close of [...cleanups]) await close(); });
test.after(() => {
  dom.window.close(); globalThis.MessageChannel = NativeMessageChannel;
  for (const channel of channels) { channel.port1.close(); channel.port2.close(); }
});

test("each guide step positions its target once and focuses the dialog without starting a competing scroll", async () => {
  const view = await mount();
  assert.deepEqual(view.scrolls, [{ target: view.targets[0], options: { block: "center", inline: "nearest", behavior: "instant" } }]);
  assert.equal(dom.window.document.activeElement, dialog());
  assert.deepEqual(focusCalls.at(-1)?.options, { preventScroll: true });
  await flushFrames(); assert.equal(ring().style.top, "148px"); assert.equal(frames.size, 0);
  view.props.targetRef = { current: view.targets[1] }; view.props.step = 2; view.props.title = "Second feature";
  await view.render(); await flushFrames();
  assert.equal(view.scrolls.length, 2); assert.equal(view.scrolls[1].target, view.targets[1]);
  assert.equal(dom.window.document.activeElement, dialog());
  assert.equal(observers[0].disconnected, true); assert.equal(frames.size, 0);
});

test("scroll, layout and viewport changes update the spotlight in one scheduled frame and stop after unmount", async () => {
  const view = await mount(); await flushFrames();
  view.bounds[0].top = 95;
  view.targets[0].dispatchEvent(new dom.window.Event("scroll"));
  dom.window.dispatchEvent(new dom.window.Event("resize")); viewport.dispatchEvent(new dom.window.Event("resize"));
  assert.equal(frames.size, 1); await flushFrames(); assert.equal(ring().style.top, "93px");
  view.bounds[0].width = 400; observers.at(-1)!.resize();
  await flushFrames(); assert.equal(ring().style.width, "414px"); assert.equal(frames.size, 0);
  dom.window.dispatchEvent(new dom.window.Event("scroll")); assert.equal(frames.size, 1);
  await view.close(); assert.equal(frames.size, 0); assert.equal(observers.at(-1)!.disconnected, true);
  dom.window.dispatchEvent(new dom.window.Event("scroll")); dom.window.dispatchEvent(new dom.window.Event("resize"));
  viewport.dispatchEvent(new dom.window.Event("scroll")); assert.equal(frames.size, 0);
});

test("the modal locks the background and restores existing styles, inert state and focus without scrolling", async () => {
  dom.window.document.body.style.overflow = "clip"; dom.window.document.body.style.paddingRight = "12px";
  dom.window.document.documentElement.style.overflow = "auto";
  const alreadyInert = dom.window.document.createElement("aside"); alreadyInert.setAttribute("inert", "preserved");
  dom.window.document.body.append(alreadyInert);
  const view = await mount();
  assert.equal(dom.window.document.body.style.overflow, "hidden"); assert.equal(dom.window.document.documentElement.style.overflow, "hidden");
  assert.equal(dom.window.document.body.style.paddingRight, "36px"); assert.equal(view.page.hasAttribute("inert"), true);
  assert.equal(dom.window.document.querySelector(".walkthrough-layer")?.hasAttribute("inert"), false);
  await view.close();
  assert.equal(dom.window.document.body.style.overflow, "clip"); assert.equal(dom.window.document.documentElement.style.overflow, "auto");
  assert.equal(dom.window.document.body.style.paddingRight, "12px"); assert.equal(alreadyInert.getAttribute("inert"), "preserved");
  assert.equal(view.page.hasAttribute("inert"), false); assert.deepEqual(focusCalls.at(-1), { element: view.launcher, options: { preventScroll: true } });
  alreadyInert.remove();
});

test("keyboard focus stays within enabled guide controls while navigation callbacks retain their behavior", async () => {
  const view = await mount();
  const buttons = [...dialog().querySelectorAll<HTMLButtonElement>("button")];
  buttons.at(-1)!.focus();
  dom.window.document.dispatchEvent(new dom.window.KeyboardEvent("keydown", { key: "Tab", bubbles: true, cancelable: true }));
  assert.equal(dom.window.document.activeElement, buttons[0]);
  dom.window.document.dispatchEvent(new dom.window.KeyboardEvent("keydown", { key: "Tab", shiftKey: true, bubbles: true, cancelable: true }));
  assert.equal(dom.window.document.activeElement, buttons.at(-1));
  await act(async () => { buttons[0].click(); buttons[1].click(); buttons[2].click(); });
  assert.deepEqual(view.calls, { skip: 1, back: 1, next: 1 });
  view.props.saving = true; await view.render();
  dom.window.document.dispatchEvent(new dom.window.KeyboardEvent("keydown", { key: "Tab", bubbles: true, cancelable: true }));
  assert.equal(dom.window.document.activeElement, dialog());
});
