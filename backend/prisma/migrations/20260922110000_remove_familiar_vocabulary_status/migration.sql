-- Existing familiar records represent completed I-Spy and are therefore learning.
UPDATE public.user_vocabulary_progress
SET status = 'learning'
WHERE status = 'familiar';

ALTER TABLE public.user_vocabulary_progress
  DROP CONSTRAINT user_vocabulary_progress_status_check;

ALTER TABLE public.user_vocabulary_progress
  ADD CONSTRAINT user_vocabulary_progress_status_check
  CHECK (status IN ('new', 'learning', 'mastered'));
