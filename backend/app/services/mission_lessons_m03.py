"""Build the M03 A1 lesson task from a learner-counted group and a validated result."""

from collections import Counter

from app.ai.features.learning_tasks.mission import fold, tokens
from app.ai.features.learning_tasks.mission_m03 import SECTION_BOARD, SECTION_PHOTO
from app.services.mission_eligibility import countable_groups
from app.services.mission_lessons import build_mission_task, noun_gender
from app.services.quantities import (
    ENGLISH_NUMBERS,
    NUMBER_WORDS,
    QUANTITY_FRAMES,
    english_plural,
    quantity_sentence,
    regular_plural,
    taught_numbers,
)

M03_FOCUS = "sayHowMany"
_VOWELS = set("aeiouyàâäéèêëîïôöùûü")
_ASK_TRANSLATION = "How many {noun} are there?"
_ANSWER_TRANSLATION = "How many {noun} are there? Answer with a sentence."
_EVALUATIONS = {
    "chooseQuantity": (["say-quantity"], "recognition", ["quantity-matches-photo"]),
    "buildQuantity": (
        ["say-quantity", "plural-noun"],
        "construction",
        ["quantity-matches-photo", "plural-form-correct"],
    ),
    "matchQuantity": (["understand-quantity"], "recognition", ["understands-quantity"]),
}


def _plural(language, word):
    plural = regular_plural(language, word.display_text)
    recorded = getattr(word, "plural_form", None)
    if plural is None or (recorded and recorded.casefold() != plural.casefold()):
        return None
    return plural


def _how_many(language, plural, gender):
    """The reviewed how-many question for the plural, or ``None`` when unreviewed."""
    if language == "es":
        if gender == "masculine":
            return f"¿Cuántos {plural} hay?"
        if gender == "feminine":
            return f"¿Cuántas {plural} hay?"
        return None
    if language == "fr":
        first = plural[:1].casefold()
        if first == "h":
            return None
        if first in _VOWELS:
            return f"Combien d'{plural} y a-t-il ?"
        return f"Combien de {plural} y a-t-il ?"
    return None


def m03_payload(
    mission, language, objects, _relations, words, translated_scene, counts,
    progress=None, session_id=None,
):
    """The first counted group with a taught quantity and a phraseable question."""
    language = language.lower()
    numbers, source = taught_numbers(mission, progress)
    taught = set(numbers)
    by_id = {str(obj.id): (obj, word) for obj, word in zip(objects, words, strict=True)}
    terms = {term.key: term for term in translated_scene.objects} if translated_scene else {}
    group = None
    for counted in countable_groups(mission, counts):
        quantity = counted["quantity"]
        if quantity not in taught:
            continue
        object_ids = [str(item) for item in counted["sceneObjectIds"]]
        key = next((item for item in object_ids if item in by_id), None)
        if key is None:
            continue
        obj, word = by_id[key]
        plural = _plural(language, word)
        if plural is None:
            continue
        question = _how_many(language, plural, noun_gender(terms.get(key), word))
        if question is None:
            continue
        board_key = next(
            (item for item in object_ids
             if item in by_id and getattr(by_id[item][0], "bounding_box", None)),
            key,
        )
        group = dict(
            key=f"{key}:count", objectKey=key, objectIds=object_ids,
            boardObjectId=board_key, source=obj.label, quantity=quantity,
            numberWord=NUMBER_WORDS[language][quantity],
            englishNumber=ENGLISH_NUMBERS[quantity],
            singular=word.display_text, plural=plural,
            englishPlural=english_plural(obj.label),
            objectLabel=english_plural(obj.label).capitalize(),
            question=question,
            statement=quantity_sentence(language, NUMBER_WORDS[language][quantity], plural),
        )
        break
    return {
        "targetLanguage": language,
        "missionId": mission.mission_id,
        "practiceLevel": mission.practice_level,
        "contentVersion": mission.content_version,
        "seed": f"{session_id}:M03",
        "numberRange": {
            "low": numbers[0] if numbers else 0,
            "high": numbers[-1] if numbers else 0,
            "source": source,
        },
        "group": group,
    }


def _corrections(payload, question, label):
    group = payload["group"]
    language = payload["targetLanguage"]
    if question.purpose == "buildQuantity":
        statement = group["statement"]
        extras = list(
            (Counter(question.token_bank) - Counter(tokens(statement))).elements()
        )
        wrong_word = next(
            (token for token in extras if fold(token) != fold(group["singular"])),
            group["numberWord"],
        )
        singular_statement = quantity_sentence(language, group["numberWord"], group["singular"])
        wrong_statement = quantity_sentence(language, wrong_word, group["plural"])
        wrong_singular = quantity_sentence(language, wrong_word, group["singular"])
        return [
            dict(
                mistake="pluralForm", correction=question.correct_text,
                answers=[singular_statement, wrong_singular],
                explanation=(
                    f"After {group['numberWord']}, use the plural {group['plural']}."
                ),
            ),
            dict(
                mistake="wrongQuantity", correction=question.correct_text,
                answers=[wrong_statement, wrong_singular],
                explanation=f"You counted {group['quantity']}: {group['numberWord']}.",
            ),
            dict(
                mistake="wordOrder", correction=question.correct_text,
                explanation=f"Start with {QUANTITY_FRAMES[language]}, "
                            "then the number, then the plural noun.",
            ),
        ]
    if question.purpose == "matchQuantity":
        target = (question.board_counts or {}).get(question.correct_option_id)
        return [
            dict(
                mistake="wrongQuantity", answers=[option.option_id], correction=label,
                explanation=f"“{question.quantity_word}” means {target}.",
            )
            for option in question.options if option.option_id != question.correct_option_id
        ]
    reverse_numbers = {
        fold(number_word): number for number, number_word in NUMBER_WORDS[language].items()
    }
    return [
        dict(
            mistake="wrongQuantity", answers=[option.option_id], correction=label,
            explanation=(
                f"“{option.label}” means {number}; you counted {group['quantity']}: "
                f"{group['numberWord']}."
                if (number := reverse_numbers.get(fold(option.label))) is not None
                else f"You counted {group['quantity']}: {group['numberWord']}."
            ),
        )
        for option in question.options if option.option_id != question.correct_option_id
    ]


def m03_lesson_task(session_id, mission, payload, result, vocabulary_ids):
    """The M03 lesson task from a validated result."""
    group = payload["group"]
    translations = {
        "chooseQuantity": _ASK_TRANSLATION.format(noun=group["englishPlural"]),
        "buildQuantity": _ANSWER_TRANSLATION.format(noun=group["englishPlural"]),
        "matchQuantity": None,
    }

    def evaluate(question, label):
        target_ids, evidence_type, criteria = _EVALUATIONS[question.purpose]
        vocabulary_id = vocabulary_ids.get(question.object_key)
        return dict(
            target_ids=target_ids,
            evidence_type=evidence_type,
            rubric_criterion_ids=criteria,
            vocabulary_item_ids=(
                [vocabulary_id]
                if vocabulary_id and question.purpose == "buildQuantity" else []
            ),
            corrections=_corrections(payload, question, label),
        )

    def shown(question):
        fields = dict(
            section=question.section,
            prompt_translation=translations[question.purpose],
        )
        if question.section == SECTION_PHOTO:
            fields.update(
                scene_object_id=question.object_key,
                object_label=group["objectLabel"],
                group_object_ids=question.group_object_ids,
            )
        if question.section == SECTION_BOARD:
            fields.update(
                board_counts=question.board_counts,
                board_object_id=question.board_object_id,
                quantity_word=question.quantity_word,
            )
        return fields

    return build_mission_task(session_id, mission, M03_FOCUS, result, evaluate, shown)
