"""Focused behavior tests for the fact-bound A0 M04 and M05 lessons."""

from uuid import uuid4

import pytest
from test_mission_a0 import LABELS, WORDS, _lesson, _objects, _result

from app.ai.features.learning_tasks.mission_a0_situations import (
    validate_a0_situation_lesson,
)
from app.ai.features.learning_tasks.validation import LearningTaskGenerationError
from app.missions import get_mission
from app.repositories.postgres.workflow import _lesson_answer_is_correct
from app.schemas.enums import SessionMode
from app.schemas.tasks import SessionTaskPublic
from app.services import a0_lexicon as lex
from app.services.mission_eligibility import (
    lesson_missions,
    photo_eligibility,
    plan_missions,
    provisional_mission_focus,
)
from app.services.mission_lessons_a0_situations import a0_situation_lesson_task
from app.services.mission_roleplay import assign_roleplay


@pytest.mark.parametrize("language", ["es", "fr", "de", "ko"])
@pytest.mark.parametrize(
    ("mission_id", "gap_order"),
    [
        ("M04", [None, None, "chunkChoice", "chunkChoice", "audioGap", "dialogueGap"]),
        ("M05", [None, None, "chunkChoice", "pictureToBlank", "dialogueGap", "dialogueGap"]),
    ],
)
def test_situation_lessons_follow_specified_question_order_and_option_access(
    mission_id, gap_order, language,
):
    _mission, _spec, payload, result, _objects = _result(mission_id, language)
    validate_a0_situation_lesson(payload, result)
    assert [question.gap_type for question in result.questions] == gap_order
    typed_positions = [2, 3] if mission_id == "M04" else [2]
    assert [index for index, question in enumerate(result.questions) if question.typed_allowed] == (
        typed_positions if language != "ko" else []
    )
    assert all(
        question.correct_option_id in {option.option_id for option in question.options}
        for question in result.questions
    )
    assert sum(question.gap_type is not None for question in result.questions) >= 3
    if language == "ko":
        assert not any(question.typed_allowed for question in result.questions)


@pytest.mark.parametrize("language", ["es", "fr", "de", "ko"])
@pytest.mark.parametrize("reaction", ["like", "dislike"])
def test_situation_translations_are_english_and_keep_blanks_aligned(language, reaction):
    for mission_id in ("M04", "M05"):
        _mission, _spec, _payload, result, _objects = _result(
            mission_id, language, reaction=reaction,
        )
        for question in result.questions:
            translations = [
                (turn["text"], turn["translation"])
                for turn in question.dialogue or []
            ]
            if question.complete_translation:
                translations.append((
                    question.complete_chunk or "", question.complete_translation,
                ))
            prompt_translation = getattr(question, "prompt_translation", None)
            if prompt_translation:
                translations.append((question.prompt, prompt_translation))

            for target_text, translation in translations:
                assert translation
                if target_text not in {"No, ___"}:
                    assert translation != target_text
                assert all(char.isascii() for char in translation if char.isalpha())
                assert "___" not in translation or "___" in target_text


@pytest.mark.parametrize("language", ["es", "fr", "de", "ko"])
def test_m04_prep_contains_the_closed_ownership_chunks(language):
    _mission, _spec, payload, _lesson_result, _objects = _result(
        "M04", language, labels=["cup", "book"], words=WORDS[language][:2],
    )
    texts = {item["text"] for item in payload["prep"]}
    expected = {
        "es": {"Es mía.", "No es mía.", "¿Es tuya?", "La taza es mía.", "La taza es tuya."},
        "fr": {
            "C'est à moi.", "Ce n'est pas à moi.", "C'est à toi ?",
            "La tasse est à moi.", "La tasse est à toi.",
        },
        "de": {
            "Das gehört mir.", "Das gehört mir nicht.", "Gehört das dir?",
            "Die Tasse gehört mir.", "Die Tasse gehört dir.",
        },
        "ko": {
            "제 거예요.", "제 거 아니에요.", "이거 본인 거예요?",
            "컵은 제 거예요.", "컵은 본인 거예요.",
        },
    }
    assert expected[language] <= texts


@pytest.mark.parametrize("language", ["es", "fr", "de", "ko"])
def test_m05_prep_contains_the_closed_preference_chunks(language):
    _mission, _spec, payload, lesson_result, _objects = _result(
        "M05",
        language,
        labels=["apple", "book"],
        words=[WORDS[language][2], WORDS[language][1]],
    )
    texts = {item["text"] for item in payload["prep"]}
    expected = {
        "es": {
            "Me gusta la manzana.", "No me gusta la manzana.",
            "¿Te gusta la manzana?", "¿Qué eliges?",
        },
        "fr": {
            "J'aime la pomme.", "Je n'aime pas la pomme.",
            "Tu aimes la pomme ?", "Tu choisis quoi ?",
        },
        "de": {
            "Ich mag den Apfel.", "Ich mag den Apfel nicht.",
            "Magst du den Apfel?", "Was nimmst du?",
        },
        "ko": {"사과를 좋아해요.", "사과를 안 좋아해요.", "사과를 좋아해요?", "뭐 골라요?"},
    }
    assert expected[language] <= texts
    _mission, _spec, dislike_payload, _dislike_result, _objects = _result(
        "M05",
        language,
        labels=["apple", "book"],
        words=[WORDS[language][2], WORDS[language][1]],
        reaction="dislike",
    )
    choose_other = {
        "es": "Elijo el libro.",
        "fr": "Je choisis le livre.",
        "de": "Ich nehme das Buch.",
        "ko": "책을 골라요.",
    }
    assert choose_other[language] in {item["text"] for item in dislike_payload["prep"]}


@pytest.mark.parametrize("language", ["es", "fr", "de", "ko"])
def test_owned_object_drives_scenario_question_and_mine_sentence(language):
    first = _result("M04", language, labels=["cup", "book"], ownership_index=0)
    second = _result("M04", language, labels=["cup", "book"], ownership_index=1)
    first_result, second_result = first[3], second[3]
    first_question = first_result.questions[0]
    second_question = second_result.questions[0]
    assert first_question.marker_keys is None
    assert second_question.marker_keys is None
    assert first_question.instruction == "Answer yes or no."
    assert first_question.audio_text == first_question.prompt
    assert {
        option.label for option in first_question.options
    } == set(lex.YES_NO[language])
    assert first_question.object_key != second_question.object_key
    assert first_result.questions[3].complete_chunk != second_result.questions[3].complete_chunk
    if language == "es":
        assert "mía" in first_result.questions[3].complete_chunk
        assert "mío" in second_result.questions[3].complete_chunk


@pytest.mark.parametrize("language", ["es", "fr", "de", "ko"])
def test_preference_reaction_changes_answered_chunks(language):
    words = [WORDS[language][2], WORDS[language][1]]
    like = _result(
        "M05", language, labels=["apple", "book"], words=words, reaction="like",
    )[3]
    dislike = _result(
        "M05", language, labels=["apple", "book"], words=words, reaction="dislike",
    )[3]
    def correct_label(question):
        return next(option.label for option in question.options
                    if option.option_id == question.correct_option_id)
    assert correct_label(like.questions[1]) != correct_label(dislike.questions[1])
    assert like.questions[2].complete_chunk != dislike.questions[2].complete_chunk
    assert correct_label(like.questions[4]) != correct_label(dislike.questions[4])
    assert correct_label(like.questions[5]) != correct_label(dislike.questions[5])
    assert ", " in dislike.questions[4].complete_chunk


@pytest.mark.parametrize(
    ("reaction", "scenario_text"),
    [
        ("like", "Let's pretend you like the apple."),
        ("dislike", "Let's pretend you don't like the apple."),
    ],
)
def test_preference_reaction_controls_public_scenario(reaction, scenario_text):
    mission, _spec, payload, result, _objects = _result(
        "M05", "fr", labels=["apple", "book"],
        words=[WORDS["fr"][2], WORDS["fr"][1]], reaction=reaction,
    )
    task = a0_situation_lesson_task(uuid4(), mission, payload, result, {})
    assert {question.roleplay_premise for question in task.public_content.questions} == {
        scenario_text
    }
    assert result.questions[0].prompt == "Which phrase matches the scenario?"


@pytest.mark.parametrize(
    ("language", "ownership_text", "preference_text"),
    [
        ("es", "Es de Ana.", "A Leo le gusta la manzana."),
        ("fr", "C'est à Ana.", "Leo aime la pomme."),
        ("de", "Das gehört Ana.", "Leo mag den Apfel."),
        ("ko", "아나 거예요.", "레오는 사과를 좋아해요."),
    ],
)
def test_named_characters_control_scenarios_and_target_phrases(
    language, ownership_text, preference_text,
):
    ownership = _result(
        "M04", language, labels=["cup", "book"], words=WORDS[language][:2],
        owner_name="Ana",
    )
    ownership_task = a0_situation_lesson_task(
        uuid4(), ownership[0], ownership[2], ownership[3], {},
    )
    assert ownership_text in {item["text"] for item in ownership[2]["prep"]}
    assert ownership_task.public_content.questions[0].roleplay_premise == (
        "Let's pretend the cup is Ana's."
    )
    assert ownership_task.public_content.mission_snapshot.owner_name == "Ana"

    preference = _result(
        "M05", language, labels=["apple", "book"],
        words=[WORDS[language][2], WORDS[language][1]], subject_name="Leo",
    )
    preference_task = a0_situation_lesson_task(
        uuid4(), preference[0], preference[2], preference[3], {},
    )
    assert preference_text in {item["text"] for item in preference[2]["prep"]}
    assert preference_task.public_content.questions[0].roleplay_premise == (
        "Let's pretend Leo likes the apple."
    )
    assert preference_task.public_content.mission_snapshot.subject_name == "Leo"


@pytest.mark.parametrize("mission_id", ["M04", "M05"])
def test_situation_generation_is_deterministic_including_option_order(mission_id):
    mission, spec, payload, _objects = _lesson(mission_id, "fr")
    first = spec.generation.fallback(payload)
    second = spec.generation.fallback(payload)
    assert first.model_dump(mode="json") == second.model_dump(mode="json")


@pytest.mark.parametrize("mission_id", ["M04", "M05"])
def test_a0_situations_are_eligible_without_learner_choices(mission_id):
    mission = get_mission(mission_id, "A0", 1)
    objects = _objects(["cup", "book"])
    assert photo_eligibility(mission, objects).eligible
    assert photo_eligibility(mission, objects, mission_choices={}).eligible


def test_plan_surfaces_preference_but_omits_ownership_for_a0():
    candidates = lesson_missions(
        "lesson", {"proficiency_level": "A0", "target_language_code": "es"},
    )
    objects = _objects(["cup", "book"])
    provisional, _selected = provisional_mission_focus(candidates, objects, [])
    provisional_ids = [mission.mission_id for mission in provisional]
    assert "M04" not in provisional_ids
    assert "M05" in provisional_ids
    candidate_order = {
        (mission.mission_id, str(mission.practice_level), mission.content_version): index
        for index, mission in enumerate(candidates)
    }
    planned_order = [
        candidate_order[
            (mission.mission_id, str(mission.practice_level), mission.content_version)
        ]
        for mission in provisional
    ]
    assert planned_order == sorted(planned_order)

    final = plan_missions(candidates, objects, [])
    final_ids = {mission.mission_id for mission in final}
    assert "M04" not in final_ids
    assert "M05" in final_ids
    assert len(final) <= 3


@pytest.mark.parametrize("mission_id", ["M04", "M05"])
def test_a0_missions_never_get_a1_roleplay_facts(mission_id):
    objects = _objects(LABELS[:3])
    markers = {str(obj.id): index for index, obj in enumerate(objects, 1)}
    assert assign_roleplay(get_mission(mission_id, "A0", 1), uuid4(), objects, markers) == []
    assert len(assign_roleplay(get_mission(mission_id, "A1", 1), uuid4(), objects, markers)) == 3


@pytest.mark.parametrize("mission_id", ["M04", "M05"])
def test_answer_key_and_typed_answers_are_private_and_accepted(mission_id):
    mission, _spec, payload, result, _objects = _result(mission_id, "es")
    task = a0_situation_lesson_task(uuid4(), mission, payload, result, {})
    public = SessionTaskPublic.from_internal(task, mode=SessionMode.LESSON)
    assert "answerKey" not in public.model_dump(mode="json", by_alias=True)
    assert all(question.roleplay_premise for question in task.public_content.questions)
    assert task.public_content.questions[0].marker_object_ids is None
    typed = next(question for question in result.questions if question.typed_allowed)
    accepted = task.answer_key.accepted_text_answers_by_question[typed.question_id]
    assert all(_lesson_answer_is_correct(task, typed.question_id, answer) for answer in accepted)


@pytest.mark.parametrize(
    ("language", "mission_id", "equivalent"),
    [
        ("es", "M04", "Es mia."),
        ("fr", "M04", "C’est à moi."),
        ("de", "M04", "Das gehoert mir."),
        ("fr", "M05", "J’aime la pomme."),
    ],
)
def test_typed_answers_include_language_equivalents(language, mission_id, equivalent):
    options = (
        {"labels": ["apple", "book"], "words": [WORDS[language][2], WORDS[language][1]]}
        if mission_id == "M05"
        else {}
    )
    mission, _spec, payload, result, _objects = _result(
        mission_id, language, **options,
    )
    task = a0_situation_lesson_task(uuid4(), mission, payload, result, {})
    question = next(item for item in result.questions if item.typed_allowed)
    accepted = task.answer_key.accepted_text_answers_by_question[question.question_id]
    assert equivalent in accepted
    assert _lesson_answer_is_correct(task, question.question_id, equivalent)


def test_validator_rejects_missing_or_unknown_learner_facts():
    _mission, _spec, payload, result, _objects = _result("M04", "es")
    missing = {**payload, "learnerFacts": {}}
    with pytest.raises(LearningTaskGenerationError):
        validate_a0_situation_lesson(missing, result)
    wrong_facts = {
        **payload,
        "learnerFacts": {"ownedObjectId": str(uuid4()), "pretend": True},
    }
    with pytest.raises(LearningTaskGenerationError):
        validate_a0_situation_lesson(wrong_facts, result)
