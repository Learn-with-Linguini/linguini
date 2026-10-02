BEGIN;

-- Never fabricate parent records or discard learner history during deployment.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM public.vocabulary_encounters e
        LEFT JOIN public.sessions s ON (s.id, s.user_id) = (e.session_id, e.user_id)
        LEFT JOIN public.session_tasks t ON (t.id, t.session_id) = (e.session_task_id, e.session_id)
        WHERE s.id IS NULL OR t.id IS NULL
    ) THEN
        RAISE EXCEPTION 'Vocabulary encounters contain missing or mismatched session/task references'
            USING HINT = 'Reconcile the existing encounter references before retrying this migration; no records have been deleted.';
    END IF;
END $$;

-- sessions(id,user_id) is already unique from the AI-run migration.
CREATE UNIQUE INDEX session_tasks_id_session_id_key ON public.session_tasks(id, session_id);
CREATE INDEX vocabulary_encounters_session_id_user_id_idx ON public.vocabulary_encounters(session_id, user_id);
CREATE INDEX vocabulary_encounters_session_task_id_session_id_idx ON public.vocabulary_encounters(session_task_id, session_id);

ALTER TABLE public.vocabulary_encounters
    ADD CONSTRAINT vocabulary_encounters_session_owner_fkey
        FOREIGN KEY (session_id, user_id) REFERENCES public.sessions(id, user_id)
        ON DELETE NO ACTION ON UPDATE NO ACTION DEFERRABLE INITIALLY DEFERRED,
    ADD CONSTRAINT vocabulary_encounters_task_session_fkey
        FOREIGN KEY (session_task_id, session_id) REFERENCES public.session_tasks(id, session_id)
        ON DELETE NO ACTION ON UPDATE NO ACTION DEFERRABLE INITIALLY DEFERRED;

-- Deferred checks allow a whole user aggregate to cascade-delete in one transaction,
-- but prohibit deleting individual sessions/tasks while encounter history survives.
COMMIT;
