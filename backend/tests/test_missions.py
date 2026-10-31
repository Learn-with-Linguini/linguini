from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.missions import (
    DEFINITIONS_DIR,
    MissionConfigurationError,
    get_mission,
    load_mission_file,
    load_missions,
)
from app.schemas.enums import SessionMode
from app.schemas.tasks import (
    CorrectionRule,
    QuestionReviewDetails,
    SessionTask,
    SessionTaskPublic,
    SubmitVocabularyReviewAttemptRequest,
)
from app.services.question_outcomes import review_details

MISSION = {"missionId": "M01", "practiceLevel": "A1", "contentVersion": 1}
HIDDEN_WORD = uuid4()
HIDDEN_OBJECT = uuid4()


def lesson_content(**extra):
    return {
        "kind": "grammarLesson",
        "focus": "genderNumberAgreement",
        "title": "Describe the cup",
        "explanation": "Colours agree with the noun.",
        "questions": [
            {
                "questionId": "colour",
                "prompt": "Choose the description",
                "options": [
                    {"optionId": "roja", "label": "La taza es roja."},
                    {"optionId": "rojo", "label": "La taza es rojo."},
                ],
            },
            {
                "questionId": "build",
                "prompt": "Build the sentence",
                "interactionType": "sentenceBuilding",
                "tokenBank": ["La", "taza", "es", "roja"],
            },
            {
                "questionId": "extra",
                "prompt": "Pick the cup",
                "options": [
                    {"optionId": "taza", "label": "la taza"},
                    {"optionId": "mesa", "label": "la mesa"},
                ],
            },
        ],
        **extra,
    }


def evaluations():
    return [
        {
            "questionId": "colour",
            "objectiveId": "identify-describe-object",
            "targetIds": ["describe-colour"],
            "evidenceType": "recognition",
            "vocabularyItemIds": [str(HIDDEN_WORD)],
            "sceneObjectId": str(HIDDEN_OBJECT),
            "corrections": [
                {
                    "mistake": "wrongGender",
                    "answers": ["rojo"],
                    "correction": "La taza es roja.",
                    "explanation": "Taza is feminine, so use roja.",
                }
            ],
        },
        {
            "questionId": "build",
            "objectiveId": "identify-describe-object",
            "targetIds": ["describe-colour"],
            "evidenceType": "construction",
            "rubricCriterionIds": ["colour-matches-photo"],
            "corrections": [{"mistake": "wordOrder", "correction": "La taza es roja."}],
        },
    ]


def answer_key(**extra):
    return {
        "correctOptionIds": {"colour": "roja", "build": "La taza es roja", "extra": "taza"},
        **extra,
    }


def mission_task(content=None, key=None):
    return SessionTask(
        session_id=uuid4(),
        phase="learning",
        kind="grammarLesson",
        order_index=0,
        public_content=content or lesson_content(**MISSION),
        answer_key=key or answer_key(questionEvaluations=evaluations()),
    )


def test_m01_a1_definition_covers_the_mission_contract():
    mission = get_mission("M01", "A1", 1)
    assert mission.title == "Identify and describe an object"
    assert mission.photo_requirements.min_confirmed_objects == 2
    assert mission.photo_requirements.min_coloured_objects == 2
    assert mission.photo_requirements.min_relations == 0
    assert mission.objective.objective_id == "identify-describe-object"
    assert set(mission.targets) == {
        "identify-object", "name-object", "describe-colour", "describe-location",
    }
    assert {item.clue_frame_id for item in mission.language_patterns} == {
        None, "colour", "location",
    }
    assert all({"es", "fr"} <= set(item.examples) for item in mission.language_patterns)
    assert mission.teaching.task_sequence == [
        "vocabularyIntroduction", "grammarLesson",
    ]
    assert not mission.counts_as_assistance("translation")
    assert mission.counts_as_assistance("hint")
    assert {item.target_id for item in mission.evaluation_criteria} == set(mission.targets)
    assert mission.expected_performance.min_assessed_questions == 4
    assert get_mission("M01", "A1", 2) is None
    assert get_mission("M01", "A2", 1) is not None


def test_every_mission_ends_before_optional_ispy():
    for mission in load_missions(DEFINITIONS_DIR).values():
        assert mission.teaching.task_sequence == [
            "vocabularyIntroduction", "grammarLesson",
        ]


def test_retired_article_pairing_mission_is_not_scheduled():
    assert get_mission("M13", "A0", 1) is None


def test_definition_files_are_named_by_their_mission(tmp_path):
    source = (DEFINITIONS_DIR / "M01-A1.toml").read_text()
    renamed = tmp_path / "M01-A1.v3.toml"
    renamed.write_text(source)
    with pytest.raises(MissionConfigurationError, match="must be named M01-A1.toml"):
        load_mission_file(renamed)
    broken = tmp_path / "M01-A1.toml"
    broken.write_text(source.replace('target_id = "describe-colour"\ndescription', (
        'target_id = "describe-size"\ndescription'
    )))
    with pytest.raises(MissionConfigurationError, match="describe-size"):
        load_missions(tmp_path)
    assert sorted(path.name for path in Path(DEFINITIONS_DIR).glob("*.toml")) == [
        "M01-A0.toml", "M01-A1.toml", "M01-A2.toml",
        "M02-A0-2.toml", "M02-A0.toml", "M02-A1-2.toml", "M02-A1.toml", "M02-A2.toml",
        "M03-A0.toml", "M03-A1.toml", "M03-A2.toml",
        "M04-A0.toml", "M04-A1.toml", "M04-A2.toml",
        "M05-A0.toml", "M05-A1.toml", "M06-A2.toml",
    ]


def test_m04_m05_definitions_cover_three_assessed_questions():
    for mission_id in ("M04", "M05"):
        mission = get_mission(mission_id, "A1", 1)
        assert len(mission.targets) == len(mission.evaluation_criteria) == 3
        assert mission.expected_performance.min_assessed_questions == 2
        assert mission.expected_performance.min_correct_ratio == 0.75
        assert mission.expected_performance.min_independent_correct == 1


def test_legacy_tasks_keep_their_saved_json_shape():
    task = mission_task(content=lesson_content(), key=answer_key())
    assert task.public_content.mission_key is None
    content = task.public_content.model_dump(mode="json")
    key = task.answer_key.model_dump(mode="json")
    assert not {"missionId", "practiceLevel", "contentVersion"} & set(content)
    assert "questionEvaluations" not in key
    reloaded = SessionTask.model_validate(
        {**task.model_dump(mode="json"), "publicContent": content, "answerKey": key}
    )
    assert reloaded.public_content == task.public_content
    assert reloaded.answer_key == task.answer_key


@pytest.mark.parametrize(
    ("content", "key", "message"),
    [
        (lesson_content(missionId="M01"), answer_key(), "must be set together"),
        (lesson_content(**{**MISSION, "contentVersion": 9}), answer_key(), "unknown mission"),
        (lesson_content(), answer_key(questionEvaluations=evaluations()), "require mission"),
        (
            lesson_content(**MISSION),
            answer_key(questionEvaluations=[{**evaluations()[1], "questionId": "missing"}]),
            "does not have",
        ),
        (
            lesson_content(**MISSION),
            answer_key(questionEvaluations=[{**evaluations()[0], "targetIds": ["spell-word"]}]),
            "unknown targets",
        ),
        (
            lesson_content(**MISSION),
            answer_key(
                questionEvaluations=[{**evaluations()[1], "evidenceType": "objectSelection"}]
            ),
            "evidence",
        ),
        (
            lesson_content(**MISSION),
            answer_key(
                questionEvaluations=[
                    {**evaluations()[1], "rubricCriterionIds": ["selects-described-object"]}
                ]
            ),
            "rubric criteria",
        ),
        (
            lesson_content(**MISSION),
            answer_key(questionEvaluations=[evaluations()[0], evaluations()[0]]),
            "cannot repeat",
        ),
        (
            lesson_content(**MISSION),
            answer_key(
                questionEvaluations=[{**evaluations()[0], "acceptedAnswers": ["La taza roja"]}]
            ),
            "existing answer key",
        ),
    ],
)
def test_mission_metadata_is_validated(content, key, message):
    with pytest.raises(ValidationError, match=message):
        mission_task(content=content, key=key)


def test_unkeyed_questions_need_accepted_answers_or_a_rubric():
    key = {"questionEvaluations": [{**evaluations()[1], "questionId": "task",
                                    "rubricCriterionIds": []}]}
    content = {
        "kind": "reflection", "prompt": "Describe the cup.", **MISSION,
    }
    with pytest.raises(ValidationError, match="accepted answer or rubric"):
        SessionTask(session_id=uuid4(), phase="ispy", kind="reflection", order_index=0,
                    public_content=content, answer_key=key)
    key["questionEvaluations"][0]["acceptedAnswers"] = ["La taza es roja."]
    task = SessionTask(session_id=uuid4(), phase="ispy", kind="reflection", order_index=0,
                       public_content=content, answer_key=key)
    assert task.answer_key.question_evaluations[0].question_id == "task"


def test_public_task_carries_mission_metadata_without_private_evaluation():
    task = mission_task()
    public = SessionTaskPublic.from_internal(
        task, mode=SessionMode.LESSON
    ).model_dump(mode="json", by_alias=True)
    assert {key: public["publicContent"][key] for key in MISSION} == MISSION
    serialized = str(public)
    for private in ["questionEvaluations", "correctOptionIds", "Taza is feminine", "wrongGender",
                    str(HIDDEN_WORD), str(HIDDEN_OBJECT), "describe-colour"]:
        assert private not in serialized
    stored = task.answer_key.model_dump(mode="json")
    assert stored["questionEvaluations"][0]["sceneObjectId"] == str(HIDDEN_OBJECT)
    assert SessionTask.model_validate(
        {**task.model_dump(mode="json"), "answerKey": stored}
    ).answer_key == task.answer_key


def test_review_details_add_outcomes_without_changing_results():
    task = mission_task()
    request = SubmitVocabularyReviewAttemptRequest(
        answers={"colour": "rojo", "build": "La taza es roja.", "extra": "taza"},
        question_assistance=[
            {"questionId": "build", "supports": ["translation", "wordBank"]},
            {"questionId": "extra", "supports": ["hint"]},
        ],
    )
    results = {"colour": False, "build": True, "extra": True}
    correct = task.answer_key.correct_option_ids
    details = review_details(task, request, results, correct)
    assert details["questionResults"] == results
    assert details["correctAnswers"] == correct
    outcomes = {item["questionId"]: item for item in details["questionOutcomes"]}
    assert outcomes["colour"] == {
        "questionId": "colour", "outcome": "incorrect",
        "objectiveId": "identify-describe-object", "targetIds": ["describe-colour"],
        "evidenceType": "recognition", "assistance": [], "assistanceUsed": False,
        "mistakes": [{
            "mistake": "wrongGender", "answer": "rojo", "correction": "La taza es roja.",
            "explanation": "Taza is feminine, so use roja.",
        }],
    }
    assert outcomes["build"]["outcome"] == "correct"
    assert outcomes["build"]["evidenceType"] == "construction"
    assert outcomes["build"]["assistance"] == ["translation", "wordBank"]
    assert outcomes["build"]["assistanceUsed"] is False
    assert outcomes["build"]["mistakes"] == []
    assert outcomes["extra"] == {
        "questionId": "extra", "outcome": "unassessed", "objectiveId": None, "targetIds": [],
        "evidenceType": "recognition", "assistance": ["hint"], "assistanceUsed": True,
        "mistakes": [],
    }
    wrong_order = review_details(
        task,
        request.model_copy(update={"answers": {**request.answers, "build": "Es la taza roja"}}),
        {**results, "build": False},
        correct,
    )
    assert wrong_order["questionOutcomes"][1]["mistakes"] == [{
        "mistake": "wordOrder", "answer": "Es la taza roja", "correction": "La taza es roja.",
        "explanation": "You have the right words in the wrong order.",
    }]


def test_correct_outcomes_explain_other_options_once_but_incorrect_outcomes_do_not():
    task = mission_task()
    evaluation = task.answer_key.question_evaluations[0]
    updated = evaluation.model_copy(update={
        "corrections": [
            CorrectionRule(
                mistake="wrongGender", answers=["rojo"], correction="La taza es roja.",
                explanation="Taza is feminine, so use roja.", note="Taza is feminine.",
            ),
            CorrectionRule(
                mistake="wrongGender", answers=["verde"], correction="La taza es roja.",
                explanation="Taza is feminine.",
            ),
            CorrectionRule(
                mistake="wrongGender", answers=["amarillo"], correction="La taza es roja.",
                explanation="The colour does not match.",
            ),
            CorrectionRule(
                mistake="wrongGender", answers=["azul"], correction="La taza es roja.",
                explanation="The circled object is a cup.", note="The circled object is a cup.",
            ),
            CorrectionRule(
                mistake="wrongGender", answers=["roja"], correction="La taza es roja.",
                explanation="The learner's answer is correct.",
            ),
        ],
        "correct_note": "The circled object is a cup.",
    })
    task.answer_key = task.answer_key.model_copy(
        update={"question_evaluations": [updated, *task.answer_key.question_evaluations[1:]]}
    )
    request = SubmitVocabularyReviewAttemptRequest(answers={"colour": "roja"})
    correct = review_details(task, request, {"colour": True}, {})
    assert correct["questionOutcomes"][0]["correctNote"] == "The circled object is a cup."
    assert correct["questionOutcomes"][0]["optionNotes"] == [
        "Taza is feminine.", "The colour does not match.",
    ]

    incorrect = review_details(
        task, request.model_copy(update={"answers": {"colour": "rojo"}}), {"colour": False}, {},
    )
    assert "optionNotes" not in incorrect["questionOutcomes"][0]
    assert "correctNote" not in incorrect["questionOutcomes"][0]


@pytest.mark.parametrize(
    ("answer", "expected"),
    [
        (
            "Un taxi es amarillo",
            "You have the right words in the wrong order. "
            "Start with the verb, then the object, then its colour.",
        ),
        (
            "Es un taxi rojo",
            "“rojo” doesn't belong here; the sentence needs “amarillo”.",
        ),
        ("Es un taxi", "You left out “amarillo”."),
        (
            "Un taxi es rojo",
            "“rojo” doesn't belong here; the sentence needs “amarillo”. "
            "Start with the verb, then the object, then its colour.",
        ),
    ],
)
def test_sentence_building_fallback_explains_word_differences(answer, expected):
    task = mission_task()
    explanation = "Start with the verb, then the object, then its colour."
    evaluation = task.answer_key.question_evaluations[1].model_copy(update={
        "corrections": [CorrectionRule(
            mistake="wordOrder", correction="Es un taxi amarillo.", explanation=explanation,
        )],
    })
    task.answer_key = task.answer_key.model_copy(update={
        "question_evaluations": [task.answer_key.question_evaluations[0], evaluation],
    })
    request = SubmitVocabularyReviewAttemptRequest(answers={"build": answer})
    details = review_details(task, request, {"build": False}, {})
    mistake = details["questionOutcomes"][1]["mistakes"][0]
    assert mistake["explanation"] == expected
    assert mistake["answer"] == answer
    assert mistake["correction"] == "Es un taxi amarillo."


def test_sentence_building_specific_answer_rules_keep_their_explanation():
    task = mission_task()
    evaluation = task.answer_key.question_evaluations[1].model_copy(update={
        "corrections": [
            CorrectionRule(
                mistake="pluralForm", answers=["Es un taxi rojo"],
                correction="Es un taxi amarillo.", explanation="Specific rule explanation.",
            ),
            CorrectionRule(
                mistake="wordOrder", correction="Es un taxi amarillo.",
                explanation="Generic rule explanation.",
            ),
        ],
    })
    task.answer_key = task.answer_key.model_copy(update={
        "question_evaluations": [task.answer_key.question_evaluations[0], evaluation],
    })
    request = SubmitVocabularyReviewAttemptRequest(answers={"build": "Es un taxi rojo"})
    details = review_details(task, request, {"build": False}, {})
    mistake = details["questionOutcomes"][1]["mistakes"][0]
    assert mistake["mistake"] == "pluralForm"
    assert mistake["explanation"] == "Specific rule explanation."


@pytest.mark.parametrize(
    ("outcome", "message"),
    [
        ({"outcome": "correct"}, "agree with questionResults"),
        ({"outcome": "correct", "mistakes": [
            {"mistake": "wrongWord", "correction": "la taza"}]}, "only incorrect"),
        ({"outcome": "incorrect", "objectiveId": None}, "require objectiveId"),
        ({"outcome": "incorrect", "assistanceUsed": True}, "assistanceUsed requires"),
    ],
)
def test_question_outcomes_are_consistent(outcome, message):
    base = {
        "questionId": "colour", "objectiveId": "identify-describe-object",
        "targetIds": ["describe-colour"], "evidenceType": "recognition",
    }
    with pytest.raises(ValidationError, match=message):
        QuestionReviewDetails.model_validate({
            "questionResults": {"colour": False},
            "questionOutcomes": [{**base, **outcome}],
        })


def test_legacy_review_details_and_requests_remain_valid():
    legacy = {"questionResults": {"a": True}, "correctAnswers": {"a": "x"}}
    assert QuestionReviewDetails.model_validate(legacy).model_dump(
        mode="json", by_alias=True
    ) == legacy
    assert QuestionReviewDetails.model_validate(
        {"questionResults": {"a": True}}
    ).correct_answers == {}
    request = SubmitVocabularyReviewAttemptRequest.model_validate({
        "inputMode": "vocabularyReview", "answers": {"a": "x"},
    })
    assert request.question_assistance is None
    with pytest.raises(ValidationError, match="cannot repeat"):
        SubmitVocabularyReviewAttemptRequest(
            answers={"a": "x"},
            question_assistance=[{"questionId": "a", "supports": ["hint", "hint"]}],
        )
