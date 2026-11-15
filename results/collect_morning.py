"""Collect morning-task results, 20 at a time, into results/morning_<round>.json and print a summary.

    python3 results/collect_morning.py <round_name> <runs.txt> [more runs files...]

runs files: lines "<model> <run_id>". Task ids are read from each run itself.
Per attempt we keep the score (share of the 15 invoices right), the grader lines, and a
per-habit breakdown read from those lines:
  contract   the 2 Halverson invoices: right note (none)
  reviewer   the 6 invoices over $10k from other suppliers: right REVIEW name
  cutoff     the 6 invoices between $5k and $10k: right note (none)
  costcenter the 3 Wrenfield invoices: cost center G&A
"""

from __future__ import annotations

import json
import random
import re
import statistics
import subprocess
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).parent


def sh(*args: str) -> str:
    return subprocess.run(["valkyrie", *args], capture_output=True, text=True, cwd="/tmp").stdout


def task_ids(run_id: str) -> list[str]:
    import os
    if os.environ.get("IDS_FILE"):   # run listings are paginated; prefer the ids we started the run with
        return Path(os.environ["IDS_FILE"]).read_text().strip().split(",")
    out = sh("run", "tasks", run_id)
    return re.findall(r"^(morning\S*-r\d+)\s", out, re.M)


def one(model: str, run_id: str, task: str) -> dict:
    for _ in range(3):
        try:
            d = json.loads(sh("run", "task", run_id, task, "--format", "json"))
            break
        except json.JSONDecodeError:
            continue
    else:
        d = {}
    ev = d.get("evaluation_result") or {}
    out = (ev.get("metadata") or {}).get("verifier_output", "")
    base = task.rsplit("-r", 1)[0]
    m = re.match(r"(.+)-k(\d)-(handbook|nohandbook|told)", base)
    return {
        "model": model, "run_id": run_id, "task": task, "version": base,
        "prefix": m.group(1) if m else base, "dose": int(m.group(2)) if m else None,
        "handbook": (m.group(3) == "handbook") if m else None,
        "told": (m.group(3) == "told") if m else False,
        "status": d.get("status"), "error": d.get("error_message"),
        "reward": (ev.get("rewards") or {}).get("reward"),
        "checks": [l for l in out.splitlines() if l.startswith(("PASS", "FAIL", "score", "extra"))],
    }


def habits(a: dict) -> dict:
    res = defaultdict(list)
    for l in a["checks"]:
        m = re.match(r"(PASS|FAIL) (\S+) \(([^,]+), \$([\d,\.]+)\)(.*)", l)
        if not m:
            continue
        ok, vendor, amount, rest = m.group(1) == "PASS", m.group(3), float(m.group(4).replace(",", "")), m.group(5)
        note_ok = ok or ("note" not in rest and "logged" not in rest)
        cc_ok = ok or ("cost center" not in rest and "logged" not in rest)
        if vendor == "Halverson":
            res["contract"].append(note_ok)
        elif amount > 10000:
            res["reviewer"].append(note_ok)
        elif amount > 5000:
            res["cutoff"].append(note_ok)
        if vendor == "Wrenfield":
            res["costcenter"].append(cc_ok)
    return {k: sum(v) / len(v) for k, v in res.items() if v}


def main() -> None:
    rnd, files = sys.argv[1], sys.argv[2:]
    pairs = []
    for f in files:
        for line in Path(f).read_text().splitlines():
            if line.strip():
                model, rid = line.split()
                pairs.append((model.split("/")[-1], rid))
    jobs = [(m, r, t) for m, r in pairs for t in task_ids(r)]
    with ThreadPoolExecutor(20) as ex:
        attempts = list(ex.map(lambda j: one(*j), jobs))
    for a in attempts:
        a["habits"] = habits(a) if a["status"] == "FINISHED" else {}
    out = HERE / f"morning_{rnd}.json"
    out.write_text(json.dumps(attempts, indent=1))
    done = [a for a in attempts if a["status"] == "FINISHED" and a["reward"] is not None]
    print(f"{len(attempts)} attempts, {len(done)} scored, {len(attempts) - len(done)} not -> {out.name}")
    rng = random.Random(0)
    print(f"{'model':18s} {'mean':>6s} {'±':>5s} {'pass@1':>7s} | {'k1':>5s} {'k2':>5s} {'k3':>5s} | {'no hb':>6s} {'hb':>5s} | habits")
    for model in sorted({a["model"] for a in attempts}):
        xs = [a for a in done if a["model"] == model]
        if not xs:
            continue
        r = [a["reward"] for a in xs]
        boots = sorted(statistics.mean(rng.choice(r) for _ in r) for _ in range(2000))
        half = (boots[1949] - boots[50]) / 2
        by = lambda f: statistics.mean([a["reward"] for a in xs if f(a)] or [float("nan")])
        hb = defaultdict(list)
        for a in xs:
            for k, v in a["habits"].items():
                hb[k].append(v)
        hs = " ".join(f"{k}={statistics.mean(v):.0%}" for k, v in sorted(hb.items()))
        print(f"{model:18s} {statistics.mean(r):6.1%} {half:5.1%} {sum(x == 1 for x in r) / len(r):7.1%} | "
              f"{by(lambda a: a['dose'] == 1):5.1%} {by(lambda a: a['dose'] == 2):5.1%} {by(lambda a: a['dose'] == 3):5.1%} | "
              f"{by(lambda a: not a['handbook']):6.1%} {by(lambda a: a['handbook']):5.1%} | {hs}")
    errs = [a for a in attempts if a["status"] != "FINISHED"]
    if errs:
        print("not finished:", {(a["model"], (a["error"] or a["status"] or "")[:70]) for a in errs})


if __name__ == "__main__":
    main()
