"""Build the multilingual M01 contract from learner-confirmed session data."""

from __future__ import annotations

import random
from hashlib import sha256
from uuid import uuid5

from app.languages import get_language
from app.missions import get_mission
from app.missions.m01_multilingual import CONTRACT_VERSION, MissionContractError, fact_id
from app.schemas.mission_m01_contract import (
    ApprovedTerm,
    ConfirmedAttribute,
    ConfirmedCount,
    ConfirmedObject,
    ConfirmedRelation,
    ConfirmedSceneFacts,
    LearnerContext,
    M01ContractInput,
    M01ContractOutput,
    MissionRef,
)
from app.schemas.tasks import SessionTask
from app.services.mission_eligibility import confirmed_attributes, relation_type
from app.services.mission_lessons import mission_fields, mission_version


def _term_id(fact: str) -> str:
    return f"term-{sha256(fact.encode()).hexdigest()[:24]}"


def build_m01_contract_input(
    mission,
    profile,
    objects,
    relations,
    words,
    translated_scene,
    counted_groups,
    progress,
    *,
    supplemental_vocabulary=None,
    review_markers=None,
) -> M01ContractInput:
    supplemental_vocabulary = supplemental_vocabulary or {}
    review_markers = review_markers or {}
    object_terms = {
        item.key: item for item in (translated_scene.objects if translated_scene else [])
    }
    attribute_terms = {
        item.key: item for item in (translated_scene.attributes if translated_scene else [])
    }
    relation_terms = {
        item.key: item for item in (translated_scene.relationships if translated_scene else [])
    }
    word_by_object = {
        obj.id: word for obj, word in zip(objects, words, strict=True)
    }

    confirmed_objects = []
    confirmed_attributes_list = []
    confirmed_relations_list = []
    vocabulary = []
    included_object_facts = set()

    for obj in objects:
        translated = object_terms.get(str(obj.id))
        word = word_by_object.get(obj.id)
        if translated is None or word is None:
            continue
        object_fact = fact_id("object", obj.id)
        confirmed_objects.append(ConfirmedObject(
            fact_id=object_fact,
            scene_object_id=obj.id,
            label=obj.label,
            marker=review_markers.get(str(obj.id)),
        ))
        included_object_facts.add(obj.id)
        vocabulary.append(ApprovedTerm(
            term_id=_term_id(object_fact),
            fact_id=object_fact,
            source_text=translated.source,
            target_text=translated.translation,
            part_of_speech=word.part_of_speech,
            vocabulary_item_id=word.id,
            provenance="sessionTranslation",
            romanization=translated.phonetic_text,
        ))

        for source_key, kind, value in confirmed_attributes(obj):
            translated_attribute = attribute_terms.get(f"{obj.id}:{source_key}")
            supplemental = supplemental_vocabulary.get(
                ("attribute", f"{obj.id}:{source_key}")
            )
            if (
                translated_attribute is None
                or supplemental is None
                or obj.id not in included_object_facts
            ):
                continue
            attribute_fact = fact_id("attribute", obj.id, kind)
            confirmed_attributes_list.append(ConfirmedAttribute(
                fact_id=attribute_fact,
                object_fact_id=object_fact,
                kind=kind,
                value=value,
            ))
            vocabulary.append(ApprovedTerm(
                term_id=_term_id(attribute_fact),
                fact_id=attribute_fact,
                source_text=translated_attribute.source,
                target_text=translated_attribute.translation,
                part_of_speech=supplemental.part_of_speech,
                vocabulary_item_id=supplemental.id,
                provenance="sessionTranslation",
                romanization=translated_attribute.phonetic_text,
            ))

    included_by_id = {obj.id: obj for obj in objects if obj.id in included_object_facts}
    for relation in relations:
        if (
            relation.subject_scene_object_id not in included_by_id
            or relation.reference_scene_object_id not in included_by_id
        ):
            continue
        relation_key = str(relation.id)
        translated = relation_terms.get(relation_key)
        supplemental = supplemental_vocabulary.get(("relationship", relation_key))
        if translated is None or supplemental is None:
            continue
        if (
            included_by_id[relation.subject_scene_object_id].label.strip().casefold()
            == included_by_id[relation.reference_scene_object_id].label.strip().casefold()
        ):
            continue
        subject_fact = fact_id("object", relation.subject_scene_object_id)
        reference_fact = fact_id("object", relation.reference_scene_object_id)
        relation_name = relation_type(relation)
        relation_fact = fact_id("relation", subject_fact, relation_name, reference_fact)
        confirmed_relations_list.append(ConfirmedRelation(
            fact_id=relation_fact,
            subject_fact_id=subject_fact,
            reference_fact_id=reference_fact,
            relation=relation_name,
        ))
        vocabulary.append(ApprovedTerm(
            term_id=_term_id(relation_fact),
            fact_id=relation_fact,
            source_text=translated.source,
            target_text=translated.translation,
            part_of_speech=supplemental.part_of_speech,
            vocabulary_item_id=supplemental.id,
            provenance="sessionTranslation",
            romanization=translated.phonetic_text,
        ))

    learner_data = progress if isinstance(progress, dict) else {}
    familiarity = {}
    for source, prefix in (("objects", "object"), ("terms", "term")):
        values = learner_data.get(source)
        if not isinstance(values, dict):
            continue
        for key, value in values.items():
            try:
                score = float(value)
            except (TypeError, ValueError):
                continue
            if isinstance(key, str) and 0 <= score <= 1:
                familiarity[f"{prefix}:{key}"] = score
            if len(familiarity) == 20:
                break
        if len(familiarity) == 20:
            break
    history_words = learner_data.get("history_words")
    if isinstance(history_words, list):
        for item in history_words[:20]:
            if len(familiarity) == 20:
                break
            if not isinstance(item, dict):
                continue
            term = item.get("term")
            correct = item.get("correctCount", 0)
            incorrect = item.get("incorrectCount", 0)
            try:
                total = correct + incorrect
                score = correct / total
            except (TypeError, ZeroDivisionError):
                continue
            if isinstance(term, str) and total > 0 and 0 <= score <= 1:
                familiarity[f"history:{term}"] = score

    learner = LearnerContext(
        proficiency_level=mission.practice_level,
        term_familiarity=familiarity,
        recent_mission_ids=[],
        plurals_taught=bool(learner_data.get("plurals_taught", False)),
    )

    included_fact_ids = {item.fact_id for item in confirmed_objects}
    counted_facts = []
    for group in counted_groups or ():
        group_objects = (
            group.get("sceneObjectIds", group.get("scene_object_ids", []))
            if isinstance(group, dict) else group.scene_object_ids
        )
        object_fact_ids = [
            fact_id("object", object_id)
            for object_id in group_objects
            if fact_id("object", object_id) in included_fact_ids
        ]
        if not object_fact_ids:
            continue
        count_fact = fact_id("count", ",".join(sorted(object_fact_ids)))
        counted_facts.append(ConfirmedCount(
            fact_id=count_fact,
            object_fact_ids=object_fact_ids,
            quantity=(
                group.get("quantity") if isinstance(group, dict) else group.quantity
            ),
        ))

    definition = get_mission("M01", mission.practice_level, mission.content_version)
    target_language = get_language(profile["target_language_code"])
    reviewed_examples = [
        example
        for pattern in (definition.language_patterns if definition else [])
        for example in pattern.examples.get(target_language.code, [])
    ] if target_language else []

    return M01ContractInput(
        contract_version=CONTRACT_VERSION,
        mission=MissionRef(
            mission_id="M01",
            practice_level=mission.practice_level,
            content_version=mission.content_version,
        ),
        target_language=profile["target_language_code"],
        instruction_language=profile["source_language_code"],
        scene_facts=ConfirmedSceneFacts(
            objects=confirmed_objects,
            attributes=confirmed_attributes_list,
            relations=confirmed_relations_list,
            counted_groups=counted_facts,
        ),
        vocabulary=vocabulary,
        reviewed_examples=reviewed_examples,
        learner=learner,
    )


def m01_contract_has_learner_context(contract: M01ContractInput) -> bool:
    learner = contract.learner
    return bool(
        learner.term_familiarity or learner.recent_mission_ids or learner.plurals_taught
    )


def build_m01_multilingual_task(
    session_id,
    mission,
    contract: M01ContractInput,
    output: M01ContractOutput,
) -> SessionTask:
    task_id = uuid5(session_id, f"mission:{mission_version(mission)}:lesson")
    objects = {
        item.fact_id: item.scene_object_id for item in contract.scene_facts.objects
    }
    object_facts = {item.fact_id: item for item in contract.scene_facts.objects}
    first_object = next(iter(contract.scene_facts.objects), None)
    correct_answers = {}
    questions = []
    for question in output.questions:
        answer = output.private.answers[question.question_id]
        if question.interaction == "sentenceBuilding":
            correct_answers[question.question_id] = ",".join(answer.chunk_ids)
        else:
            correct_answers[question.question_id] = answer.correct_option_id
        marker_objects = None
        options = question.options
        if question.interaction == "markerChoice":
            marker_facts = question.marker_fact_ids or {}
            marker_objects = {
                option_id: objects[fact]
                for option_id, fact in marker_facts.items()
            }
            options = []
            for option in question.options:
                object_fact = object_facts[marker_facts[option.option_id]]
                if object_fact.marker is None:
                    raise MissionContractError(
                        "marker choice objects must have review markers"
                    )
                options.append(option.model_copy(update={"label": str(object_fact.marker)}))
        shown_chunks = list(question.chunks)
        if shown_chunks:
            random.Random(f"{task_id}:{question.question_id}").shuffle(shown_chunks)
        questions.append({
            "question_id": question.question_id,
            "prompt": question.prompt,
            "interaction_type": (
                "sentenceBuilding"
                if question.interaction == "sentenceBuilding" else "multipleChoice"
            ),
            "options": options,
            "token_bank": [],
            "chunks": shown_chunks or None,
            "hint_count": len(question.hints),
            "prompt_translation": question.prompt_translation,
            "instruction": question.instruction,
            "section": question.section,
            "scene_object_id": next(
                (objects[item] for item in question.fact_ids if item in objects),
                None,
            ),
            "marker_object_ids": marker_objects,
            "keep_option_order": True,
        })

    language = get_language(contract.target_language)
    if language is None:
        raise ValueError("M01 contract target language is not registered")
    hints = {
        question.question_id: [
            hint.model_dump(mode="json", by_alias=True) for hint in question.hints
        ]
        for question in output.questions
    }
    preparation = []
    for card in output.preparation:
        preparation.append({
            "text": card.text,
            "translation": card.translation,
            "scene_object_id": next(
                (objects[item] for item in card.fact_ids if item in objects),
                None,
            ),
        })
    examples = [
        {
            "example_id": example.example_id,
            "chunks": example.chunks,
            "translation": example.translation,
            "note": example.note,
        }
        for example in output.worked_examples
    ]
    return SessionTask(
        id=task_id,
        session_id=session_id,
        phase="learning",
        kind="grammarLesson",
        order_index=0,
        public_content={
            "kind": "grammarLesson",
            "focus": output.objective_id,
            "title": output.title,
            "explanation": output.explanation,
            "prep": preparation,
            "questions": questions,
            "check_each_question": True,
            "target_language": language.code,
            "text_direction": language.direction,
            "contract_version": CONTRACT_VERSION,
            "worked_examples": examples,
            **mission_fields(mission),
        },
        answer_key={
            "correct_option_ids": correct_answers,
            "question_evaluations": output.private.evaluations,
            "mission_state": {
                "contractVersion": CONTRACT_VERSION,
                "hints": hints,
            },
        },
        scene_object_id=first_object.scene_object_id if first_object else None,
    )
