"""Label every failed drift attempt with how it missed, in place in results/drift_attempts.json.

    python3 results/classify_drift.py

  kept old habit   every invoice where old and new habit disagree got the old treatment
  overcorrected    dropped the habit on an invoice where it still applies (e.g. no REVIEW on a
                   $13,960 invoice after the cutoff moved to $10k, or REVIEW with no approver tag)
  left approver open  approver task: wrote REVIEW without the approver's initials
  bookkeeping      an invoice not logged exactly once, or past rows / header changed
  (then run tag_hesitation.py: "left blank, asked" when the agent saw the habit but wouldn't apply it)
  mixed            anything else (some invoices old way, some new)
"""

import json
import re
from collections import Counter
from pathlib import Path

HERE = Path(__file__).parent
TASKS = HERE.parent / "tasks"


def actual(check: str, inv: dict):
    """What the agent actually wrote for this invoice, read back from its grader line."""
    m = re.search(r"note='([^']*)'", check)
    if m:
        note = m.group(1)
        if not re.search(r"\breview\b", note, re.I):
            return None
        t = re.search(r"\b(MA|RQ)\b", note)
        return f"REVIEW - {t.group(1)}" if t else "REVIEW"
    passed = check.startswith("PASS")
    has_line = " has REVIEW" in check
    wrote_review = passed if has_line else not passed
    return "REVIEW" if wrote_review else None


def classify(a: dict) -> str:
    if a["reward"] == 1:
        return "pass"
    checks = a["checks"]
    if any(c.startswith("FAIL") and ("logged exactly once" in c or "unchanged" in c) for c in checks):
        return "bookkeeping"
    exp = json.loads((TASKS / re.sub(r"-r\d+$", "", a["task"]) / "tests/expected.json").read_text())
    got = {}
    for inv in exp["new"]:
        line = next((c for c in checks if inv["number"] in c and "REVIEW" in c), None)
        if line:
            got[inv["number"]] = actual(line, inv)
    disagree = [i for i in exp["new"] if i["expect"] != i["alt"]]
    still = [i for i in exp["new"] if i["expect"] and i["expect"] == i["alt"]]
    if disagree and all(got.get(i["number"]) == i["alt"] for i in disagree):
        return "kept old habit"
    if "approver" in a["task"] and all(got.get(i["number"]) == "REVIEW" for i in exp["new"] if i["expect"]):
        return "left approver open"   # wrote REVIEW but no initials ("pending approver"): read the tag as a sign-off
    if any(got.get(i["number"]) != i["expect"] for i in still) or \
            any(i["expect"] and got.get(i["number"]) not in (i["expect"], i["alt"]) for i in exp["new"]):
        return "overcorrected"
    return "mixed"


attempts = json.loads((HERE / "drift_attempts.json").read_text())
for a in attempts:
    if a["status"] == "FINISHED" and a["reward"] is not None:
        a["kind_of_miss"] = classify(a)
(HERE / "drift_attempts.json").write_text(json.dumps(attempts, indent=1))
for m in sorted({a["model"] for a in attempts}):
    c = Counter(a.get("kind_of_miss") for a in attempts if a["model"] == m and a.get("kind_of_miss") != "pass")
    print(f"{m:20s}", dict(c))
print("by type:")
for t in ["cutoff", "stopped", "approver", "returned"]:
    print(f"  {t:9s}", dict(Counter(a.get("kind_of_miss") for a in attempts if a["type"] == t and a.get("kind_of_miss") != "pass")))
