import { faq } from "./faq";
import { pricing } from "./pricing";
import type { Lang } from "./types";

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
      a: `Yes. The free plan gives you one new photo lesson and one journal page every day, unlimited replays of our curated scenes and every game, with no card required. Plus ($${pricing.plusMonthly} a month or $${pricing.plusYearly} a year) raises that to 10 photo lessons a day and adds pronunciation feedback and review mode.`,
    },
    {
      q: `What level of ${name} is Linguini for?`,
      a: faqAnswer("What level is Linguini for?"),
    },
    {
      q: `Which ${name} words will I learn?`,
      a: `The names of the things in your photos, each with its article and gender (${examples}), plus the everyday adjectives and short sentences you need to talk about them. Because the words come from your own day, they are words you will actually use.`,
    },
    {
      q: "Do I have to use my own photos?",
      a: faqAnswer("Do I have to use my own photos?"),
    },
    {
      q: `Does Linguini teach ${other} too?`,
      a: `Yes. Linguini teaches both Spanish and French, from English. Italian is next on the list.`,
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
      "Learn Spanish from photos of your day. Linguini names what’s in the picture, with the article and audio, and turns it into a five-minute game. Free to start.",
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
      "Learn French from photos of your day. Linguini names what’s in the picture, with the article and audio, and turns it into a five-minute game. Free to start.",
    lede: "Photograph the promenade on your evening walk or the view from your window. Linguini finds the things in the picture and teaches you their French names, with the article, pronunciation and audio, then turns them into a five-minute game and a journal page.",
    other: { slug: "spanish", name: "Spanish" },
    faq: languageFaq("French", "Spanish", "la voiture, le pont"),
  },
];

export function getLanguagePage(slug: string): LanguagePage | undefined {
  return languagePages.find(page => page.slug === slug);
}
