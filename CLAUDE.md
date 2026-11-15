# vals-hack

Eval for Vals Hacks (track 1). See README.md for setup, build and run commands.

## Rules
- Never more than 5 Valkyrie runs in progress at once, across the whole team.
  Start runs only through `scripts/queue_runs.sh`, which enforces it.
- Every task ships with three levels (hidden / written in an email / told in the instruction).
  The told level must pass ~100% before hidden-level results count.
- Before any model run: generator self-checks pass, `gen/test_*_grader.py` passes, and the
  solution scores 1 in the real Docker box.
