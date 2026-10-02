CREATE UNIQUE INDEX language_profiles_id_user_id_key ON public.language_profiles(id, user_id);

CREATE TABLE public.sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    language_profile_id UUID NOT NULL,
    scene_media_asset_id UUID NOT NULL REFERENCES public.media_assets(id) ON DELETE RESTRICT ON UPDATE CASCADE,
    status VARCHAR(20) NOT NULL DEFAULT 'created' CHECK (status IN
        ('created','analyzingScene','awaitingObjectReview','generatingTasks','inProgress','completed','abandoned','failed')),
    started_at TIMESTAMPTZ(6), completed_at TIMESTAMPTZ(6), abandoned_at TIMESTAMPTZ(6),
    plan_version VARCHAR(100) CHECK (plan_version IS NULL OR length(btrim(plan_version)) > 0),
    failure_code VARCHAR(100),
    idempotency_key VARCHAR(200),
    demo_state JSONB NOT NULL CHECK (jsonb_typeof(demo_state) = 'object'),
    created_at TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT sessions_profile_owner_fkey FOREIGN KEY (language_profile_id,user_id)
        REFERENCES public.language_profiles(id,user_id) ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT sessions_terminal_timestamp CHECK (
        (status <> 'completed' OR completed_at IS NOT NULL) AND
        (status <> 'abandoned' OR abandoned_at IS NOT NULL) AND
        NOT (completed_at IS NOT NULL AND abandoned_at IS NOT NULL)),
    CONSTRAINT sessions_id_scene_media_asset_id_key UNIQUE(id,scene_media_asset_id),
    CONSTRAINT sessions_user_id_language_profile_id_idempotency_key_key UNIQUE(user_id,language_profile_id,idempotency_key)
);
CREATE INDEX sessions_language_profile_id_user_id_idx ON public.sessions(language_profile_id,user_id);
CREATE INDEX sessions_scene_media_asset_id_idx ON public.sessions(scene_media_asset_id);
CREATE UNIQUE INDEX sessions_one_in_progress_key ON public.sessions(language_profile_id) WHERE status='inProgress';

CREATE TABLE public.scene_objects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL,
    media_asset_id UUID NOT NULL,
    detected_label TEXT NOT NULL CHECK (length(btrim(detected_label)) > 0),
    confirmed_label VARCHAR(200) CHECK (confirmed_label IS NULL OR length(btrim(confirmed_label)) > 0),
    selection_status VARCHAR(9) NOT NULL DEFAULT 'suggested'
        CHECK (selection_status IN ('suggested','accepted','rejected','corrected')),
    x DECIMAL(10,9) NOT NULL CHECK (x BETWEEN 0 AND 1),
    y DECIMAL(10,9) NOT NULL CHECK (y BETWEEN 0 AND 1),
    width DECIMAL(10,9) NOT NULL CHECK (width > 0 AND width <= 1),
    height DECIMAL(10,9) NOT NULL CHECK (height > 0 AND height <= 1),
    confidence DECIMAL(6,5) CHECK (confidence BETWEEN 0 AND 1),
    vocabulary_item_id UUID REFERENCES public.vocabulary_items(id) ON DELETE SET NULL ON UPDATE CASCADE,
    created_at TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT scene_objects_session_media_fkey FOREIGN KEY(session_id,media_asset_id)
        REFERENCES public.sessions(id,scene_media_asset_id) ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT scene_objects_bbox CHECK (x + width <= 1 AND y + height <= 1),
    CONSTRAINT scene_objects_correction CHECK (selection_status <> 'corrected' OR confirmed_label IS NOT NULL)
);
CREATE INDEX scene_objects_session_id_media_asset_id_idx ON public.scene_objects(session_id,media_asset_id);
CREATE INDEX scene_objects_vocabulary_item_id_idx ON public.scene_objects(vocabulary_item_id);

CREATE TABLE public.user_practice_progress (
    user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE ON UPDATE CASCADE,
    language_code VARCHAR(35) NOT NULL CHECK (language_code ~ '^[a-z]{2,3}(-[a-z0-9]{2,8})*$'),
    xp INTEGER NOT NULL DEFAULT 0 CHECK (xp >= 0),
    scenarios JSONB NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(scenarios) = 'array'),
    leaderboard JSONB NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(leaderboard) = 'array'),
    created_at TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(user_id,language_code)
);

CREATE FUNCTION public.check_session_media() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE asset public.media_assets%ROWTYPE;
BEGIN
    SELECT * INTO asset FROM public.media_assets WHERE id=NEW.scene_media_asset_id FOR SHARE;
    IF FOUND AND (asset.media_type <> 'image' OR NOT (asset.source='preloaded' OR asset.owner_user_id IS NOT DISTINCT FROM NEW.user_id)) THEN
        RAISE EXCEPTION 'Session media must be an owned or preloaded image' USING ERRCODE='23514';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER sessions_media_check BEFORE INSERT OR UPDATE OF scene_media_asset_id,user_id ON public.sessions
    FOR EACH ROW EXECUTE FUNCTION public.check_session_media();

CREATE FUNCTION public.protect_session_media() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF EXISTS(SELECT 1 FROM public.sessions WHERE scene_media_asset_id=NEW.id AND
        (NEW.media_type <> 'image' OR NOT (NEW.source='preloaded' OR NEW.owner_user_id IS NOT DISTINCT FROM user_id))) THEN
        RAISE EXCEPTION 'Media change would invalidate session ownership or image type' USING ERRCODE='23514';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER media_assets_session_check BEFORE UPDATE OF media_type,source,owner_user_id ON public.media_assets
    FOR EACH ROW EXECUTE FUNCTION public.protect_session_media();

DO $$
DECLARE table_name TEXT;
BEGIN
    FOREACH table_name IN ARRAY ARRAY['sessions','scene_objects','user_practice_progress'] LOOP
        EXECUTE format('CREATE TRIGGER %I BEFORE UPDATE ON public.%I FOR EACH ROW EXECUTE FUNCTION public.set_user_updated_at()', table_name || '_updated_at', table_name);
        EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', table_name);
        EXECUTE format('REVOKE ALL ON TABLE public.%I FROM PUBLIC', table_name);
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='anon') THEN EXECUTE format('REVOKE ALL ON TABLE public.%I FROM anon',table_name); END IF;
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN EXECUTE format('REVOKE ALL ON TABLE public.%I FROM authenticated',table_name); END IF;
    END LOOP;
END;
$$;
