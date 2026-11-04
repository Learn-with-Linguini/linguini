import { createElement, Fragment } from "react";
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
  article?: { publishedTime: string; modifiedTime?: string; section?: string };
  image?: { url: string; alt: string };
};

/** React hoists these elements into the head during rendering and hydration. */
export function PageMeta({
  title, description, path, home = false, canonicalPath = path, ogUrl = path,
  noIndex = false, ogTitle, documentTitle, article, image,
}: PageMetadata) {
  const shareTitle = ogTitle ?? (article ? title : home ? site.title : `${title} · ${site.name}`);
  const imageUrl = new URL(image?.url ?? site.ogImage, site.url).toString();
  const imageAlt = image?.alt ?? site.ogImageAlt;
  const canonical = new URL(canonicalPath, site.url);
  canonical.search = "";
  canonical.hash = "";
  if (canonical.pathname !== "/") canonical.pathname = canonical.pathname.replace(/\/+$/, "");
  const meta = (name: string, content: string | undefined, property = false) =>
    content ? createElement("meta", { key: name, [property ? "property" : "name"]: name, content }) : null;

  return createElement(Fragment, null,
    createElement("title", null, documentTitle ?? (home ? site.title : `${title} · ${site.name}`)),
    !noIndex && createElement("link", { rel: "canonical", href: canonical.toString() }),
    meta("description", description),
    meta("robots", noIndex ? "noindex,follow" : "index,follow,max-image-preview:large"),
    meta("og:site_name", site.name, true),
    meta("og:locale", site.locale, true),
    meta("og:type", article ? "article" : "website", true),
    meta("og:url", new URL(ogUrl, site.url).toString(), true),
    meta("og:title", shareTitle, true),
    meta("og:description", description, true),
    meta("og:image", imageUrl, true),
    meta("og:image:width", "1200", true),
    meta("og:image:height", "630", true),
    meta("og:image:type", "image/png", true),
    meta("og:image:alt", imageAlt, true),
    meta("twitter:card", "summary_large_image"),
    meta("twitter:title", shareTitle),
    meta("twitter:description", description),
    meta("twitter:image", imageUrl),
    meta("twitter:image:alt", imageAlt),
    meta("article:published_time", article?.publishedTime, true),
    meta("article:modified_time", article?.modifiedTime, true),
    meta("article:section", article?.section, true),
    meta("article:author", article ? `${site.name} team` : undefined, true),
  );
}
