"""Throw the obvious answer shapes at a morning task's grader, before any model run.

    python3 gen/test_morning_grader.py tasks/morning3-k2-nohandbook [more task dirs...]

For every shape the expected score is counted independently of check.py, straight from the
answer key: the share of the invoices where the shape's note and cost center match.
Shapes: untouched, old habit / old policy, flag nothing, REVIEW on everything over $5k,
new rules without reviewer names, the reference answer, an invoice logged twice, an edited past
row, and notes that mention review without flagging ("no review needed", "No REVIEW: Halverson
MSA"), which must count as no flag.
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
    new = exp["new"]
    default_cc = lambda i: i["old_cc"]
    right_cc = lambda i: i["cc"]
    plain = lambda i: "REVIEW" if i["note"].startswith("REVIEW") else ""

    def want(note_fn, cc_fn):
        return sum(note_fn(i) == i["note"] and cc_fn(i).lower() == i["cc"].lower() for i in new) / len(new)

    def negated(i):     # what a cautious model might write: prose that mentions review but flags nothing
        if i["note"]:
            return i["note"]
        return "No REVIEW: Halverson MSA" if i["vendor"] == "Halverson" else "no review needed"

    cases = [
        ("untouched", [], 0.0, False),
        ("old habit / old policy", shape_rows(exp, lambda i: i["old_note"], default_cc),
         want(lambda i: i["old_note"], default_cc), False),
        ("flag nothing, usual cost centers", shape_rows(exp, lambda i: "", default_cc),
         want(lambda i: "", default_cc), False),
        ("REVIEW on everything over $5k, right cost centers",
         shape_rows(exp, lambda i: "REVIEW" if i["amount"] > 5000 else "", right_cc),
         want(lambda i: "REVIEW" if i["amount"] > 5000 else "", right_cc), False),
        ("new rules but no reviewer names", shape_rows(exp, plain, right_cc), want(plain, right_cc), False),
        ("reference answer", shape_rows(exp, lambda i: i["note"], right_cc), 1.0, False),
        ("reference, one invoice logged twice", shape_rows(exp, lambda i: i["note"], right_cc, twice=3),
         (len(new) - 1) / len(new), False),
        ("reference plus an edited past row", shape_rows(exp, lambda i: i["note"], right_cc), 0.0, True),
        ("reference, 'no review needed' notes instead of blanks", shape_rows(exp, negated, right_cc), 1.0, False),
        ("reference, reviewer in other words ('review - tomasz')",
         shape_rows(exp, lambda i: i["note"].replace("REVIEW: ", "review - ").lower(), right_cc), 1.0, False),
    ]
    for name, rows, w, edit in cases:
        got = score(task, rows, edit)
        ok = abs(got - w) < 1e-3
        bad += not ok
        print(f"{'ok ' if ok else 'BAD'} {task.name:28s} want={w:.3f} got={got:.3f}  {name}")
sys.exit(1 if bad else 0)
