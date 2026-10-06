-- Task generation claims a revision; only the current revision may persist its results.
ALTER TABLE "sessions" ADD COLUMN "generation_revision" INTEGER NOT NULL DEFAULT 0;

-- The attempt ID whose model evaluation is in flight; a newer claim invalidates it.
ALTER TABLE "session_tasks" ADD COLUMN "evaluation_claim_id" UUID;
