import type { MetadataRoute } from "next";
import { languagePages } from "@/data/languages";
import { posts } from "@/data/posts";
import { site } from "@/lib/site";

export default function sitemap(): MetadataRoute.Sitemap {
  const lastModified = new Date();
  return [
    {
      url: `${site.url}/`,
      lastModified,
      changeFrequency: "weekly",
      priority: 1,
    },
    ...languagePages.map(page => ({
      url: `${site.url}/learn/${page.slug}`,
      lastModified,
      changeFrequency: "monthly" as const,
      priority: 0.8,
    })),
    {
      url: `${site.url}/blog`,
      lastModified,
      changeFrequency: "weekly",
      priority: 0.6,
    },
    ...posts.map(post => ({
      url: `${site.url}/blog/${post.slug}`,
      lastModified: new Date(`${post.date}T00:00:00Z`),
      changeFrequency: "monthly" as const,
      priority: 0.5,
    })),
    {
      url: `${site.url}/credits`,
      lastModified,
      changeFrequency: "monthly",
      priority: 0.3,
    },
  ];
}
