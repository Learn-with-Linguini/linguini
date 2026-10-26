BEGIN;

-- These tables are accessed through the API's server-side database role.
-- Browser roles must not read survey contact details, placement answers or
-- answer keys through the Supabase Data API.
ALTER TABLE public.user_surveys ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.onboarding_placement_questions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.onboarding_placement_attempts ENABLE ROW LEVEL SECURITY;

-- xp_events already has RLS. Revoke its table privileges as well: RLS does
-- not protect operations such as TRUNCATE.
REVOKE ALL ON TABLE
    public.user_surveys,
    public.onboarding_placement_questions,
    public.onboarding_placement_attempts,
    public.xp_events
FROM PUBLIC;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
        REVOKE ALL ON TABLE
            public.user_surveys,
            public.onboarding_placement_questions,
            public.onboarding_placement_attempts,
            public.xp_events
        FROM anon;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
        REVOKE ALL ON TABLE
            public.user_surveys,
            public.onboarding_placement_questions,
            public.onboarding_placement_attempts,
            public.xp_events
        FROM authenticated;
    END IF;
END $$;

COMMIT;
