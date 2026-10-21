BEGIN;

DROP INDEX public.room_members_one_active_user;
CREATE INDEX room_members_active_user_idx ON public.room_members(user_id) WHERE active;
CREATE INDEX learning_rooms_updated_idx ON public.learning_rooms(updated_at DESC);

CREATE TABLE public.friendships (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_low_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE ON UPDATE CASCADE,
    user_high_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE ON UPDATE CASCADE,
    created_at TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_low_id, user_high_id),
    CHECK (user_low_id < user_high_id)
);
CREATE INDEX friendships_high_user_idx ON public.friendships(user_high_id);

CREATE TABLE public.friend_invitations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE ON UPDATE CASCADE,
    command_id UUID NOT NULL,
    invite_code VARCHAR(64) NOT NULL,
    invite_hash VARCHAR(64) NOT NULL UNIQUE,
    expires_at TIMESTAMPTZ(6) NOT NULL,
    accepted_user_id UUID REFERENCES public.users(id) ON DELETE SET NULL ON UPDATE CASCADE,
    accepted_command_id UUID,
    accepted_at TIMESTAMPTZ(6),
    created_at TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(owner_user_id, command_id),
    UNIQUE(accepted_user_id, accepted_command_id),
    CHECK (invite_code ~ '^[0-9a-f]{64}$' AND invite_hash = encode(sha256(convert_to(invite_code, 'UTF8')), 'hex')),
    CHECK (expires_at > created_at),
    CHECK (accepted_user_id IS NULL OR accepted_user_id <> owner_user_id)
);
CREATE INDEX friend_invitations_owner_created_idx ON public.friend_invitations(owner_user_id, created_at);

DO $$ DECLARE table_name text; BEGIN
    FOREACH table_name IN ARRAY ARRAY['friendships', 'friend_invitations'] LOOP
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
