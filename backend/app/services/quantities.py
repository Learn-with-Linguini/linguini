"""Reviewed number words, regular plurals and quantity sentences for counted groups."""


ENGLISH_NUMBERS = {
    1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight",
    9: "nine", 10: "ten", 11: "eleven", 12: "twelve", 13: "thirteen", 14: "fourteen",
    15: "fifteen", 16: "sixteen", 17: "seventeen", 18: "eighteen", 19: "nineteen",
    20: "twenty",
}


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




def english_plural(noun):
    lower = noun.casefold()
    if lower.endswith(("s", "x", "z", "ch", "sh")):
        return noun + "es"
    if lower.endswith("y") and lower[-2:-1] not in set("aeiou"):
        return noun[:-1] + "ies"
    return noun + "s"








