"""Implicit Action Bench (invoices track), second job: customer refund requests at Redwood Inference's support team.

    python3 gen/build_refunds.py <redwood_docs_dir> <out_dir>

The support team keeps a refunds log (three quarterly CSV files). Each request gets a decision
(credit / refund / deny), an approver for refunds, and sometimes a note. How the team decides lives
only in that history; nothing current is written down. Some habits changed this autumn.

Habits (the current practice, i.e. the answer key):
  L1 (4 habits)
    1. cutoff: credit up to the cutoff, cash refund above it. Cutoff $500 until Oct 5, $1,000 since.
    2. Dedicated-tier customers always get a credit, never a refund (stable).
    3. approver: refunds approved by Nadia Thorsby; since Oct 5 Private-tier refunds by Lucas Fairbairn.
    4. outage requests get the note "SLA credit" (stable).
  L2 (8 habits) adds
    5. Harrowgate Bank (contract signed Nov 2): every request is a refund approved by Lucas Fairbairn.
    6. a re-sent request (same customer, amount and reason as one already logged) is denied, note "DUPLICATE".
    7. unused prepaid credits are never refunded: deny (stable).
    8. since Oct 19, billing-error refunds over $2,000 get the note "finance check" (two conditions).
  L3 = L2 + last January's support policy in the drive (states the rules of that time).
  TOLD = L3 with the current rules stated in the instruction (fairness control).

Dose k = recent rows showing each changed habit where the old and new answers differ.
Every past row comes from the rule functions below, so history and answer key can't disagree.
"""
from __future__ import annotations

import csv
import io
import json
import random
import re
import shutil
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import build_approval_v3 as v3  # noqa: E402

SEED = 77
CHANGE = date(2026, 10, 5)
FIN_DATE = date(2026, 10, 19)
CONTRACT = date(2026, 11, 2)
ARRIVED = date(2026, 11, 13)
QUARTERS = [("2026Q2", date(2026, 4, 1), date(2026, 6, 30)),
            ("2026Q3", date(2026, 7, 1), date(2026, 9, 30)),
            ("2026Q4", date(2026, 10, 1), date(2026, 11, 12))]
LIVE = "refunds_log_2026Q4.csv"
HEADER = ["Received", "Ticket", "Customer", "Tier", "Amount (USD)", "Reason", "Decision", "Approver", "Notes"]
NADIA, LUCAS = "Nadia Thorsby", "Lucas Fairbairn"
STAFF = ["Ines Mossgiel", "Theo Rosemount", "Mara Sablewood"]   # who logs (not graded)

CUSTOMERS = {   # name: tier
    "Brambleworth Analytics": "Hosted", "Cindervale Labs": "Hosted", "Dunmore Health": "Private",
    "Ellingham Retail": "Hosted", "Farrowdale Logistics": "Dedicated", "Glenhaven Media": "Hosted",
    "Harrowgate Bank": "Private", "Islington Robotics": "Private", "Juniperline Games": "Hosted",
    "Kestrelmoor Insurance": "Dedicated", "Quillfeather Studio": "Hosted", "Ashgrove Biotech": "Private",
    "Ostrava Freight": "Hosted", "Tamsin Learning": "Dedicated",
}
REASONS_L1 = ["outage", "billing error", "downgrade", "overcharge"]
REASONS_L2 = REASONS_L1 + ["unused credits"]
REASON_TEXT = {
    "outage": "we lost service during the incident and our jobs failed, please compensate us",
    "billing error": "the invoice shows usage we did not run, it looks like a billing error",
    "downgrade": "we moved to a smaller plan mid-cycle and were still charged the old rate",
    "overcharge": "we were charged above our contracted rate this month",
    "unused credits": "we have unused prepaid credits we will not use and would like the money back",
}


# --------------------------------------------------------------------------- the rules

def cutoff(d: date) -> float:
    return 500 if d < CHANGE else 1000


def approver(tier: str, d: date) -> str:
    return LUCAS if (tier == "Private" and d >= CHANGE) else NADIA


def current(c: str, amt: float, reason: str, d: date, dup: bool, l2: bool) -> tuple[str, str, str]:
    """(decision, approver, note) the team would record today."""
    tier = CUSTOMERS[c]
    if l2 and dup:
        return "deny", "", "DUPLICATE"
    if l2 and reason == "unused credits":
        return "deny", "", ""
    note = "SLA credit" if reason == "outage" else ""
    if l2 and c == "Harrowgate Bank" and d >= CONTRACT:
        return "refund", LUCAS, note
    if tier == "Dedicated":
        return "credit", "", note
    if amt > cutoff(d):
        if l2 and reason == "billing error" and amt > 2000 and d >= FIN_DATE:
            note = "finance check"
        return "refund", approver(tier, d), note
    return "credit", "", note


def old(c: str, amt: float, reason: str, l2: bool) -> tuple[str, str, str]:
    """January's policy / the never-noticed answer."""
    if l2 and reason == "unused credits":
        return "deny", "", ""
    note = "SLA credit" if reason == "outage" else ""
    if CUSTOMERS[c] == "Dedicated":
        return "credit", "", note
    return ("refund", NADIA, note) if amt > 500 else ("credit", "", note)


# --------------------------------------------------------------------------- history

def weekdays(a: date, b: date) -> list[date]:
    out, d = [], a
    while d <= b:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


def is_evidence(e: dict, l2: bool) -> str | None:
    """Which changed habit this row shows (old and new answers differ), or None."""
    c, a, r, d = e["customer"], e["amount"], e["reason"], e["received"]
    tier = CUSTOMERS[c]
    if e.get("dup"):
        return None
    if l2 and c == "Harrowgate Bank" and d >= CONTRACT and r != "unused credits" and a <= 1000:
        return "contract"
    if l2 and r == "unused credits":
        return None
    if tier == "Dedicated" or (l2 and c == "Harrowgate Bank"):
        return None
    if d >= CHANGE and 500 < a <= 1000:
        return "cutoff"
    if d >= CHANGE and tier == "Private" and a > 1000:
        return "approver"
    if l2 and d >= FIN_DATE and r == "billing error" and a > 2000:
        return "finance"
    return None


def build_history(rng: random.Random, dose: int, l2: bool) -> list[dict]:
    days = weekdays(QUARTERS[0][1], QUARTERS[-1][2])
    reasons = REASONS_L2 if l2 else REASONS_L1
    custs = [c for c in CUSTOMERS if l2 or c != "Harrowgate Bank"]
    ev: list[dict] = []

    def add(d, c, a, r, dup=False):
        ev.append(dict(received=d, customer=c, amount=round(a, 2), reason=r, dup=dup))

    # background rows: never evidence of a change (filtered), so doses stay exact
    while len(ev) < 250:
        d = rng.choice(days)
        c = rng.choice(custs)
        a = rng.choice([rng.uniform(60, 480), rng.uniform(60, 480), rng.uniform(520, 990), rng.uniform(1100, 4800)])
        r = rng.choice(reasons)
        cand = dict(received=d, customer=c, amount=round(a, 2), reason=r, dup=False)
        if is_evidence(cand, l2):
            continue
        if l2 and c == "Harrowgate Bank" and d >= CONTRACT:
            continue
        ev.append(cand)
    # make the old habits clearly visible before the changes
    pre = weekdays(date(2026, 7, 1), CHANGE - timedelta(days=1))
    for i in range(6):
        add(pre[i * 9 + 2], rng.choice(["Glenhaven Media", "Juniperline Games", "Quillfeather Studio"]),
            rng.uniform(560, 960), "overcharge")                                  # mid refunds, Nadia
        add(pre[i * 9 + 5], rng.choice(["Dunmore Health", "Islington Robotics", "Ashgrove Biotech"]),
            rng.uniform(1300, 3800), rng.choice(["downgrade", "overcharge"]))    # Private refunds, Nadia
    # exactly `dose` recent rows per changed habit
    post = weekdays(CHANGE + timedelta(days=3), date(2026, 11, 12))
    for i in range(dose):
        add(post[2 + i * 3], rng.choice(["Ellingham Retail", "Ostrava Freight", "Brambleworth Analytics"]),
            rng.uniform(560, 960), rng.choice(["overcharge", "downgrade"]))       # cutoff
        add(post[3 + i * 3], rng.choice(["Dunmore Health", "Islington Robotics", "Ashgrove Biotech"]),
            rng.uniform(1300, 3800), rng.choice(["downgrade", "overcharge"]))    # approver
    if not l2:   # contrast for the new cutoff: ordinary refunds just above $1,000 after Oct 5
        for i in range(3):
            add(post[1 + i * 4], rng.choice(["Glenhaven Media", "Quillfeather Studio", "Juniperline Games"]),
                rng.uniform(1030, 1180), "overcharge")
    if l2:
        pre_c = weekdays(date(2026, 8, 3), date(2026, 10, 30))
        for i in range(5):
            add(pre_c[i * 11 + 1], "Harrowgate Bank", rng.uniform(120, 940), rng.choice(["overcharge", "downgrade"]))
        con = weekdays(CONTRACT + timedelta(days=1), date(2026, 11, 12))
        for i in range(dose):
            add(con[i], "Harrowgate Bank", rng.uniform(150, 900), rng.choice(["overcharge", "downgrade"]))  # contract
        pre_f = weekdays(date(2026, 6, 1), FIN_DATE - timedelta(days=1))
        for i in range(4):
            add(pre_f[i * 13 + 4], rng.choice(["Glenhaven Media", "Cindervale Labs"]), rng.uniform(2200, 4600),
                "billing error")                                                  # finance: old (no note)
        fin = weekdays(FIN_DATE + timedelta(days=1), date(2026, 11, 12))
        for i in range(dose):
            add(fin[1 + i * 2], rng.choice(["Juniperline Games", "Ellingham Retail", "Quillfeather Studio"]),
                rng.uniform(2200, 4600), "billing error")                          # finance
        # contrast rows so the finance habit is readable: billing-error refunds between $1,000 and $2,000
        # (no note) and Dedicated billing errors over $2,000 (credit, no note) after Oct 19
        for i in range(3):
            add(fin[2 + i * 2], rng.choice(["Ostrava Freight", "Cindervale Labs", "Glenhaven Media"]),
                rng.uniform(1030, 1180), "billing error")
        for i in range(2):
            add(fin[3 + i * 3], rng.choice(["Farrowdale Logistics", "Kestrelmoor Insurance", "Tamsin Learning"]),
                rng.uniform(2200, 4400), "billing error")
        # stable duplicate habit: a few re-sent requests over the months
        for i in range(6):
            src = rng.choice([e for e in ev if not e["dup"] and e["customer"] != "Harrowgate Bank"])
            add(src["received"] + timedelta(days=rng.randint(2, 6)), src["customer"], src["amount"], src["reason"], dup=True)
    ev.sort(key=lambda e: (e["received"], e["customer"], e["amount"]))
    for i, e in enumerate(ev):
        e["ticket"] = f"RF-{4100 + i * 3 + rng.randint(0, 2)}"
        e["decision"], e["approver"], e["note"] = current(e["customer"], e["amount"], e["reason"], e["received"], e["dup"], l2)
        e["logged_by"] = rng.choice(STAFF)
    return ev


def new_batch(rng: random.Random, ev: list[dict], l2: bool) -> list[dict]:
    """15 open requests, a realistic mix that exercises every habit of the level."""
    plan = [("Cindervale Labs", 240, "downgrade"), ("Ellingham Retail", 760, "overcharge"),
            ("Islington Robotics", 680, "downgrade"), ("Dunmore Health", 2380, "overcharge"),
            ("Glenhaven Media", 1840, "overcharge"), ("Kestrelmoor Insurance", 2960, "billing error"),
            ("Brambleworth Analytics", 180, "outage"), ("Ostrava Freight", 1460, "outage"),
            ("Ashgrove Biotech", 310, "overcharge"), ("Quillfeather Studio", 120, "downgrade"),
            ("Juniperline Games", 905, "downgrade"), ("Tamsin Learning", 640, "outage")]
    if l2:
        last_dupable = [e for e in ev if not e["dup"] and e["received"] >= date(2026, 11, 2)
                        and e["customer"] not in ("Harrowgate Bank",) and CUSTOMERS[e["customer"]] != "Dedicated"]
        src = sorted(last_dupable, key=lambda e: e["received"])[-1]
        plan = plan[:9] + [("Harrowgate Bank", 640, "overcharge"), ("Ellingham Retail", 880, "unused credits"),
                           ("Glenhaven Media", 2640, "billing error"), ("Juniperline Games", 1210, "billing error"),
                           ("Farrowdale Logistics", 2960, "billing error")]
        plan.append((src["customer"], src["amount"], src["reason"]))   # re-sent request
    else:
        plan += [("Farrowdale Logistics", 1290, "overcharge"), ("Islington Robotics", 1720, "overcharge"),
                 ("Cindervale Labs", 2210, "billing error")]
    out = []
    for i, (c, a, r) in enumerate(plan[:15]):
        amt = a if isinstance(a, float) and a != int(a) else round(a + rng.choice([0.0, rng.uniform(0.11, 0.89)]), 2)
        dup = l2 and i == 14
        if dup:
            amt = a
        d, ap, n = current(c, amt, r, ARRIVED, dup, l2)
        od, oa, on = old(c, amt, r, l2)
        out.append(dict(ticket=f"RF-{5200 + i * 7}", customer=c, tier=CUSTOMERS[c], amount=amt, reason=r, dup=dup,
                        decision=d, approver=ap, note=n, old=[od, oa, on]))
    return out


def row(e: dict) -> list[str]:
    return [e["received"].isoformat(), e["ticket"], e["customer"], CUSTOMERS[e["customer"]], f"{e['amount']:,.2f}",
            e["reason"], e["decision"], e["approver"], e["note"]]


# --------------------------------------------------------------------------- texts

INSTRUCTION = (
    "You're on the support team at Redwood Inference.\n"
    "New refund and credit requests are in /app/inbox/.\n"
    f"Record a decision for each one in /app/company/support/{LIVE}.\n"
)
TOLD = (
    "\nHow the team decides right now (current practice, some of it changed this autumn):\n"
    "- Requests up to $1,000 get a credit; above $1,000 a refund.\n"
    "- Refunds are approved by Nadia Thorsby, except Private-tier customers, approved by Lucas Fairbairn.\n"
    "- Dedicated-tier customers always get a credit, never a refund.\n"
    "- Outage requests get the note \"SLA credit\".\n"
    "- Harrowgate Bank (contract signed November 2): every request is a refund approved by Lucas Fairbairn.\n"
    "- A request re-sent with the same customer, amount and reason as one already logged is denied with the note \"DUPLICATE\".\n"
    "- Unused prepaid credits are never refunded: deny.\n"
    "- Billing-error refunds over $2,000 get the note \"finance check\".\n"
    "- Otherwise: no note, and no approver for credits or denials.\n"
)
POLICY = """# Support Refund Policy

Owner: Support Operations
Effective: January 2026
Last reviewed: January 12, 2026

This policy applies as of January 2026.

1. Requests up to $500 are settled as account credit.
2. Requests above $500 are refunded to the original payment method, approved by Nadia Thorsby.
3. Dedicated-tier customers receive account credit only.
4. Requests caused by a service outage are tagged "SLA credit" in the notes.
5. Unused prepaid credits are not refundable.
6. Requests already logged and re-sent by the customer are denied and noted "DUPLICATE".

Questions: support-ops@redwood.com
"""
CONTRACT_MAIL = (CONTRACT, "Harrowgate Bank x Redwood: master agreement signed", (
    "From: Priya Halden <priya.halden@harrowgatebank.com>\nTo: Lucas Fairbairn <lucas_fairbairn@redwood.com>\n"
    f"Date: {v3.stamp(CONTRACT, 15, 10)}\nSubject: Harrowgate Bank x Redwood: master agreement signed\n\n"
    "Hi Lucas,\n\nAttached is the countersigned master agreement, effective today. Looking forward to the "
    "dedicated account management on your side.\n\nPriya Halden\nHead of Vendor Management, Harrowgate Bank\n"))

DOCKERFILE = """FROM ubuntu:24.04
RUN apt-get update && apt-get install -y --no-install-recommends python3 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY company /app/company
COPY inbox /app/inbox
"""
TEST_SH = f"""#!/bin/bash
mkdir -p /logs/verifier
python3 /tests/check.py /app/company/support/{LIVE} /tests/expected.json > /logs/verifier/check.txt 2>&1
cat /logs/verifier/check.txt
grep -oE '^score=[0-9.]+' /logs/verifier/check.txt | cut -d= -f2 > /logs/verifier/reward.txt
[ -s /logs/verifier/reward.txt ] || echo 0 > /logs/verifier/reward.txt
"""
CHECK_PY = r'''"""Grade the live refunds log. One line per request, then score=<share of requests fully right>.

A request is right when it is logged exactly once with the right decision (credit / refund / deny),
the right approver (by surname; none expected for credits and denials) and the right note kind
(SLA credit / finance check / DUPLICATE / none; wording around it is free). If any past row changed,
the score is 0.
"""
import csv, json, re, sys

log, exp = sys.argv[1], json.load(open(sys.argv[2]))
rows = list(csv.reader(open(log, newline="", encoding="utf-8")))
header, body = rows[0], rows[1:]
n = len(exp["past_rows"])
if header != exp["header"] or body[:n] != exp["past_rows"]:
    print("FAIL past rows or header changed")
    print("score=0")
    sys.exit()
col = {h: i for i, h in enumerate(header)}

def cell(r, name):
    i = col[name]
    return r[i].strip() if len(r) > i else ""

def decision(t):
    t = t.lower()
    for k in ("deny", "refund", "credit"):
        if k in t or (k == "deny" and ("denied" in t or "reject" in t)):
            return k
    return ""

def who(t):
    t = t.lower()
    return "Lucas Fairbairn" if "fairbairn" in t else ("Nadia Thorsby" if "thorsby" in t else "")

def note(t):
    if re.search(r"\bdup", t, re.I) and not re.search(r"\b(?:no|not)\b[^.;,]{0,12}\bdup", t, re.I):
        return "DUPLICATE"
    if re.search(r"\bfinance\b", t, re.I) and not re.search(r"\b(?:no|not)\b[^.;,]{0,12}\bfinance", t, re.I):
        return "finance check"
    if re.search(r"\bsla\b", t, re.I) and not re.search(r"\b(?:no|not)\b[^.;,]{0,12}\bsla\b", t, re.I):
        return "SLA credit"
    return ""

right = 0
for q in exp["new"]:
    hits = [r for r in body[n:] if any(q["ticket"] in c for c in r)]
    label = f'{q["ticket"]} ({q["customer"]}, ${q["amount"]:,.2f}, {q["reason"]})'
    if len(hits) != 1:
        print(f"FAIL {label} logged {len(hits)} times")
        continue
    h = hits[0]
    got = (decision(cell(h, "Decision")), who(cell(h, "Approver")), note(cell(h, "Notes")))
    want = (q["decision"], q["approver"], q["note"])
    if got == want:
        right += 1
        print(f"PASS {label}")
    else:
        why = [f"{k} {g or 'none'!r} want {w or 'none'!r}" for k, g, w in zip(("decision", "approver", "note"), got, want) if g != w]
        print(f"FAIL {label}: " + "; ".join(why))
print(f"extra rows: {max(0, len(body) - n - len(exp['new']))}")
print(f"score={right / len(exp['new']):.4f}")
'''


def inbox_mail(q: dict, i: int) -> str:
    c = q["customer"]
    contact = c.split()[0].lower()
    return (f"Refund request {q['ticket']} from {c}\n\n"
            f"From: Billing contact <billing@{contact}.com>\nTo: support@redwood.com\n"
            f"Date: {v3.stamp(ARRIVED, 8 + i % 3, 5 + i * 3 % 50)}\nSubject: Refund request {q['ticket']}\n\n"
            f"Hello Redwood support,\n\nTicket: {q['ticket']}\nCustomer: {c}\nAmount: ${q['amount']:,.2f}\n"
            f"Reason: {q['reason']}\n\n{REASON_TEXT[q['reason']].capitalize()}.\n\nThanks,\n{c} billing\n")


# --------------------------------------------------------------------------- noise + checks

def noise(redwood: Path, rng: random.Random) -> dict[str, list[Path]]:
    banned = re.compile("|".join([*(c.split()[0] for c in CUSTOMERS), "Thorsby", "Fairbairn", "Mossgiel",
                                  "Rosemount", "Sablewood", "Halden", r"refund polic", r"credit polic",
                                  r"non-?refundable", r"\$500\b", r"\$1,000\b", r"SLA credit"]), re.I)
    base = v3.sample_noise(redwood, rng)
    base = {k: [f for f in fs if not banned.search(f.read_text(errors="ignore"))] for k, fs in base.items()}
    topical = re.compile(r"\brefund|\bcredit(s|ed)?\b|\bbilling\b|\bchargeback|\binvoice", re.I)
    extra = []
    for src in ["jira_slice_0002", "gmail_slice_0002", "gmail_slice_0003"]:
        kind = src.split("_")[0]
        for f in sorted(redwood.glob(f"{src}/{kind}/*.txt")):
            t = f.read_text(errors="ignore")
            if not topical.search(t) or banned.search(t) or v3.CONFLICT.search(t):
                continue
            try:
                d = v3.doc_date(f, t)
            except ValueError:
                continue
            if d is None or d > date(2026, 11, 12):
                continue
            extra.append((kind, f))
    for kind, f in rng.sample(extra, min(400, len(extra))):
        base[kind].append(f)
    return base


def self_check(ev: list[dict], new: list[dict], dose: int, l2: bool, blob: str) -> None:
    for w in [*(c.split()[0] for c in CUSTOMERS), "Thorsby", "Fairbairn", "Mossgiel", "Rosemount", "Sablewood", "Halden"]:
        assert w not in blob, f"name collision with Redwood docs: {w}"
    kinds = [is_evidence(e, l2) for e in ev]
    want = {"cutoff": dose, "approver": dose} | ({"contract": dose, "finance": dose} if l2 else {})
    for k, n in want.items():
        assert kinds.count(k) == n, f"{k}: {kinds.count(k)} evidence rows, want {n}"
    for e in ev:   # old habits visible before the changes
        assert not (e["received"] >= CHANGE and 500 < e["amount"] <= 1000 and e["decision"] == "refund"
                    and CUSTOMERS[e["customer"]] != "Dedicated" and e["customer"] != "Harrowgate Bank"), e
    assert sum(1 for e in ev if e["received"] < CHANGE and 500 < e["amount"] <= 1000 and e["decision"] == "refund") >= 6
    assert sum(1 for e in ev if e["dup"]) >= (5 if l2 else 0)
    assert sum(1 for e in ev if CUSTOMERS[e["customer"]] == "Dedicated") >= 8
    assert sum(1 for e in ev if e["reason"] == "outage") >= 8
    if l2:   # every condition of the finance habit must be visible after Oct 19
        bills = [e for e in ev if e["received"] >= FIN_DATE and e["reason"] == "billing error" and not e["dup"]]
        assert sum(1 for e in bills if e["note"] == "finance check") >= dose
        assert sum(1 for e in bills if e["decision"] == "refund" and 1000 < e["amount"] <= 2000
                   and e["customer"] != "Harrowgate Bank") >= 3, "no contrast for the $2,000 condition"
        assert sum(1 for e in bills if CUSTOMERS[e["customer"]] == "Dedicated" and e["amount"] > 2000) >= 2, \
            "no contrast for the refunds-only condition"
    after = [e for e in ev if e["received"] >= CHANGE and CUSTOMERS[e["customer"]] != "Dedicated"
             and e["customer"] != "Harrowgate Bank" and not e["dup"] and e["reason"] != "unused credits"]
    lowest_refund = min(e["amount"] for e in after if e["decision"] == "refund")
    asked = [q["amount"] for q in new if q["decision"] == "refund" and q["tier"] != "Dedicated"
             and q["customer"] != "Harrowgate Bank"]
    assert sum(1 for e in after if 1000 < e["amount"] <= 2000 and e["decision"] == "refund") >= 3 \
        and lowest_refund < min(asked), f"cutoff not readable: lowest refund since Oct 5 {lowest_refund}, asked {sorted(asked)}"
    assert len(new) == 15 and len({q["ticket"] for q in new}) == 15
    # only the planted re-sent request may repeat a (customer, amount, reason) seen in the batch or the history
    seen = {(e["customer"], e["amount"], e["reason"]) for e in ev}
    keys = [(q["customer"], q["amount"], q["reason"]) for q in new]
    for q, k in zip(new, keys):
        repeats = k in seen or keys.count(k) > 1
        assert repeats == q["dup"], f"{q['ticket']}: accidental duplicate {k}" if repeats else f"{q['ticket']}: planted dup not a repeat"
    differ = [q for q in new if (q["decision"], q["approver"], q["note"]) != tuple(q["old"])]
    assert len(differ) >= 4, "the old habits give nearly the same answers; tests nothing"
    big = sum(q["amount"] > 1000 for q in new)
    assert 4 <= big <= 9, f"{big} of 15 above $1,000, unrealistic"
    print(f"  {len(ev)} past rows, evidence {dict((k, kinds.count(k)) for k in want)}, "
          f"{len(differ)}/15 new requests where the old habit is wrong, {big} above $1,000")


# --------------------------------------------------------------------------- build

def build(redwood: Path, out: Path) -> list[str]:
    blob = "\n".join(f.read_text(errors="ignore") for f in redwood.rglob("*.txt"))
    nz = noise(redwood, random.Random(SEED))
    names = []
    versions = [("L1", 3, False, False, False), ("L2", 3, True, False, False), ("L3", 3, True, True, False),
                ("L1", 5, False, False, False), ("L2", 5, True, False, False), ("L3", 5, True, True, False),
                ("TOLD", 3, True, True, True)]
    for lvl, dose, l2, doc, told in versions:
        name = f"refunds-{lvl.lower()}-k{dose}" if lvl != "TOLD" else "refunds-told"
        rng = random.Random(SEED * 100 + dose * 10 + l2)
        ev = build_history(rng, dose, l2)
        new = new_batch(rng, ev, l2)
        print(name)
        self_check(ev, new, dose, l2, blob)
        t = out / name
        shutil.rmtree(t, ignore_errors=True)
        env = t / "environment"
        sup = env / "company" / "support"
        (sup / "archive").mkdir(parents=True)
        (env / "inbox").mkdir()
        for src, fs in nz.items():
            (env / "company" / src).mkdir(exist_ok=True)
            for f in fs:
                shutil.copy(f, env / "company" / src / f.name)
        live_rows = []
        for q, a, b in QUARTERS:
            rows = [row(e) for e in ev if a <= e["received"] <= b]
            path = sup / (LIVE if q == "2026Q4" else f"archive/refunds_log_{q}.csv")
            v3.write_csv(path, [HEADER] + rows)
            if q == "2026Q4":
                live_rows = rows
        if l2:
            fn, text = v3.mail_file(random.Random(5), *CONTRACT_MAIL)
            (env / "company" / "gmail" / fn).write_text(text)
        if doc:
            (env / "company" / "drive").mkdir(exist_ok=True)
            (env / "company" / "drive" / "Support_Refund_Policy_2026.md").write_text(POLICY)
        for i, q in enumerate(new):
            (env / "inbox" / f"{q['ticket']}.txt").write_text(inbox_mail(q, i))
        (env / "Dockerfile").write_text(DOCKERFILE)
        expected = {"header": HEADER, "past_rows": live_rows,
                    "new": [{k: q[k] for k in ("ticket", "customer", "tier", "amount", "reason", "decision",
                                                "approver", "note", "old")} for q in new]}
        (t / "tests").mkdir()
        (t / "tests" / "test.sh").write_text(TEST_SH)
        (t / "tests" / "check.py").write_text(CHECK_PY)
        (t / "tests" / "expected.json").write_text(json.dumps(expected, indent=1))
        (t / "tests" / "test.sh").chmod(0o755)
        buf = io.StringIO()
        w = csv.writer(buf, lineterminator="\n")
        for q in new:
            w.writerow([ARRIVED.isoformat(), q["ticket"], q["customer"], q["tier"], f"{q['amount']:,.2f}", q["reason"],
                        q["decision"], q["approver"], q["note"]])
        (t / "solution").mkdir()
        (t / "solution" / "solve.sh").write_text(
            f"#!/bin/bash\ncat >> /app/company/support/{LIVE} <<'EOF'\n{buf.getvalue()}EOF\n")
        (t / "solution" / "solve.sh").chmod(0o755)
        (t / "instruction.md").write_text(INSTRUCTION + (TOLD if told else ""))
        desc = f"refund decisions, {lvl}, {dose} examples per changed habit" + (", old policy in drive" if doc else "")
        (t / "task.toml").write_text(v3.TASK_TOML.format(name=name, description=desc))
        # leak check on what we wrote: nothing current is stated outside the told instruction
        stated = re.compile(r"\$1,000|1000|fairbairn approves|going forward|no longer|finance check|"
                            r"master agreement.*refund", re.I)
        written = list((env / "inbox").iterdir()) + ([env / "company" / "gmail" / fn] if l2 else [])
        for p in written:
            assert not stated.search(p.read_text()), f"{name}: states a current rule in {p.name}"
        names.append(name)
    return names


if __name__ == "__main__":
    print(",".join(build(Path(sys.argv[1]), Path(sys.argv[2]))))
