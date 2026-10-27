"""Local validation and preview CLI; it does not load application services."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

from app.ai.contracts.text import TextModelConfig, TextModelResponse
from app.ai.observability import NoOpAITracer
from app.ai.registry import build_routed_client
from app.ai.settings import AiFeature, load_ai_settings

from .assembly import assemble, is_correct
from .capabilities import lesson_plan, mission_capability, mission_template_key
from .evaluation import evaluate_pack
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
    load_mission_catalog,
    load_pack,
)
from .model_source import ModelSource
from .pipeline import generate_pilot


class _ScriptedTextClient:
    generation_settings = {"source": "scripted-responses"}
    approved_deployments = frozenset({"scripted"})
    max_duration_seconds = 0

    def __init__(self, response: dict[str, Any]) -> None:
        self.response = response

    def generate(self, request):
        return TextModelResponse(
            output_text=json.dumps(self.response, ensure_ascii=False),
            model_name="scripted-non-live",
            prompt_version=request.prompt_version,
        )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="language-pack-preview")
    parser.add_argument(
        "--env-file", type=Path, help="Explicit local environment file for model runs"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate")
    validate.add_argument("--pack-dir", type=Path, required=True)

    for command in ("capability", "plan"):
        preview = subparsers.add_parser(command)
        preview.add_argument("--pack-dir", type=Path, required=True)
        preview.add_argument("--language", required=True)
        preview.add_argument("--register", required=True)
        preview.add_argument("--mission", default="M01")
        if command == "capability":
            preview.add_argument("--evidence", type=Path)
        if command == "plan":
            preview.add_argument("--level", choices=["A0", "A1", "A2"], required=True)
            preview.add_argument("--scene", type=Path, required=True)

    evaluate_parser = subparsers.add_parser("evaluate")
    evaluate_parser.add_argument("--pack-dir", type=Path, required=True)
    evaluate_parser.add_argument("--language", required=True)
    evaluate_parser.add_argument("--register", required=True)
    evaluate_parser.add_argument("--level", choices=["A0", "A1", "A2"], required=True)
    evaluate_parser.add_argument("--vocabulary", type=Path, required=True)
    evaluate_parser.add_argument("--mission", default="M01")
    evaluate_parser.add_argument("--out", type=Path)

    generate_parser = subparsers.add_parser("generate")
    generate_parser.add_argument("--pack-dir", type=Path, required=True)
    generate_parser.add_argument("--language", required=True)
    generate_parser.add_argument("--register", required=True)
    generate_parser.add_argument("--level", choices=["A0", "A1", "A2"], required=True)
    generate_parser.add_argument("--scene", type=Path, required=True)
    generate_parser.add_argument("--vocabulary", type=Path, required=True)
    generate_parser.add_argument("--source", choices=["responses", "model"], default="responses")
    generate_parser.add_argument("--responses", type=Path)
    generate_parser.add_argument("--preview", action="store_true")
    generate_parser.add_argument("--evidence", type=Path)
    generate_parser.add_argument("--mission", default="M01")

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


def _evidence(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    raw = _read_json(path)
    return raw.get("evaluation_record", raw)


def _text_model_source() -> ModelSource:
    settings = load_ai_settings()
    config = settings.feature(AiFeature.LEARNING_TASK)
    if not settings.is_configured(config):
        raise ValueError(
            "model source requires configured AI learning-task credentials "
            "(for example AI_OPENAI_API_KEY); no model request was sent"
        )
    client, model_config = build_routed_client(
        "text",
        settings,
        AiFeature.LEARNING_TASK,
        default_max_output_tokens=4000,
        tracer=NoOpAITracer(),
    )
    return ModelSource(client, model_config, mode="model", propose=True)


def _evaluation_table(report: dict[str, Any]) -> str:
    structural = report["structural"]
    linguistic = report["linguistic"]
    return "\n".join(
        (
            f"{report.get('mission_id', 'M01')} {report['practice_level']} evaluation",
            (
                "Structural: "
                f"{structural['valid_alternatives_accepted']}/"
                f"{structural['valid_alternatives']} valid alternatives accepted; "
                f"{structural['rejects_rejected']} rejects structurally rejected; "
                f"{structural['rejects_missed']} missed"
            ),
            (
                "Linguistic: "
                f"{linguistic['rejects_rejected']} rejects rejected by "
                f"{linguistic['validator']}"
            ),
            f"Thresholds met: {report['thresholds_met']}",
        )
    )


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
        evidence = _evidence(args.evidence)
        return {
            "language": pack.language.code,
            "register_id": pack.language_register.register_id,
            "levels": {
                level: mission_capability(
                    pack,
                    mission_template_key(args.mission, level),
                    evaluation_record=evidence,
                ).model_dump(mode="json", by_alias=False)
                # Only the levels the mission has templates for (M05 A0/A1, M06 A2).
                for level in ("A0", "A1", "A2")
                if any(item.key[:2] == (args.mission, level)
                       for item in load_mission_catalog().missions)
            },
        }

    if args.command == "evaluate":
        vocabulary_path = args.vocabulary
        vocabulary = ApprovedVocabulary.model_validate(_read_json(vocabulary_path))
        report, record = evaluate_pack(pack, args.level, vocabulary, mission_id=args.mission)
        return {
            "table": _evaluation_table(report),
            "report": report,
            "evaluation_record": record.model_dump(mode="json", by_alias=False),
        }

    if args.command == "generate":
        scene = _read_json(args.scene)
        vocabulary = ApprovedVocabulary.model_validate(_read_json(args.vocabulary))
        facts = BoundSceneFacts.model_validate(scene["facts"])
        if args.source == "model":
            source = _text_model_source()
        else:
            if args.responses is None:
                raise ValueError("--responses is required when --source=responses")
            source = ModelSource(
                _ScriptedTextClient(_read_json(args.responses)),
                TextModelConfig(model_name="scripted-non-live"),
                mode="scripted responses (not a live model)",
                propose=False,
            )
        generated = generate_pilot(
            pack,
            args.level,
            facts,
            vocabulary,
            source,
            plan_specs=scene.get("plan_specs", {}).get(args.level),
            builder_selection=scene.get("builder_selection"),
            preview=args.preview,
            mission_id=args.mission,
        )
        evidence = _evidence(args.evidence)
        tasks = [task.model_dump(mode="json", by_alias=True) for task in generated.tasks]
        output = {
            "source": getattr(source, "mode", "scripted responses (not a live model)"),
            "result": generated.result.model_dump(mode="json", by_alias=True),
            # M06 builds its order as two tasks; other missions build one.
            "task": tasks[0] if len(tasks) == 1 else tasks,
            "payload": generated.payload,
            "sentences": [
                item.model_dump(mode="json", by_alias=False) for item in generated.sentences
            ],
            "assurance": generated.assurance,
            "assurance_scope": generated.assurance_scope,
            "mode": generated.mode,
            "fingerprint": generated.fingerprint,
        }
        if evidence is not None:
            output["capability"] = mission_capability(
                pack,
                mission_template_key(args.mission, args.level),
                evaluation_record=evidence,
            ).model_dump(mode="json", by_alias=False)
        return output

    scene = _read_json(args.scene)
    key = (
        mission_template_key(getattr(args, "mission", "M01"), args.level)
        if args.command in {"plan", "assemble"} else None
    )
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
    facts = BoundSceneFacts.model_validate(scene.get("facts", {"scene_facts": {}}))
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
            (item for item in approval.approved if item.candidate == candidate),
            None,
        )
        failure = next(
            (item for item in approval.failures if item.candidate == candidate),
            None,
        )
        outcomes.append(
            {
                "slot_id": candidate.slot_id,
                "deterministic_report": report.model_dump(mode="json", by_alias=False),
                "assessment": assessment.model_dump(mode="json", by_alias=False),
                "approved_sentence": outcome.model_dump(mode="json", by_alias=False)
                if outcome
                else None,
                "failure": failure.model_dump(mode="json", by_alias=False) if failure else None,
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
    # Native-script JSON (for example Hangul) must not fail on a legacy console code page.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    if args.env_file is not None:
        from dotenv import load_dotenv

        load_dotenv(args.env_file)
    try:
        output = _run(args)
    except (LanguagePackError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 2
    if args.command == "evaluate":
        print(output["table"])
        print(json.dumps(output["evaluation_record"], ensure_ascii=False, indent=2))
    if args.command == "evaluate" and args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(
            json.dumps(output["evaluation_record"], ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return 0
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return int(args.command == "assemble" and bool(output.get("failures")))


if __name__ == "__main__":
    raise SystemExit(main())
