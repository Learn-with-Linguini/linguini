CREATE UNIQUE INDEX scene_objects_id_session_id_key ON public.scene_objects(id, session_id);

CREATE TABLE public.session_tasks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES public.sessions(id) ON DELETE CASCADE ON UPDATE CASCADE,
    phase VARCHAR(8) NOT NULL CHECK (phase IN ('learning','ispy')),
    kind VARCHAR(22) NOT NULL CHECK (kind IN ('vocabularyIntroduction','pronunciationPractice',
        'grammarExplanation','grammarPractice','syntaxExplanation','sentenceBuilding','ispyRound','reflection')),
    order_index INTEGER NOT NULL CHECK (order_index >= 0),
    status VARCHAR(10) NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','inProgress','completed','skipped')),
    is_skippable BOOLEAN NOT NULL DEFAULT TRUE CHECK (is_skippable),
    public_content JSONB NOT NULL CHECK (jsonb_typeof(public_content) = 'object'),
    answer_key JSONB CHECK (jsonb_typeof(answer_key) = 'object'),
    vocabulary_item_id UUID REFERENCES public.vocabulary_items(id) ON DELETE RESTRICT ON UPDATE CASCADE,
    scene_object_id UUID,
    started_at TIMESTAMPTZ(6), completed_at TIMESTAMPTZ(6), skipped_at TIMESTAMPTZ(6),
    skip_reason VARCHAR(500),
    created_at TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT session_tasks_session_id_order_index_key UNIQUE(session_id, order_index),
    CONSTRAINT session_tasks_scene_object_session_fkey FOREIGN KEY(scene_object_id,session_id)
        REFERENCES public.scene_objects(id,session_id) ON DELETE NO ACTION ON UPDATE CASCADE,
    CONSTRAINT session_tasks_content_kind CHECK (public_content ? 'kind' AND public_content->>'kind' IS NOT NULL AND public_content->>'kind' = kind),
    CONSTRAINT session_tasks_phase_kind CHECK ((kind='ispyRound') = (phase='ispy')),
    CONSTRAINT session_tasks_terminal_timestamp CHECK (
        (status <> 'completed' OR completed_at IS NOT NULL) AND
        (status <> 'skipped' OR skipped_at IS NOT NULL) AND
        NOT (completed_at IS NOT NULL AND skipped_at IS NOT NULL))
);
CREATE INDEX session_tasks_vocabulary_item_id_idx ON public.session_tasks(vocabulary_item_id);
CREATE INDEX session_tasks_scene_object_id_session_id_idx ON public.session_tasks(scene_object_id,session_id);

CREATE TABLE public.task_attempts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_task_id UUID NOT NULL REFERENCES public.session_tasks(id) ON DELETE CASCADE ON UPDATE CASCADE,
    attempt_number INTEGER NOT NULL CHECK (attempt_number >= 1),
    input_mode VARCHAR(15) NOT NULL CHECK (input_mode IN ('speech','text','objectSelection','multipleChoice')),
    response_payload JSONB NOT NULL CHECK (jsonb_typeof(response_payload) = 'object'),
    audio_media_asset_id UUID REFERENCES public.media_assets(id) ON DELETE RESTRICT ON UPDATE CASCADE,
    is_correct BOOLEAN,
    score DECIMAL(6,5) CHECK (score BETWEEN 0 AND 1),
    feedback JSONB CHECK (jsonb_typeof(feedback) = 'object'),
    evaluation_details JSONB CHECK (jsonb_typeof(evaluation_details) = 'object'),
    created_at TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT task_attempts_session_task_id_attempt_number_key UNIQUE(session_task_id,attempt_number),
    CONSTRAINT task_attempts_speech_audio CHECK ((input_mode='speech') = (audio_media_asset_id IS NOT NULL))
);
CREATE INDEX task_attempts_audio_media_asset_id_idx ON public.task_attempts(audio_media_asset_id);

CREATE TABLE public.task_hints (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_task_id UUID NOT NULL REFERENCES public.session_tasks(id) ON DELETE CASCADE ON UPDATE CASCADE,
    hint_level INTEGER NOT NULL CHECK (hint_level >= 1),
    content JSONB NOT NULL CHECK (jsonb_typeof(content) = 'object'),
    requested_at TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT task_hints_session_task_id_hint_level_key UNIQUE(session_task_id,hint_level)
);

CREATE FUNCTION public.check_task_attempt_audio() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE asset public.media_assets%ROWTYPE; owner_id UUID;
BEGIN
    IF NEW.audio_media_asset_id IS NULL THEN RETURN NEW; END IF;
    SELECT s.user_id INTO owner_id FROM public.sessions s JOIN public.session_tasks t ON t.session_id=s.id
        WHERE t.id=NEW.session_task_id;
    SELECT * INTO asset FROM public.media_assets WHERE id=NEW.audio_media_asset_id FOR SHARE;
    IF FOUND AND (asset.media_type <> 'audio' OR asset.owner_user_id IS DISTINCT FROM owner_id) THEN
        RAISE EXCEPTION 'Attempt audio must belong to the session user and be audio' USING ERRCODE='23514';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER task_attempts_audio_check BEFORE INSERT OR UPDATE OF audio_media_asset_id,session_task_id
    ON public.task_attempts FOR EACH ROW EXECUTE FUNCTION public.check_task_attempt_audio();

CREATE FUNCTION public.protect_task_attempt_audio() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF EXISTS(SELECT 1 FROM public.task_attempts a JOIN public.session_tasks t ON t.id=a.session_task_id
        JOIN public.sessions s ON s.id=t.session_id WHERE a.audio_media_asset_id=NEW.id AND
        (NEW.media_type <> 'audio' OR NEW.owner_user_id IS DISTINCT FROM s.user_id)) THEN
        RAISE EXCEPTION 'Media change would invalidate attempt audio' USING ERRCODE='23514';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER media_assets_attempt_audio_check BEFORE UPDATE OF media_type,owner_user_id ON public.media_assets
    FOR EACH ROW EXECUTE FUNCTION public.protect_task_attempt_audio();

-- Prevent moving an existing task/attempt/hint to another owner or session.
CREATE FUNCTION public.protect_task_parent() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF to_jsonb(NEW)->TG_ARGV[0] IS DISTINCT FROM to_jsonb(OLD)->TG_ARGV[0] THEN
        RAISE EXCEPTION 'Task record parent is immutable' USING ERRCODE='23514';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER session_tasks_parent_check BEFORE UPDATE OF session_id ON public.session_tasks
    FOR EACH ROW EXECUTE FUNCTION public.protect_task_parent('session_id');
CREATE TRIGGER task_attempts_parent_check BEFORE UPDATE OF session_task_id ON public.task_attempts
    FOR EACH ROW EXECUTE FUNCTION public.protect_task_parent('session_task_id');
CREATE TRIGGER task_hints_parent_check BEFORE UPDATE OF session_task_id ON public.task_hints
    FOR EACH ROW EXECUTE FUNCTION public.protect_task_parent('session_task_id');

DO $$
DECLARE table_name TEXT;
BEGIN
    FOREACH table_name IN ARRAY ARRAY['session_tasks','task_attempts','task_hints'] LOOP
        EXECUTE format('CREATE TRIGGER %I BEFORE UPDATE ON public.%I FOR EACH ROW EXECUTE FUNCTION public.set_user_updated_at()', table_name || '_updated_at', table_name);
        EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY',table_name);
        EXECUTE format('REVOKE ALL ON TABLE public.%I FROM PUBLIC',table_name);
        IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='anon') THEN EXECUTE format('REVOKE ALL ON TABLE public.%I FROM anon',table_name); END IF;
        IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN EXECUTE format('REVOKE ALL ON TABLE public.%I FROM authenticated',table_name); END IF;
    END LOOP;
END;
$$;
