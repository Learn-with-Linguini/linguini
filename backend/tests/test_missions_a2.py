"""Approved-fact contracts and deterministic A2 mission registrations."""

from types import SimpleNamespace
from uuid import UUID

from app.ai.features.learning_tasks.mission import tokens
from app.services.mission_eligibility import lesson_missions

FACT_KEYS = {
    "approvedObjects",
    "approvedAttributes",
    "approvedRelationships",
    "approvedCountedGroups",
    "approvedRoleplayFacts",
    "approvedVocabulary",
    "approvedSentencePatterns",
    "approvedConnectors",
    "approvedComparatives",
}


def _scene(language="es"):
    labels = ("cup", "table", "book")
    nouns = {
        "es": (("taza", "la", "tazas"), ("mesa", "la", "mesas"), ("libro", "el", "libros")),
        "fr": (("tasse", "la", "tasses"), ("table", "la", "tables"), ("livre", "le", "livres")),
    }[language]
    objects, words, terms = [], [], []
    for index, (label, (noun, article, plural)) in enumerate(zip(labels, nouns, strict=True), 1):
        object_id = UUID(int=index)
        objects.append(
            SimpleNamespace(
                id=object_id,
                label=label,
                attributes=(
                    {"color": "red"}
                    if index in {1, 2}
                    else ({"size": "big"} if index == 3 else {})
                ),
            )
        )
        words.append(
            SimpleNamespace(
                id=UUID(int=index + 10),
                display_text=f"{article} {noun}",
                gender=article,
                plural_form=plural,
            )
        )
        terms.append(
            SimpleNamespace(
                key=str(object_id),
                translation=noun,
                article=article,
                gender={"la": "feminine", "le": "masculine", "el": "masculine"}[article],
            )
        )
    relations = [
        SimpleNamespace(
            id=UUID(int=30),
            subject_scene_object_id=objects[0].id,
            reference_scene_object_id=objects[1].id,
            relation="on",
        )
    ]
    groups = [
        {"label": "cup", "quantity": 2, "sceneObjectIds": [str(objects[0].id)]},
        {"label": "book", "quantity": 3, "sceneObjectIds": [str(objects[2].id)]},
    ]
    translated = SimpleNamespace(objects=terms)
    markers = {str(obj.id): index for index, obj in enumerate(objects, 1)}
    return objects, words, relations, groups, translated, markers




def test_every_pack_language_gets_the_a2_missions():
    for language in ("es", "fr", "de", "ko"):
        assert [
            mission.practice_level
            for mission in lesson_missions(
                "lesson", {"proficiency_level": "A2", "target_language_code": language}
            )
        ] == ["A2"] * 5
        assert [mission.mission_id for mission in lesson_missions(
            "lesson", {"proficiency_level": "A2", "target_language_code": language}
        )] == ["M01", "M02", "M03", "M04", "M06"]


def test_a2_missions_leave_the_a1_and_a0_plans_unchanged():
    a1 = lesson_missions(
        "lesson",
        {
            "proficiency_level": "A1",
            "target_language_code": "es",
            "onboarding_completed": True,
            "placement_completed": True,
        },
    )
    assert [(mission.mission_id, mission.practice_level) for mission in a1] == [
        ("M01", "A1"), ("M02", "A1"), ("M03", "A1"),
        ("M04", "A1"), ("M05", "A1"),
    ]
    a0 = lesson_missions(
        "lesson", {"proficiency_level": "A0", "target_language_code": "es"}
    )
    assert [(mission.mission_id, mission.practice_level) for mission in a0] == [
        ("M01", "A0"), ("M02", "A0"), ("M03", "A0"),
        ("M04", "A0"), ("M05", "A0"), ("M13", "A0"),
    ]
























def _replace_question(result, index, **updates):
    questions = list(result.questions)
    questions[index] = questions[index].model_copy(update=updates)
    return result.model_copy(update={"questions": questions})


def _replace_sentence(result, index, text):
    chunks = tokens(text)
    return _replace_question(
        result, index, correct_text=text, answer_chunks=chunks, token_bank=chunks,
        distractor_chunks=[],
    )




























