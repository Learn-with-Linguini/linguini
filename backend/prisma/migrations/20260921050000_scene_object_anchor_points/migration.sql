ALTER TABLE public.scene_objects ADD COLUMN anchor_point JSONB;

ALTER TABLE public.scene_objects
  ADD CONSTRAINT scene_objects_anchor_point_valid CHECK (
    anchor_point IS NULL OR (
      jsonb_typeof(anchor_point) = 'object'
      AND anchor_point ?& ARRAY['x', 'y']
      AND jsonb_typeof(anchor_point->'x') = 'number'
      AND jsonb_typeof(anchor_point->'y') = 'number'
      AND (anchor_point->>'x')::numeric BETWEEN 0 AND 1
      AND (anchor_point->>'y')::numeric BETWEEN 0 AND 1
    )
  );
