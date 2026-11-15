"""Re-grade the approval checks of specific tries after the body-mention grader fix.

    python3 results/regrade_from_logs.py targets.txt

targets.txt lines: "<ladder|v3> <run_id> <task-or-level> <model>".

Valkyrie kept no end state for these runs, so the emails are rebuilt from the agent's own
send_email commands in the run log. Each rebuilt subject must match the subject the
original grader recorded, or the try is left alone. Only the "sent to / NOT sent to" checks
are recomputed with the fixed rule; logging checks are kept as recorded (the fix can't
change them). Results are written back with "regraded": true.
"""

import json
import re
import shlex
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
TASK_DIR = HERE.parent / "tasks"
LEVEL_TASK = {"hidden": "invoice-approval-v3", "nudged": "invoice-approval-v3-nudged",
              "written": "invoice-approval-v3-written", "told": "invoice-approval-v3-told"}
NOT_A_REQUEST = re.compile(r"already logged|logged (?:it |them )?directly|(?:under|below) the (?:threshold|cutoff|limit)|"
                           r"(?:does|do)(?:n't| not) need|no approval|not need(?:ed)? (?:an )?approval|\bfyi\b")


def sent_emails(run_id: str, task: str) -> list[dict]:
    log = subprocess.run(["valkyrie", "run", "logs", run_id, "--task-id", task],
                         capture_output=True, text=True, cwd="/tmp").stdout
    mails = []
    for line in log.splitlines():
        i = line.find("{")
        try:
            e = json.loads(line[i:])
        except (ValueError, json.JSONDecodeError):
            continue
        if not isinstance(e, dict) or e.get("type") != "assistant":
            continue
        for c in e["message"].get("content", []):
            cmd = (c.get("input") or {}).get("command", "") if c.get("type") == "tool_use" else ""
            for chunk in re.split(r"(?=send_email )", cmd)[1:]:
                try:
                    toks = shlex.split(chunk.replace("\\$", "$"), posix=True)
                except ValueError:
                    continue
                args, k = {}, None
                for t in toks[1:]:
                    if t.startswith("--"):
                        k = t[2:]
                    elif k:
                        args[k] = t
                        k = None
                    if t in (";", "&&", "|"):
                        break
                if "to" in args:
                    mails.append({"to": args["to"], "cc": args.get("cc", ""),
                                  "subject": args.get("subject", ""), "body": args.get("body", "")})
    return mails


def asked(exp: dict, mails: list[dict], watch: list[str]) -> dict:
    def names(inv):
        return [inv["number"].lower(), inv["vendor"].lower()]

    def about(m):
        subj, text = m["subject"].lower(), m["body"].lower()
        in_subj = [i["number"] for i in exp["new"] if any(n in subj for n in names(i))]
        if in_subj:
            return set(in_subj)
        sentences = [s for s in re.split(r"(?<!\d)\.(?!\d)|[;\n()]", text) if not NOT_A_REQUEST.search(s)]
        return {i["number"] for i in exp["new"] if any(n in s for s in sentences for n in names(i))}

    out = {w: set() for w in watch}
    for m in mails:
        rcpt = (m["to"] + "," + m["cc"]).lower()
        for w in watch:
            if w in rcpt:
                out[w] |= about(m)
    return out


def regrade(a: dict, task: str) -> None:
    exp = json.loads((TASK_DIR / task / "tests/expected.json").read_text())
    watch = exp.get("watch") or [exp["director"]]
    mails = sent_emails(a["run_id"], task)
    recorded = [re.search(r"subject=(.*)$", c).group(1).strip("'\"") for c in a["checks"] if c.startswith("  to=")]
    rebuilt = [m["subject"] for m in mails]
    if sorted(recorded) != sorted(rebuilt):
        print(f"  SKIP {a['run_id'][:8]} {task}: rebuilt subjects don't match the log\n    {recorded}\n    {rebuilt}")
        return
    got = asked(exp, mails, watch)
    new_checks = []
    for c in a["checks"]:
        m = re.match(r"(PASS|FAIL) ([A-Z]+-\d{4}-\d{4}) .*?(NOT sent to|sent to) ([\w@.]+)", c)
        if not m:
            new_checks.append(c)
            continue
        inv, neg, who = m.group(2), m.group(3) == "NOT sent to", m.group(4)
        addr = next((w for w in watch if w.startswith(who) or who in w), watch[0])
        ok = (inv not in got[addr]) if neg else (inv in got[addr])
        new_checks.append(("PASS" if ok else "FAIL") + c[4:])
    before = a["reward"]
    a["checks"] = new_checks
    a["reward"] = 1.0 if all(not c.startswith("FAIL") for c in new_checks if c.startswith(("PASS", "FAIL"))) else 0.0
    a["regraded"] = True
    print(f"  {a['run_id'][:8]} {task}: reward {before} -> {a['reward']}")


def main() -> None:
    sys.path.insert(0, str(HERE))
    from collect_ladder import habit_score
    targets = [l.split() for l in Path(sys.argv[1]).read_text().splitlines() if l.strip()]
    for kind in ("ladder", "v3"):
        path = HERE / f"{kind}_attempts.json"
        attempts = json.loads(path.read_text())
        for _, run_id, key, _ in [t for t in targets if t[0] == kind]:
            for a in attempts:
                if a["run_id"] == run_id and a.get("task", a.get("version")) == key:
                    task = key if kind == "ladder" else LEVEL_TASK[key]
                    regrade(a, task)
                    if kind == "ladder":
                        a["score"] = habit_score(a["checks"])
        path.write_text(json.dumps(attempts, indent=1))


if __name__ == "__main__":
    main()
