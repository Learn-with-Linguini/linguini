import { SOCIAL_LINKS } from "../../config/social";

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
  /** Official profiles, for Organization `sameAs`. */
  sameAs: [
    productHunt.url,
    SOCIAL_LINKS.instagram.url,
    SOCIAL_LINKS.tiktok.url,
    SOCIAL_LINKS.x.url,
    SOCIAL_LINKS.linkedin.url,
  ].filter(Boolean),
  title: "Linguini — Learn a language from the photos you take",
  shortTitle: "Linguini",
  description:
    "Snap a café, a street, a sunset. Linguini turns the words in your photo into bite-size language games. Learn Spanish, French, German or beginner Korean in the public beta.",
  tagline: "Learn the language of your day.",
  locale: "en_US",
  ogImage: "/og/linguini-beta.png",
  ogImageAlt:
    "Linguini public beta — turn everyday photos into short lessons in Spanish, French, German or beginner Korean, with unlimited photo lessons at $0 during beta.",
  keywords: [
    "language learning app",
    "learn Spanish with photos",
    "learn French vocabulary",
    "learn German with photos",
    "beginner Korean vocabulary",
    "learn a language with pictures",
    "photo vocabulary",
    "gamified language learning",
    "I-Spy language game",
  ],
} as const;

export const appLinks = {
  signUp: "/login?mode=signup",
  signIn: "/login",
  contact: "/contact",
};
