BEGIN;
-- Obsolete demo snapshots are no longer read or written by the application.
-- Export any historical rows before deployment if they need to be retained.
-- XP comes from vocabulary_encounters; session/task and per-word progress stay intact.
-- Deliberately omit CASCADE so unexpected dependencies prevent the drop.
DROP TABLE public.user_practice_progress;
COMMIT;
