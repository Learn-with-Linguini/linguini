import { faq } from "../src/marketing/data/faq.js";
import { languagePages } from "../src/marketing/data/languages.js";
import { posts } from "../src/marketing/data/posts.js";
import { pricing } from "../src/marketing/data/pricing.js";
import { steps } from "../src/marketing/data/steps.js";
import { siteContent } from "../src/marketing/lib/siteContent.js";
import { normalizeSiteUrl } from "../src/marketing/lib/siteUrl.js";
import { marketingRoutes } from "../src/marketing/routes.js";
import type { HtmlTagDescriptor, Plugin } from "vite";

type SiteFilesOptions = {
  siteUrl: string;
  indexNowKey?: string;
  googleSiteVerification?: string;
  bingSiteVerification?: string;
};

function escapeXml(value: string): string {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&apos;");
}

export function createSiteFiles(options: SiteFilesOptions): Record<string, string> {
  const siteUrl = normalizeSiteUrl(options.siteUrl);
  const sitemap = [
    '<?xml version="1.0" encoding="UTF-8"?>',
    '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ...marketingRoutes.flatMap(path => {
      const post = posts.find(item => path === `/blog/${item.slug}`);
      return [
        "  <url>",
        `    <loc>${escapeXml(new URL(path, siteUrl).href)}</loc>`,
        ...(post ? [`    <lastmod>${escapeXml(post.updatedDate ?? post.date)}</lastmod>`] : []),
        "  </url>",
      ];
    }),
    "</urlset>",
    "",
  ].join("\n");

  const llms = [
    "# Linguini",
    "",
    `> ${siteContent.description}`,
    "",
    "Linguini teaches Spanish, French and German, plus beginner Korean, from English. Instead of a fixed word list, each lesson starts with a photo of the learner's own day. Learners review AI-suggested objects before studying vocabulary and practising sentences. Level coverage varies by language; Korean currently focuses on beginner content.",
    "",
    "## How it works",
    "",
    ...steps.map((step, index) => `${index + 1}. **${step.title}.** ${step.body}`),
    "",
    "## Public beta access",
    "",
    `- **Beta ($0 during the public beta):** ${pricing.beta.join("; ")}.`,
    "- Everyone who signs up during the public beta receives the Beta tier. Free and Plus tiers may be introduced after the beta.",
    "",
    "## FAQ",
    "",
    ...faq.flatMap(({ q, a }) => [`### ${q}`, "", a, ""]),
    "## Links",
    "",
    `- [Home](${siteUrl}/): learn how photo lessons work`,
    `- [Interactive demo](${siteUrl}/demo): try a lesson on a bundled photo without signing up`,
    `- [Pricing](${siteUrl}/#pricing)`,
    ...languagePages.map(
      page => `- [Learn ${page.name} with photos](${siteUrl}/learn/${page.slug}): vocabulary, pronunciation and a worked photo session${page.lang === "ko" ? "" : ", including articles and grammatical gender"}`,
    ),
    `- [Join the public beta](${new URL("/login?mode=signup", siteUrl).toString()})`,
    `- [Blog](${siteUrl}/blog)`,
    ...posts.map(post => `- [${post.title}](${siteUrl}/blog/${post.slug}): ${post.summary}`),
    `- [Photo credits](${siteUrl}/credits): source and licence of every photo on the site`,
    "",
  ].join("\n");
  const manifest = JSON.stringify({
    name: siteContent.title,
    short_name: siteContent.name,
    description: siteContent.description,
    start_url: "/",
    scope: "/",
    display: "standalone",
    background_color: "#fbf8ef",
    theme_color: "#fbf8ef",
    lang: "en",
    categories: ["education"],
    icons: [
      { src: "/icon.png", sizes: "64x64", type: "image/png" },
      { src: "/apple-touch-icon.png", sizes: "180x180", type: "image/png", purpose: "any" },
      { src: "/brand/linguini-logo.png", sizes: "360x360", type: "image/png", purpose: "any" },
    ],
  }, null, 2);

  const files: Record<string, string> = {
    "sitemap.xml": sitemap,
    "robots.txt": `User-agent: *\nAllow: /\nSitemap: ${siteUrl}/sitemap.xml\n`,
    "llms.txt": llms,
    "manifest.webmanifest": manifest,
  };

  if (options.indexNowKey) {
    if (!/^[A-Za-z0-9-]{8,128}$/.test(options.indexNowKey)) {
      throw new Error("INDEXNOW_KEY must contain 8–128 letters, numbers or hyphens.");
    }
    files["indexnow-key.txt"] = options.indexNowKey;
  }
  return files;
}

const contentTypes: Record<string, string> = {
  "sitemap.xml": "application/xml; charset=utf-8",
  "robots.txt": "text/plain; charset=utf-8",
  "llms.txt": "text/markdown; charset=utf-8",
  "manifest.webmanifest": "application/manifest+json; charset=utf-8",
  "indexnow-key.txt": "text/plain; charset=utf-8",
};

export function siteFiles(options: SiteFilesOptions): Plugin {
  return {
    name: "linguini-site-files",
    configureServer(server) {
      const files = createSiteFiles(options);
      server.middlewares.use((request, response, next) => {
        const fileName = (request.url ?? "").split("?")[0].replace(/^\/+/, "");
        const content = files[fileName];
        if (content === undefined) return next();
        response.statusCode = 200;
        response.setHeader("Content-Type", contentTypes[fileName] ?? "text/plain; charset=utf-8");
        response.end(content);
      });
    },
    generateBundle() {
      for (const [fileName, source] of Object.entries(createSiteFiles(options))) {
        this.emitFile({ type: "asset", fileName, source });
      }
    },
    transformIndexHtml() {
      const tags: HtmlTagDescriptor[] = [];
      if (options.googleSiteVerification) {
        tags.push({
          tag: "meta",
          attrs: { name: "google-site-verification", content: options.googleSiteVerification },
          injectTo: "head",
        });
      }
      if (options.bingSiteVerification) {
        tags.push({
          tag: "meta",
          attrs: { name: "msvalidate.01", content: options.bingSiteVerification },
          injectTo: "head",
        });
      }
      return tags;
    },
  };
}
