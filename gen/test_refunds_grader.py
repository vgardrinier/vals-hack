"""Grader test + brainless baselines for the refunds tasks, before any model run.

    python3 gen/test_refunds_grader.py tasks_refunds/refunds-*   (writes results/baselines_refunds.json)

Each answer shape is appended to a copy of the live log and graded with the task's own check.py.
Expected: reference = 1, untouched = 0, every wrong shape < 1.
"""
import collections
import csv
import io
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

LIVE = "refunds_log_2026Q4.csv"


def history(task: Path) -> list[dict]:
    sup = task / "environment/company/support"
    rows = []
    for f in sorted(sup.glob("archive/*.csv")) + [sup / LIVE]:
        rows += list(csv.DictReader(open(f, newline="")))
    return rows


def grade(task: Path, answers: list[list[str]]) -> float:
    with tempfile.TemporaryDirectory() as tmp:
        log = Path(tmp) / LIVE
        shutil.copy(task / "environment/company/support" / LIVE, log)
        with log.open("a", newline="") as f:
            csv.writer(f, lineterminator="\n").writerows(answers)
        out = subprocess.run([sys.executable, "-I", str(task / "tests/check.py"), str(log), str(task / "tests/expected.json")],
                             capture_output=True, text=True).stdout
    return float(out.strip().split("score=")[-1])


def ans(q, d, a, n):
    return ["2026-11-13", q["ticket"], q["customer"], q["tier"], f"{q['amount']:,.2f}", q["reason"], d, a, n]


def shapes(task: Path) -> dict[str, list[list[str]]]:
    exp = json.loads((task / "tests/expected.json").read_text())
    new, hist = exp["new"], history(task)
    last = {}
    for r in hist:
        last[r["Customer"]] = r
    maj = collections.defaultdict(collections.Counter)
    for r in hist:
        maj[r["Customer"]][(r["Decision"], r["Approver"], r["Notes"])] += 1
    return {
        "reference": [ans(q, q["decision"], q["approver"], q["note"]) for q in new],
        "untouched": [],
        "old habits / follow the old doc": [ans(q, *q["old"]) for q in new],
        "refund everything": [ans(q, "refund", "Nadia Thorsby", "") for q in new],
        "credit everything": [ans(q, "credit", "", "") for q in new],
        "deny everything": [ans(q, "deny", "", "") for q in new],
        "log twice": [ans(q, q["decision"], q["approver"], q["note"]) for q in new] * 2,
        "negated note": [ans(q, q["decision"], q["approver"], q["note"] or "no SLA, not a duplicate") for q in new],
        # brainless baselines
        "copy last decision for the customer": [ans(q, last[q["customer"]]["Decision"], last[q["customer"]]["Approver"],
                                                    last[q["customer"]]["Notes"]) for q in new],
        "majority for the customer": [ans(q, *maj[q["customer"]].most_common(1)[0][0]) for q in new],
    }


BASELINES = ["old habits / follow the old doc", "copy last decision for the customer", "majority for the customer",
             "credit everything", "refund everything", "deny everything"]

bad, base = 0, []
for t in map(Path, sys.argv[1:]):
    s = {k: grade(t, v) for k, v in shapes(t).items()}
    checks = {"reference=1": s["reference"] == 1, "untouched=0": s["untouched"] == 0,
              "wrong shapes <1": all(v < 1 for k, v in s.items() if k not in ("reference", "negated note")),
              "negated text is not a note": s["negated note"] == 1}
    bad += not all(checks.values())
    print(f"{'ok ' if all(checks.values()) else 'BAD'} {t.name}: " + ", ".join(f"{k} {v:.2f}" for k, v in s.items()))
    for k in BASELINES:
        base.append({"task": t.name, "strategy": k, "mean": s[k], "pass": float(s[k] == 1)})
Path("results/baselines_refunds.json").write_text(json.dumps(base, indent=1))
sys.exit(1 if bad else 0)
