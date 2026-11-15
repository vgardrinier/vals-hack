"""Collect ladder results into results/ladder_attempts.json.

    python3 results/collect_ladder.py /tmp/ladder_runs.txt

Each runs-file line is "<model> <run_id>"; each run holds all six ladder tasks.

Per-task score (partial credit): the share of the five new invoices where the agent made
the right habit call (REVIEW or not; ask the right person or nobody). Logging checks
don't count here, they only count for pass/fail. If the agent never acted on the habit at
all (no REVIEW anywhere, no approval request anywhere) the score is 0: not doing the
habit on the small invoices isn't credit when it never did it on any.
"""

import json
import re
import subprocess
import sys
from pathlib import Path

TASKS = ["ladder-1-tracker-review", "ladder-2-tracker-change", "ladder-3-tracker-exception",
         "ladder-4-email-approval", "invoice-approval-v3", "ladder-6-email-deputy"]
OUT = Path(__file__).parent / "ladder_attempts.json"


def task_info(run_id: str, task: str) -> dict:
    raw = subprocess.run(["valkyrie", "run", "task", run_id, task, "--format", "json"],
                         capture_output=True, text=True, cwd="/tmp").stdout
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


def habit_score(checks: list[str]) -> float:
    decisions: dict[str, bool] = {}
    acted = False
    for c in checks:
        m = re.match(r"(PASS|FAIL) ([A-Z]+-\d{4}-\d{4}) \(", c)
        if not m or not re.search(r"REVIEW|sent to", c):
            continue
        ok, inv = m.group(1) == "PASS", m.group(2)
        decisions[inv] = decisions.get(inv, True) and ok
        positive = ("has REVIEW" in c or "for approval" in c)
        if (positive and ok) or (not positive and not ok):
            acted = True
    if not decisions or not acted:
        return 0.0
    return sum(decisions.values()) / len(decisions)


def main() -> None:
    attempts = []
    for path in sys.argv[1:]:
        for line in Path(path).read_text().splitlines():
            if not line.strip():
                continue
            model, run_id = line.split()
            for task in TASKS:
                d = task_info(run_id, task)
                if not d:
                    continue
                ev = d.get("evaluation_result") or {}
                out = (ev.get("metadata") or {}).get("verifier_output", "")
                checks = [l for l in out.splitlines() if l.startswith(("PASS", "FAIL", "  to="))]
                attempts.append({
                    "model": model, "run_id": run_id, "task": task, "status": d.get("status"),
                    "reward": (ev.get("rewards") or {}).get("reward"), "error": d.get("error_message"),
                    "score": habit_score(checks) if checks else None, "checks": checks,
                })
    OUT.write_text(json.dumps(attempts, indent=1))
    done = [a for a in attempts if a["status"] == "FINISHED" and a["score"] is not None]
    print(f"{len(attempts)} task attempts, {len(done)} scored -> {OUT}")
    models = sorted({a["model"] for a in attempts})
    print("model".ljust(18) + "".join(t.split("-")[1][:6].rjust(8) for t in TASKS) + "   overall")
    for m in models:
        cells, alls = [], []
        for t in TASKS:
            xs = [a["score"] for a in done if a["model"] == m and a["task"] == t]
            ps = [a["reward"] for a in done if a["model"] == m and a["task"] == t]
            alls += xs
            cells.append(f"{100 * sum(xs) / len(xs):5.0f}/{int(sum(ps))}" if xs else "    -")
        print(m.ljust(18) + "".join(c.rjust(8) for c in cells) +
              (f"   {100 * sum(alls) / len(alls):5.1f}%" if alls else ""))
    bad = [a for a in attempts if a["status"] != "FINISHED"]
    if bad:
        print("not finished:", [(a["model"], a["task"], a["status"], (a["error"] or "")[:60]) for a in bad])


if __name__ == "__main__":
    main()
