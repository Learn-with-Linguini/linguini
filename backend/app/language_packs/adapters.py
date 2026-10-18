"""Adapt accepted language-pack sentences to existing M01 lesson contracts."""

from __future__ import annotations

import random
from types import SimpleNamespace
from uuid import NAMESPACE_URL, uuid5

from app.ai.features.learning_tasks.mission import fold, tokens
from app.ai.features.learning_tasks.mission_a0 import (
    SLOT,
    A0LessonResult,
    _build_question,
    _choice_question,
    _marker_question,
    _sections,
    validate_a0_lesson,
)
from app.ai.features.learning_tasks.mission_a0 import _other as _a0_other
from app.ai.features.learning_tasks.mission_a2 import (
    MissionA2Question,
    MissionA2Result,
    validate_a2_lesson,
)
from app.ai.features.learning_tasks.mission_m01 import (
    CONFIRM_IDS,
    DESCRIBE_SECTION,
    IDENTIFY_SECTION,
    M01LessonResult,
    M01Question,
    confirm_answers,
    validate_m01_lesson,
)
from app.missions import get_mission
from app.services import a0_lexicon as _a0_lexicon
from app.services.mission_eligibility import agreed_attribute, attribute_contrasts
from app.services.mission_facts_a2 import approved_facts as _approved_facts
from app.services.mission_lessons_a0 import a0_lesson_task
from app.services.mission_lessons_a2 import (
    _english_fact,
    _sentence_chunks,
    m01_a2_task,
)
from app.services.mission_lessons_m01 import SIMILAR_COLOURS, m01_lesson_task

from .capabilities import LessonPlan
from .generation import ApprovedSentence, ApprovedVocabulary, BoundSceneFacts
from .schema import LanguagePack

_SESSION_ID = uuid5(NAMESPACE_URL, "language-packs/es-m01-preview")


def _accepted_by_slot(accepted: list[ApprovedSentence]) -> dict[str, list[ApprovedSentence]]:
    result: dict[str, list[ApprovedSentence]] = {}
    for sentence in accepted:
        result.setdefault(sentence.candidate.slot_id, []).append(sentence)
    return result


def _objects(facts: BoundSceneFacts, vocabulary: ApprovedVocabulary) -> tuple[list[dict], dict]:
    terms = {term.fact_id: term for term in vocabulary.terms}
    objects = []
    by_fact = {}
    for obj in facts.scene_facts.objects:
        term = terms.get(obj.fact_id)
        if term is None:
            continue
        object_id = str(obj.scene_object_id)
        gender = term.agreement
        article = term.forms_by_key.get("article_indefinite")
        definite = term.forms_by_key.get("definite")
        bare = term.forms_by_key.get("bare")
        if not all((gender, article, definite, bare)):
            continue
        row = {
            "key": object_id,
            "fact_id": obj.fact_id,
            "source": obj.label,
            "label": obj.label,
            "marker": obj.marker,
            "gender": gender,
            "noun": bare,
            "name": definite,
            "chunk": definite,
            "nounPhrase": f"{article} {bare}",
            "identify": "",
            "isIt": "",
            "vocabularyItemId": str(
                term.vocabulary_item_id or uuid5(NAMESPACE_URL, term.term_id)
            ),
        }
        objects.append(row)
        by_fact[obj.fact_id] = row
    return objects, by_fact


def _candidate_text(sentence: ApprovedSentence) -> str:
    return sentence.candidate.text


def _label(pack: LanguagePack, semantic: str):
    return next(label for label in pack.labels if label.semantic == semantic)


def _mission(level: str):
    mission = get_mission("M01", level, 1)
    if mission is None:
        raise ValueError(f"existing mission definition M01-{level}.v1 is unavailable")
    return mission


def _a0(
    pack: LanguagePack,
    facts: BoundSceneFacts,
    vocabulary: ApprovedVocabulary,
    plan: LessonPlan,
    accepted: list[ApprovedSentence],
    builder_selection: dict | None = None,
):
    rows, by_fact = _objects(facts, vocabulary)
    slots = _accepted_by_slot(accepted)
    focus_keys = (
        builder_selection.get("focus")
        if builder_selection is not None
        else None
    )
    focus = (
        [next(row for row in rows if row["key"] == key) for key in focus_keys]
        if focus_keys is not None
        else [
            by_fact[fact]
            for fact in (
                plan.slots[0].specs[0].bindings.get("object"),
                plan.slots[3].specs[0].bindings.get("object"),
            )
            if fact in by_fact
        ]
    )
    if len(focus) != 2:
        raise ValueError("A0 needs two distinct bound objects")
    if builder_selection is not None:
        markers = builder_selection.get("markers", {})
        for row in rows:
            if row["key"] in markers:
                row["marker"] = markers[row["key"]]
    yes_label = _label(pack, "yes-answer")
    no_label = _label(pack, "no-answer")
    what_is_this = _label(pack, "what-is-this")
    payload = {
        "targetLanguage": pack.language.code,
        "missionId": "M01",
        "seed": (
            builder_selection.get("seed", "es-m01")
            if builder_selection is not None else "es-m01"
        ),
        "focus": [row["key"] for row in focus],
        "yesNo": [yes_label.text, no_label.text],
        "approvedTranslations": {what_is_this.text: what_is_this.meaning},
        "approvedSentenceChunks": [],
        "approvedArticlesOrEndings": [],
        "approvedNumberWords": {},
        "approvedObjects": rows,
        "whatIsThis": what_is_this.text,
    }
    payload["approvedSentenceChunks"].append(payload["whatIsThis"])
    for row in rows:
        noun = _a0_lexicon.reviewed_noun(row["source"], pack.language.code)
        if noun is None:
            continue
        english = row["source"]
        english_indefinite = (
            f"an {english}" if english[:1].casefold() in "aeiou"
            else f"a {english}"
        )
        name = _a0_lexicon.name_chunk(pack.language.code, noun)
        identify = _a0_lexicon.identify_sentence(pack.language.code, noun)
        is_it = _a0_lexicon.is_it_question(pack.language.code, noun)
        find = _a0_lexicon.find_prompt(pack.language.code, noun)
        chunk = _a0_lexicon.chunk(pack.language.code, noun)
        slot_template = _a0_lexicon.join(pack.language.code, SLOT, noun.noun)
        payload["approvedSentenceChunks"].extend((
            name, identify, is_it, find, chunk, slot_template,
        ))
        payload["approvedTranslations"].update({
            name: f"the {english}",
            identify: f"This is {english_indefinite}.",
            is_it: f"Is this {english_indefinite}?",
            find: f"Find the {english}.",
            chunk: f"the {english}",
            slot_template: f"the {english}",
        })
    for row, index in zip(focus, (1, 2), strict=True):
        name_sentence = slots[f"matchName-{index}"][0]
        question_sentence = slots[f"confirmName-{index}"][0]
        answer_sentence = slots[f"buildIdentify-{index}"][0]
        row["name"] = _candidate_text(name_sentence)
        confirm_slot = next(
            slot for slot in plan.slots if slot.slot_id == f"confirmName-{index}"
        )
        named_fact = confirm_slot.specs[0].bindings.get("object")
        if named_fact not in by_fact:
            raise ValueError(f"A0 question {index} names an unknown object")
        row["isIt"] = _candidate_text(question_sentence)
        row["identify"] = _candidate_text(answer_sentence)
        payload["approvedTranslations"].update({
            row["name"]: name_sentence.candidate.translation or row["source"],
            row["isIt"]: question_sentence.candidate.translation or "",
            row["identify"]: answer_sentence.candidate.translation or "",
        })
        payload["approvedSentenceChunks"].extend(
            [row["name"], row["isIt"], row["identify"]]
        )
    payload["approvedSentenceChunks"] = list(dict.fromkeys([
        *payload["approvedSentenceChunks"],
        *payload["approvedTranslations"],
        *(row["chunk"] for row in rows),
    ]))
    section_targets = _sections(payload)
    truths = (
        builder_selection.get("layout", {}).get("statementCorrect")
        if builder_selection is not None else None
    ) or [
        plan.slots[1].specs[0].truth,
        plan.slots[4].specs[0].truth,
    ]
    questions = []
    yes, no = payload["yesNo"]
    for index, ((section, target), truth) in enumerate(
        zip(section_targets, truths, strict=True), 1
    ):
        other = focus[1] if target["key"] == focus[0]["key"] else focus[0]
        named = target if truth else other
        marker = _marker_question(
            payload, "matchName", section, target, target["name"], index=index
        )
        confirm = _choice_question(
            payload,
            "confirmName",
            section,
            target,
            target["isIt"],
            [yes, no],
            yes if truth else no,
            index=index,
            shuffle=False,
            statement_true=truth,
            stated_key=named["key"],
            audio_text=target["isIt"],
        )
        correct = slots[f"buildIdentify-{index}"][0]
        other_term = _a0_other(payload, target, f"tile-{index}")
        built = _build_question(
            payload,
            "buildIdentify",
            section,
            target,
            payload["whatIsThis"],
            _candidate_text(correct),
            other_term["noun"],
            index=index,
        )
        questions.extend((marker, confirm, built))
    result = A0LessonResult(title="Name the objects", questions=questions)
    validate_a0_lesson(payload, result)
    task = a0_lesson_task(
        _SESSION_ID,
        _mission("A0"),
        payload,
        result,
        {},
    )
    return result, task, payload


def _a1(
    pack: LanguagePack,
    facts: BoundSceneFacts,
    vocabulary: ApprovedVocabulary,
    plan: LessonPlan,
    accepted: list[ApprovedSentence],
    builder_selection: dict | None = None,
):
    rows, by_fact = _objects(facts, vocabulary)
    terms = {term.fact_id: term for term in vocabulary.terms}
    attributes = {item.fact_id: item for item in facts.scene_facts.attributes}
    object_attributes: dict[str, list] = {}
    for attribute in facts.scene_facts.attributes:
        object_attributes.setdefault(attribute.object_fact_id, []).append(attribute)
    pairs = []
    pair_selection = (
        builder_selection.get("pairs")
        if builder_selection is not None else None
    )
    selections = (
        [
            (entry["object_key"], entry["attribute_key"])
            for entry in pair_selection
        ]
        if pair_selection is not None
        else [
            (obj.scene_object_id, item.fact_id)
            for obj in facts.scene_facts.objects
            for item in object_attributes.get(obj.fact_id, [])
            if item.fact_id in terms
        ]
    )
    rows_by_key = {row["key"]: row for row in rows}
    for object_key, attribute_key in selections:
        row = rows_by_key.get(str(object_key))
        detail = attributes.get(attribute_key)
        if detail is None:
            continue
        term = terms[detail.fact_id]
        form = term.forms_by_key.get(row["gender"])
        if not form:
            continue
        pairs.append({
            "key": row["key"],
            "source": row["source"],
            "nounPhrase": row["nounPhrase"],
            "gender": row["gender"],
            "vocabularyItemId": row["vocabularyItemId"],
            "attributeKey": detail.fact_id,
            "attributeType": detail.kind,
            "attributeSource": detail.value,
            "agreedForm": form,
            "before": term.position == "before",
        })
    if len(pairs) < 2:
        raise ValueError("A1 needs two objects with approved details")
    pairs = pairs[:2]
    first_detail = attributes[pairs[0]["attributeKey"]]
    if first_detail.kind == "colour":
        selected_colour = "grey" if first_detail.value == "gray" else first_detail.value
        detail_values = [
            "grey" if item.value == "gray" else item.value
            for item in facts.scene_facts.attributes
            if item.kind == "colour"
        ]
        detail_values.extend(
            value for value in SIMILAR_COLOURS
            if value not in detail_values
        )
        contrast_values = [
            value for value in detail_values
            if value != selected_colour
            and value not in SIMILAR_COLOURS.get(selected_colour, set())
        ]
    else:
        contrast_values = list(
            attribute_contrasts(first_detail.kind, first_detail.value)
        )
    attribute_options = [pairs[0]["agreedForm"]]
    attribute_meanings = {
        fold(pairs[0]["agreedForm"]): first_detail.value,
    }
    for value in contrast_values:
        if len(attribute_options) == 3:
            break
        agreement = agreed_attribute(
            first_detail.kind, value, pack.language.code, pairs[0]["gender"]
        )
        form = agreement[0] if agreement else None
        if form and fold(form) not in {fold(option) for option in attribute_options}:
            attribute_options.append(form)
            attribute_meanings[fold(form)] = value
    attribute_meanings = {
        fold(option): attribute_meanings[fold(option)]
        for option in attribute_options
    }
    payload = {
        "pairs": pairs,
        "attributeOptions": attribute_options,
        "describeExtras": [],
        "confirmPrompt": "¿Es {noun}?",
        "sentenceStart": "Es",
        "yes": next(label.text for label in pack.labels if label.semantic == "yes"),
        "no": next(label.text for label in pack.labels if label.semantic == "no"),
        "attributePrompt": next(
            label.text for label in pack.labels if label.semantic == "attribute-prompt-colour"
        ),
        "attributePromptTranslation": "What colour is it?",
        "describePrompt": next(
            label.text for label in pack.labels if label.semantic == "describe-object"
        ),
        "layout": {
            "statementCorrect": [
                plan.slots[0].specs[0].truth,
                plan.slots[1].specs[0].truth,
            ],
            "confirmOrders": [[0, 1], [0, 1]],
            "attributeOrder": list(range(3)),
        },
        "attributeMeanings": attribute_meanings,
        "seed": (
            builder_selection.get("seed", "es-m01")
            if builder_selection is not None else "es-m01"
        ),
    }
    if builder_selection is not None:
        payload["layout"] = {
            **payload["layout"],
            **builder_selection.get("layout", {}),
        }
    sentences = {
        (sentence.candidate.slot_id, sentence.candidate.spec_id): sentence
        for sentence in accepted
    }
    spec_by_slot = {
        slot.slot_id: {spec.use: spec for spec in slot.specs}
        for slot in plan.slots
    }
    questions = []
    for index, (shown, other) in enumerate((pairs, pairs[::-1]), 1):
        slot = f"confirmObject-{index}"
        specs = spec_by_slot[slot]
        prompt = sentences[(slot, specs["prompt"].spec_id)].candidate
        answer = sentences[(slot, specs["answer"].spec_id)].candidate
        contrast = sentences[(slot, specs["option"].spec_id)].candidate
        truth = specs["prompt"].truth
        correct_text, other_text = confirm_answers(payload, shown, other)[truth]
        option_text = {0: answer.text, 1: contrast.text}
        option_order = payload["layout"]["confirmOrders"][index - 1]
        options = [
            {"option_id": f"confirm-{option_index + 1}", "label": option_text[value]}
            for option_index, value in enumerate(option_order)
        ]
        if answer.text != correct_text or contrast.text != other_text:
            raise ValueError(f"A1 generated answer options do not match {slot} bindings")
        questions.append(M01Question(
            question_id=CONFIRM_IDS[index - 1],
            purpose="confirmObject",
            section=IDENTIFY_SECTION,
            prompt=prompt.text,
            interaction_type="multipleChoice",
            options=options,
            correct_option_id=next(
                option["option_id"] for option in options
                if option["label"] == answer.text
            ),
            correct_text=None,
            token_bank=[],
            translation=None,
            object_key=shown["key"],
            attribute_keys=[],
            statement_correct=truth,
        ))
    first, second = pairs
    ordered_attributes = [
        payload["attributeOptions"][index]
        for index in payload["layout"]["attributeOrder"]
        if index < len(payload["attributeOptions"])
    ][:3]
    attribute_options = [
        {"option_id": f"attribute-{index}", "label": value.capitalize()}
        for index, value in enumerate(ordered_attributes, 1)
    ]
    correct_form = first["agreedForm"]
    questions.append(M01Question(
        question_id="choose-attribute",
        purpose="chooseAttribute",
        section=DESCRIBE_SECTION,
        prompt=payload["attributePrompt"],
        interaction_type="multipleChoice",
        options=attribute_options,
        correct_option_id=next(
            option["option_id"] for option in attribute_options
            if option["label"].casefold() == correct_form.casefold()
        ),
        correct_text=None,
        token_bank=[],
        translation=None,
        object_key=first["key"],
        attribute_keys=[first["attributeKey"]],
    ))
    description_sentence = sentences[
        ("describeObject", spec_by_slot["describeObject"]["answer"].spec_id)
    ]
    question = M01Question(
        question_id="describe-object",
        purpose="describeObject",
        section=DESCRIBE_SECTION,
        prompt=payload["describePrompt"],
        interaction_type="sentenceBuilding",
        options=[],
        correct_option_id=None,
        correct_text=description_sentence.candidate.text,
        token_bank=tokens(description_sentence.candidate.text),
        translation=description_sentence.candidate.translation,
        object_key=second["key"],
        attribute_keys=[second["attributeKey"]],
    )
    questions.append(question)
    result = M01LessonResult(
        title="Identify and describe objects",
        explanation="Use the details shown in the scene.",
        questions=questions,
    )
    validate_m01_lesson(payload, result)
    task = m01_lesson_task(
        _SESSION_ID,
        _mission("A1"),
        payload,
        result,
        {pair["key"]: pair["vocabularyItemId"] for pair in pairs},
    )
    return result, task, payload


def _a2(
    pack: LanguagePack,
    facts: BoundSceneFacts,
    vocabulary: ApprovedVocabulary,
    plan: LessonPlan,
    accepted: list[ApprovedSentence],
    builder_selection: dict | None = None,
):
    rows, by_fact = _objects(facts, vocabulary)
    terms = {term.fact_id: term for term in vocabulary.terms}
    attrs = {item.fact_id: item for item in facts.scene_facts.attributes}
    sentences = {
        (item.candidate.slot_id, item.candidate.spec_id): item
        for item in accepted
    }
    specs = {slot.slot_id: {spec.use: spec for spec in slot.specs} for slot in plan.slots}

    def accepted_candidate(slot_id: str, use: str):
        spec = specs[slot_id][use]
        return sentences[(slot_id, spec.spec_id)].candidate

    def object_row(fact_id: str) -> dict:
        try:
            return by_fact[fact_id]
        except KeyError:
            raise ValueError(f"A2 references unknown object fact {fact_id!r}") from None

    def sentence_chunks(candidate) -> list[str]:
        return [chunk.text for chunk in candidate.chunks]

    def add_chunks(candidate, distractors=()):
        answers = sentence_chunks(candidate)
        distractor_values = list(distractors)
        return {
            "correct_text": candidate.text,
            "answer_chunks": answers,
            "token_bank": [*answers, *distractor_values],
            "distractor_chunks": distractor_values,
        }

    fact1 = accepted_candidate("chooseSceneMarker", "fact1")
    fact2 = accepted_candidate("buildSceneFact", "fact2")
    connected = accepted_candidate("chooseSceneDescription", "connected")
    false_attribute = accepted_candidate("chooseSceneDescription", "wrongAttribute")
    false_existence = accepted_candidate("chooseSceneDescription", "wrongExistence")
    descriptions = [
        accepted_candidate("buildSceneDescription", use)
        for use in ("fact1", "fact2", "fact3")
    ]
    followup = accepted_candidate("followUpSceneFact", "followup")

    first_spec = specs["chooseSceneMarker"]["fact1"]
    object_fact = first_spec.bindings["object"]
    selected_facts = (
        builder_selection.get("selection", {})
        if builder_selection is not None else {}
    )
    attr_fact = selected_facts.get("attribute", first_spec.bindings.get("attribute"))
    first_object = object_row(object_fact)
    third_fact = specs["chooseSceneDescription"]["connected"].bindings["other-object"]
    third_object = object_row(third_fact)
    first_attribute = attrs[attr_fact] if attr_fact else None
    first_attribute_term = terms.get(attr_fact) if attr_fact else None
    selected_form = (
        first_attribute_term.forms_by_key.get(first_object["gender"])
        if first_attribute_term else None
    )
    if not selected_form:
        raise ValueError("A2 first fact needs a bound, agreed attribute")
    attribute_options = [{"option_id": "detail-correct", "label": selected_form}]
    attribute_values = (
        ("black", "white", "blue", "green", "red")
        if first_attribute.kind == "colour"
        else attribute_contrasts(first_attribute.kind, first_attribute.value)
    )
    for index, value in enumerate(attribute_values):
        if len(attribute_options) == 3:
            break
        agreement = agreed_attribute(
            first_attribute.kind, value, "es", first_object["gender"]
        )
        form = agreement[0] if agreement else None
        if form and form.casefold() not in {
            option["label"].casefold() for option in attribute_options
        }:
            attribute_options.append(
                {"option_id": f"detail-{index}", "label": form}
            )

    selection = builder_selection.get("selection", {}) if builder_selection else {}
    object_by_fact = {item.fact_id: item for item in facts.scene_facts.objects}
    scene_objects = []
    words = []
    translated_objects = []
    review_markers = {}
    for row in rows:
        obj = object_by_fact[row["fact_id"]]
        term = terms[row["fact_id"]]
        attributes = {
            ("color" if item.kind == "colour" else item.kind): item.value
            for item in facts.scene_facts.attributes
            if item.object_fact_id == obj.fact_id
        }
        scene_objects.append(
            SimpleNamespace(id=obj.scene_object_id, label=obj.label, attributes=attributes)
        )
        words.append(
            SimpleNamespace(
                id=row["vocabularyItemId"],
                display_text=term.target_text,
                gender=term.agreement,
                plural_form=term.forms_by_key.get("plural"),
            )
        )
        translated_objects.append(
            SimpleNamespace(
                key=str(obj.scene_object_id),
                translation=term.forms_by_key["definite"],
                article=term.forms_by_key["article_definite"],
                gender=term.agreement,
            )
        )
        review_markers[str(obj.scene_object_id)] = row["marker"]
    scene_relations = [
        SimpleNamespace(
            id=(
                selection.get("relation_key")
                if selection.get("relation_key")
                else item.fact_id
            ),
            subject_scene_object_id=object_by_fact[item.subject_fact_id].scene_object_id,
            reference_scene_object_id=object_by_fact[item.reference_fact_id].scene_object_id,
            relation=item.relation.value,
        )
        for item in facts.scene_facts.relations
    ]
    approved_facts = _approved_facts(
        _mission("A2"),
        pack.language.code,
        scene_objects,
        scene_relations,
        words,
        SimpleNamespace(objects=translated_objects),
        [],
        None,
        (
            builder_selection.get("seed", "es-m01-a2")
            if builder_selection is not None else "es-m01-a2"
        ),
        review_markers,
    )
    approved_objects = approved_facts["approvedObjects"]
    approved_attributes = approved_facts["approvedAttributes"]
    approved_relationships = approved_facts["approvedRelationships"]
    selected_attribute_row = next(
        row for row in approved_attributes
        if row["objectKey"] == first_object["key"]
        and row["kind"] == first_attribute.kind
        and row["value"] == first_attribute.value
    )
    attribute_key = selection.get("attribute_key", selected_attribute_row["key"])
    alternate_value = (
        ("blue" if first_attribute.value == "red" else "red")
        if first_attribute.kind == "colour"
        else next(iter(attribute_contrasts(first_attribute.kind, first_attribute.value)), None)
    )
    alternate = (
        agreed_attribute(
            first_attribute.kind,
            alternate_value,
            pack.language.code,
            first_object["gender"],
        )
        if alternate_value else None
    )
    false_first = (
        f"Hay {first_object['nounPhrase']} {alternate[0]}."
        if alternate
        else f"Hay {first_object['nounPhrase']} que no es {selected_form}."
    )
    full_description = " ".join(item.text for item in descriptions)
    payload = {
        "approvedFacts": approved_facts,
        "selection": {
            "attributeKey": attribute_key,
            "relationKey": None,
            "firstFactKind": "attribute",
            "secondObjectKey": None,
            "thirdObjectKey": third_object["key"],
        },
        "targetLanguage": "es",
        "missionId": "M01",
        "practiceLevel": "A2",
        "contentVersion": 1,
        "seed": (
            builder_selection.get("seed", "es-m01-a2")
            if builder_selection is not None else "es-m01-a2"
        ),
        "facts": {
            "first": fact1.text,
            "second": fact2.text,
            "third": descriptions[2].text,
            "description": full_description,
            "falseFirst": false_first,
            "q3": connected.text,
            "wrongOne": false_attribute.text,
            "wrongTwo": false_existence.text,
            "detailPrompt": followup.text,
            "attribute": {
                "key": attribute_key,
                "objectKey": first_object["key"],
                "kind": first_attribute.kind,
                "value": first_attribute.value,
                "form": selected_form,
                "before": first_attribute_term.position == "before",
            },
            "relation": None,
            "firstKind": "attribute",
            "firstObject": {
                **first_object,
                "bareNoun": first_object["noun"],
                "gender": first_object["gender"],
                "nounPhrase": approved_objects[
                    next(index for index, row in enumerate(approved_objects)
                         if row["key"] == first_object["key"])
                ]["nounPhrase"],
            },
            "thirdObject": third_object,
        },
    }
    first_attribute_row = next(
        row for row in approved_attributes
        if row["objectKey"] == first_object["key"]
        and row["kind"] == first_attribute.kind
        and row["value"] == first_attribute.value
    )
    selected_relation = next(
        (
            row for row in approved_relationships
            if row["subjectKey"] == first_object["key"]
        ),
        None,
    )
    second_object_key = (
        selected_relation["key"]
        if selected_relation is not None
        else object_row(
            specs["buildSceneDescription"]["fact2"].bindings["subject"]
        )["key"]
    )
    payload["selection"]["relationKey"] = (
        selected_relation["key"] if selected_relation is not None else None
    )
    payload["selection"]["secondObjectKey"] = second_object_key
    payload["facts"]["relation"] = selected_relation
    payload["planningFacts"] = [
        _english_fact(approved_facts, "attribute", first_attribute_row),
        _english_fact(
            approved_facts,
            "relation" if selected_relation is not None else "existence",
            selected_relation
            if selected_relation is not None
            else {"key": second_object_key},
        ),
        _english_fact(approved_facts, "existence", {"key": third_object["key"]}),
    ]
    section1, section2, section3 = (
        "Task 1 · Notice the facts",
        "Task 2 · Describe the scene",
        "Task 3 · Check a detail",
    )
    marker_id = first_object["key"]
    third_marker_id = third_object["key"]
    prompt1 = next(
        label.text for label in pack.labels if label.semantic == "touch-object"
    ).replace("{f['first']}", fact1.text)
    q1_options = [
        {"option_id": row["key"], "label": str(row["marker"])}
        for row in (first_object, third_object)
    ]
    random.Random(f"{payload['seed']}:m01-q1").shuffle(q1_options)
    q3_options = [
        {"option_id": "description-correct", "label": connected.text},
        {"option_id": "description-attribute", "label": false_attribute.text},
        {"option_id": "description-existence", "label": false_existence.text},
    ]
    random.Random(f"{payload['seed']}:m01-q3").shuffle(q3_options)
    random.Random(f"{payload['seed']}:m01-q5").shuffle(attribute_options)
    description_chunks = _sentence_chunks(
        full_description,
        distractors=[false_first],
        rng=random.Random(f"{payload['seed']}:m01-q4"),
        language=pack.language.code,
        phrase_chunks=True,
    )
    questions = [
        MissionA2Question(
            question_id="m01-q1",
            purpose="chooseSceneMarker",
            prompt=prompt1,
            target_language_text=[prompt1],
            interaction_type="multipleChoice",
            options=q1_options,
            correct_option_id=marker_id,
            object_key=marker_id,
            section=section1,
            marker_object_ids={marker_id: marker_id, third_marker_id: third_marker_id},
        ),
        MissionA2Question(
            question_id="m01-q2",
            purpose="buildSceneFact",
            prompt=next(
                label.text
                for label in pack.labels
                if label.semantic == "build-second-fact"
            ),
            target_language_text=[
                next(label.text for label in pack.labels if label.semantic == "build-second-fact")
            ],
            interaction_type="sentenceBuilding",
            object_key=first_object["key"],
            section=section1,
            **add_chunks(fact2, ["pero"]),
        ),
        MissionA2Question(
            question_id="m01-q3",
            purpose="chooseSceneDescription",
            prompt=next(
                label.text
                for label in pack.labels
                if label.semantic == "choose-description"
            ),
            target_language_text=[
                next(
                    label.text
                    for label in pack.labels
                    if label.semantic == "choose-description"
                )
            ],
            interaction_type="multipleChoice",
            options=q3_options,
            correct_option_id="description-correct",
            object_key=first_object["key"],
            section=section2,
        ),
        MissionA2Question(
            question_id="m01-q4",
            purpose="buildSceneDescription",
            prompt=next(label.text for label in pack.labels if label.semantic == "describe-scene"),
            target_language_text=[
                next(label.text for label in pack.labels if label.semantic == "describe-scene")
            ],
            interaction_type="sentenceBuilding",
            object_key=first_object["key"],
            section=section2,
            planning_facts=payload["planningFacts"],
            **{
                "correct_text": description_chunks["correct_text"],
                "answer_chunks": description_chunks["answer_chunks"],
                "token_bank": description_chunks["token_bank"],
                "distractor_chunks": description_chunks["distractor_chunks"],
            },
        ),
        MissionA2Question(
            question_id="m01-q5",
            purpose="followUpSceneFact",
            prompt=followup.text,
            target_language_text=[followup.text],
            interaction_type="multipleChoice",
            options=attribute_options,
            correct_option_id="detail-correct",
            object_key=first_object["key"],
            section=section3,
        ),
    ]
    result = MissionA2Result(title="Describe the scene", questions=questions)
    validate_a2_lesson(payload, result)
    vocabulary_ids = {row["key"]: row["vocabularyItemId"] for row in rows}
    task = m01_a2_task(
        _SESSION_ID,
        _mission("A2"),
        payload,
        result,
        vocabulary_ids,
    )
    return result, task, payload


def build_lesson(
    level: str,
    pack: LanguagePack,
    facts: BoundSceneFacts,
    vocabulary: ApprovedVocabulary,
    plan: LessonPlan,
    accepted: list[ApprovedSentence],
    *,
    builder_selection: dict | None = None,
):
    if level == "A0":
        return _a0(pack, facts, vocabulary, plan, accepted, builder_selection)
    if level == "A1":
        return _a1(pack, facts, vocabulary, plan, accepted, builder_selection)
    if level == "A2":
        return _a2(pack, facts, vocabulary, plan, accepted, builder_selection)
    raise ValueError(f"unsupported M01 level {level!r}")
