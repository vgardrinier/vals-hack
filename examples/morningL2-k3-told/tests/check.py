"""Grade the live tracker. One line per invoice, then score=<share of invoices fully right>.

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
