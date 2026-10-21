BEGIN;
CREATE TABLE public.learning_rooms (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    host_user_id UUID REFERENCES public.users(id) ON DELETE SET NULL ON UPDATE CASCADE,
    source_language_code VARCHAR(35) NOT NULL,
    target_language_code VARCHAR(35) NOT NULL,
    proficiency_level VARCHAR(2) NOT NULL CHECK (proficiency_level IN ('A1','A2')),
    status VARCHAR(16) NOT NULL CHECK (status IN ('lobby','playing','completed','ended','expired')),
    revision INTEGER NOT NULL DEFAULT 0 CHECK (revision >= 0),
    invite_hash VARCHAR(64) NOT NULL UNIQUE,
    invite_expires_at TIMESTAMPTZ(6) NOT NULL,
    expires_at TIMESTAMPTZ(6) NOT NULL,
    ended_at TIMESTAMPTZ(6),
    created_at TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (expires_at > created_at)
);
CREATE TABLE public.room_members (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    room_id UUID NOT NULL REFERENCES public.learning_rooms(id) ON DELETE CASCADE ON UPDATE CASCADE,
    user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE ON UPDATE CASCADE,
    language_profile_id UUID REFERENCES public.language_profiles(id) ON DELETE SET NULL ON UPDATE CASCADE,
    seat INTEGER NOT NULL CHECK (seat IN (0,1)),
    ready BOOLEAN NOT NULL DEFAULT false,
    active BOOLEAN NOT NULL DEFAULT true,
    joined_at TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(room_id,user_id), UNIQUE(room_id,seat)
);
CREATE UNIQUE INDEX room_members_one_active_user ON public.room_members(user_id) WHERE active;
CREATE INDEX room_members_user_joined_idx ON public.room_members(user_id,joined_at);
CREATE TABLE public.room_photos (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    room_id UUID NOT NULL REFERENCES public.learning_rooms(id) ON DELETE CASCADE ON UPDATE CASCADE,
    owner_user_id UUID REFERENCES public.users(id) ON DELETE SET NULL ON UPDATE CASCADE,
    media_asset_id UUID REFERENCES public.media_assets(id) ON DELETE SET NULL ON UPDATE CASCADE,
    status VARCHAR(20) NOT NULL CHECK (status IN ('queued','analyzing','awaitingReview','preparing','ready','failed')),
    moderation_passed BOOLEAN NOT NULL DEFAULT false,
    content_hash VARCHAR(64),
    analysis JSONB, review JSONB, pack JSONB,
    processing_claim_id UUID,
    claim_expires_at TIMESTAMPTZ(6),
    analysis_attempts INTEGER NOT NULL DEFAULT 0 CHECK (analysis_attempts BETWEEN 0 AND 3),
    preparation_attempts INTEGER NOT NULL DEFAULT 0 CHECK (preparation_attempts BETWEEN 0 AND 3),
    error_code VARCHAR(60), error_message VARCHAR(300),
    retryable BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(room_id,media_asset_id)
);
CREATE INDEX room_photos_owner_idx ON public.room_photos(owner_user_id);
CREATE INDEX room_photos_media_idx ON public.room_photos(media_asset_id);
CREATE UNIQUE INDEX room_photos_content_key ON public.room_photos(room_id,content_hash)
WHERE content_hash IS NOT NULL;
CREATE TABLE public.room_turns (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    room_id UUID NOT NULL REFERENCES public.learning_rooms(id) ON DELETE CASCADE ON UPDATE CASCADE,
    photo_id UUID REFERENCES public.room_photos(id) ON DELETE SET NULL ON UPDATE CASCADE,
    turn_index INTEGER NOT NULL CHECK (turn_index BETWEEN 0 AND 3),
    sender_user_id UUID REFERENCES public.users(id) ON DELETE SET NULL ON UPDATE CASCADE,
    guesser_user_id UUID REFERENCES public.users(id) ON DELETE SET NULL ON UPDATE CASCADE,
    phase VARCHAR(16) NOT NULL CHECK (phase IN ('compose','guess','reveal','closed')),
    target_object_key VARCHAR(100), clue_option_id VARCHAR(100), clue TEXT,
    guessed_object_keys JSONB NOT NULL DEFAULT '[]'::jsonb,
    is_correct BOOLEAN,
    created_at TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMPTZ(6),
    UNIQUE(room_id,turn_index), UNIQUE(room_id,photo_id), UNIQUE(id,room_id),
    CHECK (sender_user_id IS NULL OR guesser_user_id IS NULL OR sender_user_id <> guesser_user_id),
    CHECK (jsonb_typeof(guessed_object_keys) = 'array' AND jsonb_array_length(guessed_object_keys) <= 2)
);
CREATE TABLE public.room_commands (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    room_id UUID NOT NULL REFERENCES public.learning_rooms(id) ON DELETE CASCADE ON UPDATE CASCADE,
    user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE ON UPDATE CASCADE,
    command_id UUID NOT NULL,
    kind VARCHAR(80) NOT NULL,
    fingerprint VARCHAR(64) NOT NULL,
    created_at TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(room_id,user_id,command_id)
);
CREATE TABLE public.room_contributions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    room_id UUID NOT NULL REFERENCES public.learning_rooms(id) ON DELETE CASCADE ON UPDATE CASCADE,
    turn_id UUID NOT NULL,
    user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE ON UPDATE CASCADE,
    clue_sent BOOLEAN NOT NULL DEFAULT false,
    guess_count INTEGER NOT NULL DEFAULT 0 CHECK (guess_count BETWEEN 0 AND 2),
    correct_guess BOOLEAN NOT NULL DEFAULT false,
    acknowledged BOOLEAN NOT NULL DEFAULT false,
    basil_earned INTEGER NOT NULL DEFAULT 0 CHECK (basil_earned BETWEEN 0 AND 1),
    xp_earned INTEGER NOT NULL DEFAULT 0 CHECK (xp_earned >= 0),
    created_at TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(turn_id,room_id) REFERENCES public.room_turns(id,room_id) ON DELETE CASCADE ON UPDATE CASCADE,
    UNIQUE(turn_id,user_id)
);
CREATE INDEX room_contributions_user_idx ON public.room_contributions(user_id);
DO $$ DECLARE table_name text; BEGIN
    FOREACH table_name IN ARRAY ARRAY['learning_rooms','room_members','room_photos','room_turns','room_commands','room_contributions'] LOOP
        EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', table_name);
        EXECUTE format('REVOKE ALL ON public.%I FROM PUBLIC', table_name);
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
            EXECUTE format('REVOKE ALL ON public.%I FROM anon', table_name);
        END IF;
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
            EXECUTE format('REVOKE ALL ON public.%I FROM authenticated', table_name);
        END IF;
    END LOOP;
    FOREACH table_name IN ARRAY ARRAY['learning_rooms','room_photos','room_contributions'] LOOP
        EXECUTE format('CREATE TRIGGER %I BEFORE UPDATE ON public.%I FOR EACH ROW EXECUTE FUNCTION public.set_user_updated_at()', table_name || '_updated_at', table_name);
    END LOOP;
END $$;
COMMIT;
