"""Build the M02 A1 lesson tasks from confirmed objects, relations and a validated result."""

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
_YES_NO = {"es": {"yes": "Sí", "no": "No"}, "fr": {"yes": "Oui", "no": "Non"}}
# Positions that a confirmed position rules out for the same pair.
_OPPOSITE = {"on": "under", "under": "on", "in_front_of": "behind", "behind": "in_front_of"}
_INVERSE = {
    "on": "under", "under": "on", "next_to": "next_to",
    "in_front_of": "behind", "behind": "in_front_of",
}
# Prompts never contain the sentence the learner builds.
_PROMPTS = {
    "es": {
        "choosePosition": "Elige la posición: {subject} ___ {reference}.",
        "describeLocation": "Describe la posición {of_subject}.",
        "askWhere": "Pregunta por la ubicación {of_subject}.",
        "checkAnswer": "\u201c{proposal}\u201d ¿Coincide con la foto?",
    },
    "fr": {
        "choosePosition": "Choisis la position : {subject} ___ {reference}.",
        "describeLocation": "Décris la position {of_subject}.",
        "askWhere": "Pose une question sur l'emplacement {of_subject}.",
        "checkAnswer": "\u00ab {proposal} \u00bb Est-ce que ça correspond à la photo ?",
    },
}
_TRANSLATIONS = {
    "choosePosition": "Choose the position: the {subject} ___ the {reference}.",
    "describeLocation": "Describe the position of the {subject}.",
    "askWhere": "Ask where the {subject} is.",
    "checkAnswer": "Does this match the photo?",
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
    "checkAnswer": (["understand-location"], "recognition", ["answer-matches-photo"]),
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


def _definite_phrase(language, place):
    article = _definite(language, place)
    return _with_article(article, place["translation"]) if article else None


def _of(language, place):
    """\u201cof the object\u201d, contracted where the language requires it (del, du)."""
    article = _definite(language, place)
    contracted = CONTRACTIONS[language].get(("de", article.casefold()))
    if contracted:
        return f"{contracted} {place['translation']}"
    return f"de {_with_article(article, place['translation'])}"


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
    """The least familiar relation, and another pair or position for the answer check."""
    if not found:
        return []
    ranked = sorted(found, key=lambda row: familiarity(row["expression"]))
    first = ranked[0]
    pair = {first["subjectKey"], first["referenceKey"]}
    others = ranked[1:]
    second = next(
        (row for row in others if {row["subjectKey"], row["referenceKey"]} != pair),
        next((row for row in others if row["position"] != first["position"]), None),
    )
    return [first["key"]] if second is None else [first["key"], second["key"]]


def _statement(language, subject, position, place):
    split = _place_tiles(language, REVIEWED_POSITIONS[position][language], place)
    if split is None:
        return None
    phrase_tile, tail = split
    return [
        *tokens(_capitalised(subject["nounPhrase"])), _LOCATION_VERBS[language], phrase_tile,
        *tail, ".",
    ]


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
        reference_place = places[relation.reference_scene_object_id]
        statement_tiles = _statement(language, subject, kind, reference_place)
        place = " ".join([phrase_tile, _joined(tail)])
        true_positions = _true_positions(
            relation.subject_scene_object_id, relation.reference_scene_object_id, usable,
        )
        extra = next(
            row["expression"] for row in positions if row["position"] not in true_positions
        )
        pronoun = _prefixes(language, subject["gender"])["location"]
        reference = rows[relation.reference_scene_object_id]
        answer = f"{pronoun} {place}." if pronoun != "C'est" else _joined(statement_tiles)
        subject_place = places[relation.subject_scene_object_id]
        if _definite(language, subject_place) is None:
            continue
        contradicted = sorted(
            {_OPPOSITE[p] for p in true_positions if p in _OPPOSITE} - true_positions
        )
        check = dict(proposal=_joined(statement_tiles), position=kind)
        if contradicted and relation.id.int % 2:
            check = dict(
                proposal=_joined(_statement(language, subject, contradicted[0], reference_place)),
                position=contradicted[0],
            )
        prompts = {
            purpose: template.format(
                subject=_definite_phrase(language, subject_place),
                reference=_definite_phrase(language, reference_place),
                of_subject=_of(language, subject_place),
                proposal=check["proposal"],
            )
            for purpose, template in _PROMPTS[language].items()
        }
        found.append(dict(
            key=str(relation.id),
            subjectKey=subject["key"], subjectSource=subject["source"],
            referenceKey=reference["key"], referenceSource=reference["source"],
            position=kind, expression=expression,
            truePositions=sorted(true_positions),
            contradicted=contradicted,
            check=check,
            statement=_joined(statement_tiles),
            statementTiles=statement_tiles,
            extraTile=extra,
            whereQuestion=subject["whereQuestion"],
            answer=answer,
            prompts=prompts,
        ))
    known = (progress or {}).get("terms", {})
    return {
        "targetLanguage": language,
        "missionId": mission.mission_id,
        "practiceLevel": mission.practice_level,
        "contentVersion": mission.content_version,
        "questionChunk": QUESTION_CHUNKS[language],
        "positions": positions,
        "yesNo": _YES_NO[language],
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
    if question.purpose == "checkAnswer":
        return [dict(
            mistake="wrongPosition", answers=[option.option_id], correction=relation["statement"],
            explanation=f"The photo shows: {relation['statement']}",
        ) for option in question.options if option.option_id != question.correct_option_id]
    corrections = []
    for option in question.options:
        if option.option_id == question.correct_option_id:
            continue
        chosen = by_text[fold(option.label)]
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
    """The M02 lesson task: its three or four questions in order, from a validated result."""
    relations = {row["key"]: row for row in payload["relations"]}

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
        translation = _TRANSLATIONS[question.purpose].format(
            subject=relation["subjectSource"], reference=relation["referenceSource"],
        )
        fields = dict(
            scene_object_id=question.object_key, object_label=subject,
            prompt_translation=translation,
        )
        if question.purpose != "askWhere":
            fields.update(reference_object_id=relation["referenceKey"], reference_label=reference)
        return fields

    return build_mission_task(session_id, mission, M02_FOCUS, result, evaluate, shown)
