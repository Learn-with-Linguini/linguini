import json
from dataclasses import replace
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.ai.cache.cache import CacheRequest, FeatureVersion, ResultCache
from app.ai.cache.references import ReferenceMap
from app.ai.cache.store import CacheScope
from app.languages import get_language
from app.missions import get_mission
from app.missions.m01_multilingual import (
    CONTRACT_VERSION,
    M01_VARIANTS,
    MissionContractError,
    UnroutedMissionVariant,
    convert_generated_lesson,
    default_join,
    fact_id,
    generation_enabled,
    join_chunks,
    load_m01_level_plan,
    m01_variant,
    validate_contract_input,
    validate_contract_output,
)
from app.schemas.languages import Language
from app.schemas.mission_m01_contract import (
    Answer,
    ApprovedTerm,
    ConfirmedAttribute,
    ConfirmedCount,
    ConfirmedObject,
    ConfirmedRelation,
    ConfirmedSceneFacts,
    ContractQuestion,
    Feedback,
    GeneratedMarkerOption,
    GeneratedQuestion,
    Hint,
    LearnerContext,
    M01ContractInput,
    M01ContractOutput,
    M01GeneratedLesson,
    MissionRef,
    PreparationCard,
    PrivateEvaluation,
    SentenceChunk,
    WorkedExample,
)
from app.schemas.tasks import QuestionEvaluation, VocabularyChoice
from app.services.mission_eligibility import (
    IMPLEMENTED_MISSIONS,
    m01_multilingual_eligibility,
    m01_scene_fact_eligibility,
)
from app.services.mission_lessons_m01_multilingual import build_m01_multilingual_task
from app.services.mission_registry import (
    A0_MISSION_LESSONS,
    A2_MISSION_LESSONS,
    MISSION_LESSONS,
    lesson_spec,
)

LANGUAGES = ("es", "fr", "de", "ko")
LEVELS = ("A0", "A1", "A2")


def contract_input(level="A1", language="es", linguistic=None):
    first_id, second_id, third_id = uuid4(), uuid4(), uuid4()
    first_fact = fact_id("object", first_id)
    second_fact = fact_id("object", second_id)
    third_fact = fact_id("object", third_id)
    attribute_fact = fact_id("attribute", first_id, "colour")
    second_attribute_fact = fact_id("attribute", second_id, "size")
    relation_fact = fact_id("relation", first_fact, "on", second_fact)
    count_fact = fact_id("count", "cup")
    linguistic_metadata = {"gender": "feminine"} if language == "es" else {}
    if linguistic is not None:
        linguistic_metadata = linguistic
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
                target_text={"es": "taza", "fr": "tasse", "de": "Tasse", "ko": "컵"}[
                    language
                ],
                part_of_speech="noun",
                provenance="reviewedLexicon",
                linguistic=linguistic_metadata,
            )
        ],
        learner=LearnerContext(proficiency_level=level),
    )


def example_chunks(language, prefix):
    words = {
        "es": ["Es", "una", "taza", "."],
        "fr": ["C'est", "une", "tasse", "."],
        "de": ["Das", "ist", "eine", "Tasse", "."],
        "ko": ["이것은", "컵", "입니다", "."],
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
                target_ids=definition.teaching.teach_before_assessment or required_targets[:1],
            )
        ],
        questions=question_list,
        private=PrivateEvaluation(answers=answers, evaluations=evaluations),
    )


def planned_a1_output(contract=None):
    contract = contract or contract_input()
    definition = get_mission("M01", "A1", 1)
    plan = load_m01_level_plan("A1")
    first, second = contract.scene_facts.objects[:2]
    attribute = contract.scene_facts.attributes[0]
    relation = contract.scene_facts.relations[0]
    teach_targets = list(definition.teaching.teach_before_assessment)

    def chunk(chunk_id, text):
        return SentenceChunk(
            chunk_id=chunk_id,
            text=text,
            join="none" if text in {".", ",", "!", "?"} else "space",
        )

    questions = [
        ContractQuestion(
            question_id="identify",
            target_ids=["identify-object"],
            prompt="Which object is the cup?",
            interaction="markerChoice",
            options=[
                VocabularyChoice(option_id="cup", label="taza"),
                VocabularyChoice(option_id="table", label="mesa"),
            ],
            marker_fact_ids={"cup": first.fact_id, "table": second.fact_id},
            chunks=[],
            fact_ids=[first.fact_id],
            hints=[Hint(level=1, text="Look at the cup.")],
            feedback=Feedback(correct="Correct.", corrections=[]),
        ),
        ContractQuestion(
            question_id="name",
            target_ids=["name-object"],
            prompt="Name the object.",
            interaction="multipleChoice",
            options=[
                VocabularyChoice(option_id="name-cup", label="taza"),
                VocabularyChoice(option_id="name-table", label="mesa"),
            ],
            chunks=[],
            fact_ids=[first.fact_id],
            hints=[Hint(level=1, text="It is used for a drink.")],
            feedback=Feedback(correct="Correct.", corrections=[]),
        ),
        ContractQuestion(
            question_id="colour",
            target_ids=["describe-colour"],
            prompt="Describe the cup.",
            interaction="multipleChoice",
            options=[
                VocabularyChoice(option_id="colour-correct", label="taza azul"),
                VocabularyChoice(option_id="colour-wrong", label="taza roja"),
            ],
            chunks=[],
            fact_ids=[first.fact_id, attribute.fact_id],
            hints=[Hint(level=1, text="Use the colour word.")],
            feedback=Feedback(correct="Correct.", corrections=[]),
        ),
        ContractQuestion(
            question_id="location",
            target_ids=["describe-location"],
            prompt="Say where the cup is.",
            interaction="sentenceBuilding",
            options=[],
            chunks=[
                chunk("location-la", "La"),
                chunk("location-taza", "taza"),
                chunk("location-queda", "queda"),
                chunk("location-aqui", "aquí"),
                chunk("location-period", "."),
            ],
            fact_ids=[first.fact_id, relation.fact_id],
            hints=[Hint(level=1, text="Start with the object.")],
            feedback=Feedback(correct="Correct.", corrections=[]),
        ),
    ]
    answers = {
        "identify": Answer(correct_option_id="cup"),
        "name": Answer(correct_option_id="name-cup"),
        "colour": Answer(correct_option_id="colour-correct"),
        "location": Answer(chunk_ids=[
            "location-la", "location-taza", "location-queda", "location-aqui",
            "location-period",
        ]),
    }
    evaluations = []
    for question in questions:
        permitted = set(plan.evidence[question.interaction])
        for target_id in question.target_ids:
            permitted &= set(definition.targets[target_id].evidence_types)
        evaluations.append(QuestionEvaluation(
            question_id=question.question_id,
            objective_id=definition.objective.objective_id,
            target_ids=question.target_ids,
            evidence_type=next(
                item for item in plan.evidence[question.interaction] if item in permitted
            ),
        ))
    examples = [
        WorkedExample(
            example_id=f"example-{index}",
            chunks=[chunk(f"example-{index}-a", text)],
            translation=f"Example translation {index}.",
            fact_ids=[first.fact_id, attribute.fact_id],
            target_ids=teach_targets,
        )
        for index, text in enumerate(("La taza está sobre la mesa.", "La mesa es azul."), 1)
    ]
    output = M01ContractOutput(
        contract_version=CONTRACT_VERSION,
        mission=contract.mission,
        target_language=contract.target_language,
        instruction_language=contract.instruction_language,
        objective_id=definition.objective.objective_id,
        title="Describe the scene.",
        preparation=[
            PreparationCard(card_id="prep-cup", text="taza", fact_ids=[first.fact_id]),
            PreparationCard(
                card_id="prep-colour", text="azul", fact_ids=[attribute.fact_id]
            ),
        ],
        worked_examples=examples,
        questions=questions,
        private=PrivateEvaluation(answers=answers, evaluations=evaluations),
    )
    return contract, output, plan


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
        ("es", "Es una taza."),
        ("ko", "이것은 컵 입니다."),
    ],
)
def test_language_specific_chunk_joining(language, expected):
    assert join_chunks(example_chunks(language, "joined")) == expected


def test_word_separator_none_joins_synthetic_language_without_spaces():
    language = Language.model_validate(
        {
            "code": "qaa",
            "englishName": "Test language",
            "nativeName": "Test language",
            "script": "Latn",
            "wordSeparator": "none",
            "learnable": False,
            "instruction": False,
            "speech": {"synthesisLocale": "qaa"},
        }
    )
    chunks = [
        SentenceChunk(
            chunk_id=f"chunk-{index}",
            text=text,
            join=default_join(language, text),
        )
        for index, text in enumerate(["ab", "cd", "."])
    ]

    assert join_chunks(chunks) == "abcd."


def test_linguistic_metadata_is_optional_and_accepts_extensions():
    spanish = contract_input(language="es")
    korean = contract_input(language="ko")
    korean_with_counter = contract_input(language="ko", linguistic={"counter": "개"})

    assert spanish.vocabulary[0].linguistic == {"gender": "feminine"}
    assert korean.vocabulary[0].linguistic == {}
    assert validate_contract_input(korean_with_counter).practice_level == "A1"
    assert korean_with_counter.vocabulary[0].linguistic == {"counter": "개"}


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


def test_plan_aware_validation_rejects_each_a1_structure_failure():
    contract, output, plan = planned_a1_output()

    def rejected(changed, message):
        with pytest.raises(MissionContractError, match=message):
            validate_contract_output(contract, changed, plan)

    rejected(output.model_copy(update={"questions": output.questions[:-1]}), "fewer than")
    extra_questions = []
    extra_answers = dict(output.private.answers)
    extra_evaluations = list(output.private.evaluations)
    for index in range(plan.max_questions - len(output.questions) + 1):
        question_id = f"extra-{index}"
        extra_questions.append(output.questions[1].model_copy(update={
            "question_id": question_id,
        }))
        extra_answers[question_id] = output.private.answers["name"]
        extra_evaluations.append(output.private.evaluations[1].model_copy(update={
            "question_id": question_id,
        }))
    rejected(output.model_copy(update={
        "questions": [*output.questions, *extra_questions],
        "private": output.private.model_copy(update={
            "answers": extra_answers,
            "evaluations": extra_evaluations,
        }),
    }), "question count")
    rejected(
        output.model_copy(update={
            "questions": [
                output.questions[0],
                output.questions[1].model_copy(update={
                    "interaction": "markerChoice",
                    "marker_fact_ids": {
                        "name-cup": contract.scene_facts.objects[0].fact_id,
                        "name-table": contract.scene_facts.objects[1].fact_id,
                    },
                }),
                *output.questions[2:],
            ]
        }),
        "not permitted",
    )
    missing_group_questions = [
        question.model_copy(update={"target_ids": ["name-object"]})
        if question.question_id in {"colour", "location"} else question
        for question in output.questions
    ]
    rejected(output.model_copy(update={"questions": missing_group_questions}), "required target")

    bad_prep = output.preparation[0].model_copy(
        update={"fact_ids": [contract.scene_facts.counted_groups[0].fact_id]}
    )
    rejected(output.model_copy(update={"preparation": [bad_prep, *output.preparation[1:]]}),
             "fact kind")
    rejected(output.model_copy(update={"preparation": output.preparation[:1]}),
             "preparation-card count")
    excessive_prep = [
        *output.preparation,
        *[
            output.preparation[0].model_copy(update={"card_id": f"extra-prep-{index}"})
            for index in range(plan.max_preparation_cards)
        ],
    ]
    rejected(output.model_copy(update={"preparation": excessive_prep}),
             "preparation-card count")
    rejected(output.model_copy(update={"worked_examples": output.worked_examples[:1]}),
             "worked-example count")

    name = output.questions[1]
    rejected(
        output.model_copy(update={"questions": [
            output.questions[0],
            name.model_copy(update={"options": name.options[:1]}),
            *output.questions[2:],
        ]}),
        "option count",
    )
    duplicate_labels = name.model_copy(update={
        "options": [
            name.options[0],
            name.options[1].model_copy(update={"label": " TAZA  "}),
        ]
    })
    rejected(output.model_copy(update={
        "questions": [output.questions[0], duplicate_labels, *output.questions[2:]]
    }), "labels must be distinct")
    normalized_labels = name.model_copy(update={"options": [
        name.options[0].model_copy(update={"label": "café"}),
        name.options[1].model_copy(update={"label": "cafe\u0301"}),
    ]})
    rejected(output.model_copy(update={
        "questions": [output.questions[0], normalized_labels, *output.questions[2:]]
    }), "labels must be distinct")
    rejected(output.model_copy(update={
        "questions": [
            output.questions[0],
            name.model_copy(update={"chunks": [SentenceChunk(
                chunk_id="unexpected", text="taza", join="space"
            )]}),
            *output.questions[2:],
        ]
    }), "choice questions cannot have chunks")
    bad_question_fact = output.questions[1].model_copy(update={
        "fact_ids": [*output.questions[1].fact_ids,
                     contract.scene_facts.counted_groups[0].fact_id]
    })
    rejected(output.model_copy(update={
        "questions": [output.questions[0], bad_question_fact, *output.questions[2:]]
    }), "fact kind outside the plan")
    too_many_options = name.model_copy(update={"options": [
        VocabularyChoice(option_id=f"extra-option-{index}", label=f"choice {index}")
        for index in range(plan.max_options + 1)
    ]})
    too_many_answers = dict(output.private.answers)
    too_many_answers["name"] = Answer(correct_option_id="extra-option-0")
    rejected(output.model_copy(update={
        "questions": [output.questions[0], too_many_options, *output.questions[2:]],
        "private": output.private.model_copy(update={"answers": too_many_answers}),
    }), "option count")
    location = output.questions[3]
    rejected(output.model_copy(update={
        "questions": [*output.questions[:3], location.model_copy(update={
            "options": [VocabularyChoice(option_id="extra", label="taza")]
        })]
    }), "cannot have options")

    marker = output.questions[0]
    repeated_markers = dict(marker.marker_fact_ids)
    repeated_markers["table"] = repeated_markers["cup"]
    rejected(output.model_copy(update={
        "questions": [marker.model_copy(update={"marker_fact_ids": repeated_markers}),
                      *output.questions[1:]]
    }), "distinct objects")
    wrong_correct_marker = dict(marker.marker_fact_ids)
    wrong_correct_marker["cup"] = contract.scene_facts.objects[1].fact_id
    wrong_correct_marker["table"] = contract.scene_facts.objects[0].fact_id
    rejected(output.model_copy(update={
        "questions": [marker.model_copy(update={"marker_fact_ids": wrong_correct_marker}),
                      *output.questions[1:]]
    }), "correct marker object")
    non_object_markers = dict(marker.marker_fact_ids)
    non_object_markers["table"] = contract.scene_facts.attributes[0].fact_id
    rejected(output.model_copy(update={
        "questions": [marker.model_copy(update={"marker_fact_ids": non_object_markers}),
                      *output.questions[1:]]
    }), "map to object facts")

    answers = dict(output.private.answers)
    answers["name"] = answers["name"].model_copy(update={"correct_option_id": "name-table"})
    rejected(output.model_copy(update={
        "private": output.private.model_copy(update={"answers": answers})
    }), "approved object term")
    ungrounded_sentence = location.model_copy(update={"chunks": [
        chunk.model_copy(update={"text": "objeto"})
        if chunk.chunk_id == "location-taza" else chunk
        for chunk in location.chunks
    ]})
    rejected(output.model_copy(update={
        "questions": [*output.questions[:3], ungrounded_sentence]
    }), "approved object term")

    def chunk(chunk_id, text):
        return SentenceChunk(
            chunk_id=chunk_id,
            text=text,
            join="none" if text in {".", ",", "!", "?"} else "space",
        )

    answers = dict(output.private.answers)
    answers["location"] = Answer(chunk_ids=[
        "location-la", "location-taza", "location-queda", "location-aqui",
        "location-period", "location-taza",
    ])
    rejected(output.model_copy(update={
        "private": output.private.model_copy(update={"answers": answers})
    }), "cannot repeat")
    answers["location"] = Answer(chunk_ids=[
        "location-la", "location-taza", "location-queda", "location-aqui",
        "location-period", "not-offered",
    ])
    rejected(output.model_copy(update={
        "private": output.private.model_copy(update={"answers": answers})
    }), "must use offered")

    overlong_chunks = [
        chunk.model_copy(update={"chunk_id": f"location-extra-{index}"})
        for index, chunk in enumerate(location.chunks[:4])
    ]
    long_answer_chunks = [*location.chunks, *overlong_chunks]
    long_location = location.model_copy(update={"chunks": long_answer_chunks})
    answers["location"] = Answer(chunk_ids=[chunk.chunk_id for chunk in long_answer_chunks])
    rejected(output.model_copy(update={
        "questions": [*output.questions[:3], long_location],
        "private": output.private.model_copy(update={"answers": answers}),
    }), "too many chunks")
    distracted = location.model_copy(update={"chunks": [
        *location.chunks,
        chunk("distractor-1", "extra"),
        chunk("distractor-2", "words"),
        chunk("distractor-3", "here"),
    ]})
    rejected(output.model_copy(update={
        "questions": [*output.questions[:3], distracted]
    }), "distractor chunks")
    empty_chunk = location.chunks[0].model_copy(update={"text": "  "})
    rejected(output.model_copy(update={
        "questions": [*output.questions[:3], location.model_copy(update={
            "chunks": [empty_chunk, *location.chunks[1:]]
        })]
    }), "contain text")

    rejected(output.model_copy(update={
        "questions": [output.questions[0].model_copy(update={"hints": []}),
                      *output.questions[1:]]
    }), "hint count")
    too_many_hints = output.questions[0].model_copy(update={"hints": [
        Hint(level=1, text="One."),
        Hint(level=2, text="Two."),
        Hint(level=3, text="Three."),
        Hint(level=3, text="Four.").model_copy(update={"level": 4}),
    ]})
    rejected(output.model_copy(update={
        "questions": [too_many_hints, *output.questions[1:]]
    }), "hint count")
    unordered = output.questions[0].model_copy(update={
        "hints": [Hint(level=2, text="Later."), Hint(level=1, text="Earlier.")]
    })
    rejected(output.model_copy(update={
        "questions": [unordered, *output.questions[1:]]
    }), "strictly ascending")
    early_reveal = output.questions[0].model_copy(update={
        "hints": [Hint(level=1, text="Answer.", reveals_answer=True),
                  Hint(level=2, text="Later.")]
    })
    rejected(output.model_copy(update={
        "questions": [early_reveal, *output.questions[1:]]
    }), "only the final hint")

    unteaching = [
        example.model_copy(update={"target_ids": ["name-object"]})
        for example in output.worked_examples
    ]
    rejected(output.model_copy(update={"worked_examples": unteaching}), "teach targets")
    duplicate_example = output.worked_examples[0].model_copy(update={
        "chunks": output.questions[3].chunks
    })
    rejected(output.model_copy(update={
        "worked_examples": [duplicate_example, *output.worked_examples[1:]]
    }), "cannot reuse a question answer")


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

    answers[question.question_id] = answer.model_copy(update={"chunk_ids": []})
    empty_answer = output.model_copy(
        update={"private": output.private.model_copy(update={"answers": answers})}
    )
    with pytest.raises(MissionContractError, match="need ordered chunk IDs"):
        validate_contract_output(contract, empty_answer)


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


def test_generated_lesson_conversion_derives_private_evaluations():
    contract = contract_input()
    first, second = contract.scene_facts.objects[:2]
    generated = M01GeneratedLesson(
        title="Identify a cup",
        preparation=[],
        worked_examples=[],
        questions=[
            GeneratedQuestion(
                question_id="identify-cup",
                target_ids=["identify-object"],
                prompt="Which object is the cup?",
                interaction="markerChoice",
                options=[
                    VocabularyChoice(option_id="cup-option", label="taza"),
                    VocabularyChoice(option_id="table-option", label="mesa"),
                ],
                marker_options=[
                    GeneratedMarkerOption(option_id="cup-option", fact_id=first.fact_id),
                    GeneratedMarkerOption(option_id="table-option", fact_id=second.fact_id),
                ],
                chunks=[],
                fact_ids=[first.fact_id],
                answer=Answer(correct_option_id="cup-option"),
                hints=[Hint(level=1, text="Look at the blue object.")],
                feedback=Feedback(correct="Correct.", corrections=[]),
            )
        ],
    )

    output = convert_generated_lesson(contract, generated)
    evaluation = output.private.evaluations[0]

    assert output.questions[0].marker_fact_ids == {
        "cup-option": first.fact_id,
        "table-option": second.fact_id,
    }
    assert output.private.answers["identify-cup"].correct_option_id == "cup-option"
    assert evaluation.evidence_type == "objectSelection"
    assert evaluation.scene_object_id == first.scene_object_id
    assert "evaluations" not in M01GeneratedLesson.model_json_schema()["properties"]


def test_multilingual_m01_evidence_preferences_never_emit_production():
    contract = contract_input()
    first, second = contract.scene_facts.objects[:2]
    interactions = [
        ("identify-object", "markerChoice", "objectSelection"),
        ("name-object", "multipleChoice", "recognition"),
        ("describe-colour", "sentenceBuilding", "construction"),
    ]
    questions = []
    for index, (target_id, interaction, _expected_evidence) in enumerate(interactions):
        questions.append(
            GeneratedQuestion(
                question_id=f"evidence-{index}",
                target_ids=[target_id],
                prompt="Identify the confirmed object.",
                interaction=interaction,
                options=(
                    [
                        VocabularyChoice(option_id=f"evidence-{index}-a", label="taza"),
                        VocabularyChoice(option_id=f"evidence-{index}-b", label="mesa"),
                    ]
                    if interaction != "sentenceBuilding" else []
                ),
                marker_options=(
                    [
                        GeneratedMarkerOption(
                            option_id=f"evidence-{index}-a", fact_id=first.fact_id
                        ),
                        GeneratedMarkerOption(
                            option_id=f"evidence-{index}-b", fact_id=second.fact_id
                        ),
                    ]
                    if interaction == "markerChoice" else []
                ),
                chunks=(
                    example_chunks("es", f"evidence-{index}")
                    if interaction == "sentenceBuilding" else []
                ),
                fact_ids=[first.fact_id],
                answer=(
                    Answer(chunk_ids=[
                        chunk.chunk_id
                        for chunk in example_chunks("es", f"evidence-{index}")
                    ])
                    if interaction == "sentenceBuilding"
                    else Answer(correct_option_id=f"evidence-{index}-a")
                ),
                hints=[Hint(level=1, text="Look at the object.")],
                feedback=Feedback(correct="Correct.", corrections=[]),
            )
        )
    generated = M01GeneratedLesson(
        title="Recognise the scene.",
        preparation=[],
        worked_examples=[],
        questions=questions,
    )

    output = convert_generated_lesson(contract, generated)
    evidence = [item.evidence_type for item in output.private.evaluations]

    assert evidence == ["objectSelection", "recognition", "construction"]
    assert "production" not in evidence
    assert all(
        item in {
            evidence_type
            for permitted in load_m01_level_plan("A1").evidence.values()
            for evidence_type in permitted
        }
        for item in evidence
    )


def test_m01_cache_identity_covers_payload_and_version_dimensions():
    cache = ResultCache()
    scope = CacheScope.public()
    contract = contract_input().model_dump(mode="json", by_alias=True)
    payload = {
        "contract": contract,
        "planVersion": 1,
        "levelPlan": {"contentVersion": 1},
    }
    version = FeatureVersion("learning-task", "prompt-v1", "schema-v1", "validator-v1")

    def key(changed_payload=payload, changed_version=version):
        request = CacheRequest(
            version=changed_version,
            scope=scope,
            payload=changed_payload,
            generation={"model": "test"},
            approved_deployments=frozenset({"test"}),
            compute=lambda: None,
            encode=lambda value: value,
            decode=lambda value: value,
        )
        return cache._key(request, ReferenceMap(changed_payload))

    original = key()
    assert key() == original
    variations = []

    for field, value in (
        ("targetLanguage", "fr"),
        ("practiceLevel", "A2"),
    ):
        changed = json.loads(json.dumps(payload))
        if field == "targetLanguage":
            changed["contract"][field] = value
        else:
            changed["contract"]["mission"][field] = value
        variations.append(key(changed))

    changed = json.loads(json.dumps(payload))
    changed["contract"]["sceneFacts"]["objects"][0]["label"] = "mug"
    variations.append(key(changed))
    changed = json.loads(json.dumps(payload))
    changed["contract"]["mission"]["contentVersion"] = 2
    variations.append(key(changed))
    changed = json.loads(json.dumps(payload))
    changed["contract"]["learner"]["termFamiliarity"] = {"cup": 0.5}
    variations.append(key(changed))
    for version_field, value in (
        ("prompt_version", "prompt-v2"),
        ("schema_version", "schema-v2"),
        ("validator_version", "validator-v2"),
    ):
        variations.append(key(changed_version=replace(version, **{version_field: value})))
    changed = json.loads(json.dumps(payload))
    changed["planVersion"] = 2
    variations.append(key(changed))

    assert all(candidate != original for candidate in variations)
    assert len(variations) == len(set(variations))


def test_multilingual_task_keeps_answer_and_hint_text_private():
    contract = contract_input()
    output = contract_output(contract)
    questions = [
        question.model_copy(update={
            "hints": [Hint(level=1, text=f"private hint {question.question_id}")],
        })
        for question in output.questions
    ]
    output = output.model_copy(update={"questions": questions})
    first = questions[0]
    hint_text = f"private hint {first.question_id}"
    mission = get_mission("M01", "A1", 1)
    task = build_m01_multilingual_task(uuid4(), mission, contract, output)
    public_content = task.public_content.model_dump_json(by_alias=True)

    assert task.kind == "grammarLesson"
    assert hint_text not in public_content
    assert "correctOptionIds" not in public_content
    first_question = task.public_content.questions[0]
    assert first_question.prompt_translation == first.prompt_translation
    assert first_question.translation is None
    assert task.answer_key.mission_state["hints"][first.question_id][0]["text"] == (
        hint_text
    )


def test_marker_choice_public_labels_are_review_marker_numbers():
    contract = contract_input()
    objects = [
        item.model_copy(update={"marker": marker})
        for item, marker in zip(contract.scene_facts.objects, (1, 3, 2), strict=True)
    ]
    contract = contract.model_copy(update={
        "scene_facts": contract.scene_facts.model_copy(update={"objects": objects}),
    })
    output = contract_output(contract)
    output = output.model_copy(update={
        "questions": [
            question.model_copy(update={"hints": [Hint(level=1, text="Look carefully.")]})
            for question in output.questions
        ],
    })
    mission = get_mission("M01", "A1", 1)
    task = build_m01_multilingual_task(uuid4(), mission, contract, output)

    source_question = next(
        question for question in output.questions if question.interaction == "markerChoice"
    )
    public_question = next(
        question for question in task.public_content.questions if question.marker_object_ids
    )
    object_facts = {item.fact_id: item for item in contract.scene_facts.objects}
    expected_labels = {
        option_id: str(object_facts[fact_id].marker)
        for option_id, fact_id in source_question.marker_fact_ids.items()
    }

    assert {option.option_id: option.label for option in public_question.options} == (
        expected_labels
    )
    assert set(expected_labels.values()) == {"1", "3"}


def test_marker_choice_rejects_object_facts_without_review_markers():
    contract = contract_input()
    output = contract_output(contract)
    marker_question = next(
        question for question in output.questions if question.interaction == "markerChoice"
    )
    missing_marker_fact = next(iter(marker_question.marker_fact_ids.values()))
    objects = [
        item.model_copy(update={"marker": None})
        if item.fact_id == missing_marker_fact else item
        for item in contract.scene_facts.objects
    ]
    contract = contract.model_copy(update={
        "scene_facts": contract.scene_facts.model_copy(update={"objects": objects}),
    })

    with pytest.raises(MissionContractError, match="review markers"):
        validate_contract_output(contract, output)


def test_m01_eligibility_uses_facts_before_translation_and_terms_after():
    plan = load_m01_level_plan("A1")
    objects = [
        SimpleNamespace(id=uuid4(), label="cup", attributes={"color": "red"}),
        SimpleNamespace(id=uuid4(), label="table", attributes={"size": "large"}),
    ]
    assert m01_scene_fact_eligibility(plan, objects).eligible

    contract = contract_input()
    assert not m01_multilingual_eligibility(plan, contract).eligible
    second_object = contract.scene_facts.objects[1]
    attribute = contract.scene_facts.attributes[0]
    terms = [
        term.model_copy(update={"provenance": "sessionTranslation"})
        for term in contract.vocabulary
    ]
    terms.extend([
        ApprovedTerm(
            term_id="table-term",
            fact_id=second_object.fact_id,
            source_text="table",
            target_text="mesa",
            part_of_speech="noun",
            provenance="sessionTranslation",
            vocabulary_item_id=uuid4(),
        ),
        ApprovedTerm(
            term_id="colour-term",
            fact_id=attribute.fact_id,
            source_text="blue",
            target_text="azul",
            part_of_speech="adjective",
            provenance="sessionTranslation",
            vocabulary_item_id=uuid4(),
        ),
    ])
    approved_contract = contract.model_copy(update={"vocabulary": terms})
    assert m01_multilingual_eligibility(plan, approved_contract).eligible


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


def test_a2_connected_fact_threshold_and_followup_order_and_subset():
    contract, output, _ = planned_a1_output()
    a2_contract = contract.model_copy(update={
        "mission": contract.mission.model_copy(update={"practice_level": "A2"}),
    })
    plan = load_m01_level_plan("A2")
    definition = get_mission("M01", "A2", 1)
    first = contract.scene_facts.objects[0]
    identify, *rest = output.questions
    describe_name, describe_colour, connect = rest
    identify = identify.model_copy(update={"target_ids": ["identify-scene-object"]})
    describe_name = describe_name.model_copy(update={"target_ids": ["describe-scene-facts"]})
    describe_colour = describe_colour.model_copy(
        update={"target_ids": ["describe-scene-facts"]}
    )
    connect = connect.model_copy(update={
        "target_ids": ["connect-scene-facts"],
        "section": "connect-scene-facts",
        "fact_ids": [first.fact_id, contract.scene_facts.attributes[0].fact_id],
    })
    followup = describe_name.model_copy(update={
        "question_id": "follow-up",
        "target_ids": ["follow-up-scene-fact"],
        "section": "follow-up-scene-fact",
        "fact_ids": [first.fact_id],
        "options": [
            option.model_copy(update={"label": "taza mesa"})
            if option.option_id == "name-cup" else option
            for option in describe_name.options
        ],
    })
    questions = [identify, describe_name, describe_colour, connect, followup]
    a2_answers = dict(output.private.answers)
    a2_answers["follow-up"] = output.private.answers["name"]
    target_ids = [
        "identify-scene-object",
        "describe-scene-facts",
        "describe-scene-facts",
        "connect-scene-facts",
        "follow-up-scene-fact",
    ]
    evidence_types = [
        "objectSelection", "recognition", "recognition", "construction", "recognition",
    ]
    a2_evaluations = [
        evaluation.model_copy(update={
            "objective_id": definition.objective.objective_id,
            "target_ids": [target_id],
            "evidence_type": evidence_type,
        })
        for evaluation, target_id, evidence_type in zip(
            output.private.evaluations, target_ids[:4], evidence_types[:4], strict=True
        )
    ]
    a2_evaluations.append(output.private.evaluations[1].model_copy(update={
        "question_id": "follow-up",
        "objective_id": definition.objective.objective_id,
        "target_ids": ["follow-up-scene-fact"],
        "evidence_type": "recognition",
    }))
    a2_output = output.model_copy(update={
        "mission": a2_contract.mission,
        "objective_id": definition.objective.objective_id,
        "worked_examples": [
            example.model_copy(update={
                "target_ids": [
                    "identify-scene-object",
                    "describe-scene-facts",
                    "connect-scene-facts",
                ]
            })
            for example in output.worked_examples
        ],
        "questions": questions,
        "private": output.private.model_copy(update={
            "answers": a2_answers,
            "evaluations": a2_evaluations,
        }),
    })
    validate_contract_output(a2_contract, a2_output, plan)

    with pytest.raises(MissionContractError, match="more distinct scene facts"):
        validate_contract_output(a2_contract, a2_output.model_copy(update={
            "questions": [
                *a2_output.questions[:3],
                connect.model_copy(update={"fact_ids": [first.fact_id]}),
                followup,
            ],
        }), plan)

    with pytest.raises(MissionContractError, match="preceding connect question"):
        validate_contract_output(a2_contract, a2_output.model_copy(update={
            "questions": [*a2_output.questions[:3], followup, connect],
        }), plan)

    with pytest.raises(MissionContractError, match="preceding connect question"):
        validate_contract_output(a2_contract, a2_output.model_copy(update={
            "questions": [
                *a2_output.questions[:4],
                followup.model_copy(update={
                    "fact_ids": [contract.scene_facts.relations[0].fact_id]
                }),
            ],
        }), plan)
