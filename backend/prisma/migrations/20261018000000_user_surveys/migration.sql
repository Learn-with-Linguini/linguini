-- CreateTable
CREATE TABLE "public"."user_surveys" (
    "id" UUID NOT NULL DEFAULT gen_random_uuid(),
    "user_id" UUID,
    "email" VARCHAR(320),
    "rating" INTEGER NOT NULL,
    "usage_frequency" TEXT NOT NULL DEFAULT '',
    "motivation" TEXT NOT NULL DEFAULT '',
    "improvements" TEXT NOT NULL DEFAULT '',
    "receive_follow_up" BOOLEAN NOT NULL DEFAULT false,
    "trigger_source" VARCHAR(32) NOT NULL DEFAULT 'profile',
    "lesson_count" INTEGER,
    "created_at" TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "user_surveys_pkey" PRIMARY KEY ("id"),
    CONSTRAINT "user_surveys_rating_check" CHECK ("rating" >= 1 AND "rating" <= 5),
    CONSTRAINT "user_surveys_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "public"."users"("id") ON DELETE SET NULL ON UPDATE CASCADE
);

-- CreateIndex
CREATE INDEX "user_surveys_user_id_idx" ON "public"."user_surveys"("user_id");
