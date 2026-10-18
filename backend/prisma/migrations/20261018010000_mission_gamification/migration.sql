BEGIN;

-- Preserve old balances and transactions while allowing the versioned question rewards.
ALTER TABLE public.game_resource_events DROP CONSTRAINT game_resource_events_check;
ALTER TABLE public.game_resource_events ADD CONSTRAINT game_resource_events_deltas_check CHECK (
    (kind = 'sauceSpend' AND sauce_delta = -1 AND basil_delta = 0 AND sauce_period_start IS NOT NULL)
    OR (kind = 'sauceRefund' AND sauce_delta = 1 AND basil_delta = 0 AND sauce_period_start IS NOT NULL)
    OR (kind = 'basilEarned' AND sauce_delta = 0 AND basil_delta > 0)
    OR (kind = 'appearance' AND sauce_delta = 0 AND basil_delta IN (-20, 0))
);

CREATE TABLE public.learning_question_events (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    language_profile_id UUID NOT NULL REFERENCES public.language_profiles(id) ON DELETE CASCADE,
    session_id UUID NOT NULL REFERENCES public.sessions(id) ON DELETE CASCADE,
    task_id UUID NOT NULL,
    question_id VARCHAR(100) NOT NULL,
    answer TEXT NOT NULL,
    is_correct BOOLEAN NOT NULL,
    basil_earned INTEGER NOT NULL CHECK (basil_earned IN (0, 5, 10)),
    policy_version VARCHAR(40) NOT NULL,
    mission_id VARCHAR(3),
    practice_level VARCHAR(2),
    content_version INTEGER,
    outcome JSONB NOT NULL,
    created_at TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, task_id, question_id)
);
CREATE INDEX learning_question_events_session_idx ON public.learning_question_events(session_id);
CREATE INDEX learning_question_events_profile_idx ON public.learning_question_events(language_profile_id);

CREATE TABLE public.mission_batch_results (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    language_profile_id UUID NOT NULL REFERENCES public.language_profiles(id) ON DELETE CASCADE,
    session_id UUID NOT NULL REFERENCES public.sessions(id) ON DELETE CASCADE,
    mission_id VARCHAR(3) NOT NULL,
    practice_level VARCHAR(2) NOT NULL,
    content_version INTEGER NOT NULL,
    policy_version VARCHAR(40) NOT NULL,
    successful BOOLEAN NOT NULL,
    lower_assistance BOOLEAN NOT NULL,
    photo_identity VARCHAR(160),
    scenario_identity VARCHAR(64) NOT NULL,
    evidence JSONB NOT NULL,
    created_at TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, session_id, mission_id, practice_level, content_version)
);
CREATE INDEX mission_batch_results_profile_idx ON public.mission_batch_results(language_profile_id, mission_id);

CREATE TABLE public.learning_photo_identities (
    media_asset_id UUID PRIMARY KEY REFERENCES public.media_assets(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    content_hash VARCHAR(64) NOT NULL CHECK (content_hash ~ '^[0-9a-f]{64}$'),
    created_at TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX learning_photo_identities_owner_hash_idx ON public.learning_photo_identities(user_id, content_hash);

DO $$ DECLARE table_name text; BEGIN
    FOREACH table_name IN ARRAY ARRAY['learning_question_events', 'mission_batch_results', 'learning_photo_identities'] LOOP
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
