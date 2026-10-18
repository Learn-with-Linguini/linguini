from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.config import get_language_pack_dirs, get_language_pack_releases
from app.language_packs.loader import (
    LanguagePackError,
    guidance_for,
    load_evaluation_cases,
    load_pack,
    load_packs,
)
from app.language_packs.schema import GuidanceBundle, LanguagePack, PackLanguage

FIXTURE = Path(__file__).parent / "fixtures/language_packs/es-basic"


def _copy_pack(tmp_path: Path) -> Path:
    destination = tmp_path / "es-basic"
    shutil.copytree(FIXTURE, destination)
    return destination


def _replace(path: Path, old: str, new: str) -> None:
    content = path.read_text()
    assert old in content
    path.write_text(content.replace(old, new, 1))


def test_fixture_pack_and_separate_evaluation_load():
    pack = load_pack(FIXTURE)
    cases = load_evaluation_cases(pack)

    assert pack.pack_id == "es-basic"
    assert pack.language.code == "es"
    assert len(pack.constructions) == 9
    assert [case.case_id for case in cases] == ["cup-description-case"]
    assert "expected" not in guidance_for(pack, ["describe-attribute"]).model_dump()


def test_register_toml_alias_and_snake_case_model_loading():
    pack = load_pack(FIXTURE)
    pack_data = pack.model_dump(mode="python", by_alias=False)
    bundle = guidance_for(pack, ["describe-attribute"])
    bundle_data = bundle.model_dump(mode="python", by_alias=False)

    assert "language_register" in pack_data
    assert "register" not in pack_data
    assert LanguagePack.model_validate(pack_data).language_register == pack.language_register
    assert "language_register" in bundle_data
    assert GuidanceBundle.model_validate(bundle_data).language_register == pack.language_register
    assert pack.model_dump(by_alias=True)["register"]["registerId"] == "everyday"


def test_default_roots_are_empty_and_explicit_roots_are_cached(monkeypatch):
    monkeypatch.setenv("LINGUINI_LANGUAGE_PACK_DIRS", "")
    assert load_packs().packs == ()
    assert get_language_pack_dirs() == ()

    first = load_packs([FIXTURE.parent])
    second = load_packs([FIXTURE.parent])

    assert first is second
    assert first.get("es", "everyday").pack_id == "es-basic"


def test_pack_root_and_release_environment_helpers(monkeypatch, tmp_path):
    roots = (tmp_path / "first", tmp_path / "second")
    monkeypatch.setenv(
        "LINGUINI_LANGUAGE_PACK_DIRS",
        f" {roots[0]}{os.pathsep}{roots[1]} ",
    )
    monkeypatch.setenv(
        "LINGUINI_LANGUAGE_PACK_RELEASES",
        "es:M01:A0, es:M01:A1,invalid,es::A2",
    )

    assert get_language_pack_dirs() == roots
    assert get_language_pack_releases() == frozenset(
        {("es", "M01", "A0"), ("es", "M01", "A1")}
    )


def test_unknown_pack_fields_are_rejected_with_file_and_pointer(tmp_path):
    pack_dir = _copy_pack(tmp_path)
    path = pack_dir / "pack.toml"
    path.write_text(path.read_text().replace("pack_version = 1", "pack_version = 1\nextra = 1"))

    with pytest.raises(LanguagePackError, match=r"pack\.toml /extra"):
        load_pack(pack_dir)


def test_unsupported_format_version_is_reported_at_its_pointer(tmp_path):
    pack_dir = _copy_pack(tmp_path)
    path = pack_dir / "pack.toml"
    path.write_text(path.read_text().replace("format_version = 1", "format_version = 9", 1))

    with pytest.raises(LanguagePackError, match=r"/format_version: unsupported"):
        load_pack(pack_dir)


def test_evaluation_cases_cannot_duplicate_generation_examples(tmp_path):
    pack_dir = _copy_pack(tmp_path)
    path = pack_dir / "evaluation.toml"
    path.write_text(path.read_text().replace("La taza parece azul.", "La taza es azul."))

    with pytest.raises(LanguagePackError, match="duplicates a generation example"):
        load_pack(pack_dir)


def test_duplicate_pack_ids_across_roots_are_rejected(tmp_path):
    roots = [tmp_path / "first-root", tmp_path / "second-root"]
    pack_dirs = [root / f"pack-{index}" for index, root in enumerate(roots)]
    for pack_dir in pack_dirs:
        pack_dir.parent.mkdir()
        shutil.copytree(FIXTURE, pack_dir)

    with pytest.raises(LanguagePackError, match=r"/pack_id: duplicate pack_id 'es-basic'"):
        load_packs(roots)


def test_duplicate_construction_ids_are_rejected(tmp_path):
    pack_dir = _copy_pack(tmp_path)
    path = pack_dir / "pack.toml"
    _replace(
        path,
        'construction_id = "yes-no-identity-question"',
        'construction_id = "name-object"',
    )

    with pytest.raises(
        LanguagePackError,
        match=r"pack\.toml /:[\s\S]*construction ids must be unique",
    ):
        load_pack(pack_dir)


def test_duplicate_example_ids_are_rejected(tmp_path):
    pack_dir = _copy_pack(tmp_path)
    path = pack_dir / "pack.toml"
    _replace(path, 'example_id = "identity-question-example"',
             'example_id = "name-object-example"')

    with pytest.raises(
        LanguagePackError,
        match=r"pack\.toml /:[\s\S]*example ids must be unique",
    ):
        load_pack(pack_dir)


def test_duplicate_label_semantics_are_rejected(tmp_path):
    pack_dir = _copy_pack(tmp_path)
    path = pack_dir / "pack.toml"
    _replace(path, 'semantic = "no"', 'semantic = "yes"')

    with pytest.raises(
        LanguagePackError,
        match=r"pack\.toml /:[\s\S]*label semantic ids must be unique",
    ):
        load_pack(pack_dir)


def test_unknown_required_labels_are_rejected(tmp_path):
    pack_dir = _copy_pack(tmp_path)
    path = pack_dir / "pack.toml"
    _replace(path, 'required_labels = ["yes", "no"]',
             'required_labels = ["yes", "unknown"]')

    with pytest.raises(
        LanguagePackError,
        match=r"pack\.toml /:[\s\S]*unknown required labels",
    ):
        load_pack(pack_dir)


def test_bindings_cannot_reference_undeclared_facts(tmp_path):
    pack_dir = _copy_pack(tmp_path)
    path = pack_dir / "pack.toml"
    _replace(
        path,
        'meaning = "Identify a cup."\n',
        'meaning = "Identify a cup."\n'
        'facts = [{ fact_id = "declared", label = "yes" }]\n'
        'bindings = { object = "undeclared" }\n',
    )

    with pytest.raises(
        LanguagePackError,
        match=(
            r"pack\.toml /constructions/0/examples/0: "
            r"[\s\S]*bindings reference undeclared facts"
        ),
    ):
        load_pack(pack_dir)


def test_chunks_must_reconstruct_example_sentence(tmp_path):
    pack_dir = _copy_pack(tmp_path)
    path = pack_dir / "pack.toml"
    _replace(path, 'text = "Esto"', 'text = "EstoX"')

    with pytest.raises(
        LanguagePackError,
        match=r"pack\.toml /:[\s\S]*chunks do not reconstruct sentence",
    ):
        load_pack(pack_dir)


def test_chunk_text_rejects_leading_whitespace_at_pointer(tmp_path):
    pack_dir = _copy_pack(tmp_path)
    path = pack_dir / "pack.toml"
    _replace(path, 'text = "Esto"', 'text = " Esto"')

    with pytest.raises(
        LanguagePackError,
        match=(
            r"pack\.toml /constructions/0/examples/0/chunks/0/text: "
            r"[\s\S]*leading or trailing whitespace"
        ),
    ):
        load_pack(pack_dir)


def test_evaluation_rejects_unknown_construction_at_pointer(tmp_path):
    pack_dir = _copy_pack(tmp_path)
    path = pack_dir / "evaluation.toml"
    _replace(path, 'construction_id = "describe-attribute"',
             'construction_id = "unknown-construction"')

    with pytest.raises(
        LanguagePackError,
        match=r"/cases/0/construction_id: unknown construction 'unknown-construction'",
    ):
        load_pack(pack_dir)


def test_evaluation_rejects_mismatched_construction_version_at_pointer(tmp_path):
    pack_dir = _copy_pack(tmp_path)
    path = pack_dir / "evaluation.toml"
    _replace(path, "construction_version = 1", "construction_version = 2")

    with pytest.raises(
        LanguagePackError,
        match=r"/cases/0/construction_version: expected construction version 1",
    ):
        load_pack(pack_dir)


def test_malformed_toml_is_reported_with_file_and_pointer(tmp_path):
    pack_dir = _copy_pack(tmp_path)
    path = pack_dir / "pack.toml"
    path.write_text(path.read_text() + "\n[malformed\n")

    with pytest.raises(LanguagePackError, match=r"pack\.toml /: Expected"):
        load_pack(pack_dir)


@pytest.mark.parametrize(
    ("old", "new", "message"),
    [
        ('review_status = "unreviewed"', 'review_status = "humanReviewed"',
         "humanReviewed provenance requires at least one reviewer"),
        ('review_status = "unreviewed"',
         'review_status = "unreviewed"\nreviewers = ["test reviewer"]',
         "unreviewed and generated provenance cannot list reviewers"),
    ],
)
def test_provenance_reviewers_must_match_review_status(tmp_path, old, new, message):
    pack_dir = _copy_pack(tmp_path)
    path = pack_dir / "pack.toml"
    _replace(path, old, new)

    with pytest.raises(LanguagePackError, match=message):
        load_pack(pack_dir)


def test_pack_text_must_be_nfc(tmp_path):
    pack_dir = _copy_pack(tmp_path)
    path = pack_dir / "pack.toml"
    path.write_text(
        path.read_text().replace(
            "Generic Spanish variety", "Gene\u0301ric Spanish variety", 1
        )
    )

    with pytest.raises(LanguagePackError, match="text must be NFC"):
        load_pack(pack_dir)


def test_language_code_casing_and_script_direction_are_strict():
    with pytest.raises(ValidationError):
        PackLanguage.model_validate(
            {
                "code": "es",
                "locale": "es-es",
                "script": "Latn",
                "direction": "ltr",
                "word_separator": "space",
                "speech": {
                    "synthesis_locale": "es-ES",
                    "synthesis": "browserVoice",
                    "recognition": True,
                },
            }
        )

    with pytest.raises(ValidationError):
        PackLanguage.model_validate(
            {
                "code": "ar",
                "locale": "ar",
                "script": "Arab",
                "direction": "ltr",
                "word_separator": "space",
                "speech": {
                    "synthesis_locale": "ar",
                    "synthesis": "none",
                    "recognition": False,
                },
            }
        )


def test_generic_rtl_and_no_separator_language_profiles_are_supported():
    speech = {
        "synthesis_locale": "und-x-test",
        "synthesis": "none",
        "recognition": False,
    }
    no_separator = PackLanguage.model_validate(
        {
            "code": "und-x-test",
            "locale": "und-x-test",
            "script": "Latn",
            "direction": "ltr",
            "word_separator": "none",
            "speech": speech,
        }
    )
    rtl = PackLanguage.model_validate(
        {
            "code": "ar",
            "locale": "ar",
            "script": "Arab",
            "direction": "rtl",
            "word_separator": "space",
            "speech": {
                "synthesis_locale": "ar",
                "synthesis": "none",
                "recognition": False,
            },
        }
    )

    assert no_separator.word_separator == "none"
    assert rtl.direction == "rtl"
