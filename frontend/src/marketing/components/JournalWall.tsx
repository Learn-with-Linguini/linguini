import { JournalCard } from "./product/JournalCard";
import { Reveal } from "./Reveal";
import { ArrowLeft, ArrowRight, Book } from "./icons";
import styles from "./JournalWall.module.css";

const entries = [
  {
    photos: [
      { src: "/photos/golden-gate-bridge.jpg", alt: "The Golden Gate Bridge over the bay" },
      { src: "/photos/hillside-street.jpg", alt: "A flower-lined hillside street" },
      { src: "/photos/sunlit-promenade.jpg", alt: "A sunlit square with street lamps" },
      { src: "/photos/lake-shore.jpg", alt: "A lake shore" },
      { src: "/photos/summer-meadow.jpg", alt: "A meadow" },
    ],
    title: "Un día de niebla y sol",
    body: "Por la mañana crucé el puente rojo a pie. El agua estaba fría y el cielo, gris. Por la tarde subí por una calle llena de flores y vi un coche rojo aparcado.",
    words: ["puente", "agua", "cielo", "calle", "flores", "coche"],
    date: "Saturday, 19 Sep",
    tilt: -1.5,
  },
  {
    photos: [{ src: "/photos/desk-flatlay.jpg", alt: "A notebook, phone and glasses on a white desk" }],
    title: "Mi escritorio",
    body: "Hoy estudié en casa. En la mesa hay un cuaderno, un lápiz amarillo y mis gafas. El móvil está apagado, ¡por fin!",
    words: ["mesa", "cuaderno", "lápiz", "gafas", "móvil"],
    date: "Monday, 21 Sep",
    tilt: 1.2,
  },
  {
    photos: [
      { src: "/photos/paris-rooftops.jpg", alt: "Paris rooftops at dusk" },
      { src: "/photos/alpine-castle.jpg", alt: "A castle above a forest" },
      { src: "/photos/mountain-chalet.jpg", alt: "A mountain chalet" },
    ],
    title: "Fotos de mis viajes",
    body: "Miré fotos antiguas: el río de noche, las luces de la ciudad y un castillo blanco en el bosque. Quiero volver en primavera.",
    words: ["río", "luces", "ciudad", "castillo", "bosque"],
    date: "Wednesday, 23 Sep",
    tilt: -0.8,
  },
  {
    photos: [
      { src: "/photos/summer-meadow.jpg", alt: "A meadow full of dandelions" },
      { src: "/photos/mountain-peaks.jpg", alt: "Snowy mountain peaks" },
    ],
    title: "Picnic en el campo",
    body: "Comimos en la hierba, entre flores blancas. Hacía sol y había pocas nubes. A lo lejos se veían las montañas.",
    words: ["hierba", "flores", "sol", "nubes", "montañas"],
    date: "Thursday, 24 Sep",
    tilt: 1.6,
  },
];

export function JournalWall() {
  return (
    <section id="journal" className={`section ${styles.section}`} aria-labelledby="journal-title">
      <div className={`container ${styles.grid}`}>
        <div className={styles.copy}>
          <h2 id="journal-title" className="section-title">A diary that teaches you back</h2>
          <p className="section-lede">
            Every session ends with a page. Write a few lines in your new language, add the photos from your day, and watch
            the month fill up with places you can now describe.
          </p>
          <ul className={styles.points}>
            <li><b>Words you used are highlighted,</b> and they count as mastered.</li>
            <li><b>Photos stay with the entry,</b> so the memory and the vocabulary travel together.</li>
            <li><b>One month at a time,</b> so you can look back and see how far you’ve come.</li>
          </ul>
        </div>

        <div className={styles.book}>
          <div className={styles.month}>
            <span className={styles.monthIcon} aria-hidden="true"><Book size={20} /></span>
            <p className={styles.monthName}>September 2026</p>
            <span className={styles.chevrons} aria-hidden="true">
              <ArrowLeft size={18} />
              <ArrowRight size={18} />
            </span>
          </div>
          <div className={styles.entries}>
            {entries.map((entry, index) => (
              <Reveal key={entry.title} delay={index * 90} className={styles.entry} style={{ "--tilt": `${entry.tilt}deg` } as React.CSSProperties}>
                <JournalCard
                  photos={entry.photos}
                  title={entry.title}
                  body={entry.body}
                  date={entry.date}
                  lang="es"
                  highlight={entry.words}
                  headingLevel="h3"
                />
              </Reveal>
            ))}
          </div>
          <p className={styles.caption}>A sample month from a Spanish learner’s journal.</p>
        </div>
      </div>
    </section>
  );
}
