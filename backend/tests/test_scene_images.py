from datetime import UTC, datetime
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.schemas.media import MediaAsset
from app.schemas.scenes import PreloadedSceneDetail
from app.services.media_urls import (
    MediaUrlError,
    PrivateMediaUrls,
    SignedUrlCache,
    public_media_url,
)
from app.services.scenes import SceneService

BASE = "https://project.supabase.co/storage/v1/object/public/scenes"


@pytest.mark.parametrize(
    ("key", "base", "expected"),
    [
        ("spanish/café #1?.jpg", BASE + "/", BASE + "/spanish/caf%C3%A9%20%231%3F.jpg"),
        ("demo-art/street", BASE, None),
        ("cafe.jpg", None, None),
        ("https://example.com/cafe.jpg", None, "https://example.com/cafe.jpg"),
        ("javascript:alert(1)", BASE, None),
        ("//example.com/cafe.jpg", BASE, None),
    ],
)
def test_image_url(key, base, expected):
    assert public_media_url(key, base) == expected


@pytest.mark.parametrize("private", [False, True])
def test_list_and_detail_use_current_media_key(private):
    asset = MediaAsset(
        id=uuid4(),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        source="preloaded",
        media_type="image",
        storage_key="old.jpg",
        mime_type="image/jpeg",
    )
    scene = PreloadedSceneDetail(
        scene_id="cafe",
        language="Spanish",
        title="Cafe",
        media_asset=asset,
        items=[
            {
                "id": "cup",
                "word": "taza",
                "translation": "cup",
                "word_class": "noun",
                "gender": "la",
                "marker": 1,
                "x": 30,
                "y": 40,
                "example": "",
                "example_translation": "",
            }
        ],
        tasks=[
            {
                "id": "task",
                "kind": "word",
                "title": "Cup",
                "summary": "",
                "xp": 1,
                "item_ids": ["cup"],
            }
        ],
        rounds=[
            {
                "id": "round",
                "clue": "Cup",
                "clue_translation": "",
                "answer_id": "cup",
                "choices": [{"id": "cup", "label": "Cup"}],
                "encouragement": "",
            }
        ],
        prompts=[
            {"id": "prompt", "item_id": "cup", "suggestions": [], "llm_guess": "", "feedback": ""}
        ],
    )
    repository = MagicMock()
    repository.list_scenes.return_value = [scene]
    signer = MagicMock() if private else None
    expected_url = BASE + "/old.jpg"
    if signer:
        expected_url = (
            "https://project.supabase.co/storage/v1/object/sign/scenes/old.jpg?token=test"
        )
        signer.resolve.return_value = {"old.jpg": expected_url}
    service = SceneService(repository, BASE, signer)
    summary = service.list_scenes("es")[0]
    detail = service.get_scene("cafe", "es")
    assert summary.model_dump(by_alias=True)["imageUrl"] == expected_url
    assert detail.image_url == summary.image_url
    assert detail.items == scene.items
    assert scene.image_url is None
    if signer:
        signer.resolve.assert_called_with(["old.jpg"])


def test_signing_batches_paths_and_keeps_credentials_on_server(monkeypatch):
    import httpx

    calls = []

    def post(url, **kwargs):
        calls.append((url, kwargs))
        return httpx.Response(
            200,
            request=httpx.Request("POST", url),
            json=[
                {
                    "path": "preloaded/scenes/bedroom.jpg",
                    "error": None,
                    "signedURL": (
                        "/object/sign/media-assets/preloaded/scenes/bedroom.jpg?token=test"
                    ),
                }
            ],
        )

    monkeypatch.setattr(httpx, "post", post)
    resolver = PrivateMediaUrls("https://project.supabase.co", "media-assets", "server-secret")
    result = resolver.resolve(["preloaded/scenes/bedroom.jpg"] * 2 + ["demo-art/street"])
    assert result["preloaded/scenes/bedroom.jpg"] == (
        "https://project.supabase.co/storage/v1/object/sign/media-assets/"
        "preloaded/scenes/bedroom.jpg?token=test"
    )
    assert result["demo-art/street"] is None
    assert len(calls) == 1
    assert calls[0][1]["json"] == {"paths": ["preloaded/scenes/bedroom.jpg"], "expiresIn": 3600}
    assert calls[0][1]["headers"]["Authorization"] == "Bearer server-secret"
    assert "server-secret" not in str(result)


def test_signed_url_cache_serves_repeat_resolves(monkeypatch):
    import httpx

    calls = []

    def post(url, **kwargs):
        calls.append((url, kwargs))
        return httpx.Response(
            200,
            request=httpx.Request("POST", url),
            json=[
                {
                    "path": "preloaded/scenes/bedroom.jpg",
                    "error": None,
                    "signedURL": (
                        "/object/sign/media-assets/preloaded/scenes/bedroom.jpg?token=test"
                    ),
                }
            ],
        )

    monkeypatch.setattr(httpx, "post", post)
    resolver = PrivateMediaUrls(
        "https://project.supabase.co",
        "media-assets",
        "server-secret",
        cache=SignedUrlCache(),
    )
    first = resolver.resolve(["preloaded/scenes/bedroom.jpg"])
    second = resolver.resolve(["preloaded/scenes/bedroom.jpg"])
    assert first == second
    assert second["preloaded/scenes/bedroom.jpg"].endswith("bedroom.jpg?token=test")
    assert len(calls) == 1


@pytest.mark.parametrize("payload", [[], {}, [{"path": "photo.jpg", "error": "missing"}]])
def test_signing_failure_does_not_fall_back_to_public_url(monkeypatch, payload):
    import httpx

    monkeypatch.setattr(
        httpx,
        "post",
        lambda url, **kwargs: httpx.Response(
            200,
            request=httpx.Request("POST", url),
            json=payload,
        ),
    )
    with pytest.raises(MediaUrlError, match="Unable to sign"):
        PrivateMediaUrls("https://project.supabase.co", "media-assets", "secret").resolve(
            ["photo.jpg"]
        )


def test_signing_requires_server_credentials():
    with pytest.raises(MediaUrlError, match="not configured"):
        PrivateMediaUrls("https://project.supabase.co", "media-assets", "").resolve(["photo.jpg"])


def test_new_supabase_secret_is_not_sent_as_bearer():
    resolver = PrivateMediaUrls(
        "https://project.supabase.co", "media-assets", "sb_secret_test"
    )
    assert resolver._headers() == {"apikey": "sb_secret_test"}
