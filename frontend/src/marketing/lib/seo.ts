import { useEffect } from "react";
import { site } from "./site";

type PageMetadata = {
  title: string;
  description: string;
  path: string;
  home?: boolean;
  canonicalPath?: string;
  ogUrl?: string;
  noIndex?: boolean;
  ogTitle?: string;
  documentTitle?: string;
  article?: { publishedTime: string; section?: string };
  image?: { url: string; alt: string };
};

function setMeta(name: string, content: string | undefined, property = false) {
  const existing = Array.from(document.head.querySelectorAll("meta")).find(
    element => element.getAttribute("name") === name || element.getAttribute("property") === name,
  );

  if (!content) {
    existing?.remove();
    return;
  }

  const element = existing ?? document.createElement("meta");
  element.setAttribute(property ? "property" : "name", name);
  element.setAttribute("content", content);
  if (!existing) document.head.append(element);
}

export function PageMeta({
  title,
  description,
  path,
  home = false,
  canonicalPath = path,
  ogUrl = path,
  noIndex = false,
  ogTitle,
  documentTitle,
  article,
  image,
}: PageMetadata) {
  useEffect(() => {
    const shareTitle = ogTitle ?? (article ? title : home ? site.title : `${title} · ${site.name}`);
    const imageUrl = new URL(image?.url ?? site.ogImage, site.url).toString();
    const imageAlt = image?.alt ?? site.ogImageAlt;
    const canonical = document.head.querySelector<HTMLLinkElement>('link[rel="canonical"]') ?? document.createElement("link");

    document.title = documentTitle ?? (home ? site.title : `${title} · ${site.name}`);
    canonical.rel = "canonical";
    canonical.href = new URL(canonicalPath, site.url).toString();
    if (!canonical.isConnected) document.head.append(canonical);

    setMeta("description", description);
    setMeta("robots", noIndex ? "noindex,follow" : "index,follow");
    setMeta("og:site_name", site.name, true);
    setMeta("og:locale", site.locale, true);
    setMeta("og:type", article ? "article" : "website", true);
    setMeta("og:url", new URL(ogUrl, site.url).toString(), true);
    setMeta("og:title", shareTitle, true);
    setMeta("og:description", description, true);
    setMeta("og:image", imageUrl, true);
    setMeta("og:image:width", "1200", true);
    setMeta("og:image:height", "630", true);
    setMeta("og:image:type", "image/png", true);
    setMeta("og:image:alt", imageAlt, true);
    setMeta("twitter:card", "summary_large_image");
    setMeta("twitter:title", shareTitle);
    setMeta("twitter:description", description);
    setMeta("twitter:image", imageUrl);
    setMeta("twitter:image:alt", imageAlt);
    setMeta("article:published_time", article?.publishedTime, true);
    setMeta("article:section", article?.section, true);
    setMeta("article:author", article ? `${site.name} team` : undefined, true);
  }, [article, canonicalPath, description, documentTitle, home, image, noIndex, ogTitle, ogUrl, path, title]);

  return null;
}
