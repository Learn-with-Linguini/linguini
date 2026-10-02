-- Images are identified by media_asset_id; the illustration selector is unused.
-- Earlier migrations retain art for their legacy journal-media backfill.
ALTER TABLE public.preloaded_scenes DROP COLUMN art;
