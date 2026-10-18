import logging

from app.languages import get_language
from app.missions import get_mission
from app.missions.m01_multilingual import (
    _parse_m01_combinations,
    m01_generation_enabled_for,
)
from app.schemas.enums import SessionMode
from app.services.mission_eligibility import lesson_missions


def test_combination_gate_requires_global_flag_and_preserves_legacy_path(monkeypatch):
    profile = {"target_language_code": "es", "proficiency_level": "A1"}
    monkeypatch.setenv("MULTILINGUAL_ENABLED", "true")
    monkeypatch.delenv("MULTILINGUAL_COMBINATIONS", raising=False)

    enabled_flag_missions = lesson_missions(SessionMode.LESSON, profile)

    assert not m01_generation_enabled_for("es", "A1")
    monkeypatch.setenv("MULTILINGUAL_ENABLED", "false")
    assert lesson_missions(SessionMode.LESSON, profile) == enabled_flag_missions


def test_language_level_combination_is_specific_and_case_insensitive(monkeypatch):
    monkeypatch.setenv("MULTILINGUAL_ENABLED", "true")
    monkeypatch.setenv("MULTILINGUAL_COMBINATIONS", "ES:a1")

    assert m01_generation_enabled_for("es", "A1")
    assert not m01_generation_enabled_for("es", "A0")
    assert not m01_generation_enabled_for("fr", "A1")


def test_language_wildcard_enables_each_plan_level(monkeypatch):
    monkeypatch.setenv("MULTILINGUAL_ENABLED", "true")
    monkeypatch.setenv("MULTILINGUAL_COMBINATIONS", "ko:*")

    assert all(m01_generation_enabled_for("ko", level) for level in ("A0", "A1", "A2"))
    assert not m01_generation_enabled_for("es", "A1")


def test_global_wildcard_enables_registered_languages(monkeypatch):
    monkeypatch.setenv("MULTILINGUAL_ENABLED", "true")
    monkeypatch.setenv("MULTILINGUAL_COMBINATIONS", "*")

    assert get_language("en") is not None
    assert m01_generation_enabled_for("en", "A2")
    assert m01_generation_enabled_for("es", "A0")
    assert m01_generation_enabled_for("ko", "A1")


def test_malformed_combinations_warn_and_do_not_block_valid_entries(monkeypatch, caplog):
    _parse_m01_combinations.cache_clear()
    monkeypatch.setenv("MULTILINGUAL_ENABLED", "true")
    monkeypatch.setenv("MULTILINGUAL_COMBINATIONS", "es:bad, :A1, *:A1, es:A1")

    with caplog.at_level(logging.WARNING):
        assert m01_generation_enabled_for("es", "A1")
        assert m01_generation_enabled_for("es", "A1")

    warnings = [
        record for record in caplog.records
        if "Ignoring malformed MULTILINGUAL_COMBINATIONS entry" in record.message
    ]
    assert len(warnings) == 3


def test_language_mission_levels_follow_environment_changes(monkeypatch):
    language = get_language("ko")
    assert language is not None
    monkeypatch.setenv("MULTILINGUAL_ENABLED", "true")
    monkeypatch.delenv("MULTILINGUAL_COMBINATIONS", raising=False)

    assert language.features.mission_levels == ["A0"]
    assert language.speech.recognition is False

    monkeypatch.setenv("MULTILINGUAL_COMBINATIONS", "ko:A1")
    assert language.features.mission_levels == ["A0", "A1"]
    monkeypatch.setenv("MULTILINGUAL_COMBINATIONS", "ko:A2")
    assert language.features.mission_levels == ["A0", "A2"]


def test_combination_enabled_mission_is_added_without_changing_legacy_missions(monkeypatch):
    monkeypatch.setenv("MULTILINGUAL_ENABLED", "true")
    monkeypatch.setenv("MULTILINGUAL_COMBINATIONS", "ko:A1")

    missions = lesson_missions(
        SessionMode.LESSON,
        {"target_language_code": "ko", "proficiency_level": "A1"},
    )

    assert [mission.mission_id for mission in missions] == ["M01"]
    assert get_mission("M01", "A1", 1) == missions[0]
