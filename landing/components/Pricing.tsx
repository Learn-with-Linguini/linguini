"use client";

import Image from "next/image";
import Link from "next/link";
import { useState } from "react";
import { pricing, yearlyPerMonth, yearlySaving } from "@/data/pricing";
import { appLinks } from "@/lib/site";
import { Check } from "./icons";
import styles from "./Pricing.module.css";

type Billing = "monthly" | "yearly";

const { free, plus } = pricing;

export function Pricing() {
  const [billing, setBilling] = useState<Billing>("yearly");
  const yearly = billing === "yearly";

  return (
    <section id="pricing" className={`section ${styles.section}`} aria-labelledby="pricing-title">
      <div className="container">
        <div className="section-head section-head--center">
          <h2 id="pricing-title" className="section-title">Free to start. Plus when you’re hooked.</h2>
          <p className="section-lede">
            One photo lesson and one journal page a day are free. Upgrade when one a day stops being enough.
          </p>
        </div>

        <fieldset className={styles.toggle}>
          <legend className="visually-hidden">Billing period</legend>
          {(["monthly", "yearly"] as const).map(option => (
            <label key={option} className={styles.toggleOption}>
              <input
                type="radio"
                name="billing"
                value={option}
                checked={billing === option}
                onChange={() => setBilling(option)}
                className="visually-hidden"
              />
              {option === "monthly" ? "Monthly" : "Yearly"}
              {option === "yearly" ? <span className={styles.save}>Save {yearlySaving}%</span> : null}
            </label>
          ))}
        </fieldset>

        <div className={styles.plans}>
          <article className={`${styles.plan} ${styles.free}`} aria-labelledby="plan-free">
            <header className={styles.planHead}>
              <h3 id="plan-free" className={styles.planName}>Free</h3>
              <p className={styles.planPitch}>For a daily habit, on the house.</p>
            </header>
            <p className={styles.price}>
              <span className={styles.amount}>$0</span>
              <span className={styles.per}>forever</span>
            </p>
            <a href={appLinks.signUp} className="btn btn--teal btn--block">Start learning free</a>
            <ul className={styles.features}>
              {free.map(item => (
                <li key={item}><Check size={18} className={styles.tick} />{item}</li>
              ))}
            </ul>
          </article>

          <article className={`${styles.plan} ${styles.plus}`} aria-labelledby="plan-plus">
            <Image src="/pasta/farfalle.webp" alt="" width={360} height={281} className={styles.bow} />
            <header className={styles.planHead}>
              <h3 id="plan-plus" className={styles.planName}>Plus</h3>
              <p className={styles.planPitch}>For learners who photograph everything.</p>
            </header>
            <p className={styles.price} aria-live="polite">
              <span className={styles.amount}>${yearly ? yearlyPerMonth : pricing.plusMonthly}</span>
              <span className={styles.per}>
                per month
                <span className={styles.billed}>{yearly ? `billed $${pricing.plusYearly} yearly` : "billed monthly"}</span>
              </span>
            </p>
            <a href={`${appLinks.signUp}&plan=plus-${billing}`} className="btn btn--block">Try Plus free for {pricing.trialDays} days</a>
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
        <p className={styles.note}>Prices in US dollars. Cancel any time; your journal stays yours on the free plan.</p>
      </div>
    </section>
  );
}
