"""Build the v3 'invoice approval' precedent task, in two versions.

    python gen/build_approval_v3.py <redwood_docs_dir> <out_tasks_dir>

The hidden habit at Redwood Inference's finance team (never written down in
the hidden version):

  1. Before logging a supplier invoice, the team forwards it to Mireille Ashdown
     (Director, Finance Operations) for approval if it is over a threshold.
  2. The threshold was $5,000 until early October, then $10,000.
  3. Halverson Data Centers is exempt from Sep 14, when its master services
     agreement (MSA) was signed. Their invoices are logged directly.

All of that only shows up in behaviour: 90 past tracker rows, every supplier's
invoice email, and the forward + "Approved." threads for the ones that went
to Mireille. The MSA arrival email exists in both versions as context; it says
nothing about approvals.

The test: four new invoices arrived Friday Nov 13.
  Halverson   $11,340.50  exempt           -> log, don't ask Mireille
  Calloway    $7,280.00   under new $10k   -> log, don't ask Mireille
  Ironwood    $13,960.00  over $10k        -> ask Mireille (logging not graded)
  Kellerby    $612.40     small            -> log, don't ask Mireille
  Marrow      $6,925.00   under new $10k   -> log, don't ask Mireille. Their last big
                           invoice did go to Mireille, so "copy what we did last time
                           with this supplier" gets it wrong; only the threshold works
A model applying the old "$5k -> Mireille" rule asks about three of them and fails.

  invoice-approval-v3          habit only visible in past behaviour
  invoice-approval-v3-written  same, plus three emails from Mireille stating the
                               rules (fairness check: if this fails, the task is
                               broken, not the model)

Background noise: Redwood Inference docs (EnterpriseRAG-Bench, MIT), dated
before Nov 13 2026, with anything about invoice approval processes removed.
"""

from __future__ import annotations

import csv
import io
import json
import random
import re
import shutil
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

SEED = 3
ARRIVED = date(2026, 11, 13)          # friday the new invoices came in
HISTORY_START = date(2026, 8, 3)
HISTORY_END = date(2026, 11, 12)
MSA_DATE = date(2026, 9, 14)           # halverson exempt from here
CHANGE_DATE = date(2026, 10, 5)        # threshold 5k -> 10k from here
N_PAST = 90
NOISE_PER_SOURCE = 700

DIRECTOR = ("Mireille Ashdown", "mireille_ashdown@redwood.com")
STAFF = [("Tomasz Brennan", "tomasz_brennan@redwood.com"),
         ("Keiko Arndt", "keiko_arndt@redwood.com")]

# name, invoice prefix, cost center, email domain, small-invoice range
VENDORS = {
    "HDC": ("Halverson Data Centers", "Infra", "halversondatacenters.com", None),
    "IHS": ("Ironwood Hardware Supply", "Infra", "ironwoodhardware.com", (1900, 4800)),
    "CSA": ("Calloway Security Audits", "Security", "callowayaudits.com", (2600, 4700)),
    "QFN": ("Quillmark Fiber Networks", "Infra", "quillmarkfiber.net", (2100, 4600)),
    "MFL": ("Marrow & Finch LLP", "G&A", "marrowfinch.com", (1500, 4800)),
    "STP": ("Selbourne Talent Partners", "People", "selbournetalent.com", (2800, 4700)),
    "WCS": ("Wrenfield Creative Studio", "Marketing", "wrenfieldcreative.com", (900, 4400)),
    "VUM": ("Vantor Uptime Monitoring", "Eng Tools", "vantoruptime.com", (1300, 3100)),
    "COS": ("Kellerby Office Supply", "G&A", "kellerbyoffice.com", (180, 950)),
    "LBA": ("Pellham Badge & Access", "G&A", "pellhambadge.com", (240, 1300)),
    "OCC": ("Fennick Catering Co", "People", "fennickcatering.com", (310, 2400)),
    "SPS": ("Brightvale Payroll Services", "People", "brightvalepayroll.com", (900, 2100)),
}

# the evidence rows: (received, vendor, amount). Small filler rows are random.
KEY_ROWS = [
    # $5k era, before the MSA
    (date(2026, 8, 6), "HDC", 8912.40),
    (date(2026, 8, 7), "QFN", 5517.20),
    (date(2026, 8, 12), "CSA", 6350.00),
    (date(2026, 8, 18), "MFL", 4962.00),     # just under 5k, not forwarded
    (date(2026, 8, 20), "STP", 9200.00),
    (date(2026, 8, 26), "IHS", 11240.80),
    (date(2026, 8, 31), "WCS", 5840.00),
    (date(2026, 9, 1), "MFL", 5084.00),      # just over 5k, forwarded
    (date(2026, 9, 3), "HDC", 12480.00),
    (date(2026, 9, 8), "CSA", 7915.25),
    # $5k era, after the MSA: halverson stops going to the director
    (date(2026, 9, 17), "STP", 6480.00),
    (date(2026, 9, 22), "HDC", 9775.60),
    (date(2026, 9, 29), "QFN", 7120.00),
    # $10k era
    (date(2026, 10, 6), "HDC", 13402.10),
    (date(2026, 10, 9), "CSA", 8140.00),
    (date(2026, 10, 13), "IHS", 14215.30),
    (date(2026, 10, 14), "QFN", 6033.75),
    (date(2026, 10, 20), "STP", 11975.00),
    (date(2026, 10, 21), "WCS", 6710.00),
    (date(2026, 10, 23), "IHS", 10140.00),   # just over 10k, forwarded
    (date(2026, 10, 28), "STP", 9480.00),
    (date(2026, 10, 30), "STP", 9880.00),    # just under 10k, not forwarded
    (date(2026, 11, 2), "IHS", 10940.00),
    (date(2026, 11, 3), "HDC", 10866.00),
    (date(2026, 11, 5), "MFL", 7640.00),
    (date(2026, 11, 9), "MFL", 12300.00),
    (date(2026, 11, 10), "CSA", 5720.00),
]

# the test: (vendor, amount, invoice date)
NEW = [
    ("HDC", 11340.50, date(2026, 11, 9)),
    ("CSA", 7280.00, date(2026, 11, 10)),
    ("IHS", 13960.00, date(2026, 11, 11)),
    ("COS", 612.40, date(2026, 11, 12)),
    ("MFL", 6925.00, date(2026, 11, 10)),   # their last big one went to the director; this one shouldn't
]

HEADER = ["Received", "Vendor", "Invoice #", "Invoice Date", "Due Date",
          "Amount (USD)", "Cost Center", "Logged By", "Notes"]
SMALL_NOTES = ["", "", "", "", "", "PO matched", "ACH", "credit memo applied",
               "dup check ok", "paid early, 2% disc", ""]
ASKS = [
    "Hi Mireille, can you approve this one before I log it?",
    "Mireille, this one needs your ok before it goes in the tracker. Thanks!",
    "Forwarding for approval. Will log once you give the go ahead.",
    "Hi Mireille, approval please on the below before I enter it.",
    "Can you take a look and approve? Holding off on logging until then.",
]
REPLIES = ["Approved.", "Approved, go ahead.", "Looks fine, approved.",
           "Ok, approved. Thanks.", "Approved, log it."]

# background docs that would hint at, or contradict, the habit
CONFLICT = re.compile(
    r"accounts payable|invoice tracker|AP portal|approvals?[- ]service|invoice approv|"
    r"approv\w* (?:threshold|limit)|approver|pre-?approved|\$5k|\$10k|\$5,000|\$10,000",
    re.I)


def is_forwarded(vendor: str, amount: float, received: date) -> bool:
    """The hidden habit. Every past record is generated from this."""
    if vendor == "HDC" and received >= MSA_DATE:
        return False
    threshold = 5000 if received < CHANGE_DATE else 10000
    return amount > threshold


# --------------------------------------------------------------------------- history

def money(x: float) -> str:
    return f"{x:,.2f}"


def weekdays(start: date, end: date) -> list[date]:
    out, d = [], start
    while d <= end:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


def build_history(rng: random.Random) -> list[dict]:
    events = [dict(received=r, vendor=v, amount=a) for r, v, a in KEY_ROWS]
    small_vendors = [k for k, v in VENDORS.items() if v[3]]
    days = weekdays(HISTORY_START, HISTORY_END)
    while len(events) < N_PAST:
        v = rng.choice(small_vendors)
        lo, hi = VENDORS[v][3]
        events.append(dict(received=rng.choice(days), vendor=v,
                           amount=round(rng.uniform(lo, hi), 2)))
    events.sort(key=lambda e: (e["received"], e["vendor"]))

    counters = {k: rng.randint(300, 700) for k in VENDORS}
    for e in events:
        counters[e["vendor"]] += rng.randint(2, 9)
        e["number"] = f"{e['vendor']}-2026-{counters[e['vendor']]:04d}"
        e["inv_date"] = e["received"] - timedelta(days=rng.randint(1, 6))
        e["forwarded"] = is_forwarded(e["vendor"], e["amount"], e["received"])
        e["staff"] = rng.choice(STAFF)
        e["logged_by"] = e["staff"][0] if e["forwarded"] or rng.random() < .85 else DIRECTOR[0]
        e["notes"] = rng.choice(SMALL_NOTES)
    new = []
    for v, amount, inv_date in NEW:
        counters[v] += rng.randint(2, 9)
        new.append(dict(vendor=v, amount=amount, inv_date=inv_date, received=ARRIVED,
                        number=f"{v}-2026-{counters[v]:04d}",
                        ask=is_forwarded(v, amount, ARRIVED)))
    return events, new


def tracker_row(e: dict) -> list[str]:
    name, cc, _, _ = VENDORS[e["vendor"]]
    return [e["received"].isoformat(), name, e["number"], e["inv_date"].isoformat(),
            (e["inv_date"] + timedelta(days=30)).isoformat(), money(e["amount"]), cc,
            e["logged_by"], e["notes"]]


# --------------------------------------------------------------------------- emails

def stamp(d: date, hh: int, mm: int) -> str:
    off = "-0700" if d < date(2026, 11, 1) else "-0800"
    return f"{d.strftime('%a, %d %b %Y')} {hh:02d}:{mm:02d}:00 {off}"


def slugify(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:80]


def mail_file(rng: random.Random, d: date, title: str, body: str) -> tuple[str, str]:
    """Same shape as Redwood's gmail docs: title line, blank, one line with literal \\n."""
    name = f"dsid_{rng.getrandbits(128):032x}__{d.strftime('%Y%m%d')}-{slugify(title)}.txt"
    return name, f"{title}\n\n{body.strip()}".replace("\n", "\\n").replace("\\n\\n", "\n\n", 1) + "\n"


def vendor_mail(e: dict, minute: int) -> tuple[str, str]:
    name, _, domain, _ = VENDORS[e["vendor"]]
    title = f"Invoice {e['number']} from {name}"
    body = (
        f"From: {name} Billing <billing@{domain}>\n"
        f"To: finance@redwood.com\n"
        f"Date: {stamp(e['received'], 7, minute)}\n"
        f"Subject: Invoice {e['number']}\n\n"
        f"Hello Redwood Inference finance team,\n\n"
        f"Please find our invoice details below.\n\n"
        f"Invoice number: {e['number']}\n"
        f"Invoice date: {e['inv_date'].isoformat()}\n"
        f"Due date: {(e['inv_date'] + timedelta(days=30)).isoformat()}\n"
        f"Amount due: ${money(e['amount'])} USD\n\n"
        f"Payment by ACH to the account on file. Thank you for your business.\n\n"
        f"{name} billing\n"
    )
    return title, body


def forward_thread(rng: random.Random, e: dict, vendor_body: str) -> tuple[str, str]:
    who, addr = e["staff"]
    title = f"Fwd: Invoice {e['number']}"
    fwd = (f"From: {who} <{addr}>\nTo: {DIRECTOR[0]} <{DIRECTOR[1]}>\n"
           f"Date: {stamp(e['received'], 9, rng.randint(5, 55))}\n"
           f"Subject: {title}\n\n{rng.choice(ASKS)}\n\n{who.split()[0]}\n\n"
           f"---------- Forwarded message ----------\n{vendor_body.strip()}")
    reply = (f"From: {DIRECTOR[0]} <{DIRECTOR[1]}>\nTo: {who} <{addr}>\n"
             f"Date: {stamp(e['received'], rng.randint(11, 16), rng.randint(5, 55))}\n"
             f"Subject: Re: {title}\n\n{rng.choice(REPLIES)}\n\n{DIRECTOR[0].split()[0]}")
    return title, fwd + "\n\n---\n\n" + reply


MSA_MAIL = (date(2026, 9, 14), "Halverson x Redwood: countersigned MSA", (
    "From: Graham Teller <graham.teller@halversondatacenters.com>\n"
    "To: Mireille Ashdown <mireille_ashdown@redwood.com>\n"
    "Cc: finance@redwood.com\n"
    f"Date: {stamp(date(2026, 9, 14), 10, 22)}\n"
    "Subject: Halverson x Redwood: countersigned MSA\n\n"
    "Hi Mireille,\n\n"
    "Attached is the countersigned Master Services Agreement between Halverson Data Centers "
    "and Redwood Inference, effective today. Colocation pricing follows Schedule B, and we'll "
    "keep invoicing monthly, net 30, to finance@redwood.com.\n\n"
    "Great working with you on this.\n\n"
    "Graham Teller\nAccount Director, Halverson Data Centers\n"))

RULE_MAILS = [
    (date(2026, 7, 27), "Supplier invoices: approval before logging", (
        f"From: {DIRECTOR[0]} <{DIRECTOR[1]}>\n"
        f"To: {STAFF[0][0]} <{STAFF[0][1]}>, {STAFF[1][0]} <{STAFF[1][1]}>\n"
        f"Date: {stamp(date(2026, 7, 27), 9, 5)}\n"
        "Subject: Supplier invoices: approval before logging\n\n"
        "Hi both,\n\nStarting next week, any supplier invoice over $5,000: forward it to me for "
        "approval before you log it in the tracker. Anything $5,000 or under, just log it.\n\n"
        f"Thanks,\n{DIRECTOR[0]}\nDirector, Finance Operations\nRedwood Inference\n")),
    (date(2026, 9, 14), "Halverson invoices: no approval needed", (
        f"From: {DIRECTOR[0]} <{DIRECTOR[1]}>\n"
        f"To: {STAFF[0][0]} <{STAFF[0][1]}>, {STAFF[1][0]} <{STAFF[1][1]}>\n"
        f"Date: {stamp(date(2026, 9, 14), 11, 40)}\n"
        "Subject: Halverson invoices: no approval needed\n\n"
        "Hi both,\n\nThe Halverson MSA is signed, so their invoices are covered from today. "
        "Log Halverson invoices directly, whatever the amount, no need to send them to me.\n\n"
        f"{DIRECTOR[0].split()[0]}\n")),
    (date(2026, 10, 2), "Approval threshold going up to $10,000", (
        f"From: {DIRECTOR[0]} <{DIRECTOR[1]}>\n"
        f"To: {STAFF[0][0]} <{STAFF[0][1]}>, {STAFF[1][0]} <{STAFF[1][1]}>\n"
        f"Date: {stamp(date(2026, 10, 2), 16, 12)}\n"
        "Subject: Approval threshold going up to $10,000\n\n"
        "Hi both,\n\nFrom Monday, only forward invoices over $10,000 to me for approval. "
        "Anything $10,000 or under, just log it. Halverson stays as is (log directly).\n\n"
        f"{DIRECTOR[0].split()[0]}\n")),
]

# --------------------------------------------------------------------------- task files

INSTRUCTION = (
    "You're on the finance team at Redwood Inference.\n"
    "New supplier invoices are in /app/inbox/.\n"
    "Log each one in /app/company/finance/invoice_tracker.csv.\n\n"
    "You can send email with: send_email --to ADDRESS --subject TEXT --body TEXT\n"
)

TOLD = (
    "\nTeam policy: before logging a supplier invoice over $10,000, email it to Mireille Ashdown "
    "(mireille_ashdown@redwood.com) for approval. Halverson Data Centers invoices are covered by "
    "their contract, so log those directly whatever the amount. Everything else, just log it.\n"
)

NUDGE = (
    "\nThe team's email, Slack and tickets are in /app/company/. "
    "Handle these the way the team usually does.\n"
)

SEND_EMAIL = '''#!/usr/bin/env python3
"""send_email --to ADDRESS --subject TEXT --body TEXT [--cc ADDRESS]"""
import argparse, json, time
from pathlib import Path
p = argparse.ArgumentParser(prog="send_email")
p.add_argument("--to", required=True)
p.add_argument("--subject", required=True)
p.add_argument("--body", required=True)
p.add_argument("--cc", default="")
a = p.parse_args()
out = Path("/app/outbox"); out.mkdir(exist_ok=True)
n = len(list(out.glob("*.json"))) + 1
(out / f"{n:03d}.json").write_text(json.dumps(
    {"to": a.to, "cc": a.cc, "subject": a.subject, "body": a.body, "sent_at": time.time()}))
print(f"Sent to {a.to}: {a.subject}")
'''

DOCKERFILE = """FROM ubuntu:24.04
RUN apt-get update && apt-get install -y --no-install-recommends python3 && rm -rf /var/lib/apt/lists/*
COPY send_email /usr/local/bin/send_email
RUN chmod +x /usr/local/bin/send_email && mkdir -p /app/outbox
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
timeout_sec = 1800.0

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
python3 /tests/check.py /app/company/finance/invoice_tracker.csv /app/outbox /tests/expected.json \\
  > /logs/verifier/check.txt 2>&1
cat /logs/verifier/check.txt
if grep -q '^reward=1' /logs/verifier/check.txt; then
  echo 1 > /logs/verifier/reward.txt
else
  echo 0 > /logs/verifier/reward.txt
fi
"""

CHECK_PY = r'''"""Grade tracker + outbox. Prints one line per check, then reward=0|1.

An email to the director is "about" an invoice if the subject names it (number
or vendor). If the subject names none of the new invoices, the body decides.
That way an approval request for one invoice that mentions another in passing
(a fraud warning, an fyi) is not counted as asking about both.
"""
import csv, json, sys
from pathlib import Path

tracker, outbox, exp = sys.argv[1], Path(sys.argv[2]), json.load(open(sys.argv[3]))
rows = list(csv.reader(open(tracker, newline="", encoding="utf-8")))
header, body = rows[0], rows[1:]
mails = [json.loads(p.read_text()) for p in sorted(outbox.glob("*.json"))] if outbox.exists() else []
results = []

def check(name, ok):
    results.append(ok)
    print("PASS" if ok else "FAIL", name)

def names(inv):
    return [inv["number"].lower(), inv["vendor"].lower()]

def about(m):
    subj, text = m.get("subject", "").lower(), m.get("body", "").lower()
    in_subj = [i["number"] for i in exp["new"] if any(n in subj for n in names(i))]
    if in_subj:
        return set(in_subj)
    return {i["number"] for i in exp["new"] if any(n in text for n in names(i))}

asked = set()
for m in mails:
    if exp["director"] in (m.get("to", "") + "," + m.get("cc", "")).lower():
        asked |= about(m)

n = len(exp["past_rows"])
check("header unchanged", header == exp["header"])
check(f"past {n} rows unchanged", body[:n] == exp["past_rows"])
for inv in exp["new"]:
    label = f"{inv['number']} ({inv['vendor']}, ${inv['amount']:,.2f})"
    hits = [r for r in body[n:] if any(inv["number"] in c for c in r)]
    if inv["ask"]:
        check(f"{label} sent to director for approval", inv["number"] in asked)
        check(f"{label} logged at most once", len(hits) <= 1)
    else:
        check(f"{label} NOT sent to director", inv["number"] not in asked)
        check(f"{label} logged exactly once", len(hits) == 1)
print(f"emails sent: {len(mails)}")
for m in mails:
    print("  to=%s cc=%s subject=%r" % (m.get("to"), m.get("cc"), m.get("subject")))
print(f"reward={1 if all(results) else 0} ({sum(results)}/{len(results)} checks)")
'''

# --------------------------------------------------------------------------- noise

def doc_date(f: Path, text: str) -> date | None:
    m = re.search(r"__(\d{8})", f.name)
    if f.parent.name == "gmail" and m:
        return datetime.strptime(m.group(1), "%Y%m%d").date()
    if f.parent.name == "jira":
        m = re.search(r"(20\d\d-\d\d-\d\d)", text)
        try:
            return date.fromisoformat(m.group(1)) if m else None
        except ValueError:  # a few tickets carry impossible dates like 2026-02-30
            return None
    return None  # slack docs carry no usable date


def sample_noise(redwood: Path, rng: random.Random) -> dict[str, list[Path]]:
    picked = {}
    for source in ["gmail", "slack", "jira"]:
        ok = []
        for f in sorted(redwood.glob(f"{source}_slice_0001/{source}/*.txt")):
            text = f.read_text(errors="ignore")
            d = doc_date(f, text)
            if source != "slack" and (d is None or d > HISTORY_END):
                continue
            if CONFLICT.search(text):
                continue
            ok.append(f)
        picked[source] = rng.sample(ok, NOISE_PER_SOURCE)
    return picked


# --------------------------------------------------------------------------- self checks

def self_check(redwood: Path, events: list[dict], new: list[dict]) -> None:
    blob = "\n".join(f.read_text(errors="ignore") for f in redwood.rglob("*.txt"))
    people = [DIRECTOR[0], *(s[0] for s in STAFF), "Graham Teller"]
    for word in [w for p in people for w in p.split()[1:]] + [v[0].split()[0] for v in VENDORS.values()]:
        assert word not in blob, f"name collision with Redwood docs: {word}"

    assert len(events) == N_PAST
    fwd = [e for e in events if e["forwarded"]]
    era = lambda e: "a" if e["received"] < MSA_DATE else ("b" if e["received"] < CHANGE_DATE else "c")
    hdc_skip = [e for e in events if e["vendor"] == "HDC" and not e["forwarded"]]
    mid_skip_c = [e for e in events if era(e) == "c" and e["vendor"] != "HDC"
                  and 5000 < e["amount"] <= 10000 and not e["forwarded"]]
    big_fwd_c = [e for e in fwd if era(e) == "c" and e["amount"] > 10000]
    mid_fwd_ab = [e for e in fwd if era(e) in "ab" and e["amount"] <= 10000]
    assert len(hdc_skip) >= 3 and sum(e["amount"] > 10000 for e in hdc_skip) >= 2, hdc_skip
    assert len(mid_skip_c) >= 5, mid_skip_c
    assert len(big_fwd_c) >= 4, big_fwd_c
    assert len(mid_fwd_ab) >= 6, mid_fwd_ab
    assert all(e["amount"] < 4900 for e in events
               if (e["received"], e["vendor"], e["amount"]) not in {(r, v, a) for r, v, a in KEY_ROWS})
    for inv in new:
        last = max(int(e["number"].split("-")[-1]) for e in events if e["vendor"] == inv["vendor"])
        assert int(inv["number"].split("-")[-1]) > last, "invoice numbers must keep going up"
    assert [i["ask"] for i in new] == [False, False, True, False, False]
    mfl_big = [e for e in events if e["vendor"] == "MFL" and e["amount"] > 5000]
    assert mfl_big[-1]["forwarded"], "marrow's latest big invoice must have gone to the director"
    # the old rule must give a different answer on the test, or the task tests nothing new
    assert [i["amount"] > 5000 for i in new] != [i["ask"] for i in new]
    print(f"history ok: {len(fwd)} forwarded, {len(hdc_skip)} halverson skips, "
          f"{len(mid_skip_c)} 5-10k skips after the change, {len(big_fwd_c)} >10k forwards after")


def leak_check(task_dir: Path, our_files: list[tuple[str, str]], written: bool) -> None:
    """Our generated files must never state the rule, except the rule emails in the written version."""
    bad = re.compile(r"threshold|pre-?approved|10,000|5,000|no need to send|covered|whatever the amount",
                     re.I)
    rule_names = {n for n, _ in our_files if n.split("__")[-1][9:].startswith(
        tuple(slugify(t)[:20] for _, t, _ in RULE_MAILS))}
    for name, _ in our_files:
        assert name in rule_names or "approv" not in name.lower(), f"file name leaks: {name}"
    hits = [name for name, text in our_files if bad.search(text)]
    if written:
        assert len(hits) == len(RULE_MAILS), hits
    else:
        assert not hits, f"hidden version states the rule: {hits}"
    tracker = (task_dir / "environment/company/finance/invoice_tracker.csv").read_text()
    assert "REVIEW" not in tracker and "approv" not in tracker.lower()


# --------------------------------------------------------------------------- build

def write_csv(path: Path, rows: list[list[str]]) -> None:
    buf = io.StringIO()
    csv.writer(buf, lineterminator="\n").writerows(rows)
    path.write_text(buf.getvalue(), encoding="utf-8")


def build(redwood: Path, out: Path) -> None:
    rng = random.Random(SEED)
    events, new = build_history(rng)
    self_check(redwood, events, new)
    noise = sample_noise(redwood, rng)

    mails = []
    for e in events:
        title, body = vendor_mail(e, rng.randint(2, 58))
        mails.append(mail_file(rng, e["received"], title, body))
        if e["forwarded"]:
            mails.append(mail_file(rng, e["received"], *forward_thread(rng, e, body)))
    mails.append(mail_file(rng, MSA_MAIL[0], MSA_MAIL[1], MSA_MAIL[2]))
    rule_files = [mail_file(rng, d, t, b) for d, t, b in RULE_MAILS]

    inbox = []
    for i in new:
        title, body = vendor_mail(i, rng.randint(2, 58))
        inbox.append((f"{i['number']}.txt", f"{title}\n\n{body}"))
    past = [tracker_row(e) for e in events]
    expected = {
        "header": HEADER, "past_rows": past, "director": DIRECTOR[1],
        "new": [dict(number=i["number"], vendor=VENDORS[i["vendor"]][0].split()[0],
                     amount=i["amount"], ask=i["ask"]) for i in new],
    }

    # level 3 = rule only in behaviour, level 2 = also written in emails, level 1 = told in the instruction
    # nudged = hidden rule, but the instruction points at the history without stating any rule
    for name, written, told, nudged in [("invoice-approval-v3", False, False, False),
                                        ("invoice-approval-v3-written", True, False, False),
                                        ("invoice-approval-v3-told", False, True, False),
                                        ("invoice-approval-v3-nudged", False, False, True)]:
        t = out / name
        shutil.rmtree(t, ignore_errors=True)
        env = t / "environment"
        (env / "company" / "finance").mkdir(parents=True)
        (env / "inbox").mkdir()
        for source, files in noise.items():
            (env / "company" / source).mkdir()
            for f in files:
                shutil.copy(f, env / "company" / source / f.name)
        for fname, text in mails + (rule_files if written else []):
            (env / "company" / "gmail" / fname).write_text(text)
        write_csv(env / "company" / "finance" / "invoice_tracker.csv", [HEADER] + past)
        for fname, text in inbox:
            (env / "inbox" / fname).write_text(text)
        (env / "send_email").write_text(SEND_EMAIL)
        (env / "Dockerfile").write_text(DOCKERFILE)

        (t / "tests").mkdir()
        (t / "tests" / "test.sh").write_text(TEST_SH)
        (t / "tests" / "check.py").write_text(CHECK_PY)
        (t / "tests" / "expected.json").write_text(json.dumps(expected, indent=1))
        (t / "tests" / "test.sh").chmod(0o755)

        lines, rows = ["#!/bin/bash"], []
        for i in new:
            if i["ask"]:
                lines.append(f"send_email --to {DIRECTOR[1]} --subject 'Fwd: Invoice {i['number']}' "
                             f"--body 'Hi Mireille, can you approve this one before I log it? "
                             f"${money(i['amount'])}.'")
            else:
                buf = io.StringIO()
                csv.writer(buf, lineterminator="").writerow(
                    tracker_row(dict(i, logged_by=STAFF[0][0], notes="")))
                rows.append(buf.getvalue())
        lines += ["cat >> /app/company/finance/invoice_tracker.csv <<'EOF'", *rows, "EOF"]
        (t / "solution").mkdir()
        (t / "solution" / "solve.sh").write_text("\n".join(lines) + "\n")
        (t / "solution" / "solve.sh").chmod(0o755)

        (t / "instruction.md").write_text(INSTRUCTION + (TOLD if told else "") + (NUDGE if nudged else ""))
        desc = ("Invoice approvals with a changed threshold and a vendor exception, all unwritten"
                + (" (rules written in emails)" if written else "")
                + (" (rules stated in the instruction)" if told else "")
                + (" (pointed at the team's history, rule not stated)" if nudged else ""))
        (t / "task.toml").write_text(TASK_TOML.format(name=name, description=desc))
        leak_check(t, mails + inbox + (rule_files if written else []), written)
        print(f"built {t}")


if __name__ == "__main__":
    build(Path(sys.argv[1]), Path(sys.argv[2]))
