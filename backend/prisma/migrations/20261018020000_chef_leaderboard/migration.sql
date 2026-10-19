BEGIN;

CREATE INDEX game_resource_events_daily_basil_idx
    ON public.game_resource_events(kind, created_at, user_id);

CREATE TABLE public.chef_leaderboard_preferences (
    user_id UUID PRIMARY KEY REFERENCES public.users(id) ON DELETE CASCADE ON UPDATE CASCADE,
    participating BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TRIGGER chef_leaderboard_preferences_updated_at
BEFORE UPDATE ON public.chef_leaderboard_preferences
FOR EACH ROW EXECUTE FUNCTION public.set_user_updated_at();

ALTER TABLE public.chef_leaderboard_preferences ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.chef_leaderboard_preferences FROM PUBLIC;
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
        REVOKE ALL ON public.chef_leaderboard_preferences FROM anon;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
        REVOKE ALL ON public.chef_leaderboard_preferences FROM authenticated;
    END IF;
END $$;

COMMIT;
