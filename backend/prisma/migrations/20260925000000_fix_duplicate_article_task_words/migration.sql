-- Collapse definite articles duplicated by earlier task generation
-- (for example "el el camino"). Vocabulary rows are left untouched: curated
-- scene words legitimately store the article inside the display text.
UPDATE session_tasks
SET public_content = regexp_replace(
      public_content::text,
      '(?i)\y(el|la|los|las|le|les)\s+\1\y',
      '\1',
      'g'
    )::jsonb
WHERE public_content::text ~ '(?i)\y(el|la|los|las|le|les)\s+\1\y';
