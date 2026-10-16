/** "las flores" → "flores", "l’arbre" → "arbre". Used to spot a learned noun inside free text. */
export function stripArticle(word: string): string {
  return word.replace(/^(?:(?:los|las|les|el|la|le)\s+|l[’'])/i, "");
}
