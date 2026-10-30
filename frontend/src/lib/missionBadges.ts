export const MISSION_BADGE_ASSETS: Record<string, string> = {
  M01: "/badges/spot-and-say.webp",
  M02: "/badges/seek-and-find.webp",
  M03: "/badges/count-me-in.webp",
  M04: "/badges/mine-and-yours.webp",
  M05: "/badges/pick-flavour.webp",
  M06: "/badges/ask-away.webp",
  M07: "/badges/price-tag.webp",
  M08: "/badges/daily-dish.webp",
  M09: "/badges/let-me-rephrase.webp",
  M10: "/badges/problem-solver.webp",
  M11: "/badges/pass-it-on.webp",
  M12: "/badges/make-it-happen.webp",
};

export const missionBadgeAsset = (missionId: string) => MISSION_BADGE_ASSETS[missionId] ?? null;
