// "I spy" openers per language, with an example of how a clue carries on from them.
const OPENINGS: Record<string, { opening: string; example: string }> = {
  es: { opening: "Veo, veo, algo que", example: "es rojo y está sobre la mesa" },
  fr: { opening: "Je vois, je vois, quelque chose qui", example: "est rouge et sur la table" },
  de: { opening: "Ich sehe etwas, das", example: "rot ist und auf dem Tisch liegt" },
  ko: { opening: "나는 무언가를 보고 있어요:", example: "빨간색이고 탁자 위에 있어요" },
};
const ENGLISH = { opening: "I spy with my little eye, something that", example: "is red and on the table" };

const forLanguage = (languageCode: string) => OPENINGS[languageCode.split("-")[0]] ?? ENGLISH;

/** The I-Spy opener a clue continues, such as "Je vois, je vois, quelque chose qui". */
export const clueOpening = (languageCode: string) => forLanguage(languageCode).opening;

/** A sample continuation of the opener, shown so learners see how to start their clue. */
export const clueExample = (languageCode: string) => forLanguage(languageCode).example;
