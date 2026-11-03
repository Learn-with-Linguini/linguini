import { faq } from "./faq.js";
import type { Lang } from "./types.js";

export type LanguagePage = {
  /** URL segment under /learn. */
  slug: string;
  lang: Lang;
  name: string;
  /** Scene shown in the intro and used for the worked example. */
  sceneId: string;
  description: string;
  lede: string;
  other: { slug: string; name: string };
  faq: { q: string; a: string }[];
};

const faqAnswer = (q: string) => faq.find(item => item.q === q)?.a ?? "";

function languageFaq(name: string, other: string, examples: string): LanguagePage["faq"] {
  return [
    {
      q: `Can I learn ${name} for free with Linguini?`,
      a: "Yes. Everyone who signs up during the public beta gets the Beta tier with unlimited photo lessons every day, plus ready-made scenes, vocabulary games, progress and journals. No payment card is required.",
    },
    {
      q: `What level of ${name} is Linguini for?`,
      a: faqAnswer("What level is Linguini for?"),
    },
    {
      q: `Which ${name} words will I learn?`,
      a: name === "Korean"
        ? `The names of the things in your photos in Hangul (${examples}), with pronunciation and audio, plus everyday adjectives and short sentences. Korean has no grammatical gender or articles like Spanish, French or German.`
        : `The names of the things in your photos, with their articles and grammatical gender (${examples}), plus the everyday adjectives and short sentences you need to talk about them.`,
    },
    {
      q: "Do I have to use my own photos?",
      a: faqAnswer("Do I have to use my own photos?"),
    },
    {
      q: `Does Linguini teach ${other} too?`,
      a: "Yes. The Linguini app teaches Spanish, French, German and beginner Korean, from English.",
    },
  ];
}

export const languagePages: LanguagePage[] = [
  {
    slug: "spanish",
    lang: "es",
    name: "Spanish",
    sceneId: "hillside-street",
    description:
      "Learn Spanish vocabulary from your photos, with articles, pronunciation and games. Try a photo lesson free, with unlimited lessons during the public beta.",
    lede: "Photograph the café you’re sitting in or the street you walked down. Linguini finds the things in the picture and teaches you their Spanish names, with the article, pronunciation and audio, then turns them into a five-minute game and a journal page.",
    other: { slug: "french", name: "French" },
    faq: languageFaq("Spanish", "French", "el coche, la calle"),
  },
  {
    slug: "french",
    lang: "fr",
    name: "French",
    sceneId: "sunlit-promenade",
    description:
      "Learn French vocabulary from your photos, with articles, pronunciation and games. Try a photo lesson free, with unlimited lessons during the public beta.",
    lede: "Photograph the promenade on your evening walk or the view from your window. Linguini finds the things in the picture and teaches you their French names, with the article, pronunciation and audio, then turns them into a five-minute game and a journal page.",
    other: { slug: "spanish", name: "Spanish" },
    faq: languageFaq("French", "Spanish", "la voiture, le pont"),
  },
  {
    slug: "german",
    lang: "de",
    name: "German",
    sceneId: "alpine-castle",
    description:
      "Learn German words from your photos, with der, die, das, pronunciation and games. Try a photo lesson free, with unlimited lessons during the public beta.",
    lede: "Photograph your study desk, a morning walk or an alpine view. Linguini finds the things in the picture and teaches you their German names, with the article (der, die, das), pronunciation and audio, then turns them into a five-minute game and a journal page.",
    other: { slug: "korean", name: "Korean" },
    faq: languageFaq("German", "Korean", "das Schloss, der Baum, die Straße"),
  },
  {
    slug: "korean",
    lang: "ko",
    name: "Korean",
    sceneId: "cafe-interior",
    description:
      "Learn beginner Korean words from your photos, with Hangul, pronunciation and games. Try a photo lesson free, with unlimited lessons during the public beta.",
    lede: "Photograph your morning coffee, your desk or your favorite meal. Linguini finds the things in the picture and teaches you their Korean names, with pronunciation and audio, then turns them into a five-minute game and a journal page.",
    other: { slug: "german", name: "German" },
    faq: languageFaq("Korean", "German", "탁자, 소파, 시계"),
  },
];

export function getLanguagePage(slug: string): LanguagePage | undefined {
  return languagePages.find(page => page.slug === slug);
}
