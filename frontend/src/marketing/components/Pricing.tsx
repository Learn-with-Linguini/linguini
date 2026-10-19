import Link from "./Link";
import { pricing } from "../data/pricing";
import { appLinks } from "../lib/site";
import { trackAction } from "../../lib/analytics";
import { Check } from "./icons";
import styles from "./Pricing.module.css";

const { beta, free, plus } = pricing;

export function Pricing() {
  return (
    <section id="pricing" className={`section ${styles.section}`} aria-labelledby="pricing-title">
      <div className="container">
        <div className="section-head section-head--center">
          <h2 id="pricing-title" className="section-title">Beta now. Free and Plus later.</h2>
          <p className="section-lede">
            Everyone who joins now gets the Beta tier with unlimited photo lessons every day. Free and Plus are planned for after the public beta.
          </p>
        </div>

        <div className={styles.plans}>
          <article className={`${styles.plan} ${styles.beta}`} aria-labelledby="plan-beta">
            <header className={styles.planHead}>
              <span className={styles.betaBadge}>Current access</span>
              <h3 id="plan-beta" className={styles.planName}>Beta</h3>
              <p className={styles.planPitch}>Explore Linguini freely and help shape what comes next.</p>
            </header>
            <p className={styles.price}>
              <span className={styles.amount}>$0</span>
              <span className={styles.per}>during beta</span>
            </p>
            <a
              href={appLinks.signUp}
              className="btn btn--block"
              onClick={() => trackAction("pricing_cta_clicked", { tier: "beta" })}
            >
              Join the public beta
            </a>
            <ul className={styles.features}>
              {beta.map(item => (
                <li key={item}><Check size={18} className={styles.tick} />{item}</li>
              ))}
            </ul>
          </article>

          <article className={`${styles.plan} ${styles.free} ${styles.future}`} aria-labelledby="plan-free">
            <header className={styles.planHead}>
              <span className={styles.futureBadge}>After beta</span>
              <h3 id="plan-free" className={styles.planName}>Free</h3>
              <p className={styles.planPitch}>For building a steady daily habit.<br/><br/></p>
            </header>
            <p className={styles.price}>
              <span className={styles.amount}>$0</span>
              <span className={styles.per}>forever</span>
            </p>
            <p className={styles.futureAvailability}>Planned for after the public beta</p>
            <ul className={styles.features}>
              {free.map(item => (
                <li key={item}><Check size={18} className={styles.tick} />{item}</li>
              ))}
            </ul>
          </article>

          <article className={`${styles.plan} ${styles.plus} ${styles.future}`} aria-labelledby="plan-plus">
            <header className={styles.planHead}>
              <span className={styles.futureBadge}>After beta</span>
              <h3 id="plan-plus" className={styles.planName}>Plus</h3>
              <p className={styles.planPitch}>For learners who photograph everything.</p>
            </header>
            <p className={styles.price}>
              <span className={styles.amount}>${pricing.plusMonthly}</span>
              <span className={styles.per}>per month</span>
            </p>
            <p className={styles.futureAvailability}>Planned for after the public beta</p>
            <ul className={styles.features}>
              {plus.map(item => (
                <li key={item}><Check size={18} className={styles.tick} />{item}</li>
              ))}
            </ul>
          </article>

        </div>

        <p className={styles.founding}>
          <strong>Founding Plus:</strong> our first {pricing.foundingSeats} members lock in ${pricing.foundingYearly} a year and get early access to competitive
          I-Spy. <Link href="/blog/linguini-business-model">How we priced Linguini</Link>
        </p>
        <p className={styles.note}>Beta is the only tier currently available and does not require a payment card. Free, Plus and Founding Plus details are planned and may change before launch.</p>
      </div>
    </section>
  );
}
