import { useEffect, useState } from "react";
import type { SceneSummary } from "../data/types";
import { protectedMediaPath, requestBlob } from "../lib/api";
import { imageLoadingAttrs } from "../lib/imageLoading";

type Props = {
  scene: Pick<SceneSummary, "imageUrl" | "title">;
  className?: string;
  lazy?: boolean;
};

/** Resolve a possibly protected media URL to a renderable URL (blob for /api/v1/media/). */
export function useResolvedImageUrl(imageUrl: string | null | undefined) {
  const [resolved, setResolved] = useState<{ source: string; objectUrl: string } | null>(null);
  const [failedUrl, setFailedUrl] = useState<string | null>(null);

  useEffect(() => {
    setFailedUrl(null);
    const source = imageUrl;
    const path = protectedMediaPath(source);
    if (!source || !path) return;

    const controller = new AbortController();
    let objectUrl: string | null = null;
    void requestBlob(path, controller.signal).then(blob => {
      objectUrl = URL.createObjectURL(blob);
      if (controller.signal.aborted) {
        if (objectUrl) {
          URL.revokeObjectURL(objectUrl);
        }
        return;
      }
      setResolved({ source, objectUrl });
    }).catch(() => {
      if (!controller.signal.aborted) setFailedUrl(source);
    });
    return () => {
      controller.abort();
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [imageUrl]);

  const isProtected = protectedMediaPath(imageUrl) !== null;
  const failed = imageUrl != null && failedUrl === imageUrl;
  const resolvedUrl = isProtected
    ? resolved && resolved.source === imageUrl ? resolved.objectUrl : null
    : imageUrl ?? null;
  return { resolvedUrl, loading: isProtected && resolvedUrl === null && !failed, failed };
}

export function SceneImage({ scene, className, lazy }: Props) {
  const { resolvedUrl, failed } = useResolvedImageUrl(scene.imageUrl);
  const [failedUrl, setFailedUrl] = useState<string | null>(null);
  const isProtectedMediaUrl = protectedMediaPath(scene.imageUrl) !== null;

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
  if (isProtectedMediaUrl && !resolvedUrl) {
    return (
      <span className={`scene-image scene-image--loading${className ? ` ${className}` : ""}`} role="status">
        <span className="scene-image__loading-label">Preparing photo…</span>
      </span>
    );
  }
  return (
    <img
      src={resolvedUrl ?? undefined}
      alt={scene.title}
      className={`scene-image${className ? ` ${className}` : ""}`}
      decoding="async"
      {...imageLoadingAttrs(lazy)}
      onError={() => setFailedUrl(scene.imageUrl)}
    />
  );
}
