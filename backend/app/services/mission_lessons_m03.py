"""Build the M03 A1 lesson task from a learner-counted group and a validated result."""

from app.services.mission_eligibility import countable_groups
from app.services.mission_lessons import build_mission_task
from app.services.quantities import (
    ENGLISH_NUMBERS,
    NUMBER_WORDS,
    QUANTITY_FRAMES,
    english_plural,
    quantity_meaning,
    quantity_sentence,
    regular_plural,
    wrong_quantities,
)

M03_FOCUS = "sayHowMany"
_EVALUATIONS = {
    "understandQuantity": (["understand-quantity"], "recognition", ["understands-quantity"]),
    "chooseQuantity": (
        ["say-quantity", "plural-noun"],
        "recognition",
        ["quantity-matches-photo", "plural-form-correct"],
    ),
    "buildQuantity": (
        ["say-quantity", "plural-noun"],
        "construction",
        ["quantity-matches-photo", "plural-form-correct"],
    ),
}


def _plural(language, word):
    plural = regular_plural(language, word.display_text)
    recorded = getattr(word, "plural_form", None)
    if plural is None or (recorded and recorded.casefold() != plural.casefold()):
        return None
    return plural


def m03_payload(mission, language, objects, _relations, words, _translated_scene, counts):
    """Generation input for the first counted group whose noun has a reviewed regular plural."""
    language = language.lower()
    by_id = {str(obj.id): (obj, word) for obj, word in zip(objects, words, strict=True)}
    requirements = mission.photo_requirements
    group = None
    for counted in countable_groups(mission, counts):
        key = next((str(item) for item in counted["sceneObjectIds"] if str(item) in by_id), None)
        if key is None:
            continue
        obj, word = by_id[key]
        plural = _plural(language, word)
        if plural is None:
            continue
        quantity = counted["quantity"]
        number = NUMBER_WORDS[language][quantity]
        group = dict(
            key=f"{key}:count", objectKey=key, source=obj.label, quantity=quantity,
            numberWord=number, englishNumber=ENGLISH_NUMBERS[quantity],
            singular=word.display_text, plural=plural,
            englishPlural=english_plural(obj.label),
            statement=quantity_sentence(language, number, plural),
            meaning=quantity_meaning(quantity, obj.label),
        )
        break
    wrong = []
    if group:
        wrong = [
            dict(
                quantity=other,
                numberWord=NUMBER_WORDS[language][other],
                statement=quantity_sentence(
                    language, NUMBER_WORDS[language][other], group["plural"]
                ),
                meaning=quantity_meaning(other, group["source"]),
            )
            for other in wrong_quantities(
                group["quantity"], requirements.min_quantity, requirements.max_quantity
            )
        ]
    pattern = next(item for item in mission.language_patterns)
    return {
        "targetLanguage": language,
        "missionId": mission.mission_id,
        "practiceLevel": mission.practice_level,
        "contentVersion": mission.content_version,
        "group": group,
        "wrongQuantities": wrong,
        "singularStatement": (
            quantity_sentence(language, group["numberWord"], group["singular"]) if group else None
        ),
        "distractorTokens": [group["singular"], wrong[0]["numberWord"]] if group else [],
        "languagePattern": {
            "frame": QUANTITY_FRAMES[language],
            "structure": pattern.structure,
            "examples": list(pattern.examples.get(language, [])),
        },
    }


def _build_corrections(payload, correct_text):
    group = payload["group"]
    singular = payload["singularStatement"]
    wrong_number = payload["wrongQuantities"][0]
    plural_rule = dict(
        mistake="pluralForm", correction=correct_text,
        explanation=f"After {group['numberWord']}, use the plural {group['plural']}.",
    )
    quantity_rule = dict(
        mistake="wrongQuantity", correction=correct_text,
        explanation=f"You counted {group['quantity']}: {group['numberWord']}.",
    )
    wrong_singular = quantity_sentence(
        payload["targetLanguage"], wrong_number["numberWord"], group["singular"]
    )
    return [
        {**plural_rule, "answers": [singular, wrong_singular]},
        {**quantity_rule, "answers": [wrong_number["statement"], wrong_singular]},
        dict(
            mistake="wordOrder", correction=correct_text,
            explanation=f"Start with {payload['languagePattern']['frame']}, "
                        "then the number, then the plural noun.",
        ),
    ]


def _corrections(payload, question, correct_label):
    if question.purpose == "buildQuantity":
        return _build_corrections(payload, question.correct_text)
    group = payload["group"]
    rules = []
    for option in question.options:
        if option.option_id == question.correct_option_id:
            continue
        if question.purpose == "chooseQuantity" and option.label == payload["singularStatement"]:
            mistake = "pluralForm"
            explanation = f"After {group['numberWord']}, use the plural {group['plural']}."
        elif question.purpose == "chooseQuantity":
            mistake = "wrongQuantity"
            explanation = f"You counted {group['quantity']}: {group['numberWord']}."
        else:
            mistake = "wrongQuantity"
            explanation = f"\u201c{group['numberWord']}\u201d means {group['englishNumber']}."
        rules.append(dict(
            mistake=mistake, answers=[option.option_id], correction=correct_label,
            explanation=explanation,
        ))
    return rules


def m03_lesson_task(session_id, mission, payload, result, vocabulary_ids):
    """The M03 lesson task from a validated result."""

    def evaluate(question, label):
        target_ids, evidence_type, criteria = _EVALUATIONS[question.purpose]
        vocabulary_id = vocabulary_ids.get(question.object_key)
        uses_noun = question.purpose != "understandQuantity"
        return dict(
            target_ids=target_ids,
            evidence_type=evidence_type,
            rubric_criterion_ids=criteria,
            vocabulary_item_ids=[vocabulary_id] if vocabulary_id and uses_noun else [],
            corrections=_corrections(payload, question, label),
        )

    return build_mission_task(session_id, mission, M03_FOCUS, result, evaluate)
