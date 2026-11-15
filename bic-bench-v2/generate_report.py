from __future__ import annotations

import argparse
import json
from pathlib import Path

from harness.reporting import write_reports


def main() -> int:
    parser = argparse.ArgumentParser(description="Regenerate BIC-Bench V2 JSON and Markdown reports.")
    parser.add_argument("run_json", type=Path)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    run = json.loads(args.run_json.read_text(encoding="utf-8"))
    output_dir = args.output_dir or args.run_json.parent
    output_dir.mkdir(parents=True, exist_ok=True)
    summary = write_reports(run, output_dir)
    print(
        f"Wrote {output_dir / 'summary.json'} and {output_dir / 'report.md'} "
        f"({summary['overall_mean']:.3f} ± {summary['overall_stddev']:.3f})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
