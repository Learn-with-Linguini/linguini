# IndexNow submissions

IndexNow tells participating search engines that published content changed. It
does not submit to Google or guarantee crawling, indexing or rankings.

Set `INDEXNOW_KEY` in the frontend deployment settings and redeploy. The key must
contain 8–128 letters, numbers or hyphens and be served as plain text at
`https://www.learnwithlinguini.com/indexnow-key.txt`. This is a public ownership
verification key, not an account credential.

After a production content deployment, run from `frontend/`:

```sh
INDEXNOW_KEY=<deployed-key> node scripts/indexnow.mjs https://www.learnwithlinguini.com
```

The origin must be explicit. The script does not fall back to `VITE_SITE_URL`,
because a preview build may set it. Use the final production HTTPS origin rather
than the apex domain if it redirects to `www`. Development, preview and local
hosts are rejected. The script sends no notification until these checks pass:

- The deployed key matches and is served as plain text.
- Home returns HTML, declares the exact canonical origin and permits indexing.
- The sitemap returns XML with a nonempty list of canonical URLs on that origin.
- Responses are successful, bounded in size, timely and free of redirects.

Noindex on the key or sitemap file is allowed; the homepage's indexing rules
determine whether the deployment is eligible for submission.

Duplicate sitemap URLs are submitted once. One request supports up to 10,000
sitemap entries. Invalid or oversized input stops the submission. HTTP 200 means
the notification was received; HTTP 202 means key validation may still be
pending. Inspect Bing Webmaster Tools for subsequent crawl/indexing results.

Run `node --experimental-strip-types --test tests/indexnow.test.ts` to check
validation and submission behavior. Tests use simulated responses and do not
contact a search engine. Run submissions only for meaningful published changes.

References: [IndexNow documentation](https://www.indexnow.org/documentation),
[Bing setup](https://www.bing.com/indexnow/getstarted).
