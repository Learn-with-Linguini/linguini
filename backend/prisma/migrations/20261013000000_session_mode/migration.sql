-- Standalone I-Spy games are sessions with mode 'ispy'; every existing session is a lesson.
CREATE TYPE "session_mode" AS ENUM ('lesson', 'ispy');

ALTER TABLE "sessions" ADD COLUMN "session_mode" "session_mode" NOT NULL DEFAULT 'lesson',
ADD COLUMN "source_session_id" UUID,
ADD COLUMN "scene_confirmed_at" TIMESTAMPTZ(6);

-- Lessons that already started had their scene review confirmed just before
-- started_at; the rest stay unconfirmed until their next review.
UPDATE "sessions"
SET "scene_confirmed_at" = "started_at"
WHERE "started_at" IS NOT NULL
  AND "session_status" IN ('ready', 'inProgress', 'completed', 'abandoned');

CREATE INDEX "sessions_user_id_scene_media_asset_id_idx" ON "sessions"("user_id", "scene_media_asset_id");

ALTER TABLE "sessions" ADD CONSTRAINT "sessions_source_session_id_fkey" FOREIGN KEY ("source_session_id") REFERENCES "sessions"("id") ON DELETE SET NULL ON UPDATE CASCADE;
