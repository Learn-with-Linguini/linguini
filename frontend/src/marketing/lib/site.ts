const defaultSupportEmail = "linguini-support@googlegroups.com";

/** Set after launch day; the badge and `sameAs` link stay hidden until then. */
const productHunt = {
  url: import.meta.env.VITE_PRODUCT_HUNT_URL ?? "",
  postId: import.meta.env.VITE_PRODUCT_HUNT_POST_ID ?? "",
};

export const site = {
  name: "Linguini",
  url: (import.meta.env.VITE_SITE_URL || "https://www.learnwithlinguini.com").replace(/\/$/, ""),
  productHunt,
  supportEmail: import.meta.env.VITE_SUPPORT_EMAIL?.trim() || defaultSupportEmail,
  /** Official profiles, for Organization `sameAs`. Add social accounts here once they exist. */
  sameAs: [productHunt.url].filter(Boolean),
  title: "Linguini — Learn a language from the photos you take",
  shortTitle: "Linguini",
  description:
    "Snap a café, a street, a sunset. Linguini turns the words in your photo into bite-size Spanish or French games and a journal page. Join the public beta for unlimited photo lessons.",
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
  signUp: "/login?mode=signup",
  signIn: "/login",
  contact: "/contact",
};
