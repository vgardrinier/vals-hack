from __future__ import annotations

import json
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any


def build_summary(run: dict[str, Any]) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_trial: dict[int, list[float]] = defaultdict(list)
    for trial in run["trials"]:
        grouped[trial["case_id"]].append(trial)
        by_trial[int(trial["trial"])].append(float(trial["score"]["final_score"]))

    cases = []
    for case_id, trials in sorted(grouped.items()):
        scores = [float(item["score"]["final_score"]) for item in trials]
        cases.append(
            {
                "case_id": case_id,
                "industry": trials[0]["industry"],
                "difficulty": trials[0]["difficulty"],
                "category": trials[0]["category"],
                "trials": len(trials),
                "mean": round(statistics.mean(scores), 6),
                "stddev": round(statistics.pstdev(scores), 6),
                "hard_failure_rate": round(
                    sum(bool(item["score"]["hard_failure"]) for item in trials) / len(trials),
                    6,
                ),
                "deterministic_mean": round(
                    statistics.mean(
                        float(item["score"]["deterministic_completion"]) for item in trials
                    ),
                    6,
                ),
                "awareness_mean": round(
                    statistics.mean(
                        float(item["score"]["constraint_awareness"]) for item in trials
                    ),
                    6,
                ),
                "alternative_mean": round(
                    statistics.mean(
                        float(item["score"]["alternative_quality"]) for item in trials
                    ),
                    6,
                ),
            }
        )

    trial_means = [
        statistics.mean(scores)
        for _, scores in sorted(by_trial.items())
    ]
    agent_usage = _sum_usage(item.get("agent_usage", {}) for item in run["trials"])
    judge_usage = _sum_usage(
        item["score"].get("judge_usage", {}) for item in run["trials"]
    )
    return {
        "schema_version": "bic-summary-v2.0",
        "run_id": run["run_id"],
        "agent": run["agent"],
        "judge": run["judge"],
        "case_count": run["case_count"],
        "trials_per_case": run["config"]["trials"],
        "overall_mean": round(statistics.mean(trial_means), 6),
        "overall_stddev": round(statistics.pstdev(trial_means), 6),
        "hard_failure_rate": round(
            sum(bool(item["score"]["hard_failure"]) for item in run["trials"])
            / len(run["trials"]),
            6,
        ),
        "usage": {
            "agent": agent_usage,
            "judge": judge_usage,
            "total_estimated_cost_usd": round(
                agent_usage["estimated_cost_usd"] + judge_usage["estimated_cost_usd"],
                6,
            ),
            "total_api_elapsed_seconds": round(
                agent_usage["elapsed_seconds"] + judge_usage["elapsed_seconds"],
                3,
            ),
        },
        "stddev_definition": "population standard deviation across per-trial aggregate case means",
        "cases": cases,
    }


def write_reports(run: dict[str, Any], run_dir: Path) -> dict[str, Any]:
    summary = build_summary(run)
    (run_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (run_dir / "report.md").write_text(render_markdown(summary), encoding="utf-8")
    return summary


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        f"# BIC-Bench V2 report — {summary['run_id']}",
        "",
        f"- Agent: `{summary['agent']['name']}` ({summary['agent']['mode']})",
        f"- Judge: `{summary['judge']['name']}`",
        f"- Cases: {summary['case_count']}",
        f"- Trials per case: {summary['trials_per_case']}",
        f"- Overall score: **{_percent(summary['overall_mean'])} ± {_percent(summary['overall_stddev'])}**",
        f"- Hard-failure rate: **{_percent(summary['hard_failure_rate'])}**",
        f"- Estimated API cost: **${summary['usage']['total_estimated_cost_usd']:.4f}**",
        f"- Summed API latency: **{summary['usage']['total_api_elapsed_seconds']:.1f}s**",
        "",
        "| Case | Difficulty | Mean | Std. dev. | Hard failures | Deterministic | Awareness | Alternative |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for case in summary["cases"]:
        lines.append(
            "| {case_id} | {difficulty} | {mean} | {stddev} | {hard} | {det} | {aware} | {alt} |".format(
                case_id=case["case_id"],
                difficulty=case["difficulty"],
                mean=_percent(case["mean"]),
                stddev=_percent(case["stddev"]),
                hard=_percent(case["hard_failure_rate"]),
                det=_percent(case["deterministic_mean"]),
                aware=_percent(case["awareness_mean"]),
                alt=_percent(case["alternative_mean"]),
            )
        )
    lines.extend(
        [
            "",
            "The reported standard deviation is the population standard deviation across per-trial aggregate case means. Per-case standard deviations use that case's trial scores.",
            "",
        ]
    )
    return "\n".join(lines)


def _percent(value: float) -> str:
    return f"{100 * value:.1f}%"


def _sum_usage(usages: Any) -> dict[str, Any]:
    items = [usage for usage in usages if usage]
    return {
        "calls": sum(int(item.get("calls", 1)) for item in items),
        "input_tokens": sum(int(item.get("input_tokens", 0)) for item in items),
        "cached_input_tokens": sum(int(item.get("cached_input_tokens", 0)) for item in items),
        "output_tokens": sum(int(item.get("output_tokens", 0)) for item in items),
        "estimated_cost_usd": round(
            sum(float(item.get("estimated_cost_usd") or 0) for item in items),
            8,
        ),
        "elapsed_seconds": round(
            sum(float(item.get("elapsed_seconds", 0)) for item in items),
            3,
        ),
    }
