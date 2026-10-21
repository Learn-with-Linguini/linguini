BEGIN;
LOCK TABLE public.sessions IN SHARE ROW EXCLUSIVE MODE;
-- Retain session identity/history and all normalized records. Legacy unfinished runs
-- cannot safely resume without their JSON state; close them without granting credit.
UPDATE public.sessions SET status = 'abandoned', abandoned_at = CURRENT_TIMESTAMP
WHERE plan_version IS NULL AND status NOT IN ('completed', 'abandoned', 'failed');
ALTER TABLE public.sessions DROP COLUMN demo_state;
DROP INDEX public.sessions_one_in_progress_key;
CREATE UNIQUE INDEX sessions_one_active_key ON public.sessions(language_profile_id)
WHERE status NOT IN ('completed', 'abandoned', 'failed');
COMMIT;
