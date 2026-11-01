"""The M06 A2 request lesson: transaction choice, scenario helpers and tasks."""

import random
from uuid import UUID, uuid5

from app.ai.features.learning_tasks.mission_m06 import MissionM06Result
from app.schemas.tasks import (
    GrammarLessonContent,
    GrammarLessonQuestion,
    MissionScenario,
    MissionScenarioAlternative,
    QuestionEvaluation,
    SessionTask,
    TaskAnswerKey,
)
from app.services.lesson_tasks.common import mission_fields

ENGLISH_NUMBER = {1: "one", 2: "two", 3: "three"}


ENGLISH_SIZE = {"small": "small", "large": "large"}


SCENARIO_PROMPTS = {
    "cafeDrink": "Practise ordering this drink at a café.",
    "cafeFood": "Practise ordering this food at a café.",
    "shop": "Practise buying this at a shop.",
    "classroom": "Imagine you need to borrow this pen.",
    "home": "Imagine you ask someone at home to pass you this.",
}


def scenario_of(item):
    return {
        "cafe": "cafeDrink" if item.key in {"coffee", "tea", "juice"} else "cafeFood",
        "shop": "shop",
        "classroom": "classroom",
        "home": "home",
    }[item.category]


def quantity_choices(scenario):
    return (2, 3) if scenario in {"cafe", "shop"} else (1, 2)


def select_transaction(session_id, item, language):
    """Choose every role-play detail from the stable session/item seed."""
    rng = random.Random(f"{session_id}:M06:{item.key}")
    scenario = item.category
    quantity = rng.choice(quantity_choices(scenario))
    size = (
        rng.choice(("small", "large"))
        if scenario == "cafe"
        and item.key
        in {
            "coffee",
            "tea",
            "juice",
        }
        else None
    )
    if scenario == "cafe":
        follow_type = (
            rng.choice(("serviceSetting", "temperature"))
            if item.key
            in {
                "coffee",
                "tea",
            }
            else "serviceSetting"
        )
    elif scenario == "shop":
        follow_type = "size"
    else:
        follow_type = "colour"
    choices = {
        "serviceSetting": ("eatIn", "takeAway"),
        "temperature": ("hot", "cold"),
        "size": ("big", "small"),
        "colour": ("blue", "red", "black"),
    }[follow_type]
    value = rng.choice(choices)
    service_setting = (
        (value if follow_type == "serviceSetting" else rng.choice(("eatIn", "takeAway")))
        if scenario == "cafe"
        else None
    )
    mismatch = rng.random() < 0.5
    mismatch_fields = ["quantity", follow_type]
    if size:
        mismatch_fields.append("size")
    mismatch_field = rng.choice(mismatch_fields) if mismatch else None
    if mismatch_field == "quantity":
        served_value = next(number for number in quantity_choices(scenario) if number != quantity)
        corrected_value = quantity
    elif mismatch_field == "size" and size:
        served_value = "large" if size == "small" else "small"
        corrected_value = size
    elif mismatch_field:
        served_value = next(candidate for candidate in choices if candidate != value)
        corrected_value = value
    else:
        served_value = corrected_value = None
    follow_up = dict(type=follow_type, value=value)
    request_details = {}
    if size:
        request_details["size"] = size
    return {
        "missionId": "M06",
        "contentVersion": 1,
        "itemKey": item.key,
        "scenario": scenario,
        "serviceSetting": service_setting,
        "quantity": quantity,
        "requestDetails": request_details,
        "followUp": follow_up,
        "requestPattern": scenario,
        "mismatch": {
            "flag": mismatch,
            "field": mismatch_field,
            "servedValue": served_value,
            "correctedValue": corrected_value,
        },
        "seed": f"{session_id}:M06:{item.key}",
    }


def order_label(quantity, item, size=None):
    count = ENGLISH_NUMBER[quantity]
    parts = [count]
    if size:
        parts.append(ENGLISH_SIZE[size])
    label = item.label
    if quantity != 1 and not label.endswith("s"):
        label += "s"
    return " ".join((*parts, label))


def opposite_value(kind, value):
    return {
        "serviceSetting": {"eatIn": "takeAway", "takeAway": "eatIn"},
        "temperature": {"hot": "cold", "cold": "hot"},
        "size": {"big": "small", "small": "big"},
        "colour": {"blue": "red", "red": "black", "black": "blue"},
    }[kind][value]


def build_m06_tasks(session_id, mission, payload, result, _vocabulary_ids=None):
    """Return both contiguous M06 grammar tasks with stable namespace ids."""
    questions = result.questions if isinstance(result, MissionM06Result) else result["questions"]
    validate_questions = questions
    transaction = payload["transaction"]
    primary_id = UUID(transaction["sceneObjectId"])
    scenario = MissionScenario(
        scenario_id=f"m06-{transaction['itemKey']}",
        prompt=payload["scenarioPrompt"],
        scene_object_id=primary_id,
        item_label=transaction["itemLabel"],
        accepted=bool(transaction.get("scenarioAccepted", False)),
        alternatives=[
            MissionScenarioAlternative(
                scene_object_id=UUID(item["sceneObjectId"]), label=item["label"]
            )
            for item in transaction.get("alternatives", [])
        ],
    )
    task_ids = [
        uuid5(session_id, "mission:M06-A2.v1:lesson"),
        uuid5(session_id, "mission:M06-A2.v1:lesson-2"),
    ]
    built = []
    for task_index, task_questions in enumerate((validate_questions[:3], validate_questions[3:])):
        private_answers = {}
        distractors = {}
        option_order = {}
        gap_kinds = {}
        evaluations = []
        public_questions = []
        for question in task_questions:
            answer = (
                question.correct_option_id
                if question.interaction_type == "multipleChoice"
                else question.correct_text
            )
            private_answers[question.question_id] = {
                "correct": answer,
                "accepted": question.accepted_answers,
                "chunks": question.correct_chunks,
                "model": question.correct_text
                or next(
                    (
                        option.label
                        for option in question.options
                        if option.option_id == question.correct_option_id
                    ),
                    None,
                ),
            }
            distractors[question.question_id] = question.distractor_fields
            option_order[question.question_id] = [item.option_id for item in question.options]
            gap_kinds[question.question_id] = question.gap_kind
            public_questions.append(
                GrammarLessonQuestion(
                    question_id=question.question_id,
                    prompt=question.prompt,
                    interaction_type=question.interaction_type,
                    options=question.options,
                    token_bank=question.token_bank,
                    translation=question.translation,
                    audio_text=question.audio_text,
                    listen_first=question.listen_first,
                    slot_template=question.slot_template,
                    complete_chunk=question.complete_chunk,
                    gap_kind=question.gap_kind,
                    assistance_steps=question.assistance_steps,
                    dialogue=question.dialogue,
                    allow_retry=question.allow_retry,
                    wrong_field_tokens=question.distractor_fields,
                    section=(
                        "Task 1 · Place the order"
                        if task_index == 0
                        else "Task 2 · Finish the order"
                    ),
                )
            )
            evaluations.append(
                QuestionEvaluation(
                    question_id=question.question_id,
                    objective_id=mission.objective.objective_id,
                    target_ids=[question.target_id],
                    evidence_type=question.evidence_type,
                    scene_object_id=primary_id,
                )
            )
        mission_state = {
            "transaction": transaction,
            "answers": private_answers,
            "distractorFields": distractors,
            "optionOrder": option_order,
            "gapKinds": gap_kinds,
            "q5Mode": payload["q5Mode"],
            "scenarioAccepted": bool(transaction.get("scenarioAccepted", False)),
        }
        content = GrammarLessonContent(
            focus="sceneMissionM06A2",
            title="Ask for the details",
            questions=public_questions,
            check_each_question=True,
            scenario=scenario if task_index == 0 else None,
            **mission_fields(mission),
        )
        task = SessionTask(
            id=task_ids[task_index],
            session_id=session_id,
            phase="learning",
            kind="grammarLesson",
            order_index=task_index,
            public_content=content,
            answer_key=TaskAnswerKey(
                correct_option_ids={
                    q.question_id: (
                        q.correct_option_id
                        if q.interaction_type == "multipleChoice"
                        else q.correct_text
                    )
                    for q in task_questions
                },
                question_evaluations=evaluations,
                mission_state=mission_state,
            ),
            scene_object_id=primary_id,
        )
        built.append(task)
    return built
