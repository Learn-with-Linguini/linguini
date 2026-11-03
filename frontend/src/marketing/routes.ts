import { languagePages } from "./data/languages.js";
import { posts } from "./data/posts.js";

/** Public canonical pages, shared by the HTML build and sitemap. */
export const marketingRoutes: string[] = [
  "/", ...languagePages.map(page => `/learn/${page.slug}`), "/blog",
  ...posts.map(post => `/blog/${post.slug}`), "/credits", "/privacy", "/terms",
];

/** Matches the learner URLs that need the SPA shell on a direct request. */
export const learnerRoutePatterns = [
  "/:page(login|demo|reset-password|onboarding|contact|payment|home|rooms|practice|ispy|progress|vocabulary|journal|profile)",
  "/rooms/:roomId", "/practice/:path*",
  "/ispy/:page(play|challenge|friends|legacy-rooms)", "/ispy/friends/:chatId",
  "/ispy/games/:sessionId", "/ispy/games/:sessionId/:phase(clues|describe|results)",
  "/journal/new/:date", "/journal/:entryId", "/profile/edit",
];
