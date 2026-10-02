import Image from "next/image";
import type { Post } from "@/data/posts";
import { scenes } from "@/data/scenes";
import { CoverVideo } from "./CoverVideo";
import styles from "./PostCover.module.css";

const COVER_RATIO = 16 / 10;

/** Map a marker (percent of the source photo) into a 16:10 object-fit: cover frame. */
function coverPosition(x: number, y: number, width: number, height: number) {
  const ratio = width / height;
  if (ratio > COVER_RATIO) {
    const visible = COVER_RATIO / ratio;
    return { left: ((x / 100 - (1 - visible) / 2) / visible) * 100, top: y };
  }
  const visible = ratio / COVER_RATIO;
  return { left: x, top: ((y / 100 - (1 - visible) / 2) / visible) * 100 };
}

/** Card media: a looping video, a still image, or a real demo scene labelled with its words. */
export function PostCover({ post, sizes = "(min-width: 900px) 380px, 100vw", priority = false }: {
  post: Post; sizes?: string; priority?: boolean;
}) {
  const cover = post.cover;

  if (cover.kind === "video") {
    return (
      <div className={styles.cover}>
        <CoverVideo src={cover.src} poster={cover.poster} className={styles.media} label={`${post.title}: animated overview`} />
      </div>
    );
  }

  if (cover.kind === "image") {
    return (
      <div className={styles.cover}>
        <Image src={cover.src} alt={cover.alt} fill sizes={sizes} priority={priority} className={styles.media} />
      </div>
    );
  }

  const scene = scenes.find(item => item.id === cover.scene);
  if (!scene) return <div className={styles.cover} />;

  return (
    <div className={styles.cover}>
      <Image src={scene.photo} alt={scene.alt} fill sizes={sizes} priority={priority} className={styles.media} />
      {scene.words
        .filter(word => cover.words.includes(word.id))
        .map(word => {
          const { left, top } = coverPosition(word.x, word.y, scene.width, scene.height);
          if (left < 4 || left > 78 || top < 8 || top > 92) return null;
          return (
            <span key={word.id} className={styles.chip} style={{ left: `${left}%`, top: `${top}%` }}>
              {word.es.word}
            </span>
          );
        })}
    </div>
  );
}
