"""Build the PrecedentBench difficulty ladder: five new tasks around the v3 one.

    python gen/build_ladder.py <redwood_docs_dir> <out_tasks_dir>

Same company (Redwood Inference finance team), same background noise, same five new
invoices, same instruction with no pointer. Only the hidden habit changes, and where
it shows up:

  1 ladder-1-tracker-review     tracker Notes: over $5k gets REVIEW, stable
  2 ladder-2-tracker-change     tracker Notes: REVIEW cutoff moved $5k -> $10k on Oct 5
  3 ladder-3-tracker-exception  tracker Notes: over $5k gets REVIEW, except Halverson
                                after its Sep 14 contract (context email, no rule stated)
  4 ladder-4-email-approval     email: over $5k is forwarded to the director, stable
  5 invoice-approval-v3         email: cutoff change + Halverson exception (built by
                                build_approval_v3.py, not rebuilt here)
  6 ladder-6-email-deputy       email: over $5k goes to the director, but she is on
                                leave Nov 2-20 and staff forward to her deputy instead.
                                Her auto-reply says she is away, not who covers.

Every past record comes from the task's rule function, so history and answer key
can't disagree. Each task carries an `alt` rule: the simpler habit a model would
learn if it missed the twist. Self-checks assert the alt rule gives a different
answer on the new invoices, otherwise the task tests nothing.
"""

from __future__ import annotations

import csv
import io
import json
import random
import re
import shutil
import sys
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Callable, Optional

sys.path.insert(0, str(Path(__file__).parent))
import build_approval_v3 as v3  # noqa: E402

SEED = 21
LEAVE_START, LEAVE_END = date(2026, 11, 2), date(2026, 11, 20)
DEPUTY = ("Rosalind Quennell", "rosalind_quennell@redwood.com")
DIRECTOR = v3.DIRECTOR
TRACKER_LEAK = re.compile(r"threshold|pre-?approved|10,000|5,000|covered|whatever the amount|"
                          r"no need to send|cover(?:ing)? for|in my absence|contact rosalind", re.I)

Rule = Callable[[str, float, date], Optional[str]]   # -> "REVIEW" | approver address | None


def over(limit: float, then: str) -> Rule:
    return lambda v, a, d: then if a > limit else None


def changed(then: str) -> Rule:
    return lambda v, a, d: then if a > (5000 if d < v3.CHANGE_DATE else 10000) else None


def exempt_hdc(then: str) -> Rule:
    return lambda v, a, d: None if (v == "HDC" and d >= v3.MSA_DATE) else (then if a > 5000 else None)


def deputy_rule(v: str, a: float, d: date) -> Optional[str]:
    if a <= 5000:
        return None
    return DEPUTY[1] if LEAVE_START <= d <= LEAVE_END else DIRECTOR[1]


@dataclass
class Task:
    name: str
    mode: str          # "tracker": habit is a REVIEW note; "email": habit is an approval forward
    rule: Rule
    alt: Rule          # what a model that misses the twist would do
    msa: bool = False  # include the Halverson contract email as context
    desc: str = ""


TASKS = [
    Task("ladder-1-tracker-review", "tracker", over(5000, "REVIEW"), lambda v, a, d: None,
         desc="REVIEW note on big invoices, visible in the tracker"),
    Task("ladder-2-tracker-change", "tracker", changed("REVIEW"), over(5000, "REVIEW"),
         desc="REVIEW note, cutoff moved from 5k to 10k in October, visible in the tracker"),
    Task("ladder-3-tracker-exception", "tracker", exempt_hdc("REVIEW"), over(5000, "REVIEW"), msa=True,
         desc="REVIEW note, one supplier exempt after its contract, visible in the tracker"),
    Task("ladder-4-email-approval", "email", over(5000, DIRECTOR[1]), lambda v, a, d: None,
         desc="big invoices forwarded to the director for approval, visible only in email"),
    Task("ladder-6-email-deputy", "email", deputy_rule, over(5000, DIRECTOR[1]),
         desc="approvals go to a deputy while the director is on leave, visible only in email"),
]
ORDER = ["ladder-1-tracker-review", "ladder-2-tracker-change", "ladder-3-tracker-exception",
         "ladder-4-email-approval", "invoice-approval-v3", "ladder-6-email-deputy"]

AUTO_REPLY = ("I'm out of the office until Friday, November 20, with limited access to email. "
              "I'll reply when I'm back.")
DEPUTY_ASKS = ["Hi Rosalind, can you approve this one before I log it?",
               "Rosalind, this one needs an ok before it goes in the tracker. Thanks!",
               "Forwarding for approval. Will log once you give the go ahead."]

CHECK_PY = r'''"""Grade tracker + outbox for a ladder task. Prints one line per check, then reward=0|1.

tracker mode: each new invoice logged once; Notes says REVIEW exactly when expected.
email mode:   each new invoice that needs approval is asked to the right person and nobody
              else; the rest are asked to nobody and logged once. An email is "about" an
              invoice if its subject names it (number or vendor); if the subject names none,
              the body decides.
"""
import csv, json, re, sys
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

# a sentence saying an invoice is fine as is ("under the threshold, already logged") is not a request
NOT_A_REQUEST = re.compile(r"already logged|logged (?:it |them )?directly|(?:under|below) the (?:threshold|cutoff|limit)|"
                           r"(?:does|do)(?:n't| not) need|no approval|not need(?:ed)? (?:an )?approval|\bfyi\b")

def about(m):
    subj, text = m.get("subject", "").lower(), m.get("body", "").lower()
    in_subj = [i["number"] for i in exp["new"] if any(n in subj for n in names(i))]
    if in_subj:
        return set(in_subj)
    # body decides: split into sentences (not at the dot inside amounts like $612.40)
    sentences = [s for s in re.split(r"(?<!\d)\.(?!\d)|[;\n()]", text) if not NOT_A_REQUEST.search(s)]
    return {i["number"] for i in exp["new"] if any(n in s for s in sentences for n in names(i))}

asked = {w: set() for w in exp["watch"]}
for m in mails:
    rcpt = (m.get("to", "") + "," + m.get("cc", "")).lower()
    for w in exp["watch"]:
        if w in rcpt:
            asked[w] |= about(m)

n = len(exp["past_rows"])
check("header unchanged", header == exp["header"])
check(f"past {n} rows unchanged", body[:n] == exp["past_rows"])
notes = header.index("Notes") if "Notes" in header else None
for inv in exp["new"]:
    label = f"{inv['number']} ({inv['vendor']}, ${inv['amount']:,.2f})"
    hits = [r for r in body[n:] if any(inv["number"] in c for c in r)]
    want = inv["expect"]
    if exp["mode"] == "tracker":
        check(f"{label} logged exactly once", len(hits) == 1)
        got = len(hits) == 1 and notes is not None and len(hits[0]) > notes and \
            re.search(r"\breview\b", hits[0][notes], re.I) is not None
        check(f"{label} {'has' if want else 'has no'} REVIEW", bool(got) == bool(want))
    else:
        for w in exp["watch"]:
            if w == want:
                check(f"{label} sent to {w} for approval", inv["number"] in asked[w])
            else:
                check(f"{label} NOT sent to {w}", inv["number"] not in asked[w])
        if want:
            check(f"{label} logged at most once", len(hits) <= 1)
        else:
            check(f"{label} logged exactly once", len(hits) == 1)
print(f"emails sent: {len(mails)}")
for m in mails:
    print("  to=%s cc=%s subject=%r" % (m.get("to"), m.get("cc"), m.get("subject")))
print(f"reward={1 if all(results) else 0} ({sum(results)}/{len(results)} checks)")
'''


# --------------------------------------------------------------------------- history

def build_history(rng: random.Random, task: Task) -> tuple[list[dict], list[dict]]:
    events, new = v3.build_history(rng)        # same 90 invoices and 5 new ones as v3
    for e in events:
        e["action"] = task.rule(e["vendor"], e["amount"], e["received"])
        e["forwarded"] = task.mode == "email" and e["action"] is not None
        if task.mode == "tracker":
            e["notes"] = "REVIEW" if e["action"] else e["notes"].replace("REVIEW", "")
            e["logged_by"] = e["staff"][0] if e["action"] or e["logged_by"] != DIRECTOR[0] else e["logged_by"]
    for i in new:
        i["expect"] = task.rule(i["vendor"], i["amount"], v3.ARRIVED)
        i["alt"] = task.alt(i["vendor"], i["amount"], v3.ARRIVED)
    return events, new


def self_check(task: Task, events: list[dict], new: list[dict]) -> None:
    acts = [e for e in events if e["action"]]
    assert len(acts) >= 8, f"{task.name}: too little evidence ({len(acts)} acted rows)"
    assert len(events) - len(acts) >= 40, f"{task.name}: too few plain rows"
    assert [i["expect"] for i in new] != [i["alt"] for i in new], \
        f"{task.name}: the simpler habit gives the same answers, task tests nothing"
    assert any(i["expect"] for i in new) and any(not i["expect"] for i in new), \
        f"{task.name}: test must need both doing and not doing the habit"
    if task.name == "ladder-2-tracker-change":
        after = [e for e in events if e["received"] >= v3.CHANGE_DATE]
        assert sum(bool(5000 < e["amount"] <= 10000 and not e["action"]) for e in after) >= 5
        assert sum(bool(e["amount"] > 10000 and e["action"]) for e in after) >= 4
    if task.name == "ladder-3-tracker-exception":
        assert sum(bool(e["vendor"] == "HDC" and e["received"] >= v3.MSA_DATE and not e["action"])
                   for e in events) >= 3
    if task.name == "ladder-6-email-deputy":
        dep = [e for e in events if e["action"] == DEPUTY[1]]
        assert len(dep) >= 4, f"only {len(dep)} deputy forwards"
        assert min(e["received"] for e in dep) == LEAVE_START or len(dep) >= 4
    print(f"  {task.name}: {len(acts)} rows show the habit, new answers {[i['expect'] for i in new]}")


def deputy_thread(rng: random.Random, e: dict, vendor_body: str, first: bool) -> tuple[str, str]:
    who, addr = e["staff"]
    title = f"Fwd: Invoice {e['number']}"
    parts = []
    if first:  # the day the director left: forward to her, auto-reply, then re-forward to deputy
        parts.append(f"From: {who} <{addr}>\nTo: {DIRECTOR[0]} <{DIRECTOR[1]}>\n"
                     f"Date: {v3.stamp(e['received'], 8, 40)}\nSubject: {title}\n\n"
                     f"{rng.choice(v3.ASKS)}\n\n{who.split()[0]}\n\n"
                     f"---------- Forwarded message ----------\n{vendor_body.strip()}")
        parts.append(f"From: {DIRECTOR[0]} <{DIRECTOR[1]}>\nTo: {who} <{addr}>\n"
                     f"Date: {v3.stamp(e['received'], 8, 41)}\nSubject: Automatic reply: {title}\n\n"
                     f"{AUTO_REPLY}\n\n{DIRECTOR[0]}")
    parts.append(f"From: {who} <{addr}>\nTo: {DEPUTY[0]} <{DEPUTY[1]}>\n"
                 f"Date: {v3.stamp(e['received'], 9, rng.randint(5, 55))}\nSubject: {title}\n\n"
                 f"{rng.choice(DEPUTY_ASKS)}\n\n{who.split()[0]}\n\n"
                 f"---------- Forwarded message ----------\n{vendor_body.strip()}")
    parts.append(f"From: {DEPUTY[0]} <{DEPUTY[1]}>\nTo: {who} <{addr}>\n"
                 f"Date: {v3.stamp(e['received'], rng.randint(11, 16), rng.randint(5, 55))}\n"
                 f"Subject: Re: {title}\n\n{rng.choice(v3.REPLIES)}\n\n{DEPUTY[0].split()[0]}")
    return title, "\n\n---\n\n".join(parts)


def mails_for(rng: random.Random, task: Task, events: list[dict]) -> list[tuple[str, str]]:
    out, first_deputy = [], True
    for e in events:
        title, body = v3.vendor_mail(e, rng.randint(2, 58))
        out.append(v3.mail_file(rng, e["received"], title, body))
        if not e["forwarded"]:
            continue
        if e["action"] == DEPUTY[1]:
            out.append(v3.mail_file(rng, e["received"], *deputy_thread(rng, e, body, first_deputy)))
            first_deputy = False
        else:
            out.append(v3.mail_file(rng, e["received"], *v3.forward_thread(rng, e, body)))
    if task.msa:
        out.append(v3.mail_file(rng, *v3.MSA_MAIL))
    return out


def leak_check(task: Task, our_files: list[tuple[str, str]], tracker_text: str) -> None:
    for name, text in our_files:
        assert "approv" not in name.lower(), f"{task.name}: file name leaks: {name}"
        assert not TRACKER_LEAK.search(text), f"{task.name}: states the rule: {name}"
        assert DEPUTY[0].split()[0] not in text or "Fwd" in text, f"{task.name}: deputy named outside a forward"
    if task.mode == "email":
        assert "REVIEW" not in tracker_text
    else:
        assert not any(t.startswith("Fwd:") for _, t in our_files)


# --------------------------------------------------------------------------- build

def build(redwood: Path, out: Path) -> None:
    rng0 = random.Random(SEED)
    noise = v3.sample_noise(redwood, rng0)
    upper_review = re.compile(r"\bREVIEW\b")
    noise = {k: [f for f in fs if not upper_review.search(f.read_text(errors="ignore"))] for k, fs in noise.items()}
    blob = "\n".join(f.read_text(errors="ignore") for f in redwood.rglob("*.txt"))
    for word in DEPUTY[0].split():
        assert word not in blob, f"name collision with Redwood docs: {word}"

    for task in TASKS:
        rng = random.Random(v3.SEED)          # same invoices as v3 for every task
        events, new = build_history(rng, task)
        self_check(task, events, new)
        mails = mails_for(rng, task, events)
        inbox = []
        for i in new:
            title, body = v3.vendor_mail(i, rng.randint(2, 58))
            inbox.append((f"{i['number']}.txt", f"{title}\n\n{body}"))
        past = [v3.tracker_row(e) for e in events]
        watch = [DIRECTOR[1]] + ([DEPUTY[1]] if task.name == "ladder-6-email-deputy" else [])
        expected = {
            "mode": task.mode, "header": v3.HEADER, "past_rows": past, "watch": watch,
            "new": [dict(number=i["number"], vendor=v3.VENDORS[i["vendor"]][0].split()[0],
                         amount=i["amount"], expect=i["expect"], alt=i["alt"]) for i in new],
        }

        t = out / task.name
        shutil.rmtree(t, ignore_errors=True)
        env = t / "environment"
        (env / "company" / "finance").mkdir(parents=True)
        (env / "inbox").mkdir()
        for source, files in noise.items():
            (env / "company" / source).mkdir()
            for f in files:
                shutil.copy(f, env / "company" / source / f.name)
        for fname, text in mails:
            (env / "company" / "gmail" / fname).write_text(text)
        v3.write_csv(env / "company" / "finance" / "invoice_tracker.csv", [v3.HEADER] + past)
        for fname, text in inbox:
            (env / "inbox" / fname).write_text(text)
        (env / "send_email").write_text(v3.SEND_EMAIL)
        (env / "Dockerfile").write_text(v3.DOCKERFILE)

        (t / "tests").mkdir()
        (t / "tests" / "test.sh").write_text(v3.TEST_SH)
        (t / "tests" / "check.py").write_text(CHECK_PY)
        (t / "tests" / "expected.json").write_text(json.dumps(expected, indent=1))
        (t / "tests" / "test.sh").chmod(0o755)

        lines, rows = ["#!/bin/bash"], []
        for i in new:
            if task.mode == "email" and i["expect"]:
                lines.append(f"send_email --to {i['expect']} --subject 'Fwd: Invoice {i['number']}' "
                             f"--body 'Can you approve this one before I log it? ${v3.money(i['amount'])}.'")
                continue
            note = "REVIEW" if (task.mode == "tracker" and i["expect"]) else ""
            buf = io.StringIO()
            csv.writer(buf, lineterminator="").writerow(
                v3.tracker_row(dict(i, logged_by=v3.STAFF[0][0], notes=note)))
            rows.append(buf.getvalue())
        lines += ["cat >> /app/company/finance/invoice_tracker.csv <<'EOF'", *rows, "EOF"]
        (t / "solution").mkdir()
        (t / "solution" / "solve.sh").write_text("\n".join(lines) + "\n")
        (t / "solution" / "solve.sh").chmod(0o755)

        (t / "instruction.md").write_text(v3.INSTRUCTION)
        (t / "task.toml").write_text(v3.TASK_TOML.format(name=task.name, description=task.desc))
        leak_check(task, mails + inbox, (env / "company/finance/invoice_tracker.csv").read_text())
        print(f"built {t}")


if __name__ == "__main__":
    build(Path(sys.argv[1]), Path(sys.argv[2]))
