BEGIN;

ALTER TABLE public.vocabulary_encounters
    DROP CONSTRAINT vocabulary_encounters_session_owner_fkey,
    DROP CONSTRAINT vocabulary_encounters_task_session_fkey,
    ADD CONSTRAINT vocabulary_encounters_session_owner_fkey
        FOREIGN KEY (session_id, user_id) REFERENCES public.sessions(id, user_id)
        ON DELETE CASCADE ON UPDATE NO ACTION DEFERRABLE INITIALLY DEFERRED,
    ADD CONSTRAINT vocabulary_encounters_task_session_fkey
        FOREIGN KEY (session_task_id, session_id) REFERENCES public.session_tasks(id, session_id)
        ON DELETE CASCADE ON UPDATE NO ACTION DEFERRABLE INITIALLY DEFERRED;

-- Journal text and word highlights outlive the practice that first introduced a word.
ALTER TABLE public.journal_word_mentions
    DROP CONSTRAINT journal_word_mentions_source_encounter_id_fkey,
    ADD CONSTRAINT journal_word_mentions_source_encounter_id_fkey
        FOREIGN KEY (source_encounter_id) REFERENCES public.vocabulary_encounters(id)
        ON DELETE SET NULL ON UPDATE CASCADE;

-- These counts are cached on a shared per-user word record, not owned by one session.
CREATE FUNCTION public.refresh_progress_after_encounter_delete() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE exposures INTEGER; correct INTEGER; first_seen TIMESTAMPTZ; last_practice TIMESTAMPTZ;
BEGIN
    -- Serialize updates with the normal encounter writer's progress update.
    PERFORM 1 FROM public.user_vocabulary_progress
        WHERE user_id=OLD.user_id AND vocabulary_item_id=OLD.vocabulary_item_id FOR UPDATE;
    IF NOT FOUND THEN RETURN OLD; END IF;
    SELECT count(*), count(*) FILTER (WHERE outcome='correct'), min(occurred_at),
           max(occurred_at) FILTER (WHERE encounter_type <> 'introduced')
      INTO exposures, correct, first_seen, last_practice
      FROM public.vocabulary_encounters
      WHERE user_id=OLD.user_id AND vocabulary_item_id=OLD.vocabulary_item_id;
    UPDATE public.user_vocabulary_progress
       SET exposure_count=exposures, correct_attempt_count=correct,
           first_learned_at=first_seen, last_practised_at=last_practice,
           status=CASE WHEN exposures=0 THEN 'new' ELSE status END,
           mastery_score=CASE WHEN exposures=0 THEN 0 ELSE mastery_score END
       WHERE user_id=OLD.user_id AND vocabulary_item_id=OLD.vocabulary_item_id;
    RETURN OLD;
END;
$$;

CREATE TRIGGER vocabulary_encounters_refresh_after_delete
AFTER DELETE ON public.vocabulary_encounters
FOR EACH ROW EXECUTE FUNCTION public.refresh_progress_after_encounter_delete();

COMMIT;
