"""Select M01's two object-colour pairs and build its two-task, four-question lesson."""

import random
import re

from app.ai.features.learning_tasks.mission import fold
from app.ai.features.learning_tasks.mission_m01 import capitalised, description
from app.services.mission_eligibility import (
    REVIEWED_COLOURS,
    agreed_attribute,
    attribute_contrasts,
    confirmed_attributes,
    confirmed_colour,
)
from app.services.mission_lessons import build_mission_task, mission_gender

M01_FOCUS = "identifyDescribeObject"
CONFIRM_PROMPTS = {"es": "¿Es {noun}?", "fr": "Est-ce {noun} ?"}
# Q3 asks about the first object's detail; the prompt names its attribute type.
ATTRIBUTE_PROMPTS = {
    "colour": ({"es": "¿De qué color es?", "fr": "De quelle couleur est-ce ?"},
               "What colour is it?"),
    "material": ({"es": "¿De qué material es?", "fr": "C'est en quoi ?"},
                 "What is it made of?"),
}
OTHER_ATTRIBUTE_PROMPT = ({"es": "¿Cómo es?", "fr": "C'est comment ?"}, "What is it like?")
DESCRIBE_PROMPTS = {"es": "Describe este objeto.", "fr": "Décris cet objet."}
PROMPT_TRANSLATIONS = {
    "confirmObject": "Is it this? Answer with a full sentence.",
    "describeObject": "Describe this object.",
}
SENTENCE_STARTS = {"es": "Es", "fr": "C'est"}
YES_NO = {"es": ("Sí", "No"), "fr": ("Oui", "Non")}
INDEFINITE_ARTICLES = {
    "es": {"masculine": "un", "feminine": "una"},
    "fr": {"masculine": "un", "feminine": "une"},
}
MAX_COLOUR_OPTIONS = 3
# Colours a photo can make look alike; they are never each other's distractors.
SIMILAR_COLOURS = {
    "red": {"pink", "orange", "purple", "brown"},
    "pink": {"red", "purple", "orange", "beige"},
    "orange": {"red", "pink", "yellow", "gold", "brown"},
    "yellow": {"orange", "gold", "beige"},
    "gold": {"yellow", "orange", "brown", "beige", "silver"},
    "beige": {"white", "yellow", "gold", "brown", "pink", "grey", "gray"},
    "white": {"beige", "grey", "gray", "silver"},
    "grey": {"gray", "silver", "white", "black", "beige"},
    "gray": {"grey", "silver", "white", "black", "beige"},
    "silver": {"grey", "gray", "white", "gold"},
    "black": {"grey", "gray", "brown"},
    "brown": {"red", "orange", "gold", "beige", "black"},
    "purple": {"pink", "red", "blue"},
    "blue": {"purple", "green"},
    "green": {"blue"},
}
_PATTERN_ID = "copula-colour"
# Legacy vocabulary rows may keep their article inside the display text.
_LEADING_ARTICLE = re.compile(r"^(?:el|la|los|las|le|les|un|una|une)\s+|^l['’]", re.IGNORECASE)
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


def indefinite(noun, gender, language):
    article = INDEFINITE_ARTICLES[language].get(gender)
    return f"{article} {_LEADING_ARTICLE.sub('', noun.strip())}" if article else None


def _noun(phrase):
    return fold(_LEADING_ARTICLE.sub("", phrase))


def _attributes(obj, language, gender):
    """The object's confirmed details with a reviewed form agreeing with its noun."""
    found = []
    for key, kind, value in confirmed_attributes(obj):
        agreed = agreed_attribute(kind, value, language, gender)
        if agreed:
            found.append(dict(
                attributeKey=f"{obj.id}:{key}", attributeType=kind, attributeSource=value,
                agreedForm=agreed[0], before=agreed[1],
            ))
    return found


def _candidates(language, objects, words, terms, progress):
    """Objects with a noun phrase and reviewed details, least familiar first.

    Familiarity adds the object's mastery score to its first detail's past correct
    ratio. Words with no progress or history count as unseen (0); ties keep scene order.
    """
    known, results = progress.get("objects", {}), progress.get("terms", {})
    candidates = []
    for index, (obj, word) in enumerate(zip(objects, words, strict=True)):
        gender = mission_gender(terms.get(str(obj.id)), word)
        phrase = indefinite(word.display_text, gender, language)
        details = _attributes(obj, language, gender)
        if not (details and phrase):
            continue
        familiarity = known.get(str(word.id), 0.0) + results.get(
            details[0]["agreedForm"].casefold(), 0.0
        )
        candidates.append((familiarity, index, dict(
            key=str(obj.id), source=obj.label.strip(), nounPhrase=phrase, gender=gender,
            vocabularyItemId=str(word.id), details=details,
        )))
    chosen = []
    for _familiarity, _index, pair in sorted(candidates, key=lambda item: item[:2]):
        if all(fold(pair["source"]) != fold(row["source"]) for row in chosen):
            chosen.append(pair)
    return chosen


def _taught_colours(language, objects, progress):
    """Colours confirmed in this photo or already practised in this language."""
    seen = progress.get("terms", {})
    found = [colour for obj in objects if (colour := confirmed_colour(obj))]
    found += [
        colour for colour, forms in REVIEWED_COLOURS.items()
        if any(form.casefold() in seen for form in forms.get(language, ()))
    ]
    return list(dict.fromkeys("grey" if colour == "gray" else colour for colour in found))


def _detail_options(language, gender, detail, taught_colours):
    """The detail's agreed form and clearly different values of the same type.

    Colours offer taught colours that never look alike; other types offer the
    reviewed contrasts (big/small, open/closed, wooden/metal...).
    """
    kind, value = detail["attributeType"], detail["attributeSource"]
    if kind == "colour":
        target = "grey" if value == "gray" else value
        others = [
            colour for colour in taught_colours
            if colour != target and colour not in SIMILAR_COLOURS.get(target, set())
        ]
    else:
        others = list(attribute_contrasts(kind, value))
    options = [detail["agreedForm"]]
    for other in others:
        agreed = agreed_attribute(kind, other, language, gender)
        if agreed and fold(agreed[0]) not in map(fold, options):
            options.append(agreed[0])
    return options[:MAX_COLOUR_OPTIONS]


def _order(rng, size):
    order = list(range(size))
    rng.shuffle(order)
    return order


def _with_detail(pair, detail):
    return {**{key: value for key, value in pair.items() if key != "details"}, **detail}


def _select(language, ranked, taught_colours):
    """The asked pair with its detail options and the described pair.

    Q3 prefers the first object's colour; Q4 prefers another type of detail for the
    second object, so lessons use sizes, materials and states as well as colours.
    """
    for first in ranked:
        for asked in first["details"]:
            options = _detail_options(language, first["gender"], asked, taught_colours)
            if len(options) < 2:
                continue
            for second in ranked:
                if fold(first["source"]) == fold(second["source"]):
                    continue
                described = next((
                    detail for detail in second["details"] if detail["attributeType"] != "colour"
                ), second["details"][0])
                return [_with_detail(first, asked), _with_detail(second, described)], options
    return [], []


def m01_payload(
    mission, language, objects, words, translated_scene, progress=None, session_id=None,
):
    """The two selected pairs and options drawn only from taught, confirmed facts.

    Each pair gets a yes/no "is it this?" check (Q1, Q2) whose truth is drawn
    independently per question; the first pair's detail is chosen (Q3) and the
    second pair's description built (Q4). ``pairs`` is empty when the confirmed
    facts cannot give two pairs with a clearly different distractor.
    """
    language = language.lower()
    progress = progress or {}
    terms = {term.key: term for term in translated_scene.objects} if translated_scene else {}
    ranked = _candidates(language, objects, words, terms, progress)
    pairs, options = _select(language, ranked, _taught_colours(language, objects, progress))
    taught = list(dict.fromkeys(phrase for phrase in [
        *(pair["nounPhrase"] for pair in pairs),
        *(
            indefinite(word.display_text, mission_gender(terms.get(str(obj.id)), word), language)
            for obj, word in zip(objects, words, strict=True)
        ),
        *(
            indefinite(noun["text"], noun["gender"], language)
            for noun in progress.get("taught_nouns", [])
        ),
    ] if phrase))
    nouns, seen = [], set()
    for phrase in taught:
        if _noun(phrase) not in seen:
            seen.add(_noun(phrase))
            nouns.append(phrase)
    extras = []
    if pairs:
        second = pairs[1]
        other = {"masculine": "feminine", "feminine": "masculine"}.get(second["gender"])
        wrong = other and agreed_attribute(
            second["attributeType"], second["attributeSource"], language, other,
        )
        if wrong and fold(wrong[0]) != fold(second["agreedForm"]):
            extras.append(wrong[0])
    rng = random.Random(f"{session_id}:M01")
    pattern = next(item for item in mission.language_patterns if item.pattern_id == _PATTERN_ID)
    selected = {_noun(pair["nounPhrase"]) for pair in pairs}
    example = next((
        sentence for sentence in pattern.examples.get(language, [])
        if not any(noun in fold(sentence) for noun in selected)
    ), None)
    prompts, prompt_translation = ATTRIBUTE_PROMPTS.get(
        pairs[0]["attributeType"] if pairs else "colour", OTHER_ATTRIBUTE_PROMPT,
    )
    yes, no = YES_NO[language]
    return {
        "targetLanguage": language,
        "missionId": mission.mission_id,
        "practiceLevel": mission.practice_level,
        "contentVersion": mission.content_version,
        "pairs": pairs,
        "taughtNouns": nouns,
        "attributeOptions": options,
        "describeExtras": extras,
        "layout": dict(
            confirmOrders=[_order(rng, 2), _order(rng, 2)],
            attributeOrder=_order(rng, len(options)),
            # Independent per question, so learners can't learn a yes-then-no pattern.
            statementCorrect=[rng.random() < 0.5, rng.random() < 0.5],
        ),
        "confirmPrompt": CONFIRM_PROMPTS[language],
        "attributePrompt": prompts[language],
        "attributePromptTranslation": prompt_translation,
        "describePrompt": DESCRIBE_PROMPTS[language],
        "sentenceStart": SENTENCE_STARTS[language],
        "yes": yes,
        "no": no,
        "example": example,
    }


def _corrections(payload, question, correct_label):
    pairs = {pair["key"]: pair for pair in payload["pairs"]}
    pair = pairs[question.object_key]
    wrong = [
        option for option in question.options if option.option_id != question.correct_option_id
    ]
    if question.purpose == "describeObject":
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
        return rules
    if question.purpose == "confirmObject":
        explanation = (
            f"Yes — this is {pair['nounPhrase']} ({pair['source']})."
            if question.statement_correct
            else f"No — this is {pair['nounPhrase']} ({pair['source']})."
        )
        return [dict(
            mistake="wrongObject", answers=[option.option_id], correction=correct_label,
            explanation=explanation,
        ) for option in wrong]
    return [dict(
        mistake="wrongColour" if pair["attributeType"] == "colour" else "wrongAttribute",
        answers=[option.option_id], correction=correct_label,
        explanation=f"This {pair['source']} is {pair['attributeSource']}: {pair['agreedForm']}.",
    ) for option in wrong]


def m01_lesson_task(session_id, mission, payload, result, vocabulary_ids):
    """The M01 lesson task; Task 2 questions also show the object's English label."""
    labels = {pair["key"]: pair["source"] for pair in payload["pairs"]}

    def evaluate(question, label):
        target_ids, evidence_type, criteria = _EVALUATIONS[question.purpose]
        vocabulary_id = vocabulary_ids.get(question.object_key)
        assessed = vocabulary_id and question.purpose != "chooseAttribute"
        return dict(
            target_ids=target_ids,
            evidence_type=evidence_type,
            rubric_criterion_ids=criteria,
            vocabulary_item_ids=[vocabulary_id] if assessed else [],
            corrections=_corrections(payload, question, label),
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
