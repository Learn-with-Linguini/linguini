"""Load and validate opt-in language packs and mission plans."""

from __future__ import annotations

import re
import tomllib
from collections.abc import Sequence
from dataclasses import dataclass
from functools import cache
from glob import glob, has_magic
from pathlib import Path, PurePosixPath, PureWindowsPath
from unicodedata import normalize

from pydantic import ValidationError

from app.config import get_language_pack_dirs
from app.missions import get_mission

from .schema import (
    SUPPORTED_FORMAT_VERSIONS,
    Construction,
    ConstructionExamplesFile,
    EvaluationCase,
    EvaluationFile,
    GuidanceBundle,
    LabelsFile,
    LanguagePack,
    MissionCatalog,
    PackFiles,
)


class LanguagePackError(ValueError):
    def __init__(self, file: str | Path, pointer: str, message: str) -> None:
        self.file = str(file)
        self.pointer = pointer
        self.message = message
        super().__init__(f"{self.file} {pointer}: {message}")


_LOCALE_DIRECTORY = re.compile(
    r"^[a-z]{2,3}(?:-[A-Z][a-z]{3})?(?:-(?:[A-Z]{2}|[0-9]{3}))?$"
)


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


def _check_nfc(
    value: object,
    file: Path,
    path: tuple[object, ...] = (),
    allowed_paths: tuple[tuple[object, ...], ...] = (),
) -> None:
    if path in allowed_paths:
        return
    if isinstance(value, str):
        if normalize("NFC", value) != value:
            raise LanguagePackError(file, _pointer(path), "text must be NFC")
    elif isinstance(value, dict):
        for key, item in value.items():
            _check_nfc(item, file, (*path, key), allowed_paths)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _check_nfc(item, file, (*path, index), allowed_paths)


def _load_toml(
    path: Path,
    *,
    allowed_non_nfc_paths: tuple[tuple[object, ...], ...] = (),
) -> dict:
    try:
        data = tomllib.loads(path.read_text("utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise LanguagePackError(path, "/", f"malformed TOML: {exc}") from None
    _check_nfc(data, path, allowed_paths=allowed_non_nfc_paths)
    return data


def _validation_pointer(exc: ValidationError) -> str:
    first = exc.errors(include_url=False)[0]
    return _pointer(first["loc"])


def _relative_file(
    pack_dir: Path,
    reference: str,
    source: Path,
    pointer: str,
    category: str | None = None,
) -> Path:
    relative = PurePosixPath(reference)
    windows = PureWindowsPath(reference)
    if (
        relative.is_absolute()
        or windows.is_absolute()
        or windows.drive
        or ".." in relative.parts
        or "\\" in reference
    ):
        raise LanguagePackError(source, pointer, "file reference must stay inside the pack")
    if not relative.parts or relative.suffix != ".toml":
        raise LanguagePackError(source, pointer, "file reference must name a TOML file")
    if category is not None and relative.parts[0] != category:
        raise LanguagePackError(
            source, pointer, f"file reference must be under {category}/"
        )
    resolved = (pack_dir / Path(*relative.parts)).resolve()
    if not resolved.is_relative_to(pack_dir):
        raise LanguagePackError(source, pointer, "file reference escapes the pack directory")
    if not resolved.is_file():
        raise LanguagePackError(source, pointer, f"referenced file does not exist: {reference}")
    return resolved


def _referenced_files(pack_dir: Path, source: Path, files: PackFiles) -> dict[str, list[Path]]:
    resolved = {
        "labels": [
            _relative_file(pack_dir, files.labels, source, "/files/labels")
        ],
        "constructions": [
            _relative_file(
                pack_dir, value, source, f"/files/constructions/{index}", "constructions"
            )
            for index, value in enumerate(files.constructions)
        ],
        "examples": [
            _relative_file(
                pack_dir, value, source, f"/files/examples/{index}", "examples"
            )
            for index, value in enumerate(files.examples)
        ],
        "evaluations": [
            _relative_file(
                pack_dir, value, source, f"/files/evaluations/{index}", "evaluations"
            )
            for index, value in enumerate(files.evaluations)
        ],
    }
    all_paths = [path for group in resolved.values() for path in group]
    if len(all_paths) != len(set(all_paths)):
        raise LanguagePackError(source, "/files", "duplicate file references")

    referenced = set(all_paths)
    for category in ("constructions", "examples", "evaluations"):
        folder = pack_dir / category
        for path in folder.rglob("*.toml") if folder.exists() else ():
            resolved_path = path.resolve()
            if not resolved_path.is_relative_to(pack_dir):
                raise LanguagePackError(
                    path, "/", "TOML file resolves outside the pack directory"
                )
            if resolved_path not in referenced:
                raise LanguagePackError(
                    path, "/", f"unreferenced TOML file under {category}/"
                )
    return resolved


def _model_from_file(model, data: dict, path: Path):
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        raise LanguagePackError(path, _validation_pointer(exc), str(exc)) from None


def _validate_pack_directory(
    pack: LanguagePack,
    pack_file: Path,
    root: Path,
) -> None:
    relative = pack_file.parent.resolve().relative_to(root)
    if len(relative.parts) < 2:
        return
    locale_directory, register_directory = relative.parts[-2:]
    if not _LOCALE_DIRECTORY.fullmatch(locale_directory):
        return
    if pack.language.locale != locale_directory:
        raise LanguagePackError(
            pack_file,
            "/language/locale",
            f"locale {pack.language.locale!r} does not match directory "
            f"{locale_directory!r}",
        )
    if pack.language_register.register_id != register_directory:
        raise LanguagePackError(
            pack_file,
            "/register/register_id",
            f"register_id {pack.language_register.register_id!r} does not match "
            f"directory {register_directory!r}",
        )


def load_pack(path: Path) -> LanguagePack:
    path = Path(path)
    pack_file = path / "pack.toml" if path.is_dir() else path
    pack_dir = pack_file.parent.resolve()
    data = _load_toml(pack_file)
    format_version = data.get("format_version")
    if format_version not in SUPPORTED_FORMAT_VERSIONS:
        raise LanguagePackError(
            pack_file, "/format_version", f"unsupported format_version {format_version!r}"
        )
    files = _model_from_file(PackFiles, data.get("files", {}), pack_file)
    resolved = _referenced_files(pack_dir, pack_file, files)

    labels_data = _load_toml(resolved["labels"][0])
    labels_file = _model_from_file(LabelsFile, labels_data, resolved["labels"][0])

    definitions = {}
    for construction_path in resolved["constructions"]:
        if construction_path.stem in definitions:
            raise LanguagePackError(
                construction_path, "/construction_id", "duplicate construction file stem"
            )
        definition_data = _load_toml(construction_path)
        construction_id = definition_data.get("construction_id")
        if construction_id != construction_path.stem:
            raise LanguagePackError(
                construction_path,
                "/construction_id",
                "construction_id must equal the file stem",
            )
        definitions[construction_path.stem] = definition_data

    examples_by_construction = {}
    examples_paths_by_stem = {}
    for examples_path in resolved["examples"]:
        if examples_path.stem in examples_by_construction:
            raise LanguagePackError(
                examples_path, "/construction_id", "duplicate examples file stem"
            )
        examples_data = _load_toml(examples_path)
        examples_file = _model_from_file(
            ConstructionExamplesFile, examples_data, examples_path
        )
        if examples_file.construction_id != examples_path.stem:
            raise LanguagePackError(
                examples_path,
                "/construction_id",
                "construction_id must equal the file stem",
            )
        examples_by_construction[examples_path.stem] = examples_file
        examples_paths_by_stem[examples_path.stem] = examples_path

    if set(definitions) != set(examples_by_construction):
        raise LanguagePackError(
            pack_file,
            "/files",
            "construction and examples files must have matching stems",
        )
    constructions = []
    for construction_id, definition in definitions.items():
        examples_file = examples_by_construction[construction_id]
        combined = {
            **definition,
            "examples": [item.model_dump(mode="python", by_alias=False)
                         for item in examples_file.examples],
            "mistakes": [item.model_dump(mode="python", by_alias=False)
                         for item in examples_file.mistakes],
        }
        try:
            constructions.append(Construction.model_validate(combined))
        except ValidationError as exc:
            path_for_error = (
                examples_paths_by_stem[construction_id]
                if exc.errors(include_url=False)[0]["loc"][0] in {"examples", "mistakes"}
                else next(
                    item for item in resolved["constructions"]
                    if item.stem == construction_id
                )
            )
            raise LanguagePackError(
                path_for_error, _validation_pointer(exc), str(exc)
            ) from None

    pack_data = {key: value for key, value in data.items() if key != "files"}
    pack_data["labels"] = [
        item.model_dump(mode="python", by_alias=False) for item in labels_file.labels
    ]
    pack_data["constructions"] = [
        item.model_dump(mode="python", by_alias=False) for item in constructions
    ]
    try:
        pack = LanguagePack.model_validate(pack_data)
    except ValidationError as exc:
        raise LanguagePackError(pack_file, _validation_pointer(exc), str(exc)) from None
    pack._pack_dir = pack_dir
    pack._evaluation_files = resolved["evaluations"]
    _validate_pack_mission_contracts(pack, pack_file, examples_paths_by_stem)
    return pack


def _validate_pack_mission_contracts(
    pack: LanguagePack,
    pack_file: Path,
    examples_paths_by_stem: dict[str, Path],
) -> None:
    catalog = load_mission_catalog()
    level_slots = [
        (template.practice_level, slot)
        for template in catalog.missions
        for slot in template.slots
    ]
    labels_by_id = {label.semantic: label for label in pack.labels}
    for template_index, template in enumerate(catalog.missions):
        for slot_index, slot in enumerate(template.slots):
            slot_pointer = f"/missions/{template_index}/slots/{slot_index}"
            for label_id in slot.prompt_labels:
                label = labels_by_id.get(label_id)
                if label is None:
                    continue
                if label.usage != "prompt":
                    raise LanguagePackError(
                        pack_file, f"{slot_pointer}/prompt_labels",
                        f"label {label_id!r} must have prompt usage",
                    )
            for label_id in slot.sentence_labels:
                label = labels_by_id.get(label_id)
                if label is None:
                    continue
                if label.usage != "sentence":
                    raise LanguagePackError(
                        pack_file, f"{slot_pointer}/sentence_labels",
                        f"label {label_id!r} must have sentence usage",
                    )

    for construction in pack.constructions:
        source = examples_paths_by_stem[construction.construction_id]
        for example in (*construction.examples, *construction.mistakes):
            for level in example.levels:
                for purpose in example.purposes:
                    if not any(
                        slot_purpose.purpose == purpose
                        and slot_purpose.construction_ids.count(
                            construction.construction_id
                        )
                        and str(getattr(slot_level, "value", slot_level))
                        == str(getattr(level, "value", level))
                        for slot_level, slot_purpose in level_slots
                    ):
                        raise LanguagePackError(
                            source,
                            f"/{ 'examples' if example in construction.examples else 'mistakes' }",
                            f"{example.example_id} ({level}, {purpose}) does not match a "
                            f"mission slot using {construction.construction_id}",
                        )


def load_evaluation_cases(pack: LanguagePack) -> list[EvaluationCase]:
    if pack._pack_dir is None:
        raise LanguagePackError("<pack>", "/files/evaluations", "pack has no source directory")
    constructions = {item.construction_id: item for item in pack.constructions}
    known_labels = {item.semantic for item in pack.labels}
    example_sentences = {
        sentence
        for construction in pack.constructions
        for example in construction.examples
        for sentence in (example.sentence, *example.accepted_alternatives)
    }
    mission_keys = {item.key for item in load_mission_catalog().missions}
    cases = []
    seen_case_ids = set()
    for path in pack._evaluation_files:
        try:
            raw_data = tomllib.loads(path.read_text("utf-8"))
        except (OSError, tomllib.TOMLDecodeError) as exc:
            raise LanguagePackError(path, "/", f"malformed TOML: {exc}") from None
        allowed_non_nfc_paths = tuple(
            ("cases", index, "reject", reject_index, "sentence")
            for index, case in enumerate(raw_data.get("cases", []))
            for reject_index, _ in enumerate(case.get("reject", []))
        )
        _check_nfc(raw_data, path, allowed_paths=allowed_non_nfc_paths)
        data = raw_data
        evaluation = _model_from_file(EvaluationFile, data, path)
        level = getattr(evaluation.practice_level, "value", evaluation.practice_level)
        key = (evaluation.mission_id, str(level), evaluation.content_version)
        if key not in mission_keys:
            raise LanguagePackError(
                path, "/mission_id",
                f"unknown mission/level/content version {key}",
            )
        mission = next(item for item in load_mission_catalog().missions if item.key == key)
        mission_constructions = {
            construction_id
            for slot in mission.slots
            for construction_id in slot.construction_ids
        }
        for index, case in enumerate(evaluation.cases):
            if case.case_id in seen_case_ids:
                raise LanguagePackError(
                    path, f"/cases/{index}/case_id", "case_id values must be unique"
                )
            seen_case_ids.add(case.case_id)
            construction = constructions.get(case.construction_id)
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
            if case.construction_id not in mission_constructions:
                raise LanguagePackError(
                    path,
                    f"/cases/{index}/construction_id",
                    f"construction {case.construction_id!r} is not used by "
                    f"{evaluation.mission_id} {level}",
                )
            if unknown := set(case.labels) - known_labels:
                raise LanguagePackError(
                    path, f"/cases/{index}/labels", f"unknown labels: {sorted(unknown)}"
                )
            if any(
                next(label for label in pack.labels if label.semantic == semantic).usage
                != "sentence"
                for semantic in case.labels
            ):
                raise LanguagePackError(
                    path, f"/cases/{index}/labels", "evaluation labels must be sentence labels"
                )
            if leaked := example_sentences & set(case.acceptable):
                raise LanguagePackError(
                    path, f"/cases/{index}/acceptable",
                    f"evaluation sentence duplicates a generation example: {sorted(leaked)}",
                )
            cases.append(case)
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
            for construction_id in slot.construction_ids:
                if construction_id not in {
                    item.construction_id for item in template.required_constructions
                }:
                    raise LanguagePackError(
                        catalog_path,
                        f"/missions/{mission_index}/slots/{slot_index}/construction_id",
                        f"{construction_id!r} is not a required construction",
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


def guidance_for_slot(
    pack: LanguagePack,
    mission_key,
    purpose: str,
    construction_id: str | None = None,
) -> GuidanceBundle:
    key = mission_key.key if hasattr(mission_key, "key") else tuple(mission_key)
    templates = {template.key: template for template in load_mission_catalog().missions}
    template = templates.get(key)
    if template is None:
        raise LanguagePackError(
            pack._pack_dir or "<pack>", "/missions",
            f"unknown mission key {key!r}",
        )
    matches = [slot for slot in template.slots if slot.purpose == purpose]
    if construction_id is not None:
        matches = [slot for slot in matches if construction_id in slot.construction_ids]
    if len(matches) != 1:
        raise LanguagePackError(
            pack._pack_dir or "<pack>", "/missions",
            f"expected one slot for {purpose!r}, found {len(matches)}",
        )
    slot = matches[0]
    selected_id = construction_id or slot.construction_id
    by_id = {item.construction_id: item for item in pack.constructions}
    construction = by_id.get(selected_id)
    if construction is None:
        raise LanguagePackError(
            pack._pack_dir or "<pack>", "/constructions",
            f"missing construction {selected_id!r}",
        )
    level = getattr(template.practice_level, "value", template.practice_level)
    selected_examples = [
        item for item in construction.examples
        if level in item.levels and purpose in item.purposes
    ]
    selected_mistakes = [
        item for item in construction.mistakes
        if level in item.levels and purpose in item.purposes
    ]
    slot_labels = set(slot.required_labels)
    filtered_construction = construction.model_copy(update={
        "required_labels": [
            label for label in construction.required_labels if label in slot_labels
        ],
        "examples": selected_examples,
        "mistakes": selected_mistakes,
    })
    labels = [label for label in pack.labels if label.semantic in slot_labels]
    return GuidanceBundle(
        language=pack.language,
        variety=pack.variety,
        language_register=pack.language_register,
        labels=labels,
        constructions=[filtered_construction],
        mission_id=template.mission_id,
        practice_level=template.practice_level,
        purpose=purpose,
        prompt_labels=slot.prompt_labels,
        sentence_labels=slot.sentence_labels,
    )


@cache
def _load_packs_for_roots(root_paths: tuple[str, ...], revision=()) -> PackSet:
    if not root_paths:
        return PackSet()
    packs = []
    seen_pack_ids: set[str] = set()
    seen_files: set[Path] = set()
    load_mission_catalog()
    for root_text in root_paths:
        root = Path(root_text)
        if not root.is_dir():
            raise LanguagePackError(root, "/", "pack root is not a directory")
        root = root.resolve()
        pack_files = sorted(root.rglob("pack.toml"))
        if (root / "pack.toml").is_file():
            nested = [item for item in pack_files if item != root / "pack.toml"]
            pack_files = [root / "pack.toml", *nested]
        for pack_file in pack_files:
            if not pack_file.is_file():
                continue
            if not pack_file.resolve().is_relative_to(root):
                raise LanguagePackError(pack_file, "/", "pack file escapes the configured root")
            if pack_file.resolve() in seen_files:
                continue
            seen_files.add(pack_file.resolve())
            pack = load_pack(pack_file)
            _validate_pack_directory(pack, pack_file, root)
            if pack.pack_id in seen_pack_ids:
                raise LanguagePackError(
                    pack_file, "/pack_id", f"duplicate pack_id {pack.pack_id!r}"
                )
            seen_pack_ids.add(pack.pack_id)
            packs.append(pack)
    return PackSet(tuple(packs))


def load_packs(roots: Sequence[Path] | None = None) -> PackSet:
    selected_roots = get_language_pack_dirs() if roots is None else roots
    expanded = []
    for root in selected_roots:
        pattern = str(Path(root).expanduser())
        matches = sorted(glob(pattern, recursive=True)) if has_magic(pattern) else [pattern]
        if not matches:
            raise LanguagePackError(root, "/", "pack root pattern matched no paths")
        if has_magic(pattern) and not any(Path(match).is_dir() for match in matches):
            raise LanguagePackError(root, "/", "pack root pattern matched no directories")
        for match in matches:
            if has_magic(pattern) and not Path(match).is_dir():
                continue
            expanded.append(str(Path(match).resolve()))
    resolved = tuple(dict.fromkeys(expanded))
    revision = tuple((str(path), path.stat().st_mtime_ns, path.stat().st_size)
                     for root in resolved for path in sorted(Path(root).rglob("*.toml")))
    return _load_packs_for_roots(resolved, revision)
