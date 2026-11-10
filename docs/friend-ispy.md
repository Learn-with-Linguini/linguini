# Private I-Spy chats

`/ispy/friends` lists persistent conversations. Create a chat, share its private
invitation, and have one friend explicitly join using a profile for the same target
language. The learners may use different proficiency levels. Opening an invitation
does not switch a profile or join automatically. A full or closed invitation does
not expose the participants to another account.

Either participant can start a round with one owned uploaded photo. After analysis,
the sender checks the objects with the same review as practice scene analysis:
numbered markers on the photo, and Objects, Adjectives and Relations tabs to remove,
move, add and restore objects and to edit adjectives and connections. Nothing is
translated or shown to the friend until the sender presses Confirm objects; the
confirmed set is then translated, and only it is used for markers, guesses and clue
pieces. While unconfirmed, the API reports the round as `reviewingObjects` (stored as
`selectingTarget`, so no schema change was needed) and sends the analysis only to the
sender as `reviewObjects` and `reviewRelations`. An added object is a tapped point and
gets a small estimated box for crops; a moved object keeps its box size around the new
centre. The sender then chooses the secret object from the confirmed objects and
confirms its identity. Rounds stored before this change already hold translated
objects and are treated as confirmed. Beginner clues use confirmed description pieces; other learners
can edit or write a clue. Audio and the existing mission cheatsheets support the
composer. Suggestions require review and an explicit send.

The receiver sees the photo and original clue, picks one of the marked objects and
confirms the guess. Every detected object is marked, with the target always among
them, so the markers do not give the answer away; reading the clue does. Markers are
unlabelled on the photo. Tapping one shows that object's crop, word and a speaker
button before the guess is submitted; the translation is included only when both
learners share an explanation language. Each marker carries an opaque per-round key
(a hash of the round and object keys), its position, size and name, in the same
shape for every object, and markers are ordered by that key. A custom target replaces any
detected marker centred on the same spot. The server scores a guess by comparing the
chosen key with the target's key; older clients may still send a photo point, which
is scored against the target region. Markers already guessed wrong are shown as
tried. Unfinished rounds do not expose object names, the answer or the target region
to the receiver. An incorrect guess lets the sender add a useful clue or
reveal the answer. Completed rounds remain in the conversation. Players take turns:
either learner can start the first round, and after a round finishes (found or
revealed) the learner who guessed starts the next one. A cancelled round does not
pass the turn. The next player can upload a new photo or continue on the finished
round's photo; continuing copies that round's analyzed objects, so the new round is
ready at once without another AI call. The photo stays owned by whoever uploaded it,
and the chat image route serves a photo owned by either member of the chat. Photo
reuse is offered only when both learners share an explanation language, because
object names and translations were prepared in the original sender's explanation
language. Starting a round never requires both learners online.

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
