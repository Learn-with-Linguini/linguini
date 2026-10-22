import { useEffect, useRef } from "react";
import { useLocation } from "react-router-dom";
import { initAnalytics, trackPageView } from "../lib/analytics.ts";
import { captureAttribution } from "../lib/attribution.ts";

export function AnalyticsTracker() {
  const location = useLocation();
  const lastTrackedPath = useRef<string | null>(null);

  useEffect(() => {
    initAnalytics();
  }, []);

  useEffect(() => {
    captureAttribution(location.search);
    const currentPath = location.pathname + location.search;
    if (lastTrackedPath.current === currentPath) return;
    lastTrackedPath.current = currentPath;
    trackPageView(currentPath);
  }, [location.pathname, location.search]);

  return null;
}
