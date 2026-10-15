"""Select M01's two object-colour pairs and build its four-question lesson task."""

import re

from app.ai.features.learning_tasks.mission import fold
from app.services.ispy_clue_frames import COLOUR_ATTRIBUTE_TYPES
from app.services.mission_eligibility import agreed_colour, confirmed_colour
from app.services.mission_lessons import build_mission_task, noun_gender

M01_FOCUS = "identifyDescribeObject"
IDENTIFY_PROMPTS = {"es": "¿Qué es esto?", "fr": "Qu'est-ce que c'est ?"}
DESCRIBE_PROMPTS = {"es": "Describe este objeto.", "fr": "Décris cet objet."}
PROMPT_TRANSLATIONS = {"identifyObject": "What is this?", "describeObject": "Describe this object."}
SENTENCE_STARTS = {"es": "Es", "fr": "C'est"}
INDEFINITE_ARTICLES = {
    "es": {"masculine": "un", "feminine": "una"},
    "fr": {"masculine": "un", "feminine": "une"},
}
MAX_DISTRACTORS = 3
_PATTERN_ID = "copula-colour"
# Legacy vocabulary rows may keep their article inside the display text.
_LEADING_ARTICLE = re.compile(r"^(?:el|la|los|las|le|les|un|una|une)\s+|^l['’]", re.IGNORECASE)
_EVALUATIONS = {
    "identifyObject": (
        ["identify-object", "name-object"],
        "recognition",
        ["selects-described-object", "article-matches-noun"],
    ),
    "describeObject": (
        ["name-object", "describe-colour"],
        "construction",
        ["article-matches-noun", "colour-matches-photo"],
    ),
}


def indefinite(noun, gender, language):
    article = INDEFINITE_ARTICLES[language].get(gender)
    return f"{article} {_LEADING_ARTICLE.sub('', noun.strip())}" if article else None


def _pairs(language, objects, words, terms, progress):
    """Usable confirmed pairs, least familiar first; ties keep scene order.

    Familiarity adds the object's mastery score to the colour's past correct ratio,
    so a familiar object with an unfamiliar colour still ranks well. Words with no
    progress or history count as unseen (0).
    """
    known, colour_results = progress.get("objects", {}), progress.get("terms", {})
    candidates = []
    for index, (obj, word) in enumerate(zip(objects, words, strict=True)):
        gender = noun_gender(terms.get(str(obj.id)), word)
        colour = confirmed_colour(obj)
        form = colour and agreed_colour(colour, language, gender)
        phrase = indefinite(word.display_text, gender, language)
        if not (form and phrase):
            continue
        attribute = next(key for key in obj.attributes if key.casefold() in COLOUR_ATTRIBUTE_TYPES)
        familiarity = known.get(str(word.id), 0.0) + colour_results.get(form.casefold(), 0.0)
        candidates.append((familiarity, index, dict(
            key=str(obj.id), source=obj.label.strip(), nounPhrase=phrase,
            colourKey=f"{obj.id}:{attribute}", colourSource=colour, agreedForm=form,
            vocabularyItemId=str(word.id),
        )))
    chosen = []
    for _familiarity, _index, pair in sorted(candidates, key=lambda item: item[:2]):
        if all(fold(pair["source"]) != fold(row["source"]) for row in chosen):
            chosen.append(pair)
    return chosen[:2]


def m01_payload(mission, language, objects, words, translated_scene, progress=None):
    """The two selected pairs and identification distractors from taught nouns only."""
    language = language.lower()
    terms = {term.key: term for term in translated_scene.objects} if translated_scene else {}
    pairs = _pairs(language, objects, words, terms, progress or {})
    taught = [
        indefinite(word.display_text, noun_gender(terms.get(str(obj.id)), word), language)
        for obj, word in zip(objects, words, strict=True)
    ] + [
        indefinite(noun["text"], noun["gender"], language)
        for noun in (progress or {}).get("taught_nouns", [])
    ]
    nouns = {fold(_LEADING_ARTICLE.sub("", pair["nounPhrase"])) for pair in pairs}
    distractors = {}
    for pair in pairs if len(pairs) == 2 else []:
        other = next(row["nounPhrase"] for row in pairs if row is not pair)
        pool = [other, *(phrase for phrase in taught if phrase)]
        options, seen = [], {fold(_LEADING_ARTICLE.sub("", pair["nounPhrase"]))}
        for phrase in pool:
            noun = fold(_LEADING_ARTICLE.sub("", phrase))
            if noun not in seen:
                seen.add(noun)
                options.append(phrase)
        distractors[pair["key"]] = options[:MAX_DISTRACTORS]
    pattern = next(item for item in mission.language_patterns if item.pattern_id == _PATTERN_ID)
    example = next((
        sentence for sentence in pattern.examples.get(language, [])
        if not any(noun in fold(sentence) for noun in nouns)
    ), None)
    return {
        "targetLanguage": language,
        "missionId": mission.mission_id,
        "practiceLevel": mission.practice_level,
        "contentVersion": mission.content_version,
        "pairs": pairs,
        "distractors": distractors,
        "identifyPrompt": IDENTIFY_PROMPTS[language],
        "describePrompt": DESCRIBE_PROMPTS[language],
        "sentenceStart": SENTENCE_STARTS[language],
        "example": example,
    }


def _corrections(question, correct_label):
    if question.purpose == "describeObject":
        return [dict(
            mistake="wordOrder",
            correction=question.correct_text,
            explanation="Start with the verb, then the object, then its colour.",
        )]
    return [
        dict(
            mistake="wrongWord", answers=[option.option_id], correction=correct_label,
            explanation="That word names a different object.",
        )
        for option in question.options if option.option_id != question.correct_option_id
    ]


def m01_lesson_task(session_id, mission, payload, result, vocabulary_ids):
    """The M01 lesson task; each question shows its object and English label."""
    labels = {pair["key"]: pair["source"] for pair in payload["pairs"]}

    def evaluate(question, label):
        target_ids, evidence_type, criteria = _EVALUATIONS[question.purpose]
        vocabulary_id = vocabulary_ids.get(question.object_key)
        return dict(
            target_ids=target_ids,
            evidence_type=evidence_type,
            rubric_criterion_ids=criteria,
            vocabulary_item_ids=[vocabulary_id] if vocabulary_id else [],
            corrections=_corrections(question, label),
        )

    def shown(question):
        label = labels[question.object_key]
        return dict(
            scene_object_id=question.object_key,
            object_label=f"{label[:1].upper()}{label[1:]}",
            prompt_translation=PROMPT_TRANSLATIONS[question.purpose],
        )

    return build_mission_task(session_id, mission, M01_FOCUS, result, evaluate, shown)
