import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import test from "node:test";
import { submitIndexNow } from "../scripts/indexnow.mjs";

const origin = "https://www.learnwithlinguini.com";
const key = "Linguini-test-key-123";
const endpoint = "https://api.indexnow.org/indexnow";
const sitemap = (urls: string[]) => `<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">${
  urls.map(url => `<url><loc>${url}</loc></url>`).join("")
}</urlset>`;
const home = `<html><head><link rel="canonical" href="${origin}/"></head><body>Linguini</body></html>`;

type FixtureOptions = {
  keyBody?: string;
  keyType?: string;
  keyStatus?: number;
  keyRobots?: string;
  homeBody?: string;
  homeType?: string;
  homeStatus?: number;
  homeRobots?: string;
  sitemapBody?: string;
  sitemapType?: string;
  sitemapStatus?: number;
  sitemapRobots?: string;
  submissionStatus?: number;
};

function fixture(options: FixtureOptions = {}) {
  const requests: { url: string; options: RequestInit }[] = [];
  const submissions: Record<string, unknown>[] = [];
  const fetchImpl = async (url: string, requestOptions: RequestInit = {}) => {
    requests.push({ url, options: requestOptions });
    assert.equal(requestOptions.redirect, "error");
    assert.ok(requestOptions.signal instanceof AbortSignal);
    if (url === endpoint) {
      assert.equal(requestOptions.method, "POST");
      assert.equal(new Headers(requestOptions.headers).get("content-type"), "application/json; charset=utf-8");
      submissions.push(JSON.parse(String(requestOptions.body)));
      return new Response(null, { status: options.submissionStatus ?? 200 });
    }
    if (url === `${origin}/indexnow-key.txt`) return new Response(options.keyBody ?? `${key}\n`, {
      status: options.keyStatus ?? 200,
      headers: { "content-type": options.keyType ?? "text/plain; charset=utf-8", "x-robots-tag": options.keyRobots ?? "" },
    });
    if (url === `${origin}/`) return new Response(options.homeBody ?? home, {
      status: options.homeStatus ?? 200,
      headers: { "content-type": options.homeType ?? "text/html", "x-robots-tag": options.homeRobots ?? "" },
    });
    assert.equal(url, `${origin}/sitemap.xml`);
    return new Response(options.sitemapBody ?? sitemap([`${origin}/`, `${origin}/blog`]), {
      status: options.sitemapStatus ?? 200,
      headers: { "content-type": options.sitemapType ?? "application/xml; charset=utf-8", "x-robots-tag": options.sitemapRobots ?? "" },
    });
  };
  return { requests, submissions, fetchImpl };
}

test("valid deployments submit only unique canonical URLs and accept received/pending statuses", async () => {
  for (const status of [200, 202]) {
    const site = fixture({ submissionStatus: status, sitemapBody: sitemap([
      `${origin}/`, `${origin}/blog`, `${origin}/blog`, `${origin}/learn/korean`,
    ]) });
    const result = await submitIndexNow({ siteUrl: `${origin}/`, key, fetchImpl: site.fetchImpl });
    assert.deepEqual(result, { status, submitted: 3 });
    assert.deepEqual(site.submissions, [{
      host: "www.learnwithlinguini.com", key, keyLocation: `${origin}/indexnow-key.txt`,
      urlList: [`${origin}/`, `${origin}/blog`, `${origin}/learn/korean`],
    }]);
    assert.deepEqual(site.requests.map(request => request.url), [
      `${origin}/indexnow-key.txt`, `${origin}/`, `${origin}/sitemap.xml`, endpoint,
    ]);
  }
});

test("discovery files may be noindex while the canonical home page is indexable", async () => {
  const site = fixture({ keyRobots: "noindex", sitemapRobots: "noindex, follow" });
  const result = await submitIndexNow({ siteUrl: origin, key, fetchImpl: site.fetchImpl });
  assert.equal(result.submitted, 2);
  assert.equal(site.submissions.length, 1);
});

test("invalid origins, keys and previews perform no network request", async () => {
  for (const siteUrl of [
    "", "/", "ftp://www.learnwithlinguini.com", `${origin}/blog`, `${origin}?source=launch`, `${origin}#fragment`,
    "https://name:password@www.learnwithlinguini.com", "https://www.learnwithlinguini.com:8443", `${origin}/./`,
    "https://WWW.learnwithlinguini.com", ` ${origin}`, "https://linguini-pr-1.vercel.app", "https://dev.learnwithlinguini.com",
    "https://preview.example.com", "https://staging.example.com", "http://localhost", "http://127.0.0.1", "http://[::1]",
  ]) {
    const site = fixture();
    await assert.rejects(submitIndexNow({ siteUrl, key, fetchImpl: site.fetchImpl }), undefined, siteUrl);
    assert.equal(site.requests.length, 0, siteUrl);
  }
  for (const invalidKey of [undefined, "", "short", "x".repeat(129), "invalid_key", "valid-key ", "a/bcdefg"]) {
    const site = fixture();
    await assert.rejects(submitIndexNow({ siteUrl: origin, key: invalidKey, fetchImpl: site.fetchImpl }), /INDEXNOW_KEY/);
    assert.equal(site.requests.length, 0);
  }
});

test("key failures, HTML fallback and noncanonical or noindex home pages cannot submit", async () => {
  const cases: FixtureOptions[] = [
    { keyStatus: 404 }, { keyBody: "wrong-key" }, { keyBody: key, keyType: "text/html" },
    { keyBody: "x".repeat(513) }, { homeStatus: 503 }, { homeType: "application/json" },
    { homeBody: "<html><head></head></html>" },
    { homeBody: home.replace(`${origin}/`, "https://learnwithlinguini.com/") },
    { homeBody: home.replace("</head>", `<link rel="canonical" href="${origin}/"></head>`) },
    { homeRobots: "noindex, nofollow" }, { homeRobots: "bingbot: none" },
    { homeBody: home.replace("</head>", '<meta name="ROBOTS" content="noindex,follow"></head>') },
    { homeBody: home.replace("</head>", '<meta name="bingbot" content="none"></head>') },
  ];
  for (const options of cases) {
    const site = fixture(options);
    await assert.rejects(submitIndexNow({ siteUrl: origin, key, fetchImpl: site.fetchImpl }));
    assert.equal(site.submissions.length, 0, JSON.stringify(options));
  }
});

test("invalid, non-XML, mixed-origin and oversized sitemaps cannot submit", async () => {
  const cases: FixtureOptions[] = [
    { sitemapStatus: 500 }, { sitemapType: "text/html" }, { sitemapBody: "<html>SPA fallback</html>" },
    { sitemapBody: '<urlset xmlns="wrong"><url><loc>https://example.com/</loc></url></urlset>' },
    { sitemapBody: '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url></urlset>' },
    { sitemapBody: sitemap([]) }, { sitemapBody: sitemap([`${origin}/`, "https://learnwithlinguini.com/"]) },
    { sitemapBody: sitemap([`${origin}/blog?code=private`]) }, { sitemapBody: sitemap([`${origin}/blog#private`]) },
    { sitemapBody: sitemap(["https://name:password@www.learnwithlinguini.com/blog"]) },
    { sitemapBody: sitemap(["/blog"]) }, { sitemapBody: sitemap([`${origin}/blog/../`]) },
    { sitemapBody: sitemap([`${origin}/`]).replace("<loc>", "<loc><nested/>") },
    { sitemapBody: sitemap([`${origin}/`]).replace("</loc>", `</loc><loc>${origin}/blog</loc>`) },
    { sitemapBody: `<!DOCTYPE urlset [<!ENTITY expanded "${origin}/">]>${sitemap(["&expanded;"])}` },
    { sitemapBody: sitemap([`${origin}/`]).replace("<url>", "<url xmlns='wrong'>") },
    { sitemapBody: sitemap(Array.from({ length: 10_001 }, (_, i) => `${origin}/${i}`)) },
    { sitemapBody: "x".repeat(5 * 1024 * 1024 + 1) },
  ];
  for (const options of cases) {
    const site = fixture(options);
    await assert.rejects(submitIndexNow({ siteUrl: origin, key, fetchImpl: site.fetchImpl }));
    assert.equal(site.submissions.length, 0);
  }
});

test("network failures and request timeouts never reach the submission endpoint", async () => {
  const site = fixture();
  const failingFetch = async (url: string, options: RequestInit) => {
    if (url.endsWith("sitemap.xml")) throw new TypeError("fetch failed");
    return site.fetchImpl(url, options);
  };
  await assert.rejects(submitIndexNow({ siteUrl: origin, key, fetchImpl: failingFetch }), /Could not fetch.*sitemap.xml/);
  assert.equal(site.submissions.length, 0);

  let calls = 0;
  const pendingFetch = (_url: string, options: RequestInit) => new Promise((_resolve, reject) => {
    calls++;
    const timer = setTimeout(() => reject(new Error("The abort signal was not used")), 100);
    options.signal?.addEventListener("abort", () => { clearTimeout(timer); reject(options.signal?.reason); }, { once: true });
  });
  await assert.rejects(submitIndexNow({ siteUrl: origin, key, fetchImpl: pendingFetch, timeoutMs: 5 }), /timed out after 5ms/);
  assert.equal(calls, 1);
});

test("redirects and rejected IndexNow statuses produce bounded errors", async () => {
  const redirectedFetch = async () => {
    const response = new Response(key, { headers: { "content-type": "text/plain" } });
    Object.defineProperty(response, "url", { value: "https://preview.example.com/indexnow-key.txt" });
    return response;
  };
  await assert.rejects(submitIndexNow({ siteUrl: origin, key, fetchImpl: redirectedFetch }), /redirects are not accepted/);
  for (const status of [201, 204, 403, 422, 429, 500]) {
    const site = fixture({ submissionStatus: status });
    await assert.rejects(submitIndexNow({ siteUrl: origin, key, fetchImpl: site.fetchImpl }), new RegExp(`HTTP ${status}`));
    assert.equal(site.submissions.length, 1);
  }
  const enormousFailure = async () => { throw new Error("network".repeat(1000)); };
  await assert.rejects(submitIndexNow({ siteUrl: origin, key, fetchImpl: enormousFailure }), error =>
    error instanceof Error && error.message.length <= 400);
});

test("rejected deployment responses cancel their bodies before returning without a submission", async () => {
  for (const failure of ["status", "redirect"]) {
    let cancelled = false;
    let submissions = 0;
    const fetchImpl = async (_url: string, options: RequestInit) => {
      if (options.method === "POST") submissions++;
      const body = new ReadableStream({ cancel() { cancelled = true; } });
      const response = new Response(body, { status: failure === "status" ? 503 : 200 });
      if (failure === "redirect") Object.defineProperty(response, "url", { value: "https://preview.example.com/indexnow-key.txt" });
      return response;
    };
    await assert.rejects(submitIndexNow({ siteUrl: origin, key, fetchImpl }));
    assert.equal(cancelled, true, failure);
    assert.equal(submissions, 0, failure);
  }
});

test("CLI requires an explicit origin instead of using a preview environment value", () => {
  const script = fileURLToPath(new URL("../scripts/indexnow.mjs", import.meta.url));
  const result = spawnSync(process.execPath, [script], {
    encoding: "utf8", env: { ...process.env, VITE_SITE_URL: "https://preview.example.com", INDEXNOW_KEY: key },
  });
  assert.equal(result.status, 1);
  assert.match(result.stderr, /Usage:/);
  assert.equal(result.stdout, "");
});
