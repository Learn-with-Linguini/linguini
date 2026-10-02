import Link from "next/link";
import { competitors, competitorSources } from "@/data/competitors";
import { pricing } from "@/data/pricing";
import s from "../article.module.css";

export function CompareAppsPost() {
  return (
    <div className={s.body}>
      <p>
        People ask how Linguini compares with the apps they already know. The short answer: Duolingo and Babbel are
        courses, Speak is for speaking practice, CapWords turns photos into flashcards, and Linguini turns a photo of your
        day into a short lesson and a journal page. They solve different problems, so the right pick depends on what you
        want from the next five minutes.
      </p>

      <h2 id="at-a-glance">At a glance</h2>
      <figure className={s.fig}>
        <table className={s.table}>
          <thead>
            <tr>
              <th scope="col">App</th>
              <th scope="col">Paid plan</th>
              <th scope="col" className={s.num}>Price a year</th>
              <th scope="col">Free plan</th>
              <th scope="col">Lessons from your photos</th>
              <th scope="col">Games and a journal</th>
            </tr>
          </thead>
          <tbody>
            {competitors.map(app => (
              <tr key={app.name}>
                <th scope="row">{app.name}</th>
                <td data-label="Paid plan">{app.plan}</td>
                <td data-label="Price a year" className={s.num}>{app.label}</td>
                <td data-label="Free plan">{app.free}</td>
                <td data-label="Your photos">{app.photos ? "Yes" : "No"}</td>
                <td data-label="Games and journal">{app.journal ? "Yes" : "No"}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <figcaption>
          US list prices checked September 2026; they vary by country and promotion. CapWords turns photos into
          flashcards, without games or a journal.
        </figcaption>
      </figure>

      <h2 id="differences">How they differ</h2>
      <h3>Duolingo and Babbel: a course</h3>
      <p>
        Both give everyone a fixed path of lessons. That is their strength: if you are starting from zero, a path makes
        sure nothing gets skipped. The trade-off is that everyone learns the same words in the same order, whether or not
        those words are in your life yet.
      </p>
      <h3>Speak: conversation practice</h3>
      <p>
        Speak is built around talking. If your goal is to rehearse conversations out loud, that focus is the point, and
        it is priced like a tutor substitute.
      </p>
      <h3>CapWords: photos to flashcards</h3>
      <p>
        CapWords is the closest to us. You photograph something and get its name as a flashcard. It is cheaper than
        Linguini, and it stops there.
      </p>
      <h3>Linguini: a lesson made from your day</h3>
      <p>
        Linguini starts from a photo too, then keeps going. Every word comes with its article, gender, pronunciation and
        audio. You play with the words for five minutes: word cards, an I-Spy clue about your photo, a fill-the-gap
        sentence and one you build yourself. Then you keep the day as a journal page, using the words you just learned.
      </p>

      <h2 id="not-for">When Linguini is the wrong pick</h2>
      <ul>
        <li><strong>You want a full grammar course or exam preparation.</strong> Linguini is for everyday words and short sentences, roughly CEFR A1 to A2.</li>
        <li><strong>You want a language other than Spanish or French.</strong> We teach those two, from English. Italian is next.</li>
        <li><strong>You want many new lessons a day for free.</strong> Free is one new photo lesson a day, with unlimited replays of our curated scenes. Plus raises it to ten.</li>
      </ul>

      <h2 id="together">Using Linguini next to another app</h2>
      <p>
        Linguini is small on purpose, so it fits next to a course. Five minutes on today’s photo gives you the words
        for your own surroundings, and your course keeps the grammar moving. Free covers one photo lesson a day; Plus is
        ${pricing.plusYearly} a year, about half of what the course apps charge.
      </p>

      <h2 id="try">See for yourself</h2>
      <p>
        The <Link href="/#try">demo on our home page</Link> runs a whole lesson on a real photo, no sign-up needed. You
        can also browse the words from every demo scene in <Link href="/learn/spanish">Spanish</Link> or{" "}
        <Link href="/learn/french">French</Link>, or compare <Link href="/#pricing">our plans</Link>. How we set our own
        price is in <Link href="/blog/linguini-business-model">the Linguini business model</Link>.
      </p>

      <h2 id="sources">Sources</h2>
      <p className={s.muted} style={{ fontSize: 14 }}>
        {competitorSources.map((source, i) => (
          <span key={source.href}>
            {i > 0 ? " · " : null}
            <a href={source.href}>{source.label}</a>
          </span>
        ))}
        . Linguini’s own prices are on <Link href="/#pricing">our pricing section</Link>.
      </p>
    </div>
  );
}
