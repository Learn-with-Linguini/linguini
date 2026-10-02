/** The deployed learner app (the `frontend/` Vercel project). */
const productionAppUrl = "https://linguini-navy.vercel.app";

function resolveAppUrl(): string {
  if (process.env.NEXT_PUBLIC_APP_URL) return process.env.NEXT_PUBLIC_APP_URL;
  // `VERCEL` is not inlined into browser bundles; `NODE_ENV` is, so client components get the same URL.
  return process.env.NODE_ENV === "production" ? productionAppUrl : "http://localhost:5173";
}

function resolveSiteUrl(): string {
  if (process.env.NEXT_PUBLIC_SITE_URL) return process.env.NEXT_PUBLIC_SITE_URL;
  if (process.env.VERCEL_PROJECT_PRODUCTION_URL) return `https://${process.env.VERCEL_PROJECT_PRODUCTION_URL}`;
  if (process.env.VERCEL_URL) return `https://${process.env.VERCEL_URL}`;
  return "http://localhost:3000";
}

/** Set after launch day; the badge and `sameAs` link stay hidden until then. */
const productHunt = {
  url: process.env.NEXT_PUBLIC_PRODUCT_HUNT_URL ?? "",
  postId: process.env.NEXT_PUBLIC_PRODUCT_HUNT_POST_ID ?? "",
};

const repoUrl = "https://github.com/CS3216-A3-G7/linguini";

export const site = {
  name: "Linguini",
  url: resolveSiteUrl().replace(/\/$/, ""),
  repoUrl,
  productHunt,
  /** Official profiles, for Organization `sameAs`. Add social accounts here once they exist. */
  sameAs: [repoUrl, productHunt.url].filter(Boolean),
  appUrl: resolveAppUrl().replace(/\/$/, ""),
  title: "Linguini — Learn a language from the photos you take",
  shortTitle: "Linguini",
  description:
    "Snap a café, a street, a sunset. Linguini finds the words in your photo and turns them into bite-size Spanish or French games and a journal page. Free to start.",
  tagline: "Learn the language of your day.",
  locale: "en_US",
  ogImageAlt:
    "Linguini — Learn the language of your day. Real photos pinned like prints, one tagged “la mesa · the table”.",
  keywords: [
    "language learning app",
    "learn Spanish with photos",
    "learn French vocabulary",
    "learn a language with pictures",
    "photo vocabulary",
    "language journal",
    "gamified language learning",
    "I-Spy language game",
  ],
} as const;

export const appLinks = {
  signUp: `${site.appUrl}/login?mode=signup`,
  signIn: `${site.appUrl}/login`,
};
