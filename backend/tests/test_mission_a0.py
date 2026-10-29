"""A0 (pre-A1) scene missions: level gating, closed content and per-mission rules."""

from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.ai.features.learning_tasks.mission_a0 import validate_a0_lesson
from app.ai.features.learning_tasks.mission_a0_situations import (
    validate_a0_situation_lesson,
)
from app.ai.features.learning_tasks.validation import LearningTaskGenerationError
from app.missions import get_mission
from app.schemas.enums import SessionMode
from app.services import a0_lexicon as lex
from app.services.mission_eligibility import (
    IMPLEMENTED_MISSIONS,
    lesson_missions,
    photo_eligibility,
)
from app.services.mission_registry import MISSION_LESSONS, lesson_spec, registry_key

WORDS = {
    "es": ["la taza", "el libro", "la manzana", "el árbol"],
    "fr": ["la tasse", "le livre", "la pomme", "l'arbre"],
    "de": ["die Tasse", "das Buch", "der Apfel", "der Baum"],
    "ko": ["컵", "책", "사과", "나무"],
}
LABELS = ["cup", "book", "apple", "tree"]
MISSIONS = ("M01", "M02", "M03", "M04", "M05", "M13")


def _objects(labels=LABELS):
    return [SimpleNamespace(id=uuid4(), label=label, attributes={}, bounding_box=None)
            for label in labels]


def _lesson(mission_id, language, *, labels=LABELS, words=None, quantity=2,
            plurals_taught=False, count_label="apple", ownership_index=0,
            compared_indices=(0,), reaction="like", groups=None,
            owner_name=None, subject_name=None):
    objects = _objects(labels)
    relations = []
    if mission_id == "M02":
        objects[0].attributes = {"color": "red"}
        relations = [SimpleNamespace(
            relation="on",
            subject_scene_object_id=objects[0].id,
            reference_scene_object_id=objects[1].id,
        )]
    words = [SimpleNamespace(display_text=word, id=uuid4())
             for word in (words or WORDS[language][:len(labels)])]
    mission = get_mission(mission_id, "A0", 2 if mission_id == "M02" else 1)
    spec = lesson_spec(mission)
    group = next((obj for obj in objects if obj.label == count_label), objects[0])
    counts = [{"label": count_label, "quantity": quantity, "sceneObjectIds": [str(group.id)]}]
    if groups is not None:
        # ``(label, quantity)`` pairs, each counting the object with that label.
        by_label = {obj.label: obj for obj in objects}
        counts = [
            {"label": label, "quantity": amount, "sceneObjectIds": [str(by_label[label].id)]}
            for label, amount in groups
        ]
    context = {}
    if mission_id == "M04":
        context["learner_facts"] = {
            "ownedObjectId": str(objects[ownership_index].id), "pretend": False,
            "ownerName": owner_name,
        }
    elif mission_id == "M05":
        context["learner_facts"] = {"preference": {
            "sceneObjectIds": [str(objects[index].id) for index in compared_indices],
            "chosenObjectId": (
                str(objects[compared_indices[0]].id) if len(compared_indices) == 2 else None
            ),
            "reaction": reaction,
            "subjectName": subject_name,
        }}
    payload = spec.payload(
        mission, language, objects, relations, words, None, counts,
        {"plurals_taught": plurals_taught}, uuid4(), context=context,
    )
    return mission, spec, payload, objects


def _result(mission_id, language, **options):
    mission, spec, payload, objects = _lesson(mission_id, language, **options)
    assert spec.ready(payload)
    result = spec.generation.fallback(payload)
    return mission, spec, payload, result, objects


def _profile(level, language="es", **extra):
    return {"proficiency_level": level, "target_language_code": language, **extra}


@pytest.mark.parametrize("language", ["es", "fr", "de", "ko"])
@pytest.mark.parametrize("onboarded", [True, False])
def test_a0_profiles_get_the_a0_missions_whatever_their_onboarding(language, onboarded):
    missions = lesson_missions(
        SessionMode.LESSON, _profile("A0", language, onboarding_completed=onboarded),
    )
    assert [registry_key(mission) for mission in missions] == [
        "A0:M01", "A0:M02", "A0:M03", "A0:M05",
    ]
    assert next(mission for mission in missions if mission.mission_id == "M02").content_version == 2
    assert all(str(mission.practice_level) == "A0" for mission in missions)


@pytest.mark.parametrize("level", ["A1", "A2"])
def test_a1_and_a2_profiles_never_get_a0_missions(level):
    missions = lesson_missions(
        SessionMode.LESSON, _profile(level, onboarding_completed=False),
    )
    assert all(str(mission.practice_level) != "A0" for mission in missions)
    korean_missions = lesson_missions(SessionMode.LESSON, _profile(level, "ko"))
    assert [mission.mission_id for mission in korean_missions] == (
        ["M06"] if level == "A2" else []
    )


def test_a0_needs_a_lesson_and_a_stored_a0_level():
    assert lesson_missions(SessionMode.QUICK_REVIEW, _profile("A0")) if hasattr(
        SessionMode, "QUICK_REVIEW") else True
    for mode in SessionMode:
        if mode != SessionMode.LESSON:
            assert lesson_missions(mode, _profile("A0")) == []
    # The display label is never a stored level.
    assert lesson_missions(SessionMode.LESSON, _profile("Pre-A1")) == []
    assert "Pre-A1" not in IMPLEMENTED_MISSIONS


def test_a1_lessons_keep_their_own_builders():
    for mission_id in ("M01", "M02", "M03"):
        a1 = get_mission(mission_id, "A1", 1) or get_mission(mission_id, "A1", 2)
        assert lesson_spec(a1) is MISSION_LESSONS[mission_id]
        version = 2 if mission_id == "M02" else 1
        assert lesson_spec(get_mission(
            mission_id, "A0", version,
        )) is not MISSION_LESSONS[mission_id]


def test_a0_definitions_store_the_canonical_level():
    for mission_id in MISSIONS:
        mission = get_mission(mission_id, "A0", 2 if mission_id == "M02" else 1)
        assert mission.practice_level == "A0"
        assert registry_key(mission) == f"A0:{mission_id}"


@pytest.mark.parametrize("language", ["es", "fr", "de", "ko"])
@pytest.mark.parametrize("mission_id", MISSIONS)
def test_each_lesson_is_two_tasks_of_three_questions(mission_id, language):
    _mission, _spec, payload, result, _objects = _result(mission_id, language)
    if mission_id in {"M04", "M05"}:
        validate_a0_situation_lesson(payload, result)
    else:
        validate_a0_lesson(payload, result)
    sections = [question.section for question in result.questions]
    assert len(result.questions) == 6
    if mission_id in {"M04", "M05"}:
        assert len(set(sections)) == 1
        return
    assert len(set(sections)) == 2
    if mission_id in {"M01", "M02"}:
        assert sections == [sections[0], sections[1]] * 3
        assert [question.object_key for question in result.questions] == [
            result.questions[0].object_key,
            result.questions[1].object_key,
        ] * 3
    else:
        assert sections[:3] == [sections[0]] * 3
        assert sections[3:] == [sections[3]] * 3


@pytest.mark.parametrize("mission_id", MISSIONS)
def test_generation_is_deterministic(mission_id):
    first = _result(mission_id, "es")
    payload = first[2]
    again = first[1].generation.fallback(payload)
    assert again == first[3]


@pytest.mark.parametrize("language", ["es", "fr", "de", "ko"])
def test_m01_markers_and_yes_no_truth(language):
    _mission, _spec, payload, result, objects = _result("M01", language)
    rows = {row["key"]: row for row in payload["approvedObjects"]}
    taught = {row["key"] for row in payload["approvedObjects"]}
    for question in result.questions:
        if question.marker_keys:
            for option in question.options:
                assert rows[question.marker_keys[option.option_id]]["marker"] == int(option.label)
            assert question.marker_keys[question.correct_option_id] == question.object_key
        if question.purpose == "confirmName":
            assert question.stated_key in taught
            assert question.statement_true is (question.stated_key == question.object_key)
            correct = next(o for o in question.options if o.option_id == question.correct_option_id)
            yes, no = lex.YES_NO[language]
            assert correct.label == (yes if question.statement_true else no)


def test_m01_rejects_untaught_nouns_and_flipped_truth():
    _mission, _spec, payload, result, _objects = _result("M01", "es")
    question = next(q for q in result.questions if q.purpose == "confirmName")
    position = result.questions.index(question)
    flipped = question.model_copy(update={"statement_true": not question.statement_true})
    with pytest.raises(LearningTaskGenerationError):
        validate_a0_lesson(payload, _replace(result, position, flipped))
    untaught = question.model_copy(update={"stated_key": str(uuid4())})
    with pytest.raises(LearningTaskGenerationError):
        validate_a0_lesson(payload, _replace(result, position, untaught))


def _replace(result, position, question):
    questions = list(result.questions)
    questions[position] = question
    return result.model_copy(update={"questions": questions})


def test_unconfirmed_or_untaught_objects_are_never_approved():
    # "sofa" has no reviewed noun; "book" was taught as a different word.
    _m, _s, payload, _o = _lesson(
        "M01", "es", labels=["cup", "book", "sofa"], words=["la taza", "la mesa", "el sofá"],
    )
    assert [row["source"] for row in payload["approvedObjects"]] == ["cup"]
    assert not lesson_spec(get_mission("M01", "A0", 1)).ready(payload)


def test_m02_teaches_an_adjective_and_a_preposition():
    _mission, _spec, payload, result, _objects = _result("M02", "es")
    building = [q for q in result.questions if q.purpose == "buildDescription"]
    assert len(building) == 2
    assert [task["kind"] for task in payload["descriptionTasks"]] == [
        "adjective", "preposition",
    ]
    assert "roja" in payload["descriptionTasks"][0]["description"]
    assert "sobre" in payload["descriptionTasks"][1]["description"]
    assert all("___" in task["blankPrompt"] for task in payload["descriptionTasks"])
    assert payload["descriptionTasks"][0]["buildSentence"] == "Es una taza roja."
    assert all(
        len(question.options) == 2
        for question in result.questions if question.purpose == "chooseDescriptor"
    )
    for question in result.questions:
        if question.purpose == "chooseDescriptor":
            answer = next(
                option.label for option in question.options
                if option.option_id == question.correct_option_id
            )
            assert answer not in question.prompt


@pytest.mark.parametrize("quantity", [2, 3])
@pytest.mark.parametrize("language", ["es", "fr", "de", "ko"])
def test_m03_keeps_the_learner_count(language, quantity):
    _mission, _spec, payload, result, _objects = _result("M03", language, quantity=quantity)
    assert payload["group"]["quantity"] == payload["group"]["confirmedQuantity"] == quantity
    first = result.questions[:3]
    count = first[0]
    correct = next(o for o in count.options if o.option_id == count.correct_option_id)
    assert correct.label == payload["approvedNumberWords"][str(quantity)]
    assert all(not any(ch.isdigit() for ch in o.label) for q in result.questions for o in q.options)
    for question in result.questions:
        if question.options:
            labels = [o.label for o in question.options]
            assert len(labels) == len(set(labels)) <= 3
    assert first[2].correct_text == payload["quantityChunks"][str(quantity)]
    for question in result.questions:
        for text in (question.prompt, question.correct_text or ""):
            assert not text.startswith(("Hay", "Il y a", "Es gibt", "있"))


def test_m03_rejects_a_changed_count_and_bad_groups():
    _mission, _spec, payload, result, _objects = _result("M03", "es", quantity=2)
    changed = dict(payload, group=dict(payload["group"], quantity=3))
    with pytest.raises(LearningTaskGenerationError):
        validate_a0_lesson(changed, result)
    _m, spec, too_many, _o = _lesson("M03", "es", quantity=4)
    assert not spec.ready(too_many)


@pytest.mark.parametrize(("language", "forms"), [
    ("es", {"el", "la"}),
    ("fr", {"le", "la", "l'"}),
    ("de", {"der", "die", "das"}),
    ("ko", {"이에요", "예요"}),
])
def test_m13_uses_the_reviewed_words_for_each_language(language, forms):
    _mission, _spec, payload, result, _objects = _result("M13", language)
    rows = {row["key"]: row for row in payload["approvedObjects"]}
    for question in result.questions:
        if question.purpose == "fillSlot":
            labels = {o.label for o in question.options}
            assert labels <= forms
            correct = next(o for o in question.options if o.option_id == question.correct_option_id)
            assert correct.label == rows[question.object_key]["form"]
            assert question.complete_chunk == rows[question.object_key]["chunk"]
        if question.purpose == "chooseChunk":
            correct = [o for o in question.options
                       if o.label == rows[question.object_key]["chunk"]]
            assert len(correct) == 1
    if language == "ko":
        assert payload["approvedArticlesOrEndings"] == sorted(lex.KOREAN_ENDINGS)
        assert rows and all(not row["gender"] for row in rows.values())


def test_korean_endings_follow_the_reviewed_final_consonant():
    _m, _s, payload, _o = _lesson("M13", "ko", labels=["cup", "book", "apple"])
    chunks = {row["noun"]: row["chunk"] for row in payload["approvedObjects"]}
    assert chunks["책"] == "책이에요"
    assert chunks["컵"] == "컵이에요"
    assert chunks["사과"] == "사과예요"


def test_french_elision_comes_from_reviewed_metadata():
    _m, _s, payload, _o = _lesson(
        "M13", "fr", labels=["cup", "tree"], words=["la tasse", "l'arbre"],
    )
    rows = {row["noun"]: row for row in payload["approvedObjects"]}
    assert rows["arbre"]["chunk"] == "l'arbre"
    assert "l'" not in {item["form"] for item in rows["tasse"]["formChoices"]}


@pytest.mark.parametrize("language", ["es", "fr"])
def test_m13_plural_words_need_plurals_taught(language):
    plural = {"es": {"los", "las"}, "fr": {"les"}}[language]
    _m, _s, before, _o = _lesson("M13", language)
    assert not plural & set(before["approvedArticlesOrEndings"])
    _m, _s, after, _o = _lesson("M13", language, plurals_taught=True)
    assert plural & set(after["approvedArticlesOrEndings"])
    _mission, _spec, payload, result, _objects = _result("M13", language)
    taught = dict(payload, pluralsTaught=True)
    validate_a0_lesson(taught, result)


def test_m13_rejects_multiple_correct_answers_and_endings_as_articles():
    _mission, _spec, payload, result, _objects = _result("M13", "ko")
    question = next(q for q in result.questions if q.purpose == "chooseChunk")
    position = result.questions.index(question)
    duplicate = question.model_copy(update={"options": [
        o.model_copy(update={"label": question.options[0].label}) for o in question.options
    ]})
    with pytest.raises(LearningTaskGenerationError):
        validate_a0_lesson(payload, _replace(result, position, duplicate))
    articles = dict(payload, approvedArticlesOrEndings=["el", "la"])
    with pytest.raises(LearningTaskGenerationError):
        validate_a0_lesson(articles, result)


def _groups(objects, *pairs):
    by_label = {obj.label: obj for obj in objects}
    return [
        {"label": label, "quantity": amount, "sceneObjectIds": [str(by_label[label].id)]}
        for label, amount in pairs
    ]


def test_m03_counts_the_first_valid_group_when_several_are_counted():
    mission = get_mission("M03", "A0", 1)
    objects = _objects(["cup", "book", "apple", "sofa"])
    several = _groups(objects, ("cup", 2), ("book", 2), ("apple", 3))
    assert photo_eligibility(mission, objects, [], several).eligible
    # A group out of range does not block a later valid one.
    mixed = _groups(objects, ("cup", 1), ("book", 4), ("apple", 2))
    assert photo_eligibility(mission, objects, [], mixed).eligible
    # Objects outside the reviewed list can be counted too.
    assert photo_eligibility(mission, objects, [], _groups(objects, ("sofa", 2))).eligible
    unusable = _groups(objects, ("sofa", 1), ("cup", 1))
    check = photo_eligibility(mission, objects, [], unusable)
    assert not check.eligible
    assert "Count a group of 2 or 3 matching objects." in check.reasons
    assert check.missing == ("counts",)


def test_m03_lesson_uses_the_first_valid_group():
    _m, _s, payload, result, objects = _result(
        "M03", "es", labels=["cup", "book", "apple", "sofa"],
        groups=[("sofa", 2), ("cup", 1), ("book", 3), ("apple", 2)],
    )
    book = next(obj for obj in objects if obj.label == "book")
    assert payload["group"]["key"] == str(book.id)
    assert payload["group"]["quantity"] == 3
    validate_a0_lesson(payload, result)


def test_photo_eligibility_needs_two_different_objects_not_reviewed_nouns():
    mission = get_mission("M01", "A0", 1)
    assert not photo_eligibility(mission, _objects(["sofa"]), []).eligible
    assert not photo_eligibility(mission, _objects(["sofa", "sofa"]), []).eligible
    # Any confirmed objects qualify; their nouns come from the scene translation.
    assert photo_eligibility(mission, _objects(["cup", "sofa"]), []).eligible
    assert photo_eligibility(mission, _objects(["cup", "book"]), []).eligible


@pytest.mark.parametrize("mission_id", MISSIONS)
def test_tasks_persist_questions_answers_and_option_order(mission_id):
    mission, spec, payload, result, _objects = _result(mission_id, "de")
    session_id = uuid4()
    task = spec.task(session_id, mission, payload, result, {})
    again = spec.task(session_id, mission, payload, spec.generation.fallback(payload), {})
    assert task.id == again.id and task.public_content == again.public_content
    content = task.public_content
    assert content.mission_id == mission_id and content.practice_level == "A0"
    assert content.prep
    assert set(task.answer_key.correct_option_ids) == {q.question_id for q in content.questions}
    for question in content.questions:
        if question.interaction_type == "multipleChoice":
            assert len(question.options) <= 3
            if mission_id not in {"M04", "M05"}:
                assert question.keep_option_order
