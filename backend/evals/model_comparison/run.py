"""Run the model comparison.

    python -m evals.model_comparison.run --stage screen --dry-run
    python -m evals.model_comparison.run --stage screen
    python -m evals.model_comparison.run --stage full --calls translation \\
        --models openai:gpt-4.1-mini gemini:gemini-3.5-flash-lite ...
    python -m evals.model_comparison.run --stage sweep --calls translation \\
        --models openai:gpt-4.1-mini --grid temperature=0,0.3,0.7

Keys are read from ``backend/.env.local``. Every provider call is costed and
added to ``results/spend.json``; a job is skipped, not sent, once the running
total plus its estimate would pass ``--budget``.
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import replace
from pathlib import Path
from typing import Any

from . import calls
from .providers import CALLS, CANDIDATES, Candidate, facts
from .recording import Overrides

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results"
LEDGER = RESULTS / "spend.json"

# Screening subsets: cover each call's hardest behaviours at low cost.
SCREEN = {
    "scene_analysis": ["classroom-clean", "grocery-clean", "classroom-low-light",
                       "grocery-blur-heavy", "classroom-unusable"],
    "translation": ["classroom-es", "grocery-fr", "gender-trap-es", "elision-fr",
                    "classroom-ja", "grocery-ko"],
    "learning_tasks": ["study-es", "classroom-fr"],
    "ispy_clues": ["study-es", "market-fr", "room-ja", "park-ko"],
    "ispy_guess": ["study-es-clear-book", "study-es-direction", "study-es-contradiction",
                   "kitchen-es-vague", "classroom-fr-offtopic", "market-fr-near-basket",
                   "room-ja-book", "park-ko-bicycle"],
}
# Typical (input, output) tokens per call, for estimates before any data exists.
PRIOR_TOKENS = {
    "scene_analysis": (2500, 1200), "translation": (900, 700),
    "learning_tasks": (3500, 3000), "ispy_clues": (1500, 400), "ispy_guess": (1500, 300),
}
JUDGE_ESTIMATE = {"learning_tasks": 0.02, "ispy_clues": 0.008}


class Ledger:
    def __init__(self, cap: float) -> None:
        self.cap = cap
        self.lock = threading.Lock()
        self.data = (
            json.loads(LEDGER.read_text(encoding="utf-8")) if LEDGER.exists()
            else {"total": 0.0, "by_call": {}, "by_model": {}}
        )

    def reserve(self, estimate: float) -> bool:
        with self.lock:
            if self.data["total"] + self.data.get("_pending", 0) + estimate > self.cap:
                return False
            self.data["_pending"] = self.data.get("_pending", 0) + estimate
            return True

    def settle(self, estimate: float, call: str, model: str, actual: float) -> None:
        with self.lock:
            self.data["_pending"] = max(0.0, self.data.get("_pending", 0) - estimate)
            self.data["total"] += actual
            self.data["by_call"][call] = self.data["by_call"].get(call, 0) + actual
            self.data["by_model"][model] = self.data["by_model"].get(model, 0) + actual
            self.save()

    def save(self) -> None:
        RESULTS.mkdir(parents=True, exist_ok=True)
        out = {k: v for k, v in self.data.items() if not k.startswith("_")}
        LEDGER.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")


def estimate(call: str, cand: Candidate, judged: bool) -> float:
    fact = facts()[cand.catalogue_id]
    tokens_in, tokens_out = PRIOR_TOKENS[call]
    if fact.reasoning:
        tokens_out *= 2  # thinking tokens are billed as output
    if call == "scene_analysis" and cand.model.startswith("gpt-4o-mini"):
        tokens_in *= 10  # 4o-mini bills images at an inflated token rate
    cost = fact.cost(tokens_in, tokens_out)
    return cost + (JUDGE_ESTIMATE.get(call, 0) if judged else 0)


def load_env() -> None:
    import os

    from dotenv import dotenv_values

    for key, value in dotenv_values(HERE.parent.parent / ".env.local").items():
        if value and key not in os.environ:
            os.environ[key] = value
    try:  # antivirus TLS inspection: trust the OS certificate store
        import truststore

        truststore.inject_into_ssl()
    except ImportError:
        pass


def parse_grid(specs: list[str]) -> list[Overrides]:
    grid = [Overrides()]
    for spec in specs:
        name, values = spec.split("=", 1)
        expanded = []
        for base in grid:
            for raw in values.split(","):
                value: Any = raw
                if name == "temperature":
                    value = float(raw)
                elif name == "max_output_tokens":
                    value = int(raw)
                else:
                    raise SystemExit(f"unknown sweep parameter {name!r}")
                expanded.append(replace(base, **{name: value}))
        grid = expanded
    return grid


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("screen", "full", "sweep"), required=True)
    parser.add_argument("--calls", nargs="+", default=list(CALLS))
    parser.add_argument("--models", nargs="+", default=None,
                        help="provider:model specs; default = all candidates for the call")
    parser.add_argument("--providers", nargs="+", default=None,
                        choices=("openai", "gemini", "openrouter"))
    parser.add_argument("--cases", nargs="+", default=None)
    parser.add_argument("--runs", type=int, default=None)
    parser.add_argument("--grid", nargs="+", default=[],
                        help="sweep: name=v1,v2 for temperature or max_output_tokens")
    parser.add_argument("--judge-runs", type=int, default=1,
                        help="how many repeat runs per case get an LLM-judge verdict")
    parser.add_argument("--budget", type=float, default=6.5)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--tag", default=None, help="output file suffix")
    args = parser.parse_args(argv)

    load_env()
    runs = args.runs or {"screen": 1, "full": 3, "sweep": 2}[args.stage]
    grid = [Overrides()]  # production settings are always the baseline
    if args.stage == "sweep":
        grid += [o for o in parse_grid(args.grid) if o != Overrides()]
    ledger = Ledger(args.budget)

    jobs = []
    for call in args.calls:
        cases = calls.load_cases(call)
        wanted = args.cases or (SCREEN[call] if args.stage == "screen" else None)
        if wanted:
            cases = [c for c in cases if calls.case_id(c) in wanted]
        cands = (
            [Candidate(*m.split(":", 1)) for m in args.models] if args.models
            else CANDIDATES[call]
        )
        if args.providers:
            cands = [c for c in cands if c.provider in args.providers]
        for cand in cands:
            if cand.catalogue_id not in facts():
                print(f"skip {cand}: not in pricing snapshot", file=sys.stderr)
                continue
            if call == "scene_analysis" and not facts()[cand.catalogue_id].vision:
                continue
            if call == "ispy_guess" and cand.provider == "gemini":
                # That adapter speaks the OpenAI SDK; Gemini models are
                # reached through OpenRouter instead.
                print(f"skip {cand} for ispy_guess: use openrouter:google/*", file=sys.stderr)
                continue
            for overrides in grid:
                for run in range(runs):
                    for case in cases:
                        judged = call in calls.JUDGED and run < args.judge_runs
                        jobs.append((call, cand, overrides, case, run, judged))

    total_estimate = sum(estimate(c, cand, j) for c, cand, _, _, _, j in jobs)
    print(f"{len(jobs)} calls planned, estimated ${total_estimate:.2f}; "
          f"spent so far ${ledger.data['total']:.2f} of ${args.budget:.2f}")
    if args.dry_run:
        by: dict[str, float] = {}
        for c, cand, _, _, _, j in jobs:
            by[f"{c} {cand}"] = by.get(f"{c} {cand}", 0) + estimate(c, cand, j)
        for key, value in sorted(by.items()):
            print(f"  ${value:7.4f}  {key}")
        return 0

    stamp = time.strftime("%Y%m%d-%H%M%S")
    out_dir = RESULTS / args.stage
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{args.tag or stamp}.jsonl"
    write_lock = threading.Lock()
    done = skipped = failed = 0

    def execute(job):
        call, cand, overrides, case, run, judged = job
        est = estimate(call, cand, judged)
        if not ledger.reserve(est):
            return None, est
        try:
            runner = calls.RUNNERS[call]
            row = (runner(cand, overrides, case, judged) if call in calls.JUDGED
                   else runner(cand, overrides, case))
        except Exception as exc:  # noqa: BLE001 - harness bug: record, keep going
            row = {"ok": False, "adapter_error": f"harness: {type(exc).__name__}: {exc}",
                   "primary": 0.0, "quality": {}}
        actual = (row.get("cost_usd") or 0) + (row.get("judge_cost_usd") or 0)
        ledger.settle(est, call, str(cand), actual)
        row.update(
            call=call, provider=cand.provider, model=cand.model, candidate=str(cand),
            overrides=overrides.label(), case_id=calls.case_id(case),
            language=calls.case_language(call, case), run=run, stage=args.stage,
        )
        return row, est

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(execute, job) for job in jobs]
        for index, future in enumerate(as_completed(futures), start=1):
            row, _ = future.result()
            if row is None:
                skipped += 1
                continue
            done += 1
            failed += not row["ok"]
            with write_lock, out_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
            if index % 10 == 0 or index == len(futures):
                print(f"[{index}/{len(futures)}] spent ${ledger.data['total']:.3f} "
                      f"failed={failed} skipped={skipped}", flush=True)

    print(f"done={done} failed={failed} skipped_for_budget={skipped} -> {out_path}")
    print(f"total spend ${ledger.data['total']:.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
