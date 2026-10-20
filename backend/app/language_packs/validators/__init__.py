"""Language-scoped validator selection; instances never share session vocabulary."""

from ..generation import ApprovedVocabulary
from .checks import CombinedValidator, PackChecksValidator, has_pack_checks
from .noun_phrase import NounPhraseValidator

STRUCTURE_VERSION = "language-pack-structure.v4"

_FACTORIES = {}


def register_validator_factory(language: str, factory) -> None:
    """Register a versioned validator type that receives request-local vocabulary."""
    _FACTORIES[language] = factory


def _factory(language):
    if language in _FACTORIES:
        return _FACTORIES[language]
    if language == "es":
        from .es import SpanishM01Validator

        return SpanishM01Validator
    return None


def _uses_noun_phrases(pack) -> bool:
    return pack is not None and pack.language.articles == "required"


def validator_versions(language: str, pack=None) -> dict[str, str]:
    factory = _factory(language)
    versions = {language: factory.validator_id} if factory else {}
    if _uses_noun_phrases(pack):
        versions["noun-phrase"] = NounPhraseValidator.validator_id
    if has_pack_checks(pack):
        versions["pack-checks"] = PackChecksValidator.validator_id
    return versions


def select_validator(language: str, vocabulary: ApprovedVocabulary, pack=None):
    """The language's targeted validator, shared noun-phrase rules and pack checks."""
    factory = _factory(language)
    validators = [factory(vocabulary)] if factory else []
    if _uses_noun_phrases(pack):
        validators.append(NounPhraseValidator(vocabulary))
    if has_pack_checks(pack):
        validators.append(PackChecksValidator())
    if len(validators) > 1:
        return CombinedValidator(validators)
    return validators[0] if validators else None
