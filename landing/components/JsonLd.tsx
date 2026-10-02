import { pricing } from "@/data/pricing";
import { appLinks, site } from "@/lib/site";

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
  const logoUrl = `${site.url}/brand/linguini-logo.png`;

  const graph: Record<string, unknown>[] = [
    {
      "@type": "Organization",
      "@id": orgId,
      name: site.name,
      url: `${site.url}/`,
      sameAs: site.sameAs,
      logo: {
        "@type": "ImageObject",
        url: logoUrl,
        width: 360,
        height: 360,
      },
    },
    {
      "@type": "WebSite",
      "@id": websiteId,
      name: site.name,
      url: `${site.url}/`,
      description: site.description,
      inLanguage: "en",
      publisher: { "@id": orgId },
    },
    {
      "@type": "SoftwareApplication",
      "@id": appId,
      name: site.name,
      description: site.description,
      url: `${site.url}/`,
      installUrl: appLinks.signUp,
      applicationCategory: "EducationalApplication",
      operatingSystem: "Web",
      image: `${site.url}/opengraph-image`,
      publisher: { "@id": orgId },
      inLanguage: ["es", "fr"],
      featureList: [...pricing.free, ...pricing.plus],
      offers: [
        {
          "@type": "Offer",
          name: "Free",
          description: pricing.free.join("; "),
          price: "0",
          priceCurrency: pricing.currency,
          category: "free",
        },
        {
          "@type": "Offer",
          name: "Plus",
          description: pricing.plus.join("; "),
          price: String(pricing.plusMonthly),
          priceCurrency: pricing.currency,
          category: "subscription",
          priceSpecification: {
            "@type": "UnitPriceSpecification",
            price: String(pricing.plusMonthly),
            priceCurrency: pricing.currency,
            unitCode: "MON",
            billingDuration: "P1M",
            referenceQuantity: {
              "@type": "QuantitativeValue",
              value: 1,
              unitCode: "MON",
            },
          },
        },
        {
          "@type": "Offer",
          name: "Plus (yearly)",
          description: pricing.plus.join("; "),
          price: String(pricing.plusYearly),
          priceCurrency: pricing.currency,
          category: "subscription",
          priceSpecification: {
            "@type": "UnitPriceSpecification",
            price: String(pricing.plusYearly),
            priceCurrency: pricing.currency,
            unitCode: "ANN",
            billingDuration: "P1Y",
            referenceQuantity: {
              "@type": "QuantitativeValue",
              value: 1,
              unitCode: "ANN",
            },
          },
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
