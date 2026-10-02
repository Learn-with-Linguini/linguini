"use client";

import { useId } from "react";
import { languageNames, type Lang } from "@/data/types";
import styles from "./session.module.css";

const codes: Record<Lang, string> = { es: "ES", fr: "FR" };

export function LanguageToggle({ value, onChange, compact = false }: { value: Lang; onChange: (lang: Lang) => void; compact?: boolean }) {
  const name = useId();
  return (
    <fieldset className={`${styles.langToggle} ${compact ? styles.langCompact : ""}`}>
      <legend className="visually-hidden">Language to learn</legend>
      {(Object.keys(languageNames) as Lang[]).map(lang => (
        <label key={lang} className={styles.langOption}>
          <input
            type="radio"
            name={name}
            value={lang}
            checked={value === lang}
            onChange={() => onChange(lang)}
            className="visually-hidden"
          />
          <span className={styles.langCode} aria-hidden="true">{codes[lang]}</span>
          {languageNames[lang]}
        </label>
      ))}
    </fieldset>
  );
}
