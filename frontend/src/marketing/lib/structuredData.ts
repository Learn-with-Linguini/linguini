import { site } from "./site";

/** Include these entities on each public page so local references resolve independently. */
export function siteEntities(): Record<string, unknown>[] {
  const orgId = `${site.url}/#organization`;
  return [
    {
      "@type": "Organization",
      "@id": orgId,
      name: site.name,
      url: `${site.url}/`,
      sameAs: site.sameAs,
      logo: {
        "@type": "ImageObject",
        url: `${site.url}/brand/linguini-logo.png`,
        width: 360,
        height: 360,
      },
    },
    {
      "@type": "WebSite",
      "@id": `${site.url}/#website`,
      name: site.name,
      url: `${site.url}/`,
      description: site.description,
      inLanguage: "en",
      publisher: { "@id": orgId },
    },
  ];
}
