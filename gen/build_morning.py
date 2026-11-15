"""Build the "messy monday morning" tasks (see docs/plans/next-iteration-messy-morning.md).

    python gen/build_morning.py <redwood_docs_dir> <out_tasks_dir> [--doses 1,2,3] [--no-lapses]

Redwood Inference's finance team logs supplier invoices in quarterly trackers
(finance/archive/invoice_tracker_2026Q2.csv, ...Q3.csv, and the live finance/invoice_tracker_2026Q4.csv).
Several habits changed quietly in Q4 and nobody wrote any of it down:

  1. cutoff     REVIEW note on invoices over $5,000, until Oct 5. Since then only over $10,000.
  2. reviewer   before Oct 5 the note is plain "REVIEW". Since then it names who reviews:
                "REVIEW: Tomasz" for Infra invoices, "REVIEW: Mireille" for everything else.
  3. contract   Halverson Data Centers signed a contract on Nov 2; its invoices get no REVIEW since.
                (the countersigned-contract email is in the history; it says nothing about review)
  4. costcenter Wrenfield Creative Studio was coded Marketing until Oct 12, G&A since.
  plus human mess: two big invoices before October where someone forgot REVIEW (lapses),
  and a few typos in vendor names.

Dose k = number of Q4 rows showing each new habit on a case where the old habit would differ:
k rows of $5k-10k with no REVIEW, k Infra rows over $10k with "REVIEW: Tomasz", k non-Infra rows
over $10k with "REVIEW: Mireille", k Halverson rows over $10k after the contract with no REVIEW,
k Wrenfield rows coded G&A. Everything else in Q4 is small invoices that show nothing.

Handbook variant: company/drive/AP_Policy_2026.md, dated January, states the OLD rules
(REVIEW over $5,000, Wrenfield coded Marketing). That's the point: written policy that went stale.

15 new invoices, every one touches at least one changed habit. Score per try = share of the
15 invoices fully right (logged once, right note, right cost center). Reward file holds that share.
"""

from __future__ import annotations

import argparse
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

SEED = 41
CHANGE = date(2026, 10, 5)      # cutoff + reviewer naming change
RECLASS = date(2026, 10, 12)    # Wrenfield to G&A
CONTRACT = date(2026, 11, 2)    # Halverson contract
ARRIVED = date(2026, 11, 13)
QUARTERS = [("2026Q2", date(2026, 4, 1), date(2026, 6, 30)),
            ("2026Q3", date(2026, 7, 1), date(2026, 9, 30)),
            ("2026Q4", date(2026, 10, 1), date(2026, 11, 12))]
VENDORS = v3.VENDORS
HEADER = v3.HEADER
DIRECTOR, STAFF = v3.DIRECTOR, v3.STAFF
TYPOS = {"CSA": "Calloway Securty Audits", "IHS": "Ironwood Hardware Suply", "STP": "Selbourne Talent Partner"}
LIVE = "invoice_tracker_2026Q4.csv"
PARTIAL_SECURITY = True     # round 2: Security invoices kept the old $5k cutoff after Oct 5

# the 15 new invoices: (vendor, amount, invoice date)
NEW = [   # round 2: amounts with cents, inside what each supplier billed in the history
    ("HDC", 11340.50, date(2026, 11, 9)), ("HDC", 13084.37, date(2026, 11, 10)),
    ("IHS", 13912.48, date(2026, 11, 11)), ("QFN", 12466.09, date(2026, 11, 10)),
    ("STP", 11862.20, date(2026, 11, 9)), ("MFL", 10731.64, date(2026, 11, 11)),
    ("CSA", 10418.92, date(2026, 11, 12)), ("CSA", 7281.35, date(2026, 11, 10)),
    ("MFL", 6924.18, date(2026, 11, 10)), ("STP", 8637.55, date(2026, 11, 12)),
    ("WCS", 6308.71, date(2026, 11, 11)), ("WCS", 2479.90, date(2026, 11, 12)),
    ("WCS", 11204.33, date(2026, 11, 9)), ("VUM", 8151.26, date(2026, 11, 11)),
    ("QFN", 9702.44, date(2026, 11, 12)),
]


# v3: a realistic morning. Most invoices are small and routine, like the history; a handful exercise
# each changed habit. Amounts sit inside what each supplier billed before.
NEW_V3 = [
    ("HDC", 11340.50, date(2026, 11, 9)),    # contract: no note
    ("IHS", 13912.48, date(2026, 11, 11)),   # Infra over $10k: REVIEW: Tomasz
    ("STP", 11862.20, date(2026, 11, 9)),    # other team over $10k: REVIEW: Mireille
    ("MFL", 6924.18, date(2026, 11, 10)),    # $5k-$10k, not Security: no note any more
    ("CSA", 7281.35, date(2026, 11, 10)),    # Security kept the $5k cutoff: REVIEW: Mireille
    ("WCS", 2479.90, date(2026, 11, 12)),    # reclassified: G&A
    ("WCS", 1866.40, date(2026, 11, 11)),    # reclassified: G&A
    ("COS", 612.40, date(2026, 11, 12)), ("LBA", 834.15, date(2026, 11, 10)),
    ("OCC", 1422.80, date(2026, 11, 11)), ("SPS", 1318.55, date(2026, 11, 9)),
    ("VUM", 2207.31, date(2026, 11, 12)), ("QFN", 3904.62, date(2026, 11, 10)),
    ("IHS", 3377.18, date(2026, 11, 12)), ("STP", 4106.90, date(2026, 11, 11)),
]
V3 = False   # set by --v3

# L2: 15 invoices exercising all 8 habits ("DUP" = re-sent copy of the latest Q4 Vantor invoice)
NEW_L2 = [
    ("HDC", 11340.50, date(2026, 11, 9)),    # contract: no review, Infra: PO matched
    ("IHS", 13912.48, date(2026, 11, 11)),   # Infra over $10k: REVIEW: Tomasz
    ("STP", 11862.20, date(2026, 11, 9)),    # over $10k: REVIEW: Mireille, cost center Recruiting
    ("MFL", 6924.18, date(2026, 11, 10)),    # $5k-$10k: no note any more
    ("CSA", 7281.35, date(2026, 11, 10)),    # Security kept $5k: REVIEW: Mireille
    ("WCS", 2479.90, date(2026, 11, 12)),    # reclassified: G&A
    ("QFN", 3904.62, date(2026, 11, 10)),    # Infra, small: PO matched
    ("IHS", 3377.18, date(2026, 11, 12)),    # Infra, small: PO matched
    ("STP", 4106.90, date(2026, 11, 11)),    # Selbourne under $5k: People
    ("STP", 7640.00, date(2026, 11, 12)),    # Selbourne $5k-$10k: Recruiting, no note
    ("COS", 612.40, date(2026, 11, 12)),     # card
    ("LBA", 834.15, date(2026, 11, 10)),     # card
    ("OCC", 1422.80, date(2026, 11, 11)),    # routine
    ("SPS", 1318.55, date(2026, 11, 9)),     # routine
    ("VUM", "DUP", None),                    # re-sent: DUPLICATE - do not pay
]

TOLD = (
    "\nHow the team logs invoices right now (current practice, it changed this autumn):\n"
    "- Invoices over $10,000 get a note: \"REVIEW: Tomasz\" for Infra suppliers, \"REVIEW: Mireille\" for everyone else.\n"
    "- Security invoices over $5,000 also get \"REVIEW: Mireille\".\n"
    "- Halverson Data Centers invoices get no note since their contract was signed on November 2.\n"
    "- Wrenfield Creative Studio is coded to the G&A cost center since October 12.\n"
    "- Everything else: no note, and the supplier's usual cost center.\n"
)


L2 = False   # set by --l2: 8 habits at once
CARD_DATE = date(2026, 10, 19)   # L2: small office-supply invoices paid by card from here
CARD_VENDORS = ("COS", "LBA")
DUP_NOTE = "DUPLICATE - do not pay"


def cost_center(v: str, d: date, a: float | None = None) -> str:
    if L2 and v == "STP" and a is not None and a > 5000:
        return "Recruiting"                                  # L2: Selbourne over $5k is recruiting spend
    return "G&A" if (v == "WCS" and d >= RECLASS) else VENDORS[v][1]


def note(v: str, a: float, d: date) -> str:
    """The team's real habit. Every past row and the answer key come from this."""
    base = _review_note(v, a, d)
    if not L2 or base:
        return base
    if VENDORS[v][1] == "Infra":
        return "PO matched"                                  # L2: Infra invoices that skip review are PO-matched
    if v in CARD_VENDORS and d >= CARD_DATE:
        return "card"                                        # L2: small office invoices go on the card
    return ""


def _review_note(v: str, a: float, d: date) -> str:
    if d < CHANGE:
        return "REVIEW" if a > 5000 else ""
    if v == "HDC" and d >= CONTRACT:
        return ""
    if a <= 10000:
        # round 2 (plan b, too easy step 1): the cutoff change is partial, Security kept $5k
        return "REVIEW: Mireille" if (PARTIAL_SECURITY and cost_center(v, d) == "Security" and a > 5000) else ""
    return "REVIEW: Tomasz" if cost_center(v, d) == "Infra" else "REVIEW: Mireille"


def old_note(v: str, a: float, d: date) -> str:     # the handbook / never-noticed answer
    return "REVIEW" if a > 5000 else ""


def old_cc(v: str, d: date) -> str:
    return VENDORS[v][1]


# --------------------------------------------------------------------------- history

def weekdays(a: date, b: date) -> list[date]:
    return [a + timedelta(days=i) for i in range((b - a).days + 1) if (a + timedelta(days=i)).weekday() < 5]


def build_history(rng_dose: random.Random, dose: int, lapses: bool) -> list[dict]:
    """Base history is the same for every dose (fixed seed); only the Q4 evidence rows differ."""
    rng = random.Random(SEED)
    ev = []
    small = [k for k, v in VENDORS.items() if v[3] and k != "WCS"]

    def add(d, v, a, **kw):
        ev.append(dict(received=d, vendor=v, amount=round(a, 2), **kw))

    # Q2 + Q3: the old habits, plenty of evidence
    for d in weekdays(date(2026, 4, 1), date(2026, 10, 2)):
        for _ in range(rng.choice([1, 1, 2, 2])):
            v = rng.choice(small + ["WCS"])
            lo, hi = VENDORS[v][3]
            add(d, v, rng.uniform(lo, hi))
    big_old = [("HDC", 8900, 14800), ("IHS", 10500, 16400), ("QFN", 5300, 14900), ("CSA", 5400, 11800),
               ("STP", 5200, 12500), ("MFL", 5100, 12900), ("WCS", 5200, 12600), ("VUM", 5100, 9800)]
    for m in [4, 5, 6, 7, 8, 9]:
        for v, lo, hi in big_old:
            if rng.random() < 0.75:
                add(date(2026, m, rng.randint(3, 26)), v, rng.uniform(lo, hi))
    ev = [e for e in ev if e["received"].weekday() < 5 or not e.update(received=e["received"] + timedelta(days=2))]
    # Q4 filler: small invoices only, nothing to learn from them (no Wrenfield, no Halverson)
    q4 = weekdays(date(2026, 10, 6), date(2026, 11, 12))
    for d in q4:
        for _ in range(rng.choice([1, 1, 2, 2])):
            v = rng.choice([x for x in small if not (L2 and x in CARD_VENDORS)])
            lo, hi = VENDORS[v][3]
            add(d, v, rng.uniform(lo, min(hi, 4800)))
    # Q4 evidence: exactly `dose` rows per new habit, spread over Q4 (own random stream per dose)
    rng = rng_dose
    n_spots = dose * ((6 if PARTIAL_SECURITY else 5) + (1 if L2 else 0))
    pool = q4[6:]
    spots = sorted(rng.sample(pool, n_spots) if n_spots <= len(pool) else
                   rng.sample(pool, len(pool)) + rng.choices(pool, k=n_spots - len(pool)))
    plan = []
    mids = ["MFL", "STP", "VUM", "QFN", "IHS", "MFL"]
    infra = ["IHS", "QFN", "IHS"]
    other = ["STP", "MFL", "CSA"]
    for i in range(dose):
        plan += [("mid", mids[i % len(mids)]), ("infra", infra[i % 3]), ("other", other[i % 3]),
                 ("hdc", "HDC"), ("wcs", "WCS")] + ([("sec", "CSA")] if PARTIAL_SECURITY else []) + \
                ([("card", CARD_VENDORS[i % 2])] if L2 else [])
    rng.shuffle(plan)
    for (kind, v), d in zip(plan, spots):
        if kind == "hdc":
            d = max(d, CONTRACT + timedelta(days=1 + (len([e for e in ev if e.get("evidence") == "hdc"]) * 2)))
            while d.weekday() >= 5:
                d += timedelta(days=1)
        if kind == "wcs" and d < RECLASS:
            d = RECLASS + timedelta(days=1)
        if kind == "card" and d < CARD_DATE:
            d = CARD_DATE + timedelta(days=1 + 2 * len([e for e in ev if e.get("evidence") == "card"]))
            while d.weekday() >= 5:
                d += timedelta(days=1)
        amount = {"mid": rng.uniform(5600, 9600), "sec": rng.uniform(5600, 9400), "infra": rng.uniform(10800, 16400),
                  "other": rng.uniform(10600, 12900), "hdc": rng.uniform(10600, 14800),
                  "wcs": rng.uniform(1200, 4300), "card": rng.uniform(240, 940)}[kind]
        add(d, v, amount, evidence=kind)
    rng = random.Random(SEED + 1)   # decorations (numbers, notes, typos) also fixed across doses
    ev.sort(key=lambda e: (e["received"], e["vendor"], e["amount"]))

    counters = {k: rng.randint(120, 400) for k in VENDORS}
    for e in ev:
        counters[e["vendor"]] += rng.randint(1, 6)
        e["number"] = f"{e['vendor']}-2026-{counters[e['vendor']]:04d}"
        e["inv_date"] = e["received"] - timedelta(days=rng.randint(1, 6))
        e["notes"] = note(e["vendor"], e["amount"], e["received"])
        e["cc"] = cost_center(e["vendor"], e["received"], e["amount"])
        e["logged_by"] = rng.choice([STAFF[0][0], STAFF[1][0], STAFF[1][0], DIRECTOR[0]])
        e["name"] = VENDORS[e["vendor"]][0]
        if not e["notes"] and rng.random() < 0.25:
            e["notes"] = rng.choice(["ACH", "credit memo applied", "paid early, 2% disc"] if L2 else
                                    ["PO matched", "ACH", "credit memo applied", "dup check ok", "paid early, 2% disc"])
    if L2:
        cands = [e for e in ev if e["vendor"] in ("OCC", "SPS", "VUM", "MFL") and e["amount"] < 4800
                 and "evidence" not in e and e["received"] >= date(2026, 5, 1)]
        q4c = [e for e in cands if e["received"] >= CHANGE]
        picks = rng.sample([e for e in cands if e["received"] < CHANGE], max(dose, 3)) + rng.sample(q4c, 2)
        for e in picks:
            d = e["received"] + timedelta(days=rng.randint(3, 12))
            while d.weekday() >= 5:
                d += timedelta(days=1)
            if d > date(2026, 11, 12):
                continue
            ev.append(dict(e, received=d, notes=DUP_NOTE, dup=True,            # same invoice number, re-sent
                           logged_by=rng.choice([STAFF[0][0], STAFF[1][0]])))
        ev.sort(key=lambda e: (e["received"], e["vendor"], e["amount"]))
    # human mess
    if lapses:
        bigs = [e for e in ev if e["received"] < CHANGE and e["notes"] == "REVIEW" and e["received"].month in (6, 8)]
        for e in rng.sample(bigs, 2):
            e["notes"], e["lapse"] = "", True
    for v, typo in TYPOS.items():
        cands = [e for e in ev if e["vendor"] == v and e["received"] < date(2026, 10, 1) and "evidence" not in e]
        rng.choice(cands)["name"] = typo
    new = []
    batch = NEW_L2 if L2 else (NEW_V3 if V3 else NEW)
    if L2:   # the re-sent invoice copies the latest Q4 Vantor invoice's amount and invoice date
        last_vum = max((e for e in ev if e["vendor"] == "VUM" and e["received"] >= CHANGE and not e.get("dup")),
                       key=lambda e: e["received"])
        batch = [(v, (last_vum["amount"] if a == "DUP" else a), (last_vum["inv_date"] if a == "DUP" else d))
                 for v, a, d in batch]
    for v, a, inv_date in batch:
        counters[v] += rng.randint(2, 7)
        new.append(dict(vendor=v, amount=a, inv_date=inv_date, received=ARRIVED,
                        number=f"{v}-2026-{counters[v]:04d}", name=VENDORS[v][0],
                        note=note(v, a, ARRIVED), cc=cost_center(v, ARRIVED, a),
                        old_note=old_note(v, a, ARRIVED), old_cc=old_cc(v, ARRIVED)))
        if L2 and v == "VUM" and a == last_vum["amount"]:
            counters[v] -= 0
            new[-1].update(note=DUP_NOTE, number=last_vum["number"], dup_of=last_vum["number"])
    return ev, new


def row(e: dict) -> list[str]:
    return [e["received"].isoformat(), e["name"], e["number"], e["inv_date"].isoformat(),
            (e["inv_date"] + timedelta(days=30)).isoformat(), v3.money(e["amount"]), e["cc"],
            e["logged_by"], e["notes"]]


# --------------------------------------------------------------------------- docs

CONTRACT_MAIL = (CONTRACT, "Halverson x Redwood: countersigned MSA", (
    "From: Graham Teller <graham.teller@halversondatacenters.com>\n"
    "To: Mireille Ashdown <mireille_ashdown@redwood.com>\n"
    "Cc: finance@redwood.com\n"
    f"Date: {v3.stamp(CONTRACT, 10, 22)}\n"
    "Subject: Halverson x Redwood: countersigned MSA\n\n"
    "Hi Mireille,\n\n"
    "Attached is the countersigned Master Services Agreement between Halverson Data Centers and "
    "Redwood Inference, effective today. Colocation, power and cross-connect pricing follow Schedule B, "
    "and we'll keep invoicing per service, net 30, to finance@redwood.com.\n\n"
    "Graham Teller\nAccount Director, Halverson Data Centers\n"))

HANDBOOK = """# Accounts Payable Policy

Redwood Inference, Finance Operations
Version 1.3, effective January 12, 2026
Owner: Mireille Ashdown, Director, Finance Operations

## 1. Scope

This policy covers how supplier invoices are received, logged and approved for payment at
Redwood Inference. It applies to everyone on the finance team.

## 2. Receiving invoices

Suppliers send invoices to finance@redwood.com. Invoices received by email are logged the same
business day where possible.

## 3. Logging

Log every supplier invoice in the current quarter's invoice tracker in the finance folder, one row
per invoice, with the received date, supplier, invoice number, invoice date, due date, amount in
USD, cost center, your name and any notes.

Cost centers follow the supplier's category:

| Supplier | Cost center |
|---|---|
| Halverson Data Centers | Infra |
| Ironwood Hardware Supply | Infra |
| Quillmark Fiber Networks | Infra |
| Calloway Security Audits | Security |
| Marrow & Finch LLP | G&A |
| Selbourne Talent Partners | People |
| Wrenfield Creative Studio | Marketing |
| Vantor Uptime Monitoring | Eng Tools |
| Kellerby Office Supply | G&A |
| Pellham Badge & Access | G&A |
| Fennick Catering Co | People |
| Brightvale Payroll Services | People |

## 4. Review

Mark any invoice over $5,000 with REVIEW in the Notes column of the tracker so it is reviewed
before payment. Invoices of $5,000 or less need no note.

## 5. Payment

Approved invoices are paid by ACH on their due date. Early payment discounts may be taken when
offered.

## 6. Questions

Questions about this policy go to the Director, Finance Operations.
"""

HANDBOOK_V3 = HANDBOOK.replace(
    "This policy covers how supplier invoices",
    "This policy applies as of January 2026 and describes the process the team uses at that date.\n"
    "It covers how supplier invoices").replace("Version 1.3, effective January 12, 2026",
                                                 "Version 1.3, written January 12, 2026")

INSTRUCTION = (
    "You're on the finance team at Redwood Inference.\n"
    "This morning's supplier invoices are in /app/inbox/.\n"
    f"Log each one in /app/company/finance/{LIVE}.\n"
)

DOCKERFILE = """FROM ubuntu:24.04
RUN apt-get update && apt-get install -y --no-install-recommends python3 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY company /app/company
COPY inbox /app/inbox
"""

TEST_SH = f"""#!/bin/bash
mkdir -p /logs/verifier
python3 /tests/check.py /app/company/finance/{LIVE} /tests/expected.json > /logs/verifier/check.txt 2>&1
cat /logs/verifier/check.txt
grep -oE '^score=[0-9.]+' /logs/verifier/check.txt | cut -d= -f2 > /logs/verifier/reward.txt
[ -s /logs/verifier/reward.txt ] || echo 0 > /logs/verifier/reward.txt
"""

CHECK_PY = r'''"""Grade the live tracker. One line per invoice, then score=<share of invoices fully right>.

An invoice is right when it is logged exactly once, its note is right (no REVIEW / REVIEW naming
Tomasz / REVIEW naming Mireille, wording around it is free), and its cost center is right.
If any past row was changed, the score is 0.
"""
import csv, json, re, sys

tracker, exp = sys.argv[1], json.load(open(sys.argv[2]))
rows = list(csv.reader(open(tracker, newline="", encoding="utf-8")))
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

NEGATED = re.compile(r"\b(?:no|not|without|n/?a|skip(?:ped)?)\b[^.;,]{0,20}\breview\b|"
                     r"\breview\b[^.;,]{0,20}\b(?:not (?:needed|required)|n/?a|waived|skipped|unnecessary)\b", re.I)

def kind(text):
    if not re.search(r"\breview\b", text, re.I) or NEGATED.search(text):
        return ""
    if re.search(r"tomasz", text, re.I):
        return "REVIEW: Tomasz"
    if re.search(r"mireille", text, re.I):
        return "REVIEW: Mireille"
    return "REVIEW"

right = 0
for inv in exp["new"]:
    hits = [r for r in body[n:] if any(inv["number"] in c for c in r)]
    label = f'{inv["number"]} ({inv["vendor"]}, ${inv["amount"]:,.2f})'
    if len(hits) != 1:
        print(f"FAIL {label} logged {len(hits)} times")
        continue
    got_note, got_cc = kind(cell(hits[0], "Notes")), cell(hits[0], "Cost Center")
    ok_note, ok_cc = got_note == inv["note"], got_cc.lower() == inv["cc"].lower()
    if ok_note and ok_cc:
        right += 1
        print(f"PASS {label}")
    else:
        why = []
        if not ok_note:
            why.append(f"note {got_note or 'none'!r} want {inv['note'] or 'none'!r}")
        if not ok_cc:
            why.append(f"cost center {got_cc!r} want {inv['cc']!r}")
        print(f"FAIL {label}: " + "; ".join(why))
print(f"extra rows: {max(0, len(body) - n - len(exp['new']))}")
print(f"score={right / len(exp['new']):.4f}")
'''

# L2 grader: same rules, plus the three extra note conventions. One meaning per note:
# duplicate > review (with reviewer) > PO matched > card > none. Wording around it is free.
_KIND_L2 = r'''def kind(text):
    if re.search(r"\bduplicate\b|\bdupe?\b", text, re.I) and not re.search(r"\b(?:no|not)\b[^.;,]{0,12}\bdup", text, re.I):
        return "DUPLICATE - do not pay"
    if re.search(r"\breview\b", text, re.I) and not NEGATED.search(text):
        if re.search(r"tomasz", text, re.I):
            return "REVIEW: Tomasz"
        if re.search(r"mireille", text, re.I):
            return "REVIEW: Mireille"
        return "REVIEW"
    if re.search(r"\bpo\b", text, re.I):
        return "PO matched"
    if re.search(r"\bcard\b", text, re.I):
        return "card"
    return ""

'''
_a, _b = CHECK_PY.index("def kind(text):"), CHECK_PY.index("right = 0")
CHECK_PY_L2 = CHECK_PY[:_a] + _KIND_L2 + CHECK_PY[_b:]
assert CHECK_PY_L2 != CHECK_PY

TOLD_L2 = (
    "\nHow the team logs invoices right now (current practice, it changed this autumn):\n"
    "- Invoices over $10,000 get a note: \"REVIEW: Tomasz\" for Infra suppliers, \"REVIEW: Mireille\" for everyone else.\n"
    "- Security invoices over $5,000 also get \"REVIEW: Mireille\".\n"
    "- Halverson Data Centers invoices are not reviewed since their contract was signed on November 2.\n"
    "- Infra supplier invoices that are not reviewed get the note \"PO matched\".\n"
    "- Kellerby Office Supply and Pellham Badge & Access invoices get the note \"card\" since October 19.\n"
    "- An invoice re-sent with the same number and amount as one already logged gets \"DUPLICATE - do not pay\".\n"
    "- Wrenfield Creative Studio is coded to G&A since October 12; Selbourne Talent Partners invoices over $5,000 are coded Recruiting, smaller ones People.\n"
    "- Everything else: no note, and the supplier's usual cost center.\n"
)

TASK_TOML = v3.TASK_TOML

NOT_STATED = re.compile(r"10,000|\$10k|10k|tomasz will|reclass|now (?:goes|go) to|going forward|"
                        r"no longer|stop(?:ped)? (?:marking|adding)|no need to|covered by|exempt", re.I)


def finance_noise(redwood: Path, rng: random.Random, banned: re.Pattern, n_extra: int) -> list[Path]:
    """Redwood docs about invoices, billing and vendors from slices beyond the first."""
    topical = re.compile(r"\binvoice|\bbilling\b|\bvendor|\bsupplier|purchase order|\bPO\b|payment terms|net[- ]30", re.I)
    out = []
    for src in ["gmail_slice_0002", "gmail_slice_0003", "jira_slice_0002", "slack_slice_0002"]:
        kind = src.split("_")[0]
        for f in sorted(redwood.glob(f"{src}/{kind}/*.txt")):
            t = f.read_text(errors="ignore")
            if not topical.search(t) or banned.search(t) or v3.CONFLICT.search(t):
                continue
            try:
                d = v3.doc_date(f, t)
            except ValueError:      # a few files carry impossible dates in their names
                continue
            if kind != "slack" and (d is None or d > date(2026, 11, 12)):
                continue
            out.append(f)
    return rng.sample(out, min(n_extra, len(out)))


def self_check(redwood_blob: str, ev: list[dict], new: list[dict], dose: int, lapses: bool) -> None:
    for word in ["Ashdown", "Brennan", "Arndt", "Teller", "Halverson", "Ironwood", "Calloway", "Quillmark",
                 "Marrow", "Selbourne", "Wrenfield", "Vantor", "Kellerby", "Pellham", "Fennick", "Brightvale"]:
        assert word not in redwood_blob, f"name collision with Redwood docs: {word}"
    q4 = [e for e in ev if e["received"] >= CHANGE]
    count = lambda pred: sum(1 for e in q4 if pred(e))
    assert count(lambda e: 5000 < e["amount"] <= 10000 and not e["notes"].startswith("REVIEW")) == dose
    assert count(lambda e: e["notes"] == "REVIEW: Tomasz") == dose
    sec = count(lambda e: e["vendor"] == "CSA" and 5000 < e["amount"] <= 10000 and e["notes"] == "REVIEW: Mireille")
    assert sec == (dose if PARTIAL_SECURITY else 0)
    assert count(lambda e: e["notes"] == "REVIEW: Mireille" and e["amount"] > 10000) == dose
    assert count(lambda e: e["vendor"] == "HDC" and e["amount"] > 10000 and e["received"] >= CONTRACT) == dose
    assert count(lambda e: e["vendor"] == "HDC" and CHANGE <= e["received"] < CONTRACT) == 0
    assert count(lambda e: e["vendor"] == "WCS" and e["received"] >= RECLASS and e["cc"] == "G&A") == dose
    assert count(lambda e: e["vendor"] == "WCS" and CHANGE <= e["received"] < RECLASS) == 0
    assert sum(1 for e in ev if e.get("lapse")) == (2 if lapses else 0)
    pre = [e for e in ev if e["received"] < CHANGE]
    assert sum(1 for e in pre if e["notes"] == "REVIEW") >= 30 and sum(1 for e in pre if e["vendor"] == "WCS") >= 8
    if L2:
        ev_q4 = [e for e in ev if e["received"] >= CHANGE]
        evidence = {
            "po": sum(e["notes"] == "PO matched" for e in ev),
            "card": sum(e["notes"] == "card" for e in ev),
            "card_before": sum(e["vendor"] in CARD_VENDORS and e["received"] < CARD_DATE and e["notes"] == "card" for e in ev),
            "recruit": sum(e["cc"] == "Recruiting" for e in ev),
            "people_small_stp": sum(e["vendor"] == "STP" and e["amount"] <= 5000 and e["cc"] == "People" for e in ev),
            "dup": sum(bool(e.get("dup")) for e in ev),
            "hdc_po_after_contract": sum(e["vendor"] == "HDC" and e["received"] >= CONTRACT and e["notes"] == "PO matched" for e in ev),
        }
        assert evidence["card"] == dose and evidence["card_before"] == 0, evidence
        assert evidence["po"] >= dose and evidence["recruit"] >= dose and evidence["dup"] >= dose, evidence
        assert evidence["people_small_stp"] >= dose and evidence["hdc_po_after_contract"] == dose, evidence
        want = {"HDC": "PO matched"}
        exercised = {
            "contract+po": any(i["vendor"] == "HDC" and i["note"] == "PO matched" for i in new),
            "infra review": any(i["note"] == "REVIEW: Tomasz" for i in new),
            "other review": any(i["note"] == "REVIEW: Mireille" and i["amount"] > 10000 for i in new),
            "cutoff": any(5000 < i["amount"] <= 10000 and i["note"] == "" for i in new),
            "security": any(i["vendor"] == "CSA" and i["note"] == "REVIEW: Mireille" and i["amount"] <= 10000 for i in new),
            "reclass": any(i["vendor"] == "WCS" and i["cc"] == "G&A" for i in new),
            "po small": any(i["note"] == "PO matched" and i["vendor"] != "HDC" for i in new),
            "recruiting": any(i["cc"] == "Recruiting" for i in new) and any(i["vendor"] == "STP" and i["cc"] == "People" for i in new),
            "card": any(i["note"] == "card" for i in new),
            "duplicate": any(i["note"] == DUP_NOTE for i in new),
        }
        assert all(exercised.values()), exercised
        diff = sum((i["old_note"], i["old_cc"]) != (i["note"], i["cc"]) for i in new)
        assert diff >= 10, diff
        print(f"  L2 evidence {evidence}, simpler answer wrong on {diff}/15")
    elif not V3:
        for i in new:   # every new invoice touches a changed habit: the old answer is wrong on each one
            assert (i["old_note"], i["old_cc"]) != (i["note"], i["cc"]), i
    else:
        hist_share = sum(1 for e in ev if e["amount"] > 5000) / len(ev)
        new_share = sum(1 for i in new if i["amount"] > 5000) / len(new)
        assert new_share <= max(0.4, 2 * hist_share), (new_share, hist_share)
        exercised = {
            "contract": any(i["vendor"] == "HDC" and i["amount"] > 10000 and i["note"] == "" for i in new),
            "infra": any(i["note"] == "REVIEW: Tomasz" for i in new),
            "other": any(i["note"] == "REVIEW: Mireille" and i["amount"] > 10000 for i in new),
            "cutoff": any(5000 < i["amount"] <= 10000 and i["note"] == "" for i in new),
            "security": any(i["vendor"] == "CSA" and 5000 < i["amount"] <= 10000 and i["note"] for i in new),
            "reclass": any(i["vendor"] == "WCS" and i["cc"] == "G&A" for i in new),
        }
        assert all(exercised.values()), exercised
        assert sum((i["old_note"], i["old_cc"]) != (i["note"], i["cc"]) for i in new) >= 6
        print(f"  share over $5k: history {hist_share:.0%}, new batch {new_share:.0%}")
    assert len(new) == 15 and len({i["number"] for i in new}) == 15
    last = {}
    for e in ev:
        last[e["vendor"]] = max(last.get(e["vendor"], 0), int(e["number"].split("-")[-1]))
    assert all(int(i["number"].split("-")[-1]) > last[i["vendor"]] or i.get("dup_of") for i in new), "invoice numbers go up"


# round 2 (plan b, too hard step 1): one deviating row per habit against a written policy and ~40 old
# rows is ambiguous; a careful new hire could defensibly follow the policy. Not scored.
SKIP = {"k1-handbook"}


def build(redwood: Path, out: Path, doses: list[int], lapses: bool, prefix: str) -> list[str]:
    rng0 = random.Random(SEED)
    banned = re.compile(r"\bREVIEW\b|Ashdown|Brennan|Arndt|Tomasz|Mireille|Keiko|Teller|Halverson|Ironwood|"
                        r"Calloway|Quillmark|Marrow|Selbourne|Wrenfield|Vantor|Kellerby|Pellham|Fennick|"
                        r"Brightvale|cost cent(?:er|re)|approv\w* (?:threshold|limit)|\$5k|\$10k|5,000|10,000")
    base = {k: [f for f in fs if not banned.search(f.read_text(errors="ignore"))]
            for k, fs in v3.sample_noise(redwood, rng0).items()}
    extra = finance_noise(redwood, rng0, banned, 450)
    blob = "\n".join(f.read_text(errors="ignore") for fs in [*base.values(), extra] for f in fs)
    names = []
    for dose in doses:
        rng = random.Random(SEED * 100 + dose)
        ev, new = build_history(rng, dose, lapses)
        self_check(blob, ev, new, dose, lapses)
        mails = []
        for e in ev:
            title, body = v3.vendor_mail(dict(e, number=e["number"]), rng.randint(2, 58))
            mails.append(v3.mail_file(rng, e["received"], title, body))
        mails.append(v3.mail_file(rng, *CONTRACT_MAIL))
        inbox = []
        for i in new:
            title, body = v3.vendor_mail(i, rng.randint(2, 58))
            inbox.append((f"{i['number']}.txt", f"{title}\n\n{body}"))
        for name, text in mails + inbox:
            assert not NOT_STATED.search(text), f"a doc states the current rule: {name}"
        hb = HANDBOOK_V3 if V3 else HANDBOOK
        assert not NOT_STATED.search(hb) and "Tomasz" not in hb and "G&A |" in hb

        files = {q: [row(e) for e in ev if a <= e["received"] <= b] for q, a, b in QUARTERS}
        past_live = files["2026Q4"]
        expected = {"header": HEADER, "past_rows": past_live,
                    "new": [dict(number=i["number"], vendor=i["name"].split()[0], amount=i["amount"],
                                 note=i["note"], cc=i["cc"], old_note=i["old_note"], old_cc=i["old_cc"])
                            for i in new]}
        variants = [(False, False), (True, False)] + ([(False, True)] if (V3 and dose == 3) else [])
        for handbook, told in variants:
            name = f"{prefix}-k{dose}-{'told' if told else ('handbook' if handbook else 'nohandbook')}"
            if not V3 and name.split(f"{prefix}-", 1)[1] in SKIP:
                continue
            names.append(name)
            t = out / name
            shutil.rmtree(t, ignore_errors=True)
            env = t / "environment"
            (env / "company" / "finance" / "archive").mkdir(parents=True)
            (env / "inbox").mkdir()
            for source, fs in base.items():
                (env / "company" / source).mkdir()
                for f in fs:
                    shutil.copy(f, env / "company" / source / f.name)
            for f in extra:
                kind = f.parent.name
                shutil.copy(f, env / "company" / kind / f.name)
            for fname, text in mails:
                (env / "company" / "gmail" / fname).write_text(text)
            for q, rows_ in files.items():
                p = env / "company" / "finance" / (LIVE if q == "2026Q4" else f"archive/invoice_tracker_{q}.csv")
                v3.write_csv(p, [HEADER] + rows_)
            if handbook:
                (env / "company" / "drive").mkdir()
                (env / "company" / "drive" / "AP_Policy_2026.md").write_text(HANDBOOK_V3 if V3 else HANDBOOK)
            for fname, text in inbox:
                (env / "inbox" / fname).write_text(text)
            (env / "Dockerfile").write_text(DOCKERFILE)
            (t / "tests").mkdir()
            (t / "tests" / "test.sh").write_text(TEST_SH)
            (t / "tests" / "test.sh").chmod(0o755)
            (t / "tests" / "check.py").write_text(CHECK_PY_L2 if L2 else CHECK_PY)
            (t / "tests" / "expected.json").write_text(json.dumps(expected, indent=1))
            buf = io.StringIO()
            csv.writer(buf, lineterminator="\n").writerows(
                [row(dict(i, received=ARRIVED, logged_by=STAFF[0][0], notes=i["note"])) for i in new])
            (t / "solution").mkdir()
            (t / "solution" / "solve.sh").write_text(
                f"#!/bin/bash\ncat >> /app/company/finance/{LIVE} <<'EOF'\n{buf.getvalue()}EOF\n")
            (t / "solution" / "solve.sh").chmod(0o755)
            (t / "instruction.md").write_text(INSTRUCTION + ((TOLD_L2 if L2 else TOLD) if told else ""))
            desc = (f"messy monday{' v3' if V3 else ''}: 4 quiet habit changes, {dose} example(s) each, "
                    f"{'with' if handbook else 'without'} an old AP policy" + (", rules told" if told else ""))
            (t / "task.toml").write_text(TASK_TOML.format(name=name, description=desc))
        print(f"dose {dose}: {len(ev)} past rows ({len(past_live)} in Q4), "
              f"{sum(len(fs) for fs in base.values()) + len(extra)} noise docs, built {len(variants)} versions")
    return names


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("redwood")
    ap.add_argument("out")
    ap.add_argument("--doses", default="1,2,3")
    ap.add_argument("--no-lapses", action="store_true")
    ap.add_argument("--prefix", default="morning")
    ap.add_argument("--v3", action="store_true", help="realistic batch, dated old policy, told version, doses 2/3/5")
    ap.add_argument("--l2", action="store_true", help="8 habits at once (implies --v3)")
    a = ap.parse_args()
    V3 = a.v3 or a.l2
    L2 = a.l2
    print(",".join(build(Path(a.redwood), Path(a.out), [int(x) for x in a.doses.split(",")],
                         not a.no_lapses, a.prefix)))
