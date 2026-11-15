"""Collect per-attempt results for the drift benchmark into results/drift_attempts.json.

    python3 results/collect_drift.py runs.txt

runs.txt has lines "<model> <run_id>"; each run holds every copy (-r1..-r5) of the 12 drift
tasks. Each attempt keeps its reward, the grader's check lines, and a partial-credit score:
the share of the four non-trivial new invoices logged once with the team's current note.
"""

import json
import re
import subprocess
import sys
from pathlib import Path

OUT = Path(__file__).parent / "drift_attempts.json"
TYPES = ["cutoff", "stopped", "approver", "returned"]
DOSES = [1, 3, 7]
COPIES = 5


def task_info(run_id: str, task: str) -> dict:
    raw = subprocess.run(["valkyrie", "run", "task", run_id, task, "--format", "json"],
                         capture_output=True, text=True, cwd="/tmp").stdout
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


TASKS_DIR = Path(__file__).parent.parent / "tasks"


def partial(task: str, checks: list[str]) -> float:
    """Share of the four non-trivial new invoices handled the team's current way.

    An invoice counts only if it was logged exactly once AND its note matches the current habit.
    The small office-supply bill is left out: every version of the habit agrees on it.
    """
    base = re.sub(r"-r\d+$", "", task)
    exp = json.loads((TASKS_DIR / base / "tests/expected.json").read_text())
    scored = [i for i in exp["new"] if not (i["expect"] is None and i["alt"] is None)]
    ok = 0
    for i in scored:
        num = i["number"]
        logged = any(c.startswith("PASS") and num in c and "logged exactly once" in c for c in checks)
        note = any(c.startswith("PASS") and num in c and "REVIEW" in c for c in checks)
        ok += logged and note
    return ok / len(scored)


attempts = []
for line in Path(sys.argv[1]).read_text().split("\n"):
    if not line.strip():
        continue
    model, run_id = line.split()
    for t in TYPES:
        for k in DOSES:
            for r in range(1, COPIES + 1):
                task = f"drift-{t}-k{k}-r{r}"
                d = task_info(run_id, task)
                if not d:
                    continue
                ev = d.get("evaluation_result") or {}
                out = (ev.get("metadata") or {}).get("verifier_output", "")
                checks = [l for l in out.splitlines() if l.startswith(("PASS", "FAIL"))]
                attempts.append({
                    "model": model, "run_id": run_id, "type": t, "dose": k, "copy": r, "task": task,
                    "status": d.get("status"), "reward": (ev.get("rewards") or {}).get("reward"),
                    "error": d.get("error_message"), "score": partial(task, checks), "checks": checks,
                })

OUT.write_text(json.dumps(attempts, indent=1))
done = [a for a in attempts if a["status"] == "FINISHED" and a["reward"] is not None]
print(f"{len(attempts)} attempts, {len(done)} scored -> {OUT}")
for m in sorted({a["model"] for a in attempts}):
    mine = [a for a in done if a["model"] == m]
    errs = [a for a in attempts if a["model"] == m and a not in done]
    print(f"  {m:22s} score {sum(a['score'] for a in mine) / max(1, len(mine)):.3f}  "
          f"passed {sum(int(a['reward']) for a in mine)}/{len(mine)}"
          + (f"  not scored: {len(errs)}" if errs else ""))
