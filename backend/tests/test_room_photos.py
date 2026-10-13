"""Room preparation gates sharing, reuses real provider seams and respects owner edits."""

import copy
import json
from uuid import uuid4, uuid5

import pytest
from pydantic import ValidationError

from app.ai.contracts import VisionModelConfig, VisionModelResponse
from app.ai.features.moderation import ImageModerationError, ImageModerationResult
from app.ai.features.object_grounding.service import GroundedBox
from app.ai.features.scene_analysis import UploadedSceneAnalyzer
from app.ai.features.translation.schemas import SceneTranslationResult
from app.ai.observability import NoOpAITracer
from app.schemas.media import MediaAsset, SceneObject, SceneObjectRelation
from app.services.room_photos import RoomPhotoError, RoomPhotoPreparer, RoomPhotoReview
from app.services.scene_analysis import SceneAnalysisResult


class FakeStorage:
    def __init__(self, data=b"image bytes"):
        self.data, self.calls = data, []

    def download(self, key):
        self.calls.append(key)
        if isinstance(self.data, Exception):
            raise self.data
        return self.data


class FakeModerator:
    def __init__(self, result=None):
        self.result = ImageModerationResult(False) if result is None else result
        self.calls = []

    def moderate(self, image):
        self.calls.append(image)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class FakeAnalyzer:
    def __init__(self, error=None):
        self.calls, self.error = [], error

    def analyze(self, identity, asset, profile, scene):
        self.calls.append((identity, asset, profile, scene))
        if self.error:
            raise self.error
        objects = [
            SceneObject(
                id=uuid5(identity.id, name),
                session_id=identity.id,
                label=name,
                anchor_point={"x": x, "y": 0.5},
                attributes={"color": colour},
            )
            for name, x, colour in [("cup", 0.2, "red"), ("book", 0.8, "blue")]
        ]
        return SceneAnalysisResult(
            title="Desk",
            summary="Old cup summary",
            objects=objects,
            relations=[
                SceneObjectRelation(
                    id=uuid5(identity.id, "next-to"),
                    subject_scene_object_id=objects[0].id,
                    reference_scene_object_id=objects[1].id,
                    relation="next_to",
                )
            ],
        )


class FakeTranslator:
    def __init__(self, error=None):
        self.calls, self.error = [], error

    def translate(self, payload, **options):
        self.calls.append((copy.deepcopy(payload), options))
        if self.error:
            raise self.error
        nouns = {
            "cup": ("taza", "la", "feminine"),
            "book": ("libro", "el", "masculine"),
            "bowl": ("bol", "el", "masculine"),
        }
        translations = {
            "red": "rojo",
            "blue": "azul",
            "green": "verde",
            "next_to": "al lado de",
            "under": "debajo de",
        }
        return SceneTranslationResult(
            objects=[
                {
                    **row,
                    "translation": nouns[row["source"]][0],
                    "article": nouns[row["source"]][1],
                    "gender": nouns[row["source"]][2],
                }
                for row in payload["objects"]
            ],
            **{
                field: [
                    {**row, "translation": translations[row["source"]]} for row in payload[field]
                ]
                for field in ("attributes", "relationships")
            },
        )


@pytest.fixture
def setup_photo():
    owner, photo_id = uuid4(), uuid4()
    asset = MediaAsset(
        owner_user_id=owner,
        media_type="image",
        source="userUpload",
        storage_key="users/test/images/photo.jpg",
        mime_type="image/jpeg",
    )
    profile = {
        "id": uuid4(),
        "room_id": uuid4(),
        "source_language_code": "en",
        "target_language_code": "es",
    }
    analyzer, translator, storage, moderator = (
        FakeAnalyzer(),
        FakeTranslator(),
        FakeStorage(),
        FakeModerator(),
    )
    helper = RoomPhotoPreparer(analyzer, translator, storage=storage, image_moderator=moderator)
    return helper, photo_id, owner, asset, profile


def review_of(analysis):
    return {
        "objects": copy.deepcopy(analysis["objects"]),
        "relations": copy.deepcopy(analysis["relations"]),
    }


def test_analysis_is_private_owner_review_and_does_not_translate_or_create_a_session(setup_photo):
    helper, photo_id, owner, asset, profile = setup_photo
    result = helper.analyze(photo_id, owner, asset, profile)
    identity = helper.analyzer.calls[0][0]
    assert identity.id == photo_id
    assert identity.user_id == owner
    assert result["moderationPassed"] is True
    assert result["photoId"] == str(photo_id) and result["ownerId"] == str(owner)
    assert result["objects"][0]["x"] == 20
    assert result["objects"][0]["color"] == "red"
    assert result["relations"][0]["relation"] == "next_to"
    assert not helper.translator.calls
    assert len(helper.image_moderator.calls) == 1


@pytest.mark.parametrize(
    "verdict,code,retryable",
    [
        (ImageModerationResult(True, ("violence",)), "room_photo_unsafe", False),
        (
            ImageModerationError("secret provider details"),
            "room_photo_moderation_unavailable",
            True,
        ),
        ({"flagged": False}, "room_photo_moderation_unavailable", True),
        (ImageModerationResult(None), "room_photo_moderation_unavailable", True),
    ],
)
def test_moderation_rejection_or_missing_verdict_never_starts_analysis(
    setup_photo, verdict, code, retryable
):
    helper, photo_id, owner, asset, profile = setup_photo
    helper.image_moderator = FakeModerator(verdict)
    with pytest.raises(RoomPhotoError) as caught:
        helper.analyze(photo_id, owner, asset, profile)
    assert caught.value.code == code and caught.value.retryable is retryable
    assert "secret" not in str(caught.value)
    assert helper.analyzer.calls == [] and helper.translator.calls == []


@pytest.mark.parametrize("missing", ["analyzer", "image_moderator", "storage"])
def test_unconfigured_required_services_fail_closed(setup_photo, missing):
    helper, photo_id, owner, asset, profile = setup_photo
    setattr(helper, missing, None)
    with pytest.raises(RoomPhotoError, match="must be configured") as caught:
        helper.analyze(photo_id, owner, asset, profile)
    assert caught.value.code == "room_photo_unavailable"


def test_foreign_upload_is_rejected_before_bytes_or_provider_calls(setup_photo):
    helper, photo_id, _owner, asset, profile = setup_photo
    with pytest.raises(RoomPhotoError) as caught:
        helper.analyze(photo_id, uuid4(), asset, profile)
    assert caught.value.code == "room_photo_review_invalid"
    assert not helper.storage.calls and not helper.image_moderator.calls


def test_supported_language_case_matches_room_admission(setup_photo):
    helper, photo_id, owner, asset, profile = setup_photo
    profile.update(source_language_code="EN", target_language_code="ES")
    assert helper.analyze(photo_id, owner, asset, profile)["moderationPassed"] is True


@pytest.mark.parametrize("problem", ["storage", "analysis"])
def test_preparation_failures_are_safe_and_do_not_publish_success(setup_photo, problem):
    helper, photo_id, owner, asset, profile = setup_photo
    if problem == "storage":
        helper.storage.data = RuntimeError("provider-secret")
    else:
        helper.analyzer.error = RuntimeError("provider-secret")
    with pytest.raises(RoomPhotoError) as caught:
        helper.analyze(photo_id, owner, asset, profile)
    assert caught.value.code == "room_photo_analysis_failed"
    assert "provider-secret" not in str(caught.value)


def test_owner_corrections_are_the_only_facts_translated_and_use_private_room_scope(setup_photo):
    helper, photo_id, owner, asset, profile = setup_photo
    analysis = helper.analyze(photo_id, owner, asset, profile)
    review = review_of(analysis)
    review["objects"][0].update(label="bowl", x=91, y=6, color="green")
    review["relations"][0]["relation"] = "under"
    review["title"] = "My corrected desk"
    result = helper.build_pack(photo_id, owner, profile, analysis, review)
    payload, options = helper.translator.calls[0]
    assert payload["objects"][0]["source"] == "bowl"
    assert payload["attributes"][0]["source"] == "green"
    assert payload["relationships"][0]["source"] == "under"
    assert "cup" not in payload["sceneSummary"]
    assert options["cache_scope"].owner == f"user:{owner}:room:{profile['room_id']}"
    assert result["objects"][0]["label"] == "bowl"
    assert result["objects"][0]["word"] == "el bol"
    assert (result["objects"][0]["x"], result["objects"][0]["y"]) == (91, 6)
    assert result["title"] == "My corrected desk"
    assert analysis["objects"][0]["label"] == "cup"
    assert len(result["targets"]) == 2


@pytest.mark.parametrize("change", ["foreign_owner", "unchecked", "foreign_photo", "new_object"])
def test_untrusted_or_other_photo_review_cannot_reach_translation(setup_photo, change):
    helper, photo_id, owner, asset, profile = setup_photo
    analysis = helper.analyze(photo_id, owner, asset, profile)
    review = review_of(analysis)
    if change == "foreign_owner":
        owner = uuid4()
    elif change == "unchecked":
        analysis["moderationPassed"] = False
    elif change == "foreign_photo":
        photo_id = uuid4()
    else:
        review["objects"][0]["key"] = str(uuid4())
        review["relations"] = []
    with pytest.raises(RoomPhotoError) as caught:
        helper.build_pack(photo_id, owner, profile, analysis, review)
    assert caught.value.code == "room_photo_review_invalid"
    assert not helper.translator.calls


def test_review_rejects_invalid_markers_duplicate_objects_and_foreign_relation_endpoints(
    setup_photo,
):
    helper, photo_id, owner, asset, profile = setup_photo
    review = review_of(helper.analyze(photo_id, owner, asset, profile))
    invalid = copy.deepcopy(review)
    invalid["objects"][0]["x"] = 101
    with pytest.raises(ValidationError):
        RoomPhotoReview.model_validate(invalid)
    invalid = copy.deepcopy(review)
    invalid["objects"][1]["key"] = invalid["objects"][0]["key"]
    with pytest.raises(ValidationError):
        RoomPhotoReview.model_validate(invalid)
    invalid = copy.deepcopy(review)
    invalid["relations"][0]["referenceObjectKey"] = str(uuid4())
    with pytest.raises(ValidationError):
        RoomPhotoReview.model_validate(invalid)


def test_translation_failure_and_ambiguous_facts_allow_owner_to_correct_the_photo(setup_photo):
    helper, photo_id, owner, asset, profile = setup_photo
    analysis = helper.analyze(photo_id, owner, asset, profile)
    review = review_of(analysis)
    helper.translator.error = RuntimeError("secret provider body")
    with pytest.raises(RoomPhotoError) as caught:
        helper.build_pack(photo_id, owner, profile, analysis, review)
    assert caught.value.code == "room_photo_translation_failed"
    assert "secret" not in str(caught.value)
    helper.translator.error = None
    for obj in review["objects"]:
        obj["color"] = "red"
    review["relations"] = []
    with pytest.raises(RoomPhotoError) as caught:
        helper.build_pack(photo_id, owner, profile, analysis, review)
    assert caught.value.code == "room_photo_no_clues" and caught.value.retryable
    assert analysis["moderationPassed"] is True


class FakeVisionClient:
    def __init__(self, output):
        self.output, self.calls = output, []

    def generate(self, request):
        self.calls.append(request)
        return VisionModelResponse(
            output_text=json.dumps(self.output),
            model_name="test-model",
            prompt_version=request.prompt_version,
        )


class FakeGrounder:
    def __init__(self):
        self.calls = []

    def ground(self, image, labels):
        self.calls.append((image, labels))
        return {"cup": GroundedBox(x=0.6, y=0.2, width=0.2, height=0.2, score=0.99)}


def test_actual_uploaded_analyzer_reuses_grounding_and_one_moderation_without_shared_mutation(
    setup_photo,
):
    helper, photo_id, owner, asset, profile = setup_photo
    output = {
        "suggestedSceneTitle": "Desk",
        "summary": "A cup and book.",
        "objects": [
            {
                "objectKey": key,
                "label": label,
                "confidenceScore": 0.9,
                "boundingBox": {"x": x, "y": 0.1, "width": 0.1, "height": 0.1},
                "attributes": [{"type": "color", "value": colour}],
            }
            for key, label, x, colour in [("cup", "cup", 0.1, "red"), ("book", "book", 0.3, "blue")]
        ],
        "relations": [],
    }
    client, grounder = FakeVisionClient(output), FakeGrounder()
    original_moderator = FakeModerator(ImageModerationError("should not be called"))
    analyzer = UploadedSceneAnalyzer(
        helper.storage,
        client,
        VisionModelConfig(model_name="test-model", max_retries=0),
        tracer=NoOpAITracer(),
        provider="openai",
        object_grounder=grounder,
        image_moderator=original_moderator,
    )
    helper.analyzer = analyzer
    result = helper.analyze(photo_id, owner, asset, profile)
    assert len(helper.storage.calls) == len(helper.image_moderator.calls) == len(client.calls) == 1
    assert grounder.calls[0][1] == ["cup", "book"]
    assert result["objects"][0]["key"] == str(uuid5(photo_id, "scene-object:cup"))
    assert result["objects"][0]["x"] == pytest.approx(70)
    assert result["objects"][0]["y"] == pytest.approx(30)
    assert analyzer._storage is helper.storage
    assert analyzer._image_moderator is original_moderator
    assert original_moderator.calls == []
