import type { Metadata } from "next";
import { site } from "@/lib/site";

type PageMetadata = {
  title: string;
  description: string;
  /** Site-relative path, e.g. `/blog`. Used for the canonical URL and `og:url`. */
  path: string;
  /** Articles get `og:type=article`; set `ownImage` when the segment has its own opengraph-image file. */
  article?: { publishedTime: string; section?: string };
  ownImage?: boolean;
  /** A 1200×630 card other than the default, e.g. a `/og?…` journal card. */
  image?: { url: string; alt: string };
};

/** The root `app/opengraph-image.tsx` card, for pages without their own. */
const defaultImage = { url: "/opengraph-image", width: 1200, height: 630, alt: site.ogImageAlt, type: "image/png" };

/**
 * Complete per-page metadata. Next merges `openGraph` and `twitter` shallowly, so a page that sets
 * only a title would otherwise keep the homepage's og:title, og:url and X card text.
 */
export function pageMetadata({ title, description, path, article, ownImage, image }: PageMetadata): Metadata {
  const shareTitle = article ? title : `${title} · ${site.name}`;
  // Leave `images` out entirely when the segment has its own image file; even `images: undefined` hides it.
  const images = ownImage ? {} : { images: [image ? { ...defaultImage, ...image } : defaultImage] };
  return {
    title,
    description,
    alternates: { canonical: path },
    openGraph: {
      siteName: site.name,
      locale: site.locale,
      url: path,
      title: shareTitle,
      description,
      ...images,
      ...(article
        ? { type: "article", publishedTime: article.publishedTime, section: article.section, authors: [`${site.name} team`] }
        : { type: "website" }),
    },
    twitter: { card: "summary_large_image", title: shareTitle, description, ...images },
  };
}
