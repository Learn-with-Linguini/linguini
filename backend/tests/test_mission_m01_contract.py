import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

import app.missions.m01_multilingual as m01_multilingual
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
    bind_m01_focus,
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
    ContractOption,
    ContractQuestion,
    Feedback,
    GeneratedMarkerOption,
    GeneratedQuestion,
    LearnerContext,
    M01ContractInput,
    M01ContractOutput,
    M01GeneratedLesson,
    MissionRef,
    PreparationCard,
    PrivateEvaluation,
    SentenceChunk,
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
    second_attribute_fact = fact_id("attribute", second_id, "colour")
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
                kind="colour", value="red",
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
                term_id=name,
                fact_id=object_fact,
                source_text=name,
                target_text={
                    "es": {"cup": "taza", "table": "mesa", "chair": "silla"},
                    "fr": {"cup": "tasse", "table": "table", "chair": "chaise"},
                    "de": {"cup": "Tasse", "table": "Tisch", "chair": "Stuhl"},
                    "ko": {"cup": "컵", "table": "탁자", "chair": "의자"},
                }[language][name],
                part_of_speech="noun",
                provenance="reviewedLexicon",
                linguistic=linguistic_metadata if name == "cup" else {},
            )
            for name, object_fact in zip(
                ("cup", "table", "chair"), (first_fact, second_fact, third_fact), strict=True
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
            ),
            PreparationCard(
                card_id="introduce-table",
                text="table",
                translation="table",
                fact_ids=[contract.scene_facts.objects[1].fact_id],
            ),
        ],
        questions=question_list,
        private=PrivateEvaluation(answers=answers, evaluations=evaluations),
    )


def _planned_output(contract, questions, answers, preparation, plan):
    definition = get_mission("M01", contract.mission.practice_level, 1)
    evaluations = [
        QuestionEvaluation(
            question_id=question.question_id,
            objective_id=definition.objective.objective_id,
            target_ids=slot.target_ids,
            evidence_type=slot.evidence,
            rubric_criterion_ids=slot.criteria,
        )
        for question, slot in zip(questions, plan.questions, strict=True)
    ]
    return M01ContractOutput(
        contract_version=CONTRACT_VERSION,
        mission=contract.mission,
        target_language=contract.target_language,
        instruction_language=contract.instruction_language,
        objective_id=definition.objective.objective_id,
        title=plan.title,
        preparation=preparation,
        questions=questions,
        private=PrivateEvaluation(answers=answers, evaluations=evaluations),
    )


def _chunk(chunk_id, text):
    return SentenceChunk(
        chunk_id=chunk_id,
        text=text,
        join="none" if text in {".", ",", "!", "?"} else "space",
    )


def _with_detail_terms(contract, kinds=("attribute",)):
    """Add placeholder approved terms for colour and relation facts that lack one."""
    existing_term_facts = {term.fact_id for term in contract.vocabulary}
    added = []
    if "attribute" in kinds:
        added.extend(
            ApprovedTerm(
                term_id=f"colour-term-{index}",
                fact_id=attribute.fact_id,
                source_text=attribute.value,
                target_text=attribute.value,
                part_of_speech="adjective",
                provenance="reviewedLexicon",
            )
            for index, attribute in enumerate(contract.scene_facts.attributes)
            if attribute.kind == "colour" and attribute.fact_id not in existing_term_facts
        )
    if "relation" in kinds:
        added.extend(
            ApprovedTerm(
                term_id=f"relation-term-{index}",
                fact_id=relation.fact_id,
                source_text=relation.relation,
                target_text=relation.relation,
                part_of_speech="preposition",
                provenance="reviewedLexicon",
            )
            for index, relation in enumerate(contract.scene_facts.relations)
            if relation.fact_id not in existing_term_facts
        )
    if added:
        contract = contract.model_copy(update={"vocabulary": [*contract.vocabulary, *added]})
    return contract


def _term_texts(contract):
    terms = {}
    for term in contract.vocabulary:
        terms.setdefault(term.fact_id, term.target_text)
    return terms


def planned_a1_output(contract=None):
    contract = _with_detail_terms(contract or contract_input())
    plan = load_m01_level_plan("A1")
    objects_by_fact = {item.fact_id: item for item in contract.scene_facts.objects}
    colours = [
        attribute for attribute in contract.scene_facts.attributes
        if attribute.kind == "colour"
    ]
    first_attribute, second_attribute = colours[:2]
    first = objects_by_fact[first_attribute.object_fact_id]
    second = objects_by_fact[second_attribute.object_fact_id]
    term_text = _term_texts(contract)
    first_name, second_name = term_text[first.fact_id], term_text[second.fact_id]
    first_colour, second_colour = (
        term_text[first_attribute.fact_id], term_text[second_attribute.fact_id]
    )
    questions = [
        ContractQuestion(
            question_id="confirm-first",
            target_ids=plan.questions[0].target_ids,
            prompt=f"¿Es {first_name}?",
            instruction="Is this the cup?",
            interaction="multipleChoice",
            options=[
                ContractOption(
                    option_id="yes-first", label=f"Yes, this is {first_name}.",
                    meaning="yes",
                ),
                ContractOption(
                    option_id="no-first", label=f"No, this is {second_name}.",
                    meaning="no",
                ),
            ],
            chunks=[],
            fact_ids=[first.fact_id],
            statement_fact_id=first.fact_id,
            feedback=Feedback(correct="Correct.", corrections=[]),
        ),
        ContractQuestion(
            question_id="confirm-second",
            target_ids=plan.questions[1].target_ids,
            prompt=f"¿Es {first_name}?",
            instruction="Is this the table?",
            interaction="multipleChoice",
            options=[
                ContractOption(
                    option_id="yes-second", label=f"Yes, this is {first_name}.",
                    meaning="yes",
                ),
                ContractOption(
                    option_id="no-second", label=f"No, this is {second_name}.",
                    meaning="no",
                ),
            ],
            chunks=[],
            fact_ids=[second.fact_id, first.fact_id],
            statement_fact_id=first.fact_id,
            feedback=Feedback(correct="Correct.", corrections=[]),
        ),
        ContractQuestion(
            question_id="choose-attribute",
            target_ids=plan.questions[2].target_ids,
            prompt="What colour is the cup?",
            interaction="multipleChoice",
            options=[
                ContractOption(option_id="blue", label=first_colour),
                ContractOption(option_id="red", label=second_colour),
            ],
            chunks=[],
            fact_ids=[first.fact_id, first_attribute.fact_id],
            feedback=Feedback(correct="Correct.", corrections=[]),
        ),
        ContractQuestion(
            question_id="describe-second",
            target_ids=plan.questions[3].target_ids,
            prompt="Describe the table.",
            interaction="sentenceBuilding",
            options=[],
            chunks=[
                _chunk("describe-la", "La"),
                _chunk("describe-mesa", second_name),
                _chunk("describe-es", "is"),
                _chunk("describe-grande", second_colour),
                _chunk("describe-period", "."),
                _chunk("describe-distractor", "small"),
            ],
            fact_ids=[second.fact_id, second_attribute.fact_id],
            feedback=Feedback(correct="Correct.", corrections=[]),
        ),
    ]
    answers = {
        "confirm-first": Answer(correct_option_id="yes-first"),
        "confirm-second": Answer(correct_option_id="no-second"),
        "choose-attribute": Answer(correct_option_id="blue"),
        "describe-second": Answer(chunk_ids=[
            "describe-la", "describe-mesa", "describe-es", "describe-grande",
            "describe-period",
        ]),
    }
    return (
        contract,
        _planned_output(contract, questions, answers, [], plan),
        plan,
    )


def planned_a0_output(contract=None):
    contract = contract or contract_input(level="A0")
    plan = load_m01_level_plan("A0")
    objects = contract.scene_facts.objects
    term_by_fact = _term_texts(contract)
    names = [term_by_fact[obj.fact_id] for obj in objects]
    questions = []
    answers = {}
    for focus in range(2):
        obj, name = objects[focus], names[focus]
        other_index = (focus + 1) % len(objects)
        marker_options = [
            ContractOption(option_id=f"marker-{focus}-{i}", label=names[i])
            for i in range(min(3, len(objects)))
        ]
        marker_facts = {
            option.option_id: objects[index].fact_id
            for index, option in enumerate(marker_options)
        }
        match_id = f"match-{focus}"
        questions.append(ContractQuestion(
            question_id=match_id,
            target_ids=plan.questions[focus * 3].target_ids,
            prompt="Match the name to its marker.",
            interaction="markerChoice",
            options=marker_options,
            marker_fact_ids=marker_facts,
            chunks=[],
            fact_ids=[obj.fact_id],
            feedback=Feedback(correct="Correct.", corrections=[]),
        ))
        answers[match_id] = Answer(correct_option_id=f"marker-{focus}-{focus}")

        confirm_id = f"confirm-{focus}"
        questions.append(ContractQuestion(
            question_id=confirm_id,
            target_ids=plan.questions[focus * 3 + 1].target_ids,
            prompt=f"Is this {name}?",
            interaction="multipleChoice",
            options=[
                ContractOption(option_id=f"yes-{focus}", label="Yes.", meaning="yes"),
                ContractOption(option_id=f"no-{focus}", label="No.", meaning="no"),
            ],
            chunks=[],
            fact_ids=[obj.fact_id],
            statement_fact_id=obj.fact_id,
            feedback=Feedback(correct="Correct.", corrections=[]),
        ))
        answers[confirm_id] = Answer(correct_option_id=f"yes-{focus}")

        build_id = f"build-{focus}"
        chunks = [
            _chunk(f"build-{focus}-this", "This"),
            _chunk(f"build-{focus}-is", "is"),
            _chunk(f"build-{focus}-name", name),
            _chunk(f"build-{focus}-period", "."),
            _chunk(f"build-{focus}-extra", names[other_index]),
        ]
        questions.append(ContractQuestion(
            question_id=build_id,
            target_ids=plan.questions[focus * 3 + 2].target_ids,
            prompt="Build an identification.",
            interaction="sentenceBuilding",
            options=[],
            chunks=chunks,
            fact_ids=[obj.fact_id],
            feedback=Feedback(correct="Correct.", corrections=[]),
        ))
        answers[build_id] = Answer(chunk_ids=[chunk.chunk_id for chunk in chunks[:4]])

    preparation = [
        PreparationCard(
            card_id=f"object-{index}",
            text=name,
            translation=name,
            fact_ids=[obj.fact_id],
        )
        for index, (obj, name) in enumerate(zip(objects, names, strict=True))
    ] + [
        PreparationCard(card_id="frame", text="What is this?", fact_ids=[]),
        PreparationCard(
            card_id="first-identify",
            text=f"This is {names[0]}.",
            fact_ids=[objects[0].fact_id],
        ),
    ]
    return contract, _planned_output(
        contract, questions, answers, preparation, plan
    ), plan


def planned_a2_output(contract=None):
    contract = _with_detail_terms(
        contract or contract_input(level="A2"), ("attribute", "relation")
    )
    plan = load_m01_level_plan("A2")
    first, second, third = contract.scene_facts.objects[:3]
    attribute = contract.scene_facts.attributes[0]
    relation = contract.scene_facts.relations[0]
    term_text = _term_texts(contract)
    names = [term_text[item.fact_id] for item in (first, second, third)]
    colour, other_colour = term_text[attribute.fact_id], "other-colour"
    position = term_text[relation.fact_id]
    questions = [
        ContractQuestion(
            question_id="scene-marker",
            target_ids=plan.questions[0].target_ids,
            prompt="Select the object named by the fact.",
            interaction="markerChoice",
            options=[
                ContractOption(option_id="first", label=names[0]),
                ContractOption(option_id="third", label=names[2]),
            ],
            marker_fact_ids={"first": first.fact_id, "third": third.fact_id},
            chunks=[],
            fact_ids=[first.fact_id],
            feedback=Feedback(correct="Correct.", corrections=[]),
        ),
        ContractQuestion(
            question_id="scene-fact",
            target_ids=plan.questions[1].target_ids,
            prompt="Build the confirmed fact.",
            interaction="sentenceBuilding",
            options=[],
            chunks=[
                _chunk("fact-hay", "There"),
                _chunk("fact-is", "is"),
                _chunk("fact-name", names[0]),
                _chunk("fact-blue", colour),
                _chunk("fact-period", "."),
                _chunk("fact-extra", "but"),
            ],
            fact_ids=[first.fact_id, attribute.fact_id],
            feedback=Feedback(correct="Correct.", corrections=[]),
        ),
        ContractQuestion(
            question_id="scene-description-choice",
            target_ids=plan.questions[2].target_ids,
            prompt="Which description matches the photo?",
            interaction="multipleChoice",
            options=[
                ContractOption(
                    option_id="description-correct",
                    label=f"There is {names[0]} {colour} and {names[2]}.",
                ),
                ContractOption(option_id="description-wrong-one", label=f"There is {names[1]}."),
                ContractOption(option_id="description-wrong-two", label="There are no objects."),
            ],
            chunks=[],
            fact_ids=[first.fact_id, attribute.fact_id, third.fact_id],
            feedback=Feedback(correct="Correct.", corrections=[]),
        ),
        ContractQuestion(
            question_id="scene-description-build",
            target_ids=plan.questions[3].target_ids,
            prompt="Build the connected description.",
            interaction="sentenceBuilding",
            options=[],
            chunks=[
                _chunk("connect-there", "There"),
                _chunk("connect-is", "is"),
                _chunk("connect-first", names[0]),
                _chunk("connect-blue", colour),
                _chunk("connect-on", position),
                _chunk("connect-table", names[1]),
                _chunk("connect-here", "is here"),
                _chunk("connect-period", "."),
                _chunk("connect-extra", "but"),
            ],
            fact_ids=[
                first.fact_id, attribute.fact_id, second.fact_id, relation.fact_id,
            ],
            feedback=Feedback(correct="Correct.", corrections=[]),
        ),
        ContractQuestion(
            question_id="scene-follow-up",
            target_ids=plan.questions[4].target_ids,
            prompt="Which detail was used in the description?",
            interaction="multipleChoice",
            options=[
                ContractOption(option_id="detail-blue", label=colour),
                ContractOption(option_id="detail-red", label=other_colour),
            ],
            chunks=[],
            fact_ids=[first.fact_id, attribute.fact_id],
            feedback=Feedback(correct="Correct.", corrections=[]),
        ),
    ]
    answers = {
        "scene-marker": Answer(correct_option_id="first"),
        "scene-fact": Answer(chunk_ids=[
            "fact-hay", "fact-is", "fact-name", "fact-blue", "fact-period",
        ]),
        "scene-description-choice": Answer(correct_option_id="description-correct"),
        "scene-description-build": Answer(chunk_ids=[
            "connect-there", "connect-is", "connect-first", "connect-blue",
            "connect-on", "connect-table", "connect-here", "connect-period",
        ]),
        "scene-follow-up": Answer(correct_option_id="detail-blue"),
    }
    return contract, _planned_output(contract, questions, answers, [], plan), plan


@pytest.mark.parametrize("level", LEVELS)
@pytest.mark.parametrize("language", LANGUAGES)
def test_valid_contracts_cover_all_levels_and_registered_languages(level, language):
    contract = contract_input(level, language)
    output = contract_output(contract)

    assert validate_contract_input(contract).practice_level == level
    validate_contract_output(contract, output)


def test_output_rejects_explanation_that_reveals_a_correct_answer():
    contract, output, _ = planned_a1_output()
    leaking_output = output.model_copy(
        update={"explanation": "\u00a0YES,\u00a0THIS\tIS TAZA!!!"}
    )

    with pytest.raises(
        MissionContractError,
        match="explanation reveals the answer to confirm-first",
    ):
        validate_contract_output(contract, leaking_output)


def test_output_allows_explanation_that_only_mentions_a_preparation_term():
    contract, output, _ = planned_a1_output()
    prepared_term_output = output.model_copy(update={"explanation": "\tTAZA\u00a0"})

    validate_contract_output(contract, prepared_term_output)


def test_output_allows_missing_explanation():
    contract, output, _ = planned_a1_output()

    assert output.explanation is None
    validate_contract_output(contract, output)


def test_output_rejects_no_space_synthetic_language_answer_leak(monkeypatch):
    contract, output, _ = planned_a1_output()
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

    def synthetic_language_lookup(code):
        return language if code.casefold() == "qaa" else get_language(code)

    monkeypatch.setattr(
        "app.missions.m01_multilingual.get_language",
        synthetic_language_lookup,
    )
    contract = contract.model_copy(update={"target_language": "qaa"})
    no_space_chunks = [
        SentenceChunk(chunk_id="no-space-mesa", text="mesa", join="none"),
        SentenceChunk(chunk_id="no-space-roja", text="roja", join="none"),
    ]
    changed_questions = [
        question.model_copy(update={"chunks": no_space_chunks})
        if question.question_id == "describe-second"
        else question
        for question in output.questions
    ]
    answers = dict(output.private.answers)
    answers["describe-second"] = Answer(
        chunk_ids=["no-space-mesa", "no-space-roja"]
    )
    no_space_output = output.model_copy(
        update={
            "target_language": "qaa",
            "explanation": "XMESAROJAY",
            "questions": changed_questions,
            "private": output.private.model_copy(update={"answers": answers}),
        }
    )

    assert join_chunks(no_space_chunks) == "mesaroja"
    with pytest.raises(
        MissionContractError,
        match="explanation reveals the answer to describe-second",
    ):
        validate_contract_output(contract, no_space_output)


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


def test_plan_aware_validation_rejects_wrong_slot_order():
    contract, output, plan = planned_a1_output()
    questions = list(output.questions)
    questions[2], questions[3] = questions[3], questions[2]

    with pytest.raises(
        MissionContractError,
        match=r"question 3 \(describe-second, slot chooseAttribute\): targets",
    ):
        validate_contract_output(contract, output.model_copy(update={"questions": questions}), plan)


def test_plan_aware_validation_rejects_wrong_option_count():
    contract, output, plan = planned_a1_output()
    first = output.questions[0]
    changed = first.model_copy(update={
        "options": [
            *first.options,
            VocabularyChoice(option_id="maybe-first", label="Perhaps this is taza."),
        ]
    })

    with pytest.raises(
        MissionContractError,
        match=r"option count 3 is outside 2–2 for confirmObject",
    ):
        validate_contract_output(
            contract, output.model_copy(update={"questions": [changed, *output.questions[1:]]}),
            plan,
        )


def test_plan_aware_validation_rejects_wrong_distractor_count():
    contract, output, plan = planned_a1_output()
    last = output.questions[3]
    changed = last.model_copy(update={
        "chunks": [*last.chunks, _chunk("second-distractor", "small")],
    })

    with pytest.raises(
        MissionContractError,
        match=r"distractor-chunk count 2 is outside 0–1 for describeObject",
    ):
        validate_contract_output(
            contract, output.model_copy(update={"questions": [*output.questions[:3], changed]}),
            plan,
        )


def test_question_count_error_contains_actual_and_expected():
    contract, output, plan = planned_a1_output()
    questions = output.questions[:-1]
    ids = {question.question_id for question in questions}
    changed = output.model_copy(update={
        "questions": questions,
        "private": output.private.model_copy(update={
            "answers": {key: value for key, value in output.private.answers.items() if key in ids},
            "evaluations": [
                item for item in output.private.evaluations if item.question_id in ids
            ],
        }),
    })

    with pytest.raises(
        MissionContractError,
        match=r"question count 3 does not match plan 4",
    ):
        validate_contract_output(contract, changed, plan)


@pytest.mark.parametrize("builder", [planned_a1_output, planned_a2_output])
def test_a1_and_a2_reject_any_preparation_card(builder):
    contract, output, plan = builder()
    extra = PreparationCard(
        card_id="unexpected-preparation",
        text="taza",
        fact_ids=[contract.scene_facts.objects[0].fact_id],
    )

    with pytest.raises(
        MissionContractError,
        match=r"preparation-card count 1 is outside 0–0",
    ):
        validate_contract_output(contract, output.model_copy(update={
            "preparation": [extra],
        }), plan)


def test_a0_preparation_count_is_objects_plus_two():
    contract, output, plan = planned_a0_output()
    validate_contract_output(contract, output, plan)
    expected = len(contract.scene_facts.objects) + 2
    extra = output.preparation[0].model_copy(update={"card_id": "extra-preparation"})

    for cards, actual in (
        (output.preparation[:-1], expected - 1),
        ([*output.preparation, extra], expected + 1),
    ):
        with pytest.raises(
            MissionContractError,
            match=rf"preparation-card count {actual} is outside {expected}–{expected}",
        ):
            validate_contract_output(contract, output.model_copy(update={
                "preparation": cards,
            }), plan)


def test_question_must_use_its_bound_focus_object():
    contract, output, plan = planned_a1_output()
    first, second = contract.scene_facts.objects[:2]
    second_attribute = contract.scene_facts.attributes[1]
    questions = list(output.questions)
    questions[2] = questions[2].model_copy(update={
        "fact_ids": [second.fact_id, second_attribute.fact_id],
    })

    with pytest.raises(MissionContractError) as exc_info:
        validate_contract_output(contract, output.model_copy(update={"questions": questions}), plan)
    assert (
        f"question 3 (choose-attribute, slot chooseAttribute): focus 1 expects object "
        f"fact {bind_m01_focus(plan, contract)[1].object_fact_id}, got {second.fact_id}"
    ) in str(exc_info.value)

    assert first.fact_id != second.fact_id


def test_questions_two_and_four_must_use_the_same_bound_focus_object():
    contract, output, plan = planned_a1_output()
    expected = bind_m01_focus(plan, contract)[2].object_fact_id
    assert output.questions[1].fact_ids[0] == expected
    other = next(
        item.fact_id for item in contract.scene_facts.objects if item.fact_id != expected
    )
    other_colour = next(
        item.fact_id
        for item in contract.scene_facts.attributes
        if item.object_fact_id == other and item.kind == "colour"
    )
    questions = list(output.questions)
    questions[3] = questions[3].model_copy(update={
        "fact_ids": [other, other_colour],
    })
    assert other in questions[3].fact_ids
    assert expected not in questions[3].fact_ids
    with pytest.raises(MissionContractError) as exc_info:
        validate_contract_output(contract, output.model_copy(update={"questions": questions}), plan)
    assert (
        f"question 4 (describe-second, slot describeObject): focus 2 expects object fact "
        f"{expected}, got {other}"
    ) in str(exc_info.value)


def test_a2_focus_prefers_an_object_with_an_approved_detail_fact():
    contract, _, plan = planned_a2_output()
    first, second, third = contract.scene_facts.objects[:3]
    contract = contract.model_copy(update={
        "scene_facts": contract.scene_facts.model_copy(update={
            "attributes": [
                contract.scene_facts.attributes[0].model_copy(
                    update={"object_fact_id": third.fact_id}
                )
            ],
            "relations": [
                contract.scene_facts.relations[0].model_copy(update={
                    "subject_fact_id": second.fact_id,
                    "reference_fact_id": third.fact_id,
                })
            ],
        })
    })

    binding = bind_m01_focus(plan, contract)[1]
    assert binding.object_fact_id == second.fact_id
    assert binding.object_fact_id != first.fact_id


def test_colour_question_requires_a_colour_fact_for_its_focus_object():
    contract, output, plan = planned_a1_output()
    first, _ = contract.scene_facts.objects[:2]
    second_attribute = contract.scene_facts.attributes[1]
    questions = list(output.questions)
    questions[2] = questions[2].model_copy(update={
        "fact_ids": [first.fact_id, second_attribute.fact_id],
    })

    with pytest.raises(
        MissionContractError,
        match=r"question 3 \(choose-attribute, slot chooseAttribute\): focus 1 expects "
        r"colour fact attribute:\S+, got attribute:\S+",
    ):
        validate_contract_output(contract, output.model_copy(update={"questions": questions}), plan)


@pytest.mark.parametrize(
    ("failure", "message"),
    [
        ("unknown-target", "undefined targets"),
        ("uncovered-group", "does not cover required target group"),
        ("too-few-slots", "fewer slots than required"),
        ("object-count", "min_objects must match photo requirements"),
        ("too-many-focus-objects", "focus_objects cannot exceed min_objects"),
        ("unknown-criterion", "undefined evaluation criteria"),
    ],
)
def test_load_plan_checks_mission_definition_consistency(
    tmp_path, monkeypatch, failure, message,
):
    source = Path(m01_multilingual.M01_PLAN_PATH).read_text(encoding="utf-8")
    if failure == "unknown-target":
        source = source.replace(
            'target_ids = ["recognise-name"]',
            'target_ids = ["not-a-target"]',
            1,
        )
    elif failure == "uncovered-group":
        source = source.replace(
            'target_ids = ["identify-object"]',
            'target_ids = ["recognise-name"]',
        )
    elif failure == "too-few-slots":
        start = source.index("[levels.A0]")
        end = source.index("[levels.A1]")
        section = source[start:end].split("[[levels.A0.questions]]")
        source = (
            source[:start]
            + "[[levels.A0.questions]]".join(section[:4])
            + source[end:]
        )
    elif failure == "object-count":
        source = source.replace("min_objects = 2", "min_objects = 3", 1)
    elif failure == "too-many-focus-objects":
        source = source.replace("focus_objects = 2", "focus_objects = 3", 1)
    elif failure == "unknown-criterion":
        source = source.replace(
            'criteria = ["name-matches-object"]',
            'criteria = ["not-a-criterion"]',
            1,
        )
    plan_path = tmp_path / "m01-plan.toml"
    plan_path.write_text(source, encoding="utf-8")
    monkeypatch.setattr(m01_multilingual, "M01_PLAN_PATH", plan_path)
    load_m01_level_plan.cache_clear()
    try:
        with pytest.raises(MissionContractError, match=message):
            load_m01_level_plan("A0")
    finally:
        load_m01_level_plan.cache_clear()



def test_preparation_cards_must_cover_every_assessed_object():
    contract = contract_input(level="A0")
    output = contract_output(contract)
    marker_question = next(
        question for question in output.questions if question.interaction == "markerChoice"
    )
    chair = contract.scene_facts.objects[2]
    marker_fact_ids = dict(marker_question.marker_fact_ids)
    marker_fact_ids[marker_question.options[1].option_id] = chair.fact_id
    changed = marker_question.model_copy(update={"marker_fact_ids": marker_fact_ids})
    invalid = output.model_copy(update={
        "questions": [
            changed if question.question_id == marker_question.question_id else question
            for question in output.questions
        ],
    })

    with pytest.raises(
        MissionContractError,
        match="preparation cards must teach every assessed object before assessment",
    ):
        validate_contract_output(contract, invalid)


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


def _generated_from_planned_output(contract, planned):
    return M01GeneratedLesson(
        explanation=planned.explanation,
        preparation=planned.preparation,
        questions=[
            GeneratedQuestion(
                question_id=question.question_id,
                target_ids=question.target_ids,
                prompt=question.prompt,
                prompt_translation=question.prompt_translation,
                instruction=question.instruction,
                interaction=question.interaction,
                options=question.options,
                marker_options=[
                    GeneratedMarkerOption(option_id=option_id, fact_id=object_fact)
                    for option_id, object_fact in (question.marker_fact_ids or {}).items()
                ],
                chunks=question.chunks,
                fact_ids=question.fact_ids,
                statement_fact_id=question.statement_fact_id,
                prompt_term_uses=question.prompt_term_uses,
                answer=planned.private.answers[question.question_id],
                feedback=question.feedback,
            )
            for question in planned.questions
        ],
    )


def test_generated_lesson_conversion_derives_private_evaluations():
    contract, planned, _ = planned_a0_output()
    first, second = contract.scene_facts.objects[:2]
    generated = _generated_from_planned_output(contract, planned)
    output = convert_generated_lesson(contract, generated)
    marker = output.questions[0]
    evaluation = output.private.evaluations[0]

    assert marker.marker_fact_ids == {
        f"marker-0-{index}": obj.fact_id
        for index, obj in enumerate(contract.scene_facts.objects[:3])
    }
    assert output.private.answers["match-0"].correct_option_id == "marker-0-0"
    assert evaluation.evidence_type == "recognition"
    assert evaluation.scene_object_id == first.scene_object_id
    assert "evaluations" not in M01GeneratedLesson.model_json_schema()["properties"]


@pytest.mark.parametrize(
    ("level", "builder", "title", "plan_sections", "task_sections"),
    [
        (
            "A0",
            planned_a0_output,
            "Name and identify",
            ["Task 1 · {label}"] * 3 + ["Task 2 · {label}"] * 3,
            ["Task 1 · Cup"] * 3 + ["Task 2 · Table"] * 3,
        ),
        (
            "A1",
            planned_a1_output,
            "Name it and describe it",
            [
                "Task 1 · Identify objects in your photo",
                "Task 1 · Identify objects in your photo",
                "Task 2 · Describe them",
                "Task 2 · Describe them",
            ],
            [
                "Task 1 · Identify objects in your photo",
                "Task 1 · Identify objects in your photo",
                "Task 2 · Describe them",
                "Task 2 · Describe them",
            ],
        ),
        (
            "A2",
            planned_a2_output,
            "Describe the scene",
            [
                "Task 1 · Notice the facts",
                "Task 1 · Notice the facts",
                "Task 2 · Describe the scene",
                "Task 2 · Describe the scene",
                "Task 3 · Check a detail",
            ],
            [
                "Task 1 · Notice the facts",
                "Task 1 · Notice the facts",
                "Task 2 · Describe the scene",
                "Task 2 · Describe the scene",
                "Task 3 · Check a detail",
            ],
        ),
    ],
)
def test_task_title_and_sections_come_from_level_plan(
    level, builder, title, plan_sections, task_sections
):
    contract, planned, plan = builder()
    assert plan.level == level
    assert plan.title == title
    assert [slot.section for slot in plan.questions] == plan_sections

    generated = _generated_from_planned_output(contract, planned)
    output = convert_generated_lesson(contract, generated)
    validate_contract_output(contract, output, plan)
    mission = get_mission("M01", level, plan.content_version)
    task = build_m01_multilingual_task(uuid4(), mission, contract, output)

    assert output.title == task.public_content.title == plan.title
    assert [question.section for question in task.public_content.questions] == task_sections


def test_generated_schema_rejects_server_planned_title_and_sections():
    contract, planned, _ = planned_a1_output()
    generated = _generated_from_planned_output(contract, planned)
    payload = generated.model_dump(mode="json", by_alias=True)

    assert "title" not in M01GeneratedLesson.model_json_schema()["properties"]
    assert "section" not in GeneratedQuestion.model_json_schema()["properties"]
    with pytest.raises(ValidationError):
        M01GeneratedLesson.model_validate({**payload, "title": "Model title"})

    payload["questions"][0]["section"] = "Model section"
    with pytest.raises(ValidationError):
        M01GeneratedLesson.model_validate(payload)


def test_generated_evidence_and_criteria_come_from_ordered_slots():
    contract, output, plan = planned_a1_output()
    generated = _generated_from_planned_output(contract, output)
    converted = convert_generated_lesson(contract, generated)
    evaluations = converted.private.evaluations

    assert [item.evidence_type for item in evaluations] == [
        slot.evidence for slot in plan.questions
    ]
    assert [item.rubric_criterion_ids for item in evaluations] == [
        slot.criteria for slot in plan.questions
    ]
    assert "production" not in {item.evidence_type for item in evaluations}


def test_m01_cache_identity_covers_payload_and_version_dimensions():
    cache = ResultCache()
    scope = CacheScope.public()
    contract = contract_input().model_dump(mode="json", by_alias=True)
    payload = {
        "contract": contract,
        "planVersion": 5,
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
    changed["planVersion"] = 6
    variations.append(key(changed))

    assert all(candidate != original for candidate in variations)
    assert len(variations) == len(set(variations))


def test_multilingual_task_keeps_answer_key_private():
    contract = contract_input()
    output = contract_output(contract)
    mission = get_mission("M01", "A1", 1)
    task = build_m01_multilingual_task(uuid4(), mission, contract, output)
    public_content = task.public_content.model_dump_json(by_alias=True)

    assert task.kind == "grammarLesson"
    assert "correctOptionIds" not in public_content
    assert "missionState" not in public_content


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
        SimpleNamespace(id=uuid4(), label="table", attributes={"color": "red"}),
    ]
    assert m01_scene_fact_eligibility(plan, objects).eligible

    contract = contract_input()
    assert not m01_multilingual_eligibility(plan, contract).eligible
    second_object = contract.scene_facts.objects[1]
    attribute = contract.scene_facts.attributes[0]
    second_attribute = contract.scene_facts.attributes[1]
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
        ApprovedTerm(
            term_id="second-colour-term",
            fact_id=second_attribute.fact_id,
            source_text="red",
            target_text="roja",
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
        lesson_spec(SimpleNamespace(mission_id="M04", practice_level="B1"))


def test_fact_id_helpers_are_stable():
    object_uuid = uuid4()
    assert fact_id("object", object_uuid) == f"object:{object_uuid}"
    assert fact_id("attribute", object_uuid, "colour") == f"attribute:{object_uuid}:colour"
    assert fact_id("relation", "object:a", "on", "object:b") == (
        "relation:object:a:on:object:b"
    )
    assert fact_id("count", "cup") == "count:cup"


def test_a2_connected_fact_threshold_and_followup_order_and_subset():
    contract, output, plan = planned_a2_output()
    validate_contract_output(contract, output, plan)
    first = contract.scene_facts.objects[0]
    connect, followup = output.questions[3:5]

    with pytest.raises(MissionContractError, match="more distinct scene facts"):
        questions = list(output.questions)
        questions[3] = connect.model_copy(update={"fact_ids": [first.fact_id]})
        validate_contract_output(
            contract, output.model_copy(update={"questions": questions}), plan
        )

    with pytest.raises(
        MissionContractError,
        match=r"question 4 \(scene-follow-up, slot buildSceneDescription\): targets",
    ):
        questions = [
            *output.questions[:3],
            followup,
            connect,
        ]
        validate_contract_output(
            contract, output.model_copy(update={"questions": questions}), plan
        )

    with pytest.raises(MissionContractError, match="preceding connect question"):
        questions = list(output.questions)
        questions[3] = connect.model_copy(update={
            "fact_ids": [
                first.fact_id,
                contract.scene_facts.objects[1].fact_id,
                contract.scene_facts.relations[0].fact_id,
            ],
        })
        validate_contract_output(
            contract, output.model_copy(update={"questions": questions}), plan
        )
