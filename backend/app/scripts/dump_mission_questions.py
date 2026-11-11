"""Dump French pack lessons without a database or pytest dependency."""

import argparse
import json
import os
from pathlib import Path
from unittest.mock import patch
from uuid import UUID

from app.ai.contracts.text import TextModelConfig
from app.ai.features.learning_tasks.mission import tokens
from app.language_packs.context import resolve_language_context
from app.language_packs.model_source import ModelSource
from app.language_packs.pipeline import generate_pilot
from app.language_packs.runtime import session_inputs
from app.missions import get_mission
from app.scripts.french_mission_mock import COUNTED, MockPackProvider, build_scene
from app.services.mission_eligibility import IMPLEMENTED_MISSIONS
from app.services.mission_roleplay import assign_roleplay

ROOT = Path(__file__).resolve().parents[3]
PACK = ROOT / "backend/app/language_packs/packs/fr-FR/everyday"
DEFAULT_OUTPUT = ROOT / "docs/french_mission_questions.md"
ITEMS = (("cup", "red"), ("book", "white"), ("table", "green"), ("coffee", "black"))
SESSION_ID = UUID(int=100)


def model_source(provider, context):
    if provider == "mock":
        return ModelSource(
            MockPackProvider("fr"),
            TextModelConfig(model_name="mocked-pack-provider"),
            propose=True,
            language_context=context,
        )
    from app.ai.observability import NoOpAITracer
    from app.ai.registry import build_routed_client
    from app.ai.settings import AiFeature, load_ai_settings

    client, config = build_routed_client(
        "text",
        load_ai_settings(),
        AiFeature.LEARNING_TASK,
        default_max_output_tokens=4000,
        tracer=NoOpAITracer(),
    )
    return ModelSource(client, config, propose=True, language_context=context)


def dump_questions(provider="mock"):
    report = {"provider": provider, "missions": []}
    env = {
        "APP_ENV": "test",
        "LINGUINI_LANGUAGE_PACK_EXPERIMENTAL": "true",
        "LINGUINI_LANGUAGE_PACK_DIRS": str(PACK),
    }
    with patch.dict(os.environ, env):
        context = resolve_language_context("fr")
        objects, relations, words, translated = build_scene("fr", ITEMS)
        markers = {str(obj.id): index for index, obj in enumerate(objects, 1)}
        by_label = {obj.label: str(obj.id) for obj in objects}
        counted = [
            dict(sceneObjectIds=[by_label[label]], quantity=quantity) for label, quantity in COUNTED
        ]
        for level, keys in IMPLEMENTED_MISSIONS.items():
            for mission_id, _, version in keys:
                mission = get_mission(mission_id, level, version)
                entry = dict(
                    level=level,
                    mission_id=mission_id,
                    version=version,
                    title=mission.title if mission else "Missing mission definition",
                    tasks=[],
                )
                report["missions"].append(entry)
                try:
                    if context is None or mission is None:
                        raise ValueError("French pack context or mission definition unavailable")
                    learner = None
                    roleplay = None
                    if mission_id in {"M04", "M05"}:
                        roleplay = assign_roleplay(mission, SESSION_ID, objects, markers)
                    if mission_id == "M05":
                        learner = {
                            "preference": {
                                "sceneObjectIds": [str(objects[0].id), str(objects[1].id)],
                                "chosenObjectId": str(objects[0].id),
                                "reaction": "like",
                            }
                        }
                    facts, vocabulary = session_inputs(
                        context.pack,
                        objects,
                        relations,
                        words,
                        translated,
                        markers,
                        counted,
                    )
                    generated = generate_pilot(
                        context.pack,
                        level,
                        facts,
                        vocabulary,
                        model_source(provider, context),
                        session_id=SESSION_ID,
                        preview=context.experimental,
                        cache_scope=None,
                        mission_id=mission_id,
                        mission_context={
                            "learner_facts": learner,
                            "roleplay_facts": roleplay,
                            "progress": {},
                        },
                    )
                    result = generated.result
                    raw_questions = (
                        result["questions"] if isinstance(result, dict) else result.questions
                    )
                    raw = {q.question_id: q for q in raw_questions}
                    for task in generated.tasks:
                        questions = []
                        for question in task.public_content.questions:
                            qid = question.question_id
                            original = raw[qid]
                            answers = task.answer_key
                            data = question.model_dump(
                                mode="json",
                                by_alias=False,
                                exclude_none=True,
                            )
                            data.update(
                                purpose=getattr(original, "purpose", None) or original.target_group,
                                correct_option_ids=[
                                    answers.correct_option_ids.get(qid),
                                    *answers.accepted_option_ids.get(qid, []),
                                ],
                                correct_chunks=list(
                                    getattr(original, "correct_chunks", None)
                                    or getattr(original, "answer_chunks", None)
                                    or (
                                        original.complete_chunk.split()
                                        if not hasattr(original, "correct_text")
                                        and original.complete_chunk
                                        else []
                                    )
                                    or [
                                        token
                                        for token in tokens(
                                            getattr(original, "correct_text", None) or ""
                                        )
                                        if token in question.token_bank
                                    ]
                                ),
                                accepted_text_answers=answers.accepted_text_answers_by_question.get(
                                    qid, []
                                ),
                            )
                            questions.append(data)
                        entry["tasks"].append(
                            dict(
                                title=task.public_content.title,
                                scenario=(
                                    task.public_content.scenario.model_dump(mode="json")
                                    if task.public_content.scenario
                                    else None
                                ),
                                questions=questions,
                            )
                        )
                except Exception as exc:
                    # Keep the rest of the catalogue useful even when a builder fails.
                    entry["error"] = f"{type(exc).__name__}: {exc}"
    return report


def literal(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def markdown(report):
    lines = [
        "# French mission questions",
        "",
        f"Provider: **{report['provider']}**. Pack: `fr-FR/everyday`.",
        "",
        "Mock-generated text is illustrative test data and may differ from production LLM "
        "output; it is not a linguistic review. Real-provider runs are not deterministic.",
        "",
        "Generated by `cd backend && .venv/bin/python -m app.scripts.dump_mission_questions`.",
        "The default mock run is deterministic, uses no API keys and makes no database calls.",
        "Coverage follows `IMPLEMENTED_MISSIONS`, not every template declared in missions.toml.",
        "This is every question in one fixed lesson per supported combination, not every "
        "possible scene, role-play or adaptive-history variant.",
        "",
        "Scene: marker 1 red cup (3 cups), marker 2 white book (5 books), marker 3 green "
        "table, marker 4 black coffee; cup on table. Fixed session UUID: "
        "`00000000-0000-0000-0000-000000000064`.",
        "M05 uses a learner's like choice for the cup; A1 ownership/preferences use assigned "
        "role-play. M06 uses empty prior progress (default reply mode).",
        "",
        "Correct options are marked **[correct]**. Marker options refer to the scene above.",
        "For A0 situation questions, purpose is the builder's target_group (that schema "
        "has no purpose field). Where builders store only correct_text, correct_chunks "
        "are its ordered answer tokens present in the public token bank.",
        "",
        "## Question counts",
        "",
        "| Level | Mission | Questions | Status |",
        "| --- | --- | ---: | --- |",
    ]
    for entry in report["missions"]:
        count = sum(len(t["questions"]) for t in entry["tasks"])
        lines.append(
            f"| {entry['level']} | {entry['mission_id']} | {count} | "
            f"{'error' if entry.get('error') else 'ok'} |"
        )
    level = None
    for entry in report["missions"]:
        if level != entry["level"]:
            level = entry["level"]
            lines.extend(["", f"## {level}"])
        lines.extend(
            [
                "",
                f"### {entry['mission_id']} — {entry['title']}",
                "",
                f"Content version: {entry['version']}.",
                "",
            ]
        )
        if entry.get("error"):
            lines.extend([f"Could not build: {entry['error']}", ""])
        for index, task in enumerate(entry["tasks"], 1):
            lines.extend([f"#### Task {index}: {task['title']}", ""])
            if task["scenario"]:
                lines.extend([f"Scenario: {literal(task['scenario'])}", ""])
            for q in task["questions"]:
                lines.extend(
                    [
                        f"##### {q['question_id']}",
                        "",
                        f"- purpose: `{q['purpose']}`",
                        f"- interaction_type: `{q['interaction_type']}`",
                        f"- prompt: {q['prompt']}",
                    ]
                )
                for field in (
                    "instruction",
                    "roleplay_premise",
                    "audio_text",
                    "dialogue",
                    "slot_template",
                    "complete_chunk",
                ):
                    if q.get(field):
                        lines.append(f"- {field}: {literal(q[field])}")
                for option in q["options"]:
                    mark = (
                        " **[correct]**" if option["option_id"] in q["correct_option_ids"] else ""
                    )
                    lines.append(f"- option `{option['option_id']}`: {option['label']}{mark}")
                if q["interaction_type"] == "sentenceBuilding":
                    lines.extend(
                        [
                            f"- token_bank: {literal(q['token_bank'])}",
                            f"- correct_chunks: {literal(q['correct_chunks'])}",
                        ]
                    )
                if not q["options"]:
                    lines.append(f"- correct answer: {literal(q['correct_option_ids'][0])}")
                if q["accepted_text_answers"]:
                    lines.append(f"- accepted_text_answers: {literal(q['accepted_text_answers'])}")
                lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", choices=("mock", "real"), default="mock")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--json", type=Path, help="Also write the structured report")
    args = parser.parse_args()
    report = dump_questions(args.provider)
    args.output.write_text(markdown(report), encoding="utf-8")
    if args.json:
        args.json.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    for entry in report["missions"]:
        count = sum(len(t["questions"]) for t in entry["tasks"])
        print(
            f"{entry['level']} {entry['mission_id']}: {count} questions"
            + (f" — {entry['error']}" if entry.get("error") else "")
        )
    print(f"Wrote {args.output}")
    return int(any(entry.get("error") for entry in report["missions"]))


if __name__ == "__main__":
    raise SystemExit(main())
