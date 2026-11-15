"""Throw the obvious answer shapes at a morning task's grader, before any model run.

    python3 gen/test_morning_grader.py tasks/morning-k1-nohandbook [more task dirs...]

Expected scores are worked out by hand from the 15 invoices (see NEW in build_morning.py):
  untouched / old habit or handbook (REVIEW over $5k, Wrenfield Marketing)  -> 0
  flag nothing, supplier's usual cost center                               -> 7/15
  flag every invoice over $5k with REVIEW, Wrenfield in G&A                 -> 1/15
  new cutoff + contract + reclass, but plain REVIEW with no reviewer name   -> 9/15
  reference answer -> 1;  reference with one invoice logged twice -> 14/15
  reference plus an edited past row -> 0
"""

from __future__ import annotations

import csv
import io
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def shape_rows(exp: dict, note_fn, cc_fn, twice: int | None = None) -> list[list[str]]:
    out = []
    for i, inv in enumerate(exp["new"]):
        r = ["2026-11-13", inv["vendor"], inv["number"], "", "", f'{inv["amount"]:,.2f}',
             cc_fn(inv), "x", note_fn(inv)]
        out.append(r)
        if twice == i:
            out.append(r)
    return out


def score(task: Path, rows: list[list[str]], edit_past: bool = False) -> float:
    exp_path = task / "tests/expected.json"
    live = next((task / "environment/company/finance").glob("invoice_tracker_*.csv"))
    with tempfile.TemporaryDirectory() as tmp:
        t = Path(tmp) / "tracker.csv"
        shutil.copy(live, t)
        if edit_past:
            lines = t.read_text().splitlines()
            lines[1] = lines[1].replace(",", ", ", 1)
            t.write_text("\n".join(lines) + "\n")
        buf = io.StringIO()
        csv.writer(buf, lineterminator="\n").writerows(rows)
        with t.open("a") as f:
            f.write(buf.getvalue())
        out = subprocess.run([sys.executable, "-I", str(task / "tests/check.py"), str(t), str(exp_path)],
                             capture_output=True, text=True).stdout
    return float(out.strip().split("score=")[-1])


bad = 0
for arg in sys.argv[1:]:
    task = Path(arg)
    exp = json.loads((task / "tests/expected.json").read_text())
    is_wcs = lambda i: i["vendor"] == "Wrenfield"
    default_cc = lambda i: i["old_cc"]
    right_cc = lambda i: i["cc"]
    plain = lambda i: "REVIEW" if i["note"].startswith("REVIEW") else ""
    cases = [
        ("untouched", [], 0.0, False),
        ("old habit / handbook", shape_rows(exp, lambda i: i["old_note"], default_cc), 0.0, False),
        ("flag nothing, usual cost centers", shape_rows(exp, lambda i: "", default_cc), 7 / 15, False),
        ("REVIEW on everything over $5k, Wrenfield G&A",
         shape_rows(exp, lambda i: "REVIEW" if i["amount"] > 5000 else "", right_cc), 1 / 15, False),
        ("new rules but no reviewer names", shape_rows(exp, plain, right_cc), 9 / 15, False),
        ("reference answer", shape_rows(exp, lambda i: i["note"], right_cc), 1.0, False),
        ("reference, one invoice logged twice", shape_rows(exp, lambda i: i["note"], right_cc, twice=3), 14 / 15, False),
        ("reference plus an edited past row", shape_rows(exp, lambda i: i["note"], right_cc), 0.0, True),
    ]
    for name, rows, want, edit in cases:
        got = score(task, rows, edit)
        ok = abs(got - want) < 1e-3
        bad += not ok
        print(f"{'ok ' if ok else 'BAD'} {task.name:28s} want={want:.3f} got={got:.3f}  {name}")
sys.exit(1 if bad else 0)
