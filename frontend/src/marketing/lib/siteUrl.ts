export const DEFAULT_SITE_URL = "https://www.learnwithlinguini.com";

/** Every canonical, sitemap URL and entity ID must use the same origin. */
export function normalizeSiteUrl(value: string | undefined): string {
  const url = new URL(value?.trim() || DEFAULT_SITE_URL);
  if (!/^https?:$/.test(url.protocol) || url.username || url.password || url.pathname !== "/" || url.search || url.hash) {
    throw new Error("VITE_SITE_URL must be an HTTP(S) origin without credentials, a path, a query or a fragment");
  }
  return url.origin;
}
