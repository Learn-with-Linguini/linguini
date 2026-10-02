CREATE TABLE "public"."media_assets" (
    "id" UUID NOT NULL DEFAULT gen_random_uuid(),
    "owner_user_id" UUID,
    "media_type" VARCHAR(5) NOT NULL,
    "source" VARCHAR(10) NOT NULL,
    "storage_key" TEXT NOT NULL,
    "mime_type" TEXT NOT NULL,
    "width" INTEGER,
    "height" INTEGER,
    "duration_ms" INTEGER,
    "captured_at" TIMESTAMPTZ(6),
    "created_at" TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "media_assets_pkey" PRIMARY KEY ("id"),
    CONSTRAINT "media_assets_owner_user_id_fkey" FOREIGN KEY ("owner_user_id")
        REFERENCES "public"."users"("id") ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT "media_assets_type" CHECK ("media_type" IN ('image', 'audio')),
    CONSTRAINT "media_assets_source" CHECK
        ("source" IN ('userUpload', 'camera', 'preloaded', 'generated')),
    CONSTRAINT "media_assets_storage_key" CHECK (length(btrim("storage_key")) > 0),
    CONSTRAINT "media_assets_mime_type" CHECK
        (lower("mime_type") LIKE "media_type" || '/_%'),
    CONSTRAINT "media_assets_width" CHECK ("width" > 0),
    CONSTRAINT "media_assets_height" CHECK ("height" > 0),
    CONSTRAINT "media_assets_duration" CHECK ("duration_ms" > 0),
    CONSTRAINT "media_assets_image_metadata" CHECK
        ("media_type" <> 'image' OR "duration_ms" IS NULL),
    CONSTRAINT "media_assets_audio_metadata" CHECK
        ("media_type" <> 'audio' OR ("width" IS NULL AND "height" IS NULL)),
    CONSTRAINT "media_assets_preloaded_owner" CHECK
        ("source" <> 'preloaded' OR "owner_user_id" IS NULL),
    CONSTRAINT "media_assets_upload_owner" CHECK
        ("source" NOT IN ('userUpload', 'camera') OR "owner_user_id" IS NOT NULL)
);
CREATE UNIQUE INDEX "media_assets_storage_key_key" ON "public"."media_assets"("storage_key");
CREATE INDEX "media_assets_owner_user_id_idx" ON "public"."media_assets"("owner_user_id");
CREATE TRIGGER "media_assets_updated_at"
BEFORE UPDATE ON "public"."media_assets"
FOR EACH ROW EXECUTE FUNCTION "public"."set_user_updated_at"();

ALTER TABLE "public"."media_assets" ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE "public"."media_assets" FROM PUBLIC;
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
        REVOKE ALL ON TABLE "public"."media_assets" FROM anon;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
        REVOKE ALL ON TABLE "public"."media_assets" FROM authenticated;
    END IF;
END;
$$;
