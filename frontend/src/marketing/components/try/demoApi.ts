import type { Lang, Scene } from "../../data/types";

export type GuestWord = { id: string; source: string; translation: string; phoneticText?: string | null; gender?: string | null; x: number; y: number };
export type GuestTerm = { source: string; translation: string };
export type GuestScene = { id: string; photo: string; title: string; place: string; width: number; height: number; alt: string; words: GuestWord[]; adjectives: GuestTerm[]; prepositions: GuestTerm[] };

const supportingTerms: Record<Lang, { adjectives: GuestTerm[]; prepositions: GuestTerm[] }> = {
  es: { adjectives: [{ source: "red", translation: "rojo" }, { source: "small", translation: "pequeño" }, { source: "bright", translation: "luminoso" }], prepositions: [{ source: "next to", translation: "al lado de" }, { source: "in front of", translation: "delante de" }, { source: "behind", translation: "detrás de" }] },
  fr: { adjectives: [{ source: "red", translation: "rouge" }, { source: "small", translation: "petit" }, { source: "bright", translation: "lumineux" }], prepositions: [{ source: "next to", translation: "à côté de" }, { source: "in front of", translation: "devant" }, { source: "behind", translation: "derrière" }] },
  de: { adjectives: [{ source: "red", translation: "rot" }, { source: "small", translation: "klein" }, { source: "bright", translation: "hell" }], prepositions: [{ source: "next to", translation: "neben" }, { source: "in front of", translation: "vor" }, { source: "behind", translation: "hinter" }] },
  ko: { adjectives: [{ source: "red", translation: "빨간" }, { source: "small", translation: "작은" }, { source: "bright", translation: "밝은" }], prepositions: [{ source: "next to", translation: "옆에" }, { source: "in front of", translation: "앞에" }, { source: "behind", translation: "뒤에" }] },
};

export function staticGuestScene(scene: Scene, lang: Lang): GuestScene {
  return { id: scene.id, photo: scene.photo, title: scene.title, place: scene.place, width: scene.width, height: scene.height, alt: scene.alt, words: scene.words.slice(0, 5).map(word => ({ id: word.id, source: word.en, translation: word[lang].word, phoneticText: word[lang].ipa, gender: word[lang].gender === "none" ? null : word[lang].gender, x: word.x, y: word.y })), ...supportingTerms[lang] };
}
