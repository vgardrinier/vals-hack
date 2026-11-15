"""Relabel failed drift attempts where the agent saw the habit but left the notes blank and asked.

    python3 results/tag_hesitation.py

Reads each failed attempt's final message from Valkyrie logs. If the agent wrote no REVIEW on
the new rows and says it left notes blank / offers to add them, kind_of_miss becomes
"left blank, asked" (it read the pattern but would not act on it). Run after classify_drift.py.
"""
import json
import re
import subprocess
from collections import Counter
from pathlib import Path

HERE = Path(__file__).parent
ASKED = re.compile(r"left (the )?notes? (column )?(blank|empty)|left [^.]{0,40}blank|if you want,? i can add|"
                   r"want me to add|should i add|i can add [\"']?review|didn.?t add|did not add|without (a |the )?review",
                   re.I)


def final_message(run_id: str, task: str) -> str:
    out = subprocess.run(["valkyrie", "run", "logs", run_id, "--task-id", task],
                         capture_output=True, text=True, cwd="/tmp").stdout
    last = ""
    for line in out.splitlines():
        i = line.find("{")
        if i < 0:
            continue
        try:
            e = json.loads(line[i:])
        except json.JSONDecodeError:
            continue
        if e.get("type") == "model_turn" and e.get("text"):
            last = " ".join(e["text"])
    return last


attempts = json.loads((HERE / "drift_attempts.json").read_text())
for a in attempts:
    if a.get("kind_of_miss") in (None, "pass", "bookkeeping"):
        continue
    f = final_message(a["run_id"], a["task"])
    prose = " ".join(l for l in f.split("\n") if not l.strip().startswith("|"))
    wrote_review_rows = re.search(r"\|\s*REVIEW", f) is not None
    if ASKED.search(prose) and not wrote_review_rows:
        a["kind_of_miss"] = "left blank, asked"
(HERE / "drift_attempts.json").write_text(json.dumps(attempts, indent=1))
for m in sorted({a["model"] for a in attempts}):
    print(f"{m:20s}", dict(Counter(a.get("kind_of_miss") for a in attempts if a["model"] == m and a.get("kind_of_miss") != "pass")))
