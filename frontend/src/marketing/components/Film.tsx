import { SoundVideo } from "./SoundVideo";
import styles from "./Film.module.css";

/** The launch film as a muted loop between the hero and the pitch. */
export function Film() {
  return (
    <div className={`container ${styles.wrap}`}>
      <SoundVideo
        poster="/film/poster.jpg"
        label="Linguini launch film: everyday moments, each labelled with its word in Spanish and French"
        sources={[
          { src: "/film/linguini-film-1080p.mp4", media: "(min-width: 900px)" },
          { src: "/film/linguini-film-720p.mp4" },
        ]}
      />
    </div>
  );
}
