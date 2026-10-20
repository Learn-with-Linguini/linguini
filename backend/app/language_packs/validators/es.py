"""Targeted Spanish M01 checks; this is not a general grammar checker."""

from __future__ import annotations

import re

from ..generation import (
    ApprovedVocabulary,
    CandidateSentence,
    ValidatorResult,
    register_validator,
)
from ..schema import LanguagePack


def _contains_phrase(text: str, phrase: str, *, contractions: bool = False) -> bool:
    # Translation capitalisation and word spacing do not change agreement.
    words = phrase.casefold().split()
    parts = [re.escape(word) for word in words]
    if contractions and words and words[0] == "el":
        parts[0] = "(?:el|del|al)"
    pattern = r"\s+".join(parts)
    return bool(re.search(r"(?<!\w)" + pattern + r"(?!\w)", text.casefold()))


# Choices that are phrases, not sentences: no final punctuation.
_PHRASE_CONSTRUCTIONS = {"location-phrase", "quantity-chunk"}


def _is_phrase(candidate):
    """Name chunks, position phrases and number-noun chunks are not sentences."""
    return candidate.spec_use == "name" or candidate.construction_id in _PHRASE_CONSTRUCTIONS


class SpanishM01Validator:
    validator_id = "es-targeted@7"

    def __init__(self, vocabulary: ApprovedVocabulary) -> None:
        self.terms = {term.term_id: term for term in vocabulary.terms}

    def validate(self, candidate: CandidateSentence, _pack: LanguagePack) -> ValidatorResult:
        messages = []
        if candidate.proposed_realizations:
            # Open wording is assessed against meanings/context by the mandatory
            # model reviewer. Do not force it into reference-example templates.
            text = candidate.text.casefold()
            if not _is_phrase(candidate) and not text.endswith((".", "?", "!")):
                messages.append("Complete sentences need final punctuation.")
            if candidate.spec_use in {"question", "prompt"} and (
                not text.startswith("¿") or not text.endswith("?")
            ):
                messages.append("Questions need opening and closing Spanish marks.")
            if " de el " in f" {text} " or " a el " in f" {text} ":
                messages.append("Spanish contracts de el to del and a el to al.")
            return ValidatorResult(passed=not messages, messages=messages)
        uses = {item.role: item for item in candidate.term_uses if item.role}
        object_use = uses.get("object") or uses.get("subject") or uses.get("first")
        # Article/gender agreement, adjective agreement and adjective position are
        # checked by the shared noun-phrase validator (validators/noun_phrase.py).
        if object_use is not None and candidate.spec_use == "name":
            object_term = self.terms.get(object_use.term_id)
            if object_term is not None:
                expected_name = object_term.forms_by_key.get("definite")
                if (
                    expected_name is None
                    or candidate.text != expected_name
                    or candidate.text[:1].isupper()
                    or candidate.text.endswith((".", "?", "!"))
                ):
                    messages.append(
                        "Name chunks use the lower-case definite article and noun "
                        "without final punctuation."
                    )
        reference_use = uses.get("reference")
        if reference_use is not None:
            reference_term = self.terms.get(reference_use.term_id)
            if reference_term is not None:
                definite = reference_term.forms_by_key.get("article_definite")
                bare = reference_term.forms_by_key.get("bare")
                if definite and bare and not _contains_phrase(
                    candidate.text, f"{definite} {bare}", contractions=True,
                ):
                    messages.append(
                        "Location references use the definite determiner for the approved noun."
                    )

        text = candidate.text.casefold()
        if candidate.spec_use == "wrongExistence" and "no hay " not in text:
            messages.append("The false existence option must deny the bound object's presence.")
        if not _is_phrase(candidate) and not text.endswith((".", "?", "!")):
            messages.append("Complete sentences need final punctuation.")
        if candidate.spec_use in {"question", "prompt"} or text.lstrip().startswith("¿"):
            if not text.startswith("¿") or not text.endswith("?"):
                messages.append("Questions need opening and closing Spanish marks.")
        if " de el " in f" {text} " or " a el " in f" {text} ":
            messages.append("Spanish contracts de el to del and a el to al.")
        if candidate.construction_id == "scene-existence":
            if (
                candidate.truth is False
                and candidate.spec_use != "falseFirst"
                and not text.startswith("no hay ")
            ):
                messages.append(
                    "False existence statements must negate the bound object's presence."
                )
            if not text.startswith(("hay ", "también hay ", "no hay ")):
                messages.append("Scene existence uses hay.")
            if text.startswith(("hay el ", "hay la ", "hay los ", "hay las ")):
                messages.append("Hay introduces an indefinite noun phrase.")
        elif candidate.construction_id == "scene-location":
            if " está " not in f" {text} " or " es " in f" {text} ":
                messages.append("Location uses está, not es.")
        elif candidate.construction_id == "yes-no-identification":
            if candidate.spec_use in {"question", "prompt"} and not text.startswith("¿es "):
                messages.append("Yes/no identification questions use ¿Es …?")
            if candidate.spec_use in {"answer", "option"}:
                expected = "sí," if candidate.label_uses == ["yes"] else "no,"
                if not text.startswith(expected) or " es " not in f" {text} ":
                    messages.append("Yes/no answers start with Sí/No and name the shown object.")
        elif candidate.construction_id == "describe-attribute":
            if text.startswith("¿de qué color") and " es " not in f" {text} ":
                messages.append("Colour questions use es.")
            elif (
                not text.startswith(("es ", "¿de qué color", "¿dónde"))
                and candidate.spec_use != "question"
            ):
                messages.append("Object descriptions use Es.")
        elif candidate.construction_id == "identify-object":
            if candidate.spec_use != "name" and not text.startswith(("es ", "esto es ")):
                messages.append("Object identification uses Es.")
        elif candidate.construction_id == "connected-description":
            if not any(form in text for form in ("hay ", "está ")):
                messages.append("Connected scene descriptions need a bound scene predicate.")

        return ValidatorResult(passed=not messages, messages=messages)


def register_spanish_validators(vocabulary: ApprovedVocabulary) -> None:
    validator = SpanishM01Validator(vocabulary)
    for construction_id in (
        "identify-object",
        "yes-no-identification",
        "describe-attribute",
        "scene-existence",
        "scene-location",
        "connected-description",
    ):
        register_validator("es", construction_id, validator)
