export interface UserAttribution {
  utmSource?: string;
  utmMedium?: string;
  utmCampaign?: string;
  utmContent?: string;
  utmTerm?: string;
}

export const ATTRIBUTION_STORAGE_KEY = "linguini_attribution";

export function extractAttributionFromQuery(search: string): UserAttribution | null {
  if (!search) return null;
  const params = new URLSearchParams(search);
  const utmSource = params.get("utm_source")?.trim();
  const utmMedium = params.get("utm_medium")?.trim();
  const utmCampaign = params.get("utm_campaign")?.trim();
  const utmContent = params.get("utm_content")?.trim();
  const utmTerm = params.get("utm_term")?.trim();

  if (!utmSource && !utmMedium && !utmCampaign && !utmContent && !utmTerm) {
    return null;
  }

  const attribution: UserAttribution = {};
  if (utmSource) attribution.utmSource = utmSource.slice(0, 100);
  if (utmMedium) attribution.utmMedium = utmMedium.slice(0, 100);
  if (utmCampaign) attribution.utmCampaign = utmCampaign.slice(0, 100);
  if (utmContent) attribution.utmContent = utmContent.slice(0, 100);
  if (utmTerm) attribution.utmTerm = utmTerm.slice(0, 100);

  return attribution;
}

export function getStoredAttribution(): UserAttribution | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(ATTRIBUTION_STORAGE_KEY);
    return raw ? JSON.parse(raw) as UserAttribution : null;
  } catch {
    return null;
  }
}

export function captureAttribution(search?: string): UserAttribution | null {
  if (typeof window === "undefined") return null;
  const queryString = search ?? window.location.search;
  const extracted = extractAttributionFromQuery(queryString);
  if (!extracted) return getStoredAttribution();

  try {
    const existing = getStoredAttribution();
    // First touch attribution: keep existing values if set, fill with newly extracted values
    const merged: UserAttribution = {
      ...extracted,
      ...existing,
    };
    window.localStorage.setItem(ATTRIBUTION_STORAGE_KEY, JSON.stringify(merged));
    return merged;
  } catch {
    return extracted;
  }
}

export function clearStoredAttribution(): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.removeItem(ATTRIBUTION_STORAGE_KEY);
  } catch {
    // Ignore storage exceptions in private modes
  }
}
