/**
 * Global social media links and handles for Linguini.
 * Update these constants when URLs or handles change.
 */

export const SOCIAL_LINKS = {
  linkedin: {
    platform: "linkedin" as const,
    label: "LinkedIn",
    url: "https://www.linkedin.com/in/learn-with-linguini",
    handle: "learn-with-linguini",
  },
  instagram: {
    platform: "instagram" as const,
    label: "Instagram",
    url: "https://www.instagram.com/learn_with_linguini/",
    handle: "@learn_with_linguini",
  },
  x: {
    platform: "x" as const,
    label: "X",
    url: "https://x.com/Linguini_App",
    handle: "@Linguini_App",
  },
  tiktok: {
    platform: "tiktok" as const,
    label: "TikTok",
    url: "https://www.tiktok.com/@learnwithlinguini",
    handle: "@learnwithlinguini",
  },
} as const;

export type SocialPlatform = keyof typeof SOCIAL_LINKS;

export const SOCIAL_LINKS_LIST = [
  SOCIAL_LINKS.instagram,
  SOCIAL_LINKS.tiktok,
  SOCIAL_LINKS.x,
  SOCIAL_LINKS.linkedin,
];
