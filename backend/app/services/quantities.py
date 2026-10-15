"""Reviewed number words, regular plurals and quantity sentences for counted groups."""

import re

NUMBER_WORDS = {
    "es": {2: "dos", 3: "tres", 4: "cuatro", 5: "cinco", 6: "seis", 7: "siete", 8: "ocho",
           9: "nueve", 10: "diez", 11: "once", 12: "doce", 13: "trece", 14: "catorce",
           15: "quince", 16: "dieciséis", 17: "diecisiete", 18: "dieciocho",
           19: "diecinueve", 20: "veinte"},
    "fr": {2: "deux", 3: "trois", 4: "quatre", 5: "cinq", 6: "six", 7: "sept", 8: "huit",
           9: "neuf", 10: "dix", 11: "onze", 12: "douze", 13: "treize", 14: "quatorze",
           15: "quinze", 16: "seize", 17: "dix-sept", 18: "dix-huit", 19: "dix-neuf",
           20: "vingt"},
}
ENGLISH_NUMBERS = {
    1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight",
    9: "nine", 10: "ten", 11: "eleven", 12: "twelve", 13: "thirteen", 14: "fourteen",
    15: "fifteen", 16: "sixteen", 17: "seventeen", 18: "eighteen", 19: "nineteen",
    20: "twenty",
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


def taught_numbers(mission, progress):
    """The numbers practice may use, and where they came from.

    An explicit ``taught_number_range`` in progress widens the range to at most
    2-20; without one the mission's counted-group range (2-10) applies.
    """
    explicit = (progress or {}).get("taught_number_range")
    if explicit and len(explicit) == 2:
        low, high = max(int(explicit[0]), 2), min(int(explicit[1]), 20)
        source = "learnerRecords"
    else:
        requirements = mission.photo_requirements
        low, high, source = requirements.min_quantity, requirements.max_quantity, "missionDefault"
    return tuple(number for number in range(low, high + 1) if number in NUMBER_WORDS["es"]), source


def wrong_quantities(quantity, low, high):
    """Nearby distinct quantities within the taught range, closest first."""
    return [
        other for step in (1, 2, 3)
        for other in (quantity + step, quantity - step)
        if low <= other <= high
    ][:3]
