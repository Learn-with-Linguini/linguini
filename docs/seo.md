# Search visibility

Linguini's public site and learner application share a Vite deployment. Search
engines should index the public explanations and vocabulary pages; account,
lesson, invitation and journal URLs use `noindex`. Authentication and private
media access remain enforced by the API. Indexing directives are not access controls.

## Routes and rendering

`frontend/src/marketing/routes.ts` lists the canonical public pages and supported
learner refresh patterns. The four language pages, blog index, four articles,
home, credits and legal pages produce **13 HTML documents** at build time.
The same React pages hydrate in the browser, including their interactive controls.
No crawler-specific version or backend request is needed to produce this HTML.

`PageMeta` renders title, description, canonical and sharing tags into the initial
HTML and maintains them during navigation. `siteContent.ts` supplies shared product
copy; `siteUrl.ts` validates the canonical origin. English is the interface and
article language. Spanish, French, German and beginner Korean are taught languages,
not translated versions of the website, so these pages do not use `hreflang`.

`npm run build` typechecks, builds the browser assets, renders the public pages,
and runs `npm run check:seo`. This check reads HTML without executing JavaScript.
It verifies content, unique metadata, canonical URLs, structured data, initial
styles, asset existence, sitemap agreement and noindex shells. Existing CI runs it
as part of the frontend build. CI also starts the built preview and checks its
actual HTTP responses. Hydration/navigation regressions run with `npm test`.

`vercel.json` uses clean URLs and rewrites only supported learner routes to the
noindex app shell. `/share` remains a query-dependent, noindex browser page.
Missing public pages and missing assets return the custom `404.html` with HTTP
404. Legacy `/practice/:sceneId/*` URLs retain their SPA compatibility fallback.
The old lesson article has a permanent redirect to its current slug.

The sitemap and HTML renderer use the same route list. Article `lastmod` dates
come from editorial `updatedDate` or publication dates. Pages without a known
modification date omit it; a new build does not imply a content update.
`robots.txt` permits crawling so engines can read app/error noindex rules.
`llms.txt` is a supplementary product summary, not a ranking or indexing guarantee.

## Deployment settings

Set these on the **frontend Vercel project**, rooted at `frontend/`, then redeploy:

| Variable | Value or source |
| --- | --- |
| `VITE_SITE_URL` | `https://www.learnwithlinguini.com` — an origin without a path, query or fragment |
| `GOOGLE_SITE_VERIFICATION` | Optional public verification token from the Google Search Console HTML-tag method |
| `BING_SITE_VERIFICATION` | Optional public token from Bing Webmaster Tools' HTML meta-tag method |
| `INDEXNOW_KEY` | Optional 8–128 character key using letters, numbers or hyphens; served publicly at `/indexnow-key.txt` |

Keep the production canonical origin on preview builds. Vercel's preview
deployment `X-Robots-Tag: noindex` must remain in place. Do not submit preview or
development hosts to search engines. In Vercel Domains, confirm HTTP and the apex
domain redirect permanently to the HTTPS `www` origin; this is a host setting,
not something a canonical tag can enforce.

## Verify and submit

1. In [Google Search Console](https://search.google.com/search-console), create or
   use the domain property `learnwithlinguini.com`. Verify its DNS TXT record with
   the domain owner. Alternatively use the exact URL-prefix property
   `https://www.learnwithlinguini.com/` and the HTML token setting above.
2. In [Bing Webmaster Tools](https://www.bing.com/webmasters), import the verified
   Search Console property or complete its ownership verification.
3. Submit `https://www.learnwithlinguini.com/sitemap.xml` to both properties.
4. In Google's URL Inspection, test the live home page, `/learn/spanish`,
   `/learn/korean` and one blog article. Confirm the HTML contains its actual
   heading, the declared canonical is the exact URL, and indexing is allowed.
   Request indexing once for the changed representative pages.
5. Inspect `/login`, `/share` and a made-up blog slug. Expect noindex for the first
   two and HTTP 404 for the missing article. Test the home page and an article in
   [Rich Results Test](https://search.google.com/test/rich-results). Organization,
   breadcrumb and article markup describes real content. FAQ/app markup does not
   guarantee a rich result; do not invent ratings to satisfy eligibility checks.

IndexNow is optional and covers participating engines, not Google. After a
production content release, use the existing script with the deployed public key:

```sh
cd frontend
INDEXNOW_KEY=<deployed-key> node scripts/indexnow.mjs https://www.learnwithlinguini.com
```

Do not run it on a schedule for unchanged pages. Search engines decide whether
and when to index a submitted URL.

## Release checks

```sh
cd frontend
npm ci
npm run lint
npm test
npm run build
npm run preview -- --host 127.0.0.1 --port 4173
```

In another terminal, run:

```sh
cd frontend
node scripts/check-seo.mjs http://127.0.0.1:4173
# After production deployment:
node scripts/check-seo.mjs https://www.learnwithlinguini.com
```

The HTTP checker verifies raw HTML, content types, sharing images, app refreshes,
private-page noindex headers, the old-article redirect and real 404 responses.
Preview hosting intentionally fails its public-page indexing check when Vercel
adds a noindex header. Never remove preview protections to make the check pass.

## Measure outcomes

Before release, export a 28-day Search Console baseline by page and query. Record
indexed canonical URLs, non-brand impressions, clicks, click-through rate and
average position. After release, check sitemap processing and coverage first;
compare the next 28 days with the baseline rather than judging daily fluctuations.
Review Google-selected versus declared canonicals when a page stays excluded.

Group queries around photo-based language learning and the four supported
languages. These are content themes, not measured search-volume claims. Improve
the existing language pages using real learner questions and Search Console
queries. Add a page only when it offers a distinct, useful lesson or explanation.
Publish original product examples; seek relevant links from course pages and
project profiles using the canonical site URL.

In GA4, compare organic landing pages with `guest_demo_scene_selected`,
`guest_demo_signup_clicked`, `signup_submitted` and completed Google sign-ins.
These events indicate actions, not necessarily verified new accounts. The new
`marketing_language_link` event measures comparison-article links to language
pages. Existing SPA pageviews cover all public routes; build-time rendering does
not send analytics events. See [ANALYTICS.md](../ANALYTICS.md).

## References

- [Google JavaScript SEO](https://developers.google.com/search/docs/crawling-indexing/javascript/javascript-seo-basics)
- [Canonical URLs](https://developers.google.com/search/docs/crawling-indexing/consolidate-duplicate-urls)
- [Sitemaps and accurate modification dates](https://developers.google.com/search/docs/crawling-indexing/sitemaps/build-sitemap)
- [Noindex and crawler access](https://developers.google.com/search/docs/crawling-indexing/block-indexing)
- [Vercel configuration](https://vercel.com/docs/project-configuration/vercel-json)
- [Bing IndexNow](https://www.bing.com/indexnow/getstarted)
