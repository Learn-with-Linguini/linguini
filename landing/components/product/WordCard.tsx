"use client";

import type { Lang, SceneWord } from "@/data/types";
import { speak } from "@/lib/speech";
import { Speaker } from "../icons";
import styles from "./product.module.css";

type WordCardProps = {
  word: SceneWord;
  lang: Lang;
  className?: string;
};

export function WordCard({ word, lang, className = "" }: WordCardProps) {
  const entry = word[lang];
  return (
    <div className={`${styles.wordCard} ${className}`}>
      <div className={styles.wordTop}>
        <span className={styles.wordLabel}>noun · {entry.gender}</span>
        <button
          type="button"
          className={styles.speak}
          onClick={() => speak(entry.word, lang)}
          aria-label={`Hear “${entry.word}”`}
        >
          <Speaker size={20} />
        </button>
      </div>
      <p className={styles.wordTarget} lang={lang}>{entry.word}</p>
      <p className={styles.wordMeaning}>the {word.en}</p>
      <p className={styles.wordIpa}>/{entry.ipa}/</p>
    </div>
  );
}
