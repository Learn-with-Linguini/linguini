"""Build the M02 A1 lesson task from confirmed objects, relations and a validated result."""

import random
import re

from app.ai.features.learning_tasks.mission import fold, tokens
from app.ai.features.learning_tasks.mission_m02 import _joined
from app.services.ispy_clue_frames import CONTRACTIONS, _definite, _with_article
from app.services.mission_eligibility import (
    POSITION_MEANINGS,
    REVIEWED_POSITIONS,
    confirmed_relations,
    relation_type,
)
from app.services.mission_lessons import build_mission_task, definite, mission_gender

M02_FOCUS = "findAndLocate"
QUESTION_CHUNKS = {"es": "¿Dónde está…?", "fr": "Où est… ?"}
_QUESTION_FRAMES = {"es": "¿Dónde está {}?", "fr": "Où est {} ?"}
_LOCATION_VERBS = {"es": "está", "fr": "est"}
# Positions that a confirmed position rules out for the same pair.
_OPPOSITE = {"on": "under", "under": "on", "in_front_of": "behind", "behind": "in_front_of"}
_INVERSE = {
    "on": "under", "under": "on", "next_to": "next_to",
    "in_front_of": "behind", "behind": "in_front_of",
}
# Prompts never contain the sentence the learner builds.
_PROMPTS = {
    "es": {
        "askWhere": "Pregunta por la ubicación {of_subject}.",
        "answerWhere": "Responde con la posición que muestra la foto.",
    },
    "fr": {
        "askWhere": "Pose une question sur l'emplacement {of_subject}.",
        "answerWhere": "Réponds avec la position que montre la photo.",
    },
}
_TRANSLATIONS = {
    "findObject": "Tap the numbered marker on the object this sentence describes.",
    "chooseLocation": "Choose where it is in the photo.",
    "askWhere": "Ask where the {subject} is.",
    "answerWhere": "Answer with the position the photo shows.",
}
MAX_MARKERS = 4
MAX_PLACES = 4
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


# Catalog words may carry their definite article ("la mesa", "l'arbre").
_LEADING_DEFINITE = re.compile(r"^(el|la|le|los|las|les)\s+|^(l)['’]", re.IGNORECASE)


def _article_and_noun(text, term):
    """The definite article (the translated term's, else the word's own) and the bare noun."""
    text = text.strip()
    match = _LEADING_DEFINITE.match(text)
    noun = text[match.end():] if match else text
    own = (match.group(1) or f"{match.group(2)}'").casefold() if match else None
    return (term.article if term is not None and term.article else own), noun


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
    """The least familiar confirmed relation; every question reuses it."""
    ranked = sorted(found, key=lambda row: familiarity(row["expression"]))
    return [ranked[0]["key"]] if ranked else []


def _statement(language, subject, position, place):
    split = _place_tiles(language, REVIEWED_POSITIONS[position][language], place)
    if split is None:
        return None
    phrase_tile, tail = split
    return [
        *tokens(_capitalised(subject["nounPhrase"])), _LOCATION_VERBS[language], phrase_tile,
        *tail, ".",
    ]


def _shuffled(seed, size):
    order = list(range(size))
    random.Random(seed).shuffle(order)
    return order


_ENGLISH_ARTICLE = re.compile(r"^(?:the|an?)\s+", re.IGNORECASE)


def _english(label):
    """The English label without a leading article, as explanations add their own."""
    return _ENGLISH_ARTICLE.sub("", label.strip())


def scene_markers(objects, review_markers=None):
    """Photo marker numbers from the review screen, else the confirmed objects in ID order."""
    numbers = review_markers or {}
    if not all(str(obj.id) in numbers for obj in objects):
        numbers = {str(obj.id): number for number, obj in enumerate(
            sorted(objects, key=lambda obj: obj.id), 1,
        )}
    ordered = sorted(objects, key=lambda obj: numbers[str(obj.id)])
    return ordered, [
        dict(key=str(obj.id), marker=numbers[str(obj.id)], source=_english(obj.label))
        for obj in ordered
    ]


def m02_payload(
    mission, language, objects, relations, words, translated_scene, progress=None,
    session_id=None, review_markers=None,
):
    """Confirmed relations with reviewed forms, and the one selected for the lesson."""
    language = language.lower()
    ordered, markers = scene_markers(objects, review_markers)
    terms = {term.key: term for term in translated_scene.objects} if translated_scene else {}
    rows, places = {}, {}
    for obj, word in zip(objects, words, strict=True):
        term = terms.get(str(obj.id))
        article, noun = _article_and_noun(word.display_text, term)
        phrase = _with_article(article, noun) if article else noun
        rows[obj.id] = dict(
            key=str(obj.id), source=_english(obj.label), nounPhrase=phrase,
            hasArticle=bool(article),
            whereQuestion=_QUESTION_FRAMES[language].format(phrase),
            gender=mission_gender(term, word),
        )
        places[obj.id] = dict(
            article=article, gender=mission_gender(term, word), translation=noun,
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
        reference = rows[relation.reference_scene_object_id]
        subject_place = places[relation.subject_scene_object_id]
        if _definite(language, subject_place) is None:
            continue
        untrue = [row for row in positions if row["position"] not in true_positions]
        untrue.sort(key=lambda row: row["position"] != _OPPOSITE.get(kind))
        place_options = [dict(position=kind, label=place)]
        for row in untrue[:MAX_PLACES - 1]:
            other_tile, other_tail = _place_tiles(language, row["expression"], reference_place)
            place_options.append(dict(
                position=row["position"], label=" ".join([other_tile, _joined(other_tail)]),
            ))
        wrong = untrue[0]
        extra = _place_tiles(language, wrong["expression"], reference_place)[0]
        contradiction = _joined(_statement(language, subject, wrong["position"], reference_place))
        same = fold(subject["source"])
        distractors = [reference["key"]] + [
            str(obj.id) for obj in ordered
            if str(obj.id) not in {subject["key"], reference["key"]}
            and fold(rows[obj.id]["source"]) != same
        ]
        if fold(reference["source"]) == same:
            continue
        prompts = {
            purpose: template.format(of_subject=_of(language, subject_place))
            for purpose, template in _PROMPTS[language].items()
        }
        found.append(dict(
            key=str(relation.id),
            subjectKey=subject["key"], subjectSource=subject["source"],
            referenceKey=reference["key"], referenceSource=reference["source"],
            position=kind, expression=expression, meaning=POSITION_MEANINGS[kind],
            truePositions=sorted(true_positions),
            statement=_joined(statement_tiles),
            statementTiles=statement_tiles,
            answerExtra=extra,
            contradiction=contradiction,
            whereQuestion=subject["whereQuestion"],
            markerOptions=[subject["key"], *distractors[:MAX_MARKERS - 1]],
            placeOptions=place_options,
            placeOrder=_shuffled(f"{session_id}:M02:{relation.id}", len(place_options)),
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
        "markers": markers,
        "relations": found,
        "selected": _select(found, lambda expression: known.get(fold(expression), 0.0)),
    }


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
    correct_note = _capitalised(
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
            object_label=_capitalised(relation["subjectSource"]),
        )
        if question.purpose != "askWhere":
            fields.update(
                reference_object_id=relation["referenceKey"],
                reference_label=_capitalised(relation["referenceSource"]),
            )
        if question.interaction_type == "multipleChoice":
            fields["keep_option_order"] = True
        return fields

    return build_mission_task(session_id, mission, M02_FOCUS, result, evaluate, shown)
