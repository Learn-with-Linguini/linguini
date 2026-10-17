"""Approved-fact contracts and deterministic A2 mission registrations."""

from types import SimpleNamespace
from uuid import UUID

import pytest

from app.ai.features.learning_tasks.mission import tokens
from app.ai.features.learning_tasks.mission_a2 import A2_GENERATIONS, validate_a2_lesson
from app.ai.features.learning_tasks.validation import LearningTaskGenerationError
from app.missions import get_mission
from app.services.mission_eligibility import lesson_missions
from app.services.mission_eligibility_a2 import eligibility_reasons
from app.services.mission_facts_a2 import approved_facts
from app.services.mission_language_a2 import A2_ENABLED_LANGUAGES
from app.services.mission_registry import MISSION_LESSONS

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


@pytest.mark.parametrize("mission_id", ["M01", "M02", "M03", "M04"])
def test_a2_generations_are_deterministic_version_one(mission_id):
    generation = A2_GENERATIONS[mission_id]
    code = mission_id.lower()
    assert generation.prompt_version == f"learning-tasks.{code}-a2.v1"
    assert generation.schema_version == f"learning-tasks-{code}-a2-result.v1"
    assert generation.validator_version == f"learning-tasks-{code}-a2-validator.v1"
    assert generation.json_schema_name == f"mission_lesson_{code}_a2_v1"
    assert generation.uses_model is False
    assert (mission_id, "A2") in MISSION_LESSONS


def test_only_spanish_and_french_are_enabled_for_a2():
    assert A2_ENABLED_LANGUAGES == frozenset({"es", "fr"})
    for language in ("es", "fr"):
        assert [
            mission.practice_level
            for mission in lesson_missions(
                "lesson", {"proficiency_level": "A2", "target_language_code": language}
            )
        ] == ["A2"] * 4
    for language in ("de", "ko"):
        assert (
            lesson_missions("lesson", {"proficiency_level": "A2", "target_language_code": language})
            == []
        )


def test_gating_preserves_the_a1_plan_and_excludes_a0_and_other_a2_languages():
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
    ]
    assert lesson_missions(
        "lesson", {"proficiency_level": "A0", "target_language_code": "es"}
    ) == []
    for language in ("de", "ko"):
        assert lesson_missions(
            "lesson", {"proficiency_level": "A2", "target_language_code": language}
        ) == []


def test_a2_eligibility_uses_confirmed_relations_and_unequal_named_groups():
    objects, _words, relations, groups, _translated, _markers = _scene()
    m01 = get_mission("M01", "A2", 1)
    m02 = get_mission("M02", "A2", 1)
    m03 = get_mission("M03", "A2", 1)

    assert eligibility_reasons("describeScene", m01, objects, relations, []) == []
    assert eligibility_reasons("describeScene", m01, objects, [], []) == []
    assert eligibility_reasons("findTarget", m02, objects, relations, []) == []
    assert eligibility_reasons("findTarget", m02, objects, [], []) != []
    assert eligibility_reasons("compareQuantities", m03, objects, [], groups) == []
    equal_groups = [{**group, "quantity": 2} for group in groups]
    assert eligibility_reasons("compareQuantities", m03, objects, [], equal_groups) != []


def test_a2_eligibility_rejects_missing_facts_and_removed_review_objects():
    objects, words, relations, groups, translated, markers = _scene()
    m01 = get_mission("M01", "A2", 1)
    m02 = get_mission("M02", "A2", 1)
    m03 = get_mission("M03", "A2", 1)
    m04 = get_mission("M04", "A2", 1)
    assert eligibility_reasons("describeScene", m01, objects[:2], relations, []) != []
    plain = [
        SimpleNamespace(id=obj.id, label=obj.label, attributes={})
        for obj in objects
    ]
    assert eligibility_reasons("describeScene", m01, plain, [], []) != []
    assert eligibility_reasons("findTarget", m02, objects, [], []) != []
    assert eligibility_reasons("compareQuantities", m03, objects, [], groups[:1]) != []
    assert eligibility_reasons("fictionalOwnership", m04, objects[:1], [], []) != []

    retained = objects[:2]
    retained_markers = {str(obj.id): markers[str(obj.id)] for obj in retained}
    facts = approved_facts(
        m02, "es", retained, relations, words[:2], translated, groups, {},
        "review-removed", retained_markers,
    )
    assert all(row["key"] in retained_markers for row in facts["approvedObjects"])
    assert all(
        row["subjectKey"] in retained_markers and row["referenceKey"] in retained_markers
        for row in facts["approvedRelationships"]
    )


def test_m01_relation_only_scene_remains_eligible_and_buildable():
    objects, words, relations, groups, translated, markers = _scene()
    plain = [
        SimpleNamespace(id=obj.id, label=obj.label, attributes={})
        for obj in objects
    ]
    mission = get_mission("M01", "A2", 1)
    assert eligibility_reasons("describeScene", mission, plain, relations, []) == []
    spec = MISSION_LESSONS[("M01", "A2")]
    payload = spec.payload(
        mission, "es", plain, relations, words, translated, groups, {},
        "relation-only", review_markers=markers,
    )
    result = spec.generation.fallback(payload)
    assert result.questions[0].correct_option_id is not None
    assert payload["selection"]["firstFactKind"] == "relation"


def test_removed_review_object_is_absent_from_m02_facts_and_questions():
    mission = get_mission("M02", "A2", 1)
    objects, words, relations, groups, translated, markers = _scene()
    removed = objects[2]
    retained = objects[:2]
    retained_words = words[:2]
    retained_markers = {str(obj.id): markers[str(obj.id)] for obj in retained}
    payload = MISSION_LESSONS[("M02", "A2")].payload(
        mission, "es", retained, relations, retained_words, translated, groups,
        {}, "review-removed-object", review_markers=retained_markers,
    )
    result = MISSION_LESSONS[("M02", "A2")].generation.fallback(payload)
    public = repr([question.model_dump() for question in result.questions])
    assert removed.label not in public
    assert all(row["key"] != str(removed.id) for row in payload["approvedFacts"]["approvedObjects"])
    assert all(
        str(removed.id) != object_id
        for question in result.questions
        if question.marker_object_ids
        for object_id in question.marker_object_ids.values()
    )


@pytest.mark.parametrize("language", ["es", "fr"])
def test_approved_facts_use_only_reviewed_scene_data(language):
    mission = get_mission("M02", "A2", 1)
    objects, words, relations, groups, translated, markers = _scene(language)
    objects[0].attributes["state"] = "sparkly"
    facts = approved_facts(
        mission,
        language,
        objects,
        relations,
        words,
        translated,
        groups,
        {},
        "session-a2",
        markers,
    )

    assert set(facts) == FACT_KEYS
    assert [row["englishLabel"] for row in facts["approvedObjects"]] == [
        "cup",
        "table",
        "book",
    ]
    assert all(row["marker"] == markers[row["key"]] for row in facts["approvedObjects"])
    assert {(row["kind"], row["value"]) for row in facts["approvedAttributes"]} == {
        ("colour", "red"),
        ("size", "big"),
    }
    assert len(facts["approvedRelationships"]) == 1
    assert "sparkly" not in facts["approvedVocabulary"]
    assert facts["approvedRoleplayFacts"][0]["kind"] == "lostObject"


@pytest.mark.parametrize("language", ["es", "fr"])
@pytest.mark.parametrize("mission_id", ["M01", "M02", "M03", "M04"])
def test_deterministic_builders_validate_all_a2_lessons(language, mission_id):
    mission = get_mission(mission_id, "A2", 1)
    objects, words, relations, groups, translated, markers = _scene(language)
    spec = MISSION_LESSONS[(mission_id, "A2")]
    payload = spec.payload(
        mission,
        language,
        objects,
        relations,
        words,
        translated,
        groups,
        {},
        "session-a2",
        review_markers=markers,
    )

    result = spec.generation.fallback(payload)

    assert len(result.questions) == 5
    assert [question.question_id for question in result.questions] == [
        f"{mission_id.lower()}-q{index}" for index in range(1, 6)
    ]


@pytest.mark.parametrize("language", ["es", "fr"])
def test_m04_owner_clues_and_corrections_match_assigned_facts(language):
    mission = get_mission("M04", "A2", 1)
    objects, words, relations, groups, translated, markers = _scene(language)
    spec = MISSION_LESSONS[("M04", "A2")]
    payload = spec.payload(
        mission,
        language,
        objects,
        relations,
        words,
        translated,
        groups,
        {},
        "session-a2",
        review_markers=markers,
    )
    result = spec.generation.fallback(payload)
    facts = payload["approvedFacts"]
    assigned = next(
        row
        for row in facts["approvedObjects"]
        if row["key"] == payload["selection"]["assignedObjectKey"]
    )
    owner = "Marta" if language == "es" else "Léa"
    possessive_labels = {option.label for option in result.questions[1].options}
    correction = result.questions[3]
    correction_labels = {option.label for option in correction.options}
    correct = next(
        option.label
        for option in correction.options
        if option.option_id == correction.correct_option_id
    )

    assert owner in result.questions[1].prompt
    assert possessive_labels == (
        {"mi", "mis", "su"} if language == "es" else {"ma", "mon", "mes", "sa"}
    )
    assert (
        f"No, es mi {assigned['bareNoun']}."
        if language == "es"
        else f"Non, c'est {('ma' if assigned['gender'] == 'feminine' else 'mon')} "
        f"{assigned['bareNoun']}."
    ) in correction_labels
    assert (
        f"Sí, es mi {assigned['bareNoun']}."
        if language == "es"
        else f"Oui, c'est {('ma' if assigned['gender'] == 'feminine' else 'mon')} "
        f"{assigned['bareNoun']}."
    ) in correction_labels
    assert owner in correct


def test_m02_validator_rejects_a_leaked_target_noun():
    mission = get_mission("M02", "A2", 1)
    objects, words, relations, groups, translated, markers = _scene()
    spec = MISSION_LESSONS[("M02", "A2")]
    payload = spec.payload(
        mission,
        "es",
        objects,
        relations,
        words,
        translated,
        groups,
        {},
        "session-a2",
        review_markers=markers,
    )
    result = spec.generation.fallback(payload)
    target = next(
        row
        for row in payload["approvedFacts"]["approvedObjects"]
        if row["key"] == payload["selection"]["targetObjectKey"]
    )
    assert target["bareNoun"] in result.questions[4].correct_text
    questions = list(result.questions)
    questions[0] = questions[0].model_copy(
        update={"prompt": f"{questions[0].prompt} {target['bareNoun']}"}
    )

    with pytest.raises(LearningTaskGenerationError, match="hides target nouns"):
        validate_a2_lesson(payload, result.model_copy(update={"questions": questions}))


@pytest.mark.parametrize("mission_id", ["M03", "M04"])
def test_roleplay_validator_rejects_unapproved_provenance(mission_id):
    mission = get_mission(mission_id, "A2", 1)
    objects, words, relations, groups, translated, markers = _scene()
    spec = MISSION_LESSONS[(mission_id, "A2")]
    payload = spec.payload(
        mission,
        "es",
        objects,
        relations,
        words,
        translated,
        groups,
        {},
        "session-a2",
        review_markers=markers,
    )
    result = spec.generation.fallback(payload)
    facts = dict(payload["approvedFacts"])
    facts["approvedRoleplayFacts"] = [
        {**fact, "source": "scene"} for fact in facts["approvedRoleplayFacts"]
    ]

    with pytest.raises(LearningTaskGenerationError):
        validate_a2_lesson({**payload, "approvedFacts": facts}, result)


def test_disabled_language_returns_the_closed_empty_contract():
    facts = approved_facts(
        get_mission("M01", "A2", 1),
        "de",
        [],
        [],
        [],
        None,
        [],
        {},
        "session-a2",
        {},
    )
    assert set(facts) == FACT_KEYS
    assert all(not value for value in facts.values())


def _built(mission_id, language="es", session_id="mutation"):
    mission = get_mission(mission_id, "A2", 1)
    objects, words, relations, groups, translated, markers = _scene(language)
    spec = MISSION_LESSONS[(mission_id, "A2")]
    payload = spec.payload(
        mission, language, objects, relations, words, translated, groups, {},
        session_id, review_markers=markers,
    )
    return payload, spec.generation.fallback(payload)


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


@pytest.mark.parametrize("change", ["option", "prompt_text", "token"])
def test_closed_vocabulary_rejects_mutated_target_language_surfaces(change):
    payload, result = _built("M01")
    if change == "option":
        question = result.questions[2]
        options = [option.model_copy(update={"label": "inventado"} if index == 0 else {})
                   for index, option in enumerate(question.options)]
        result = _replace_question(result, 2, options=options)
    elif change == "prompt_text":
        question = result.questions[2]
        result = _replace_question(
            result, 2, prompt=f"{question.prompt} inventado",
            target_language_text=[*question.target_language_text, "inventado"],
        )
    else:
        question = result.questions[1]
        result = _replace_question(
            result, 1, token_bank=[*question.token_bank, "inventado"],
            distractor_chunks=[*question.distractor_chunks, "inventado"],
        )
    with pytest.raises(LearningTaskGenerationError, match="unapproved vocabulary"):
        validate_a2_lesson(payload, result)


@pytest.mark.parametrize(
    ("mission_id", "index", "mutation"),
    [
        ("M01", 1, "unapproved_fact"),
        ("M01", 2, "wrong_option"),
        ("M01", 3, "one_fact"),
        ("M01", 3, "unapproved_description_fact"),
        ("M01", 2, "true_wrong_option"),
        ("M02", 1, "wrong_clue"),
        ("M02", 0, "wrong_meaning"),
        ("M02", 2, "wrong_marker"),
        ("M02", 2, "missing_distractor"),
        ("M02", 3, "wrong_clarification"),
        ("M02", 3, "missing_shared_detail"),
        ("M02", 4, "wrong_noun"),
        ("M03", 0, "wrong_count"),
        ("M03", 1, "wrong_quantity"),
        ("M03", 2, "reverse_comparison"),
        ("M03", 3, "wrong_roleplay_response"),
        ("M03", 4, "wrong_comparison"),
        ("M04", 0, "wrong_assignment"),
        ("M04", 1, "wrong_possessive"),
        ("M04", 2, "wrong_belonging"),
        ("M04", 3, "wrong_owner"),
        ("M04", 4, "wrong_ownership_description"),
    ],
)
def test_a2_semantic_contracts_reject_mutated_valid_results(mission_id, index, mutation):
    payload, result = _built(mission_id)
    question = result.questions[index]
    if mutation in {"unapproved_fact", "wrong_clue", "wrong_quantity", "wrong_comparison",
                    "wrong_belonging", "wrong_ownership_description"}:
        text = payload["facts"].get("first", payload["facts"].get("firstSentence", ""))
        if mutation == "unapproved_fact":
            text = "Hay una taza azul."
        elif mutation == "wrong_clue":
            text = payload["facts"]["attributeClue"]
        elif mutation == "wrong_quantity":
            text = payload["facts"]["firstSentence"]
        elif mutation == "wrong_comparison":
            text = payload["facts"]["secondSentence"]
        elif mutation == "wrong_belonging":
            text = (
                f"{payload['facts']['possessive']} "
                f"{payload['facts']['alternative']['bareNoun']}."
            )
        elif mutation == "wrong_ownership_description":
            text = (
                f"{payload['facts']['possessive']} "
                f"{payload['facts']['alternative']['bareNoun']}."
            )
        result = _replace_sentence(result, index, text)
    elif mutation == "one_fact":
        result = _replace_sentence(result, index, payload["facts"]["first"])
    elif mutation == "unapproved_description_fact":
        text = (
            f"{payload['facts']['first']} {payload['facts']['second']} "
            "Hay una taza azul."
        )
        result = _replace_sentence(result, index, text)
    elif mutation == "true_wrong_option":
        options = list(question.options)
        wrong_index = next(
            index for index, option in enumerate(options)
            if option.option_id != question.correct_option_id
        )
        options[wrong_index] = options[wrong_index].model_copy(
            update={"label": payload["facts"]["first"]}
        )
        result = _replace_question(result, index, options=options)
    elif mutation == "wrong_noun":
        text = question.correct_text.replace(
            next(row["bareNoun"] for row in payload["approvedFacts"]["approvedObjects"]
                 if row["key"] == payload["selection"]["targetObjectKey"]),
            next(row["bareNoun"] for row in payload["approvedFacts"]["approvedObjects"]
                 if row["key"] != payload["selection"]["targetObjectKey"]),
        )
        result = _replace_sentence(result, index, text)
    elif mutation == "wrong_marker":
        wrong_id = payload["selection"]["distractorObjectKey"]
        option_id = next(option.option_id for option in question.options
                         if question.marker_object_ids.get(option.option_id) == wrong_id)
        result = _replace_question(result, index, correct_option_id=option_id)
    elif mutation == "wrong_meaning":
        options = list(question.options)
        correct_index = next(
            index for index, option in enumerate(options)
            if option.option_id == question.correct_option_id
        )
        wrong_label = next(
            option.label for option in options
            if option.option_id != question.correct_option_id
        )
        options[correct_index] = options[correct_index].model_copy(
            update={"label": wrong_label}
        )
        result = _replace_question(result, index, options=options)
    elif mutation == "missing_distractor":
        distractor_id = payload["selection"]["distractorObjectKey"]
        marker_map = {
            option_id: object_id
            for option_id, object_id in question.marker_object_ids.items()
            if object_id != distractor_id
        }
        result = _replace_question(result, index, marker_object_ids=marker_map)
    elif mutation == "missing_shared_detail":
        result = _replace_question(
            result,
            index,
            options=[
                option for option in question.options
                if option.option_id != "clarify-shared"
            ],
        )
    elif mutation == "wrong_assignment":
        result = _replace_question(
            result, index, correct_option_id=next(
                option.option_id for option in question.options
                if option.option_id != question.correct_option_id
            ),
        )
    elif mutation == "wrong_possessive":
        result = _replace_question(
            result, index, correct_option_id=next(
                option.option_id for option in question.options
                if option.option_id != question.correct_option_id
            ),
        )
    else:
        result = _replace_question(
            result, index, correct_option_id=next(
                option.option_id for option in question.options
                if option.option_id != question.correct_option_id
            ),
        )
    with pytest.raises(LearningTaskGenerationError):
        validate_a2_lesson(payload, result)


def test_m03_generates_both_comparison_directions_across_seeds():
    directions = set()
    for first_quantity, second_quantity in ((3, 2), (2, 3)):
        for seed in range(24):
            mission = get_mission("M03", "A2", 1)
            objects, words, relations, groups, translated, markers = _scene()
            groups = [
                {
                    **group,
                    "quantity": first_quantity
                    if group["label"] == "cup"
                    else second_quantity,
                }
                for group in groups
            ]
            payload = MISSION_LESSONS[("M03", "A2")].payload(
                mission, "es", objects, relations, words, translated, groups, {},
                f"direction-{seed}", review_markers=markers,
            )
            MISSION_LESSONS[("M03", "A2")].generation.fallback(payload)
            first = next(row for row in payload["approvedFacts"]["approvedCountedGroups"]
                         if row["key"] == payload["selection"]["firstGroupKey"])
            second = next(row for row in payload["approvedFacts"]["approvedCountedGroups"]
                          if row["key"] == payload["selection"]["secondGroupKey"])
            directions.add(first["quantity"] > second["quantity"])
    assert directions == {True, False}


def test_m03_validator_rejects_equal_counts_and_untaught_number_words():
    payload, result = _built("M03")
    groups = payload["approvedFacts"]["approvedCountedGroups"]
    selection = payload["selection"]
    first = next(row for row in groups if row["key"] == selection["firstGroupKey"])
    second = next(row for row in groups if row["key"] == selection["secondGroupKey"])
    second["quantity"] = first["quantity"]
    with pytest.raises(LearningTaskGenerationError, match="equal quantities"):
        validate_a2_lesson(payload, result)

    payload, result = _built("M03")
    payload["approvedFacts"]["approvedVocabulary"].append("once")
    question = result.questions[0]
    options = list(question.options)
    wrong_index = next(
        index for index, option in enumerate(options)
        if option.option_id != question.correct_option_id
    )
    options[wrong_index] = options[wrong_index].model_copy(update={"label": "once"})
    result = _replace_question(result, 0, options=options)
    with pytest.raises(LearningTaskGenerationError, match="outside the taught range"):
        validate_a2_lesson(payload, result)


def test_m03_fictional_count_cannot_leak_outside_roleplay_statement():
    payload, result = _built("M03")
    question = result.questions[0]
    false_count = next(
        fact["numberWord"] for fact in payload["approvedFacts"]["approvedRoleplayFacts"]
        if fact["kind"] == "falseCount"
    )
    result = _replace_question(
        result, 0, prompt=f"{question.prompt} {false_count}"
    )
    with pytest.raises(LearningTaskGenerationError, match="outside its role-play statement"):
        validate_a2_lesson(payload, result)


def test_french_m04_uses_mon_before_a_vowel_initial_feminine_noun():
    mission = get_mission("M04", "A2", 1)
    objects, words, relations, groups, translated, markers = _scene("fr")
    spec = MISSION_LESSONS[("M04", "A2")]
    initial = spec.payload(
        mission, "fr", objects, relations, words, translated, groups, {},
        "french-vowel", review_markers=markers,
    )
    assigned_key = initial["selection"]["assignedObjectKey"]
    orange_term = next(term for term in translated.objects if term.key == assigned_key)
    orange_term.translation = "orange"
    orange_term.article = "l'"
    orange_term.gender = "feminine"
    payload = MISSION_LESSONS[("M04", "A2")].payload(
        mission, "fr", objects, relations, words, translated, groups, {},
        "french-vowel", review_markers=markers,
    )
    result = MISSION_LESSONS[("M04", "A2")].generation.fallback(payload)
    assigned = next(
        obj for obj in payload["approvedFacts"]["approvedObjects"]
        if obj["key"] == payload["selection"]["assignedObjectKey"]
    )
    assert assigned["bareNoun"] == "orange"
    correct = next(
        option.label for option in result.questions[1].options
        if option.option_id == result.questions[1].correct_option_id
    )
    assert correct == "mon"
    assert "Mon orange" in result.questions[2].correct_text
