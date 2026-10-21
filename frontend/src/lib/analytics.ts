/**
 * Analytics integration for Contentsquare (SPA pageviews & custom events)
 * and Google Analytics 4 (GA4 measurement & event tracking).
 */

declare global {
  interface Window {
    dataLayer?: unknown[];
    gtag?: (...args: unknown[]) => void;
    _uxa?: unknown[][];
  }
}

export const GA_MEASUREMENT_IDS = {
  dev: "G-ET4KFFXFMZ",
  prod: "G-CHBF82TVG3",
} as const;

export function resolveGaMeasurementId(hostname?: string): string | null {
  // 1. Explicitly configured in .env / .env.local
  const envId = (
    typeof import.meta !== "undefined" && import.meta.env
      ? (import.meta.env.VITE_GA_MEASUREMENT_ID as string | undefined)
      : undefined
  )?.trim();
  if (envId) return envId;

  // 2. Auto-detect from domain if running in browser
  const host =
    hostname ??
    (typeof window !== "undefined" && window.location?.hostname
      ? window.location.hostname.toLowerCase()
      : "");
  if (!host) return null;

  if (host === "dev.learnwithlinguini.com") {
    return GA_MEASUREMENT_IDS.dev;
  }
  if (host === "www.learnwithlinguini.com" || host === "learnwithlinguini.com") {
    return GA_MEASUREMENT_IDS.prod;
  }

  return null;
}

export function initAnalytics(): void {
  if (typeof window === "undefined") return;

  // Ensure Contentsquare command queue exists
  window._uxa = window._uxa || [];

  // Setup GA4 gtag
  const measurementId = resolveGaMeasurementId();
  if (measurementId && typeof document !== "undefined") {
    window.dataLayer = window.dataLayer || [];
    if (!window.gtag) {
      window.gtag = function () {
        window.dataLayer?.push(arguments);
      };
      window.gtag("js", new Date());
      window.gtag("config", measurementId, {
        send_page_view: false, // SPA handles page_view manually on route transitions
      });
    }

    const scriptSrc = `https://www.googletagmanager.com/gtag/js?id=${measurementId}`;
    if (!document.querySelector(`script[src*="googletagmanager.com/gtag/js"]`)) {
      const script = document.createElement("script");
      script.async = true;
      script.src = scriptSrc;
      document.head.appendChild(script);
    }
  }
}

export function trackPageView(path?: string, title?: string): void {
  if (typeof window === "undefined") return;
  const currentPath =
    path ??
    (typeof window !== "undefined" && window.location
      ? window.location.pathname + window.location.search
      : "");
  const currentTitle =
    title ?? (typeof document !== "undefined" ? document.title : "");

  // 1. Contentsquare SPA pageview
  window._uxa = window._uxa || [];
  window._uxa.push(["trackPageview", currentPath]);

  // 2. GA4 SPA page_view
  if (typeof window.gtag === "function") {
    const measurementId = resolveGaMeasurementId();
    window.gtag("event", "page_view", {
      page_path: currentPath,
      page_location:
        typeof window !== "undefined" && window.location
          ? window.location.href
          : "",
      page_title: currentTitle,
      ...(measurementId ? { send_to: measurementId } : {}),
    });
  }
}

export function trackAction(
  action: string,
  params: Record<string, unknown> = {},
): void {
  if (typeof window === "undefined") return;

  // 1. Google Analytics 4 event
  if (typeof window.gtag === "function") {
    window.gtag("event", action, params);
  }

  // 2. Contentsquare custom event
  window._uxa = window._uxa || [];
  window._uxa.push(["trackCustomEvent", action, params]);
}
