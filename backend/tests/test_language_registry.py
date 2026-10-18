import re

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.languages import get_language, languages, learnable_languages
from app.main import app
from app.schemas.languages import Language, derive_direction


def test_registry_entries_have_unique_canonical_codes_and_iso_scripts():
    entries = languages()
    codes = [language.code for language in entries]

    assert len(codes) == len(set(codes))
    for language in entries:
        subtags = language.code.split("-")
        assert subtags[0] == subtags[0].lower()
        assert re.fullmatch(r"[A-Z][a-z]{3}", language.script)
        assert language.direction == derive_direction(language.script)


def test_direction_is_derived_for_right_to_left_scripts():
    assert derive_direction("Arab") == "rtl"


def test_registry_helpers_and_picker_availability():
    assert {language.code for language in learnable_languages()} == {"es", "fr", "de", "ko"}
    assert {
        language.code: language.flag
        for language in learnable_languages()
    } == {
        "es": "🇪🇸",
        "fr": "🇫🇷",
        "de": "🇩🇪",
        "ko": "🇰🇷",
    }
    english = get_language("en")
    assert not english.learnable
    assert english.instruction
    assert get_language("ES").code == "es"
    assert get_language("KO").code == "ko"


def test_mission_levels_are_derived_from_implemented_legacy_eligibility():
    expected = {
        "es": ["A0", "A1", "A2"],
        "de": ["A0", "A1", "A2"],
        "ko": ["A0", "A2"],
    }
    for code, levels in expected.items():
        assert get_language(code).features.mission_levels == levels


def test_optional_grammar_metadata_is_not_required():
    language = Language.model_validate({
        "code": "en",
        "englishName": "English",
        "nativeName": "English",
        "script": "Latn",
        "learnable": False,
        "instruction": True,
        "speech": {"synthesisLocale": "en-US"},
    })

    assert language.grammar is None


def test_language_codes_require_canonical_bcp47_casing():
    language = Language.model_validate({
        "code": "qaa",
        "englishName": "Test language",
        "nativeName": "Test language",
        "script": "Latn",
        "learnable": False,
        "instruction": False,
        "speech": {"synthesisLocale": "qaa"},
    })
    assert language.code == "qaa"

    with pytest.raises(ValidationError, match="canonical BCP 47 casing"):
        Language.model_validate({
            "code": "qaa-latn",
            "englishName": "Test language",
            "nativeName": "Test language",
            "script": "Latn",
            "learnable": False,
            "instruction": False,
            "speech": {"synthesisLocale": "qaa"},
        })


def test_public_language_endpoint_is_unauthenticated_camel_case_and_tagged():
    client = TestClient(app)
    response = client.get("/api/v1/languages")

    assert response.status_code == 200
    body = response.json()
    assert [item["code"] for item in body["items"]] == ["es", "fr", "de", "ko", "en"]
    korean = next(item for item in body["items"] if item["code"] == "ko")
    assert korean["nativeName"] == "한국어"
    assert korean["speech"] == {
        "synthesisLocale": "ko-KR",
        "synthesis": "browserVoice",
        "recognition": False,
    }
    assert korean["features"] == {"missionLevels": ["A0", "A2"]}
    openapi = client.get("/openapi.json").json()
    assert openapi["paths"]["/api/v1/languages"]["get"]["tags"] == ["languages"]
