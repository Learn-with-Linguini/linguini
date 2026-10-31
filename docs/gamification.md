# Mission progress and Basil

This release implements the first part of #90. Sauce Jars describe a mission in
progress. Basil Points are the rewards earned from learning; their totals are
separate from XP and from the balance available for accent purchases.

## Reward policy: `basil-questions.v1`

- First accepted correct vocabulary or mission question: 10 Basil.
- First accepted incorrect answer: 5 Basil for the attempt.
- Repeated checks, a lost-response retry, a correction during the same question,
  subsequent typing practice, and final submission of already checked answers:
  no additional reward.
- Reading, skipping, scene analysis, and merely opening a page: no reward.
- Existing non-grouped lesson practice retains its one-Basil reward per task.
- Standalone I-Spy games retain their existing no-reward policy. Friend room
  contribution rewards retain their existing policy.

An accepted question and its reward are saved in the same transaction. The first
choice, reward amount, content fingerprint, profile, session, and policy version
are retained. A different question reusing an old identity is rejected rather
than inheriting a stale answer or paying again. Completing a legacy graded task
does not retrospectively create question rewards.

Today's Basil and lifetime Basil sum earned credits, including historical
credits. Buying an accent reduces the available balance, not either earned
total. Existing XP and Basil history are preserved.

## I-Spy assistance and XP

Lesson description practice keeps its task-completion XP when a learner uses
optional support. The separate independent-correct bonus is awarded only when
none of that task's saved attempts used a clue frame, inserted phrase, selected
slot, English or phrase hint, word bank, or cheatsheet. Offering those controls
or showing the target word alone does not count as help usage. Revising a clue
does not erase support already recorded on an earlier attempt. Confirmation
retries award credit only once. Standalone I-Spy continues to award no XP.

## Mission badges: `mission-badges.v1`

A successful batch must meet its versioned mission definition's minimum assessed
questions, correct-answer ratio, independent correct answers, and required
language targets. Every task in the batch must be completed; skipped tasks and
unfinished generation cannot award a badge. An unsuccessful finished batch shows
the requirements to practise next.

- **Taster:** one successful batch.
- **Cook:** successful batches across at least three distinct photos and two
  target/context sets, with at least 75% independently correct answers in two
  different photos.
- **Chef, Head Chef, Master:** reserved for original spoken production, harder
  situations, and follow-up conversations. The current exercise evaluator does
  not assess that evidence, so this release does not award these ranks. The UI
  explains their availability with future spoken missions.

Badges belong to a language profile and mission, across that profile's CEFR
changes. Every recorded batch retains its own practice level and content version.
Curated images have stable asset identities. New uploaded-photo analyses retain
an owner-scoped SHA-256 of the downloaded image bytes so reuploading the same
image does not count as new variety. Older uploads without a verified content
identity can earn Taster but cannot supply distinct-photo evidence for Cook.
An image identity alone does not prove a different target or conversation context.

The jar fills from checked, assessed questions, reaching at most 90% until the
whole batch meets its learning requirements. At 100% it becomes the mission's
badge illustration. The six illustration stages use the messages from #90;
finished batches needing review receive a review message instead.

## Chef of the Day

Participation is off until the learner explicitly joins. Leaving immediately
removes them from standings. Only opted-in learners with positive earned Basil
today appear; standings expose the learner's profile name, score, and rank.
Emails, account identifiers, learning profiles, and photos are not returned.

The competition day is midnight to midnight UTC for everyone. The API supplies
the day and its closing time; the UI shows that time locally. Rankings use earned
credits across the account's languages. Equal scores share a rank; moving above
the next higher score requires one more Basil than that score. Personal best is
the highest daily earned total, independently of participation and spending.

## Energy compatibility and rollout

Starting or resuming lessons and friend rooms no longer spends Sauce. The old
energy account fields, transactions, and refund behavior remain for compatibility
with historical requests; current screens do not present them as an energy bar.

The additive Prisma migrations create private question, batch, photo-identity,
and leaderboard-preference tables, and widen the existing positive Basil credit
constraint. They preserve balances and historical events. Deploy these migrations
before the API and frontend. They have only been applied to disposable local
PostgreSQL during development; no live Supabase database has been changed.

The remaining parts of #90 are spoken-production assessment and its three higher
badge ranks. This implementation intentionally leaves the issue open for those
learning capabilities.
