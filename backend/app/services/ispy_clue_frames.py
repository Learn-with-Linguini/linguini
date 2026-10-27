"""Guided I-Spy clue frames built only from confirmed, translated scene facts.

The grammar a frame needs (prefixes, articles, contractions, positions and colours) is
the language pack's ``clues.toml``; a language whose ready pack has none gets no frames.
"""

import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache

from app.repositories.practice import ClueNamesTargetError, PracticeConflictError
from app.schemas.enums import SYMMETRIC_SCENE_RELATION_TYPES
from app.schemas.tasks import (
    ClueAssistance,
    ClueFrame,
    ClueSlot,
    ClueSlotChip,
    ReflectionContent,
)

GENDERS = ("masculine", "feminine", "neuter")
MEANINGS = {
    "colour": "It is … — say what colour your object is.",
    "location": "It is … — say where your object is, using another object as a reference.",
}
COLOUR_ATTRIBUTE_TYPES = {"color", "colour"}


@dataclass(frozen=True)
class ClueGrammar:
    """A language's clue grammar (its pack's ``clues.toml``), ready for lookups."""

    clues: object
    articleless: bool

    def prefix(self, frame, gender):
        prefixes = [item for item in self.clues.prefixes if item.frame == frame]
        return next(
            (item.text for item in prefixes if gender and item.agreement == gender),
            next(item.text for item in prefixes if item.agreement is None),
        )

    def definite(self, gender):
        return next((a.text for a in self.clues.articles if a.agreement == gender), None)

    def place_article(self, article, gender):
        """The article after a position: the term's own, or its ``place_articles`` form."""
        if not self.clues.place_articles:
            return article
        gender = gender or next(
            (a.agreement for a in self.clues.articles
             if a.text.casefold() == article.casefold()), None,
        )
        return next((a.text for a in self.clues.place_articles if a.agreement == gender), None)

    def contraction(self, preposition, article):
        return next((
            item.text for item in self.clues.contractions
            if (item.preposition.casefold(), item.article.casefold())
            == (preposition.casefold(), article.casefold())
        ), None)

    def starts_with_verb(self, text):
        folded = _fold(text)
        return any(folded.startswith(f"{_fold(start)} ")
                   for start in self.clues.location_verb_starts)

    @property
    def reference_first(self):
        return self.clues.place.index("{reference}") < self.clues.place.index("{position}")


@lru_cache(maxsize=16)
def _grammar_of(pack_json, experimental, require_release=False):
    from app.language_packs.schema import LanguagePack

    pack = LanguagePack.model_validate_json(pack_json)
    clues = pack.clues
    if clues is None or (
        require_release and not experimental and clues.provenance.review_status != "humanReviewed"
    ):
        return None
    return ClueGrammar(clues, articleless=pack.language.articles == "none")


def clue_grammar(language):
    """The clue grammar of ``language``'s ready pack, or ``None`` (no clue frames)."""
    from app.config import get_language_pack_require_release
    from app.language_packs.context import resolve_language_context

    if not language:
        return None
    try:
        context = resolve_language_context(str(language).lower())
    except ValueError:
        return None
    return None if context is None else _grammar_of(
        context.pack_json, context.experimental, get_language_pack_require_release(),
    )


def _with_article(article, noun):
    return f"{article}{noun}" if article.endswith("'") else f"{article} {noun}"


def _definite(grammar, term):
    if grammar.articleless:
        return None
    if term.get("article"):
        return term["article"]
    return grammar.definite(term.get("gender"))


def _reference_phrase(grammar, term):
    article = _definite(grammar, term)
    return _with_article(article, term["translation"]) if article else term["translation"]


def _place(language, preposition, term):
    """The location phrase for ``preposition`` and a reference term, or ``None``."""
    grammar = clue_grammar(language)
    return None if grammar is None else _place_with(grammar, preposition, term)


def _place_with(grammar, preposition, term):
    place = grammar.clues.place
    if grammar.articleless:
        return place.format(position=preposition, reference=term["translation"])
    article = _definite(grammar, term)
    if not article or grammar.starts_with_verb(preposition):
        return None
    words = preposition.split()
    article = grammar.place_article(article, term.get("gender"))
    if not article:
        return None
    contracted = grammar.contraction(words[-1], article)
    if contracted:
        return place.format(position=" ".join([*words[:-1], contracted]),
                            reference=term["translation"])
    return place.format(position=preposition,
                        reference=_with_article(article, term["translation"]))


def agree_colour(language, adjective, gender):
    """The colour form agreeing with a singular noun, or None when it is not certain."""
    grammar = clue_grammar(language)
    return None if grammar is None else _agree_with(grammar, adjective, gender)


def colour_key(language, text):
    """One key for a colour however it is written: its gender form, a written clue
    form (빨간색이에요) or a recognised spelling (빨간). ``None`` for an unknown colour."""
    grammar = clue_grammar(language)
    if grammar is None:
        return None
    folded = _fold(text.strip())
    return next((
        colour.forms[0] for colour in grammar.clues.colours
        if folded in {_fold(form) for form in [*colour.forms, *colour.recognised]}
    ), None)


def _agree_with(grammar, adjective, gender):
    folded = _fold(adjective.strip())
    for colour in grammar.clues.colours:
        if folded in {_fold(form) for form in colour.recognised or colour.forms}:
            forms = colour.forms
            if len(set(forms)) == 1:
                return forms[0]
            return dict(zip(GENDERS, forms, strict=False)).get(gender)
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
    grammar = clue_grammar(language)
    if grammar is None:
        return [], []
    clues = grammar.clues
    facts = context.get("sceneObjects", {})
    objects = {term["key"]: term for term in facts.get("objects", [])}
    target_key = str(target.id)
    target_term = objects.get(target_key, {})
    gender = target_term.get("gender")
    forms = _target_forms(grammar, target, word, target_term)
    prefixes = {frame: grammar.prefix(frame, gender) for frame in ("colour", "location")}
    frames = []

    confirmed_colours = [
        (_agree_with(grammar, term["translation"], gender), term.get("source"))
        for term in facts.get("attributes", [])
        if term.get("objectKey") == target_key
        and term["key"].rsplit(":", 1)[-1] in COLOUR_ATTRIBUTE_TYPES
    ]
    colour_help = _allowed([form for form, _ in confirmed_colours], forms)
    if colour_help:
        bank = {}
        bank_colours = [
            (_agree_with(grammar, colour.forms[0], gender), colour.meaning)
            for colour in clues.colours if colour.bank
        ]
        for form, meaning in [*bank_colours, *confirmed_colours]:
            if form and not mentions_target(form, forms):
                bank.setdefault(_fold(form), (form, meaning))
        frames.append(ClueFrame(
            frame_id="colour",
            prefix=prefixes["colour"],
            meaning=MEANINGS["colour"],
            example=clues.examples.colour,
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
        article = term and _definite(grammar, term)
        if str(key) != target_key and term and (article or grammar.articleless):
            text = _reference_phrase(grammar, term)
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
        if (
            other and other_key != target_key
            and _fold(_reference_phrase(grammar, other)) in references
        ):
            location_help.append(_place_with(grammar, relation["translation"], other))
            extra_positions.append((relation["translation"], relation.get("source"), None))
    location_help = _allowed(location_help, forms)
    if location_help and references:
        positions = {}
        bank_positions = [(item.text, item.meaning, item.example) for item in clues.positions]
        for text, meaning, example in [*bank_positions, *extra_positions]:
            if not grammar.starts_with_verb(text):
                positions.setdefault(_fold(text), (text, meaning, example))
        phrases = {
            f"{position}|{reference}": phrase
            for position, _, _ in positions.values()
            for reference, term in references.values()
            if (phrase := _place_with(grammar, position, term))
        }
        frames.append(ClueFrame(
            frame_id="location",
            prefix=prefixes["location"],
            meaning=MEANINGS["location"],
            example=clues.examples.location,
            template=(
                f"{prefixes['location']} [reference object] [position]"
                if grammar.reference_first
                else f"{prefixes['location']} [position] [reference object]"
            ),
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


def _target_forms(grammar, target, word, target_term):
    forms = [word.lemma, word.display_text, word.plural_form, target.label]
    forms.append(target_term.get("translation"))
    plurals = []
    for form in filter(None, forms):
        if " " in form.strip():
            continue
        plurals.append(f"{form}s")
        if _fold(form)[-1:] not in "aeiou":
            plurals.append(f"{form}es")
        for plural in grammar.clues.avoid_plurals:
            if _fold(form).endswith(tuple(_fold(ending) for ending in plural.after)):
                plurals.append(f"{form}{plural.suffix}")
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
