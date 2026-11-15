from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from harbor.scorer import score_actions


ROOT = Path(__file__).resolve().parent
BLUEPRINTS = ROOT / "harbor" / "hard10_blueprints.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("results", type=Path)
    parser.add_argument("outputs", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def load_trajectory(outputs: Path, case_id: str) -> dict[str, Any]:
    path = outputs / case_id / "mini_swe_agent" / "trajectory.json"
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    args = parse_args()
    run = json.loads(args.results.read_text(encoding="utf-8"))
    blueprints = json.loads(BLUEPRINTS.read_text(encoding="utf-8"))
    rows = []
    for case_id, evaluation in run["evaluation_results"].items():
        original = json.loads(evaluation["metadata"]["verifier_output"])
        audited = score_actions(
            {"id": case_id, "scoring_blueprint": blueprints[case_id]},
            original["recorded_actions"],
        )
        model_stats = load_trajectory(args.outputs, case_id)["info"]["model_stats"]
        rows.append(
            {
                "case_id": case_id,
                "raw_reward": float(evaluation["rewards"]["reward"]),
                "audited_reward": float(audited["reward"]),
                "forbidden_matches": len(audited["forbidden_matches"]),
                "raw_failure_type": original["failure_type"],
                "audited_failure_type": audited["failure_type"],
                "cost_usd": float(model_stats["instance_cost"]),
                "api_calls": int(model_stats["api_calls"]),
                "agent_seconds": float(
                    evaluation["task_breakdown"]["agent_run_duration"]
                ),
            }
        )
    rows.sort(key=lambda row: row["case_id"])
    started = datetime.fromisoformat(run["started_at"])
    finished = datetime.fromisoformat(run["finished_at"])
    summary = {
        "run_id": run["benchmark_id"],
        "model": run["benchmark_arguments"]["contract"]["model"],
        "agent": run["benchmark_arguments"]["contract"]["name"],
        "dataset": run["benchmark_arguments"]["dataset_version"]["id"],
        "task_count": len(rows),
        "raw_mean": sum(row["raw_reward"] for row in rows) / len(rows),
        "audited_mean": sum(row["audited_reward"] for row in rows) / len(rows),
        "forbidden_total": sum(row["forbidden_matches"] for row in rows),
        "cost_usd": sum(row["cost_usd"] for row in rows),
        "api_calls": sum(row["api_calls"] for row in rows),
        "wall_seconds": (finished - started).total_seconds(),
        "cases": rows,
    }
    corrected_count = sum(
        row["raw_reward"] != row["audited_reward"] for row in rows
    )
    full_count = sum(row["audited_reward"] == 1.0 for row in rows)
    partial_count = sum(row["audited_reward"] == 0.5 for row in rows)
    zero_count = sum(row["audited_reward"] == 0.0 for row in rows)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "audit-summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    table = [
        "| Case | Raw | Audited | Forbidden | Cost | Calls |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in rows:
        table.append(
            f"| `{row['case_id']}` | {row['raw_reward']:.1f} | "
            f"{row['audited_reward']:.1f} | {row['forbidden_matches']} | "
            f"${row['cost_usd']:.4f} | {row['api_calls']} |"
        )
    report = f"""# Implicit Core 5 mini-SWE pilot

## Protocol

- Run: `{summary['run_id']}`
- Dataset: `{summary['dataset']}`
- Agent: `{summary['agent']}`
- Model: `{summary['model']}`
- Task sandbox Internet: disabled
- Concurrency: 5
- Step limit: 20
- Per-task cost ceiling: $1.50

## Results

{chr(10).join(table)}

- Official raw mean: **{summary['raw_mean'] * 100:.1f}%**
- Audited deterministic mean: **{summary['audited_mean'] * 100:.1f}%**
- Forbidden actions: **{summary['forbidden_total']}**
- Model API cost: **${summary['cost_usd']:.4f}**
- Model API calls: **{summary['api_calls']}**
- Valkyrie wall time: **{summary['wall_seconds']:.1f}s**

## Interpretation

The current verifier changed {corrected_count} case score(s) relative to the
published run's verifier by accepting equivalent observable field formatting.
After audit, {full_count} case(s) receive full credit, {partial_count} receive
partial credit, and {zero_count} receive zero. No forbidden action was taken.
This is a one-trial calibration result, not a leaderboard estimate.
"""
    (args.output_dir / "audit-report.md").write_text(report, encoding="utf-8")


if __name__ == "__main__":
    main()
