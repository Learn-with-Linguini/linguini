import { SOCIAL_LINKS } from "../../config/social";
import { siteContent } from "./siteContent";
import { normalizeSiteUrl } from "./siteUrl";

const defaultSupportEmail = "linguini-support@googlegroups.com";

/** Set after launch day; the badge and `sameAs` link stay hidden until then. */
const productHunt = {
  url: import.meta.env.VITE_PRODUCT_HUNT_URL ?? "",
  postId: import.meta.env.VITE_PRODUCT_HUNT_POST_ID ?? "",
};

export const site = {
  ...siteContent,
  url: normalizeSiteUrl(import.meta.env.VITE_SITE_URL),
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
