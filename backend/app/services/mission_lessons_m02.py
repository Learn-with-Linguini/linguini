"""Build the M02 A1 lesson task from confirmed objects, one relation and a validated result."""

from app.services.ispy_clue_frames import _place
from app.services.mission_eligibility import (
    POSITION_MEANINGS,
    REVIEWED_POSITIONS,
    confirmed_relations,
    relation_type,
)
from app.services.mission_lessons import build_mission_task, noun_gender
from app.services.session_plan import _with_article

M02_FOCUS = "askWhereItIs"
QUESTION_CHUNKS = {"es": "¿Dónde está…?", "fr": "Où est… ?"}
_QUESTION_FRAMES = {"es": "¿Dónde está {}?", "fr": "Où est {} ?"}
_LOCATION_VERBS = {"es": "está", "fr": "est"}
_EVALUATIONS = {
    "recogniseQuestion": (
        ["recognise-question", "name-object"],
        "recognition",
        ["question-chunk-correct", "article-matches-noun"],
    ),
    "buildQuestion": (
        ["build-question", "name-object"],
        "construction",
        ["question-names-object", "article-matches-noun"],
    ),
    "understandAnswer": (["understand-location"], "recognition", ["position-matches-photo"]),
}


def _capitalised(text):
    return f"{text[:1].upper()}{text[1:]}"


def m02_payload(mission, language, objects, relations, words, translated_scene):
    """Generation input holding confirmed objects and relations of one selected position."""
    language = language.lower()
    terms = {term.key: term for term in translated_scene.objects} if translated_scene else {}
    rows, places = {}, {}
    for obj, word in zip(objects, words, strict=True):
        term = terms.get(str(obj.id))
        phrase = _with_article(word.display_text, term)
        rows[obj.id] = dict(
            key=str(obj.id), source=obj.label, nounPhrase=phrase,
            whereQuestion=_QUESTION_FRAMES[language].format(phrase),
        )
        places[obj.id] = dict(
            article=term.article if term else None,
            gender=noun_gender(term, word),
            translation=word.display_text,
        )
    selected, found = None, []
    for relation in confirmed_relations(mission, objects, relations):
        if selected not in (None, relation_type(relation)):
            continue
        expression = REVIEWED_POSITIONS[relation_type(relation)][language]
        place = _place(language, expression, places[relation.reference_scene_object_id])
        if place is None:
            continue
        selected = relation_type(relation)
        subject = rows[relation.subject_scene_object_id]
        reference = rows[relation.reference_scene_object_id]
        meaning = POSITION_MEANINGS[relation_type(relation)]
        found.append(dict(
            key=str(relation.id),
            subjectKey=subject["key"],
            referenceKey=reference["key"],
            expression=expression,
            position=meaning,
            answer=f"{_capitalised(subject['nounPhrase'])} {_LOCATION_VERBS[language]} {place}.",
            meaning=f"The {subject['source']} is {meaning} the {reference['source']}.",
            wrongMeanings=[
                f"The {subject['source']} is {other} the {reference['source']}."
                for other in POSITION_MEANINGS.values() if other != meaning
            ][:3],
        ))
    pattern = {item.pattern_id: item for item in mission.language_patterns}
    return {
        "targetLanguage": language,
        "missionId": mission.mission_id,
        "practiceLevel": mission.practice_level,
        "contentVersion": mission.content_version,
        "objects": list(rows.values()),
        "relations": found,
        "languagePattern": {
            "questionChunk": QUESTION_CHUNKS[language],
            "questionExamples": list(pattern["where-question"].examples.get(language, [])),
            "answerExamples": list(pattern["location-answer"].examples.get(language, [])),
            "expression": found[0]["expression"] if found else None,
            "position": found[0]["position"] if found else None,
        },
    }


def _corrections(payload, question, correct_label):
    if question.purpose == "buildQuestion":
        return [dict(
            mistake="wordOrder",
            correction=question.correct_text,
            explanation="Start with the question words, then the object.",
        )]
    relation = next(
        (row for row in payload["relations"] if row["key"] == question.relation_key), None
    )
    if question.purpose == "recogniseQuestion":
        mistake = "wrongObject"
        explanation = "That question asks about another object in your photo."
    else:
        mistake = "wrongPosition"
        explanation = f"\u201c{relation['expression']}\u201d means {relation['position']}."
    return [
        dict(
            mistake=mistake, answers=[option.option_id], correction=correct_label,
            explanation=explanation,
        )
        for option in question.options
        if option.option_id != question.correct_option_id
    ]


def m02_lesson_task(session_id, mission, payload, result, vocabulary_ids):
    """The M02 lesson task from a validated result."""

    def evaluate(question, label):
        target_ids, evidence_type, criteria = _EVALUATIONS[question.purpose]
        vocabulary_id = vocabulary_ids.get(question.object_key)
        names_object = question.purpose != "understandAnswer"
        return dict(
            target_ids=target_ids,
            evidence_type=evidence_type,
            rubric_criterion_ids=criteria,
            vocabulary_item_ids=[vocabulary_id] if vocabulary_id and names_object else [],
            corrections=_corrections(payload, question, label),
        )

    return build_mission_task(session_id, mission, M02_FOCUS, result, evaluate)
