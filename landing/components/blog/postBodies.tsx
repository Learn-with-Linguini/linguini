import type { ComponentType } from "react";
import { BusinessModel } from "./posts/BusinessModel";
import { CompareAppsPost } from "./posts/CompareApps";
import { LaunchCampaign } from "./posts/LaunchCampaign";
import { PhotoLessons } from "./posts/PhotoLessons";

/** Body component for each post slug in data/posts.ts. */
export const postBodies: Record<string, ComponentType> = {
  "launch-week": LaunchCampaign,
  "linguini-business-model": BusinessModel,
  "why-we-teach-with-your-photos": PhotoLessons,
  "linguini-vs-duolingo": CompareAppsPost,
};
