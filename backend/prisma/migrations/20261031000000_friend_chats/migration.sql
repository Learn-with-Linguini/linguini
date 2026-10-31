BEGIN;

CREATE TABLE public.friend_chats (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    creator_user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE ON UPDATE CASCADE,
    partner_user_id UUID REFERENCES public.users(id) ON DELETE CASCADE ON UPDATE CASCADE,
    creator_profile JSONB NOT NULL,
    partner_profile JSONB,
    target_language_code VARCHAR(35) NOT NULL,
    status VARCHAR(12) NOT NULL CHECK (status IN ('waiting','active','left','blocked')),
    revision INTEGER NOT NULL DEFAULT 0 CHECK (revision >= 0),
    invite_hash VARCHAR(64) NOT NULL UNIQUE,
    invite_status VARCHAR(12) NOT NULL CHECK (invite_status IN ('open','accepted','revoked')),
    invite_expires_at TIMESTAMPTZ(6) NOT NULL,
    created_at TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (creator_user_id <> partner_user_id),
    CHECK ((partner_user_id IS NULL) = (partner_profile IS NULL)),
    CHECK (status <> 'active' OR partner_user_id IS NOT NULL)
);
CREATE INDEX friend_chats_creator_updated_idx ON public.friend_chats(creator_user_id, updated_at DESC);
CREATE INDEX friend_chats_partner_updated_idx ON public.friend_chats(partner_user_id, updated_at DESC);

CREATE TABLE public.friend_chat_rounds (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chat_id UUID NOT NULL REFERENCES public.friend_chats(id) ON DELETE CASCADE ON UPDATE CASCADE,
    sender_user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE ON UPDATE CASCADE,
    media_asset_id UUID REFERENCES public.media_assets(id) ON DELETE SET NULL ON UPDATE CASCADE,
    status VARCHAR(24) NOT NULL CHECK (status IN ('selectingTarget','composingClue','awaitingGuess','awaitingFollowUp','completed','cancelled')),
    photo_status VARCHAR(12) NOT NULL CHECK (photo_status IN ('analyzing','ready','failed')),
    content JSONB,
    target JSONB,
    clue_options JSONB NOT NULL DEFAULT '[]',
    claim_id UUID,
    claim_expires_at TIMESTAMPTZ(6),
    analysis_attempts INTEGER NOT NULL DEFAULT 0 CHECK (analysis_attempts BETWEEN 0 AND 3),
    retryable BOOLEAN NOT NULL DEFAULT false,
    error VARCHAR(300),
    created_at TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMPTZ(6),
    UNIQUE(id, chat_id),
    CHECK ((status IN ('completed','cancelled')) = (completed_at IS NOT NULL)),
    CHECK (jsonb_typeof(clue_options) = 'array'),
    CHECK ((claim_id IS NULL) = (claim_expires_at IS NULL))
);
CREATE UNIQUE INDEX friend_chat_one_active_round ON public.friend_chat_rounds(chat_id)
    WHERE status NOT IN ('completed','cancelled');
CREATE INDEX friend_chat_rounds_history_idx ON public.friend_chat_rounds(chat_id, created_at, id);
CREATE INDEX friend_chat_rounds_sender_idx ON public.friend_chat_rounds(sender_user_id);
CREATE INDEX friend_chat_rounds_media_idx ON public.friend_chat_rounds(media_asset_id);

CREATE TABLE public.friend_chat_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chat_id UUID NOT NULL REFERENCES public.friend_chats(id) ON DELETE CASCADE ON UPDATE CASCADE,
    round_id UUID,
    sender_user_id UUID REFERENCES public.users(id) ON DELETE SET NULL ON UPDATE CASCADE,
    type VARCHAR(24) NOT NULL CHECK (type IN ('system','clue','followUpClue','guess','incorrectResult','correctResult','reveal')),
    text TEXT,
    x DOUBLE PRECISION CHECK (x BETWEEN 0 AND 1),
    y DOUBLE PRECISION CHECK (y BETWEEN 0 AND 1),
    is_correct INTEGER CHECK (is_correct IN (0,1)),
    created_at TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(round_id,chat_id) REFERENCES public.friend_chat_rounds(id,chat_id) ON DELETE CASCADE ON UPDATE CASCADE,
    CHECK ((x IS NULL) = (y IS NULL)),
    CHECK ((type = 'guess') = (x IS NOT NULL))
);
CREATE INDEX friend_chat_messages_timeline_idx ON public.friend_chat_messages(chat_id, created_at, id);

CREATE TABLE public.friend_chat_commands (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chat_id UUID NOT NULL REFERENCES public.friend_chats(id) ON DELETE CASCADE ON UPDATE CASCADE,
    user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE ON UPDATE CASCADE,
    command_id UUID NOT NULL,
    kind VARCHAR(100) NOT NULL,
    fingerprint VARCHAR(64) NOT NULL,
    result JSONB,
    created_at TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(chat_id,user_id,command_id)
);

CREATE TABLE public.user_blocks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE ON UPDATE CASCADE,
    blocked_user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE ON UPDATE CASCADE,
    created_at TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id,blocked_user_id),
    CHECK (user_id <> blocked_user_id)
);
CREATE INDEX user_blocks_blocked_user_idx ON public.user_blocks(blocked_user_id);

CREATE TABLE public.friend_chat_reports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chat_id UUID NOT NULL REFERENCES public.friend_chats(id) ON DELETE CASCADE ON UPDATE CASCADE,
    reporter_user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE ON UPDATE CASCADE,
    reported_user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE ON UPDATE CASCADE,
    reason VARCHAR(500) NOT NULL,
    created_at TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (reporter_user_id <> reported_user_id)
);

CREATE TABLE public.friend_chat_assistance (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    round_id UUID NOT NULL REFERENCES public.friend_chat_rounds(id) ON DELETE CASCADE ON UPDATE CASCADE,
    user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE ON UPDATE CASCADE,
    created_at TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX friend_chat_assistance_round_idx ON public.friend_chat_assistance(round_id);

DO $$ DECLARE table_name text; BEGIN
    FOREACH table_name IN ARRAY ARRAY['friend_chats','friend_chat_rounds','friend_chat_messages','friend_chat_commands','user_blocks','friend_chat_reports','friend_chat_assistance'] LOOP
        EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', table_name);
        EXECUTE format('REVOKE ALL ON public.%I FROM PUBLIC', table_name);
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
            EXECUTE format('REVOKE ALL ON public.%I FROM anon', table_name);
        END IF;
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
            EXECUTE format('REVOKE ALL ON public.%I FROM authenticated', table_name);
        END IF;
    END LOOP;
END $$;

COMMIT;
