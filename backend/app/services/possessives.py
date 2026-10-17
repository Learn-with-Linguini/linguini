"""Reviewed singular possessive sentences for A1 roleplay missions."""

import re

from app.services.mission_lessons import normalized_gender

_LEADING_ARTICLE = re.compile(
    r"^(?:(?:el|la|los|las|un|una|unos|unas|le|la|les|un|une|des|"
    r"der|die|das|den|dem|des|ein|eine|einen|einem|einer|eines)\s+|"
    r"(?:l|d)['’])",
    re.IGNORECASE,
)
_LETTERS = re.compile(r"[^\W\d_]+(?:[ '-][^\W\d_]+)*", re.UNICODE)
_FRENCH_VOWELS = set("aeiouyàâäéèêëîïôöùûüœ")
_CAST_NAMES = {"Ana": "아나", "Leo": "레오"}


def _gender(_language, value):
    return normalized_gender(value)


def _noun(language, value, gender):
    if not isinstance(value, str) or not _gender(language, gender):
        return None
    noun = _LEADING_ARTICLE.sub("", value.strip()).strip()
    if not noun or not _LETTERS.fullmatch(noun):
        return None
    if language == "fr" and noun[0].casefold() == "h":
        return None
    return noun


def _name(name):
    return name if name in _CAST_NAMES else None


def _french_vowel(noun):
    return noun[0].casefold() in _FRENCH_VOWELS


def _article(language, noun, gender):
    gender = _gender(language, gender)
    if not gender:
        return None
    if language == "es":
        return "el" if gender == "masculine" else "la"
    if language == "fr":
        return "l'" if _french_vowel(noun) else ("le" if gender == "masculine" else "la")
    if language == "de":
        return {"masculine": "den", "feminine": "die", "neuter": "das"}[gender]
    return None


def _with_article(article, noun):
    return f"{article}{noun}" if article.endswith("'") else f"{article} {noun}"


def definite_noun_phrase(language, noun, gender):
    noun = _noun(language, noun, gender)
    if noun is None:
        return None
    article = _article(language, noun, gender)
    return _with_article(article, noun) if article else None


def _has_batchim(noun):
    last = ord(noun[-1])
    if not 0xAC00 <= last <= 0xD7A3:
        return None
    return (last - 0xAC00) % 28 != 0


def _korean_ending(noun):
    batchim = _has_batchim(noun)
    return None if batchim is None else "이에요" if batchim else "예요"


def _korean_particle(noun):
    batchim = _has_batchim(noun)
    return None if batchim is None else "을" if batchim else "를"


def possessive_sentence(language, person, owner_name, noun, gender):
    """A reviewed singular possessive sentence, or None when its form is uncertain."""
    noun = _noun(language, noun, gender)
    if language not in {"es", "fr", "de", "ko"} or noun is None:
        return None
    if person not in {"first", "third"}:
        return None
    if person == "third" and _name(owner_name) is None:
        return None
    if language == "es":
        possessive = "mi" if person == "first" else "su"
        return f"Es {possessive} {noun}."
    if language == "fr":
        gender = _gender(language, gender)
        if person == "first":
            possessive = "mon" if gender == "masculine" or _french_vowel(noun) else "ma"
        else:
            possessive = "son" if gender == "masculine" or _french_vowel(noun) else "sa"
        return f"C'est {possessive} {noun}."
    if language == "de":
        gender = _gender(language, gender)
        if person == "first":
            possessive = "meine" if gender == "feminine" else "mein"
        else:
            possessive = (
                "ihr" if owner_name == "Ana" else "sein"
            ) + ("e" if gender == "feminine" else "")
        return f"Das ist {possessive} {noun[:1].upper()}{noun[1:]}."
    ending = _korean_ending(noun)
    if ending is None:
        return None
    if person == "first":
        return f"제 {noun}{ending}."
    return f"{_CAST_NAMES[owner_name]}의 {noun}{ending}."


def ownership_statement(language, owner_name, noun, gender):
    """A reviewed named-character ownership statement for the question prompt."""
    noun = _noun(language, noun, gender)
    if language not in {"es", "fr", "de", "ko"} or noun is None or _name(owner_name) is None:
        return None
    if language == "es":
        article = _article(language, noun, gender)
        return f"Es {_with_article(article, noun)} de {owner_name}."
    if language == "fr":
        phrase = definite_noun_phrase(language, noun, gender)
        owner = (
            f"d'{owner_name}"
            if owner_name[0].casefold() in _FRENCH_VOWELS
            else f"de {owner_name}"
        )
        return f"C'est {phrase} {owner}."
    if language == "de":
        possessive = "Anas" if owner_name == "Ana" else "Leos"
        return f"Das ist {possessive} {noun[:1].upper()}{noun[1:]}."
    ending = _korean_ending(noun)
    return f"{_CAST_NAMES[owner_name]}의 {noun}{ending}." if ending else None
