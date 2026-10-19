import assert from "node:assert/strict";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import test from "node:test";
import { rolldown } from "rolldown";
import type { PracticeDetail, SessionPersonalization } from "../src/lib/api.ts";

const here = dirname(fileURLToPath(import.meta.url));
const folder = mkdtempSync(join(tmpdir(), "linguini-personalization-test-"));
const entry = join(here, `.personalization-entry-${crypto.randomUUID()}.ts`);
writeFileSync(entry, [
  'export { createElement as h } from "react";',
  'export { renderToStaticMarkup } from "react-dom/server";',
  'export { SessionPersonalization } from "../src/components/SessionPersonalization";',
].join("\n"));
let view: {
  h: typeof import("react").createElement;
  renderToStaticMarkup: typeof import("react-dom/server").renderToStaticMarkup;
  SessionPersonalization: typeof import("../src/components/SessionPersonalization.tsx").SessionPersonalization;
};
try {
  const bundler = await rolldown({ input: entry, platform: "node", resolve: { extensions: [".tsx", ".ts", ".js"] },
    plugins: [{ name: "test-css", resolveId: id => id.endsWith(".css") ? "\0empty-css" : null,
      load: id => id === "\0empty-css" ? "export default {};" : null }],
  });
  const { output } = await bundler.generate({ format: "cjs" });
  await bundler.close();
  const target = join(folder, "bundle.cjs");
  writeFileSync(target, output[0].code);
  view = await import(pathToFileURL(target).href);
} finally { rmSync(entry, { force: true }); rmSync(folder, { recursive: true, force: true }); }

const render = (personalization?: SessionPersonalization | null) => view.renderToStaticMarkup(view.h(view.SessionPersonalization, { personalization }));
const context: SessionPersonalization = { previousSessions: 2,
  returningWords: [{ word: "taza", needsReview: true }, { word: "ventana", needsReview: false }],
  practiceFocuses: ["genderNumberAgreement", "pluralNounForm"] };

test("older sessions and empty history have no personalization panel", () => {
  assert.equal(render(), "");
  assert.equal(render(null), "");
  assert.equal(render({ previousSessions: 0, returningWords: [], practiceFocuses: [] }), "");
  assert.equal(render({ previousSessions: 3, returningWords: [], practiceFocuses: [] }), "");
});

test("earlier words distinguish review from exposure without claiming mastery", () => {
  const html = render(context);
  assert.match(html, /Based on 2 completed sessions/);
  assert.match(html, /<strong>taza<\/strong>.*Review again/);
  assert.match(html, /<strong>ventana<\/strong>.*Saved before/);
  assert.match(html, /matching word endings, talking about more than one/);
  assert.doesNotMatch(html, /mastered|you remembered|independent|genderNumberAgreement|pluralNounForm/i);
});

test("observed description practice appears without inventing returning words", () => {
  const html = render({ previousSessions: 1, returningWords: [], practiceFocuses: ["sceneDescription", "chainedDescription"] });
  assert.match(html, /Based on 1 completed session\./);
  assert.match(html, /describing what you see, joining short descriptions/);
  assert.doesNotMatch(html, /Words from earlier photos/);
});

test("practice from incomplete sessions stays visible without inventing completed sessions", () => {
  const html = render({ previousSessions: 0, returningWords: [{ word: "taza", needsReview: true }], practiceFocuses: ["sceneDescription"] });
  assert.match(html, /Drawn from your earlier practice\./);
  assert.match(html, /<strong>taza<\/strong>.*Review again/);
  assert.match(html, /describing what you see/);
  assert.doesNotMatch(html, /completed session/);
});

test("the practice API preserves provided personalization and supports older responses", async () => {
  process.env.VITE_API_BASE_URL = "http://api.test";
  const { getPractice } = await import("../src/lib/api.ts");
  const base = { session: { id: "session-1", status: "ready", sceneMediaAssetId: "asset", sessionTitle: null, sessionSummary: null, failureCode: null },
    mediaAsset: { id: "asset", source: "userUpload" }, sceneId: null, title: "A café", analysisMode: null, analysisRetryable: false,
    sceneObjects: [], sceneObjectRelations: [], vocabulary: [], translations: [], translationPreview: null, tasks: [], nextTaskId: null,
    progress: { completedTaskCount: 0, skippedTaskCount: 0, terminalTaskCount: 0, totalTaskCount: 0 } } satisfies PracticeDetail;
  let response: PracticeDetail = { ...base, personalization: context };
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async input => {
    assert.equal(String(input), "http://api.test/api/v1/sessions/session-1");
    return Response.json(response);
  };
  try {
    assert.deepEqual((await getPractice("session-1")).personalization, context);
    response = base;
    assert.equal((await getPractice("session-1")).personalization, undefined);
  } finally { globalThis.fetch = originalFetch; }
});
