"""Which learner profiles can play photo rooms: one rule for rooms, friends and photos."""

# Languages the guided room clue builder writes clues for. A room also needs the
# language's ready pack (``room_profile_supported``).
ROOM_CLUE_LANGUAGES = frozenset({"es", "fr", "de"})
ROOM_LEVELS = frozenset({"A1", "A2"})


def room_language_ready(language: str, register=None) -> bool:
    """The language has a ready pack and room clues."""
    from app.language_packs.context import resolve_language_context

    code = language.lower()
    if code not in ROOM_CLUE_LANGUAGES:
        return False
    try:
        return resolve_language_context(code, register) is not None
    except ValueError:
        # A broken pack configuration offers no rooms rather than failing the request.
        return False


def room_profile_supported(profile, *, check_level: bool = True) -> bool:
    """An English-source profile whose language is ready for rooms, at A1/A2 when
    ``check_level``."""
    return bool(
        profile
        and str(profile["source_language_code"]).lower() == "en"
        and (not check_level or str(profile["proficiency_level"]) in ROOM_LEVELS)
        and room_language_ready(
            str(profile["target_language_code"]), profile.get("language_register")
        )
    )
