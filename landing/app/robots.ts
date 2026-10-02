import type { MetadataRoute } from "next";
import { site } from "@/lib/site";

export default function robots(): MetadataRoute.Robots {
  return {
    // Everything stays crawlable: social crawlers (e.g. Twitterbot) honour robots.txt, so
    // blocking /share or /og would break link previews. /share opts out of indexing via
    // its own `noindex` robots meta instead.
    rules: [{ userAgent: "*", allow: "/" }],
    sitemap: `${site.url}/sitemap.xml`,
  };
}
