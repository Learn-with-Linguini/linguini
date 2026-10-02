import { faq } from "@/data/faq";
import { languagePages } from "@/data/languages";
import { posts } from "@/data/posts";
import { pricing, yearlyPerMonth } from "@/data/pricing";
import { steps } from "@/data/steps";
import { appLinks, site } from "@/lib/site";

export const dynamic = "force-static";

/**
 * A plain-Markdown summary for AI assistants and answer engines (https://llmstxt.org).
 * Built from the same data as the page so prices, steps and FAQ answers never drift.
 */
export function GET() {
  const body = [
    `# ${site.name}`,
    "",
    `> ${site.description}`,
    "",
    `${site.name} is a web app for beginners and returning learners (roughly CEFR A1–A2) who want to learn Spanish or French from English. Instead of a fixed word list, each lesson is built from a photo of the learner's own day, so the vocabulary is about things they actually see.`,
    "",
    "## How it works",
    "",
    ...steps.map((step, i) => `${i + 1}. **${step.title}.** ${step.body}`),
    "",
    "## Pricing",
    "",
    `- **Free ($0, forever):** ${pricing.free.join("; ")}.`,
    `- **Plus ($${pricing.plusMonthly}/month, or $${pricing.plusYearly}/year ≈ $${yearlyPerMonth}/month):** ${pricing.plus.join("; ")}. ${pricing.trialDays}-day free trial.`,
    `- **Founding Plus:** the first ${pricing.foundingSeats} members pay $${pricing.foundingYearly}/year.`,
    `- Prices in ${pricing.currency}. Cancel any time; the journal stays on the free plan.`,
    "",
    "## FAQ",
    "",
    ...faq.flatMap(({ q, a }) => [`### ${q}`, "", a, ""]),
    "## Links",
    "",
    `- [Home and interactive demo](${site.url}/): try a lesson on a real photo without signing up`,
    `- [Pricing](${site.url}/#pricing)`,
    ...languagePages.map(
      page => `- [Learn ${page.name} with photos](${site.url}/learn/${page.slug}): every ${page.name} word in the demo scenes, with article, gender and pronunciation, and a worked session`,
    ),
    `- [Start learning free](${appLinks.signUp})`,
    `- [Blog](${site.url}/blog)`,
    ...posts.map(post => `- [${post.title}](${site.url}/blog/${post.slug}): ${post.summary}`),
    `- [Photo credits](${site.url}/credits): source and licence of every photo on the site`,
    "",
  ].join("\n");

  return new Response(body, { headers: { "Content-Type": "text/markdown; charset=utf-8" } });
}
