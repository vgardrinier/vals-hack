"""Throw the obvious answer shapes at each drift task's grader, before any model run.

    python3 gen/test_drift_grader.py tasks/drift-*-k*

Per task: untouched, the reference answer, the old habit (missed the change), ignoring the
habit, the habit on everything, logging an invoice twice, and for the approver task the
tag variants (bare REVIEW, old tag, both tags, lowercase new tag).
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from test_ladder_grader import grade  # noqa: E402


def rows(exp: dict, decide) -> list[tuple[str, str]]:
    return [(i["number"], decide(i) or "") for i in exp["new"]]


def main() -> int:
    bad = 0
    for arg in sys.argv[1:]:
        task = Path(arg)
        exp = json.loads((task / "tests/expected.json").read_text())
        ref = rows(exp, lambda i: i["expect"])
        same = lambda r: int(r == ref)   # noqa: E731
        cases = [("untouched", [], 0), ("reference", ref, 1)]
        for name, r in [("old habit, missed the change", rows(exp, lambda i: i["alt"])),
                        ("ignores the habit", rows(exp, lambda i: None)),
                        ("REVIEW on everything", rows(exp, lambda i: "REVIEW"))]:
            cases.append((name, r, same(r)))
        small = next(i["number"] for i in exp["new"] if not i["expect"])
        cases.append(("logs one invoice twice", ref + [(small, "")], 0))
        if "approver" in task.name:
            for name, tag, want in [("bare REVIEW, no tag", "REVIEW", 0), ("old tag", "REVIEW - MA", 0),
                                    ("both tags", "REVIEW - MA/RQ", 0), ("lowercase new tag", "review - RQ", 1),
                                    ("tag written differently", "REVIEW (RQ)", 1)]:
                cases.append((name, rows(exp, lambda i, t=tag: t if i["expect"] else None), want))
        for name, r, want in cases:
            got = grade(task, r, [])
            ok = got == want
            bad += not ok
            print(f"{'ok ' if ok else 'BAD'} {task.name:20s} want={want} got={got}  {name}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
