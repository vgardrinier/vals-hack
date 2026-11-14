"""Throw every answer shape we can think of at the v3 grader, before any model run.

    python3 gen/test_approval_v3_grader.py tasks/invoice-approval-v3

Each case = (what the agent emails, which invoices it logs) -> expected reward.
"""

import csv
import io
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

task = Path(sys.argv[1])
exp = json.loads((task / "tests/expected.json").read_text())
tracker_src = task / "environment/company/finance/invoice_tracker.csv"
D = exp["director"]
by_vendor = {i["vendor"]: i for i in exp["new"]}
HDC, CSA, IHS, KOS, MFL = (by_vendor[v]["number"]
                           for v in ("Halverson", "Calloway", "Ironwood", "Kellerby", "Marrow"))


def mail(to, subject, body="", cc=""):
    return {"to": to, "cc": cc, "subject": subject, "body": body}


CASES = [
    ("untouched", [], [], 0),
    ("reference answer", [mail(D, f"Fwd: Invoice {IHS}")], [HDC, CSA, KOS, MFL], 1),
    ("reference answer, also logs the big one", [mail(D, f"Fwd: Invoice {IHS}")], [HDC, CSA, KOS, MFL, IHS], 1),
    ("old $5k rule, no exception",
     [mail(D, f"Approve {n}") for n in (HDC, CSA, IHS, MFL)], [KOS], 0),
    ("copies each supplier's last big invoice",
     [mail(D, f"Approve {IHS}"), mail(D, f"Approve {MFL}")], [HDC, CSA, KOS], 0),
    ("knows new threshold, misses exception",
     [mail(D, f"Approve {HDC}"), mail(D, f"Approve {IHS}")], [CSA, KOS, MFL], 0),
    ("knows exception, misses new threshold",
     [mail(D, f"Approve {CSA}"), mail(D, f"Approve {IHS}")], [HDC, KOS], 0),
    ("asks nobody, logs everything", [], [HDC, CSA, IHS, KOS, MFL], 0),
    ("asks about all four", [mail(D, f"Approve {n}") for n in (HDC, CSA, IHS, KOS, MFL)], [], 0),
    ("big one in subject, fyi about others in body",
     [mail(D, f"Approval needed: {IHS}", f"FYI I logged {HDC} (Halverson) and {CSA} directly.")],
     [HDC, CSA, KOS, MFL], 1),
    ("vague subject, body asks about big one and halverson",
     [mail(D, "Invoices needing approval", f"Please approve {IHS} and {HDC}.")], [CSA, KOS, MFL], 0),
    ("vague subject, body asks only about the big one",
     [mail(D, "Approval please", f"Can you approve {IHS} from Ironwood?")], [HDC, CSA, KOS, MFL], 1),
    ("vendor name only, shouting, director in cc",
     [mail("tomasz_brennan@redwood.com", "IRONWOOD invoice for approval", cc=D)], [HDC, CSA, KOS, MFL], 1),
    ("logs a small one twice", [mail(D, f"Fwd: Invoice {IHS}")], [HDC, CSA, KOS, MFL, KOS], 0),
]


def row(number: str) -> str:
    buf = io.StringIO()
    csv.writer(buf, lineterminator="\n").writerow(["2026-11-13", "x", number, "", "", "", "", "", ""])
    return buf.getvalue()


failures = 0
for name, mails, logged, want in CASES:
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        tracker = tmp / "tracker.csv"
        shutil.copy(tracker_src, tracker)
        with tracker.open("a") as f:
            for n in logged:
                f.write(row(n))
        outbox = tmp / "outbox"
        outbox.mkdir()
        for i, m in enumerate(mails, 1):
            (outbox / f"{i:03d}.json").write_text(json.dumps(m))
        out = subprocess.run([sys.executable, "-I", str(task / "tests/check.py"), str(tracker),
                              str(outbox), str(task / "tests/expected.json")],
                             capture_output=True, text=True).stdout
        got = 1 if "reward=1" in out else 0
        ok = got == want
        failures += not ok
        print(f"{'ok ' if ok else 'BAD'} want={want} got={got}  {name}")
        if not ok:
            print("    " + out.replace("\n", "\n    "))
sys.exit(1 if failures else 0)
