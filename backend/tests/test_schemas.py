from uuid import uuid4

import pytest
from pydantic import TypeAdapter, ValidationError

from app.schemas.enums import (
    ISpyInteractionMode,
    PartOfSpeech,
    SessionMode,
    TaskKind,
    TaskPhase,
)
from app.schemas.media import BoundingBox
from app.schemas.tasks import (
    ISpyRoundContent,
    SessionTask,
    SessionTaskPublic,
    SubmitObjectSelectionAttemptRequest,
    SubmitTaskAttemptRequest,
    VocabularyIntroductionContent,
)
from app.schemas.users import UpdateUserRequest


def test_api_models_accept_and_emit_camel_case() -> None:
    request = SubmitObjectSelectionAttemptRequest.model_validate({"sceneObjectId": str(uuid4())})

    dumped = request.model_dump(mode="json")

    assert "sceneObjectId" in dumped
    assert "scene_object_id" not in dumped


def test_walkthrough_version_is_bounded_and_emitted_in_camel_case() -> None:
    request = UpdateUserRequest.model_validate({"walkthroughVersionSeen": 1})
    assert request.model_dump(mode="json")["walkthroughVersionSeen"] == 1
    with pytest.raises(ValidationError):
        UpdateUserRequest(walkthrough_version_seen=-1)


def test_user_attribution_is_validated_and_emitted_in_camel_case() -> None:
    payload = {
        "utmSource": "tiktok",
        "utmMedium": "social",
        "utmCampaign": "public_beta",
        "utmContent": "week_1_photo",
        "utmTerm": "learn_spanish",
    }
    request = UpdateUserRequest.model_validate(payload)
    dumped = request.model_dump(mode="json")
    assert dumped["utmSource"] == "tiktok"
    assert dumped["utmMedium"] == "social"
    assert dumped["utmCampaign"] == "public_beta"
    assert dumped["utmContent"] == "week_1_photo"
    assert dumped["utmTerm"] == "learn_spanish"


def test_bounding_box_must_remain_inside_image() -> None:
    with pytest.raises(ValidationError):
        BoundingBox(x="0.8", y="0.1", width="0.3", height="0.2")


def test_task_content_must_match_kind() -> None:
    content = VocabularyIntroductionContent(
        title="Tree",
        vocabulary_item_id=uuid4(),
        target_text="árbol",
        translation="tree",
        part_of_speech=PartOfSpeech.NOUN,
    )

    with pytest.raises(ValidationError):
        SessionTask(
            session_id=uuid4(),
            phase=TaskPhase.ISPY,
            kind=TaskKind.ISPY_ROUND,
            order_index=0,
            public_content=content,
        )


def test_public_task_does_not_serialize_answer_key() -> None:
    internal = SessionTask(
        session_id=uuid4(),
        phase=TaskPhase.ISPY,
        kind=TaskKind.ISPY_ROUND,
        order_index=0,
        public_content=ISpyRoundContent(
            clue="Veo algo verde.",
            interaction_mode=ISpyInteractionMode.SELECT_OBJECT,
        ),
        answer_key={"correctSceneObjectId": str(uuid4())},
    )

    public = SessionTaskPublic.from_internal(internal, mode=SessionMode.LESSON)

    assert "answerKey" not in public.model_dump(mode="json")


def test_attempt_request_is_discriminated_by_input_mode() -> None:
    parsed = TypeAdapter(SubmitTaskAttemptRequest).validate_python(
        {"inputMode": "objectSelection", "sceneObjectId": str(uuid4())}
    )

    assert isinstance(parsed, SubmitObjectSelectionAttemptRequest)
