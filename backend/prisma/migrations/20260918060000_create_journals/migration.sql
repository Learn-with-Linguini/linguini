CREATE TABLE public.journals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    language_profile_id UUID NOT NULL,
    local_date DATE NOT NULL,
    timezone TEXT NOT NULL,
    title VARCHAR(200) NOT NULL DEFAULT 'Today''s entry',
    art VARCHAR(7) NOT NULL DEFAULT 'street' CHECK (art IN ('street','cafe','market','bedroom','kitchen','park')),
    selected_words JSONB NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(selected_words)='array'),
    status VARCHAR(9) NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','completed')),
    current_revision_id UUID,
    audio_media_asset_id UUID REFERENCES public.media_assets(id) ON DELETE RESTRICT ON UPDATE CASCADE,
    completed_at TIMESTAMPTZ(6),
    created_at TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT journals_user_id_local_date_key UNIQUE(user_id,local_date),
    CONSTRAINT journals_profile_owner_fkey FOREIGN KEY(language_profile_id,user_id)
        REFERENCES public.language_profiles(id,user_id) ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT journals_completion CHECK (status <> 'completed' OR (completed_at IS NOT NULL AND current_revision_id IS NOT NULL))
);
CREATE INDEX journals_language_profile_id_user_id_idx ON public.journals(language_profile_id,user_id);
CREATE INDEX journals_audio_media_asset_id_idx ON public.journals(audio_media_asset_id);
CREATE INDEX journals_current_revision_id_id_idx ON public.journals(current_revision_id,id);

CREATE TABLE public.journal_media (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    journal_id UUID NOT NULL REFERENCES public.journals(id) ON DELETE CASCADE ON UPDATE CASCADE,
    media_asset_id UUID NOT NULL REFERENCES public.media_assets(id) ON DELETE RESTRICT ON UPDATE CASCADE,
    display_order INTEGER NOT NULL CHECK (display_order >= 0),
    caption VARCHAR(1000),
    created_at TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT journal_media_journal_id_media_asset_id_key UNIQUE(journal_id,media_asset_id),
    CONSTRAINT journal_media_journal_id_display_order_key UNIQUE(journal_id,display_order)
);
CREATE INDEX journal_media_media_asset_id_idx ON public.journal_media(media_asset_id);

CREATE TABLE public.journal_revisions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    journal_id UUID NOT NULL REFERENCES public.journals(id) ON DELETE CASCADE ON UPDATE CASCADE,
    revision_number INTEGER NOT NULL CHECK (revision_number >= 1),
    content VARCHAR(20000) NOT NULL CHECK (length(btrim(content)) > 0),
    created_by VARCHAR(6) NOT NULL CHECK (created_by IN ('user','ai','merged')),
    created_at TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT journal_revisions_journal_id_revision_number_key UNIQUE(journal_id,revision_number),
    CONSTRAINT journal_revisions_id_journal_id_key UNIQUE(id,journal_id)
);
-- Journal and its first revision can be inserted in a single transaction.
ALTER TABLE public.journals ADD CONSTRAINT journals_current_revision_fkey
    FOREIGN KEY(current_revision_id,id) REFERENCES public.journal_revisions(id,journal_id)
    ON DELETE NO ACTION ON UPDATE NO ACTION DEFERRABLE INITIALLY DEFERRED;

CREATE TABLE public.journal_suggestions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    journal_id UUID NOT NULL,
    base_revision_id UUID NOT NULL,
    suggestion_type VARCHAR(10) NOT NULL CHECK (suggestion_type IN ('grammar','spelling','syntax','vocabulary','clarity')),
    start_offset INTEGER NOT NULL CHECK (start_offset >= 0),
    end_offset INTEGER NOT NULL CHECK (end_offset > start_offset),
    original_text TEXT NOT NULL,
    suggested_text TEXT NOT NULL CHECK (length(btrim(suggested_text)) > 0),
    explanation TEXT NOT NULL CHECK (length(btrim(explanation)) > 0),
    status VARCHAR(8) NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','accepted','rejected')),
    created_at TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT journal_suggestions_base_revision_fkey FOREIGN KEY(base_revision_id,journal_id)
        REFERENCES public.journal_revisions(id,journal_id) ON DELETE CASCADE ON UPDATE CASCADE
);
CREATE INDEX journal_suggestions_journal_id_status_idx ON public.journal_suggestions(journal_id,status);
CREATE INDEX journal_suggestions_base_revision_id_journal_id_idx ON public.journal_suggestions(base_revision_id,journal_id);

CREATE TABLE public.journal_word_mentions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    journal_revision_id UUID NOT NULL REFERENCES public.journal_revisions(id) ON DELETE CASCADE ON UPDATE CASCADE,
    vocabulary_item_id UUID NOT NULL REFERENCES public.vocabulary_items(id) ON DELETE RESTRICT ON UPDATE CASCADE,
    start_offset INTEGER NOT NULL CHECK (start_offset >= 0),
    end_offset INTEGER NOT NULL CHECK (end_offset > start_offset),
    matched_text TEXT NOT NULL CHECK (length(btrim(matched_text)) > 0),
    match_method VARCHAR(13) NOT NULL CHECK (match_method IN ('exact','inflected','semantic','userConfirmed')),
    source_encounter_id UUID REFERENCES public.vocabulary_encounters(id) ON DELETE NO ACTION ON UPDATE CASCADE,
    created_at TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT journal_word_mentions_occurrence_key UNIQUE(journal_revision_id,vocabulary_item_id,start_offset,end_offset)
);
CREATE INDEX journal_word_mentions_vocabulary_item_id_idx ON public.journal_word_mentions(vocabulary_item_id);
CREATE INDEX journal_word_mentions_source_encounter_id_idx ON public.journal_word_mentions(source_encounter_id);

CREATE FUNCTION public.check_journal() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE asset public.media_assets%ROWTYPE;
BEGIN
    IF TG_OP='UPDATE' AND (NEW.user_id,NEW.language_profile_id,NEW.local_date,NEW.timezone)
        IS DISTINCT FROM (OLD.user_id,OLD.language_profile_id,OLD.local_date,OLD.timezone) THEN
        RAISE EXCEPTION 'Journal identity is immutable' USING ERRCODE='23514';
    END IF;
    IF NOT EXISTS(SELECT 1 FROM pg_timezone_names WHERE name=NEW.timezone) THEN
        RAISE EXCEPTION 'Invalid journal timezone' USING ERRCODE='23514';
    END IF;
    IF jsonb_typeof(NEW.selected_words) <> 'array' OR EXISTS(
        SELECT 1 FROM jsonb_array_elements(NEW.selected_words) AS word
        WHERE jsonb_typeof(word) <> 'string' OR length(btrim(word #>> '{}'))=0) THEN
        RAISE EXCEPTION 'Selected words must be nonempty strings' USING ERRCODE='23514';
    END IF;
    IF NEW.audio_media_asset_id IS NOT NULL THEN
        SELECT * INTO asset FROM public.media_assets WHERE id=NEW.audio_media_asset_id FOR SHARE;
        IF FOUND AND (asset.media_type <> 'audio' OR asset.owner_user_id IS DISTINCT FROM NEW.user_id) THEN
            RAISE EXCEPTION 'Journal audio must belong to its user' USING ERRCODE='23514';
        END IF;
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER journals_validate BEFORE INSERT OR UPDATE ON public.journals
    FOR EACH ROW EXECUTE FUNCTION public.check_journal();

CREATE FUNCTION public.check_journal_media() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE asset public.media_assets%ROWTYPE; owner_id UUID;
BEGIN
    SELECT user_id INTO owner_id FROM public.journals WHERE id=NEW.journal_id;
    SELECT * INTO asset FROM public.media_assets WHERE id=NEW.media_asset_id FOR SHARE;
    IF FOUND AND (asset.media_type <> 'image' OR NOT(asset.source='preloaded' OR asset.owner_user_id IS NOT DISTINCT FROM owner_id)) THEN
        RAISE EXCEPTION 'Journal photo must be an owned or preloaded image' USING ERRCODE='23514';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER journal_media_validate BEFORE INSERT OR UPDATE ON public.journal_media
    FOR EACH ROW EXECUTE FUNCTION public.check_journal_media();

CREATE FUNCTION public.protect_journal_media() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF EXISTS(SELECT 1 FROM public.journals WHERE audio_media_asset_id=NEW.id
        AND (NEW.media_type <> 'audio' OR NEW.owner_user_id IS DISTINCT FROM user_id)) OR
       EXISTS(SELECT 1 FROM public.journal_media m JOIN public.journals j ON j.id=m.journal_id
        WHERE m.media_asset_id=NEW.id AND (NEW.media_type <> 'image' OR
            NOT(NEW.source='preloaded' OR NEW.owner_user_id IS NOT DISTINCT FROM j.user_id))) THEN
        RAISE EXCEPTION 'Media change would invalidate journal access' USING ERRCODE='23514';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER media_assets_journal_check BEFORE UPDATE OF media_type,source,owner_user_id ON public.media_assets
    FOR EACH ROW EXECUTE FUNCTION public.protect_journal_media();

-- Offsets are zero-based Unicode code points, with an exclusive end.
CREATE FUNCTION public.check_journal_annotation() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE revision public.journal_revisions%ROWTYPE; excerpt TEXT; owner_id UUID;
BEGIN
    IF TG_TABLE_NAME='journal_suggestions' THEN
        SELECT * INTO revision FROM public.journal_revisions WHERE id=NEW.base_revision_id;
        excerpt := NEW.original_text;
    ELSE
        SELECT * INTO revision FROM public.journal_revisions WHERE id=NEW.journal_revision_id;
        excerpt := NEW.matched_text;
    END IF;
    IF revision.id IS NOT NULL AND (NEW.end_offset > length(revision.content) OR
        substring(revision.content FROM NEW.start_offset+1 FOR NEW.end_offset-NEW.start_offset) <> excerpt) THEN
        RAISE EXCEPTION 'Annotation must match its revision text' USING ERRCODE='23514';
    END IF;
    IF TG_TABLE_NAME='journal_word_mentions' THEN
        IF NEW.source_encounter_id IS NOT NULL THEN
            SELECT user_id INTO owner_id FROM public.journals WHERE id=revision.journal_id;
            PERFORM 1 FROM public.vocabulary_encounters WHERE id=NEW.source_encounter_id
                AND user_id=owner_id AND vocabulary_item_id=NEW.vocabulary_item_id FOR SHARE;
            IF NOT FOUND THEN RAISE EXCEPTION 'Encounter must match journal owner and vocabulary' USING ERRCODE='23514'; END IF;
        END IF;
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER journal_suggestions_validate BEFORE INSERT OR UPDATE ON public.journal_suggestions
    FOR EACH ROW EXECUTE FUNCTION public.check_journal_annotation();
CREATE TRIGGER journal_word_mentions_validate BEFORE INSERT OR UPDATE ON public.journal_word_mentions
    FOR EACH ROW EXECUTE FUNCTION public.check_journal_annotation();

CREATE FUNCTION public.protect_journal_revision() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF (NEW.id,NEW.journal_id,NEW.revision_number,NEW.content,NEW.created_by,NEW.created_at)
        IS DISTINCT FROM (OLD.id,OLD.journal_id,OLD.revision_number,OLD.content,OLD.created_by,OLD.created_at) THEN
        RAISE EXCEPTION 'Revision history is immutable; create a new revision' USING ERRCODE='23514';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER journal_revisions_immutable BEFORE UPDATE ON public.journal_revisions
    FOR EACH ROW EXECUTE FUNCTION public.protect_journal_revision();

CREATE FUNCTION public.protect_mentioned_encounter() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF (NEW.user_id,NEW.vocabulary_item_id) IS DISTINCT FROM (OLD.user_id,OLD.vocabulary_item_id)
        AND EXISTS(SELECT 1 FROM public.journal_word_mentions WHERE source_encounter_id=OLD.id) THEN
        RAISE EXCEPTION 'Encounter change would invalidate journal mentions' USING ERRCODE='23514';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER vocabulary_encounters_journal_check BEFORE UPDATE OF user_id,vocabulary_item_id ON public.vocabulary_encounters
    FOR EACH ROW EXECUTE FUNCTION public.protect_mentioned_encounter();

DO $$
DECLARE table_name TEXT;
BEGIN
    FOREACH table_name IN ARRAY ARRAY['journals','journal_media','journal_revisions','journal_suggestions','journal_word_mentions'] LOOP
        EXECUTE format('CREATE TRIGGER %I BEFORE UPDATE ON public.%I FOR EACH ROW EXECUTE FUNCTION public.set_user_updated_at()',table_name || '_updated_at',table_name);
        EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY',table_name);
        EXECUTE format('REVOKE ALL ON TABLE public.%I FROM PUBLIC',table_name);
        IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='anon') THEN EXECUTE format('REVOKE ALL ON TABLE public.%I FROM anon',table_name); END IF;
        IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN EXECUTE format('REVOKE ALL ON TABLE public.%I FROM authenticated',table_name); END IF;
    END LOOP;
END;
$$;
