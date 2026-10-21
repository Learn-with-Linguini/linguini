/** "las flores" → "flores", "l’arbre" → "arbre", "das Auto" → "Auto". Used to spot a learned noun inside free text. */
export function stripArticle(word: string): string {
  return word.replace(/^(?:(?:los|las|les|el|la|le|der|die|das|den|dem|des|ein|eine)\s+|l[’'])/i, "");
}
