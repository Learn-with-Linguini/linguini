"""Guided I-Spy clue frames built only from confirmed, translated scene facts."""

import re
import unicodedata

from app.repositories.practice import ClueNamesTargetError, PracticeConflictError
from app.schemas.enums import SYMMETRIC_SCENE_RELATION_TYPES
from app.schemas.tasks import ClueAssistance, ClueFrame, ReflectionContent

INDEFINITE_ARTICLES = {
    "es": {"masculine": "un", "feminine": "una"},
    "fr": {"masculine": "un", "feminine": "une"},
}
DEFINITE_ARTICLES = {
    "es": {"masculine": "el", "feminine": "la"},
    "fr": {"masculine": "le", "feminine": "la"},
}
CONTRACTIONS = {
    "es": {("de", "el"): "del", ("a", "el"): "al"},
    "fr": {("de", "le"): "du", ("de", "les"): "des", ("à", "le"): "au", ("à", "les"): "aux"},
}
MEANINGS = {
    "name": "I see a … — name something you can see in the scene.",
    "colour": "It is … — say what colour your object is.",
    "location": "It is … — say where your object is.",
}
EXAMPLES = {
    "es": {"name": "Veo una taza", "colour": "Es roja", "location": "Está sobre la mesa"},
    "fr": {
        "name": "Je vois une tasse",
        "colour": "Elle est rouge",
        "location": "Elle est sur la table",
    },
}
COLOUR_ATTRIBUTE_TYPES = {"color", "colour"}


def _french_subject(gender):
    return {"feminine": "Elle est", "masculine": "Il est"}.get(gender, "C'est")


def _prefixes(language, gender):
    if language == "es":
        return {"name": "Veo", "colour": "Es", "location": "Está"}
    subject = _french_subject(gender)
    return {"name": "Je vois", "colour": subject, "location": subject}


def _with_article(article, noun):
    return f"{article}{noun}" if article.endswith("'") else f"{article} {noun}"


def _definite(language, term):
    if term.get("article"):
        return term["article"]
    return DEFINITE_ARTICLES[language].get(term.get("gender"))


def _place(language, preposition, term):
    article = _definite(language, term)
    if not article:
        return None
    words = preposition.split()
    contracted = CONTRACTIONS[language].get((words[-1].casefold(), article.casefold()))
    if contracted:
        return " ".join([*words[:-1], contracted, term["translation"]])
    return f"{preposition} {_with_article(article, term['translation'])}"


def _unique(values):
    seen, result = set(), []
    for value in values:
        if value and value.casefold() not in seen:
            seen.add(value.casefold())
            result.append(value)
    return result


def build_clue_support(context, target, word):
    """Frames and the target's own word forms; only confirmed facts become chips."""
    language = context.get("targetLanguage")
    if language not in EXAMPLES:
        return [], []
    facts = context.get("sceneObjects", {})
    objects = {term["key"]: term for term in facts.get("objects", [])}
    target_key = str(target.id)
    target_term = objects.get(target_key, {})
    prefixes = _prefixes(language, target_term.get("gender"))
    name_chips = [
        _with_article(INDEFINITE_ARTICLES[language][term["gender"]], term["translation"])
        for key, term in objects.items()
        if key != target_key and term.get("gender") in INDEFINITE_ARTICLES[language]
    ]
    colour_chips = [
        term["translation"]
        for term in facts.get("attributes", [])
        if term.get("objectKey") == target_key
        and term["key"].rsplit(":", 1)[-1] in COLOUR_ATTRIBUTE_TYPES
    ]
    place_chips = []
    for relation in facts.get("relations", []):
        subject, reference = relation.get("subjectObjectKey"), relation.get("referenceObjectKey")
        if subject != target_key and not (
            reference == target_key and relation["source"] in SYMMETRIC_SCENE_RELATION_TYPES
        ):
            continue
        other = objects.get(reference if subject == target_key else subject)
        if other:
            place_chips.append(_place(language, relation["translation"], other))
    chips = {
        "name": _unique(name_chips),
        "colour": _unique(colour_chips),
        "location": _unique(place_chips),
    }
    frames = [
        ClueFrame(
            frame_id=frame_id,
            prefix=prefixes[frame_id],
            meaning=MEANINGS[frame_id],
            example=EXAMPLES[language][frame_id],
            chips=chips[frame_id][:20],
        )
        for frame_id in ("name", "colour", "location")
        if frame_id == "name" or chips[frame_id]
    ]
    return frames, _target_forms(language, target, word, target_term)


def _target_forms(language, target, word, target_term):
    forms = [word.lemma, word.display_text, word.plural_form, target.label]
    forms.append(target_term.get("translation"))
    plurals = []
    for form in filter(None, forms):
        if " " in form.strip():
            continue
        plurals.append(f"{form}s")
        if _fold(form)[-1:] not in "aeiou":
            plurals.append(f"{form}es")
        if language == "fr" and _fold(form).endswith(("au", "eu")):
            plurals.append(f"{form}x")
    return _unique([form.strip() for form in [*forms, *plurals] if form and form.strip()])[:20]


def _fold(text):
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def mentions_target(text, avoid_words):
    """Whole-word match ignoring case and accents, so "Tazas" and "TAZA" both count."""
    folded = _fold(text)
    for word in avoid_words:
        parts = _fold(word).split()
        if parts and re.search(
            r"(?<!\w)" + r"\s+".join(map(re.escape, parts)) + r"(?!\w)", folded
        ):
            return True
    return False


def check_clue(content, request):
    """Reject a clue naming its target and assistance that this task never offered."""
    if not isinstance(content, ReflectionContent):
        if request.assistance is not None:
            raise PracticeConflictError("Clue assistance does not apply to this task.")
        return
    if mentions_target(request.text, content.avoid_words):
        raise ClueNamesTargetError("Your clue uses the word for this object.")
    if request.assistance is not None:
        _check_assistance(content, request.assistance)


def _check_assistance(content, assistance: ClueAssistance):
    frames = {frame.frame_id: frame for frame in content.clue_frames}
    selected = [frames.get(frame_id) for frame_id in assistance.selected_frame_ids]
    if None in selected:
        raise PracticeConflictError("Clue assistance does not match this task.")
    offered_chips = {chip for frame in selected for chip in frame.chips}
    if (
        assistance.offered_frame_ids != list(frames)
        or not set(assistance.inserted_chips) <= offered_chips
    ):
        raise PracticeConflictError("Clue assistance does not match this task.")
