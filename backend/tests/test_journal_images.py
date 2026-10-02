from unittest.mock import MagicMock
from uuid import uuid4

from app.schemas.base import utc_now
from app.schemas.journals import Journal, JournalDetailResponse, JournalMedia
from app.schemas.media import MediaAsset
from app.services.journals import JournalService


def test_replacing_cover_preserves_other_attachments_and_is_idempotent():
    journal = Journal(
        user_id=uuid4(), language_profile_id=uuid4(), local_date=utc_now().date(), timezone="UTC"
    )
    old = JournalMedia(journal_id=journal.id, media_asset_id=uuid4(), display_order=0)
    extra = JournalMedia(journal_id=journal.id, media_asset_id=uuid4(), display_order=1)
    entry = JournalDetailResponse(journal=journal, media=[old, extra])
    selected = uuid4()
    JournalService._set_cover(entry, selected)
    cover = next(row for row in entry.media if row.display_order == 0)
    assert cover.media_asset_id == selected
    assert extra in entry.media
    assert old not in entry.media
    JournalService._set_cover(entry, selected)
    assert len(entry.media) == 2
    assert next(row for row in entry.media if row.display_order == 0).id == cover.id
    JournalService._set_cover(entry, extra.media_asset_id)
    assert entry.media == [extra]
    assert extra.display_order == 0


def test_text_update_preserves_cover_and_invalid_media_does_not_write():
    import pytest

    from app.repositories.journals import JournalConflictError
    from app.schemas.journals import UpdateJournalRequest

    journal = Journal(
        user_id=uuid4(), language_profile_id=uuid4(), local_date=utc_now().date(), timezone="UTC"
    )
    cover = JournalMedia(journal_id=journal.id, media_asset_id=uuid4(), display_order=0)
    entry = JournalDetailResponse(journal=journal, media=[cover])
    repository = MagicMock()
    repository.change.side_effect = lambda fn: fn([entry])
    users = MagicMock()
    users.get_current_user.return_value.id = journal.user_id
    media = MagicMock()
    media.get_by_ids.return_value = {}
    service = JournalService(repository, users, MagicMock(), media)
    service.update(journal.id, UpdateJournalRequest(title="Edited"))
    assert entry.journal.title == "Edited"
    assert entry.media == [cover]
    repository.change.reset_mock()
    with pytest.raises(JournalConflictError):
        service.update(journal.id, UpdateJournalRequest(media_asset_id=uuid4()))
    repository.change.assert_not_called()


def test_journal_cover_uses_attachment_and_checks_ownership():
    owner = uuid4()
    journal = Journal(
        id=uuid4(),
        user_id=owner,
        language_profile_id=uuid4(),
        local_date=utc_now().date(),
        timezone="UTC",
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    asset = MediaAsset(
        id=uuid4(),
        source="preloaded",
        media_type="image",
        storage_key="preloaded/scenes/cafe.jpg",
        mime_type="image/jpeg",
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    entry = JournalDetailResponse(
        journal=journal,
        media=[
            JournalMedia(
                id=uuid4(),
                journal_id=journal.id,
                media_asset_id=asset.id,
                display_order=0,
                created_at=utc_now(),
                updated_at=utc_now(),
            )
        ],
    )
    media = MagicMock()
    media.get_by_ids.return_value = {asset.id: asset}
    signer = MagicMock()
    signer.resolve.return_value = {asset.storage_key: "https://example.com/signed-cafe.jpg"}
    service = JournalService(MagicMock(), MagicMock(), MagicMock(), media, None, signer)
    result = service._with_images([entry])[0]
    assert result.image_url == "https://example.com/signed-cafe.jpg"
    assert entry.image_url is None
    signer.resolve.assert_called_once_with([asset.storage_key])

    signer.reset_mock()
    media.get_by_ids.return_value = {
        asset.id: asset.model_copy(
            update={
                "source": "userUpload",
                "owner_user_id": uuid4(),
            }
        )
    }
    signer.resolve.return_value = {}
    assert service._with_images([entry])[0].image_url is None
    signer.resolve.assert_called_once_with([])


def test_with_images_resolves_all_attachments_in_one_resolve_call():
    owner = uuid4()
    journal = Journal(
        user_id=owner,
        language_profile_id=uuid4(),
        local_date=utc_now().date(),
        timezone="UTC",
    )
    cover = MediaAsset(
        id=uuid4(),
        source="userUpload",
        owner_user_id=owner,
        media_type="image",
        storage_key="users/x/cover.jpg",
        mime_type="image/jpeg",
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    extra = MediaAsset(
        id=uuid4(),
        source="userUpload",
        owner_user_id=owner,
        media_type="image",
        storage_key="users/x/extra.jpg",
        mime_type="image/jpeg",
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    entry = JournalDetailResponse(
        journal=journal,
        media=[
            JournalMedia(journal_id=journal.id, media_asset_id=cover.id, display_order=0),
            JournalMedia(journal_id=journal.id, media_asset_id=extra.id, display_order=1),
        ],
    )
    media = MagicMock()
    media.get_by_ids.return_value = {cover.id: cover, extra.id: extra}
    signer = MagicMock()
    signer.resolve.return_value = {
        cover.storage_key: "https://example.com/signed-cover.jpg",
        extra.storage_key: "https://example.com/signed-extra.jpg",
    }
    service = JournalService(MagicMock(), MagicMock(), MagicMock(), media, None, signer)

    result = service._with_images([entry])[0]

    assert result.image_url == "https://example.com/signed-cover.jpg"
    assert result.image_urls == {
        cover.id: "https://example.com/signed-cover.jpg",
        extra.id: "https://example.com/signed-extra.jpg",
    }
    media.get_by_ids.assert_called_once()
    signer.resolve.assert_called_once()
    assert sorted(signer.resolve.call_args.args[0]) == sorted(
        [cover.storage_key, extra.storage_key]
    )
