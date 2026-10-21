-- Curated colours and relations for the preloaded scenes, so their lessons
-- and I-Spy games can build describing rounds. Updates scene content only.
BEGIN;

UPDATE public.preloaded_scenes AS scene
SET content = jsonb_set(
        scene.content || jsonb_build_object('relations', facts.relations),
        '{items}',
        (
            SELECT jsonb_agg(
                CASE
                    WHEN facts.colours ? (entry.item->>'id') THEN entry.item || jsonb_build_object(
                        'attributes', jsonb_build_object('color', facts.colours->>(entry.item->>'id'))
                    )
                    ELSE entry.item
                END
                ORDER BY entry.position
            )
            FROM jsonb_array_elements(scene.content->'items') WITH ORDINALITY AS entry(item, position)
        )
    ),
    updated_at = now()
FROM (VALUES
    ('calle-mayor', '{"building": "brown", "taxi": "yellow", "streetlight": "grey", "tree": "orange", "crosswalk": "white"}'::jsonb, '[{"subjectItemId": "streetlight", "relation": "in_front_of", "referenceItemId": "building"}, {"subjectItemId": "tree", "relation": "next_to", "referenceItemId": "building"}, {"subjectItemId": "taxi", "relation": "near", "referenceItemId": "crosswalk"}]'::jsonb),
    ('rue-principale', '{"building": "brown", "taxi": "yellow", "streetlight": "grey", "tree": "orange", "crosswalk": "white"}'::jsonb, '[{"subjectItemId": "streetlight", "relation": "in_front_of", "referenceItemId": "building"}, {"subjectItemId": "tree", "relation": "next_to", "referenceItemId": "building"}, {"subjectItemId": "taxi", "relation": "near", "referenceItemId": "crosswalk"}]'::jsonb),
    ('mi-cuarto', '{"bed": "white", "bedside-table": "brown", "lamp": "white", "curtains": "grey", "door": "white"}'::jsonb, '[{"subjectItemId": "lamp", "relation": "on", "referenceItemId": "bedside-table"}, {"subjectItemId": "bedside-table", "relation": "next_to", "referenceItemId": "bed"}, {"subjectItemId": "curtains", "relation": "next_to", "referenceItemId": "door"}]'::jsonb),
    ('ma-chambre', '{"bed": "white", "bedside-table": "brown", "lamp": "white", "curtains": "grey", "door": "white"}'::jsonb, '[{"subjectItemId": "lamp", "relation": "on", "referenceItemId": "bedside-table"}, {"subjectItemId": "bedside-table", "relation": "next_to", "referenceItemId": "bed"}, {"subjectItemId": "curtains", "relation": "next_to", "referenceItemId": "door"}]'::jsonb),
    ('cafe-plaza', '{"table": "brown", "chair": "white", "counter": "white", "coffee-machine": "grey", "lamp": "white"}'::jsonb, '[{"subjectItemId": "chair", "relation": "next_to", "referenceItemId": "table"}, {"subjectItemId": "coffee-machine", "relation": "behind", "referenceItemId": "counter"}, {"subjectItemId": "lamp", "relation": "above", "referenceItemId": "table"}]'::jsonb),
    ('cafe-de-la-place', '{"table": "brown", "chair": "white", "counter": "white", "coffee-machine": "grey", "lamp": "white"}'::jsonb, '[{"subjectItemId": "chair", "relation": "next_to", "referenceItemId": "table"}, {"subjectItemId": "coffee-machine", "relation": "behind", "referenceItemId": "counter"}, {"subjectItemId": "lamp", "relation": "above", "referenceItemId": "table"}]'::jsonb),
    ('la-cocina', '{"cabinet": "white", "sink": "grey", "stove": "grey", "table": "white", "vase": "white"}'::jsonb, '[{"subjectItemId": "vase", "relation": "on", "referenceItemId": "table"}, {"subjectItemId": "cabinet", "relation": "above", "referenceItemId": "sink"}, {"subjectItemId": "sink", "relation": "left_of", "referenceItemId": "stove"}]'::jsonb),
    ('la-cuisine', '{"cabinet": "white", "sink": "grey", "stove": "grey", "table": "white", "vase": "white"}'::jsonb, '[{"subjectItemId": "vase", "relation": "on", "referenceItemId": "table"}, {"subjectItemId": "cabinet", "relation": "above", "referenceItemId": "sink"}, {"subjectItemId": "sink", "relation": "left_of", "referenceItemId": "stove"}]'::jsonb),
    ('mercado-central', '{"banana": "yellow", "bicycle": "blue", "tomato": "red", "watermelon": "green", "market-stall": "brown"}'::jsonb, '[{"subjectItemId": "banana", "relation": "above", "referenceItemId": "market-stall"}, {"subjectItemId": "tomato", "relation": "next_to", "referenceItemId": "watermelon"}]'::jsonb),
    ('marche-central', '{"banana": "yellow", "bicycle": "blue", "tomato": "red", "watermelon": "green", "market-stall": "brown"}'::jsonb, '[{"subjectItemId": "banana", "relation": "above", "referenceItemId": "market-stall"}, {"subjectItemId": "tomato", "relation": "next_to", "referenceItemId": "watermelon"}]'::jsonb),
    ('el-parque', '{"bench": "brown", "lamp-post": "black", "flower-bed": "red", "tree": "green"}'::jsonb, '[{"subjectItemId": "bench", "relation": "next_to", "referenceItemId": "walkway"}, {"subjectItemId": "lamp-post", "relation": "next_to", "referenceItemId": "walkway"}, {"subjectItemId": "flower-bed", "relation": "near", "referenceItemId": "walkway"}]'::jsonb),
    ('le-parc', '{"bench": "brown", "lamp-post": "black", "flower-bed": "red", "tree": "green"}'::jsonb, '[{"subjectItemId": "bench", "relation": "next_to", "referenceItemId": "walkway"}, {"subjectItemId": "lamp-post", "relation": "next_to", "referenceItemId": "walkway"}, {"subjectItemId": "flower-bed", "relation": "near", "referenceItemId": "walkway"}]'::jsonb)
) AS facts(slug, colours, relations)
WHERE scene.slug = facts.slug;

COMMIT;
