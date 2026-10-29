"""The M01 A1 lesson task: grading, corrections and shown fields."""

from app.ai.features.learning_tasks.mission import fold
from app.ai.features.learning_tasks.mission_m01 import capitalised, description
from app.services.lesson_tasks.common import build_mission_task, definite

M01_FOCUS = "identifyDescribeObject"


PROMPT_TRANSLATIONS = {
    "confirmObject": "Is it this? Answer with a full sentence.",
    "describeObject": "Describe this object.",
}


_EVALUATIONS = {
    "confirmObject": (
        ["identify-object", "name-object"],
        "recognition",
        ["selects-described-object", "article-matches-noun"],
    ),
    "chooseAttribute": (["describe-colour"], "recognition", ["colour-matches-photo"]),
    "describeObject": (
        ["name-object", "describe-colour"],
        "construction",
        ["article-matches-noun", "colour-matches-photo"],
    ),
}


def _corrections(payload, question, correct_label):
    pairs = {pair["key"]: pair for pair in payload["pairs"]}
    pair = pairs[question.object_key]
    wrong = [
        option for option in question.options if option.option_id != question.correct_option_id
    ]
    if question.purpose == "describeObject":
        if "packCorrections" in payload:
            return payload["packCorrections"], None
        rules = [dict(
            mistake="wordOrder",
            correction=question.correct_text,
            explanation=(
                "Start with the verb, then the object and its detail"
                + (" (this word goes before the noun)." if pair["before"] else ".")
            ),
        )]
        for form in payload["describeExtras"]:
            rules.insert(0, dict(
                mistake="wrongGender",
                answers=[description(payload, {**pair, "agreedForm": form})],
                correction=question.correct_text,
                explanation=f"The word agrees with {pair['nounPhrase']}: {pair['agreedForm']}.",
            ))
        return rules, None
    if question.purpose == "confirmObject":
        correct_note = f"This is {pair['nounPhrase']} ({pair['source']})."
        explanation = (
            f"Yes — this is {pair['nounPhrase']} ({pair['source']})."
            if question.statement_correct
            else f"No — this is {pair['nounPhrase']} ({pair['source']})."
        )
        return [dict(
            mistake="wrongObject", answers=[option.option_id], correction=correct_label,
            explanation=explanation, note=correct_note,
        ) for option in wrong], correct_note
    correct_note = capitalised(
        f"{definite(pair['source'])} is {pair['attributeSource']}: {pair['agreedForm']}."
    )
    meanings = payload.get("attributeMeanings", {})
    rules = []
    for option in wrong:
        meaning = meanings.get(fold(option.label))
        note = f"“{option.label}” means {meaning}." if meaning else None
        explanation = (
            f"“{option.label}” means {meaning}; {definite(pair['source'])} is "
            f"{pair['attributeSource']}: {pair['agreedForm']}."
            if meaning else correct_note
        )
        rules.append(dict(
            mistake="wrongColour" if pair["attributeType"] == "colour" else "wrongAttribute",
            answers=[option.option_id], correction=correct_label,
            explanation=explanation, note=note,
        ))
    return rules, correct_note


def m01_lesson_task(session_id, mission, payload, result, vocabulary_ids):
    """The M01 lesson task; Task 2 questions also show the object's English label."""
    labels = {pair["key"]: pair["source"] for pair in payload["pairs"]}

    def evaluate(question, label):
        target_ids, evidence_type, criteria = _EVALUATIONS[question.purpose]
        vocabulary_id = vocabulary_ids.get(question.object_key)
        assessed = vocabulary_id and question.purpose != "chooseAttribute"
        corrections, correct_note = _corrections(payload, question, label)
        return dict(
            target_ids=target_ids,
            evidence_type=evidence_type,
            rubric_criterion_ids=criteria,
            vocabulary_item_ids=[vocabulary_id] if assessed else [],
            corrections=corrections,
            correct_note=correct_note,
        )

    def shown(question):
        fields = dict(
            section=question.section,
            scene_object_id=question.object_key,
            prompt_translation=(
                payload["attributePromptTranslation"] if question.purpose == "chooseAttribute"
                else PROMPT_TRANSLATIONS[question.purpose]
            ),
        )
        if question.purpose in {"chooseAttribute", "describeObject"}:
            fields["object_label"] = capitalised(labels[question.object_key])
        if question.interaction_type == "multipleChoice":
            fields["keep_option_order"] = True
        return fields

    task = build_mission_task(session_id, mission, M01_FOCUS, result, evaluate, shown)
    statements = {
        question.question_id: question.statement_correct
        for question in result.questions if question.statement_correct is not None
    }
    return task.model_copy(update={
        "answer_key": task.answer_key.model_copy(update={"statement_correct": statements}),
    })
