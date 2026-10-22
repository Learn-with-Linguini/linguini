from __future__ import annotations

import os
import shutil
import tomllib
from pathlib import Path

import pytest

from app.config import get_language_pack_dirs, get_language_pack_releases
from app.language_packs.fingerprint import pack_fingerprint
from app.language_packs.loader import (
    LanguagePackError,
    guidance_for,
    load_evaluation_cases,
    load_pack,
    load_packs,
)

PACK = Path(__file__).parents[1] / "app/language_packs/packs/es-ES/everyday"
FIXTURE = Path(__file__).parent / "fixtures/language_packs/es-basic"


def _copy_pack(tmp_path: Path) -> Path:
    destination = tmp_path / "pack"
    shutil.copytree(PACK, destination)
    return destination


def _replace(path: Path, old: str, new: str) -> None:
    content = path.read_text("utf-8")
    assert old in content
    path.write_text(content.replace(old, new, 1), encoding="utf-8")


def test_nested_pack_loads_and_evaluations_remain_separate():
    pack = load_pack(PACK)
    cases = load_evaluation_cases(pack)

    assert pack.pack_id == "es-es-everyday"
    assert pack.language.locale == "es-ES"
    assert len(pack.constructions) == 26
    assert len(cases) == 100
    assert not any(key in pack.model_dump() for key in ("evaluations", "evaluation_cases"))
    assert all("cases" not in item for item in guidance_for(pack, [
        "identify-object"
    ]).model_dump())
    assert pack_fingerprint(pack, ["identify-object"], "generation.v1")
    assert all(case.input.isascii() for case in cases)
    assert all(
        case.input not in {item.sentence for item in case.reject}
        and case.input not in case.acceptable
        for case in cases
    )


def test_held_out_evaluations_cover_the_required_categories():
    evaluation_files = {
        path.stem: tomllib.loads(path.read_text("utf-8"))
        for path in (PACK / "evaluations").glob("*.toml")
    }
    assert {name: len(data["cases"]) for name, data in evaluation_files.items()} == {
        "M01-A0": 9,
        "M01-A1": 7,
        "M01-A2": 8,
        "M02-A0": 7,
        "M02-A1": 7,
        "M02-A2": 6,
        "M03-A0": 8,
        "M03-A1": 7,
        "M03-A2": 11,
        "M04-A0": 6,
        "M04-A1": 5,
        "M04-A2": 7,
        "M05-A0": 6,
        "M05-A1": 6,
    }
    categories = {
        category
        for data in evaluation_files.values()
        for case in data["cases"]
        for category in (
            case["category"],
            *(reject["category"] for reject in case.get("reject", [])),
        )
    }
    assert {
        "wrongObject",
        "wrongAttribute",
        "wrongRelation",
        "wrongCount",
        "wrongOwner",
        "agreement",
        "wordOrder",
        "verbChoice",
        "punctuation",
        "article",
        "languageLeakage",
        "contraction",
        "unicode",
    } <= categories
    all_cases = [
        case for data in evaluation_files.values() for case in data["cases"]
    ]
    assert any(
        sentence.startswith("Esto es ")
        for case in all_cases
        for sentence in case["acceptable"]
    )
    assert any(case["scene"].get("absent") for case in all_cases)


def test_labels_match_current_builder_text():
    labels = {item.semantic: item.text for item in load_pack(PACK).labels}

    assert labels == {
        "yes": "Sí",
        "no": "No",
        "yes-answer": "Sí.",
        "no-answer": "No.",
        "what-is-this": "¿Qué es esto?",
        "attribute-prompt-colour": "¿De qué color es?",
        "attribute-prompt": "¿Cómo es?",
        "attribute-prompt-material": "¿De qué material es?",
        "describe-object": "Describe este objeto.",
        "touch-object": "Toca el objeto que corresponde a la frase: «{f['first']}».",
        "build-second-fact": "Construye la segunda frase.",
        "choose-description": "¿Qué descripción coincide con la foto?",
        "describe-scene": "Describe la escena con estas frases.",
        "connector-distractor": "pero",
        "vocabulary-unsure": "No sé",
        "vocabulary-other": "No estoy seguro",
        "ask-where": "Pregunta dónde está.",
        "answer-where": "Responde con la posición que muestra la foto.",
        "clue-meaning": "¿Qué significa?",
        "build-location-clue": "Construye la segunda pista.",
        "find-both-clues": "Toca el objeto que coincide con las dos pistas.",
        "friend-points": "Tu amigo señala el marcador {marker}. ¿Qué aclaras?",
        "name-and-locate": "Nombra el objeto y di dónde está.",
        "answer-in-sentence": "Responde con una frase.",
        "build-group-sentence": "Escribe una frase sobre el grupo marcado.",
        "choose-comparison": "Elige la comparación correcta.",
        "friend-says": "Tu amigo dice: «{statement}» ¿Qué respondes?",
        "friend-is-right": "Sí, tu amigo tiene razón.",
        "describe-compare": "Describe y compara los dos grupos.",
        "more": "más",
        "fewer": "menos",
        "choose-sentence": "Elige la frase correcta.",
        "which-is-yours": "¿Cuál es tu objeto?",
        "choose-possessive": "Tú dices:",
        "describe-your-object": "Describe tu objeto con un detalle.",
        "clarify-and-describe": "Aclara cuál es tu objeto y descríbelo.",
        "what-choose": "¿Qué eliges?",
    }


def test_counterfactual_absence_does_not_assert_the_object_is_present():
    pack = load_pack(PACK)
    absent = next(
        example
        for construction in pack.constructions
        for example in construction.examples
        if example.example_id == "counterfactual-clock"
    )

    assert absent.truth is False
    assert absent.scene.objects == []
    assert [item.fact_id for item in absent.scene.absent] == ["object:clock"]
    assert absent.bindings == {"object": "object:clock"}


def test_absent_fact_bindings_are_allowed_only_for_false_examples(tmp_path):
    pack = load_pack(PACK)
    counterfactual = next(
        example
        for construction in pack.constructions
        for example in construction.examples
        if example.example_id == "counterfactual-clock"
    )
    assert counterfactual.truth is False
    assert counterfactual.scene.absent_fact_ids == {"object:clock"}
    assert counterfactual.bindings["object"] in counterfactual.scene.absent_fact_ids

    pack_dir = _copy_pack(tmp_path)
    _replace(
        pack_dir / "examples/scene-existence.toml",
        "truth = false",
        "truth = true",
    )
    with pytest.raises(LanguagePackError, match="cannot bind absent facts"):
        load_pack(pack_dir)


def test_small_fixture_uses_nested_layout_and_loads_held_out_case():
    pack = load_pack(FIXTURE)

    assert [item.construction_id for item in pack.constructions] == ["identify-object"]
    assert [item.case_id for item in load_evaluation_cases(pack)] == ["fixture-case"]


def test_pack_locale_and_register_match_nested_directory_names(tmp_path):
    root = tmp_path / "correct-root"
    nested = root / "es-ES" / "everyday"
    nested.parent.mkdir(parents=True)
    shutil.copytree(PACK, nested)
    pack = load_packs([root]).packs[0]
    assert pack.language.locale == "es-ES"
    assert pack.language_register.register_id == "everyday"

    wrong_register_root = tmp_path / "wrong-register-root"
    wrong_register = wrong_register_root / "es-ES" / "neutral-classroom"
    wrong_register.parent.mkdir(parents=True)
    shutil.copytree(PACK, wrong_register)
    with pytest.raises(LanguagePackError, match=r"/register/register_id"):
        load_packs([wrong_register_root])

    wrong_locale_root = tmp_path / "wrong-locale-root"
    wrong_locale = wrong_locale_root / "fr-FR" / "everyday"
    wrong_locale.parent.mkdir(parents=True)
    shutil.copytree(PACK, wrong_locale)
    with pytest.raises(LanguagePackError, match=r"/language/locale"):
        load_packs([wrong_locale_root])


def test_default_roots_are_empty_and_nested_roots_are_cached(monkeypatch):
    monkeypatch.setenv("LINGUINI_LANGUAGE_PACK_DIRS", "")
    assert load_packs().packs == ()
    assert get_language_pack_dirs() == ()

    root = PACK.parents[2]
    first = load_packs([root])
    second = load_packs([root])

    assert first is second
    assert first.get("es", "everyday").pack_id == "es-es-everyday"


def test_release_environment_parser(monkeypatch, tmp_path):
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


def test_duplicate_pack_ids_across_roots_are_rejected(tmp_path):
    roots = [tmp_path / "root-one", tmp_path / "root-two"]
    for root in roots:
        root.mkdir()
        shutil.copytree(PACK, root / "es-ES" / "everyday")

    with pytest.raises(LanguagePackError, match=r"/pack_id: duplicate pack_id"):
        load_packs(roots)


@pytest.mark.parametrize(
    "reference",
    ["/tmp/outside.toml", "../outside.toml"],
)
def test_absolute_and_parent_references_are_rejected(tmp_path, reference):
    pack_dir = _copy_pack(tmp_path)
    _replace(pack_dir / "pack.toml", 'labels = "labels.toml"', f'labels = "{reference}"')

    with pytest.raises(LanguagePackError, match=r"/files/labels: file reference"):
        load_pack(pack_dir)


def test_symlink_escape_and_unreferenced_toml_are_rejected(tmp_path):
    pack_dir = _copy_pack(tmp_path)
    outside = tmp_path / "outside.toml"
    outside.write_text((pack_dir / "labels.toml").read_text("utf-8"), encoding="utf-8")
    (pack_dir / "labels.toml").unlink()
    (pack_dir / "labels.toml").symlink_to(outside)

    with pytest.raises(LanguagePackError, match="escapes the pack directory"):
        load_pack(pack_dir)

    pack_dir = _copy_pack(tmp_path / "second")
    unused = pack_dir / "constructions" / "unused.toml"
    unused.write_text("construction_id = 'unused'\n", encoding="utf-8")
    with pytest.raises(LanguagePackError, match="unreferenced TOML file"):
        load_pack(pack_dir)


def test_duplicate_construction_identity_is_rejected(tmp_path):
    pack_dir = _copy_pack(tmp_path)
    _replace(
        pack_dir / "constructions/scene-location.toml",
        'construction_id = "scene-location"',
        'construction_id = "identify-object"',
    )

    with pytest.raises(LanguagePackError, match=r"/construction_id: construction_id"):
        load_pack(pack_dir)


def test_duplicate_example_and_label_ids_are_rejected(tmp_path):
    pack_dir = _copy_pack(tmp_path)
    _replace(
        pack_dir / "examples/identify-object.toml",
        'example_id = "name-apple"',
        'example_id = "name-book"',
    )
    with pytest.raises(LanguagePackError, match="example ids must be unique"):
        load_pack(pack_dir)

    pack_dir = _copy_pack(tmp_path / "labels")
    _replace(
        pack_dir / "labels.toml",
        'semantic = "no"',
        'semantic = "yes"',
    )
    with pytest.raises(LanguagePackError, match="label semantic ids must be unique"):
        load_pack(pack_dir)


def test_unknown_required_label_and_undeclared_fact_are_rejected(tmp_path):
    pack_dir = _copy_pack(tmp_path)
    _replace(
        pack_dir / "constructions/identify-object.toml",
        'required_labels = ["what-is-this"]',
        'required_labels = ["missing-label"]',
    )
    with pytest.raises(LanguagePackError, match="unknown required labels"):
        load_pack(pack_dir)

    pack_dir = _copy_pack(tmp_path / "facts")
    _replace(
        pack_dir / "examples/identify-object.toml",
        'bindings = { object = "object:book" }',
        'bindings = { object = "object:ghost" }',
    )
    with pytest.raises(LanguagePackError, match="bindings reference undeclared facts"):
        load_pack(pack_dir)


def test_sentence_chunks_must_reconstruct_and_have_no_edge_whitespace(tmp_path):
    pack_dir = _copy_pack(tmp_path)
    _replace(
        pack_dir / "examples/identify-object.toml",
        '{ text = "libro", join = "space" }',
        '{ text = "libr0", join = "space" }',
    )
    with pytest.raises(LanguagePackError, match="chunks do not reconstruct sentence"):
        load_pack(pack_dir)

    pack_dir = _copy_pack(tmp_path / "whitespace")
    _replace(
        pack_dir / "examples/identify-object.toml",
        '{ text = "el", join = "none" }',
        '{ text = " el", join = "none" }',
    )
    with pytest.raises(LanguagePackError, match="chunk text cannot have leading"):
        load_pack(pack_dir)


def test_unknown_evaluation_construction_and_version_are_rejected(tmp_path):
    pack_dir = _copy_pack(tmp_path)
    _replace(
        pack_dir / "evaluations/M01-A0.toml",
        'construction_id = "identify-object"',
        'construction_id = "not-a-construction"',
    )
    with pytest.raises(LanguagePackError, match=r"/cases/0/construction_id"):
        load_evaluation_cases(load_pack(pack_dir))

    pack_dir = _copy_pack(tmp_path / "version")
    _replace(
        pack_dir / "evaluations/M01-A0.toml",
        "construction_version = 1",
        "construction_version = 2",
    )
    with pytest.raises(LanguagePackError, match=r"/cases/0/construction_version"):
        load_evaluation_cases(load_pack(pack_dir))


def test_evaluation_construction_must_be_used_by_its_mission_level(tmp_path):
    pack_dir = _copy_pack(tmp_path)
    _replace(
        pack_dir / "evaluations/M01-A0.toml",
        'construction_id = "identify-object"',
        'construction_id = "scene-location"',
    )
    with pytest.raises(
        LanguagePackError,
        match=r"/cases/0/construction_id: construction 'scene-location' is not used",
    ):
        load_evaluation_cases(load_pack(pack_dir))


def test_evaluation_mission_and_leakage_are_validated_only_when_requested(tmp_path):
    pack_dir = _copy_pack(tmp_path)
    eval_file = pack_dir / "evaluations/M01-A0.toml"
    _replace(eval_file, 'mission_id = "M01"', 'mission_id = "M99"')
    with pytest.raises(LanguagePackError, match=r"/mission_id: unknown mission"):
        load_evaluation_cases(load_pack(pack_dir))

    pack_dir = _copy_pack(tmp_path / "leak")
    eval_file = pack_dir / "evaluations/M01-A0.toml"
    _replace(
        eval_file,
        'acceptable = ["Esto es un tenedor."]',
        'acceptable = ["el libro"]',
    )
    with pytest.raises(LanguagePackError, match="duplicates a generation example"):
        load_evaluation_cases(load_pack(pack_dir))

    pack_dir = _copy_pack(tmp_path / "non-nfc-input")
    eval_file = pack_dir / "evaluations/M01-A0.toml"
    _replace(
        eval_file,
        'input = "Say what the highlighted object is (a fork)."',
        r'input = "Say what the highlighted object is (a pla\u0301te)."',
    )
    with pytest.raises(LanguagePackError, match=r"/cases/0/input: text must be NFC"):
        load_evaluation_cases(load_pack(pack_dir))

    pack_dir = _copy_pack(tmp_path / "isolation")
    eval_file = pack_dir / "evaluations/M01-A0.toml"
    eval_file.write_text("not valid TOML", encoding="utf-8")
    assert load_pack(pack_dir).pack_id == "es-es-everyday"
    with pytest.raises(LanguagePackError):
        load_evaluation_cases(load_pack(pack_dir))


def test_malformed_toml_and_provenance_reviewers_are_rejected(tmp_path):
    pack_dir = _copy_pack(tmp_path)
    (pack_dir / "labels.toml").write_text("not valid TOML", encoding="utf-8")
    with pytest.raises(LanguagePackError, match="TOML"):
        load_pack(pack_dir)

    pack_dir = _copy_pack(tmp_path / "review-status")
    _replace(
        pack_dir / "pack.toml",
        'review_status = "unreviewed"',
        'review_status = "humanReviewed"',
    )
    with pytest.raises(LanguagePackError, match="humanReviewed provenance requires"):
        load_pack(pack_dir)

    pack_dir = _copy_pack(tmp_path / "reviewer-list")
    _replace(
        pack_dir / "pack.toml",
        'review_status = "unreviewed"',
        'review_status = "unreviewed"\nreviewers = ["test reviewer"]',
    )
    with pytest.raises(LanguagePackError, match="cannot list reviewers"):
        load_pack(pack_dir)


def test_scene_relations_and_attribute_kinds_use_shared_enums(tmp_path):
    pack_dir = _copy_pack(tmp_path)
    _replace(
        pack_dir / "examples/scene-location.toml",
        'relation = "on"',
        'relation = "sobre"',
    )
    with pytest.raises(LanguagePackError, match=r"(?i)input should be"):
        load_pack(pack_dir)

    pack_dir = _copy_pack(tmp_path / "attribute-kind")
    _replace(
        pack_dir / "examples/describe-attribute.toml",
        'kind = "color"',
        'kind = "colour"',
    )
    with pytest.raises(LanguagePackError, match=r"(?i)input should be"):
        load_pack(pack_dir)

    pack_dir = _copy_pack(tmp_path / "fact-id")
    _replace(
        pack_dir / "examples/identify-object.toml",
        'fact_id = "object:book"',
        'fact_id = "shown:book"',
    )
    with pytest.raises(LanguagePackError, match="object fact_id must be object"):
        load_pack(pack_dir)
