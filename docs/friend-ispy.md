# Private I-Spy chats

`/ispy/friends` lists persistent conversations. Create a chat, share its private
invitation, and have one friend explicitly join using a profile for the same target
language. The learners may use different proficiency levels. Opening an invitation
does not switch a profile or join automatically. A full or closed invitation does
not expose the participants to another account.

Either participant can start a round with one owned uploaded photo. The sender
reviews a detected object or taps another region for analysis, then confirms the
object's identity. Beginner clues use confirmed description pieces; other learners
can edit or write a clue. Audio and the existing mission cheatsheets support the
composer. Suggestions require review and an explicit send.

The receiver sees the photo and original clue, selects a location and confirms
the guess. Unfinished rounds do not expose the object inventory, answer or target
region to the receiver. An incorrect guess lets the sender add a useful clue or
reveal the answer. Completed rounds remain in the conversation, and either learner
can start the next round. Starting a round never requires both learners online.

Private assistance is requested separately and never enters the shared timeline,
revision or partner response. Reports remain private. Leaving revokes the invitation
and closes the conversation; blocking closes the pair's chats and prevents further
joins between them. Shared photo access ends when a conversation closes.

## Implementation

The authenticated API is `/api/v1/friend-chats`. It has conversation create/list/get,
POST invitation-preview/join, invitation rotation/revocation, leave/report/block,
round creation/retry, target review/confirmation, clue/suggestion, coordinate guess,
private help, reveal/cancel and authenticated image routes. Existing `/rooms` API
and `/rooms/:roomId` screens continue to support older games.

Prisma owns the additive `20261031000000_friend_chats` migration. The new tables have
RLS enabled and browser-role grants revoked. Participant authorization is checked
on the server. A partial unique index permits only one unfinished round per chat;
ordered locks, revisions and fingerprinted command IDs protect concurrent writes
and retries. Do not apply the migration to Supabase without review.

Only invitation hashes are stored. The creator receives the raw token once and
keeps it in browser session storage. If a creation response is lost and a retry
recovers the conversation without a token, create a replacement invitation. New
links carry tokens in a fragment consumed before analytics scripts load. Preview
and join send the token in a POST body. Event names and permitted parameters are
documented in [ANALYTICS.md](../ANALYTICS.md#private-i-spy-chats).

Photo analysis, translation and clue wording use the configured AI runtime, private
cache scope, language packs and the normal upload-moderation policy. Confirmed
regions determine guesses; the browser cannot submit a hidden object ID as its
answer. The clue composer and private help reference the canonical stored mission
cheatsheets rather than copies of their content.

Unsent browser drafts and unknown-outcome commands are scoped to the account,
conversation and round. A retry reuses its original command ID and payload. A
definitive stale-revision response refreshes the saved conversation. The interface
keeps saved history visible during connection failures and disables sends offline.

## Verification

Backend regressions cover ownership, safe invitation previews, mixed-level joins,
concurrent joins and rounds, command replay, target secrecy, private assistance,
immutable history, blocking, account deletion and stale photo jobs. Content tests
exercise owned-photo analysis, actual region mapping, clue-name exclusions and
grounded assistance. Frontend tests cover invitations, confirmation controls,
drafts, retries and safe receiver rendering.

Run the checks in [AGENTS.md](../AGENTS.md). PostgreSQL tests require a disposable
database with this migration deployed. They skip without `TEST_DATABASE_URL`; a
local run with skips does not establish persistence or concurrency correctness.
