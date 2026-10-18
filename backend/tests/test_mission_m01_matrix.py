"""Structural M01 fixed-scene coverage; lesson text is placeholder content."""

from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

import app.languages as language_registry
from app.languages import learnable_languages
from app.missions.m01_multilingual import (
    CONTRACT_VERSION,
    MissionContractError,
    convert_generated_lesson,
    default_join,
    fact_id,
    join_chunks,
    load_m01_level_plan,
    validate_contract_input,
    validate_contract_output,
)
from app.repositories.postgres.workflow import _lesson_answer_is_correct
from app.schemas.mission_m01_contract import (
    Answer,
    ApprovedTerm,
    ConfirmedAttribute,
    ConfirmedObject,
    ConfirmedRelation,
    ConfirmedSceneFacts,
    Feedback,
    GeneratedMarkerOption,
    GeneratedQuestion,
    LearnerContext,
    M01ContractInput,
    M01GeneratedLesson,
    MissionRef,
    PreparationCard,
    SentenceChunk,
)
from app.schemas.tasks import VocabularyChoice
from app.services.mission_eligibility import m01_multilingual_eligibility
from app.services.mission_lessons_m01_multilingual import build_m01_multilingual_task

REGISTERED = tuple(language_registry.languages())
LANGUAGE_CODES = tuple(
    language.code for language in learnable_languages()
) + ("qaa", "qab")
OBJECT_IDS = {
    name: UUID(int=index)
    for index, name in enumerate(("cup", "table", "book"), start=1)
}
OBJECT_TEXT = {"cup": "cup", "table": "table", "book": "book"}
DETAIL_TEXT = {"blue": "blue", "red": "red", "on": "on"}


@pytest.fixture
def synthetic_registry(monkeypatch):
    aliases = (
        SimpleNamespace(
            code="qaa", english_name="Synthetic One", native_name="Synthetic One",
            script="Hani", direction="ltr", word_separator="none",
            learnable=True, instruction=False,
        ),
        SimpleNamespace(
            code="qab", english_name="Synthetic Two", native_name="Synthetic Two",
            script="Arab", direction="rtl", word_separator="space",
            learnable=True, instruction=False,
        ),
    )
    monkeypatch.setattr(language_registry, "_load_languages", lambda: (*REGISTERED, *aliases))


def _scene(name):
    scenes = {
        "S1": (("cup", "table"), (), ()),
        "S2": (
            ("cup", "book"),
            (("cup", "blue"), ("book", "red")),
            (),
        ),
        "S3": (
            ("cup", "table", "book"),
            (("cup", "blue"),),
            (("cup", "on", "table"),),
        ),
        "S4": (("cup",), (), ()),
        "S5": (
            ("cup", "table"),
            (),
            (("cup", "on", "table"),),
        ),
    }
    return scenes[name]


def _contract(language, level, scene):
    names, attributes, relations = _scene(scene)
    objects = [
        ConfirmedObject(
            fact_id=fact_id("object", OBJECT_IDS[name]),
            scene_object_id=OBJECT_IDS[name],
            label=name,
            marker=("cup", "table", "book").index(name) + 1,
        )
        for name in names
    ]
    object_facts = {item.label: item.fact_id for item in objects}
    confirmed_attributes = [
        ConfirmedAttribute(
            fact_id=fact_id("attribute", OBJECT_IDS[object_name], "colour"),
            object_fact_id=object_facts[object_name],
            kind="colour",
            value=value,
        )
        for object_name, value in attributes
    ]
    confirmed_relations = [
        ConfirmedRelation(
            fact_id=fact_id(
                "relation",
                object_facts[subject],
                relation,
                object_facts[reference],
            ),
            subject_fact_id=object_facts[subject],
            reference_fact_id=object_facts[reference],
            relation=relation,
        )
        for subject, relation, reference in relations
    ]
    terms = [
        ApprovedTerm(
            term_id=f"term-{name}",
            fact_id=object_facts[name],
            source_text=name,
            target_text=OBJECT_TEXT[name],
            part_of_speech="noun",
            provenance="sessionTranslation",
        )
        for name in names
    ]
    terms.extend(
        ApprovedTerm(
            term_id=f"term-{object_name}-{value}",
            fact_id=fact_id("attribute", OBJECT_IDS[object_name], "colour"),
            source_text=value,
            target_text=DETAIL_TEXT[value],
            part_of_speech="adjective",
            provenance="sessionTranslation",
        )
        for object_name, value in attributes
    )
    terms.extend(
        ApprovedTerm(
            term_id=f"term-{subject}-{relation}-{reference}",
            fact_id=fact_id(
                "relation",
                object_facts[subject],
                relation,
                object_facts[reference],
            ),
            source_text=relation,
            target_text=DETAIL_TEXT[relation],
            part_of_speech="preposition",
            provenance="sessionTranslation",
        )
        for subject, relation, reference in relations
    )
    return M01ContractInput(
        contract_version=CONTRACT_VERSION,
        mission=MissionRef(
            mission_id="M01",
            practice_level=level,
            content_version=1,
        ),
        target_language=language,
        instruction_language="en",
        scene_facts=ConfirmedSceneFacts(
            objects=objects,
            attributes=confirmed_attributes,
            relations=confirmed_relations,
            counted_groups=[],
        ),
        vocabulary=terms,
        learner=LearnerContext(proficiency_level=level),
    )


def _question(contract, question_id, target_id, interaction, fact_ids, answer_terms):
    term_by_fact = {term.fact_id: term.target_text for term in contract.vocabulary}
    question_id = question_id
    options = []
    marker_options = []
    chunks = []
    if interaction in {"multipleChoice", "markerChoice"}:
        correct_id = f"{question_id}-correct"
        distractor_id = f"{question_id}-other"
        correct_text = " ".join(answer_terms)
        distractor_text = next(
            (
                term_by_fact[item.fact_id]
                for item in contract.scene_facts.objects[1:]
                if item.fact_id not in fact_ids
            ),
            None,
        )
        if distractor_text is None:
            distractor_text = " ".join(
                term for term in answer_terms if term != answer_terms[-1]
            ) or "other"
        options = [
            VocabularyChoice(option_id=correct_id, label=correct_text),
            VocabularyChoice(option_id=distractor_id, label=distractor_text),
        ]
        if interaction == "markerChoice":
            object_by_label = {
                item.label: item.fact_id for item in contract.scene_facts.objects
            }
            correct_fact = next(
                item for item in fact_ids if item in object_by_label.values()
            )
            distractor_fact = next(
                item for item in object_by_label.values() if item != correct_fact
            )
            marker_options = [
                GeneratedMarkerOption(option_id=correct_id, fact_id=correct_fact),
                GeneratedMarkerOption(option_id=distractor_id, fact_id=distractor_fact),
            ]
        answer = Answer(correct_option_id=correct_id)
    else:
        for index, text in enumerate([*answer_terms, "."]):
            language = language_registry.get_language(contract.target_language)
            chunks.append(SentenceChunk(
                chunk_id=f"{question_id}-chunk-{index}",
                text=text,
                join=default_join(language, text),
            ))
        answer = Answer(chunk_ids=[item.chunk_id for item in chunks])
    return GeneratedQuestion(
        question_id=question_id,
        target_ids=[target_id],
        prompt="Choose or build an answer from the confirmed scene.",
        interaction=interaction,
        options=options,
        marker_options=marker_options,
        chunks=chunks,
        fact_ids=fact_ids,
        answer=answer,
        feedback=Feedback(correct="Correct.", corrections=[]),
    )


def _generated_lesson(contract):
    level = contract.mission.practice_level
    object_facts = {item.label: item.fact_id for item in contract.scene_facts.objects}
    term_text = {term.fact_id: term.target_text for term in contract.vocabulary}
    cup = term_text[object_facts["cup"]]
    table = term_text[object_facts["table"]] if "table" in object_facts else None
    detail = next(
        (
            item for item in contract.scene_facts.attributes
            if item.object_fact_id == object_facts["cup"]
        ),
        None,
    )
    relation = contract.scene_facts.relations[0] if contract.scene_facts.relations else None
    questions = []
    if level == "A0":
        questions.extend([
            _question(contract, "marker", "recognise-name", "markerChoice",
                      [object_facts["cup"]], [cup]),
            _question(contract, "recognise", "recognise-name", "multipleChoice",
                      [object_facts["cup"]], [cup]),
            _question(contract, "identify-build", "identify-object", "sentenceBuilding",
                      [object_facts["cup"]], [cup]),
            _question(contract, "identify-choice", "identify-object", "multipleChoice",
                      [object_facts["cup"]], [cup]),
        ])
    elif level == "A1":
        detail_target = "describe-colour" if detail else "describe-location"
        detail_facts = (
            [object_facts["cup"], detail.fact_id] if detail else
            [object_facts["cup"], object_facts["table"], relation.fact_id]
        )
        detail_terms = (
            [cup, term_text[detail.fact_id]] if detail else
            [cup, term_text[relation.fact_id], table]
        )
        questions.extend([
            _question(contract, "marker", "identify-object", "markerChoice",
                      [object_facts["cup"]], [cup]),
            _question(contract, "name", "name-object", "multipleChoice",
                      [object_facts["cup"]], [cup]),
            _question(contract, "detail-build", detail_target, "sentenceBuilding",
                      detail_facts, detail_terms),
            _question(contract, "detail-choice", detail_target, "multipleChoice",
                      detail_facts, detail_terms),
        ])
    else:
        if detail is None or relation is None or table is None:
            raise AssertionError("A2 matrix generation requires the connected scene.")
        connected_facts = [
            object_facts["cup"], detail.fact_id, relation.reference_fact_id,
            relation.fact_id,
        ]
        blue = term_text[detail.fact_id]
        relation_text = term_text[relation.fact_id]
        questions.extend([
            _question(contract, "marker", "identify-scene-object", "markerChoice",
                      [object_facts["cup"]], [cup]),
            _question(contract, "describe", "describe-scene-facts", "sentenceBuilding",
                      [object_facts["cup"], detail.fact_id], [cup, blue]),
            _question(contract, "connect", "connect-scene-facts", "sentenceBuilding",
                      connected_facts, [cup, blue, relation_text, table]),
            _question(contract, "follow-up", "follow-up-scene-fact", "multipleChoice",
                      [detail.fact_id], [blue]),
            _question(contract, "describe-choice", "describe-scene-facts", "multipleChoice",
                      [object_facts["cup"], detail.fact_id], [cup, blue]),
        ])

    object_names = list(object_facts)
    preparation = [
        PreparationCard(
            card_id=f"prep-{name}",
            text=term_text[object_facts[name]],
            translation=f"the {name}",
            fact_ids=[object_facts[name]],
        )
        for name in object_names[:2]
    ]
    return M01GeneratedLesson(
        title="Fixed-scene practice",
        explanation=None,
        preparation=preparation,
        questions=questions,
    )


@pytest.mark.parametrize("language", LANGUAGE_CODES)
def test_fixed_scene_matrix(language, synthetic_registry):
    expected = {
        "S1": {"A0"},
        "S2": {"A0", "A1"},
        "S3": {"A0", "A1", "A2"},
        "S4": set(),
        "S5": {"A0", "A1"},
    }
    for scene, levels in expected.items():
        for level in ("A0", "A1", "A2"):
            contract = _contract(language, level, scene)
            plan = load_m01_level_plan(level)
            eligibility = m01_multilingual_eligibility(plan, contract)
            assert eligibility.eligible is (level in levels), (language, scene, level)
            if not eligibility.eligible:
                continue

            definition = validate_contract_input(contract)
            generated = _generated_lesson(contract)
            output = convert_generated_lesson(contract, generated)
            validate_contract_output(contract, output, plan)
            assert len(output.questions) == plan.min_questions
            task = build_m01_multilingual_task(uuid4(), definition, contract, output)

            assert any(question.interaction == "markerChoice" for question in output.questions)
            assert any(question.interaction == "sentenceBuilding" for question in output.questions)
            assert all(
                evaluation.evidence_type != "production"
                for evaluation in task.answer_key.question_evaluations
            )
            marker_question = next(
                question for question in task.public_content.questions
                if question.question_id == "marker"
            )
            generated_marker_question = next(
                question for question in generated.questions
                if question.question_id == "marker"
            )
            markers_by_fact = {
                item.fact_id: item.marker for item in contract.scene_facts.objects
            }
            expected_marker_labels = {
                str(markers_by_fact[item.fact_id])
                for item in generated_marker_question.marker_options
            }
            assert (
                {option.label for option in marker_question.options}
                == expected_marker_labels
            )

            sentence = next(
                question for question in task.public_content.questions
                if question.interaction_type == "sentenceBuilding"
            )
            answer_ids = task.answer_key.correct_option_ids[sentence.question_id].split(",")
            chunks = {chunk.chunk_id: chunk for chunk in sentence.chunks}
            correct_text = join_chunks([chunks[item] for item in answer_ids])
            assert all(
                chunk.join == "none" for chunk in sentence.chunks if chunk.text == "."
            )
            assert _lesson_answer_is_correct(task, sentence.question_id, ",".join(answer_ids))
            assert not _lesson_answer_is_correct(
                task, sentence.question_id, ",".join(reversed(answer_ids))
            )
            assert not _lesson_answer_is_correct(
                task, sentence.question_id, ",".join([*answer_ids, "unknown-chunk"])
            )
            assert not _lesson_answer_is_correct(
                task, sentence.question_id, ",".join([*answer_ids, answer_ids[0]])
            )
            if language == "qaa":
                assert " " not in correct_text
                assert all(chunk.join == "none" for chunk in sentence.chunks)
            if language == "qab":
                assert task.public_content.text_direction == "rtl"
            for question in task.public_content.questions:
                if question.interaction_type == "multipleChoice":
                    expected_option = task.answer_key.correct_option_ids[question.question_id]
                    wrong_option = next(
                        option.option_id for option in question.options
                        if option.option_id != expected_option
                    )
                    assert _lesson_answer_is_correct(task, question.question_id, expected_option)
                    assert not _lesson_answer_is_correct(task, question.question_id, wrong_option)


def test_missing_approved_translation_for_the_only_detail_makes_a1_ineligible(
    synthetic_registry,
):
    contract = _contract("es", "A1", "S5")
    relation_fact = contract.scene_facts.relations[0].fact_id
    contract = contract.model_copy(update={
        "vocabulary": [term for term in contract.vocabulary if term.fact_id != relation_fact],
    })
    result = m01_multilingual_eligibility(load_m01_level_plan("A1"), contract)
    assert not result.eligible
    assert "At least 1 approved detail terms are required." in result.reasons
    assert {item.label for item in contract.scene_facts.objects} == {"cup", "table"}
    assert contract.scene_facts.attributes == []
    assert len(contract.scene_facts.relations) == 1


@pytest.mark.parametrize("removed_fact_id", [
    fact_id("object", OBJECT_IDS["book"]),
    fact_id("attribute", OBJECT_IDS["cup"], "colour"),
])
def test_s5_output_cannot_reference_removed_facts(synthetic_registry, removed_fact_id):
    contract = _contract("es", "A1", "S5")
    plan = load_m01_level_plan("A1")
    output = convert_generated_lesson(contract, _generated_lesson(contract))
    question = output.questions[0].model_copy(update={
        "fact_ids": [*output.questions[0].fact_ids, removed_fact_id],
    })
    invalid = output.model_copy(update={
        "questions": [question, *output.questions[1:]],
    })

    with pytest.raises(MissionContractError):
        validate_contract_output(contract, invalid, plan)
