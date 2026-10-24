import Image from "./Image";
import { Reveal } from "./Reveal";
import styles from "./Why.module.css";

const generic = ["la manzana", "el niño", "el coche rojo", "la biblioteca", "el elefante", "la abuela"];

const tags = [
  { es: "la ola", en: "the wave", x: 58, y: 84 },
  { es: "el lago", en: "the lake", x: 30, y: 62 },
  { es: "la colina", en: "the hill", x: 16, y: 44 },
  { es: "la nube", en: "the cloud", x: 64, y: 30 },
];

export function Why() {
  return (
    <section className={`section ${styles.section}`} aria-labelledby="why-title">
      <div className={`container ${styles.grid}`}>
        <Reveal className={styles.copy}>
          <h2 id="why-title" className="section-title">Word lists don’t know where you live.</h2>
          <p className={styles.body}>
            While traditional language apps teach everyone the same vocabulary, Linguini turns your own surroundings into your classroom, making language learning personal, practical, and relevant to your everyday life.
          </p>
        </Reveal>

        <div className={styles.compare}>
          <Reveal className={styles.list} delay={80}>
            <p className={styles.listHead}>Lesson 1: vocabulary</p>
            <ul lang="es">
              {generic.map(word => (
                <li key={word}>{word}</li>
              ))}
            </ul>
            <p className={styles.listFoot}>Someone else’s words</p>
          </Reveal>

          <Reveal className={styles.photoCard} delay={200}>
            <div className={styles.photo}>
              <Image
                src="/photos/lake-shore.jpg"
                alt="Turquoise lake shore with breaking waves, low hills and white clouds"
                fill
                sizes="(max-width: 900px) 90vw, 520px"
                className={styles.img}
              />
              {tags.map((tag, index) => (
                <span key={tag.es} className={styles.tag} style={{ left: `${tag.x}%`, top: `${tag.y}%`, "--i": index } as React.CSSProperties}>
                  <b lang="es">{tag.es}</b>
                  <span>{tag.en}</span>
                </span>
              ))}
            </div>
            <p className={styles.photoFoot}>Your Saturday, in Spanish</p>
          </Reveal>
        </div>
      </div>
    </section>
  );
}
