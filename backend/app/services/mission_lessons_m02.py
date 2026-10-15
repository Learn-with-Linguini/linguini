"""Build the M02 A1 lesson tasks from confirmed objects, relations and a validated result."""

from types import SimpleNamespace

from app.ai.features.learning_tasks.mission import fold, tokens
from app.ai.features.learning_tasks.mission_m02 import _joined
from app.services.ispy_clue_frames import CONTRACTIONS, _definite, _prefixes, _with_article
from app.services.mission_eligibility import (
    POSITION_MEANINGS,
    REVIEWED_POSITIONS,
    confirmed_relations,
    relation_type,
)
from app.services.mission_lessons import build_mission_task, noun_gender
from app.services.session_plan import _with_article as _noun_phrase

M02_FOCUS = "findAndLocate"
QUESTION_CHUNKS = {"es": "¿Dónde está…?", "fr": "Où est… ?"}
_QUESTION_FRAMES = {"es": "¿Dónde está {}?", "fr": "Où est {} ?"}
_LOCATION_VERBS = {"es": "está", "fr": "est"}
_INVERSE = {
    "on": "under", "under": "on", "next_to": "next_to",
    "in_front_of": "behind", "behind": "in_front_of",
}
_PARTS = {
    "choosePosition": ("Describe the location · Part 1 of 2", "lesson-1a"),
    "describeLocation": ("Describe the location · Part 2 of 2", "lesson-1b"),
    "askWhere": ("Ask and understand · Part 1 of 2", "lesson-2a"),
    "understandAnswer": ("Ask and understand · Part 2 of 2", "lesson-2b"),
}
_EVALUATIONS = {
    "choosePosition": (["recognise-position"], "recognition", ["position-matches-photo"]),
    "describeLocation": (
        ["describe-location", "name-object"],
        "construction",
        ["statement-in-order", "article-matches-noun"],
    ),
    "askWhere": (
        ["build-question", "name-object"],
        "construction",
        ["question-names-object", "article-matches-noun"],
    ),
    "understandAnswer": (["understand-location"], "recognition", ["answer-matches-diagram"]),
}


def _capitalised(text):
    return f"{text[:1].upper()}{text[1:]}"


def _place_tiles(language, expression, place):
    """The position phrase as one tile (with any contraction) and the reference noun tiles."""
    article = _definite(language, place)
    if not article:
        return None
    words = expression.split()
    contracted = CONTRACTIONS[language].get((words[-1].casefold(), article.casefold()))
    if contracted:
        return " ".join([*words[:-1], contracted]), tokens(place["translation"])
    return expression, tokens(_with_article(article, place["translation"]))


def _true_positions(subject, reference, relations):
    found = set()
    for relation in relations:
        kind = relation_type(relation)
        pair = (relation.subject_scene_object_id, relation.reference_scene_object_id)
        if pair == (subject, reference):
            found.add(kind)
        elif pair == (reference, subject) and kind in _INVERSE:
            found.add(_INVERSE[kind])
    return found


def _select(found, familiarity):
    """The least familiar relation, then preferably another pair or position for Task 2."""
    if not found:
        return []
    ranked = sorted(found, key=lambda row: familiarity(row["expression"]))
    first = ranked[0]
    pair = {first["subjectKey"], first["referenceKey"]}
    others = ranked[1:]
    second = next(
        (row for row in others if {row["subjectKey"], row["referenceKey"]} != pair),
        next((row for row in others if row["position"] != first["position"]), first),
    )
    return [first["key"], second["key"]]


def m02_payload(mission, language, objects, relations, words, translated_scene, progress=None):
    """Confirmed relations with reviewed forms, and the two selected for the lesson."""
    language = language.lower()
    terms = {term.key: term for term in translated_scene.objects} if translated_scene else {}
    rows, places = {}, {}
    for obj, word in zip(objects, words, strict=True):
        term = terms.get(str(obj.id))
        phrase = _noun_phrase(word.display_text, term)
        rows[obj.id] = dict(
            key=str(obj.id), source=obj.label, nounPhrase=phrase,
            hasArticle=bool(term and term.article),
            whereQuestion=_QUESTION_FRAMES[language].format(phrase),
            gender=noun_gender(term, word),
        )
        places[obj.id] = dict(
            article=term.article if term else None,
            gender=noun_gender(term, word),
            translation=word.display_text,
        )
    positions = [
        dict(position=key, expression=REVIEWED_POSITIONS[key][language], meaning=meaning)
        for key, meaning in POSITION_MEANINGS.items()
    ]
    usable = confirmed_relations(mission, objects, relations)
    found = []
    for relation in usable:
        kind = relation_type(relation)
        subject = rows[relation.subject_scene_object_id]
        expression = REVIEWED_POSITIONS[kind][language]
        split = _place_tiles(language, expression, places[relation.reference_scene_object_id])
        if split is None or not subject["hasArticle"]:
            continue
        phrase_tile, tail = split
        verb = _LOCATION_VERBS[language]
        statement_tiles = [
            *tokens(_capitalised(subject["nounPhrase"])), verb, phrase_tile, *tail, ".",
        ]
        place = " ".join([phrase_tile, _joined(tail)])
        true_positions = _true_positions(
            relation.subject_scene_object_id, relation.reference_scene_object_id, usable,
        )
        extra = next(
            row["expression"] for row in positions if row["position"] not in true_positions
        )
        pronoun = _prefixes(language, subject["gender"])["location"]
        reference = rows[relation.reference_scene_object_id]
        found.append(dict(
            key=str(relation.id),
            subjectKey=subject["key"], subjectSource=subject["source"],
            referenceKey=reference["key"], referenceSource=reference["source"],
            position=kind, expression=expression,
            truePositions=sorted(true_positions),
            statement=_joined(statement_tiles),
            statementTiles=statement_tiles,
            extraTile=extra,
            whereQuestion=subject["whereQuestion"],
            answer=(f"{pronoun} {place}." if pronoun != "C'est" else _joined(statement_tiles)),
        ))
    known = (progress or {}).get("terms", {})
    return {
        "targetLanguage": language,
        "missionId": mission.mission_id,
        "practiceLevel": mission.practice_level,
        "contentVersion": mission.content_version,
        "questionChunk": QUESTION_CHUNKS[language],
        "positions": positions,
        "relations": found,
        "selected": _select(found, lambda expression: known.get(fold(expression), 0.0)),
    }


def _corrections(payload, question, label):
    relation = next(row for row in payload["relations"] if row["key"] == question.relation_key)
    phrases = {row["position"]: row for row in payload["positions"]}
    by_text = {fold(row["expression"]): row for row in payload["positions"]}
    if question.purpose == "describeLocation":
        return [dict(
            mistake="wordOrder", correction=question.correct_text,
            explanation="Say the object first, then the verb, the position and the other object.",
        )]
    if question.purpose == "askWhere":
        return [dict(
            mistake="wordOrder", correction=question.correct_text,
            explanation="Start with the question words, then the object.",
        )]
    corrections = []
    for option in question.options:
        if option.option_id == question.correct_option_id:
            continue
        chosen = (
            by_text[fold(option.label)] if question.purpose == "choosePosition"
            else phrases[option.option_id]
        )
        corrections.append(dict(
            mistake="wrongPosition", answers=[option.option_id], correction=label,
            explanation=(
                f"\u201c{chosen['expression']}\u201d means {chosen['meaning']}; the "
                f"{relation['subjectSource']} is {phrases[relation['position']]['meaning']} "
                f"the {relation['referenceSource']}."
            ),
        ))
    return corrections


def m02_lesson_task(session_id, mission, payload, result, vocabulary_ids):
    """The four M02 part tasks, in order, from a validated result."""
    relations = {row["key"]: row for row in payload["relations"]}
    verb = _LOCATION_VERBS[payload["targetLanguage"]]
    explanations = {
        "choosePosition": result.explanation,
        "describeLocation": f"Now say it in a full sentence: the object, \u201c{verb}\u201d, "
        "the position, then the other object.",
        "askWhere": f"Ask where something is with \u201c{payload['questionChunk']}\u201d "
        "and the object.",
        "understandAnswer": "Read the answer, then choose the picture that shows it.",
    }

    def evaluate(question, label):
        target_ids, evidence_type, criteria = _EVALUATIONS[question.purpose]
        relation = relations[question.relation_key]
        named = {
            "describeLocation": [relation["subjectKey"], relation["referenceKey"]],
            "askWhere": [relation["subjectKey"]],
        }.get(question.purpose, [])
        return dict(
            target_ids=target_ids,
            evidence_type=evidence_type,
            rubric_criterion_ids=criteria,
            vocabulary_item_ids=[vocabulary_ids[key] for key in named if key in vocabulary_ids],
            corrections=_corrections(payload, question, label),
        )

    def shown(question):
        relation = relations[question.relation_key]
        subject = _capitalised(relation["subjectSource"])
        reference = _capitalised(relation["referenceSource"])
        if question.purpose == "understandAnswer":
            return dict(object_label=subject, reference_label=reference, diagram_options=True)
        fields = dict(scene_object_id=question.object_key, object_label=subject)
        if question.purpose != "askWhere":
            fields.update(reference_object_id=relation["referenceKey"], reference_label=reference)
        return fields

    tasks = []
    for question in result.questions:
        title, key = _PARTS[question.purpose]
        part = SimpleNamespace(
            title=title, explanation=explanations[question.purpose], questions=[question],
        )
        tasks.append(build_mission_task(
            session_id, mission, M02_FOCUS, part, evaluate, shown, key=key,
        ))
    return tasks
