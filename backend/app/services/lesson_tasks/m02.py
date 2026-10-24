"""The M02 A1 lesson task: grading, corrections and shown fields."""

from app.ai.features.learning_tasks.mission import fold
from app.services.lesson_tasks.common import build_mission_task, definite

M02_FOCUS = "findAndLocate"


_TRANSLATIONS = {
    "findObject": "Tap the numbered marker on the object this sentence describes.",
    "chooseLocation": "Choose where it is in the photo.",
    "askWhere": "Ask where the {subject} is.",
    "answerWhere": "Answer with the position the photo shows.",
}


_EVALUATIONS = {
    "findObject": (["understand-location"], "recognition", ["answer-matches-photo"]),
    "chooseLocation": (["recognise-position"], "recognition", ["position-matches-photo"]),
    "askWhere": (
        ["build-question", "name-object"],
        "construction",
        ["question-names-object", "article-matches-noun"],
    ),
    "answerWhere": (
        ["describe-location", "name-object"],
        "construction",
        ["statement-in-order", "article-matches-noun"],
    ),
}


def capitalised(text):
    return f"{text[:1].upper()}{text[1:]}"


def _corrections(payload, question, label):
    relation = next(row for row in payload["relations"] if row["key"] == question.relation_key)
    wrong = [
        option for option in question.options if option.option_id != question.correct_option_id
    ]
    if question.purpose == "answerWhere":
        return [
            dict(
                mistake="wrongPosition", answers=[relation["contradiction"]],
                correction=question.correct_text,
                explanation=(
                    f"The photo shows the {relation['subjectSource']} {relation['meaning']} "
                    f"the {relation['referenceSource']}."
                ),
            ),
            dict(
                mistake="wordOrder", correction=question.correct_text,
                explanation="Say the object, then the verb, the position and the other object.",
            ),
        ], None
    if question.purpose == "askWhere":
        return [dict(
            mistake="wordOrder", correction=question.correct_text,
            explanation="Start with the question words, then the object.",
        )], None
    if question.purpose == "findObject":
        sources = {row["key"]: row["source"] for row in payload["markers"]}
        correct_note = f"Marker {label} is {definite(relation['subjectSource'])}."
        rules = []
        for option in wrong:
            source = sources[question.marker_keys[option.option_id]]
            rules.append(dict(
                mistake="wrongObject", answers=[option.option_id], correction=label,
                note=f"Marker {option.label} is {definite(source)}.",
                explanation=(
                    f"Marker {option.label} is {definite(source)}; the sentence describes "
                    f"{definite(relation['subjectSource'])} (marker {label})."
                ),
            ))
        return rules, correct_note
    meanings = {row["position"]: row["meaning"] for row in payload["positions"]}
    places = {fold(row["label"]): row["position"] for row in relation["placeOptions"]}
    correct_note = capitalised(
        f"{definite(relation['subjectSource'])} is {relation['meaning']} "
        f"{definite(relation['referenceSource'])}."
    )
    rules = []
    for option in wrong:
        meaning = meanings[places[fold(option.label)]]
        note = f"“{option.label}” means {meaning} {definite(relation['referenceSource'])}."
        rules.append(dict(
            mistake="wrongPosition", answers=[option.option_id], correction=label,
            note=note,
            explanation=f"{note[:-1]}; {correct_note[0].lower()}{correct_note[1:]}",
        ))
    return rules, correct_note


def m02_lesson_task(session_id, mission, payload, result, vocabulary_ids):
    """The M02 lesson task: four questions on one confirmed relation, from a validated result."""
    relations = {row["key"]: row for row in payload["relations"]}

    def evaluate(question, label):
        target_ids, evidence_type, criteria = _EVALUATIONS[question.purpose]
        relation = relations[question.relation_key]
        corrections, correct_note = _corrections(payload, question, label)
        named = {
            "answerWhere": [relation["subjectKey"], relation["referenceKey"]],
            "askWhere": [relation["subjectKey"]],
        }.get(question.purpose, [])
        return dict(
            target_ids=target_ids,
            evidence_type=evidence_type,
            rubric_criterion_ids=criteria,
            vocabulary_item_ids=[vocabulary_ids[key] for key in named if key in vocabulary_ids],
            corrections=corrections,
            correct_note=correct_note,
        )

    def shown(question):
        relation = relations[question.relation_key]
        fields = dict(
            section=question.section,
            prompt_translation=_TRANSLATIONS[question.purpose].format(
                subject=relation["subjectSource"],
            ),
        )
        if question.purpose == "findObject":
            # No highlight: the learner finds the object from the sentence.
            return dict(fields, marker_object_ids=question.marker_keys, keep_option_order=True)
        fields.update(
            scene_object_id=question.object_key,
            object_label=capitalised(relation["subjectSource"]),
        )
        if question.purpose != "askWhere":
            fields.update(
                reference_object_id=relation["referenceKey"],
                reference_label=capitalised(relation["referenceSource"]),
            )
        if question.interaction_type == "multipleChoice":
            fields["keep_option_order"] = True
        return fields

    return build_mission_task(session_id, mission, M02_FOCUS, result, evaluate, shown)
