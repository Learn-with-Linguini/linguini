"""Render MODEL_COMPARISON.md from the recorded results.

    python -m evals.model_comparison.report --out ../MODEL_COMPARISON.md

Every table is generated from ``results/*.jsonl``, so the document can be
rebuilt whenever a stage is re-run. The narrative around the tables lives in
``narrative.py`` beside this file.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path
from typing import Any

from .providers import CALLS
from .summarize import CALLS_PER_SESSION, aggregate, load_rows

RESULTS = Path(__file__).resolve().parent / "results"

CALL_TITLES = {
    "scene_analysis": "1. Scene analysis (vision)",
    "translation": "2. Scene translation",
    "learning_tasks": "3. Grammar learning tasks",
    "ispy_clues": "4. I-Spy clue generation",
    "ispy_guess": "5. I-Spy guess and feedback",
}

# Per-call quality columns, as (heading, summary key, decimals).
QUALITY_COLUMNS: dict[str, list[tuple[str, str, int]]] = {
    "scene_analysis": [
        ("Anchor recall", "m.anchor_recall", 2),
        ("Supported precision", "m.supported_precision", 2),
        ("Relation recall", "m.relation_recall", 2),
        ("Refused unusable photo", "m.empty_as_required", 2),
        ("Hallucinated objects", "m.hallucinated_objects", 2),
        ("Rule violations", "m.violations", 2),
    ],
    "translation": [
        ("Noun accuracy (es/fr)", "m.eu.noun_accuracy", 2),
        ("Article accuracy", "m.eu.article_accuracy", 2),
        ("Gender accuracy", "m.eu.gender_accuracy", 2),
        ("Relation accuracy", "m.eu.relation_accuracy", 2),
        ("Fully clean cases", "m.eu.clean", 2),
        ("Term accuracy (ja/ko)", "m.cjk.term_accuracy", 2),
        ("Wrong language (ja/ko)", "m.cjk.wrong_language", 2),
    ],
    "learning_tasks": [
        ("Accepted by validator", "m.validator_pass", 2),
        ("Automatic checks passed", "m.check_pass_rate", 2),
        ("Judge score (1-5)", "m.judge.score", 2),
        ("Wrong answer keys", "m.judge.wrong_answer_keys", 2),
        ("Ambiguous questions", "m.judge.ambiguous_questions", 2),
    ],
    "ispy_clues": [
        ("Accepted by validator", "m.validator_pass", 2),
        ("Answer word leaked", "m.name_leaks", 2),
        ("Judge solved the clue", "m.judge.solved_rate", 2),
        ("Grounded in scene facts", "m.judge.grounded_rate", 2),
        ("Language score (1-5)", "m.judge.language_score", 2),
    ],
    "ispy_guess": [
        ("Correct guess", "m.guess_correct", 2),
        ("Ambiguity flagged right", "m.ambiguity_correct", 2),
        ("Evidence recall", "m.evidence_recall", 2),
        ("Contradiction spotted", "m.contradiction_correct", 2),
        ("Feedback in English", "m.feedback_is_english", 2),
    ],
}

COST_COLUMNS = [
    ("Latency p50 (s)", "latency_p50_ms", 1),
    ("Latency p95 (s)", "latency_p95_ms", 1),
    ("Input tokens", "input_tokens_mean", 0),
    ("Output tokens", "output_tokens_mean", 0),
    ("Cost / call ($)", "cost_per_call_usd", 5),
    ("Cost / 1k sessions ($)", "cost_per_1k_sessions_usd", 2),
]

RELIABILITY_COLUMNS = [
    ("Output usable by app", "accepted_by_app", 2),
    ("API errors", "api_error_rate", 2),
    ("Run-to-run spread", "run_to_run_spread", 3),
    ("Identical repeat runs", "identical_output_rate", 2),
    ("Rate-limit retries", "rate_limit_retries_mean", 2),
]

CAPABILITY_COLUMNS = [
    ("Input $/Mtok", "input_price_per_mtok", 2),
    ("Output $/Mtok", "output_price_per_mtok", 2),
    ("Context window", "context_window", 0),
    ("Max output tokens", "max_output_tokens", 0),
    ("Vision", "vision", 0),
    ("Temperature", "supports_temperature", 0),
    ("Reasoning model", "reasoning_model", 0),
]


def fmt(value: Any, digits: int) -> str:
    if value is None:
        return "–"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, (int, float)):
        return f"{value:,.{digits}f}" if digits else f"{round(value):,}"
    return str(value)


def table(rows: list[dict], columns: list[tuple[str, str, int]], label: str) -> str:
    head = f"| {label} | " + " | ".join(c[0] for c in columns) + " |"
    rule = "|---" * (len(columns) + 1) + "|"
    lines = [head, rule]
    for row in rows:
        name = row["candidate"]
        if row["is_production_default"]:
            name += " **(current default)**"
        if row.get("settings") and row["settings"] != "production":
            name += f" [{row['settings']}]"
        values = []
        for _, key, digits in columns:
            value = row.get(key)
            if "latency" in key and value is not None:
                value = value / 1000
            values.append(fmt(value, digits))
        lines.append(f"| {name} | " + " | ".join(values) + " |")
    return "\n".join(lines)


def scaled(rows: list[dict]) -> list[dict]:
    return sorted(rows, key=lambda r: (-r["quality"], r.get("cost_per_call_usd") or 0))


def call_section(call: str, rows: list[dict], stage_note: str) -> str:
    rows = scaled([r for r in rows if r["call"] == call])
    if not rows:
        return ""
    cases = max(r["cases"] for r in rows)
    runs = max(r["runs"] for r in rows)
    parts = [
        f"## {CALL_TITLES[call]}",
        "",
        f"{stage_note} {cases} cases, up to {runs} run(s) per case. "
        f"Cost per 1,000 sessions assumes {CALLS_PER_SESSION[call]} call(s) per session.",
        "",
        "### Quality",
        "",
        table(rows, [("Overall", "quality", 2), *QUALITY_COLUMNS[call]], "Model"),
        "",
        "### Reliability",
        "",
        table(rows, RELIABILITY_COLUMNS, "Model"),
        "",
        "### Speed, tokens and cost",
        "",
        table(rows, COST_COLUMNS, "Model"),
        "",
    ]
    return "\n".join(parts)


def capability_section(rows: list[dict]) -> str:
    seen: dict[str, dict] = {}
    for row in rows:
        seen.setdefault(row["candidate"], row)
    ordered = sorted(seen.values(), key=lambda r: r["candidate"])
    return "\n".join([
        "## Model facts (from the OpenRouter catalogue snapshot)",
        "",
        table(ordered, CAPABILITY_COLUMNS, "Model"),
        "",
    ])


def spend(rows_raw: list[dict]) -> tuple[float, int]:
    total = sum(
        (row.get("cost_usd") or 0) + (row.get("judge_cost_usd") or 0) for row in rows_raw
    )
    return total, len(rows_raw)


def failure_section(rows_raw: list[dict]) -> str:
    counts: dict[tuple[str, str, str], int] = defaultdict(int)
    for row in rows_raw:
        code = row.get("error_code") or (
            "validator rejected" if not row.get("ok") and row.get("adapter_error") else None
        )
        if code:
            counts[(row["call"], row["candidate"], code)] += 1
    if not counts:
        return ""
    lines = ["## Failures by cause", "", "| Call | Model | Cause | Calls |", "|---|---|---|---|"]
    for (call, cand, code), count in sorted(counts.items(), key=lambda kv: -kv[1]):
        lines += [f"| {call} | {cand} | {code} | {count} |"]
    return "\n".join(lines) + "\n"


def build(stages: list[str]) -> str:
    from .narrative import (
        FOOTER,
        HEADER,
        METHOD,
        PARAMETERS,
        PER_CALL_NOTES,
        RECOMMENDATIONS,
    )

    rows_raw = load_rows(stages)
    summaries = aggregate(rows_raw)
    total, calls_made = spend(rows_raw)
    parts = [
        HEADER,
        METHOD,
        PARAMETERS,
        RECOMMENDATIONS,
    ]
    for call in CALLS:
        section = call_section(call, summaries, PER_CALL_NOTES.get(call, ""))
        if section:
            parts.append(section)
    parts += [
        capability_section(summaries),
        failure_section(rows_raw),
        f"## Spend\n\n{calls_made:,} provider calls, ${total:,.2f} total.\n",
        FOOTER,
    ]
    return "\n".join(parts)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", action="append", default=None)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    stages = args.stage or [p.name for p in sorted(RESULTS.iterdir()) if p.is_dir()]
    args.out.write_text(build(stages), encoding="utf-8")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
