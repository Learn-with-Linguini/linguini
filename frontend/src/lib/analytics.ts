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

function analyticsPath(path?: string): string {
  try {
    const url = new URL(path ?? window.location.pathname, window.location.origin);
    return url.protocol === "https:" || url.protocol === "http:" ? url.pathname : "/";
  } catch {
    return "/";
  }
}

function analyticsPageFields(path = analyticsPath()) {
  let referrer = "";
  if (typeof document !== "undefined" && document.referrer) {
    try {
      const url = new URL(document.referrer);
      if (url.protocol === "https:" || url.protocol === "http:") {
        referrer = url.origin + url.pathname;
      }
    } catch { /* Ignore malformed referrers. */ }
  }
  return {
    page_path: path,
    page_location: window.location.origin + path,
    page_referrer: referrer,
  };
}

function setContentsquareUrl(path: string): void {
  window._uxa = window._uxa || [];
  // Queue these before loading the tag, which sends its own initial pageview.
  // Overrides persist through renewals until the next full page load.
  window._uxa.push(["setPath", path], ["setQuery", ""], ["referrer:removeQueryString"]);
}

export function initAnalytics(): void {
  if (typeof window === "undefined") return;

  const page = analyticsPageFields();
  setContentsquareUrl(page.page_path);

  if (typeof document === "undefined") return;

  if (!document.querySelector('script[src*="t.contentsquare.net/uxa/"]')) {
    const script = document.createElement("script");
    script.async = true;
    script.referrerPolicy = "no-referrer";
    script.src = "https://t.contentsquare.net/uxa/6a01544c67dfc.js";
    document.head.appendChild(script);
  }

  // Setup GA4 gtag
  const measurementId = resolveGaMeasurementId();
  if (measurementId) {
    window.dataLayer = window.dataLayer || [];
    if (!window.gtag) {
      window.gtag = function () {
        window.dataLayer?.push(arguments);
      };
      window.gtag("js", new Date());
    }
    // Set safe defaults for automatic events as well as our explicit events.
    window.gtag("set", page);
    window.gtag("config", measurementId, {
      ...page,
      send_page_view: false, // SPA handles page_view manually on route transitions
    });

    const scriptSrc = `https://www.googletagmanager.com/gtag/js?id=${measurementId}`;
    if (!document.querySelector(`script[src*="googletagmanager.com/gtag/js"]`)) {
      const script = document.createElement("script");
      script.async = true;
      script.referrerPolicy = "no-referrer";
      script.src = scriptSrc;
      document.head.appendChild(script);
    }
  }
}

export function trackPageView(path?: string, title?: string): void {
  if (typeof window === "undefined") return;
  const currentPath = analyticsPath(path);
  const page = analyticsPageFields(currentPath);
  const currentTitle =
    title ?? (typeof document !== "undefined" ? document.title : "");

  // 1. Contentsquare SPA pageview
  setContentsquareUrl(currentPath);
  window._uxa!.push(["trackPageview", currentPath]);

  // 2. GA4 SPA page_view
  if (typeof window.gtag === "function") {
    const measurementId = resolveGaMeasurementId();
    window.gtag("set", page);
    window.gtag("event", "page_view", {
      ...page,
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

  // Reserved URL dimensions cannot be replaced by raw URLs from a caller.
  const page = analyticsPageFields();
  const eventParams = { ...params, ...page };

  // 1. Google Analytics 4 event
  if (typeof window.gtag === "function") {
    window.gtag("set", page);
    window.gtag("event", action, eventParams);
  }

  // 2. Contentsquare custom event
  setContentsquareUrl(page.page_path);
  window._uxa!.push(["trackCustomEvent", action, eventParams]);
}
