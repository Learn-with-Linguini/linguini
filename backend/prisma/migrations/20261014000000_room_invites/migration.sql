BEGIN;

ALTER TABLE public.learning_rooms ADD COLUMN invite_code VARCHAR(64);

-- Rotate old HMAC invitations without retaining a deployment-wide secret.
-- gen_random_uuid and sha256(bytea) are PostgreSQL core functions; no extension
-- or external secret is required. Materialize each random code exactly once.
WITH rotated AS MATERIALIZED (
    SELECT id,
           replace(gen_random_uuid()::text, '-', '') ||
           replace(gen_random_uuid()::text, '-', '') AS code
    FROM public.learning_rooms
    WHERE status = 'lobby'
      AND host_user_id IS NOT NULL
      AND invite_expires_at > CURRENT_TIMESTAMP
      AND expires_at > CURRENT_TIMESTAMP
)
UPDATE public.learning_rooms AS room
SET invite_code = rotated.code,
    invite_hash = encode(sha256(convert_to(rotated.code, 'UTF8')), 'hex'),
    revision = room.revision + 1
FROM rotated
WHERE room.id = rotated.id;

UPDATE public.learning_rooms
SET invite_expires_at = LEAST(invite_expires_at, CURRENT_TIMESTAMP)
WHERE status <> 'lobby' OR host_user_id IS NULL OR expires_at <= CURRENT_TIMESTAMP;

ALTER TABLE public.learning_rooms
ADD CONSTRAINT learning_rooms_invite_code_valid CHECK (
    invite_code IS NULL OR (
        invite_code ~ '^[0-9a-f]{64}$'
        AND invite_hash = encode(sha256(convert_to(invite_code, 'UTF8')), 'hex')
    )
);

COMMIT;
