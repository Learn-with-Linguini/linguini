"""Build the M01 A1 lesson task from confirmed facts and a validated lesson result."""

from app.ai.features.learning_tasks.mission_m01 import colour_sentence
from app.services.ispy_clue_frames import COLOUR_ATTRIBUTE_TYPES
from app.services.mission_eligibility import (
    REVIEWED_COLOURS,
    agreed_colour,
    confirmed_colour,
)
from app.services.mission_lessons import build_mission_task, noun_gender
from app.services.session_plan import _with_article

M01_FOCUS = "identifyDescribeObject"
COPULAS = {"es": "es", "fr": "est"}
_PATTERN_ID = "copula-colour"
_EVALUATIONS = {
    "identifyObject": (
        ["identify-object", "name-object"],
        "recognition",
        ["selects-described-object", "article-matches-noun"],
    ),
    "describeColour": (["describe-colour"], "recognition", ["colour-matches-photo"]),
    "buildDescription": (
        ["name-object", "describe-colour"],
        "construction",
        ["article-matches-noun", "colour-matches-photo"],
    ),
}


def _distractor_colours(colour, language, gender):
    masculine, feminine = REVIEWED_COLOURS[colour][language]
    wrong_gender = feminine if gender == "masculine" else masculine
    forms = [wrong_gender] if masculine != feminine else []
    for other, by_language in REVIEWED_COLOURS.items():
        if other in {colour, "gray"} or len(forms) >= 3:
            continue
        forms.append(agreed_colour(other, language, gender) or by_language[language][0])
    return forms


def m01_payload(mission, language, objects, words, translated_scene):
    """Generation input holding only confirmed objects, colours and reviewed forms."""
    language = language.lower()
    terms = {term.key: term for term in translated_scene.objects} if translated_scene else {}
    rows, colours, genders = [], [], {}
    for obj, word in zip(objects, words, strict=True):
        term = terms.get(str(obj.id))
        gender = noun_gender(term, word)
        rows.append(dict(
            key=str(obj.id), source=obj.label, nounPhrase=_with_article(word.display_text, term)
        ))
        colour = confirmed_colour(obj)
        form = colour and agreed_colour(colour, language, gender)
        if form:
            attribute = next(
                key for key in obj.attributes if key.casefold() in COLOUR_ATTRIBUTE_TYPES
            )
            colours.append(dict(
                key=f"{obj.id}:{attribute}", objectKey=str(obj.id), source=colour, agreedForm=form
            ))
            genders[str(obj.id)] = gender
    pattern = next(item for item in mission.language_patterns if item.pattern_id == _PATTERN_ID)
    first = colours[0] if colours else None
    return {
        "targetLanguage": language,
        "missionId": mission.mission_id,
        "practiceLevel": mission.practice_level,
        "contentVersion": mission.content_version,
        "objects": rows,
        "colours": colours,
        "languagePattern": {
            "patternId": pattern.pattern_id,
            "structure": pattern.structure,
            "copula": COPULAS[language],
            "examples": list(pattern.examples.get(language, [])),
            "distractorColours": (
                _distractor_colours(first["source"], language, genders[first["objectKey"]])
                if first else []
            ),
        },
    }


def _corrections(payload, question, correct_label):
    if question.purpose == "buildDescription":
        return [dict(
            mistake="wordOrder",
            correction=question.correct_text,
            explanation="Use every word: the object, then the verb, then its colour.",
        )]
    rules = []
    colours = {row["key"]: row for row in payload["colours"]}
    objects = {row["key"]: row for row in payload["objects"]}
    wrong_gender = set()
    if question.purpose == "describeColour":
        colour = colours[question.attribute_keys[0]]
        wrong_gender = {
            colour_sentence(payload, objects[question.object_key], {"agreedForm": form})
            for form in REVIEWED_COLOURS[colour["source"]][payload["targetLanguage"]]
            if form != colour["agreedForm"]
        }
    for option in question.options:
        if option.option_id == question.correct_option_id:
            continue
        if question.purpose == "identifyObject":
            mistake, explanation = "wrongWord", "That word names another object in your photo."
        elif option.label in wrong_gender:
            mistake, explanation = "wrongGender", "The colour must match the noun."
        else:
            mistake, explanation = "wrongColour", "Check the colour you confirmed in the photo."
        rules.append(dict(
            mistake=mistake, answers=[option.option_id], correction=correct_label,
            explanation=explanation,
        ))
    return rules


def m01_lesson_task(session_id, mission, payload, result, vocabulary_ids):
    """The M01 lesson task from a validated result."""

    def evaluate(question, label):
        target_ids, evidence_type, criteria = _EVALUATIONS[question.purpose]
        vocabulary_id = vocabulary_ids.get(question.object_key)
        return dict(
            target_ids=target_ids,
            evidence_type=evidence_type,
            rubric_criterion_ids=criteria,
            vocabulary_item_ids=[vocabulary_id] if vocabulary_id else [],
            corrections=_corrections(payload, question, label),
        )

    return build_mission_task(session_id, mission, M01_FOCUS, result, evaluate)
