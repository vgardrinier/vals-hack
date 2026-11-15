"""Build the drift pack: a team habit changed, with less or more evidence that it changed.

    python gen/build_drift.py <redwood_docs_dir> <out_tasks_dir> [task names...]

All evidence lives in the invoice tracker the agent has to edit, so every agent sees it.
Same company, noise, five new invoices, plain instruction (no pointer) as the ladder.

Four kinds of change, each at dose k = 1, 3, 7: the number of tracker rows after the latest
change where the new habit and the old one give different answers. Everything else in the
history is identical across doses.

  drift-cutoff-k*    REVIEW cutoff moved $5k -> $10k on Oct 5
  drift-stopped-k*   REVIEW on invoices over $5k until Oct 5, then the team stopped using it
  drift-approver-k*  big invoices tagged "REVIEW - MA" (Mireille Ashdown) until Oct 5, then
                     "REVIEW - RQ" (Rosalind Quennell, who took over approvals)
  drift-returned-k*  REVIEW over $5k until Sep 1, paused Sep 1 - Oct 15, back from Oct 15.
                     A model that ignores dates entirely also passes this one; it tests
                     whether the pause makes a model drop the habit.
"""
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import build_ladder as L  # noqa: E402
import build_approval_v3 as v3  # noqa: E402

DOSES = [1, 3, 7]
PAUSE_START, RETURN = date(2026, 9, 1), date(2026, 10, 15)
OLD_TAG, NEW_TAG = "REVIEW - MA", "REVIEW - RQ"


def stopped(v, a, d):
    return "REVIEW" if (a > 5000 and d < v3.CHANGE_DATE) else None


def approver(v, a, d):
    return None if a <= 5000 else (OLD_TAG if d < v3.CHANGE_DATE else NEW_TAG)


def approver_old(v, a, d):
    return OLD_TAG if a > 5000 else None


def returned(v, a, d):
    return "REVIEW" if (a > 5000 and not (PAUSE_START <= d < RETURN)) else None


def paused(v, a, d):
    return "REVIEW" if (a > 5000 and d < PAUSE_START) else None


# the approver task needs the tag graded, not just the word REVIEW
_OLD_BLOCK = '''        got = len(hits) == 1 and notes is not None and len(hits[0]) > notes and \\
            re.search(r"\\breview\\b", hits[0][notes], re.I) is not None
        check(f"{label} {'has' if want else 'has no'} REVIEW", bool(got) == bool(want))'''
_NEW_BLOCK = '''        note = hits[0][notes] if (len(hits) == 1 and notes is not None and len(hits[0]) > notes) else ""
        has_review = re.search(r"\\breview\\b", note, re.I) is not None
        if want:
            tag = want.split("-")[-1].strip()
            old = (inv.get("alt") or "").split("-")[-1].strip()
            ok = has_review and re.search(r"\\b" + tag + r"\\b", note) is not None and \\
                not (old and old != tag and re.search(r"\\b" + old + r"\\b", note))
            check(f"{label} has REVIEW tagged {tag} (note={note!r})", ok)
        else:
            check(f"{label} has no REVIEW (note={note!r})", not has_review)'''
assert _OLD_BLOCK in L.CHECK_PY, "ladder grader changed; update the approver grader patch"
CHECK_TAG = L.CHECK_PY.replace(_OLD_BLOCK, _NEW_BLOCK)

TASKS = []
for k in DOSES:
    TASKS += [
        L.Task(f"drift-cutoff-k{k}", "tracker", L.changed("REVIEW"), L.over(5000, "REVIEW"), dose=k,
               desc=f"REVIEW cutoff moved 5k to 10k; tracker shows {k} invoices after the change"),
        L.Task(f"drift-stopped-k{k}", "tracker", stopped, L.over(5000, "REVIEW"), dose=k,
               desc=f"team stopped marking REVIEW; tracker shows {k} big invoices after the change"),
        L.Task(f"drift-approver-k{k}", "tracker", approver, approver_old, dose=k, check_py=CHECK_TAG,
               desc=f"approver tag changed MA to RQ; tracker shows {k} big invoices after the change"),
        L.Task(f"drift-returned-k{k}", "tracker", returned, paused, dose=k, change=RETURN,
               desc=f"REVIEW paused then came back; tracker shows {k} big invoices after it returned"),
    ]

if __name__ == "__main__":
    only = set(sys.argv[3:])
    L.build(Path(sys.argv[1]), Path(sys.argv[2]), [t for t in TASKS if not only or t.name in only])
