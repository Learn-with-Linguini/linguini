from datetime import date, datetime, time, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from app.repositories.journals import (
    FutureJournalDateError,
    JournalConflictError,
    JournalNotFoundError,
    JournalRepository,
)
from app.repositories.media_assets import MediaAssetRepository, SessionImage
from app.repositories.vocabulary import VocabularyRepository
from app.schemas.base import utc_now
from app.schemas.enums import JournalStatus, JournalSuggestionStatus, MediaSource, MediaType
from app.schemas.journals import (
    AddJournalMediaRequest,
    Journal,
    JournalDetailResponse,
    JournalMedia,
    JournalPhotoOption,
    JournalRevision,
    JournalSuggestion,
    JournalTodayContextResponse,
    UpdateJournalRequest,
    UpsertTodayJournalRequest,
)
from app.services.language_profiles import LanguageProfileService
from app.services.media_urls import PrivateMediaUrls, public_media_url
from app.services.users import UserService

DEFAULT_JOURNAL_LIST_LIMIT = 365


class JournalService:
    def __init__(
        self,
        repository: JournalRepository,
        users: UserService,
        profiles: LanguageProfileService,
        media: MediaAssetRepository | None = None,
        media_public_base_url: str | None = None,
        private_media_urls: PrivateMediaUrls | None = None,
        vocabulary: VocabularyRepository | None = None,
    ) -> None:
        self.repository = repository
        self.users = users
        self.profiles = profiles
        self.media = media
        self.media_public_base_url = media_public_base_url
        self.private_media_urls = private_media_urls
        self.vocabulary = vocabulary

    def _with_images(self, rows: list[JournalDetailResponse]) -> list[JournalDetailResponse]:
        covers = {
            row.journal.id: min(row.media, key=lambda media: media.display_order).media_asset_id
            for row in rows
            if row.media
        }
        asset_ids = {media.media_asset_id for row in rows for media in row.media}
        assets = self.media.get_by_ids(list(asset_ids)) if self.media and asset_ids else {}
        keys: dict[UUID, str] = {}
        attachment_keys: dict[UUID, dict[UUID, str]] = {}
        for row in rows:
            accessible = {
                media.media_asset_id: assets[media.media_asset_id].storage_key
                for media in row.media
                if (
                    media.media_asset_id in assets
                    and assets[media.media_asset_id].media_type == MediaType.IMAGE
                    and (
                        assets[media.media_asset_id].owner_user_id == row.journal.user_id
                        or assets[media.media_asset_id].source == MediaSource.PRELOADED
                    )
                )
            }
            attachment_keys[row.journal.id] = accessible
            cover_id = covers.get(row.journal.id)
            if cover_id in accessible:
                keys[row.journal.id] = accessible[cover_id]
        all_keys = [key for mapping in attachment_keys.values() for key in mapping.values()]
        urls = (
            self.private_media_urls.resolve(list(dict.fromkeys(all_keys)))
            if self.private_media_urls
            else {
                key: public_media_url(key, self.media_public_base_url) for key in all_keys
            }
        )
        return [
            row.model_copy(
                update={
                    "image_url": urls.get(keys.get(row.journal.id)),
                    "image_urls": {
                        asset_id: urls[key]
                        for asset_id, key in attachment_keys[row.journal.id].items()
                        if urls.get(key) is not None
                    },
                }
            )
            for row in rows
        ]

    @staticmethod
    def _find(rows, journal_id, user_id):
        entry = next(
            (
                row
                for row in rows
                if row.journal.id == journal_id and row.journal.user_id == user_id
            ),
            None,
        )
        if entry is None:
            raise JournalNotFoundError("Journal not found.")
        return entry

    def _check_media(self, asset_id: UUID, user_id: UUID, media_type: MediaType) -> None:
        asset = self.media.get_by_ids([asset_id]).get(asset_id) if self.media is not None else None
        if (
            asset is None
            or asset.media_type != media_type
            or not (
                asset.owner_user_id == user_id
                or media_type == MediaType.IMAGE
                and asset.source == MediaSource.PRELOADED
            )
        ):
            raise JournalConflictError(
                "Journal media is missing, inaccessible or has the wrong type."
            )

    def list_entries(
        self, limit: int | None = DEFAULT_JOURNAL_LIST_LIMIT
    ) -> list[JournalDetailResponse]:
        user = self.users.get_current_user()
        return self._with_images(
            [
                row
                for row in self.repository.read_for_user(limit=limit)
                if row.journal.user_id == user.id
            ]
        )

    def get_entry(self, journal_id: UUID) -> JournalDetailResponse:
        user = self.users.get_current_user()
        entry = self.repository.read_one(journal_id)
        if entry is None or entry.journal.user_id != user.id:
            raise JournalNotFoundError("Journal not found.")
        return self._with_images([entry])[0]

    def today(self) -> JournalTodayContextResponse:
        return self.day_context(None)

    def day_context(self, day: date | None = None) -> JournalTodayContextResponse:
        user = self.users.get_current_user()
        tz = ZoneInfo(user.timezone)
        today = datetime.now(tz).date()
        day = day or today
        if day > today:
            raise FutureJournalDateError("Cannot create a journal entry for a future date.")
        entry = self.repository.read_for_date(day)
        if entry is not None and entry.journal.user_id != user.id:
            entry = None
        eligible_photos: list[JournalPhotoOption] = []
        suggested_words: list[str] = []
        if self.media is not None:
            start = datetime.combine(day, time.min, tzinfo=tz)
            end = start + timedelta(days=1)
            language_profile_id = (
                entry.journal.language_profile_id
                if entry is not None
                else next(
                    (profile.id for profile in self.profiles.list_profiles() if profile.is_active),
                    None,
                )
            )
            if language_profile_id is not None:
                suggested_words = self.media.list_session_translation_suggestions(
                    user.id, language_profile_id, start, end
                )
            unique: dict[UUID, SessionImage] = {}
            for image in self.media.list_completed_session_images(user.id, start, end):
                unique.setdefault(image.asset.id, image)
            images = list(unique.values())
            keys = [image.asset.storage_key for image in images]
            urls = (
                self.private_media_urls.resolve(keys)
                if self.private_media_urls
                else {key: public_media_url(key, self.media_public_base_url) for key in keys}
            )
            eligible_photos = [
                JournalPhotoOption(
                    media_asset_id=image.asset.id,
                    image_url=urls.get(image.asset.storage_key),
                    session_id=image.session_id,
                    completed_at=image.completed_at,
                )
                for image in images
            ]
        return JournalTodayContextResponse(
            local_date=day,
            journal=entry.journal if entry else None,
            eligible_photos=eligible_photos,
            suggested_words=suggested_words,
            can_create=entry is None,
        )

    @staticmethod
    def _revision(entry: JournalDetailResponse, content: str, created_by="user") -> JournalRevision:
        latest = next(
            (row for row in entry.revisions if row.id == entry.journal.current_revision_id), None
        )
        if latest is not None and latest.content == content:
            return latest
        revision = JournalRevision(
            journal_id=entry.journal.id,
            revision_number=max((row.revision_number for row in entry.revisions), default=0) + 1,
            content=content,
            created_by=created_by,
        )
        entry.revisions.append(revision)
        entry.journal.current_revision_id = revision.id
        entry.journal.updated_at = utc_now()
        return revision

    @staticmethod
    def _set_cover(entry: JournalDetailResponse, asset_id: UUID | None) -> None:
        cover = min(entry.media, key=lambda row: row.display_order, default=None)
        if cover is not None and cover.media_asset_id == asset_id:
            return
        order = cover.display_order if cover else 0
        if cover:
            entry.media.remove(cover)
        if asset_id is not None:
            existing = next((row for row in entry.media if row.media_asset_id == asset_id), None)
            if existing:
                existing.display_order = order
            else:
                entry.media.append(
                    JournalMedia(
                        journal_id=entry.journal.id,
                        media_asset_id=asset_id,
                        display_order=order,
                    )
                )

    def _record_usage(self, journal: Journal, user_id: UUID) -> None:
        if self.vocabulary is not None:
            self.vocabulary.record_journal_usage(
                user_id=user_id,
                language_profile_id=journal.language_profile_id,
                journal_id=journal.id,
                words=journal.selected_words,
                occurred_at=utc_now(),
            )

    def upsert_today(self, request: UpsertTodayJournalRequest) -> Journal:
        return self.upsert(request, None)

    def upsert(self, request: UpsertTodayJournalRequest, day: date | None = None) -> Journal:
        user = self.users.get_current_user()
        today = datetime.now(ZoneInfo(user.timezone)).date()
        day = day or today
        if day > today:
            raise FutureJournalDateError("Cannot create a journal entry for a future date.")
        if request.media_asset_id is not None:
            self._check_media(request.media_asset_id, user.id, MediaType.IMAGE)
        if not any(
            row.id == request.language_profile_id and row.is_active
            for row in self.profiles.list_profiles()
        ):
            raise JournalConflictError("Choose the active language profile before saving.")

        def change(rows: list[JournalDetailResponse]) -> Journal:
            entry = next(
                (
                    row
                    for row in rows
                    if row.journal.user_id == user.id and row.journal.local_date == day
                ),
                None,
            )
            if entry is None:
                entry = JournalDetailResponse(
                    journal=Journal(
                        user_id=user.id,
                        language_profile_id=request.language_profile_id,
                        local_date=day,
                        timezone=user.timezone,
                    )
                )
                rows.append(entry)
            elif entry.journal.language_profile_id != request.language_profile_id:
                raise JournalConflictError(
                    "That day's journal uses another language. Open it from journal history."
                )
            if request.content is not None:
                entry.journal.title = request.title
                entry.journal.selected_words = request.selected_words
                self._revision(entry, request.content)
            if "media_asset_id" in request.model_fields_set:
                self._set_cover(entry, request.media_asset_id)
            return entry.journal

        journal = self.repository.change(change)
        self._record_usage(journal, user.id)
        return journal

    def update(self, journal_id: UUID, request: UpdateJournalRequest) -> Journal:
        user = self.users.get_current_user()
        if request.media_asset_id is not None:
            self._check_media(request.media_asset_id, user.id, MediaType.IMAGE)
        if request.audio_media_asset_id is not None:
            self._check_media(request.audio_media_asset_id, user.id, MediaType.AUDIO)

        def change(rows: list[JournalDetailResponse]) -> Journal:
            entry = next(
                (
                    row
                    for row in rows
                    if row.journal.id == journal_id and row.journal.user_id == user.id
                ),
                None,
            )
            if entry is None:
                raise JournalNotFoundError("Journal not found.")
            for field, value in request.model_dump(exclude_unset=True, by_alias=False).items():
                if field not in ("content", "media_asset_id") and (
                    value is not None or field == "audio_media_asset_id"
                ):
                    setattr(entry.journal, field, value)
            if request.content is not None:
                self._revision(entry, request.content)
            if "media_asset_id" in request.model_fields_set:
                self._set_cover(entry, request.media_asset_id)
            entry.journal.updated_at = utc_now()
            return entry.journal

        journal = self.repository.change(change)
        self._record_usage(journal, user.id)
        return journal

    def add_revision(self, journal_id: UUID, content: str) -> JournalRevision:
        journal = self.update(journal_id, UpdateJournalRequest(content=content))
        return next(
            row
            for row in self.get_entry(journal_id).revisions
            if row.id == journal.current_revision_id
        )

    def add_media(self, journal_id: UUID, request: AddJournalMediaRequest) -> JournalMedia:
        user = self.users.get_current_user()
        self._check_media(request.media_asset_id, user.id, MediaType.IMAGE)

        def change(rows):
            entry = self._find(rows, journal_id, user.id)
            existing = next(
                (row for row in entry.media if row.media_asset_id == request.media_asset_id), None
            )
            if existing is not None:
                if (
                    existing.display_order != request.display_order
                    or existing.caption != request.caption
                ):
                    raise JournalConflictError("Photo already attached with different metadata.")
                return existing
            if any(row.display_order == request.display_order for row in entry.media):
                raise JournalConflictError("Photo position is occupied.")
            media = JournalMedia(journal_id=journal_id, **request.model_dump(by_alias=False))
            entry.media.append(media)
            entry.journal.updated_at = utc_now()
            return media

        return self.repository.change(change)

    def remove_media(self, journal_id: UUID, media_asset_id: UUID) -> None:
        user = self.users.get_current_user()

        def change(rows):
            entry = self._find(rows, journal_id, user.id)
            if any(row.media_asset_id == media_asset_id for row in entry.media):
                entry.media = [row for row in entry.media if row.media_asset_id != media_asset_id]
                entry.journal.updated_at = utc_now()

        self.repository.change(change)

    def complete(self, journal_id: UUID, revision_id: UUID) -> Journal:
        user = self.users.get_current_user()

        def change(rows):
            entry = self._find(rows, journal_id, user.id)
            if not any(row.id == revision_id for row in entry.revisions):
                raise JournalConflictError("Revision does not belong to this journal.")
            if (
                entry.journal.status == JournalStatus.COMPLETED
                and entry.journal.current_revision_id == revision_id
            ):
                return entry.journal
            entry.journal.current_revision_id = revision_id
            entry.journal.completed_at = utc_now()
            entry.journal.status = JournalStatus.COMPLETED
            entry.journal.updated_at = utc_now()
            return entry.journal

        return self.repository.change(change)

    def review_suggestion(self, suggestion_id: UUID, *, accept: bool) -> JournalSuggestion:
        user = self.users.get_current_user()

        def change(rows):
            pair = next(
                (
                    (entry, suggestion)
                    for entry in rows
                    if entry.journal.user_id == user.id
                    for suggestion in entry.suggestions
                    if suggestion.id == suggestion_id
                ),
                None,
            )
            if pair is None:
                raise JournalNotFoundError("Suggestion not found.")
            entry, suggestion = pair
            status = (
                JournalSuggestionStatus.ACCEPTED if accept else JournalSuggestionStatus.REJECTED
            )
            if suggestion.status == status:
                return suggestion
            if suggestion.status != JournalSuggestionStatus.PENDING:
                raise JournalConflictError("Suggestion has already been reviewed.")
            if accept:
                if entry.journal.current_revision_id != suggestion.base_revision_id:
                    raise JournalConflictError(
                        "Suggestion is stale; request feedback for the current revision."
                    )
                base = next(row for row in entry.revisions if row.id == suggestion.base_revision_id)
                if (
                    base.content[suggestion.start_offset : suggestion.end_offset]
                    != suggestion.original_text
                ):
                    raise JournalConflictError("Suggestion no longer matches its revision.")
                content = (
                    base.content[: suggestion.start_offset]
                    + suggestion.suggested_text
                    + base.content[suggestion.end_offset :]
                )
                if len(content) > 20_000:
                    raise JournalConflictError(
                        "Accepted suggestion would exceed the journal length limit."
                    )
                self._revision(entry, content, created_by="merged")
            suggestion.status = status
            suggestion.updated_at = utc_now()
            return suggestion

        return self.repository.change(change)
