"""Select M01's two object-colour pairs and build its two-task, four-question lesson."""

import random
import re

from app.ai.features.learning_tasks.mission import fold
from app.ai.features.learning_tasks.mission_m01 import capitalised, description
from app.services.ispy_clue_frames import COLOUR_ATTRIBUTE_TYPES
from app.services.mission_eligibility import REVIEWED_COLOURS, agreed_colour, confirmed_colour
from app.services.mission_lessons import build_mission_task, mission_gender

M01_FOCUS = "identifyDescribeObject"
IDENTIFY_PROMPTS = {"es": "¿Qué es esto?", "fr": "Qu'est-ce que c'est ?"}
CONFIRM_PROMPTS = {"es": "¿Es {noun}?", "fr": "Est-ce {noun} ?"}
COLOUR_PROMPTS = {"es": "¿De qué color es?", "fr": "De quelle couleur est-ce ?"}
DESCRIBE_PROMPTS = {"es": "Describe este objeto.", "fr": "Décris cet objet."}
PROMPT_TRANSLATIONS = {
    "identifyObject": "What is this?",
    "confirmObject": "Is the question right about this object? Answer with a full sentence.",
    "chooseColour": "What colour is it?",
    "describeObject": "Describe this object.",
}
SENTENCE_STARTS = {"es": "Es", "fr": "C'est"}
YES_NO = {"es": ("Sí", "No"), "fr": ("Oui", "Non")}
INDEFINITE_ARTICLES = {
    "es": {"masculine": "un", "feminine": "una"},
    "fr": {"masculine": "un", "feminine": "une"},
}
MAX_NOUN_OPTIONS = 4
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
    "identifyObject": (
        ["identify-object", "name-object"],
        "recognition",
        ["selects-described-object", "article-matches-noun"],
    ),
    "confirmObject": (
        ["identify-object", "name-object"],
        "recognition",
        ["selects-described-object", "article-matches-noun"],
    ),
    "chooseColour": (["describe-colour"], "recognition", ["colour-matches-photo"]),
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


def _candidates(language, objects, words, terms, progress):
    """Usable confirmed pairs, least familiar first; ties keep scene order.

    Familiarity adds the object's mastery score to the colour's past correct ratio,
    so a familiar object with an unfamiliar colour still ranks well. Words with no
    progress or history count as unseen (0).
    """
    known, colour_results = progress.get("objects", {}), progress.get("terms", {})
    candidates = []
    for index, (obj, word) in enumerate(zip(objects, words, strict=True)):
        gender = mission_gender(terms.get(str(obj.id)), word)
        colour = confirmed_colour(obj)
        form = colour and agreed_colour(colour, language, gender)
        phrase = indefinite(word.display_text, gender, language)
        if not (form and phrase):
            continue
        attribute = next(key for key in obj.attributes if key.casefold() in COLOUR_ATTRIBUTE_TYPES)
        familiarity = known.get(str(word.id), 0.0) + colour_results.get(form.casefold(), 0.0)
        candidates.append((familiarity, index, dict(
            key=str(obj.id), source=obj.label.strip(), nounPhrase=phrase, gender=gender,
            colourKey=f"{obj.id}:{attribute}", colourSource=colour, agreedForm=form,
            vocabularyItemId=str(word.id),
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


def _colour_options(language, pair, taught):
    """The pair's agreed colour and clearly different taught colours in the same form."""
    target = "grey" if pair["colourSource"] == "gray" else pair["colourSource"]
    options = [pair["agreedForm"]]
    for colour in taught:
        form = agreed_colour(colour, language, pair["gender"])
        if colour == target or colour in SIMILAR_COLOURS.get(target, set()) or not form:
            continue
        if fold(form) not in map(fold, options):
            options.append(form)
    return options[:MAX_COLOUR_OPTIONS]


def _order(rng, size):
    order = list(range(size))
    rng.shuffle(order)
    return order


def m01_payload(
    mission, language, objects, words, translated_scene, progress=None, session_id=None,
):
    """The two selected pairs and options drawn only from taught, confirmed facts.

    The first pair is identified (Q1) and its colour chosen (Q3); the second pair's
    statement is checked (Q2) and its description built (Q4). ``pairs`` is empty
    when the confirmed facts cannot give two pairs with a clearly different colour
    distractor.
    """
    language = language.lower()
    progress = progress or {}
    terms = {term.key: term for term in translated_scene.objects} if translated_scene else {}
    ranked = _candidates(language, objects, words, terms, progress)
    taught_colours = _taught_colours(language, objects, progress)
    pairs, colours = [], []
    for first in ranked:
        for second in ranked:
            if fold(first["source"]) == fold(second["source"]):
                continue
            options = _colour_options(language, first, taught_colours)
            if len(options) >= 2:
                pairs, colours = [first, second], options
                break
        if pairs:
            break
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
        wrong = other and agreed_colour(second["colourSource"], language, other)
        if wrong and fold(wrong) != fold(second["agreedForm"]):
            extras.append(wrong)
    rng = random.Random(f"{session_id}:M01")
    identify = nouns[:MAX_NOUN_OPTIONS]
    pattern = next(item for item in mission.language_patterns if item.pattern_id == _PATTERN_ID)
    selected = {_noun(pair["nounPhrase"]) for pair in pairs}
    example = next((
        sentence for sentence in pattern.examples.get(language, [])
        if not any(noun in fold(sentence) for noun in selected)
    ), None)
    yes, no = YES_NO[language]
    return {
        "targetLanguage": language,
        "missionId": mission.mission_id,
        "practiceLevel": mission.practice_level,
        "contentVersion": mission.content_version,
        "pairs": pairs,
        "taughtNouns": nouns,
        "identifyOptions": identify,
        "colourOptions": colours,
        "describeExtras": extras,
        "layout": dict(
            identifyOrder=_order(rng, len(identify)),
            confirmOrder=_order(rng, 2),
            colourOrder=_order(rng, len(colours)),
            statementCorrect=rng.random() < 0.5,
        ),
        "identifyPrompt": IDENTIFY_PROMPTS[language],
        "confirmPrompt": CONFIRM_PROMPTS[language],
        "colourPrompt": COLOUR_PROMPTS[language],
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
            explanation="Start with the verb, then the object, then its colour.",
        )]
        for form in payload["describeExtras"]:
            rules.insert(0, dict(
                mistake="wrongGender",
                answers=[description(payload, {**pair, "agreedForm": form})],
                correction=question.correct_text,
                explanation=f"The colour agrees with {pair['nounPhrase']}: {pair['agreedForm']}.",
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
    if question.purpose == "chooseColour":
        return [dict(
            mistake="wrongColour", answers=[option.option_id], correction=correct_label,
            explanation=f"This {pair['source']} is {pair['colourSource']}: {pair['agreedForm']}.",
        ) for option in wrong]
    return [dict(
        mistake="wrongWord", answers=[option.option_id], correction=correct_label,
        explanation="That word names a different object.",
    ) for option in wrong]


def m01_lesson_task(session_id, mission, payload, result, vocabulary_ids):
    """The M01 lesson task; Task 2 questions also show the object's English label."""
    labels = {pair["key"]: pair["source"] for pair in payload["pairs"]}

    def evaluate(question, label):
        target_ids, evidence_type, criteria = _EVALUATIONS[question.purpose]
        vocabulary_id = vocabulary_ids.get(question.object_key)
        assessed = vocabulary_id and question.purpose != "chooseColour"
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
            prompt_translation=PROMPT_TRANSLATIONS[question.purpose],
        )
        if question.purpose in {"chooseColour", "describeObject"}:
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
