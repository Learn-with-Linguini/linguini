ALTER TABLE public.users
ADD COLUMN IF NOT EXISTS tier VARCHAR(16) NOT NULL DEFAULT 'beta';

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'users_tier_valid'
          AND conrelid = 'public.users'::regclass
    ) THEN
        ALTER TABLE public.users
        ADD CONSTRAINT users_tier_valid CHECK (tier IN ('beta', 'free', 'plus'));
    END IF;
END
$$;
