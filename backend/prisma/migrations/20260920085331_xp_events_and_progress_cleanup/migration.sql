BEGIN;
CREATE TABLE public.xp_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE ON UPDATE CASCADE,
    language_profile_id UUID REFERENCES public.language_profiles(id) ON DELETE CASCADE ON UPDATE CASCADE,
    session_id UUID REFERENCES public.sessions(id) ON DELETE SET NULL ON UPDATE CASCADE,
    event_type VARCHAR(20) NOT NULL CHECK (event_type IN
        ('taskCompleted','ispyCorrect','sessionCompleted','perfectSession','journalEntry','legacyBackfill')),
    amount INTEGER NOT NULL,
    idempotency_key TEXT NOT NULL,
    occurred_at TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT xp_events_user_id_idempotency_key_key UNIQUE(user_id,idempotency_key)
);
CREATE INDEX xp_events_user_id_idx ON public.xp_events(user_id);
CREATE INDEX xp_events_session_id_idx ON public.xp_events(session_id);
ALTER TABLE public.xp_events ENABLE ROW LEVEL SECURITY;

-- Preserve historical XP: each (user, language profile) keeps its past awards
-- as one legacy event; encounters without a resolvable profile land on a
-- per-user NULL-profile row so the unfiltered total stays exact.
INSERT INTO public.xp_events (user_id, language_profile_id, event_type, amount, idempotency_key)
SELECT encounters.user_id,
       encounters.profile_id,
       'legacyBackfill',
       COUNT(*) * 5,
       'legacy:' || COALESCE(encounters.profile_id::text, 'none')
FROM (
    SELECT e.user_id, s.language_profile_id AS profile_id
    FROM public.vocabulary_encounters e
    LEFT JOIN public.sessions s ON s.id = e.session_id
) AS encounters
GROUP BY encounters.user_id, encounters.profile_id;

-- scene_id/topic are now derived from each word's latest encounter scene.
ALTER TABLE public.user_vocabulary_progress DROP COLUMN scene_id, DROP COLUMN topic;
COMMIT;
