-- One language-independent preloaded scene per image. Target-language words
-- come from the vocabulary catalog and session-time translation, not the scene.
BEGIN;

-- Keep the curated words, genders and examples in the vocabulary catalog.
INSERT INTO public.vocabulary_items (language_code, lemma, display_text, part_of_speech, gender, example_sentence)
SELECT DISTINCT ON (lower(scene.language_code), lower(item->>'word'), coalesce(item->>'wordClass', 'noun'))
    scene.language_code, item->>'word', item->>'word', coalesce(item->>'wordClass', 'noun'),
    item->>'gender', nullif(item->>'example', '')
FROM public.preloaded_scenes AS scene
CROSS JOIN LATERAL jsonb_array_elements(scene.content->'items') AS item
WHERE length(btrim(coalesce(item->>'word', ''))) > 0
  AND NOT EXISTS (
    SELECT 1 FROM public.vocabulary_items AS existing
    WHERE lower(existing.language_code) = lower(scene.language_code)
      AND lower(existing.lemma) = lower(item->>'word')
      AND existing.part_of_speech = coalesce(item->>'wordClass', 'noun')
  )
ORDER BY lower(scene.language_code), lower(item->>'word'), coalesce(item->>'wordClass', 'noun'), scene.sort_order;

INSERT INTO public.vocabulary_translations (vocabulary_item_id, source_language_code, translated_text)
SELECT DISTINCT ON (vocabulary.id) vocabulary.id, 'en', item->>'translation'
FROM public.preloaded_scenes AS scene
CROSS JOIN LATERAL jsonb_array_elements(scene.content->'items') AS item
JOIN LATERAL (
    SELECT id FROM public.vocabulary_items AS existing
    WHERE lower(existing.language_code) = lower(scene.language_code)
      AND lower(existing.lemma) = lower(item->>'word')
      AND existing.part_of_speech = coalesce(item->>'wordClass', 'noun')
    ORDER BY existing.created_at, existing.id
    LIMIT 1
) AS vocabulary ON true
WHERE length(btrim(coalesce(item->>'translation', ''))) > 0
ORDER BY vocabulary.id, scene.sort_order
ON CONFLICT DO NOTHING;

-- Keep one row per image under a neutral slug; carry over every language's templates.
CREATE TEMPORARY TABLE scene_slugs (old_slug TEXT PRIMARY KEY, new_slug TEXT NOT NULL, kept BOOLEAN NOT NULL) ON COMMIT DROP;
INSERT INTO scene_slugs VALUES
    ('calle-mayor', 'street', true), ('rue-principale', 'street', false),
    ('cafe-plaza', 'cafe', true), ('cafe-de-la-place', 'cafe', false),
    ('mercado-central', 'market', true), ('marche-central', 'market', false),
    ('mi-cuarto', 'bedroom', true), ('ma-chambre', 'bedroom', false),
    ('la-cocina', 'kitchen', true), ('la-cuisine', 'kitchen', false),
    ('el-parque', 'park', true), ('le-parc', 'park', false);

UPDATE public.preloaded_scenes AS kept
SET content = jsonb_set(
    kept.content,
    '{generated}',
    jsonb_build_object(
        'artifactVersion', coalesce(
            kept.content->'generated'->>'artifactVersion',
            merged.artifact_version
        ),
        'templates', coalesce(kept.content->'generated'->'templates', '[]'::jsonb) || merged.templates
    )
)
FROM (
    SELECT other.media_asset_id,
           max(other.content->'generated'->>'artifactVersion') AS artifact_version,
           jsonb_agg(template) AS templates
    FROM public.preloaded_scenes AS other
    CROSS JOIN LATERAL jsonb_array_elements(other.content->'generated'->'templates') AS template
    WHERE jsonb_typeof(other.content->'generated'->'templates') = 'array'
      AND other.slug NOT IN (SELECT old_slug FROM scene_slugs WHERE kept)
    GROUP BY other.media_asset_id
) AS merged
WHERE kept.media_asset_id = merged.media_asset_id
  AND kept.slug IN (SELECT old_slug FROM scene_slugs WHERE kept);

-- Any other duplicate keeps the oldest row per image, preferring the Spanish base rows.
DELETE FROM public.preloaded_scenes AS scene
WHERE scene.id <> (
    SELECT keep.id FROM public.preloaded_scenes AS keep
    WHERE keep.media_asset_id = scene.media_asset_id
    ORDER BY (keep.slug IN (SELECT old_slug FROM scene_slugs WHERE kept)) DESC,
             (lower(keep.language_code) = 'es') DESC, keep.created_at, keep.id
    LIMIT 1
);

UPDATE public.preloaded_scenes AS scene
SET slug = scene_slugs.new_slug
FROM scene_slugs
WHERE scene.slug = scene_slugs.old_slug;

-- Items keep only language-free facts; placeholder rounds use the English labels.
UPDATE public.preloaded_scenes AS scene
SET content = scene.content
    || jsonb_build_object(
        'items', (
            SELECT jsonb_agg(
                entry.item - 'word' - 'gender' - 'example' - 'exampleTranslation'
                ORDER BY entry.position
            )
            FROM jsonb_array_elements(scene.content->'items') WITH ORDINALITY AS entry(item, position)
        ),
        'rounds', jsonb_build_array(jsonb_build_object(
            'id', 'round-1',
            'clue', scene.content->'items'->0->>'translation',
            'clueTranslation', scene.content->'items'->0->>'translation',
            'answerId', scene.content->'items'->0->>'id',
            'choices', (
                SELECT jsonb_agg(
                    jsonb_build_object('id', entry.item->>'id', 'label', entry.item->>'translation')
                    ORDER BY entry.position
                )
                FROM jsonb_array_elements(scene.content->'items') WITH ORDINALITY AS entry(item, position)
                WHERE entry.position <= 4
            ),
            'encouragement', 'Keep looking closely!'
        ))
    ),
    updated_at = now()
WHERE jsonb_array_length(scene.content->'items') > 0;

DROP INDEX public.preloaded_scenes_language_code_is_active_sort_order_idx;
DROP INDEX public.preloaded_scenes_media_asset_id_idx;
ALTER TABLE public.preloaded_scenes DROP COLUMN language_code, DROP COLUMN language;
CREATE UNIQUE INDEX preloaded_scenes_media_asset_id_key ON public.preloaded_scenes(media_asset_id);
CREATE INDEX preloaded_scenes_is_active_sort_order_idx ON public.preloaded_scenes(is_active, sort_order);

COMMIT;
