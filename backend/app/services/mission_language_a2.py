"""A2 language frames and agreement checks for scene-mission validators."""

A2_ENABLED_LANGUAGES = frozenset({"es", "fr"})

_EXISTENTIALS = {
    "es": "Hay {quantity} {noun}.",
    "fr": "Il y a {quantity} {noun}.",
    "de": "Es gibt {quantity} {noun}.",
}
_COUNTERS = {"개", "권", "잔", "마리", "장", "대"}
_POSSESSIVES = {
    "es": {
        ("masculine", "singular", "nominative"): "mi",
        ("feminine", "singular", "nominative"): "mi",
        ("masculine", "plural", "nominative"): "mis",
        ("feminine", "plural", "nominative"): "mis",
    },
    "fr": {
        ("masculine", "singular", "nominative"): "mon",
        ("feminine", "singular", "nominative"): "ma",
        ("feminine-vowel", "singular", "nominative"): "mon",
        ("masculine", "plural", "nominative"): "mes",
        ("feminine", "plural", "nominative"): "mes",
    },
}
_GERMAN_POSSESSIVES = {
    ("masculine", "singular", "nominative"): "mein",
    ("feminine", "singular", "nominative"): "meine",
    ("neuter", "singular", "nominative"): "mein",
    ("masculine", "singular", "accusative"): "meinen",
    ("feminine", "singular", "accusative"): "meine",
    ("neuter", "singular", "accusative"): "mein",
    ("plural", "plural", "nominative"): "meine",
}


def existential(language: str, quantity: str, noun: str, counter: str = "개") -> str:
    """Render a taught existential frame, including Korean counting particles."""
    language = language.lower()
    if language == "ko":
        if counter not in _COUNTERS:
            raise ValueError("Use a Korean counter from the taught counter set.")
        return f"{noun}{korean_particle(noun, subject=True)} {quantity} {counter} 있어요."
    try:
        return _EXISTENTIALS[language].format(quantity=quantity, noun=noun)
    except KeyError as error:
        raise ValueError(f"Unsupported A2 language: {language}") from error


def comparative(language: str, subject: str, reference: str, greater: bool) -> str:
    """Render a directional quantity comparison in the requested language."""
    language = language.lower()
    if language == "es":
        return f"Hay {'más' if greater else 'menos'} {subject} que {reference}."
    if language == "fr":
        return f"Il y a {'plus' if greater else 'moins'} de {subject} que de {reference}."
    if language == "de":
        return f"Es gibt {'mehr' if greater else 'weniger'} {subject} als {reference}."
    if language == "ko":
        comparison = "많아요" if greater else "적어요"
        return (
            f"{subject}{korean_particle(subject, subject=True)} "
            f"{reference}보다 더 {comparison}."
        )
    raise ValueError(f"Unsupported A2 language: {language}")


def possessive(
    language: str,
    gender: str,
    number: str = "singular",
    case: str = "nominative",
    noun: str = "",
    formal: bool = True,
) -> str:
    """Return the agreeing possessive, including French vowel-initial feminine nouns."""
    language = language.lower()
    if language == "fr" and gender == "feminine" and noun[:1].casefold() in "aeiouyh":
        gender = "feminine-vowel"
    if language in _POSSESSIVES:
        key = (gender, number, case)
        if key not in _POSSESSIVES[language]:
            raise ValueError("Unsupported possessive agreement.")
        return _POSSESSIVES[language][key]
    if language == "de":
        key = ("plural" if number == "plural" else gender, number, case)
        if key not in _GERMAN_POSSESSIVES:
            raise ValueError("Unsupported possessive agreement.")
        return _GERMAN_POSSESSIVES[key]
    if language == "ko":
        return "제" if formal else "내"
    raise ValueError(f"Unsupported A2 language: {language}")


def korean_particle(noun: str, subject: bool = False) -> str:
    """Choose 은/는 or 이/가 by whether the final Hangul syllable has batchim."""
    last = next((char for char in reversed(noun) if "\uac00" <= char <= "\ud7a3"), "")
    has_batchim = bool(last and (ord(last) - 0xAC00) % 28)
    if subject:
        return "이" if has_batchim else "가"
    return "은" if has_batchim else "는"


def validate_existential(text: str, language: str) -> bool:
    """Check that a sentence starts with the language's approved existential frame."""
    text = text.strip().casefold()
    if language == "ko":
        return text.endswith(("있어요.", "있습니다.", "있다."))
    frame = {"es": "hay ", "fr": "il y a ", "de": "es gibt "}.get(language)
    return bool(frame and text.startswith(frame))


def validate_comparative(text: str, language: str, greater: bool) -> bool:
    """Check the direction word used by a simple A2 quantity comparison."""
    terms = {
        "es": ("más", "menos"),
        "fr": ("plus", "moins"),
        "de": ("mehr", "weniger"),
        "ko": ("많아요", "적어요"),
    }.get(language)
    if not terms:
        return False
    expected, opposite = terms if greater else terms[::-1]
    return expected in text and opposite not in text


def validate_possessive(
    text: str,
    language: str,
    gender: str,
    number: str = "singular",
    case: str = "nominative",
    noun: str = "",
    formal: bool = True,
) -> bool:
    """Check the expected possessive form is present in a noun phrase."""
    try:
        expected = possessive(language, gender, number, case, noun, formal)
    except ValueError:
        return False
    return expected in text.split()


def validate_korean_counter(text: str, counter: str) -> bool:
    """Check that Korean counted quantities use a recognized counter."""
    return counter in _COUNTERS and counter in text


def validate_korean_particle(text: str, noun: str, subject: bool = False) -> bool:
    """Check the correctly chosen Korean particle immediately follows a noun."""
    particle = korean_particle(noun, subject)
    return f"{noun}{particle}" in text
