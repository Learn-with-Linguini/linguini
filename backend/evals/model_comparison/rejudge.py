"""Add LLM-judge verdicts to saved rows that lack them, and re-score CJK rows.

    python -m evals.model_comparison.rejudge results/screen/*.jsonl --judge-runs 1

Judging is separate from generation so outputs can be produced first and
judged later (for example when the judge's provider was unavailable), without
paying for generation twice. Rows are rewritten in place.
"""

from __future__ import annotations

import argparse
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import calls
from .run import Ledger, load_env


def _rejudge(row: dict, ledger: Ledger) -> dict:
    if row["call"] == "translation" and row["language"] in ("ja", "ko"):
        case = next(c for c in calls.load_cases("translation") if c.case_id == row["case_id"])
        row["quality"] = calls._score_cjk(case, row.get("raw_text"))
        row["primary"] = row["quality"].get("term_accuracy") or 0.0
        return row
    if row["call"] not in calls.JUDGED or not row.get("raw_text"):
        return row
    scene = calls.scenes()[row["case_id"]]
    if row["call"] == "learning_tasks":
        # Re-score from the returned lesson, which may predate lenient scoring.
        payload, lesson = calls.rebuild_lesson(scene, row["raw_text"])
        if lesson is not None:
            checks = calls._lesson_checks(payload, lesson)
            row["quality"]["checks"] = checks
            row["quality"]["check_pass_rate"] = sum(checks.values()) / len(checks)
            row["quality"]["questions"] = sum(
                len(t.get("questions", [])) for t in lesson["tasks"]
            )
            row["quality"]["tasks"] = len(lesson["tasks"])
            row["primary"] = calls.lesson_primary(row["quality"])
    if row["quality"].get("judge") or not ledger.reserve(0.02):
        return row
    cost = None
    try:
        if row["call"] == "learning_tasks":
            payload, lesson = calls.rebuild_lesson(scene, row["raw_text"])
            if lesson is None:
                return row
            cost = calls.judge_lesson(row["quality"], payload, lesson)
            row["primary"] = calls.lesson_primary(row["quality"])
        else:
            from app.ai.features.ispy_clues import ISpyClueResult

            payload = calls.clue_payload(scene)
            try:
                result = ISpyClueResult.model_validate_json(row["raw_text"])
            except Exception:  # noqa: BLE001 - output the app rejected outright
                return row
            names = {o["key"]: o["translation"].casefold() for o in payload["objects"]}
            row["quality"]["answers"] = [c.answer_object_key for c in result.clues]
            row["quality"]["leaked"] = [
                c.answer_object_key for c in result.clues
                if names[c.answer_object_key] in c.clue.casefold()
            ]
            cost = calls.judge_clues(row["quality"], payload, result)
            row["primary"] = calls.clue_primary(row["quality"])
    finally:
        ledger.settle(0.02, row["call"], "judge", cost or 0.0)
    row["judge_cost_usd"] = cost
    return row


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", type=Path)
    parser.add_argument("--judge-runs", type=int, default=1)
    parser.add_argument("--budget", type=float, default=6.5)
    args = parser.parse_args(argv)
    load_env()
    ledger = Ledger(args.budget)
    for path in args.paths:
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        todo = [r for r in rows if r.get("run", 0) < args.judge_runs]
        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(lambda r: _rejudge(r, ledger), todo))
        path.write_text(
            "".join(json.dumps(r, ensure_ascii=False, default=str) + "\n" for r in rows),
            encoding="utf-8",
        )
        judged = sum(1 for r in rows if r["quality"].get("judge"))
        print(f"{path.name}: {judged} judged rows; spend ${ledger.data['total']:.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
