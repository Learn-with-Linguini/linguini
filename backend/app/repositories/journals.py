from collections.abc import Callable
from datetime import date
from typing import Protocol
from uuid import UUID

from app.schemas.journals import JournalDetailResponse


class JournalStorageError(Exception):
    pass


class JournalConflictError(Exception):
    pass


class FutureJournalDateError(JournalConflictError):
    pass


class JournalNotFoundError(Exception):
    pass


def validate_entries(rows: list[JournalDetailResponse]) -> None:
    """Check aggregate references before a write or import; offsets use code points."""
    if len({row.journal.id for row in rows}) != len(rows):
        raise ValueError("Duplicate journal IDs.")
    if len({(row.journal.user_id, row.journal.local_date) for row in rows}) != len(rows):
        raise ValueError("Only one journal per user and local date is allowed.")
    for entry in rows:
        revisions = {row.id: row for row in entry.revisions}
        if (
            entry.journal.current_revision_id is not None
            and entry.journal.current_revision_id not in revisions
        ):
            raise ValueError("Current revision must belong to this journal.")
        for items in (entry.media, entry.revisions, entry.suggestions, entry.word_mentions):
            if len({row.id for row in items}) != len(items):
                raise ValueError("Duplicate journal child IDs.")
        for items, fields in (
            (entry.revisions, ("revision_number",)),
            (entry.media, ("display_order",)),
            (entry.media, ("media_asset_id",)),
            (
                entry.word_mentions,
                ("journal_revision_id", "vocabulary_item_id", "start_offset", "end_offset"),
            ),
        ):
            if len({tuple(getattr(row, field) for field in fields) for row in items}) != len(items):
                raise ValueError("Duplicate revision, media order or word occurrence.")
        for row in [*entry.media, *entry.revisions, *entry.suggestions]:
            if row.journal_id != entry.journal.id:
                raise ValueError("Journal child belongs to another journal.")
        for annotation in [*entry.suggestions, *entry.word_mentions]:
            revision_id = (
                getattr(annotation, "base_revision_id", None) or annotation.journal_revision_id
            )
            revision = revisions.get(revision_id)
            excerpt = getattr(annotation, "original_text", None)
            if excerpt is None:
                excerpt = annotation.matched_text
            if (
                revision is None
                or annotation.end_offset > len(revision.content)
                or revision.content[annotation.start_offset : annotation.end_offset] != excerpt
            ):
                raise ValueError("Annotation does not match its revision text.")


class JournalRepository(Protocol):
    def read(self) -> list[JournalDetailResponse]: ...

    def read_for_user(self, limit: int | None = None) -> list[JournalDetailResponse]: ...

    def read_one(self, journal_id: UUID) -> JournalDetailResponse | None: ...

    def read_for_date(self, local_date: date) -> JournalDetailResponse | None: ...

    def change[T](self, action: Callable[[list[JournalDetailResponse]], T]) -> T: ...
