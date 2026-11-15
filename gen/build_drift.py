"""Build the drift pack: the same habit change, with less or more evidence that it changed.

    python gen/build_drift.py <redwood_docs_dir> <out_tasks_dir>

Pilot: the tracker REVIEW cutoff moved from $5k to $10k on Oct 5. The tracker shows
1, 3 or 7 mid-size invoices ($5k-10k) after that date that no longer got REVIEW.
Everything else (company, noise, the 5 new invoices, grader) is the ladder's.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import build_ladder as L  # noqa: E402

DOSES = [1, 3, 7]
TASKS = [L.Task(f"drift-cutoff-k{k}", "tracker", L.changed("REVIEW"), L.over(5000, "REVIEW"), dose=k,
                desc=f"REVIEW cutoff moved 5k to 10k; tracker shows {k} invoices after the change")
         for k in DOSES]

if __name__ == "__main__":
    L.build(Path(sys.argv[1]), Path(sys.argv[2]), TASKS)
