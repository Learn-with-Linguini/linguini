from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.languages import get_language
from app.missions import get_mission
from app.missions.m01_multilingual import (
    CONTRACT_VERSION,
    M01_VARIANTS,
    MissionContractError,
    UnroutedMissionVariant,
    default_join,
    fact_id,
    generation_enabled,
    join_chunks,
    m01_variant,
    validate_contract_input,
    validate_contract_output,
)
from app.schemas.mission_m01_contract import (
    ApprovedTerm,
    ConfirmedAttribute,
    ConfirmedCount,
    ConfirmedObject,
    ConfirmedRelation,
    ConfirmedSceneFacts,
    ContractQuestion,
    Feedback,
    Hint,
    LearnerContext,
    M01ContractInput,
    M01ContractOutput,
    MissionRef,
    PreparationCard,
    PrivateEvaluation,
    SentenceChunk,
    WorkedExample,
)
from app.schemas.tasks import QuestionEvaluation, VocabularyChoice
from app.services.mission_eligibility import IMPLEMENTED_MISSIONS
from app.services.mission_registry import (
    A0_MISSION_LESSONS,
    A2_MISSION_LESSONS,
    MISSION_LESSONS,
    lesson_spec,
)

LANGUAGES = ("hi", "ta", "zh-Hans", "es")
LEVELS = ("A0", "A1", "A2")


def contract_input(level="A1", language="es"):
    first_id, second_id, third_id = uuid4(), uuid4(), uuid4()
    first_fact = fact_id("object", first_id)
    second_fact = fact_id("object", second_id)
    third_fact = fact_id("object", third_id)
    attribute_fact = fact_id("attribute", first_id, "colour")
    second_attribute_fact = fact_id("attribute", second_id, "size")
    relation_fact = fact_id("relation", first_fact, "on", second_fact)
    count_fact = fact_id("count", "cup")
    linguistic = {"gender": "feminine"} if language == "es" else {}
    if language == "zh-Hans":
        linguistic = {"classifier": "个"}
    facts = ConfirmedSceneFacts(
        objects=[
            ConfirmedObject(fact_id=first_fact, scene_object_id=first_id, label="cup", marker=1),
            ConfirmedObject(
                fact_id=second_fact, scene_object_id=second_id, label="table", marker=2
            ),
            ConfirmedObject(
                fact_id=third_fact, scene_object_id=third_id, label="chair", marker=3
            ),
        ],
        attributes=[
            ConfirmedAttribute(
                fact_id=attribute_fact, object_fact_id=first_fact, kind="colour", value="blue"
            ),
            ConfirmedAttribute(
                fact_id=second_attribute_fact, object_fact_id=second_fact,
                kind="size", value="large",
            ),
        ],
        relations=[
            ConfirmedRelation(
                fact_id=relation_fact, subject_fact_id=first_fact,
                reference_fact_id=second_fact, relation="on",
            )
        ],
        counted_groups=[
            ConfirmedCount(
                fact_id=count_fact, object_fact_ids=[first_fact, third_fact], quantity=2
            )
        ],
    )
    return M01ContractInput(
        contract_version=CONTRACT_VERSION,
        mission=MissionRef(mission_id="M01", practice_level=level, content_version=1),
        target_language=language,
        instruction_language="en",
        scene_facts=facts,
        vocabulary=[
            ApprovedTerm(
                term_id="cup",
                fact_id=first_fact,
                source_text="cup",
                target_text={"hi": "कप", "ta": "கோப்பை", "zh-Hans": "杯子", "es": "taza"}[
                    language
                ],
                part_of_speech="noun",
                provenance="reviewedLexicon",
                linguistic=linguistic,
            )
        ],
        learner=LearnerContext(proficiency_level=level),
    )


def example_chunks(language, prefix):
    words = {
        "zh-Hans": ["桌子", "上", "有", "一个", "杯子", "。"],
        "hi": ["यह", "एक", "कप", "है", "।"],
        "ta": ["இது", "ஒரு", "கோப்பை", "."],
        "es": ["La", "taza", "está", "sobre", "la", "mesa", "."],
    }[language]
    entry = get_language(language)
    return [
        SentenceChunk(
            chunk_id=f"{prefix}-{index}",
            text=word,
            join=default_join(entry, word),
        )
        for index, word in enumerate(words)
    ]


def contract_output(contract):
    definition = get_mission(
        contract.mission.mission_id,
        contract.mission.practice_level,
        contract.mission.content_version,
    )
    targets = list(definition.objective.targets)
    required_targets = [
        group[0] for group in definition.expected_performance.required_target_groups
    ]
    chosen_targets = required_targets[:]
    while len(chosen_targets) < definition.expected_performance.min_assessed_questions:
        chosen_targets.append(targets[len(chosen_targets) % len(targets)].target_id)
    object_fact = contract.scene_facts.objects[0].fact_id
    question_list = []
    answers = {}
    evaluations = []

    for index in range(definition.expected_performance.min_assessed_questions):
        question_id = f"question-{index}"
        interaction = ("multipleChoice", "markerChoice", "sentenceBuilding")[index % 3]
        options = [
            VocabularyChoice(option_id=f"option-{index}-a", label="cup"),
            VocabularyChoice(option_id=f"option-{index}-b", label="table"),
        ]
        chunks = example_chunks(contract.target_language, f"question-{index}")
        selected_target = chosen_targets[index]
        target = definition.targets[selected_target]
        question = ContractQuestion(
            question_id=question_id,
            target_ids=[selected_target],
            prompt="Choose the confirmed object.",
            interaction=interaction,
            options=[] if interaction == "sentenceBuilding" else options,
            marker_fact_ids=(
                {
                    options[0].option_id: object_fact,
                    options[1].option_id: contract.scene_facts.objects[1].fact_id,
                }
                if interaction == "markerChoice"
                else None
            ),
            chunks=chunks if interaction == "sentenceBuilding" else [],
            fact_ids=[object_fact],
            hints=[],
            feedback=Feedback(correct="Nice work.", corrections=[]),
        )
        question_list.append(question)
        answers[question_id] = (
            {
                "correct_option_id": None,
                "chunk_ids": [chunk.chunk_id for chunk in chunks],
            }
            if interaction == "sentenceBuilding"
            else {
                "correct_option_id": options[0].option_id,
                "chunk_ids": [],
            }
        )
        evaluations.append(
            QuestionEvaluation(
                question_id=question_id,
                objective_id=definition.objective.objective_id,
                target_ids=[selected_target],
                evidence_type=target.evidence_types[0],
            )
        )

    chunks = example_chunks(contract.target_language, "example")
    return M01ContractOutput(
        contract_version=CONTRACT_VERSION,
        mission=contract.mission,
        target_language=contract.target_language,
        instruction_language=contract.instruction_language,
        objective_id=definition.objective.objective_id,
        title=definition.title,
        preparation=[
            PreparationCard(
                card_id="introduce-cup",
                text=contract.vocabulary[0].target_text,
                translation="cup",
                fact_ids=[object_fact],
            )
        ],
        worked_examples=[
            WorkedExample(
                example_id="example-one",
                chunks=chunks,
                translation="A cup is on the table.",
                fact_ids=[object_fact, contract.scene_facts.objects[1].fact_id],
            )
        ],
        questions=question_list,
        private=PrivateEvaluation(answers=answers, evaluations=evaluations),
    )


@pytest.mark.parametrize("level", LEVELS)
@pytest.mark.parametrize("language", LANGUAGES)
def test_valid_contracts_cover_all_levels_and_registered_languages(level, language):
    contract = contract_input(level, language)
    output = contract_output(contract)

    assert validate_contract_input(contract).practice_level == level
    validate_contract_output(contract, output)


@pytest.mark.parametrize(
    ("language", "expected"),
    [
        ("zh-Hans", "桌子上有一个杯子。"),
        ("hi", "यह एक कप है।"),
        ("ta", "இது ஒரு கோப்பை."),
    ],
)
def test_language_specific_chunk_joining(language, expected):
    assert join_chunks(example_chunks(language, "joined")) == expected


def test_spanish_vocabulary_accepts_gender_metadata_without_requiring_it_elsewhere():
    spanish = contract_input(language="es")
    hindi = contract_input(language="hi")
    chinese = contract_input(language="zh-Hans")

    assert spanish.vocabulary[0].linguistic == {"gender": "feminine"}
    assert hindi.vocabulary[0].linguistic == {}
    assert chinese.vocabulary[0].linguistic == {"classifier": "个"}


def test_contract_input_rejects_vocabulary_for_an_unconfirmed_fact():
    data = contract_input().model_dump(by_alias=False)
    data["vocabulary"][0]["fact_id"] = "object:unconfirmed"

    with pytest.raises(ValidationError, match="unknown scene facts"):
        M01ContractInput.model_validate(data)


def test_contract_input_requires_unique_fact_ids_and_matching_learner_level():
    data = contract_input().model_dump(by_alias=False)
    data["scene_facts"]["objects"][1]["fact_id"] = data["scene_facts"]["objects"][0]["fact_id"]
    with pytest.raises(ValidationError, match="scene fact IDs must be unique"):
        M01ContractInput.model_validate(data)

    data = contract_input().model_dump(by_alias=False)
    data["learner"]["proficiency_level"] = "A0"
    with pytest.raises(ValidationError, match="must match mission practice level"):
        M01ContractInput.model_validate(data)


@pytest.mark.parametrize(
    ("target_language", "instruction_language", "message"),
    [
        ("xx", "en", "unregistered target"),
        ("es", "es", "must differ"),
        ("es", "fr", "not enabled for instruction"),
    ],
)
def test_contract_input_checks_registry_language_roles(
    target_language, instruction_language, message
):
    contract = contract_input()
    contract = contract.model_copy(
        update={"target_language": target_language, "instruction_language": instruction_language}
    )

    with pytest.raises(MissionContractError, match=message):
        validate_contract_input(contract)


def test_contract_input_rejects_unresolvable_mission_definition():
    contract = contract_input()
    contract = contract.model_copy(
        update={
            "mission": MissionRef(
                mission_id="M01", practice_level="A1", content_version=99
            )
        }
    )

    with pytest.raises(UnroutedMissionVariant):
        validate_contract_input(contract)


def test_output_rejects_fact_ids_outside_confirmed_input():
    contract = contract_input()
    output = contract_output(contract)
    first = output.questions[0].model_copy(update={"fact_ids": ["object:unknown"]})
    bad_output = output.model_copy(update={"questions": [first, *output.questions[1:]]})

    with pytest.raises(MissionContractError, match="unknown scene facts"):
        validate_contract_output(contract, bad_output)


def test_output_rejects_unknown_marker_and_prep_fact_ids():
    contract = contract_input()
    output = contract_output(contract)
    marker_question = next(
        question for question in output.questions if question.interaction == "markerChoice"
    )
    marker_facts = dict(marker_question.marker_fact_ids)
    marker_facts[next(iter(marker_facts))] = "object:unknown"
    changed_marker = marker_question.model_copy(update={"marker_fact_ids": marker_facts})
    bad_markers = output.model_copy(
        update={
            "questions": [
                changed_marker if question.question_id == marker_question.question_id else question
                for question in output.questions
            ]
        }
    )
    with pytest.raises(MissionContractError, match="unknown scene facts"):
        validate_contract_output(contract, bad_markers)

    prep_card = output.preparation[0].model_copy(update={"fact_ids": ["object:unknown"]})
    bad_preparation = output.model_copy(update={"preparation": [prep_card]})
    with pytest.raises(MissionContractError, match="preparation card"):
        validate_contract_output(contract, bad_preparation)


def test_output_rejects_targets_from_another_level():
    contract = contract_input(level="A0")
    output = contract_output(contract)
    first = output.questions[0].model_copy(update={"target_ids": ["name-object"]})
    bad_output = output.model_copy(update={"questions": [first, *output.questions[1:]]})

    with pytest.raises(MissionContractError, match="do not belong"):
        validate_contract_output(contract, bad_output)


def test_output_checks_mission_language_and_question_count():
    contract = contract_input()
    output = contract_output(contract)
    wrong_language = output.model_copy(update={"target_language": "fr"})
    with pytest.raises(MissionContractError, match="must match the input"):
        validate_contract_output(contract, wrong_language)

    too_few_questions = output.model_copy(update={"questions": output.questions[:-1]})
    with pytest.raises(MissionContractError, match="fewer than the required"):
        validate_contract_output(contract, too_few_questions)


def test_output_requires_each_required_target_group():
    contract = contract_input(level="A2")
    output = contract_output(contract)
    questions = [
        question.model_copy(update={"target_ids": ["identify-scene-object"]})
        for question in output.questions
    ]
    bad_output = output.model_copy(update={"questions": questions})

    with pytest.raises(MissionContractError, match="required target group"):
        validate_contract_output(contract, bad_output)


def test_output_requires_ordered_hints_and_only_last_hint_may_reveal():
    contract = contract_input()
    output = contract_output(contract)
    first_question = output.questions[0].model_copy(
        update={
            "hints": [
                Hint(level=2, text="Second hint."),
                Hint(level=1, text="First hint."),
            ]
        }
    )
    bad_order = output.model_copy(update={"questions": [first_question, *output.questions[1:]]})
    with pytest.raises(MissionContractError, match="strictly ascending"):
        validate_contract_output(contract, bad_order)

    revealing_question = output.questions[0].model_copy(
        update={
            "hints": [
                Hint(level=1, text="Answer hint.", reveals_answer=True),
                Hint(level=2, text="Final hint."),
            ]
        }
    )
    early_reveal = output.model_copy(
        update={"questions": [revealing_question, *output.questions[1:]]}
    )
    with pytest.raises(MissionContractError, match="final hint"):
        validate_contract_output(contract, early_reveal)


def test_output_requires_one_offered_answer_for_each_question():
    contract = contract_input()
    output = contract_output(contract)
    first = output.questions[0]
    answers = dict(output.private.answers)
    answers[first.question_id] = answers[first.question_id].model_copy(
        update={"correct_option_id": "not-offered"}
    )
    wrong_answer = output.model_copy(
        update={"private": output.private.model_copy(update={"answers": answers})}
    )
    with pytest.raises(MissionContractError, match="one of the offered options"):
        validate_contract_output(contract, wrong_answer)

    del answers[first.question_id]
    missing_answer = output.model_copy(
        update={"private": output.private.model_copy(update={"answers": answers})}
    )
    with pytest.raises(MissionContractError, match="exactly one private answer"):
        validate_contract_output(contract, missing_answer)


def test_output_checks_evaluation_evidence_against_target_definition():
    contract = contract_input()
    output = contract_output(contract)
    evaluation = output.private.evaluations[0].model_copy(
        update={"evidence_type": "participation"}
    )
    private = output.private.model_copy(
        update={"evaluations": [evaluation, *output.private.evaluations[1:]]}
    )
    bad_output = output.model_copy(update={"private": private})

    with pytest.raises(MissionContractError, match="do not accept"):
        validate_contract_output(contract, bad_output)


def test_sentence_answer_chunks_must_be_unique_and_offered():
    contract = contract_input()
    output = contract_output(contract)
    question = next(
        question for question in output.questions if question.interaction == "sentenceBuilding"
    )
    answer = output.private.answers[question.question_id]
    answers = dict(output.private.answers)
    answers[question.question_id] = answer.model_copy(
        update={"chunk_ids": [answer.chunk_ids[0], answer.chunk_ids[0]]}
    )
    bad_output = output.model_copy(
        update={"private": output.private.model_copy(update={"answers": answers})}
    )

    with pytest.raises(MissionContractError, match="cannot repeat"):
        validate_contract_output(contract, bad_output)

    answers[question.question_id] = answer.model_copy(update={"chunk_ids": ["not-offered"]})
    out_of_bank = output.model_copy(
        update={"private": output.private.model_copy(update={"answers": answers})}
    )
    with pytest.raises(MissionContractError, match="must use offered question chunks"):
        validate_contract_output(contract, out_of_bank)


def test_chunk_ids_must_be_unique_and_marker_options_must_match():
    contract = contract_input()
    output = contract_output(contract)
    sentence_question = next(
        question for question in output.questions if question.interaction == "sentenceBuilding"
    )
    chunks = list(sentence_question.chunks)
    chunks[1] = chunks[1].model_copy(update={"chunk_id": chunks[0].chunk_id})
    changed_chunks = sentence_question.model_copy(update={"chunks": chunks})
    duplicate_ids = output.model_copy(
        update={
            "questions": [
                changed_chunks
                if question.question_id == sentence_question.question_id
                else question
                for question in output.questions
            ]
        }
    )
    with pytest.raises(MissionContractError, match="chunk IDs must be unique"):
        validate_contract_output(contract, duplicate_ids)

    marker_question = next(
        question for question in output.questions if question.interaction == "markerChoice"
    )
    changed_markers = marker_question.model_copy(update={"marker_fact_ids": {}})
    mismatched_markers = output.model_copy(
        update={
            "questions": [
                changed_markers if question.question_id == marker_question.question_id else question
                for question in output.questions
            ]
        }
    )
    with pytest.raises(MissionContractError, match="cover exactly"):
        validate_contract_output(contract, mismatched_markers)


def test_public_dump_excludes_private_evaluation():
    output = contract_output(contract_input())

    assert "private" not in output.public_dump()
    assert output.public_dump()["contractVersion"] == CONTRACT_VERSION


def test_explicit_routes_are_disabled_and_legacy_registry_never_falls_back():
    assert set(M01_VARIANTS) == {("M01", "A0", 1), ("M01", "A1", 1), ("M01", "A2", 1)}
    for level in LEVELS:
        assert m01_variant("M01", level, 1).practice_level == level
    for key in (("M01", "B1", 1), ("M01", "A1", 99), ("M02", "A1", 1)):
        with pytest.raises(UnroutedMissionVariant):
            m01_variant(*key)
    assert generation_enabled() is False

    for level, variants in IMPLEMENTED_MISSIONS.items():
        for variant in variants:
            mission = get_mission(*variant)
            spec = lesson_spec(mission)
            key = f"{level}:{mission.mission_id}"
            expected = (
                A0_MISSION_LESSONS.get(key)
                if level == "A0"
                else A2_MISSION_LESSONS.get(key)
                if level == "A2"
                else MISSION_LESSONS.get(mission.mission_id)
            )
            assert spec is expected

    with pytest.raises(UnroutedMissionVariant):
        lesson_spec(SimpleNamespace(mission_id="M04", practice_level="A0"))


def test_fact_id_helpers_are_stable():
    object_uuid = uuid4()
    assert fact_id("object", object_uuid) == f"object:{object_uuid}"
    assert fact_id("attribute", object_uuid, "colour") == f"attribute:{object_uuid}:colour"
    assert fact_id("relation", "object:a", "on", "object:b") == (
        "relation:object:a:on:object:b"
    )
    assert fact_id("count", "cup") == "count:cup"
