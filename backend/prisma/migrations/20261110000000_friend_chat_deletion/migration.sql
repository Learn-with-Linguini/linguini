-- Each member can delete an ended friend chat from their own list. The chat itself is
-- removed once both members have deleted it (or the only member has).
ALTER TABLE public.friend_chats
    ADD COLUMN creator_deleted_at TIMESTAMPTZ,
    ADD COLUMN partner_deleted_at TIMESTAMPTZ;
