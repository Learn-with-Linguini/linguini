"""Targeted Korean checks for particle forms; this is not a general grammar checker.

Only rules without exceptions are checked: after a syllable ending in a consonant
(받침) the copula is 이에요 and the object particle is 을, so 예요 or 를 directly after
such a syllable is always wrong (문예요 → 문이에요, 책를 → 책을).
"""

from __future__ import annotations

import re

from ..generation import ApprovedVocabulary, CandidateSentence, ValidatorResult
from ..schema import LanguagePack

_FIRST_SYLLABLE, _LAST_SYLLABLE = 0xAC00, 0xD7A3
_FORMS = (
    ("예요", "After a final consonant the copula is 이에요, not 예요 (문이에요)."),
    ("를", "After a final consonant the object particle is 을, not 를 (책을)."),
)


def _has_final_consonant(syllable: str) -> bool:
    code = ord(syllable)
    return _FIRST_SYLLABLE <= code <= _LAST_SYLLABLE and (code - _FIRST_SYLLABLE) % 28 != 0


class KoreanValidator:
    validator_id = "ko-targeted@1"

    def __init__(self, vocabulary: ApprovedVocabulary) -> None:
        self.vocabulary = vocabulary

    def validate(self, candidate: CandidateSentence, _pack: LanguagePack) -> ValidatorResult:
        messages = []
        for form, message in _FORMS:
            for match in re.finditer(form, candidate.text):
                before = candidate.text[match.start() - 1] if match.start() else ""
                if before and _has_final_consonant(before) and message not in messages:
                    messages.append(message)
        return ValidatorResult(passed=not messages, messages=messages)
