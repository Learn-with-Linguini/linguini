from pathlib import Path
from textwrap import dedent

import pytest
from fastapi.testclient import TestClient

from app.learning_resources import (
    CHARACTER_REFERENCES_DIR,
    CHEAT_SHEETS_DIR,
    LearningResourceConfigurationError,
    load_character_references,
    load_cheat_sheets,
)
from app.main import app

CHARACTER_REFERENCE = """
reference_id = "ko-hangul"
language_code = "ko"
content_version = 1
script_name = "Hangul"
title = "Hangul character guide"
introduction = "See how letters combine into syllable blocks."

[[sections]]
section_id = "syllable-blocks"
title = "Build a syllable block"
explanation = "Letters are arranged together rather than written in a line."

[[sections.characters]]
character = "ㄱ"
name = "giyeok"
pronunciation = "g or k"
example = "가"
example_translation = "ga"
"""

CHEAT_SHEET = """
mission_id = "M01"
practice_level = "A1"
content_version = 1
language_code = "ko"
title = "Name and describe an object"
summary = "Keep the useful pattern beside you while you practise."
character_reference_id = "ko-hangul"
character_reference_version = 1

[[concepts]]
concept_id = "name-object"
title = "Name the object"
explanation = "Use the reviewed Korean name for the object."
formula = "[noun]"
character_reference_section_ids = ["syllable-blocks"]

[[concepts.examples]]
target_text = "책"
translation = "book"
"""


def write_resource(directory: Path, relative_path: str, content: str) -> None:
    path = directory / relative_path
    path.parent.mkdir(parents=True)
    path.write_text(dedent(content), encoding="utf-8")


def test_loads_cheatsheet_linked_to_mission_and_character_reference(tmp_path: Path) -> None:
    references_dir = tmp_path / "character-references"
    cheatsheets_dir = tmp_path / "cheatsheets"
    write_resource(references_dir, "ko/ko-hangul.toml", CHARACTER_REFERENCE)
    write_resource(cheatsheets_dir, "ko/M01-A1.toml", CHEAT_SHEET)

    references = load_character_references(references_dir)
    cheat_sheets = load_cheat_sheets(cheatsheets_dir, references)

    assert references[("ko-hangul", 1)].sections[0].section_id == "syllable-blocks"
    sheet = cheat_sheets[("M01", "A1", 1, "ko")]
    assert sheet.concepts[0].concept_id == "name-object"


def test_all_committed_learning_resources_are_valid() -> None:
    references = load_character_references(CHARACTER_REFERENCES_DIR)

    cheat_sheets = load_cheat_sheets(CHEAT_SHEETS_DIR, references)

    french_m01 = cheat_sheets[("M01", "A0", 1, "fr")]
    article = french_m01.concepts[1].pattern_parts[1]
    assert [(choice.text, choice.label) for choice in article.choices] == [
        ("un", "masculine"),
        ("une", "feminine"),
    ]

    french_structure = [
        (
            concept.concept_id,
            concept.explanation is not None,
            len(concept.pattern_parts),
        )
        for concept in french_m01.concepts
    ]
    for language_code in ("es", "de"):
        sheet = cheat_sheets[("M01", "A0", 1, language_code)]
        assert sheet.summary is french_m01.summary is None
        assert [
            (
                concept.concept_id,
                concept.explanation is not None,
                len(concept.pattern_parts),
            )
            for concept in sheet.concepts
        ] == french_structure


def test_rejects_a_concept_not_in_the_mission_definition(tmp_path: Path) -> None:
    references_dir = tmp_path / "character-references"
    cheatsheets_dir = tmp_path / "cheatsheets"
    write_resource(references_dir, "ko/ko-hangul.toml", CHARACTER_REFERENCE)
    write_resource(
        cheatsheets_dir,
        "ko/M01-A1.toml",
        CHEAT_SHEET.replace('concept_id = "name-object"', 'concept_id = "invented-rule"'),
    )

    with pytest.raises(
        LearningResourceConfigurationError,
        match="unknown mission concepts: invented-rule",
    ):
        load_cheat_sheets(cheatsheets_dir, load_character_references(references_dir))


def test_rejects_an_unknown_character_reference_section(tmp_path: Path) -> None:
    references_dir = tmp_path / "character-references"
    cheatsheets_dir = tmp_path / "cheatsheets"
    write_resource(references_dir, "ko/ko-hangul.toml", CHARACTER_REFERENCE)
    write_resource(
        cheatsheets_dir,
        "ko/M01-A1.toml",
        CHEAT_SHEET.replace("syllable-blocks", "missing-section", 1),
    )

    with pytest.raises(
        LearningResourceConfigurationError,
        match="unknown character sections: missing-section",
    ):
        load_cheat_sheets(cheatsheets_dir, load_character_references(references_dir))


def test_learning_resource_routes_are_exposed() -> None:
    paths = app.openapi()["paths"]

    assert "/api/v1/learning-resources/cheatsheets" in paths
    assert "/api/v1/learning-resources/cheatsheets/{mission_id}" in paths
    assert "/api/v1/learning-resources/character-references" in paths
    assert "/api/v1/learning-resources/character-references/{reference_id}" in paths


def test_french_a0_m01_cheatsheet_is_served_to_the_ui() -> None:
    response = TestClient(app).get(
        "/api/v1/learning-resources/cheatsheets/M01",
        params={"languageCode": "fr", "practiceLevel": "A0"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["textDirection"] == "ltr"
    assert body["concepts"][1]["formula"] == "C'est + un/une + object."
    assert body["concepts"][1]["patternParts"][1]["choices"] == [
        {"text": "un", "label": "masculine"},
        {"text": "une", "label": "feminine"},
    ]


@pytest.mark.parametrize(
    ("language", "formula"),
    [
        ("es", "Es + un/una + object."),
        ("de", "Das ist + ein/eine + object."),
        ("ko", "이것은 + object + 이에요/예요."),
    ],
)
def test_other_a0_m01_cheatsheets_are_served_to_the_ui(
    language: str, formula: str
) -> None:
    response = TestClient(app).get(
        "/api/v1/learning-resources/cheatsheets/M01",
        params={"languageCode": language, "practiceLevel": "A0"},
    )

    assert response.status_code == 200
    assert response.json()["concepts"][1]["formula"] == formula


def test_french_a0_m02_description_cheatsheet_is_served_to_the_ui() -> None:
    response = TestClient(app).get(
        "/api/v1/learning-resources/cheatsheets/M02",
        params={
            "languageCode": "fr",
            "practiceLevel": "A0",
            "contentVersion": 2,
        },
    )

    assert response.status_code == 200
    assert response.json()["title"] == "Adjectives can be before or after the object"
    assert [concept["conceptId"] for concept in response.json()["concepts"]] == [
        "recognise-adjective",
        "recognise-adjective",
        "recognise-preposition",
    ]
    assert [concept["title"] for concept in response.json()["concepts"][:2]] == [
        "After the object",
        "Before the object",
    ]


@pytest.mark.parametrize(
    ("language", "title", "adjective_example", "location_example"),
    [
        (
            "es",
            "Adjectives usually come after the object",
            "la taza roja",
            "La taza está sobre la mesa.",
        ),
        (
            "de",
            "Adjectives come before the object",
            "die rote Tasse",
            "Die Tasse ist auf dem Tisch.",
        ),
        ("ko", "Descriptors come before the object", "빨간 컵", "컵이 책상 위에 있어요."),
    ],
)
def test_other_a0_m02_cheatsheets_are_served_to_the_ui(
    language: str, title: str, adjective_example: str, location_example: str
) -> None:
    response = TestClient(app).get(
        "/api/v1/learning-resources/cheatsheets/M02",
        params={
            "languageCode": language,
            "practiceLevel": "A0",
            "contentVersion": 2,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["title"] == title
    assert [concept["conceptId"] for concept in body["concepts"]] == [
        "recognise-adjective",
        "recognise-preposition",
    ]
    assert body["concepts"][0]["examples"][0]["targetText"] == adjective_example
    assert body["concepts"][1]["examples"][0]["targetText"] == location_example
    if language == "ko":
        assert [
            example["targetText"] for example in body["concepts"][1]["examples"]
        ] == ["컵이 책상 위에 있어요.", "컵이 책상 아래에 있어요."]


@pytest.mark.parametrize(
    ("language", "two", "chunk"),
    [
        ("fr", "deux", "deux tasses"),
        ("es", "dos", "dos tazas"),
        ("de", "zwei", "zwei Tassen"),
        ("ko", "두 개", "컵 두 개"),
    ],
)
def test_a0_m03_cheatsheets_include_numbers_and_counted_objects(
    language: str, two: str, chunk: str
) -> None:
    response = TestClient(app).get(
        "/api/v1/learning-resources/cheatsheets/M03",
        params={"languageCode": language, "practiceLevel": "A0"},
    )

    assert response.status_code == 200
    concepts = response.json()["concepts"]
    assert [concept["conceptId"] for concept in concepts] == [
        "count-small-group",
        "number-noun-chunk",
    ]
    assert len(concepts[0]["referenceItems"]) == 10
    assert concepts[0]["referenceItems"][1]["targetText"] == two
    assert concepts[1]["examples"][1]["targetText"] == chunk


def test_french_a0_m05_cheatsheet_separates_like_and_dislike() -> None:
    response = TestClient(app).get(
        "/api/v1/learning-resources/cheatsheets/M05",
        params={"languageCode": "fr", "practiceLevel": "A0"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "Say what you like and don't like"
    assert [concept["title"] for concept in body["concepts"]] == [
        "I like",
        "I don't like",
    ]
    assert [concept["patternParts"][0]["text"] for concept in body["concepts"]] == [
        "J'aime",
        "Je n'aime pas",
    ]
    assert body["concepts"][1]["examples"][1]["targetText"] == (
        "Leo n'aime pas le livre."
    )


def test_missing_learning_resources_return_clear_404s() -> None:
    client = TestClient(app)

    cheat_sheet = client.get(
        "/api/v1/learning-resources/cheatsheets/M99",
        params={"languageCode": "ko", "practiceLevel": "A1"},
    )
    character_reference = client.get(
        "/api/v1/learning-resources/character-references/missing-reference"
    )

    assert cheat_sheet.status_code == 404
    assert cheat_sheet.json()["detail"]["code"] == "cheatsheet_not_found"
    assert character_reference.status_code == 404
    assert character_reference.json()["detail"]["code"] == "character_reference_not_found"
