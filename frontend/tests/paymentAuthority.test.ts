import assert from "node:assert/strict";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import test from "node:test";
import { JSDOM } from "jsdom";
import { rolldown } from "rolldown";
import type { AppState } from "../src/state/context.ts";

const dom = new JSDOM("<!doctype html><html><body></body></html>", { url: "http://localhost/payment" });
for (const key of ["window", "document", "HTMLElement"] as const) {
  Object.defineProperty(globalThis, key, { value: key === "window" ? dom.window : dom.window[key], configurable: true });
}
(globalThis as Record<string, unknown>).IS_REACT_ACT_ENVIRONMENT = true;
const NativeMessageChannel = globalThis.MessageChannel;
const channels: MessageChannel[] = [];
globalThis.MessageChannel = class extends NativeMessageChannel {
  constructor() { super(); channels.push(this); }
};
const requests: Array<{ path: string; method: string; body: unknown }> = [];
const events: unknown[][] = [];
(dom.window as unknown as Window).gtag = (...args) => { events.push(args); };
let tier: "free" | "plus" = "free";
const originalFetch = globalThis.fetch;
globalThis.fetch = async (input, init) => {
  const path = new URL(String(input)).pathname;
  requests.push({ path, method: init?.method ?? "GET", body: init?.body ? JSON.parse(String(init.body)) : null });
  if (path === "/api/v1/payments/subscription-status") {
    return Response.json({ tier, dailyLessonLimit: tier === "plus" ? 10 : 1, hasActiveSubscription: tier === "plus", canUpgrade: tier !== "plus" });
  }
  if (path === "/api/v1/payments/create-checkout-session") return Response.json({ checkoutUrl: "http://localhost/payment#checkout" });
  if (path === "/api/v1/payments/create-portal-session") return Response.json({ portalUrl: "http://localhost/payment#portal" });
  throw new Error(`Unexpected billing request: ${path}`);
};
const folder = mkdtempSync(join(tmpdir(), "payment-authority-"));
const entry = join(dirname(fileURLToPath(import.meta.url)), `.paymentAuthority-${crypto.randomUUID()}.ts`);
writeFileSync(entry, [
  'export { createElement as h, act } from "react";',
  'export { createRoot } from "react-dom/client";',
  'export { MemoryRouter } from "react-router-dom";',
  'export { QueryClient, QueryClientProvider } from "@tanstack/react-query";',
  'export { AppStateContext } from "../src/state/context";',
  'export { Payment } from "../src/pages/Payment";',
].join("\n"));
let bundled: unknown;
try {
  const bundler = await rolldown({
    input: entry, platform: "node", resolve: { extensions: [".tsx", ".ts", ".js"] },
    plugins: [{ name: "test-api-url", transform: code => code.replaceAll("import.meta.env?.VITE_API_BASE_URL", '"http://test.local"') }, {
      name: "test-css", resolveId: id => id.endsWith(".css") ? "\0empty-css" : null,
      load: id => id === "\0empty-css" ? "export default {};" : null,
    }],
  });
  try {
    const { output } = await bundler.generate({ format: "esm" });
    const path = join(folder, "bundle.mjs");
    writeFileSync(path, `import.meta.env = {};\n${output[0].code}`);
    bundled = await import(pathToFileURL(path).href);
  } finally { await bundler.close(); }
} finally { rmSync(entry, { force: true }); rmSync(folder, { recursive: true, force: true }); }
const { h, act, createRoot, MemoryRouter, QueryClient, QueryClientProvider, AppStateContext, Payment } = bundled as {
  h: typeof import("react").createElement; act: typeof import("react").act;
  createRoot: typeof import("react-dom/client").createRoot;
  MemoryRouter: typeof import("react-router-dom").MemoryRouter;
  QueryClient: typeof import("@tanstack/react-query").QueryClient;
  QueryClientProvider: typeof import("@tanstack/react-query").QueryClientProvider;
  AppStateContext: typeof import("../src/state/context.ts").AppStateContext;
  Payment: typeof import("../src/pages/Payment.tsx").Payment;
};
test.after(() => {
  dom.window.close();
  for (const channel of channels) { channel.port1.close(); channel.port2.close(); }
  globalThis.MessageChannel = NativeMessageChannel;
  globalThis.fetch = originalFetch;
});

for (const plan of ["free", "plus"] as const) {
  test(`${plan} learners use Stripe billing without a direct tier switch`, async () => {
    tier = plan;
    requests.length = 0;
    events.length = 0;
    dom.reconfigure({ url: "http://localhost/payment" });
    const container = dom.window.document.createElement("div");
    dom.window.document.body.appendChild(container);
    const root = createRoot(container);
    const client = new QueryClient();
    try {
      await act(async () => root.render(h(QueryClientProvider, { client },
        h(AppStateContext.Provider, { value: { user: { tier: plan } } as AppState },
          h(MemoryRouter, null, h(Payment))))));
      assert.doesNotMatch(container.textContent ?? "", /Development & Testing Toolbox|Switch Test Tier|Stripe Test Mode Card/);
      const label = plan === "plus" ? "Manage Subscription & Invoices" : "Upgrade to Plus";
      const button = [...container.querySelectorAll("button")].find(element => element.textContent?.trim() === label);
      assert.ok(button, `Expected ${label}`);
      assert.equal(button.disabled, false);
      await act(async () => button.click());
      assert.deepEqual(requests, [
        { path: "/api/v1/payments/subscription-status", method: "GET", body: null },
        { path: `/api/v1/payments/${plan === "plus" ? "create-portal-session" : "create-checkout-session"}`, method: "POST", body: { returnUrl: "http://localhost/payment" } },
      ]);
      assert.equal(dom.window.location.hash, plan === "plus" ? "#portal" : "#checkout");
      assert.ok(events.some(event => event[1] === (plan === "plus" ? "payment_portal_opened" : "payment_checkout_started")));
    } finally {
      await act(async () => root.unmount());
      client.clear();
      container.remove();
    }
  });
}
