import { pricing } from "../data/pricing";
import { appLinks, site } from "../lib/site";
import { siteEntities } from "../lib/structuredData";

export type FaqItem = { q: string; a: string };

type JsonLdProps = {
  /** Optional FAQ entries; when present a FAQPage node is added to the graph. */
  faq?: FaqItem[];
};

/** Serialise for an inline <script>: `<` is escaped so the payload can never close the tag. */
export function serializeJsonLd(data: unknown): string {
  return JSON.stringify(data).replace(/</g, "\\u003c");
}

export function JsonLd({ faq }: JsonLdProps) {
  const orgId = `${site.url}/#organization`;
  const websiteId = `${site.url}/#website`;
  const appId = `${site.url}/#app`;
  const graph: Record<string, unknown>[] = [
    ...siteEntities(),
    {
      "@type": "SoftwareApplication",
      "@id": appId,
      name: site.name,
      description: site.description,
      url: `${site.url}/`,
      installUrl: new URL(appLinks.signUp, site.url).toString(),
      applicationCategory: "EducationalApplication",
      operatingSystem: "Web",
      image: new URL(site.ogImage, site.url).toString(),
      publisher: { "@id": orgId },
      inLanguage: "en",
      featureList: pricing.beta,
      offers: [
        {
          "@type": "Offer",
          name: "Beta",
          description: pricing.beta.join("; "),
          price: "0",
          priceCurrency: pricing.currency,
          category: "free",
        },
      ],
    },
  ];

  if (faq && faq.length > 0) {
    graph.push({
      "@type": "FAQPage",
      "@id": `${site.url}/#faq`,
      isPartOf: { "@id": websiteId },
      mainEntity: faq.map(({ q, a }) => ({
        "@type": "Question",
        name: q,
        acceptedAnswer: { "@type": "Answer", text: a },
      })),
    });
  }

  return (
    <script
      type="application/ld+json"
      dangerouslySetInnerHTML={{ __html: serializeJsonLd({ "@context": "https://schema.org", "@graph": graph }) }}
    />
  );
}
export default JsonLd;
