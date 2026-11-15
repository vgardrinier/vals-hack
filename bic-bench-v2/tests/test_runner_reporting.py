from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from harness.adapters import ReferenceAgent
from harness.case_loader import load_case
from harness.reporting import write_reports
from harness.runner import EvaluationRunner, RunnerConfig
from harness.tools import ACTION_CATALOG, TOOL_DEFINITIONS
from scoring.judge import HeuristicJudge


class RunnerReportingTests(unittest.TestCase):
    def test_runner_logs_trajectory_and_reports_statistics(self) -> None:
        case = load_case(
            ROOT / "cases" / "v2-meadowgene-seed-certificate.json",
            ROOT / "contexts",
        )
        with tempfile.TemporaryDirectory() as temporary:
            runner = EvaluationRunner(
                config=RunnerConfig(
                    trials=2,
                    max_steps=3,
                    concurrency=2,
                    run_id="unit-run",
                ),
                agent_factory=lambda loaded_case, trial: ReferenceAgent(loaded_case),
                judge=HeuristicJudge(),
                output_root=Path(temporary),
            )
            run, run_dir = runner.run([case])
            summary = write_reports(run, run_dir)
            self.assertEqual(summary["overall_mean"], 1.0)
            self.assertEqual(summary["overall_stddev"], 0.0)
            self.assertTrue((run_dir / "report.md").is_file())
            trajectory_path = run_dir / run["trials"][0]["trajectory_path"]
            trajectory = json.loads(trajectory_path.read_text(encoding="utf-8"))
            self.assertEqual(trajectory["loop_version"], "bic-agent-loop-v2.0")
            self.assertEqual(trajectory["terminated"], "finish")
            self.assertNotIn("implicit_constraints", trajectory["user_prompt"])
            required_action = case["scoring_blueprint"]["required"][0]["action"]
            self.assertIn(required_action, ACTION_CATALOG)
            action_schema = TOOL_DEFINITIONS[0]["input_schema"]["properties"]["action"]
            self.assertEqual(tuple(action_schema["enum"]), ACTION_CATALOG)


if __name__ == "__main__":
    unittest.main()
