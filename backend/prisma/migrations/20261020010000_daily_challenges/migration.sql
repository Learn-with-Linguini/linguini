BEGIN;

-- One row per lesson session started from a day's challenge. Only the first
-- session a learner completes during that UTC day counts.
CREATE TABLE public.daily_challenge_entries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    challenge_day DATE NOT NULL,
    scene_key VARCHAR(40) NOT NULL,
    user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE ON UPDATE CASCADE,
    session_id UUID NOT NULL UNIQUE REFERENCES public.sessions(id) ON DELETE CASCADE ON UPDATE CASCADE,
    completed_at TIMESTAMPTZ(6),
    created_at TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE UNIQUE INDEX daily_challenge_entries_one_completion
    ON public.daily_challenge_entries(user_id, challenge_day) WHERE completed_at IS NOT NULL;
CREATE INDEX daily_challenge_entries_day_idx
    ON public.daily_challenge_entries(challenge_day, completed_at);
CREATE INDEX daily_challenge_entries_user_day_idx
    ON public.daily_challenge_entries(user_id, challenge_day);

-- Words a learner found for a day, snapshotted at completion and normalized by label_key.
CREATE TABLE public.daily_challenge_finds (
    challenge_day DATE NOT NULL,
    user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE ON UPDATE CASCADE,
    label_key TEXT NOT NULL CHECK (length(label_key) BETWEEN 1 AND 200),
    label TEXT NOT NULL,
    created_at TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (challenge_day, user_id, label_key)
);
CREATE INDEX daily_challenge_finds_day_label_idx
    ON public.daily_challenge_finds(challenge_day, label_key);

-- A settled day has paid its rank bonuses and accepts no further completions.
CREATE TABLE public.daily_challenge_settlements (
    challenge_day DATE PRIMARY KEY,
    participant_count INTEGER NOT NULL CHECK (participant_count >= 0),
    policy_version VARCHAR(40) NOT NULL,
    settled_at TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP
);

DO $$
DECLARE t TEXT;
BEGIN
    FOREACH t IN ARRAY ARRAY['daily_challenge_entries', 'daily_challenge_finds', 'daily_challenge_settlements'] LOOP
        EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', t);
        EXECUTE format('REVOKE ALL ON public.%I FROM PUBLIC', t);
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
            EXECUTE format('REVOKE ALL ON public.%I FROM anon', t);
        END IF;
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
            EXECUTE format('REVOKE ALL ON public.%I FROM authenticated', t);
        END IF;
    END LOOP;
END $$;

COMMIT;
