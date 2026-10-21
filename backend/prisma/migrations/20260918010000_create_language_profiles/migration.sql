CREATE TABLE "public"."language_profiles" (
    "id" UUID NOT NULL DEFAULT gen_random_uuid(),
    "user_id" UUID NOT NULL,
    "source_language_code" VARCHAR(35) NOT NULL,
    "target_language_code" VARCHAR(35) NOT NULL,
    "proficiency_level" VARCHAR(2) NOT NULL,
    "is_active" BOOLEAN NOT NULL DEFAULT true,
    "preferred_input_mode" VARCHAR(6) NOT NULL DEFAULT 'both',
    "daily_goal_minutes" INTEGER,
    "created_at" TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "language_profiles_pkey" PRIMARY KEY ("id"),
    CONSTRAINT "language_profiles_user_id_fkey" FOREIGN KEY ("user_id")
        REFERENCES "public"."users"("id") ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT "language_profiles_different_languages" CHECK
        (lower("source_language_code") <> lower("target_language_code")),
    CONSTRAINT "language_profiles_source_code" CHECK
        ("source_language_code" ~ '^[A-Za-z]{2,3}(-[A-Za-z0-9]{2,8})*$'),
    CONSTRAINT "language_profiles_target_code" CHECK
        ("target_language_code" ~ '^[A-Za-z]{2,3}(-[A-Za-z0-9]{2,8})*$'),
    CONSTRAINT "language_profiles_level" CHECK
        ("proficiency_level" IN ('A1', 'A2', 'B1', 'B2', 'C1', 'C2')),
    CONSTRAINT "language_profiles_input_mode" CHECK
        ("preferred_input_mode" IN ('speech', 'text', 'both')),
    CONSTRAINT "language_profiles_daily_goal" CHECK
        ("daily_goal_minutes" BETWEEN 1 AND 240)
);

CREATE INDEX "language_profiles_user_id_idx" ON "public"."language_profiles"("user_id");
CREATE UNIQUE INDEX "language_profiles_pair_key" ON "public"."language_profiles"
    ("user_id", lower("source_language_code"), lower("target_language_code"));
CREATE UNIQUE INDEX "language_profiles_one_active_key" ON "public"."language_profiles"
    ("user_id") WHERE "is_active";

CREATE TRIGGER "language_profiles_updated_at"
BEFORE UPDATE ON "public"."language_profiles"
FOR EACH ROW EXECUTE FUNCTION "public"."set_user_updated_at"();

ALTER TABLE "public"."language_profiles" ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE "public"."language_profiles" FROM PUBLIC;
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
        REVOKE ALL ON TABLE "public"."language_profiles" FROM anon;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
        REVOKE ALL ON TABLE "public"."language_profiles" FROM authenticated;
    END IF;
END;
$$;
