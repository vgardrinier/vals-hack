"""Dumb baselines: scripted, no-AI strategies on the round-2 messy monday tasks.

    python3 results/baselines.py          # round 2
    python3 results/baselines.py --v3     # messy monday v3

Each strategy reads only what an agent could read in the box (trackers, inbox, handbook),
writes the 15 new rows into a copy of the Q4 tracker, and is graded by the task's own
tests/check.py. If a dumb strategy scores high, the task has a shortcut.
"""

import csv
import io
import json
import re
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
V3 = "--v3" in sys.argv
VERSIONS = (["morning3-k2-nohandbook", "morning3-k3-nohandbook", "morning3-k5-nohandbook",
             "morning3-k2-handbook", "morning3-k3-handbook", "morning3-k5-handbook"] if V3 else
            ["morning2-k1-nohandbook", "morning2-k2-nohandbook", "morning2-k3-nohandbook",
             "morning2-k2-handbook", "morning2-k3-handbook"])
OUT = ROOT / "results" / ("baselines_v3.json" if V3 else "baselines.json")


def money(s: str) -> float:
    return float(s.replace(",", "").replace("$", "").strip())


def read_history(env: Path) -> tuple[list[str], list[list[str]], list[dict]]:
    fin = env / "company" / "finance"
    files = sorted((fin / "archive").glob("*.csv")) + [fin / "invoice_tracker_2026Q4.csv"]
    rows, header, q4 = [], None, None
    for f in files:
        r = list(csv.reader(open(f, newline="", encoding="utf-8")))
        header = r[0]
        if f.name == "invoice_tracker_2026Q4.csv":
            q4 = r
        rows += [dict(zip(r[0], x)) for x in r[1:]]
    rows.sort(key=lambda d: d["Received"])
    return header, q4, rows


def read_inbox(env: Path) -> list[dict]:
    out = []
    for f in sorted((env / "inbox").glob("*.txt")):
        t = f.read_text()
        vendor = re.search(r"^Invoice \S+ from (.+)$", t, re.M).group(1).strip()
        out.append({
            "number": re.search(r"Invoice number: (\S+)", t).group(1),
            "vendor": vendor,
            "inv_date": re.search(r"Invoice date: (\S+)", t).group(1),
            "due": re.search(r"Due date: (\S+)", t).group(1),
            "amount": money(re.search(r"Amount due: \$([\d,.]+)", t).group(1)),
        })
    return out


def handbook_cc() -> dict:
    # the stale policy's table (same in every version; read from the handbook build)
    hb = ROOT / "tasks" / ("morning3-k2-handbook" if V3 else "morning2-k2-handbook") / "environment" / "company" / "drive" / "AP_Policy_2026.md"
    return {m.group(1).strip(): m.group(2).strip()
            for m in re.finditer(r"^\| ([^|]+?) \| ([^|]+?) \|$", hb.read_text(), re.M)
            if m.group(1).strip() not in ("Supplier", "---")}


def band(a: float) -> str:
    return "big" if a > 10000 else ("mid" if a > 5000 else "small")


# --------------------------------------------------------------------------- strategies
# each returns (note, cost_center) for one new invoice given the history

def last_time(inv, hist, hb):
    same = [r for r in hist if r["Vendor"] == inv["vendor"]]
    return (same[-1]["Notes"], same[-1]["Cost Center"]) if same else ("", hb.get(inv["vendor"], ""))


def last_time_same_size(inv, hist, hb):
    same = [r for r in hist if r["Vendor"] == inv["vendor"] and band(money(r["Amount (USD)"])) == band(inv["amount"])]
    if not same:
        return last_time(inv, hist, hb)
    return same[-1]["Notes"], same[-1]["Cost Center"]


def follow_handbook(inv, hist, hb):
    return ("REVIEW" if inv["amount"] > 5000 else ""), hb.get(inv["vendor"], "")


def majority(inv, hist, hb):
    same = [r for r in hist if r["Vendor"] == inv["vendor"]]
    if not same:
        return follow_handbook(inv, hist, hb)
    note = Counter(r["Notes"] if re.search(r"review", r["Notes"], re.I) else "" for r in same).most_common(1)[0][0]
    cc = Counter(r["Cost Center"] for r in same).most_common(1)[0][0]
    return note, cc


def no_notes(inv, hist, hb):
    return "", last_time(inv, hist, hb)[1]


def flag_over_5k(inv, hist, hb):
    return ("REVIEW" if inv["amount"] > 5000 else ""), last_time(inv, hist, hb)[1]


STRATEGIES = {
    "copy last time for this supplier": last_time,
    "copy last time for this supplier, same size": last_time_same_size,
    "follow the handbook": follow_handbook,
    "majority for this supplier": majority,
    "log everything, no notes": no_notes,
    "flag everything over $5k": flag_over_5k,
}


def grade(task: Path, rows: list[list[str]], q4: list[list[str]]) -> float:
    with tempfile.TemporaryDirectory() as tmp:
        tracker = Path(tmp) / "t.csv"
        buf = io.StringIO()
        csv.writer(buf, lineterminator="\n").writerows(q4 + rows)
        tracker.write_text(buf.getvalue(), encoding="utf-8")
        out = subprocess.run([sys.executable, "-I", str(task / "tests" / "check.py"), str(tracker),
                              str(task / "tests" / "expected.json")], capture_output=True, text=True).stdout
    m = re.search(r"^score=([\d.]+)", out, re.M)
    return float(m.group(1)) if m else 0.0


def main() -> None:
    hb = handbook_cc()
    results = []
    for v in VERSIONS:
        task = ROOT / "tasks" / v
        env = task / "environment"
        header, q4, hist = read_history(env)
        inbox = read_inbox(env)
        for name, fn in STRATEGIES.items():
            new_rows = []
            for inv in inbox:
                note, cc = fn(inv, hist, hb)
                d = {"Received": "2026-11-13", "Vendor": inv["vendor"], "Invoice #": inv["number"],
                     "Invoice Date": inv["inv_date"], "Due Date": inv["due"],
                     "Amount (USD)": f"{inv['amount']:,.2f}", "Cost Center": cc,
                     "Logged By": "Baseline", "Notes": note}
                new_rows.append([d.get(h, "") for h in header])
            s = grade(task, new_rows, q4)
            results.append({"version": v, "handbook": "nohandbook" not in v, "strategy": name, "score": s})
    OUT.write_text(json.dumps(results, indent=1))

    print(f"{'strategy':46s} {'no handbook':>12s} {'handbook':>10s} {'all':>6s}  pass@1")
    for name in STRATEGIES:
        r = [x for x in results if x["strategy"] == name]
        nh = [x["score"] for x in r if not x["handbook"]]
        h = [x["score"] for x in r if x["handbook"]]
        allv = [x["score"] for x in r]
        p1 = sum(x == 1.0 for x in allv) / len(allv)
        print(f"{name:46s} {sum(nh)/len(nh)*100:11.0f}% {sum(h)/len(h)*100:9.0f}% {sum(allv)/len(allv)*100:5.0f}%  {p1*100:.0f}%")


if __name__ == "__main__":
    main()
