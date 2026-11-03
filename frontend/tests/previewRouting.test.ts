import assert from "node:assert/strict";
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";
import test from "node:test";
import { rolldown } from "rolldown";

test("preview serves canonical pages, preserves learner refreshes and returns real public 404s", async () => {
  const folder = mkdtempSync(join(tmpdir(), "preview-routing-"));
  const output = join(folder, "dist");
  mkdirSync(join(output, "learn"), { recursive: true });
  for (const [file, content] of Object.entries({ "index.html": "Home", "learn/spanish.html": "Spanish", "app.html": "Learner shell", "share.html": "Share shell", "404.html": "Page not found", "robots.txt": "User-agent: *" })) {
    writeFileSync(join(output, file), content);
  }
  const bundler = await rolldown({ input: "vite/previewRoutes.ts", platform: "node", resolve: { extensions: [".ts", ".js"] } });
  try {
    const { output: chunks } = await bundler.generate({ format: "esm" });
    const path = join(folder, "preview.mjs");
    writeFileSync(path, chunks[0].code);
    const { previewRoutes } = await import(pathToFileURL(path).href);
    let handler: (request: unknown, response: unknown, next: (error?: unknown) => void) => Promise<void>;
    previewRoutes().configurePreviewServer({ config: { root: folder, build: { outDir: "dist" } }, middlewares: { use(value: typeof handler) { handler = value; } } });
    async function request(url: string, method = "GET") {
      const result = { status: 0, headers: {} as Record<string, string>, body: "", next: false };
      const response = {
        set statusCode(value: number) { result.status = value; },
        setHeader(key: string, value: string) { result.headers[key.toLowerCase()] = value; },
        writeHead(status: number, headers: Record<string, string>) { result.status = status; Object.entries(headers).forEach(([key, value]) => response.setHeader(key, value)); },
        end(body?: Buffer) { result.body = body?.toString() ?? ""; },
      };
      await handler!({ url, method }, response, error => { if (error) throw error; result.next = true; });
      return result;
    }
    assert.equal((await request("/")).body, "Home");
    assert.equal((await request("/learn/spanish?utm_source=google")).body, "Spanish");
    for (const path of ["/home", "/login?mode=signup", "/ispy/friends/abc", "/ispy/legacy-rooms", "/ispy/games/abc/describe", "/practice/sessions/abc/learn/q1", "/practice/old-scene/learn", "/journal/new/2026-11-03", "/rooms/abc", "/profile/edit"]) {
      const response = await request(path);
      assert.equal(response.status, 200, path);
      assert.equal(response.body, "Learner shell", path);
      assert.equal(response.headers["x-robots-tag"], "noindex, follow", path);
    }
    for (const path of ["/missing", "/blog/missing-post", "/learn/elvish", "/assets/missing.js", "/missing.xml"]) {
      const response = await request(path);
      assert.equal(response.status, 404, path);
      assert.equal(response.body, "Page not found", path);
    }
    const moved = await request("/blog/inside-a-linguini-lesson?utm_source=link");
    assert.equal(moved.status, 308);
    assert.equal(moved.headers.location, "/blog/why-we-teach-with-your-photos?utm_source=link");
    assert.equal((await request("/learn/spanish/")).headers.location, "/learn/spanish");
    assert.equal((await request("/index.html")).headers.location, "/");
    assert.equal((await request("/learn/spanish.html")).headers.location, "/learn/spanish");
    assert.equal((await request("/share?title=Coffee")).body, "Share shell");
    assert.equal((await request("/robots.txt")).next, true, "existing static resources pass to Vite");
    assert.equal((await request("/learn/spanish", "HEAD")).body, "");
  } finally {
    await bundler.close();
    rmSync(folder, { recursive: true, force: true });
  }
});
