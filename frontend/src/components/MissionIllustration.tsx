import type { ReactNode } from "react";

const paths: Record<string, ReactNode> = {
  M01: <><path d="M2 16s5-8 14-8 14 8 14 8-5 8-14 8S2 16 2 16Z" /><circle cx="16" cy="16" r="4" /></>,
  M02: <><circle cx="13" cy="13" r="8" /><path d="m19 19 9 9" /></>,
  M03: <><path d="M5 8h2v16M13 10c0-5 8-5 8 0 0 4-8 7-8 12h9" /><circle cx="27" cy="24" r="1" /></>,
  M04: <><path d="M5 9h15l9 9-12 12L5 18V9Z" /><circle cx="11" cy="15" r="2" /><path d="m4 4 7 9" /></>,
  M05: <path d="M16 27 5 16C-3 7 10 0 16 9 22 0 35 7 27 16L16 27Z" />,
  M06: <><path d="M4 5h24v17H15l-8 6v-6H4V5Z" /><path d="M10 11h12M10 16h8" /></>,
  M07: <><path d="M3 8h16l11 11-12 11L3 15V8Z" /><circle cx="9" cy="13" r="2" /><path d="M18 13v11m4-9c-8-4-9 7-1 5" /></>,
  M08: <><circle cx="16" cy="16" r="12" /><path d="M16 8v9l6 4" /></>,
  M09: <><path d="M7 10a11 11 0 1 1-1 12M3 4v8h8" /><path d="M12 14h10M12 19h7" /></>,
  M10: <><path d="m5 27 11-11a8 8 0 0 1 10-11l-6 6 1 4 4 1 6-6a8 8 0 0 1-11 10L9 31Z" /></>,
  M11: <><rect x="4" y="7" width="24" height="19" rx="3" /><path d="m5 9 11 9L27 9" /></>,
  M12: <><rect x="4" y="7" width="24" height="22" rx="3" /><path d="M4 13h24M10 3v7M22 3v7m-11 10 4 4 7-7" /></>,
};

export function MissionIllustration({ missionId }: { missionId: string }) {
  return <svg width="28" height="28" viewBox="0 0 34 34" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    {paths[missionId] ?? paths.M01}
  </svg>;
}
