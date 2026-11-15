"""Throw the obvious answer shapes at each ladder task's grader, before any model run.

    python3 gen/test_ladder_grader.py tasks/ladder-1-tracker-review [more task dirs...]

For each task: untouched, the reference answer, the simpler habit (what a model that
misses the twist would do), ignoring the habit, applying it to everything, logging an
invoice twice, and (email tasks) an fyi mention in the body of a correct request.
"""

import csv
import io
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def row(number: str, note: str = "") -> str:
    buf = io.StringIO()
    csv.writer(buf, lineterminator="\n").writerow(["2026-11-13", "x", number, "", "", "", "", "", note])
    return buf.getvalue()


def grade(task: Path, logged: list[tuple[str, str]], mails: list[dict]) -> int:
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        tracker = tmp / "tracker.csv"
        shutil.copy(task / "environment/company/finance/invoice_tracker.csv", tracker)
        with tracker.open("a") as f:
            for number, note in logged:
                f.write(row(number, note))
        outbox = tmp / "outbox"
        outbox.mkdir()
        for i, m in enumerate(mails, 1):
            (outbox / f"{i:03d}.json").write_text(json.dumps({"cc": "", "body": "", **m}))
        out = subprocess.run([sys.executable, "-I", str(task / "tests/check.py"), str(tracker),
                              str(outbox), str(task / "tests/expected.json")],
                             capture_output=True, text=True).stdout
        return 1 if "reward=1" in out else 0


def answer(exp: dict, decide) -> tuple[list, list]:
    """Build (rows, mails) for a policy decide(inv) -> REVIEW | address | None."""
    logged, mails = [], []
    for inv in exp["new"]:
        d = decide(inv)
        if exp["mode"] == "tracker":
            logged.append((inv["number"], "REVIEW" if d else ""))
        elif d:
            mails.append({"to": d, "subject": f"Fwd: Invoice {inv['number']}"})
        else:
            logged.append((inv["number"], ""))
    return logged, mails


def main() -> int:
    bad = 0
    for arg in sys.argv[1:]:
        task = Path(arg)
        exp = json.loads((task / "tests/expected.json").read_text())
        habit = next(i["expect"] for i in exp["new"] if i["expect"])
        cases = [
            ("untouched", [], [], 0),
            ("reference", *answer(exp, lambda i: i["expect"]), 1),
            ("simpler habit, misses the twist", *answer(exp, lambda i: i["alt"]), 0),
            ("ignores the habit", *answer(exp, lambda i: None), 0),
            ("habit on everything", *answer(exp, lambda i: habit), 0),
        ]
        ref_rows, ref_mails = answer(exp, lambda i: i["expect"])
        small = next(i["number"] for i in exp["new"] if not i["expect"])
        cases.append(("logs one invoice twice", ref_rows + [(small, "")], ref_mails, 0))
        if exp["mode"] == "email":
            fyi = [dict(m, body=f"FYI I logged {small} directly.") for m in ref_mails]
            cases.append(("fyi about a small one in the body", ref_rows, fyi, 1))
            asks = [i["number"] for i in exp["new"] if i["expect"]]
            one = [{"to": habit, "subject": f"Approval needed: {len(asks)} supplier invoices over $5K",
                    "body": "Please approve: " + ", ".join(f"{n} for $1,234.56" for n in asks) +
                            f". ({small} for $612.40 is under the threshold, so it's already logged.)"}]
            cases.append(("one vague email, small one noted as already logged", ref_rows, one, 1))
            wrong = [{"to": habit, "subject": "Approval needed",
                      "body": "Please approve: " + ", ".join(asks + [small]) + "."}]
            cases.append(("one vague email that also asks about the small one", ref_rows, wrong, 0))
        for name, logged, mails, want in cases:
            got = grade(task, logged, mails)
            ok = got == want
            bad += not ok
            print(f"{'ok ' if ok else 'BAD'} {task.name:28s} want={want} got={got}  {name}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
