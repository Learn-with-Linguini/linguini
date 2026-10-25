"""Which profiles can play photo rooms, and which languages get curated templates."""

import pytest

from app.scripts.precompute_preloaded_scenes import template_languages
from app.services.room_languages import room_language_ready, room_profile_supported


def profile(language="es", level="A1", source="en"):
    return {"source_language_code": source, "target_language_code": language,
            "proficiency_level": level}


def test_a_ready_pack_with_room_clues_opens_rooms_at_a1_and_a2():
    for language in ("es", "fr", "de", "ES"):
        assert room_profile_supported(profile(language))
    assert room_profile_supported(profile(level="A2"))
    assert not room_profile_supported(profile(level="A0"))
    assert not room_profile_supported(profile(source="fr"))
    assert not room_profile_supported(None)
    # Room photos check the language only; the room itself checks the level.
    assert room_profile_supported(profile(level="A0"), check_level=False)


def test_rooms_need_both_the_pack_and_room_clues(monkeypatch):
    # Korean has a pack but no guided room clues yet.
    assert not room_language_ready("ko")
    monkeypatch.setattr("app.language_packs.context.resolve_language_context",
                        lambda *_args: None)
    assert not room_profile_supported(profile("es"))


def test_a_broken_pack_configuration_offers_no_rooms(monkeypatch):
    def broken(*_args):
        raise ValueError("ambiguous pack configuration")

    monkeypatch.setattr("app.language_packs.context.resolve_language_context", broken)
    assert not room_language_ready("es")


DISCOVERED = [
    {"code": "de", "experimental": False},
    {"code": "es", "experimental": False},
    {"code": "xx", "experimental": True},
]


def test_templates_default_to_released_packs_and_name_experimental_ones():
    assert template_languages(None, DISCOVERED) == ["de", "es"]
    assert template_languages(["xx", "es", "xx"], DISCOVERED) == ["xx", "es"]
    with pytest.raises(ValueError, match="no ready language pack for fr"):
        template_languages(["fr"], DISCOVERED)
    assert template_languages(None, []) == []
