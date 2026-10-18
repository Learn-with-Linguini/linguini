"""Local validation and preview CLI; it does not load application services."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

from app.schemas.enums import ProficiencyLevel

from .assembly import assemble, is_correct
from .capabilities import lesson_plan, mission_capability
from .fingerprint import language_pack_feature_version, pack_fingerprint
from .generation import (
    ApprovedVocabulary,
    BoundSceneFacts,
    CandidateSentence,
    approve,
    assess,
    check_deterministic,
)
from .loader import (
    LanguagePackError,
    guidance_for,
    load_evaluation_cases,
    load_pack,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="language-pack-preview")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate")
    validate.add_argument("--pack-dir", type=Path, required=True)

    for command in ("capability", "plan"):
        preview = subparsers.add_parser(command)
        preview.add_argument("--pack-dir", type=Path, required=True)
        preview.add_argument("--language", required=True)
        preview.add_argument("--register", required=True)
        if command == "plan":
            preview.add_argument("--level", choices=["A0", "A1", "A2"], required=True)
            preview.add_argument("--scene", type=Path, required=True)

    assemble_parser = subparsers.add_parser("assemble")
    assemble_parser.add_argument("--pack-dir", type=Path, required=True)
    assemble_parser.add_argument("--language", required=True)
    assemble_parser.add_argument("--register", required=True)
    assemble_parser.add_argument("--candidates", type=Path, required=True)
    assemble_parser.add_argument("--scene", type=Path, required=True)
    assemble_parser.add_argument("--level", choices=["A0", "A1", "A2"], required=True)
    assemble_parser.add_argument("--allow-unassessed", action="store_true")
    return parser


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text("utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"{path}: {exc}") from None


def _checked_pack(args: argparse.Namespace):
    pack = load_pack(args.pack_dir)
    if args.command != "validate":
        if pack.language.code != args.language:
            raise ValueError(
                f"pack language {pack.language.code!r} does not match {args.language!r}"
            )
        if pack.language_register.register_id != args.register:
            raise ValueError(
                f"pack register {pack.language_register.register_id!r} does not match "
                f"{args.register!r}"
            )
    return pack


def _run(args: argparse.Namespace) -> dict[str, Any]:
    pack = _checked_pack(args)
    if args.command == "validate":
        return {
            "valid": True,
            "pack_id": pack.pack_id,
            "language": pack.language.code,
            "evaluation_cases": len(load_evaluation_cases(pack)),
        }
    if args.command == "capability":
        return {
            "language": pack.language.code,
            "register_id": pack.language_register.register_id,
            "levels": {
                level: mission_capability(
                    pack, ("M01", ProficiencyLevel(level), 1)
                ).model_dump(mode="json", by_alias=False)
                for level in ("A0", "A1", "A2")
            },
        }

    scene = _read_json(args.scene)
    key = ("M01", ProficiencyLevel(args.level), 1) if args.command in {
        "plan", "assemble"
    } else None
    plan = lesson_plan(pack, key, scene.get("slot_bindings", {})) if key else None
    if args.command == "plan":
        assert plan is not None
        construction_ids = list(dict.fromkeys(slot.construction_id for slot in plan.slots))
        generation_version = "language-pack-generation.v1"
        fingerprint = pack_fingerprint(pack, construction_ids, generation_version)
        return {
            "plan": plan.model_dump(mode="json", by_alias=False),
            "guidance": guidance_for(pack, construction_ids).model_dump(
                mode="json", by_alias=False
            ),
            "fingerprint": fingerprint,
            "feature_version": asdict(
                language_pack_feature_version(
                    "language-pack-generation", generation_version, fingerprint
                )
            ),
        }

    raw_candidates = _read_json(args.candidates)
    candidates = [CandidateSentence.model_validate(item) for item in raw_candidates]
    assert plan is not None
    facts = BoundSceneFacts.model_validate(
        scene.get("facts", {"scene_facts": {}})
    )
    vocabulary = ApprovedVocabulary.model_validate(scene.get("vocabulary", {}))
    approval = approve(
        candidates,
        plan,
        facts=facts,
        vocabulary=vocabulary,
        pack=pack,
        allow_unassessed=args.allow_unassessed,
    )
    assembled = []
    for approved in approval.approved:
        item = assemble(approved)
        assembled.append(
            {
                "slot_id": approved.candidate.slot_id,
                "item": item.model_dump(mode="json", by_alias=False),
                "answer_tile_ids": item.answer_tile_ids,
                "answer_is_correct": is_correct(item, item.answer_tile_ids),
            }
        )
    outcomes = []
    for candidate in candidates:
        report = check_deterministic(candidate, plan, facts, vocabulary, pack)
        assessment = assess(candidate, pack)
        outcome = next(
            (
                item for item in approval.approved
                if item.candidate == candidate
            ),
            None,
        )
        failure = next(
            (
                item for item in approval.failures
                if item.candidate == candidate
            ),
            None,
        )
        outcomes.append(
            {
                "slot_id": candidate.slot_id,
                "deterministic_report": report.model_dump(
                    mode="json", by_alias=False
                ),
                "assessment": assessment.model_dump(mode="json", by_alias=False),
                "approved_sentence": outcome.model_dump(
                    mode="json", by_alias=False
                ) if outcome else None,
                "failure": failure.model_dump(
                    mode="json", by_alias=False
                ) if failure else None,
            }
        )
    return {
        "outcomes": outcomes,
        "approved": [item.candidate.slot_id for item in approval.approved],
        "failures": [item.model_dump(mode="json", by_alias=False) for item in approval.failures],
        "assembled": assembled,
    }


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        output = _run(args)
    except (LanguagePackError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 2
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return int(args.command == "assemble" and bool(output.get("failures")))


if __name__ == "__main__":
    raise SystemExit(main())
