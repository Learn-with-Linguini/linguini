"""Aggregate result rows into one line per (call, candidate, settings).

    python -m evals.model_comparison.summarize --stage screen
    python -m evals.model_comparison.summarize --stage full --stage sweep

Writes ``results/summary_<stages>.csv`` and ``.json`` and prints a Markdown
table per call. Metric definitions live in the report and README.
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any

from .pricing import catalogue_id
from .providers import PRODUCTION_DEFAULTS, facts

RESULTS = Path(__file__).resolve().parent / "results"

# Calls per learning session, used for cost-per-session. One scene analysis,
# one translation and one lesson per session; the clue call runs once; the
# learner typically submits about three I-Spy descriptions.
CALLS_PER_SESSION = {
    "scene_analysis": 1, "translation": 1, "learning_tasks": 1,
    "ispy_clues": 1, "ispy_guess": 3,
}

HEADLINE = {
    "scene_analysis": ["anchor_recall", "supported_precision", "relation_recall",
                       "empty_as_required", "hallucinated_objects", "violations"],
    "translation": ["eu.noun_accuracy", "eu.article_accuracy", "eu.gender_accuracy",
                    "eu.relation_accuracy", "eu.clean", "cjk.term_accuracy",
                    "cjk.wrong_language"],
    "learning_tasks": ["validator_pass", "check_pass_rate", "judge.score",
                       "judge.wrong_answer_keys"],
    "ispy_clues": ["validator_pass", "name_leaks", "judge.solved_rate",
                   "judge.grounded_rate", "judge.language_score"],
    "ispy_guess": ["guess_correct", "ambiguity_correct", "evidence_recall",
                   "contradiction_correct", "feedback_is_english"],
}


def load_rows(stages: list[str]) -> list[dict[str, Any]]:
    rows = []
    for stage in stages:
        for path in sorted((RESULTS / stage).glob("*.jsonl")):
            rows += [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    return rows


def _flatten(row: dict[str, Any]) -> dict[str, float]:
    out: dict[str, float] = {}
    quality = row.get("quality") or {}
    prefix = ""
    if row["call"] == "translation":
        prefix = "cjk." if row.get("language") in ("ja", "ko") else "eu."
    for key, value in quality.items():
        if isinstance(value, dict):
            for sub, inner in value.items():
                if isinstance(inner, (bool, int, float)) and inner is not None:
                    out[f"{prefix}{key}.{sub}"] = float(inner)
        elif isinstance(value, (bool, int, float)) and value is not None:
            out[prefix + key] = float(value)
    return out


def _pct(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round(q * (len(ordered) - 1))))
    return ordered[index]


def aggregate(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for row in rows:
        groups[(row["call"], row["candidate"], row.get("overrides", "production"))].append(row)
    summaries = []
    for (call, cand, overrides), items in sorted(groups.items()):
        provider, model = cand.split(":", 1)
        latencies = [r["latency_ms"] for r in items if r.get("latency_ms") and not r.get("error")]
        costs = [r["cost_usd"] for r in items if r.get("cost_usd") is not None]
        outputs = [r["output_tokens"] for r in items if r.get("output_tokens")]
        speeds = [
            r["output_tokens"] / (r["latency_ms"] / 1000)
            for r in items if r.get("output_tokens") and r.get("latency_ms")
        ]
        # Consistency: spread of the ranking score across repeat runs of a case,
        # and how often repeat runs returned byte-identical output.
        by_case: dict[str, list[dict]] = defaultdict(list)
        for r in items:
            by_case[r["case_id"]].append(r)
        spreads, identical = [], []
        for case_rows in by_case.values():
            if len(case_rows) > 1:
                spreads.append(statistics.pstdev([r["primary"] for r in case_rows]))
                identical.append(float(len({r.get("raw_text") for r in case_rows}) == 1))
        metrics: dict[str, list[float]] = defaultdict(list)
        for r in items:
            for key, value in _flatten(r).items():
                metrics[key].append(value)
        fact = facts().get(catalogue_id(provider, model))
        summary = {
            "call": call, "candidate": cand, "provider": provider, "model": model,
            "settings": overrides,
            "is_production_default": PRODUCTION_DEFAULTS.get(call) == cand,
            "n": len(items), "cases": len(by_case),
            "runs": max(r.get("run", 0) for r in items) + 1,
            "quality": statistics.mean(r["primary"] for r in items),
            "accepted_by_app": statistics.mean(float(r["ok"]) for r in items),
            "api_error_rate": statistics.mean(float(bool(r.get("error"))) for r in items),
            "rate_limit_retries_mean": _avg(items, "rate_limit_retries"),
            "run_to_run_spread": statistics.mean(spreads) if spreads else None,
            "identical_output_rate": statistics.mean(identical) if identical else None,
            "latency_mean_ms": statistics.mean(latencies) if latencies else None,
            "latency_p50_ms": _pct(latencies, 0.5),
            "latency_p95_ms": _pct(latencies, 0.95),
            "output_tokens_per_s": statistics.mean(speeds) if speeds else None,
            "input_tokens_mean": _avg(items, "input_tokens"),
            "output_tokens_mean": _avg(items, "output_tokens"),
            "reasoning_tokens_mean": _avg(items, "reasoning_tokens"),
            "output_tokens_max": max(outputs) if outputs else None,
            "cost_per_call_usd": statistics.mean(costs) if costs else None,
            "cost_per_1k_sessions_usd": (
                statistics.mean(costs) * CALLS_PER_SESSION[call] * 1000 if costs else None
            ),
            "input_price_per_mtok": fact.input_per_mtok if fact else None,
            "output_price_per_mtok": fact.output_per_mtok if fact else None,
            "context_window": fact.context_length if fact else None,
            "max_output_tokens": fact.max_output_tokens if fact else None,
            "vision": fact.vision if fact else None,
            "supports_temperature": fact.temperature if fact else None,
            "reasoning_model": fact.reasoning if fact else None,
        }
        for key, values in sorted(metrics.items()):
            summary[f"m.{key}"] = statistics.mean(values)
        summaries.append(summary)
    return summaries


def _avg(items: list[dict], key: str) -> float | None:
    values = [r[key] for r in items if r.get(key) is not None]
    return statistics.mean(values) if values else None


def _fmt(value: Any, digits: int = 2) -> str:
    if value is None:
        return "–"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def markdown(summaries: list[dict[str, Any]]) -> str:
    lines = []
    for call in HEADLINE:
        rows = sorted((s for s in summaries if s["call"] == call),
                      key=lambda s: -s["quality"])
        if not rows:
            continue
        cols = ["quality", "accepted_by_app", *(f"m.{m}" for m in HEADLINE[call]),
                "latency_p50_ms", "latency_p95_ms", "cost_per_1k_sessions_usd"]
        lines.append(f"\n### {call}\n")
        lines.append("| candidate | settings | n | " + " | ".join(cols) + " |")
        lines.append("|---|---|---|" + "---|" * len(cols))
        for s in rows:
            mark = " *(current)*" if s["is_production_default"] else ""
            values = [
                _fmt(s.get(c), 0 if "latency" in c else (3 if "cost" in c else 2))
                for c in cols
            ]
            lines.append(f"| {s['candidate']}{mark} | {s['settings']} | {s['n']} | "
                         + " | ".join(values) + " |")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", action="append", required=True)
    args = parser.parse_args(argv)
    summaries = aggregate(load_rows(args.stage))
    name = "_".join(args.stage)
    keys = sorted({k for s in summaries for k in s}, key=lambda k: (k.startswith("m."), k))
    with (RESULTS / f"summary_{name}.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=keys)
        writer.writeheader()
        writer.writerows(summaries)
    (RESULTS / f"summary_{name}.json").write_text(
        json.dumps(summaries, indent=1, default=str) + "\n", encoding="utf-8"
    )
    print(markdown(summaries))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
