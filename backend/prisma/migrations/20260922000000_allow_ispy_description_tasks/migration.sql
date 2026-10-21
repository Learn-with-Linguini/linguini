-- A reflection can be a regular learning reflection or the learner-described
-- half of I-Spy. Only I-Spy phases are restricted to I-Spy task kinds.
ALTER TABLE public.session_tasks
    DROP CONSTRAINT session_tasks_phase_kind;

ALTER TABLE public.session_tasks
    ADD CONSTRAINT session_tasks_phase_kind
    CHECK (phase <> 'ispy' OR kind IN ('ispyRound', 'reflection'));
