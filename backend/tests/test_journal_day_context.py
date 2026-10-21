from datetime import date, datetime, time, timedelta
from unittest.mock import MagicMock
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest

from app.repositories.journals import FutureJournalDateError
from app.repositories.media_assets import SessionImage
from app.schemas.base import utc_now
from app.schemas.journals import Journal, JournalDetailResponse, UpsertTodayJournalRequest
from app.schemas.media import MediaAsset
from app.services.journals import JournalService

TIMEZONE = "Asia/Singapore"


def _service(rows, media=None, signer=None):
    user = MagicMock()
    user.id = uuid4()
    user.timezone = TIMEZONE
    users = MagicMock()
    users.get_current_user.return_value = user
    profiles = MagicMock()
    profiles.list_profiles.return_value = [MagicMock(id=uuid4(), is_active=True)]
    repository = MagicMock()
    repository.read_for_user.return_value = rows
    repository.read_for_date.return_value = None
    repository.read_one.return_value = None
    repository.change.side_effect = lambda fn: fn(rows)
    service = JournalService(repository, users, profiles, media, None, signer)
    return service, user, profiles.list_profiles.return_value[0]


def _asset(storage_key):
    return MediaAsset(
        id=uuid4(),
        source="userUpload",
        owner_user_id=uuid4(),
        media_type="image",
        storage_key=storage_key,
        mime_type="image/jpeg",
        created_at=utc_now(),
        updated_at=utc_now(),
    )


def test_day_context_returns_journal_and_signed_eligible_photos():
    today = datetime.now(ZoneInfo(TIMEZONE)).date()
    service, user, _ = _service([], media=MagicMock(), signer=MagicMock())
    journal = Journal(
        user_id=user.id,
        language_profile_id=uuid4(),
        local_date=today,
        timezone=TIMEZONE,
    )
    entry = JournalDetailResponse(journal=journal)
    service.repository.read_for_date.return_value = entry
    asset = _asset("users/x/photo.jpg")
    completed_at = datetime.now(ZoneInfo(TIMEZONE))
    service.media.list_completed_session_images.return_value = [
        SessionImage(session_id=uuid4(), completed_at=completed_at, asset=asset)
    ]
    service.private_media_urls.resolve.return_value = {
        asset.storage_key: "https://example.com/signed.jpg"
    }

    context = service.day_context(None)

    assert context.local_date == today
    assert context.journal == journal
    assert context.can_create is False
    assert len(context.eligible_photos) == 1
    option = context.eligible_photos[0]
    assert option.media_asset_id == asset.id
    assert option.image_url == "https://example.com/signed.jpg"
    key_calls = [
        call.args[0] for call in service.private_media_urls.resolve.call_args_list if call.args[0]
    ]
    assert key_calls == [[asset.storage_key]]


def test_day_context_queries_local_midnight_window_in_user_timezone():
    yesterday = datetime.now(ZoneInfo(TIMEZONE)).date() - timedelta(days=1)
    media = MagicMock()
    media.list_completed_session_images.return_value = []
    service, user, _ = _service([], media=media)

    service.day_context(yesterday)

    media.list_completed_session_images.assert_called_once()
    _, start, end = media.list_completed_session_images.call_args.args
    tz = ZoneInfo(TIMEZONE)
    assert start == datetime.combine(yesterday, time.min, tzinfo=tz)
    assert end == start + timedelta(days=1)
    assert start.utcoffset() == timedelta(hours=8)


def test_day_context_deduplicates_repeated_asset_across_sessions():
    today = datetime.now(ZoneInfo(TIMEZONE)).date()
    media = MagicMock()
    asset = _asset("preloaded/scenes/cafe.jpg")
    media.list_completed_session_images.return_value = [
        SessionImage(session_id=uuid4(), completed_at=utc_now(), asset=asset),
        SessionImage(session_id=uuid4(), completed_at=utc_now(), asset=asset),
    ]
    service, _, _ = _service([], media=media)

    context = service.day_context(today)

    assert [option.media_asset_id for option in context.eligible_photos] == [asset.id]


def test_day_context_includes_every_translated_term_from_that_day():
    today = datetime.now(ZoneInfo(TIMEZONE)).date()
    media = MagicMock()
    media.list_completed_session_images.return_value = []
    media.list_session_translation_suggestions.return_value = [
        "mesa",
        "roja",
        "al lado de",
    ]
    service, user, profile = _service([], media=media)

    context = service.day_context(today)

    assert context.suggested_words == ["mesa", "roja", "al lado de"]
    _, language_profile_id, start, end = media.list_session_translation_suggestions.call_args.args
    assert language_profile_id == profile.id
    assert start == datetime.combine(today, time.min, tzinfo=ZoneInfo(TIMEZONE))
    assert end == start + timedelta(days=1)


def test_day_context_rejects_future_dates():
    service, _, _ = _service([], media=MagicMock())
    tomorrow = datetime.now(ZoneInfo(TIMEZONE)).date() + timedelta(days=1)
    with pytest.raises(FutureJournalDateError):
        service.day_context(tomorrow)


def test_upsert_creates_and_updates_past_day_entry():
    rows = []
    service, user, profile = _service(rows, media=MagicMock())
    past = datetime.now(ZoneInfo(TIMEZONE)).date() - timedelta(days=3)
    request = UpsertTodayJournalRequest(
        language_profile_id=profile.id, title="Backfill", content="Wrote late.", selected_words=[]
    )

    created = service.upsert(request, past)
    assert created.local_date == past
    assert created.timezone == TIMEZONE
    assert len(rows) == 1

    updated = service.upsert(request, past)
    assert updated.id == created.id
    assert len(rows) == 1


def test_upsert_rejects_future_dates():
    service, _, profile = _service([], media=MagicMock())
    tomorrow = date.today() + timedelta(days=7)
    request = UpsertTodayJournalRequest(language_profile_id=profile.id, content="Future.")
    with pytest.raises(FutureJournalDateError):
        service.upsert(request, tomorrow)


def test_future_date_error_maps_to_dedicated_409_code():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api.learning_errors import register_learning_errors

    app = FastAPI()
    register_learning_errors(app)

    @app.get("/journal/{local_date}/context")
    def context(local_date: date):
        raise FutureJournalDateError("Cannot create a journal entry for a future date.")

    response = TestClient(app).get("/journal/2999-01-01/context")
    assert response.status_code == 409
    assert response.json() == {
        "detail": {
            "code": "journal_future_date",
            "message": "Cannot create a journal entry for a future date.",
        }
    }
