import { useEffect, useRef } from "react";
import { useLocation } from "react-router-dom";
import { initAnalytics, trackPageView } from "../lib/analytics.ts";

export function AnalyticsTracker() {
  const location = useLocation();
  const isFirstMount = useRef(true);

  useEffect(() => {
    initAnalytics();
  }, []);

  useEffect(() => {
    const currentPath = location.pathname + location.search;
    if (isFirstMount.current) {
      isFirstMount.current = false;
      trackPageView(currentPath);
      return;
    }
    trackPageView(currentPath);
  }, [location.pathname, location.search]);

  return null;
}
