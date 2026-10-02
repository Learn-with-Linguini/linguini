import { faq } from "@/data/faq";
import type { FaqItem } from "./JsonLd";
import { Plus } from "./icons";
import styles from "./Faq.module.css";

export function Faq({ items = faq, title = "Questions, answered" }: { items?: FaqItem[]; title?: string }) {
  return (
    <section id="faq" className={`section ${styles.section}`} aria-labelledby="faq-title">
      <div className={`container ${styles.grid}`}>
        <div className={styles.intro}>
          <h2 id="faq-title" className="section-title">{title}</h2>
          <p className="section-lede">
            Something we missed? Ask the team on{" "}
            <a href="https://github.com/CS3216-A3-G7/linguini" className={styles.mail}>GitHub</a>.
          </p>
        </div>
        <div className={styles.list}>
          {items.map(item => (
            <details key={item.q} className={styles.item}>
              <summary className={styles.question}>
                <h3>{item.q}</h3>
                <span className={styles.icon} aria-hidden="true"><Plus size={20} /></span>
              </summary>
              <p className={styles.answer}>{item.a}</p>
            </details>
          ))}
        </div>
      </div>
    </section>
  );
}
