import assert from "node:assert/strict";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import test from "node:test";
import { JSDOM } from "jsdom";
import { rolldown } from "rolldown";
import type { UploadedImage } from "../src/lib/api.ts";

const dom = new JSDOM("<!doctype html><html><body></body></html>", { url: "http://localhost/" });
for (const key of ["window", "document", "HTMLElement"] as const) {
  Object.defineProperty(globalThis, key, { value: key === "window" ? dom.window : dom.window[key], configurable: true });
}
(globalThis as Record<string, unknown>).IS_REACT_ACT_ENVIRONMENT = true;
const NativeMessageChannel = globalThis.MessageChannel;
const channels: MessageChannel[] = [];
globalThis.MessageChannel = class extends NativeMessageChannel {
  constructor() { super(); channels.push(this); }
};
const auth = { session: { user: { id: "learner-a" } } };
(globalThis as Record<string, unknown>).__uploadAuth = auth;
const events: unknown[][] = [];
(dom.window as unknown as Window).gtag = (...args) => { events.push(args); };
const folder = mkdtempSync(join(tmpdir(), "image-upload-retry-"));
const entry = join(dirname(fileURLToPath(import.meta.url)), `.imageUploadRetry-${crypto.randomUUID()}.ts`);
writeFileSync(entry, [
  'export { createElement as h, act } from "react";',
  'export { createRoot } from "react-dom/client";',
  'export { ImageUpload } from "../src/components/ImageUpload";',
  'export { uploadImage } from "../src/lib/api";',
].join("\n"));
let bundled: unknown;
try {
  const bundler = await rolldown({ input: entry, platform: "node", resolve: { extensions: [".tsx", ".ts", ".js"] },
    plugins: [{
      name: "upload-test-auth",
      resolveId: id => id.endsWith("/state/Auth") ? "\0upload-auth" : id.endsWith("/supabase.ts") ? "\0upload-token" : null,
      load: id => id === "\0upload-auth" ? "export const useAuth = () => globalThis.__uploadAuth;"
        : id === "\0upload-token" ? "export const getAccessToken = async () => globalThis.__uploadAuth.session?.user.id ?? null; export const waitForAccessToken = getAccessToken;" : null,
      transform: code => code.replaceAll("import.meta.env", "({})"),
    }, {
      name: "test-css",
      resolveId: id => id.endsWith(".css") ? "\0empty-css" : null,
      load: id => id === "\0empty-css" ? "export default {};" : null,
    }],
  });
  try {
    const { output } = await bundler.generate({ format: "esm" });
    const path = join(folder, "bundle.mjs");
    writeFileSync(path, output[0].code);
    const previousApiUrl = process.env.VITE_API_BASE_URL;
    process.env.VITE_API_BASE_URL = "http://localhost";
    try { bundled = await import(pathToFileURL(path).href); }
    finally {
      if (previousApiUrl === undefined) delete process.env.VITE_API_BASE_URL;
      else process.env.VITE_API_BASE_URL = previousApiUrl;
    }
  } finally { await bundler.close(); }
} finally { rmSync(entry, { force: true }); rmSync(folder, { recursive: true, force: true }); }
const { h, act, createRoot, ImageUpload, uploadImage } = bundled as {
  h: typeof import("react").createElement; act: typeof import("react").act;
  createRoot: typeof import("react-dom/client").createRoot;
  ImageUpload: typeof import("../src/components/ImageUpload.tsx").ImageUpload;
  uploadImage: typeof import("../src/lib/api.ts").uploadImage;
};
const originalFetch = globalThis.fetch;
const requests: { path: string; body: Record<string, unknown> | null }[] = [];
let confirmFailures = 0;
let confirmStatus = 503;
let nextAsset = 0;
let holdConfirmation: (() => Promise<Response>) | null = null;
globalThis.fetch = async (input, init) => {
  const path = String(input);
  const body = typeof init?.body === "string" ? JSON.parse(init.body) as Record<string, unknown> : null;
  requests.push({ path, body });
  if (path.endsWith("/media/upload-url")) {
    const id = `asset-${++nextAsset}`;
    return Response.json({ assetId: id, storageKey: `users/learner-a/images/${id}.jpg`, uploadUrl: `https://storage.example.test/${id}` });
  }
  if (path.startsWith("https://storage.example.test/")) return new Response(null, { status: 200 });
  if (path.endsWith("/media/confirm-upload")) {
    if (holdConfirmation) return holdConfirmation();
    if (confirmFailures-- > 0) {
      if (confirmStatus === 0) throw new TypeError("Response lost after confirmation committed");
      return Response.json({ detail: { message: "Could not confirm image." } }, { status: confirmStatus });
    }
    return Response.json({ id: body?.assetId, signedUrl: "https://storage.example.test/read", mimeType: "image/jpeg", width: 100, height: 80 });
  }
  throw new Error(`Unexpected request: ${path}`);
};
const cleanups = new Set<() => Promise<void>>();
async function mount() {
  const container = dom.window.document.createElement("div");
  dom.window.document.body.appendChild(container);
  const root = createRoot(container);
  const uploaded: UploadedImage[] = [];
  const render = () => root.render(h(ImageUpload, { onUploaded: image => { uploaded.push(image); } }));
  await act(async () => render());
  cleanups.add(async () => { await act(async () => root.unmount()); container.remove(); });
  return { container, uploaded, render };
}
async function choose(container: Element, file: File) {
  const input = container.querySelector<HTMLInputElement>('input[type="file"]');
  assert.ok(input);
  Object.defineProperty(input, "files", { value: [file], configurable: true });
  await act(async () => { input.dispatchEvent(new dom.window.Event("change", { bubbles: true })); });
}
function retryButton(container: Element) {
  const button = [...container.querySelectorAll("button")].find(candidate => candidate.textContent === "Retry upload");
  assert.ok(button, "Confirmation failure must offer a retry for the existing image");
  return button;
}
test.beforeEach(() => {
  auth.session.user.id = "learner-a";
  confirmFailures = 0; confirmStatus = 503; nextAsset = 0; holdConfirmation = null; requests.length = 0; events.length = 0;
});
test.afterEach(async () => { for (const cleanup of cleanups) await cleanup(); cleanups.clear(); });
test.after(() => {
  globalThis.fetch = originalFetch;
  dom.window.close();
  for (const channel of channels) { channel.port1.close(); channel.port2.close(); }
  globalThis.MessageChannel = NativeMessageChannel;
});

for (const status of [0, 503]) {
  test(`confirmation retry after ${status || "a lost response"} reuses the stored image`, async () => {
    confirmFailures = 2; confirmStatus = status;
    const view = await mount();
    await choose(view.container, new File(["photo"], "photo.jpg", { type: "image/jpeg" }));
    assert.equal(view.uploaded.length, 0);
    await act(async () => retryButton(view.container).click());
    assert.equal(view.uploaded[0]?.id, "asset-1");
    assert.equal(requests.filter(request => request.path.endsWith("/upload-url")).length, 1);
    assert.equal(requests.filter(request => request.path.startsWith("https://storage.example.test/")).length, 1);
    assert.deepEqual(requests.filter(request => request.path.endsWith("/confirm-upload")).map(request => request.body?.assetId), ["asset-1", "asset-1", "asset-1"]);
    assert.equal(view.container.textContent?.includes("Retry upload"), false);
    const event = events.find(event => event[1] === "photo_upload_retried");
    assert.ok(event);
    assert.deepEqual(event.slice(0, 2), ["event", "photo_upload_retried"]);
    assert.equal((event[2] as Record<string, unknown>).source, "userUpload");
  });
}

test("choosing another file starts a fresh attempt instead of confirming the prior image", async () => {
  confirmFailures = 2;
  const view = await mount();
  await choose(view.container, new File(["first"], "same-name.jpg", { type: "image/jpeg" }));
  retryButton(view.container);
  await choose(view.container, new File(["second"], "same-name.jpg", { type: "image/jpeg" }));
  assert.equal(view.uploaded[0]?.id, "asset-2");
  assert.equal(requests.filter(request => request.path.endsWith("/upload-url")).length, 2);
  assert.equal(view.container.textContent?.includes("Retry upload"), false);
});

test("switching accounts clears the pending file and never offers its confirmation retry again", async () => {
  confirmFailures = 2;
  const view = await mount();
  await choose(view.container, new File(["photo"], "photo.jpg", { type: "image/jpeg" }));
  retryButton(view.container);
  const count = requests.length;
  auth.session.user.id = "learner-b";
  await act(async () => view.render());
  assert.equal(view.container.textContent?.includes("Retry upload"), false);
  auth.session.user.id = "learner-a";
  await act(async () => view.render());
  assert.equal(view.container.textContent?.includes("Retry upload"), false);
  assert.equal(requests.length, count);
});

test("a confirmation response from the previous account cannot publish an uploaded image", async () => {
  let finish: ((response: Response) => void) | undefined;
  holdConfirmation = () => new Promise(resolve => { finish = resolve; });
  const view = await mount();
  await choose(view.container, new File(["photo"], "photo.jpg", { type: "image/jpeg" }));
  assert.ok(finish);
  auth.session.user.id = "learner-b";
  await act(async () => view.render());
  await act(async () => { finish?.(Response.json({ id: "asset-1", signedUrl: "https://storage.example.test/read", mimeType: "image/jpeg", width: 100, height: 80 })); });
  assert.deepEqual(view.uploaded, []);
  assert.equal(view.container.textContent?.includes("Retry upload"), false);
});

for (const status of [0, 503]) {
  test(`an in-flight confirmation failure ${status || "from the network"} cannot retry under another account`, async () => {
    let finish: ((response: Response) => void) | undefined;
    let fail: ((error: Error) => void) | undefined;
    holdConfirmation = () => new Promise((resolve, reject) => { finish = resolve; fail = reject; });
    const view = await mount();
    await choose(view.container, new File(["photo"], "photo.jpg", { type: "image/jpeg" }));
    assert.ok(finish && fail);
    auth.session.user.id = "learner-b";
    await act(async () => view.render());
    await act(async () => {
      if (status) finish?.(Response.json({ detail: { message: "Could not confirm image." } }, { status }));
      else fail?.(new TypeError("Connection lost"));
    });
    assert.equal(requests.filter(request => request.path.endsWith("/confirm-upload")).length, 1);
    assert.deepEqual(view.uploaded, []);
    assert.equal(view.container.textContent?.includes("Retry upload"), false);
  });
}

test("rate limiting retains the uploaded image for manual retry without repeating the request immediately", async () => {
  confirmFailures = 1; confirmStatus = 429;
  const view = await mount();
  await choose(view.container, new File(["photo"], "photo.jpg", { type: "image/jpeg" }));
  assert.equal(requests.filter(request => request.path.endsWith("/confirm-upload")).length, 1);
  await act(async () => retryButton(view.container).click());
  assert.equal(view.uploaded[0]?.id, "asset-1");
  assert.equal(requests.filter(request => request.path.endsWith("/upload-url")).length, 1);
});

for (const status of [400, 401, 403, 404, 422]) {
  test(`a terminal confirmation error ${status} clears its attempt without automatic retry`, async () => {
    confirmFailures = 2; confirmStatus = status;
    const file = new File(["photo"], "photo.jpg", { type: "image/jpeg" });
    const attempt = { file, source: "userUpload" as const, uploaded: undefined };
    await assert.rejects(uploadImage(file, "userUpload", () => {}, attempt));
    assert.equal(requests.filter(request => request.path.endsWith("/confirm-upload")).length, 1);
    assert.equal(attempt.uploaded, undefined);
  });
}

test("a retry context cannot be reused for a different file or source", async () => {
  const file = new File(["photo"], "photo.jpg", { type: "image/jpeg" });
  const attempt = { file, source: "userUpload" as const };
  await assert.rejects(uploadImage(new File(["other"], "photo.jpg", { type: "image/jpeg" }), "userUpload", () => {}, attempt));
  await assert.rejects(uploadImage(file, "camera", () => {}, attempt));
  assert.deepEqual(requests, []);
});

function mockCamera(getUserMedia: (constraints: unknown) => Promise<unknown>) {
  Object.defineProperty(globalThis, "navigator", { value: dom.window.navigator, configurable: true });
  Object.defineProperty(dom.window.navigator, "mediaDevices", { value: { getUserMedia }, configurable: true });
  dom.window.HTMLDialogElement.prototype.showModal = function () { this.setAttribute("open", ""); };
  dom.window.HTMLMediaElement.prototype.play = async () => {};
}

function button(container: Element, text: string) {
  const found = [...container.querySelectorAll("button")].find(item => item.textContent?.trim() === text);
  assert.ok(found, `Missing button: ${text}`);
  return found;
}

test("camera capture uploads a JPEG with camera provenance and stops the webcam", async () => {
  let stopped = 0;
  mockCamera(async constraints => {
    assert.deepEqual(constraints, { audio: false, video: { facingMode: { ideal: "environment" } } });
    return { getTracks: () => [{ stop: () => { stopped++; } }] };
  });
  const view = await mount();
  await act(async () => button(view.container, "Open camera").click());
  const preview = view.container.querySelector("video");
  assert.ok(preview);
  assert.equal(button(view.container, "Take photo").disabled, true);
  Object.defineProperties(preview, { videoWidth: { value: 2560 }, videoHeight: { value: 1440 } });
  await act(async () => preview.dispatchEvent(new dom.window.Event("loadeddata")));
  const originalContext = dom.window.HTMLCanvasElement.prototype.getContext;
  const originalBlob = dom.window.HTMLCanvasElement.prototype.toBlob;
  dom.window.HTMLCanvasElement.prototype.getContext = (() => ({ drawImage: () => {} })) as typeof originalContext;
  dom.window.HTMLCanvasElement.prototype.toBlob = function (callback, type) {
    assert.equal(this.width, 1920);
    assert.equal(this.height, 1080);
    assert.equal(type, "image/jpeg");
    callback(new Blob(["photo"], { type }));
  };
  try {
    await act(async () => button(view.container, "Take photo").click());
    assert.equal(stopped, 1);
    assert.equal(view.container.querySelector("dialog"), null);
    assert.equal(view.uploaded.length, 1);
    assert.equal(requests.find(request => request.path.endsWith("/upload-url"))?.body?.source, "camera");
    assert.ok(events.some(event => event[1] === "photo_camera_captured"));
  } finally {
    dom.window.HTMLCanvasElement.prototype.getContext = originalContext;
    dom.window.HTMLCanvasElement.prototype.toBlob = originalBlob;
  }
});

test("closing a pending permission request stops a camera granted afterwards without uploading", async () => {
  let grant!: (stream: unknown) => void;
  let stopped = 0;
  mockCamera(() => new Promise(resolve => { grant = resolve; }));
  const view = await mount();
  await act(async () => button(view.container, "Open camera").click());
  await act(async () => button(view.container, "Cancel").click());
  await act(async () => grant({ getTracks: () => [{ stop: () => { stopped++; } }] }));
  assert.equal(stopped, 1);
  assert.equal(view.container.querySelector("dialog"), null);
  assert.deepEqual(requests, []);
});

for (const action of ["escape", "account change"]) {
  test(`${action} stops a live camera without uploading`, async () => {
    let stopped = 0;
    mockCamera(async () => ({ getTracks: () => [{ stop: () => { stopped++; } }] }));
    const view = await mount();
    await act(async () => button(view.container, "Open camera").click());
    await act(async () => {
      if (action === "escape") view.container.querySelector("dialog")?.dispatchEvent(new dom.window.Event("cancel", { cancelable: true }));
      else { auth.session.user.id = "learner-b"; view.render(); }
    });
    assert.equal(stopped, 1);
    assert.equal(view.container.querySelector("dialog"), null);
    assert.deepEqual(requests, []);
  });
}

test("camera permission failure explains recovery and preserves file upload", async () => {
  mockCamera(async () => { throw new DOMException("Denied", "NotAllowedError"); });
  const view = await mount();
  await act(async () => button(view.container, "Open camera").click());
  assert.match(view.container.querySelector('[role="alert"]')?.textContent ?? "", /site permissions/);
  await act(async () => button(view.container, "Cancel").click());
  await choose(view.container, new File(["photo"], "photo.jpg", { type: "image/jpeg" }));
  assert.equal(view.uploaded.length, 1);
});

test("browsers without the camera API offer an actionable error", async () => {
  mockCamera(async () => { throw new Error("Must not be called"); });
  Object.defineProperty(dom.window.navigator, "mediaDevices", { value: undefined, configurable: true });
  const view = await mount();
  await act(async () => button(view.container, "Open camera").click());
  assert.match(view.container.querySelector('[role="alert"]')?.textContent ?? "", /HTTPS or localhost/);
  assert.equal(button(view.container, "Take photo").disabled, true);
  await act(async () => button(view.container, "Cancel").click());
  assert.equal(button(view.container, "Upload").disabled, false);
});
