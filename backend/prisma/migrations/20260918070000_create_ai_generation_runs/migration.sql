CREATE UNIQUE INDEX sessions_id_user_id_key ON public.sessions(id,user_id);
CREATE UNIQUE INDEX journals_id_user_id_key ON public.journals(id,user_id);

CREATE TABLE public.ai_generation_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES public.users(id) ON DELETE CASCADE ON UPDATE NO ACTION,
    session_id UUID,
    journal_id UUID,
    feature VARCHAR(23) NOT NULL CHECK (feature IN (
        'sceneAnalysis','vocabularyGeneration','sessionPlanGeneration','clueGeneration',
        'attemptEvaluation','speechTranscription','pronunciationEvaluation','journalFeedback','journalWordMatching')),
    model_name TEXT NOT NULL CHECK (length(btrim(model_name)) > 0),
    prompt_version TEXT NOT NULL CHECK (length(btrim(prompt_version)) > 0),
    schema_version TEXT NOT NULL CHECK (length(btrim(schema_version)) > 0),
    status VARCHAR(9) NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','succeeded','failed')),
    latency_ms BIGINT CHECK (latency_ms >= 0),
    input_tokens BIGINT CHECK (input_tokens >= 0),
    output_tokens BIGINT CHECK (output_tokens >= 0),
    validation_passed BOOLEAN,
    error_code VARCHAR(100),
    input_reference TEXT,
    output_reference TEXT,
    completed_at TIMESTAMPTZ(6),
    created_at TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT ai_generation_runs_context_owner CHECK ((session_id IS NULL AND journal_id IS NULL) OR user_id IS NOT NULL),
    CONSTRAINT ai_generation_runs_session_owner_fkey FOREIGN KEY(session_id,user_id)
        REFERENCES public.sessions(id,user_id) ON DELETE CASCADE ON UPDATE NO ACTION,
    CONSTRAINT ai_generation_runs_journal_owner_fkey FOREIGN KEY(journal_id,user_id)
        REFERENCES public.journals(id,user_id) ON DELETE CASCADE ON UPDATE NO ACTION,
    CONSTRAINT ai_generation_runs_lifecycle CHECK (
        (status='pending' AND completed_at IS NULL AND error_code IS NULL) OR
        (status='succeeded' AND completed_at IS NOT NULL AND error_code IS NULL) OR
        (status='failed' AND completed_at IS NOT NULL AND error_code IS NOT NULL AND length(btrim(error_code)) > 0))
);
CREATE INDEX ai_generation_runs_user_id_created_at_idx ON public.ai_generation_runs(user_id,created_at);
CREATE INDEX ai_generation_runs_session_id_user_id_idx ON public.ai_generation_runs(session_id,user_id);
CREATE INDEX ai_generation_runs_journal_id_user_id_idx ON public.ai_generation_runs(journal_id,user_id);
CREATE INDEX ai_generation_runs_feature_status_created_at_idx ON public.ai_generation_runs(feature,status,created_at);

CREATE FUNCTION public.protect_ai_generation_run() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF (NEW.id,NEW.user_id,NEW.session_id,NEW.journal_id,NEW.feature,NEW.model_name,
        NEW.prompt_version,NEW.schema_version,NEW.input_reference,NEW.created_at)
        IS DISTINCT FROM (OLD.id,OLD.user_id,OLD.session_id,OLD.journal_id,OLD.feature,OLD.model_name,
        OLD.prompt_version,OLD.schema_version,OLD.input_reference,OLD.created_at) THEN
        RAISE EXCEPTION 'AI run identity is immutable' USING ERRCODE='23514';
    END IF;
    IF OLD.status <> 'pending' AND (to_jsonb(NEW)-'updated_at') IS DISTINCT FROM (to_jsonb(OLD)-'updated_at') THEN
        RAISE EXCEPTION 'Completed AI run results are immutable' USING ERRCODE='23514';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER ai_generation_runs_validate BEFORE UPDATE ON public.ai_generation_runs
    FOR EACH ROW EXECUTE FUNCTION public.protect_ai_generation_run();
CREATE TRIGGER ai_generation_runs_updated_at BEFORE UPDATE ON public.ai_generation_runs
    FOR EACH ROW EXECUTE FUNCTION public.set_user_updated_at();

ALTER TABLE public.ai_generation_runs ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.ai_generation_runs FROM PUBLIC;
DO $$
BEGIN
    IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='anon') THEN REVOKE ALL ON TABLE public.ai_generation_runs FROM anon; END IF;
    IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN REVOKE ALL ON TABLE public.ai_generation_runs FROM authenticated; END IF;
END;
$$;
