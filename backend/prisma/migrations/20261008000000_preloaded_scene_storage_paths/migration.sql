-- Point the six seeded scene assets at their uploaded image objects.
BEGIN;

UPDATE public.media_assets AS asset
SET storage_key = image.storage_key,
    mime_type = image.mime_type
FROM (VALUES
    ('036a3de3-3ee0-4e75-8226-8204430d096c'::uuid, 'preloaded/scenes/bedroom.jpg', 'image/jpeg'),
    ('40e54611-22fb-4a38-977c-f0786df70866'::uuid, 'preloaded/scenes/cafe.webp', 'image/webp'),
    ('aed4f104-241a-42f2-8e3a-d3408787179c'::uuid, 'preloaded/scenes/kitchen.jpg', 'image/jpeg'),
    ('79059369-eaa4-4805-a11e-a91bd6eff467'::uuid, 'preloaded/scenes/market.jpg', 'image/jpeg'),
    ('835e99a0-7a37-4a98-86ff-08185ebb2c63'::uuid, 'preloaded/scenes/park.webp', 'image/webp'),
    ('f9507eb2-776b-4a4f-a6a7-a7c622ff3a16'::uuid, 'preloaded/scenes/street.jpg', 'image/jpeg')
) AS image(id, storage_key, mime_type)
WHERE asset.id = image.id
  AND asset.source = 'preloaded'
  AND (asset.storage_key, asset.mime_type) IS DISTINCT FROM (image.storage_key, image.mime_type);

COMMIT;
