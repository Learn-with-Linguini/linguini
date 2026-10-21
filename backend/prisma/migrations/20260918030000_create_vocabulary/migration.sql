CREATE TABLE public.vocabulary_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    language_code VARCHAR(35) NOT NULL CHECK (language_code ~ '^[A-Za-z]{2,3}(-[A-Za-z0-9]{2,8})*$'),
    lemma VARCHAR(200) NOT NULL CHECK (length(btrim(lemma)) > 0),
    display_text VARCHAR(200) NOT NULL CHECK (length(btrim(display_text)) > 0),
    part_of_speech VARCHAR(13) NOT NULL CHECK (part_of_speech IN
        ('noun','verb','adjective','adverb','pronoun','preposition','conjunction','interjection','determiner','phrase','other')),
    gender VARCHAR(50),
    plural_form VARCHAR(200),
    phonetic_text VARCHAR(300),
    pronunciation_audio_asset_id UUID REFERENCES public.media_assets(id) ON DELETE SET NULL ON UPDATE CASCADE,
    example_sentence VARCHAR(1000),
    difficulty_level VARCHAR(2) CHECK (difficulty_level IN ('A1','A2','B1','B2','C1','C2')),
    created_at TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX vocabulary_items_language_code_lemma_idx ON public.vocabulary_items(language_code, lemma);
CREATE INDEX vocabulary_items_pronunciation_audio_asset_id_idx ON public.vocabulary_items(pronunciation_audio_asset_id);

CREATE TABLE public.vocabulary_translations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    vocabulary_item_id UUID NOT NULL REFERENCES public.vocabulary_items(id) ON DELETE CASCADE ON UPDATE CASCADE,
    source_language_code VARCHAR(35) NOT NULL CHECK (source_language_code ~ '^[A-Za-z]{2,3}(-[A-Za-z0-9]{2,8})*$'),
    translated_text VARCHAR(300) NOT NULL CHECK (length(btrim(translated_text)) > 0),
    short_definition VARCHAR(1000),
    created_at TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE UNIQUE INDEX vocabulary_translations_item_source_key
    ON public.vocabulary_translations(vocabulary_item_id, lower(source_language_code));

CREATE TABLE public.user_vocabulary_progress (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE ON UPDATE CASCADE,
    vocabulary_item_id UUID NOT NULL REFERENCES public.vocabulary_items(id) ON DELETE RESTRICT ON UPDATE CASCADE,
    status VARCHAR(8) NOT NULL DEFAULT 'new' CHECK (status IN ('new','learning','familiar','mastered')),
    exposure_count INTEGER NOT NULL DEFAULT 0 CHECK (exposure_count >= 0),
    correct_attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (correct_attempt_count >= 0 AND correct_attempt_count <= exposure_count),
    mastery_score DECIMAL(6,5) NOT NULL DEFAULT 0 CHECK (mastery_score BETWEEN 0 AND 1),
    first_learned_at TIMESTAMPTZ(6),
    last_practised_at TIMESTAMPTZ(6),
    scene_id TEXT,
    topic TEXT,
    created_at TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT user_vocabulary_progress_user_id_vocabulary_item_id_key UNIQUE(user_id, vocabulary_item_id)
);
CREATE INDEX user_vocabulary_progress_vocabulary_item_id_idx ON public.user_vocabulary_progress(vocabulary_item_id);

CREATE TABLE public.vocabulary_encounters (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    vocabulary_item_id UUID NOT NULL,
    session_id UUID NOT NULL,
    session_task_id UUID NOT NULL,
    encounter_type VARCHAR(10) NOT NULL CHECK (encounter_type IN ('introduced','practised','recalled','mastered')),
    outcome VARCHAR(9) NOT NULL CHECK (outcome IN ('correct','incorrect','completed')),
    occurred_at TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT vocabulary_encounters_progress_fkey FOREIGN KEY (user_id, vocabulary_item_id)
        REFERENCES public.user_vocabulary_progress(user_id, vocabulary_item_id) ON DELETE CASCADE ON UPDATE CASCADE
);
CREATE INDEX vocabulary_encounters_user_id_vocabulary_item_id_occurred_at_idx
    ON public.vocabulary_encounters(user_id, vocabulary_item_id, occurred_at);
CREATE INDEX vocabulary_encounters_session_id_idx ON public.vocabulary_encounters(session_id);
CREATE INDEX vocabulary_encounters_session_task_id_idx ON public.vocabulary_encounters(session_task_id);

-- Keep audio references valid, including media metadata edits outside the app.
CREATE FUNCTION public.check_vocabulary_audio() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.pronunciation_audio_asset_id IS NOT NULL AND EXISTS (
        SELECT 1 FROM public.media_assets WHERE id = NEW.pronunciation_audio_asset_id AND media_type <> 'audio'
    ) THEN
        RAISE EXCEPTION 'Pronunciation media must be audio' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER vocabulary_items_audio_check BEFORE INSERT OR UPDATE OF pronunciation_audio_asset_id
    ON public.vocabulary_items FOR EACH ROW EXECUTE FUNCTION public.check_vocabulary_audio();
CREATE FUNCTION public.protect_vocabulary_audio() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.media_type <> 'audio' AND EXISTS (
        SELECT 1 FROM public.vocabulary_items WHERE pronunciation_audio_asset_id = NEW.id
    ) THEN
        RAISE EXCEPTION 'Referenced pronunciation media must remain audio' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER media_assets_vocabulary_audio_check BEFORE UPDATE OF media_type ON public.media_assets
    FOR EACH ROW EXECUTE FUNCTION public.protect_vocabulary_audio();

DO $$
DECLARE table_name TEXT;
BEGIN
    FOREACH table_name IN ARRAY ARRAY['vocabulary_items','vocabulary_translations','user_vocabulary_progress','vocabulary_encounters'] LOOP
        EXECUTE format('CREATE TRIGGER %I BEFORE UPDATE ON public.%I FOR EACH ROW EXECUTE FUNCTION public.set_user_updated_at()', table_name || '_updated_at', table_name);
        EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', table_name);
        EXECUTE format('REVOKE ALL ON TABLE public.%I FROM PUBLIC', table_name);
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
            EXECUTE format('REVOKE ALL ON TABLE public.%I FROM anon', table_name);
        END IF;
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
            EXECUTE format('REVOKE ALL ON TABLE public.%I FROM authenticated', table_name);
        END IF;
    END LOOP;
END;
$$;
