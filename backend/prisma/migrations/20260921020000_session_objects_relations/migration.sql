BEGIN;
LOCK TABLE public.sessions, public.scene_objects IN SHARE ROW EXCLUSIVE MODE;

CREATE TYPE public.session_failure_code AS ENUM (
    'imageUploadFailed', 'sceneAnalysisFailed', 'noValidObjects',
    'vocabularyMappingFailed', 'taskGenerationFailed'
);
CREATE TYPE public.session_status AS ENUM (
    'created', 'analyzingScene', 'awaitingObjectReview', 'generatingTasks',
    'ready', 'inProgress', 'completed', 'abandoned', 'failed'
);
-- Unknown historical codes fail this cast rather than silently losing debugging data.
ALTER TABLE public.sessions
    ADD COLUMN session_title TEXT,
    ADD COLUMN session_summary TEXT,
    ALTER COLUMN failure_code TYPE public.session_failure_code
        USING failure_code::public.session_failure_code;
ALTER TABLE public.sessions DROP CONSTRAINT sessions_status_check;
-- Remove expressions bound to the old varchar type before converting it.
ALTER TABLE public.sessions DROP CONSTRAINT sessions_terminal_timestamp;
DROP INDEX public.sessions_one_active_key;
ALTER TABLE public.sessions ALTER COLUMN status DROP DEFAULT;
ALTER TABLE public.sessions ALTER COLUMN status TYPE public.session_status
    USING status::text::public.session_status;
ALTER TABLE public.sessions RENAME COLUMN status TO session_status;
ALTER TABLE public.sessions ALTER COLUMN session_status SET DEFAULT 'created'::public.session_status;
ALTER TABLE public.sessions ADD CONSTRAINT sessions_terminal_timestamp CHECK (
    (session_status <> 'completed' OR completed_at IS NOT NULL) AND
    (session_status <> 'abandoned' OR abandoned_at IS NOT NULL) AND
    NOT (completed_at IS NOT NULL AND abandoned_at IS NOT NULL)
);

UPDATE public.sessions s SET session_title = p.title
FROM public.preloaded_scenes p WHERE p.media_asset_id = s.scene_media_asset_id;

-- Convert resumable legacy drafts without inserting unconfirmed objects.
UPDATE public.sessions s SET analysis_draft = jsonb_build_object(
    'objects', COALESCE((SELECT jsonb_agg(jsonb_build_object(
        'id', obj->'id', 'session_id', obj->'session_id',
        'label', obj->'detected_label', 'bounding_box', obj->'bounding_box',
        'attributes', NULL, 'confidence_score', obj->'confidence',
        'source_object_key', NULL, 'vocabulary_item_id', obj->'vocabulary_item_id'
    )) FROM jsonb_array_elements(s.analysis_draft) obj), '[]'::jsonb),
    'relations', '[]'::jsonb
) WHERE jsonb_typeof(analysis_draft) = 'array';
UPDATE public.sessions SET session_status = 'awaitingObjectReview'
WHERE analysis_draft IS NOT NULL AND plan_version IS NULL
    AND session_status NOT IN ('completed', 'abandoned', 'failed');

-- Status values in this database are camelCase/lowercase, not enum member names.
CREATE UNIQUE INDEX one_active_session_per_profile
    ON public.sessions(user_id, language_profile_id)
    WHERE session_status NOT IN ('completed', 'abandoned', 'failed');

-- Keep only confirmed objects. Historical task references must be reviewed before
-- deployment if they point to suggestions; do not silently delete learning history.
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM public.session_tasks t JOIN public.scene_objects o
        ON o.id = t.scene_object_id WHERE o.selection_status IN ('suggested', 'rejected')) THEN
        RAISE EXCEPTION 'Unconfirmed objects have task references; reconcile them before migration';
    END IF;
END $$;
DELETE FROM public.scene_objects WHERE selection_status IN ('suggested', 'rejected');

ALTER TABLE public.scene_objects ADD COLUMN bounding_box JSONB,
    ADD COLUMN attributes JSONB, ADD COLUMN source_object_key TEXT;
UPDATE public.scene_objects SET bounding_box = jsonb_build_object(
    'x', x, 'y', y, 'height', height, 'width', width
);
ALTER TABLE public.scene_objects
    DROP CONSTRAINT scene_objects_session_media_fkey,
    DROP CONSTRAINT scene_objects_bbox,
    DROP CONSTRAINT scene_objects_correction,
    DROP COLUMN media_asset_id,
    DROP COLUMN confirmed_label,
    DROP COLUMN selection_status,
    DROP COLUMN x, DROP COLUMN y, DROP COLUMN width, DROP COLUMN height;
ALTER TABLE public.scene_objects RENAME COLUMN detected_label TO label;
ALTER TABLE public.scene_objects RENAME COLUMN confidence TO confidence_score;
ALTER TABLE public.scene_objects ADD CONSTRAINT scene_objects_session_fkey
    FOREIGN KEY(session_id) REFERENCES public.sessions(id) ON DELETE CASCADE ON UPDATE CASCADE;
CREATE INDEX scene_objects_session_id_idx ON public.scene_objects(session_id);
ALTER TABLE public.scene_objects ADD CONSTRAINT scene_objects_attributes_object
    CHECK (attributes IS NULL OR jsonb_typeof(attributes) = 'object');
ALTER TABLE public.scene_objects ADD CONSTRAINT scene_objects_bounding_box_valid CHECK (
    bounding_box IS NULL OR (
        jsonb_typeof(bounding_box) = 'object'
        AND bounding_box ?& ARRAY['x','y','width','height']
        AND jsonb_typeof(bounding_box->'x') = 'number'
        AND jsonb_typeof(bounding_box->'y') = 'number'
        AND jsonb_typeof(bounding_box->'width') = 'number'
        AND jsonb_typeof(bounding_box->'height') = 'number'
        AND (bounding_box->>'x')::numeric BETWEEN 0 AND 1
        AND (bounding_box->>'y')::numeric BETWEEN 0 AND 1
        AND (bounding_box->>'width')::numeric > 0
        AND (bounding_box->>'height')::numeric > 0
        AND (bounding_box->>'x')::numeric + (bounding_box->>'width')::numeric <= 1
        AND (bounding_box->>'y')::numeric + (bounding_box->>'height')::numeric <= 1
    )
);

DROP TRIGGER sessions_updated_at ON public.sessions;
DROP TRIGGER scene_objects_updated_at ON public.scene_objects;
ALTER TABLE public.sessions DROP CONSTRAINT sessions_id_scene_media_asset_id_key,
    DROP COLUMN plan_version, DROP COLUMN created_at, DROP COLUMN updated_at;
ALTER TABLE public.scene_objects DROP COLUMN created_at, DROP COLUMN updated_at;

CREATE TABLE public.scene_object_relations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    subject_scene_object_id UUID NOT NULL REFERENCES public.scene_objects(id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    relation TEXT NOT NULL CHECK (length(btrim(relation)) BETWEEN 1 AND 200),
    reference_scene_object_id UUID NOT NULL REFERENCES public.scene_objects(id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    source_relation_key TEXT,
    CHECK (subject_scene_object_id <> reference_scene_object_id)
);
CREATE INDEX scene_object_relations_subject_scene_object_id_idx
    ON public.scene_object_relations(subject_scene_object_id);
CREATE INDEX scene_object_relations_reference_scene_object_id_idx
    ON public.scene_object_relations(reference_scene_object_id);

CREATE FUNCTION public.check_scene_object_relation_session() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE subject_session UUID; reference_session UUID;
BEGIN
    -- Lock endpoints in stable order so concurrent writes cannot move them underneath us.
    PERFORM id FROM public.scene_objects
        WHERE id IN (NEW.subject_scene_object_id, NEW.reference_scene_object_id)
        ORDER BY id FOR SHARE;
    SELECT session_id INTO subject_session FROM public.scene_objects WHERE id = NEW.subject_scene_object_id;
    SELECT session_id INTO reference_session FROM public.scene_objects WHERE id = NEW.reference_scene_object_id;
    IF subject_session IS DISTINCT FROM reference_session THEN
        RAISE EXCEPTION 'Relation endpoints must belong to the same session' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER scene_object_relations_session_check BEFORE INSERT OR UPDATE
    ON public.scene_object_relations FOR EACH ROW
    EXECUTE FUNCTION public.check_scene_object_relation_session();

CREATE FUNCTION public.prevent_scene_object_session_move() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.session_id <> OLD.session_id THEN
        RAISE EXCEPTION 'Scene objects cannot move between sessions' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER scene_objects_session_immutable BEFORE UPDATE OF session_id
    ON public.scene_objects FOR EACH ROW EXECUTE FUNCTION public.prevent_scene_object_session_move();

ALTER TABLE public.scene_object_relations ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.scene_object_relations FROM PUBLIC;
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
        REVOKE ALL ON TABLE public.scene_object_relations FROM anon;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
        REVOKE ALL ON TABLE public.scene_object_relations FROM authenticated;
    END IF;
END $$;
COMMIT;
