"""Generic discovery and selection tests using only the Spanish pack; no model calls."""

import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.language_packs.loader import LanguagePackError, load_packs
from app.language_packs.runtime import available_pack_languages
from app.main import app
from app.schemas.enums import SessionMode
from app.services.mission_eligibility import lesson_missions

SPANISH = Path(__file__).parents[1] / "app/language_packs/packs/es-ES/everyday"


@pytest.fixture
def configured_spanish(tmp_path, monkeypatch):
    root = tmp_path / "packs"
    shutil.copytree(SPANISH, root / "es-ES" / "everyday")
    monkeypatch.setenv("LINGUINI_LANGUAGE_PACK_DIRS", str(root / "*"))
    monkeypatch.setenv("LINGUINI_LANGUAGE_PACKS", "true")
    monkeypatch.setenv("LINGUINI_LANGUAGE_PACK_EXPERIMENTAL", "true")
    monkeypatch.setenv("LINGUINI_LANGUAGE_PACK_REGISTER", "everyday")
    monkeypatch.setenv("APP_ENV", "test")
    return root


def test_wildcard_and_recursive_root_find_same_spanish_pack(configured_spanish):
    root = configured_spanish
    wildcard = load_packs()
    recursive = load_packs([root])
    overlapping = load_packs([root, root / "*", root / "es-ES" / "everyday"])
    for result in (wildcard, recursive, overlapping):
        assert len(result.packs) == 1
        assert result.get("es", "everyday").pack_id == "es-es-everyday"


def test_unmatched_pattern_reports_configuration_error(tmp_path):
    with pytest.raises(LanguagePackError, match="matched no paths"):
        load_packs([tmp_path / "missing" / "*"])


def test_different_manifests_with_duplicate_id_still_rejected(configured_spanish):
    root = configured_spanish
    shutil.copytree(SPANISH, root / "duplicate")
    with pytest.raises(LanguagePackError, match="duplicate pack_id"):
        load_packs()


def test_available_levels_and_endpoint_are_local_experimental(configured_spanish):
    expected = [dict(code="es", levels=["A0", "A1", "A2"], experimental=True)]
    rows = available_pack_languages()
    assert [{k: row[k] for k in ("code", "levels", "experimental")} for row in rows] == expected
    assert rows[0]["language_context"].language_code == "es"
    response = TestClient(app).get("/api/v1/me/practice-languages")
    assert response.status_code == 200
    assert [{k: row[k] for k in ("code", "levels", "experimental")}
            for row in response.json()] == expected


def test_flag_off_does_not_discover_or_offer_packs(configured_spanish, monkeypatch):
    monkeypatch.setenv("LINGUINI_LANGUAGE_PACKS", "false")
    monkeypatch.setenv("LINGUINI_LANGUAGE_PACK_DIRS", "nonexistent/*")
    assert available_pack_languages() == []
    assert TestClient(app).get("/api/v1/me/practice-languages").json() == []


@pytest.mark.parametrize("environment,experimental", [("test", "false"), ("production", "true")])
def test_local_switch_never_releases_unreviewed_pack(
    configured_spanish, monkeypatch, environment, experimental,
):
    monkeypatch.setenv("APP_ENV", environment)
    monkeypatch.setenv("LINGUINI_LANGUAGE_PACK_EXPERIMENTAL", experimental)
    assert available_pack_languages() == []


@pytest.mark.parametrize("level", ["A0", "A1", "A2"])
def test_pack_only_language_plans_only_pack_missions_through_existing_photo_flow(
    configured_spanish, monkeypatch, level,
):
    # Exercise the generic extension with Spanish treated as absent from the
    # legacy registry; no new-language pack or linguistic fixture is created.
    import app.services.mission_eligibility as module

    monkeypatch.setattr(module, "MISSION_LANGUAGES", set())
    monkeypatch.setattr(module, "LEVEL_LANGUAGES", {})
    profile = {"target_language_code": "es", "proficiency_level": level}
    missions = lesson_missions(SessionMode.LESSON, profile)
    assert [(m.mission_id, str(m.practice_level)) for m in missions] == [
        ("M01", level), ("M02", level), ("M03", level), ("M04", level),
        # M05 has pack templates at A0 and A1 only, M06 at A2 only.
        *([("M05", level)] if level != "A2" else [("M06", level)]),
    ]
    assert lesson_missions(SessionMode.ISPY, profile) == []
    monkeypatch.setenv("LINGUINI_LANGUAGE_PACKS", "false")
    assert lesson_missions(SessionMode.LESSON, profile) == []


def test_bad_discovery_configuration_is_recoverable(configured_spanish, monkeypatch):
    monkeypatch.setenv("LINGUINI_LANGUAGE_PACK_DIRS", "nonexistent/*")
    response = TestClient(app).get("/api/v1/me/practice-languages")
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "language_packs_unavailable"
