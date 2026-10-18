"""Targeted Spanish M01 checks; this is not a general grammar checker."""

from __future__ import annotations

from ..generation import (
    ApprovedVocabulary,
    CandidateSentence,
    ValidatorResult,
    register_validator,
)
from ..schema import LanguagePack


class SpanishM01Validator:
    validator_id = "es-targeted@1"

    def __init__(self, vocabulary: ApprovedVocabulary) -> None:
        self.terms = {term.term_id: term for term in vocabulary.terms}

    def validate(self, candidate: CandidateSentence, _pack: LanguagePack) -> ValidatorResult:
        messages = []
        uses = {item.role: item for item in candidate.term_uses if item.role}
        object_use = uses.get("object") or uses.get("subject") or uses.get("first")
        attribute_use = uses.get("attribute")
        folded_text = candidate.text.casefold()
        if object_use is not None:
            object_term = self.terms.get(object_use.term_id)
            if object_term is not None:
                bare = object_term.forms_by_key.get("bare")
                if candidate.spec_use == "name":
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
                if candidate.construction_id in {"scene-location", "connected-description"}:
                    article_keys = ("article_definite", "article_indefinite")
                elif candidate.spec_use == "name" or (
                    candidate.spec_use in {"question", "followup"}
                    and candidate.construction_id == "describe-attribute"
                ):
                    article_keys = ("article_definite",)
                else:
                    article_keys = ("article_indefinite",)
                articles = [
                    object_term.forms_by_key.get(key)
                    for key in article_keys
                    if object_term.forms_by_key.get(key)
                ]
                negative_existence = (
                    candidate.construction_id == "scene-existence"
                    and folded_text.startswith(f"no hay ningún {bare}")
                )
                if articles and bare and not negative_existence and not any(
                    f"{article} {bare}" in folded_text for article in articles
                ):
                    messages.append(
                        "The determiner must match the approved noun gender."
                    )
                if attribute_use is not None:
                    attribute_term = self.terms.get(attribute_use.term_id)
                    if attribute_term is not None:
                        agreement = object_term.agreement
                        expected = attribute_term.forms_by_key.get(agreement or "")
                        if expected and attribute_use.surface != expected:
                            messages.append(
                                "The adjective form must agree with the approved noun."
                            )
                        if (
                            attribute_term.position == "after"
                            and bare
                            and candidate.text.find(attribute_use.surface)
                            < candidate.text.find(bare)
                        ):
                            messages.append(
                                "The basic colour adjective follows the noun."
                            )
        reference_use = uses.get("reference")
        if reference_use is not None:
            reference_term = self.terms.get(reference_use.term_id)
            if reference_term is not None:
                definite = reference_term.forms_by_key.get("article_definite")
                bare = reference_term.forms_by_key.get("bare")
                if definite and bare and f"{definite} {bare}" not in candidate.text:
                    messages.append(
                        "Location references use the definite determiner for the approved noun."
                    )

        text = candidate.text.casefold()
        if candidate.spec_use != "name" and not text.endswith((".", "?", "!")):
            messages.append("Complete sentences need final punctuation.")
        if candidate.spec_use in {"question", "prompt"} or text.lstrip().startswith("¿"):
            if not text.startswith("¿") or not text.endswith("?"):
                messages.append("Questions need opening and closing Spanish marks.")
        if " de el " in f" {text} " or " a el " in f" {text} ":
            messages.append("Spanish contracts de el to del and a el to al.")
        if candidate.construction_id == "scene-existence":
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
                    messages.append(
                        "Yes/no answers start with Sí/No and name the shown object."
                    )
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
