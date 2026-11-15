from __future__ import annotations

import argparse
import sys
from pathlib import Path

from harness.adapters import CommandAgent, DemoAgent, NaiveAgent, ReferenceAgent
from harness.case_loader import load_cases
from harness.reporting import write_reports
from harness.runner import EvaluationRunner, RunnerConfig
from scoring.judge import CommandJudge, HeuristicJudge


ROOT = Path(__file__).resolve().parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the fixed BIC-Bench V2 harness.")
    parser.add_argument("--case", action="append", dest="cases", help="Case ID; repeat as needed.")
    parser.add_argument("--limit", type=int, help="Run the first N sorted cases.")
    parser.add_argument("--all", action="store_true", help="Explicitly authorize all 70 cases.")
    parser.add_argument("--trials", type=int, default=5, help="Trials per case (default: 5).")
    parser.add_argument(
        "--leaderboard",
        action="store_true",
        help="Use the fixed leaderboard protocol: exactly 8 trials per case.",
    )
    parser.add_argument("--max-steps", type=int, default=8)
    parser.add_argument("--concurrency", type=int, default=1, choices=range(1, 6))
    parser.add_argument(
        "--agent",
        choices=("reference", "naive", "demo", "command"),
        default="demo",
    )
    parser.add_argument("--agent-command", help="Subprocess command for --agent command.")
    parser.add_argument("--agent-name", default="external-agent")
    parser.add_argument("--agent-mode", choices=("text", "tool"), default="tool")
    parser.add_argument("--judge", choices=("heuristic", "command"), default="heuristic")
    parser.add_argument("--judge-command", help="Subprocess command for --judge command.")
    parser.add_argument("--judge-name", default="external-llm-judge")
    parser.add_argument("--run-id")
    parser.add_argument("--output-root", type=Path, default=ROOT / "results")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.all and not args.cases and args.limit is None:
        raise SystemExit("Select cases with --case/--limit, or explicitly pass --all.")
    if args.all and (args.cases or args.limit is not None):
        raise SystemExit("--all cannot be combined with --case or --limit.")
    if args.leaderboard:
        args.trials = 8
        if args.judge != "command":
            raise SystemExit("Leaderboard mode requires --judge command with a versioned LLM judge.")
    if args.agent == "command" and not args.agent_command:
        raise SystemExit("--agent command requires --agent-command.")
    if args.judge == "command" and not args.judge_command:
        raise SystemExit("--judge command requires --judge-command.")

    cases = load_cases(
        ROOT / "cases",
        ROOT / "contexts",
        selected_ids=set(args.cases) if args.cases else None,
        limit=None if args.all else args.limit,
    )

    def agent_factory(case: dict, trial: int):
        if args.agent == "reference":
            return ReferenceAgent(case)
        if args.agent == "naive":
            return NaiveAgent(case)
        if args.agent == "demo":
            return DemoAgent(case, trial)
        return CommandAgent(
            command=args.agent_command,
            name=args.agent_name,
            mode=args.agent_mode,
        )

    judge = (
        HeuristicJudge()
        if args.judge == "heuristic"
        else CommandJudge(args.judge_command, name=args.judge_name)
    )
    config = RunnerConfig(
        trials=args.trials,
        max_steps=args.max_steps,
        concurrency=args.concurrency,
        run_id=args.run_id or "",
    )
    runner = EvaluationRunner(
        config=config,
        agent_factory=agent_factory,
        judge=judge,
        output_root=args.output_root,
    )
    run, run_dir = runner.run(cases)
    summary = write_reports(run, run_dir)
    print(f"Run: {run_dir}")
    print(
        f"Score: {summary['overall_mean']:.3f} ± {summary['overall_stddev']:.3f}; "
        f"hard failures: {summary['hard_failure_rate']:.1%}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
