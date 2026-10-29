import assert from "node:assert/strict";
import test from "node:test";
import { scenes } from "../src/marketing/data/scenes.ts";
import type { Lang } from "../src/marketing/data/types.ts";

// Only the singular/plural forms used by these authored exercises, not inflection rules.
const exerciseForms: Record<Lang, Record<string, string[]>> = {
  es: {
    "la flor": ["flor", "flores"], "el coche": ["coche", "coches"], "el sofá": ["sofá", "sofás"],
    "la página": ["página", "páginas"], "el puente": ["puente", "puentes"], "la torre": ["torre", "torres"],
    "la palmera": ["palmera", "palmeras"], "el árbol": ["árbol", "árboles"],
  },
  fr: {
    "la fleur": ["fleur", "fleurs"], "la voiture": ["voiture", "voitures"], "le canapé": ["canapé", "canapés"],
    "la page": ["page", "pages"], "le pont": ["pont", "ponts"], "la tour": ["tour", "tours"],
    "le palmier": ["palmier", "palmiers"], "l’arbre": ["arbre", "arbres"],
  },
  de: {
    "die Blume": ["Blume", "Blumen"], "das Auto": ["Auto", "Autos"], "das Sofa": ["Sofa", "Sofas"],
    "die Seite": ["Seite", "Seiten"], "die Brücke": ["Brücke", "Brücken"], "der Turm": ["Turm", "Türme"],
    "die Palme": ["Palme", "Palmen"], "der Baum": ["Baum", "Bäume"],
  },
  ko: {},
};

for (const scene of scenes) {
  test(`${scene.id} teaches the noun assessed by its gap exercise in every language`, () => {
    for (const lang of ["es", "fr", "de", "ko"] as const) {
      const round = scene.blank[lang];
      const taughtForms = scene.words.flatMap(word => [word[lang].word, ...exerciseForms[lang][word[lang].word] ?? []]);
      for (const option of round.options) {
        assert.ok(taughtForms.includes(option), `${scene.id}/${lang}: ${option} is not a form of any taught noun`);
      }
      const target = scene.words.find(word => word.id === scene.blankWordId);
      assert.ok(target, `${scene.id}: gap target must have a word card`);
      assert.ok([target[lang].word, ...exerciseForms[lang][target[lang].word] ?? []].includes(round.answer),
        `${scene.id}/${lang}: the gap must assess its declared word`);
      assert.ok(round.options.includes(round.answer), `${scene.id}/${lang}: answer must be selectable`);
    }
  });
}
