BEGIN;
CREATE TABLE public.game_accounts (
    user_id UUID PRIMARY KEY REFERENCES public.users(id) ON DELETE CASCADE ON UPDATE CASCADE,
    sauce_remaining INTEGER NOT NULL CHECK (sauce_remaining >= 0),
    sauce_capacity INTEGER NOT NULL CHECK (sauce_capacity BETWEEN 1 AND 100),
    sauce_period_start TIMESTAMPTZ(6) NOT NULL,
    sauce_refills_at TIMESTAMPTZ(6) NOT NULL,
    basil_balance INTEGER NOT NULL DEFAULT 0 CHECK (basil_balance >= 0),
    appearance VARCHAR(10) NOT NULL DEFAULT 'default' CHECK (appearance IN ('default','herb','pasta')),
    owned_appearances JSONB NOT NULL DEFAULT '["default"]'::jsonb,
    created_at TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (sauce_remaining <= sauce_capacity),
    CHECK (sauce_refills_at > sauce_period_start),
    CHECK (jsonb_typeof(owned_appearances) = 'array' AND owned_appearances ? 'default'),
    CHECK (owned_appearances ? appearance)
);
CREATE TRIGGER game_accounts_updated_at BEFORE UPDATE ON public.game_accounts
FOR EACH ROW EXECUTE FUNCTION public.set_user_updated_at();
CREATE TABLE public.game_resource_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE ON UPDATE CASCADE,
    source_key TEXT NOT NULL CHECK (length(source_key) BETWEEN 1 AND 500),
    kind VARCHAR(20) NOT NULL CHECK (kind IN ('sauceSpend','sauceRefund','basilEarned','appearance')),
    sauce_delta INTEGER NOT NULL DEFAULT 0,
    basil_delta INTEGER NOT NULL DEFAULT 0,
    sauce_period_start TIMESTAMPTZ(6),
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT game_resource_events_source_key UNIQUE (user_id, source_key),
    CHECK ((kind = 'sauceSpend' AND sauce_delta = -1 AND basil_delta = 0 AND sauce_period_start IS NOT NULL)
        OR (kind = 'sauceRefund' AND sauce_delta = 1 AND basil_delta = 0 AND sauce_period_start IS NOT NULL)
        OR (kind = 'basilEarned' AND sauce_delta = 0 AND basil_delta = 1)
        OR (kind = 'appearance' AND sauce_delta = 0 AND basil_delta IN (-20,0)))
);
CREATE INDEX game_resource_events_user_time_idx ON public.game_resource_events(user_id, created_at);
ALTER TABLE public.game_accounts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.game_resource_events ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.game_accounts, public.game_resource_events FROM PUBLIC;
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
        REVOKE ALL ON public.game_accounts, public.game_resource_events FROM anon;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
        REVOKE ALL ON public.game_accounts, public.game_resource_events FROM authenticated;
    END IF;
END $$;
COMMIT;
