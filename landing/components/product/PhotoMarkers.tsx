import Image from "next/image";
import type { Lang, Scene } from "@/data/types";
import styles from "./product.module.css";

type PhotoMarkersProps = {
  scene: Scene;
  lang?: Lang;
  /** Show the target-language label beside each marker. */
  labels?: boolean;
  activeId?: string | null;
  hiddenIds?: string[];
  sizes?: string;
  priority?: boolean;
  className?: string;
  style?: React.CSSProperties;
  children?: React.ReactNode;
};

/** A real scene photo with numbered vocabulary markers laid over it. */
export function PhotoMarkers({
  scene,
  lang = "es",
  labels = false,
  activeId = null,
  hiddenIds = [],
  sizes = "(max-width: 900px) 100vw, 640px",
  priority = false,
  className = "",
  style,
  children,
}: PhotoMarkersProps) {
  return (
    <div className={`${styles.photoFrame} ${className}`} style={{ aspectRatio: `${scene.width} / ${scene.height}`, ...style }}>
      <Image src={scene.photo} alt={scene.alt} fill sizes={sizes} priority={priority} className={styles.photoImg} />
      {scene.words.map((word, index) =>
        hiddenIds.includes(word.id) ? null : (
          <span
            key={word.id}
            className={`${styles.marker} ${activeId === word.id ? styles.markerActive : ""}`}
            style={{ left: `${word.x}%`, top: `${word.y}%`, "--i": index } as React.CSSProperties}
          >
            <span className={styles.markerDot}>{index + 1}</span>
            {labels ? (
              <span className={`${styles.markerLabel} ${word.x > 62 ? styles.markerLabelLeft : ""}`} lang={lang}>
                {word[lang].word}
              </span>
            ) : null}
          </span>
        ),
      )}
      {children}
    </div>
  );
}
