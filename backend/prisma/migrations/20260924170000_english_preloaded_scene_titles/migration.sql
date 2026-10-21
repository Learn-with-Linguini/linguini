-- Preloaded scene titles are shown to learners in English.
BEGIN;

UPDATE public.preloaded_scenes SET title = 'At the café', updated_at = now() WHERE slug = 'cafe-plaza';
UPDATE public.preloaded_scenes SET title = 'At the market', updated_at = now() WHERE slug = 'mercado-central';
UPDATE public.preloaded_scenes SET title = 'In the park', updated_at = now() WHERE slug = 'el-parque';

COMMIT;
