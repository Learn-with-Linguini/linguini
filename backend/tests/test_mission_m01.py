"""M01 A1 eligibility, reviewed colour forms and the deterministic lesson."""

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.ai.features.learning_tasks.mission_m01 import (
    M01LessonResult,
    fallback_m01_lesson,
    validate_m01_lesson,
)
from app.ai.features.learning_tasks.validation import LearningTaskGenerationError
from app.api.learning_errors import register_learning_errors
from app.missions import get_mission
from app.repositories.practice import MissionPhotoNotReadyError
from app.services.mission_eligibility import agreed_colour, lesson_missions, photo_eligibility

MISSION = get_mission("M01", "A1", 1)
CUP = "11111111-1111-1111-1111-111111111111"
BOOK = "22222222-2222-2222-2222-222222222222"


def obj(label, **attributes):
    return SimpleNamespace(label=label, attributes=attributes or None)


def payload(language="fr"):
    return {
        "targetLanguage": language, "missionId": "M01", "practiceLevel": "A1",
        "contentVersion": 1,
        "objects": [
            {"key": CUP, "source": "cup", "nounPhrase": "la tasse"},
            {"key": BOOK, "source": "book", "nounPhrase": "le livre"},
        ],
        "colours": [
            {"key": f"{BOOK}:color", "objectKey": BOOK, "source": "green", "agreedForm": "vert"},
        ],
        "languagePattern": {
            "patternId": "copula-colour", "structure": "[article] [noun] [is] [colour]",
            "copula": "est", "examples": [], "distractorColours": ["verte", "rouge", "bleu"],
        },
    }


@pytest.mark.parametrize(("objects", "reasons"), [
    ([obj("cup", color="red"), obj("book")], ()),
    ([obj("cup", color="red"), obj("Cup ")], ("Confirm at least 2 different objects.",)),
    ([obj("cup"), obj("book", material="paper")], ("Confirm the colour of at least one object.",)),
    ([obj("cup", color="sparkly"), obj("book")], ("Confirm the colour of at least one object.",)),
])
def test_eligibility_uses_only_confirmed_names_and_reviewed_colours(objects, reasons):
    result = photo_eligibility(MISSION, objects)
    assert (result.eligible, result.reasons) == (not reasons, reasons)


def test_colour_forms_agree_only_when_the_gender_is_known():
    assert agreed_colour("red", "es", "feminine") == "roja"
    assert agreed_colour("green", "fr", "feminine") == "verte"
    assert agreed_colour("blue", "es", None) == "azul"
    assert agreed_colour("red", "es", None) is None
    assert agreed_colour("red", "de", "masculine") is None


@pytest.mark.parametrize(("enabled", "mode", "level", "language", "selected"), [
    ("true", "lesson", "A1", "es", True),
    ("true", "lesson", "A1", "fr", True),
    ("false", "lesson", "A1", "es", False),
    ("true", "lesson", "A2", "es", False),
    ("true", "lesson", "A1", "de", False),
    ("true", "ispyGame", "A1", "es", False),
])
def test_mission_path_needs_the_flag_an_a1_profile_and_a_supported_language(
    monkeypatch, enabled, mode, level, language, selected,
):
    monkeypatch.setenv("MISSION_LESSONS_ENABLED", enabled)
    profile = {"proficiency_level": level, "target_language_code": language}
    assert bool(lesson_missions(mode, profile)) is selected


def test_fallback_meets_the_lesson_rules_in_french():
    result = fallback_m01_lesson(payload())
    assert 2 <= len(result.questions) <= 4
    build = result.questions[-1]
    assert build.correct_text == "Le livre est vert."
    assert sorted(build.token_bank) == sorted(["Le", "livre", "est", "vert", "."])


@pytest.mark.parametrize("change", [
    lambda data: data["questions"][-1].update(correct_text="Le livre est rouge."),
    lambda data: data["questions"][0].update(object_key="33333333-3333-3333-3333-333333333333"),
    lambda data: data["questions"].reverse(),
    lambda data: data["questions"][-1].update(token_bank=["Le", "livre", "est"]),
])
def test_validator_rejects_unconfirmed_or_unanswerable_lessons(change):
    data = fallback_m01_lesson(payload()).model_dump()
    change(data)
    with pytest.raises((ValueError, LearningTaskGenerationError)):
        validate_m01_lesson(payload(), M01LessonResult.model_validate(data))


def test_an_unready_photo_reaches_the_client_with_its_reasons():
    app = FastAPI()
    register_learning_errors(app)
    reason = "This photo is not ready for this lesson. Confirm at least 2 different objects."

    @app.post("/review")
    def review():
        raise MissionPhotoNotReadyError(reason)

    response = TestClient(app).post("/review")
    assert response.status_code == 409
    assert response.json()["detail"] == {"code": "mission_photo_not_ready", "message": reason}
