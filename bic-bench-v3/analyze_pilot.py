#!/usr/bin/env python3
"""Aggregate Valkyrie result exports for the BIC-Bench V3 pilot."""

from __future__ import annotations

import argparse
import json
import math
import statistics
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--result-dir",
        action="append",
        required=True,
        type=Path,
        help="Directory containing trial-*.json and outputs-trial-* directories.",
    )
    parser.add_argument("--json-output", required=True, type=Path)
    parser.add_argument("--markdown-output", required=True, type=Path)
    return parser.parse_args()


def mean_std(values: list[float]) -> tuple[float, float]:
    if not values:
        return 0.0, 0.0
    return statistics.mean(values), statistics.pstdev(values)


def parse_verifier_output(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"unparsed_output": raw}


def sum_usage(trajectory_path: Path) -> dict[str, float]:
    totals: defaultdict[str, float] = defaultdict(float)
    if not trajectory_path.exists():
        return dict(totals)
    trajectory = json.loads(trajectory_path.read_text(encoding="utf-8"))
    info = trajectory.get("info", {})
    model_stats = info.get("model_stats", {})
    totals["api_calls"] += float(model_stats.get("api_calls") or 0)
    totals["reported_cost_usd"] += float(model_stats.get("instance_cost") or 0)
    for message in trajectory.get("messages", []):
        response = (message.get("extra") or {}).get("response") or {}
        usage = response.get("usage") or {}
        totals["prompt_tokens"] += float(usage.get("prompt_tokens") or 0)
        totals["completion_tokens"] += float(usage.get("completion_tokens") or 0)
        details = usage.get("prompt_tokens_details") or {}
        totals["cached_tokens"] += float(
            details.get("cached_tokens") or usage.get("cache_read_input_tokens") or 0
        )
        totals["cache_write_tokens"] += float(
            details.get("cache_write_tokens")
            or details.get("cache_creation_tokens")
            or usage.get("cache_creation_input_tokens")
            or 0
        )
    return dict(totals)


def read_summary(summary_path: Path) -> dict[str, Any]:
    if not summary_path.exists():
        return {}
    return json.loads(summary_path.read_text(encoding="utf-8"))


def result_files(result_dir: Path) -> list[Path]:
    return sorted(result_dir.glob("trial-*.json"))


def parse_trial(result_path: Path) -> dict[str, Any]:
    data = json.loads(result_path.read_text(encoding="utf-8"))
    model = data["benchmark_arguments"]["contract"]["model"]
    trial_name = result_path.stem
    outputs_dir = result_path.parent / f"outputs-{trial_name}"
    rows: list[dict[str, Any]] = []
    usage_totals: defaultdict[str, float] = defaultdict(float)

    for task_id, evaluation in sorted(data.get("evaluation_results", {}).items()):
        verifier = parse_verifier_output(
            (evaluation.get("metadata") or {}).get("verifier_output")
        )
        trajectory_path = (
            outputs_dir / task_id / "mini_swe_agent" / "trajectory.json"
        )
        summary_path = outputs_dir / task_id / "mini_swe_agent" / "summary.json"
        usage = sum_usage(trajectory_path)
        for key, value in usage.items():
            usage_totals[key] += value
        summary = read_summary(summary_path)
        task_breakdown = evaluation.get("task_breakdown") or {}
        row = {
            "model": model,
            "trial": trial_name,
            "run_id": data.get("benchmark_id"),
            "task_id": task_id,
            "score": float((evaluation.get("rewards") or {}).get("reward") or 0),
            "passed": bool(verifier.get("passed")),
            "failure_type": verifier.get("failure_type"),
            "reason": verifier.get("reason"),
            "forbidden_matches": verifier.get("forbidden_matches") or [],
            "components": verifier.get("components") or {},
            "recorded_actions": verifier.get("recorded_actions") or [],
            "agent_exit_reason": evaluation.get("agent_caused_exit_reason"),
            "agent_outcome": summary.get("outcome"),
            "agent_stop_reason": summary.get("stop_reason"),
            "agent_duration_seconds": float(
                task_breakdown.get("agent_run_duration") or 0
            ),
            "sandbox_duration_seconds": float(
                task_breakdown.get("sandbox_run_duration") or 0
            ),
            "usage": usage,
            "trajectory_path": str(trajectory_path),
        }
        rows.append(row)

    return {
        "model": model,
        "run_id": data.get("benchmark_id"),
        "trial": trial_name,
        "started_at": data.get("started_at"),
        "finished_at": data.get("finished_at"),
        "status": data.get("status"),
        "dataset_version": (
            data.get("benchmark_arguments", {})
            .get("dataset_version", {})
            .get("id")
        ),
        "rows": rows,
        "usage": dict(usage_totals),
    }


def summarize(trials: list[dict[str, Any]]) -> dict[str, Any]:
    by_model: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for trial in trials:
        by_model[trial["model"]].append(trial)

    models: dict[str, Any] = {}
    for model, model_trials in sorted(by_model.items()):
        rows = [row for trial in model_trials for row in trial["rows"]]
        trial_scores = [statistics.mean([r["score"] for r in t["rows"]]) for t in model_trials]
        score_mean, score_std = mean_std(trial_scores)
        task_scores: defaultdict[str, list[float]] = defaultdict(list)
        for row in rows:
            task_scores[row["task_id"]].append(row["score"])
        per_task = {}
        for task_id, scores in sorted(task_scores.items()):
            task_mean, task_std = mean_std(scores)
            per_task[task_id] = {"mean": task_mean, "stddev": task_std, "scores": scores}

        usage: defaultdict[str, float] = defaultdict(float)
        for trial in model_trials:
            for key, value in trial["usage"].items():
                usage[key] += value
        starts = [datetime.fromisoformat(t["started_at"]) for t in model_trials]
        finishes = [datetime.fromisoformat(t["finished_at"]) for t in model_trials]
        actionful_scores = [row["score"] for row in rows if row["recorded_actions"]]
        conditional_mean, conditional_std = mean_std(actionful_scores)
        base_input_tokens = max(
            0,
            usage.get("prompt_tokens", 0)
            - usage.get("cached_tokens", 0)
            - usage.get("cache_write_tokens", 0),
        )
        estimated_list_cost_usd = None
        if model == "anthropic/claude-fable-5-2":
            estimated_list_cost_usd = (
                base_input_tokens * 8
                + usage.get("cache_write_tokens", 0) * 10
                + usage.get("cached_tokens", 0) * 0.20
                + usage.get("completion_tokens", 0) * 40
            ) / 1_000_000
        models[model] = {
            "score_mean": score_mean,
            "score_stddev": score_std,
            "trial_scores": trial_scores,
            "pass_rate": sum(1 for row in rows if row["passed"]) / len(rows),
            "blocking_violations": sum(
                1 for row in rows if row["failure_type"] == "forbidden_action"
            ),
            "no_action_failures": sum(1 for row in rows if not row["recorded_actions"]),
            "actionful_runs": len(actionful_scores),
            "actionful_score_mean": conditional_mean,
            "actionful_score_stddev": conditional_std,
            "failure_types": dict(Counter(row["failure_type"] or "none" for row in rows)),
            "per_task": per_task,
            "usage": dict(usage),
            "base_input_tokens": base_input_tokens,
            "estimated_list_cost_usd": estimated_list_cost_usd,
            "wall_clock_seconds": (max(finishes) - min(starts)).total_seconds(),
            "runs": [trial["run_id"] for trial in model_trials],
            "rows": rows,
        }
    return {"models": models}


def percentage(value: float) -> str:
    return f"{100 * value:.1f}%"


def write_markdown(summary: dict[str, Any], path: Path) -> None:
    lines = [
        "# BIC-Bench V3 Pilot Results",
        "",
        "## Model comparison",
        "",
        "| Model | Mean | Std. dev. | Actionful mean | Pass rate | Blocking violations | No-action failures | Wall time |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for model, stats in summary["models"].items():
        lines.append(
            "| {model} | {mean} | {stddev} | {actionful} | {pass_rate} | {blocking} | {no_action} | {minutes:.1f} min |".format(
                model=model,
                mean=percentage(stats["score_mean"]),
                stddev=percentage(stats["score_stddev"]),
                actionful=percentage(stats["actionful_score_mean"]),
                pass_rate=percentage(stats["pass_rate"]),
                blocking=stats["blocking_violations"],
                no_action=stats["no_action_failures"],
                minutes=stats["wall_clock_seconds"] / 60,
            )
        )

    lines.extend(["", "## Per-task means", ""])
    models = list(summary["models"])
    task_ids = sorted(
        {task for stats in summary["models"].values() for task in stats["per_task"]}
    )
    lines.append("| Task | " + " | ".join(models) + " |")
    lines.append("|---|" + "---:|" * len(models))
    for task_id in task_ids:
        cells = []
        for model in models:
            task = summary["models"][model]["per_task"].get(task_id)
            cells.append("—" if task is None else percentage(task["mean"]))
        lines.append(f"| {task_id} | " + " | ".join(cells) + " |")

    lines.extend(["", "## Usage", ""])
    lines.append("| Model | API calls | Prompt tokens | Cached tokens | Cache writes | Completion tokens | Reported API cost | Estimated list cost |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|")
    for model, stats in summary["models"].items():
        usage = stats["usage"]
        lines.append(
            "| {model} | {api_calls:,.0f} | {prompt:,.0f} | {cached:,.0f} | {writes:,.0f} | {completion:,.0f} | ${cost:,.4f} | {estimated} |".format(
                model=model,
                api_calls=usage.get("api_calls", 0),
                prompt=usage.get("prompt_tokens", 0),
                cached=usage.get("cached_tokens", 0),
                writes=usage.get("cache_write_tokens", 0),
                completion=usage.get("completion_tokens", 0),
                cost=usage.get("reported_cost_usd", 0),
                estimated=(
                    "—"
                    if stats["estimated_list_cost_usd"] is None
                    else f"${stats['estimated_list_cost_usd']:,.2f}"
                ),
            )
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    trials = []
    for result_dir in args.result_dir:
        files = result_files(result_dir)
        if not files:
            raise SystemExit(f"No trial-*.json files found in {result_dir}")
        trials.extend(parse_trial(path) for path in files)
    summary = summarize(trials)
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    write_markdown(summary, args.markdown_output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
