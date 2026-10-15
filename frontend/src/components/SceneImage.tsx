import { useEffect, useState } from "react";
import type { SceneSummary } from "../data/types";
import { imageLoadingAttrs } from "../lib/imageLoading";
import { getAccessToken } from "../lib/supabase.ts";

type Props = {
  scene: Pick<SceneSummary, "imageUrl" | "title">;
  className?: string;
  lazy?: boolean;
};

/** Resolve a possibly protected media URL to a renderable URL (blob for /api/v1/media/). */
export function useResolvedImageUrl(imageUrl: string | null | undefined) {
  const [failedUrl, setFailedUrl] = useState<string | null>(null);
  const [resolvedUrl, setResolvedUrl] = useState<string | null>(imageUrl ?? null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setFailedUrl(null);
    if (!imageUrl || !imageUrl.includes("/api/v1/media/")) {
      setResolvedUrl(imageUrl ?? null);
      setLoading(false);
      return;
    }

    let cancelled = false;
    let objectUrl: string | null = null;
    setResolvedUrl(null);
    setLoading(true);
    void (async () => {
      try {
        const token = await getAccessToken();
        const response = await fetch(imageUrl, {
          headers: token ? { Authorization: `Bearer ${token}` } : undefined,
        });
        if (!response.ok) throw new Error("Unable to load image.");
        objectUrl = URL.createObjectURL(await response.blob());
        if (cancelled) {
          URL.revokeObjectURL(objectUrl);
          return;
        }
        setResolvedUrl(objectUrl);
      } catch {
        if (!cancelled) setFailedUrl(imageUrl);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [imageUrl]);

  return { resolvedUrl, loading, failed: imageUrl != null && failedUrl === imageUrl };
}

export function SceneImage({ scene, className, lazy }: Props) {
  const { resolvedUrl, loading, failed } = useResolvedImageUrl(scene.imageUrl);
  const [failedUrl, setFailedUrl] = useState<string | null>(null);
  const isProtectedMediaUrl = Boolean(scene.imageUrl?.includes("/api/v1/media/"));

  if (!scene.imageUrl || failed || failedUrl === scene.imageUrl) {
    return (
      <span
        className={`scene-image scene-image--error${className ? ` ${className}` : ""}`}
        role="img"
        aria-label={`Image unavailable: ${scene.title}`}
      >
        Image unavailable
      </span>
    );
  }
  if (isProtectedMediaUrl && (loading || !resolvedUrl)) {
    return (
      <span className={`scene-image scene-image--loading${className ? ` ${className}` : ""}`} role="status">
        <span className="scene-image__loading-label">Preparing photo…</span>
      </span>
    );
  }
  return (
    <img
      src={resolvedUrl ?? scene.imageUrl}
      alt={scene.title}
      className={`scene-image${className ? ` ${className}` : ""}`}
      decoding="async"
      {...imageLoadingAttrs(lazy)}
      onError={() => setFailedUrl(scene.imageUrl)}
    />
  );
}
