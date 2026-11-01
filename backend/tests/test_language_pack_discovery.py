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


@pytest.mark.parametrize("environment,experimental", [("test", "false"), ("production", "true")])
def test_local_switch_never_releases_unreviewed_pack(
    configured_spanish, monkeypatch, environment, experimental,
):
    monkeypatch.setenv("APP_ENV", environment)
    monkeypatch.setenv("LINGUINI_LANGUAGE_PACK_EXPERIMENTAL", experimental)
    monkeypatch.setenv("LINGUINI_LANGUAGE_PACK_REQUIRE_RELEASE", "true")
    assert available_pack_languages() == []


def test_production_discovers_bundled_languages_without_release_metadata(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    for name in ("LINGUINI_LANGUAGE_PACK_DIRS", "LINGUINI_LANGUAGE_PACK_REQUIRE_RELEASE",
                 "LINGUINI_LANGUAGE_PACK_EXPERIMENTAL", "LINGUINI_LANGUAGE_PACK_RELEASES",
                 "LINGUINI_LANGUAGE_PACK_EVIDENCE_DIR"):
        monkeypatch.delenv(name, raising=False)
    rows = {row["code"]: row for row in available_pack_languages()}
    for code in ("es", "fr", "de", "ko"):
        assert rows[code]["levels"] == ["A0", "A1", "A2"]
        assert rows[code]["experimental"] is False


def test_release_policy_changes_invalidate_discovery_context(configured_spanish, monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("LINGUINI_LANGUAGE_PACK_REQUIRE_RELEASE", "false")
    assert available_pack_languages()[0]["code"] == "es"
    monkeypatch.setenv("LINGUINI_LANGUAGE_PACK_REQUIRE_RELEASE", "true")
    assert available_pack_languages() == []


def test_production_still_hides_structurally_unsupported_missions(configured_spanish, monkeypatch):
    from app.language_packs.context import LanguageContext
    from app.language_packs.loader import load_pack
    from app.language_packs.runtime import check_pack_readiness

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("LINGUINI_LANGUAGE_PACK_REQUIRE_RELEASE", "false")
    pack = load_pack(configured_spanish / "es-ES" / "everyday")
    broken = pack.model_copy(update={"constructions": []})
    with pytest.raises(ValueError, match="unavailable") as error:
        check_pack_readiness(broken, "A0", 1)
    assert "review" not in str(error.value)
    assert "evidence" not in str(error.value)
    # Existing sessions still validate the saved pack, rather than resolving a new one.
    from app.language_packs.context import resolve_language_context
    snapshot = resolve_language_context("es").snapshot()
    snapshot["pack"] = broken.model_dump_json()
    with pytest.raises(ValueError, match="constructions"):
        LanguageContext.from_snapshot(snapshot)


def test_optional_evidence_files_do_not_block_default_discovery(configured_spanish, monkeypatch):
    folder = configured_spanish / "evidence"
    folder.mkdir()
    (folder / "es-es-everyday-M01-A0.json").write_text("not json", encoding="utf-8")
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("LINGUINI_LANGUAGE_PACK_REQUIRE_RELEASE", "false")
    monkeypatch.setenv("LINGUINI_LANGUAGE_PACK_EVIDENCE_DIR", str(folder))
    assert available_pack_languages()[0]["code"] == "es"


@pytest.mark.parametrize("level", ["A0", "A1", "A2"])
def test_pack_only_language_plans_only_pack_missions_through_existing_photo_flow(
    configured_spanish, monkeypatch, level,
):
    # Missions come only from the discovered pack; no language list gates them.
    profile = {"target_language_code": "es", "proficiency_level": level}
    missions = lesson_missions(SessionMode.LESSON, profile)
    expected = {
        "A0": [("M01", level), ("M02", level), ("M03", level), ("M05", level)],
        "A1": [
            ("M01", level), ("M02", level), ("M03", level), ("M04", level),
            ("M05", level),
        ],
        "A2": [
            ("M01", level), ("M02", level), ("M03", level), ("M04", level),
            ("M06", level),
        ],
    }[level]
    assert [(m.mission_id, str(m.practice_level)) for m in missions] == expected
    assert lesson_missions(SessionMode.ISPY, profile) == []


def test_bad_discovery_configuration_is_recoverable(configured_spanish, monkeypatch):
    monkeypatch.setenv("LINGUINI_LANGUAGE_PACK_DIRS", "nonexistent/*")
    response = TestClient(app).get("/api/v1/me/practice-languages")
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "language_packs_unavailable"
