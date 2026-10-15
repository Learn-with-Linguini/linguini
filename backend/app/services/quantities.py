"""Reviewed number words, regular plurals and quantity sentences for counted groups."""

import re

NUMBER_WORDS = {
    "es": {2: "dos", 3: "tres", 4: "cuatro", 5: "cinco", 6: "seis", 7: "siete", 8: "ocho",
           9: "nueve", 10: "diez"},
    "fr": {2: "deux", 3: "trois", 4: "quatre", 5: "cinq", 6: "six", 7: "sept", 8: "huit",
           9: "neuf", 10: "dix"},
}
ENGLISH_NUMBERS = {
    1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight",
    9: "nine", 10: "ten",
}
QUANTITY_FRAMES = {"es": "Hay", "fr": "Il y a"}
_FRENCH_OUX = {"bijou", "caillou", "chou", "genou", "hibou", "joujou", "pou"}
_SPANISH_ACCENTS = set("áéíóú")


def suggested_quantity(value):
    """A detected quantity attribute read as 1-10, or ``None``; labels never imply a count."""
    if not isinstance(value, str):
        return None
    word = value.strip().casefold().split(" ")[0] if value.strip() else ""
    if word.isdigit():
        number = int(word)
    else:
        number = next((n for n, name in ENGLISH_NUMBERS.items() if name == word), None)
    return number if number is not None and 1 <= number <= 10 else None


def regular_plural(language, noun):
    """The noun's reviewed regular plural, or ``None`` when the rules cannot vouch for one."""
    if not re.fullmatch(r"[^\W\d_]+", noun):
        return None
    lower = noun.casefold()
    if language == "es":
        if lower[-1] in "aeiouáéó":
            return noun + "s"
        if lower[-1] in "dlrj" and not _SPANISH_ACCENTS & set(lower):
            return noun + "es"
        return None
    if language == "fr":
        if lower[-1] in "sxz" or lower.endswith(("au", "eu", "al", "ail")) or lower in _FRENCH_OUX:
            return None
        return noun + "s"
    return None


def english_plural(noun):
    lower = noun.casefold()
    if lower.endswith(("s", "x", "z", "ch", "sh")):
        return noun + "es"
    if lower.endswith("y") and lower[-2:-1] not in set("aeiou"):
        return noun[:-1] + "ies"
    return noun + "s"


def quantity_sentence(language, number_word, noun):
    return f"{QUANTITY_FRAMES[language]} {number_word} {noun}."


def quantity_meaning(quantity, label):
    return f"There are {ENGLISH_NUMBERS[quantity]} {english_plural(label)}."


def wrong_quantities(quantity, low, high):
    """Nearby distinct quantities within the taught range, closest first."""
    return [
        other for step in (1, 2, 3)
        for other in (quantity + step, quantity - step)
        if low <= other <= high
    ][:3]
