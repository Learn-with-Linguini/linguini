BEGIN;
-- AI-call observability moved to an external platform; runs are no longer stored.
-- Export any historical rows before deployment if they need to be retained.
-- sessions_id_user_id_key and journals_id_user_id_key stay: vocabulary_encounters
-- and other composite foreign keys depend on them.
-- Deliberately omit CASCADE so unexpected dependencies prevent the drop.
DROP TABLE public.ai_generation_runs;
DROP FUNCTION public.protect_ai_generation_run();
COMMIT;
