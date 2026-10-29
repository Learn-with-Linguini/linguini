import Image from "../../components/Image";
import Link from "../../components/Link";
import { useParams } from "react-router-dom";
import { Faq } from "../../components/Faq";
import { FinalCta } from "../../components/FinalCta";
import { ArrowRight } from "../../components/icons";
import { serializeJsonLd } from "../../components/JsonLd";
import { PhotoMarkers } from "../../components/product/PhotoMarkers";
import { SiteFooter } from "../../components/SiteFooter";
import { SiteHeader } from "../../components/SiteHeader";
import { getLanguagePage } from "../../data/languages";
import { getScene, scenes } from "../../data/scenes";
import { steps } from "../../data/steps";
import { PageMeta } from "../../lib/seo";
import { appLinks, site } from "../../lib/site";
import NotFoundPage from "../NotFoundPage";
import styles from "./learn.module.css";

/** Step 4 of the worked session — the landing `steps` list only holds the first three. */
const journalStep = {
  title: "Keep the day in your journal",
  body: "Write a few lines with your new words. Linguini highlights the ones you used, files them in your vocabulary bank and adds Basil, and your progress page grows another farfalle on your streak.",
};

export default function LearnLanguagePage() {
  const { language = "" } = useParams();
  const page = getLanguagePage(language);
  const scene = page && getScene(page.sceneId);
  if (!page || !scene) return <NotFoundPage />;
  const { lang, name } = page;
  const wordCount = scenes.reduce((sum, item) => sum + item.words.length, 0);
  const url = `${site.url}/learn/${page.slug}`;

  const jsonLd = {
    "@context": "https://schema.org",
    "@graph": [
      {
        "@type": "BreadcrumbList",
        itemListElement: [
          { "@type": "ListItem", position: 1, name: site.name, item: `${site.url}/` },
          { "@type": "ListItem", position: 2, name: `Learn ${name}`, item: url },
        ],
      },
      {
        "@type": "DefinedTermSet",
        "@id": `${url}#words`,
        name: `${name} words from Linguini photo lessons`,
        inLanguage: lang,
        hasDefinedTerm: scenes.flatMap(item =>
          item.words.map(word => ({
            "@type": "DefinedTerm",
            name: word[lang].word,
            description: `${word.en} (${word[lang].gender})`,
            inLanguage: lang,
          })),
        ),
      },
      {
        "@type": "FAQPage",
        "@id": `${url}#faq`,
        mainEntity: page.faq.map(({ q, a }) => ({ "@type": "Question", name: q, acceptedAnswer: { "@type": "Answer", text: a } })),
      },
    ],
  };

  return (
    <>
      <PageMeta
        title={`Learn ${name} with photos`}
        description={page.description}
        path={`/learn/${page.slug}`}
        image={{
          url: `/og/learn-${page.slug}.png`,
          alt: `A Linguini journal page: a real photo with its ${page.name} words`,
        }}
      />
      <a href="#main" className="skip-link">Skip to content</a>
      <SiteHeader />
      <main id="main">
        <section className={`container ${styles.intro}`} aria-labelledby="learn-title">
          <div className={styles.copy}>
            <h1 id="learn-title" className={styles.title}>
              Learn {name} from the photos <span className={styles.accent}>you take.</span>
            </h1>
            <p className={styles.lede}>{page.lede}</p>
            <div className={styles.ctas}>
              <a href={appLinks.signUp} className="btn">Start learning free</a>
              <Link href={`/demo?photo=${scene.id}&lang=${lang}`} className="btn btn--teal">
                Try a lesson now <ArrowRight size={20} />
              </Link>
            </div>
            <p className={styles.aside}>
              Learning {page.other.name} instead? <Link href={`/learn/${page.other.slug}`}>Learn {page.other.name} with photos</Link>
            </p>
          </div>
          <figure className={styles.print}>
            <span className={styles.tape} aria-hidden="true" />
            <PhotoMarkers scene={scene} lang={lang} labels priority sizes="(min-width: 960px) 520px, 92vw" className={styles.photo} />
            <figcaption className={styles.caption}>{scene.title} · {scene.place}</figcaption>
          </figure>
        </section>

        <section className={`section ${styles.words}`} aria-labelledby="words-title">
          <div className="container">
            <div className="section-head">
              <h2 id="words-title" className="section-title">{wordCount} {name} words from {scenes.length} photos</h2>
              <p className="section-lede">
                Every lesson starts like this. Linguini finds the things in a photo and teaches each one with its article,
                gender and pronunciation. These are the words in our demo scenes; yours will come from your own day.
              </p>
            </div>
            <ul className={styles.scenes}>
              {scenes.map(item => (
                <li key={item.id} className={styles.scene}>
                  <PhotoMarkers scene={item} lang={lang} sizes="(min-width: 900px) 560px, 92vw" className={styles.scenePhoto} />
                  <div className={styles.sceneText}>
                    <h3 className={styles.sceneTitle}>{item.title}</h3>
                    <table className={styles.table}>
                      <caption className="visually-hidden">{name} words in “{item.title}”</caption>
                      <thead>
                        <tr>
                          <th scope="col"><span className="visually-hidden">Marker</span></th>
                          <th scope="col">{name}</th>
                          <th scope="col">English</th>
                          <th scope="col">Sounds like</th>
                        </tr>
                      </thead>
                      <tbody>
                        {item.words.map((word, index) => (
                          <tr key={word.id}>
                            <td className={styles.num}>{index + 1}</td>
                            <th scope="row" lang={lang}>
                              {word[lang].word}
                              {word[lang].gender && word[lang].gender !== "none" ? (
                                <small className={styles.gender}>{word[lang].gender}</small>
                              ) : null}
                            </th>
                            <td>{word.en}</td>
                            <td className={styles.ipa}>/{word[lang].ipa}/</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    <Link href={`/demo?photo=${item.id}&lang=${lang}`} className={`btn-quiet ${styles.play}`}>
                      Play this scene <ArrowRight size={16} />
                    </Link>
                  </div>
                </li>
              ))}
            </ul>
            <p className={styles.footnote}>
              Pronunciation is a broad IPA transcription of the noun without its article
              ({lang === "es" ? "Castilian Spanish" : lang === "fr" ? "standard Parisian French" : lang === "de" ? "Standard German" : "Standard Korean"}). In the app every word also has audio.
            </p>
          </div>
        </section>

        <section className={`section ${styles.session}`} aria-labelledby="session-title">
          <div className="container">
            <div className="section-head">
              <h2 id="session-title" className="section-title">Five minutes, one photo</h2>
              <p className="section-lede">Here is a whole {name} session built from the photo at the top of this page.</p>
            </div>
            <ol className={styles.steps}>
              <li className={styles.step}>
                <h3>{steps[0].title}</h3>
                <p>{steps[0].body}</p>
                <div className={styles.thumb}>
                  <Image src={scene.photo} alt={scene.alt} fill sizes="(min-width: 900px) 280px, 90vw" className={styles.thumbImg} />
                </div>
              </li>
              <li className={styles.step}>
                <h3>{steps[1].title}</h3>
                <p>{steps[1].body}</p>
                <ul className={styles.chips}>
                  {scene.words.map(word => (
                    <li key={word.id} lang={lang}>{word[lang].word}</li>
                  ))}
                </ul>
              </li>
              <li className={styles.step}>
                <h3>{steps[2].title}</h3>
                <p>{steps[2].body}</p>
                <dl className={styles.example}>
                  <div>
                    <dt>I-Spy</dt>
                    <dd><span lang={lang}>{scene.ispy[lang].clue}</span> <small>{scene.ispy[lang].clueEn}</small></dd>
                  </div>
                  <div>
                    <dt>Fill the gap</dt>
                    <dd><span lang={lang}>{scene.blank[lang].sentence.replace("___", scene.blank[lang].answer)}</span> <small>{scene.blank[lang].en}</small></dd>
                  </div>
                  <div>
                    <dt>Build it</dt>
                    <dd><span lang={lang}>{scene.build[lang].tokens.join(" ")}</span> <small>{scene.build[lang].en}</small></dd>
                  </div>
                </dl>
              </li>
              <li className={styles.step}>
                <h3>{journalStep.title}</h3>
                <p>{journalStep.body}</p>
                <blockquote className={styles.journal} lang={lang}>
                  <b>{scene.journal[lang].title}</b>
                  <p>{scene.journal[lang].body}</p>
                </blockquote>
              </li>
            </ol>
          </div>
        </section>

        <Faq items={page.faq} title={`Learning ${name} with Linguini`} />
        <FinalCta
          title={`Your first ${name} lesson is one photo away.`}
          lede={`Free every day. Sign up in under a minute, pick ${name}, and turn today into your first page.`}
          shareUrl={url}
        />
      </main>
      <SiteFooter />
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: serializeJsonLd(jsonLd) }} />
    </>
  );
}
