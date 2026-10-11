"""Guided I-Spy clue frames built only from confirmed, translated scene facts."""

import re
import unicodedata

from app.repositories.practice import ClueNamesTargetError, PracticeConflictError
from app.schemas.enums import SYMMETRIC_SCENE_RELATION_TYPES
from app.schemas.tasks import (
    ClueAssistance,
    ClueFrame,
    ClueSlot,
    ClueSlotChip,
    ReflectionContent,
)

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
# A small introduced bank: (expression, meaning, teaching example about other objects).
POSITIONS = {
    "es": [
        ("sobre", "on", "El libro está sobre la mesa."),
        ("debajo de", "under", "El gato está debajo de la silla."),
        ("al lado de", "next to", "La silla está al lado de la puerta."),
        ("delante de", "in front of", "El perro está delante de la casa."),
        ("detrás de", "behind", "El árbol está detrás de la casa."),
    ],
    "fr": [
        ("sur", "on", "Le livre est sur la table."),
        ("sous", "under", "Le chat est sous la chaise."),
        ("à côté de", "next to", "La chaise est à côté de la porte."),
        ("devant", "in front of", "Le chien est devant la maison."),
        ("derrière", "behind", "L'arbre est derrière la maison."),
    ],
}
COLOUR_BANK = {
    "es": [("rojo", "red"), ("azul", "blue"), ("verde", "green"), ("blanco", "white"),
           ("negro", "black"), ("amarillo", "yellow")],
    "fr": [("rouge", "red"), ("bleu", "blue"), ("vert", "green"), ("blanc", "white"),
           ("noir", "black"), ("jaune", "yellow")],
}
TEACHING_EXAMPLES = {
    "es": {"colour": "La manzana es roja.", "location": "El libro está sobre la mesa."},
    "fr": {"colour": "La pomme est rouge.", "location": "Le livre est sur la table."},
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


def build_clue_support(context, target, word, introduced_keys=()):
    """Colour and Location frames whose slots offer introduced vocabulary banks.

    Choices are language options, not scene claims, so they include plausible wrong
    answers; the correct phrases from confirmed facts are kept as optional ``help``.
    Reference nouns come only from ``introduced_keys`` (this session's lesson words).
    """
    language = context.get("targetLanguage")
    if language not in SUPPORTED_LANGUAGES:
        return [], []
    facts = context.get("sceneObjects", {})
    objects = {term["key"]: term for term in facts.get("objects", [])}
    target_key = str(target.id)
    target_term = objects.get(target_key, {})
    gender = target_term.get("gender")
    forms = _target_forms(language, target, word, target_term)
    prefixes = _prefixes(language, gender)
    frames = []

    confirmed_colours = [
        (agree_colour(language, term["translation"], gender), term.get("source"))
        for term in facts.get("attributes", [])
        if term.get("objectKey") == target_key
        and term["key"].rsplit(":", 1)[-1] in COLOUR_ATTRIBUTE_TYPES
    ]
    colour_help = _allowed([form for form, _ in confirmed_colours], forms)
    if colour_help:
        bank = {}
        bank_colours = [(agree_colour(language, c, gender), m) for c, m in COLOUR_BANK[language]]
        for form, meaning in [*bank_colours, *confirmed_colours]:
            if form and not mentions_target(form, forms):
                bank.setdefault(_fold(form), (form, meaning))
        frames.append(ClueFrame(
            frame_id="colour",
            prefix=prefixes["colour"],
            meaning=MEANINGS["colour"],
            example=TEACHING_EXAMPLES[language]["colour"],
            template=f"{prefixes['colour']} [colour]",
            slots=[ClueSlot(slot_id="colour", label="colour", chips=[
                ClueSlotChip(text=form, meaning=meaning)
                for _, (form, meaning) in sorted(bank.items())
            ])],
            help=colour_help,
        ))

    references = {}
    for key in introduced_keys:
        term = objects.get(str(key))
        article = term and _definite(language, term)
        if str(key) != target_key and article:
            text = _with_article(article, term["translation"])
            if not mentions_target(text, forms):
                references.setdefault(_fold(text), (text, term))
    location_help, extra_positions = [], []
    for relation in facts.get("relations", []):
        subject, reference = relation.get("subjectObjectKey"), relation.get("referenceObjectKey")
        if subject != target_key and not (
            reference == target_key and relation.get("source") in SYMMETRIC_SCENE_RELATION_TYPES
        ):
            continue
        other_key = reference if subject == target_key else subject
        other = objects.get(other_key)
        if other and other_key != target_key and _fold(_with_article(
            _definite(language, other) or "", other["translation"]
        )) in references:
            location_help.append(_place(language, relation["translation"], other))
            extra_positions.append((relation["translation"], relation.get("source"), None))
    location_help = _allowed(location_help, forms)
    if location_help and references:
        positions = {}
        for text, meaning, example in [*POSITIONS[language], *extra_positions]:
            if not _fold(text).startswith(LOCATION_VERB_STARTS):
                positions.setdefault(_fold(text), (text, meaning, example))
        phrases = {
            f"{position}|{reference}": phrase
            for position, _, _ in positions.values()
            for reference, term in references.values()
            if (phrase := _place(language, position, term))
        }
        frames.append(ClueFrame(
            frame_id="location",
            prefix=prefixes["location"],
            meaning=MEANINGS["location"],
            example=TEACHING_EXAMPLES[language]["location"],
            template=f"{prefixes['location']} [position] [reference object]",
            slots=[
                ClueSlot(slot_id="position", label="position", chips=[
                    ClueSlotChip(text=text, meaning=meaning, example=example)
                    for text, meaning, example in positions.values()
                ][:12]),
                ClueSlot(slot_id="reference", label="reference object", chips=[
                    ClueSlotChip(text=text, meaning=term.get("source"))
                    for text, term in sorted(references.values())
                ][:12]),
            ],
            phrases=phrases,
            help=location_help,
        ))
    return frames, forms


def _allowed(values, forms):
    return [value for value in _unique(values) if not mentions_target(value, forms)][:12]


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
    """Whole target forms ignoring case and accents; near-misses only warn client-side."""
    folded = _fold(text)
    return any(
        parts and re.search(
            r"(?<!\w)" + r"\s+".join(map(re.escape, parts)) + r"(?!\w)", folded
        )
        for parts in (_fold(word).split() for word in avoid_words)
    )


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
    """Assistance must name offered frames, slots and chips; legacy Name frames stay valid."""
    frames = {frame.frame_id: frame for frame in content.clue_frames}
    offered = assistance.offered_frame_ids
    selected_ids = set(assistance.selected_frame_ids)
    selected = [frames.get(frame_id) for frame_id in assistance.selected_frame_ids]
    revealed = set(assistance.revealed_help_frame_ids)
    if (
        None in selected
        or offered != [frame_id for frame_id in frames if frame_id in offered]
        or not selected_ids <= set(offered)
        or not revealed <= set(offered)
    ):
        raise PracticeConflictError("Clue assistance does not match this task.")
    allowed = {
        chip
        for frame in selected
        for chip in [
            *frame.chips,
            *(frame.help if frame.frame_id in revealed else []),
            *frame.phrases.values(),
            *(choice.text for slot in frame.slots for choice in slot.chips),
        ]
    }
    slots_ok = all(
        choice.frame_id in selected_ids
        and any(
            slot.slot_id == choice.slot_id and choice.chip in {c.text for c in slot.chips}
            for slot in frames[choice.frame_id].slots
        )
        for choice in assistance.selected_slots
    )
    if not set(assistance.inserted_chips) <= allowed or not slots_ok:
        raise PracticeConflictError("Clue assistance does not match this task.")
