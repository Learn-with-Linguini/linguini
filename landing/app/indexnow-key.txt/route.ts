export const dynamic = "force-static";

/**
 * IndexNow ownership key (https://www.indexnow.org). Bing, Yandex, Naver and Seznam re-crawl URLs
 * submitted with it; `scripts/indexnow.mjs` passes this path as `keyLocation`.
 */
export function GET() {
  const key = process.env.INDEXNOW_KEY;
  if (!key) return new Response("Not found", { status: 404 });
  return new Response(key, { headers: { "Content-Type": "text/plain; charset=utf-8" } });
}
