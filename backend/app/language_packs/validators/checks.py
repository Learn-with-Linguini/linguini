"""Pack-declared surface checks shared by every language; not a grammar checker."""

from __future__ import annotations

from ..generation import CandidateSentence, ValidatorResult
from ..schema import LanguagePack


def has_pack_checks(pack: LanguagePack | None) -> bool:
    return pack is not None and any(item.checks for item in pack.constructions)


class PackChecksValidator:
    """Runs each construction's `checks`; rule content is versioned by the pack fingerprint."""

    validator_id = "pack-checks.v1"

    def validate(self, candidate: CandidateSentence, pack: LanguagePack) -> ValidatorResult:
        construction = next(
            (c for c in pack.constructions if c.construction_id == candidate.construction_id),
            None,
        )
        messages = [
            f"{check.message} (pack check {check.check_id})"
            for check in (construction.checks if construction else [])
            if check.applies(candidate.spec_use, candidate.truth)
            and not check.passes(candidate.text)
        ]
        return ValidatorResult(passed=not messages, messages=messages)


class CombinedValidator:
    """Every validator must pass; messages are reported together for repair."""

    def __init__(self, validators) -> None:
        self.validators = list(validators)
        self.validator_id = "+".join(item.validator_id for item in self.validators)

    def validate(self, candidate: CandidateSentence, pack: LanguagePack) -> ValidatorResult:
        results = [item.validate(candidate, pack) for item in self.validators]
        return ValidatorResult(
            passed=all(result.passed for result in results),
            messages=[message for result in results for message in result.messages],
        )
