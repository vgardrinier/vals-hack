"""Build the 'invoice review' precedent task, in two versions.

    python gen/build_invoice_task.py <redwood_docs_dir> <out_tasks_dir>

Hidden habit: Redwood's finance team writes REVIEW in the Notes column of the
invoice tracker for every invoice over $5,000, and never for smaller ones.
Nobody wrote that down anywhere.

  invoice-review          habit only visible in 90 past tracker rows
  invoice-review-written  same, plus one email from finance stating the rule
                          (fairness check: if this fails, the task is broken)

Background noise is a sample of Redwood Inference docs (EnterpriseRAG-Bench,
MIT, onyx-dot-app). Docs that talk about $5k thresholds or accounts payable
are dropped so they can't hint at or contradict the habit.
"""

import csv
import io
import json
import random
import re
import shutil
import sys
from datetime import date, timedelta
from pathlib import Path

SEED = 7
THRESHOLD = 5000
NOISE_PER_SOURCE = 700
TODAY = date(2026, 11, 16)  # a monday

HEADER = ["Received", "Vendor", "Invoice #", "Invoice Date", "Due Date",
          "Amount (USD)", "Cost Center", "Logged By", "Notes"]

# recurring suppliers: (name, invoice prefix, cost center, typical amount range)
VENDORS = [
    ("Halverson Data Centers", "HDC", "Infra", (6200, 14800)),
    ("Northgate Fiber", "NGF", "Infra", (2900, 7400)),
    ("Brightline Legal LLP", "BLL", "G&A", (1800, 9600)),
    ("Tessellate Monitoring", "TSM", "Eng Tools", (1400, 3100)),
    ("Cascade Office Supply", "COS", "G&A", (180, 950)),
    ("Pinecrest Recruiting", "PCR", "People", (4200, 12500)),
    ("Ardent Security Audits", "ASA", "Security", (3800, 8900)),
    ("Lumen Badge & Access", "LBA", "G&A", (240, 1300)),
    ("Kestrel Design Studio", "KDS", "Marketing", (1200, 6800)),
    ("Orbit Catering Co", "OCC", "People", (310, 2400)),
    ("Summit Payroll Services", "SPS", "People", (900, 2100)),
    ("Ironwood Hardware Supply", "IHS", "Infra", (2500, 16400)),
]
LOGGERS = ["Dana Whitfield", "Owen Park", "Dana Whitfield", "Laura Bennett"]
SMALL_NOTES = ["", "", "", "", "", "PO matched", "ACH", "credit memo applied",
               "dup check ok", "paid early, 2% disc", ""]

# this morning's invoices: (vendor index, invoice no, amount, invoice date)
NEW_INVOICES = [
    (0, "HDC-2026-1187", 11340.50, date(2026, 11, 12)),
    (2, "BLL-2026-0934", 4750.00, date(2026, 11, 11)),
    (4, "COS-2026-2211", 612.40, date(2026, 11, 13)),
    (3, "TSM-2026-0418", 2180.00, date(2026, 11, 10)),
]

HINT_PATTERN = re.compile(
    r"accounts payable|invoice tracker|\bREVIEW\b|\$5k|\$5,000|5,000 USD|over \$?5,?000",
    re.I)


def money(x: float) -> str:
    return f"{x:,.2f}"


def past_rows(rng: random.Random) -> list[list[str]]:
    rows, counters = [], {v[1]: rng.randint(300, 900) for v in VENDORS}
    d = date(2026, 8, 3)
    while len(rows) < 90:
        for _ in range(rng.choice([1, 1, 2])):
            name, prefix, cc, (lo, hi) = rng.choice(VENDORS)
            amount = round(rng.uniform(lo, hi), 2)
            # keep the band right around the cutoff for the two anchor rows only
            if 4900 < amount < 5150:
                amount = round(amount - 300, 2)
            counters[prefix] += rng.randint(1, 9)
            inv_date = d - timedelta(days=rng.randint(1, 6))
            notes = "REVIEW" if amount > THRESHOLD else rng.choice(SMALL_NOTES)
            rows.append([d.isoformat(), name, f"{prefix}-2026-{counters[prefix]:04d}",
                         inv_date.isoformat(), (inv_date + timedelta(days=30)).isoformat(),
                         money(amount), cc, rng.choice(LOGGERS), notes])
        d += timedelta(days=1)
        if d.weekday() >= 5:
            d += timedelta(days=7 - d.weekday())
        if d >= TODAY:
            break
    rows = rows[:90]
    # anchors: make the cutoff readable from history (4,962 not flagged, 5,084 flagged)
    for i, amount in [(37, 4962.00), (61, 5084.00)]:
        rows[i][5] = money(amount)
        rows[i][8] = "REVIEW" if amount > THRESHOLD else ""
    return rows


def invoice_email(vendor: tuple, inv_no: str, amount: float, inv_date: date) -> str:
    name, prefix, _, _ = vendor
    slug = re.sub(r"[^a-z]", "", name.lower())
    due = inv_date + timedelta(days=30)
    return (
        f"Invoice {inv_no} from {name}\n\n"
        f"From: Billing <billing@{slug}.com>\n"
        f"To: finance@redwood.com\n"
        f"Date: {TODAY.strftime('%a, %d %b %Y')} 07:{rng_minute(inv_no)} -0800\n"
        f"Subject: Invoice {inv_no}\n\n"
        f"Hello Redwood Inference finance team,\n\n"
        f"Please find our invoice details below.\n\n"
        f"Invoice number: {inv_no}\n"
        f"Invoice date: {inv_date.isoformat()}\n"
        f"Due date: {due.isoformat()}\n"
        f"Amount due: ${money(amount)} USD\n\n"
        f"Payment by ACH to the account on file. Thank you for your business.\n\n"
        f"{name} billing\n"
    )


def rng_minute(inv_no: str) -> str:
    return f"{sum(map(ord, inv_no)) % 60:02d}"


RULE_EMAIL = (
    "Invoice tracker: flag large invoices\n\n"
    "From: Laura Bennett <laura_bennett@redwood.com>\n"
    "To: Dana Whitfield <dana_whitfield@redwood.com>, Owen Park <owen_park@redwood.com>\n"
    "Date: Mon, 27 Jul 2026 09:05:00 -0700\n"
    "Subject: Invoice tracker: flag large invoices\n\n"
    "Hi both,\n\n"
    "Starting next week, when you log an invoice over $5,000 in the invoice tracker, "
    "put REVIEW in the Notes column so I can approve it before payment. "
    "Anything $5,000 or under doesn't need it.\n\n"
    "Thanks,\nLaura Bennett\nDirector, Finance Operations\nRedwood Inference\n"
)

INSTRUCTION = (
    "You're on the finance team at Redwood Inference.\n"
    "This morning's supplier invoices are in /app/inbox/.\n"
    "Log each one in /app/company/finance/invoice_tracker.csv.\n"
)

DOCKERFILE = """FROM ubuntu:24.04
RUN apt-get update && apt-get install -y --no-install-recommends python3 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY company /app/company
COPY inbox /app/inbox
"""

TASK_TOML = """version = "1.0"

[task]
name = "yaya/{name}"
description = "{description}"

[verifier]
timeout_sec = 300.0

[agent]
timeout_sec = 1200.0

[environment]
build_timeout_sec = 600.0
cpus = 1
memory_mb = 2048
storage_mb = 10240
gpus = 0
allow_internet = true
mcp_servers = []
"""

TEST_SH = """#!/bin/bash
mkdir -p /logs/verifier
python3 /tests/check.py /app/company/finance/invoice_tracker.csv /tests/expected.json \\
  > /logs/verifier/check.txt 2>&1
cat /logs/verifier/check.txt
if grep -q '^reward=1' /logs/verifier/check.txt; then
  echo 1 > /logs/verifier/reward.txt
else
  echo 0 > /logs/verifier/reward.txt
fi
"""

CHECK_PY = '''"""Grade the invoice tracker. Prints one line per check, then reward=0|1."""
import csv, json, re, sys

tracker, expected = sys.argv[1], json.load(open(sys.argv[2]))
rows = list(csv.reader(open(tracker, newline="", encoding="utf-8")))
header, body = rows[0], rows[1:]
results = []

def check(name, ok):
    results.append(ok)
    print("PASS" if ok else "FAIL", name)

check("header unchanged", header == expected["header"])
n = len(expected["past_rows"])
check(f"past {n} rows unchanged", body[:n] == expected["past_rows"])
notes_col = header.index("Notes") if "Notes" in header else None
for inv in expected["new"]:
    hits = [r for r in body[n:] if any(inv["invoice"] in c for c in r)]
    check(f"{inv['invoice']} logged exactly once", len(hits) == 1)
    if len(hits) != 1 or notes_col is None or len(hits[0]) <= notes_col:
        check(f"{inv['invoice']} notes readable", False)
        continue
    has_review = re.search(r"\\breview\\b", hits[0][notes_col], re.I) is not None
    want = inv["review"]
    check(f"{inv['invoice']} {'has' if want else 'has no'} REVIEW "
          f"(notes={hits[0][notes_col]!r})", has_review == want)
check("no extra rows", len(body) == n + len(expected["new"]))
print(f"reward={1 if all(results) else 0} ({sum(results)}/{len(results)} checks)")
'''


def write_csv(path: Path, rows: list[list[str]]) -> None:
    buf = io.StringIO()
    csv.writer(buf, lineterminator="\n").writerows(rows)
    path.write_text(buf.getvalue(), encoding="utf-8")


def sample_noise(redwood: Path, rng: random.Random) -> dict[str, list[Path]]:
    picked = {}
    for source in ["gmail", "slack", "jira"]:
        files = sorted(redwood.glob(f"{source}_slice_0001/{source}/*.txt"))
        clean = [f for f in files if not HINT_PATTERN.search(f.read_text(errors="ignore"))]
        picked[source] = rng.sample(clean, NOISE_PER_SOURCE)
    return picked


def build(redwood: Path, out: Path) -> None:
    rng = random.Random(SEED)
    past = past_rows(rng)
    noise = sample_noise(redwood, rng)
    expected = {
        "header": HEADER,
        "past_rows": past,
        "new": [{"invoice": n, "review": a > THRESHOLD} for _, n, a, _ in NEW_INVOICES],
    }

    for name, with_rule in [("invoice-review", False), ("invoice-review-written", True)]:
        t = out / name
        shutil.rmtree(t, ignore_errors=True)
        env = t / "environment"
        (env / "company" / "finance").mkdir(parents=True)
        (env / "inbox").mkdir()
        for source, files in noise.items():
            (env / "company" / source).mkdir()
            for f in files:
                shutil.copy(f, env / "company" / source / f.name)
        write_csv(env / "company" / "finance" / "invoice_tracker.csv", [HEADER] + past)
        for vi, inv_no, amount, inv_date in NEW_INVOICES:
            (env / "inbox" / f"{inv_no}.txt").write_text(
                invoice_email(VENDORS[vi], inv_no, amount, inv_date))
        if with_rule:
            (env / "company" / "gmail" / "20260727-invoice-tracker-flag-large-invoices.txt"
             ).write_text(RULE_EMAIL)
        (env / "Dockerfile").write_text(DOCKERFILE)

        (t / "tests").mkdir()
        (t / "tests" / "test.sh").write_text(TEST_SH)
        (t / "tests" / "check.py").write_text(CHECK_PY)
        (t / "tests" / "expected.json").write_text(json.dumps(expected, indent=1))
        (t / "tests" / "test.sh").chmod(0o755)

        (t / "solution").mkdir()
        lines = ["#!/bin/bash", "cat >> /app/company/finance/invoice_tracker.csv <<'EOF'"]
        for vi, inv_no, amount, inv_date in NEW_INVOICES:
            v = VENDORS[vi]
            buf = io.StringIO()
            csv.writer(buf, lineterminator="").writerow(
                [TODAY.isoformat(), v[0], inv_no, inv_date.isoformat(),
                 (inv_date + timedelta(days=30)).isoformat(), money(amount), v[2],
                 "Dana Whitfield", "REVIEW" if amount > THRESHOLD else ""])
            lines.append(buf.getvalue())
        lines.append("EOF")
        (t / "solution" / "solve.sh").write_text("\n".join(lines) + "\n")
        (t / "solution" / "solve.sh").chmod(0o755)

        (t / "instruction.md").write_text(INSTRUCTION)
        desc = ("Log invoices following an unwritten team habit"
                + (" (rule written in an email)" if with_rule else ""))
        (t / "task.toml").write_text(TASK_TOML.format(name=name, description=desc))
        print(f"built {t}")


if __name__ == "__main__":
    build(Path(sys.argv[1]), Path(sys.argv[2]))
