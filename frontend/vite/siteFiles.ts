import { faq } from "../src/marketing/data/faq.js";
import { languagePages } from "../src/marketing/data/languages.js";
import { posts } from "../src/marketing/data/posts.js";
import { pricing } from "../src/marketing/data/pricing.js";
import { steps } from "../src/marketing/data/steps.js";
import type { HtmlTagDescriptor, Plugin } from "vite";

type SiteFilesOptions = {
  siteUrl: string;
  indexNowKey?: string;
  googleSiteVerification?: string;
  bingSiteVerification?: string;
};

type SitemapEntry = {
  url: string;
  lastModified: Date;
  changeFrequency: string;
  priority: number;
};

function escapeXml(value: string): string {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&apos;");
}

function createSiteFiles(options: SiteFilesOptions): Record<string, string> {
  const siteUrl = (options.siteUrl || "https://www.learnwithlinguini.com").replace(/\/$/, "");
  const lastModified = new Date();
  const sitemapEntries: SitemapEntry[] = [
    { url: `${siteUrl}/`, lastModified, changeFrequency: "weekly", priority: 1 },
    ...languagePages.map(page => ({
      url: `${siteUrl}/learn/${page.slug}`,
      lastModified,
      changeFrequency: "monthly",
      priority: 0.8,
    })),
    { url: `${siteUrl}/blog`, lastModified, changeFrequency: "weekly", priority: 0.6 },
    ...posts.map(post => ({
      url: `${siteUrl}/blog/${post.slug}`,
      lastModified: new Date(`${post.date}T00:00:00Z`),
      changeFrequency: "monthly",
      priority: 0.5,
    })),
    { url: `${siteUrl}/credits`, lastModified, changeFrequency: "monthly", priority: 0.3 },
    { url: `${siteUrl}/privacy`, lastModified, changeFrequency: "yearly", priority: 0.2 },
    { url: `${siteUrl}/terms`, lastModified, changeFrequency: "yearly", priority: 0.2 },
  ];
  const sitemap = [
    '<?xml version="1.0" encoding="UTF-8"?>',
    '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ...sitemapEntries.flatMap(entry => [
      "  <url>",
      `    <loc>${escapeXml(entry.url)}</loc>`,
      `    <lastmod>${entry.lastModified.toISOString()}</lastmod>`,
      `    <changefreq>${entry.changeFrequency}</changefreq>`,
      `    <priority>${entry.priority}</priority>`,
      "  </url>",
    ]),
    "</urlset>",
    "",
  ].join("\n");

  const llms = [
    "# Linguini",
    "",
    "> Snap a café, a street, a sunset. Linguini turns the words in your photo into bite-size Spanish or French games and a journal page. Join the public beta for unlimited photo lessons.",
    "",
    "Linguini is a web app for beginners and returning learners (roughly CEFR A1–A2) who want to learn Spanish or French from English. Instead of a fixed word list, each lesson is built from a photo of the learner's own day, so the vocabulary is about things they actually see.",
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
    `- [Home and interactive demo](${siteUrl}/): try a lesson on a real photo without signing up`,
    `- [Pricing](${siteUrl}/#pricing)`,
    ...languagePages.map(
      page => `- [Learn ${page.name} with photos](${siteUrl}/learn/${page.slug}): every ${page.name} word in the demo scenes, with article, gender and pronunciation, and a worked session`,
    ),
    `- [Join the public beta](${new URL("/login?mode=signup", siteUrl).toString()})`,
    `- [Blog](${siteUrl}/blog)`,
    ...posts.map(post => `- [${post.title}](${siteUrl}/blog/${post.slug}): ${post.summary}`),
    `- [Photo credits](${siteUrl}/credits): source and licence of every photo on the site`,
    "",
  ].join("\n");
  const manifest = JSON.stringify({
    name: "Linguini — Learn a language from the photos you take",
    short_name: "Linguini",
    description: "Snap a café, a street, a sunset. Linguini turns the words in your photo into bite-size Spanish or French games and a journal page. Join the public beta for unlimited photo lessons.",
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

  if (options.indexNowKey) files["indexnow-key.txt"] = options.indexNowKey;
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
