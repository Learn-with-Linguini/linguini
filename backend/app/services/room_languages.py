"""Which learner profiles can play photo rooms: one rule for rooms, friends and photos."""

ROOM_LEVELS = frozenset({"A1", "A2"})


def room_language_ready(language: str, register=None) -> bool:
    """The language has a ready pack whose clue grammar (``clues.toml``) rooms can use."""
    from app.language_packs.context import resolve_language_context
    from app.services.ispy_clue_frames import clue_grammar

    code = language.lower()
    try:
        if resolve_language_context(code, register) is None:
            return False
    except ValueError:
        # A broken pack configuration offers no rooms rather than failing the request.
        return False
    return clue_grammar(code) is not None


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
