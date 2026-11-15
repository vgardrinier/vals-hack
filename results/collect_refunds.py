"""Collect refunds-job attempts into results/refunds_v1.json (20 fetches at a time).

    python3 results/collect_refunds.py /tmp/refunds_runs.txt

Runs file lines: "<model> <run_id>". Each run holds every task copy (refunds-<lvl>-k<dose>-r<n>,
refunds-told-r<n>). reward = share of the 15 requests fully right; pass = all 15 right.
"""
import json
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

OUT = Path(__file__).parent / "refunds_v1.json"
IDS = Path("/tmp/refunds_ids.txt").read_text().strip().split(",")


def fetch(job):
    model, run_id, task = job
    raw = subprocess.run(["valkyrie", "run", "task", run_id, task, "--format", "json"],
                         capture_output=True, text=True, cwd="/tmp").stdout
    try:
        d = json.loads(raw)
    except json.JSONDecodeError:
        return None
    ev = d.get("evaluation_result") or {}
    out = (ev.get("metadata") or {}).get("verifier_output", "")
    version = re.sub(r"-r\d+$", "", task)
    m = re.match(r"refunds-(l\d)-k(\d)", version)
    return {"model": model, "run_id": run_id, "task": task, "version": version,
            "level": m.group(1).upper() if m else "TOLD", "dose": int(m.group(2)) if m else 3,
            "status": d.get("status"), "reward": (ev.get("rewards") or {}).get("reward"),
            "error": d.get("error_message"),
            "checks": [l for l in out.splitlines() if l.startswith(("PASS", "FAIL", "extra", "score"))]}


jobs = []
for line in Path(sys.argv[1]).read_text().split("\n"):
    if line.strip():
        model, run_id = line.split()
        jobs += [(model.split("/")[-1], run_id, t) for t in IDS]
res = [r for r in ThreadPoolExecutor(20).map(fetch, jobs) if r]
OUT.write_text(json.dumps(res, indent=1))
done = [r for r in res if r["status"] == "FINISHED" and r["reward"] is not None]
print(f"{len(res)} attempts, {len(done)} scored, {sum(r['status'] == 'ERROR' for r in res)} errored")
for m in sorted({r["model"] for r in res}):
    cells = []
    for lv, d in [("L1", 3), ("L2", 3), ("L3", 3), ("L1", 5), ("L2", 5), ("L3", 5), ("TOLD", 3)]:
        xs = [r for r in done if r["model"] == m and r["level"] == lv and r["dose"] == d]
        cells.append(f"{lv}k{d} {sum(r['reward'] >= .9999 for r in xs)}/{len(xs)}")
    print(f"  {m:20s} " + "  ".join(cells))
