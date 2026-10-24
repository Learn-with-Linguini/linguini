import type { Lang, Scene } from "../../data/types";

export type GuestWord = { id: string; source: string; translation: string; phoneticText?: string | null; x: number; y: number };
export type GuestTerm = { source: string; translation: string };
export type GuestScene = { id: string; photo: string; title: string; place: string; width: number; height: number; alt: string; words: GuestWord[]; adjectives: GuestTerm[]; prepositions: GuestTerm[]; uploaded?: boolean };
type DemoResponse = { id: string; title: string; summary?: string | null; width: number; height: number; words: Array<{ id: string; source: string; translation: string; phoneticText?: string | null; boundingBox?: { x: number; y: number; width: number; height: number } | null; anchorPoint?: { x: number; y: number } | null }>; adjectives?: GuestTerm[]; prepositions?: GuestTerm[] };

const supportingTerms: Record<Lang, { adjectives: GuestTerm[]; prepositions: GuestTerm[] }> = {
  es: { adjectives: [{ source: "red", translation: "rojo" }, { source: "small", translation: "pequeño" }, { source: "bright", translation: "luminoso" }], prepositions: [{ source: "next to", translation: "al lado de" }, { source: "in front of", translation: "delante de" }, { source: "behind", translation: "detrás de" }] },
  fr: { adjectives: [{ source: "red", translation: "rouge" }, { source: "small", translation: "petit" }, { source: "bright", translation: "lumineux" }], prepositions: [{ source: "next to", translation: "à côté de" }, { source: "in front of", translation: "devant" }, { source: "behind", translation: "derrière" }] },
  de: { adjectives: [{ source: "red", translation: "rot" }, { source: "small", translation: "klein" }, { source: "bright", translation: "hell" }], prepositions: [{ source: "next to", translation: "neben" }, { source: "in front of", translation: "vor" }, { source: "behind", translation: "hinter" }] },
  ko: { adjectives: [{ source: "red", translation: "빨간" }, { source: "small", translation: "작은" }, { source: "bright", translation: "밝은" }], prepositions: [{ source: "next to", translation: "옆에" }, { source: "in front of", translation: "앞에" }, { source: "behind", translation: "뒤에" }] },
};

export function staticGuestScene(scene: Scene, lang: Lang): GuestScene {
  return { id: scene.id, photo: scene.photo, title: scene.title, place: scene.place, width: scene.width, height: scene.height, alt: scene.alt, words: scene.words.slice(0, 5).map(word => ({ id: word.id, source: word.en, translation: word[lang].word, phoneticText: word[lang].ipa, x: word.x, y: word.y })), ...supportingTerms[lang] };
}

function readAsBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error("We couldn't read that photo."));
    reader.onload = () => { const value = String(reader.result ?? ""); resolve(value.includes(",") ? value.split(",", 2)[1] : value); };
    reader.readAsDataURL(file);
  });
}

export async function analyzeGuestPhoto(file: File, language: Lang): Promise<GuestScene> {
  if (!["image/jpeg", "image/png", "image/webp"].includes(file.type)) throw new Error("Choose a JPEG, PNG or WebP image.");
  if (!file.size || file.size > 10 * 1024 * 1024) throw new Error("Choose an image between 1 byte and 10 MB.");
  const apiBaseUrl = (import.meta.env?.VITE_API_BASE_URL ?? "").replace(/\/+$/, "");
  const response = await fetch(`${apiBaseUrl}/api/v1/demo/photo`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ imageBase64: await readAsBase64(file), targetLanguage: language }) });
  const payload = await response.json().catch(() => null) as DemoResponse | { detail?: { message?: string } } | null;
  if (!response.ok) {
    const message = payload && "detail" in payload ? payload.detail?.message : null;
    throw new Error(message || "We couldn't prepare that photo lesson. Please try another photo.");
  }
  const result = payload as DemoResponse;
  return { id: result.id, photo: URL.createObjectURL(file), title: result.title, place: result.summary || "Your photo", width: result.width, height: result.height, alt: `Your uploaded photo: ${result.title}`, uploaded: true, words: result.words.slice(0, 5).map(word => { const box = word.boundingBox; return { id: word.id, source: word.source, translation: word.translation, phoneticText: word.phoneticText, x: (word.anchorPoint?.x ?? (box ? box.x + box.width / 2 : 0.5)) * 100, y: (word.anchorPoint?.y ?? (box ? box.y + box.height / 2 : 0.5)) * 100 }; }), adjectives: result.adjectives ?? [], prepositions: result.prepositions ?? [] };
}
