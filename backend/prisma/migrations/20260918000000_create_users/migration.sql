CREATE TABLE "public"."users" (
    "id" UUID NOT NULL DEFAULT gen_random_uuid(),
    "auth_provider_id" TEXT NOT NULL,
    "display_name" VARCHAR(100) NOT NULL,
    "email" VARCHAR(320),
    "timezone" TEXT NOT NULL DEFAULT 'UTC',
    "learning_goal" VARCHAR(300) NOT NULL DEFAULT '',
    "microphone_enabled" BOOLEAN NOT NULL DEFAULT true,
    "camera_enabled" BOOLEAN NOT NULL DEFAULT true,
    "onboarding_completed" BOOLEAN NOT NULL DEFAULT false,
    "created_at" TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "users_pkey" PRIMARY KEY ("id"),
    CONSTRAINT "users_display_name_nonempty" CHECK (length(btrim("display_name")) > 0),
    CONSTRAINT "users_auth_provider_id_nonempty" CHECK (length(btrim("auth_provider_id")) > 0),
    CONSTRAINT "users_timezone_nonempty" CHECK (length(btrim("timezone")) > 0)
);

CREATE UNIQUE INDEX "users_auth_provider_id_key" ON "public"."users"("auth_provider_id");

-- Database-managed timestamps also cover writes outside the Python repository.
CREATE FUNCTION "public"."set_user_updated_at"() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at = clock_timestamp();
    RETURN NEW;
END;
$$;

CREATE TRIGGER "users_updated_at"
BEFORE UPDATE ON "public"."users"
FOR EACH ROW EXECUTE FUNCTION "public"."set_user_updated_at"();

-- Access is through the trusted backend DB role, not the Supabase browser API.
ALTER TABLE "public"."users" ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE "public"."users" FROM PUBLIC;
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
        REVOKE ALL ON TABLE "public"."users" FROM anon;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
        REVOKE ALL ON TABLE "public"."users" FROM authenticated;
    END IF;
END;
$$;
