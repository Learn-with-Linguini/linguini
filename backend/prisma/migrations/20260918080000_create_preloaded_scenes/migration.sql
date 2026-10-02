CREATE TABLE public.preloaded_scenes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    slug TEXT NOT NULL UNIQUE CHECK (length(btrim(slug)) > 0),
    language_code VARCHAR(35) NOT NULL CHECK (language_code ~ '^[A-Za-z]{2,3}(-[A-Za-z0-9]{2,8})*$'),
    language TEXT NOT NULL CHECK (length(btrim(language)) > 0),
    media_asset_id UUID NOT NULL REFERENCES public.media_assets(id) ON DELETE RESTRICT ON UPDATE CASCADE,
    title TEXT NOT NULL CHECK (length(btrim(title)) > 0),
    description TEXT,
    art VARCHAR(7) NOT NULL CHECK (art IN ('street','cafe','market','bedroom','kitchen','park')),
    difficulty VARCHAR(12) NOT NULL DEFAULT 'beginner' CHECK (difficulty IN ('beginner','intermediate','advanced')),
    content JSONB NOT NULL CHECK (
        jsonb_typeof(content) = 'object' AND
        content ?& ARRAY['items','tasks','rounds','prompts'] AND
        jsonb_typeof(content->'items') = 'array' AND
        jsonb_typeof(content->'tasks') = 'array' AND
        jsonb_typeof(content->'rounds') = 'array' AND
        jsonb_typeof(content->'prompts') = 'array'
    ),
    sort_order INTEGER NOT NULL DEFAULT 0 CHECK (sort_order >= 0),
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ(6) NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ(6) NOT NULL DEFAULT now()
);
CREATE INDEX preloaded_scenes_language_code_is_active_sort_order_idx ON public.preloaded_scenes(language_code, is_active, sort_order);
CREATE INDEX preloaded_scenes_media_asset_id_idx ON public.preloaded_scenes(media_asset_id);
CREATE TRIGGER preloaded_scenes_updated_at BEFORE UPDATE ON public.preloaded_scenes
FOR EACH ROW EXECUTE FUNCTION public.set_user_updated_at();

CREATE FUNCTION public.check_preloaded_scene_media() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    PERFORM 1 FROM public.media_assets WHERE id = NEW.media_asset_id
        AND media_type = 'image' AND source = 'preloaded' AND owner_user_id IS NULL FOR SHARE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Scene media must be a shared preloaded image' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER preloaded_scene_media BEFORE INSERT OR UPDATE OF media_asset_id ON public.preloaded_scenes
FOR EACH ROW EXECUTE FUNCTION public.check_preloaded_scene_media();

CREATE FUNCTION public.protect_preloaded_scene_media() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF (NEW.media_type <> 'image' OR NEW.source <> 'preloaded' OR NEW.owner_user_id IS NOT NULL)
       AND EXISTS (SELECT 1 FROM public.preloaded_scenes WHERE media_asset_id = OLD.id) THEN
        RAISE EXCEPTION 'Referenced scene media must remain a shared preloaded image' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER protect_preloaded_scene_media BEFORE UPDATE ON public.media_assets
FOR EACH ROW EXECUTE FUNCTION public.protect_preloaded_scene_media();
ALTER TABLE public.preloaded_scenes ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.preloaded_scenes FROM PUBLIC;
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
        REVOKE ALL ON public.preloaded_scenes FROM anon;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
        REVOKE ALL ON public.preloaded_scenes FROM authenticated;
    END IF;
END $$;
