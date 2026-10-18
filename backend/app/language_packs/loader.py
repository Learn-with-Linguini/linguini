"""Load and validate opt-in language packs and mission plans."""

from __future__ import annotations

import tomllib
from collections.abc import Sequence
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from unicodedata import normalize

from pydantic import ValidationError

from app.config import get_language_pack_dirs
from app.missions import get_mission

from .schema import (
    SUPPORTED_FORMAT_VERSIONS,
    EvaluationCase,
    GuidanceBundle,
    LanguagePack,
    MissionCatalog,
)


class LanguagePackError(ValueError):
    def __init__(self, file: str | Path, pointer: str, message: str) -> None:
        self.file = str(file)
        self.pointer = pointer
        self.message = message
        super().__init__(f"{self.file} {pointer}: {message}")


@dataclass(frozen=True)
class PackSet:
    packs: tuple[LanguagePack, ...] = ()

    def get(self, language: str, register_id: str) -> LanguagePack:
        matches = [
            pack for pack in self.packs
            if (
                pack.language.code == language
                and pack.language_register.register_id == register_id
            )
        ]
        if not matches:
            raise LanguagePackError(
                "<pack set>", "/", f"no pack for language={language!r}, register={register_id!r}"
            )
        if len(matches) > 1:
            raise LanguagePackError(
                "<pack set>", "/", f"ambiguous packs for language={language!r}, "
                f"register={register_id!r}"
            )
        return matches[0]


def _pointer(parts: Sequence[object]) -> str:
    if not parts:
        return "/"
    escaped = [str(part).replace("~", "~0").replace("/", "~1") for part in parts]
    return "/" + "/".join(escaped)


def _check_nfc(value: object, file: Path, path: tuple[object, ...] = ()) -> None:
    if isinstance(value, str):
        if normalize("NFC", value) != value:
            raise LanguagePackError(file, _pointer(path), "text must be NFC")
    elif isinstance(value, dict):
        for key, item in value.items():
            _check_nfc(item, file, (*path, key))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _check_nfc(item, file, (*path, index))


def _load_toml(path: Path) -> dict:
    try:
        data = tomllib.loads(path.read_text("utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise LanguagePackError(path, "/", str(exc)) from None
    _check_nfc(data, path)
    return data


def _validation_pointer(exc: ValidationError) -> str:
    first = exc.errors(include_url=False)[0]
    return _pointer(first["loc"])


def _validate_pack(path: Path) -> LanguagePack:
    data = _load_toml(path)
    format_version = data.get("format_version")
    if format_version not in SUPPORTED_FORMAT_VERSIONS:
        raise LanguagePackError(
            path, "/format_version", f"unsupported format_version {format_version!r}"
        )
    try:
        pack = LanguagePack.model_validate(data)
    except ValidationError as exc:
        raise LanguagePackError(path, _validation_pointer(exc), str(exc)) from None
    pack._pack_dir = path.parent.resolve()
    return pack


def _check_evaluation(pack: LanguagePack, cases: list[EvaluationCase], path: Path) -> None:
    by_id = {construction.construction_id: construction for construction in pack.constructions}
    example_sentences = {
        sentence
        for construction in pack.constructions
        for example in construction.examples
        for sentence in (example.sentence, *example.accepted_alternatives)
    }
    known_labels = {label.semantic for label in pack.labels}
    case_ids = [case.case_id for case in cases]
    if len(case_ids) != len(set(case_ids)):
        raise LanguagePackError(path, "/cases", "case_id values must be unique")
    for index, case in enumerate(cases):
        construction = by_id.get(case.construction_id)
        if construction is None:
            raise LanguagePackError(
                path, f"/cases/{index}/construction_id",
                f"unknown construction {case.construction_id!r}",
            )
        if case.construction_version != construction.version:
            raise LanguagePackError(
                path, f"/cases/{index}/construction_version",
                f"expected construction version {construction.version}",
            )
        if unknown := {fact.label for fact in case.facts} - known_labels:
            raise LanguagePackError(
                path, f"/cases/{index}/facts",
                f"unknown fact labels: {sorted(unknown)}",
            )
        if leaked := example_sentences & set(case.expected):
            raise LanguagePackError(
                path, f"/cases/{index}/expected",
                f"evaluation expected sentence duplicates a generation example: "
                f"{sorted(leaked)}",
            )


def load_pack(path: Path) -> LanguagePack:
    path = Path(path)
    pack_file = path / "pack.toml" if path.is_dir() else path
    pack = _validate_pack(pack_file)
    evaluation_file = pack._pack_dir / "evaluation.toml"
    if evaluation_file.exists():
        load_evaluation_cases(pack)
    return pack


def load_evaluation_cases(pack: LanguagePack) -> list[EvaluationCase]:
    pack_dir = pack._pack_dir
    if pack_dir is None:
        raise LanguagePackError("<pack>", "/evaluation.toml", "pack has no source directory")
    path = pack_dir / "evaluation.toml"
    if not path.exists():
        return []
    data = _load_toml(path)
    try:
        cases = [EvaluationCase.model_validate(item) for item in data.get("cases", [])]
    except ValidationError as exc:
        raise LanguagePackError(path, _validation_pointer(exc), str(exc)) from None
    if set(data) - {"cases"}:
        extra = sorted(set(data) - {"cases"})[0]
        raise LanguagePackError(path, f"/{extra}", "unknown evaluation key")
    _check_evaluation(pack, cases, path)
    return cases


@cache
def _load_mission_catalog_cached(path: str) -> MissionCatalog:
    catalog_path = Path(path)
    data = _load_toml(catalog_path)
    try:
        catalog = MissionCatalog.model_validate(data)
    except ValidationError as exc:
        raise LanguagePackError(catalog_path, _validation_pointer(exc), str(exc)) from None

    for mission_index, template in enumerate(catalog.missions):
        mission = get_mission(
            template.mission_id, template.practice_level, template.content_version
        )
        if mission is None:
            raise LanguagePackError(
                catalog_path, f"/missions/{mission_index}",
                f"unknown mission {template.key}",
            )
        target_ids = set(mission.targets)
        for slot_index, slot in enumerate(template.slots):
            if unknown := set(slot.target_ids) - target_ids:
                raise LanguagePackError(
                    catalog_path, f"/missions/{mission_index}/slots/{slot_index}/target_ids",
                    f"unknown mission targets: {sorted(unknown)}",
                )
        required = [item.construction_id for item in template.required_constructions]
        if len(required) != len(set(required)):
            raise LanguagePackError(
                catalog_path, f"/missions/{mission_index}/required_constructions",
                "construction requirements must be unique",
            )
    return catalog


def load_mission_catalog(path: Path | None = None) -> MissionCatalog:
    catalog_path = path or Path(__file__).with_name("missions.toml")
    return _load_mission_catalog_cached(str(catalog_path.resolve()))


def guidance_for(pack: LanguagePack, construction_ids: Sequence[str]) -> GuidanceBundle:
    requested = list(dict.fromkeys(construction_ids))
    by_id = {item.construction_id: item for item in pack.constructions}
    missing = [item for item in requested if item not in by_id]
    if missing:
        raise LanguagePackError(
            pack._pack_dir or "<pack>", "/constructions",
            f"missing constructions: {', '.join(missing)}",
        )
    return GuidanceBundle(
        language=pack.language,
        variety=pack.variety,
        language_register=pack.language_register,
        labels=pack.labels,
        constructions=[by_id[item] for item in requested],
    )


@cache
def _load_packs_for_roots(root_paths: tuple[str, ...]) -> PackSet:
    if not root_paths:
        return PackSet()
    packs = []
    seen_pack_ids: set[str] = set()
    load_mission_catalog()
    for root_text in root_paths:
        root = Path(root_text)
        if not root.is_dir():
            raise LanguagePackError(root, "/", "pack root is not a directory")
        for pack_dir in sorted(path for path in root.iterdir() if path.is_dir()):
            pack_file = pack_dir / "pack.toml"
            if not pack_file.is_file():
                continue
            pack = load_pack(pack_file)
            if pack.pack_id in seen_pack_ids:
                raise LanguagePackError(
                    pack_file, "/pack_id", f"duplicate pack_id {pack.pack_id!r}"
                )
            seen_pack_ids.add(pack.pack_id)
            packs.append(pack)
    return PackSet(tuple(packs))


def load_packs(roots: Sequence[Path] | None = None) -> PackSet:
    selected_roots = get_language_pack_dirs() if roots is None else roots
    resolved = tuple(str(Path(root).expanduser().resolve()) for root in selected_roots)
    return _load_packs_for_roots(resolved)
