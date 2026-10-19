BEGIN;

CREATE TABLE public.media_scene_analyses (
    media_asset_id UUID PRIMARY KEY REFERENCES public.media_assets(id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    prompt_version VARCHAR(80) NOT NULL,
    schema_version VARCHAR(80) NOT NULL,
    inventory JSONB NOT NULL,
    created_at TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT media_scene_analyses_inventory_object
        CHECK (jsonb_typeof(inventory) = 'object')
);

ALTER TABLE public.media_scene_analyses ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.media_scene_analyses FROM PUBLIC;
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
        REVOKE ALL ON public.media_scene_analyses FROM anon;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
        REVOKE ALL ON public.media_scene_analyses FROM authenticated;
    END IF;
END $$;
CREATE TRIGGER media_scene_analyses_updated_at
BEFORE UPDATE ON public.media_scene_analyses
FOR EACH ROW EXECUTE FUNCTION public.set_user_updated_at();

COMMIT;
