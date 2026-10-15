-- Pre-A1 is stored as A0 so the existing VARCHAR(2) level columns are unchanged.
BEGIN;

ALTER TABLE public.language_profiles DROP CONSTRAINT language_profiles_level;
ALTER TABLE public.language_profiles ADD CONSTRAINT language_profiles_level CHECK
    (proficiency_level IN ('A0', 'A1', 'A2', 'B1', 'B2', 'C1', 'C2'));

ALTER TABLE public.vocabulary_items DROP CONSTRAINT vocabulary_items_difficulty_level_check;
ALTER TABLE public.vocabulary_items ADD CONSTRAINT vocabulary_items_difficulty_level_check CHECK
    (difficulty_level IN ('A0', 'A1', 'A2', 'B1', 'B2', 'C1', 'C2'));

COMMIT;
