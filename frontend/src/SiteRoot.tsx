import { Suspense, type ReactNode } from "react";
import { AnalyticsTracker } from "./components/AnalyticsTracker";

/** Keep the server/client component tree identical, including useId positions. */
export function SiteRoot({ children }: { children: ReactNode }) {
  return <><AnalyticsTracker /><Suspense fallback={null}>{children}</Suspense></>;
}
