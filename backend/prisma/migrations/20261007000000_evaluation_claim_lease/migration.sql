-- The in-flight evaluation's request fingerprint and lease; an expired lease may be taken over.
ALTER TABLE "session_tasks" ADD COLUMN "evaluation_claim_fingerprint" VARCHAR(64),
ADD COLUMN "evaluation_claim_expires_at" TIMESTAMPTZ(6);
