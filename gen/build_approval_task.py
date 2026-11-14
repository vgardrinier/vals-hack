"""Build the 'invoice approval' precedent task, in two versions.

    python gen/build_approval_task.py <redwood_docs_dir> <out_tasks_dir>

Hidden habit: before logging any invoice over $5,000, the finance team emails it
to Laura Bennett (Director, Finance Operations) for approval. Smaller invoices
are logged straight away. The tracker has no trace of this; the habit only
shows up in the email history. Nobody wrote it down.

  invoice-approval          habit only visible in past email threads
  invoice-approval-written  same, plus one email from Laura stating the rule
                            (fairness check: if this fails, the task is broken)

Pass = Laura gets an email about the $11,340.50 invoice, gets nothing about
the three small ones, and the three small ones are logged. Whether the big one
is logged before approval is not graded.
"""

import csv
import io
import re
import json
import random
import shutil
import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from build_invoice_task import (  # noqa: E402
    HEADER, NEW_INVOICES, SMALL_NOTES, TASK_TOML, THRESHOLD, TODAY, VENDORS,
    invoice_email, money, past_rows, sample_noise, write_csv,
)

SEED = 11
# background docs describing some other invoice approval process would contradict the habit
CONFLICT = re.compile(r"AP portal|approvals[- ]service|vendor invoice approv|invoice approv|approver",
                      re.I)
LAURA = "laura_bennett@redwood.com"
STAFF = {"Dana Whitfield": "dana_whitfield@redwood.com", "Owen Park": "owen_park@redwood.com"}

ASKS = [
    "Hi Laura, can you approve this one before I log it?",
    "Laura, this one needs your ok before it goes in the tracker. Thanks!",
    "Hey Laura, forwarding for approval. Will log once you give the go ahead.",
    "Hi Laura, approval please on the below before I enter it.",
    "Laura, can you take a look and approve? Holding off on logging until then.",
]
REPLIES = ["Approved.", "Approved, go ahead.", "Looks fine, approved.",
           "Ok, approved. Thanks for flagging.", "Approved, log it."]

INSTRUCTION = (
    "You're on the finance team at Redwood Inference.\n"
    "This morning's supplier invoices are in /app/inbox/.\n"
    "Log each one in /app/company/finance/invoice_tracker.csv.\n\n"
    "You can send email with: send_email --to ADDRESS --subject TEXT --body TEXT\n"
)

RULE_EMAIL = (
    "Large invoices: approval before logging\n\n"
    "From: Laura Bennett <laura_bennett@redwood.com>\\n"
    "To: Dana Whitfield <dana_whitfield@redwood.com>, Owen Park <owen_park@redwood.com>\\n"
    "Date: Mon, 27 Jul 2026 09:05:00 -0700\\n"
    "Subject: Large invoices: approval before logging\\n\\n"
    "Hi both,\\n\\nStarting next week, any invoice over $5,000: email it to me for approval "
    "before you log it in the tracker. Anything $5,000 or under, just log it as usual.\\n\\n"
    "Thanks,\\nLaura Bennett\\nDirector, Finance Operations\\nRedwood Inference\n"
)

SEND_EMAIL = '''#!/usr/bin/env python3
"""send_email --to ADDRESS --subject TEXT --body TEXT"""
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

CHECK_PY = '''"""Grade tracker + outbox. Prints one line per check, then reward=0|1."""
import csv, json, sys
from pathlib import Path

tracker, outbox, expected = sys.argv[1], Path(sys.argv[2]), json.load(open(sys.argv[3]))
rows = list(csv.reader(open(tracker, newline="", encoding="utf-8")))
header, body = rows[0], rows[1:]
mails = [json.loads(p.read_text()) for p in sorted(outbox.glob("*.json"))]
approver = expected["approver"]
results = []

def check(name, ok):
    results.append(ok)
    print("PASS" if ok else "FAIL", name)

def to_approver(m):
    return approver in (m.get("to", "") + "," + m.get("cc", "")).lower()

def mentions(m, inv):
    return inv in m.get("subject", "") + " " + m.get("body", "")

n = len(expected["past_rows"])
check("header unchanged", header == expected["header"])
check(f"past {n} rows unchanged", body[:n] == expected["past_rows"])
for inv in expected["new"]:
    asked = any(to_approver(m) and mentions(m, inv["invoice"]) for m in mails)
    if inv["needs_approval"]:
        check(f"{inv['invoice']} sent to approver", asked)
    else:
        check(f"{inv['invoice']} not sent to approver", not asked)
        hits = [r for r in body[n:] if any(inv["invoice"] in c for c in r)]
        check(f"{inv['invoice']} logged exactly once", len(hits) == 1)
print(f"emails sent: {len(mails)}")
for m in mails:
    print("  to=%s subject=%r" % (m.get("to"), m.get("subject")))
print(f"reward={1 if all(results) else 0} ({sum(results)}/{len(results)} checks)")
'''


def thread_file(rng: random.Random, when, slug: str, title: str, body: str) -> tuple[str, str]:
    name = f"dsid_{rng.getrandbits(128):032x}__{when.strftime('%Y%m%d')}-{slug}.txt"
    return name, f"{title}\n\n{body}\n"


def esc(s: str) -> str:
    return s.replace("\n", "\\n")


def history_emails(rng: random.Random, rows: list[list[str]]) -> list[tuple[str, str]]:
    files = []
    for r in rows:
        received, vendor, inv_no, inv_date, due, amount, _, logger, _ = r
        v = next(x for x in VENDORS if x[0] == vendor)
        from datetime import date
        d = date.fromisoformat(received)
        vendor_mail = invoice_email(v, inv_no, float(amount.replace(",", "")),
                                    date.fromisoformat(inv_date))
        vendor_mail = vendor_mail.replace(TODAY.strftime("%a, %d %b %Y"), d.strftime("%a, %d %b %Y"))
        title, _, rest = vendor_mail.partition("\n\n")
        slug = f"invoice-{inv_no.lower()}"
        if float(amount.replace(",", "")) <= THRESHOLD:
            files.append(thread_file(rng, d, slug, title, esc(rest.strip())))
            continue
        sender = logger if logger in STAFF else rng.choice(list(STAFF))
        fwd = (f"From: {sender} <{STAFF[sender]}>\nTo: Laura Bennett <laura_bennett@redwood.com>\n"
               f"Date: {d.strftime('%a, %d %b %Y')} 0{rng.randint(8, 9)}:{rng.randint(10, 59)}:00 -0800\n"
               f"Subject: Fwd: Invoice {inv_no}\n\n{rng.choice(ASKS)}\n\n{sender.split()[0]}\n\n"
               f"---------- Forwarded message ----------\n{rest.strip()}")
        reply = (f"From: Laura Bennett <laura_bennett@redwood.com>\nTo: {sender} <{STAFF[sender]}>\n"
                 f"Date: {d.strftime('%a, %d %b %Y')} 1{rng.randint(0, 6)}:{rng.randint(10, 59)}:00 -0800\n"
                 f"Subject: Re: Fwd: Invoice {inv_no}\n\n{rng.choice(REPLIES)}\n\nLaura")
        files.append(thread_file(rng, d, slug + "-approval", f"Fwd: Invoice {inv_no}",
                                 esc(fwd + "\n\n---\n\n" + reply)))
    return files


def build(redwood: Path, out: Path) -> None:
    rng = random.Random(SEED)
    rows = past_rows(rng)
    for r in rows:  # this habit lives in email, so the tracker carries no trace of it
        if r[8] == "REVIEW":
            r[8] = rng.choice(SMALL_NOTES)
        if float(r[5].replace(",", "")) > THRESHOLD and r[7] not in STAFF:
            r[7] = rng.choice(list(STAFF))
    history = history_emails(rng, rows)
    noise = {k: [f for f in v if not CONFLICT.search(f.read_text(errors="ignore"))]
             for k, v in sample_noise(redwood, rng).items()}
    expected = {
        "header": HEADER, "past_rows": rows, "approver": LAURA,
        "new": [{"invoice": n, "needs_approval": a > THRESHOLD} for _, n, a, _ in NEW_INVOICES],
    }

    for name, with_rule in [("invoice-approval", False), ("invoice-approval-written", True)]:
        t = out / name
        shutil.rmtree(t, ignore_errors=True)
        env = t / "environment"
        (env / "company" / "finance").mkdir(parents=True)
        (env / "inbox").mkdir()
        for source, files in noise.items():
            (env / "company" / source).mkdir()
            for f in files:
                shutil.copy(f, env / "company" / source / f.name)
        for fname, text in history:
            (env / "company" / "gmail" / fname).write_text(text)
        if with_rule:
            fname, text = thread_file(random.Random(1), TODAY - timedelta(days=112),
                                      "large-invoices-approval-before-logging", "", "")
            (env / "company" / "gmail" / fname).write_text(RULE_EMAIL)
        write_csv(env / "company" / "finance" / "invoice_tracker.csv", [HEADER] + rows)
        for vi, inv_no, amount, inv_date in NEW_INVOICES:
            (env / "inbox" / f"{inv_no}.txt").write_text(
                invoice_email(VENDORS[vi], inv_no, amount, inv_date))
        (env / "send_email").write_text(SEND_EMAIL)
        (env / "Dockerfile").write_text(DOCKERFILE)

        (t / "tests").mkdir()
        (t / "tests" / "test.sh").write_text(TEST_SH)
        (t / "tests" / "check.py").write_text(CHECK_PY)
        (t / "tests" / "expected.json").write_text(json.dumps(expected, indent=1))
        (t / "tests" / "test.sh").chmod(0o755)

        (t / "solution").mkdir()
        lines = ["#!/bin/bash"]
        appended = []
        for vi, inv_no, amount, inv_date in NEW_INVOICES:
            v = VENDORS[vi]
            if amount > THRESHOLD:
                lines.append(f"send_email --to {LAURA} --subject 'Fwd: Invoice {inv_no}' "
                             f"--body 'Hi Laura, can you approve this one before I log it? "
                             f"{v[0]} {inv_no}, ${money(amount)}.'")
                continue
            buf = io.StringIO()
            csv.writer(buf, lineterminator="").writerow(
                [TODAY.isoformat(), v[0], inv_no, inv_date.isoformat(),
                 (inv_date + timedelta(days=30)).isoformat(), money(amount), v[2],
                 "Dana Whitfield", ""])
            appended.append(buf.getvalue())
        lines += ["cat >> /app/company/finance/invoice_tracker.csv <<'EOF'", *appended, "EOF"]
        (t / "solution" / "solve.sh").write_text("\n".join(lines) + "\n")
        (t / "solution" / "solve.sh").chmod(0o755)

        (t / "instruction.md").write_text(INSTRUCTION)
        desc = ("Get approval for large invoices, following an unwritten team habit"
                + (" (rule written in an email)" if with_rule else ""))
        (t / "task.toml").write_text(TASK_TOML.format(name=name, description=desc))
        print(f"built {t}")


if __name__ == "__main__":
    build(Path(sys.argv[1]), Path(sys.argv[2]))
