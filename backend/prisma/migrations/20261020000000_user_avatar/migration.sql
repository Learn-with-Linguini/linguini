ALTER TABLE "public"."users"
ADD COLUMN "avatar" VARCHAR(20) NOT NULL DEFAULT 'farfalle';

ALTER TABLE "public"."users"
ADD CONSTRAINT "users_avatar_valid"
CHECK ("avatar" IN ('farfalle', 'fusilli', 'penne', 'macaroni'));
