"""Vocabulary-aware noun-phrase checks for packs whose nouns require articles.

Generalized from the Spanish targeted validator. Every rule reads the session's own
forms (articles, agreement forms, adjective position), never a fixed word list, so
it applies to any language declaring `articles = "required"`. Model-proposed wording
is left to the contextual model review, as in the Spanish validator.
"""

from __future__ import annotations

import re

from ..generation import ApprovedVocabulary, CandidateSentence, ValidatorResult
from ..schema import LanguagePack

AGREEMENT_KEYS = ("masculine", "feminine", "neuter")
# Words allowed between a determiner and its noun (attributive adjectives).
_MAX_BETWEEN = 2
# Counting constructions introduce the noun with a number or quantity word (cinco
# libros, combien de, wie viele) instead of an article; numbers are checked elsewhere.
COUNTING = frozenset({
    "how-many-question", "quantity-chunk", "quantity-statement", "quantity-comparison",
    "quantity-pair",
})
# Ownership constructions introduce the noun with a possessive (mi taza, meine Tasse) or
# name it beside one; possessive agreement is checked by the deterministic count rules.
OWNING = frozenset({
    "ownership-question", "ownership-statement", "owned-object", "possessive-statement",
    "whose-question", "owned-description",
})
# Preference constructions name a liked or chosen object in the case its verb takes
# (Ich mag den Teller), which the session's nominative forms do not cover.
PREFERRING = frozenset({
    "my-preference", "their-preference", "preference-question", "choice-statement",
})
# Request constructions introduce the item with a quantity (dos cafés, einen Kaffee) or
# leave it out (Para llevar, por favor.); quantities are pack request words.
REQUESTING = frozenset({
    "polite-request", "order-phrase", "detail-question", "detail-reply", "order-repeat",
    "order-confirmation", "order-repair",
})


def _word(text: str) -> str:
    return r"(?<!\w)" + re.escape(text.casefold()) + r"(?!\w)"


def _determiners(term) -> list[tuple[str, str]]:
    """(family, determiner) pairs taken from the term's own forms.

    Families: definite, indefinite, negative. Keys such as definite_dative or
    indefinite_accusative contribute case forms; article_* keys are bare articles.
    """
    bare = term.forms_by_key.get("bare", "")
    found = []
    for key, form in term.forms_by_key.items():
        family = next(
            (name for name in ("definite", "indefinite", "negative")
             if key.removeprefix("article_").startswith(name)),
            None,
        )
        if family is None:
            continue
        if key.startswith("article_"):
            determiner = form
        elif bare and form.casefold().endswith(bare.casefold()) and len(form) > len(bare):
            determiner = form[: len(form) - len(bare)].strip()
        else:
            continue
        if determiner:
            found.append((family, determiner))
    return list(dict.fromkeys(found))


def _phrase_families(text: str, term) -> set[str]:
    """Families of the term's determiners that introduce its noun in the text."""
    bare = term.forms_by_key.get("bare")
    if not bare:
        return set()
    folded = text.casefold()
    families = set()
    for family, determiner in _determiners(term):
        # Elided articles (l', d') attach directly to the next word.
        gap = r"\s*" if determiner.endswith("'") else r"\s+"
        pattern = (
            r"(?<!\w)" + re.escape(determiner.casefold()) + gap
            + r"(?:\S+\s+){0," + str(_MAX_BETWEEN) + r"}?" + _word(bare)
        )
        if re.search(pattern, folded):
            families.add(family)
    return families


def _required_family(candidate: CandidateSentence) -> str | None:
    """Definiteness each M01 construction teaches; None accepts either."""
    if candidate.construction_id in {
        "scene-location", "connected-description", "target-location",
    }:
        return None
    if candidate.construction_id in {"find-object", "where-question"}:
        # Finding or locating a named object refers to it with the definite article.
        return "definite"
    if candidate.construction_id == "describe-attribute" and candidate.spec_use == "answer":
        # Es una taza roja. / La taza es roja. (predicative) are both descriptions.
        return None
    if candidate.spec_use == "name" or (
        candidate.construction_id == "describe-attribute"
        and candidate.spec_use in {"question", "followup"}
    ):
        return "definite"
    # Identifying, confirming, describing and stating existence introduce the object.
    return "indefinite"


class NounPhraseValidator:
    validator_id = "noun-phrase.v5"

    def __init__(self, vocabulary: ApprovedVocabulary) -> None:
        self.terms = {term.term_id: term for term in vocabulary.terms}

    def validate(self, candidate: CandidateSentence, _pack: LanguagePack) -> ValidatorResult:
        if candidate.proposed_realizations or candidate.construction_id in (
            COUNTING | OWNING | PREFERRING | REQUESTING
        ):
            return ValidatorResult(passed=True)
        messages = []
        uses = {item.role: item for item in candidate.term_uses if item.role}
        object_use = uses.get("object") or uses.get("subject") or uses.get("first")
        noun = self.terms.get(object_use.term_id) if object_use else None
        if noun is None:
            return ValidatorResult(passed=True)
        bare = noun.forms_by_key.get("bare")
        determiners = _determiners(noun)
        # A negated existence may use a gender-neutral partitive (pas de, ningún).
        negated = (
            candidate.construction_id == "scene-existence"
            and candidate.truth is False
            and candidate.spec_use != "falseFirst"
        )
        families = _phrase_families(candidate.text, noun)
        required = _required_family(candidate)
        allowed = [
            determiner for family, determiner in determiners
            if required is None or family == required
        ]
        if bare and allowed and not negated and not (
            families if required is None else required in families
        ):
            kind = f"{required} " if required else ""
            messages.append(
                f"Use one of this noun's own {kind}articles with {bare!r} "
                f"(agreement={noun.agreement!r}): {', '.join(sorted(set(allowed)))}."
            )
        attribute_use = uses.get("attribute")
        attribute = self.terms.get(attribute_use.term_id) if attribute_use else None
        if attribute is not None and bare:
            keyed = {
                key: attribute.forms_by_key[key]
                for key in AGREEMENT_KEYS
                if key in attribute.forms_by_key
            }
            surface = attribute_use.surface
            attributive = surface.casefold() in {
                *(value.casefold() for value in keyed.values()),
                attribute.forms_by_key.get("modifier", "").casefold(),
            }
            expected_form = keyed.get(noun.agreement or "")
            # After an indefinite article the gender ending is fixed; after a definite
            # article some languages (German) use one weak ending for every gender.
            if (
                expected_form
                and attributive
                and "indefinite" in families
                and surface.casefold() != expected_form.casefold()
            ):
                messages.append(
                    f"The adjective agrees with {bare!r} ({noun.agreement}): {expected_form}."
                )
            if attributive and attribute.position in {"before", "after"}:
                adjective_at = re.search(_word(surface), candidate.text.casefold())
                noun_at = re.search(_word(bare), candidate.text.casefold())
                if adjective_at and noun_at:
                    before = adjective_at.start() < noun_at.start()
                    if before != (attribute.position == "before"):
                        messages.append(
                            f"This adjective goes {attribute.position} the noun {bare!r}."
                        )
        return ValidatorResult(passed=not messages, messages=messages)
