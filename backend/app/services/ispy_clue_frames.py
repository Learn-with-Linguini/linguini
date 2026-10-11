"""Guided I-Spy clue frames built only from confirmed, translated scene facts."""

import re
import unicodedata

from app.repositories.practice import ClueNamesTargetError, PracticeConflictError
from app.schemas.enums import SYMMETRIC_SCENE_RELATION_TYPES
from app.schemas.tasks import ClueAssistance, ClueFrame, ReflectionContent

DEFINITE_ARTICLES = {
    "es": {"masculine": "el", "feminine": "la"},
    "fr": {"masculine": "le", "feminine": "la"},
}
CONTRACTIONS = {
    "es": {("de", "el"): "del", ("a", "el"): "al"},
    "fr": {("de", "le"): "du", ("de", "les"): "des", ("à", "le"): "au", ("à", "les"): "aux"},
}
MEANINGS = {
    "colour": "It is … — say what colour your object is.",
    "location": "It is … — say where your object is, using another object as a reference.",
}
# Singular (masculine, feminine) forms. A colour missing here is never suggested,
# because its agreement with the target noun cannot be established safely.
COLOUR_FORMS = {
    "es": [
        ("rojo", "roja"), ("blanco", "blanca"), ("negro", "negra"),
        ("amarillo", "amarilla"), ("morado", "morada"), ("dorado", "dorada"),
        ("plateado", "plateada"), ("anaranjado", "anaranjada"),
        ("azul", "azul"), ("verde", "verde"), ("gris", "gris"), ("marrón", "marrón"),
        ("rosa", "rosa"), ("naranja", "naranja"), ("violeta", "violeta"),
        ("beige", "beige"), ("turquesa", "turquesa"),
    ],
    "fr": [
        ("noir", "noire"), ("vert", "verte"), ("bleu", "bleue"), ("gris", "grise"),
        ("blanc", "blanche"), ("violet", "violette"), ("doré", "dorée"),
        ("argenté", "argentée"), ("rouge", "rouge"), ("jaune", "jaune"),
        ("rose", "rose"), ("beige", "beige"), ("orange", "orange"), ("marron", "marron"),
    ],
}
SUPPORTED_LANGUAGES = set(COLOUR_FORMS)
COLOUR_ATTRIBUTE_TYPES = {"color", "colour"}
LOCATION_VERB_STARTS = ("esta ", "es ", "est ", "il est ", "elle est ")


def _prefixes(language, gender):
    if language == "es":
        return {"colour": "Es", "location": "Está"}
    subject = {"feminine": "Elle est", "masculine": "Il est"}.get(gender, "C'est")
    return {"colour": subject, "location": subject}


def _with_article(article, noun):
    return f"{article}{noun}" if article.endswith("'") else f"{article} {noun}"


def _definite(language, term):
    if term.get("article"):
        return term["article"]
    return DEFINITE_ARTICLES[language].get(term.get("gender"))


def _place(language, preposition, term):
    article = _definite(language, term)
    folded = _fold(preposition)
    if not article or folded.startswith(LOCATION_VERB_STARTS):
        return None
    words = preposition.split()
    contracted = CONTRACTIONS[language].get((words[-1].casefold(), article.casefold()))
    if contracted:
        return " ".join([*words[:-1], contracted, term["translation"]])
    return f"{preposition} {_with_article(article, term['translation'])}"


def agree_colour(language, adjective, gender):
    """The colour form agreeing with a singular noun, or None when it is not certain."""
    folded = _fold(adjective.strip())
    for masculine, feminine in COLOUR_FORMS.get(language, []):
        if folded in {_fold(masculine), _fold(feminine)}:
            if masculine == feminine:
                return masculine
            return {"masculine": masculine, "feminine": feminine}.get(gender)
    return None


def _unique(values):
    seen, result = set(), []
    for value in values:
        if value and value.casefold() not in seen:
            seen.add(value.casefold())
            result.append(value)
    return result


def build_clue_support(context, target, word):
    """Colour and Location frames from confirmed facts, plus the target's own word forms."""
    language = context.get("targetLanguage")
    if language not in SUPPORTED_LANGUAGES:
        return [], []
    facts = context.get("sceneObjects", {})
    objects = {term["key"]: term for term in facts.get("objects", [])}
    target_key = str(target.id)
    target_term = objects.get(target_key, {})
    forms = _target_forms(language, target, word, target_term)
    colour_chips = [
        agree_colour(language, term["translation"], target_term.get("gender"))
        for term in facts.get("attributes", [])
        if term.get("objectKey") == target_key
        and term["key"].rsplit(":", 1)[-1] in COLOUR_ATTRIBUTE_TYPES
    ]
    place_chips = []
    for relation in facts.get("relations", []):
        subject, reference = relation.get("subjectObjectKey"), relation.get("referenceObjectKey")
        if subject != target_key and not (
            reference == target_key and relation.get("source") in SYMMETRIC_SCENE_RELATION_TYPES
        ):
            continue
        other_key = reference if subject == target_key else subject
        other = objects.get(other_key)
        if other and other_key != target_key:
            place_chips.append(_place(language, relation["translation"], other))
    chips = {
        "colour": [c for c in _unique(colour_chips) if not mentions_target(c, forms)],
        "location": [c for c in _unique(place_chips) if not mentions_target(c, forms)],
    }
    prefixes = _prefixes(language, target_term.get("gender"))
    frames = [
        ClueFrame(
            frame_id=frame_id,
            prefix=prefixes[frame_id],
            meaning=MEANINGS[frame_id],
            example=f"{prefixes[frame_id]} {chips[frame_id][0]}",
            chips=chips[frame_id][:20],
        )
        for frame_id in ("colour", "location")
        if chips[frame_id]
    ]
    return frames, forms


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


def _squeeze(word):
    return re.sub(r"(\w)\1+", r"\1", word)


def _one_edit(a, b):
    if abs(len(a) - len(b)) > 1:
        return False
    if len(a) > len(b):
        a, b = b, a
    i = 0
    while i < len(a) and a[i] == b[i]:
        i += 1
    return a[i + (len(a) == len(b)):] == b[i + 1:]


def mentions_target(text, avoid_words):
    """Whole words ignoring case and accents; single words also match one-letter misspellings.

    "Tazas", "TAZA", "mesaa" and "mesaaa" all count for their targets; words of
    under four letters must match exactly so short unrelated words stay allowed.
    """
    folded = _fold(text)
    tokens = [_squeeze(token) for token in re.findall(r"\w+", folded)]
    for word in avoid_words:
        parts = _fold(word).split()
        if parts and re.search(
            r"(?<!\w)" + r"\s+".join(map(re.escape, parts)) + r"(?!\w)", folded
        ):
            return True
        if len(parts) == 1 and len(parts[0]) >= 4:
            form = _squeeze(parts[0])
            if any(len(token) >= 4 and _one_edit(form, token) for token in tokens):
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
    """Offered frames are the task's frames in order; legacy tasks may hide a Name frame."""
    frames = {frame.frame_id: frame for frame in content.clue_frames}
    offered = assistance.offered_frame_ids
    selected = [frames.get(frame_id) for frame_id in assistance.selected_frame_ids]
    if (
        None in selected
        or offered != [frame_id for frame_id in frames if frame_id in offered]
        or not set(assistance.selected_frame_ids) <= set(offered)
        or not set(assistance.inserted_chips) <= {c for frame in selected for c in frame.chips}
    ):
        raise PracticeConflictError("Clue assistance does not match this task.")
