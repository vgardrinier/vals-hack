"""Collect per-attempt results for the v3 runs into results/v3_attempts.json.

    python3 results/collect.py runs.txt [runs.txt ...]

Each runs file has lines "<model> <run_id>". The oracle line is skipped.
Each attempt keeps its reward and the grader's per-check lines, so the
chart and any later analysis read from the same source.
"""

import json
import subprocess
import sys
from pathlib import Path

TASKS = {"invoice-approval-v3": "hidden", "invoice-approval-v3-written": "written"}
OUT = Path(__file__).parent / "v3_attempts.json"


def task_info(run_id: str, task: str) -> dict:
    raw = subprocess.run(["valkyrie", "run", "task", run_id, task, "--format", "json"],
                         capture_output=True, text=True, cwd="/tmp").stdout
    return json.loads(raw)


attempts = []
for path in sys.argv[1:]:
    for line in Path(path).read_text().split("\n"):
        if not line.strip():
            continue
        model, run_id = line.split()
        if model == "oracle":
            continue
        model = {"opus": "claude-opus-5-5"}.get(model, model)
        for task, version in TASKS.items():
            d = task_info(run_id, task)
            ev = d.get("evaluation_result") or {}
            out = (ev.get("metadata") or {}).get("verifier_output", "")
            attempts.append({
                "model": model, "run_id": run_id, "version": version,
                "status": d.get("status"),
                "reward": (ev.get("rewards") or {}).get("reward"),
                "error": d.get("error_message"),
                "checks": [l for l in out.splitlines() if l.startswith(("PASS", "FAIL", "  to="))],
            })

OUT.write_text(json.dumps(attempts, indent=1))
done = [a for a in attempts if a["status"] == "FINISHED" and a["reward"] is not None]
print(f"{len(attempts)} attempts, {len(done)} scored -> {OUT}")
for m in sorted({a["model"] for a in attempts}):
    for v in ("hidden", "written"):
        rs = [a["reward"] for a in done if a["model"] == m and a["version"] == v]
        other = [a["status"] for a in attempts if a["model"] == m and a["version"] == v and a not in done]
        print(f"  {m:20s} {v:8s} {sum(rs):.0f}/{len(rs)} passed" + (f"  (not scored: {other})" if other else ""))
