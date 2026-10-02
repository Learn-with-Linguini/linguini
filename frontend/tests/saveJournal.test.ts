import assert from "node:assert/strict";
import test from "node:test";

process.env.VITE_API_BASE_URL = "http://api.test";
const { saveJournal } = await import("../src/lib/api.ts");

function journalDetail(photos: { mediaAssetId: string; displayOrder: number }[]) {
  return {
    journal: { id: "j1", languageProfileId: "p1", localDate: "2026-01-01", title: "T", selectedWords: [], currentRevisionId: "r1" },
    media: photos.map(photo => ({ ...photo, id: `m-${photo.mediaAssetId}`, width: 1, height: 1, mimeType: "image/jpeg" })),
    imageUrl: null,
    revisions: [{ id: "r1", content: "body" }],
  };
}

function stubFetch() {
  const calls: { path: string; method: string }[] = [];
  globalThis.fetch = (async (input: unknown, init?: RequestInit) => {
    const path = String(input).replace("http://api.test", "");
    calls.push({ path, method: init?.method ?? "GET" });
    if (path === "/api/v1/journals/j1" && init?.method === "PATCH") return Response.json({ id: "j1" });
    if (path === "/api/v1/journals/j1") return Response.json(journalDetail([{ mediaAssetId: "a", displayOrder: 0 }, { mediaAssetId: "b", displayOrder: 1 }]));
    return Response.json({});
  }) as typeof fetch;
  return calls;
}

test("unchanged photo attachments skip the trailing journal re-fetch", async () => {
  const calls = stubFetch();
  await saveJournal({ title: "T", mediaAssetId: null, body: "body", wordsUsed: [], photoAssetIds: ["a", "b"] }, "p1", "j1");
  assert.deepEqual(calls.map(call => `${call.method} ${call.path}`), [
    "PATCH /api/v1/journals/j1",
    "GET /api/v1/journals/j1",
  ]);
});

test("changed photo attachments still re-fetch the journal", async () => {
  const calls = stubFetch();
  await saveJournal({ title: "T", mediaAssetId: null, body: "body", wordsUsed: [], photoAssetIds: ["b", "a"] }, "p1", "j1");
  assert.deepEqual(calls.map(call => `${call.method} ${call.path}`), [
    "PATCH /api/v1/journals/j1",
    "GET /api/v1/journals/j1",
    "DELETE /api/v1/journals/j1/media/a",
    "DELETE /api/v1/journals/j1/media/b",
    "POST /api/v1/journals/j1/media",
    "POST /api/v1/journals/j1/media",
    "GET /api/v1/journals/j1",
  ]);
});

test("a draft without photoAssetIds keeps the single trailing re-fetch", async () => {
  const calls = stubFetch();
  await saveJournal({ title: "T", mediaAssetId: "a", body: "body", wordsUsed: [] }, "p1", "j1");
  assert.deepEqual(calls.map(call => `${call.method} ${call.path}`), [
    "PATCH /api/v1/journals/j1",
    "GET /api/v1/journals/j1",
  ]);
});
