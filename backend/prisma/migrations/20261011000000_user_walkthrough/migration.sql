-- Persist which product walkthrough a learner has already completed or skipped.
ALTER TABLE public.users
ADD COLUMN IF NOT EXISTS walkthrough_version_seen INTEGER NOT NULL DEFAULT 0;
