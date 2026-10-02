BEGIN;
LOCK TABLE public.journals, public.journal_media IN SHARE ROW EXCLUSIVE MODE;

-- Preserve legacy selections on installations that have not been backfilled.
-- Refuse ambiguous/missing mappings instead of silently discarding a selection.
DO $$
BEGIN
    IF EXISTS (
        SELECT j.id FROM public.journals j
        JOIN public.language_profiles p ON p.id = j.language_profile_id
        LEFT JOIN public.preloaded_scenes s ON s.art = j.art
            AND lower(s.language_code) = lower(p.target_language_code)
        WHERE NOT EXISTS (SELECT 1 FROM public.journal_media m WHERE m.journal_id = j.id)
        GROUP BY j.id HAVING count(DISTINCT s.media_asset_id) <> 1
    ) THEN
        RAISE EXCEPTION 'Backfill journal_media for journals with missing or ambiguous scene matches before removing art';
    END IF;
END $$;

INSERT INTO public.journal_media (journal_id, media_asset_id, display_order)
SELECT j.id, (array_agg(DISTINCT s.media_asset_id))[1], 0
FROM public.journals j
JOIN public.language_profiles p ON p.id = j.language_profile_id
JOIN public.preloaded_scenes s ON s.art = j.art
    AND lower(s.language_code) = lower(p.target_language_code)
WHERE NOT EXISTS (SELECT 1 FROM public.journal_media m WHERE m.journal_id = j.id)
GROUP BY j.id;

ALTER TABLE public.journals DROP COLUMN art;
COMMIT;
